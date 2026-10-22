"""Sound Mixer screen — preview SFX + Music."""

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QToolButton, QSlider, QProgressBar,
    QSpinBox, QCheckBox, QButtonGroup, QComboBox, QStackedWidget, QScrollArea, QSizePolicy,
)
from ui.common.popup import MessageBox as QMessageBox
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtCore import (
    Qt, QSize, QObject, QRunnable, QThreadPool, pyqtSignal, QTimer,
)

from ui.common.theme import C, T, QSS, ui_font
from ui.common.three_column_body import ThreeColumnBody
from ui.common.widgets import W
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.unit_spin import UnitSpin
from ui.common.icons import get as _ico

from core.engine_emulation.module_render import GBA_MIX_RATE, RenderCancelled
from core.models.audio import Jingle, Music, Sfx, sfx_rom_bytes
from ui.sound_mixer.state_machines import (
    ActionMatrix, MusicMachinePanel, MusicStateInspector,
)
from ui.sound_mixer.box_playback import BoxPlayer, render_track
from ui.sound_mixer.music_editor import MusicEditor
from ui.sound_mixer.sfx_editor import SfxEditor
from ui.sound_mixer.waveform_view import peak_envelope
from core.music_structure import is_wav_asset
from core.sfx_render import clear_preview_cache
from ui.sound_mixer.sound_budget_bar import SoundBudgetBar
from ui.sound_mixer.sound_commands import RenameSoundCmd
from ui.common.asset_library import AssetLibrary
from ui.common.asset_kinds import SFX, MUSIC, JINGLES
from core.keybindings import bind
from core.project import Project
from core.history import get_history, DeleteResourceCmd
from core.command_dispatcher import get_dispatcher
from ui.common.deferred_writes import get_deferred_writes, schedule_save


_RENDER_SWITCH_INTERVAL = 0.0002    # s : la durée max qu'un thread tient le GIL face aux autres pendant un rendu d'onde


class _WaveformRenderSignals(QObject):
    done = pyqtSignal(int, object, object)  # jeton, Track, enveloppe de dessin
    failed = pyqtSignal(int)             # jeton : rendu en échec OU abandonné ; l'écran garde l'onde précédente


class _WaveformRenderTask(QRunnable):
    """Rend une onde hors du fil Qt : aucun widget, cache ou modèle mutable ici.

    Le rendu peut être abandonné en route (`cancel`) : quand la main reprend un potard, il ne sert plus à rien."""

    def __init__(self, token: int, params: dict):
        super().__init__()
        self._token, self._params = token, params
        self._cancelled = False
        self.signals = _WaveformRenderSignals()

    def cancel(self) -> None:
        self._cancelled = True

    def _checkpoint(self) -> None:
        if self._cancelled:
            raise RenderCancelled

    def run(self) -> None:
        # Le rendu est du Python pur : il tient le GIL, et le thread de la carte son (qui tire le deck en Python)
        # attendait jusqu'à 44 ms son tour — le tampon audio n'en a que 50. Un intervalle de bascule court le lui
        # rend en moins de 3 ms, sans ralentir le rendu (mesuré le 2026-10-12). Restauré à la fin : il est global.
        switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(_RENDER_SWITCH_INTERVAL)
        try:
            track = render_track(**self._params, checkpoint=self._checkpoint)
            self.signals.done.emit(self._token, track, peak_envelope(track.pcm, GBA_MIX_RATE))
        except Exception:
            self.signals.failed.emit(self._token)
        finally:
            sys.setswitchinterval(switch_interval)


