"""L'allocateur OAM per-scène.

`oam_alloc.scene_oam_layout` est la source de vérité de la géométrie OAM d'une
scène : ses acteurs actifs d'abord (base 0), puis les pools qu'ELLE déclare, à
leur place. Ces tests fixent le contrat que `headers`, `main_gen` et la façade
`actor_budget` lisent — base 0 par scène, symboles de pool préfixés par la
scène, pas de repli `max_instances`, et `g_actors` dimensionné sur le MAX des
scènes (pas la somme).
"""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from oam_fixtures import tout_afficher, donner_un_sprite
from codegen.oam_alloc import (
    OAM_LIMIT, scene_oam_layout, project_actor_count, project_oam_entry_count,
    scene_pool_instances, prefab_group,
)


def _a_part(nom: str) -> Prefab:
    """Un prefab qui garde sa réserve À LUI : un interacteur n'entre pas dans le pool partagé
    (`oam_alloc.is_plain_model`), donc il se dimensionne par `Scene.prefab_pools`."""
    pf = Prefab(name=nom)
    pf.actor.is_player = True
    return pf


def _projet(tmp_path, *, scenes, prefabs=None, sprites=True) -> Project:
    p = Project(tmp_path)
    p.scenes.items = list(scenes)
    p.prefabs.items = list(prefabs or [])
    if sprites:
        tout_afficher(p)
    return p


# ── Base 0 par scène ──────────────────────────────────────────────────

def test_pools_partent_apres_les_acteurs_actifs(tmp_path):
    ball = _a_part("Ball")
    scene = Scene(name="S", actors=[Actor(name="A"), Actor(name="B")])
    scene.prefab_pools = {"Ball": 4}
    p = _projet(tmp_path, scenes=[scene], prefabs=[ball])
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 2
    (pool,) = lay.pools
    assert pool.start == 2          # juste après les 2 acteurs, base 0
    assert pool.size == 4 and lay.table_size == 6


def test_chaque_scene_repart_de_zero(tmp_path):
    """Deux scènes, deux plages qui partent chacune de leur propre base 0 —
    aucune ne porte les acteurs de l'autre."""
    ball = _a_part("Ball")
    s1 = Scene(name="Menu", actors=[Actor(name="Cursor")])
    s2 = Scene(name="Level", actors=[Actor(name=f"E{i}") for i in range(5)])
    s2.prefab_pools = {"Ball": 8}
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[ball])
    l1, l2 = scene_oam_layout(p, s1), scene_oam_layout(p, s2)
    assert l1.pools == [] and l1.table_size == 1
    assert l2.pools[0].start == 5 and l2.table_size == 13


# ── Symboles de pool préfixés par la scène ────────────────────────────

def test_symbole_de_pool_prefixe_par_la_scene(tmp_path):
    ball = _a_part("Ball")
    s1 = Scene(name="Menu"); s1.prefab_pools = {"Ball": 2}
    s2 = Scene(name="Level"); s2.prefab_pools = {"Ball": 2}
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[ball])
    assert scene_oam_layout(p, s1).pools[0].sym == "Menu_Ball"
    assert scene_oam_layout(p, s2).pools[0].sym == "Level_Ball"


# ── Pas de repli max_instances, plus de max inter-scènes ──────────────

def test_pas_de_repli_sur_max_instances(tmp_path):
    """Un prefab qu'aucune scène ne déclare n'est plus poolé. Le champ hérité
    `Prefab.max_instances` a été RETIRÉ en T7 : le pool ne vit que sur la scène,
    et un prefab non déclaré n'a aucune plage."""
    ball = _a_part("Ball")
    assert not hasattr(ball, "max_instances")     # le champ n'existe plus
    scene = Scene(name="S")
    p = _projet(tmp_path, scenes=[scene], prefabs=[ball])
    assert scene_pool_instances(p, scene, ball) == 0
    assert scene_oam_layout(p, scene).pools == []


