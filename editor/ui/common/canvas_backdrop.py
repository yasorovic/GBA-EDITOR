"""ui/common/canvas_backdrop.py — grille de fond + halo au survol.

Source unique de l'effet visuel introduit par le Font Editor (comparaison
couverture/sortie) : une grille grise à peine visible, dont un dégradé radial
centré sur le pointeur ne révèle qu'un aperçu proche — jamais une case
encadrée, jamais une sélection. Partagé par tous les canvas de pixel art
(police, fond, sprite) pour que le geste — et son coût — reste identique
partout : une amélioration ici profite aux trois d'un coup.

Deux pièges de performance, corrigés une fois pour toutes :
  · le halo est un pinceau à dégradé radial — Qt l'évalue sur toute la
    LONGUEUR de chaque ligne tracée, pas seulement près du centre. Le peindre
    sur la grille entière (comme au premier jet) coûte donc proportionnellement
    à la taille du canvas, pas au rayon du halo. `draw_grid_halo` borne le
    tracé à un carré autour du pointeur : le coût ne dépend plus que du rayon.
  · la grille statique, elle, est identique à chaque appel : `draw_grid` la
    carrelle une fois dans un QPixmap caché par pas (`tiled=True`), au lieu de
    retracer une ligne par case à chaque repaint — coût constant quel que soit
    le nombre de cases visibles. Réservé aux canvas SANS transformation de vue
    (le pas y est déjà en pixels écran) ; un QGraphicsView zoomé garde le tracé
    cosmétique (`tiled=False`, réglage par défaut) pour ne jamais épaissir le
    trait au zoom.
"""
from __future__ import annotations

from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPixmap, QRadialGradient, QGradient
from PyQt6.QtCore import Qt, QPointF, QRectF

from ui.common.theme import C

# Le fond clair (`CANVAS_BG` ≈ #dcdcdc) est trop proche du gris de grille
# d'origine (150,150,165) pour que l'alpha faible du thème sombre reste
# lisible : la ligne se noie dans le fond au lieu de s'en détacher. On fonce
# le trait et on relève l'alpha uniquement en thème clair.
_GRID_COLOR = QColor(90, 90, 105, 60) if C.IS_LIGHT else QColor(150, 150, 165, 28)
# Le halo éclaircit la grille : sur fond sombre, un dégradé blanc se voit ;
# sur fond clair, la même couleur se fond dans le fond. On assombrit le halo
# en thème clair pour garder le même effet de « zone révélée ».
_HALO_COLOR = QColor(40, 40, 50) if C.IS_LIGHT else QColor(255, 255, 255)
_TILE_CACHE: dict[int, QPixmap] = {}


def draw_grid(painter: QPainter, rect: QRectF, step: float,
              origin: QPointF = QPointF(0, 0), *, tiled: bool = False):
    """Grille grise permanente, alignée sur `origin` et prolongée à tout `rect`."""
    if tiled:
        tile = _grid_tile(step)
        if tile is None:
            return
        painter.save()
        painter.setBrushOrigin(origin)
        painter.fillRect(rect, QBrush(tile))
        painter.restore()
        return
    pen = QPen(_GRID_COLOR)
    pen.setCosmetic(True)
    pen.setWidth(0)
    painter.setPen(pen)
    _lines(painter, rect, step, origin)


def draw_grid_halo(painter: QPainter, rect: QRectF, step: float,
                   hover: QPointF | None, origin: QPointF = QPointF(0, 0)):
    """Même grille, peinte à travers un dégradé radial centré sur `hover` —
    bornée à un carré autour du pointeur, jamais à tout le canvas : le halo
    ne coûte que ce que son propre rayon coûte, quelle que soit la taille de
    la grille qui l'entoure."""
    if hover is None or not rect.contains(hover):
        return
    radius = max(48.0, 1.5 * step)
    clip = QRectF(hover.x() - radius, hover.y() - radius, radius * 2, radius * 2).intersected(rect)
    if clip.isEmpty():
        return
    halo = QRadialGradient(hover, radius)
    halo.setCoordinateMode(QGradient.CoordinateMode.LogicalMode)
    halo.setColorAt(0.0, QColor(_HALO_COLOR.red(), _HALO_COLOR.green(), _HALO_COLOR.blue(), 145))
    halo.setColorAt(0.35, QColor(_HALO_COLOR.red(), _HALO_COLOR.green(), _HALO_COLOR.blue(), 72))
    halo.setColorAt(1.0, QColor(_HALO_COLOR.red(), _HALO_COLOR.green(), _HALO_COLOR.blue(), 0))
    pen = QPen(QBrush(halo), 1)
    pen.setCosmetic(True)
    painter.save()
    painter.setClipRect(clip)
    painter.setPen(pen)
    _lines(painter, clip, step, origin)
    painter.restore()


def _grid_tile(step: float) -> QPixmap | None:
    """Motif carrelable d'un pas de grille — un coin en équerre, mis en cache
    par taille : le calculer une fois par zoom plutôt qu'à chaque repaint."""
    size = round(step)
    if size <= 0:
        return None
    tile = _TILE_CACHE.get(size)
    if tile is None:
        tile = QPixmap(size, size)
        tile.fill(Qt.GlobalColor.transparent)
        p = QPainter(tile)
        p.setPen(_GRID_COLOR)
        p.drawLine(0, 0, 0, size - 1)
        p.drawLine(0, 0, size - 1, 0)
        p.end()
        _TILE_CACHE[size] = tile
    return tile


def _lines(painter: QPainter, rect: QRectF, step: float, origin: QPointF):
    if step <= 0:
        return
    start_x = origin.x() + ((rect.left() - origin.x()) // step) * step
    start_y = origin.y() + ((rect.top() - origin.y()) // step) * step
    x = start_x
    while x <= rect.right() + step:
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        x += step
    y = start_y
    while y <= rect.bottom() + step:
        painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        y += step
