"""Le pool PARTAGÉ d'une scène : un seul tas d'emplacements pour tous les modèles qui y naissent.

Plus de réserve par prefab : tout modèle que la scène spawne (plat, à parties, affine, interacteur, bloqueur)
naît dans les emplacements qui restent après les acteurs posés, `OBJECT_CAPACITY` en tout par scène.
"""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from core.models.components import SpriteComponent
from oam_fixtures import tout_afficher, SPRITE
from codegen.oam_alloc import OBJECT_CAPACITY, scene_oam_layout
from codegen.oam_budget import project_actor_count, project_oam_entry_count


def _scene_qui_spawne(tmp_path, *, actors=2, prefabs=("Bullet",), affines=()):
    """Une scène à `actors` acteurs posés dont un script spawne chacun des `prefabs`. Ceux de `affines` ont
    une matrice affine."""
    pfs = []
    for nom in prefabs:
        pf = Prefab(name=nom)
        if nom in affines:
            pf.actor.components.append(SpriteComponent(sprite_name=SPRITE, affine_transform=True))
        pfs.append(pf)
    scene = Scene(name="S", script="assets/s.lua", actors=[Actor(name=f"A{i}") for i in range(actors)])
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = pfs
    tout_afficher(p)
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "assets" / "s.lua").write_text(
        "function on_update()\n" + "".join(f'    actor:spawn("{n}", vec2(0, 0))\n' for n in prefabs) + "end\n",
        encoding="utf-8")
    return p, scene


def test_un_modele_qui_naît_prend_le_pool_partage(tmp_path):
    p, scene = _scene_qui_spawne(tmp_path, actors=3)
    lay = scene_oam_layout(p, scene)
    (pool,) = lay.pools
    assert pool.shared and pool.root_type_id == 1
    assert lay.shared.start == 3 and lay.shared.size == OBJECT_CAPACITY - 3
    assert lay.actors == OBJECT_CAPACITY


def test_les_etats_d_affichage_du_pool_suivent_ceux_des_poses(tmp_path):
    p, scene = _scene_qui_spawne(tmp_path, actors=3)
    sh = scene_oam_layout(p, scene).shared
    assert sh.entry_start == 3 and sh.entries == sh.size
    assert project_oam_entry_count(p) == 3 + sh.size


def test_deux_modeles_simples_partagent_le_meme_tas(tmp_path):
    p, scene = _scene_qui_spawne(tmp_path, prefabs=("Bullet", "Coin"))
    lay = scene_oam_layout(p, scene)
    ids = {pl.prefab.name: pl.root_type_id for pl in lay.pools}
    assert ids == {"Bullet": 1, "Coin": 2}
    assert len(lay.pools) == 2 and all(pl.shared for pl in lay.pools)
    assert lay.shared.size == OBJECT_CAPACITY - 2          # un seul tas, pas un par modèle


def test_un_modele_affine_naît_aussi_dans_le_pool_partage(tmp_path):
    """Plus de réserve à part : un modèle affine prend lui aussi ses emplacements dans le pool (ses matrices sont
    prises à la frame)."""
    p, scene = _scene_qui_spawne(tmp_path, actors=2, prefabs=("Bullet", "Hero"), affines=("Hero",))
    lay = scene_oam_layout(p, scene)
    assert all(pl.shared for pl in lay.pools) and lay.shared.start == 2
    assert lay.shared.size == OBJECT_CAPACITY - 2


def test_sans_modele_qui_naisse_il_n_y_a_pas_de_pool_partage(tmp_path):
    p = Project(tmp_path)
    scene = Scene(name="S", actors=[Actor(name=f"A{i}") for i in range(4)])
    p.scenes.items = [scene]
    tout_afficher(p)
    lay = scene_oam_layout(p, scene)
    assert lay.shared is None and lay.actors == 4 and project_actor_count(p) == 4


def test_une_scene_trop_pleine_le_dit(tmp_path):
    p, scene = _scene_qui_spawne(tmp_path, actors=OBJECT_CAPACITY + 1)
    lay = scene_oam_layout(p, scene)
    assert lay.over_capacity and lay.shared.size == 0
    from core.validator import ValidationContext, _check_actor_budget
    ctx = ValidationContext(p)
    _check_actor_budget(ctx)
    assert any("a scene holds" in m.message for m in ctx.errors)


