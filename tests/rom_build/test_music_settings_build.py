"""Les réglages d'une musique traversent un VRAI build : le C généré compile, se lie, et la ROM sort.

Rien n'est court-circuité sauf mGBA (cf. `test_shipped_projects_build`). Le comportement du C
sur console — la section qui boucle, les fondus, le tempo — a été mesuré sur ROM le 2026-10-11 ; ce test tient que ce C continue de COMPILER, avec la table qu'on
attend, et que le WAV est encapsulé avec sa boucle et son taux.

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
from core.models.audio import MusicSection, UNIT_MS                    # noqa: E402
from core.models.sound_box import (                                    # noqa: E402
    MusicBox, MusicState, MusicTransition, TRANSITION_FADE)
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
        pytest.fail(f"{reason} alors que la CI l'exige : le build des musiques n'a pas été éprouvé")
    pytest.skip(f"{reason} : le build ne peut pas tourner")


@pytest.fixture(autouse=True)
def _own_crash_log(tmp_path, monkeypatch):
    from core import crash_log
    monkeypatch.setattr(crash_log, "LOG_FILE", tmp_path / "crash.log")


def _wav(path: Path, seconds: float = 3.0) -> None:
    t = np.arange(int(44100 * seconds)) / 44100
    samples = (np.sin(2 * np.pi * 300 * t) * 0.5 * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(samples.tobytes())


def _project_with_settings(tmp_path) -> Project:
    starter = next(s.id for s in available_starters() if s.builtin)
    project = Project.create(tmp_path / "Neuf", "Neuf", starter)
    for folder in ((project.user_library_dir / "scripts"),):
        folder.mkdir(parents=True, exist_ok=True)
    project.save()
    music = project.user_library_dir / "music"
    music.mkdir(parents=True, exist_ok=True)
    (music / "Theme.it").write_bytes(F.make_it(orders=[0] * 8))
    _wav(music / "Ambient.wav")

    theme = create(project, "music", music / "Theme.it")
    theme.sections = [MusicSection("Intro", start=0, end=2),
                      MusicSection("Main", start=2, end=6, loop=True)]
    theme.loop_section = "Main"
    theme.tempo, theme.pitch, theme.fade_in, theme.fade_out = 120, 110, 30, 60
    project.save_music(theme)

    ambient = create(project, "music", music / "Ambient.wav")
    ambient.unit = UNIT_MS
    ambient.sections = [MusicSection("Zone", start=500, end=2500, loop=True)]
    ambient.loop_section = "Zone"
    ambient.sample_rate = 11025
    project.save_music(ambient)

    # Une MusicBox cite les deux : sans elle, le WAV ne serait référencé nulle part et la
    # ROM le laisserait de côté.
    project.music_boxes.append(MusicBox(
        name="musics", start="theme",
        states=[MusicState(name="theme", music="Theme"), MusicState(name="calm", music="Ambient")],
        transitions=[MusicTransition(src="theme", dst="calm", trigger="calm", kind=TRANSITION_FADE)]))
    project.scenes[0].music = "Theme"

    # Un script qui surcharge les réglages à l'appel : les six appels doivent compiler ET se lier.
    (project.user_library_dir / "scripts").mkdir(parents=True, exist_ok=True)
    ((project.user_library_dir / "scripts") / "Level.lua").write_text(
        'function on_update()\n'
        '  music:set_tempo(150)\n'
        '  music:set_pitch(120)\n'
        '  music:fade_in("Theme", 90)\n'
        '  music:fade_out(90)\n'
        '  music:set_section("Main")\n'
        '  music:leave_loop()\n'
        'end\n', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/Level.lua"
    project.save()
    return project


def _build(project: Project):
    worker = BuildWorker(project, Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict, tool_output, logs = [], [], [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("error_line", tool_output.append)
    worker.on("log_line", logs.append)
    worker.on("finished", verdict.append)
    worker.run()
    return verdict[-1], diagnostics, tool_output, logs


def test_des_musiques_reglees_produisent_une_rom(tmp_path):
    project = _project_with_settings(tmp_path)
    ok, diagnostics, tool_output, logs = _build(project)
    errors = [d.console_line() for d in diagnostics if d.level == "error"] + tool_output[-40:]
    assert ok is True and not errors, "ne builde pas :\n  " + "\n  ".join(errors)
    assert project.rom_path.is_file() and project.rom_path.stat().st_size > 1024

    # La table : une ligne pour le morceau réglé, et une pour le WAV — qui est un module comme lui : sa
    # section « Zone » (500-2500 ms) est la plage d'ordres [1, 2) du module que le build a écrit.
    main_c = (project.src_dir / "main.c").read_text(encoding="utf-8")
    assert "[MOD_THEME] = { 2, 6, 1229, 1126, 30, 60 }" in main_c
    assert "[MOD_AMBIENT] = { 1, 2, 0, 0, 0, 0 }" in main_c
    assert "void music_play(int id, int loop, int volume){" in main_c
    assert "music_loop_tick();" in main_c
    # Le script, lui, appelle les six surcharges, et la table de main.c porte la section citée.
    sources = "\n".join(f.read_text(encoding="utf-8", errors="replace")
                        for f in project.src_dir.glob("*.c"))
    assert "music_set_section(MSEC_MAIN)" in sources and "music_leave_loop()" in sources
    # Rangs triés : Intro = 0, Main = 1, Zone = 2 — les mêmes que les `#define MSEC_*` du script.
    assert "{ MOD_THEME, 0, 0, 2 }" in main_c and "{ MOD_THEME, 1, 2, 6 }" in main_c
    assert "{ MOD_AMBIENT, 2, 1, 2 }" in main_c
    assert "#define MSEC_INTRO 0" in sources and "#define MSEC_MAIN 1" in sources and "#define MSEC_ZONE 2" in sources

    # Le WAV : encapsulé en module avec ses sections et son taux, et dit dans le journal.
    assert any("1 section(s), 11025 Hz" in line for line in logs)
    module = project.build_dir / "music" / "Ambient.xm"
    assert module.is_file()
    # 3 s à 11 025 Hz, TOUTE la piste (ce qui suit la section est son outro) : un échantillon par segment.
    assert 2.9 * 11025 < module.stat().st_size < 3.0 * 11025 + 4000


def test_un_jingle_module_coupe_aux_ordres_produit_une_rom(tmp_path):
    """La plage d'ordres d'un jingle en module : le build écrit le module COUPÉ dans `build/music/`, mmutil l'accepte, et la ROM
    sort. Le fichier de `assets/` n'est jamais réécrit."""
    from core.engine_emulation.module_model import ORDER_END, load_module
    starter = next(s.id for s in available_starters() if s.builtin)
    project = Project.create(tmp_path / "Neuf", "Neuf", starter)
    for folder in ((project.user_library_dir / "scripts"),):
        folder.mkdir(parents=True, exist_ok=True)
    project.save()
    folder = project.user_library_dir / "jingles"
    folder.mkdir(parents=True, exist_ok=True)
    source = F.make_it(orders=[0] * 8)
    (folder / "Fanfare.it").write_bytes(source)
    fanfare = create(project, "jingles", folder / "Fanfare.it")
    fanfare.order_start, fanfare.order_end = 2, 6
    fanfare.music_policy = "duck"
    project.save_jingle(fanfare)
    (project.user_library_dir / "scripts").mkdir(parents=True, exist_ok=True)
    ((project.user_library_dir / "scripts") / "Level.lua").write_text(
        'function on_update()\n  music:jingle("Fanfare")\nend\n', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/Level.lua"
    project.save()

    ok, diagnostics, tool_output, logs = _build(project)

    errors = [d.console_line() for d in diagnostics if d.level == "error"] + tool_output[-40:]
    assert ok is True and not errors, "ne builde pas :\n  " + "\n  ".join(errors)
    assert project.rom_path.is_file()
    assert any("cut to orders 2–6" in line for line in logs)
    cut = project.build_dir / "music" / "Fanfare.it"
    assert cut.is_file() and load_module(cut).order == [0, 0, 0, 0] + [ORDER_END] * 4
    assert (folder / "Fanfare.it").read_bytes() == source
    sources = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in project.src_dir.glob("*.c"))
    assert "music_jingle(MUSIC_FANFARE" in sources and ", 1, 307, 30)" in sources     # la politique « baisser » voyage avec l'appel


