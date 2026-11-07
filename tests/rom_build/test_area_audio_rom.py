"""Un émetteur sonore d'Area traverse un VRAI build : le C généré compile, se lie, et l'effet que seul l'émetteur cite entre en ROM.

Lent et dépendant de devkitPro : `pytest -m slow`. Que le son soit entendu à la bonne distance ne se prouve que sur console ;
le pas C lui-même est exécuté par `tests/physics/test_area_audio.py`.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from asset_fixtures import create                                      # noqa: E402
from codegen import BuildWorker                                        # noqa: E402
from core.models.components import AudioEmitterComponent              # noqa: E402
from core.models.scene import Area                                     # noqa: E402
from core.project import Project                                       # noqa: E402
from core.toolchain import DEVKITPRO_OK, Toolchain                     # noqa: E402

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(Toolchain().devkitpro_state != DEVKITPRO_OK,
                       reason=f"devkitPro non prêt ({Toolchain().devkitpro_state})"),
]


def _wav(path: Path, seconds: float = 0.3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(22050 * seconds)) / 22050
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes((np.sin(2 * np.pi * 300 * t) * 0.5 * 32767).astype("<i2").tobytes())


def test_un_emetteur_sonore_se_compile_et_son_effet_entre_en_rom(tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    _wav(project.user_library_dir / "sfx" / "Wind.wav")
    wind = create(project, "sfx", project.user_library_dir / "sfx" / "Wind.wav")
    zone = Area(name="Breeze", x=40, y=40)
    zone.components.append(AudioEmitterComponent(sfx_name=wind.name, volume=80, falloff=48, panning=True))
    project.scenes[0].areas.append(zone)
    project.save()

    worker = BuildWorker(Project.open(project.root), Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()
    assert verdict == [True], [d.message for d in diagnostics if d.level == "error"]

    main_c = next((project.root / "build").rglob("main.c")).read_text(encoding="utf-8")
    assert "int g_snd_h[1] EWRAM_BSS;" in main_c
    assert "static const AudioEmitter _snd[1]={" in main_c and "{&g_areas[0],SFX_WIND," in main_c
    assert "audio_emitter_step(&_snd[_k],&g_snd_h[_k]);" in main_c
    assert "if(g_snd_h[_i]) sfx_stop(g_snd_h[_i]);" in main_c               # l'entrée de scène coupe les effets d'avant
    header = next((project.root / "build").rglob("runtime_api.h")).read_text(encoding="utf-8")
    assert "audio_emitter_step" in header and "typedef struct { Area* area;" in header
