"""L'option « physique de scène » : la clé du format, la projection que le build applique à une scène sans physique,
et les avertissements du validateur."""
from __future__ import annotations

import pytest

from codegen.runtime_codegen.physics.body import physics_body_mode, without_scene_physics
from core import validator
from core.models.components import (
    COLLISION_RESPONSE_BLOCK, ONE_WAY_OFF, CollisionShapeComponent, PhysicMaterialComponent, PhysicsBodyComponent,
    ScriptComponent)
from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from core.validator import ValidationContext


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


def _warnings(project: Project, scene: Scene) -> list[str]:
    ctx = ValidationContext(project)
    ctx.focus(scene)
    validator._check_scene_without_physics(ctx, scene)
    return [m.message for m in ctx._msgs if m.level == "warning"]


def test_une_nouvelle_scene_n_a_pas_de_physique():
    assert Scene(name="S").physics_enabled is False


def test_la_cle_s_ecrit_et_une_scene_sans_cle_garde_sa_physique():
    scene = Scene(name="S")
    assert Scene.from_dict(scene.to_dict()).physics_enabled is False
    scene.physics_enabled = True
    assert Scene.from_dict(scene.to_dict()).physics_enabled is True
    legacy = scene.to_dict()
    del legacy["physics_enabled"]
    assert Scene.from_dict(legacy).physics_enabled is True


def _physical_actor() -> Actor:
    actor = Actor(name="Crate")
    actor.components = [
        PhysicsBodyComponent(mode="RigidBody"),
        PhysicMaterialComponent(id="bouncy", restitution=0.5),
        CollisionShapeComponent(id="hit", tag="body", solid=True, response=COLLISION_RESPONSE_BLOCK,
                                one_way="up", material_id="bouncy"),
    ]
    return actor


def test_la_projection_retire_corps_et_materiau_et_garde_la_reponse():
    actor = _physical_actor()
    view = without_scene_physics(actor)
    assert view is not actor
    assert [type(c) for c in view.components] == [CollisionShapeComponent]
    shape = view.components[0]
    assert (shape.one_way, shape.material_id, shape.response) == (ONE_WAY_OFF, "", COLLISION_RESPONSE_BLOCK)
    # l'original ne change pas : la même scène peut être rebâtie avec la physique
    assert len(actor.components) == 3 and actor.components[2].one_way == "up"
    # la boîte solide donne l'ancien comportement Character : le déplacement contre la carte continue
    assert physics_body_mode(view) == "CharacterBody"


def test_la_projection_d_un_prefab_retire_la_physique_de_sa_racine_et_de_ses_parties():
    """Un prefab délègue `components` à son acteur racine (propriété en lecture seule) : la vue remplace cet acteur par
    une copie projetée. Avant, la projection écrivait `components` sur le prefab et le build d'une scène sans physique
    qui fait naître un prefab à corps s'arrêtait sur une AttributeError."""
    prefab = Prefab(name="Crate")
    prefab.actor.components = _physical_actor().components
    prefab.children = [_physical_actor()]
    view = without_scene_physics(prefab)
    assert view is not prefab and view.name == "Crate"
    assert [type(c) for c in view.components] == [CollisionShapeComponent]
    assert [type(c) for c in view.children[0].components] == [CollisionShapeComponent]
    # l'original ne change pas
    assert len(prefab.components) == 3 and len(prefab.children[0].components) == 3


def test_la_projection_rend_le_meme_objet_quand_il_n_y_a_rien_a_retirer():
    actor = Actor(name="Plain")
    actor.components = [CollisionShapeComponent(id="hit", tag="body")]
    assert without_scene_physics(actor) is actor


def test_une_scene_sans_physique_avertit_des_composants_ignores(project):
    scene = Scene(name="S")
    scene.actors = [_physical_actor()]
    found = _warnings(project, scene)
    assert any("PhysicsBody 'physics_body' is ignored" in m for m in found)
    assert any("PhysicMaterial 'bouncy' is ignored" in m for m in found)
    scene.physics_enabled = True
    assert _warnings(project, scene) == []


def test_une_scene_sans_physique_avertit_des_fonctions_lua_physiques(project):
    path = project.root / "assets" / "scripts" / "crate.lua"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("function on_crushed(obstacle)\nend\n", encoding="utf-8")
    actor = Actor(name="Crate")
    actor.components = [ScriptComponent(script="assets/scripts/crate.lua")]
    scene = Scene(name="S")
    scene.actors = [actor]
    found = _warnings(project, scene)
    assert any("assets/scripts/crate.lua" in m and "on_crushed" in m for m in found)
    scene.physics_enabled = True
    assert _warnings(project, scene) == []
