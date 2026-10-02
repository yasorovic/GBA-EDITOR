"""Inspecteur de la recette persistée d'une FontAsset."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QSpinBox, QLineEdit, QCheckBox, QLabel
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from core.models.font_asset import (DITHER_PATTERNS, HINTING_MODES, PIXEL_FIT_MODES,
                                    RASTER_MODES)
from ui.common.theme import T, QSS
from ui.common.widgets import W, CollapsibleCard
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.text_editor.colors import FONT_COLOR
from ui.text_editor.inspector_shell import insp_scroll


class FontAssetInspector(QWidget):
    """Édite des choix de rendu, jamais les contours de la source."""

    field_changed = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._asset = None
        self._blocking = False
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        host, lay, self._name = insp_scroll(FONT_COLOR, label("fontasset.title"))
        root.addWidget(host)

        source_card = CollapsibleCard(label("fontasset.sources"))
        self._primary = QComboBox(); self._primary.setStyleSheet(QSS.combobox)
        self._fallbacks = QLineEdit(); self._fallbacks.setStyleSheet(QSS.lineedit)
        self._fallbacks.setPlaceholderText(label("fontasset.fallback_placeholder"))
        self._primary.setToolTip(tooltip(title=label("fontasset.primary"), body=label("fontasset.primary_tip")))
        self._fallbacks.setToolTip(tooltip(title=label("fontasset.fallbacks"), body=label("fontasset.fallbacks_tip")))
        W.row(label("fontasset.primary"), self._primary, source_card.body_layout)
        W.row(label("fontasset.fallbacks"), self._fallbacks, source_card.body_layout)
        lay.addWidget(source_card)

        faces_card = CollapsibleCard(label("fontasset.faces"))
        self._faces = QLabel()
        self._faces.setWordWrap(True)
        self._faces.setFont(QFont(T.MONO, T.SM))
        self._faces.setStyleSheet("padding: 2px 0;")
        faces_card.body_layout.addWidget(self._faces)
        lay.addWidget(faces_card)

        raster_card = CollapsibleCard(label("fontasset.rasterization"))
        self._height = self._spin(1, 128)
        self._line_height = self._spin(1, 256)
        self._pixel_fit = self._choices(PIXEL_FIT_MODES)
        self._hinting = self._choices(HINTING_MODES)
        self._raster_mode = self._choices(RASTER_MODES)
        self._threshold = self._spin(0, 255)
        self._dither = self._choices(DITHER_PATTERNS)
        self._offset_x = self._spin(-32, 32)
        self._offset_y = self._spin(-32, 32)
        self._prefer_strike = QCheckBox(label("fontasset.prefer_bitmap_strike"))
        self._prefer_strike.setFont(QFont(T.UI, T.SM))
        tips = {
            self._height: "fontasset.pixel_height_tip",
            self._line_height: "fontasset.line_height_tip",
            self._pixel_fit: "fontasset.pixel_fit_tip",
            self._hinting: "fontasset.hinting_tip",
            self._raster_mode: "fontasset.raster_mode_tip",
            self._threshold: "fontasset.threshold_tip",
            self._dither: "fontasset.dither_tip",
            self._offset_x: "fontasset.offset_x_tip",
            self._offset_y: "fontasset.offset_y_tip",
        }
        titles = {
            self._height: "fontasset.pixel_height",
            self._line_height: "fontasset.line_height",
            self._pixel_fit: "fontasset.pixel_fit",
            self._hinting: "fontasset.hinting",
            self._raster_mode: "fontasset.raster_mode",
            self._threshold: "fontasset.threshold",
            self._dither: "fontasset.dither",
            self._offset_x: "fontasset.offset_x",
            self._offset_y: "fontasset.offset_y",
        }
        for widget, tip_key in tips.items():
            widget.setToolTip(tooltip(title=label(titles[widget]), body=label(tip_key)))
        self._prefer_strike.setToolTip(tooltip(
            title=label("fontasset.prefer_bitmap_strike"),
            body=label("fontasset.prefer_bitmap_strike_tip"),
        ))
        for text, widget in (("fontasset.pixel_height", self._height),
                             ("fontasset.line_height", self._line_height),
                             ("fontasset.pixel_fit", self._pixel_fit),
                             ("fontasset.hinting", self._hinting),
                             ("fontasset.raster_mode", self._raster_mode),
                             ("fontasset.threshold", self._threshold),
                             ("fontasset.dither", self._dither),
                             ("fontasset.offset_x", self._offset_x),
                             ("fontasset.offset_y", self._offset_y)):
            W.row(label(text), widget, raster_card.body_layout)
        raster_card.body_layout.addWidget(self._prefer_strike)
        lay.addWidget(raster_card)
        lay.addStretch()

        self._primary.currentTextChanged.connect(self._sources_changed)
        self._fallbacks.editingFinished.connect(self._sources_changed)
        for field, widget in (("pixel_height", self._height), ("line_height", self._line_height),
                              ("coverage_threshold", self._threshold), ("offset_x", self._offset_x),
                              ("offset_y", self._offset_y)):
            widget.valueChanged.connect(lambda value, f=field: self._change(f, value))
        for field, widget in (("pixel_fit", self._pixel_fit), ("hinting", self._hinting),
                              ("raster_mode", self._raster_mode),
                              ("dither_pattern", self._dither)):
            widget.currentTextChanged.connect(lambda value, f=field: self._change(f, value))
        self._prefer_strike.toggled.connect(lambda value: self._change("prefer_bitmap_strike", value))

    @staticmethod
    def _spin(minimum, maximum):
        spin = QSpinBox(); spin.setRange(minimum, maximum)
        spin.setFont(QFont(T.MONO, T.SM)); spin.setStyleSheet(QSS.spinbox)
        return spin

    @staticmethod
    def _choices(values):
        box = QComboBox(); box.addItems(values); box.setStyleSheet(QSS.combobox)
        box.setFont(QFont(T.MONO, T.SM)); return box

    def load(self, asset, project):
        self._asset = asset
        self._blocking = True
        self._name.setText(asset.name if asset else "")
        self._primary.clear()
        self._primary.addItem(label("common.none_dash"), "")
        for font in getattr(project, "fonts", ()) if project else ():
            self._primary.addItem(font.name, font.name)
        if asset:
            self._set_current(self._primary, asset.primary_source_name())
            self._fallbacks.setText(", ".join(asset.source_names()[1:]))
            self._faces.setText("\n".join(
                label("fontasset.face_line", style=self._face_style(face), source=face.source_name)
                for face in asset.faces
            ) or label("common.none_dash"))
            for field, widget in (("pixel_height", self._height), ("line_height", self._line_height),
                                  ("coverage_threshold", self._threshold), ("offset_x", self._offset_x),
                                  ("offset_y", self._offset_y)):
                widget.setValue(getattr(asset, field))
            for field, widget in (("pixel_fit", self._pixel_fit), ("hinting", self._hinting),
                                  ("raster_mode", self._raster_mode),
                                  ("dither_pattern", self._dither)):
                self._set_current(widget, getattr(asset, field))
            self._prefer_strike.setChecked(asset.prefer_bitmap_strike)
        else:
            self._fallbacks.clear()
            self._faces.setText("")
        self._blocking = False

    @staticmethod
    def _face_style(face):
        if face.weight == 700 and face.italic:
            return label("fontasset.face_bold_italic")
        if face.italic:
            return label("fontasset.face_italic")
        if face.weight == 700:
            return label("fontasset.face_bold")
        if face.weight == 400:
            return label("fontasset.face_regular")
        return label("fontasset.face_weight", weight=face.weight)

    @staticmethod
    def _set_current(widget, value):
        index = widget.findData(value)
        if index < 0:
            index = widget.findText(value)
        widget.setCurrentIndex(max(0, index))

    def _sources_changed(self, *_args):
        if self._blocking or not self._asset:
            return
        primary = self._primary.currentData() or ""
        fallbacks = [name.strip() for name in self._fallbacks.text().split(",") if name.strip()]
        sources = [primary] if primary else []
        sources += [name for name in fallbacks if name != primary]
        self.field_changed.emit("sources", {"regular": sources} if sources else {})

    def _change(self, field, value):
        if not self._blocking and self._asset is not None:
            self.field_changed.emit(field, value)
