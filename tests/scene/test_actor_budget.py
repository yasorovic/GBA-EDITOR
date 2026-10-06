"""Le budget d'acteurs DÉRIVÉ d'une scène (ROADMAP v0.17, révision 2026-09-19).

Le budget n'est plus réparti entre deux tranches réglables (l'ancien 96/32) : il
est dérivé. Acteurs posés (et, en B2, OBJ d'interface) se COMPTENT ; le pool est
ce qui reste. Ces tests fixent la nouvelle arithmétique et la faute unique qui en
découle — le débordement des 128 entrées de l'OAM.
"""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from oam_fixtures import tout_afficher, donner_un_sprite
from codegen.actor_budget import (
    OAM_LIMIT, scene_actor_budget, scene_actor_slots, scene_ui_obj_slots,
    scene_pool_slots,
)


def _projet(tmp_path, *, scene: Scene, prefabs=None, sprites=True) -> Project:
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = list(prefabs or [])
    if sprites:
        tout_afficher(p)
    return p


# ── Les acteurs se COMPTENT, ils ne se réservent pas ──────────────────

def test_scene_vide_ne_consomme_rien(tmp_path):
    p = _projet(tmp_path, scene=Scene(name="S"))
    b = scene_actor_budget(p.scenes[0], p)
    assert b["actors"] == 0 and b["pool"] == 0 and b["used"] == 0
    assert b["free"] == OAM_LIMIT and b["over_budget"] is False


def test_les_acteurs_poses_sont_comptes(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(3)])
    p = _projet(tmp_path, scene=scene)
    b = scene_actor_budget(scene, p)
    assert b["placed"] == 3
    assert b["actors"] == 3        # auto : le poste vaut ce qui est posé
    assert b["free"] == OAM_LIMIT - 3


def test_actor_slots_est_un_override(tmp_path):
    """0 = auto (compté) ; une valeur > 0 fige le poste, sans toucher au
    décompte réel des acteurs posés."""
    scene = Scene(name="S", actors=[Actor(name="A"), Actor(name="B")])
    scene.actor_slots = 10
    p = _projet(tmp_path, scene=scene)
    b = scene_actor_budget(scene, p)
    assert scene_actor_slots(scene) == 10
    assert b["actors"] == 10 and b["placed"] == 2
    assert b["free"] == OAM_LIMIT - 10


# ── Le pool se dit en INSTANCES, se paie en SLOTS ─────────────────────

def test_un_prefab_plat_coute_une_instance_un_slot(tmp_path):
    ball = Prefab(name="Ball")
    scene = Scene(name="S")
    scene.prefab_pools = {"Ball": 4}
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    assert scene_pool_slots(scene, p) == 4
    assert scene_actor_budget(scene, p)["pool"] == 4


def test_un_prefab_a_sous_arbre_coute_instances_x_parties(tmp_path):
    boss = Prefab(name="Boss")
    boss.children = [Actor(name="ArmL"), Actor(name="ArmR")]   # 1 racine + 2 = 3
    scene = Scene(name="S")
    scene.prefab_pools = {"Boss": 4}
    p = _projet(tmp_path, scene=scene, prefabs=[boss])
    assert scene_pool_slots(scene, p) == 12                    # 4 × 3
    assert scene_actor_budget(scene, p)["pool"] == 12


# ── Une seule faute possible : le débordement des 128 ─────────────────

def test_debordement_oam(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(120)])
    ball = Prefab(name="Ball")
    scene.prefab_pools = {"Ball": 16}                          # 120 + 16 = 136
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    b = scene_actor_budget(scene, p)
    assert b["used"] == 136 and b["over_budget"] is True
    assert b["free"] == OAM_LIMIT - 136                        # négatif, assumé


def test_pile_dans_le_budget_ne_deborde_pas(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(100)])
    ball = Prefab(name="Ball")
    scene.prefab_pools = {"Ball": 28}                          # 100 + 28 = 128
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    b = scene_actor_budget(scene, p)
    assert b["used"] == OAM_LIMIT and b["over_budget"] is False and b["free"] == 0


# ── Le poste UI est nul en B1 (décomposition par scène = B2) ──────────

def test_ui_est_nul_en_b1(tmp_path):
    scene = Scene(name="S", actors=[Actor(name="A")])
    p = _projet(tmp_path, scene=scene)
    assert scene_ui_obj_slots(scene, p) == 0
    assert scene_actor_budget(scene, p)["ui"] == 0


# ── Le validateur n'a plus qu'une faute : over_budget ─────────────────

def test_le_validateur_bloque_sur_le_debordement(tmp_path):
    """ROADMAP v0.17 T7 : le débordement OAM est une ERREUR bloquante (le rendu
    écrit `shadow_oam[index]`, 128 entrées — au-delà c'est une corruption), et il
    est mesuré sur la même source que le build (`scene_oam_layout`)."""
    from core.validator import ValidationContext, _check_actor_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(130)])
    p = _projet(tmp_path, scene=scene)
    ctx = ValidationContext(p)
    _check_actor_budget(ctx)
    errs = [m for m in ctx._msgs if m.level == "error"]
    assert len(errs) == 1
    assert "OAM" in errs[0].message


def test_le_validateur_se_tait_dans_le_budget(tmp_path):
    from core.validator import ValidationContext, _check_actor_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(10)])
    p = _projet(tmp_path, scene=scene)
    ctx = ValidationContext(p)
    _check_actor_budget(ctx)
    assert [m for m in ctx._msgs if m.level in ("warning", "error")] == []
