"""Le placement des réserves du runtime, vérifié sur l'ELF LIÉE.

`test_runtime_memory_placement` relit `gba_engine.h` : il dit que l'attribut est écrit, pas que le lien l'a suivi. Un
`EWRAM_BSS` redéfini à vide, une section renommée, un script de lien changé passeraient. Ici le build tourne pour de
vrai et `nm` donne l'adresse de chaque réserve. Deux contrôles :

- chaque `EWRAM_BSS` de `gba_engine.h` que le lien a gardé tombe dans l'EWRAM, jamais dans l'IWRAM ;
- `malloc` n'est pas lié. Les tampons de maxmod sont statiques (cf. `sound_memory_lines`) ; un retour à
  `mmInitDefault` ramènerait le tas, donc une allocation au démarrage et l'IWRAM qu'elle prend.

Lent (deux compilations) et dépendant de devkitPro, comme `test_shipped_projects_build` : `pytest -m slow`.
"""
from __future__ import annotations

import os
import re
import wave
from pathlib import Path

import pytest

from codegen import BuildWorker
from codegen.rom_report import read_symbols
from core.project import Project
from core.project_starters import available_starters
from core.toolchain import DEVKITPRO_INCOMPLETE, DEVKITPRO_OK, Toolchain

pytestmark = pytest.mark.slow

MOTEUR = Path(__file__).resolve().parents[2] / "runtime" / "include" / "gba_engine.h"

EWRAM, EWRAM_END = 0x02000000, 0x02040000
IWRAM, IWRAM_END = 0x03000000, 0x03008000

# `static <type> <nom>[...] EWRAM_BSS;` : la déclaration que le chantier IWRAM a posée sur chaque réserve mesurée.
_DECLARATION = re.compile(
    r"^\s*static\s+(?:const\s+)?[A-Za-z_][\w ]*?\s+(\w+)\s*(?:\[[^;]*\])?\s*EWRAM_BSS\s*;", re.M)

# Sous ce nombre de réserves retrouvées dans l'ELF, le test ne prouve plus rien : une erreur de lecture de `nm`, un
# renommage en masse ou un starter devenu vide le feraient passer à vide.
MIN_RESERVES = 15


@pytest.fixture(scope="module", autouse=True)
def _devkitpro():
    toolchain = Toolchain()
    state = toolchain.devkitpro_state
    if state == DEVKITPRO_OK:
        return
    reason = (f"devkitPro est incomplet (manque : {', '.join(toolchain.devkitpro_missing_tools())})"
              if state == DEVKITPRO_INCOMPLETE else "devkitPro est introuvable")
    if os.environ.get("GBA_TESTS_REQUIRE_DEVKITPRO"):
        pytest.fail(f"{reason} alors que la CI l'exige : le placement n'a pas été vérifié sur l'ELF")
    pytest.skip(f"{reason} : le build ne peut pas tourner")


def _starter_id() -> str:
    starter = next(s for s in available_starters() if s.builtin)
    return starter.id


