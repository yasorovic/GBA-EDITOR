"""Le budget d'acteurs DÉRIVÉ d'une scène.

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


def _a_part(nom: str) -> Prefab:
    """Un prefab qui garde sa réserve À LUI : un interacteur n'entre pas dans le pool partagé
    (`oam_alloc.is_plain_model`), donc il se dimensionne par `Scene.prefab_pools`."""
    pf = Prefab(name=nom)
    pf.actor.is_player = True
    return pf


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
    assert lay.placed_entries == 0 and lay.pool_entries == 0 and lay.table_size == 0
    assert lay.free == OAM_LIMIT and lay.over_budget is False


def test_les_acteurs_poses_sont_comptes(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(3)])
    p = _projet(tmp_path, scene=scene)
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 3
    assert lay.placed_entries == 3
    assert lay.free == OAM_LIMIT      # aucune interface : tous les emplacements restent aux acteurs


# ── Le pool se dit en INSTANCES, se paie en SLOTS ─────────────────────

def test_un_prefab_plat_coute_une_instance_un_slot(tmp_path):
    ball = _a_part("Ball")
    scene = Scene(name="S")
    scene.prefab_pools = {"Ball": 4}
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    assert scene_oam_layout(p, scene).pool_entries == 4


def test_un_prefab_a_sous_arbre_coute_instances_x_parties(tmp_path):
    boss = _a_part("Boss")
    boss.children = [Actor(name="ArmL"), Actor(name="ArmR")]   # 1 racine + 2 = 3
    scene = Scene(name="S")
    scene.prefab_pools = {"Boss": 4}
    p = _projet(tmp_path, scene=scene, prefabs=[boss])
    assert scene_oam_layout(p, scene).pool_entries == 12       # 4 × 3


# ── Les 128 emplacements se prennent à la frame, rien n'est réservé ───

def test_un_pool_garde_toutes_ses_instances_au_dela_de_128(tmp_path):
    """L'OAM borne ce qui s'AFFICHE ensemble, pas ce qui existe : chaque instance a son état."""
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(120)])
    ball = _a_part("Ball")
    scene.prefab_pools = {"Ball": 16}                          # 120 + 16 = 136
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    lay = scene_oam_layout(p, scene)
    assert lay.pools[0].instances == 16 and lay.pools[0].entry_size == 16
    assert lay.table_size == 136 and lay.over_budget is False
    assert lay.requested == 136                                # la demande reste visible


def test_tous_les_acteurs_poses_ont_un_etat_au_dela_de_128(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(130)])
    ball = _a_part("Ball")
    scene.prefab_pools = {"Ball": 4}
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    lay = scene_oam_layout(p, scene)
    assert lay.placed_entries == 130
    assert lay.placed_entry == list(range(130))
    assert lay.pools[0].entry_start == 130


def test_le_tableau_d_etats_n_a_pas_d_entree_poubelle(tmp_path):
    """Une instance écrit toujours dans SON état : la table fait exactement la somme des états."""
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(126)])
    boss = _a_part("Boss")
    boss.children = [Actor(name="Arm")]                        # 2 entrées par instance
    scene.prefab_pools = {"Boss": 3}
    p = _projet(tmp_path, scene=scene, prefabs=[boss])
    lay = scene_oam_layout(p, scene)
    assert lay.pools[0].entry_size == 6 and lay.table_size == 126 + 6


# ── Le poste UI est nul en B1 (décomposition par scène = B2) ──────────

def test_ui_est_nul_en_b1(tmp_path):
    scene = Scene(name="S", actors=[Actor(name="A")])
    p = _projet(tmp_path, scene=scene)
    assert scene_ui_obj_slots(scene, p) == 0
    assert scene_oam_layout(p, scene).ui == 0


# ── Le validateur ne bloque que l'interface ───────────────────────────

def test_le_validateur_se_tait_quand_les_acteurs_depassent_128(tmp_path):
    """Un surplus d'acteurs n'est un souci qu'à l'écran, au jeu : pas d'avertissement au build."""
    from core.validator import ValidationContext, _check_actor_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(130)])
    scene.prefab_pools = {"Ball": 16}
    p = _projet(tmp_path, scene=scene, prefabs=[_a_part("Ball")])
    ctx = ValidationContext(p)
    _check_actor_budget(ctx)
    assert ctx.errors == [] and ctx.warnings == []


def test_le_validateur_refuse_une_interface_qui_depasse_l_oam(tmp_path, monkeypatch):
    import codegen.oam_alloc as oam_alloc
    from core.validator import ValidationContext, _check_actor_budget
    monkeypatch.setattr(oam_alloc, "scene_ui_obj_slots", lambda scene, project: 129)
    p = _projet(tmp_path, scene=Scene(name="S", actors=[Actor(name="A")]))
    ctx = ValidationContext(p)
    _check_actor_budget(ctx)
    assert len(ctx.errors) == 1 and "interface" in ctx.errors[0].message


def test_le_validateur_se_tait_dans_le_budget(tmp_path):
    from core.validator import ValidationContext, _check_actor_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(10)])
    p = _projet(tmp_path, scene=scene)
    ctx = ValidationContext(p)
    _check_actor_budget(ctx)
    assert [m for m in ctx._msgs if m.level in ("warning", "error")] == []


# ── Le pool d'un prefab spawné s'alloue tout seul ─────────────────────

def _scene_qui_spawne(tmp_path, *, actors=0, declared=None):
    ball = _a_part("Ball")
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
    """La taille du pool dit combien d'instances VIVENT ; l'OAM dit combien s'affichent ENSEMBLE."""
    p, scene, ball = _scene_qui_spawne(tmp_path, actors=125)       # 125 acteurs : l'OAM n'y change rien
    assert scene_pool_instances(p, scene, ball) == POOL_DEFAULT_INSTANCES
    pool = scene_oam_layout(p, scene).pools[0]
    assert pool.instances == pool.entry_size == POOL_DEFAULT_INSTANCES


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
    p = _projet(tmp_path, scene=scene, prefabs=[_a_part("Ball")])
    _tout_affine(p)
    ctx = ValidationContext(p)
    _check_affine_budget(ctx)
    assert ctx.errors == []
    assert len(ctx.warnings) == 1
    assert "36 affine matrices" in ctx.warnings[0].message and "last 4" in ctx.warnings[0].message


def test_chaque_instance_d_etat_demande_sa_matrice(tmp_path):
    from codegen.oam_alloc import scene_affine_requests
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(126)])
    scene.prefab_pools = {"Ball": 6}
    p = _projet(tmp_path, scene=scene, prefabs=[_a_part("Ball")])
    _tout_affine(p)
    assert scene_affine_requests(p, scene) == 126 + 6          # une matrice par instance : l'affine reste statique


def test_le_validateur_se_tait_sous_32_matrices(tmp_path):
    from core.validator import ValidationContext, _check_affine_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(32)])
    p = _projet(tmp_path, scene=scene)
    _tout_affine(p)
    ctx = ValidationContext(p)
    _check_affine_budget(ctx)
    assert ctx.warnings == []
