"""Le pool PARTAGÉ d'une scène : un seul tas d'emplacements pour tous les modèles simples.

Plus de réserve par prefab : tout modèle simple (`oam_alloc.is_plain_model`) que la scène spawne naît dans
les emplacements qui restent après les acteurs posés, 512 en tout par scène (`OBJECT_CAPACITY`). Les
modèles qui demandent encore des emplacements fixes (un sous-arbre, une matrice affine, un interacteur, un
bloqueur) gardent une réserve à eux.
"""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from oam_fixtures import tout_afficher
from codegen.oam_alloc import (
    OBJECT_CAPACITY, scene_oam_layout, is_plain_model, project_actor_count, project_oam_entry_count,
)


def _scene_qui_spawne(tmp_path, *, actors=2, prefabs=("Bullet",), a_part=()):
    """Une scène à `actors` acteurs posés dont un script spawne chacun des `prefabs`. Ceux de `a_part`
    sont des interacteurs : ils gardent leur réserve."""
    pfs = []
    for nom in prefabs:
        pf = Prefab(name=nom)
        pf.actor.is_player = nom in a_part
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


def test_un_modele_simple_qui_naît_prend_le_pool_partage(tmp_path):
    p, scene = _scene_qui_spawne(tmp_path, actors=3)
    lay = scene_oam_layout(p, scene)
    (pool,) = lay.pools
    assert pool.shared and pool.model_id == 1 and pool.size == 0 and pool.reserve == 0
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


def test_un_modele_qui_garde_sa_reserve_passe_avant_le_pool(tmp_path):
    p, scene = _scene_qui_spawne(tmp_path, actors=2, prefabs=("Bullet", "Hero"), a_part=("Hero",))
    lay = scene_oam_layout(p, scene)
    dedie = next(pl for pl in lay.pools if pl.prefab.name == "Hero")
    assert not dedie.shared and dedie.start == 2 and dedie.size == 8
    assert lay.shared.start == 2 + 8 and lay.shared.size == OBJECT_CAPACITY - 10


def test_sans_modele_simple_qui_naisse_il_n_y_a_pas_de_pool_partage(tmp_path):
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


def test_les_modeles_a_emplacements_fixes_ne_sont_pas_simples():
    from core.models.components import InteractiveComponent, CollisionBoxComponent, SpriteComponent
    simple = Prefab(name="Bullet")
    assert is_plain_model(simple)
    for cas in ("sous-arbre", "affine", "interacteur", "bloqueur", "joueur"):
        pf = Prefab(name="X")
        if cas == "sous-arbre":
            pf.children = [Actor(name="Arm")]
        elif cas == "affine":
            pf.actor.components.append(SpriteComponent(affine_transform=True))
        elif cas == "interacteur":
            pf.actor.components.append(InteractiveComponent())
        elif cas == "bloqueur":
            pf.actor.components.append(CollisionBoxComponent(blocks_actors=True))
        else:
            pf.actor.is_player = True
        assert not is_plain_model(pf), cas


# ── Le C émis ─────────────────────────────────────────────────────────

def test_le_spawn_prend_le_premier_emplacement_libre_du_pool(tmp_path):
    from codegen.runtime_codegen.main_gen import _scene_pi, _section_spawn
    p, scene = _scene_qui_spawne(tmp_path)
    code = "\n".join(_section_spawn(_scene_pi(p, scene), p, None))
    assert "for(int _k=g_spool_start; _k<g_spool_end; _k++)" in code
    assert "if(!g_actors[_k].alive) {" in code and "if(_k+1>g_spool_hw) g_spool_hw=_k+1;" in code
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
