"""Sound Mixer screen — import/preview SFX + Music."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QFileDialog, QToolButton, QSlider, QProgressBar,
    QSpinBox, QCheckBox, QMessageBox,
    QButtonGroup, QComboBox, QStackedWidget,
)
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtCore import (
    Qt, QSize, pyqtSignal, QTimer,
)

from ui.common.theme import C, T, QSS, ui_font
from ui.common.three_column_body import ThreeColumnBody
from ui.common.widgets import W
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.icons import get as _ico

from core.resources.asset_reconciliation import check_audio_file
from core.models.audio import (
    Jingle, Music, Sfx, SFX_FILE_EXTS, MUSIC_FILE_EXTS,
    file_dialog_filter, sfx_rom_bytes,
)
from ui.sound_mixer.state_machines import (
    ActionMatrix, MusicMachinePanel, MusicStateInspector,
)
from ui.sound_mixer.box_playback import BoxPlayer
from ui.sound_mixer.music_editor import MusicEditor
from core.music_structure import is_wav_asset
from core.models.audio import FADE_MAX_FRAMES, PITCH_MAX, PITCH_MIN, TEMPO_MAX, TEMPO_MIN
from ui.sound_mixer.sound_budget_bar import SoundBudgetBar
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import SFX, MUSIC, JINGLES
from core.keybindings import bind
from core.project import Project
from core.history import get_history, DeleteResourceCmd
from core.command_dispatcher import get_dispatcher


# ──────────────────────────────────────────────────────────────────
#  Inspector d'un Sfx
# ──────────────────────────────────────────────────────────────────
class _AssetInspectorBase(QWidget):
    """Base commune à SfxInspector/MusicInspector : header renommable,
    import de fichier, volume 0-255. Les sous-classes ne fournissent que
    leurs textes/filtres spécifiques et le manager de persistence."""
    changed = pyqtSignal()

    _EMPTY_TEXT = ""
    _HEADER_KIND = ""
    _HEADER_LABEL = ""
    _IMPORT_BTN_TEXT = ""
    _IMPORT_DIALOG_TITLE = ""
    _IMPORT_FILTER = ""
    _IMPORT_FOLDER = ""
    _HAS_LOOP = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._asset = None
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._empty = QLabel(label(self._EMPTY_TEXT) if self._EMPTY_TEXT else "")
        self._empty.setFont(QFont(T.UI, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        def row(label, widget):
            r = QHBoxLayout()
            l = QLabel(label); l.setFont(QFont(T.UI, T.SM))
            l.setStyleSheet(f"color:{C.TEXT_DIM};"); l.setFixedWidth(92)
            r.addWidget(l); r.addWidget(widget, 1); cl.addLayout(r); return widget

        from ui.common.widgets import AssetHeaderBar
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_renamed)
        cl.addWidget(self._header)

        self._file_lbl = QLabel(label("sndpanel.no_file"))
        self._file_lbl.setFont(QFont(T.UI, T.SM))
        self._file_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        cl.addWidget(self._file_lbl)

        btn_import = QPushButton(label(self._IMPORT_BTN_TEXT))
        btn_import.setFont(QFont(T.UI, T.MD))
        btn_import.setToolTip(tooltip(
            title=label("sndpanel.import_title"), body=label("sndpanel.import_tip"),
        ))
        btn_import.clicked.connect(self._import)
        cl.addWidget(btn_import)

        if self._HAS_LOOP:
            self._loop = QCheckBox(label("common.loop"))
            self._loop.setFont(QFont(T.UI, T.MD))
            self._loop.setStyleSheet(f"color:{C.TEXT_NORM};")
            self._loop.toggled.connect(self._on_loop)
            cl.addWidget(self._loop)

        self._vol = QSpinBox(); self._vol.setRange(0, 100); self._vol.setSuffix(" %")
        self._vol.setFont(QFont(T.MONO, T.MD))
        self._vol.setStyleSheet(
            f"QSpinBox{{background:{C.BG_INPUT};color:{C.TEXT_NORM};border:1px solid {C.BORDER_MID};"
            "border-radius:3px;padding:2px;}"
        )
        self._vol.valueChanged.connect(self._on_vol)
        row(label("sndpanel.volume"), self._vol)

        self._build_extra_rows(row, cl)

        # Poids réel en ROM, relevé au dernier build. Vide tant qu'aucun build
        # n'a eu lieu : l'éditeur mesure, il ne devine pas.
        self._weight = QLabel("")
        self._weight.setFont(QFont(T.UI, T.SM))
        self._weight.setStyleSheet(f"color:{C.TEXT_DIM}; margin-top:6px;")
        self._weight.setWordWrap(True)
        cl.addWidget(self._weight)

        cl.addStretch()
        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    def _build_extra_rows(self, row, layout):
        """Champs propres à une famille. Rien par défaut."""

    def _weight_text(self, entry) -> str:
        """Ce que pèse cet asset en ROM, tel qu'on l'écrit à l'auteur."""
        return label("sndpanel.weight", kb=f"{entry.own_bytes / 1024:.1f}")

    def refresh_weight(self, entry):
        self._weight.setText(self._weight_text(entry) if entry else "")

    def _manager(self):
        raise NotImplementedError

    def _save(self):
        raise NotImplementedError

    def _persist(self):
        """Écrit le sidecar SANS réveiller le watcher.

        Les sidecars de assets/sfx|music|jingles sont surveillés : une écriture
        non suspendue revient comme une modification externe, `load_one`
        remplace l'asset par une copie et l'écran se recharge — l'inspecteur se
        vide à chaque réglage. Même règle que tout écran qui écrit sous assets/.
        """
        with get_dispatcher().suspended():
            self._save()

    def load(self, asset, project: Project):
        self._asset = asset; self._project = project
        if not asset:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        self._header.set_header(self._HEADER_KIND, label(self._HEADER_LABEL), asset.name)
        ap = project.asset_abs(asset.asset) if asset.asset else None
        self._set_file_label(ap)
        if self._HAS_LOOP:
            self._loop.setChecked(getattr(asset, "loop", True))
        self._vol.setValue(getattr(asset, "volume", 100))
        if rate := getattr(self, "_rate", None):
            idx = rate.findData(int(getattr(asset, "sample_rate", 0) or 0))
            rate.setCurrentIndex(idx if idx >= 0 else 0)
        self._blocking = False

    def _on_renamed(self, new_name: str):
        if self._blocking or not self._asset or not self._project: return
        new_name = new_name.strip()
        if new_name and new_name != self._asset.name:
            # Passe par le projet (pas le ResourceStore brut) : il met aussi
            # à jour les sfx:play()/music:play() des scripts.
            with get_dispatcher().suspended():
                self._project.rename_sound(self._asset, new_name)
            self.changed.emit()

    def _on_loop(self, v):
        if self._blocking or not self._asset: return
        self._asset.loop = v
        self._persist()
        self.changed.emit()

    def _on_vol(self, v):
        if self._blocking or not self._asset: return
        self._asset.volume = v
        self._persist()
        self.changed.emit()

    def _file_hint(self, path: Path) -> str:
        """Complément affiché à côté du nom de fichier. Vide par défaut."""
        return ""

    def _set_file_label(self, path: Optional[Path]):
        if path is None:
            self._file_lbl.setText(label("sndpanel.no_file")); return
        self._file_lbl.setText(f"{path.name}{self._file_hint(path)}")

    def _import(self):
        if not self._project or not self._asset: return
        path, _ = QFileDialog.getOpenFileName(
            self, label(self._IMPORT_DIALOG_TITLE), "", self._IMPORT_FILTER
        )
        if not path:
            return
        # Refuser AVANT la copie : un fichier écarté ne doit pas atterrir dans
        # assets/. Et c'est le seul refus possible — mmutil construit la ROM
        # sans broncher sur un wav 24 bits, en la laissant muette.
        if reason := check_audio_file(Path(path), into=self._IMPORT_FOLDER):
            QMessageBox.warning(self, label("sndpanel.import_rejected_title"),
                                label("sndpanel.import_rejected_text",
                                      name=Path(path).name, reason=reason))
            return
        with get_dispatcher().suspended():
            dst = self._project.import_asset(Path(path), self._IMPORT_FOLDER)
        self._asset.asset = self._project.asset_rel(dst)
        self._persist()
        self._set_file_label(dst)
        self.changed.emit()


