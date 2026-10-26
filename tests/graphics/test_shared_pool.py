"""Le pool PARTAGÉ d'une scène : un seul tas d'emplacements pour tous les modèles qui y naissent.

Plus de réserve par prefab : tout modèle que la scène spawne (plat, à parties, affine, interacteur, bloqueur)
naît dans les emplacements qui restent après les acteurs posés, 512 en tout par scène (`OBJECT_CAPACITY`).
"""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from core.models.components import SpriteComponent
from oam_fixtures import tout_afficher, SPRITE
from codegen.oam_alloc import (
    OBJECT_CAPACITY, scene_oam_layout, project_actor_count, project_oam_entry_count,
)


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
    assert pool.shared and pool.model_id == 1
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
    ids = {pl.prefab.name: pl.model_id for pl in lay.pools}
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
    from codegen.runtime_codegen.main_gen import _scene_pi, _section_spawn
    p, scene = _scene_qui_spawne(tmp_path)
    code = "\n".join(_section_spawn(_scene_pi(p, scene), p, None))
    # La recherche part du curseur, pas du début du pool : un spawn ne parcourt pas les emplacements pleins.
    assert "int _k=g_spool_free;" in code and "while(_k<g_spool_end && g_actors[_k].alive) _k++;" in code
    assert "if(_k+1>g_spool_hw) g_spool_hw=_k+1;" in code and "g_spool_free=_k+1;" in code
    assert "g_actors[_i].model    = 1;" in code and "g_actors[_i].inst = _i;" in code


def test_la_boucle_du_tick_choisit_le_code_par_le_modele(tmp_path):
    from codegen.runtime_codegen import shared_pool_gen
    from codegen.runtime_codegen.main_gen import _scene_pi
    p, scene = _scene_qui_spawne(tmp_path, prefabs=("Bullet", "Coin"))
    pi = _scene_pi(p, scene)
    code = "\n".join(shared_pool_gen.hook_lines(pi, "on_update", lambda sym, ev: sym.endswith("Bullet")))
    assert "for(int _pk=g_spool_start; _pk<g_spool_hw; _pk++)" in code
    assert "switch(_a->model)" in code
    assert "case 1: S_Bullet_on_update(_a); break;" in code
    assert "S_Coin_on_update" not in code                     # ce modèle n'a pas de on_update
    assert shared_pool_gen.hook_lines(pi, "on_update", lambda sym, ev: False) == []


def test_l_ecriture_oam_du_pool_garde_les_constantes_de_chaque_modele(tmp_path):
    from codegen.runtime_codegen import shared_pool_gen
    from codegen.runtime_codegen.gen_sprite import Appearance, oam_write_lines
    from codegen.runtime_codegen.main_gen import _scene_pi
    from core.models.sprite import SpriteAsset
    p, scene = _scene_qui_spawne(tmp_path, prefabs=("Bullet", "Coin"))
    pi = _scene_pi(p, scene)
    bases = {"Bullet": 0, "Coin": 16}
    code = "\n".join(shared_pool_gen.oam_lines(
        pi, lambda owner: [Appearance(SpriteAsset(name=owner.name, asset="a.png"), bases[owner.name])],
        oam_write_lines))
    assert "int _pe=g_spool_entry+(_pk-g_spool_start);" in code
    assert "case 1: {" in code and "case 2: {" in code
    assert "u16 ti=(u16)(0+g_oam_entries[_pe].frame" in code
    assert "u16 ti=(u16)(16+g_oam_entries[_pe].frame" in code
    assert "g_actors[_pk]" in code


def test_la_scene_pose_le_pool_et_une_scene_sans_pool_le_vide(tmp_path):
    from codegen.runtime_codegen.main_gen import _scene_pi
    p, scene = _scene_qui_spawne(tmp_path, actors=3)
    (shared,) = [m for m in _scene_pi(p, scene) if m["shared"]]
    assert shared["spool"]["start"] == 3 and shared["spool"]["end"] == OBJECT_CAPACITY
    assert shared["spool"]["entries"] == OBJECT_CAPACITY - 3


def test_les_instances_du_pool_animent_leur_sprite_par_le_modele(tmp_path):
    from codegen.runtime_codegen import shared_pool_gen
    from codegen.runtime_codegen.gen_sprite import anim_tick_variants
    from codegen.runtime_codegen.main_gen import _scene_pi
    p, scene = _scene_qui_spawne(tmp_path, prefabs=("Bullet", "Coin"))
    pi = _scene_pi(p, scene)
    variants = {"Bullet": [dict(sym="sprite_Bullet")], "Coin": [None]}      # Coin : un sprite fixe
    code = "\n".join(shared_pool_gen.anim_lines(pi, lambda owner, sym: variants[owner.name], anim_tick_variants))
    assert "for(int _pk=g_spool_start; _pk<g_spool_hw; _pk++){" in code
    assert "int _pe=g_spool_entry+(_pk-g_spool_start);" in code
    assert "case 1: {" in code and "case 2:" not in code                  # seul le modèle animé a un cas
    assert "g_oam_entries[_pe].timer++;" in code and "g_actors[_pk].facing_y" in code
    assert "sprite_Bullet_state_start" in code
    assert shared_pool_gen.anim_lines(pi, lambda owner, sym: [None], anim_tick_variants) == []