def test_la_capacite_se_decide_en_un_seul_endroit(tmp_path, monkeypatch):
    import codegen.oam_alloc as oam_alloc
    monkeypatch.setattr(oam_alloc, "scene_object_capacity", lambda project, scene: 64)
    p, scene = _scene_qui_spawne(tmp_path, actors=4)
    lay = scene_oam_layout(p, scene)
    assert lay.capacity == 64 and lay.shared.size == 60 and lay.actors == 64


# ── Le C émis ─────────────────────────────────────────────────────────

def test_le_spawn_prend_le_premier_emplacement_libre_du_pool(tmp_path):
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    p, scene = _scene_qui_spawne(tmp_path)
    code = "\n".join(section_spawn(scene_pi(p, scene), p, None))
    # La recherche part du curseur, pas du début du pool : un spawn ne parcourt pas les emplacements pleins.
    assert "int _k=g_spool_free;" in code and "while(_k<g_spool_end && g_actors[_k].alive) _k++;" in code
    assert "if(_k+1>g_actor_slot_end) g_actor_slot_end=_k+1;" in code and "g_spool_free=_k+1;" in code
    assert "actor_init_slot(_i, _e," in code and ".type_id = 1" in code


def test_le_crochet_d_image_d_un_modele_se_lit_dans_son_descripteur(tmp_path):
    """Plus de `switch` par modèle pour `on_update` : la ligne du type porte le crochet, la boucle l'appelle."""
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.model_desc import model_desc_lines
    p, scene = _scene_qui_spawne(tmp_path, prefabs=("Bullet", "Coin"))
    pi = scene_pi(p, scene)
    actors = [(a, None) for a in scene.actors]
    table = model_desc_lines(p, scene, actors, pi, None, lambda sym, ev: sym.endswith("Bullet") and ev == "on_update")
    bullet = next(line for line in table if "né : Bullet" in line)
    coin = next(line for line in table if "né : Coin" in line)
    assert ".on_update=S_Bullet_on_update" in bullet
    assert "on_update" not in coin                            # ce modèle n'a pas de on_update


def _passe_rendu(p, scene, monkeypatch, variants=None, apps=None):
    """La passe d'animation et d'écriture OAM de la scène (`anim_oam_pass_lines`), ses deux générateurs remplacés :
    `variants(nom)` donne les arguments de tick de chaque porteur, `apps(nom)` ses apparences."""
    from codegen.runtime_codegen import gen_sprite
    from codegen.runtime_codegen.gen_pool import scene_pi
    if variants is not None:
        monkeypatch.setattr(gen_sprite, "anim_variants", lambda _p, owner, _sym: variants(owner.name))
    if apps is not None:
        monkeypatch.setattr(gen_sprite, "appearances", lambda _p, owner, _offs: apps(owner.name))
    actors = [(a, None) for a in scene.actors]
    return "\n".join(gen_sprite.anim_oam_pass_lines(
        p, actors, 0, scene_pi(p, scene), scene_oam_layout(p, scene), [None] * len(actors), set(), {}))


def test_l_ecriture_oam_garde_les_constantes_de_chaque_type(tmp_path, monkeypatch):
    from codegen.runtime_codegen.gen_sprite import Appearance
    from core.models.sprite import SpriteAsset
    p, scene = _scene_qui_spawne(tmp_path, prefabs=("Bullet", "Coin"))
    bases = {"Bullet": 0, "Coin": 16}
    code = _passe_rendu(p, scene, monkeypatch, variants=lambda nom: [None],
                        apps=lambda nom: [Appearance(SpriteAsset(name=nom, asset="a.png"), bases.get(nom, 32))])
    assert "int _pe=_a->oam_entry;" in code                         # l'entrée se lit dans l'emplacement, posé ou né
    assert "case 1: {" in code and "case 2: {" in code
    assert "u16 ti=(u16)(0+g_oam_entries[_pe].frame" in code
    assert "u16 ti=(u16)(16+g_oam_entries[_pe].frame" in code
    assert "g_actors[_pk]" in code


