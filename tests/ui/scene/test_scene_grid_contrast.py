"""La grille de la scène se lit sur un décor clair comme sur un décor sombre."""
import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from ui.scene_manager.canvas.canvas_items import GridItem


def _render(background: QColor, cell: int) -> QImage:
    image = QImage(32, 32, QImage.Format.Format_RGB32)
    image.fill(background)
    painter = QPainter(image)
    item = GridItem(32, 32, cell)

    class Option:
        exposedRect = QRectF(0, 0, 32, 32)
    item.paint(painter, Option())
    painter.end()
    return image


def _gap(a: QColor, b: QColor) -> int:
    return max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue()))


@pytest.mark.parametrize("background", [QColor(120, 150, 245), QColor(235, 235, 245), QColor(20, 24, 60), QColor(0, 0, 0)])
@pytest.mark.parametrize("cell", [8, 16])
def test_les_lignes_ressortent_du_fond(background, cell):
    image = _render(background, cell)
    line = image.pixelColor(cell, 5)          # sur la ligne verticale x = cell
    between = image.pixelColor(cell + 3, 5)   # entre deux lignes
    assert between == background
    assert _gap(line, background) >= 40, (background.name(), cell, line.name())
