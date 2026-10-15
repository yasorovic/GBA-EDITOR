"""ui/sound_mixer/mix_faders.py — volume, tempo et hauteur d'une musique, en trois curseurs verticaux,
et ses deux fondus (en frames) dessous.

Comme sur une table de mixage : la valeur au-dessus (qu'on peut taper), le curseur, le nom dessous, le tout
sans couleur et à angles droits. Un double-clic remet le curseur à sa valeur neutre, et il s'y aimante. Le widget ne connaît pas la `Music` qu'il règle : il dit `changed(champ, valeur)`
à chaque cran, et c'est l'éditeur qui écrit le modèle (le modèle reste la source unique).

Tempo et hauteur ne valent pas pour toutes les pistes : un WAV les ignore (ses segments sont cadencés par les
lignes du module), un jingle n'applique que son volume. Un curseur grisé le dit dans son infobulle plutôt
que de rester muet.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QBoxLayout, QLabel, QLayout, QLineEdit, QSlider, QVBoxLayout, QHBoxLayout, QWidget

from core.models.audio import (
    FADE_MAX_FRAMES, PANNING_MAX, PITCH_MAX, PITCH_MIN, SFX_PITCH_MAX, SFX_PITCH_MIN, SFX_PITCH_VARIATION_MAX, TEMPO_MAX, TEMPO_MIN,
)
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.tooltip import tooltip

# (champ de la `Music`, libellé, infobulle, plancher, plafond, valeur neutre, lettre)
_FADERS = (
    ("volume", "sndpanel.volume", "sndedit.mix_volume_tip", 0, 100, 100, "V"),
    ("tempo", "sndpanel.tempo", "sndedit.mix_tempo_tip", TEMPO_MIN, TEMPO_MAX, 100, "T"),
    ("pitch", "sndpanel.pitch", "sndedit.mix_pitch_tip", PITCH_MIN, PITCH_MAX, 100, "P"),
)

# (champ de la `Music`, libellé, infobulle, lettres) — des frames, en curseurs horizontaux
_FADES = (
    ("fade_in", "sndpanel.fade_in", "sndpanel.fade_in_tip", "IN"),
    ("fade_out", "sndpanel.fade_out", "sndpanel.fade_out_tip", "OUT"),
)

# La table d'un EFFET : le même schéma (trois curseurs, deux fondus), d'autres réglages. La variation aléatoire de la hauteur
# a sa valeur neutre à zéro, une extrémité de la course : pas d'aimant, le bout de course la tient déjà.
SFX_FADERS = (
    ("volume", "sndpanel.volume", "sfxedit.mix_volume_tip", 0, 100, 100, "V"),
    ("pitch", "sndpanel.sfx_pitch", "sfxedit.mix_pitch_tip", SFX_PITCH_MIN, SFX_PITCH_MAX, 100, "P"),
    ("pitch_variation", "sndpanel.sfx_spread", "sfxedit.mix_variation_tip", 0, SFX_PITCH_VARIATION_MAX, 0, "VAR"),
)
SFX_FADES = (
    ("fade_in", "sfxedit.fade_in", "sfxedit.fade_in_tip", "IN"),
    ("fade_out", "sfxedit.fade", "sfxedit.fade_tip", "OUT"),
)

# Le panoramique d'un EFFET : un axe gauche–droite sous les curseurs, pas un cinquième curseur vertical (ce n'est pas un niveau, c'est une
# position). (champ, libellé, infobulle, lettres)
SFX_PAN = ("panning", "sndpanel.sfx_pan", "sfxedit.mix_pan_tip", "PAN")

# Les bornes de chaque champ, pour qui règle la musique autrement qu'avec ces curseurs (cf. waveform_view).
RANGES = {field: (low, high) for field, _caption, _tip, low, high, *_rest in _FADERS}

_FADER_HEIGHT = 104
_FADER_WIDTH = 38
_COLUMN_WIDTH = 50                 # la place d'une colonne, pour que « 135 % » tienne au-dessus de son curseur
_UNBOUNDED = 16777215              # QWIDGETSIZE_MAX
_SNAP_SHARE = 0.03                 # l'aimantage de la valeur neutre : cette part de la course, de chaque côté


class Fader(QSlider):
    """Un curseur de table de mixage, tout en angles droits : fond noir, rail, capuchon rectangulaire. Un
    double-clic revient à la valeur neutre, et le curseur s'y aimante quand on le tient près d'elle. Vertical,
    le niveau se remplit depuis le bas ; horizontal, depuis la gauche. Il peut changer de sens (cf. `MixFaders`)."""

    def __init__(self, low: int, high: int, neutral: int, orientation=Qt.Orientation.Vertical, parent=None):
        super().__init__(orientation, parent)
        self.setRange(low, high)
        self._neutral = neutral
        # Pas d'aimant quand la valeur neutre est une extrémité : le bout de course la tient déjà.
        self._snap = max(1, round((high - low) * _SNAP_SHARE)) if low < neutral < high else 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_sense(orientation)

    def set_sense(self, orientation) -> None:
        self.setOrientation(orientation)
        if orientation == Qt.Orientation.Vertical:
            self.setMinimumSize(_FADER_WIDTH, _FADER_HEIGHT)
            self.setMaximumSize(_FADER_WIDTH, _UNBOUNDED)
            kind, level, rest = "vertical", "add-page", "sub-page"
            groove, handle = "width:8px;", "height:12px; margin:0 -9px;"
        else:
            self.setMinimumSize(0, 22)
            self.setMaximumSize(_UNBOUNDED, 22)
            kind, level, rest = "horizontal", "sub-page", "add-page"
            groove, handle = "height:8px;", "width:12px; margin:-9px 0;"
        self.setStyleSheet(
            f"QSlider{{background:{C.BG_DEEP}; border:1px solid {C.BORDER_MID}; border-radius:0;}}"
            f"QSlider::groove:{kind}{{background:{C.BG_INPUT}; {groove} border-radius:0;"
            f"border:1px solid {C.BORDER_MID};}}"
            f"QSlider::{level}:{kind}{{background:{C.TEXT_DIM}; border-radius:0;}}"     # le niveau
            f"QSlider::{rest}:{kind}{{background:transparent;}}"
            f"QSlider::handle:{kind}{{background:{C.TEXT_NORM}; {handle}"
            f"border:1px solid {C.TEXT_HI}; border-radius:0;}}"
            f"QSlider::handle:{kind}:hover{{background:{C.TEXT_HI};}}"
            f"QSlider::handle:{kind}:pressed{{background:{C.ACCENT}; border-color:{C.ACCENT_HOVER};}}"
            f"QSlider::{level}:{kind}:disabled{{background:{C.BORDER_MID};}}"
            f"QSlider::handle:{kind}:disabled{{background:{C.TEXT_MUTED}; border-color:{C.TEXT_MUTED};}}")

    def mouseDoubleClickEvent(self, event):
        self.setValue(self._neutral)

    def mouseMoveEvent(self, event):
        """Tenu près de la valeur neutre, le curseur s'y accroche ; il faut s'en éloigner pour la quitter. La
        valeur intermédiaire n'est pas émise : le son ne la voit jamais."""
        if not self._snap or not self.isSliderDown():
            return super().mouseMoveEvent(event)
        before = self.value()
        self.blockSignals(True)
        super().mouseMoveEvent(event)
        if abs(self.value() - self._neutral) <= self._snap:
            self.setValue(self._neutral)
        self.blockSignals(False)
        if self.value() != before:
            self.valueChanged.emit(self.value())

    def paintEvent(self, event):
        """Ajoute un repère de valeur neutre sans surcharger le rail.

        Le repère permet de retrouver 100 % d'un coup d'œil ; le double-clic
        conserve le geste rapide pour y revenir.
        """
        super().paintEvent(event)
        if not self.isEnabled() or self.maximum() <= self.minimum():
            return
        ratio = (self._neutral - self.minimum()) / (self.maximum() - self.minimum())
        p = QPainter(self)
        p.setPen(QPen(QColor(C.TEXT_HI), 1))
        if self.orientation() == Qt.Orientation.Vertical:
            y = int(self.height() - 8 - ratio * max(1, self.height() - 16))
            p.drawLine(4, y, 9, y)
        else:
            x = int(8 + ratio * max(1, self.width() - 16))
            p.drawLine(x, 4, x, 9)
        p.end()