def test_deux_types_au_meme_code_partagent_un_seul_cas(tmp_path, monkeypatch):
    """Deux types dont l'animation et l'écriture OAM sont identiques n'émettent qu'un corps, sous deux étiquettes : le
    rendu est en IWRAM, une copie par type y coûtait environ 1 Ko."""
    from codegen.runtime_codegen.gen_sprite import Appearance
    from core.models.sprite import SpriteAsset
    p, scene = _scene_qui_spawne(tmp_path, prefabs=("Bullet", "Coin"))
    sprite = SpriteAsset(name="Coin", asset="a.png")
    code = _passe_rendu(p, scene, monkeypatch, variants=lambda nom: [dict(sym="sprite_Coin")],
                        apps=lambda nom: [Appearance(sprite, 0)])
    assert "        case 1:\n        case 2:" in code
    assert code.count("shadow_oam[_o].attr0") == 1 and code.count("} break;") == 1


def test_la_scene_pose_le_pool_et_une_scene_sans_pool_le_vide(tmp_path):
    from codegen.runtime_codegen.gen_pool import scene_pi
    p, scene = _scene_qui_spawne(tmp_path, actors=3)
    (shared,) = [m for m in scene_pi(p, scene) if m["shared"]]
    assert shared["spool"]["start"] == 3 and shared["spool"]["end"] == OBJECT_CAPACITY
    assert shared["spool"]["entries"] == OBJECT_CAPACITY - 3


def test_chaque_type_anime_son_sprite_par_son_code(tmp_path, monkeypatch):
    p, scene = _scene_qui_spawne(tmp_path, prefabs=("Bullet", "Coin"))
    variants = {"Bullet": [dict(sym="sprite_Bullet")]}               # les autres : un sprite fixe
    code = _passe_rendu(p, scene, monkeypatch, variants=lambda nom: variants.get(nom, [None]), apps=lambda nom: [])
    # Une boucle sur les posés puis le pool, qui les suit dans `g_actors`.
    assert "SLOT_EACH(_pk){" in code
    assert "case 1: {" in code and "case 2:" not in code                  # seul le type animé a un cas
    assert "g_oam_entries[_pe].timer++;" in code and "g_actors[_pk].facing_y" in code
    assert "sprite_Bullet_state_start" in code
    assert _passe_rendu(p, scene, monkeypatch, variants=lambda nom: [None], apps=lambda nom: []) == ""


def test_l_animation_et_l_ecriture_oam_tiennent_dans_une_seule_boucle(tmp_path, monkeypatch):
    """Un seul parcours des emplacements, et dans le cas d'un type le tick d'animation précède l'écriture OAM (qui lit
    la frame qu'il vient de poser)."""
    from codegen.runtime_codegen.gen_sprite import Appearance
    from core.models.sprite import SpriteAsset
    p, scene = _scene_qui_spawne(tmp_path, prefabs=("Bullet", "Coin"))
    variants = {"Bullet": [dict(sym="sprite_Bullet")]}
    code = _passe_rendu(p, scene, monkeypatch, variants=lambda nom: variants.get(nom, [None]),
                        apps=lambda nom: [Appearance(SpriteAsset(name=nom, asset="a.png"), 0)])
    assert code.count("SLOT_EACH(_pk){") == 1 and "POOL_EACH(" not in code
    assert "if(!_a->active) continue;" in code
    bullet = code[code.index("case 1: {"):code.index("case 2:")]
    assert bullet.index("g_oam_entries[_pe].timer++;") < bullet.index("shadow_oam[_o].attr0")   # animer, puis écrire
    coin = code[code.index("case 2:"):code.index("} break;", code.index("case 2:"))]
    assert "timer++" not in coin and "shadow_oam[_o].attr0" in coin                              # sprite fixe : écrit seulement


def test_une_copie_posee_et_le_modele_ne_partagent_leur_cas_de_rendu(tmp_path, monkeypatch):
    """Posé = spawné : la copie identique au prefab porte son type, son rendu est le même cas que celui du né. Une copie
    affine d'un prefab qui ne l'est pas garde ce type ; le cas prend alors la branche affine, que le drapeau de
    l'emplacement (`affine_slot`) choisit."""
    import copy
    from codegen.runtime_codegen.gen_affine import compute_affine_info
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import anim_oam_pass_lines
    p, scene = _scene_qui_spawne(tmp_path, actors=0, prefabs=("Coin",))
    coin = p.prefabs.items[0]
    scene.actors = [Actor(name="CoinPose", prefab_name="Coin", components=copy.deepcopy(coin.actor.components))]
    scene.actors[0].get_component("sprite").affine_transform = True
    lay = scene_oam_layout(p, scene)
    (ne,) = [m for m in scene_pi(p, scene) if m["shared"]]
    assert lay.placed_type_ids == [ne["root_type_id"]]
    actors = [(a, None) for a in scene.actors]
    code = "\n".join(anim_oam_pass_lines(p, actors, 0, scene_pi(p, scene), lay, ["S_Coin"],
                                         set(compute_affine_info(0, actors)), {}))
    assert code.count(f"case {ne['root_type_id']}: {{") == 1
    assert "if(g_oam_entries[_pe].affine_slot>=0&&_affn<32) {" in code and "int _affn = 0;" in code


