"""core/bg_tile_merge.py — fusion des tuiles d'un fond tuilé jusqu'à une cible.

Le budget de tuiles (512 en 4bpp, 256 en 8bpp par charblock, 1024 au plus : l'index
de tuile tient sur 10 bits) est ce qui fait qu'une photo ne rentre pas. La
déduplication exacte ne suffit pas — une photo n'a presque pas de tuiles
identiques. On fusionne donc les tuiles qui se ressemblent, avec perte.

Quelles tuiles garder ? Pas « les plus employées » : sur une photo presque toutes le
sont une fois, et l'égalité se tranche alors par l'ordre de balayage — le bas de
l'image disparaissait d'abord. On regroupe à la place par **plus faible perte**
(agglomération de Ward) : à chaque pas, on fusionne les deux groupes dont la
fusion coûte le moins d'écart visuel, coût pondéré par le nombre de cases que
couvrent les groupes. Les zones lisses (ciel, mer) se fondent en premier, le détail
est gardé, et la perte se répartit sur toute l'image. Chaque groupe est représenté
par sa tuile la plus centrale.

Le calcul se fait sur l'APPARENCE rendue (couleurs réelles, retournements compris)
et dans un espace qui pèse la luminance plus que la teinte, pas sur les index : deux
tuiles de banques différentes se comparent sur ce que l'écran montrera. Une case
renvoyée reprend la banque et les retournements de la tuile choisie — elle reste
valide quelle que soit sa banque d'origine.
"""
from __future__ import annotations

from collections import Counter

from core.models.tile_codec import flip_h, flip_v

_CHUNK = 256          # cases comparées par passe : borne la mémoire des matrices de distances
MAX_TILES = 6000      # au-delà, la matrice de coûts (carrée) ne tient plus raisonnablement

# Poids de (Y, Cb, Cr, alpha) : l'œil voit la luminance bien mieux que la teinte.
_WEIGHTS = (1.0, 0.6, 0.6, 1.0)


def _flip(grid, fh: bool, fv: bool):
    """La grille telle que la case la montre — MÊME opération que le rendu
    (`tile_codec`), pas une réécriture : sinon la fusion et l'écran divergeraient."""
    grid = tuple(grid)
    if fh:
        grid = flip_h(grid)
    if fv:
        grid = flip_v(grid)
    return grid


def _appearance(grid, pal_rgb, fh: bool, fv: bool) -> list:
    """64 pixels RGBA à plat (256 valeurs) : ce que la case montrera. L'index 0 est
    transparent — sa différence avec un pixel opaque pèse autant qu'un noir/blanc."""
    out: list = []
    for idx in _flip(grid, fh, fv):
        if idx == 0 or idx > len(pal_rgb):
            out += (0, 0, 0, 0)
        else:
            r, g, b = pal_rgb[idx - 1]
            out += (r, g, b, 255)
    return out


def _perceptual(np, rows):
    """(n, 256) RGBA → (n, 256) YCbCr pondéré + alpha : l'espace où l'on mesure."""
    a = np.asarray(rows, dtype=np.float32).reshape(len(rows), 64, 4)
    r, g, b, alpha = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = (b - y) * 0.564
    cr = (r - y) * 0.713
    out = np.stack([y * _WEIGHTS[0], cb * _WEIGHTS[1], cr * _WEIGHTS[2],
                    alpha * _WEIGHTS[3]], axis=-1)
    return out.reshape(len(rows), 256)


def _ward_groups(np, vectors, weights, target: int) -> list:
    """Regroupe `vectors` (u, d) en `target` groupes par plus faible coût de Ward
    (Δ(i,j) = ni·nj/(ni+nj) · |ci−cj|²). Renvoie, par groupe, la liste des indices
    membres.

    O(u²) en mémoire et en temps : la matrice des coûts est tenue à jour par la
    formule de Lance–Williams, et seules les lignes dont le meilleur voisin vient
    de disparaître sont recalculées."""
    u = len(vectors)
    n = np.asarray(weights, dtype=np.float64)
    cen = vectors.astype(np.float64)
    sq = (cen * cen).sum(axis=1)
    d2 = np.maximum(sq[:, None] + sq[None, :] - 2.0 * (cen @ cen.T), 0.0)
    cost = (n[:, None] * n[None, :] / (n[:, None] + n[None, :])) * d2
    inf = np.inf
    np.fill_diagonal(cost, inf)
    members = [[i] for i in range(u)]
    alive = np.ones(u, dtype=bool)
    row_arg = cost.argmin(axis=1)
    row_min = cost[np.arange(u), row_arg]

    for _ in range(u - target):
        i = int(row_min.argmin())
        j = int(row_arg[i])
        if i > j:
            i, j = j, i
        ni, nj = n[i], n[j]
        dij = cost[i, j]
        # Lance–Williams pour Ward : coût de (i ∪ j) avec chaque autre groupe k.
        nk = n
        new = ((nk + ni) * cost[:, i] + (nk + nj) * cost[:, j] - nk * dij) / (nk + ni + nj)
        new[~alive] = inf
        new[i] = inf
        new[j] = inf
        cen[i] = (ni * cen[i] + nj * cen[j]) / (ni + nj)
        n[i] = ni + nj
        members[i] += members[j]
        members[j] = []
        alive[j] = False
        cost[:, i] = new
        cost[i, :] = new
        cost[:, j] = inf
        cost[j, :] = inf
        row_min[j] = inf
        row_arg[j] = j
        # Lignes à jour : soit la nouvelle colonne fait mieux, soit leur meilleur
        # voisin était i ou j — alors on rescanne la ligne entière.
        better = new < row_min
        row_min[better] = new[better]
        row_arg[better] = i
        stale = np.where(alive & ~better & ((row_arg == i) | (row_arg == j)))[0]
        stale = np.append(stale, i)
        for k in stale:
            a = int(cost[k].argmin())
            row_arg[k], row_min[k] = a, cost[k, a]
    return [m for m in members if m], cen[alive]


