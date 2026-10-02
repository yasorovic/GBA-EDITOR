"""
ui/scene_manager/inspectors/project_settings_dialog.py — fenêtre « Project
Settings », ouverte depuis Game → Project Settings. Même pattern que
`SettingsDialog` (ui/common/settings_dialog.py) : une colonne de catégories à
gauche, un panneau à droite, chaque champ se sauvegarde à l'instant où il
change (undo par `SetFieldCmd`, persistance immédiate dans project.json).

Ce que cette fenêtre regroupe (2026-08-25) — tout ce que `ProjectSettings`
porte SAUF l'identité du projet :

  - **Build** — emplacements de sauvegarde, cartouche visée, debug build.
  - **Visual** — backdrop par défaut du projet ENTIER (pas de la scène) et
    transition de scène par défaut. Ce que le rendu montre sans qu'un script
    intervienne, par opposition à Sound (ce qu'il fait entendre) et à Build
    (comment il est compilé).
  - **Sound** — taux d'échantillonnage des effets et canaux logiciels.
  - **Input** — actions nommées liées à un combo de boutons physiques
    (placeholder, cf. `InputsCard` — rien ne les consomme encore).
  - **Languages** — déclaration des langues, reprend `LanguagesCard` telle
    quelle (ROADMAP v0.9).
  - **Collisions** — matrice triangulaire de tags qui s'ignorent
    (ROADMAP v0.23), tags renommables/déclarables/retirables en place.

Ce qui RESTE dans `ProjectInspector` (panneau latéral du Scene Manager, visible
en permanence quand rien n'est sélectionné) : auteur, version, scène de
départ — l'identité du projet, pas sa configuration. Ainsi que la carte
Content (compteurs d'assets, lecture seule) : ce n'est pas un réglage, juste
un aperçu utile à garder sous les yeux.

Le dialogue suppose un projet déjà chargé (`window._open_project_settings`
garde contre `self.project is None` avant de l'ouvrir) : contrairement à
ProjectInspector, aucun panneau ici ne gère l'absence de projet.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QListWidget, QListWidgetItem, QStackedWidget, QScrollArea,
    QLineEdit, QComboBox, QSpinBox, QCheckBox, QPushButton, QColorDialog,
)
from PyQt6.QtGui import QFont, QColor, QPainter, QFontMetrics
from PyQt6.QtCore import Qt, QEvent, QPointF

from core.project import Project
from core.models.settings import Language, InputBinding, InputSequence, pair_key
from core.models.components import CollisionBoxComponent
from core.history import (get_history, SetFieldCmd, AddListItemCmd,
                          RemoveListItemCmd, RenameCollisionTagCmd,
                          RemoveCollisionTagCmd)
from core.command_dispatcher import get_dispatcher
from core.models.gba_color import bgr555_to_rgb888, rgb888_to_bgr555
from ui.common.theme import C, T, QSS
from ui.common.widgets import W
from ui.common.notice import note, tip
from ui.scene_manager.inspectors.languages_card import LanguagesCard
from ui.scene_manager.inspectors.inputs_card import InputsCard
from ui.scene_manager.inspectors.sequences_card import SequencesCard
from ui.scene_manager.inspectors.axes_card import AxesCard
from ui.scene_manager.inspectors.project_inspector import TRANSITION_LABELS


def _category_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont(T.UI, T.LG, QFont.Weight.DemiBold))
    lbl.setStyleSheet(f"color:{C.TEXT_HI};")
    return lbl


def _row(label: str, widget: QWidget, layout: QVBoxLayout, stretch: bool = True):
    """Une ligne label + champ — même geste que ProjectInspector._row, en
    fonction libre puisque chaque panneau ici est autonome."""
    if isinstance(widget, QLineEdit):
        widget.setFont(QFont(T.MONO, T.MD))
        widget.setStyleSheet(QSS.lineedit)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    lbl = QLabel(label)
    lbl.setFont(QFont(T.UI, T.SM))
    lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
    lbl.setFixedWidth(120)
    row.addWidget(lbl)
    row.addWidget(widget, 1 if stretch else 0)
    if not stretch:
        row.addStretch(1)
    layout.addLayout(row)


# ── Build ───────────────────────────────────────────────────────────────

class BuildPanel(QWidget):
    """Ce que la compilation produit — emplacements de sauvegarde, cartouche
    visée, debug build. Voir Sound pour l'audio et Visual pour le rendu."""

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._blocking = False

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_category_title(label('projset.build')))

        # ── Emplacements de sauvegarde ────────────────────────────
        self._spin_slots = QSpinBox()
        self._spin_slots.setRange(1, 99)
        self._spin_slots.setFixedWidth(64)
        self._spin_slots.setFont(QFont(T.MONO, T.MD))
        self._spin_slots.setStyleSheet(QSS.spinbox)
        self._spin_slots.setToolTip(tooltip(
            title=label('projset.save_slots'), body=label('projset.save_slots_tip'),
            note=label('projset.save_slots_note')))
        self._spin_slots.valueChanged.connect(
            lambda v: self._set_setting("save_slots", int(v)))
        _row(label('projset.save_slots'), self._spin_slots, lay, stretch=False)

        # ── Cartouche visée ───────────────────────────────────────
        from codegen.rom_report import CARTRIDGE_SIZES_MIB
        self._combo_cart = QComboBox()
        self._combo_cart.setFont(QFont(T.UI, T.MD))
        self._combo_cart.setStyleSheet(QSS.combobox)
        for mib in CARTRIDGE_SIZES_MIB:
            self._combo_cart.addItem(f"{mib} MiB", mib)
        self._combo_cart.setToolTip(tooltip(
            title=label('projset.cartridge_title'), body=label('projset.cartridge_tip'),
            note=label('projset.cartridge_note')))
        self._combo_cart.currentIndexChanged.connect(
            lambda i: self._set_setting("cartridge_mib", int(self._combo_cart.itemData(i) or 4)))
        _row(label('projset.cartridge'), self._combo_cart, lay, stretch=False)

        # ── Build debug ─────────────────────────────────────────────
        self._chk_debug = QCheckBox(label('projset.debug_build'))
        self._chk_debug.setFont(QFont(T.UI, T.MD))
        self._chk_debug.setToolTip(tooltip(
            title=label('projset.debug_build'), body=label('projset.debug_tip'),
            note=label('projset.debug_note')))
        self._chk_debug.toggled.connect(
            lambda v: self._set_setting("debug_build", bool(v)))
        _row(label('projset.build'), self._chk_debug, lay, stretch=False)

        lay.addStretch()
        self._refresh_fields()

    def _refresh_fields(self):
        p = self._project
        self._spin_slots.blockSignals(True)
        self._spin_slots.setValue(getattr(p.settings, "save_slots", 1))
        self._spin_slots.blockSignals(False)

        self._chk_debug.blockSignals(True)
        self._chk_debug.setChecked(getattr(p.settings, "debug_build", True))
        self._chk_debug.blockSignals(False)

        self._combo_cart.blockSignals(True)
        idx = self._combo_cart.findData(getattr(p.settings, "cartridge_mib", 4))
        self._combo_cart.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo_cart.blockSignals(False)

    def _persist(self):
        self._project.save_settings()
        self._blocking = True
        try:
            self._refresh_fields()   # resynchronise l'UI après execute ET undo
        finally:
            self._blocking = False

    def _set_setting(self, field: str, value):
        if self._blocking:
            return
        old = getattr(self._project.settings, field, None)
        if old == value:
            return
        get_history().push(SetFieldCmd(
            self._project.settings, field, old, value,
            label=f"Projet.{field}", persist_fn=self._persist,
        ))