# ── Blocage et interaction des instances du pool ──────────────────────

def _scene_blocage(tmp_path):
    """Un mur (boîte bloquante) et un héros (boîte solide, regard, joueur) tous deux spawnés dans le pool, plus
    un acteur posé qui bloque aussi."""
    from core.models.components import CollisionShapeComponent
    wall, hero = Prefab(name="Wall"), Prefab(name="Hero")
    wall.actor.components.append(CollisionShapeComponent(response="block", solid=False, w=16, h=16))
    hero.actor.components.append(CollisionShapeComponent(solid=True, w=16, h=16))
    hero.actor.is_player = True
    scene = Scene(name="S", script="assets/s.lua",
                  actors=[Actor(name="Rock", components=[CollisionShapeComponent(response="block", solid=False, w=16, h=16)])])
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [wall, hero]
    tout_afficher(p)
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "assets" / "s.lua").write_text(
        'function on_update()\n    actor:spawn("Wall", vec2(0, 0))\n    actor:spawn("Hero", vec2(0, 0))\nend\n',
        encoding="utf-8")
    return p, scene


def test_les_bloqueurs_et_les_mobiles_du_pool_se_decident_par_le_modele(tmp_path):
    from codegen.runtime_codegen.physics.blocks import block_tick_lines
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    p, scene = _scene_blocage(tmp_path)
    pi = scene_pi(p, scene)
    ids = {m["prefab"].name: m["root_type_id"] for m in pi if m["shared"]}
    code = "\n".join(block_tick_lines(p, scene, [(a, None) for a in scene.actors], pi, resolve_initial_appearance))
    import re
    table = lambda nom: [int(v) for v in re.search(rf"{nom}\[\d+\][^=]*=\{{([^}}]*)\}};", code)[1].split(",")]
    rock = scene_oam_layout(p, scene).placed_type_ids[0]
    mobiles, bloqueurs = table("_bk_mi"), table("_bk_bi")
    # Le héros né est le seul mobile ; le mur né et le rocher posé sont ses bloqueurs, lus par type.
    assert [k for k, i in enumerate(mobiles) if i != 255] == [ids["Hero"]]
    assert {k for k, i in enumerate(bloqueurs) if i != 255} == {ids["Wall"], rock}
    # Posés puis pool, pour le mobile comme pour ses bloqueurs.
    assert "_bk_n=block_targets(_bk_bi,_bk_list);" in code and "actors_resolve_blocks(_a,_bk_mask[_mi],_bk_run[_mi],_bk_list,_bk_n,_bk_box);" in code
    assert "SLOT_EACH(_k){" in code


def test_sans_instance_du_pool_qui_bloque_aucun_appel_au_pool(tmp_path):
    from codegen.runtime_codegen.physics.blocks import block_tick_lines
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    p, scene = _scene_blocage(tmp_path)
    p.prefabs.items = [pf for pf in p.prefabs.items if pf.name == "Hero"]      # plus de mur né
    (tmp_path / "assets" / "s.lua").write_text('function on_update()\n    actor:spawn("Hero", vec2(0, 0))\nend\n',
                                               encoding="utf-8")
    pi = scene_pi(p, scene)
    code = "\n".join(block_tick_lines(p, scene, [(a, None) for a in scene.actors], pi, resolve_initial_appearance))
    # Le héros né reste un mobile ; seul le rocher posé est un bloqueur : la liste n'a de place que pour lui.
    assert "static BlockTarget _bk_list[1]" in code and "_bk_n=block_targets(_bk_bi,_bk_list);" in code
    assert "SLOT_EACH(_k){" in code