class SfxInspector(_AssetInspectorBase):
    _EMPTY_TEXT = "sndpanel.sfx_empty"
    _HEADER_KIND = "sfx"
    _HEADER_LABEL = "common.sfx"
    _IMPORT_BTN_TEXT = "sndpanel.sfx_import_btn"
    _IMPORT_DIALOG_TITLE = "sndpanel.sfx_import_title"
    _IMPORT_FILTER = file_dialog_filter("WAV PCM 8/16 bits", SFX_FILE_EXTS)
    _IMPORT_FOLDER = "sfx"

    # Taux proposés. Maxmod mixe autour de 16 kHz : au-delà on paie de la ROM
    # pour un détail que la console ne restitue pas.
    _RATES = ((0, label('sndpanel.from_project')), (8000, "8 000 Hz"), (11025, "11 025 Hz"),
              (16000, "16 000 Hz"), (22050, "22 050 Hz"), (32000, "32 000 Hz"))

    def _file_hint(self, path: Path) -> str:
        """Le poids du FICHIER SOURCE, avant tout ré-échantillonnage.

        mmutil conserve le taux : sans quantification, un effet en 44,1 kHz
        coûte près de trois fois ce qu'il coûterait en 16 kHz sans rien
        apporter que le mixeur Maxmod sache restituer. On affiche le fait, on
        ne refuse pas le choix (ROADMAP v0.8.1).
        """
        n = sfx_rom_bytes(path)
        return label("sndpanel.sfx_source", kb=f"{n / 1024:.1f}") if n else ""

    def _build_extra_rows(self, row, layout):
        self._rate = QComboBox()
        self._rate.setFont(QFont(T.UI, T.MD))
        for value, rate_label in self._RATES:
            self._rate.addItem(rate_label, value)
        self._rate.setToolTip(tooltip(
            title=label("sndpanel.rate_title"), body=label("sndpanel.rate_tip"),
        ))
        self._rate.currentIndexChanged.connect(self._on_rate)
        row(label("sndpanel.rate"), self._rate)

    def _manager(self):
        return self._project.sfx

    def _on_rate(self, idx: int):
        if self._blocking or not self._asset: return
        self._asset.sample_rate = int(self._rate.itemData(idx) or 0)
        self._persist()
        self.changed.emit()

    def _save(self):
        self._project.save_sfx(self._asset)


