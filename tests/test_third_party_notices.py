"""`THIRD-PARTY-NOTICES.md` couvre ce que l'éditeur redistribue.

Une notice manquante est un manquement de licence qu'on ne découvre qu'après la
publication. Ces tests ne lisent pas les licences : ils vérifient que chaque
dépendance DIRECTE et chaque police du Starter est NOMMÉE dans la page.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
NOTICES = (REPO_DIR / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements() -> list[str]:
    names = []
    for line in (REPO_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            names.append(re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0])
    return names


@pytest.mark.parametrize("package", _requirements())
def test_chaque_dependance_directe_a_sa_notice(package):
    assert _normalise(package) in _normalise(NOTICES), (
        f"« {package} » est dans requirements.txt mais pas dans THIRD-PARTY-NOTICES.md")


def test_freetype_est_credite_comme_l_exige_sa_licence():
    # La FTL exige une mention dans la documentation livrée avec le logiciel.
    assert "The FreeType Project" in NOTICES
    assert "freetype.org" in NOTICES


def _starter_license_files() -> list[Path]:
    return sorted((REPO_DIR / "editor" / "project_starters").rglob("licenses/*.txt"))


def test_le_starter_livre_des_notices_de_polices():
    assert _starter_license_files(), "le Starter ne livre plus de licences de polices"


@pytest.mark.parametrize("notice", _starter_license_files(), ids=lambda p: p.name)
def test_chaque_notice_de_police_du_starter_est_citee(notice):
    assert notice.name in NOTICES, f"{notice.name} est livrée avec le Starter mais pas citée"
