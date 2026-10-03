"""core/sprite_import.py — validator + encodage d'import sprite (miroir de bg_import).

Pipeline aligné sur les backgrounds : Watcher → **Validator** (detect) →
**Encodage** (non-destructif) → Asset éditable. Un sprite OBJ est TOUJOURS paletté
(pas de couleur directe possible en OAM) : le seul axe est le nombre de couleurs.

Le PNG source n'est JAMAIS modifié — l'encodage vit en métadonnées sur le
SpriteAsset (cf. Project.apply_sprite_encoding), dérivé à la volée pour le
preview/build (comme les backgrounds).
"""
from __future__ import annotations

from core.bg_import import open_image, is_indexed
from core.models.gba_color import own_palette_from_source, distinct_opaque
from core.models.gba_color import RESERVED_SLOT_COLOR

# 4bpp : 16 entrées/banque dont l'index 0 réservé (transparent) → 15 opaques.
MAX_4BPP_COLORS = 15


def detect_sprite_import_mode(source) -> dict:
    """Décision d'import d'un sprite (ne modifie jamais le source). OBJ est
    toujours paletté :
    - ≤15 couleurs opaques → 4bpp propre (une banque, sans perte) ;
    - >15 → la palette sera réduite (perte) : `lossy=True` + `warning`.

    (Le multi-sous-palettes / 8bpp du sprite arrivera avec l'éditeur — cf.
    incrément Sprite Editor.) Clés : indexed, n_colors, bpp, lossy, warning."""
    img = open_image(source)
    indexed = is_indexed(img)
    order, _counts = distinct_opaque(img.convert("RGBA"))
    n = len(order)

    lossy = n > MAX_4BPP_COLORS
    bpp = 4 if not lossy else 8   # informatif (8bpp/multi-palette = éditeur, à venir)
    warning = None
    if lossy:
        warning = (f"{n} opaque colours (> {MAX_4BPP_COLORS}): the sprite palette is reduced to "
                   f"{MAX_4BPP_COLORS} colours (lossy).")

    return {
        "indexed": indexed,
        "n_colors": n,
        "bpp": bpp,
        "lossy": lossy,
        "warning": warning,
    }


def encode_sprite(source, method: str = "median_cut") -> dict:
    """Encodage NON-DESTRUCTIF d'un sprite : dérive UNE sous-palette (≤15 couleurs
    opaques, forme banque hardware avec index 0 réservé) de son PNG. Retourne un
    dict appliqué par `Project.apply_sprite_encoding` (calcul/application séparés,
    comme apply_bg_encoding). Ne modifie jamais le source.

    Le multi-sous-palettes (peinture par tuile façon Background Editor) viendra
    avec l'éditeur ; ici on produit la banque primaire, source du pont de
    compatibilité `own_palette`."""
    own = own_palette_from_source(source, method) or []   # list[int] BGR555, ≤15, sans index 0
    bank = ([RESERVED_SLOT_COLOR] + list(own))[:16]
    bank += [0] * (16 - len(bank))
    return {
        "palettes": [bank],
        "own_palette": list(own),
        "quantize_method": method,
    }
