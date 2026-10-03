"""
editor/core/gba_color.py — Conversions couleur GBA (BGR555) et quantification.

Format hardware GBA (confirmé par `grit --help`, "-gT{n} ... 16bit BGR hex") :
bits 0-4 = R, bits 5-9 = G, bits 10-14 = B, 5 bits par canal.
"""
from __future__ import annotations

# Index 0 réservé d'une PaletteBank — le hardware GBA traite toujours l'index 0
# comme transparent (OBJ comme BG), quelle que soit la couleur stockée ; sa valeur
# exacte n'a donc aucune incidence visuelle pour une tuile normale. La constante
# vit ICI, avec l'encodage des palettes qui l'emploie le plus (write_palettes/
# write_colors, et au-delà bg_import, codegen) : `palette` l'importe désormais
# d'ici, ce qui rompt le cycle gba_color↔palette d'autrefois.
RESERVED_SLOT_COLOR = 0


def rgb888_to_bgr555(r: int, g: int, b: int) -> int:
    return ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)


def bgr555_to_rgb888(v: int) -> tuple[int, int, int]:
    r = (v & 0x1F) << 3
    g = ((v >> 5) & 0x1F) << 3
    b = ((v >> 10) & 0x1F) << 3
    return (r, g, b)


def bgr555_components(v: int) -> tuple[int, int, int]:
    """Retourne (r, g, b) en 0-31 (profondeur native GBA), sans passer par le 0-255."""
    return v & 0x1F, (v >> 5) & 0x1F, (v >> 10) & 0x1F


def components_to_bgr555(r5: int, g5: int, b5: int) -> int:
    return ((b5 & 0x1F) << 10) | ((g5 & 0x1F) << 5) | (r5 & 0x1F)


# ── La forme ÉCRITE d'une couleur (ROADMAP v0.24) ────────────────────
# Sur disque, une couleur s'écrit `#39A8FF` et non `20253` : le nombre décimal
# ne se relit pas — ni en revoyant un diff, ni en ouvrant le fichier — alors
# que c'est la même donnée. Le passage est EXACTEMENT réversible sur les 32 768
# valeurs BGR555 (vérifié exhaustivement) : les 3 bits de poids faible que
# `bgr555_to_rgb888` met à zéro sont ceux que `rgb888_to_bgr555` rejette de
# toute façon, donc aucune couleur ne se dégrade en traversant le fichier.
#
# La LECTURE accepte les deux formes, pour toujours : un projet écrit avant
# cette version se relit sans conversion préalable, et le premier
# enregistrement le réécrit au passage.

def bgr555_to_hex(v: int) -> str:
    r, g, b = bgr555_to_rgb888(int(v) & 0x7FFF)
    return f"#{r:02X}{g:02X}{b:02X}"


