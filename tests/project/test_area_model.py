"""Area : une zone de jeu posée dans la scène, avec une forme de collision capteur."""
import json

from core.models.components import CollisionShapeComponent
from core.models.scene import AREA_DEFAULT_TAG, Area, Scene
from core.project import Project


def _scene_json(project, scene):
    return json.loads(project.scenes.path_of(scene).read_text(encoding="utf-8"))


def _project(tmp_path, *areas):
    p = Project.create(tmp_path / "Game", "Game")
    scene = Scene(name="Arena", areas=list(areas))
    p.scenes.append(scene)
    p.scenes.save_all()
    return p, scene


def test_une_area_neuve_porte_une_forme_capteur_de_32_pixels_et_un_declencheur():
    from core.models.components import TriggerComponent
    area = Area(name="Door")
    shape, trigger = area.components
    assert isinstance(trigger, TriggerComponent) and trigger.active
    assert isinstance(shape, CollisionShapeComponent)
    assert (shape.w, shape.h, shape.tag) == (32, 32, AREA_DEFAULT_TAG)
    assert not shape.solid and shape.response == "sensor"


def test_aller_retour_json_garde_nom_id_position_et_forme(tmp_path):
    area = Area(name="Door", x=40, y=56, active=False, notes="vers la cave")
    area.components[0].w = 48
    area.components[0].tag = "door"
    p, scene = _project(tmp_path, area)

    saved = _scene_json(p, scene)["areas"][0]
    assert list(saved)[:2] == ["name", "id"] and "source" not in saved

    p.scenes.load()
    back = p.scenes.get("Arena").areas[0]
    assert (back.name, back.id, back.x, back.y, back.active, back.notes) == \
        ("Door", area.id, 40, 56, False, "vers la cave")
    assert (back.components[0].w, back.components[0].tag) == (48, "door")


def test_une_scene_sans_area_n_ecrit_pas_la_cle(tmp_path):
    p, scene = _project(tmp_path)
    assert "areas" not in _scene_json(p, scene)


def test_lecture_tolerante_des_champs_absents():
    area = Area.from_dict({"name": "Bare"})
    assert (area.x, area.y, area.active) == (112, 72, True)
    assert len(area.components) == 2 and area.components[0].w == 32 and area.is_trigger()
    # Une liste vide écrite par l'auteur est respectée (le validateur la signale).
    assert Area.from_dict({"name": "Empty", "components": []}).components == []


def test_les_formes_sont_toujours_des_capteurs_non_solides():
    area = Area.from_dict({"name": "Wall", "components": [
        {"component_type": "collision_shape", "solid": True, "response": "block", "one_way": "up"}]})
    shape = area.components[0]
    assert (shape.solid, shape.response, shape.one_way) == (False, "sensor", "off")


def test_le_parent_s_ecrit_seulement_s_il_existe_et_se_relit(tmp_path):
    from core.models.scene import Actor
    follower, free = Area(name="Follower", parent="Boss"), Area(name="Free")
    p, scene = _project(tmp_path, follower, free)
    scene.actors.append(Actor(name="Boss"))
    saved = _scene_json(p, scene)["areas"]
    assert saved[0]["parent"] == "Boss" and "parent" not in saved[1]
    p.scenes.load()
    back = p.scenes.get("Arena").areas
    assert [a.parent for a in back] == ["Boss", None]


def test_renommer_un_acteur_fait_suivre_ses_areas(tmp_path):
    from core.models.scene import Actor
    p, scene = _project(tmp_path, Area(name="Follower", parent="Boss"), Area(name="Other", parent="Rock"))
    boss = Actor(name="Boss")
    scene.actors += [boss, Actor(name="Rock")]
    assert p.rename_actor(boss, "Chief", scene=scene) is True
    assert [a.parent for a in scene.areas] == ["Chief", "Rock"]       # seules celles de cet acteur
    assert p.rename_actor(boss, "Boss", scene=scene) is True          # le défaire (RenameActorCmd) les remet
    assert scene.areas[0].parent == "Boss"


def test_le_validateur_refuse_un_parent_qui_n_est_pas_un_acteur_de_la_scene(tmp_path):
    from core import validator
    from core.models.scene import Actor
    p, scene = _project(tmp_path, Area(name="Follower", parent="Ghost"))
    ctx = validator.ValidationContext(p)
    validator._check_areas(ctx, scene)
    assert any(m.level == "error" and "\"Ghost\"" in m.message for m in ctx._msgs)
    scene.actors.append(Actor(name="Ghost"))
    ctx = validator.ValidationContext(p)
    validator._check_areas(ctx, scene)
    assert not [m for m in ctx._msgs if m.level == "error"]


def test_les_ids_de_membres_sont_uniques_avec_les_acteurs(tmp_path):
    p, scene = _project(tmp_path, Area(name="A"), Area(name="B"))
    ids = [a["id"] for a in _scene_json(p, scene)["areas"]]
    assert len(set(ids)) == 2


def _validate_areas(project, scene):
    from core import validator
    ctx = validator.ValidationContext(project)
    validator._check_areas(ctx, scene)
    return [(m.level, m.message) for m in ctx._msgs]


def test_validateur_deux_areas_de_meme_symbole_c_avertissent(tmp_path):
    p, scene = _project(tmp_path, Area(name="Door 1"), Area(name="Door-1"))
    assert any("share the C symbol" in msg for _, msg in _validate_areas(p, scene))


def test_validateur_une_area_sans_forme_avertit_et_une_forme_nulle_est_une_erreur(tmp_path):
    empty = Area(name="Empty", components=[])
    flat = Area(name="Flat")
    flat.components[0].w = 0
    p, scene = _project(tmp_path, empty, flat)
    found = _validate_areas(p, scene)
    assert ("warning", "The Area has no active collision shape: it covers nothing.") in found
    assert any(lvl == "error" and "zero width or height" in msg for lvl, msg in found)


def test_validateur_une_area_saine_ne_dit_rien(tmp_path):
    p, scene = _project(tmp_path, Area(name="Door"))
    assert _validate_areas(p, scene) == []


def test_renommer_un_tag_de_collision_suit_les_areas(tmp_path):
    from core.history import RenameCollisionTagCmd
    area = Area(name="Door")
    area.components[0].tag = "door"
    p, _ = _project(tmp_path, area)
    cmd = RenameCollisionTagCmd(p, "door", "gate")
    cmd.execute()
    assert area.components[0].tag == "gate"
    cmd.undo()
    assert area.components[0].tag == "door"


def test_le_tag_d_une_area_entre_dans_les_tags_du_projet(tmp_path):
    area = Area(name="Door")
    area.components[0].tag = "door_zone"
    p, _ = _project(tmp_path, area)
    assert "door_zone" in p.collision_tags()
