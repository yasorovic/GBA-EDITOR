"""Les diagnostics de `codegen/rom_build.py` qu'aucun test ne déclenchait (la liste d'exemptions de la couverture : cf.
`tools/diagnostic_coverage_exemptions.json`) : outils qui ne répondent plus, ROM verrouillée, rapport de poids, ROM absente
au lancement de mGBA, chemin trop long, animation de fond impossible à fusionner.

Aucun outil ne tourne : on remplace l'appel qui échouerait et on lit ce que le journal en dit."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from codegen import BuildWorker, rom_build
from core.project import Project
from core.toolchain import Toolchain


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


class Journal:
    def __init__(self):
        self.diagnostics = []

    def says(self, level: str, fragment: str) -> bool:
        return any(d.level == level and fragment in d.message for d in self.diagnostics)


def _worker(project) -> tuple[BuildWorker, Journal]:
    worker = BuildWorker(project, Toolchain())
    journal = Journal()
    worker.on("diagnostic", journal.diagnostics.append)
    worker.on("log_line", lambda _line: None)
    worker.on("error_line", lambda _line: None)
    return worker, journal


def test_un_outil_qui_ne_repond_plus_est_arrete_et_dit(project, monkeypatch):
    def hang(cmd, **_kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(rom_build, "run_tool", hang)
    worker, journal = _worker(project)
    assert worker._capture_cmd(["make"], "[make]") is None
    assert journal.says("error", "no answer after 15 minutes: the tool was stopped")


def test_une_rom_verrouillee_par_un_emulateur_est_expliquee(project):
    worker, journal = _worker(project)
    proc = SimpleNamespace(returncode=2, stdout="", stderr="arm-none-eabi-objcopy: game.gba: Permission denied")
    assert worker._report_cmd(proc, "[make]") is False
    assert journal.says("error", "failed (code 2)")
    assert journal.says("error", "the ROM could not be overwritten: it is probably still open in an emulator")


def test_un_rapport_de_poids_qui_plante_est_un_avertissement_sans_annuler_le_build(project, monkeypatch):
    from codegen import rom_report

    def crash(*_args, **_kwargs):
        raise RuntimeError("nm is missing")

    monkeypatch.setattr(rom_report, "measure", crash)
    worker, journal = _worker(project)
    worker._step_rom_report(project, None)
    assert journal.says("warning", "report unavailable: nm is missing")


def test_une_rom_trop_grosse_ou_une_ewram_trop_juste_avertit(project, monkeypatch):
    from codegen import rom_report
    report = SimpleNamespace(over_capacity=True, ewram_tight=True, ewram_free=2048)
    monkeypatch.setattr(rom_report, "measure", lambda *_args, **_kwargs: report)
    monkeypatch.setattr(rom_report, "format_report", lambda _report: [])
    worker, journal = _worker(project)
    worker.on("rom_report", lambda _report: None)
    worker._step_rom_report(project, None)
    assert journal.says("warning", "the ROM exceeds the declared cartridge capacity")
    assert journal.says("warning", "only 2 KiB of EWRAM stay free after the link")


def test_une_rom_absente_arrete_le_lancement_de_mgba(project):
    worker, journal = _worker(project)
    assert not project.rom_path.exists()
    assert worker._step_launch_mgba(project) is False
    assert journal.says("error", "ROM missing")


def test_un_chemin_de_projet_trop_long_arrete_le_build_avant_tout_travail(project, monkeypatch):
    monkeypatch.setattr(rom_build, "path_too_long_message", lambda _project: "the project path is too long for the tools")
    worker, journal = _worker(project)
    verdict = []
    worker.on("finished", verdict.append)
    worker.run()
    assert journal.says("error", "the project path is too long for the tools")
    assert verdict == [False]


def test_une_animation_de_fond_impossible_a_fusionner_arrete_l_emission(project, monkeypatch):
    from codegen import bg_anim

    def refuse(_project, _scene, _skip=None, err=None):
        if err:                                               # l'émission l'appelle aussi sans rappels
            err("Waves", SimpleNamespace(col=3, row=4, host_name="Sky"), "256 colours do not fit")
        return []

    monkeypatch.setattr(bg_anim, "scene_animations", refuse)
    worker, journal = _worker(project)
    assert worker._emit_scene_animations(project, project.active_scene, None) is False
    assert journal.says("error", "'Waves' placed at (3, 4) tiles on 'Sky': 256 colours do not fit")


def test_un_fond_8bpp_avec_un_second_calque_avertit_que_les_couleurs_seront_fausses(project, monkeypatch):
    """Le build s'arrête juste après l'avertissement (la suite de l'émission du fond est remplacée par une panne) : ce que le
    test juge, c'est ce qui a été dit avant."""
    from PIL import Image
    from core.models.background import BackgroundAsset, BackgroundLayer

    sky = BackgroundAsset(name="sky", asset="sky.png", tileset=["0" * 64] * 4)
    sky.bpp = 8
    project.backgrounds.append(sky)
    Image.new("RGB", (8, 8)).save(project.background_image_path(sky, "sky"))
    project.active_scene.background_layers = [BackgroundLayer(background_name="sky", bg_slot=0),
                                              BackgroundLayer(background_name="sky", bg_slot=1)]
    worker, journal = _worker(project)
    monkeypatch.setattr(worker, "_bg_build_asset", lambda _p, ba: ba)

    def stop(*_args, **_kwargs):
        raise RuntimeError("stop here")

    monkeypatch.setattr(worker, "_bg_final_tilemap", stop)
    worker.run()
    assert journal.says("warning", "'sky' 8bpp takes the whole BG palette")
