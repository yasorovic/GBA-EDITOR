"""Les repères d'une musique traversent un VRAI build : le C généré compile, se lie, et la ROM sort.

Les quatre natures à la fois (action de SoundBox, action de JingleBox, effet direct, jingle direct), sur un module ET sur un
WAV (dont les repères coupent la piste en segments). Que le son parte au bon pas ne se prouve que sur console ; ce test tient
que le C continue de COMPILER avec la table qu'on attend, et que l'effet cité par un seul repère entre bien en ROM.

Lent et dépendant de devkitPro : `pytest -m slow`.
"""
from __future__ import annotations

import os
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audio"))

import module_fixtures as F                                            # noqa: E402
from asset_fixtures import create                                      # noqa: E402
from codegen import BuildWorker                                        # noqa: E402
from core.models.audio import (                                        # noqa: E402
    CUE_JINGLE, CUE_JINGLE_ACTION, CUE_SFX, CUE_SOUND_ACTION, UNIT_MS,
)
from core.models.sound_box import (                                    # noqa: E402
    ActionState, JingleBox, MusicBox, MusicState, MusicTransition, SoundBox, TRANSITION_FADE,
)
from core.project import Project                                       # noqa: E402
from core.project_starters import available_starters                   # noqa: E402
from core.toolchain import DEVKITPRO_INCOMPLETE, DEVKITPRO_OK, Toolchain  # noqa: E402

pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def _devkitpro():
    toolchain = Toolchain()
    state = toolchain.devkitpro_state
    if state == DEVKITPRO_OK:
        return
    reason = (f"devkitPro est incomplet (manque : {', '.join(toolchain.devkitpro_missing_tools())})"
              if state == DEVKITPRO_INCOMPLETE else "devkitPro est introuvable")
    if os.environ.get("GBA_TESTS_REQUIRE_DEVKITPRO"):
        pytest.fail(f"{reason} alors que la CI l'exige : le build des repères n'a pas été éprouvé")
    pytest.skip(f"{reason} : le build ne peut pas tourner")


@pytest.fixture(autouse=True)
def _own_crash_log(tmp_path, monkeypatch):
    from core import crash_log
    monkeypatch.setattr(crash_log, "LOG_FILE", tmp_path / "crash.log")


def _wav(path: Path, seconds: float = 3.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(44100 * seconds)) / 44100
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes((np.sin(2 * np.pi * 300 * t) * 0.5 * 32767).astype("<i2").tobytes())


def _project_with_cues(tmp_path) -> Project:
    starter = next(s.id for s in available_starters() if s.builtin)
    project = Project.create(tmp_path / "Neuf", "Neuf", starter)
    project.save()
    assets = project.user_library_dir
    (assets / "music").mkdir(parents=True, exist_ok=True)
    (assets / "music" / "Theme.it").write_bytes(F.make_it(orders=[0] * 8))
    _wav(assets / "music" / "Ambient.wav")
    (assets / "jingles").mkdir(parents=True, exist_ok=True)
    (assets / "jingles" / "Fanfare.it").write_bytes(F.make_it(orders=[0]))
    _wav(assets / "sfx" / "Step.wav", 0.3)
    _wav(assets / "sfx" / "Ping.wav", 0.3)

    step = create(project, "sfx", assets / "sfx" / "Step.wav")
    ping = create(project, "sfx", assets / "sfx" / "Ping.wav")
    fanfare = create(project, "jingles", assets / "jingles" / "Fanfare.it")

    # Les boîtes disent vers quoi pointent leurs actions ; `Ping` et `Fanfare` ne sont cités QUE par des repères directs.
    project.sound_boxes.append(SoundBox(name="sounds", actions=["step"], start="walk",
                                        states=[ActionState(name="walk", mapping={"step": step.name})]))
    project.jingle_boxes.append(JingleBox(name="jingles", actions=["win"], start="main",
                                          states=[ActionState(name="main", mapping={"win": fanfare.name})]))

    # Le jingle déclenche lui aussi des sons, en TEMPS (la ROM compte les images depuis `mmJingle`).
    fanfare.add_cue(0, CUE_SFX, ping.name)
    fanfare.add_cue(1000, CUE_SOUND_ACTION, "step")
    project.save_jingle(fanfare)

    theme = create(project, "music", assets / "music" / "Theme.it")
    theme.add_cue(0, CUE_SOUND_ACTION, "step")
    theme.add_cue(2, CUE_JINGLE_ACTION, "win")
    theme.add_cue(4, CUE_SFX, ping.name)
    theme.add_cue(6, CUE_JINGLE, fanfare.name)
    project.save_music(theme)

    ambient = create(project, "music", assets / "music" / "Ambient.wav")
    ambient.unit = UNIT_MS
    ambient.add_cue(1500, CUE_SFX, ping.name)
    project.save_music(ambient)

    # Une MusicBox cite le WAV : sans elle il ne serait référencé nulle part et la ROM le laisserait de côté.
    project.music_boxes.append(MusicBox(
        name="musics", start="theme",
        states=[MusicState(name="theme", music="Theme"), MusicState(name="calm", music="Ambient")],
        transitions=[MusicTransition(src="theme", dst="calm", trigger="calm", kind=TRANSITION_FADE)]))
    project.scenes[0].music = "Theme"
    project.save()
    return project


def _build(project: Project):
    worker = BuildWorker(project, Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict, tool_output = [], [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("error_line", tool_output.append)
    worker.on("finished", verdict.append)
    worker.run()
    return verdict[-1], diagnostics, tool_output


def test_des_reperes_produisent_une_rom(tmp_path):
    project = _project_with_cues(tmp_path)
    ok, diagnostics, tool_output = _build(project)
    errors = [d.console_line() for d in diagnostics if d.level == "error"] + tool_output[-40:]
    assert ok is True and not errors, "ne builde pas :\n  " + "\n  ".join(errors)
    assert project.rom_path.is_file() and project.rom_path.stat().st_size > 1024

    main_c = (project.src_dir / "main.c").read_text(encoding="utf-8")
    assert "music_cue_tick();" in main_c and "static void music_cue_tick(void){" in main_c
    # Le module : ses quatre repères, aux positions d'ordre du modèle.
    assert "{ MOD_THEME, 0, 0, 0, 0 }," in main_c and "{ MOD_THEME, 2, 1, 0, 0 }," in main_c
    assert "{ MOD_THEME, 4, 2, SFX_PING, 255 }," in main_c
    assert "{ MOD_THEME, 6, 3, MOD_FANFARE, 1024 }," in main_c
    # Le jingle : deux repères en images (1 s = 60 images à 59,73 Hz), jamais en ordres.
    assert "{ MOD_FANFARE, 0, 2, SFX_PING, 255 }," in main_c and "{ MOD_FANFARE, 60, 0, 0, 0 }," in main_c
    assert "music_cue_jingle_tick();" in main_c and "g_jingle_frame = 0;" in main_c
    # Le WAV est un module : son repère à 1,5 s est une position d'ordre du plan du build, pas une milliseconde.
    wav_rows = [line for line in main_c.splitlines() if line.strip().startswith("{ MOD_AMBIENT,") and "SFX_PING" in line]
    assert len(wav_rows) == 1
