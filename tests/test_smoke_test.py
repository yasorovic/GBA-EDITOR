"""`main.py --smoke-test` : le point d'entrée tel que la CI de release l'exécutera sur
le binaire livré. Lancé en SOUS-PROCESSUS, comme un utilisateur le lancerait.

Il garde aussi la fermeture ordonnée (`main._shutdown_qt`) : sans elle, le processus
plantait à la sortie (violation d'accès) 4 fois sur 6 sous Windows, APRÈS avoir écrit
un rapport « SMOKE OK » — donc avec un code de sortie non nul.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
MAIN = REPO_DIR / "editor" / "main.py"


def _lancer(rapport: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, str(MAIN), f"--smoke-test={rapport}"],
                          capture_output=True, text=True, errors="replace",
                          env=env, timeout=170)


def test_le_smoke_test_reussit_et_sort_proprement(tmp_path):
    rapport = tmp_path / "rapport.txt"

    proc = _lancer(rapport)
    texte = rapport.read_text(encoding="utf-8") if rapport.exists() else "(aucun rapport)"

    assert "SMOKE OK" in texte, texte
    assert proc.returncode == 0, f"code de sortie {proc.returncode} malgré le rapport :\n{texte}"


def test_le_rapport_dit_ce_qui_a_ete_verifie(tmp_path):
    rapport = tmp_path / "rapport.txt"
    _lancer(rapport)
    texte = rapport.read_text(encoding="utf-8")

    assert "projet créé et ouvert" in texte
    assert "validation du projet" in texte and "projet enregistré" in texte
    # chaque écran est visité, par son nom
    for ecran in ("Scenes", "Backgrounds", "Palettes", "Scripts"):
        assert f"écran {ecran}" in texte
    # les données embarquées sont contrôlées
    for donnee in ("licence de l'éditeur", "notices tierces", "runtime : Makefile", "starter Basic"):
        assert donnee in texte


def test_le_rapport_nomme_la_version_de_l_editeur(tmp_path):
    from core.app_info import APP_NAME, APP_VERSION

    rapport = tmp_path / "rapport.txt"
    _lancer(rapport)

    assert f"{APP_NAME} {APP_VERSION}" in rapport.read_text(encoding="utf-8")
