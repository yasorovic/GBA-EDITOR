"""Le cycle de vie d'un emplacement du pool : détruit = libre, désactivé = occupé.

Le spawn ne reprend que les emplacements LIBRES. Désactiver la racine d'un prefab à sous-arbre désactive ses
parties sans libérer le groupe ; la détruire libère le groupe entier (`actor_destroy_internal`, cf. la sonde native
`tests/native/actor_box_probe.c`). Une partie détruite seule garde son emplacement tant que la racine vit.
"""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from oam_fixtures import tout_afficher, faire_naitre


def _boss_project(tmp_path):
    boss = Prefab(name="Boss")
    boss.children = [Actor(name="ArmL"), Actor(name="ArmR")]
    scene = Scene(name="S")
    faire_naitre(tmp_path, scene, "Boss")
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [boss]
    tout_afficher(p)
    return p, scene


def test_le_spawn_ne_reprend_qu_un_emplacement_libre(tmp_path):
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    p, scene = _boss_project(tmp_path)
    code = "\n".join(section_spawn(scene_pi(p, scene), p, None))
    assert "spool_slot_free(_k+_j)" in code and "actor_init_slot(_i," in code