# ──────────────────────────────────────────────────────────────────
#  Inspector d'un Sfx
# ──────────────────────────────────────────────────────────────────
class _AssetInspectorBase(QWidget):
    """Base commune à SfxInspector/MusicInspector : header renommable,
    volume 0-255. Les sous-classes ne fournissent que
    leurs textes/filtres spécifiques et le manager de persistence."""
    changed = pyqtSignal()

    _EMPTY_TEXT = ""
    _HEADER_KIND = ""
    _HEADER_LABEL = ""
    _HAS_LOOP = False
    _HAS_FILE_LABEL = True   # le nom du fichier sous celui de l'asset ; le lecteur du bas le donne pour une musique
    _HAS_VOLUME = True       # une musique règle son volume à la table de mixage de l'éditeur

    def __init__(self, parent=None):
        super().__init__(parent)
        self._asset = None
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 4)
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
        # L'en-tête n'est pas posé ici : l'écran le ferre en haut de la colonne, hors de la zone qui défile
        # (cf. `SoundPanel._header_stack`), comme tous les inspecteurs.

        self._file_lbl = QLabel(label("sndpanel.no_file"))
        self._file_lbl.setFont(QFont(T.UI, T.SM))
        self._file_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        if not self._HAS_FILE_LABEL:        # jamais `setVisible(True)` ici : sans parent, le libellé s'ouvrirait en fenêtre
            self._file_lbl.setVisible(False)
        cl.addWidget(self._file_lbl)

        if self._HAS_LOOP:
            self._loop = QCheckBox(label("common.loop"))
            self._loop.setFont(QFont(T.UI, T.MD))
            self._loop.setStyleSheet(f"color:{C.TEXT_NORM};")
            self._loop.setToolTip(tooltip(
                title=label("sndpanel.loop_title"), body=label("sndpanel.loop_tip"),
            ))
            self._loop.toggled.connect(self._on_loop)
            # Une seule ligne ferrée en haut : la case Loop, puis ce que la famille y ajoute (le taux).
            self._loop_line = QHBoxLayout()
            self._loop_line.addWidget(self._loop)
            cl.addLayout(self._loop_line)

        if self._HAS_VOLUME:
            self._vol = UnitSpin(); self._vol.setRange(0, 100); self._vol.setSuffix(" %")
            self._vol.setFont(QFont(T.MONO, T.MD))
            self._vol.setStyleSheet(
                f"QSpinBox{{background:{C.BG_INPUT};color:{C.TEXT_NORM};border:1px solid {C.BORDER_MID};"
                "border-radius:3px;padding:2px;}"
            )
            self._vol.setToolTip(tooltip(
                title=label("sndpanel.volume_title"), body=label("sndpanel.volume_tip"),
            ))
            self._vol.valueChanged.connect(self._on_vol)
            row(label("sndpanel.volume"), self._vol)

        self._build_extra_rows(row, cl)

        # Poids réel en ROM, relevé au dernier build. Vide tant qu'aucun build
        # n'a eu lieu : l'éditeur mesure, il ne devine pas.
        self._weight = QLabel("")
        self._weight.setFont(QFont(T.UI, T.SM))
        self._weight.setStyleSheet(f"color:{C.TEXT_DIM}; margin-top:6px;")
        self._weight.setWordWrap(True)
        self._weight.setVisible(False)
        cl.addWidget(self._weight)

        cl.addStretch()
        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    @property
    def header(self):
        return self._header

    def _build_extra_rows(self, row, layout):
        """Champs propres à une famille. Rien par défaut."""

    def _weight_text(self, entry) -> str:
        """Ce que pèse cet asset en ROM, tel qu'on l'écrit à l'auteur."""
        return label("sndpanel.weight", kb=f"{entry.own_bytes / 1024:.1f}")

    def refresh_weight(self, entry):
        self._weight.setText(self._weight_text(entry) if entry else "")
        self._weight.setVisible(entry is not None)

    def _store(self, project: Project):
        """Le magasin de la famille de cet asset."""
        raise NotImplementedError

    def _persist(self):
        """Planifie l'écriture du sidecar (cf. `ui/common/deferred_writes.py`) : un champ qu'on tourne ne le réécrit
        pas à chaque cran. L'asset en mémoire est déjà à jour ; la file l'écrit après un silence, ou dès que la
        fenêtre la vide."""
        schedule_save(self._store(self._project), self._asset)

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
        if self._HAS_VOLUME:
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
            taken = self._store(self._project).get(new_name)
            if taken is not None and taken is not self._asset:
                self._restore_header_name()         # nom déjà pris : refus sans fenêtre, le champ reprend l'ancien nom
                return
            try:
                get_history().push(RenameSoundCmd(self._project, self._asset, new_name, self._after_rename))
            except FileExistsError:                 # fichier voisin de même nom (casse comprise, sous Windows)
                self._restore_header_name()

    def _after_rename(self, asset):
        """Après un renommage, ou son annulation : l'en-tête n'est remis à jour que si l'inspecteur montre cet asset."""
        if asset is self._asset:
            self._restore_header_name()
        self.changed.emit()

    def _restore_header_name(self):
        self._blocking = True
        self._header.set_header(self._HEADER_KIND, label(self._HEADER_LABEL), self._asset.name)
        self._blocking = False

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