def test_l_interaction_cherche_les_consommateurs_nes_et_reconnait_les_interacteurs_nes(tmp_path):
    from types import SimpleNamespace
    from codegen.runtime_codegen.interact_gen import interact_tick_lines
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from core.models.components import CollisionShapeComponent, InteractiveComponent
    hero, chest = Prefab(name="Hero"), Prefab(name="Chest")
    hero.actor.components.append(CollisionShapeComponent(solid=True, w=16, h=16))
    hero.actor.is_player = True
    chest.actor.components += [CollisionShapeComponent(tag="zone", w=16, h=16),
                               InteractiveComponent(interaction="facing", box_tag="zone")]
    scene = Scene(name="S", script="assets/s.lua", actors=[Actor(name="A")])
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [hero, chest]
    tout_afficher(p)
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "assets" / "s.lua").write_text(
        'function on_update()\n    actor:spawn("Hero", vec2(0, 0))\n    actor:spawn("Chest", vec2(0, 0))\nend\n',
        encoding="utf-8")
    pi = scene_pi(p, scene)
    ids = {m["prefab"].name: m["root_type_id"] for m in pi if m["shared"]}
    code = "\n".join(interact_tick_lines(
        p, scene, [(a, None) for a in scene.actors], pi, [None], lambda sym, ev: True,
        SimpleNamespace(masks={"interact": "KEY_A"}), resolve_initial_appearance))
    kinds = scene_oam_layout(p, scene).type_table_size
    tags = list(p.collision_tags())
    # Les tables sont indexées par type : seul le type du coffre né porte un tag de zone et son action.
    row = ["255"] * kinds
    row[ids["Chest"]] = str(tags.index("zone"))
    assert f"static const u8 _ia_tag[{kinds}]={{{','.join(row)}}};" in code
    assert f"static const IaAction _ia_action[{kinds}]=" in code and "S_Chest_on_interact" in code
    # L'interacteur né est reconnu au descripteur ; la recherche parcourt tous les emplacements, posés ou nés.
    assert "if(g_model_desc_S[_a->type_id].interactor){ int _t=interact_pick(_a,_ia_tag,_ia_aim," in code
    assert "SLOT_EACH(_k){" in code


# ── Les modèles à parties dans le pool ─────────────────────────────────

def _scene_boss(tmp_path):
    """Un projectile plat et un boss à deux parties, tous deux spawnés ; le boss a un sprite, une partie un marqueur."""
    from core.models.components import CollisionShapeComponent
    bullet, boss = Prefab(name="Bullet"), Prefab(name="Boss")
    arm = Actor(name="Arm")
    arm.components.append(CollisionShapeComponent(w=8, h=8))
    boss.children = [arm, Actor(name="Muzzle")]
    scene = Scene(name="S", script="assets/s.lua", actors=[Actor(name="A")])
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [bullet, boss]
    tout_afficher(p)
    # le marqueur n'affiche rien
    boss.children[1].components[:] = [c for c in boss.children[1].components if not isinstance(c, SpriteComponent)]
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "assets" / "s.lua").write_text(
        'function on_update()\n    actor:spawn("Bullet", vec2(0, 0))\n    actor:spawn("Boss", vec2(0, 0))\nend\n',
        encoding="utf-8")
    return p, scene


def test_un_modele_a_parties_prend_une_identite_par_emplacement_de_son_groupe(tmp_path):
    p, scene = _scene_boss(tmp_path)
    lay = scene_oam_layout(p, scene)
    ids = {pl.prefab.name: (pl.root_type_id, pl.group) for pl in lay.pools}
    assert ids == {"Bullet": (1, 1), "Boss": (2, 3)}            # le boss prend les types 2 (racine), 3 et 4 (parties)
    assert all(pl.shared for pl in lay.pools) and lay.shared.size == OBJECT_CAPACITY - 1
    from codegen.oam_alloc import shared_type_count
    assert shared_type_count(lay.shared) == 4


