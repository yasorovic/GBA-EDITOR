"""Génération de tiles de collision (pentes) pour un drag (sc,sr)→(ec,er) sur
la grille 8×8 de la scène. Pure géométrie (Bresenham + règles de pentes GBA),
sans dépendance UI — consommé par CollisionSlopeTool (cf. ui/scene_manager/canvas_tools.py).

Angle du drag         Résultat
───────────────────── ────────────────────────────────
Point (dx=dy=0)       TILE_SOLID (clic simple)
Horizontal (dy=0)     ligne TILE_SOLID (sol/plafond plat)
Vertical pur (dx=0)   colonne TILE_SOLID (mur)
Doux (|dx| > |dy|)    paires LO/HI (pente ~26°)
45° (|dx| == |dy|)    SLOPE_L / SLOPE_R selon direction
Raide (|dy| > |dx|)   paires HI/LO par colonne (~63°)
"""

from __future__ import annotations

from core.models.collision_tiles import (
    TILE_SOLID,
    TILE_SLOPE_L,
    TILE_SLOPE_L_HI,
    TILE_SLOPE_L_HI_INV,
    TILE_SLOPE_L_INV,
    TILE_SLOPE_L_LO,
    TILE_SLOPE_L_LO_INV,
    TILE_SLOPE_L_STEEP_HI,
    TILE_SLOPE_L_STEEP_HI_INV,
    TILE_SLOPE_L_STEEP_LO,
    TILE_SLOPE_L_STEEP_LO_INV,
    TILE_SLOPE_R,
    TILE_SLOPE_R_HI,
    TILE_SLOPE_R_HI_INV,
    TILE_SLOPE_R_INV,
    TILE_SLOPE_R_LO,
    TILE_SLOPE_R_LO_INV,
    TILE_SLOPE_R_STEEP_HI,
    TILE_SLOPE_R_STEEP_HI_INV,
    TILE_SLOPE_R_STEEP_LO,
    TILE_SLOPE_R_STEEP_LO_INV,
)

# Modes du trait de pente (sol ou plafond).
SLOPE_MODES = ("collision_slope", "collision_slope_inv")


def slope_tiles_for(mode: str, sc: int, sr: int, ec: int, er: int) -> list[tuple[int, int, int]]:
    """Génère les tiles le long du segment (sc,sr)→(ec,er), selon `mode`
    ("collision_slope" = sol, "collision_slope_inv" = plafond)."""
    inv = mode == "collision_slope_inv"
    dx, dy = ec - sc, er - sr

    if dx == 0 and dy == 0:
        return [(sc, sr, TILE_SOLID)]

    adx, ady = abs(dx), abs(dy)
    going_right = dx >= 0
    going_up = dy < 0  # Y croît vers le bas en coords écran

    # ── Sol/plafond plat → SOLID ──────────────────────────────
    if dy == 0:
        return _bresenham(sc, sr, ec, er, TILE_SOLID)

    # ── Mur vertical pur → SOLID ──────────────────────────────
    if dx == 0:
        return _bresenham(sc, sr, ec, er, TILE_SOLID)

    # Tile 45° sélectionné selon la direction
    if not inv:
        base45 = (
            (TILE_SLOPE_L if going_up else TILE_SLOPE_R)
            if going_right
            else (TILE_SLOPE_R if going_up else TILE_SLOPE_L)
        )
    else:
        base45 = (
            (TILE_SLOPE_L_INV if going_up else TILE_SLOPE_R_INV)
            if going_right
            else (TILE_SLOPE_R_INV if going_up else TILE_SLOPE_L_INV)
        )

    # ── Pente douce ~26° : |dx| > |dy| → paires LO/HI ────────
    if adx > ady:
        return _gentle_slope_rows(
            sc, sr, ec, er, going_right, going_up, inv, base45
        )

    # ── Pente 45° : |dx| == |dy| → Bresenham diag ────────────
    if adx == ady:
        return _bresenham(sc, sr, ec, er, base45)

    # ── Pente raide : |dy| > |dx| → paires HI/LO par colonne ──
    if not inv:
        if going_right:
            hi = TILE_SLOPE_L_STEEP_HI if going_up else TILE_SLOPE_R_STEEP_HI
            lo = TILE_SLOPE_L_STEEP_LO if going_up else TILE_SLOPE_R_STEEP_LO
        else:
            hi = TILE_SLOPE_R_STEEP_HI if going_up else TILE_SLOPE_L_STEEP_HI
            lo = TILE_SLOPE_R_STEEP_LO if going_up else TILE_SLOPE_L_STEEP_LO
    else:
        # INV : HI_INV = petit triangle en BAS de la paire plafond,
        #       LO_INV = grand quad en HAUT → rôles HI/LO inversés vs non-INV.
        # Le miroir vertical inverse aussi la famille L/R (comme dans _gentle_slope_rows) :
        #   non-INV right+up → L  |  INV right+up → R
        if going_right:
            hi = (
                TILE_SLOPE_R_STEEP_LO_INV if going_up else TILE_SLOPE_L_STEEP_LO_INV
            )
            lo = (
                TILE_SLOPE_R_STEEP_HI_INV if going_up else TILE_SLOPE_L_STEEP_HI_INV
            )
        else:
            hi = (
                TILE_SLOPE_L_STEEP_LO_INV if going_up else TILE_SLOPE_R_STEEP_LO_INV
            )
            lo = (
                TILE_SLOPE_L_STEEP_HI_INV if going_up else TILE_SLOPE_R_STEEP_HI_INV
            )
    return _steep_slope(sc, sr, ec, er, hi, lo)


