"""
ui/scene_manager/inspectors/web_player_card.py — la carte « WEB build » de la
fenêtre Project Settings (catégorie Build).

Deux modes exclusifs pour le lecteur web (cf. codegen/web_build.py) :
- Built-in : le lecteur fourni, habillé par des couleurs, une ombre
  et un contour. Ces réglages ne deviennent que des variables CSS.
- Custom CSS : le lecteur vierge et le CSS du projet. « Eject Web Template » copie
  ce lecteur dans `web_template/` pour en éditer le HTML et le JavaScript ; le CSS
  reste dans le champ du projet, sa seule source.

La carte reçoit `set_setting` de BuildPanel, qui en fait une commande annulable
et rappelle `refresh()` après exécution et annulation.
"""
from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from codegen.web_build import EJECTED_TEMPLATE, FRAME_SIZE, WEB_TEMPLATE, eject_template
from core.models.settings import WEB_BUTTON_BORDER_WIDTH_MAX
from core.project import Project
from ui.common.color_field import ColorField
from ui.common.labels import label
from ui.common.notice import tip
from ui.common.theme import C, T, QSS
from ui.common.tooltip import tooltip
from ui.common.widgets import CardInset, CollapsibleCard, W
from ui.scene_manager.inspectors.web_player_preview import WebPlayerPreview

# Les images du thème importées dans le projet, à côté du dossier éjecté.
THEME_FOLDER = "web_theme"
_LABEL_WIDTH = 120   # celle des autres catégories de Project Settings


def _fixed_row(text: str, widget: QWidget, lay: QVBoxLayout) -> None:
    """Libellé puis champ à sa taille naturelle, calé à gauche, comme les champs
    de la carte ROM build."""
    W.row(text, widget, lay, _LABEL_WIDTH)
    row = widget.parentWidget().layout()
    row.setStretchFactor(widget, 0)
    row.addStretch(1)

_SEGMENTED = f"""
QPushButton {{
    background: {C.BG_INPUT};
    color: {C.TEXT_DIM};
    border: 1px solid {C.BORDER_MID};
    border-radius: 3px;
    padding: 4px 14px;
}}
QPushButton:hover {{ background: {C.BG_HOVER}; color: {C.TEXT_HI}; }}
QPushButton:checked {{
    background: {C.BG_SEL};
    color: {C.TEXT_HI};
    border-color: {C.ACCENT};
}}
"""

# (réglage, clé du libellé) des couleurs du thème Built-in, dans l'ordre affiché.
_COLORS = (
    ("web_player_color", "projset.web_player_color"),
    ("web_text_color", "projset.web_text_color"),
    ("web_button_color", "projset.web_button_color"),
    ("web_button_border_color", "projset.web_button_border_color"),
    ("web_accent_color", "projset.web_accent_color"),
)
_FRAMES = (
    ("backstage", "projset.web_frame_backstage"),
    ("backstage-light", "projset.web_frame_backstage_light"),
    ("none", "projset.web_frame_none"),
    ("image", "projset.web_frame_image"),
)


