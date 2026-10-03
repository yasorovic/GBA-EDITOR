"""Régénère packaging/icon.png et packaging/icon.ico depuis le SVG de l'icône d'application.

Source unique : editor/ui/common/CustomIcons/Backstage_icon.svg (aussi chargé à l'exécution
par main.py pour l'icône de fenêtre). À relancer quand le SVG change :

    QT_QPA_PLATFORM=offscreen python -X utf8 tools/generate_app_icon.py
"""
import sys
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

REPO_ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = REPO_ROOT / "editor" / "ui" / "common" / "CustomIcons" / "Backstage_icon.svg"
PACKAGING_DIR = REPO_ROOT / "packaging"
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
MASTER_SIZE = 256


def render_square(renderer: QSvgRenderer, size: int) -> QImage:
    """Rend le SVG centré dans un carré transparent, proportions conservées."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    view = renderer.viewBoxF()
    scale = size * 0.94 / max(view.width(), view.height())
    width, height = view.width() * scale, view.height() * scale
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF((size - width) / 2, (size - height) / 2, width, height))
    painter.end()
    return image


def main() -> int:
    _app = QGuiApplication(sys.argv)
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        print(f"SVG illisible : {SVG_PATH}", file=sys.stderr)
        return 1
    master_path = PACKAGING_DIR / "icon.png"
    render_square(renderer, MASTER_SIZE).save(str(master_path))
    Image.open(master_path).save(PACKAGING_DIR / "icon.ico", sizes=ICO_SIZES)
    print(f"écrit : {master_path} et icon.ico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