# ── Visual ──────────────────────────────────────────────────────────────

class VisualPanel(QWidget):
    """Rendu par défaut du projet ENTIER — backdrop et transition de scène.
    Chaque scène peut surcharger les deux depuis son propre inspecteur
    (SceneInspector) ; ce panneau règle ce qu'elle hérite tant qu'elle ne le
    fait pas."""

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._blocking = False

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_category_title(label('projset.visual')))

        # ── Backdrop (défaut projet) ──────────────────────────────
        # Couleur de PAL_BG_RAM[0] : ce que le hardware affiche là où aucun
        # calque ni sprite ne dessine. Réglée ici pour TOUT le projet ; une
        # scène peut la surcharger depuis son propre inspecteur.
        bd_box = QWidget()
        bd_row = QHBoxLayout(bd_box)
        bd_row.setContentsMargins(0, 0, 0, 0)
        bd_row.setSpacing(6)
        self._btn_backdrop = QPushButton()
        self._btn_backdrop.setFixedSize(40, 22)
        self._btn_backdrop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_backdrop.setToolTip(tooltip(
            title=label('projset.backdrop_title'), body=label('projset.backdrop_tip'),
            note=label('projset.backdrop_note')))
        self._btn_backdrop.clicked.connect(self._pick_backdrop)
        self._lbl_backdrop = QLabel()
        self._lbl_backdrop.setFont(QFont(T.MONO, T.XS))
        self._lbl_backdrop.setStyleSheet(f"color:{C.TEXT_MUTED};")
        bd_row.addWidget(self._btn_backdrop)
        bd_row.addWidget(self._lbl_backdrop)
        bd_row.addStretch(1)
        _row(label('projset.backdrop'), bd_box, lay)

        # ── Transition de scène (défaut projet) ───────────────────
        # Le fondu joué à chaque changement de scène. Réglé une fois ici pour
        # tout le jeu ; une scène peut le surcharger depuis son inspecteur.
        trans_box = QWidget()
        trans_row = QHBoxLayout(trans_box)
        trans_row.setContentsMargins(0, 0, 0, 0)
        trans_row.setSpacing(6)
        self._combo_trans = QComboBox()
        self._combo_trans.setFont(QFont(T.UI, T.MD))
        self._combo_trans.setStyleSheet(QSS.combobox)
        for kind, lbl_key in TRANSITION_LABELS:
            self._combo_trans.addItem(label(lbl_key), kind)
        self._combo_trans.setToolTip(tooltip(
            title=label('projset.transition_title'), body=label('projset.transition_tip'),
            note=label('projset.transition_note')))
        self._combo_trans.currentIndexChanged.connect(
            lambda i: self._set_setting("transition_kind",
                                        self._combo_trans.itemData(i) or "none"))
        self._spin_trans = QSpinBox()
        self._spin_trans.setRange(1, 255)
        self._spin_trans.setFixedWidth(64)
        self._spin_trans.setSuffix(" f")
        self._spin_trans.setFont(QFont(T.MONO, T.MD))
        self._spin_trans.setStyleSheet(QSS.spinbox)
        self._spin_trans.setToolTip(tooltip(
            title=label('projset.frames_title'), body=label('projset.frames_tip')))
        self._spin_trans.valueChanged.connect(
            lambda v: self._set_setting("transition_frames", int(v)))
        trans_row.addWidget(self._combo_trans, 1)
        trans_row.addWidget(self._spin_trans)
        _row(label('projset.transition'), trans_box, lay)

        lay.addStretch()
        self._refresh_fields()

    def _refresh_fields(self):
        p = self._project
        v = p.settings.backdrop_color
        r, g, b = bgr555_to_rgb888(v)
        self._btn_backdrop.setStyleSheet(
            f"QPushButton{{background:rgb({r},{g},{b});"
            f"border:1px solid {C.BORDER_MID};border-radius:3px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}"
        )
        self._lbl_backdrop.setText(f"0x{v:04X}")

        kind = getattr(p.settings, "transition_kind", "none")
        self._combo_trans.blockSignals(True)
        idx = self._combo_trans.findData(kind)
        self._combo_trans.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo_trans.blockSignals(False)
        self._spin_trans.blockSignals(True)
        self._spin_trans.setValue(getattr(p.settings, "transition_frames", 16))
        self._spin_trans.blockSignals(False)
        # La durée ne veut rien dire sans fondu.
        self._spin_trans.setEnabled(kind != "none")

    def _persist(self):
        self._project.save_settings()
        self._blocking = True
        try:
            self._refresh_fields()
        finally:
            self._blocking = False

    def _set_setting(self, field: str, value, extra_persist=None):
        if self._blocking:
            return
        old = getattr(self._project.settings, field, None)
        if old == value:
            return

        def _do_persist():
            self._persist()
            if extra_persist:
                extra_persist()

        get_history().push(SetFieldCmd(
            self._project.settings, field, old, value,
            label=f"Projet.{field}", persist_fn=_do_persist,
        ))

    def _pick_backdrop(self):
        """Couleur de backdrop par défaut du projet — quantifiée en BGR555 :
        la valeur stockée est celle que la console affichera réellement, pas
        la couleur 8 bits/canal choisie dans le dialogue."""
        r, g, b = bgr555_to_rgb888(self._project.settings.backdrop_color)
        col = QColorDialog.getColor(
            QColor(r, g, b), self, label('projset.project_backdrop_color'),
            QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if not col.isValid():
            return
        self._set_setting(
            "backdrop_color", rgb888_to_bgr555(col.red(), col.green(), col.blue()),
            # Les scènes sans override affichent cette couleur : prévenir le
            # canvas pour qu'il se repeigne (même signal que SceneInspector).
            extra_persist=lambda: get_dispatcher()._emit("backdrop_changed"),
        )


# ── Sound ───────────────────────────────────────────────────────────────

class SoundPanel(QWidget):
    """Audio par défaut du projet — taux d'échantillonnage des effets et
    canaux logiciels. Surchargeable par effet (cf. Sfx.sample_rate)."""

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._blocking = False

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_category_title(label('projset.sound')))

        # ── Taux d'échantillonnage des effets (défaut projet) ──────
        # « Source » ne ré-échantillonne rien : c'est le défaut, parce que
        # dégrader d'office un projet existant serait le faire dans le dos
        # de son auteur.
        self._combo_rate = QComboBox()
        self._combo_rate.setFont(QFont(T.UI, T.MD))
        self._combo_rate.setStyleSheet(QSS.combobox)
        for value, disp in ((0, label('projset.source_no_resampling')), (8000, "8 000 Hz"),
                            (11025, "11 025 Hz"), (16000, "16 000 Hz"),
                            (22050, "22 050 Hz"), (32000, "32 000 Hz")):
            self._combo_rate.addItem(disp, value)
        self._combo_rate.setToolTip(tooltip(
            title=label('projset.rate_title'), body=label('projset.rate_tip'),
            note=label('projset.rate_note')))
        self._combo_rate.currentIndexChanged.connect(
            lambda i: self._set_setting("sfx_sample_rate", int(self._combo_rate.itemData(i) or 0)))
        _row(label('projset.sfx_rate'), self._combo_rate, lay, stretch=False)

        # ── Canaux logiciels ──────────────────────────────────────
        # Musique et effets se les partagent. Le coût est exact et vient du
        # modèle, pas d'un chiffre recopié ici (cf. audio.sound_channels_bytes).
        from core.models.audio import (SOUND_CHANNELS_MIN, SOUND_CHANNELS_MAX,
                                       SOUND_HANDLE_SLOTS, sound_channels_bytes)
        self._spin_channels = QSpinBox()
        self._spin_channels.setRange(SOUND_CHANNELS_MIN, SOUND_CHANNELS_MAX)
        self._spin_channels.setFixedWidth(64)
        self._spin_channels.setFont(QFont(T.MONO, T.MD))
        self._spin_channels.setStyleSheet(QSS.spinbox)
        self._spin_channels.setToolTip(tooltip(
            title=label('projset.sound_channels'),
            body=label('projset.channels_tip', handle_slots=SOUND_HANDLE_SLOTS),
            note=label('projset.channels_note',
                       channel_bytes=sound_channels_bytes(1) - sound_channels_bytes(0),
                       buffer_bytes=sound_channels_bytes(0),
                       default_bytes=sound_channels_bytes(8))))
        self._spin_channels.valueChanged.connect(
            lambda v: self._set_setting("sound_channels", int(v)))
        _row(label('projset.sound_channels'), self._spin_channels, lay, stretch=False)

        lay.addStretch()
        self._refresh_fields()

    def _refresh_fields(self):
        p = self._project
        self._combo_rate.blockSignals(True)
        idx = self._combo_rate.findData(getattr(p.settings, "sfx_sample_rate", 0))
        self._combo_rate.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo_rate.blockSignals(False)

        self._spin_channels.blockSignals(True)
        self._spin_channels.setValue(getattr(p.settings, "sound_channels", 8))
        self._spin_channels.blockSignals(False)

    def _persist(self):
        self._project.save_settings()
        self._blocking = True
        try:
            self._refresh_fields()
        finally:
            self._blocking = False

    def _set_setting(self, field: str, value):
        if self._blocking:
            return
        old = getattr(self._project.settings, field, None)
        if old == value:
            return
        get_history().push(SetFieldCmd(
            self._project.settings, field, old, value,
            label=f"Projet.{field}", persist_fn=self._persist,
        ))


