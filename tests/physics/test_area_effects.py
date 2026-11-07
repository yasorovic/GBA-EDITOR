"""Les effets de zone d'une Area : le modèle (bornes, sérialisation) et le C émis par le pas de mouvement."""
from __future__ import annotations

import pytest

from codegen.runtime_codegen.physics.areas import effect_areas, effect_table_lines, effects_affect_characters
from codegen.runtime_codegen.physics.motion import physics_motion_lines
from core.models.components import (
    PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID, CollisionShapeComponent, ForceFieldComponent,
    GravityOverrideComponent, PhysicsBodyComponent, components_from_list, components_to_list,
)
from core.models.settings import ProjectSettings
from core.models.scene import Actor, Area, Scene


def _settings():
    return ProjectSettings()


def _body(name, mode, **fields):
    return Actor(name=name, components=[CollisionShapeComponent(id="body", w=8, h=8, solid=True),
                                        PhysicsBodyComponent(mode=mode, **fields)])


def _scene(*components, actors=()):
    area = Area(name="Zone")
    area.components += list(components)
    return Scene(name="S", areas=[area], actors=list(actors))


def _motion(tmp_path, scene, actors):
    """Le pas de mouvement émis pour une vraie scène de ces acteurs posés (types 1, 2, ...)."""
    from codegen.oam_alloc import scene_oam_layout
    from core.project import Project
    p = Project(tmp_path)
    p.scenes.items = [scene]
    return "\n".join(physics_motion_lines(scene, _settings(), [(a, None) for a in actors], [], False,
                                          scene_oam_layout(p, scene)))


@pytest.mark.parametrize("kind, field, value", [
    (GravityOverrideComponent, "gravity_y", 9.0), (ForceFieldComponent, "force_x", -9.0),
    (ForceFieldComponent, "turbulence", -0.1), (ForceFieldComponent, "buoyancy", 4.5), (ForceFieldComponent, "drag", 1.5),
])
def test_les_bornes_des_composants_d_effet(kind, field, value):
    with pytest.raises(ValueError):
        kind(**{field: value})


def test_les_composants_d_effet_font_l_aller_retour_dans_une_area():
    scene = _scene(GravityOverrideComponent(gravity_y=0.5), ForceFieldComponent(force_x=0.25, drag=0.5, affects_characters=True))
    again = Area.from_dict(scene.areas[0].to_dict())
    assert again.effect(GravityOverrideComponent).gravity_y == 0.5
    assert again.effect(ForceFieldComponent).affects_characters is True
    assert components_from_list(components_to_list(again.components)) == again.components


def test_une_area_sans_effet_ne_change_pas_le_c_emis(tmp_path):
    rigid = _body("Ball", PHYSICS_BODY_RIGID)
    assert "area_effects_apply" not in _motion(tmp_path / "a", Scene(name="S", actors=[rigid]), [rigid])
    assert "area_effects_apply" not in _motion(tmp_path / "b", _scene(actors=[rigid]), [rigid])   # une Area, mais sans effet


def test_une_zone_inactive_ou_sans_forme_n_est_pas_emise():
    scene = _scene(ForceFieldComponent(force_x=1.0, active=False))
    assert effect_areas(scene) == []
    scene = _scene(ForceFieldComponent(force_x=1.0))
    scene.areas[0].components = [c for c in scene.areas[0].components if not isinstance(c, CollisionShapeComponent)]
    assert effect_areas(scene) == []


def test_la_table_d_effets_est_cuite_en_q8():
    scene = _scene(GravityOverrideComponent(gravity_x=0.0, gravity_y=0.25),
                   ForceFieldComponent(force_x=1.0, force_y=-0.5, turbulence=0.5, buoyancy=1.0, drag=0.25))
    text = "\n".join(effect_table_lines(scene))
    assert "{&g_areas[0],0,64,256,-128,256,128,192,AREAFX_GRAVITY}" in text


def test_rigid_et_kinematic_subissent_la_zone_le_personnage_seulement_sur_option(tmp_path):
    rigid, kin = _body("Ball", PHYSICS_BODY_RIGID), _body("Plank", PHYSICS_BODY_KINEMATIC)
    hero = _body("Hero", PHYSICS_BODY_CHARACTER)
    scene = _scene(ForceFieldComponent(force_x=1.0), actors=[rigid, kin, hero])
    text = _motion(tmp_path / "a", scene, [rigid, kin, hero])
    assert "static const u8 _fx_rank[4]={255,0,0,255};" in text        # types 1 et 2 : la boîte de physique ; le Character, rien
    scene.areas[0].effect(ForceFieldComponent).affects_characters = True
    assert effects_affect_characters(scene)
    assert "static const u8 _fx_rank[4]={255,0,0,0};" in _motion(tmp_path / "b", scene, [rigid, kin, hero])


def test_la_zone_s_applique_avant_le_pas_de_mouvement_et_donc_avant_la_garde_de_sommeil_d_un_rigid(tmp_path):
    rigid = _body("Ball", PHYSICS_BODY_RIGID)
    text = _motion(tmp_path, _scene(ForceFieldComponent(force_x=1.0), actors=[rigid]), [rigid])
    assert text.index("area_effects_apply(") < text.index("body_motion_step(")


def test_la_gravite_de_zone_n_atteint_que_les_corps_qui_suivent_la_gravite(tmp_path):
    follower = _body("Follower", PHYSICS_BODY_KINEMATIC, use_scene_gravity=True)
    ignorer = _body("Ignorer", PHYSICS_BODY_KINEMATIC, use_scene_gravity=False)
    scene = _scene(GravityOverrideComponent(gravity_y=0.25), actors=[follower, ignorer])
    text = _motion(tmp_path, scene, [follower, ignorer])
    assert "static const u8 _fx_rank[3]={255,0,255};" in text        # la gravité seule n'intéresse pas qui l'ignore


def test_le_corps_sans_boite_de_physique_n_est_pas_teste(tmp_path):
    ghost = Actor(name="Ghost", components=[PhysicsBodyComponent(mode=PHYSICS_BODY_RIGID)])
    assert "area_effects_apply" not in _motion(tmp_path, _scene(ForceFieldComponent(force_x=1.0), actors=[ghost]), [ghost])