# ── Blocage et interaction des instances du pool ──────────────────────

def _scene_blocage(tmp_path):
    """Un mur (boîte bloquante) et un héros (boîte solide, regard, joueur) tous deux spawnés dans le pool, plus
    un acteur posé qui bloque aussi."""
    from core.models.components import CollisionBoxComponent
    wall, hero = Prefab(name="Wall"), Prefab(name="Hero")
    wall.actor.components.append(CollisionBoxComponent(blocks_actors=True, solid=False, w=16, h=16))
    hero.actor.components.append(CollisionBoxComponent(solid=True, w=16, h=16))
    hero.actor.is_player = True
    scene = Scene(name="S", script="assets/s.lua",
                  actors=[Actor(name="Rock", components=[CollisionBoxComponent(blocks_actors=True, solid=False, w=16, h=16)])])
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
    from codegen.runtime_codegen.block_gen import block_tick_lines
    from codegen.runtime_codegen.main_gen import _scene_pi, _shown
    p, scene = _scene_blocage(tmp_path)
    pi = _scene_pi(p, scene)
    ids = {m["prefab"].name: m["model_id"] for m in pi if m["shared"]}
    code = "\n".join(block_tick_lines(p, scene, [(a, None) for a in scene.actors], 0, pi, _shown))
    # le héros né est repoussé par le mur né (modèle) ET par le rocher posé (emplacement)
    assert f"case {ids['Hero']}: {{" in code and f"case {ids['Wall']}:" not in code     # le mur n'est pas un mobile
    assert f"static const u8 _bk_pm[]={{{ids['Wall']}}};" in code
    assert "static const u16 _bk_idx[]={0};" in code
    assert "actors_resolve_blocks_pool(_a,_bk_pm,_bk_pb,1);" in code
    assert "for(int _bm=g_spool_start;_bm<g_spool_hw;_bm++){" in code


def test_sans_instance_du_pool_qui_bloque_aucun_appel_au_pool(tmp_path):
    from codegen.runtime_codegen.block_gen import block_tick_lines
    from codegen.runtime_codegen.main_gen import _scene_pi, _shown
    p, scene = _scene_blocage(tmp_path)
    p.prefabs.items = [pf for pf in p.prefabs.items if pf.name == "Hero"]      # plus de mur né
    (tmp_path / "assets" / "s.lua").write_text('function on_update()\n    actor:spawn("Hero", vec2(0, 0))\nend\n',
                                               encoding="utf-8")
    pi = _scene_pi(p, scene)
    code = "\n".join(block_tick_lines(p, scene, [(a, None) for a in scene.actors], 0, pi, _shown))
    assert "actors_resolve_blocks_pool" not in code and "actors_resolve_blocks(_a,_bk_idx" in code