# ──────────────────────────────────────────────────────────────────
#  Inspector d'une Music
# ──────────────────────────────────────────────────────────────────
class MusicInspector(_AssetInspectorBase):
    _EMPTY_TEXT = "sndpanel.music_empty"
    _HEADER_KIND = "music"
    _HEADER_LABEL = "sndpanel.header_music"
    _IMPORT_BTN_TEXT = "sndpanel.music_import_btn"
    _IMPORT_DIALOG_TITLE = "sndpanel.music_import_title"
    _IMPORT_FILTER = file_dialog_filter("Module", MUSIC_FILE_EXTS)
    _IMPORT_FOLDER = "music"
    _HAS_LOOP = True
    # Les réglages que la ROM applique à une musique. Un jingle n'en applique aucun (il joue sur
    # l'autre couche, avec son propre volume) : son inspecteur ne les propose pas.
    _SETTINGS = True

    # Taux de build d'une piste WAV : 0 = le défaut. Plus bas, la piste pèse moins et peut être plus longue.
    _RATES = ((0, "sndpanel.rate_default"), (8000, "8 000 Hz"), (11025, "11 025 Hz"),
              (13379, "13 379 Hz"), (16000, "16 000 Hz"))

    def _build_extra_rows(self, row, layout):
        if not self._SETTINGS:
            return
        self._tempo = self._setting_spin(TEMPO_MIN, TEMPO_MAX, " %", self._on_tempo,
                                         "sndpanel.tempo_tip")
        self._pitch = self._setting_spin(PITCH_MIN, PITCH_MAX, " %", self._on_pitch,
                                         "sndpanel.pitch_tip")
        self._fade_in = self._setting_spin(0, FADE_MAX_FRAMES, " fr", self._on_fade_in,
                                           "sndpanel.fade_in_tip")
        self._fade_out = self._setting_spin(0, FADE_MAX_FRAMES, " fr", self._on_fade_out,
                                            "sndpanel.fade_out_tip")
        row(label("sndpanel.tempo"), self._tempo)
        row(label("sndpanel.pitch"), self._pitch)
        row(label("sndpanel.fade_in"), self._fade_in)
        row(label("sndpanel.fade_out"), self._fade_out)
        self._rate = QComboBox()
        self._rate.setFont(QFont(T.UI, T.MD))
        for value, text in self._RATES:
            self._rate.addItem(label(text) if text.startswith("sndpanel.") else text, value)
        self._rate.setToolTip(tooltip(title=label("sndpanel.music_rate"),
                                      body=label("sndpanel.music_rate_tip")))
        self._rate.currentIndexChanged.connect(self._on_rate)
        row(label("sndpanel.rate"), self._rate)

    def _setting_spin(self, low: int, high: int, suffix: str, slot, tip_key: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        spin.setFont(QFont(T.MONO, T.MD))
        spin.setStyleSheet(QSS.spinbox)
        spin.setToolTip(tooltip(title=label(tip_key.removesuffix("_tip")), body=label(tip_key)))
        spin.valueChanged.connect(slot)
        return spin

    def load(self, asset, project):
        super().load(asset, project)
        if not asset or not self._SETTINGS:
            return
        self._blocking = True
        self._tempo.setValue(asset.tempo)
        self._pitch.setValue(asset.pitch)
        self._fade_in.setValue(asset.fade_in)
        self._fade_out.setValue(asset.fade_out)
        index = self._rate.findData(int(asset.sample_rate or 0))
        self._rate.setCurrentIndex(index if index >= 0 else 0)
        # Un WAV n'a ni tempo ni hauteur (son module n'a qu'une note, calée sur la piste) et ne
        # change de taux que lui ; un module garde ses échantillons, donc pas de taux.
        wav = is_wav_asset(asset.asset)
        for widget in (self._tempo, self._pitch):
            widget.setEnabled(not wav)
        self._rate.setEnabled(wav)
        self._blocking = False

    def _set_setting(self, field: str, value) -> None:
        if self._blocking or not self._asset:
            return
        setattr(self._asset, field, value)
        self._persist()
        self.changed.emit()

    def _on_tempo(self, v): self._set_setting("tempo", v)
    def _on_pitch(self, v): self._set_setting("pitch", v)
    def _on_fade_in(self, v): self._set_setting("fade_in", v)
    def _on_fade_out(self, v): self._set_setting("fade_out", v)
    def _on_rate(self, index): self._set_setting("sample_rate", int(self._rate.itemData(index) or 0))

    def _weight_text(self, entry) -> str:
        """DEUX nombres, jamais un seul.

        mmutil mutualise les échantillons identiques entre les modules d'un
        même soundbank — et un catalogue de variantes du même morceau
        (DRUMLESS / FAST / SLOW) n'en porte donc qu'un jeu. Un chiffre unique
        mentirait dans les deux sens : le total laisserait croire qu'en retirer
        une en rend autant, et le poids propre cacherait ce qu'elle a fait
        entrer (cf. ROADMAP v0.8.4).
        """
        kb = f"{entry.own_bytes / 1024:.1f}"
        if entry.shared_bytes and entry.shared_with:
            return label("sndpanel.music_weight_shared", kb=kb,
                         shared=f"{entry.shared_bytes / 1024:.1f}", n=entry.shared_with)
        return label("sndpanel.music_weight", kb=kb)

    def _manager(self):
        return self._project.music

    def _save(self):
        self._project.save_music(self._asset)


class JingleInspector(MusicInspector):
    """Même réglages qu'une musique, d'un autre dossier : le jingle ne boucle pas
    dans le jeu (maxmod le joue une fois), mais le réglage reste celui du module."""
    _EMPTY_TEXT = "sndpanel.jingle_empty"
    _SETTINGS = False
    _HEADER_LABEL = "sndpanel.header_jingle"
    _IMPORT_DIALOG_TITLE = "sndpanel.jingle_import_title"
    _IMPORT_FOLDER = "jingles"

    def _manager(self):
        return self._project.jingles

    def _save(self):
        self._project.save_jingle(self._asset)


# ──────────────────────────────────────────────────────────────────
#  Un onglet de famille : le sélecteur de boîte, et son éditeur
# ──────────────────────────────────────────────────────────────────
class _BoxTab(QWidget):
    """Choisit UNE boîte d'une famille et la donne à son éditeur.

    Trois instances, une par famille. Ce qui les distingue tient en trois
    valeurs — le registre du projet, la classe à instancier, l'éditeur — donc
    en paramètres, pas en sous-classes.
    """
    changed = pyqtSignal()      # la boîte courante a changé (choix ou création)

    def __init__(self, store_attr: str, cls, editor: QWidget,
                 load_fn, empty_text: str, parent=None):
        super().__init__(parent)
        self._store_attr = store_attr
        self._cls = cls
        self._editor = editor
        self._load_fn = load_fn
        self._project: Optional[Project] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        bar = QHBoxLayout(); bar.setSpacing(6)
        lbl = QLabel(label("sndpanel.box"))
        lbl.setFont(QFont(T.UI, T.SM))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._combo = QComboBox()
        self._combo.setFont(QFont(T.UI, T.SM))
        self._combo.setStyleSheet(QSS.combobox)
        self._combo.setToolTip(tooltip(
            title=label("sndpanel.box_title"), body=label("sndpanel.box_tip"),
        ))
        self._combo.currentIndexChanged.connect(lambda _i: self._load())
        # Le champ de renommage prend la PLACE du sélecteur, il ne s'ajoute
        # pas à côté : on renomme la boîte qu'on a sous les yeux, et la barre
        # ne grandit pas d'un widget qui ne sert qu'un instant.
        # Drapeau EXPLICITE et non `isVisible()` : un widget d'onglet non
        # affiché est « invisible » même quand il est en cours d'édition, et
        # la validation serait alors avalée en silence.
        self._renaming = False
        self._name_edit = QLineEdit()
        self._name_edit.setFont(QFont(T.UI, T.SM))
        self._name_edit.setStyleSheet(QSS.lineedit)
        self._name_edit.setVisible(False)
        self._name_edit.editingFinished.connect(self._commit_rename)
        self._btn_ren = W.btn_ghost("✎")
        self._btn_ren.setToolTip(tooltip(title=label("sndpanel.rename_box_title")))
        self._btn_ren.clicked.connect(self._begin_rename)
        btn_new = W.btn_ghost(label("sndpanel.new_box"))
        btn_new.setToolTip(tooltip(title=label("sndpanel.new_box_title"), body=label("sndpanel.new_box_tip")))
        btn_new.clicked.connect(self._new)
        self._btn_del = W.btn_danger()
        self._btn_del.setToolTip(tooltip(title=label("sndpanel.delete_box_title"), warning=label("sndpanel.delete_box_warning")))
        self._btn_del.clicked.connect(self._delete)
        bar.addWidget(lbl)
        bar.addWidget(self._combo, 1); bar.addWidget(self._name_edit, 1)
        bar.addWidget(self._btn_ren); bar.addWidget(btn_new)
        bar.addWidget(self._btn_del)
        lay.addLayout(bar)

        lay.addWidget(editor, 1)
        self._empty = W.empty_state(empty_text)
        lay.addWidget(self._empty)

    # ── Chargement ────────────────────────────────────────────────

    def _store(self):
        return getattr(self._project, self._store_attr) if self._project else []

    def current(self):
        if not self._project:
            return None
        return getattr(self._project, self._store_attr).get(
            self._combo.currentData() or "")

    def load_project(self, project: Project):
        self._project = project
        self.refresh()

    def refresh(self):
        """Repeuple la liste et recharge la boîte courante dans l'éditeur."""
        if not self._project:
            return
        want = self._combo.currentData()
        self._combo.blockSignals(True)
        self._combo.clear()
        for box in sorted(self._store(), key=lambda b: b.name):
            self._combo.addItem(box.name, box.name)
        i = self._combo.findData(want)
        self._combo.setCurrentIndex(i if i >= 0 else 0)
        self._combo.blockSignals(False)
        self._load()

    def _load(self):
        box = self.current()
        self._editor.setVisible(box is not None)
        self._empty.setVisible(box is None)
        self._btn_del.setEnabled(box is not None)
        self._btn_ren.setEnabled(box is not None)
        if box is not None:
            self._load_fn(box)
        self.changed.emit()

    # ── Édition ───────────────────────────────────────────────────

    def _new(self):
        """Crée une boîte au nom automatique — pas de pop-up de saisie."""
        if not self._project:
            return
        from core.models.unique_name import unique_name
        store = getattr(self._project, self._store_attr)
        box = self._cls(name=unique_name(self._cls().name,
                                         [b.name for b in store]))
        store.append(box)
        store.save(box)
        self.refresh()
        i = self._combo.findData(box.name)
        if i >= 0:
            self._combo.setCurrentIndex(i)

    # ── Renommage ─────────────────────────────────────────────────

    def _begin_rename(self):
        """Le nom passe en édition, sélectionné — prêt à être remplacé."""
        box = self.current()
        if box is None:
            return
        self._name_edit.setText(box.name)
        self._renaming = True
        self._combo.setVisible(False)
        self._name_edit.setVisible(True)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _commit_rename(self):
        """Applique, ou revient en arrière en silence.

        Un nom vide, inchangé ou déjà pris est REFUSÉ sans pop-up : le champ
        reprend l'ancien nom, ce qui dit le refus sans interrompre. Rien ne
        cite une boîte par son nom — ni scène, ni script —, donc le renommage
        n'a rien à réparer : c'est le fichier sur le disque qui suit.
        """
        if not self._renaming:
            return
        self._renaming = False
        box, new = self.current(), self._name_edit.text().strip()
        self._name_edit.setVisible(False)
        self._combo.setVisible(True)
        if box is None or not new or new == box.name:
            return
        store = getattr(self._project, self._store_attr)
        if store.get(new) is not None:
            return
        store.rename(box, new)
        self.refresh()
        i = self._combo.findData(new)
        if i >= 0:
            self._combo.setCurrentIndex(i)

    def keyPressEvent(self, e):
        # Échap pendant l'édition : on annule sans écrire.
        if e.key() == Qt.Key.Key_Escape and self._renaming:
            self._renaming = False
            self._name_edit.setVisible(False)
            self._combo.setVisible(True)
            e.accept()
            return
        super().keyPressEvent(e)

    def _delete(self):
        """Supprime la boîte courante — annulable, comme tout asset.

        Confirmation d'abord : une boîte porte des états, des mappings et,
        pour la MusicBox, une disposition de graphe. Ce n'est pas ce qu'on
        refait de tête après un clic malheureux.
        """
        box = self.current()
        if box is None or not self._project:
            return
        if QMessageBox.question(
            self, label("common.delete"),
            label("sndpanel.del_box_text", name=box.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        get_history().push(DeleteResourceCmd(
            getattr(self._project, self._store_attr), box))
        self.refresh()

    def save_current(self):
        box = self.current()
        if box is not None and self._project:
            getattr(self._project, self._store_attr).save(box)


# ──────────────────────────────────────────────────────────────────
#  SoundMixerScreen
# ──────────────────────────────────────────────────────────────────
class SoundMixerScreen(QWidget):
    """Écran complet Sound Mixer : SFX + Music (via AssetFinder) + preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._weights: Optional[dict] = None   # poids du dernier build, à la demande
        self._last_selected = None             # cf. _on_state_selected
        # L'asset du Sound finder que le lecteur jouera à la place de la boîte,
        # tant qu'on n'a pas touché à la boîte (cf. _disarm_asset).
        self._armed_asset = None
        self._edited_music = None              # l'asset que l'éditeur central montre
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Pas de bandeau-titre d'écran : la nav du haut indique déjà où on est
        # (décision refonte thème 2026-08).

        # La simulation matérielle est sous le node editor : elle joue la
        # MusicBox telle que la ROM la résout, pas le fichier sur l'ordinateur.
        self._box_player = BoxPlayer(self)

        # ── Panneau gauche : Sound finder ──────────────────────────
        # Deux familles dans un seul finder partagé ; c'est le TYPE de l'asset
        # reçu qui dit quel inspecteur montrer, pas un signal par famille.
        self._finder = AssetFinder(label('sndpanel.sound_finder'), [SFX, MUSIC, JINGLES],
                                   min_width=180, max_width=360)
        self._finder.selected.connect(lambda _kind, a: self._on_asset_selected(a))
        self._finder.emptied.connect(self._on_finder_emptied)

        # ── Panneau central : contextes audio (masqué temporairement) ──
        # Les MusicBox/SoundBox/JingleBox restent chargées afin que les projets
        # existants gardent leurs données et leur build. Leur éditeur visuel,
        # en revanche, disparaît de l'écran pendant le recentrage sur les deux
        # modules fondamentaux : Music et Sound FX.
        # La COLONNE reste (le panneau de build s'y loge, sa poignée aussi) ; seul son
        # contenu est masqué.
        self._machines_panel = self._build_machines_panel()
        self._machines_panel.hide()
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self._machines_panel, 1)
        # L'éditeur d'une musique ou d'un jingle : la forme d'onde et les sections de boucle. Il prend la
        # place du graphe masqué quand un module est choisi dans le finder (cf. `_show_music_editor`).
        self._music_editor = MusicEditor(self._box_player.track_for)
        self._music_editor.changed.connect(self._on_editor_changed)
        self._music_editor.preview_section.connect(self._preview_section)
        self._music_editor.hide()
        center_layout.addWidget(self._music_editor, 1)
        # Le lecteur ne dépend pas de l'éditeur de boîtes : il reste ancré en bas de la colonne (hauteur
        # fixe) même quand le panneau des boîtes est masqué. Le remplissage pousse la barre vers le bas
        # tant que l'éditeur n'est pas là, et lui cède la place sinon.
        self._center_filler = QWidget()
        center_layout.addWidget(self._center_filler, 1)
        center_layout.addWidget(self._build_player_bar())
        # Espace lance / arrête l'aperçu, comme le bouton du bandeau. Sur tout l'écran et non sur la
        # seule colonne centrale : on choisit un asset dans le finder puis on l'écoute sans changer de focus.
        play_pause = QShortcut(QKeySequence(), self)
        play_pause.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        play_pause.activated.connect(self._btn_rom.toggle)
        bind("sound.play_pause", play_pause)

        # ── Panneau droit : inspector ─────────────────────────────
        self._right_stack = QStackedWidget()
        self._right_stack.setMinimumWidth(200)

        empty_w = QWidget(); empty_w.setStyleSheet(f"background:{C.BG_PANEL};")
        el = QVBoxLayout(empty_w)
        hint = QLabel(label("sndpanel.right_empty"))
        hint.setFont(QFont(T.UI, T.MD))
        hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addStretch(); el.addWidget(hint); el.addStretch()
        self._right_stack.addWidget(empty_w)      # 0

        self._sfx_insp = SfxInspector()
        self._sfx_insp.changed.connect(self._on_changed)
        self._right_stack.addWidget(self._sfx_insp)   # 1

        self._music_insp = MusicInspector()
        self._music_insp.changed.connect(self._on_changed)
        self._music_insp.changed.connect(self._music_editor.reload)
        self._right_stack.addWidget(self._music_insp)  # 2

        # L'inspecteur du nœud sélectionné dans le graphe. Il partage la
        # colonne avec les inspecteurs d'asset : c'est la même question posée
        # à la même place — « qu'est-ce qui est sélectionné, et comment se
        # règle-t-il ? ».
        self._state_insp = MusicStateInspector()
        self._state_insp.changed.connect(self._music_tab.save_current)
        self._state_insp.changed.connect(self._refresh_budget)
        self._state_insp.restructured.connect(self._music_machine.refresh)
        self._right_stack.addWidget(self._state_insp)  # 3

        self._jingle_insp = JingleInspector()
        self._jingle_insp.changed.connect(self._on_changed)
        self._jingle_insp.changed.connect(self._music_editor.reload)
        self._right_stack.addWidget(self._jingle_insp)  # 4

        self.body = ThreeColumnBody(self._finder, center, self._right_stack,
                                    sizes=(200, 560, 300))
        root.addWidget(self.body, 1)

        # Bandeau de canaux : jumeau LOCAL de GbaStatusBar (window.py), pour
        # la ressource rare de CET écran — cf. sound_budget_bar.py. Sous le
        # splitter, comme la barre de fenêtre est sous tout le reste.
        self._budget_bar = SoundBudgetBar()
        root.addWidget(self._budget_bar)

    # ── Les trois machines ────────────────────────────────────────

    def _build_machines_panel(self) -> QWidget:
        """Un onglet par FAMILLE, et chacune choisit sa propre boîte.

        Trois onglets et non un graphe unique : les trois couches sont
        indépendantes sur ce matériel (module, couche jingle, canaux d'effets),
        et « sur du sable » n'a rien à voir avec « en combat ». Depuis qu'elles
        sont trois assets, chaque onglet porte aussi son propre sélecteur — une
        MusicBox et une SoundBox n'ont aucune raison de s'appeler pareil ni
        d'être choisies ensemble.
        """
        from core.models.sound_box import (
            MusicBox, JingleBox, SoundBox, KIND_SOUND, KIND_JINGLE,
        )

        panel = QWidget()
        panel.setStyleSheet(f"background:{C.BG_PANEL};")
        # Le contexte reste visible en haut et l'éditeur occupe tout le milieu ;
        # la lecture, elle, vit sous ce panneau (cf. `__init__`).
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._music_machine = MusicMachinePanel()
        self._music_machine.state_selected.connect(self._on_state_selected)
        self._music_machine.state_created.connect(
            lambda: QTimer.singleShot(0, self._state_insp.focus_name))
        self._sfx_matrix = ActionMatrix(KIND_SOUND)
        self._jingle_matrix = ActionMatrix(KIND_JINGLE)

        self._tabs = QStackedWidget()
        self._music_tab = _BoxTab(
            "music_boxes", MusicBox, self._music_machine,
            lambda box: self._music_machine.load(box),
            label("sndpanel.musicbox_empty"))
        self._sound_tab = _BoxTab(
            "sound_boxes", SoundBox, self._sfx_matrix,
            lambda box: self._sfx_matrix.load(
                box, [s.name for s in self._project.sfx]),
            label("sndpanel.soundbox_empty"))
        self._jingle_tab = _BoxTab(
            "jingle_boxes", JingleBox, self._jingle_matrix,
            lambda box: self._jingle_matrix.load(
                box, [j.name for j in self._project.jingles]),
            label("sndpanel.jinglebox_empty"))
        for tab in (self._music_tab, self._sound_tab, self._jingle_tab):
            tab.changed.connect(self._on_box_changed)
            self._tabs.addWidget(tab)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._music_machine.changed.connect(self._music_tab.save_current)
        self._sfx_matrix.changed.connect(self._sound_tab.save_current)
        self._jingle_matrix.changed.connect(self._jingle_tab.save_current)
        # Le bandeau ne lit que musique + jingle (cf. sound_budget_bar.py) :
        # la SoundBox n'y entre pas, donc `_sfx_matrix.changed` n'a rien à y
        # déclencher.
        self._music_machine.changed.connect(self._refresh_budget)
        self._jingle_matrix.changed.connect(self._refresh_budget)
        lay.addWidget(self._build_context_bar())
        lay.addWidget(self._tabs, 1)
        return panel

    def _build_context_bar(self) -> QFrame:
        """Sélecteur persistant des trois contextes du Sound Mixer.

        Il reprend volontairement la géométrie et les états visuels du
        sélecteur « Scene / Graph » : ce sont ici trois espaces de travail
        exclusifs, pas trois onglets de document.
        """
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setStyleSheet(
            f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(5)

        group = QButtonGroup(bar)
        group.setExclusive(True)
        self._context_buttons: list[QToolButton] = []
        contexts = (
            (label("sndpanel.context_music"), label("sndpanel.context_music_tip")),
            (label("sndpanel.context_sfx"), label("sndpanel.context_sfx_tip")),
            (label("sndpanel.context_jingles"), label("sndpanel.context_jingles_tip")),
        )
        lay.addStretch(1)
        for index, (text, tip) in enumerate(contexts):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tooltip(title=text, body=tip))
            button.setCheckable(True)
            button.setFont(ui_font(T.MD))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QToolButton{{border:1px solid {C.BORDER};background:{C.BG_INPUT};"
                f"color:{C.TEXT_NORM};padding:3px 12px;margin:0px;}}"
                f"QToolButton:hover{{background:{C.BG_HOVER};}}"
                f"QToolButton:checked{{background:{C.BG_SEL};border-color:{C.ACCENT};"
                f"color:{C.TEXT_HI};}}")
            group.addButton(button)
            button.clicked.connect(
                lambda _checked=False, i=index: self._tabs.setCurrentIndex(i))
            self._context_buttons.append(button)
            lay.addWidget(button)
        lay.addStretch(1)

        # Le premier contexte est visible dès la construction, avant que le
        # projet soit chargé et avant le premier signal currentChanged.
        self._context_buttons[0].setChecked(True)
        return bar

    def _build_player_bar(self) -> QWidget:
        """Le lecteur, en bas de la colonne centrale : les commandes de monitoring de la ROM."""
        bar = QWidget()
        bar.setFixedHeight(42)
        bar.setStyleSheet(f"background:{C.BG_DEEP}; border-top:1px solid {C.BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(6)

        # Le bandeau reste une zone instrumentale : ses pavés sont plus
        # profonds que les champs d'édition, tout en gardant la palette thème.
        block = (f"background:{C.BG_BASE}; color:{C.TEXT_DIM}; "
                 f"border:1px solid {C.BORDER_MID}; padding:0 7px;")
        self._rom_label = QLabel(label("sndpanel.rom_play").removeprefix("▶ ").upper())
        self._rom_label.setFont(QFont(T.MONO, T.XS, QFont.Weight.DemiBold))
        self._rom_label.setFixedHeight(24)
        self._rom_label.setStyleSheet(block)
        lay.addWidget(self._rom_label)

        self._rom_source = QLabel("—")
        self._rom_source.setFont(QFont(T.MONO, T.XS))
        self._rom_source.setMinimumWidth(120)
        self._rom_source.setFixedHeight(24)
        self._rom_source.setStyleSheet(block)
        lay.addWidget(self._rom_source)

        self._btn_rom = QPushButton()
        self._btn_rom.setCheckable(True)
        self._btn_rom.setIcon(_ico("playback_play", C.TEXT_DIM, C.ACCENT))
        self._btn_rom.setIconSize(QSize(14, 14))
        self._btn_rom.setFixedWidth(30)
        self._btn_rom.setFixedHeight(24)
        self._btn_rom.setStyleSheet(
            f"QPushButton{{background:{C.BG_BASE}; color:{C.TEXT_DIM};"
            f"border:1px solid {C.BORDER_MID}; padding:0;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER}; border-color:{C.ACCENT};}}"
            f"QPushButton:checked{{background:{C.BG_SEL}; color:{C.ACCENT};"
            f"border-color:{C.ACCENT};}}")
        self._btn_rom.setToolTip(tooltip(
            title=label("sndpanel.rom_play").removeprefix("▶ "),
            body=label("sndpanel.rom_play_tip"),
            note=label("sndpanel.rom_play_note")))
        self._btn_rom.toggled.connect(self._on_rom_toggled)
        lay.addWidget(self._btn_rom)

        self._btn_rom_stop = QPushButton()
        self._btn_rom_stop.setFixedSize(30, 24)
        self._btn_rom_stop.setIcon(_ico("playback_stop", C.TEXT_DIM))
        self._btn_rom_stop.setIconSize(QSize(14, 14))
        self._btn_rom_stop.setToolTip(tooltip(title=label("sndpanel.rom_stop_title")))
        self._btn_rom_stop.setStyleSheet(
            f"QPushButton{{background:{C.BG_BASE}; color:{C.TEXT_DIM};"
            f"border:1px solid {C.BORDER_MID}; padding:0;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER}; border-color:{C.ACCENT_RED};"
            f"color:{C.ACCENT_RED};}}")
        self._btn_rom_stop.clicked.connect(self._stop_rom_playback)
        lay.addWidget(self._btn_rom_stop)

        self._btn_rom_loop = QToolButton()
        self._btn_rom_loop.setIcon(_ico("playback_loop", C.TEXT_DIM, C.ACCENT))
        self._btn_rom_loop.setIconSize(QSize(14, 14))
        self._btn_rom_loop.setCheckable(True)
        self._btn_rom_loop.setChecked(True)
        self._btn_rom_loop.setFixedSize(30, 24)
        self._btn_rom_loop.setToolTip(tooltip(title=label("sndpanel.rom_loop_title")))
        self._btn_rom_loop.setStyleSheet(
            f"QToolButton{{background:{C.BG_BASE}; color:{C.TEXT_DIM};"
            f"border:1px solid {C.BORDER_MID}; padding:0;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER}; border-color:{C.ACCENT};}}"
            f"QToolButton:checked{{background:{C.BG_SEL}; color:{C.ACCENT};"
            f"border-color:{C.ACCENT};}}")
        self._btn_rom_loop.toggled.connect(
            lambda enabled: self._box_player.set_looping(enabled))
        lay.addWidget(self._btn_rom_loop)

        self._rom_volume = QSlider(Qt.Orientation.Horizontal)
        self._rom_volume.setRange(0, 100)
        self._rom_volume.setValue(80)
        self._rom_volume.setFixedWidth(74)
        self._rom_volume.setToolTip(tooltip(
            title=label("sndpanel.preview_volume_title"), body=label("sndpanel.preview_volume_tip"),
        ))
        self._rom_volume.setStyleSheet(
            f"QSlider::groove:horizontal{{height:8px;background:{C.BG_BASE};"
            f"border:1px solid {C.BORDER};}}"
            f"QSlider::sub-page:horizontal{{background:{C.ACCENT};}}"
            f"QSlider::handle:horizontal{{width:8px;margin:-4px 0;background:{C.TEXT_NORM};"
            f"border:1px solid {C.BORDER_MID};}}")
        self._rom_volume.valueChanged.connect(self._on_rom_volume)
        lay.addWidget(self._rom_volume)

        self._rom_volume_readout = QLabel("VOL 80")
        self._rom_volume_readout.setFont(QFont(T.MONO, T.XS, QFont.Weight.DemiBold))
        self._rom_volume_readout.setFixedHeight(24)
        self._rom_volume_readout.setStyleSheet(block)
        lay.addWidget(self._rom_volume_readout)

        self._rom_progress = QProgressBar()
        self._rom_progress.setRange(0, 1000)
        self._rom_progress.setValue(0)
        self._rom_progress.setTextVisible(False)
        self._rom_progress.setMinimumWidth(130)
        self._rom_progress.setFixedHeight(12)
        self._rom_progress.setToolTip(tooltip(title=label("sndpanel.rom_progress_title")))
        self._rom_progress.setStyleSheet(
            f"QProgressBar{{background:{C.BG_BASE};border:1px solid {C.BORDER};}}"
            f"QProgressBar::chunk{{background:{C.ACCENT};}}")
        lay.addWidget(self._rom_progress, 1)

        self._rom_state = QLabel("IDLE")
        self._rom_state.setFont(QFont(T.MONO, T.XS, QFont.Weight.DemiBold))
        self._rom_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rom_state.setMinimumWidth(128)
        self._rom_state.setFixedHeight(24)
        self._rom_state.setStyleSheet(
            block)
        lay.addWidget(self._rom_state)

        self._box_player.state_changed.connect(self._on_rom_state)
        self._box_player.track_changed.connect(self._on_rom_track_changed)
        self._box_player.message.connect(lambda m: self._rom_state.setText(m))
        self._rom_progress_timer = QTimer(bar)
        self._rom_progress_timer.setInterval(100)
        self._rom_progress_timer.timeout.connect(self._refresh_rom_progress)
        self._rom_progress_timer.start()
        return bar

    # ── Lecture ROM ───────────────────────────────────────────────

    def _on_rom_toggled(self, on: bool):
        if on and self._armed_asset is not None:
            self._rom_state.setText(label("sndpanel.asset_preview"))
            if not self._box_player.preview(self._project, self._armed_asset):
                self._btn_rom.blockSignals(True)
                self._btn_rom.setChecked(False)
                self._btn_rom.blockSignals(False)
                self._rom_state.setText("IDLE")
            return
        if on:
            box =self._music_tab.current()
            if box is None or not box.states:
                # Décoché sans signal : le rappel de décochage remettrait « IDLE »
                # par-dessus le message.
                self._btn_rom.blockSignals(True)
                self._btn_rom.setChecked(False)
                self._btn_rom.blockSignals(False)
                self._rom_state.setText(label("sndpanel.no_state"))
                return
            self._box_player.load(self._project, box)
            self._box_player.start()
        else:
            self._box_player.stop()
            self._rom_state.setText("IDLE")
            self._rom_progress.setValue(0)

    def _stop_rom_playback(self):
        """Arrête la simulation sans modifier le contexte sélectionné."""
        self._btn_rom.setChecked(False)

    def _on_rom_volume(self, value: int):
        self._box_player.set_volume(value / 100.0)
        self._rom_volume_readout.setText(f"VOL {value:02d}")

    def _on_rom_track_changed(self, name: str, looping: bool):
        self._rom_source.setText(name or "—")
        self._btn_rom_loop.blockSignals(True)
        self._btn_rom_loop.setChecked(looping)
        self._btn_rom_loop.blockSignals(False)
        self._refresh_rom_progress()

    def _refresh_rom_progress(self):
        # Un aperçu d'asset non bouclé se termine tout seul : le bouton le suit.
        if (self._armed_asset is not None and self._btn_rom.isChecked()
                and not self._box_player.sounding):
            self._btn_rom.setChecked(False)
            return
        duration = self._box_player.duration_seconds
        if self._music_editor.isVisible():
            self._music_editor.set_playhead_seconds(
                self._box_player.position_seconds if self._box_player.sounding else -1.0)
        if duration <= 0:
            self._rom_progress.setValue(0)
            return
        self._rom_progress.setValue(
            min(1000, round(1000 * self._box_player.position_seconds / duration)))

    def _on_rom_state(self, name: str):
        self._rom_state.setText(label("sndpanel.preview_state", name=name))

    def _box_tabs(self) -> tuple:
        return (self._music_tab, self._sound_tab, self._jingle_tab)

    def _on_tab_changed(self, index: int):
        """Le finder ne montre que ce que l'onglet courant peut résoudre.

        Une action de SoundBox pointe vers un Sfx, une action de JingleBox vers
        un Jingle, un état de MusicBox vers une Music : la banque d'effets n'a
        rien à faire à côté d'un graphe musical, et l'inverse non plus. C'est aussi ce
        qui rend le glisser-déposer sans ambiguïté — ce qui est visible est ce
        qui se dépose.
        """
        self._disarm_asset()
        if self._machines_panel.isHidden():
            # Sans éditeur de boîtes, rien ne se dépose : le finder garde ses trois familles.
            self._finder.show_only(None)
        else:
            visible = {0: MUSIC.label, 1: SFX.label, 2: JINGLES.label}
            self._finder.show_only({visible.get(index, MUSIC.label)})
        if 0 <= index < len(self._context_buttons):
            self._context_buttons[index].setChecked(True)

    def _on_box_changed(self):
        """Une boîte a été choisie ou créée : l'inspecteur d'état la suit."""
        # Une autre boîte, ce sont d'autres états : ce qui jouait n'a plus de
        # sens. On coupe plutôt que de laisser sonner un état disparu.
        self._disarm_asset()
        if self._btn_rom.isChecked():
            self._btn_rom.setChecked(False)
        self._last_selected = None
        self._state_insp.load(self._music_tab.current(), None)
        if self._right_stack.currentWidget() is self._state_insp:
            self._right_stack.setCurrentIndex(0)
        self._refresh_budget()

    def _refresh_budget(self):
        """Recalcule le bandeau depuis les boîtes MUSIQUE et JINGLE en cours
        d'édition — pas depuis « la » boîte active en jeu (v0.8.7 : une seule
        par famille, la première par nom), parce que c'est celles-ci que
        l'auteur règle sous ses yeux.

        Le plafond est relu depuis le projet à CHAQUE appel plutôt que mis en
        cache : rien ne prévient cet écran quand il change ailleurs (aucun
        écran ne l'est — cf. window._show_screen), donc le lire à chaque
        édition est la seule façon de ne jamais afficher une valeur périmée.
        """
        if not self._project:
            return
        limit = int(getattr(self._project.settings, "sound_channels", 8))
        self._budget_bar.update_boxes(
            self._project, self._music_tab.current(), self._jingle_tab.current(), limit)

    def load_project(self, project: Project):
        self._disarm_asset()
        if self._btn_rom.isChecked():
            self._btn_rom.setChecked(False)
        self._last_selected = None
        self._project = project
        self._show_music_editor(None)
        self._finder.load_project(project)
        self._right_stack.setCurrentIndex(0)
        self._weights = None
        self._state_insp.set_musics([m.name for m in project.music])
        for tab in self._box_tabs():
            tab.load_project(project)
        self._on_tab_changed(self._tabs.currentIndex())
        self._refresh_budget()

    def _sound_weights(self) -> dict:
        """Poids relevés au dernier build, calculés à la demande puis gardés.

        Le rapprochement nom↔entrée du soundbank exige de connaître l'ORDRE
        dans lequel le build a passé les fichiers à mmutil — donc de reparcourir
        les scripts. Une fois par ouverture de projet suffit ; la mesure ne
        change qu'au build suivant.
        """
        if self._weights is not None or not self._project:
            return self._weights or {}
        try:
            from codegen.grit_conversion import resolve_sound_assets
            from codegen.rom_report import sound_weights
            sa = resolve_sound_assets(self._project)
            self._weights = sound_weights(
                self._project,
                [s.name for s, _ in sa["sfx"]],
                [m.name for m, _ in sa["music"]],
            )
        except Exception:
            # Aucun build, ou soundbank illisible : on n'affiche rien plutôt
            # que d'annoncer un poids deviné.
            self._weights = {}
        return self._weights

    def _on_state_selected(self, state):
        """Un nœud du graphe : c'est lui que la colonne de droite montre."""
        # Et, en lecture ROM, c'est le déclencheur qui y mène. Le graphe se
        # reconstruit à chaque édition et ré-émet la même sélection : sans ce
        # garde-fou, régler un volume rejouerait une transition.
        if state is not None:
            self._disarm_asset()
        if (state is not None and state is not self._last_selected
                and self._btn_rom.isChecked()):
            self._box_player.go_to(state.name)
        self._last_selected = state
        self._state_insp.load(self._music_tab.current(), state)
        if state is not None:
            self._right_stack.setCurrentWidget(self._state_insp)
        elif self._right_stack.currentWidget() is self._state_insp:
            self._right_stack.setCurrentIndex(0)

    # ── Sélection / lecture (relayées depuis le Sound finder) ──────

    def select_sound(self, family: str, name: str):
        """Ouvre le son `name` de `family` (« sfx », « music », « jingles ») — navigation entrante depuis l'onglet Disk."""
        kind, store = {"sfx": (SFX, self._project.sfx), "music": (MUSIC, self._project.music),
                       "jingles": (JINGLES, self._project.jingles)}[family]
        asset = store.get(name)
        if asset is not None:
            self._finder.select(kind.label, asset)

    def _on_asset_selected(self, asset):
        """Un seul point d'entrée pour les deux familles — le type de l'asset
        choisit l'inspecteur."""
        if isinstance(asset, Sfx):
            self._on_sfx_selected(asset)
        elif isinstance(asset, Jingle):      # avant Music : un Jingle EST une Music
            self._on_jingle_selected(asset)
        elif isinstance(asset, Music):
            self._on_music_selected(asset)
        self._arm_asset(asset)

    def _arm_asset(self, asset):
        """Le lecteur vise cet asset : un clic dans l'arbre suffit à l'écouter.

        Déjà en lecture, la sélection suivante enchaîne tout de suite, pour
        parcourir une liste à l'oreille avec les flèches.
        """
        same = asset is self._armed_asset
        was_on = self._btn_rom.isChecked()
        if was_on and self._armed_asset is None:
            # Ce qui sonne est la boîte : on la coupe avant de changer de cible.
            self._btn_rom.setChecked(False)
            was_on = False
        self._armed_asset = asset
        self._rom_source.setText(asset.name)
        if was_on and not same:
            self._on_rom_toggled(True)

    def _disarm_asset(self):
        """Retour à la boîte : le lecteur ne vise plus l'asset du finder."""
        if self._armed_asset is None:
            return
        self._armed_asset = None
        self._rom_source.setText("—")
        if self._btn_rom.isChecked():
            self._btn_rom.setChecked(False)

    def _show_music_editor(self, asset, sections: bool = True) -> None:
        """Montre l'éditeur sur cet asset, ou le cache (`asset` None). Il remplace le remplissage."""
        self._music_editor.load(self._project, asset, sections) if asset is not None \
            else self._music_editor.load(None, None)
        self._music_editor.setVisible(asset is not None)
        self._center_filler.setVisible(asset is None)
        self._edited_music = asset

    def _on_finder_emptied(self, _kind) -> None:
        self._right_stack.setCurrentIndex(0)
        self._show_music_editor(None)

    def _on_editor_changed(self) -> None:
        """Une section a bougé dans l'éditeur : on enregistre l'asset, sans réveiller le watcher
        (même règle que l'inspecteur, cf. `_AssetInspectorBase._persist`)."""
        asset = self._edited_music
        if asset is None or self._project is None:
            return
        with get_dispatcher().suspended():
            if isinstance(asset, Jingle):
                self._project.save_jingle(asset)
            else:
                self._project.save_music(asset)
        self._finder.refresh()

    def _preview_section(self, section) -> None:
        """Le ▶ d'une ligne du tableau : la musique, depuis le début de cette section."""
        asset = self._edited_music
        if asset is None or self._project is None:
            return
        self._arm_asset(asset)
        self._btn_rom.blockSignals(True)
        self._btn_rom.setChecked(True)
        self._btn_rom.blockSignals(False)
        self._rom_state.setText(label("sndpanel.asset_preview"))
        if not self._box_player.preview(self._project, asset, section):
            self._btn_rom.blockSignals(True)
            self._btn_rom.setChecked(False)
            self._btn_rom.blockSignals(False)
            self._rom_state.setText("IDLE")

    def _on_sfx_selected(self, sfx: Sfx):
        self._show_music_editor(None)
        self._sfx_insp.load(sfx, self._project)
        self._sfx_insp.refresh_weight(self._sound_weights().get(("sfx", sfx.name)))
        self._right_stack.setCurrentIndex(1)

    def _on_music_selected(self, music: Music):
        self._show_music_editor(music)
        self._music_insp.load(music, self._project)
        self._music_insp.refresh_weight(self._sound_weights().get(("music", music.name)))
        self._right_stack.setCurrentIndex(2)

    def _on_jingle_selected(self, jingle: Jingle):
        self._show_music_editor(jingle, sections=False)
        self._jingle_insp.load(jingle, self._project)
        # Même soundbank que les musiques : le poids se relève sous la même clé.
        self._jingle_insp.refresh_weight(self._sound_weights().get(("music", jingle.name)))
        self._right_stack.setCurrentWidget(self._jingle_insp)

    def _on_changed(self):
        self._finder.refresh()