def hex_to_bgr555(s: str) -> int:
    h = s.strip().lstrip("#")
    return rgb888_to_bgr555(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def read_color(v) -> int:
    """Une couleur relue du disque, quelle que soit sa forme écrite."""
    return hex_to_bgr555(v) if isinstance(v, str) else int(v) & 0x7FFF


def write_colors(colors) -> list[str]:
    return [bgr555_to_hex(c) for c in colors]


def read_colors(values) -> list[int]:
    return [read_color(c) for c in (values or [])]


def write_palettes(palettes) -> list[list[str]]:
    return [write_colors(p) for p in (palettes or [])]


def read_palettes(palettes) -> list[list[int]]:
    return [read_colors(p) for p in (palettes or [])]




def nearest_bank_color(rgb888: tuple[int, int, int], bank_colors: list[int]) -> int:
    """Retourne la valeur BGR555 de `bank_colors` la plus proche de `rgb888`
    (distance euclidienne dans l'espace 5-bit/canal). L'index 0 est exclu de
    la recherche : un pixel opaque n'a jamais le droit d'y être snappé (il
    deviendrait transparent au lieu d'afficher une couleur approximative)."""
    candidates = bank_colors[1:] if len(bank_colors) > 1 else bank_colors
    r, g, b = rgb888
    r5, g5, b5 = r >> 3, g >> 3, b >> 3
    best = candidates[0]
    best_dist = None
    for c in candidates:
        cr, cg, cb = bgr555_to_rgb888(c)
        cr5, cg5, cb5 = cr >> 3, cg >> 3, cb >> 3
        dist = (r5 - cr5) ** 2 + (g5 - cg5) ** 2 + (b5 - cb5) ** 2
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = c
    return best


def quantize_image_to_bank(img: "Image.Image", bank_colors: list[int]) -> "Image.Image":
    """Snappe chaque pixel RGB(A) de `img` vers la couleur de banque la plus
    proche (alpha préservé, pixels transparents non touchés). `img` doit être
    en mode RGBA. `bank_colors` doit être non-vide."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    cache: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            key = (r, g, b)
            snapped = cache.get(key)
            if snapped is None:
                nearest = nearest_bank_color(key, bank_colors)
                snapped = bgr555_to_rgb888(nearest)
                cache[key] = snapped
            px[x, y] = (snapped[0], snapped[1], snapped[2], a)
    return img


def compress_colors(
    colors: list[tuple[int, int, int]], max_colors: int
) -> dict[tuple[int, int, int], tuple[int, int, int]]:
    """Réduit une liste de couleurs RGB distinctes à `max_colors` représentants
    (median-cut, PIL `Image.quantize`). Construit une image synthétique 1×N
    (une couleur par pixel, ordre préservé), quantifie, puis relit les
    valeurs de sortie pour bâtir couleur d'origine -> couleur réduite. No-op
    (identité) si `colors` tient déjà dans `max_colors`."""
    if len(colors) <= max_colors:
        return {c: c for c in colors}
    from PIL import Image
    n = len(colors)
    src = Image.new("RGB", (n, 1))
    src.putdata(colors)
    quantized = src.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT).convert("RGB")
    reduced = list(quantized.getdata())
    return dict(zip(colors, reduced))


def extract_palette_from_image(path, max_colors: int = 15) -> list[int]:
    """Construit une palette (liste BGR555) depuis les couleurs opaques d'un
    PNG, pour le bouton "Extraire du PNG" du Sprite Editor. L'index 0 reste
    réservé (transparence), suivi des couleurs réelles triées de la plus
    sombre à la plus lumineuse (luminance croissante). Si le PNG référence
    plus de `max_colors` couleurs distinctes, `compress_colors` (median-cut)
    réduit d'abord — sinon toutes sont conservées telles quelles.
    Retourne `[RESERVED_SLOT_COLOR] + couleurs` (longueur 1 à max_colors+1)."""
    from PIL import Image
    img = Image.open(path).convert("RGBA")
    px = img.load()
    w, h = img.size
    distinct: dict[tuple[int, int, int], None] = {}
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            distinct.setdefault((r, g, b), None)
    colors = list(distinct.keys())
    if not colors:
        return [RESERVED_SLOT_COLOR]
    if len(colors) > max_colors:
        color_map = compress_colors(colors, max_colors)
        # dict.fromkeys : dédup les représentants réduits en préservant l'ordre
        colors = list(dict.fromkeys(color_map.values()))
    # PAS de tri : l'ordre = ordre d'apparition des couleurs dans le PNG.
    # L'index de palette est le slot hardware réellement visible in-game ;
    # réordonner risquerait de désaligner les tuiles déjà quantifiées d'un
    # sprite. C'est à l'utilisateur d'organiser ses couleurs en amont.
    return [RESERVED_SLOT_COLOR] + [rgb888_to_bgr555(r, g, b) for r, g, b in colors]


def direct_index_to_bank(path, bank_colors: list[int]) -> "Image.Image":
    """Mode "indexation directe" : `path` doit être un PNG en mode `'P'`
    natif (palette + index par pixel) — pas de recherche de correspondance,
    les index du PNG se calent directement sur ceux de la banque. Convention
    fixe (pas une détection automatique) : l'index PNG 0 est toujours
    transparent, quel que soit l'éventuel tag `tRNS` du fichier — à
    l'appelant/au validateur de prévenir si le fichier semble mal préparé
    pour ce mode (transparence native à un autre index). Si plus de couleurs
    réelles (index 1+) que de slots éditables, `compress_colors` réduit
    d'abord — l'assignation elle-même reste dans l'ordre d'apparition des
    index PNG, sans tri ni recherche. Retourne une image RGBA, même forme de
    sortie que `quantize_image_to_bank`/`quantize_image_luminance_preserving`."""
    from PIL import Image
    img = Image.open(path)
    if img.mode != "P":
        raise ValueError(f"direct_index_to_bank: {path} is not an indexed PNG (mode "
                         f"{img.mode!r})")

    palette = img.getpalette() or []
    used_indices = sorted(idx for _count, idx in img.getcolors(maxcolors=256))
    real_indices = [i for i in used_indices if i != 0]

    editable = bank_colors[1:] if len(bank_colors) > 1 else bank_colors
    index_to_bank_color: dict[int, int] = {}
    if real_indices and editable:
        real_colors_by_index = {
            i: (palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]) for i in real_indices
        }
        real_colors_list = [real_colors_by_index[i] for i in real_indices]
        color_map = compress_colors(real_colors_list, len(editable))

        ordered_reduced: list[tuple[int, int, int]] = []
        slot_of: dict[tuple[int, int, int], int] = {}
        for i in real_indices:
            reduced = color_map[real_colors_by_index[i]]
            if reduced not in slot_of:
                slot_of[reduced] = len(ordered_reduced)
                ordered_reduced.append(reduced)
            index_to_bank_color[i] = editable[slot_of[reduced]]

    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    src_px = img.load()
    dst_px = out.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            idx = src_px[x, y]
            bank_color = index_to_bank_color.get(idx)
            if bank_color is None:
                continue
            r, g, b = bgr555_to_rgb888(bank_color)
            dst_px[x, y] = (r, g, b, 255)
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  Indexation d'un PNG (mode 'P') pour le Sprite Editor
#
#  Un sprite indexé est auto-descriptif : index PNG i == index de palette
#  hardware i (index 0 = transparent par convention). Plus besoin de résoudre
#  « quelle palette / quelle scène » au build — cf. le cap direct-index.
# ─────────────────────────────────────────────────────────────────────────────

# Méthodes de compression proposées quand un sprite dépasse `max_colors`
# couleurs. La valeur est le jeton stocké/échangé par l'UI ; le libellé sert à
# l'affichage.
COMPRESSION_METHODS = [
    ("median_cut",   "Median-cut"),
    ("nearest_pair", "Fusion des paires proches"),
    ("most_frequent", "Couleurs les plus fréquentes"),
    ("kmeans",       "k-means"),
]


def _rgb_dist2(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def nearest_rgb(color: tuple[int, int, int],
                candidates: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    """Couleur de `candidates` la plus proche de `color` (distance RGB²)."""
    best = candidates[0]
    best_d = _rgb_dist2(color, best)
    for c in candidates[1:]:
        d = _rgb_dist2(color, c)
        if d < best_d:
            best_d, best = d, c
    return best


def reduce_nearest_pair(colors: list[tuple[int, int, int]], n: int) -> list[tuple[int, int, int]]:
    """Réduit `colors` à `n` en retirant à chaque fois l'une des deux couleurs
    les plus proches (distance RGB²) — garde les couleurs EXACTES (pas de
    moyenne). Ordre source préservé pour ce qui reste. Brique partagée avec
    cette fonction."""
    colors = list(colors)
    while len(colors) > n:
        best = None
        drop = 0
        for i in range(len(colors)):
            for j in range(i + 1, len(colors)):
                d = _rgb_dist2(colors[i], colors[j])
                if best is None or d < best:
                    best, drop = d, j
        colors.pop(drop)
    return colors


def _reps_kmeans(colors, counts, n) -> list[tuple[int, int, int]]:
    """k représentants par Lloyd pondéré sur les couleurs distinctes,
    initialisé par le résultat median-cut -> déterministe, sans dépendance
    externe. Les centres finaux sont arrondis à l'entier le plus proche."""
    seed = list(dict.fromkeys(compress_colors(colors, n).values()))
    centers = [tuple(float(v) for v in c) for c in seed]
    for _ in range(8):
        sums = [[0.0, 0.0, 0.0, 0.0] for _ in centers]  # r,g,b,poids
        for c in colors:
            w = counts.get(c, 1)
            k = min(range(len(centers)),
                    key=lambda i: _rgb_dist2(c, tuple(round(v) for v in centers[i])))
            s = sums[k]
            s[0] += c[0] * w; s[1] += c[1] * w; s[2] += c[2] * w; s[3] += w
        moved = False
        for i, s in enumerate(sums):
            if s[3] > 0:
                nc = (s[0] / s[3], s[1] / s[3], s[2] / s[3])
                if nc != centers[i]:
                    centers[i] = nc; moved = True
        if not moved:
            break
    reps = list(dict.fromkeys(tuple(round(v) for v in c) for c in centers))
    return reps


def reduce_colors(colors: list[tuple[int, int, int]],
                  counts: dict, max_colors: int, method: str = "median_cut") -> dict:
    """Réduit une liste de couleurs RGB distinctes à `max_colors` représentants
    et retourne un mapping {couleur d'origine -> représentant}. No-op (identité)
    si `colors` tient déjà. `counts` = {couleur: nb de pixels} (pour
    most_frequent / kmeans). `method` ∈ COMPRESSION_METHODS."""
    if len(colors) <= max_colors:
        return {c: c for c in colors}
    if method == "median_cut":
        return compress_colors(colors, max_colors)
    if method == "nearest_pair":
        reps = reduce_nearest_pair(colors, max_colors)
    elif method == "most_frequent":
        reps = sorted(colors, key=lambda c: counts.get(c, 0), reverse=True)[:max_colors]
    elif method == "kmeans":
        reps = _reps_kmeans(colors, counts, max_colors)
    else:
        raise ValueError(f"reduce_colors: unknown method {method!r}")
    return {c: nearest_rgb(c, reps) for c in colors}


def distinct_opaque(img) -> tuple[list, dict]:
    """Couleurs RGB opaques distinctes d'une image RGBA, dans l'ordre
    d'apparition (scan haut-gauche -> bas-droite), + comptes par couleur.
    Un pixel d'alpha 0 est transparent (ignoré)."""
    data = list(img.getdata())
    order: list = []
    counts: dict = {}
    for px in data:
        r, g, b, a = px
        if a == 0:
            continue
        key = (r, g, b)
        c = counts.get(key)
        if c is None:
            order.append(key)
            counts[key] = 1
        else:
            counts[key] = c + 1
    return order, counts


def _flat_palette(reps: list[tuple[int, int, int]]) -> list[int]:
    """Palette PIL plate : index 0 réservé (noir/transparent) + les
    représentants aux index 1..N."""
    flat = [0, 0, 0]
    for r, g, b in reps:
        flat += [r, g, b]
    return flat


def own_palette_from_source(source, method: str = "median_cut",
                            max_colors: int = 15) -> list[int]:
    """Palette propre (compression) d'un sprite, calculée depuis les couleurs
    opaques du PNG source SANS le modifier : couleurs distinctes → réduction à
    `max_colors` via `method` → valeurs BGR555 ordonnées (ordre d'apparition).
    C'est la métadonnée stockée dans le JSON du sprite (index 1..N ; index 0
    transparent implicite). Retourne [] si le source n'a aucun pixel opaque.
    `source` : chemin ou image PIL."""
    from PIL import Image
    img = (source if hasattr(source, "mode") else Image.open(source)).convert("RGBA")
    order, counts = distinct_opaque(img)
    if not order:
        return []
    color_map = reduce_colors(order, counts, max_colors, method)
    reps_ordered: list = []
    seen: set = set()
    for c in order:
        rep = color_map[c]
        if rep not in seen:
            seen.add(rep)
            reps_ordered.append(rep)
    return [rgb888_to_bgr555(r, g, b) for r, g, b in reps_ordered]


def render_indexed(source, own_palette: list[int]):
    """Rend une image mode 'P' depuis `source` (chemin/image) en calant chaque
    pixel opaque sur l'index (1..N) de la couleur `own_palette` (BGR555) la plus
    proche ; pixel transparent → index 0. La palette de sortie = `own_palette`.
    Ne modifie JAMAIS le source. Brique de rendu partagée preview + build."""
    from PIL import Image
    img = (source if hasattr(source, "mode") else Image.open(source)).convert("RGBA")
    w, h = img.size
    out = Image.new("P", (w, h), 0)
    reps_rgb = [bgr555_to_rgb888(c) for c in own_palette]   # index 1..N
    if not reps_rgb:
        out.putpalette(_flat_palette([]))
        out.info["transparency"] = 0
        return out

    cache: dict = {}
    def _idx(rgb):
        i = cache.get(rgb)
        if i is None:
            best, best_d = 1, None
            for k, rep in enumerate(reps_rgb, start=1):
                d = _rgb_dist2(rgb, rep)
                if best_d is None or d < best_d:
                    best_d, best = d, k
            cache[rgb] = best
            i = best
        return i

    data = list(img.getdata())
    out.putdata([0 if px[3] == 0 else _idx((px[0], px[1], px[2])) for px in data])
    out.putpalette(_flat_palette(reps_rgb))
    out.info["transparency"] = 0
    return out


def recolor_indexed(p_img, bank_colors: list[int]):
    """Réhabille une image 'P' (index 1..N) avec les couleurs BGR555 de
    `bank_colors` (index i → bank_colors[i]) → RGBA. Sert au mode preview
    « indexed » du Sprite Editor (rendu in-game avec une palette référencée)."""
    reps = [bgr555_to_rgb888(c) for c in bank_colors[1:16]]
    p_img = p_img.copy()
    p_img.putpalette(_flat_palette(reps))
    p_img.info["transparency"] = 0
    return p_img.convert("RGBA")


def quantize_preview(img, sprite, bank):
    """Aperçu acteur du canvas de scène, aligné sur le build INDEXÉ universel :
    l'image composée est rendue via la own_palette du sprite (compression
    stockée), puis ses index sont recolorés par la banque référencée
    (index i -> banque[i]) ou laissés en couleurs propres (OWN). WYSIWYG avec
    le build réel."""
    own_pal = list(getattr(sprite, "own_palette", []) or [])
    if not own_pal:
        return img
    p_img = render_indexed(img, own_pal)
    if bank and bank.colors:
        return recolor_indexed(p_img, bank.colors)
    return p_img.convert("RGBA")
