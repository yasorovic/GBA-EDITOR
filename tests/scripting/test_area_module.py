"""Le module `area` : `area:get("Nom")`, `area.name`, `active` par verbes, `position`, `bounds`, `overlaps`.

Une Area est nommée dans la scène (nom local à la scène) : `area:get("Door")` et `area.name == "Door"` se résolvent à la constante
`AREA_<SCÈNE>_<NOM>`, qui EST la référence (le rang dans `g_areas`, plus un). Le nom est un domaine comme celui des acteurs : il se
vérifie contre les Areas de la scène, se complète, et suit un renommage."""
from __future__ import annotations

from core.models.components import CollisionShapeComponent, ScriptComponent
from core.models.scene import Actor, Area
from scripting.api import DOMAIN_AREA_NAME, RUNTIME_API, RUNTIME_PROPS

AREAS = ["Door", "Zone"]


def _lua(src: str, areas=AREAS):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(actor_name="Hero", anim_names=["idle"], box_tag_names=["body", "door"],
                                        area_names=areas))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Hero", actor_sym="Hero", anim_names=["idle"], sfx_names=[], scene_sym="Scene_01",
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Hero"]))
    return [e.message for e in errors if e.level == "error"], code


def test_get_se_resout_a_la_constante_de_la_scene():
    errs, code = _lua("function on_update()\n  local door = area:get(\"Door\")\n  door:deactivate()\nend\n")
    assert errs == []
    assert "int door = area_by_name(AREA_SCENE_01_DOOR);" in code
    assert "area_set_active(door, 0);" in code


def test_un_nom_inconnu_est_refuse_et_les_noms_de_la_scene_sont_cites():
    errs, _code = _lua("function on_update()\n  local a = area:get(\"Ghost\")\nend\n")
    assert any("no Area named 'Ghost'" in e and "Door, Zone" in e for e in errs)
    errs, _code = _lua("function on_area_enter(area, my_box)\n  if area.name == \"Ghost\" then self:hide() end\nend\n")
    assert any("no Area named 'Ghost'" in e for e in errs)


def test_un_script_sans_scene_ne_juge_pas_les_noms_d_area():
    errs, _code = _lua("function on_update()\n  local a = area:get(\"Anything\")\nend\n", areas=None)
    assert errs == []


def test_le_nom_se_compare_a_la_meme_constante_que_get_rend():
    errs, code = _lua("function on_area_enter(area, my_box)\n  if area.name == \"Door\" then self:hide() end\nend\n")
    assert errs == []
    assert "area_get_name(area) == AREA_SCENE_01_DOOR" in code


def test_position_bounds_et_overlaps_se_compilent_vers_les_accesseurs():
    errs, code = _lua(
        "function on_update()\n"
        "  local door = area:get(\"Door\")\n"
        "  door.position = vec2(8, 16)\n"
        "  local b = door.bounds\n"
        "  if door:overlaps(self) and b.w > 0 then door:activate() end\n"
        "end\n")
    assert errs == []
    assert "area_set_position(door," in code and "area_get_bounds(door)" in code
    assert "area_overlaps_actor(door, self)" in code and "area_set_active(door, 1)" in code


def test_active_et_name_et_bounds_sont_en_lecture_seule():
    for key in ("area.active", "area.name", "area.bounds", "area.tag"):
        assert RUNTIME_PROPS[key].read_only and RUNTIME_PROPS[key].c_setter is None, key
    assert not RUNTIME_PROPS["area.position"].read_only
    for src in ("area.active = false", "area.name = 3", "area.bounds = rect(0, 0, 1, 1)"):
        errs, _code = _lua(f"function on_area_enter(area, my_box)\n  {src}\nend\n")
        assert errs, src


def test_le_catalogue_de_l_area_est_complet():
    assert RUNTIME_API["area.get"].ret == "area"
    for verbe in ("activate", "deactivate", "overlaps"):
        assert f"area:{verbe}" in {f.lua_name for f in RUNTIME_API.values()}


def test_un_renommage_d_area_reecrit_les_deux_formes():
    from scripting.refactor import rename_in_text
    src = ("function on_area_enter(area, my_box)\n"
           "  local d = area:get(\"Door\")\n"
           "  if area.name == \"Door\" then d:deactivate() end\nend\n")
    out, n = rename_in_text(src, DOMAIN_AREA_NAME, "Door", "Gate")
    assert n == 2 and out.count("Gate") == 2 and "Door" not in out


# ── Le projet ────────────────────────────────────────────────────────────

def _projet(tmp_path):
    from core.project import Project
    projet = Project.create(tmp_path / "Game", "Game")
    scripts = projet.user_library_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "Hero.lua").write_text(
        "function on_update()\n  local d = area:get(\"Door\")\n  d:deactivate()\nend\n", encoding="utf-8")
    scene = projet.scenes[0]
    scene.actors.append(Actor(name="Hero", components=[CollisionShapeComponent(id="body"),
                                                       ScriptComponent(script="assets/scripts/Hero.lua")]))
    scene.areas += [Area(name="Door"), Area(name="Zone")]
    projet.save()
    return projet, scene, scripts / "Hero.lua"


def test_renommer_une_area_reecrit_les_scripts_et_refuse_un_nom_pris(tmp_path):
    projet, scene, script = _projet(tmp_path)
    door, zone = scene.areas
    assert projet.rename_area(scene, door, "Zone") is False and door.name == "Door"        # déjà pris
    assert projet.rename_area(scene, door, "  ") is False and projet.rename_area(scene, door, "Door") is False
    assert projet.rename_area(scene, door, "Gate") is True
    assert door.name == "Gate" and 'area:get("Gate")' in script.read_text(encoding="utf-8")


def test_le_renommage_d_area_s_annule_scripts_compris(tmp_path):
    from core.history import RenameAreaCmd
    projet, scene, script = _projet(tmp_path)
    door = scene.areas[0]
    cmd = RenameAreaCmd(projet, scene, door, "Gate")
    cmd.execute()
    assert door.name == "Gate" and "Gate" in script.read_text(encoding="utf-8")
    cmd.undo()
    assert door.name == "Door" and 'area:get("Door")' in script.read_text(encoding="utf-8")


def test_les_noms_d_area_de_la_scene_sont_proposes_a_la_completion(tmp_path):
    from scripting.project_names import names_by_domain
    projet, scene, _script = _projet(tmp_path)
    assert names_by_domain(projet, scene)[DOMAIN_AREA_NAME] == ["Door", "Zone"]
