"""Le rapport de diagnostic qu'on colle dans un compte rendu de bug.

Il doit tenir debout sans projet ni toolchain (l'éditeur démarre aussi dans cet
état), dire ce qui est cassé dans le projet ouvert, et ne jamais embarquer le
contenu du projet.
"""
from __future__ import annotations

from types import SimpleNamespace

from core import crash_log
from core.app_info import APP_NAME, APP_VERSION
from core.diagnostics import diagnostic_report
from core.project import Project


def test_rapport_sans_projet_ni_toolchain():
    report = diagnostic_report()

    assert report.startswith(f"{APP_NAME} — diagnostic")
    assert "(aucun projet ouvert)" in report
    assert "(toolchain non lue)" in report
    assert "Python :" in report and "système :" in report


def test_la_version_de_l_editeur_vient_de_la_source_unique():
    assert f"version de l'éditeur : {APP_VERSION}" in diagnostic_report()


def test_toolchain_manquante_est_nommee():
    toolchain = SimpleNamespace(
        devkitpro_path=None,
        check=lambda: {"grit": None, "make": "C:/dkp/make.exe"})

    report = diagnostic_report(toolchain=toolchain)

    assert "devkitPro : non configuré" in report
    assert "grit : INTROUVABLE" in report
    assert "make : C:/dkp/make.exe" in report


def test_projet_decrit_ses_fichiers_illisibles_sans_leur_contenu(tmp_path):
    root = tmp_path / "Jeu"
    project = Project.create(root, "Jeu")
    scene_file = project.scenes.path_of(project.scenes[0])
    scene_file.write_text('{"secret_du_joueur": "tronqu', encoding="utf-8")
    reopened = Project.open(root)

    report = diagnostic_report(project=reopened)

    assert "nom : Jeu" in report
    assert "fichiers illisibles : 1" in report
    assert "Scene_01.json" in report
    assert "secret_du_joueur" not in report


def test_la_fin_du_journal_est_reprise(tmp_path, monkeypatch):
    log = tmp_path / "crash.log"
    log.write_text("\n".join(f"ligne {i}" for i in range(100)), encoding="utf-8")
    monkeypatch.setattr(crash_log, "LOG_FILE", log)
    monkeypatch.setattr(crash_log, "NATIVE_LOG_FILE", tmp_path / "absent.log")

    report = diagnostic_report(journal_lines=5)

    assert "ligne 99" in report and "ligne 95" in report
    assert "ligne 94" not in report


def test_journal_absent_ou_vide_est_dit(tmp_path, monkeypatch):
    monkeypatch.setattr(crash_log, "LOG_FILE", tmp_path / "absent.log")
    monkeypatch.setattr(crash_log, "NATIVE_LOG_FILE", tmp_path / "absent2.log")

    assert "aucune panne enregistrée" in diagnostic_report()
