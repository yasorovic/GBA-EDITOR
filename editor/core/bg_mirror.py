"""core/bg_mirror.py — miroir d'une image PIL autour d'un axe, avant la compression.

L'axe est une coordonnée en pixels de l'image préparée (recadrée, redimensionnée). Par défaut le côté GAUCHE d'un axe
vertical (le côté HAUT d'un axe horizontal) est gardé, l'autre côté en est le reflet ; `flip` garde l'autre côté. Si le reflet n'atteint pas le bord, il
se poursuit en zigzag (reflet du reflet…) : l'image garde sa taille, aucun pixel n'est laissé vide.

Le mode de l'image est conservé : une image indexée reste indexée, avec sa palette d'auteur. Le fichier source n'est
jamais touché."""
from __future__ import annotations

from PIL import Image


def _mirror_axis(img: Image.Image, axis: int, horizontal: bool) -> Image.Image:
    size = img.width if horizontal else img.height
    axis = max(1, min(int(axis), size - 1)) if size > 1 else 0
    if axis <= 0:
        return img
    box = (0, 0, axis, img.height) if horizontal else (0, 0, img.width, axis)
    kept = img.crop(box)
    flip = Image.Transpose.FLIP_LEFT_RIGHT if horizontal else Image.Transpose.FLIP_TOP_BOTTOM
    reflected = kept.transpose(flip)
    out = img.copy()
    pos, use_reflected = axis, True
    while pos < size:
        piece = reflected if use_reflected else kept
        out.paste(piece, (pos, 0) if horizontal else (0, pos))
        pos += axis
        use_reflected = not use_reflected
    return out


def _mirror_side(img: Image.Image, axis: int, horizontal: bool, flip: bool) -> Image.Image:
    """Le miroir d'un axe ; `flip` garde le côté droit (bas) : on retourne l'image, on la reflète, on la retourne."""
    if not flip:
        return _mirror_axis(img, axis, horizontal)
    turn = Image.Transpose.FLIP_LEFT_RIGHT if horizontal else Image.Transpose.FLIP_TOP_BOTTOM
    size = img.width if horizontal else img.height
    return _mirror_axis(img.transpose(turn), size - axis, horizontal).transpose(turn)


def apply_mirror(img: Image.Image, mirror) -> Image.Image:
    """L'image en miroir ; `img` elle-même si `mirror` est neutre. `mirror` = (axe_x, axe_y, garde_droite, garde_bas) :
    des entiers ou None pour les axes, des booléens pour le côté gardé (les deux derniers sont facultatifs)."""
    if not mirror:
        return img
    axis_x, axis_y, flip_x, flip_y = (tuple(mirror) + (False, False))[:4]
    if axis_x is not None:
        img = _mirror_side(img, axis_x, True, flip_x)
    if axis_y is not None:
        img = _mirror_side(img, axis_y, False, flip_y)
    return img
