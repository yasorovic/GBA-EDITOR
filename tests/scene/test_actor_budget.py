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
from codegen.oam_alloc import (
    OAM_LIMIT, POOL_DEFAULT_INSTANCES, scene_oam_layout, scene_pool_instances, scene_ui_obj_slots,
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
    lay = scene_oam_layout(p, p.scenes[0])
    assert lay.placed_entries == 0 and lay.pool_entries == 0 and lay.used == 0
    assert lay.free == OAM_LIMIT and lay.over_budget is False


def test_les_acteurs_poses_sont_comptes(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(3)])
    p = _projet(tmp_path, scene=scene)
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 3
    assert lay.placed_entries == 3
    assert lay.free == OAM_LIMIT - 3


# ── Le pool se dit en INSTANCES, se paie en SLOTS ─────────────────────

def test_un_prefab_plat_coute_une_instance_un_slot(tmp_path):
    ball = Prefab(name="Ball")
    scene = Scene(name="S")
    scene.prefab_pools = {"Ball": 4}
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    assert scene_oam_layout(p, scene).pool_entries == 4


def test_un_prefab_a_sous_arbre_coute_instances_x_parties(tmp_path):
    boss = Prefab(name="Boss")
    boss.children = [Actor(name="ArmL"), Actor(name="ArmR")]   # 1 racine + 2 = 3
    scene = Scene(name="S")
    scene.prefab_pools = {"Boss": 4}
    p = _projet(tmp_path, scene=scene, prefabs=[boss])
    assert scene_oam_layout(p, scene).pool_entries == 12       # 4 × 3


# ── Les 128 entrées se distribuent par priorité, rien ne bloque ───────

def test_un_pool_recoit_ce_qui_reste(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(120)])
    ball = Prefab(name="Ball")
    scene.prefab_pools = {"Ball": 16}                          # 120 + 16 = 136
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    lay = scene_oam_layout(p, scene)
    pool = lay.pools[0]
    assert pool.instances == 16 and pool.granted == 8 and pool.hidden == 8
    assert lay.used == OAM_LIMIT and lay.over_budget is False
    assert lay.requested == 136                                # la demande reste visible


def test_les_acteurs_posés_passent_avant_les_pools(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(130)])
    ball = Prefab(name="Ball")
    scene.prefab_pools = {"Ball": 4}
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    lay = scene_oam_layout(p, scene)
    assert lay.placed_entries == OAM_LIMIT and lay.placed_hidden == 2
    assert lay.pools[0].granted == 0 and lay.pools[0].hidden == 4
    assert lay.placed_entry[:128] == list(range(128)) and lay.placed_entry[128:] == [-1, -1]


def test_pile_dans_le_budget_rien_n_est_cache(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(100)])
    ball = Prefab(name="Ball")
    scene.prefab_pools = {"Ball": 28}                          # 100 + 28 = 128
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    lay = scene_oam_layout(p, scene)
    assert lay.used == OAM_LIMIT and lay.free == 0 and lay.pool_hidden == 0 and lay.table_size == OAM_LIMIT


def test_une_instance_cachee_ecrit_sur_l_entree_poubelle(tmp_path):
    """Le tableau d'entrées gagne de quoi absorber UNE instance : elle n'écrit jamais hors tableau."""
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(126)])
    boss = Prefab(name="Boss")
    boss.children = [Actor(name="Arm")]                        # 2 entrées par instance
    scene.prefab_pools = {"Boss": 3}                           # 2 restantes : 1 instance
    p = _projet(tmp_path, scene=scene, prefabs=[boss])
    lay = scene_oam_layout(p, scene)
    assert lay.pools[0].granted == 1 and lay.pools[0].hidden == 2
    assert lay.scratch_start == OAM_LIMIT and lay.table_size == OAM_LIMIT + 2


# ── Le poste UI est nul en B1 (décomposition par scène = B2) ──────────

def test_ui_est_nul_en_b1(tmp_path):
    scene = Scene(name="S", actors=[Actor(name="A")])
    p = _projet(tmp_path, scene=scene)
    assert scene_ui_obj_slots(scene, p) == 0
    assert scene_oam_layout(p, scene).ui == 0


# ── Le validateur avertit, il ne bloque pas ───────────────────────────

def test_le_validateur_avertit_d_un_pool_qui_ne_tient_pas(tmp_path):
    from core.validator import ValidationContext, _check_actor_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(120)])
    scene.prefab_pools = {"Ball": 16}
    p = _projet(tmp_path, scene=scene, prefabs=[Prefab(name="Ball")])
    ctx = ValidationContext(p)
    _check_actor_budget(ctx)
    assert ctx.errors == []
    assert len(ctx.warnings) == 1 and "'Ball'" in ctx.warnings[0].message


