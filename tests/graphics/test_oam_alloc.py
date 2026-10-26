"""L'allocateur OAM per-scène.

`oam_alloc.scene_oam_layout` est la source de vérité de la géométrie OAM d'une
scène : ses acteurs actifs d'abord (base 0), puis le pool partagé des acteurs qui
y naissent. Ces tests fixent le contrat que `headers` et `main_gen` lisent — base 0
par scène, symboles de modèle préfixés par la scène, et `g_actors` dimensionné sur
le MAX des scènes (pas la somme).
"""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from oam_fixtures import tout_afficher, donner_un_sprite, faire_naitre
from codegen.oam_alloc import OAM_LIMIT, OBJECT_CAPACITY, scene_oam_layout, scene_has_model
from codegen.oam_budget import project_actor_count, project_oam_entry_count
from codegen.pool_model import prefab_group


def _projet(tmp_path, *, scenes, prefabs=None, sprites=True) -> Project:
    p = Project(tmp_path)
    p.scenes.items = list(scenes)
    p.prefabs.items = list(prefabs or [])
    if sprites:
        tout_afficher(p)
    return p


# ── Base 0 par scène ──────────────────────────────────────────────────

def test_le_pool_partage_part_apres_les_acteurs_actifs(tmp_path):
    scene = Scene(name="S", actors=[Actor(name="A"), Actor(name="B")])
    faire_naitre(tmp_path, scene, "Ball")
    p = _projet(tmp_path, scenes=[scene], prefabs=[Prefab(name="Ball")])
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 2
    assert lay.shared.start == 2                 # juste après les 2 acteurs, base 0
    assert lay.shared.size == OBJECT_CAPACITY - 2 and lay.shared.entry_start == 2


def test_chaque_scene_repart_de_zero(tmp_path):
    """Deux scènes, deux pools qui partent chacun de leur propre base 0 — aucun ne porte les acteurs de l'autre."""
    s1 = Scene(name="Menu", actors=[Actor(name="Cursor")])
    s2 = Scene(name="Level", actors=[Actor(name=f"E{i}") for i in range(5)])
    faire_naitre(tmp_path, s2, "Ball")
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[Prefab(name="Ball")])
    l1, l2 = scene_oam_layout(p, s1), scene_oam_layout(p, s2)
    assert l1.pools == [] and l1.shared is None and l1.table_size == 1
    assert l2.shared.start == 5 and l2.actors == OBJECT_CAPACITY


# ── Symboles de modèle préfixés par la scène ──────────────────────────

def test_symbole_de_modele_prefixe_par_la_scene(tmp_path):
    s1, s2 = Scene(name="Menu"), Scene(name="Level")
    faire_naitre(tmp_path, s1, "Ball")
    faire_naitre(tmp_path, s2, "Ball")
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[Prefab(name="Ball")])
    assert scene_oam_layout(p, s1).pools[0].sym == "Menu_Ball"
    assert scene_oam_layout(p, s2).pools[0].sym == "Level_Ball"


# ── Un prefab que personne ne fait naître n'a pas de modèle ───────────

def test_un_prefab_non_spawne_n_a_pas_de_modele(tmp_path):
    """Les champs hérités `Prefab.max_instances` et `Scene.prefab_pools` n'existent plus : un prefab n'a un modèle
    dans une scène que si un script de cette scène le spawne (ou si des acteurs posés en sont des copies)."""
    ball = Prefab(name="Ball")
    assert not hasattr(ball, "max_instances") and not hasattr(Scene(name="S"), "prefab_pools")
    scene = Scene(name="S")
    p = _projet(tmp_path, scenes=[scene], prefabs=[ball])
    assert not scene_has_model(p, scene, ball)
    assert scene_oam_layout(p, scene).pools == []


def test_une_scene_ne_paie_que_ce_qu_elle_fait_naitre(tmp_path):
    s1 = Scene(name="Menu")                          # ne spawne rien
    s2 = Scene(name="Level")
    faire_naitre(tmp_path, s2, "Ball")
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[Prefab(name="Ball")])
    assert scene_oam_layout(p, s1).pool_slots == 0
    assert scene_oam_layout(p, s2).pool_slots == OBJECT_CAPACITY


# ── g_actors = MAX des scènes, pas la somme ───────────────────────────

def test_taille_g_actors_est_le_max_pas_la_somme(tmp_path):
    s1 = Scene(name="Menu", actors=[Actor(name="Cursor")])
    s2 = Scene(name="Level", actors=[Actor(name=f"E{i}") for i in range(4)])
    faire_naitre(tmp_path, s2, "Ball")
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[Prefab(name="Ball")])
    assert project_actor_count(p) == OBJECT_CAPACITY        # le pool de Level couvre la scène : max, pas somme


def test_projet_vide_plancher_a_un(tmp_path):
    p = _projet(tmp_path, scenes=[Scene(name="S")])
    assert project_actor_count(p) == 1         # Actor g_actors[0] ne compile pas
    assert project_oam_entry_count(p) == 1     # OamEntry g_oam_entries[0] non plus


def test_sans_interface_les_deux_tables_ont_la_meme_taille(tmp_path):
    """Sans OBJ d'interface, un acteur = une entrée de même indice : les deux tables se dimensionnent pareil et le
    pool commence au même rang dans les deux."""
    s = Scene(name="Level", actors=[Actor(name=f"E{i}") for i in range(4)])
    faire_naitre(tmp_path, s, "Ball")
    p = _projet(tmp_path, scenes=[s], prefabs=[Prefab(name="Ball")])
    assert project_oam_entry_count(p) == project_actor_count(p) == OBJECT_CAPACITY
    sh = scene_oam_layout(p, s).shared
    assert sh.entry_start == sh.start == 4


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