# ── Input (placeholder) ────────────────────────────────────────────────

class InputsPanel(QWidget):
    """Enveloppe autour de `InputsCard` — même pattern que LanguagesPanel :
    la carte SIGNALE un geste, ce panneau en fait une commande annulable."""

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_category_title(label('projset.input')))

        self._card = InputsCard()
        self._card.input_added.connect(self._add_input)
        self._card.input_removed.connect(self._remove_input)
        self._card.input_field_changed.connect(self._set_input_field)
        lay.addWidget(self._card)

        self._sequences_card = SequencesCard()
        self._sequences_card.sequence_added.connect(self._add_sequence)
        self._sequences_card.sequence_removed.connect(self._remove_sequence)
        self._sequences_card.sequence_field_changed.connect(self._set_sequence_field)
        lay.addWidget(self._sequences_card)

        self._axes_card = AxesCard()
        self._axes_card.axis_added.connect(self._add_axis)
        self._axes_card.axis_removed.connect(self._remove_axis)
        self._axes_card.axis_field_changed.connect(self._set_axis_field)
        lay.addWidget(self._axes_card)

        lay.addStretch()

        self._card.load(project)
        self._sequences_card.load(project)
        self._axes_card.load(project)

    def _persist(self):
        self._project.save_settings()

    def _refresh_both(self):
        # Un input renommé/retiré change la liste que la carte Axes propose
        # comme côté d'axe (`_side_choices`) — les trois cartes se
        # rafraîchissent ensemble, quelle que soit celle qui a bougé.
        self._persist()
        self._card.refresh()
        self._sequences_card.refresh()
        self._axes_card.refresh()

    def _set_input_field(self, binding, field: str, value):
        old = getattr(binding, field, None)
        if old == value:
            return
        get_history().push(SetFieldCmd(
            binding, field, old, value,
            label=f"Input.{field}",
            persist_fn=self._refresh_both,
        ))

    def _add_input(self):
        binding = InputBinding(name=self._card.free_name())
        get_history().push(AddListItemCmd(
            self._project.settings.inputs, binding,
            label=f"Ajouter l'input {binding.name}",
            persist_fn=self._refresh_both,
        ))

    def _remove_input(self, binding):
        get_history().push(RemoveListItemCmd(
            self._project.settings.inputs, binding,
            label=f"Retirer l'input {binding.name}",
            persist_fn=self._refresh_both,
        ))

    def _set_axis_field(self, axis, field: str, value):
        old = getattr(axis, field, None)
        if old == value:
            return
        get_history().push(SetFieldCmd(
            axis, field, old, value,
            label=f"Axis.{field}",
            persist_fn=self._refresh_both,
        ))

    def _add_axis(self):
        from core.models.settings import InputAxis
        axis = InputAxis(name=self._axes_card.free_name(),
                         negative="left", positive="right")
        get_history().push(AddListItemCmd(
            self._project.settings.axes, axis,
            label=f"Ajouter l'axe {axis.name}",
            persist_fn=self._refresh_both,
        ))

    def _remove_axis(self, axis):
        get_history().push(RemoveListItemCmd(
            self._project.settings.axes, axis,
            label=f"Retirer l'axe {axis.name}",
            persist_fn=self._refresh_both,
        ))

    def _set_sequence_field(self, seq, field: str, value):
        old = getattr(seq, field, None)
        if old == value:
            return
        get_history().push(SetFieldCmd(
            seq, field, old, value,
            label=f"Sequence.{field}",
            persist_fn=self._refresh_both,
        ))

    def _add_sequence(self):
        seq = InputSequence(name=self._sequences_card.free_name())
        get_history().push(AddListItemCmd(
            self._project.settings.sequences, seq,
            label=f"Ajouter la séquence {seq.name}",
            persist_fn=self._refresh_both,
        ))

    def _remove_sequence(self, seq):
        get_history().push(RemoveListItemCmd(
            self._project.settings.sequences, seq,
            label=f"Retirer la séquence {seq.name}",
            persist_fn=self._refresh_both,
        ))