def _gentle_slope_rows(
    sc: int,
    sr: int,
    ec: int,
    er: int,
    going_right: bool,
    going_up: bool,
    inv: bool,
    corner_tile: int,  # tile 45° utilisé pour les rangées à 1 col et le 3e col
) -> list[tuple[int, int, int]]:
    """
    Slope douce (|dx| > |dy| > 0) : paires LO/HI groupées par rangée.

    Vue de gauche à droite :
      SLOPE_L (ascendant L→R)  : col gauche = LO (petit), col droite = HI (grand)
      SLOPE_R (descendant L→R) : col gauche = HI (grand), col droite = LO (petit)

    Rangée 1 col  → corner_tile (tile 45°, jamais de demi-paire seule)
    Rangée 2 cols → LO + HI
    Rangée 3 cols → LO + HI + corner_tile
    Rangée 4+     → LO + HI + corner_tile (cols supplémentaires ignorées)
    """
    is_l = (going_right and going_up) or (not going_right and not going_up)

    if not inv:
        left_t = TILE_SLOPE_L_LO if is_l else TILE_SLOPE_R_HI
        right_t = TILE_SLOPE_L_HI if is_l else TILE_SLOPE_R_LO
    else:
        # Plafond : familles L/R échangées — SR_HI+SR_LO ascendant, SL_LO+SL_HI descendant
        left_t = TILE_SLOPE_R_HI_INV if is_l else TILE_SLOPE_L_LO_INV
        right_t = TILE_SLOPE_R_LO_INV if is_l else TILE_SLOPE_L_HI_INV

    # Bresenham → regrouper par rangée
    adx = abs(ec - sc)
    ady = abs(er - sr)
    sx = 1 if ec >= sc else -1
    sy = 1 if er >= sr else -1
    err = adx - ady
    x, y = sc, sr
    rows: dict[int, list[int]] = {}
    while True:
        rows.setdefault(y, []).append(x)
        if x == ec and y == er:
            break
        e2 = 2 * err
        if e2 > -ady:
            err -= ady
            x += sx
        if e2 < adx:
            err += adx
            y += sy

    sorted_rows = sorted(rows.keys())
    tiles: list[tuple[int, int, int]] = []

    for row_y in sorted_rows:
        cols = sorted(set(rows[row_y]))
        n = len(cols)
        if n == 1:
            # Impossible de placer une paire complète → tile 45° propre
            tiles.append((cols[0], row_y, corner_tile))
        elif n == 2:
            tiles.append((cols[0], row_y, left_t))
            tiles.append((cols[1], row_y, right_t))
        else:
            # 1 seule paire LO+HI + 1 tile 45° max — jamais de SOLID, jamais 2 paires
            tiles.append((cols[0], row_y, left_t))
            tiles.append((cols[1], row_y, right_t))
            tiles.append((cols[2], row_y, corner_tile))
            # cols[3+] volontairement ignorées

    return tiles


def _steep_slope(
    sc: int,
    sr: int,
    ec: int,
    er: int,
    tile_hi: int,
    tile_lo: int,
) -> list[tuple[int, int, int]]:
    """
    Pente raide (|dy| > |dx|) : paires HI/LO par colonne.
    HI = petit triangle (tête visuelle de la colonne).
    LO = grand quadrilatère (queue visuelle).
    Bresenham axe Y : garantit que chaque colonne accumule ses rangées
    avant de passer à la suivante (ex. ratio 1:2 → col 0 = HI+LO, col 1 = HI).
    """
    adx = abs(ec - sc)
    ady = abs(er - sr)
    sx = 1 if ec >= sc else -1
    sy = 1 if er >= sr else -1
    err = adx - ady
    x, y = sc, sr
    tiles: list[tuple[int, int, int]] = []
    prev_col: int | None = None
    row_in_col = 0
    while True:
        if x != prev_col:
            row_in_col = 0
        # HI = tile du haut visuel, LO = tile du bas visuel
        # going down (sy>0) : row_in_col==0 = haut → HI
        # going up  (sy<0) : row_in_col==0 = bas  → LO
        tile = tile_hi if (row_in_col == 0) == (sy > 0) else tile_lo
        tiles.append((x, y, tile))
        row_in_col += 1
        prev_col = x
        if x == ec and y == er:
            break
        e2 = 2 * err
        if e2 > -ady:
            err -= ady
            x += sx
        if e2 < adx:
            err += adx
            y += sy
    return tiles


def _bresenham(
    sc: int,
    sr: int,
    ec: int,
    er: int,
    tile_type: int,
) -> list[tuple[int, int, int]]:
    """Ligne de Bresenham → liste (col, row, tile_type)."""
    adx = abs(ec - sc)
    ady = abs(er - sr)
    sx = 1 if ec >= sc else -1
    sy = 1 if er >= sr else -1
    err = adx - ady
    x, y = sc, sr
    seen: set[tuple[int, int]] = set()
    tiles: list[tuple[int, int, int]] = []
    while True:
        if (x, y) not in seen:
            seen.add((x, y))
            tiles.append((x, y, tile_type))
        if x == ec and y == er:
            break
        e2 = 2 * err
        if e2 > -ady:
            err -= ady
            x += sx
        if e2 < adx:
            err += adx
            y += sy
    return tiles
