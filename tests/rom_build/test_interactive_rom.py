"""Le composant Interactive, de bout en bout : un projet qui le déclare se compile en ROM avec le vrai
gcc, et le C émis contient le test du geste, les tables du consommateur et l'appel d'`on_interact`."""
from __future__ import annotations

import pytest

from codegen import BuildWorker
from core.models.components import CollisionShapeComponent, InteractiveComponent, ScriptComponent
from core.models.scene import Actor
from core.project import Project
from core.toolchain import DEVKITPRO_OK, Toolchain

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(Toolchain().devkitpro_state != DEVKITPRO_OK,
                       reason=f"devkitPro non prêt ({Toolchain().devkitpro_state})"),
]

CHEST = """function on_interact(who)
  self:hide()
end
"""
HERO = """function on_update()
end
"""
SIGN = """function on_interact(who)
  who.position = vec2(0, 0)
end
"""


def _projet(tmp_path) -> Project:
    projet = Project.create(tmp_path / "Game", "Game")
    scripts = projet.user_library_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "Chest.lua").write_text(CHEST, encoding="utf-8")
    (scripts / "Sign.lua").write_text(SIGN, encoding="utf-8")

    joueur = Actor(name="Hero", x=40, y=40, is_player=True)
    joueur.components = [CollisionShapeComponent(id="body", tag="body", solid=True)]

    coffre = Actor(name="Chest", x=50, y=40)
    coffre.components = [
        InteractiveComponent(input_mode="pressed", interaction="hover"),
        ScriptComponent(script="assets/scripts/Chest.lua"),
    ]
    panneau = Actor(name="Sign", x=80, y=40)
    panneau.components = [
        CollisionShapeComponent(id="reach", tag="reach", solid=False),
        InteractiveComponent(input_mode="hold", hold_frames=20, interaction="facing", box_tag="reach"),
        ScriptComponent(script="assets/scripts/Sign.lua"),
    ]
    projet.scenes[0].actors += [joueur, coffre, panneau]
    projet.save()
    return projet


def test_un_projet_interactif_se_compile_et_appelle_on_interact(tmp_path):
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
    assert "interact_pick(" in main_c                               # les aides sont émises
    assert "input_pressed(BTN_A)" in main_c                         # le geste du coffre
    assert "input_held_n(BTN_A,20)&&!input_held_n(BTN_A,21)" in main_c   # celui du panneau
    assert "_on_interact" in main_c
    # La boîte propre du coffre est posée sur l'acteur, avec le tag réservé.
    assert "BOXTAG_INTERACTIVE" in main_c


def test_un_prefab_joueur_poole_interagit_par_une_boucle(tmp_path):
    """Un prefab marqué Player est un interacteur : chaque instance de son pool est testée."""
    from core.models.scene import Prefab
    projet = _projet(tmp_path)
    heros = Prefab(name="Hero2", actor=Actor(name="Hero2", is_player=True))
    # Le héros a un script (`on_interact` en sort) ; un prefab sans script naît aussi, sans `pool_init`.
    (projet.user_library_dir / "scripts" / "Hero2.lua").write_text(HERO, encoding="utf-8")
    heros.actor.components = [CollisionShapeComponent(id="body", tag="body", solid=True),
                              ScriptComponent(script="assets/scripts/Hero2.lua")]
    projet.prefabs.append(heros)
    projet.prefabs.save(heros, None)
    (projet.user_library_dir / "scripts" / "Naissance.lua").write_text(
        'function on_update()\n    actor:spawn("Hero2", vec2(0, 0))\nend\n', encoding="utf-8")
    projet.scenes[0].script = "assets/scripts/Naissance.lua"
    projet.save()

    worker = BuildWorker(Project.open(projet.root), Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()

    assert verdict == [True], [d.message for d in diagnostics if d.level == "error"]
    main_c = next((projet.root / "build").rglob("main.c")).read_text(encoding="utf-8")
    assert "SLOT_EACH(_k){" in main_c and "interact_pick(_a,_ia_tag,_ia_aim," in main_c
    # Sans sprite, pas de tick d'animation : le regard de l'interacteur se suit dans le bloc Interactive.
    assert "(*_a).facing_x=(*_a).dir_x" in main_c


def test_soundfx_interaction_sans_script_pose_et_spawne_se_compile(tmp_path):
    import wave
    from asset_fixtures import create
    from core.models.components import SoundFxComponent
    from core.models.scene import Prefab
    project = _projet(tmp_path)
    path = project.user_library_dir / "Open.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(bytes([128]) * 800)
    sound = create(project, "sfx", path)
    chest = next(a for a in project.scenes[0].actors if a.name == "Chest")
    chest.components = [InteractiveComponent(), SoundFxComponent(sfx_name=sound.name, trigger="on_interact")]
    prefab = Prefab(name="Bell", actor=Actor(name="Bell", components=[
        InteractiveComponent(), SoundFxComponent(sfx_name=sound.name, trigger="on_interact")]))
    project.prefabs.append(prefab)
    project.prefabs.save(prefab)
    (project.user_library_dir / "scripts" / "Spawn.lua").write_text(
        'function on_start()\n actor:spawn("Bell", vec2(50,40))\nend\n', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/Spawn.lua"
    project.save()
    worker = BuildWorker(Project.open(project.root), Toolchain())
    worker._step_launch_mgba = lambda p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()
    assert verdict == [True], [d.message for d in diagnostics if d.level == "error"]
    code = next((project.root / "build").rglob("main.c")).read_text(encoding="utf-8")
    assert "_ia_action[]" in code and "_ia_paction[" in code
    assert "{0,SFX_OPEN," in code
    assert "KEY_ON_INTERACT" not in code and "BTN_ON_INTERACT" not in code


def test_un_acteur_bloquant_se_compile_et_repousse_le_joueur(tmp_path):
    """Une boîte « Bloque les acteurs » sur le coffre : le C émis repousse le joueur (boîte solide) avant la carte."""
    projet = _projet(tmp_path)
    scene = projet.scenes[0]
    heros = next(a for a in scene.actors if a.name == "Hero")
    coffre = next(a for a in scene.actors if a.name == "Chest")
    heros.components.append(ScriptComponent(script="assets/scripts/Hero2.lua"))
    (projet.user_library_dir / "scripts" / "Hero2.lua").write_text(HERO, encoding="utf-8")
    coffre.components.append(CollisionShapeComponent(id="body", tag="body", solid=False, response="block"))
    projet.save()

    worker = BuildWorker(Project.open(projet.root), Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()

    assert verdict == [True], [d.message for d in diagnostics if d.level == "error"]
    main_c = next((projet.root / "build").rglob("main.c")).read_text(encoding="utf-8")
    # La passe est par type : le héros est un mobile, le coffre un bloqueur, posés tous deux.
    assert "static const PairRun _bk_run[" in main_c
    assert "_bk_n=block_targets(_bk_bi,_bk_list);" in main_c and "actors_resolve_blocks(_a,_bk_mask[_mi],_bk_run[_mi],_bk_list,_bk_n,_bk_box);" in main_c
    assert "static void __attribute__((unused)) actors_resolve_blocks(" in main_c
