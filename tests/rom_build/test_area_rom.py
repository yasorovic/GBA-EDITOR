"""Les Areas à déclencheur, de bout en bout : un projet qui en pose une et dont un script répond à `on_area_*` se compile en
ROM avec le vrai gcc, et le C émis contient la table `g_areas`, les contacts des emplacements posés et nés. Une Area peut aussi
porter son propre script (`on_start`, `on_update`, `on_actor_*`), compilé dans son fichier."""
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
      door.size = vec2(40, door.size.y)
    end
    local boss = area.parent
    if boss then
      boss:show()
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
    porte.parent = "Hero"                      # la porte suit le héros (un acteur posé)
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
    # Posés et nés : un seul parcours des emplacements, crochets et masques lus par type, mémoire par emplacement (l'Area sans
    # déclencheur n'entre dans aucun test).
    assert "static const AreaFn _ar_on[" in main_c
    assert "_Hero_on_area_enter,0,Scene_01_Hero_on_area_exit}" in main_c
    assert "area_contact_step(&g_areas[0],_a,_ar_allowed[_i][0],_ar_on[_i],0,&g_area_prev[_k][0]);" in main_c
    assert "g_area_gen[_k]!=_a->gen" in main_c
    assert "area_contact_step(&g_areas[1]" not in main_c            # l'Area muette n'est pas testée
    # Le module `area` : les noms deviennent les références (rang + 1), et le script du héros les cite.
    types_h = next((projet.root / "build").rglob("actor_types.h")).read_text(encoding="utf-8")
    assert "#define AREA_SCENE_01_DOOR 1" in types_h and "#define AREA_SCENE_01_QUIET 2" in types_h
    sources = "\n".join(c.read_text(encoding="utf-8") for c in (projet.root / "build").rglob("*.c"))
    assert "area_by_name(AREA_SCENE_01_DOOR)" in sources and "area_get_name(area) == AREA_SCENE_01_DOOR" in sources
    assert "area_overlaps_actor(door, self)" in sources and "area_set_active(quiet, 0)" in sources
    # Une Area qui suit un acteur : le parent est posé à l'entrée de scène, la position recomposée après les acteurs.
    assert "g_areas[0].parent=2;" in main_c and "g_areas[1].parent" not in main_c          # le héros est l'emplacement 1
    assert "g_areas[0].held = !(g_actors[1].active && g_actors[1].alive);" in main_c
    assert main_c.index("Areas that follow an actor") < main_c.index("static const AreaFn _ar_on")   # avant les contacts
    assert "area_get_parent(area)" in sources and "area_set_size(door," in sources


