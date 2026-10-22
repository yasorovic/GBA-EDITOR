"""
ui/text_editor/colors.py — les deux familles de couleur de l'écran Texte.

Point unique : c'est la couleur qui dit lequel des deux concepts on regarde,
de la library à l'inspecteur.
"""
from ui.common.theme import C
from ui.common.icons import COLOR_FONT


FONT_COLOR = COLOR_FONT      # famille « police » (asset) — icons.py
TEXT_COLOR = C.ACCENT        # famille « texte » (contenu) — accent primaire
