"""Les Areas à déclencheur, de bout en bout : un projet qui en pose une et dont un script répond à `on_area_*` se compile en
ROM avec le vrai gcc, et le C émis contient la table `g_areas`, les contacts de l'acteur posé et ceux du pool."""
from __future__ import annotations

import pytest

from codegen import BuildWorker
from core.models.components import CollisionShapeComponent, ScriptComponent
from core.models.scene import Actor, Area, Prefab
from core.project import Project
from core.toolchain import DEVKITPRO_OK, Toolchain

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(Toolchain().devkitpro_state != DEVKITPRO_OK,
                       reason=f"devkitPro non prêt ({Toolchain().devkitpro_state})"),
]

HERO = """function on_area_enter(area, my_box)
  if area.tag == "door" and my_box.tag == "body" then
    local door = area:get("Door")
    if area.name == "Door" and door:overlaps(self) then
      door.position = vec2(40, 56)
    end
    self:hide()
  end
end

function on_area_exit(area, my_box)
  local quiet = area:get("Quiet")
  if quiet.active and quiet.bounds.w > 0 then
    quiet:deactivate()
  end
  self:show()
end
"""
BULLET = """function on_area_collide(area, my_box)
  if area.active then
    self:hide()
  end
end
"""
SPAWNER = """function on_update()
  actor:spawn("Bullet", vec2(40, 56))
end
"""


def _projet(tmp_path) -> Project:
    projet = Project.create(tmp_path / "Game", "Game")
    scripts = projet.user_library_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "Hero.lua").write_text(HERO, encoding="utf-8")
    (scripts / "Bullet.lua").write_text(BULLET, encoding="utf-8")
    (scripts / "Spawner.lua").write_text(SPAWNER, encoding="utf-8")

    heros = Actor(name="Hero", x=40, y=56, is_player=True)
    heros.components = [CollisionShapeComponent(id="body", tag="body", solid=True),
                        ScriptComponent(script="assets/scripts/Hero.lua")]
    porte = Area(name="Door", x=40, y=56)
    porte.components[0].tag = "door"
    muette = Area(name="Quiet", x=120, y=56)
    muette.components = [c for c in muette.components if isinstance(c, CollisionShapeComponent)]   # sans déclencheur

    balle = Prefab(name="Bullet", actor=Actor(name="Bullet"))
    balle.actor.components = [CollisionShapeComponent(id="body", tag="body", solid=False),
                              ScriptComponent(script="assets/scripts/Bullet.lua")]
    projet.prefabs.append(balle)
    projet.prefabs.save(balle, None)

    projet.scenes[0].actors.append(heros)
    projet.scenes[0].areas += [porte, muette]
    projet.scenes[0].script = "assets/scripts/Spawner.lua"
    projet.save()
    return projet


def test_un_projet_avec_areas_se_compile_et_emet_les_contacts_poses_et_pool(tmp_path):
    projet = _projet(tmp_path)
    worker = BuildWorker(Project.open(projet.root), Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()

    erreurs = [d.message for d in diagnostics if d.level == "error"]
    assert verdict == [True], erreurs

    main_c = next((projet.root / "build").rglob("main.c")).read_text(encoding="utf-8")
    assert "Area g_areas[2] EWRAM_BSS;" in main_c                    # la scène la plus fournie
    assert "g_areas[0].x=(40)<<8;" in main_c and "g_areas[0].box.tag=BOXTAG_DOOR;" in main_c
    # L'acteur posé : une table de couples, une seule ligne (l'Area sans déclencheur n'entre dans aucun test).
    assert "static const AreaContact _area_pairs[1]" in main_c
    assert "{&g_areas[0]," in main_c and "_Hero_on_area_enter,0,Scene_01_Hero_on_area_exit}" in main_c
    assert "area_contact_run(" in main_c
    # Le pool : la boucle sur les emplacements, le même pas, la mémoire par emplacement.
    assert "area_contact_step(&g_areas[0],_a," in main_c and "_parea_gen" in main_c
    assert "g_areas[1]" not in main_c.split("_area_pairs")[1].split("};")[0]   # l'Area muette n'est pas testée
    # Le module `area` : les noms deviennent les références (rang + 1), et le script du héros les cite.
    types_h = next((projet.root / "build").rglob("actor_types.h")).read_text(encoding="utf-8")
    assert "#define AREA_SCENE_01_DOOR 1" in types_h and "#define AREA_SCENE_01_QUIET 2" in types_h
    sources = "\n".join(c.read_text(encoding="utf-8") for c in (projet.root / "build").rglob("*.c"))
    assert "area_by_name(AREA_SCENE_01_DOOR)" in sources and "area_get_name(area) == AREA_SCENE_01_DOOR" in sources
    assert "area_overlaps_actor(door, self)" in sources and "area_set_active(quiet, 0)" in sources
