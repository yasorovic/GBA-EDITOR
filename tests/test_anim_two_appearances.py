"""Un porteur (acteur ou prefab) à DEUX composants sprite, l'un actif et l'autre non : ce que
l'autocomplétion propose et ce que le build accepte pour les états d'animation.

Règle : les deux sprites comptent, actif ou non. Un état se nomme s'il existe dans AU MOINS UN
des sprites ; à l'exécution, le nom se résout contre l'apparence COURANTE, et un état absent de
celle-ci est un no-op (255). La complétion propose donc l'union."""
from __future__ import annotations

from codegen.runtime_codegen.lua_compiler import _anim_union
from codegen.oam_alloc import owner_appearances
from core.models.components import ScriptComponent, SpriteComponent
from core.models.scene import Actor, Prefab, Scene
from core.models.sprite import AnimState, SpriteAsset
from core.project import Project
from scripting.checker import BuildContext, check
from scripting.codegen import CodegenContext, generate
from scripting.parser import parse
from scripting.project_names import anim_names_of_script

SCRIPT = 'function on_update()\n    self:play_anim("{}")\nend\n'


def _projet(tmp_path) -> Project:
    p = Project(tmp_path)
    p.sprites.append(SpriteAsset(name="Normal", asset="n.png",
                                 states=[AnimState(name="Idle"), AnimState(name="Run")]))
    p.sprites.append(SpriteAsset(name="Blesse", asset="b.png",
                                 states=[AnimState(name="Idle"), AnimState(name="Hurt")]))
    (tmp_path / "hero.lua").write_text(SCRIPT.format("Idle"), encoding="utf-8")
    return p


def _deux_apparences(owner):
    owner.components.append(SpriteComponent(id="normal", sprite_name="Normal", active=True))
    owner.components.append(SpriteComponent(id="blesse", sprite_name="Blesse", active=False))
    owner.components.append(ScriptComponent(script="hero.lua"))
    return owner


def _acteur(p: Project) -> Actor:
    scene = Scene(name="S")
    actor = _deux_apparences(Actor(name="Hero"))
    scene.actors.append(actor)
    p.scenes.append(scene)
    return actor


def _prefab(p: Project) -> Prefab:
    prefab = Prefab(name="Hero")
    _deux_apparences(prefab.actor)
    p.prefabs.append(prefab)
    return prefab


def _warnings(anim_names, name: str) -> list[str]:
    ctx = BuildContext(actor_name="Hero", anim_names=anim_names)
    return [e.message for e in check(parse(SCRIPT.format(name)), ctx) if e.level == "warning"]


# ── L'autocomplétion ──────────────────────────────────────────────────

def test_la_completion_propose_l_union_des_deux_sprites_actif_ou_non_pour_un_acteur(tmp_path):
    p = _projet(tmp_path)
    _acteur(p)
    assert anim_names_of_script(p, tmp_path / "hero.lua") == ["Idle", "Run", "Hurt"]


def test_la_completion_propose_l_union_des_deux_sprites_pour_un_prefab(tmp_path):
    p = _projet(tmp_path)
    _prefab(p)
    assert anim_names_of_script(p, tmp_path / "hero.lua") == ["Idle", "Run", "Hurt"]


# ── La compilation ────────────────────────────────────────────────────

def test_le_build_nomme_l_union_et_une_correspondance_par_apparence(tmp_path):
    p = _projet(tmp_path)
    for owner in (_acteur(p), _prefab(p).actor):
        names, maps = _anim_union(p, owner, owner_appearances(p, owner)[0][1])
        assert names == ["Idle", "Run", "Hurt"]
        assert maps == [[0, 1, 255],      # Normal : pas de « Hurt »
                        [0, 255, 1]]      # Blesse : pas de « Run »


def test_un_etat_de_l_apparence_inactive_ne_donne_pas_d_avertissement(tmp_path):
    names = ["Idle", "Run", "Hurt"]
    assert _warnings(names, "Hurt") == []            # n'existe que dans le sprite inactif
    assert _warnings(names, "run") == []             # n'existe que dans l'actif, et sans égard à la casse
    (msg,) = _warnings(names, "Fly")
    assert "(Idle, Run, Hurt)" in msg


def test_le_c_emis_resout_l_etat_contre_l_apparence_courante(tmp_path):
    ctx = CodegenContext(actor_name="Hero", actor_sym="Hero", anim_names=["Idle", "Run", "Hurt"],
                         anim_maps=[[0, 1, 255], [0, 255, 1]], sprite_ids=["normal", "blesse"],
                         sfx_names=[], music_names=[], global_names=set(),
                         const_names=set(), all_actor_syms=["Hero"])
    code, _, _ = generate(parse(SCRIPT.format("Hurt")), ctx)
    assert "Hero_anim_map[2][3] = {{0,1,255},{0,255,1}};" in code
    assert "ANIM_HERO_HURT ((int)Hero_anim_map[actor_get_appearance(self)][2])" in code
