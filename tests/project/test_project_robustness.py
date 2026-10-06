"""Ouverture d'un projet abîmé ou trop récent : un message clair, jamais une
trace brute, et aucun fichier de l'utilisateur modifié.

Cas couverts : manifeste illisible, sidecar d'asset illisible, projet écrit par
un format plus récent, version de format écrite à la sauvegarde.
"""
from __future__ import annotations

import json

import pytest

from core.project import Project
from core.project_paths import (
    PROJECT_FORMAT_VERSION, ProjectFileError, ProjectManifestError, find_manifest)


def _manifest(root):
    return find_manifest(root)


def test_manifeste_tronque_donne_une_erreur_de_projet(tmp_path):
    root = tmp_path / "Jeu"
    Project.create(root, "Jeu")
    manifest = _manifest(root)
    manifest.write_text('{"start_scene": "Scene_0', encoding="utf-8")   # JSON coupé

    with pytest.raises(ProjectFileError) as err:
        Project.open(root)

    assert "unreadable" in str(err.value)
    assert isinstance(err.value, ProjectManifestError)    # déjà attrapée par l'UI
    assert manifest.read_text(encoding="utf-8") == '{"start_scene": "Scene_0'


def test_manifeste_en_encodage_invalide_donne_une_erreur_de_projet(tmp_path):
    root = tmp_path / "Jeu"
    Project.create(root, "Jeu")
    _manifest(root).write_bytes(b"\xff\xfe\x00 pas de l'utf-8")

    with pytest.raises(ProjectFileError):
        Project.open(root)


def test_sidecar_illisible_est_signale_et_laisse_intact(tmp_path):
    root = tmp_path / "Jeu"
    project = Project.create(root, "Jeu")
    scene_file = project.scenes.path_of(project.scenes[0])
    scene_file.write_text("{ pas du json", encoding="utf-8")

    reopened = Project.open(root)

    assert any(scene_file.name in warning for warning in reopened.load_warnings)
    assert scene_file.read_text(encoding="utf-8") == "{ pas du json"


def test_projet_d_un_format_plus_recent_est_refuse_sans_rien_modifier(tmp_path):
    root = tmp_path / "Jeu"
    Project.create(root, "Jeu")
    manifest = _manifest(root)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["format_version"] = PROJECT_FORMAT_VERSION + 1
    text = json.dumps(data)
    manifest.write_text(text, encoding="utf-8")

    with pytest.raises(ProjectFileError) as err:
        Project.open(root)

    assert "newer version" in str(err.value)
    assert manifest.read_text(encoding="utf-8") == text


def test_la_sauvegarde_ecrit_la_version_de_format(tmp_path):
    root = tmp_path / "Jeu"
    Project.create(root, "Jeu")

    data = json.loads(_manifest(root).read_text(encoding="utf-8"))

    assert data["format_version"] == PROJECT_FORMAT_VERSION


def test_projet_sans_version_de_format_s_ouvre(tmp_path):
    root = tmp_path / "Jeu"
    Project.create(root, "Jeu")
    manifest = _manifest(root)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    del data["format_version"]                      # projet d'avant son introduction
    manifest.write_text(json.dumps(data), encoding="utf-8")

    assert Project.open(root).settings.name == "Jeu"