def merge_tiles(tiles: list, cells: list, pal_rgb: list, target: int):
    """`tiles` : grilles d'index (64 entiers) ; `cells` : (tuile, banque, flip_h,
    flip_v) par case ; `pal_rgb[banque]` : couleurs RGB de l'index 1 à N.

    Renvoie (tiles, cells, fusionnées) — le nombre de tuiles retirées. `target` <= 0
    ou déjà atteint : rien ne change. Sans numpy, ou au-delà de `MAX_TILES` tuiles à
    regrouper, rien ne change non plus."""
    usage = Counter(tid for tid, _pb, _fh, _fv in cells)
    if target <= 0 or len(usage) <= target or len(usage) > MAX_TILES:
        return tiles, cells, 0
    try:
        import numpy as np
    except ImportError:
        return tiles, cells, 0

    # Chaque tuile est jugée sur la façon dont elle est le plus souvent montrée.
    tids = sorted(usage)
    main: dict = {}
    for tid, pb, fh, fv in cells:
        main.setdefault(tid, Counter())[(pb, fh, fv)] += 1
    vec = _perceptual(np, [
        _appearance(tiles[tid], pal_rgb[main[tid].most_common(1)[0][0][0]],
                    *main[tid].most_common(1)[0][0][1:]) for tid in tids])
    groups, centroids = _ward_groups(np, vec, [usage[t] for t in tids], target)

    # Une tuile par groupe : celle qui ressemble le plus à son centre.
    keep = set()
    for members, centre in zip(groups, centroids):
        best = min(members, key=lambda m: float(((vec[m] - centre) ** 2).sum()))
        keep.add(tids[best])

    # Meublé de ce qu'on garde : chaque (tuile, banque) réellement employée, sous
    # ses quatre retournements.
    hay_keys: list = []
    hay_rows: list = []
    seen: set = set()
    for tid, pb, _fh, _fv in cells:
        if tid in keep and (tid, pb) not in seen:
            seen.add((tid, pb))
            for fh in (False, True):
                for fv in (False, True):
                    hay_keys.append((tid, pb, fh, fv))
                    hay_rows.append(_appearance(tiles[tid], pal_rgb[pb], fh, fv))
    hay = _perceptual(np, hay_rows)
    hay_sq = (hay * hay).sum(axis=1)

    # Ce qu'on remplace : chaque apparence distincte d'une case pointant une tuile
    # abandonnée — calculée une fois, quel que soit le nombre de cases. Chacune va à
    # la plus proche des variantes gardées, pas forcément celle de son groupe.
    needles: dict = {}
    for tid, pb, fh, fv in cells:
        if tid not in keep and (tid, pb, fh, fv) not in needles:
            needles[(tid, pb, fh, fv)] = _appearance(tiles[tid], pal_rgb[pb], fh, fv)
    need_keys = list(needles)
    need = _perceptual(np, [needles[k] for k in need_keys])

    choice: dict = {}
    for start in range(0, len(need_keys), _CHUNK):
        block = need[start:start + _CHUNK]
        dist = (block * block).sum(axis=1)[:, None] + hay_sq[None, :] - 2.0 * block @ hay.T
        for key, best in zip(need_keys[start:start + _CHUNK], dist.argmin(axis=1)):
            choice[key] = hay_keys[int(best)]

    renumber = {tid: n for n, tid in enumerate(sorted(keep))}
    new_cells = []
    for cell in cells:
        tid, pb, fh, fv = choice.get(cell, cell)
        new_cells.append((renumber[tid], pb, fh, fv))
    return [tiles[tid] for tid in sorted(keep)], new_cells, len(usage) - len(keep)
