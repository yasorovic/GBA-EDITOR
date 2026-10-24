"""ui/data_editor/data_cell_preview.py — ce que la cellule sélectionnée désigne, montré dans l'inspecteur.

Un texte s'y relit et s'y corrige ; une palette montre ses couleurs ; un sprite ou un fond, son image ; un son, son
fichier source. Le reste (scène, police, caméra…) n'a rien à montrer de plus que sa description.

Le texte est la seule chose qu'on écrit ici, et il n'appartient pas à la table : c'est le contenu (langue source) de
l'entrée citée, écrit par une commande d'historique comme depuis l'écran Texte. La valeur de la cellule, elle, ne
passe que par la grille. L'édition se valide à la perte du focus ou au changement de sélection, jamais à la frappe :
un Ctrl+Z annule une correction, pas une lettre.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QEvent, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPlainTextEdit

from ui.common.theme import C, T, S
from ui.common.labels import label

from core.models.data_table import DataColumn
from core.models.gba_color import bgr555_to_rgb888

_IMAGE_MAX = (220, 140)
_TEXT_LINES = (2, 12)      # hauteur du champ de texte, en lignes : il grandit avec le contenu entre ces deux bornes
_SWATCH = 12
_SWATCH_COLUMNS = 16


class CellPreview(QWidget):
    """Un aperçu à la fois, choisi par le type de la colonne."""

    text_edited = pyqtSignal(object, str, str)    # (Text, contenu avant, contenu après)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(S.SM)

        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._image)

        self._swatches = QLabel()
        self._swatches.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._swatches)

        self._caption = QLabel()
        self._caption.setWordWrap(True)
        self._caption.setStyleSheet(f"color:{C.TEXT_DIM}; font-size:{T.SM}px;")
        layout.addWidget(self._caption)

        self._text = QPlainTextEdit()
        self._text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._text.textChanged.connect(self._fit_text_height)
        self._text.setStyleSheet(
            f"QPlainTextEdit {{ background:{C.BG_INPUT}; color:{C.TEXT_HI}; border:1px solid {C.BORDER_MID};"
            f" border-radius:4px; padding:3px 6px; font-size:{T.MD}px; }}"
            f"QPlainTextEdit:focus {{ border-color:{C.ACCENT}; }}")
        self._text.installEventFilter(self)
        layout.addWidget(self._text)

        self._entry = None            # le Text en cours d'édition
        self._before = ""
        self._clear()

    # ── Affichage ─────────────────────────────────────────────────

    def show_for(self, project, column: Optional[DataColumn], value) -> None:
        """Montre ce que `value` désigne dans `column`. Valide d'abord une correction de texte en attente."""
        self.commit()
        self._clear()
        name = str(value or "").strip()
        if column is None or project is None or not name:
            return
        if column.type == "text":
            self._show_text(project, name)
        elif column.type == "palette":
            self._show_palette(project, name)
        elif column.type in ("sprite", "background"):
            store = project.sprites if column.type == "sprite" else project.backgrounds
            self._show_image(project, store.get(name))
        elif column.type in ("sfx", "music"):
            store = project.sfx if column.type == "sfx" else project.music
            self._show_sound(store.get(name))
        self.setVisible(any(not w.isHidden() for w in (self._image, self._swatches, self._caption, self._text)))

    def _clear(self) -> None:
        for widget in (self._image, self._swatches, self._caption, self._text):
            widget.hide()
        self._entry = None
        self.hide()

    def _show_text(self, project, key: str) -> None:
        entry = project.get_text(key)
        if entry is None:
            return
        self._entry, self._before = entry, entry.content
        self._text.blockSignals(True)
        self._text.setPlainText(entry.content)
        self._text.blockSignals(False)
        self._text.show()
        self._fit_text_height()

    def _fit_text_height(self) -> None:
        """Une ligne visuelle (retours à la ligne compris) de plus, une ligne de hauteur de plus, jusqu'au plafond."""
        lines = int(self._text.document().size().height())     # un QPlainTextEdit mesure son document en LIGNES
        lines = max(_TEXT_LINES[0], min(_TEXT_LINES[1], lines))
        margins = 2 * self._text.document().documentMargin() + 2 * self._text.frameWidth() + 8   # 8 : le padding du style
        self._text.setFixedHeight(int(lines * self._text.fontMetrics().lineSpacing() + margins))

    def _show_palette(self, project, name: str) -> None:
        bank = project.palettes.get(name)
        if bank is None or not bank.colors:
            return
        rows = -(-len(bank.colors) // _SWATCH_COLUMNS)
        pixmap = QPixmap(_SWATCH * min(len(bank.colors), _SWATCH_COLUMNS), _SWATCH * rows)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        for index, color in enumerate(bank.colors):
            r, g, b = bgr555_to_rgb888(color)
            painter.fillRect((index % _SWATCH_COLUMNS) * _SWATCH, (index // _SWATCH_COLUMNS) * _SWATCH,
                             _SWATCH - 1, _SWATCH - 1, QColor(r, g, b))
        painter.end()
        self._swatches.setPixmap(pixmap)
        self._swatches.show()
        self._caption.setText(label("datainsp.pal_colors", n=len(bank.colors)))
        self._caption.show()

    def _show_image(self, project, asset) -> None:
        path = project.asset_abs(asset.asset) if asset is not None else None
        pixmap = QPixmap(str(path)) if path is not None and path.exists() else QPixmap()
        if pixmap.isNull():
            return
        shown = pixmap.scaled(*_IMAGE_MAX, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.FastTransformation)    # les pixels restent des pixels
        self._image.setPixmap(shown)
        self._image.show()
        self._caption.setText(label("datainsp.image_size", w=pixmap.width(), h=pixmap.height()))
        self._caption.show()

    def _show_sound(self, sound) -> None:
        if sound is None or not sound.asset:
            return
        file = str(sound.asset).replace("\\", "/").rsplit("/", 1)[-1]
        self._caption.setText(label("datainsp.sound_source", file=file))
        self._caption.show()

    # ── Texte ─────────────────────────────────────────────────────

    def refresh_text(self) -> None:
        """Le contenu a changé ailleurs (écran Texte, annulation) : relit-le, sauf pendant qu'on y écrit."""
        if self._entry is None or self._text.hasFocus():
            return
        if self._text.toPlainText() != self._entry.content:
            self._before = self._entry.content
            self._text.blockSignals(True)
            self._text.setPlainText(self._entry.content)
            self._text.blockSignals(False)

    def commit(self) -> None:
        if self._entry is None:
            return
        after = self._text.toPlainText()
        if after != self._before:
            before, self._before = self._before, after
            self.text_edited.emit(self._entry, before, after)

    def eventFilter(self, watched, event):
        if watched is self._text and event.type() == QEvent.Type.FocusOut:
            self.commit()
        elif watched is self._text and event.type() == QEvent.Type.Resize:
            self._fit_text_height()        # la largeur change les retours à la ligne
        return super().eventFilter(watched, event)
