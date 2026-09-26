"""ui/script_editor/colors.py — proxys de couleur partagés par tout l'écran Script Editor."""
from ui.common.theme import C
from ui.common.icons import COLOR_EVENT, COLOR_BEHAVIOR, COLOR_GLOBAL, COLOR_CONST

_BG       = C.BG_PANEL    # fond sidebar / body
_BG_HDR   = C.BG_PANEL    # fond headers de section
_BG_HOVER = C.BG_HOVER    # état survol
_BORDER   = C.BORDER      # séparateurs
_TEXT_DIM   = C.TEXT_DIM  # labels discrets
_TEXT_NORM  = C.TEXT_NORM # texte courant
_TEXT_HI    = C.TEXT_HI   # texte mis en avant
_C_API      = C.ACCENT_WARM  # chaud — API Lua
_C_REF      = C.ACCENT_COOL  # froid — références projet
_C_SUB      = C.TEXT_MUTED  # sous-labels grisés
# Couleurs de catégorie du script editor — centralisées dans ui/common/icons.py
# (pas de type d'objet dédié dans COMPONENT/PROJECT panel pour ces concepts).
_C_EVENT    = COLOR_EVENT
_C_BEHAVIOR = COLOR_BEHAVIOR
_C_GLOBAL   = COLOR_GLOBAL
_C_CONST    = COLOR_CONST
_BG_SEL_REF = C.BG_SEL   # fond "sélectionné" pour fichiers/refs — dérivé de _C_REF