def _build(root: Path) -> Path:
    """Construit le projet et rend son `build/`. Échoue en nommant les erreurs : sans ELF, rien à vérifier."""
    project = Project.open(root)
    worker = BuildWorker(project, Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict, tool_output = [], [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("error_line", tool_output.append)
    worker.on("finished", verdict.append)
    worker.run()
    errors = [d.console_line() for d in diagnostics if d.level == "error"] + tool_output[-20:]
    assert verdict[-1] is True, f"{root.name} ne builde pas :\n  " + "\n  ".join(errors or ["(aucune erreur nommée)"])
    assert (project.build_dir / "rom.elf").is_file(), "le build réussit sans produire rom.elf"
    return project.build_dir


def _un_son(path: Path) -> None:
    """Le plus petit effet que mmutil accepte : sans asset audio, maxmod n'est pas référencé et le test du tas serait vide."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(bytes(2 * 800))


def _symbols(build_dir: Path) -> dict[str, tuple[int, int, str]]:
    nm = Toolchain().resolve_binutil("nm")
    assert nm is not None, "arm-none-eabi-nm manque alors que devkitPro est complet"
    symbols = read_symbols(nm, build_dir / "rom.elf")
    assert symbols, "nm n'a rien rendu sur rom.elf"
    return symbols


@pytest.fixture(scope="module")
def rom_muette(tmp_path_factory) -> dict[str, tuple[int, int, str]]:
    root = tmp_path_factory.mktemp("muette") / "Neuf"
    Project.create(root, "Neuf", _starter_id()).save()
    return _symbols(_build(root))


@pytest.fixture(scope="module")
def rom_sonore(tmp_path_factory) -> dict[str, tuple[int, int, str]]:
    """Un projet neuf plus un effet QUE LA SCÈNE JOUE : un son qu'aucun acteur ne nomme est écarté du soundbank
    (`resolve_sound_assets`), maxmod ne serait pas référencé et les deux contrôles ci-dessous passeraient à vide."""
    from core.models.components import SoundFxComponent

    from tests.asset_fixtures import create_now

    root = tmp_path_factory.mktemp("sonore") / "Neuf"
    Project.create(root, "Neuf", _starter_id()).save()
    project = Project.open(root)
    project.load_all_resources()
    _un_son(root / "assets" / "sfx" / "bip.wav")
    create_now(project, "sfx", root / "assets" / "sfx" / "bip.wav")
    acteur = project.scenes[0].actors[0]
    acteur.components = list(acteur.components) + [SoundFxComponent(sfx_name="bip", trigger="on_spawn")]
    project.save()
    return _symbols(_build(root))


def _zone(symbols: dict, nom: str) -> int:
    assert nom in symbols, f"{nom} n'est pas dans rom.elf"
    return symbols[nom][0]


def test_les_reserves_mesurees_du_moteur_sont_liees_en_ewram(rom_muette):
    """Les noms viennent du header lui-même : une réserve ajoutée demain est contrôlée sans toucher ce test.

    Une réserve qu'aucun starter n'utilise n'est pas dans l'ELF (le compilateur jette un statique mort) : on vérifie
    celles qui y sont, et qu'il y en a assez pour que le test dise quelque chose."""
    declarees = _DECLARATION.findall(MOTEUR.read_text(encoding="utf-8"))
    assert len(declarees) >= MIN_RESERVES, f"{len(declarees)} réserves EWRAM_BSS déclarées dans gba_engine.h"

    liees = {nom: rom_muette[nom][0] for nom in declarees if nom in rom_muette}
    assert len(liees) >= MIN_RESERVES, (
        f"seules {len(liees)} réserves sur {len(declarees)} sont dans rom.elf : "
        f"absentes {sorted(set(declarees) - set(liees))}")
    hors_ewram = {nom: hex(addr) for nom, addr in liees.items() if not EWRAM <= addr < EWRAM_END}
    assert not hors_ewram, f"réserves liées hors de l'EWRAM : {hors_ewram}"


def test_les_tampons_de_maxmod_sont_la_ou_le_build_les_a_voulus(rom_sonore):
    """Les canaux et la mémoire d'onde en EWRAM, le tampon de mixage en IWRAM (il est lu à chaque interruption son).

    C'est le partage que `sound_memory_lines` écrit ; seul le lien dit s'il a été suivi."""
    for nom in ("g_mm_module_channels", "g_mm_active_channels", "g_mm_mixing_channels", "g_mm_wave_memory"):
        addr = _zone(rom_sonore, nom)
        assert EWRAM <= addr < EWRAM_END, f"{nom} est à {hex(addr)}, hors de l'EWRAM"
    mixage = _zone(rom_sonore, "g_mm_mixing_memory")
    assert IWRAM <= mixage < IWRAM_END, f"g_mm_mixing_memory est à {hex(mixage)}, hors de l'IWRAM"


def test_le_tas_n_est_pas_lie(rom_sonore):
    """Le son est le seul besoin de tas qu'avait le runtime (`mmInitDefault`). Plus de `malloc` dans l'ELF : plus de tas,
    donc plus rien à épuiser ni à placer, et l'IWRAM qu'il prenait reste au jeu."""
    tas = sorted(nom for nom in rom_sonore
                 if nom in ("malloc", "free", "calloc", "realloc", "_malloc_r", "_free_r", "__malloc_lock"))
    assert not tas, f"le tas est lié malgré les tampons statiques : {tas}"
