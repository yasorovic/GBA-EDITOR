"""Diagnostics de la tranche 5 des grilles de valeurs."""
from __future__ import annotations

from core import validator
from core.models.grid import Grid, GridValue
from core.project import Project
from core.validator import ValidationContext
from scripting.refactor import iter_grid_refs


def _project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


def _messages(project: Project) -> list[str]:
    ctx = ValidationContext(project)
    validator._check_scene_grids(ctx)
    return [message.message for message in ctx.warnings]


def _script(project: Project, name: str, source: str) -> str:
    path = project.user_library_dir / "scripts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path.relative_to(project.root).as_posix()


def test_une_grille_trop_courte_le_dit(tmp_path):
    project = _project(tmp_path)
    project.active_scene.grids.append(Grid(name="Terrain", step=16, cells=[[0]]))

    assert any("smaller than scene" in message for message in _messages(project))


def test_une_valeur_peinte_sans_nom_le_dit(tmp_path):
    project = _project(tmp_path)
    project.active_scene.grids.append(Grid(
        name="Terrain", cells=[[7]], values=[GridValue(value=7, name="")]))

    assert any("painted value 7 has no name" in message for message in _messages(project))


def test_une_grille_lue_directement_n_est_pas_dite_inutilisee(tmp_path):
    project = _project(tmp_path)
    project.active_scene.grids.append(Grid(name="Terrain", cells=[[0]]))
    project.active_scene.script = _script(
        project, "Scene.lua", "function on_update()\n  local value = data.grid.Terrain:at(0, 0)\nend\n")

    assert not any("never read" in message for message in _messages(project))


def test_une_grille_lue_par_un_behavior_n_est_pas_dite_inutilisee(tmp_path):
    project = _project(tmp_path)
    project.active_scene.grids.append(Grid(name="Terrain", cells=[[0]]))
    _script(project, "Terrain.lua", "-- @behavior\nlocal M = {}\nfunction M.update()\n"
            "  local value = data.grid.Terrain:at(0, 0)\nend\nreturn M\n")
    project.active_scene.script = _script(
        project, "Scene.lua", "local terrain = require(\"behaviors/Terrain\")\n"
        "function on_update()\nend\n")

    assert not any("never read" in message for message in _messages(project))


def test_un_commentaire_ou_une_chaine_ne_compte_pas_comme_lecture(tmp_path):
    project = _project(tmp_path)
    project.active_scene.grids.append(Grid(name="Terrain", cells=[[0]]))
    project.active_scene.script = _script(
        project, "Scene.lua", "-- data.grid.Terrain:at(0, 0)\n"
        "function on_update()\n  local text = \"data.grid.Terrain\"\nend\n")

    assert any("never read" in message for message in _messages(project))


def test_iter_grid_refs_ne_prend_que_les_acces_structurels():
    refs = list(iter_grid_refs(
        "-- data.grid.Faux\nlocal text = 'data.grid.Faux'\n"
        "local value = data.grid.Terrain:at(0, 0)\n"))

    assert [(ref.name, ref.line) for ref in refs] == [("Terrain", 3)]
