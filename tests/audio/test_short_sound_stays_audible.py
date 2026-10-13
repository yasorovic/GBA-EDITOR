"""Un son COURT doit s'entendre en entier à l'aperçu.

Le deck tire loin devant la carte son : un effet de 0,15 s est tout entier produit dès le premier paquet, `deck.playing`
retombe aussitôt — et l'écran Son, qui arrête l'aperçu dès que le deck ne joue plus, fermait la carte son avant qu'on ait
entendu quoi que ce soit. Seuls les sons assez longs pour dépasser l'avance du deck passaient (`blade`, `bomb` oui ;
`break`, `bump`, `ball_roll` non). `BoxPlayer.sounding` suit désormais ce que la carte son a JOUÉ.
"""
import os
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from core.models.audio import Sfx
from core.project import Project
from ui.sound_mixer.box_playback import BoxPlayer, _AudioOutput, _DeckDevice


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _short_sfx(tmp_path, seconds=0.12):
    project = Project.create(tmp_path / "Jeu", "Jeu")
    src = project.assets_dir / "short.wav"
    src.parent.mkdir(parents=True, exist_ok=True)
    frames = int(8000 * seconds)
    with wave.open(str(src), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes((np.sin(np.linspace(0, 300, frames)) * 20000).astype("<i2").tobytes())
    return project, Sfx(name="short", asset=project.asset_rel(src))


def test_a_short_sound_is_still_sounding_until_the_sound_card_has_played_it(app, tmp_path):
    project, sfx = _short_sfx(tmp_path)
    player = BoxPlayer()
    # `preview` ouvrirait une vraie carte son (et son thread) : on lance le deck directement, comme `preview` le fait.
    player._deck.play(player._live_track(project, sfx), 1024, False, 0)
    output = _AudioOutput(player._deck)                           # la carte son, sans carte : on joue son rôle à la main
    output._device = _DeckDevice(player._deck)
    output.active = True
    player._output = output

    output._device.readData(4 * 4096)                              # un seul paquet tire TOUT le son, et du silence derrière
    assert not player._deck.playing                                # le deck a fini : c'est ce qui coupait l'aperçu
    assert output._device.sound_frames > 0

    output.queued_frames = output._device.pulled_frames            # rien n'a encore été joué
    assert player.sounding                                         # ... donc le son n'a pas fini de s'entendre

    output.queued_frames = output._device.pulled_frames - output._device.sound_frames // 2
    assert player.sounding                                         # à moitié joué : toujours

    output.queued_frames = output._device.pulled_frames - output._device.sound_frames
    assert not player.sounding                                     # tout joué : l'aperçu peut s'arrêter


def test_a_sound_that_never_started_is_not_sounding(app):
    player = BoxPlayer()
    assert not player.sounding
    output = _AudioOutput(player._deck)
    output._device = _DeckDevice(player._deck)
    output.active = True
    player._output = output
    assert not player.sounding                                     # rien tiré, rien à entendre
