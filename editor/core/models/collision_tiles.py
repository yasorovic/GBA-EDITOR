"""Le format d'une tuile de COLLISION : ses 22 types, et leur géométrie.

Module feuille — il n'importe rien. Même rôle que `tile_codec.py` pour la tuile
graphique : la forme d'une tuile de collision est réclamée par le modèle de
scène, par l'outil de peinture, par le canvas qui la dessine et par le codegen
qui l'émet en C. Tant qu'elle vivait dans le canvas, la physique du jeu et le
dessin de l'éditeur étaient deux écritures indépendantes de la même chose,
libres de diverger au premier ajustement.

## Une tuile = une droite et un côté

Chacune des 22 tuiles se décrit par la **droite de sa surface** et le côté où se
trouve la matière. La droite est donnée par ses ordonnées en `x=0` et `x=8`, en
pixels dans la tuile ; elle a le droit de sortir de la tuile — c'est ce qui
décrit les pentes raides, dont la surface ne traverse que la moitié de la
largeur, le reste de la colonne étant plein ou vide selon le côté.

    SLOPE_L (45° montant)      y0=8  y1=0   sol      la matière est SOUS la droite
    SLOPE_L_LO (26°, gauche)   y0=8  y1=4   sol
    R_STEEP_HI (63°, haut)     y0=0  y1=16  sol      sort par le bas dès x=4
    L_INV (45° plafond)        y0=8  y1=0   plafond  la matière est AU-DESSUS

De là dérivent les deux consommateurs, et rien n'est écrit deux fois :

- `polygon()` — la forme exacte, pour le dessin. C'est le carré de la tuile
  découpé par la droite, donc jamais une approximation ;
- `column_surfaces()` — l'ordonnée de la surface pour chacune des 8 colonnes de
  pixels, ce que le runtime lit pour poser un acteur dessus.
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────
#  Types de tuiles
# ──────────────────────────────────────────────────────────────────

TILE_EMPTY      = 0   # passable
TILE_SOLID      = 1   # bloc plein
TILE_SLOPE_L    = 2   # ◥  45° sol montant  L→R
TILE_SLOPE_R    = 3   # ◤  45° sol descendant L→R
TILE_SLOPE_L_LO = 4   # ◢  ~26° sol montant, tile gauche (bas)
TILE_SLOPE_L_HI = 5   # ◥½ ~26° sol montant, tile droite (haut)
TILE_SLOPE_R_LO = 6   # ◣  ~26° sol descendant, tile droite (bas)
TILE_SLOPE_R_HI = 7   # ◤½ ~26° sol descendant, tile gauche (haut)
# Plafond — miroir vertical des sols
TILE_SLOPE_L_INV    = 8   # ◣  45° plafond montant  L→R
TILE_SLOPE_R_INV    = 9   # ◢  45° plafond descendant L→R
TILE_SLOPE_L_LO_INV = 10  # ~26° plafond montant, tile gauche
TILE_SLOPE_L_HI_INV = 11  # ~26° plafond montant, tile droite
TILE_SLOPE_R_LO_INV = 12  # ~26° plafond descendant, tile droite
TILE_SLOPE_R_HI_INV = 13  # ~26° plafond descendant, tile gauche
# Pentes raides sol (>45°, X=1 Y=2) — paires HI (petit triangle) + LO (grand quadrilatère)
TILE_SLOPE_R_STEEP_HI     = 14  # ~63° sol descendant L→R, tile haut (petit triangle gauche)
TILE_SLOPE_R_STEEP_LO     = 15  # ~63° sol descendant L→R, tile bas  (grand quadrilatère gauche)
TILE_SLOPE_L_STEEP_HI     = 16  # ~63° sol montant  L→R, tile haut (petit triangle droit)
TILE_SLOPE_L_STEEP_LO     = 17  # ~63° sol montant  L→R, tile bas  (grand quadrilatère droit)
# Pentes raides plafond (miroir vertical)
TILE_SLOPE_R_STEEP_HI_INV = 18  # ~63° plafond descendant L→R, tile bas  (petit triangle gauche)
TILE_SLOPE_R_STEEP_LO_INV = 19  # ~63° plafond descendant L→R, tile haut (grand quadrilatère gauche)
TILE_SLOPE_L_STEEP_HI_INV = 20  # ~63° plafond montant  L→R, tile bas  (petit triangle droit)
TILE_SLOPE_L_STEEP_LO_INV = 21  # ~63° plafond montant  L→R, tile haut (grand quadrilatère droit)

# Tuiles à SENS UNIQUE : une face plate qu'on ne franchit que dans un sens. Le nom
# dit la NORMALE, le côté d'où l'on vient se poser : ONEWAY_UP se traverse par
# en dessous et par les côtés, et porte par le dessus (la plateforme classique).
# Quatre tuiles et non une : la gravité a quatre sens, et « le haut » n'est pas
# toujours l'axe Y négatif.
TILE_ONEWAY_UP    = 22   # face en HAUT de la tuile
TILE_ONEWAY_DOWN  = 23   # face en BAS de la tuile
TILE_ONEWAY_LEFT  = 24   # face sur le bord GAUCHE
TILE_ONEWAY_RIGHT = 25   # face sur le bord DROIT

COLLISION_TILE_SIZE = 8   # pixels par tile de collision

# ──────────────────────────────────────────────────────────────────
#  Familles — ce que le runtime a besoin de distinguer
# ──────────────────────────────────────────────────────────────────

KIND_EMPTY   = 0   # rien
KIND_SOLID   = 1   # plein : le SEUL type qui repousse horizontalement
KIND_FLOOR   = 2   # matière sous la droite — on marche dessus
KIND_CEILING = 3   # matière au-dessus — on s'y cogne la tête
KIND_ONEWAY  = 4   # face plate franchissable dans un sens (cf. `oneway_normal`)

# Sens de la normale d'une tuile à sens unique, tel que le runtime le lit :
# 0 aucune, 1 haut, 2 bas, 3 gauche, 4 droite.
ONEWAY_NONE, ONEWAY_UP, ONEWAY_DOWN, ONEWAY_LEFT, ONEWAY_RIGHT = 0, 1, 2, 3, 4
_ONEWAY_DIR = {
    TILE_ONEWAY_UP: ONEWAY_UP, TILE_ONEWAY_DOWN: ONEWAY_DOWN,
    TILE_ONEWAY_LEFT: ONEWAY_LEFT, TILE_ONEWAY_RIGHT: ONEWAY_RIGHT,
}
ONEWAY_STRIP = 2   # épaisseur DESSINÉE de la face, en pixels (la collision est la ligne)

# (y en x=0, y en x=8, famille). Le sens de la droite n'a pas d'importance :
# seuls comptent le côté plein et les deux ordonnées.
_GEOMETRY: dict[int, tuple[int, int, int]] = {
    TILE_EMPTY: (0, 0, KIND_EMPTY),
    TILE_SOLID: (0, 0, KIND_SOLID),

    TILE_SLOPE_L:    (8, 0, KIND_FLOOR),
    TILE_SLOPE_R:    (0, 8, KIND_FLOOR),
    TILE_SLOPE_L_LO: (8, 4, KIND_FLOOR),
    TILE_SLOPE_L_HI: (4, 0, KIND_FLOOR),
    TILE_SLOPE_R_LO: (4, 8, KIND_FLOOR),
    TILE_SLOPE_R_HI: (0, 4, KIND_FLOOR),

    TILE_SLOPE_L_INV:    (8, 0, KIND_CEILING),
    TILE_SLOPE_R_INV:    (0, 8, KIND_CEILING),
    TILE_SLOPE_L_LO_INV: (0, 4, KIND_CEILING),
    TILE_SLOPE_L_HI_INV: (4, 8, KIND_CEILING),
    TILE_SLOPE_R_LO_INV: (4, 0, KIND_CEILING),
    TILE_SLOPE_R_HI_INV: (8, 4, KIND_CEILING),

    # Raides : la droite sort de la tuile — 16 et -8 sont volontaires.
    TILE_SLOPE_R_STEEP_HI: (0, 16, KIND_FLOOR),
    TILE_SLOPE_R_STEEP_LO: (-8, 8, KIND_FLOOR),
    TILE_SLOPE_L_STEEP_HI: (16, 0, KIND_FLOOR),
    TILE_SLOPE_L_STEEP_LO: (8, -8, KIND_FLOOR),

    TILE_SLOPE_R_STEEP_HI_INV: (8, -8, KIND_CEILING),
    TILE_SLOPE_R_STEEP_LO_INV: (16, 0, KIND_CEILING),
    TILE_SLOPE_L_STEEP_HI_INV: (-8, 8, KIND_CEILING),
    TILE_SLOPE_L_STEEP_LO_INV: (0, 16, KIND_CEILING),

    TILE_ONEWAY_UP:    (0, 0, KIND_ONEWAY),
    TILE_ONEWAY_DOWN:  (0, 0, KIND_ONEWAY),
    TILE_ONEWAY_LEFT:  (0, 0, KIND_ONEWAY),
    TILE_ONEWAY_RIGHT: (0, 0, KIND_ONEWAY),
}

TILE_COUNT = len(_GEOMETRY)


def kind_of(tile: int) -> int:
    return _GEOMETRY.get(tile, (0, 0, KIND_EMPTY))[2]


def oneway_dir(tile: int) -> int:
    """Le sens de la face d'une tuile à sens unique (`ONEWAY_*`), 0 pour les autres."""
    return _ONEWAY_DIR.get(tile, ONEWAY_NONE)


