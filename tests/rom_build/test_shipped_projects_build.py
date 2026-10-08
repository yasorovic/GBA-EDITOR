"""Chaque projet livré s'ouvre et produit une VRAIE ROM.

« Livré » : les starters intégrés à l'éditeur (`editor/project_starters/`) et les démos
publiques (`Project Demo/*`). Rien n'est court-circuité sauf mGBA : le build passe par
`BuildWorker.run()` entier — validation, grit, transpilation, `make`, `arm-none-eabi-gcc`,
liaison — et exige une `rom.gba` non vide en sortie.

Les cas se découvrent : un nouveau starter ou un nouveau dossier de démo est testé sans
toucher ce fichier, et une démo qui ne builde plus ne peut pas être livrée en l'oubliant.
Chaque projet est copié sans son `build/` (un `build/` ancien masquerait un échec).

Lent (une compilation par projet) et dépendant de devkitPro : `pytest -m slow`. Sans devkitPro
le test saute, donc il ne prouve rien sur une machine qui n'en a pas — sauf quand la CI de release
pose `GBA_TESTS_REQUIRE_DEVKITPRO` : l'absence devient alors un ÉCHEC, car une release qui saute
ce contrôle en silence publierait des projets jamais buildés.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from codegen import BuildWorker
from core.project import Project
from core.project_starters import available_starters
from core.toolchain import DEVKITPRO_INCOMPLETE, DEVKITPRO_OK, Toolchain

DEMOS_DIR = Path(__file__).resolve().parents[2] / "Project Demo"

# Sous 1 Kio, ce n'est pas une ROM GBA : l'en-tête seul en prend 192 octets.
MIN_ROM_BYTES = 1024

pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def _devkitpro():
    toolchain = Toolchain()
    state = toolchain.devkitpro_state
    if state == DEVKITPRO_OK:
        return
    # Incomplet (outils manquants) et absent ne sont pas la même consigne : réinstaller
    # ou vérifier, plutôt que chercher le dossier.
    reason = (f"devkitPro est incomplet (manque : {', '.join(toolchain.devkitpro_missing_tools())})"
              if state == DEVKITPRO_INCOMPLETE else "devkitPro est introuvable")
    if os.environ.get("GBA_TESTS_REQUIRE_DEVKITPRO"):
        pytest.fail(f"{reason} alors que la CI l'exige : les projets livrés n'ont pas été buildés")
    pytest.skip(f"{reason} : le build ne peut pas tourner")


def _demos() -> list[Path]:
    if not DEMOS_DIR.is_dir():
        return []
    return sorted(d for d in DEMOS_DIR.iterdir() if d.is_dir() and any(d.glob("*.project")))


def _starters():
    for starter in available_starters():
        if starter.builtin:
            yield pytest.param(starter.id, id=f"starter-{starter.id}")


def _build(root: Path):
    """(réussi ?, diagnostics, ROM, sortie des outils) d'un build réel, mGBA exclu."""
    project = Project.open(root)
    worker = BuildWorker(project, Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict, tool_output = [], [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("error_line", tool_output.append)
    worker.on("finished", verdict.append)
    worker.run()
    return verdict[-1], diagnostics, project.rom_path, tool_output


def _assert_rom(root: Path, name: str):
    ok, diagnostics, rom, tool_output = _build(root)
    errors = [d.console_line() for d in diagnostics if d.level == "error"] + tool_output[-40:]
    assert ok is True and not errors, f"{name} ne builde pas :\n  " + "\n  ".join(errors or ["(aucune erreur nommée)"])
    assert rom.is_file(), f"{name} : le build réussit mais {rom.name} n'existe pas"
    assert rom.stat().st_size >= MIN_ROM_BYTES, f"{name} : {rom.name} fait {rom.stat().st_size} octets"


@pytest.fixture(autouse=True)
def _own_crash_log(tmp_path, monkeypatch):
    from core import crash_log
    monkeypatch.setattr(crash_log, "LOG_FILE", tmp_path / "crash.log")


def test_il_y_a_quelque_chose_a_tester():
    """Un dossier de démos déplacé ou renommé ne doit pas faire passer ce fichier à vide."""
    assert any(s.builtin for s in available_starters()), "aucun starter intégré"
    assert _demos(), f"aucune démo trouvée dans {DEMOS_DIR}"


@pytest.mark.parametrize("starter_id", list(_starters()))
def test_un_projet_neuf_depuis_le_starter_produit_une_rom(tmp_path, starter_id):
    project = Project.create(tmp_path / "Neuf", "Neuf", starter_id)
    project.save()
    _assert_rom(tmp_path / "Neuf", f"starter {starter_id}")


@pytest.mark.parametrize("demo", _demos(), ids=lambda d: d.name)
def test_une_demo_publique_s_ouvre_et_produit_une_rom(tmp_path, demo):
    root = tmp_path / demo.name
    shutil.copytree(demo, root, ignore=shutil.ignore_patterns("build"))
    _assert_rom(root, f"démo {demo.name}")
