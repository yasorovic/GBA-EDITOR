"""La mémoire des contacts des paires d'acteurs posés ne survit pas à la scène : c'est une globale que `scene_init` remet à zéro.

Un `static` dans le tick d'une scène gardait le recouvrement de la dernière frame après une sortie de scène : au retour, la
paire encore recouverte appelait `on_collide` ou `on_collision_exit` sans `enter`. Un build ROM réel vérifie le C émis."""
from __future__ import annotations

import pytest

from codegen import BuildWorker
from core.models.components import CollisionShapeComponent, ScriptComponent
from core.models.scene import Actor
from core.project import Project
from core.toolchain import DEVKITPRO_OK, Toolchain

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(Toolchain().devkitpro_state != DEVKITPRO_OK,
                       reason=f"devkitPro non prêt ({Toolchain().devkitpro_state})"),
]

HERO = "function on_collision_enter(other, my_box, other_box)\n  self:hide()\nend\n"


def test_la_memoire_des_contacts_est_une_globale_remise_a_zero_a_l_entree_de_scene(tmp_path):
    projet = Project.create(tmp_path / "Game", "Game")
    scripts = projet.user_library_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "Hero.lua").write_text(HERO, encoding="utf-8")
    heros = Actor(name="Hero", x=40, y=40, components=[
        CollisionShapeComponent(id="body", tag="body"), ScriptComponent(script="assets/scripts/Hero.lua")])
    pierre = Actor(name="Rock", x=44, y=40, components=[CollisionShapeComponent(id="body", tag="body")])
    projet.scenes[0].actors += [heros, pierre]
    projet.save()

    worker = BuildWorker(Project.open(projet.root), Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()
    assert verdict == [True], [d.message for d in diagnostics if d.level == "error"]

    main_c = next((projet.root / "build").rglob("main.c")).read_text(encoding="utf-8")
    assert "static u16 _col_prev" not in main_c                       # plus de static qui survit à la scène
    assert "u16 g_col_prev[" in main_c and "contact_pair_run(&_col_pairs[_k],&g_col_prev[_k])" in main_c
    assert "g_col_prev[_i]=0;" in main_c                              # remise à zéro à l'entrée de la scène