def _initial(text: str) -> QLabel:
    """La lettre (ou les lettres) qui nomme un curseur : en gras, sans couleur."""
    name = QLabel(text)
    name.setFont(QFont(T.UI, T.MD, QFont.Weight.Bold))
    name.setStyleSheet(f"color:{C.TEXT_BASE};")
    name.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return name


def _digits(text: str):
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def pan_text(value: int) -> str:
    """−40 → « L 40 », 0 → « C », 25 → « R 25 » : la position se lit sans avoir à connaître le signe."""
    return "C" if value == 0 else f"L {-value}" if value < 0 else f"R {value}"


def pan_value(text: str):
    """Le contraire de `pan_text` ; « -40 » et « 40 » se lisent aussi (le signe fait le côté). Illisible : None."""
    text = text.strip().upper()
    magnitude = _digits(text)
    if text.startswith("C") or magnitude == 0:
        return 0
    if magnitude is None:
        return None
    return -magnitude if text.startswith(("L", "-")) else magnitude


class PanFader(Fader):
    """L'axe du panoramique : couché, centré sur 0. Le niveau ne se remplit pas depuis la gauche, mais depuis le CENTRE
    jusqu'au capuchon — la distance au milieu est ce qu'on règle. Même rail, même double-clic, même aimant que les autres."""

    def __init__(self, parent=None):
        super().__init__(-PANNING_MAX, PANNING_MAX, 0, Qt.Orientation.Horizontal, parent)

    def set_sense(self, orientation) -> None:
        super().set_sense(Qt.Orientation.Horizontal)
        self.setStyleSheet(self.styleSheet() + f"QSlider::sub-page:horizontal{{background:transparent;}}")

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isEnabled() or self.value() == 0:
            return
        span = max(1, self.width() - 16)
        centre, here = (8 + span // 2), int(8 + (self.value() - self.minimum()) / (self.maximum() - self.minimum()) * span)
        p = QPainter(self)
        p.fillRect(min(centre, here), self.height() // 2 - 4, abs(here - centre), 8, QColor(C.TEXT_DIM))
        p.end()


def _axis_end(text: str) -> QLabel:
    end = QLabel(text)
    end.setFont(QFont(T.UI, T.SM))
    end.setStyleSheet(f"color:{C.TEXT_DIM};")
    return end


class _Readout(QLineEdit):
    """La valeur d'un curseur, dans un cadre d'afficheur ; on la tape à la main pour les valeurs que la souris
    atteint mal. Entrée l'applique (bornée à la course du curseur) ; un texte illisible est remplacé par la
    valeur courante."""

    def __init__(self, slider: Fader, unit: str, show=None, read=None):
        super().__init__()
        self._slider, self._unit = slider, unit
        self._show, self._read = show, read        # un axe se lit « L 40 » et se tape de même ; sinon : le nombre et son unité
        self.setFont(QFont(T.MONO, T.SM))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(0)
        self.setStyleSheet(
            f"QLineEdit{{color:{C.TEXT_HI}; background:{C.BG_DEEP}; border:1px solid {C.BORDER_MID};"
            f"border-radius:0; padding:1px 2px;}}"
            f"QLineEdit:focus{{border-color:{C.ACCENT};}}"
            f"QLineEdit:disabled{{color:{C.TEXT_MUTED};}}")
        self.editingFinished.connect(self._apply)

    def show_value(self, value: int) -> None:
        self.setText(self._show(value) if self._show else f"{value} {self._unit}")

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

    def _apply(self) -> None:
        typed = self._read(self.text()) if self._read else _digits(self.text())
        if typed is not None:
            self._slider.setValue(typed)              # bornée par le curseur lui-même
        self.show_value(self._slider.value())         # texte illisible, ou valeur bornée : on montre ce qui est
        self.clearFocus()


class _Cell(QWidget):
    """Un curseur et ses deux étiquettes : en colonne (la valeur au-dessus, le nom dessous) ou, couché,
    en ligne « IN ——— 93 fr »."""

    def __init__(self, readout: QLineEdit, slider: Fader, name: QLabel):
        super().__init__()
        self._parts = (readout, slider, name)
        self._box = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(4)
        self.set_vertical(True)

    def set_vertical(self, vertical: bool) -> None:
        readout, slider, name = self._parts
        while self._box.count():
            self._box.takeAt(0)
        slider.set_sense(Qt.Orientation.Vertical if vertical else Qt.Orientation.Horizontal)
        if vertical:
            self.setMinimumWidth(_COLUMN_WIDTH)
            for label_ in (readout, name):
                label_.setMinimumWidth(0)
                label_.setMaximumWidth(_UNBOUNDED)
            readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._box.setDirection(QBoxLayout.Direction.TopToBottom)
            self._box.addWidget(readout, 0, Qt.AlignmentFlag.AlignHCenter)
            self._box.addWidget(slider, 1, Qt.AlignmentFlag.AlignHCenter)
            self._box.addWidget(name, 0, Qt.AlignmentFlag.AlignHCenter)
        else:
            self.setMinimumWidth(0)
            name.setFixedWidth(34)
            readout.setFixedWidth(48)
            readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._box.setDirection(QBoxLayout.Direction.LeftToRight)
            self._box.addWidget(name)
            self._box.addWidget(slider, 1)
            self._box.addWidget(readout)


class MixFaders(QWidget):
    """Cinq curseurs verticaux côte à côte (par défaut ceux d'une musique : volume, tempo, hauteur, fondu d'entrée,
    fondu de sortie ; `SFX_FADERS` / `SFX_FADES` pour un effet). Quand la place manque, les deux fondus descendent
    sous les trois autres et se couchent à l'horizontale."""
    changed = pyqtSignal(str, int)         # (champ de l'asset, valeur) à chaque cran
    released = pyqtSignal()                # un curseur tenu vient d'être lâché

    def __init__(self, faders=_FADERS, fades=_FADES, pan=None, parent=None):
        super().__init__(parent)
        self._spec_faders, self._spec_fades, self._spec_pan = faders, fades, pan
        self._faders: dict[str, Fader] = {}
        self._readouts: dict[str, _Readout] = {}
        self._blocking = False
        self._wide: bool | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)   # la largeur mini est celle de TROIS colonnes
        self._upper = QHBoxLayout()
        self._upper.setSpacing(6)
        self._lower = QVBoxLayout()
        self._lower.setSpacing(6)
        root.addLayout(self._upper, 1)
        root.addLayout(self._lower)
        for field, caption, tip, low, high, neutral, letter in self._spec_faders:
            fader = Fader(low, high, neutral)
            fader.valueChanged.connect(lambda value, f=field: self._on_value(f, value))
            fader.sliderReleased.connect(self.released)
            readout = _Readout(fader, "%")
            readout.setToolTip(tooltip(title=label(caption), body=label("sndedit.mix_type_tip")))
            name = _initial(letter)
            name.setToolTip(tooltip(title=label(caption), body=label(tip)))
            self._upper.addWidget(_Cell(readout, fader, name))
            self._faders[field], self._readouts[field] = fader, readout
        # Les fondus : en frames (un fondu n'est pas un pourcentage). Mêmes curseurs, deux dispositions.
        self._fades: dict[str, Fader] = {}
        self._fade_readouts: dict[str, _Readout] = {}
        self._fade_cells: list[_Cell] = []
        for field, caption, tip, letters in self._spec_fades:
            slider = Fader(0, FADE_MAX_FRAMES, 0)
            slider.setToolTip(tooltip(title=label(caption), body=label(tip)))
            slider.valueChanged.connect(lambda value, f=field: self._on_fade(f, value))
            readout = _Readout(slider, "fr")
            readout.setToolTip(tooltip(title=label(caption), body=label("sndedit.mix_type_tip")))
            name = _initial(letters)
            name.setToolTip(tooltip(title=label(caption), body=label(tip)))
            self._fade_cells.append(_Cell(readout, slider, name))
            self._fades[field], self._fade_readouts[field] = slider, readout
        self._pan: PanFader | None = None
        if pan is not None:
            self._build_pan(root, *pan)
        self._arrange(True)

    def _build_pan(self, root: QVBoxLayout, field: str, caption: str, tip: str, letters: str) -> None:
        """L'axe du panoramique, sous les curseurs : « PAN  L ——|—— R  C » — la valeur à droite, comme celle d'un fondu couché."""
        self._pan = PanFader()
        self._pan.setToolTip(tooltip(title=label(caption), body=label(tip)))
        self._pan.valueChanged.connect(lambda value: self._on_value(field, value))
        self._pan.sliderReleased.connect(self.released)
        readout = _Readout(self._pan, "", pan_text, pan_value)
        readout.setToolTip(tooltip(title=label(caption), body=label("sndedit.mix_pan_type_tip")))
        readout.setFixedWidth(48)
        readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        name = _initial(letters)
        name.setFixedWidth(34)
        name.setToolTip(tooltip(title=label(caption), body=label(tip)))
        row = QHBoxLayout()
        row.setSpacing(4)
        for part in (name, _axis_end("L"), self._pan, _axis_end("R"), readout):
            row.addWidget(part, 1 if part is self._pan else 0)
        root.addLayout(row)
        self._faders[field], self._readouts[field] = self._pan, readout

    def _arrange(self, wide: bool) -> None:
        """Les fondus à côté des trois curseurs (`wide`), ou dessous, couchés."""
        if wide == self._wide:
            return
        self._wide = wide
        for cell in self._fade_cells:
            self._upper.removeWidget(cell)
            self._lower.removeWidget(cell)
            cell.set_vertical(wide)
            (self._upper if wide else self._lower).addWidget(cell)

    def minimumSizeHint(self) -> QSize:
        """Trois colonnes suffisent : les fondus se couchent dessous quand les cinq ne tiennent plus."""
        return QSize(_COLUMN_WIDTH * 3 + self._upper.spacing() * 2, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange(event.size().width() >= _COLUMN_WIDTH * 5 + self._upper.spacing() * 4)

    def set_fades(self, fade_in: int, fade_out: int) -> None:
        """Pose les fondus SANS rien émettre (l'onde vient de les régler, ou une musique vient de charger)."""
        self._blocking = True
        self._fades["fade_in"].setValue(fade_in)
        self._fades["fade_out"].setValue(fade_out)
        self._blocking = False

    def _on_fade(self, field: str, value: int) -> None:
        self._fade_readouts[field].show_value(value)
        if not self._blocking:
            self.changed.emit(field, value)

    def fader(self, field: str) -> Fader:
        """Un curseur vertical par son champ, ou l'axe du panoramique (`panning`)."""
        return self._faders[field]

    def fade(self, field: str) -> Fader:
        """Le curseur d'un fondu (`fade_in` ou `fade_out`)."""
        return self._fades[field]

    @property
    def held(self) -> bool:
        """Un curseur est tenu à la souris."""
        return any(fader.isSliderDown() for fader in self._faders.values())   # l'axe du panoramique compte aussi

    def load(self, music, *, tempo_pitch: bool, fades: bool, unavailable_key: str = "") -> None:
        """Pose les valeurs de `music` SANS rien émettre. `tempo_pitch` faux grise les deux derniers curseurs,
        et `unavailable_key` (un libellé) dit pourquoi dans leur infobulle. `fades` faux grise les fondus
        (un jingle n'en applique pas)."""
        self.set_fades(music.fade_in, music.fade_out)
        for field, slider in self._fades.items():
            slider.setEnabled(fades)
            self._fade_readouts[field].setEnabled(fades)
        self._blocking = True
        for field, caption, tip, _low, _high, *_rest in self._spec_faders:
            fader = self._faders[field]
            fader.setValue(int(getattr(music, field)))
            self._readouts[field].show_value(fader.value())
            enabled = field == "volume" or tempo_pitch
            fader.setEnabled(enabled)
            self._readouts[field].setEnabled(enabled)
            body = label(tip) if enabled else label(unavailable_key)
            fader.setToolTip(tooltip(title=label(caption), body=body))
        if self._pan is not None:
            field = self._spec_pan[0]
            self._pan.setValue(int(getattr(music, field, 0)))
            self._readouts[field].show_value(self._pan.value())
        self._blocking = False

    def _on_value(self, field: str, value: int) -> None:
        self._readouts[field].show_value(value)
        if not self._blocking:
            self.changed.emit(field, value)


def mix_panel(faders: MixFaders) -> QWidget:
    """Le panneau « Mix » d'un asset : son titre et ses curseurs, avec les marges de celui d'une musique (cf.
    `MusicEditor.mix_panel`), pour que l'écran Son monte l'un ou l'autre au même endroit de sa colonne de droite."""
    panel = QWidget()
    lay = QVBoxLayout(panel)
    lay.setContentsMargins(10, 8, 10, 8)
    lay.setSpacing(8)
    title = QLabel(label("sndedit.mix_title"))
    title.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
    title.setStyleSheet(f"color:{C.TEXT_HI};")
    lay.addWidget(title)
    lay.addWidget(faders)
    return panel