def test_le_validateur_avertit_d_un_acteur_pose_sans_entree(tmp_path):
    from core.validator import ValidationContext, _check_actor_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(130)])
    p = _projet(tmp_path, scene=scene)
    ctx = ValidationContext(p)
    _check_actor_budget(ctx)
    assert ctx.errors == []
    assert len(ctx.warnings) == 1 and "2 sprite actor" in ctx.warnings[0].message


def test_le_validateur_se_tait_dans_le_budget(tmp_path):
    from core.validator import ValidationContext, _check_actor_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(10)])
    p = _projet(tmp_path, scene=scene)
    ctx = ValidationContext(p)
    _check_actor_budget(ctx)
    assert [m for m in ctx._msgs if m.level in ("warning", "error")] == []


# ── Le pool d'un prefab spawné s'alloue tout seul ─────────────────────

def _scene_qui_spawne(tmp_path, *, actors=0, declared=None):
    ball = Prefab(name="Ball")
    scene = Scene(name="S", script="assets/s.lua", actors=[Actor(name=f"A{i}") for i in range(actors)])
    scene.prefab_pools = dict(declared or {})
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    (tmp_path / "assets").mkdir(parents=True)
    (tmp_path / "assets" / "s.lua").write_text(
        'function M.update(actor)\n    actor:spawn("Ball", vec2(0, 0))\nend\n', encoding="utf-8")
    return p, scene, ball


def test_un_prefab_spawne_sans_pool_declare_prend_le_defaut(tmp_path):
    p, scene, ball = _scene_qui_spawne(tmp_path)
    assert scene_pool_instances(p, scene, ball) == POOL_DEFAULT_INSTANCES


def test_le_defaut_ne_depend_pas_de_la_place_oam(tmp_path):
    """La taille du pool dit combien d'instances VIVENT ; l'OAM dit combien s'affichent."""
    p, scene, ball = _scene_qui_spawne(tmp_path, actors=125)       # 3 entrées libres
    assert scene_pool_instances(p, scene, ball) == POOL_DEFAULT_INSTANCES
    pool = scene_oam_layout(p, scene).pools[0]
    assert pool.granted == 3 and pool.hidden == POOL_DEFAULT_INSTANCES - 3


def test_le_pool_declare_garde_la_main(tmp_path):
    p, scene, ball = _scene_qui_spawne(tmp_path, declared={"Ball": 12})
    assert scene_pool_instances(p, scene, ball) == 12


def test_un_prefab_non_spawne_n_a_pas_de_pool(tmp_path):
    p, scene, ball = _scene_qui_spawne(tmp_path)
    scene.script = ""
    assert scene_pool_instances(p, scene, ball) == 0


# ── Les 32 matrices affines : un avertissement, pas un silence ────────

def _tout_affine(project) -> None:
    from core.models.components import affine_sprite_component
    for sc in project.scenes:
        for a in sc.actors:
            affine_sprite_component(a).affine_transform = True
    for pf in project.prefabs:
        affine_sprite_component(pf).affine_transform = True


def test_le_validateur_avertit_de_matrices_affines_manquantes(tmp_path):
    from core.validator import ValidationContext, _check_affine_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(30)])
    scene.prefab_pools = {"Ball": 6}                           # 30 + 6 = 36 matrices pour 32
    p = _projet(tmp_path, scene=scene, prefabs=[Prefab(name="Ball")])
    _tout_affine(p)
    ctx = ValidationContext(p)
    _check_affine_budget(ctx)
    assert ctx.errors == []
    assert len(ctx.warnings) == 1
    assert "36 affine matrices" in ctx.warnings[0].message and "last 4" in ctx.warnings[0].message


def test_une_instance_cachee_ne_demande_pas_de_matrice(tmp_path):
    from codegen.oam_alloc import scene_affine_requests
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(126)])   # 2 entrées libres
    scene.prefab_pools = {"Ball": 6}
    p = _projet(tmp_path, scene=scene, prefabs=[Prefab(name="Ball")])
    _tout_affine(p)
    assert scene_affine_requests(p, scene) == 126 + 2          # 2 instances affichées sur 6


def test_le_validateur_se_tait_sous_32_matrices(tmp_path):
    from core.validator import ValidationContext, _check_affine_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(32)])
    p = _projet(tmp_path, scene=scene)
    _tout_affine(p)
    ctx = ValidationContext(p)
    _check_affine_budget(ctx)
    assert ctx.warnings == []
