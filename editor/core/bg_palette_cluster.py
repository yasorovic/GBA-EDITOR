"""core/bg_palette_cluster.py — répartir les tuiles d'un fond entre N sous-palettes.

Le packing glouton exact (`bg_import._pack_palettes`) est sans perte tant que les
tuiles tiennent chacune en 15 couleurs ET que le nombre de palettes suffit — le cas
d'un pixel art. Une photo n'y est jamais : il en faut des centaines. Garder les 16
palettes les plus employées et renvoyer les autres tuiles vers « la plus proche »
laissait des zones entières (l'océan) sur des palettes sans leurs couleurs.

Ici on procède à l'envers, comme une quantification vectorielle : on regroupe les
tuiles qui se ressemblent (couleur moyenne, contraste), on bâtit UNE palette par
groupe depuis les pixels réels du groupe, puis on affine — chaque tuile passe à la
palette qui l'approche le mieux, les palettes sont refaites, quelques tours. Les
zones voisines et semblables (mer, ciel) partagent alors une palette taillée pour
elles.

Déterministe : aucune graine aléatoire, l'ordre des tuiles suffit à départager.
"""
from __future__ import annotations

import numpy as np

from core.models.gba_color import reduce_colors

_LLOYD_STEPS = 10      # itérations du regroupement initial (sur des vecteurs de 4 nombres)
_REFINE_ROUNDS = 3     # « palette → meilleure affectation → palette »


def _tile_arrays(tile_grids):
    """(rgb (T,64,3) float32, opaque (T,64) bool) — les pixels transparents (None)
    ne comptent ni dans les palettes ni dans l'erreur."""
    t = len(tile_grids)
    rgb = np.zeros((t, 64, 3), dtype=np.float32)
    opaque = np.zeros((t, 64), dtype=bool)
    for i, grid in enumerate(tile_grids):
        for p, c in enumerate(grid):
            if c is not None:
                rgb[i, p] = c
                opaque[i, p] = True
    return rgb, opaque


def _features(rgb, opaque):
    """Ce qui fait ressembler deux tuiles : couleur moyenne + contraste (écart-type
    de luminance). Une tuile sans pixel opaque a des zéros."""
    n = np.maximum(opaque.sum(axis=1), 1)[:, None]
    mean = (rgb * opaque[..., None]).sum(axis=1) / n
    lum = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    dev = np.sqrt(np.maximum(((lum - (lum * opaque).sum(axis=1, keepdims=True) / n) ** 2 * opaque)
                             .sum(axis=1) / n[:, 0], 0.0))
    return np.concatenate([mean, dev[:, None]], axis=1)