def test_le_spawn_d_un_groupe_cherche_une_serie_libre_et_type_chaque_partie(tmp_path):
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    p, scene = _scene_boss(tmp_path)
    code = "\n".join(section_spawn(scene_pi(p, scene), p, None))
    boss = code[code.index("Actor* spawn_S_Boss"):]
    assert "while(_k<g_spool_end && !spool_slot_free(_k)) _k++;" in boss          # une partie détruite garde sa place
    assert "if(_k+3>g_spool_end) { _k=g_spool_end; break; }" in boss
    assert "while(_j<3 && spool_slot_free(_k+_j)) _j++;" in boss and "if(_k+3>g_actor_slot_end) g_actor_slot_end=_k+3;" in boss
    assert "actor_init_slot(_i, _e," in boss and ".type_id = 2" in boss
    assert "actor_init_slot(group_slot(_i, 1), group_entry(_e, 1)," in boss and ".type_id = 3" in boss
    assert "actor_init_slot(group_slot(_i, 2), -1," in boss and ".type_id = 4" in boss
    # L'hypothèse de contiguïté d'un groupe ne s'écrit qu'à un endroit (`group_slot`, `group_entry`) : plus de `_i+k`.
    assert "_i+1" not in boss and "_i+2" not in boss and "_e+1" not in boss
    plat = code[code.index("Actor* spawn_S_Bullet"):code.index("Actor* spawn_S_Boss")]
    assert "spool_slot_free(_k+_j)" not in plat and "g_spool_free=_k+1;" in plat
    assert "!spool_slot_free(_k)" in plat                      # un modèle plat respecte aussi les groupes vivants


def test_la_scene_sans_modele_a_parties_garde_le_test_simple(tmp_path):
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    p, scene = _scene_qui_spawne(tmp_path)
    code = "\n".join(section_spawn(scene_pi(p, scene), p, None))
    assert "spool_slot_free" not in code and "while(_k<g_spool_end && g_actors[_k].alive) _k++;" in code


def test_le_spawn_lie_chaque_partie_a_son_parent(tmp_path):
    """La composition est celle du runtime (`slot_compose_all`, posés compris) : le spawn ne fait que poser le lien de
    chaque partie, parent la racine ou une autre partie, par les accès de groupe."""
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    p, scene = _scene_boss(tmp_path)
    code = "\n".join(section_spawn(scene_pi(p, scene), p, None))
    assert "actor_link_slot(group_slot(_i, 1), _i, 1, 1," in code
    assert "actor_link_slot(group_slot(_i, 2), _i, 1, 1," in code
    assert "_i+1" not in code and "_i+2" not in code     # contiguïté : seulement dans group_slot / group_entry


def test_chaque_type_d_emplacement_a_son_cas_d_affichage_et_ses_collisions(tmp_path, monkeypatch):
    from codegen.runtime_codegen import shared_pool_gen
    from codegen.runtime_codegen.gen_sprite import Appearance
    from codegen.runtime_codegen.gen_pool import scene_pi
    from core.models.sprite import SpriteAsset
    p, scene = _scene_boss(tmp_path)
    pi = scene_pi(p, scene)
    code = _passe_rendu(p, scene, monkeypatch, variants=lambda nom: [None],
                        apps=lambda nom: [Appearance(SpriteAsset(name=nom, asset="a.png"), 0)])
    assert "case 1:" in code and "case 2:" in code and "case 3:" in code and "case 4:" not in code   # le marqueur n'affiche rien
    # Une partie réagit aux contacts avec le script de sa racine : sa ligne du descripteur porte les crochets de la
    # racine (types 3 et 4, racine 2), lus par la passe de contacts comme pour tout emplacement.
    from codegen.runtime_codegen.model_desc import model_desc_lines
    boss = next(m for m in pi if m["shared"] and m["root_type_id"] == 2)
    desc = "\n".join(model_desc_lines(p, scene, [(a, None) for a in scene.actors], pi, [None] * len(scene.actors),
                                      lambda sym, ev: sym == boss["sym"] and ev == "on_collision_enter"))
    hooks = f".on_contact={{{boss['sym']}_on_collision_enter,0,0}}"
    for kind in (2, 3, 4):
        assert any(hooks in line and f"/* {kind} " in line for line in desc.splitlines()), kind


def test_un_prefab_ne_sans_script_n_appelle_pas_init_script_state(tmp_path):
    """`pool_init` sort du script Lua du prefab : sans script, le spawn n'en déclare ni n'en appelle (l'édition de
    liens échouait sur le symbole absent)."""
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    p, scene = _scene_qui_spawne(tmp_path)
    code = "\n".join(section_spawn(scene_pi(p, scene), p, None))
    assert "Actor* spawn_S_Bullet" in code and "pool_init" not in code