def test_une_scene_ne_paie_que_ce_qu_elle_declare(tmp_path):
    ball = _a_part("Ball")
    s1 = Scene(name="Menu")                          # ne spawne rien
    s2 = Scene(name="Level"); s2.prefab_pools = {"Ball": 10}
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[ball])
    assert scene_oam_layout(p, s1).pool_slots == 0
    assert scene_oam_layout(p, s2).pool_slots == 10


# ── g_actors = MAX des scènes, pas la somme ───────────────────────────

def test_taille_g_actors_est_le_max_pas_la_somme(tmp_path):
    ball = _a_part("Ball")
    s1 = Scene(name="Menu", actors=[Actor(name="Cursor")])          # used 1
    s2 = Scene(name="Level", actors=[Actor(name=f"E{i}") for i in range(4)])
    s2.prefab_pools = {"Ball": 6}                                   # used 10
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[ball])
    assert project_actor_count(p) == 10        # max(1, 10), pas 11


def test_projet_vide_plancher_a_un(tmp_path):
    p = _projet(tmp_path, scenes=[Scene(name="S")])
    assert project_actor_count(p) == 1         # Actor g_actors[0] ne compile pas
    assert project_oam_entry_count(p) == 1     # OamEntry g_oam_entries[0] non plus


def test_sans_interface_les_deux_tables_ont_la_meme_taille(tmp_path):
    """Sans OBJ d'interface, un acteur = une entrée de même indice : les deux
    tables se dimensionnent pareil et le décalage des pools est nul."""
    s = Scene(name="Level", actors=[Actor(name=f"E{i}") for i in range(4)])
    s.prefab_pools = {"Ball": 6}
    p = _projet(tmp_path, scenes=[s], prefabs=[_a_part("Ball")])
    assert project_oam_entry_count(p) == project_actor_count(p) == 10
    pool = scene_oam_layout(p, s).pools[0]
    assert pool.entry_start == pool.start == 4


# ── Marche 0b : seul un porteur de sprite occupe une entrée OAM ────────

def test_un_acteur_sans_sprite_n_a_pas_d_entree(tmp_path):
    """Un contrôleur ou un déclencheur existe (g_actors) sans rien afficher : il ne
    réserve aucune entrée, et les entrées des autres se compactent."""
    a, ctl, b = Actor(name="A"), Actor(name="Controller"), Actor(name="B")
    scene = Scene(name="S", actors=[a, ctl, b])
    p = _projet(tmp_path, scenes=[scene], sprites=False)
    donner_un_sprite(p, a)
    donner_un_sprite(p, b)
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 3 and lay.placed_entry == [0, -1, 1]
    assert lay.table_size == 2 and lay.actors == 3
    assert project_actor_count(p) == 3 and project_oam_entry_count(p) == 2


def test_un_marqueur_de_prefab_n_a_pas_d_entree(tmp_path):
    """Racine + point de tir (sans sprite) + bras : 3 acteurs par instance, mais
    2 entrées OAM. L'entrée d'un membre = début de l'instance + son rang."""
    boss = _a_part("Boss")
    muzzle, arm = _a_part("Muzzle"), _a_part("Arm")
    boss.children = [muzzle, arm]
    scene = Scene(name="S", actors=[Actor(name="Hero")])
    scene.prefab_pools = {"Boss": 2}
    p = _projet(tmp_path, scenes=[scene], prefabs=[boss], sprites=False)
    donner_un_sprite(p, scene.actors[0])
    donner_un_sprite(p, boss)
    donner_un_sprite(p, arm)
    lay = scene_oam_layout(p, scene)
    (pool,) = lay.pools
    assert pool.group == 3 and pool.member_entries == [0, -1, 1]
    assert (pool.size, pool.entry_size) == (6, 4)
    assert (pool.start, pool.entry_start) == (1, 1)
    assert lay.actors == 7 and lay.table_size == 5


