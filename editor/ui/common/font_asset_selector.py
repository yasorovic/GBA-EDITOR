"""Sélecteur réutilisable d'une police logique et de son poids natif."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QToolButton
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from ui.common.theme import C, T, QSS
from ui.common.widgets import ScriptSlot, ScriptPickerPopup
from ui.common import icons
from ui.common.labels import label
from ui.common.tooltip import tooltip


def weight_label(weight: int, italic: bool = False) -> str:
    """Un libellé court pour les valeurs usuelles de la table OS/2."""
    names = {100: "Thin", 200: "Extra light", 300: "Light", 400: "Regular",
             500: "Medium", 600: "Semi bold", 700: "Bold", 800: "Extra bold",
             900: "Black"}
    name = names.get(weight, str(weight))
    return label("fontselect.weight_italic" if italic else "fontselect.weight_named",
                 name=name, weight=weight)


class FontAssetSelector(QWidget):
    """Asset searchable + poids natif, sans inventer de gras artificiel.

    Le choix d'asset réemploie ``ScriptSlot``/``ScriptPickerPopup`` : c'est le
    picker standard de l'éditeur, avec recherche, plutôt qu'une énième liste
    déroulante qui divergerait de l'expérience des autres assets.
    """

    changed = pyqtSignal(str, int, bool)

    def __init__(self, parent=None, *, allow_inherit: bool = True):
        super().__init__(parent)
        self._project = None
        self._name = ""
        self._blocking = False
        self._allow_inherit = allow_inherit
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)
        self.font_slot = ScriptSlot(label("fontselect.choose_asset"), C.ACCENT,
                                    show_clear=allow_inherit)
        self.font_slot.set_callbacks(on_add=self._open_picker,
                                     on_open=self._open_picker,
                                     on_clear=self._clear)
        self.weight_box = QComboBox()
        self.weight_box.setFont(QFont(T.UI, T.MD)); self.weight_box.setStyleSheet(QSS.combobox)
        self.weight_box.setMinimumWidth(96)
        self.weight_box.setToolTip(tooltip(
            title=label("fontselect.weight_title"),
            body=label("fontselect.weight_tip")))
        self.bold_button = self._style_button("B", "fontselect.bold_tip", bold=True)
        self.italic_button = self._style_button("I", "fontselect.italic_tip", italic=True)
        lay.addWidget(self.font_slot, 1); lay.addWidget(self.weight_box)
        lay.addWidget(self.bold_button); lay.addWidget(self.italic_button)
        self.weight_box.currentIndexChanged.connect(lambda _index: self._sync_style_buttons())
        self.weight_box.currentIndexChanged.connect(self._emit_changed)
        self.bold_button.toggled.connect(self._toggle_bold)
        self.italic_button.toggled.connect(self._toggle_italic)

    def set_project(self, project):
        self._project = project

    def set_value(self, name: str, weight: int = 400, italic: bool = False):
        """Charge une valeur persistée, y compris l'ancien nom d'une source."""
        self._blocking = True
        assets = list(getattr(self._project, "font_assets", ()) or ())
        self._name = self._asset_name_for_legacy_source(name, assets)
        self._show_name(name)
        self._reload_weights(weight, italic)
        self._blocking = False

    def value(self) -> tuple[str, int, bool]:
        return self._name, int(self.weight_box.currentData() or 400), self.italic_button.isChecked()

    @staticmethod
    def _style_button(text: str, tooltip_key: str, *, bold: bool = False, italic: bool = False):
        button = QToolButton()
        title_key = "fontselect.bold_title" if bold else "fontselect.italic_title"
        button.setText(text); button.setToolTip(tooltip(
            title=label(title_key), body=label(tooltip_key)))
        button.setCheckable(True); button.setFixedSize(26, 26)
        font = QFont(T.UI, T.MD, QFont.Weight.Bold if bold else QFont.Weight.Normal)
        font.setItalic(italic); button.setFont(font)
        button.setStyleSheet(
            f"QToolButton{{background:{C.BG_DEEP};color:{C.TEXT_DIM};border:1px solid {C.BORDER};"
            "border-radius:3px;}"
            f"QToolButton:hover{{color:{C.ACCENT};border-color:{C.ACCENT};}}"
            f"QToolButton:checked{{background:{C.BG_SEL};color:{C.ACCENT};border-color:{C.ACCENT};}}"
            f"QToolButton:disabled{{color:{C.TEXT_MUTED};border-color:{C.BORDER_DARK};}}"
        )
        return button

    def _asset_name_for_legacy_source(self, name: str, assets: list) -> str:
        if not name or any(asset.name == name for asset in assets):
            return name
        for asset in assets:
            if name in asset.source_names() or any(face.source_name == name for face in asset.faces):
                return asset.name
        return name

    def _asset(self):
        return next((asset for asset in getattr(self._project, "font_assets", ())
                     if asset.name == self._name), None)

    def _show_name(self, original_name: str = ""):
        if not self._name:
            self.font_slot.set_script(label("uiinsp.text.font_scene"), icons.get("font", C.TEXT_DIM))
        elif self._asset() is not None:
            self.font_slot.set_script(self._name, icons.get("font", C.ACCENT))
        else:
            self.font_slot.set_script(label("fontselect.missing", name=original_name or self._name),
                                      icons.get("font", C.ACCENT_YLW))

    def _reload_weights(self, current: int, current_italic: bool = False):
        self.weight_box.clear()
        asset = self._asset()
        weights = sorted({face.weight for face in asset.faces}) if asset else []
        if not weights:
            weights = [400]
        for weight in weights:
            self.weight_box.addItem(weight_label(weight), weight)
        index = self.weight_box.findData(current)
        if index < 0:
            index = min(range(len(weights)), key=lambda i: abs(weights[i] - current))
        self.weight_box.setCurrentIndex(index)
        self.weight_box.setEnabled(bool(asset))
        self._sync_style_buttons(current_italic)

    def _faces(self) -> set[tuple[int, bool]]:
        asset = self._asset()
        return {(face.weight, face.italic) for face in asset.faces} if asset else set()

    def _sync_style_buttons(self, italic: bool | None = None):
        if italic is None:
            italic = self.italic_button.isChecked()
        faces = self._faces()
        weight = int(self.weight_box.currentData() or 400)
        # Changer de poids peut faire quitter la seule face italique disponible
        # (ex. Light Italic sans Bold Italic). On revient alors à la face droite
        # correspondante, jamais à une combinaison inexistante.
        if faces and (weight, italic) not in faces:
            italic = (weight, True) in faces
        has_bold = any(face_weight >= 600 for face_weight, _ in faces)
        has_italic = any(face_italic for _, face_italic in faces)
        self.bold_button.setVisible(has_bold)
        self.italic_button.setVisible(has_italic)
        self.bold_button.setEnabled(any(face_weight >= 600 and face_italic == italic
                                        for face_weight, face_italic in faces))
        self.italic_button.setEnabled((weight, not italic) in faces or (weight, italic) in faces)
        self.bold_button.blockSignals(True); self.italic_button.blockSignals(True)
        self.bold_button.setChecked(weight >= 600)
        self.italic_button.setChecked(bool(italic))
        self.bold_button.blockSignals(False); self.italic_button.blockSignals(False)

    def _set_face(self, weight: int, italic: bool):
        self._blocking = True
        index = self.weight_box.findData(weight)
        if index >= 0:
            self.weight_box.setCurrentIndex(index)
        self._sync_style_buttons(italic)
        self._blocking = False
        self._emit_changed()

    def _toggle_bold(self, checked: bool):
        if self._blocking:
            return
        faces = self._faces()
        weight = int(self.weight_box.currentData() or 400)
        italic = self.italic_button.isChecked()
        options = sorted(face_weight for face_weight, face_italic in faces
                         if face_italic == italic and (face_weight >= 600) == checked)
        if not options:
            self._sync_style_buttons(italic)
            return
        self._set_face(options[-1] if checked else min(options, key=lambda value: abs(value - weight)), italic)

    def _toggle_italic(self, checked: bool):
        if self._blocking:
            return
        weight = int(self.weight_box.currentData() or 400)
        if (weight, checked) not in self._faces():
            self._sync_style_buttons(not checked)
            return
        self._set_face(weight, checked)

    def _open_picker(self):
        entries = []
        if self._allow_inherit:
            entries.append((label("uiinsp.text.font_scene"), "", icons.get("font", C.TEXT_DIM)))
        entries += [(asset.name, asset.name, icons.get("font", C.ACCENT))
                    for asset in getattr(self._project, "font_assets", ())]
        if self._name and self._asset() is None:
            entries.append((label("fontselect.missing", name=self._name), self._name,
                            icons.get("font", C.ACCENT_YLW)))
        popup = ScriptPickerPopup(entries, C.ACCENT, parent=self, new_label=None)
        popup.picked.connect(self._picked)
        popup.show_below(self.font_slot)

    def _picked(self, name: str):
        if name == self._name:
            return
        self._name = name
        self._show_name()
        self._blocking = True
        self._reload_weights(400, False)
        self._blocking = False
        self._emit_changed()

    def _clear(self):
        self._picked("")

    def _emit_changed(self, _index: int = -1):
        if not self._blocking:
            self.changed.emit(*self.value())