def _initial_groups(feat, k: int):
    """Regroupement des tuiles en `k` groupes : centres par plus grand écart
    (le premier = la tuile au plus près de la moyenne), puis quelques passes de
    Lloyd."""
    centre_of_mass = feat.mean(axis=0)
    first = int(((feat - centre_of_mass) ** 2).sum(axis=1).argmin())
    centres = [feat[first]]
    nearest = ((feat - centres[0]) ** 2).sum(axis=1)
    while len(centres) < k:
        nxt = int(nearest.argmax())
        if nearest[nxt] <= 0:
            break                                  # plus de tuiles distinctes
        centres.append(feat[nxt])
        nearest = np.minimum(nearest, ((feat - feat[nxt]) ** 2).sum(axis=1))
    centres = np.asarray(centres)
    assign = np.zeros(len(feat), dtype=np.int64)
    for _ in range(_LLOYD_STEPS):
        dist = ((feat[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        assign = dist.argmin(axis=1)
        for g in range(len(centres)):
            members = feat[assign == g]
            if len(members):
                centres[g] = members.mean(axis=0)
    return assign


def _build_palette(pixels, editable: int, method: str) -> list:
    """≤ `editable` couleurs représentant `pixels` (n, 3) uint8. Les pixels réels
    pèsent chacun pour un : les couleurs fréquentes (le gros de la mer) obtiennent
    ainsi plus de représentants que les rares."""
    if len(pixels) == 0:
        return []
    packed = (pixels[:, 0].astype(np.uint32) << 16) | (pixels[:, 1].astype(np.uint32) << 8) \
        | pixels[:, 2]
    values, counts = np.unique(packed, return_counts=True)
    order = np.argsort(-counts, kind="stable")
    colors = [((int(values[i]) >> 16) & 255, (int(values[i]) >> 8) & 255, int(values[i]) & 255)
              for i in order]
    weight = {c: int(counts[i]) for c, i in zip(colors, order)}
    if len(colors) <= editable:
        return colors
    if method == "median_cut":
        from PIL import Image
        img = Image.fromarray(pixels.reshape(1, -1, 3), "RGB")
        q = img.quantize(colors=editable, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette() or []
        used = sorted({i for _n, i in q.getcolors(maxcolors=256)})
        return [tuple(pal[3 * i:3 * i + 3]) for i in used]
    reps = reduce_colors(colors, weight, editable, method)
    return sorted(set(reps.values()), key=lambda c: -weight.get(c, 0))


class _Pixels:
    """Les pixels de l'image, vus par COULEUR DISTINCTE : une photo compte quelques
    milliers de couleurs pour des dizaines de milliers de pixels, et l'erreur d'une
    couleur contre une palette ne dépend pas de la case où elle se trouve."""

    def __init__(self, rgb, opaque):
        flat = rgb.reshape(-1, 3).astype(np.uint32)
        packed = (flat[:, 0] << 16) | (flat[:, 1] << 8) | flat[:, 2]
        values, inverse = np.unique(packed, return_inverse=True)
        self.colors = np.stack([(values >> 16) & 255, (values >> 8) & 255, values & 255],
                               axis=1).astype(np.float32)             # (U, 3)
        self.squares = (self.colors * self.colors).sum(axis=1)         # (U,)
        self.index = inverse.reshape(len(rgb), 64)                     # (T, 64)
        self.opaque = opaque

    def errors(self, palettes: list, width: int):
        """(T, P) : somme, sur les pixels opaques de la tuile, du carré de la
        distance à la couleur la plus proche de la palette — ce que coûte de la
        mettre sur cette palette. Une palette vide coûte l'infini."""
        p = len(palettes)
        pal = np.full((p, width, 3), 1e6, dtype=np.float32)
        for j, colors in enumerate(palettes):
            if colors:
                arr = np.asarray(colors, dtype=np.float32)
                pal[j, :len(arr)] = arr
                pal[j, len(arr):] = arr[-1]            # remplissage : ne change aucun minimum
        flat = pal.reshape(-1, 3)
        # |x − c|² = |x|² + |c|² − 2 x·c : un produit matriciel, sans tenseur 4D.
        d = (self.squares[:, None] + (flat * flat).sum(axis=1)[None, :]
             - 2.0 * (self.colors @ flat.T))
        nearest = np.maximum(d.reshape(len(self.colors), p, width).min(axis=2), 0.0)   # (U, P)
        return (nearest[self.index] * self.opaque[..., None]).sum(axis=1)               # (T, P)


def cluster_palettes(tile_grids: list, max_palettes: int, editable: int, method: str):
    """Renvoie (palettes, tile_pal) : au plus `max_palettes` palettes de `editable`
    couleurs (listes de (r, g, b)), et la palette de chaque tuile.

    `tile_grids` : par tuile, 64 pixels (r, g, b) ou None (transparent), déjà
    ramenés à la grille 5 bits."""
    rgb, opaque = _tile_arrays(tile_grids)
    pixels = _Pixels(rgb, opaque)
    feat = _features(rgb, opaque)
    k = max(1, min(max_palettes, len(np.unique(feat, axis=0))))
    assign = _initial_groups(feat, k)

    def _palettes_for(assignment, groups: int) -> list:
        out = []
        for g in range(groups):
            mask = (assignment == g)[:, None] & opaque
            out.append(_build_palette(rgb[mask].astype(np.uint8), editable, method))
        return out

    groups = int(assign.max()) + 1
    palettes = _palettes_for(assign, groups)
    for _ in range(_REFINE_ROUNDS):
        assign = pixels.errors(palettes, editable).argmin(axis=1)
        palettes = _palettes_for(assign, groups)
    assign = pixels.errors(palettes, editable).argmin(axis=1)

    # Palettes vides (aucune tuile ne les a choisies) : retirées, indices resserrés.
    used = sorted({int(a) for a in assign})
    renumber = {old: new for new, old in enumerate(used)}
    return ([palettes[old] for old in used],
            [renumber[int(a)] for a in assign])