def test_l_interaction_cherche_les_consommateurs_nes_et_reconnait_les_interacteurs_nes(tmp_path):
    from types import SimpleNamespace
    from codegen.c_names import scene_actor_sym
    from codegen.runtime_codegen.interact_gen import interact_tick_lines
    from codegen.runtime_codegen.main_gen import _scene_pi, _shown
    from core.models.components import CollisionBoxComponent, InteractiveComponent
    hero, chest = Prefab(name="Hero"), Prefab(name="Chest")
    hero.actor.components.append(CollisionBoxComponent(solid=True, w=16, h=16))
    hero.actor.is_player = True
    chest.actor.components += [CollisionBoxComponent(tag="zone", w=16, h=16),
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
    pi = _scene_pi(p, scene)
    ids = {m["prefab"].name: m["model_id"] for m in pi if m["shared"]}
    code = "\n".join(interact_tick_lines(
        p, scene, [(a, None) for a in scene.actors], 0, pi, set(), lambda sym, ev: True, scene_actor_sym,
        SimpleNamespace(masks={"interact": "KEY_A"}), _shown, lambda j: 0))
    top = max(ids.values()) + 1
    assert f"static const u8 _ia_pbox[{top}]=" in code and f"static const u8 _ia_paim[{top}]=" in code
    assert f"static void (*const _ia_pfn[{top}])(Actor*,Actor*)=" in code and "S_Chest_on_interact" in code
    assert f"g_actors[_w].model=={ids['Hero']}" in code                      # l'interacteur né est reconnu au modèle
    assert "int _k=interact_pick(&g_actors[_w],_ia_idx,_ia_box,_ia_aim,0,_ia_pbox,_ia_paim," in code
    assert "if(_k<-1){ Actor* _t=&g_actors[-2-_k]; _ia_pfn[_t->model](_t,&g_actors[_w]); }" in code
    assert "_ia_fn[" not in code                                            # aucun consommateur d'emplacement connu


# ── Les modèles à parties dans le pool ─────────────────────────────────

def _scene_boss(tmp_path):
    """Un projectile plat et un boss à deux parties, tous deux spawnés ; le boss a un sprite, une partie un marqueur."""
    from core.models.components import CollisionBoxComponent
    bullet, boss = Prefab(name="Bullet"), Prefab(name="Boss")
    arm = Actor(name="Arm")
    arm.components.append(CollisionBoxComponent(w=8, h=8))
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
    ids = {pl.prefab.name: (pl.model_id, pl.group) for pl in lay.pools}
    assert ids == {"Bullet": (1, 1), "Boss": (2, 3)}            # le boss prend les types 2 (racine), 3 et 4 (parties)
    assert all(pl.shared for pl in lay.pools) and lay.shared.size == OBJECT_CAPACITY - 1
    from codegen.oam_alloc import shared_kinds
    assert shared_kinds(lay.shared) == 4


def test_le_spawn_d_un_groupe_cherche_une_serie_libre_et_type_chaque_partie(tmp_path):
    from codegen.runtime_codegen.main_gen import _scene_pi, _section_spawn
    p, scene = _scene_boss(tmp_path)
    code = "\n".join(_section_spawn(_scene_pi(p, scene), p, None))
    boss = code[code.index("Actor* spawn_S_Boss"):]
    assert "while(_k<g_spool_end && !spool_slot_free(_k)) _k++;" in boss          # une partie détruite garde sa place
    assert "if(_k+3>g_spool_end) { _k=g_spool_end; break; }" in boss
    assert "while(_j<3 && spool_slot_free(_k+_j)) _j++;" in boss and "if(_k+3>g_spool_hw) g_spool_hw=_k+3;" in boss
    assert "g_actors[_i].model    = 2;" in boss
    assert "g_actors[_i+1].model    = 3;" in boss and "g_actors[_i+2].model    = 4;" in boss
    assert "g_oam_entries[_e+1] = (OamEntry){0};" in boss         # la partie k : l'entrée de son emplacement, `_e + k`
    plat = code[code.index("Actor* spawn_S_Bullet"):code.index("Actor* spawn_S_Boss")]
    assert "spool_slot_free(_k+_j)" not in plat and "g_spool_free=_k+1;" in plat
    assert "!spool_slot_free(_k)" in plat                      # un modèle plat respecte aussi les groupes vivants


def test_la_scene_sans_modele_a_parties_garde_le_test_simple(tmp_path):
    from codegen.runtime_codegen.main_gen import _scene_pi, _section_spawn
    p, scene = _scene_qui_spawne(tmp_path)
    code = "\n".join(_section_spawn(_scene_pi(p, scene), p, None))
    assert "spool_slot_free" not in code and "while(_k<g_spool_end && g_actors[_k].alive) _k++;" in code


def test_la_composition_des_parties_parcourt_les_racines_vivantes_du_pool(tmp_path):
    from codegen.runtime_codegen.main_gen import _scene_pi, _pool_compose_lines
    p, scene = _scene_boss(tmp_path)
    code = "\n".join(_pool_compose_lines(_scene_pi(p, scene)))
    assert "for(int _b=g_spool_start; _b<g_spool_hw; _b++) {" in code
    assert "if(g_actors[_b].model!=2||!g_actors[_b].alive) continue;" in code
    assert "int _eb = g_spool_entry + (_b - g_spool_start);" in code
    assert "g_actors[_b+1].x" in code and "g_actors[_b+2].x" in code
    assert "g_oam_entries[_eb+1].visible" in code                  # la partie k : l'entrée de son emplacement
    assert "g_actors[_b+_k].alive = 0" not in code                 # la libération du groupe est celle de destroy


def test_chaque_type_d_emplacement_a_son_cas_d_affichage_et_ses_collisions(tmp_path):
    from codegen.runtime_codegen import shared_pool_gen
    from codegen.runtime_codegen.gen_sprite import Appearance, oam_write_lines
    from codegen.runtime_codegen.main_gen import _scene_pi
    from core.models.sprite import SpriteAsset
    p, scene = _scene_boss(tmp_path)
    pi = _scene_pi(p, scene)
    code = "\n".join(shared_pool_gen.oam_lines(
        pi, lambda owner: [Appearance(SpriteAsset(name=owner.name, asset="a.png"), 0)], oam_write_lines))
    assert "case 1: {" in code and "case 2: {" in code and "case 3: {" in code and "case 4:" not in code   # le marqueur n'affiche rien
    from codegen.runtime_codegen.main_gen import _box_contact_lines
    from core.models.components import CollisionBoxComponent
    boxed = [(0, scene.actors[0])]
    scene.actors[0].components.append(CollisionBoxComponent(w=8, h=8))
    col = "\n".join(shared_pool_gen.collision_lines(
        pi, 100, boxed, lambda pf, a: True, lambda sym, ev: sym.endswith("Boss") and ev == "on_collision_enter",
        lambda sym, ev: True, lambda scn, name: f"{scn}_{name}", {0}, "S", _box_contact_lines))
    assert "case 2: case 3: case 4: {" in col     # une partie réagit avec le script de sa racine