class WebPlayerCard(CollapsibleCard):
    """Réglages du lecteur web : mode, thème Built-in, CSS personnalisé."""

    def __init__(self, project: Project, set_setting, parent=None):
        super().__init__(label('projset.web_build'), expanded=False, parent=parent)
        self._project = project
        self._set_setting = set_setting
        self._preview: WebPlayerPreview | None = None
        self._starting_preview = False
        body = self.body_layout

        status = QLabel(label('projset.web_build_output' if WEB_TEMPLATE.is_dir()
                              else 'projset.web_build_unavailable'))
        status.setWordWrap(True)
        status.setStyleSheet(f"color:{C.TEXT_DIM};")
        body.addWidget(status)
        if not WEB_TEMPLATE.is_dir():
            return

        # ── Mode : deux boutons côte à côte, exclusifs ────────────
        mode_box = QWidget()
        mode_row = QHBoxLayout(mode_box)
        mode_row.setContentsMargins(0, 4, 0, 4)
        mode_row.setSpacing(4)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_buttons = {}
        for mode, key, tip_key in (("builtin", 'projset.web_mode_builtin', 'projset.web_mode_builtin_tip'),
                                   ("custom", 'projset.web_mode_custom', 'projset.web_mode_custom_tip')):
            button = QPushButton(label(key))
            button.setCheckable(True)
            button.setStyleSheet(_SEGMENTED)
            button.setToolTip(tooltip(title=label(key), body=label(tip_key)))
            button.clicked.connect(lambda _=False, m=mode: self._set_setting("web_player_mode", m))
            self._mode_group.addButton(button)
            self._mode_buttons[mode] = button
            mode_row.addWidget(button)
        mode_row.addStretch(1)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        body.addLayout(columns)
        fields = QVBoxLayout()
        columns.addLayout(fields, 1)
        fields.addWidget(mode_box)

        settings = CardInset()
        self._builtin = QWidget()
        self._build_builtin(QVBoxLayout(self._builtin))
        settings.inset_layout.addWidget(self._builtin)
        self._custom = QWidget()
        self._build_custom(QVBoxLayout(self._custom))
        settings.inset_layout.addWidget(self._custom)
        fields.addWidget(settings)
        fields.addStretch(1)

        preview_box = CardInset()
        preview_box.setMinimumWidth(240)
        # 340 px d'aperçu, plus le padding du bloc en haut et en bas.
        preview_box.setFixedHeight(340 + 2 * CardInset.PADDING)
        self._preview_layout = preview_box.inset_layout
        toolbar = QHBoxLayout()
        title = QLabel(label('projset.web_preview_title'))
        title.setFont(QFont(T.UI, T.MD))
        title.setStyleSheet(f"color:{C.TEXT_DIM};")
        toolbar.addWidget(title, 1)
        self._preview_mode = QComboBox()
        self._preview_mode.setAccessibleName(label('projset.web_preview_view'))
        self._preview_mode.setFont(QFont(T.UI, T.MD))
        self._preview_mode.setStyleSheet(QSS.combobox)
        for mode in ("desktop", "portrait", "landscape"):
            self._preview_mode.addItem(label(f'projset.web_preview_{mode}'), mode)
        self._preview_mode.setCurrentIndex(self._preview_mode.findData("portrait"))
        self._preview_mode.currentIndexChanged.connect(self._set_preview_layout)
        toolbar.addWidget(self._preview_mode)
        self._preview_layout.addLayout(toolbar)
        self._preview_notice = QLabel()
        self._preview_notice.setWordWrap(True)
        self._preview_layout.addWidget(self._preview_notice)
        self._preview_notice.hide()
        columns.addWidget(preview_box, 1, Qt.AlignmentFlag.AlignTop)
        tip('web.itch_integration', body)
        self.toggled.connect(self._start_preview)
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self._start_preview(not self._body.isHidden())

    def _start_preview(self, expanded):
        if expanded and self.isVisible():
            self.prepare_preview()
            self._refresh_preview()

    def prepare_preview(self):
        if not hasattr(self, "_preview_layout"):
            return
        if self._starting_preview or self._preview is not None or not self._preview_notice.isHidden():
            return
        self._starting_preview = True
        dialog = self.window()
        try:
            if isinstance(dialog, QDialog):
                # Ancre la surface WebEngine dans la boîte encore masquée.
                dialog.winId()
            self._preview = WebPlayerPreview(self._preview_layout.parentWidget())
        except (ImportError, OSError) as exc:
            self._preview_notice.setText(label('projset.web_preview_unavailable'))
            self._preview_notice.setToolTip(str(exc))
            self._preview_notice.show()
            self._preview_mode.setEnabled(False)
            return
        finally:
            self._starting_preview = False
        self._preview_layout.addWidget(self._preview.view, 1)
        if isinstance(dialog, QDialog):
            dialog.finished.connect(self._close_preview)
        self._set_preview_layout()

    def _set_preview_layout(self):
        if self._preview is not None:
            self._preview.set_layout(self._preview_mode.currentData())

    def _close_preview(self):
        if self._preview is not None:
            self._preview_layout.parentWidget().destroyed.disconnect(self._preview.close)
            self._preview.close()
            self._preview.view.deleteLater()
            self._preview = None
        dialog = self.window()
        if isinstance(dialog, QDialog):
            dialog.finished.disconnect(self._close_preview)

    def _refresh_preview(self, **colors):
        if self._preview is not None and self.isVisible() and not self._body.isHidden():
            settings = self._project.settings
            if settings.web_player_mode == "custom":
                settings = replace(settings, web_custom_css=self._css.toPlainText())
            elif colors:
                settings = replace(settings, **colors)
            self._preview.update(settings, self._project.root, self._project.project_file.stem)

    # ── Built-in ────────────────────────────────────────────────

    def _build_builtin(self, lay: QVBoxLayout):
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._color_fields = {}
        for field, key in _COLORS:
            color = ColorField()
            color.previewed.connect(lambda value, f=field: self._refresh_preview(**{f: value}))
            color.committed.connect(lambda value, f=field: self._set_setting(f, value))
            _fixed_row(label(key), color, lay)
            self._color_fields[field] = color

        self._spin_border = QSpinBox()
        self._spin_border.setRange(0, WEB_BUTTON_BORDER_WIDTH_MAX)
        self._spin_border.setSuffix(" px")
        self._spin_border.setFixedWidth(64)
        self._spin_border.setFont(QFont(T.MONO, T.MD))
        self._spin_border.setStyleSheet(QSS.spinbox)
        self._spin_border.valueChanged.connect(
            lambda v: self._set_setting("web_button_border_width", int(v)))
        _fixed_row(label('projset.web_button_border_width'), self._spin_border, lay)

        self._chk_shadow = QCheckBox(label('projset.web_player_shadow'))
        self._chk_shadow.setFont(QFont(T.UI, T.MD))
        self._chk_shadow.setStyleSheet(QSS.checkbox)
        self._chk_shadow.setToolTip(tooltip(title=label('projset.web_player_shadow'),
                                            body=label('projset.web_player_shadow_tip')))
        self._chk_shadow.toggled.connect(lambda v: self._set_setting("web_player_shadow", bool(v)))
        _fixed_row("", self._chk_shadow, lay)

        self._combo_frame = QComboBox()
        self._combo_frame.setFont(QFont(T.UI, T.MD))
        self._combo_frame.setStyleSheet(QSS.combobox)
        for value, key in _FRAMES:
            self._combo_frame.addItem(label(key), value)
        self._combo_frame.setToolTip(tooltip(title=label('projset.web_frame'),
                                             body=label('projset.web_frame_tip')))
        self._combo_frame.activated.connect(
            lambda i: self._set_setting("web_frame", self._combo_frame.itemData(i)))
        _fixed_row(label('projset.web_frame'), self._combo_frame, lay)

        self._frame_image = self._image_row(
            lay, "web_frame_image", 'projset.web_frame_image_file', 'projset.web_frame_image_tip',
            width=FRAME_SIZE[0], height=FRAME_SIZE[1])

    def _image_row(self, lay: QVBoxLayout, field: str, key: str, tip_key: str, **tip_args) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        name = QLabel()
        name.setFont(QFont(T.MONO, T.XS))
        name.setStyleSheet(f"color:{C.TEXT_MUTED};")
        choose = QPushButton(label('projset.web_choose_image'))
        choose.setStyleSheet(QSS.button_neutral)
        choose.setCursor(Qt.CursorShape.PointingHandCursor)
        choose.setToolTip(tooltip(title=label(key), body=label(tip_key, **tip_args)))
        choose.clicked.connect(lambda: self._pick_image(field, key))
        clear = W.btn_remove(label('projset.web_clear_image'))
        clear.clicked.connect(lambda: self._set_setting(field, ""))
        row.addWidget(choose)
        row.addWidget(name)
        row.addWidget(clear)
        _fixed_row(label(key), box, lay)
        box.name_label, box.clear_button = name, clear
        return box

    def _pick_image(self, field: str, key: str):
        path, _ = QFileDialog.getOpenFileName(
            self, label(key), str(self._project.root),
            f"{label('projset.web_image_filter')} (*.png *.webp *.svg)")
        if path:
            self._set_setting(field, self._import_image(Path(path)))

    def _import_image(self, source: Path) -> str:
        """Chemin relatif au projet. Une image hors du projet y est copiée, dans
        `web_theme/`, sans jamais remplacer une autre image du même nom."""
        root = self._project.root
        try:
            return source.resolve().relative_to(root).as_posix()
        except ValueError:
            pass
        folder = root / THEME_FOLDER
        folder.mkdir(exist_ok=True)
        target, n = folder / source.name, 2
        while target.exists() and target.read_bytes() != source.read_bytes():
            target, n = folder / f"{source.stem}_{n}{source.suffix}", n + 1
        if not target.exists():
            shutil.copyfile(source, target)
        return target.relative_to(root).as_posix()

    # ── Custom CSS ──────────────────────────────────────────────

    def _build_custom(self, lay: QVBoxLayout):
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._css = QPlainTextEdit()
        self._css.setFont(QFont(T.MONO, T.MD))
        self._css.setStyleSheet(
            f"QPlainTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_HI};"
            f" border:1px solid {C.BORDER_MID}; border-radius:4px; padding:4px;}}"
            f"QPlainTextEdit:focus{{border:1px solid {C.ACCENT};}}")
        # Du code : pas de retour à la ligne automatique, une tabulation de deux espaces.
        self._css.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._css.setTabStopDistance(self._css.fontMetrics().horizontalAdvance("  "))
        self._css.setPlaceholderText(".player {\n  background: darkgreen;\n}")
        self._css.setMinimumHeight(180)
        self._css.setToolTip(tooltip(title=label('projset.web_custom_css'),
                                     body=label('projset.web_custom_css_tip')))
        # Une commande annulable par pause de frappe, pas par touche.
        self._css_timer = QTimer(self)
        self._css_timer.setSingleShot(True)
        self._css_timer.setInterval(600)
        self._css_timer.timeout.connect(
            lambda: self._set_setting("web_custom_css", self._css.toPlainText()))
        self._css.textChanged.connect(self._css_timer.start)
        self._css.textChanged.connect(self._refresh_preview)
        lay.addWidget(self._css)

        eject_row = QHBoxLayout()
        eject_row.setContentsMargins(0, 0, 0, 0)
        eject = QPushButton(label('projset.web_eject'))
        eject.setStyleSheet(QSS.button_neutral)
        eject.setCursor(Qt.CursorShape.PointingHandCursor)
        eject.setToolTip(tooltip(title=label('projset.web_eject'),
                                 body=label('projset.web_eject_tip', folder=EJECTED_TEMPLATE)))
        eject.clicked.connect(self._eject)
        eject_row.addWidget(eject)
        eject_row.addStretch(1)
        lay.addLayout(eject_row)

    def _eject(self):
        destination = self._project.root / EJECTED_TEMPLATE
        if destination.exists():
            answer = QMessageBox.question(
                self, label('projset.web_eject'),
                label('projset.web_eject_overwrite', folder=EJECTED_TEMPLATE))
            if answer != QMessageBox.StandardButton.Yes:
                return
        eject_template(destination, self._project.project_file.stem)
        self._refresh_preview()

    # ── Synchronisation ─────────────────────────────────────────

    def refresh(self):
        if not WEB_TEMPLATE.is_dir():
            return
        s = self._project.settings
        custom = s.web_player_mode == "custom"
        self._mode_buttons[s.web_player_mode].setChecked(True)
        self._builtin.setVisible(not custom)
        self._custom.setVisible(custom)

        for field, color in self._color_fields.items():
            color.set_value(getattr(s, field))
        self._spin_border.blockSignals(True)
        self._spin_border.setValue(s.web_button_border_width)
        self._spin_border.blockSignals(False)
        self._chk_shadow.blockSignals(True)
        self._chk_shadow.setChecked(s.web_player_shadow)
        self._chk_shadow.blockSignals(False)
        self._combo_frame.setCurrentIndex(self._combo_frame.findData(s.web_frame))
        self._frame_image.name_label.setText(s.web_frame_image or label('projset.web_no_image'))
        self._frame_image.clear_button.setEnabled(bool(s.web_frame_image))
        self._frame_image.parentWidget().setVisible(s.web_frame == "image")

        if self._css.toPlainText() != s.web_custom_css:
            self._css_timer.stop()
            self._css.blockSignals(True)
            self._css.setPlainText(s.web_custom_css)
            self._css.blockSignals(False)
        self._refresh_preview()