def _project_with_cut_jingle(tmp_path, **fields) -> Project:
    starter = next(s.id for s in available_starters() if s.builtin)
    project = Project.create(tmp_path / "Neuf", "Neuf", starter)
    for folder in ((project.user_library_dir / "scripts"),):
        folder.mkdir(parents=True, exist_ok=True)
    project.save()
    folder = project.user_library_dir / "jingles"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Fanfare.it").write_bytes(F.make_it(orders=[0] * 4))
    fanfare = create(project, "jingles", folder / "Fanfare.it")
    for name, value in fields.items():
        setattr(fanfare, name, value)
    project.save_jingle(fanfare)
    (project.user_library_dir / "scripts").mkdir(parents=True, exist_ok=True)
    ((project.user_library_dir / "scripts") / "Level.lua").write_text('function on_update()\n  music:jingle("Fanfare")\nend\n', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/Level.lua"
    project.save()
    return project


def test_une_plage_d_ordres_hors_du_module_arrete_le_build_en_le_disant(tmp_path):
    """Le validateur la nomme avant tout : pas une ROM sans le jingle."""
    project = _project_with_cut_jingle(tmp_path, order_start=9)

    ok, diagnostics, _tool_output, _logs = _build(project)

    assert ok is False
    assert any("Fanfare" in d.console_line() and "past the last order" in d.console_line() for d in diagnostics)


def test_une_coupe_qui_echoue_au_build_est_une_erreur_nommee(tmp_path, monkeypatch):
    """Ce que le validateur ne voit pas (un module abîmé que la coupe refuse) s'arrête au build, avec le nom du jingle."""
    import codegen.grit_conversion as conversion
    project = _project_with_cut_jingle(tmp_path, order_start=1)
    monkeypatch.setattr(conversion, "cut_orders", lambda *_args: (_ for _ in ()).throw(ValueError("boom")))

    ok, diagnostics, _tool_output, _logs = _build(project)

    assert ok is False
    assert any("Fanfare" in d.console_line() and "boom" in d.console_line() for d in diagnostics)
