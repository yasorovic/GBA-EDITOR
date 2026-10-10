"""
core/models/asset_extensions.py — l'extension de chaque type d'asset : la table unique.

Un asset vit dans un fichier dont l'extension dit son TYPE (`Player.sprite`, `boom.sfx`). Le contenu est
du JSON — lisible, diffable, fusionnable —, seule l'extension change. Le type se lit donc dans le nom,
sans ouvrir le fichier : c'est ce qui permet à un asset de vivre n'importe où sous `assets/`.

Chaque modèle porte sa constante (`sidecar_extension`) ; `ResourceStore` la lit. Cette table réunit les
constantes pour ce qui doit connaître TOUS les types (migration, balayage global, tests).

Restent en `.json` : `texts.json`, `texts_<langue>.json` et `variables.json` — un fichier pour tout le
projet, pas un par asset.
"""

SPRITE      = ".sprite"
BACKGROUND  = ".background"
SFX         = ".sfx"
MUSIC       = ".music"
JINGLE      = ".jingle"
FONT        = ".font"
PALETTE     = ".palette"
SCENE       = ".scene"
PREFAB      = ".prefab"
LAYOUT      = ".layout"
MUSIC_BOX   = ".musicbox"
JINGLE_BOX  = ".jinglebox"
SOUND_BOX   = ".soundbox"
TABLE       = ".table"
FONT_ASSET  = ".fontasset"

# Le dossier de `assets/` qui porte chaque famille, et l'extension de ses sidecars. Le nom du dossier est
# celui que `Project` donne déjà à ses magasins (`assets/<dossier>`).
FAMILY_EXTENSIONS = {
    "sprites":      SPRITE,
    "backgrounds":  BACKGROUND,
    "sfx":          SFX,
    "music":        MUSIC,
    "jingles":      JINGLE,
    "fonts":        FONT,
    "palettes":     PALETTE,
    "scenes":       SCENE,
    "prefab":       PREFAB,
    "ui_layouts":   LAYOUT,
    "music_boxes":  MUSIC_BOX,
    "jingle_boxes": JINGLE_BOX,
    "sound_boxes":  SOUND_BOX,
    "data":         TABLE,
    "fonts_assets": FONT_ASSET,
}

ALL_EXTENSIONS = frozenset(FAMILY_EXTENSIONS.values())
