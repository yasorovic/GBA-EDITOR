"""Renommer un acteur doit repointer les exports `actor_ref` qui le visaient.

Un export `actor_ref` se choisit dans l'inspecteur par un menu déroulant (cf.
`component_editors/script.py`), mais la valeur retenue est le NOM de l'acteur,
stocké dans `ScriptComponent.exports_values` — pas une référence vivante.
`rename_actor` réécrivait déjà les scripts Lua qui citaient l'ancien nom
(`rename_lua_refs`) ; il ne touchait pas cette autre forme de référence, le
même trou déjà refermé pour l'`id` d'un composant sprite
(`rename_sprite_id_refs`). Trouvé en discutant du récepteur direct
(ROADMAP v0.16, section « Ouvert »).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.scene import Scene, Actor
    from core.models.components import ScriptComponent

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)

    script_rel = "assets/scripts/chasseur.lua"
    script_path = p.asset_abs(script_rel)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        'exports = {\n'
        '    cible = { type = "actor_ref", default = "" },\n'
        '    label = { type = "string",    default = "" },\n'
        '}\n'
        'function on_update()\nend\n',
        encoding="utf-8",
    )

    canard = Actor(name="canard")
    chasseur = Actor(name="chasseur")
    chasseur.components.append(ScriptComponent(
        script=script_rel,
        exports_values={"cible": "canard", "label": "canard"},
    ))
    scene = Scene(name="Foret")
    scene.actors = [canard, chasseur]
    p.scenes.append(scene)

    return p, scene, canard, chasseur


def test_renommer_lacteur_vise_repointe_lexport_actor_ref(projet):
    p, scene, canard, chasseur = projet

    p.rename_actor(canard, "coincoin", scene=scene)

    comp = chasseur.components[0]
    assert comp.exports_values["cible"] == "coincoin"


def test_un_export_string_de_meme_valeur_nest_pas_touche(projet):
    """`label` est une chaîne LIBRE, pas un `actor_ref` : sa valeur ressemble à
    un nom d'acteur par coïncidence, elle ne doit pas suivre le renommage."""
    p, scene, canard, chasseur = projet

    p.rename_actor(canard, "coincoin", scene=scene)

    comp = chasseur.components[0]
    assert comp.exports_values["label"] == "canard"


def test_renommer_un_acteur_non_vise_ne_touche_rien(projet):
    p, scene, canard, chasseur = projet

    p.rename_actor(chasseur, "traqueur", scene=scene)

    assert chasseur.components[0].exports_values["cible"] == "canard"


def test_persiste_sur_le_disque(projet):
    p, scene, canard, chasseur = projet

    p.rename_actor(canard, "coincoin", scene=scene)

    on_disk = p.scenes._path(scene.name).read_text(encoding="utf-8")
    assert '"cible": "coincoin"' in on_disk
    assert '"label": "canard"' in on_disk


def test_le_compte_de_references_reecrites_inclut_lexport(projet):
    """`_notify_renamed` annonce `{script: n}` — le script qui ne portait
    qu'un export corrigé (aucune ligne Lua ne citait « canard ») doit quand
    même apparaître dans ce décompte, sinon l'auteur n'a aucun retour."""
    p, scene, canard, chasseur = projet
    events = []
    p.events.on("renamed", lambda *a: events.append(a))

    p.rename_actor(canard, "coincoin", scene=scene)

    assert len(events) == 1
    _label, _old, _new, refs, _n_texts, _n_regions = events[0]
    script_path = p.asset_abs("assets/scripts/chasseur.lua")
    assert refs.get(script_path) == 1