# ── Languages ───────────────────────────────────────────────────────────

class LanguagesPanel(QWidget):
    """Enveloppe autour de `LanguagesCard` (ROADMAP v0.9) — la carte SIGNALE
    un geste, ce panneau en fait une commande annulable, exactement comme le
    faisait ProjectInspector avant que Languages n'en sorte."""

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._blocking = False

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_category_title(label('projset.languages')))

        # ── Police par défaut ─────────────────────────────────────
        # Celle qu'une zone ou `text.draw` emploie sans choix explicite. Une
        # langue peut la remplacer dans la carte ci-dessous ; la couverture des
        # autres FontAsset reste dans leur inspecteur.
        self._combo_fallback = QComboBox()
        self._combo_fallback.setFont(QFont(T.UI, T.MD))
        self._combo_fallback.setStyleSheet(QSS.combobox)
        self._combo_fallback.setToolTip(tooltip(
            title=label('projset.default_font'), body=label('projset.default_font_tip'),
            note=label('projset.default_font_note')))
        self._combo_fallback.currentIndexChanged.connect(self._on_fallback_changed)
        _row(label('projset.default_font'), self._combo_fallback, lay)

        self._card = LanguagesCard()
        self._card.set_expanded(True)   # dépliée d'office : c'est tout l'écran ici
        self._card.source_field_changed.connect(self._set_source_field)
        self._card.language_added.connect(self._add_language)
        self._card.language_removed.connect(self._remove_language)
        self._card.language_field_changed.connect(self._set_language_field)
        lay.addWidget(self._card)
        lay.addStretch()

        self._card.load(project)
        self._refresh_fallback()

    # ── Police par défaut ─────────────────────────────────────────

    def _refresh_fallback(self):
        """(Re)synchronise le combo depuis settings.default_font — au chargement
        ET après chaque mutation (donc aussi après un undo)."""
        self._blocking = True
        try:
            self._combo_fallback.clear()
            self._combo_fallback.addItem(label('common.none_paren'), "")
            try:
                from codegen.font_emit import encodable_project_fonts
                fonts = encodable_project_fonts(self._project)
            except Exception:
                fonts = list(self._project.fonts)
            for f in fonts:
                self._combo_fallback.addItem(f.name, f.name)
            cur = getattr(self._project.settings, "default_font", "") or ""
            idx = self._combo_fallback.findData(cur)
            if idx < 0 and cur:
                # Police disparue (renommée/supprimée hors d'ici) : la garder
                # visible plutôt que de la réécrire silencieusement.
                self._combo_fallback.addItem(label('projset.cur_not_found', cur=cur), cur)
                idx = self._combo_fallback.findData(cur)
            self._combo_fallback.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self._blocking = False

    def _on_fallback_changed(self, _idx: int):
        if self._blocking:
            return
        value = self._combo_fallback.currentData() or ""
        old = getattr(self._project.settings, "default_font", "") or ""
        if old == value:
            return
        get_history().push(SetFieldCmd(
            self._project.settings, "default_font", old, value,
            label="Projet.default_font",
            persist_fn=lambda: (self._persist(), self._refresh_fallback()),
        ))

    def _persist(self):
        self._project.save_settings()

    def _set_source_field(self, field: str, value: str):
        """La langue source n'a pas de fichier side : le maître EST sa
        langue. La déclarer sert à la nommer."""
        if field == "code" and value and any(
                l.code == value for l in self._project.settings.languages):
            self._card.refresh()   # code déjà pris par une traduction
            return
        self._push_lang(self._project.settings.source_lang, field, value)

    def _set_language_field(self, lang, field: str, value):
        self._push_lang(lang, field, value)

    def _push_lang(self, obj, field: str, value):
        old = getattr(obj, field, None)
        if old == value:
            return
        get_history().push(SetFieldCmd(
            obj, field, old, value,
            label=f"Langue.{field}",
            persist_fn=lambda: (self._sync_translation_files(), self._persist(), self._card.refresh()),
        ))

    def _add_language(self):
        """Une langue déclarée arrive AVEC un code utilisable : elle doit
        pouvoir nommer son fichier avant même d'être renommée."""
        lang = Language(code=self._card.free_code())
        get_history().push(AddListItemCmd(
            self._project.settings.languages, lang,
            label=f"Ajouter la langue {lang.code}",
            persist_fn=lambda: (self._sync_translation_files(), self._persist(), self._card.refresh()),
        ))

    def _remove_language(self, lang):
        get_history().push(RemoveListItemCmd(
            self._project.settings.languages, lang,
            label=f"Retirer la langue {lang.code}",
            persist_fn=lambda: (self._sync_translation_files(), self._persist(), self._card.refresh()),
        ))

    def _sync_translation_files(self):
        """Un fichier par langue déclarée, et rien de supprimé — cf.
        ProjectInspector avant son déménagement pour le détail des trois
        pièges (fichier vide, code repris, retrait qui n'efface rien)."""
        p = self._project
        declared = {l.code for l in p.settings.languages if l.code}
        for code in declared:
            p.ensure_translation_file(code)
        for code in [c for c in p.translations if c not in declared]:
            p.forget_translations(code)
        p.prune_empty_translations(declared)