def test_une_zone_d_effet_se_compile_et_agit_sur_le_pose_et_le_spawne(tmp_path):
    """Une Area à champ de force et gravité de zone, un Rigid posé et un Rigid spawné : le C compile avec le vrai gcc, et les
    deux passent par `area_effects_apply` avec la même table `_fx`."""
    from core.models.components import ForceFieldComponent, GravityOverrideComponent, PhysicsBodyComponent
    projet = Project.create(tmp_path / "Game", "Game")
    scripts = projet.user_library_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "Spawner.lua").write_text(SPAWNER.replace("Bullet", "Ball"), encoding="utf-8")

    def rigid(name):
        actor = Actor(name=name, x=40, y=20)
        actor.components = [CollisionShapeComponent(id="body", tag="body", solid=True),
                            PhysicsBodyComponent(mode="rigid")]
        return actor

    projet.scenes[0].actors.append(rigid("Crate"))
    balle = Prefab(name="Ball", actor=rigid("Ball"))
    projet.prefabs.append(balle)
    projet.prefabs.save(balle, None)
    zone = Area(name="Water", x=20, y=40)
    zone.components += [GravityOverrideComponent(gravity_y=0.05),
                        ForceFieldComponent(force_x=0.1, turbulence=0.1, buoyancy=0.5, drag=0.1)]
    projet.scenes[0].areas.append(zone)
    projet.scenes[0].physics_enabled = True
    projet.scenes[0].script = "assets/scripts/Spawner.lua"
    projet.save()

    worker = BuildWorker(Project.open(projet.root), Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()
    assert verdict == [True], [d.message for d in diagnostics if d.level == "error"]

    main_c = next((projet.root / "build").rglob("main.c")).read_text(encoding="utf-8")
    assert "static const AreaEffect _fx[1]" in main_c
    assert "{&g_areas[0],0,13,26,0,128,26,230,AREAFX_GRAVITY}" in main_c
    assert "static const u8 _fx_rank[" in main_c                     # les rangs de boîte, par type d'emplacement
    assert "area_effects_apply(_fx,1,_a,_r," in main_c               # un seul pas pour le posé et le spawné
    assert "g_fx_rng=1;" in main_c                                   # la suite de la turbulence repart à chaque scène


TRAP = """local hits = 0

function on_start()
  self.size = vec2(24, 24)
end

function on_update()
  if hits > 3 then
    self:deactivate()
  end
end

function on_actor_enter(other, other_box)
  if other_box.tag == "body" and self:overlaps(other) then
    hits = hits + 1
    other:hide()
  end
end

function on_actor_exit(other)
  other:show()
end
"""


def test_une_area_scriptee_se_compile_et_recoit_les_contacts_des_poses_et_des_nes(tmp_path):
    """Une Area qui porte un script : son fichier `<Scène>_<Area>_area.c` compile avec le vrai gcc, `on_start` et `on_update`
    sont appelés par la scène, et ses `on_actor_*` passent par le même pas que les crochets des acteurs, pour le héros posé
    comme pour la balle née du pool (aucun des deux n'a de crochet d'Area)."""
    projet = Project.create(tmp_path / "Game", "Game")
    scripts = projet.user_library_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "Trap.lua").write_text(TRAP, encoding="utf-8")
    (scripts / "Spawner.lua").write_text(SPAWNER, encoding="utf-8")
    heros = Actor(name="Hero", x=40, y=56, is_player=True)
    heros.components = [CollisionShapeComponent(id="body", tag="body", solid=True)]
    balle = Prefab(name="Bullet", actor=Actor(name="Bullet"))
    balle.actor.components = [CollisionShapeComponent(id="body", tag="body", solid=False)]
    projet.prefabs.append(balle)
    projet.prefabs.save(balle, None)
    piege = Area(name="Trap", x=40, y=56)
    piege.components.append(ScriptComponent(script="assets/scripts/Trap.lua"))
    projet.scenes[0].actors.append(heros)
    projet.scenes[0].areas.append(piege)
    projet.scenes[0].script = "assets/scripts/Spawner.lua"
    projet.save()

    worker = BuildWorker(Project.open(projet.root), Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()
    assert verdict == [True], [d.message for d in diagnostics if d.level == "error"]

    build = projet.root / "build"
    main_c = next(build.rglob("main.c")).read_text(encoding="utf-8")
    trap_c = next(build.rglob("Scene_01_Trap_area.c")).read_text(encoding="utf-8")
    assert "static const int self __attribute__((unused)) = 1;" in trap_c
    assert "area_set_size(self," in trap_c and "area_overlaps_actor(self, other)" in trap_c
    assert "Scene_01_Trap_area_on_start();" in main_c
    assert "if(g_areas[0].active && !g_areas[0].held) Scene_01_Trap_area_on_update();" in main_c
    # Les deux types (héros posé, balle née) entrent dans la passe sans crochet propre : le script de l'Area les écoute.
    assert "static const AreaActorFn _ar_own[1][3]={{Scene_01_Trap_area_on_actor_enter,0,Scene_01_Trap_area_on_actor_exit}};" in main_c
    assert "_ar_on[_i],_ar_own[0],&g_area_prev[_k][0]" in main_c
    assert main_c.count("{0,0,0}") >= 2                               # une ligne de crochets d'acteur vide par type