def surface_y(tile: int, x: int) -> int:
    """Ordonnée de la surface dans la colonne de pixels `x`, bornée à [0, 8].

    Pour un SOL, la matière va de cette ordonnée au bas de la tuile : 8 = colonne
    vide, 0 = colonne pleine. Pour un PLAFOND c'est l'inverse — la matière va du
    haut jusque-là, donc 0 = colonne vide."""
    y0, y1, kind = _GEOMETRY.get(tile, (0, 0, KIND_EMPTY))
    if kind == KIND_SOLID:
        return 0                    # matière du haut au bas : surface au sommet
    if kind in (KIND_EMPTY, KIND_ONEWAY):
        return COLLISION_TILE_SIZE      # la face à sens unique n'est pas une surface de marche
    y = y0 + ((y1 - y0) * x) // COLLISION_TILE_SIZE
    return max(0, min(COLLISION_TILE_SIZE, y))


def surface_normal(tile: int) -> tuple[float, float, float, float] | None:
    """Le point milieu de la surface d'une tuile et sa normale unitaire : `(x, y, nx, ny)`, repère de la tuile (y vers le
    bas), la normale sortant de la matière. `None` pour une tuile vide ou pleine : les faces d'un bloc plein dépendent de
    ses voisines, c'est à l'appelant de les poser.

    Pour une pente, le point est le milieu de la partie de la droite qui traverse la tuile (une pente raide n'en
    traverse que la moitié). Pour une face à sens unique, c'est le centre de sa face et la normale est son sens."""
    y0, y1, kind = _GEOMETRY.get(tile, (0, 0, KIND_EMPTY))
    T = COLLISION_TILE_SIZE
    if kind == KIND_ONEWAY:
        n = oneway_dir(tile)
        return {ONEWAY_UP: (T / 2, 0, 0, -1), ONEWAY_DOWN: (T / 2, T, 0, 1),
                ONEWAY_LEFT: (0, T / 2, -1, 0), ONEWAY_RIGHT: (T, T / 2, 1, 0)}[n]
    if kind not in (KIND_FLOOR, KIND_CEILING):
        return None
    dy = y1 - y0
    lo, hi = 0.0, 1.0
    if dy:
        ta, tb = (0 - y0) / dy, (T - y0) / dy
        lo, hi = max(lo, min(ta, tb)), min(hi, max(ta, tb))
    t = (lo + hi) / 2
    nx, ny = (dy, -T) if kind == KIND_FLOOR else (-dy, T)
    length = (nx * nx + ny * ny) ** 0.5
    return (T * t, y0 + dy * t, nx / length, ny / length)


