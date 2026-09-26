"""Sound Mixer screen — import/preview SFX + Music."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QSplitter, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QMenu, QFileDialog, QToolButton,
    QSlider, QSpinBox, QCheckBox, QScrollArea, QMessageBox,
    QComboBox, QTabWidget, QStackedWidget,
)
from PyQt6.QtMultimedia import (
    QMediaPlayer, QAudioOutput, QSoundEffect,
    QAudioSink, QAudioFormat, QMediaDevices, QAudio,
)
from PyQt6.QtGui import QFont, QColor, QShortcut, QKeySequence
from PyQt6.QtCore import (
    Qt, QUrl, QSize, pyqtSignal, QBuffer, QByteArray, QIODevice, QTimer,
)

from ui.common.theme import C, T, QSS
from ui.common.widgets import W
from ui.common.labels import label
from ui.common.icons import get as _ico, COLOR_DEFAULT
from ui.common import external_editor

from core.resources.asset_reconciliation import check_audio_file
from core.models.audio import (
    Music, Sfx, SFX_FILE_EXTS, MUSIC_FILE_EXTS,
    file_dialog_filter, sfx_rom_bytes,
)
from ui.sound_mixer.state_machines import (
    ActionMatrix, MusicMachinePanel, MusicStateInspector,
)
from ui.sound_mixer.box_playback import BoxPlayer
from ui.sound_mixer.sound_budget_bar import SoundBudgetBar
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import SFX, MUSIC
from core.project import Project
from core.engine_emulation.module_model import load_module
from core.engine_emulation.module_render import render_module, GBA_MIX_RATE
from core.history import get_history, DeleteResourceCmd
from core.keybindings import bind


# ──────────────────────────────────────────────────────────────────
#  Lecteur audio partagé
# ──────────────────────────────────────────────────────────────────
class AudioPlayer(QWidget):
    """
    Barre de lecture minimale (lecture seule, pas de scrub).

    Deux moteurs selon le format :
      - QMediaPlayer (Qt Multimedia) pour tout ce qu'il sait décoder nativement
        (wav/ogg/mp3…).
      - Rendu maison (core.engine_emulation.mod_render) + QAudioSink pour les .mod : Qt
        Multimedia n'a aucun décodeur tracker (FormatError à l'ouverture), et
        le rendu maison simule en plus le mixeur logiciel Maxmod du GBA (taux
        réduit, pas d'interpolation) pour une preview fidèle au rendu en jeu.
    """

    # Cache {chemin: pcm} pour ne pas re-render à chaque clic play/pause sur
    # le même morceau (le rendu prend jusqu'à ~1s pour un morceau long).
    _module_cache: dict = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer()
        self._audio  = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(0.8)
        self._player.errorOccurred.connect(self._on_player_error)
        self._current: Optional[Path] = None

        self._sink: Optional[QAudioSink] = None
        self._buffer: Optional[QBuffer] = None
        self._is_module = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._lbl = QLabel("—")
        self._lbl.setFont(QFont(T.UI, T.SM))
        self._lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        layout.addWidget(self._lbl, 1)

        self._btn = QPushButton("▶")
        self._btn.setFixedSize(28, 22)
        self._btn.setFont(QFont(T.MONO, T.MD))
        self._btn.setStyleSheet(
            f"QPushButton{{background:{C.BG_SEL};color:{C.ACCENT};border:1px solid #3a3a5a;"
            "border-radius:3px;}"
            "QPushButton:hover{background:#2e2e3d;}"
        )
        self._btn.clicked.connect(self._toggle)
        layout.addWidget(self._btn)

        self._stop_btn = QPushButton("■")
        self._stop_btn.setFixedSize(28, 22)
        self._stop_btn.setFont(QFont(T.MONO, T.MD))
        self._stop_btn.setStyleSheet(
            f"QPushButton{{background:{C.BORDER};color:{C.TEXT_DIM};border:1px solid {C.BORDER_MID};"
            "border-radius:3px;}"
            f"QPushButton:hover{{background:#3a2a2a;color:{C.ACCENT_RED};}}"
        )
        self._stop_btn.clicked.connect(self._stop)
        layout.addWidget(self._stop_btn)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100); self._vol.setValue(80); self._vol.setFixedWidth(70)
        self._vol.setStyleSheet(f"QSlider::groove:horizontal{{height:4px;background:{C.BORDER_MID};border-radius:2px;}}"
                          "QSlider::handle:horizontal{width:10px;height:10px;margin:-3px 0;"
                          f"background:{C.ACCENT};border-radius:5px;}}")
        self._vol.valueChanged.connect(self._on_volume)
        layout.addWidget(self._vol)

        # Éditer le fichier source dans un logiciel externe — même bouton
        # standard que le Background Editor / Sprite Editor (cf.
        # ui/common/external_editor.py) : cette barre écoute, elle ne retouche
        # pas une forme d'onde.
        self._btn_edit = QToolButton()
        self._btn_edit.setIcon(_ico("edit_external", COLOR_DEFAULT))
        self._btn_edit.setIconSize(QSize(15, 15))
        self._btn_edit.setFixedSize(24, 22)
        self._btn_edit.setStyleSheet(
            f"QToolButton{{border:none;background:transparent;border-radius:3px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};}}"
        )
        self._btn_edit.setToolTip(label("sndpanel.edit_audio_tip"))
        self._btn_edit.setEnabled(False)
        self._btn_edit.clicked.connect(self._on_edit_audio)
        self._btn_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._btn_edit.customContextMenuRequested.connect(self._on_edit_menu)
        layout.addWidget(self._btn_edit)

        self._player.playbackStateChanged.connect(self._on_state)

    def _on_edit_audio(self):
        if self._current is not None:
            external_editor.open_audio(self._current, self)

    def _on_edit_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        cur = external_editor.get_configured_editor(external_editor.KIND_AUDIO)
        act_choose = menu.addAction(label("common.choose_editor"))
        act_default = menu.addAction(label("common.use_default"))
        act_default.setEnabled(bool(cur))
        chosen = menu.exec(self._btn_edit.mapToGlobal(pos))
        if chosen == act_choose:
            external_editor.choose_editor(self, external_editor.KIND_AUDIO)
        elif chosen == act_default:
            external_editor.use_system_default(external_editor.KIND_AUDIO)

    def load(self, path: Path):
        self._teardown_sink()
        self._current = path
        self._is_module = path.suffix.lower() in MUSIC_FILE_EXTS
        self._lbl.setText(path.name)
        self._btn.setText("▶")
        self._btn_edit.setEnabled(bool(path and path.exists()))

        if self._is_module:
            self._player.stop()
            self._player.setSource(QUrl())
            self._prepare_module_sink(path)
        else:
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(str(path)))

    def play(self, path: Path):
        self.load(path)
        if self._is_module:
            if self._sink is not None:
                self._buffer.seek(0)
                self._sink.start(self._buffer)
                self._btn.setText("⏸")
        else:
            self._player.play()

    def _prepare_module_sink(self, path: Path):
        try:
            pcm = self._module_cache.get(path)
            if pcm is None:
                pcm = render_module(load_module(path))
                self._module_cache[path] = pcm
            if pcm.shape[0] == 0:
                self._lbl.setText(label("sndpanel.mod_empty", name=path.name))
                return
            fmt = QAudioFormat()
            fmt.setSampleRate(GBA_MIX_RATE)
            fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            device = QMediaDevices.defaultAudioOutput()
            self._sink = QAudioSink(device, fmt)
            self._sink.setVolume(self._vol.value() / 100.0)
            self._sink.stateChanged.connect(self._on_sink_state)
            self._buffer = QBuffer()
            self._buffer.setData(QByteArray(pcm.tobytes()))
            self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        except Exception as e:
            self._lbl.setText(label("sndpanel.mod_error", name=path.name, error=e))
            self._sink = None

    def _teardown_sink(self):
        if self._sink is not None:
            self._sink.stop()
            self._sink = None
        if self._buffer is not None:
            self._buffer.close()
            self._buffer = None

    def _toggle(self):
        if self._is_module:
            if self._sink is None:
                return
            if self._sink.state() == QAudio.State.ActiveState:
                self._sink.suspend()
            elif self._sink.state() == QAudio.State.SuspendedState:
                self._sink.resume()
            else:
                self._buffer.seek(0)
                self._sink.start(self._buffer)
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stop(self):
        self.stop_playback()

    def stop_playback(self):
        """Couper la lecture d'asset — appelé aussi de l'extérieur : la lecture
        ROM et l'aperçu d'un fichier se disputent la même carte son."""
        if self._is_module:
            if self._sink is not None:
                self._sink.stop()
            self._btn.setText("▶")
            return
        self._player.stop()

    def _on_state(self, state):
        if self._is_module:
            return
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._btn.setText("⏸" if playing else "▶")

    def _on_sink_state(self, state):
        if not self._is_module:
            return
        self._btn.setText("⏸" if state == QAudio.State.ActiveState else "▶")

    def _on_volume(self, v: int):
        vol = v / 100.0
        self._audio.setVolume(vol)
        if self._sink is not None:
            self._sink.setVolume(vol)

    def _on_player_error(self, error, error_string: str):
        if self._is_module or error == QMediaPlayer.Error.NoError:
            return
        self._lbl.setText(label("sndpanel.preview_unavailable",
                                name=self._current.name if self._current else "—",
                                error=error_string))


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
            l.setStyleSheet(f"color:{C.TEXT_DIM};"); l.setFixedWidth(70)
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
        self._vol.setToolTip(label("sndpanel.volume_tip"))
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
            self._project.rename_sound(self._asset, new_name)
            self.changed.emit()

    def _on_loop(self, v):
        if self._blocking or not self._asset: return
        self._asset.loop = v
        self._save()
        self.changed.emit()

    def _on_vol(self, v):
        if self._blocking or not self._asset: return
        self._asset.volume = v
        self._save()
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
        if reason := check_audio_file(Path(path)):
            QMessageBox.warning(self, label("sndpanel.import_rejected_title"),
                                label("sndpanel.import_rejected_text",
                                      name=Path(path).name, reason=reason))
            return
        dst = self._project.import_asset(Path(path), self._IMPORT_FOLDER)
        self._asset.asset = self._project.asset_rel(dst)
        self._save()
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
        self._rate.setToolTip(label("sndpanel.rate_tip"))
        self._rate.currentIndexChanged.connect(self._on_rate)
        row(label("sndpanel.rate"), self._rate)

    def _manager(self):
        return self._project.sfx

    def _on_rate(self, idx: int):
        if self._blocking or not self._asset: return
        self._asset.sample_rate = int(self._rate.itemData(idx) or 0)
        self._save()
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
        self._combo.setToolTip(label("sndpanel.box_tip"))
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
        self._btn_ren.setToolTip(label("sndpanel.rename_box_tip"))
        self._btn_ren.clicked.connect(self._begin_rename)
        btn_new = W.btn_ghost(label("sndpanel.new_box"))
        btn_new.clicked.connect(self._new)
        self._btn_del = W.btn_danger(label("sndpanel.del_box_tip"))
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
        from core.command_dispatcher import unique_name
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
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Pas de bandeau-titre d'écran : la nav du haut indique déjà où on est
        # (décision refonte thème 2026-08).

        # La barre de lecture ne vit plus en haut de l'écran : elle est sous
        # le node editor, dans le panneau central (cf. _build_machines_panel).
        # C'est là qu'on écoute, donc là qu'on commande.
        self._player = AudioPlayer()
        self._box_player = BoxPlayer(self)

        # Splitter principal
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setStyleSheet(QSS.splitter)
        root.addWidget(split, 1)

        # ── Panneau gauche : Sound finder ──────────────────────────
        # Deux familles dans un seul finder partagé ; c'est le TYPE de l'asset
        # reçu qui dit quel inspecteur montrer, pas un signal par famille.
        self._finder = AssetFinder(label('sndpanel.sound_finder'), [SFX, MUSIC],
                                   min_width=180, max_width=360)
        self._finder.selected.connect(lambda _kind, a: self._on_asset_selected(a))
        self._finder.emptied.connect(lambda _kind: self._right_stack.setCurrentIndex(0))
        # Double-clic ou Espace : écouter. Le finder ne sait pas ce qu'« activer »
        # veut dire, l'écran si.
        self._finder.activated.connect(lambda _kind, a: self._play_asset(a))
        sc_play = QShortcut(QKeySequence(), self._finder)
        sc_play.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_play.activated.connect(self._finder.activate_current)
        bind("sound.play_pause", sc_play)
        split.addWidget(self._finder)

        # ── Panneau central : les boîtes à état ───────────────────
        # C'est le cœur de l'écran (ROADMAP v0.8.7) : le finder n'est qu'un
        # magasin, l'inspecteur de droite ne règle qu'un asset à la fois, et
        # c'est ici que les sons se rangent en états et se relient.
        split.addWidget(self._build_machines_panel())

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

        split.addWidget(self._right_stack)
        split.setSizes([200, 560, 300])

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
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        self._music_machine = MusicMachinePanel()
        self._music_machine.state_selected.connect(self._on_state_selected)
        self._music_machine.state_created.connect(
            lambda: QTimer.singleShot(0, self._state_insp.focus_name))
        self._sfx_matrix = ActionMatrix(KIND_SOUND)
        self._jingle_matrix = ActionMatrix(KIND_JINGLE)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(QSS.tab)
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
                box, [m.name for m in self._project.music]),
            label("sndpanel.jinglebox_empty"))
        for tab, title in ((self._music_tab, "MusicBox"),
                           (self._sound_tab, "SoundBox"),
                           (self._jingle_tab, "JingleBox")):
            tab.changed.connect(self._on_box_changed)
            self._tabs.addTab(tab, title)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._music_machine.changed.connect(self._music_tab.save_current)
        self._sfx_matrix.changed.connect(self._sound_tab.save_current)
        self._jingle_matrix.changed.connect(self._jingle_tab.save_current)
        # Le bandeau ne lit que musique + jingle (cf. sound_budget_bar.py) :
        # la SoundBox n'y entre pas, donc `_sfx_matrix.changed` n'a rien à y
        # déclencher.
        self._music_machine.changed.connect(self._refresh_budget)
        self._jingle_matrix.changed.connect(self._refresh_budget)
        lay.addWidget(self._tabs, 1)
        lay.addWidget(self._build_player_bar())
        return panel

    def _build_player_bar(self) -> QWidget:
        """Sous le node editor : écouter un asset, ou écouter la BOÎTE.

        Deux lectures dans une seule barre parce qu'elles se disputent la même
        carte son — les mettre côte à côte, c'est rendre visible qu'on ne peut
        pas les avoir toutes les deux.
        """
        bar = QWidget()
        bar.setStyleSheet(f"background:{C.BG_BASE}; border-top:1px solid {C.BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)

        self._player.setFixedHeight(34)
        lay.addWidget(self._player, 1)

        self._btn_rom = QPushButton(label("sndpanel.rom_play"))
        self._btn_rom.setCheckable(True)
        self._btn_rom.setFont(QFont(T.UI, T.SM))
        self._btn_rom.setStyleSheet(
            f"QPushButton{{background:{C.BG_INPUT}; color:{C.TEXT_NORM};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:3px 10px;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER};}}"
            f"QPushButton:checked{{background:{C.BG_SEL}; color:{C.ACCENT};"
            f"border-color:{C.ACCENT};}}")
        self._btn_rom.setToolTip(label("sndpanel.rom_play_tip"))
        self._btn_rom.toggled.connect(self._on_rom_toggled)
        lay.addWidget(self._btn_rom)

        self._rom_state = QLabel("")
        self._rom_state.setFont(QFont(T.MONO, T.SM))
        self._rom_state.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._rom_state.setMinimumWidth(120)
        lay.addWidget(self._rom_state)

        self._box_player.state_changed.connect(self._on_rom_state)
        self._box_player.message.connect(
            lambda m: self._rom_state.setText(m))
        return bar

    # ── Lecture ROM ───────────────────────────────────────────────

    def _on_rom_toggled(self, on: bool):
        if on:
            self._player.stop_playback()   # une seule sortie audio à la fois
            box = self._music_tab.current()
            if box is None or not box.states:
                self._rom_state.setText(label("sndpanel.no_state"))
                self._btn_rom.setChecked(False)
                return
            self._box_player.load(self._project, box)
            self._box_player.start()
        else:
            self._box_player.stop()
            self._rom_state.setText("")

    def _on_rom_state(self, name: str):
        self._rom_state.setText(f"▶ {name}")

    def _box_tabs(self) -> tuple:
        return (self._music_tab, self._sound_tab, self._jingle_tab)

    def _on_tab_changed(self, index: int):
        """Le finder ne montre que ce que l'onglet courant peut résoudre.

        Une action de SoundBox pointe vers un Sfx, une action de JingleBox et
        un état de MusicBox vers une Music : la banque d'effets n'a rien à
        faire à côté d'un graphe musical, et l'inverse non plus. C'est aussi ce
        qui rend le glisser-déposer sans ambiguïté — ce qui est visible est ce
        qui se dépose.
        """
        self._finder.show_only({SFX.label} if index == 1 else {MUSIC.label})

    def _on_box_changed(self):
        """Une boîte a été choisie ou créée : l'inspecteur d'état la suit."""
        # Une autre boîte, ce sont d'autres états : ce qui jouait n'a plus de
        # sens. On coupe plutôt que de laisser sonner un état disparu.
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
        if self._btn_rom.isChecked():
            self._btn_rom.setChecked(False)
        self._last_selected = None
        self._project = project
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

    def _on_asset_selected(self, asset):
        """Un seul point d'entrée pour les deux familles — le type de l'asset
        choisit l'inspecteur."""
        if isinstance(asset, Sfx):
            self._on_sfx_selected(asset)
        elif isinstance(asset, Music):
            self._on_music_selected(asset)

    def _on_sfx_selected(self, sfx: Sfx):
        self._sfx_insp.load(sfx, self._project)
        self._sfx_insp.refresh_weight(self._sound_weights().get(("sfx", sfx.name)))
        self._right_stack.setCurrentIndex(1)
        self._load_asset(sfx)

    def _on_music_selected(self, music: Music):
        self._music_insp.load(music, self._project)
        self._music_insp.refresh_weight(self._sound_weights().get(("music", music.name)))
        self._right_stack.setCurrentIndex(2)
        self._load_asset(music)

    def _load_asset(self, obj):
        """
        Charge l'asset dans la barre de preview sans lancer la lecture — pour
        que le bouton ▶ (ou Espace) fonctionne dès la sélection, sans devoir
        d'abord double-cliquer l'entrée.
        """
        ap = self._project.asset_abs(obj.asset) if self._project and obj.asset else None
        if ap and ap.exists():
            self._player.load(ap)

    def _play_asset(self, obj):
        if self._btn_rom.isChecked():
            self._btn_rom.setChecked(False)
        ap = self._project.asset_abs(obj.asset) if self._project and obj.asset else None
        if ap and ap.exists():
            self._player.play(ap)

    def _on_changed(self):
        self._finder.refresh()
