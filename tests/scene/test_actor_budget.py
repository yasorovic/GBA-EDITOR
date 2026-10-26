"""Le budget d'acteurs DÉRIVÉ d'une scène.

Le budget n'est plus réparti entre deux tranches réglables (l'ancien 96/32) : il
est dérivé. Acteurs posés (et, en B2, OBJ d'interface) se COMPTENT ; le pool partagé est
ce qui reste, sans rien à régler. Ces tests fixent l'arithmétique et la faute unique qui en
découle — le débordement des 128 entrées de l'OAM par l'interface seule.
"""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from oam_fixtures import tout_afficher, faire_naitre
from codegen.oam_alloc import (
    OAM_LIMIT, OBJECT_CAPACITY, scene_oam_layout, scene_has_model, scene_ui_obj_slots,
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
    assert lay.placed_entries == 0 and lay.pool_entries == 0 and lay.table_size == 0
    assert lay.free == OAM_LIMIT and lay.over_budget is False


def test_les_acteurs_poses_sont_comptes(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(3)])
    p = _projet(tmp_path, scene=scene)
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 3
    assert lay.placed_entries == 3
    assert lay.free == OAM_LIMIT      # aucune interface : tous les emplacements restent aux acteurs


# ── Le pool partagé est ce qui reste ──────────────────────────────────

def test_le_pool_partage_prend_ce_que_les_poses_laissent(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(3)])
    faire_naitre(tmp_path, scene, "Ball")
    p = _projet(tmp_path, scene=scene, prefabs=[Prefab(name="Ball")])
    lay = scene_oam_layout(p, scene)
    assert lay.shared.size == OBJECT_CAPACITY - 3
    assert lay.pool_entries == OBJECT_CAPACITY - 3         # un état d'affichage par emplacement du pool


def test_un_prefab_a_sous_arbre_prend_un_groupe_par_instance(tmp_path):
    boss = Prefab(name="Boss")
    boss.children = [Actor(name="ArmL"), Actor(name="ArmR")]   # 1 racine + 2 = 3
    scene = Scene(name="S")
    faire_naitre(tmp_path, scene, "Boss")
    p = _projet(tmp_path, scene=scene, prefabs=[boss])
    (pool,) = scene_oam_layout(p, scene).pools
    assert pool.group == 3 and pool.entries_per_instance == 3


# ── Les 128 emplacements se prennent à la frame, rien n'est réservé ───

def test_un_pool_garde_tous_ses_emplacements_au_dela_de_128(tmp_path):
    """L'OAM borne ce qui s'AFFICHE ensemble, pas ce qui existe : chaque emplacement a son état."""
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(120)])
    faire_naitre(tmp_path, scene, "Ball")
    p = _projet(tmp_path, scene=scene, prefabs=[Prefab(name="Ball")])
    lay = scene_oam_layout(p, scene)
    assert lay.shared.size == OBJECT_CAPACITY - 120 == lay.shared.entries
    assert lay.table_size == OBJECT_CAPACITY and lay.over_budget is False
    assert lay.requested == OBJECT_CAPACITY                    # la demande reste visible


def test_tous_les_acteurs_poses_ont_un_etat_au_dela_de_128(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(130)])
    faire_naitre(tmp_path, scene, "Ball")
    p = _projet(tmp_path, scene=scene, prefabs=[Prefab(name="Ball")])
    lay = scene_oam_layout(p, scene)
    assert lay.placed_entries == 130
    assert lay.placed_entry == list(range(130))
    assert lay.shared.entry_start == 130


# ── Le poste UI est nul en B1 (décomposition par scène = B2) ──────────

def test_ui_est_nul_en_b1(tmp_path):
    scene = Scene(name="S", actors=[Actor(name="A")])
    p = _projet(tmp_path, scene=scene)
    assert scene_ui_obj_slots(scene, p) == 0
    assert scene_oam_layout(p, scene).ui == 0


# ── Le validateur ne bloque que l'interface et la capacité ────────────

def test_le_validateur_se_tait_quand_les_acteurs_depassent_128(tmp_path):
    """Un surplus d'acteurs n'est un souci qu'à l'écran, au jeu : pas d'avertissement au build."""
    from core.validator import ValidationContext, _check_actor_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(130)])
    faire_naitre(tmp_path, scene, "Ball")
    p = _projet(tmp_path, scene=scene, prefabs=[Prefab(name="Ball")])
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


# ── Un prefab spawné naît dans le pool, sans rien à déclarer ──────────

def test_un_prefab_spawne_a_un_modele_sans_rien_declarer(tmp_path):
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(125)])
    faire_naitre(tmp_path, scene, "Ball")
    ball = Prefab(name="Ball")
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    assert scene_has_model(p, scene, ball)
    assert scene_oam_layout(p, scene).pools[0].shared


def test_un_prefab_non_spawne_n_a_pas_de_modele(tmp_path):
    scene = Scene(name="S")
    faire_naitre(tmp_path, scene, "Ball")
    ball = Prefab(name="Ball")
    p = _projet(tmp_path, scene=scene, prefabs=[ball])
    scene.script = ""
    assert not scene_has_model(p, scene, ball)


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
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(36)])
    p = _projet(tmp_path, scene=scene)
    _tout_affine(p)
    ctx = ValidationContext(p)
    _check_affine_budget(ctx)
    assert ctx.errors == []
    assert len(ctx.warnings) == 1
    assert "36 affine matrices" in ctx.warnings[0].message and "last 4" in ctx.warnings[0].message


def test_les_instances_nees_ne_reservent_pas_de_matrice(tmp_path):
    """Les matrices des acteurs posés sont réservées au build ; une instance née prend, à la frame, une de celles
    qui restent : elle n'entre pas dans la demande du build."""
    from codegen.oam_alloc import scene_affine_requests
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(26)])
    faire_naitre(tmp_path, scene, "Ball")
    p = _projet(tmp_path, scene=scene, prefabs=[Prefab(name="Ball")])
    _tout_affine(p)
    assert scene_affine_requests(p, scene) == 26


def test_le_validateur_se_tait_sous_32_matrices(tmp_path):
    from core.validator import ValidationContext, _check_affine_budget
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(32)])
    p = _projet(tmp_path, scene=scene)
    _tout_affine(p)
    ctx = ValidationContext(p)
    _check_affine_budget(ctx)
    assert ctx.warnings == []