class SfxInspector(_AssetInspectorBase):
    _EMPTY_TEXT = "sndpanel.sfx_empty"
    _HEADER_KIND = "sfx"
    _HEADER_LABEL = "common.sfx"
    _HAS_VOLUME = False      # volume, hauteur, variation et fondus : la table de mixage de l'éditeur d'effet

    # Taux proposés. Maxmod mixe autour de 16 kHz : au-delà on paie de la ROM
    # pour un détail que la console ne restitue pas.
    _RATES = ((0, label('sndpanel.from_project')), (8000, "8 000 Hz"), (11025, "11 025 Hz"),
              (16000, "16 000 Hz"), (22050, "22 050 Hz"), (32000, "32 000 Hz"))

    def _file_hint(self, path: Path) -> str:
        """Le poids du FICHIER SOURCE, avant tout ré-échantillonnage.

        mmutil conserve le taux : sans quantification, un effet en 44,1 kHz
        coûte près de trois fois ce qu'il coûterait en 16 kHz sans rien
        apporter que le mixeur Maxmod sache restituer. On affiche le fait, on
        ne refuse pas le choix.
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

        # Protégé : maxmod ne volera jamais le canal de cet effet quand tous les canaux du projet sont pris.
        self._protected = QCheckBox(label("sndpanel.sfx_protected"))
        self._protected.setFont(QFont(T.UI, T.MD))
        self._protected.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._protected.setToolTip(tooltip(
            title=label("sndpanel.sfx_protected_title"), body=label("sndpanel.sfx_protected_tip"),
        ))
        self._protected.toggled.connect(self._on_protected)
        layout.addWidget(self._protected)

    def load(self, asset, project):
        super().load(asset, project)
        if asset:
            self._blocking = True
            self._protected.setChecked(bool(getattr(asset, "protected", False)))
            self._blocking = False

    def _store(self, project: Project):
        return project.sfx

    # Un réglage de ROM qui ne change ni le rendu ni l'explorateur, donc pas de `changed`.
    def _on_protected(self, checked: bool):
        if self._blocking or not self._asset: return
        self._asset.protected = checked
        self._persist()

    def _on_rate(self, idx: int):
        if self._blocking or not self._asset: return
        self._asset.sample_rate = int(self._rate.itemData(idx) or 0)
        self._persist()
        self.changed.emit()


# ──────────────────────────────────────────────────────────────────
#  Inspector d'une Music
# ──────────────────────────────────────────────────────────────────
class MusicInspector(_AssetInspectorBase):
    _EMPTY_TEXT = "sndpanel.music_empty"
    _HEADER_KIND = "music"
    _HEADER_LABEL = "sndpanel.header_music"
    _HAS_LOOP = True
    _HAS_VOLUME = False      # volume, tempo, hauteur et fondus : la table de mixage de l'éditeur
    _HAS_FILE_LABEL = False  # son nom de fichier est dans le lecteur, en bas
    # Le taux de build, seul réglage de ROM resté ici. Un jingle n'en applique aucun (il joue sur
    # l'autre couche, avec son propre volume) : son inspecteur ne le propose pas.
    _SETTINGS = True

    # Taux de build d'une piste WAV : 0 = le défaut. Plus bas, la piste pèse moins et peut être plus longue.
    _RATES = ((0, "sndpanel.rate_default"), (8000, "8 000 Hz"), (11025, "11 025 Hz"),
              (13379, "13 379 Hz"), (16000, "16 000 Hz"))

    def _build_extra_rows(self, row, layout):
        if not self._SETTINGS:
            return
        self._rate = QComboBox()
        self._rate.setFont(QFont(T.UI, T.MD))
        for value, text in self._RATES:
            self._rate.addItem(label(text) if text.startswith("sndpanel.") else text, value)
        self._rate.setToolTip(tooltip(title=label("sndpanel.music_rate"),
                                      body=label("sndpanel.music_rate_tip")))
        self._rate.currentIndexChanged.connect(self._on_rate)
        # Sur la ligne de la case Loop : « ☐ Loop      Rate [Default ▾] ».
        caption = QLabel(label("sndpanel.rate"))
        caption.setFont(QFont(T.UI, T.SM))
        caption.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._loop_line.addSpacing(16)
        self._loop_line.addWidget(caption)
        self._loop_line.addWidget(self._rate, 1)

    def load(self, asset, project):
        super().load(asset, project)
        if not asset or not self._SETTINGS:
            return
        self._blocking = True
        index = self._rate.findData(int(asset.sample_rate or 0))
        self._rate.setCurrentIndex(index if index >= 0 else 0)
        # Un WAV change de taux ; un module garde ses échantillons, donc pas de taux.
        self._rate.setEnabled(is_wav_asset(asset.asset))
        self._blocking = False

    def _set_setting(self, field: str, value) -> None:
        if self._blocking or not self._asset:
            return
        setattr(self._asset, field, value)
        self._persist()
        self.changed.emit()

    def _on_rate(self, index): self._set_setting("sample_rate", int(self._rate.itemData(index) or 0))

    def _store(self, project: Project):
        return project.music


class JingleInspector(MusicInspector):
    """Un jingle ne boucle pas (maxmod le joue une fois : la case Loop n'a pas de sens ici), et il règle ce que devient la
    MUSIQUE sous lui : elle continue, descend, ou attend (`Jingle.music_policy`)."""
    _EMPTY_TEXT = "sndpanel.jingle_empty"
    _SETTINGS = False
    _HAS_LOOP = False
    _HEADER_LABEL = "sndpanel.header_jingle"

    def _build_extra_rows(self, row, layout):
        from core.models.audio import FADE_MAX_FRAMES, JINGLE_POLICIES
        spin_style = (f"QSpinBox{{background:{C.BG_INPUT};color:{C.TEXT_NORM};border:1px solid {C.BORDER_MID};"
                      "border-radius:3px;padding:2px;}")
        # Un titre, le sélecteur dessous, puis — seulement quand la politique les demande — le niveau et la remontée.
        caption = QLabel(label("sndpanel.policy"))
        caption.setFont(QFont(T.UI, T.SM))
        caption.setStyleSheet(f"color:{C.TEXT_DIM};")
        layout.addWidget(caption)
        self._policy = QComboBox()
        self._policy.setFont(QFont(T.UI, T.MD))
        for policy in JINGLE_POLICIES:
            self._policy.addItem(label(f"sndpanel.policy_{policy}"), policy)
        self._policy.setToolTip(tooltip(title=label("sndpanel.policy_title"), body=label("sndpanel.policy_tip")))
        self._policy.currentIndexChanged.connect(self._on_policy)
        layout.addWidget(self._policy)

        self._duck_box = QWidget()
        box = QVBoxLayout(self._duck_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)

        def duck_row(caption_key: str, widget: UnitSpin) -> None:
            line = QHBoxLayout()
            name = QLabel(label(caption_key))
            name.setFont(QFont(T.UI, T.SM))
            name.setStyleSheet(f"color:{C.TEXT_DIM};")
            name.setFixedWidth(92)
            line.addWidget(name)
            line.addWidget(widget, 1)
            box.addLayout(line)

        self._duck_level = UnitSpin()
        self._duck_level.setRange(0, 100)
        self._duck_level.setSuffix(" %")
        self._duck_level.setFont(QFont(T.MONO, T.MD))
        self._duck_level.setStyleSheet(spin_style)
        self._duck_level.setToolTip(tooltip(title=label("sndpanel.duck_level_title"), body=label("sndpanel.duck_level_tip")))
        self._duck_level.valueChanged.connect(lambda value: self._write("duck_level", value))
        duck_row("sndpanel.duck_level", self._duck_level)

        self._duck_release = UnitSpin()
        self._duck_release.setRange(0, FADE_MAX_FRAMES)
        self._duck_release.setSuffix(" fr")
        self._duck_release.setFont(QFont(T.MONO, T.MD))
        self._duck_release.setStyleSheet(spin_style)
        self._duck_release.setToolTip(tooltip(title=label("sndpanel.duck_release_title"),
                                              body=label("sndpanel.duck_release_tip")))
        self._duck_release.valueChanged.connect(lambda value: self._write("duck_release", value))
        duck_row("sndpanel.duck_release", self._duck_release)
        layout.addWidget(self._duck_box)
        self._duck_box.setVisible(False)

    def load(self, asset, project):
        super().load(asset, project)
        if not asset:
            return
        self._blocking = True
        self._policy.setCurrentIndex(max(0, self._policy.findData(asset.music_policy)))
        self._duck_level.setValue(asset.duck_level)
        self._duck_release.setValue(asset.duck_release)
        self._sync_duck_fields()
        self._blocking = False

    def _sync_duck_fields(self) -> None:
        """Le niveau et la remontée ne valent que pour « baisser » : les autres politiques ne les montrent pas."""
        self._duck_box.setVisible(self._policy.currentData() == "duck")

    # Rien ne change au rendu ni à l'explorateur : l'asset est à jour, le sidecar s'écrit après un silence, pas de `changed`.
    def _write(self, field: str, value) -> None:
        if self._blocking or not self._asset:
            return
        setattr(self._asset, field, value)
        self._persist()

    def _on_policy(self, _index: int) -> None:
        self._sync_duck_fields()
        self._write("music_policy", self._policy.currentData())

    def _store(self, project: Project):
        return project.jingles


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
    """Écran complet Sound Mixer : SFX + Music (via AssetLibrary) + preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        clear_preview_cache()                  # les rendus d'aperçu des sessions précédentes ne servent plus
        self._project: Optional[Project] = None
        self._weights: Optional[dict] = None   # poids du dernier build, à la demande
        self._last_selected = None             # cf. _on_state_selected
        # L'asset du Sound library que le lecteur jouera à la place de la boîte,
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

        # ── Panneau gauche : Sound library ──────────────────────────
        # Deux familles dans un seul library partagé ; c'est le TYPE de l'asset
        # reçu qui dit quel inspecteur montrer, pas un signal par famille.
        self._library = AssetLibrary(label('sndpanel.sound_library'), [SFX, MUSIC, JINGLES],
                                   min_width=180, max_width=360)
        self._library.selected.connect(lambda _kind, a: self._on_asset_selected(a))
        self._library.emptied.connect(self._on_library_emptied)

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
        # place du graphe masqué quand un module est choisi dans la library (cf. `_show_music_editor`).
        self._music_editor = MusicEditor(self._box_player.track_for,
                                        lambda music: self._sound_weights().get(("music", music.name)))
        self._music_editor.changed.connect(self._on_editor_changed)
        self._music_editor.preview_section.connect(self._preview_section)
        self._music_editor.mix_changed.connect(self._on_mix_changed)
        self._music_editor.mix_released.connect(self._schedule_retune)
        self._music_editor.scrub_requested.connect(self._scrub_preview)
        self._music_editor.set_live_source(self._live_scope_window)
        # L'onde complète se relance au plus tous les 100 ms PENDANT le geste (un minuteur qui n'est pas
        # redémarré par chaque cran) : le son, lui, suit chaque cran (cf. `_on_mix_changed`).
        self._retune_timer = QTimer(self)
        self._retune_timer.setSingleShot(True)
        self._retune_timer.setInterval(100)
        self._retune_timer.timeout.connect(self._retune)
        self._retune_token = 0
        self._retune_running = False
        self._retune_pending = None                 # dernière demande seulement : les crans intermédiaires sont jetés
        self._retune_task = None                    # garde les signaux vivants pendant le travail du pool
        self._retune_active_key = None
        self._retune_pending_key = None
        self._retune_applied_key = None
        self._music_editor.hide()
        center_layout.addWidget(self._music_editor, 1)
        # La découpe d'un effet : même place que l'éditeur de musique, qu'il remplace quand c'est un effet qu'on ouvre.
        self._sfx_editor = SfxEditor(self._box_player.track_for)
        self._sfx_editor.set_live_source(self._live_scope_window)
        self._sfx_editor.changed.connect(self._on_changed)
        self._sfx_editor.original_rate_toggled.connect(self._box_player.set_original_rate)     # écoute A/B du taux
        self._sfx_editor.hide()
        center_layout.addWidget(self._sfx_editor, 1)
        # Le lecteur ne dépend pas de l'éditeur de boîtes : il reste ancré en bas de la colonne (hauteur
        # fixe) même quand le panneau des boîtes est masqué. Le remplissage pousse la barre vers le bas
        # tant que l'éditeur n'est pas là, et lui cède la place sinon.
        self._center_filler = QWidget()
        center_layout.addWidget(self._center_filler, 1)
        center_layout.addWidget(self._build_player_bar())
        # Espace lance / arrête l'aperçu, comme le bouton du bandeau. Sur tout l'écran et non sur la
        # seule colonne centrale : on choisit un asset dans la library puis on l'écoute sans changer de focus.
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
        self._sfx_insp.changed.connect(self._sfx_editor.refresh_soon)  # le taux change le poids annoncé de la découpe
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

        # Le haut de la colonne défile d'un bloc : l'inspecteur de l'asset, puis les sections de boucle de la musique
        # ou du jingle ouvert (cf. `MusicEditor.sections_panel`). Sous le tout, ferrée en bas, la table de mixage
        # (`mix_panel`) : elle ne défile pas.
        self._upper_layout = QVBoxLayout()
        self._upper_layout.setContentsMargins(0, 0, 0, 0)
        self._upper_layout.setSpacing(0)
        self._upper_layout.addWidget(self._right_stack, 1)
        self._upper_layout.addWidget(self._music_editor.sections_panel)
        self._upper_layout.addStretch(0)
        upper = QWidget()
        upper.setLayout(self._upper_layout)
        # Une pile prend la taille de sa plus grande page : on ne garde que celle de la page affichée, sinon
        # l'inspecteur le plus haut repousserait les sections même quand il n'est pas là.
        self._right_stack.currentChanged.connect(self._fit_right_stack)
        self._fit_right_stack(0)
        upper_scroll = QScrollArea()
        upper_scroll.setWidgetResizable(True)
        upper_scroll.setFrameShape(QFrame.Shape.NoFrame)
        upper_scroll.setStyleSheet(QSS.scroll_area)
        upper_scroll.setWidget(upper)
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)
        # L'en-tête (type + nom) est ferré en haut, hors du défilement : une page de `_right_stack` = une page ici.
        from ui.common.widgets import AssetHeaderBar
        self._header_stack = QStackedWidget()
        self._state_header = AssetHeaderBar()
        for header in (AssetHeaderBar(), self._sfx_insp.header, self._music_insp.header,
                       self._state_header, self._jingle_insp.header):
            self._header_stack.addWidget(header)
        self._right_stack.currentChanged.connect(self._header_stack.setCurrentIndex)
        right_lay.addWidget(self._header_stack)
        right_lay.addWidget(upper_scroll, 1)
        right_lay.addWidget(self._music_editor.mix_panel)
        right_lay.addWidget(self._sfx_editor.mix_panel)         # au même endroit : une seule des deux tables se montre
        self._music_editor.structure_changed.connect(self._sync_right_column)

        self.body = ThreeColumnBody(self._library, center, right,
                                    sizes=(200, 560, 320))
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
        # Ce que le lecteur vise : le nom du fichier, ce qu'il pèse en ROM (la pastille de l'éditeur de musique,
        # cachée quand il n'y a pas de chiffre sûr), et son extension.
        self._rom_source = QLabel("—")
        self._rom_source.setFont(QFont(T.MONO, T.XS, QFont.Weight.DemiBold))
        self._rom_source.setMinimumWidth(150)
        self._rom_source.setFixedHeight(24)
        self._rom_source.setStyleSheet(block)
        lay.addWidget(self._rom_source)

        lay.addWidget(self._music_editor.weight_pill)

        self._rom_extension = QLabel("—")
        self._rom_extension.setFont(QFont(T.MONO, T.XS))
        self._rom_extension.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rom_extension.setMinimumWidth(52)
        self._rom_extension.setFixedHeight(24)
        self._rom_extension.setStyleSheet(block)
        lay.addWidget(self._rom_extension)

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
        self._rom_progress_timer.setInterval(16)    # ~60 Hz : tête de lecture fluide
        self._rom_progress_timer.timeout.connect(self._refresh_rom_progress)
        self._rom_progress_timer.start()
        return bar

    # ── Lecture ROM ───────────────────────────────────────────────

    def _on_rom_toggled(self, on: bool):
        if on and self._armed_asset is not None:
            self._rom_state.setText(label("sndpanel.asset_preview"))
            # Une section sélectionnée dans l'éditeur : c'est elle qui boucle ; sinon la musique, d'une traite.
            scope = self._music_editor.scope_section if self._armed_asset is self._edited_music else None
            if not self._box_player.preview(self._project, self._armed_asset, scope):
                self._btn_rom.blockSignals(True)
                self._btn_rom.setChecked(False)
                self._btn_rom.blockSignals(False)
                self._rom_state.setText("IDLE")
            else:
                self._seek_to_cue()
            return
        if on:
            box = self._music_tab.current()
            # Panneau des boîtes caché : jouer une boîte que l'auteur ne voit pas serait un son sans cause visible.
            if self._machines_panel.isHidden():
                self._btn_rom.blockSignals(True)
                self._btn_rom.setChecked(False)
                self._btn_rom.blockSignals(False)
                return
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

    def _show_source(self, asset, fallback_name: str = "") -> None:
        """Le fichier que le lecteur vise (son nom, son extension). Sans fichier : le nom de l'asset, ou un tiret."""
        path = Path(asset.asset) if asset is not None and asset.asset else None
        name = path.name if path else (asset.name if asset is not None else fallback_name)
        self._rom_source.setText(name or "—")
        self._rom_source.setToolTip(name)
        self._rom_extension.setText(path.suffix.lstrip(".").upper() if path and path.suffix else "—")

    def _find_music(self, name: str):
        """La musique ou le jingle de ce nom, ou None (la boîte joue des musiques par leur nom)."""
        if not name or self._project is None:
            return None
        return self._project.music.get(name) or self._project.jingles.get(name)

    def _on_rom_track_changed(self, name: str, looping: bool):
        self._show_source(self._find_music(name), name)
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
        if self._sfx_editor.isVisible():
            self._sfx_editor.set_playhead_seconds(
                self._box_player.position_seconds
                if self._box_player.sounding and self._box_player.previewing(self._edited_sfx()) else -1.0)
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
        """La library ne montre que ce que l'onglet courant peut résoudre.

        Une action de SoundBox pointe vers un Sfx, une action de JingleBox vers
        un Jingle, un état de MusicBox vers une Music : la banque d'effets n'a
        rien à faire à côté d'un graphe musical, et l'inverse non plus. C'est aussi ce
        qui rend le glisser-déposer sans ambiguïté — ce qui est visible est ce
        qui se dépose.
        """
        self._disarm_asset()
        if self._machines_panel.isHidden():
            # Sans éditeur de boîtes, rien ne se dépose : la library garde ses trois familles.
            self._library.show_only(None)
        else:
            visible = {0: MUSIC.label, 1: SFX.label, 2: JINGLES.label}
            self._library.show_only({visible.get(index, MUSIC.label)})
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
        # Il lit les boîtes : sans leur panneau à l'écran, le chiffre décrirait des boîtes invisibles.
        self._budget_bar.setVisible(not self._machines_panel.isHidden())
        limit = int(getattr(self._project.settings, "sound_channels", 8))
        self._budget_bar.update_boxes(
            self._project, self._music_tab.current(), self._jingle_tab.current(), limit)

    def set_folder_store(self, store) -> None:
        """Range effets, musiques et jingles en dossiers d'auteur, dans le store PARTAGÉ de la session
        (celui des scènes : une seule instance par fichier). Les assets sont rangés par id — renommer ou
        déplacer le fichier d'un son ne le fait pas sortir de son dossier."""
        if self._project is not None:
            for family, assets in (("sfx", self._project.sfx), ("music", self._project.music),
                                   ("jingles", self._project.jingles)):
                store.prune(family, {a.id for a in assets})
        self._library.set_folder_store(store)

    def load_project(self, project: Project):
        self._disarm_asset()
        if self._btn_rom.isChecked():
            self._btn_rom.setChecked(False)
        self._last_selected = None
        self._music_editor.flush_pending()      # avant le changement de projet : l'écriture en attente vise l'ancien
        self._project = project
        self._show_music_editor(None)
        self._library.load_project(project)
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
            # Le nom se change dans le champ de l'inspecteur : l'en-tête le montre sans l'éditer.
            self._state_header.set_header("music", label("sndmix.sec_state"), state.name, editable=False)
            self._right_stack.setCurrentWidget(self._state_insp)
        elif self._right_stack.currentWidget() is self._state_insp:
            self._right_stack.setCurrentIndex(0)

    # ── Sélection / lecture (relayées depuis le Sound library) ──────

    def select_sound(self, family: str, name: str):
        """Ouvre le son `name` de `family` (« sfx », « music », « jingles ») — navigation entrante depuis l'onglet Disk."""
        kind, store = {"sfx": (SFX, self._project.sfx), "music": (MUSIC, self._project.music),
                       "jingles": (JINGLES, self._project.jingles)}[family]
        asset = store.get(name)
        if asset is not None:
            self._library.select(kind.label, asset)

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
        self._show_source(asset)
        if was_on and not same:
            self._on_rom_toggled(True)

    def _disarm_asset(self):
        """Retour à la boîte : le lecteur ne vise plus l'asset de la library."""
        if self._armed_asset is None:
            return
        self._armed_asset = None
        self._show_source(None)
        if self._btn_rom.isChecked():
            self._btn_rom.setChecked(False)

    def _show_music_editor(self, asset, sections: bool = True) -> None:
        """Montre l'éditeur sur cet asset, ou le cache (`asset` None). Il remplace le remplissage."""
        self._music_editor.load(self._project, asset, sections) if asset is not None \
            else self._music_editor.load(None, None)
        self._music_editor.setVisible(asset is not None)
        self._sfx_editor.setVisible(False)             # `_on_sfx_selected` le remontre : un seul des deux occupe la colonne
        self._sfx_editor.mix_panel.setVisible(False)   # et sa table de mixage avec lui
        self._center_filler.setVisible(asset is None)
        self._edited_music = asset

    def _fit_right_stack(self, index: int) -> None:
        for i in range(self._right_stack.count()):
            page = self._right_stack.widget(i)
            policy = page.sizePolicy()
            policy.setVerticalPolicy(QSizePolicy.Policy.Preferred if i == index else QSizePolicy.Policy.Ignored)
            page.setSizePolicy(policy)
        self._right_stack.updateGeometry()

    def _sync_right_column(self) -> None:
        """Sans sections à montrer (jingle, fichier illisible), la pile de l'inspecteur reprend toute la hauteur ;
        avec, elle prend la sienne et les sections suivent juste dessous."""
        with_sections = not self._music_editor.sections_panel.isHidden()
        self._upper_layout.setStretch(0, 0 if with_sections else 1)
        self._upper_layout.setStretch(2, 1 if with_sections else 0)

    def _on_library_emptied(self, _kind) -> None:
        self._right_stack.setCurrentIndex(0)
        self._show_music_editor(None)

    def _on_editor_changed(self) -> None:
        """Une section ou un curseur a bougé dans l'éditeur : on enregistre l'asset, sans réveiller le watcher
        (même règle que l'inspecteur, cf. `_AssetInspectorBase._persist`). Le Sound library ne montre ni les
        sections ni le mixage : on ne le recharge pas (il perdrait sa sélection et son défilement)."""
        asset = self._edited_music
        if asset is None or self._project is None:
            return
        with get_dispatcher().suspended():
            if isinstance(asset, Jingle):
                self._project.save_jingle(asset)
            else:
                self._project.save_music(asset)

    def _on_mix_changed(self, field: str) -> None:
        """Un curseur de la table de mixage bouge : l'aperçu en cours le suit PENDANT qu'il bouge, au tick près —
        le module est joué tick par tick, avec le volume, le tempo et la hauteur du moment. L'onde complète est
        reconstruite pendant le geste, au rythme où le rendu suit."""
        asset = self._edited_music
        if asset is None or self._project is None:
            return
        if field == "volume":
            self._box_player.set_preview_volume(asset)
            return
        self._box_player.set_preview_tuning(asset)
        self._schedule_retune()

    def _schedule_retune(self) -> None:
        """Un réglage de tempo ou de hauteur bouge : l'onde et la règle le suivent sans rendu (cf. `WaveformView`), et
        celui qui tournait encore est abandonné. Le rendu exact part à la première pause, quand la main ne tient plus."""
        if self._retune_task is not None:
            self._retune_task.cancel()
        self._retune_timer.start()

    def _live_scope_window(self, frames: int):
        """Ce que l'aperçu de la musique en cours d'édition fait entendre à l'instant : le tracé de l'oscilloscope."""
        asset = self._edited_music if self._edited_music is not None else self._edited_sfx()
        return None if asset is None else self._box_player.scope_window(asset, frames)

    def _edited_sfx(self):
        """L'effet dont l'éditeur de découpe est ouvert, ou None."""
        return self._sfx_editor._sfx if self._sfx_editor.isVisible() else None

    def _scrub_preview(self, seconds: float, held: bool) -> None:
        """La tête de lecture est glissée dans l'onde : tant que la main est posée, la lecture automatique attend et
        le son suit le geste ; au lâcher, elle reprend d'où la main l'a laissée."""
        asset = self._edited_music
        if asset is None or self._project is None or not self._box_player.previewing(asset):
            return
        if held:
            self._box_player.scrub(seconds)
        else:
            self._box_player.scrub_end(seconds)

    def _retune(self) -> None:
        """Le geste s'est calmé : l'éditeur refait le rendu exact pour ces réglages (la frise sur laquelle le deck
        scrube). Tant que la main tient un potard, rien : l'onde n'a presque pas changé, et le geste reprendra."""
        if self._music_editor.mixing:
            return
        asset = self._edited_music
        if asset is None or self._project is None:
            return
        request = self._box_player.waveform_render_request(self._project, asset)
        if request is None:
            return
        key, params, info, cached = request
        # Le relâchement arrive souvent juste après le dernier cran. S'il vise
        # exactement le rendu en cours, en attente ou déjà affiché, il n'a rien
        # à refaire — c'était la principale source de saut en fin de geste.
        if key == self._retune_pending_key:
            return
        if key == self._retune_active_key and self._retune_pending is None:
            return
        if (key == self._retune_applied_key and not self._retune_running
                and self._retune_pending is None):
            return
        self._retune_token += 1
        token = self._retune_token
        if cached is not None:
            self._apply_cached_retuned_track(token, asset, key, cached)
            return
        # Pendant qu'un rendu est occupé, on ne l'interrompt pas ici ; on remplace simplement la demande qui
        # l'attend. Au retour, seule la dernière valeur aura le droit d'apparaître.
        self._retune_pending = (token, asset, key, params, info)
        self._retune_pending_key = key
        if not self._retune_running:
            self._start_pending_retune()

    def _start_pending_retune(self) -> None:
        if self._retune_running or self._retune_pending is None:
            return
        token, _asset, key, params, _info = self._retune_pending
        self._retune_pending = None
        self._retune_pending_key = None
        self._retune_running = True
        self._retune_active_key = key
        task = _WaveformRenderTask(token, params)
        self._retune_task = task
        task.signals.done.connect(self._on_retuned_track)
        task.signals.failed.connect(self._on_retune_failed)
        QThreadPool.globalInstance().start(task)

    def _on_retuned_track(self, token: int, track, envelope) -> None:
        self._retune_running = False
        self._retune_task = None
        self._retune_active_key = None
        # Un cran plus récent est arrivé pendant le rendu : son résultat est
        # plus utile que celui-ci, qui ne touche donc jamais l'interface.
        if token == self._retune_token:
            asset = self._edited_music
            if asset is not None and self._project is not None:
                request = self._box_player.waveform_render_request(self._project, asset)
                if request is not None:
                    key, _params, info, _cached = request
                    self._apply_retuned_track(token, asset, key, info, track, envelope)
        self._start_pending_retune()

    def _on_retune_failed(self, _token: int) -> None:
        self._retune_running = False
        self._retune_task = None
        self._retune_active_key = None
        self._start_pending_retune()

    def _apply_retuned_track(self, token: int, asset, key, info: tuple, track, envelope) -> None:
        if (token != self._retune_token or asset is not self._edited_music
                or self._project is None):
            return
        rendered = self._box_player.accept_waveform_render(key, info, track)
        self._music_editor.apply_retuned_track(rendered, envelope)
        self._retune_applied_key = key
        self._box_player.refresh_reference(self._project, asset)

    def _apply_cached_retuned_track(self, token: int, asset, key, track) -> None:
        if (token != self._retune_token or asset is not self._edited_music
                or self._project is None):
            return
        self._music_editor.apply_retuned_track(track)
        # Le cache est déjà indexé par cette clé : retenir la clé évite de
        # reposer le même pixmap au relâchement du curseur.
        self._retune_applied_key = key
        self._box_player.refresh_reference(self._project, asset)

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

    def _seek_to_cue(self) -> None:
        """La lecture d'une musique entière part de la poignée de la règle, pas forcément du début."""
        asset = self._edited_music
        start = self._music_editor.start_seconds()
        if asset is not None and start is not None and self._box_player.previewing(asset):
            self._box_player.seek(start)

    def _on_sfx_selected(self, sfx: Sfx):
        self._show_music_editor(None)
        self._sfx_editor.load(self._project, sfx)
        self._sfx_editor.setVisible(True)
        self._sfx_editor.mix_panel.setVisible(True)
        self._center_filler.setVisible(False)
        self._sfx_insp.load(sfx, self._project)
        self._sfx_insp.refresh_weight(self._sound_weights().get(("sfx", sfx.name)))
        self._right_stack.setCurrentIndex(1)

    def _on_music_selected(self, music: Music):
        self._show_music_editor(music)
        self._music_insp.load(music, self._project)
        self._right_stack.setCurrentIndex(2)

    def _on_jingle_selected(self, jingle: Jingle):
        self._show_music_editor(jingle, sections=False)
        self._jingle_insp.load(jingle, self._project)
        self._right_stack.setCurrentWidget(self._jingle_insp)

    def _on_changed(self):
        self._library.refresh()