# ── Collisions ──────────────────────────────────────────────────────────

_TAG_HANDLE_W = 18    # largeur de la poignée de drag (colonne muette côté en-tête)
_TAG_NAME_W = 106     # largeur de la colonne des noms de tag (en-tête + lignes)
_TAG_CELL_W = 30      # largeur d'une case de la matrice, uniforme sur tout l'axe
_TAG_REMOVE_W = 22    # largeur du bouton × en bout de ligne
_ROW_SPACING = 4      # même valeur en-tête et lignes : c'est ce qui aligne les colonnes

# Case de la matrice, en plus voyant que le QCheckBox par défaut de l'appli
# (indicateur minuscule, pensé pour une ligne de formulaire) : la matrice n'a
# QUE ça à montrer, la case peut se permettre d'être le point focal.
_CELL_QSS = f"""
QCheckBox {{ spacing: 0px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border: 1px solid {C.BORDER_MID};
    border-radius: 4px;
    background: {C.BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {C.ACCENT};
    border-color: {C.ACCENT};
}}
QCheckBox::indicator:hover {{
    border-color: {C.ACCENT};
}}
"""


class _TagHeaderLabel(QWidget):
    """En-tête de colonne façon étiquette : le nom du tag en texte vertical,
    incliné 12° vers la droite depuis la pure verticale (comme une étiquette
    penchée, pas un texte à 90° raide), un petit œillet périwinkle en tête —
    clin d'œil à l'anneau d'une étiquette physique, et rappel visuel du mot
    « tag »."""

    _ANGLE = 12   # degrés, sens horaire, depuis la verticale

    def __init__(self, text: str, width: int, parent=None):
        super().__init__(parent)
        self._text = text
        self._font = QFont(T.UI, T.XS, QFont.Weight.DemiBold)
        text_w = QFontMetrics(self._font).horizontalAdvance(text)
        self.setFixedWidth(width)
        self.setFixedHeight(min(150, text_w + 26))
        self.setToolTip(text)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2
        p.setBrush(QColor(C.ACCENT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, 7), 3, 3)
        p.setPen(QColor(C.TEXT_HI))
        p.setFont(self._font)
        p.translate(cx + 4, self.height() - 4)
        p.rotate(-90 + self._ANGLE)
        p.drawText(0, 0, self._text)