def speed_scale(tile: int) -> int:
    """Le cosinus de la pente, en virgule fixe 8 bits (256 = plat).

    Marcher sur une pente parcourt `√(1 + p²)` fois plus de distance qu'à plat
    pour le même pas horizontal — 114 % à 26°, 141 % à 45°, 224 % à 63°. C'est
    de ce facteur que le moteur réduit le pas pour que la vitesse soit constante
    LE LONG du sol, ce qu'on entend par « vitesse de marche ».

    Précalculé ici plutôt qu'au runtime : la GBA n'a pas de racine carrée, et la
    valeur ne dépend que de la géométrie déjà décrite plus haut."""
    y0, y1, kind = _GEOMETRY.get(tile, (0, 0, KIND_EMPTY))
    if kind not in (KIND_FLOOR, KIND_CEILING):
        return 256
    rise = abs(y1 - y0) / COLLISION_TILE_SIZE       # px de montée par px parcouru
    return int(round(256 / ((1 + rise * rise) ** 0.5)))


def column_surfaces(tile: int) -> list[int]:
    """Les 8 ordonnées de surface d'une tuile — ce que le codegen émet en C."""
    return [surface_y(tile, x) for x in range(COLLISION_TILE_SIZE)]


def polygon(tile: int) -> list[tuple[int, int]]:
    """La forme EXACTE de la matière, en coordonnées locales à la tuile.

    Le carré de la tuile découpé par la droite de surface (Sutherland-Hodgman) :
    aucune approximation, et les cas dégénérés — colonne vide, colonne pleine —
    tombent d'eux-mêmes sans être écrits."""
    y0, y1, kind = _GEOMETRY.get(tile, (0, 0, KIND_EMPTY))
    T = COLLISION_TILE_SIZE
    if kind == KIND_EMPTY:
        return []
    if kind == KIND_SOLID:
        return [(0, 0), (T, 0), (T, T), (0, T)]
    if kind == KIND_ONEWAY:
        # Seule la bande côté face est dessinée : la matière n'existe que sur la
        # face, le reste de la tuile se traverse.
        n, w = oneway_dir(tile), ONEWAY_STRIP
        if n == ONEWAY_UP:
            return [(0, 0), (T, 0), (T, w), (0, w)]
        if n == ONEWAY_DOWN:
            return [(0, T - w), (T, T - w), (T, T), (0, T)]
        if n == ONEWAY_LEFT:
            return [(0, 0), (w, 0), (w, T), (0, T)]
        return [(T - w, 0), (T, 0), (T, T), (T - w, T)]

    def line_y(x: float) -> float:
        return y0 + (y1 - y0) * x / T

    def inside(pt) -> bool:
        x, y = pt
        return (y >= line_y(x)) if kind == KIND_FLOOR else (y <= line_y(x))

    def cross(a, b):
        """Intersection du segment a→b avec la droite (les deux sont linéaires,
        donc leur écart l'est aussi : une simple interpolation suffit)."""
        (ax, ay), (bx, by) = a, b
        da, db = ay - line_y(ax), by - line_y(bx)
        t = da / (da - db)
        return (ax + (bx - ax) * t, ay + (by - ay) * t)

    out: list[tuple[float, float]] = []
    square = [(0, 0), (T, 0), (T, T), (0, T)]
    for i, cur in enumerate(square):
        prev = square[i - 1]
        if inside(cur):
            if not inside(prev):
                out.append(cross(prev, cur))
            out.append(cur)
        elif inside(prev):
            out.append(cross(prev, cur))

    # Sommets confondus : le découpage en produit dès que la droite passe par un
    # coin du carré, ce qui est le cas de la moitié des pentes.
    pts: list[tuple[int, int]] = []
    for x, y in out:
        p = (int(round(x)), int(round(y)))
        if not pts or p != pts[-1]:
            pts.append(p)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts if len(pts) >= 3 else []
