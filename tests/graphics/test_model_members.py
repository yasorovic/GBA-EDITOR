"""Un acteur posé qui est une INSTANCE d'un prefab rejoint le modèle de ce prefab.

Il partage le code du modèle (compilé une fois) et n'a que ses valeurs d'instance. Pour cela il doit
être sur le même chemin de compilation que lui : lié (`actor_prefab_linked`), mêmes sprites, mêmes
Sfx, prefab plat, pas parent d'un autre acteur posé. Les autres restent des singletons.
"""
from __future__ import annotations

import copy

from core.models.components import ScriptComponent
from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from oam_fixtures import tout_afficher, donner_un_sprite, faire_naitre
from codegen.oam_alloc import scene_oam_layout, OBJECT_CAPACITY
from codegen.pool_model import model_members


def _projet(tmp_path, *, n=3, spawned=False, script=True):
    """Un prefab `Coin` et `n` acteurs posés qui en sont des copies liées. `spawned` : un script de la scène fait
    aussi naître des `Coin`, qui prennent leurs emplacements dans le pool partagé."""
    coin = Prefab(name="Coin")
    if script:
        coin.actor.components.append(ScriptComponent(script="assets/coin.lua"))
    scene = Scene(name="S")
    if spawned:
        faire_naitre(tmp_path, scene, "Coin")
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [coin]
    donner_un_sprite(p, coin)
    scene.actors = [Actor(name=f"C{i}", prefab_name="Coin", components=copy.deepcopy(coin.components))
                    for i in range(n)]
    tout_afficher(p)
    return p, scene, coin


def test_les_copies_liees_rejoignent_le_modele(tmp_path):
    p, scene, _coin = _projet(tmp_path, n=3)
    assert model_members(p, scene.actors) == {"Coin": [0, 1, 2]}
    (pool,) = scene_oam_layout(p, scene).pools
    assert pool.members == [0, 1, 2] and not pool.shared       # aucun spawn : que ses instances posées
    assert scene_oam_layout(p, scene).shared is None


def test_les_instances_nees_s_ajoutent_aux_membres(tmp_path):
    p, scene, _coin = _projet(tmp_path, n=2, spawned=True)
    lay = scene_oam_layout(p, scene)
    (pool,) = lay.pools
    assert pool.shared and len(pool.members) == 2
    # Seul le pool partagé prend des emplacements d'acteurs et des états : les membres ont ceux de la scène.
    assert lay.shared.start == 2 and lay.shared.size == OBJECT_CAPACITY - 2
    assert lay.shared.entry_start == 2 and lay.shared.entries == lay.shared.size
    assert lay.actors == OBJECT_CAPACITY


def test_un_acteur_qui_derive_du_script_reste_un_singleton(tmp_path):
    p, scene, _coin = _projet(tmp_path, n=3)
    script = next(c for c in scene.actors[1].components if isinstance(c, ScriptComponent))
    script.script = "assets/autre.lua"
    assert model_members(p, scene.actors) == {"Coin": [0, 2]}


def test_un_acteur_qui_change_de_sprite_reste_un_singleton(tmp_path):
    """Un nom d'état se résout dans le sprite : un autre sprite, c'est un autre code."""
    from core.models.components import SpriteComponent
    from core.models.sprite import SpriteAsset
    p, scene, _coin = _projet(tmp_path, n=3)
    p.sprites.append(SpriteAsset(name="Autre", asset="autre.png"))
    sprite = next(c for c in scene.actors[2].components if isinstance(c, SpriteComponent))
    sprite.sprite_name = "Autre"
    assert model_members(p, scene.actors) == {"Coin": [0, 1]}


def test_un_acteur_non_lie_a_un_prefab_n_est_jamais_membre(tmp_path):
    p, scene, _coin = _projet(tmp_path, n=2)
    scene.actors[0].prefab_name = None
    assert model_members(p, scene.actors) == {"Coin": [1]}


def test_un_parent_d_un_autre_acteur_pose_reste_un_singleton(tmp_path):
    """`self.Enfant` se résout au build dans l'acteur : un modèle partagé ne le saurait pas."""
    p, scene, _coin = _projet(tmp_path, n=3)
    scene.actors[2].parent = "C0"
    assert model_members(p, scene.actors) == {"Coin": [1, 2]}


def test_un_prefab_a_sous_arbre_n_a_pas_de_membres(tmp_path):
    p, scene, coin = _projet(tmp_path, n=2)
    coin.children = [Actor(name="Arm")]
    assert model_members(p, scene.actors) == {}


def test_un_script_c_natif_n_est_pas_partage(tmp_path):
    p, scene, coin = _projet(tmp_path, n=2)
    next(c for c in coin.actor.components if isinstance(c, ScriptComponent)).script = "assets/coin.c"
    for a in scene.actors:
        next(c for c in a.components if isinstance(c, ScriptComponent)).script = "assets/coin.c"
    assert model_members(p, scene.actors) == {}


def test_les_exports_d_un_membre_sont_ceux_de_son_acteur(tmp_path):
    from codegen.runtime_codegen.lua_compiler import member_export_inits
    p, scene, _coin = _projet(tmp_path, n=2)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "coin.lua").write_text(
        'exports = {\n  value = { type = "int", default = 1 },\n'
        '  kind = { type = "enum", default = "COPPER", values = {"COPPER", "GOLD"} },\n}\n',
        encoding="utf-8")
    script = next(c for c in scene.actors[1].components if isinstance(c, ScriptComponent))
    script.exports_values = {"value": 50, "kind": "GOLD"}
    assert member_export_inits(p, scene, scene.actors[0]) == [("value", "int", "1"), ("kind", "enum", "0")]
    assert member_export_inits(p, scene, scene.actors[1]) == [("value", "int", "50"), ("kind", "enum", "1")]


