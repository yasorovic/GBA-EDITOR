"""Nom, auteur, version : UNE source (`core/app_info.py`), et tout le reste lui est
aligné — installateur, build Nuitka, workflow de release, libellés.

Ces tests ne vérifient pas les VALEURS (elles changent avec le produit) mais
l'ALIGNEMENT : un fichier qui recopierait à la main l'une des trois valeurs, ou
dont la recopie dériverait, fait échouer ici avant de faire échouer une release.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

from core.app_info import APP_AUTHOR, APP_NAME, APP_VERSION

REPO_DIR = Path(__file__).resolve().parent.parent
PACKAGING = REPO_DIR / "packaging"
LABELS = REPO_DIR / "editor" / "ui" / "common" / "labels"


def _nuitka_build():
    spec = importlib.util.spec_from_file_location(
        "nuitka_build_under_test", PACKAGING / "nuitka_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _nsi_defines() -> dict[str, str]:
    text = (PACKAGING / "windows" / "installer.nsi").read_text(encoding="utf-8")
    return dict(re.findall(r'^!define\s+(\w+)\s+"([^"]*)"', text, re.MULTILINE))


def test_la_version_suit_la_convention_x_y_z_etiquette():
    # X.Y.Z-alpha, X.Y.Z-beta, X.Y.Z-stable : trois chiffres, étiquette toujours
    # écrite (jamais de version « nue »). Cf. ROADMAP, « La numérotation d'une release ».
    assert re.fullmatch(r"\d+\.\d+\.\d+-(alpha|beta|stable)", APP_VERSION), APP_VERSION


@pytest.mark.parametrize("version", ["1.0", "1.0-alpha", "1.0.0", "1.0.0-rc1", "v1.0.0-alpha"])
def test_une_version_hors_convention_serait_refusee(version):
    assert not re.fullmatch(r"\d+\.\d+\.\d+-(alpha|beta|stable)", version)


def test_l_installateur_est_aligne_sur_la_source_unique():
    nsi = _nsi_defines()

    assert nsi["APP_NAME"] == APP_NAME
    assert nsi["APP_KEY"] == APP_NAME
    assert nsi["PUBLISHER"] == APP_AUTHOR
    assert nsi["APP_EXE"] == f"{APP_NAME}.exe"


def test_le_build_nuitka_lit_la_source_unique():
    build = _nuitka_build()

    assert build.APP_NAME == APP_NAME
    assert build.COMPANY == APP_AUTHOR
    command = " ".join(build.build_command(APP_VERSION, Path("out")))
    assert f"--product-name={APP_NAME}" in command
    assert f"--company-name={APP_AUTHOR}" in command


def test_un_tag_qui_diverge_de_la_version_du_depot_est_refuse(monkeypatch, capsys):
    build = _nuitka_build()
    monkeypatch.setattr(sys, "argv", ["nuitka_build.py", "--version", "v99.0", "--dry-run"])

    assert build.main() == 2
    assert "n'est pas celle du dépôt" in capsys.readouterr().err


def test_le_tag_du_depot_est_accepte(monkeypatch, capsys):
    build = _nuitka_build()
    monkeypatch.setattr(sys, "argv", ["nuitka_build.py", "--version", f"v{APP_VERSION}", "--dry-run"])

    assert build.main() == 0


def test_print_version_donne_la_version_du_depot(monkeypatch, capsys):
    build = _nuitka_build()
    monkeypatch.setattr(sys, "argv", ["nuitka_build.py", "--print-version"])

    assert build.main() == 0
    assert capsys.readouterr().out.strip() == APP_VERSION


def test_le_workflow_de_release_lit_la_version_du_depot():
    workflow = (REPO_DIR / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "--print-version" in workflow
    assert "0.0.0-dev" not in workflow          # plus de version inventée en CI


def test_sans_adresse_publique_le_produit_s_en_passe():
    """Pas d'adresse = pas de lien mort : ni modèles à télécharger, ni entrée de menu."""
    from core import project_templates
    from core.app_info import APP_DOCS_URL, APP_TEMPLATES_URL

    if not APP_TEMPLATES_URL:
        assert project_templates.TEMPLATES == []
    if not APP_DOCS_URL:
        assert 'if APP_DOCS_URL:' in (REPO_DIR / "editor" / "window.py").read_text(encoding="utf-8")


def test_le_manifeste_d_un_projet_porte_l_extension_project(tmp_path):
    from core.project import Project
    from core.project_paths import PROJECT_EXT

    Project.create(tmp_path / "Jeu", "Jeu")

    assert PROJECT_EXT == ".project"
    assert (tmp_path / "Jeu" / "Jeu.project").is_file()


def test_la_config_utilisateur_vit_sous_le_nom_du_produit():
    from core.toolchain import config_dir

    assert config_dir().name.lower() == APP_NAME.lower()


def test_les_modeles_pointent_vers_un_dossier_de_la_demo_qui_existe():
    """Un modèle renommé dans `Project Demo/` sans le registre = téléchargement qui échoue."""
    import pytest
    from core import project_templates

    if not (REPO_DIR / "Project Demo").is_dir():
        pytest.skip("`Project Demo/` n'est pas versionné : absent d'un clone neuf (CI)")
    for template in project_templates.TEMPLATES:
        assert (REPO_DIR / template.repo_subdir).is_dir(), template.repo_subdir
