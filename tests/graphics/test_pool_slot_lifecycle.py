"""Le cycle de vie d'un emplacement de pool : détruit = libre, désactivé = occupé.

Le spawn ne reprend que les emplacements LIBRES (`alive == 0`). Désactiver la racine d'un prefab à
sous-arbre désactive ses parties sans libérer le groupe ; la détruire libère le groupe entier.
"""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from oam_fixtures import tout_afficher


def _boss_project(tmp_path):
    boss = Prefab(name="Boss")
    boss.children = [Actor(name="ArmL"), Actor(name="ArmR")]
    scene = Scene(name="S")
    scene.prefab_pools = {"Boss": 2}
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [boss]
    tout_afficher(p)
    return p, scene


def test_detruire_la_racine_libere_le_groupe_et_la_desactiver_le_garde(tmp_path):
    from codegen.runtime_codegen.main_gen import _scene_pi, _pool_compose_lines
    p, scene = _boss_project(tmp_path)
    code = "\n".join(_pool_compose_lines(_scene_pi(p, scene)))
    libere = ("if(!g_actors[_b].alive) {\n"
              "            for(int _k=1; _k<3; _k++) {\n"
              "                g_actors[_b+_k].active = 0; g_actors[_b+_k].alive = 0;")
    assert libere.replace("\n", "") .replace(" ", "") in code.replace("\n", "").replace(" ", "")
    garde = "if(!g_actors[_b].active) {"
    assert garde in code
    # Désactiver ne libère rien : la branche `active` n'écrit jamais `alive`.
    apres = code[code.index(garde):]
    assert "alive" not in apres[:apres.index("continue;")]


def test_le_spawn_ne_reprend_qu_un_emplacement_libre(tmp_path):
    from codegen.runtime_codegen.main_gen import _scene_pi, _section_spawn
    p, scene = _boss_project(tmp_path)
    code = "\n".join(_section_spawn(_scene_pi(p, scene), p, None))
    assert "if(!g_actors[_i].alive) {" in code
    assert "g_actors[_i].active   = 1; g_actors[_i].alive = 1;" in code
