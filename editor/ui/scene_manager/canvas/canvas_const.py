"""ui/scene_manager/canvas/canvas_const.py : les constantes partagées du canvas.

Le module le plus bas du sous-package : ni Qt, ni modèle, juste les dimensions.
Items, scène, vue et façade les lisent d'ici, ce qui évite qu'un module bas
remonte vers la façade juste pour un entier.
"""
from __future__ import annotations

# ── Constantes GBA ───────────────────────────────────────────────
GBA_W = 240
GBA_H = 160
# Plafond MONDE : les coordonnées de la caméra sont des s16 (bounds jusqu'à
# 32767), donc un monde au-delà de 32767 ne serait pas scrollable. Le scroll
# caméra max vaut alors 32767 - screen.width. Ce n'est PAS
# une limite de carte : un axe de map > 64 tuiles est streamé au build
# (main_gen.py), le monde peut être bien plus grand que 512×512.
MAX_CANVAS_W = 32767
MAX_CANVAS_H = 32767
