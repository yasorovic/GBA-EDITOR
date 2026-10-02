"""Chemins de projet difficiles pour les outils de build Windows.

grit, mmutil et binutils sont des exécutables « ANSI » sans chemins longs : un
dossier de projet en japonais leur arrive en `?`, un chemin au-delà de 260
caractères les met en échec. Ces tests tiennent les pièces qui l'évitent, sans
devkitPro (le build de bout en bout, lui, est rejoué à la main : cf.
ALPHA_CHECKLIST, « Chemins Windows difficiles »).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from codegen.grit_conversion import relative_arg
from codegen.rom_build import (
    WINDOWS_PATH_LIMIT, BuildWorker, path_too_long_message)
from codegen import rom_report

windows_only = pytest.mark.skipif(os.name != "nt", reason="limite 260 de Windows")


def test_chemin_relatif_au_dossier_de_travail(tmp_path):
    cwd = tmp_path / "プロジェクト" / "build" / "grit_out"
    target = cwd / "_grit" / "sprite_hero"

    assert relative_arg(target, cwd) == os.path.join("_grit", "sprite_hero")
    # Aucun caractère non ASCII dans ce que l'outil reçoit.
    assert relative_arg(target, cwd).isascii()


@windows_only
def test_autre_lecteur_retombe_sur_le_chemin_absolu():
    assert relative_arg(Path("C:/a/b.png"), Path("E:/c")) == str(Path("C:/a/b.png"))


def test_binutils_tournent_dans_le_dossier_de_l_elf(tmp_path):
    """Un dossier hors page de code ne doit pas faire disparaître le rapport de
    poids : l'outil reçoit le dossier en cwd et le seul nom du fichier."""
    elf = tmp_path / "プロジェクト" / "rom.elf"
    elf.parent.mkdir()
    elf.write_bytes(b"")
    probe = "import os, sys; print(os.getcwd()); print(sys.argv[1])"

    out = rom_report._run(Path(sys.executable), ["-c", probe], elf)

    assert out is not None
    cwd_line, arg_line = out.splitlines()[:2]
    assert Path(cwd_line).name == "プロジェクト"
    assert arg_line == "rom.elf"


def test_sortie_d_outil_non_decodable_ne_tue_pas_le_build():
    """Octets invalides dans la page de code : avant, le thread de lecture de
    `subprocess` mourait et le build perdait toute la sortie de l'outil."""
    worker = BuildWorker(None, None)
    lines = []
    worker.on("log_line", lines.append)
    worker.on("error_line", lines.append)
    emit = r"import sys; sys.stdout.buffer.write(b'avant \x81\x8d apres\n')"

    assert worker._run_cmd([sys.executable, "-c", emit], "[t]") is True
    assert any("avant" in line and "apres" in line for line in lines)


def _projet_factice(root: Path, names=("hero",)):
    items = [SimpleNamespace(name=n) for n in names]
    return SimpleNamespace(
        build_dir=root / "build",
        sprites=items, backgrounds=[], scenes=[SimpleNamespace(name="Scene_01")],
        prefabs=[], settings=SimpleNamespace(name="Jeu"))


@windows_only
def test_chemin_court_n_est_pas_refuse():
    assert path_too_long_message(_projet_factice(Path("C:/Jeux/Jeu"))) is None


@windows_only
def test_chemin_trop_long_est_refuse_avec_un_message_clair():
    root = Path("C:/") / ("d" * 250) / "Jeu"

    message = path_too_long_message(_projet_factice(root))

    assert message is not None
    assert str(WINDOWS_PATH_LIMIT) in message
    assert "Déplacez le projet" in message


@windows_only
def test_un_nom_d_asset_tres_long_compte_dans_l_estimation():
    root = Path("C:/") / ("d" * 150) / "Jeu"

    assert path_too_long_message(_projet_factice(root)) is None
    assert path_too_long_message(_projet_factice(root, names=("n" * 40,))) is not None