def test_l_interface_n_a_pas_d_etat_d_acteur_elle_tient_le_debut_de_l_oam(tmp_path, monkeypatch):
    """3 OBJ d'interface : ils tiennent les 3 premiers EMPLACEMENTS de l'OAM, fixes, et ne sont ni
    des acteurs ni des états d'affichage. Les états des pools suivent ceux des posés."""
    import codegen.oam_alloc as oam_alloc
    monkeypatch.setattr(oam_alloc, "scene_ui_obj_slots", lambda scene, project: 3)
    s = Scene(name="Level", actors=[Actor(name="C"), Actor(name="E0")])
    s.prefab_pools = {"Ball": 6}
    p = _projet(tmp_path, scenes=[s], prefabs=[_a_part("Ball")], sprites=False)
    donner_un_sprite(p, s.actors[1])            # C n'affiche rien
    donner_un_sprite(p, p.prefabs.items[0])
    lay = scene_oam_layout(p, s)
    assert lay.ui == 3
    (pool,) = lay.pools
    assert (pool.start, pool.entry_start) == (2, 1)     # 1 posé à sprite : le pool suit, l'UI n'y est pas
    assert lay.actors == 8 and lay.table_size == 7 and lay.requested == 10


# ── Groupes (prefab à sous-arbre) ─────────────────────────────────────

def test_prefab_a_sous_arbre_occupe_un_groupe_par_instance(tmp_path):
    boss = _a_part("Boss")
    boss.children = [Actor(name="ArmL"), Actor(name="ArmR")]   # groupe = 3
    scene = Scene(name="S"); scene.prefab_pools = {"Boss": 4}
    p = _projet(tmp_path, scenes=[scene], prefabs=[boss])
    assert prefab_group(boss) == 3
    pool = scene_oam_layout(p, scene).pools[0]
    assert pool.group == 3 and pool.instances == 4 and pool.size == 12


# ── Acteurs inactifs : comptés comme le build les traite (exclus) ─────

def test_les_acteurs_inactifs_ne_sont_pas_comptes(tmp_path):
    a, b = Actor(name="A"), Actor(name="B")
    b.active = False
    scene = Scene(name="S", actors=[a, b])
    p = _projet(tmp_path, scenes=[scene])
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 1


# ── L'interface ne décale rien dans l'espace d'état ────────────────────

def test_ui_obj_ne_decale_pas_les_etats_des_pools(tmp_path, monkeypatch):
    """La bande d'interface tient le début de l'OAM matérielle ; `g_actors` ET `g_oam_entries`
    ne grandissent pas pour elle (les OBJ d'interface ne sont pas des acteurs et n'ont pas d'état)."""
    import codegen.oam_alloc as oa
    monkeypatch.setattr(oa, "scene_ui_obj_slots", lambda scene, project: 5)
    ball = _a_part("Ball")
    scene = Scene(name="S", actors=[Actor(name="A"), Actor(name="B")])
    scene.prefab_pools = {"Ball": 4}
    p = _projet(tmp_path, scenes=[scene], prefabs=[ball])
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 2 and lay.ui == 5
    assert lay.pools[0].entry_start == 2    # derrière les 2 états des posés, l'UI n'y est pas
    assert lay.pools[0].start == 2
    assert lay.table_size == 6 and project_oam_entry_count(p) == 6
    assert project_actor_count(p) == 6


# ── Déterminisme ──────────────────────────────────────────────────────

def test_layout_deterministe(tmp_path):
    ball, boss = _a_part("Ball"), _a_part("Boss")
    scene = Scene(name="S", actors=[Actor(name="A")])
    scene.prefab_pools = {"Ball": 3, "Boss": 2}
    p = _projet(tmp_path, scenes=[scene], prefabs=[ball, boss])
    a = [(pl.sym, pl.start, pl.size) for pl in scene_oam_layout(p, scene).pools]
    b = [(pl.sym, pl.start, pl.size) for pl in scene_oam_layout(p, scene).pools]
    assert a == b
    # Ordre = ordre du catalogue de prefabs (stable), pas celui du dict.
    assert [s for s, _, _ in a] == ["S_Ball", "S_Boss"]