def test_un_prefab_ne_avec_script_lua_appelle_init_script_state(tmp_path):
    from core.models.components import ScriptComponent
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    p, scene = _scene_qui_spawne(tmp_path)
    (tmp_path / "assets" / "bullet.lua").write_text("function on_update()\nend\n", encoding="utf-8")
    p.prefabs.items[0].actor.components.append(ScriptComponent(script="assets/bullet.lua"))
    code = "\n".join(section_spawn(scene_pi(p, scene), p, None))
    assert "extern void S_Bullet_init_script_state(Actor* self);" in code and "S_Bullet_init_script_state(&g_actors[_i]);" in code


def _scene_de_copies(tmp_path, *, masses=(1.0, 1.0, 2.0), spawne=False):
    """Une scène où le prefab « Coin » (Rigid) est posé une fois par masse, chaque copie à une autre position et avec une
    autre boîte ; un acteur « Rock » sans prefab ; si `spawne`, le script de scène fait aussi naître « Coin »."""
    import copy
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    coin = Prefab(name="Coin")
    coin.actor.components += [CollisionShapeComponent(w=8, h=8), PhysicsBodyComponent(mode="RigidBody")]
    posed = []
    for i, masse in enumerate(masses):
        a = Actor(name=f"Coin{i}", prefab_name="Coin", components=copy.deepcopy(coin.actor.components), x=10 * i)
        a.components[0].w = 8 + i                                   # la boîte vit dans l'emplacement
        a.components[1].mass = masse                                # la masse est lue au modèle
        posed.append(a)
    posed.append(Actor(name="Rock", components=[PhysicsBodyComponent(mode="RigidBody")]))
    scene = Scene(name="S", actors=posed, physics_enabled=True)
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [coin]
    if spawne:
        from oam_fixtures import faire_naitre
        faire_naitre(tmp_path, scene, "Coin")
    return p, scene


def test_les_copies_posees_qui_ne_different_que_par_l_emplacement_partagent_un_type(tmp_path):
    """Variante de modèle : même code et mêmes valeurs lues au modèle = un type ; une autre masse = un autre type ;
    un acteur qui n'est la copie d'aucun prefab est un modèle à lui seul."""
    p, scene = _scene_de_copies(tmp_path)
    lay = scene_oam_layout(p, scene)
    assert lay.placed_type_ids == [1, 1, 2, 3]
    assert lay.type_table_size == 4                                           # le type 0, puis trois types de posés


def test_un_autre_tag_de_boite_separe_deux_types(tmp_path):
    """Le tag est lu au modèle (les tables de paires appliquent la matrice des tags par couple de types) : deux copies
    de même masse dont les boîtes ont des tags différents ne partagent pas leur type."""
    p, scene = _scene_de_copies(tmp_path, masses=(1.0, 1.0))
    scene.actors[1].components[0].tag = "pied"
    lay = scene_oam_layout(p, scene)
    assert lay.placed_type_ids == [1, 2, 3]


def test_une_copie_identique_au_prefab_ne_prend_le_type_du_modele_ne(tmp_path):
    """Posé ou né, le même type : les deux copies aux valeurs du prefab prennent son `root_type_id` ; la copie d'une autre
    masse et l'acteur sans prefab ont leurs types après ceux du pool."""
    p, scene = _scene_de_copies(tmp_path, spawne=True)
    lay = scene_oam_layout(p, scene)
    (coin,) = [pl for pl in lay.pools if pl.shared]
    assert coin.root_type_id == 1
    assert lay.placed_type_ids == [1, 1, 2, 3] and lay.type_table_size == 4


def test_les_tables_par_type_couvrent_les_poses(tmp_path):
    """`group_root_slot` lit `g_spool_part[Actor.type_id]` pour tout emplacement : la table d'un modèle à parties doit avoir
    une ligne pour chaque type de posé."""
    from codegen.runtime_codegen.gen_scene_init import _shared_pool_lines
    from codegen.runtime_codegen.gen_pool import scene_pi
    p, scene = _scene_de_copies(tmp_path, spawne=True)
    p.prefabs.items[0].children = [Actor(name="Aile")]
    lay = scene_oam_layout(p, scene)
    code = "\n".join(_shared_pool_lines(scene_pi(p, scene), lay.type_table_size))
    # Un prefab à parties n'a pas de membres posés : chaque copie est un modèle à elle seule (types 3 à 6).
    assert lay.placed_type_ids == [3, 4, 5, 6]
    assert lay.type_table_size == 7 and "static const u8 _pt[7]={0,0,1,0,0,0,0};" in code