class CollisionsPanel(QWidget):
    """Matrice triangulaire entre tags de boxes (ROADMAP v0.23) — cf.
    ProjectSettings.collision_disabled_pairs. Cochée = les deux tags se
    rencontrent, ce qui est le défaut : la matrice ne stocke que les
    exceptions.

    Les tags qui peuplent lignes et colonnes viennent de DEUX sources
    réunies (`_all_tags`) : ceux TROUVÉS sur un CollisionBoxComponent
    (scènes et prefabs), et ceux DÉCLARÉS explicitement dans
    `ProjectSettings.collision_tags` — un tag qu'on veut réserver et régler
    avant même de l'assigner à un acteur. Renommer une ligne renomme le tag
    PARTOUT (composants + clés de paires + déclaration), retirer une ligne
    le fait retomber au défaut « body » partout où il était posé — les deux
    en une seule étape d'annulation (`RenameCollisionTagCmd`,
    `RemoveCollisionTagCmd`, core/history.py).

    L'ORDRE d'affichage est lui-même persisté dans `collision_tags` — glisser
    une ligne par sa poignée réécrit la liste complète dans le nouvel ordre
    (même mécanique event-filter + fantôme + trait de dépôt que
    `ReorderableButtonBar`, ui/common/reorderable_bar.py, adaptée à l'axe
    vertical). Un tag purement découvert et jamais glissé n'a pas besoin d'y
    figurer : il apparaît trié après les tags déclarés (cf. `_all_tags`)."""

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._blocking = False

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_category_title(label('projset.collisions')))

        # Ce qu'il faut FAIRE ici (niveau 1, il change avec l'état de la
        # matrice) et ce que la matrice VEUT DIRE (niveau 3 : une notion, la
        # même quel que soit l'état — donc coupable par réglage).
        self._hint = note(lay)
        tip("collisions.symmetry", lay)

        # La matrice défile HORIZONTALEMENT sur elle-même : un projet à dix
        # tags ne doit pas élargir toute la fenêtre.
        self._grid_scroll = QScrollArea()
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setStyleSheet("background:transparent; border:none;")
        self._grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._grid_host = QWidget()
        self._grid_col = QVBoxLayout(self._grid_host)
        self._grid_col.setContentsMargins(0, 6, 0, 0)
        self._grid_col.setSpacing(2)
        self._grid_scroll.setWidget(self._grid_host)
        lay.addWidget(self._grid_scroll)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 4, 0, 0)
        self._btn_add = W.btn_add(label('projset.declare_a_tag'))
        self._btn_add.clicked.connect(self._add_tag)
        add_row.addWidget(self._btn_add)
        add_row.addStretch(1)
        lay.addLayout(add_row)

        lay.addStretch()

        # ── État du drag & drop (poignée → ligne) ─────────────────
        self._row_widgets: dict = {}      # tag -> QWidget (la ligne)
        self._drag_handles: dict = {}     # QLabel (poignée) -> tag
        self._drag_handle = None
        self._drag_press = None
        self._drag_tag: str = ""
        self._drag_order: list = []
        self._drag_target = 0
        self._dragging = False

        self._ghost = QLabel(self._grid_host)
        self._ghost.setFont(QFont(T.MONO, T.SM))
        self._ghost.setStyleSheet(
            f"background:{C.BG_HOVER}; color:{C.TEXT_HI}; border:1px solid {C.ACCENT};"
            "border-radius:4px; padding:4px 10px;")
        self._ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ghost.hide()

        self._indicator = QFrame(self._grid_host)
        self._indicator.setFixedHeight(2)
        self._indicator.setStyleSheet(f"background:{C.ACCENT}; border-radius:1px;")
        self._indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._indicator.hide()

        self._refresh_matrix()

    # ── Découverte des tags ──────────────────────────────────────

    def _all_tags(self) -> list:
        """Source unique : `Project.collision_tags()` (core/project.py) —
        partagée avec le sélecteur de tag du CollisionEditor, pour que les
        deux écrans proposent toujours la même liste. Déclarés d'abord, dans
        l'ordre que le drag & drop modifie (cf. `_end_drag`), puis découverts
        triés à la suite."""
        return self._project.collision_tags()

    def _tag_usage(self, tag_name: str) -> int:
        """Combien de CollisionBoxComponent portent ce tag, EXPLICITEMENT ou
        par défaut vide — ce que `RemoveCollisionTagCmd` va faire retomber à
        « body ». Sert au bouton × pour prévenir plutôt que surprendre."""
        p = self._project
        owners = [a for sc in p.scenes for a in sc.actors] + list(p.prefabs)
        owners += [ch for pf in p.prefabs for ch in (getattr(pf, "children", []) or [])]
        return sum(1 for o in owners for c in getattr(o, "components", [])
                  if isinstance(c, CollisionBoxComponent) and (c.tag or "body") == tag_name)

    def _free_tag_name(self) -> str:
        taken = set(self._all_tags())
        n = 1
        while f"tag{n}" in taken:
            n += 1
        return f"tag{n}"

    # ── Construction de la matrice ────────────────────────────────

    def _clear_rows(self):
        while self._grid_col.count():
            item = self._grid_col.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._row_widgets = {}
        self._drag_handles = {}

    def _refresh_matrix(self):
        self._clear_rows()
        tags = self._all_tags()
        if len(tags) < 2:
            self._hint.show_text("collisions.empty")
            self._grid_host.setVisible(False)
            return
        self._hint.show_text("collisions.usage")
        self._grid_host.setVisible(True)

        disabled = set(self._project.settings.collision_disabled_pairs)

        # ── En-tête : coin vide, puis une étiquette par colonne ──────
        header = QWidget()
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(0, 0, 0, 0)
        hrow.setSpacing(_ROW_SPACING)
        hrow.addWidget(self._spacer(_TAG_HANDLE_W), 0, Qt.AlignmentFlag.AlignBottom)
        hrow.addWidget(self._spacer(_TAG_NAME_W), 0, Qt.AlignmentFlag.AlignBottom)
        for tag in tags:
            hrow.addWidget(_TagHeaderLabel(tag, _TAG_CELL_W), 0, Qt.AlignmentFlag.AlignBottom)
        hrow.addWidget(self._spacer(_TAG_REMOVE_W), 0, Qt.AlignmentFlag.AlignBottom)
        hrow.addStretch(1)
        self._grid_col.addWidget(header)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{C.BORDER_DARK};")
        self._grid_col.addWidget(sep)

        # ── Une ligne par tag : poignée, nom éditable, cases, × ──────
        for r, ta in enumerate(tags):
            row = self._build_row(r, ta, tags, disabled)
            self._row_widgets[ta] = row
            self._grid_col.addWidget(row)

    def _build_row(self, r: int, ta: str, tags: list, disabled: set) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(_ROW_SPACING)

        handle = QLabel("⋮⋮")
        handle.setFont(QFont(T.UI, T.SM))
        handle.setStyleSheet(f"color:{C.TEXT_MUTED};")
        handle.setFixedWidth(_TAG_HANDLE_W)
        handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        handle.setCursor(Qt.CursorShape.OpenHandCursor)
        handle.setToolTip(tooltip(title=label('projset.drag_to_reorder')))
        handle.installEventFilter(self)
        self._drag_handles[handle] = ta
        row.addWidget(handle)

        name = QLineEdit(ta)
        name.setFont(QFont(T.MONO, T.SM))
        name.setStyleSheet(QSS.lineedit)
        name.setFixedWidth(_TAG_NAME_W)
        name.editingFinished.connect(
            lambda _t=ta, _e=name: self._commit_rename(_t, _e.text()))
        row.addWidget(name)

        # Triangulaire : le couple (A, B) est le même que (B, A), et
        # l'afficher deux fois inviterait à en décocher un seul — les
        # colonnes avant la diagonale restent un espace vide de même largeur,
        # pour que chaque colonne reste alignée avec son en-tête.
        for c, tb in enumerate(tags):
            if c < r:
                row.addWidget(self._spacer(_TAG_CELL_W))
                continue
            cell = QWidget()
            cell.setFixedWidth(_TAG_CELL_W)
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            box = QCheckBox()
            box.setStyleSheet(_CELL_QSS)
            box.setChecked(pair_key(ta, tb) not in disabled)
            box.setToolTip(f"{ta} × {tb}")
            box.toggled.connect(lambda on, x=ta, y=tb: self._set_pair(x, y, on))
            cl.addWidget(box, 0, Qt.AlignmentFlag.AlignCenter)
            row.addWidget(cell)

        n = self._tag_usage(ta)
        rm = W.btn_danger(tooltip(
            title=label('projset.remove_tag_title'),
            body=label('projset.remove_tag_used', n=n) if n else label('projset.remove_tag_unused')))
        rm.clicked.connect(lambda _c=False, _t=ta: self._remove_tag(_t))
        row.addWidget(rm)

        row.addStretch(1)
        return host

    @staticmethod
    def _spacer(width: int) -> QWidget:
        w = QWidget()
        w.setFixedWidth(width)
        return w

    # ── Mutations ─────────────────────────────────────────────────

    def _set_pair(self, tag_a: str, tag_b: str, enabled: bool):
        if self._blocking:
            return
        key = pair_key(tag_a, tag_b)
        cur = list(self._project.settings.collision_disabled_pairs)
        new = [k for k in cur if k != key] if enabled else sorted(set(cur) | {key})
        if cur == new:
            return
        get_history().push(SetFieldCmd(
            self._project.settings, "collision_disabled_pairs", cur, new,
            label="Projet.collision_disabled_pairs", persist_fn=self._persist,
        ))

    def _commit_rename(self, old_name: str, raw: str):
        if self._blocking:
            return
        new_name = raw.strip()
        if not new_name or new_name == old_name or new_name in self._all_tags():
            # Nom vide ou déjà pris par un autre tag : on repose l'ancien
            # plutôt que d'écrire deux tags au même endroit.
            self._refresh_matrix()
            return
        get_history().push(RenameCollisionTagCmd(
            self._project, old_name, new_name, persist_fn=self._persist,
        ))

    def _add_tag(self):
        name = self._free_tag_name()
        get_history().push(AddListItemCmd(
            self._project.settings.collision_tags, name,
            label=f"Déclarer le tag {name}",
            persist_fn=self._persist,
        ))

    def _remove_tag(self, tag_name: str):
        get_history().push(RemoveCollisionTagCmd(
            self._project, tag_name, persist_fn=self._persist,
        ))

    def _persist(self):
        self._project.save_settings()
        self._blocking = True
        try:
            self._refresh_matrix()
        finally:
            self._blocking = False

    # ── Drag & drop des lignes (réordonnancement) ──────────────────
    # Même mécanique que ReorderableButtonBar (ui/common/reorderable_bar.py) :
    # un eventFilter posé sur la POIGNÉE (jamais sur toute la ligne, sinon
    # plus moyen de cliquer le champ nom ou une case), un fantôme qui suit le
    # curseur, un trait qui indique où la ligne tombera. Le layout ne bouge
    # qu'au relâché — glisser ne fait QUE lire les positions déjà posées.

    def eventFilter(self, obj, event):
        if obj not in self._drag_handles:
            return False
        t = event.type()

        if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._drag_handle = obj
            self._drag_press = event.globalPosition().toPoint()
            self._dragging = False
            return False

        if t == QEvent.Type.MouseMove and self._drag_handle is obj:
            if not self._dragging:
                delta = (event.globalPosition().toPoint() - self._drag_press).manhattanLength()
                if delta < 8:
                    return False
                self._begin_drag(obj)
            if self._dragging:
                gy = self._grid_host.mapFromGlobal(event.globalPosition().toPoint()).y()
                self._update_drag(gy)
                return True

        if t == QEvent.Type.MouseButtonRelease and self._drag_handle is obj:
            if self._dragging:
                self._end_drag()
                return True
            self._drag_handle = None

        return False

    def _begin_drag(self, handle: QLabel):
        self._dragging = True
        self._drag_tag = self._drag_handles[handle]
        row = self._row_widgets[self._drag_tag]
        row.setStyleSheet(f"background:{C.BG_INPUT}; border-radius:4px;")
        handle.setCursor(Qt.CursorShape.ClosedHandCursor)

        self._ghost.setText(self._drag_tag)
        self._ghost.adjustSize()
        self._ghost.move(row.pos())
        self._ghost.show()
        self._ghost.raise_()
        self._indicator.raise_()

        self._drag_order = self._all_tags()
        self._drag_target = self._drag_order.index(self._drag_tag)

    def _update_drag(self, mouse_y: int):
        gh = self._ghost.height()
        gy = max(0, min(mouse_y - gh // 2, self._grid_host.height() - gh))
        self._ghost.move(self._ghost.x(), gy)

        self._drag_target = self._compute_target(mouse_y)
        self._place_indicator(self._drag_target)

    def _compute_target(self, mouse_y: int) -> int:
        others = [t for t in self._drag_order if t != self._drag_tag]
        for j, tag in enumerate(others):
            row = self._row_widgets[tag]
            mid = row.y() + row.height() // 2
            if mouse_y < mid:
                return j
        return len(others)

    def _place_indicator(self, target: int):
        others = [t for t in self._drag_order if t != self._drag_tag]
        self._indicator.setFixedWidth(self._grid_host.width())
        if not others:
            self._indicator.hide()
            return
        if target == 0:
            y = self._row_widgets[others[0]].y() - 2
        elif target >= len(others):
            last = self._row_widgets[others[-1]]
            y = last.y() + last.height() + 1
        else:
            top = self._row_widgets[others[target - 1]]
            bot = self._row_widgets[others[target]]
            y = (top.y() + top.height() + bot.y()) // 2
        self._indicator.move(0, y)
        self._indicator.show()

    def _end_drag(self):
        others = [t for t in self._drag_order if t != self._drag_tag]
        others.insert(self._drag_target, self._drag_tag)
        new_order = others

        row = self._row_widgets[self._drag_tag]
        row.setStyleSheet("")
        self._drag_handle.setCursor(Qt.CursorShape.OpenHandCursor)
        self._ghost.hide()
        self._indicator.hide()
        self._dragging = False
        self._drag_handle = None

        if new_order != self._all_tags():
            old = list(self._project.settings.collision_tags)
            get_history().push(SetFieldCmd(
                self._project.settings, "collision_tags", old, new_order,
                label="Réordonner les tags de collision", persist_fn=self._persist,
            ))


# ── Le dialogue ─────────────────────────────────────────────────────────

class ProjectSettingsDialog(QDialog):
    """Colonne de catégories à gauche, panneau à droite — même squelette que
    SettingsDialog (ui/common/settings_dialog.py)."""

    _CATEGORY_KEYS = {'Build': 'projset.build', 'Visual': 'projset.visual', 'Sound': 'projset.sound', 'Input': 'projset.input', 'Languages': 'projset.languages', 'Collisions': 'projset.collisions'}

    _CATEGORIES = ("Build", "Visual", "Sound", "Input", "Languages", "Collisions")

    def __init__(self, project: Project, initial_category: str = "Build", parent=None):
        super().__init__(parent)
        self.setWindowTitle(label('projset.project_settings'))
        self.setStyleSheet(QSS.dialog)
        self.resize(820, 480)

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        self._list = QListWidget()
        self._list.setStyleSheet(QSS.list_widget)
        self._list.setFixedWidth(160)
        self._list.setFont(QFont(T.UI, T.MD))
        for cat in self._CATEGORIES:
            self._list.addItem(QListWidgetItem(label(self._CATEGORY_KEYS[cat])))
        body.addWidget(self._list)

        self._stack = QStackedWidget()
        panels = [
            BuildPanel(project), VisualPanel(project), SoundPanel(project),
            InputsPanel(project), LanguagesPanel(project), CollisionsPanel(project),
        ]
        for panel in panels:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet(f"background:{C.BG_BASE}; border:none;")
            scroll.setWidget(panel)
            self._stack.addWidget(scroll)
        body.addWidget(self._stack, 1)

        self._list.currentRowChanged.connect(self._stack.setCurrentIndex)
        idx = self._CATEGORIES.index(initial_category) if initial_category in self._CATEGORIES else 0
        self._list.setCurrentRow(idx)

        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = QPushButton(label('common.close'))
        btn_close.setStyleSheet(QSS.button_primary)
        btn_close.setFixedWidth(90)
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        root.addLayout(footer)