def test_un_marqueur_de_prefab_a_un_emplacement_mais_pas_de_rang_d_affichage(tmp_path):
    """Racine + point de tir (sans sprite) + bras : un groupe de 3 emplacements, dont 2 affichent."""
    boss = Prefab(name="Boss")
    muzzle, arm = Prefab(name="Muzzle"), Prefab(name="Arm")
    boss.children = [muzzle, arm]
    scene = Scene(name="S", actors=[Actor(name="Hero")])
    faire_naitre(tmp_path, scene, "Boss")
    p = _projet(tmp_path, scenes=[scene], prefabs=[boss], sprites=False)
    donner_un_sprite(p, scene.actors[0])
    donner_un_sprite(p, boss)
    donner_un_sprite(p, arm)
    lay = scene_oam_layout(p, scene)
    (pool,) = lay.pools
    assert pool.group == 3 and pool.member_entries == [0, -1, 1]
    assert pool.entries_per_instance == 2
    assert (lay.shared.start, lay.shared.entry_start) == (1, 1)
    # une entrée d'état par emplacement du pool, marqueur compris (la partie k est à l'entrée de son emplacement)
    assert lay.shared.entries == lay.shared.size


def test_l_interface_n_a_pas_d_etat_d_acteur_elle_tient_le_debut_de_l_oam(tmp_path, monkeypatch):
    """3 OBJ d'interface : ils tiennent les 3 premiers EMPLACEMENTS de l'OAM, fixes, et ne sont ni
    des acteurs ni des états d'affichage. Les états du pool suivent ceux des posés."""
    import codegen.oam_alloc as oam_alloc
    monkeypatch.setattr(oam_alloc, "scene_ui_obj_slots", lambda scene, project: 3)
    s = Scene(name="Level", actors=[Actor(name="C"), Actor(name="E0")])
    faire_naitre(tmp_path, s, "Ball")
    p = _projet(tmp_path, scenes=[s], prefabs=[Prefab(name="Ball")], sprites=False)
    donner_un_sprite(p, s.actors[1])            # C n'affiche rien
    donner_un_sprite(p, p.prefabs.items[0])
    lay = scene_oam_layout(p, s)
    assert lay.ui == 3
    assert (lay.shared.start, lay.shared.entry_start) == (2, 1)     # 1 posé à sprite : le pool suit, l'UI n'y est pas
    assert lay.actors == OBJECT_CAPACITY and lay.table_size == 1 + lay.shared.size


# ── Groupes (prefab à sous-arbre) ─────────────────────────────────────

def test_prefab_a_sous_arbre_occupe_un_groupe_par_instance(tmp_path):
    boss = Prefab(name="Boss")
    boss.children = [Actor(name="ArmL"), Actor(name="ArmR")]   # groupe = 3
    scene = Scene(name="S")
    faire_naitre(tmp_path, scene, "Boss")
    p = _projet(tmp_path, scenes=[scene], prefabs=[boss])
    assert prefab_group(boss) == 3
    pool = scene_oam_layout(p, scene).pools[0]
    assert pool.group == 3 and pool.model_id == 1


# ── Acteurs inactifs : comptés comme le build les traite (exclus) ─────

def test_les_acteurs_inactifs_ne_sont_pas_comptes(tmp_path):
    a, b = Actor(name="A"), Actor(name="B")
    b.active = False
    scene = Scene(name="S", actors=[a, b])
    p = _projet(tmp_path, scenes=[scene])
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 1


# ── L'interface ne décale rien dans l'espace d'état ────────────────────

def test_ui_obj_ne_decale_pas_les_etats_du_pool(tmp_path, monkeypatch):
    """La bande d'interface tient le début de l'OAM matérielle ; `g_actors` ET `g_oam_entries`
    ne grandissent pas pour elle (les OBJ d'interface ne sont pas des acteurs et n'ont pas d'état)."""
    import codegen.oam_alloc as oa
    monkeypatch.setattr(oa, "scene_ui_obj_slots", lambda scene, project: 5)
    scene = Scene(name="S", actors=[Actor(name="A"), Actor(name="B")])
    faire_naitre(tmp_path, scene, "Ball")
    p = _projet(tmp_path, scenes=[scene], prefabs=[Prefab(name="Ball")])
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 2 and lay.ui == 5
    assert lay.shared.entry_start == 2      # derrière les 2 états des posés, l'UI n'y est pas
    assert lay.shared.start == 2
    assert project_oam_entry_count(p) == project_actor_count(p) == OBJECT_CAPACITY


# ── Déterminisme ──────────────────────────────────────────────────────

def test_layout_deterministe(tmp_path):
    scene = Scene(name="S", actors=[Actor(name="A")])
    faire_naitre(tmp_path, scene, "Boss", "Ball")
    p = _projet(tmp_path, scenes=[scene], prefabs=[Prefab(name="Ball"), Prefab(name="Boss")])
    a = [(pl.sym, pl.model_id) for pl in scene_oam_layout(p, scene).pools]
    b = [(pl.sym, pl.model_id) for pl in scene_oam_layout(p, scene).pools]
    assert a == b
    # Ordre = ordre du catalogue de prefabs (stable), pas celui des appels dans le script.
    assert [s for s, _ in a] == ["S_Ball", "S_Boss"]
