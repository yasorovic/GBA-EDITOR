"""ui/background_editor/bg_placement_geometry.py — géométrie de l'image posée dans le canvas d'un fond.

Pur calcul, sans Qt : l'item graphique (bg_placement_overlay) ne fait que tenir la souris et dessiner, les règles de
modificateurs vivent ici pour être testées.

Une image posée est un rectangle `(x, y, w, h)` en pixels du CANVAS : son coin haut-gauche et sa taille à l'échelle.
Elle peut sortir du canvas (le surplus est rogné à l'usage) ou ne pas le couvrir (le vide est transparent).

Deux gestes, une grammaire :
  · glisser le corps déplace ; Ctrl accroche le coin haut-gauche à la grille 8×8 du matériel ;
  · glisser une poignée met à l'échelle, le côté opposé reste fixe ; Maj garde les proportions de l'image,
    Ctrl accroche le côté tiré à la grille.
"""
from __future__ import annotations

SNAP = 8
HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


def _snap(v: float) -> int:
    return int(round(v / SNAP)) * SNAP


def rect_of(canvas, pos, size, file_size) -> tuple:
    """Le rectangle posé d'un fond d'après ses trois valeurs de sidecar (`None` = le défaut : l'image à la taille du
    fichier, en (0, 0))."""
    w, h = size or file_size
    x, y = pos or (0, 0)
    return int(x), int(y), int(w), int(h)


def normalize(canvas, rect, file_size) -> tuple:
    """Les trois valeurs de sidecar `(canvas, pos, size)` d'un rectangle posé, `None` pour ce qui vaut le défaut.
    Le canvas vaut le défaut quand il est de la taille de l'image posée — c'est ce qu'écrit le modèle de départ."""
    x, y, w, h = rect
    size = None if (w, h) == tuple(file_size) else (w, h)
    pos = None if (x, y) == (0, 0) else (x, y)
    canvas = tuple(canvas)
    return (None if canvas == (w, h) else canvas), pos, size


def move_rect(rect, dx: float, dy: float, ctrl: bool) -> tuple:
    """`rect` déplacé de (dx, dy) ; Ctrl accroche son coin haut-gauche à la grille."""
    x, y, w, h = rect
    nx, ny = x + dx, y + dy
    if ctrl:
        nx, ny = _snap(nx), _snap(ny)
    return round(nx), round(ny), w, h


def scale_rect(rect, handle: str, dx: float, dy: float, shift: bool, ctrl: bool) -> tuple:
    """`rect` mis à l'échelle en tirant la poignée `handle` (un coin « nw »…, un bord « n », « e », « s », « w ») de
    (dx, dy). Le côté opposé reste fixe. Maj garde les proportions : à un coin le côté qui a le plus changé en
    proportion commande ; à un bord l'autre dimension suit, centrée sur le rectangle de départ."""
    x, y, w, h = rect
    left, top, right, bottom = float(x), float(y), float(x + w), float(y + h)
    if "w" in handle:
        left += dx
    if "e" in handle:
        right += dx
    if "n" in handle:
        top += dy
    if "s" in handle:
        bottom += dy
    if ctrl:
        left, right, top, bottom = (_snap(left) if "w" in handle else left, _snap(right) if "e" in handle else right,
                                    _snap(top) if "n" in handle else top, _snap(bottom) if "s" in handle else bottom)
    # Un côté ne dépasse jamais le côté opposé : l'image ne se retourne pas, et garde au moins un pixel.
    if "w" in handle:
        left = min(left, right - 1)
    if "e" in handle:
        right = max(right, left + 1)
    if "n" in handle:
        top = min(top, bottom - 1)
    if "s" in handle:
        bottom = max(bottom, top + 1)
    if shift:
        left, top, right, bottom = _keep_ratio(left, top, right, bottom, handle, x, y, w, h)
    nw, nh = max(1, round(right - left)), max(1, round(bottom - top))
    if "w" in handle:
        nx = round(right) - nw
    elif "e" in handle:
        nx = round(left)
    else:
        nx = round(left)
    if "n" in handle:
        ny = round(bottom) - nh
    elif "s" in handle:
        ny = round(top)
    else:
        ny = round(top)
    return nx, ny, nw, nh


def _keep_ratio(left, top, right, bottom, handle, x, y, w, h):
    """Ramène le rectangle aux proportions de l'image de départ (w : h)."""
    ratio = w / h
    nw, nh = right - left, bottom - top
    if len(handle) == 2:                                  # coin : le côté qui a le plus changé commande
        if abs(nw / w - 1) >= abs(nh / h - 1):
            nh = nw / ratio
        else:
            nw = nh * ratio
        if "w" in handle:
            left = right - nw
        else:
            right = left + nw
        if "n" in handle:
            top = bottom - nh
        else:
            bottom = top + nh
        return left, top, right, bottom
    if handle in ("e", "w"):                              # bord vertical : la hauteur suit, centrée
        nh = nw / ratio
        top = (y + h / 2) - nh / 2
        return left, top, right, top + nh
    nw = nh * ratio                                       # bord horizontal : la largeur suit, centrée
    left = (x + w / 2) - nw / 2
    return left, top, left + nw, bottom


def fit_rect(file_size, canvas) -> tuple:
    """L'image entière dans le canvas, proportions gardées, centrée (agrandie si elle est plus petite)."""
    fw, fh = file_size
    cw, ch = canvas
    scale = min(cw / fw, ch / fh)
    return _centered(round(fw * scale), round(fh * scale), canvas)


def fill_rect(file_size, canvas) -> tuple:
    """Le canvas entier couvert, proportions gardées, centré : ce qui dépasse est rogné."""
    fw, fh = file_size
    cw, ch = canvas
    scale = max(cw / fw, ch / fh)
    return _centered(round(fw * scale), round(fh * scale), canvas)


def one_to_one_rect(file_size, canvas) -> tuple:
    """L'image à la taille du fichier, centrée dans le canvas."""
    return _centered(file_size[0], file_size[1], canvas)


def _centered(w: int, h: int, canvas) -> tuple:
    w, h = max(1, w), max(1, h)
    return (canvas[0] - w) // 2, (canvas[1] - h) // 2, w, h
