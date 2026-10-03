"""Des fautes connues, injectées dans un vrai build, doivent ressortir dans le journal
(chantier « La fiabilité du journal de build », tranche 1).

Chaque cas est un défaut réel trouvé en cherchant pourquoi un `; ADFZ` compilait
« proprement » : le build ne disait rien parce qu'aucun chemin ne regardait le fichier fautif.
Le test passe par `BuildWorker.run()` — la validation, la transpilation, le verdict — et
remplace seulement `make` et mGBA, qui ne disent rien de la faute.

Un cas se lit : un script (ou un behavior, un prefab), un contenu, et ce que le journal doit
nommer — le fichier ET la ligne.
"""
from __future__ import annotations

import pytest

from codegen import BuildWorker
from core.models.components import ScriptComponent
from core.models.scene import Actor, Prefab
from core.project import Project
from core.toolchain import Toolchain

HANDLER_OK = "function on_update()\nend\n"


def _build(project: Project):
    """(réussi ?, lignes du journal, lignes d'erreur) d'un build dont make et mGBA sont court-circuités."""
    worker = BuildWorker(Project.open(project.root), Toolchain())
    worker._step_make = lambda _p: True
    worker._step_launch_mgba = lambda _p: True
    log, errors, verdict = [], [], []
    worker.on("log_line", log.append)
    worker.on("error_line", errors.append)
    # Un diagnostic se lit comme dans la console ; son niveau dit où il se range.
    worker.on("diagnostic", lambda d: (errors if d.level == "error" else log).append(d.console_line()))
    worker.on("finished", verdict.append)
    worker.run()
    return verdict[-1], log, errors


def _projet(tmp_path, *, actor_script=None, behavior=None, prefab_script=None, orphan=None):
    project = Project.create(tmp_path / "Game", "Game")
    scripts = project.scripts_dir
    scripts.mkdir(parents=True, exist_ok=True)
    scene = project.scenes[0]
    if actor_script is not None:
        (scripts / "Hit.lua").write_text(actor_script, encoding="utf-8")
        actor = Actor(name="A")
        actor.components = [ScriptComponent(script="assets/scripts/Hit.lua")]
        scene.actors.append(actor)
    if behavior is not None:
        project.scripts_behaviors_dir.mkdir(parents=True, exist_ok=True)
        (project.scripts_behaviors_dir / "ai.lua").write_text(behavior, encoding="utf-8")
    if prefab_script is not None:
        # Aucune instance déclarée dans la scène : le prefab n'est jamais compilé.
        (scripts / "Bullet.lua").write_text(prefab_script, encoding="utf-8")
        prefab = Prefab(name="Bullet")
        prefab.actor.components = [ScriptComponent(script="assets/scripts/Bullet.lua")]
        project.prefabs.append(prefab)
    if orphan is not None:
        (scripts / "Draft.lua").write_text(orphan, encoding="utf-8")
    project.save()
    return project


# ── Le contrôle : un projet sain ne fait pas de bruit ─────────────


def test_un_projet_sain_passe_sans_erreur(tmp_path):
    ok, _log, errors = _build(_projet(tmp_path, actor_script=HANDLER_OK))
    assert ok is True
    assert errors == []


# ── Les fautes : chacune doit nommer son fichier ET sa ligne ──────


@pytest.mark.parametrize("script, attendu", [
    # En tête de fichier : parsée puis jetée, sans un mot, avant le correctif.
    ("local vitesse = 2; ADFZ = 5\nfunction on_update()\nend\n", "Hit.lua:1: this statement is outside"),
    ("function on_update()\nend; ADFZ()\n",                       "Hit.lua:2: this statement is outside"),
    # Le cas d'origine : des lettres derrière un `;`.
    ("function on_update()\n  local x = 1; ADFZ\nend\n",         "Hit.lua:2: unexpected `ADFZ`"),
])
def test_une_faute_dans_un_script_d_acteur_est_dite(tmp_path, script, attendu):
    ok, _log, errors = _build(_projet(tmp_path, actor_script=script))
    assert ok is False
    assert any(attendu in e for e in errors), errors


def test_un_behavior_casse_bloque_le_build(tmp_path):
    ok, _log, errors = _build(_projet(
        tmp_path, behavior="local M = {}\nfunction M.update(actor)\n  actor.x = 1; ADFZ\nend\nreturn M\n"))
    assert ok is False
    assert any("ai.lua:3: unexpected `ADFZ`" in e for e in errors), errors


def test_un_prefab_sans_instance_est_quand_meme_lu(tmp_path):
    """Sauté avant même d'être parsé : sa faute ne sortait nulle part."""
    ok, _log, errors = _build(_projet(
        tmp_path, prefab_script="function on_update()\n  local x = 1; ADFZ\nend\n"))
    assert ok is False
    assert any("Bullet.lua:2: unexpected `ADFZ`" in e for e in errors), errors


def test_un_script_attache_a_rien_avertit_sans_bloquer(tmp_path):
    ok, log, errors = _build(_projet(
        tmp_path, orphan="function on_update()\n  local x = 1; ADFZ\nend\n"))
    assert ok is True
    assert errors == []
    assert any("Draft.lua:2" in line and "attached to nothing" in line for line in log), log