def test_la_table_du_modele_commence_par_ses_membres(tmp_path):
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    p, scene, _coin = _projet(tmp_path, n=2, spawned=True)
    code = "\n".join(section_spawn(scene_pi(p, scene), p, None))
    assert "const ModelSlot g_model_S_Coin[2] = {" in code
    assert code.index("{1, 1},   /* posé */") > code.index("{0, 0},   /* posé */")


def test_les_appels_de_code_d_un_membre_vont_au_modele(tmp_path):
    from codegen.runtime_codegen.gen_pool import scene_pi, dispatch_sym
    p, scene, _coin = _projet(tmp_path, n=2)
    singleton = Actor(name="Door")
    scene.actors.append(singleton)
    sym_of = dispatch_sym(p, scene, [(a, None) for a in scene.actors], scene_pi(p, scene))
    assert sym_of("S", "C0") == "S_Coin" and sym_of("S", "C1") == "S_Coin"
    assert sym_of("S", "Door") == "S_Door"


def test_l_identite_du_modele_sans_spawn_ne_vaut_aucun_nom(tmp_path):
    """`other.name == "Coin"` ne doit pas chevaucher l'identité d'un autre modèle."""
    from codegen.runtime_codegen.headers import generate_actor_types
    p, scene, _coin = _projet(tmp_path, n=2)
    p.src_dir.mkdir(parents=True, exist_ok=True)
    generate_actor_types(p)
    text = (p.src_dir / "actor_types.h").read_text(encoding="utf-8")
    assert "#define ACTOR_S_COIN -1" in text
    assert "#define MODEL_S_COIN_COUNT 2" in text and "#define ROOT_TYPE_ID_S_COIN 0" in text


def test_un_spawn_qui_reprend_l_emplacement_d_un_membre_lui_garde_son_identite(tmp_path):
    """`name` indexe la table des Sfx de destruction : -1 (le modèle sans réserve) en sortirait."""
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    p, scene, _coin = _projet(tmp_path, n=2, spawned=True)
    code = "\n".join(section_spawn(scene_pi(p, scene), p, None))
    assert ".name = _n < 2 ? _i : ACTOR_S_COIN" in code


def test_un_modele_sans_spawn_n_ecrit_pas_de_sfx_de_destruction_a_son_nom(tmp_path):
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sfx_trigger import sfx_on_destroy_table
    p, scene, _coin = _projet(tmp_path, n=2)
    d = {"scene": scene, "scene_actors": [(a, None) for a in scene.actors]}
    sfx_on_destroy_table(p, [d], [scene_pi(p, scene)])      # ne lève pas (indice hors table)


def test_un_acteur_pose_du_meme_nom_que_son_prefab_garde_sa_constante(tmp_path):
    """Une instance liée porte par défaut le nom de son prefab (`Player`). La constante `ACTOR_<Scène>_PLAYER` désigne alors
    l'acteur posé : la redéfinir en -1 (« modèle sans spawn ») faisait lire `g_actors[-1]` à `actor:get("Player")`."""
    from codegen.runtime_codegen.headers import generate_actor_types
    p, scene, _coin = _projet(tmp_path, n=2)
    scene.actors[0].name = "Coin"                     # le même nom que le prefab
    p.src_dir.mkdir(parents=True, exist_ok=True)
    generate_actor_types(p)
    text = (p.src_dir / "actor_types.h").read_text(encoding="utf-8")
    assert text.count("#define ACTOR_S_COIN ") == 1 and "#define ACTOR_S_COIN 0" in text
    assert "#define MODEL_S_COIN_COUNT 2" in text            # le modèle existe toujours, sans constante en double


def test_deux_enfants_de_parents_differents_partagent_un_type(tmp_path):
    """Un ENFANT reste partageable, un parent non (cf. `pool_model.parent_names`).

    Rien de la hiérarchie n'entre dans le code d'un enfant : le lien est posé par `scene_init`, emplacement par
    emplacement, et lu au runtime dans `g_slot_link`. Deux enfants de parents différents, et même un acteur sans
    parent de contenu identique, tiennent donc dans un seul modèle. Le jour où un accès serait résolu au build dans
    l'enfant (comme `self.Enfant` l'est dans le parent), ce test tomberait : c'est son rôle."""
    from codegen.runtime_codegen.gen_actor_hierarchy import placed_link_lines

    p = Project(tmp_path)
    scene = Scene(name="S")
    enfant = ScriptComponent(script="assets/enfant.lua")
    scene.actors = [Actor(name="P1", components=[ScriptComponent(script="assets/pere.lua")]),
                    Actor(name="P2", components=[ScriptComponent(script="assets/pere.lua")]),
                    Actor(name="E1", components=[copy.deepcopy(enfant)]),
                    Actor(name="E2", components=[copy.deepcopy(enfant)]),
                    Actor(name="Libre", components=[copy.deepcopy(enfant)])]
    scene.actors[2].parent, scene.actors[3].parent = "P1", "P2"
    p.scenes.items = [scene]
    tout_afficher(p)

    layout = scene_oam_layout(p, scene)
    assert layout.placed_type_ids[0] != layout.placed_type_ids[1]          # deux parents, deux modèles
    assert layout.placed_type_ids[2] == layout.placed_type_ids[3] == layout.placed_type_ids[4]
    assert layout.singleton_groups == [[2, 3, 4]]

    # Et ce que le modèle partagé ne porte pas, `scene_init` le pose par emplacement : chacun son parent.
    liens = "\n".join(placed_link_lines([(a, None) for a in scene.actors], 0))
    assert liens.count("actor_link_slot(") == 2
    assert "actor_link_slot(2, 0, 1," in liens and "actor_link_slot(3, 1, 1," in liens
