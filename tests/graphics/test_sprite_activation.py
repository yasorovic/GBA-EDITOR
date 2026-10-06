"""Marche 3c : l'ACTIVATION d'une apparence à l'exécution, côté script.

`self:activate_sprite("id")` est un geste comme `play_anim` (l'animation repart) ;
`self.active_sprite` se lit et se compare par son nom. L'id nomme un composant sprite
de l'acteur, résolu à la compile en `SPRITE_<ACTEUR>_<ID>`. Les noms d'animation d'un
acteur multi-apparence se résolvent contre l'apparence COURANTE : une union des noms
d'état et, par apparence, la correspondance vers le rang dans son sprite."""
from __future__ import annotations

from codegen.runtime_codegen.lua_compiler import _anim_union
from core.models.components import SpriteComponent
from core.models.scene import Actor
from core.models.sprite import AnimState, SpriteAsset
from core.project import Project
from scripting.checker import BuildContext, check
from scripting.codegen import CodegenContext, generate
from scripting.parser import parse


def _etats(*noms):
    return [AnimState(name=n) for n in noms]


def _projet(tmp_path, **sprites):
    p = Project(tmp_path)
    for nom, etats in sprites.items():
        p.sprites.append(SpriteAsset(name=nom, asset=f"{nom}.png", states=_etats(*etats)))
    return p


def _acteur(*apparences):
    a = Actor(name="Hero")
    for i, (sprite, actif) in enumerate(apparences):
        a.components.append(SpriteComponent(id=f"s{i}", sprite_name=sprite, active=actif))
    return a


# ── Le checker ────────────────────────────────────────────────────────

def _erreurs(body, ids):
    src = f"function on_update(self)\n{body}\nend\n"
    res = check(parse(src), BuildContext(actor_name="Hero", sprite_ids=ids))
    return [e.message for e in res if e.level == "error"]


def test_un_id_connu_passe():
    assert _erreurs('self:activate_sprite("blesse")', ["normal", "blesse"]) == []


def test_un_id_inconnu_est_une_erreur_qui_liste_les_ids():
    (msg,) = _erreurs('self:activate_sprite("nope")', ["normal", "blesse"])
    assert "no sprite component with this id" in msg and "normal, blesse" in msg


def test_la_comparaison_de_l_apparence_active_est_verifiee_aussi():
    assert _erreurs('if self.active_sprite == "blesse" then self:destroy() end', ["normal"])


def test_activer_le_sprite_d_un_autre_acteur_est_refuse():
    """L'id appartient à l'acteur qui exécute le script, pas au récepteur."""
    errs = _erreurs('local o = actor:get(1)\nif o then o:activate_sprite("normal") end', ["normal"])
    assert any("names an element" in e for e in errs)


# ── Le C émis ─────────────────────────────────────────────────────────

def _c(body, ids, anim_names=(), anim_maps=()):
    ctx = CodegenContext(actor_name="Hero", actor_sym="Hero", anim_names=list(anim_names),
                         anim_maps=[list(m) for m in anim_maps], sprite_ids=list(ids),
                         sfx_names=[], music_names=[], global_names=set(),
                         const_names=set(), all_actor_syms=["Hero"])
    code, _, _ = generate(parse(f"function on_update(self)\n{body}\nend\n"), ctx)
    return code


def test_les_ids_deviennent_des_constantes_par_rang():
    code = _c('self:activate_sprite("blesse")', ["normal", "blesse"])
    assert "#define SPRITE_HERO_NORMAL 0" in code and "#define SPRITE_HERO_BLESSE 1" in code
    assert "actor_set_appearance(self, SPRITE_HERO_BLESSE);" in code


def test_l_apparence_active_se_lit_par_un_getter():
    code = _c('if self.active_sprite == "blesse" then self:destroy() end', ["normal", "blesse"])
    assert "actor_get_appearance(self) == SPRITE_HERO_BLESSE" in code


def test_une_apparence_garde_des_constantes_d_animation_litterales():
    code = _c('self:play_anim("walk")', ["a"], anim_names=["idle", "walk"])
    assert "#define ANIM_HERO_WALK 1" in code and "anim_map" not in code


def test_plusieurs_apparences_resolvent_les_animations_contre_la_courante():
    code = _c('self:play_anim("walk")', ["a", "b"], anim_names=["idle", "walk"],
              anim_maps=[[0, 255], [1, 0]])
    assert "Hero_anim_map[2][2] = {{0,255},{1,0}};" in code
    assert ("#define ANIM_HERO_WALK ((int)Hero_anim_map[actor_get_appearance(self)][1])"
            in code)


# ── L'union des états ─────────────────────────────────────────────────

def test_un_acteur_mono_apparence_garde_ses_etats_sans_correspondance(tmp_path):
    p = _projet(tmp_path, A=("idle", "walk"))
    a = _acteur(("A", True))
    sprite = p.get_sprite("A")
    assert _anim_union(p, a, sprite) == (["idle", "walk"], [])


def test_l_union_suit_l_ordre_de_premiere_apparition_et_marque_les_absents(tmp_path):
    p = _projet(tmp_path, A=("idle", "walk"), B=("attack", "walk", "idle"))
    a = _acteur(("A", True), ("B", False))
    names, maps = _anim_union(p, a, p.get_sprite("A"))
    assert names == ["idle", "walk", "attack"]
    assert maps == [[0, 1, 255],      # A : pas d'« attack »
                    [2, 1, 0]]        # B : idle=2, walk=1, attack=0


# ── Suivi de renommage de l'id d'un composant sprite ───────────────────

from scripting.api import DOMAIN_ANIM, DOMAIN_SPRITE_ID           # noqa: E402
from scripting.refactor import rename_in_text                        # noqa: E402

_SCRIPT = '''function on_update(self)
  if self.active_sprite == "blesse" then self:activate_sprite("normal") end
  self:activate_sprite('blesse')
  self:play_anim("blesse")
end
'''


def test_le_renommage_suit_les_appels_et_les_comparaisons_de_self():
    texte, n = rename_in_text(_SCRIPT, DOMAIN_SPRITE_ID, "blesse", "touche")
    assert n == 2
    assert 'self.active_sprite == "touche"' in texte
    assert "self:activate_sprite('touche')" in texte           # les guillemets d'origine restent
    assert 'self:activate_sprite("normal")' in texte


def test_un_nom_d_animation_identique_n_est_pas_touche_par_un_renommage_d_id():
    texte, _ = rename_in_text(_SCRIPT, DOMAIN_SPRITE_ID, "blesse", "touche")
    assert 'self:play_anim("blesse")' in texte


def test_le_renommage_d_animation_suit_maintenant_self_anim():
    """Effet de bord voulu : `self.anim == "walk"` citait déjà un nom du projet."""
    texte, n = rename_in_text('if self.anim == "walk" then end\n', DOMAIN_ANIM, "walk", "run")
    assert n == 1 and 'self.anim == "run"' in texte


def _projet_avec_scripts(tmp_path):
    from core.models.components import ScriptComponent
    p = Project(tmp_path)
    (tmp_path / "assets" / "scripts" / "actors").mkdir(parents=True)
    heros, autre = _acteur(("A", True), ("B", False)), _acteur(("A", True), ("B", False))
    autre.name = "Autre"
    for acteur, nom in ((heros, "heros"), (autre, "autre")):
        acteur.components[1].id = "blesse"
        rel = f"assets/scripts/actors/{nom}.lua"
        (tmp_path / rel).write_text(_SCRIPT, encoding="utf-8")
        acteur.components.append(ScriptComponent(script=rel))
    return p, heros, autre


def test_le_renommage_ne_touche_que_le_script_du_proprietaire(tmp_path):
    """Deux acteurs peuvent avoir chacun un « blesse » : renommer celui de l'un ne
    réécrit pas le script de l'autre."""
    p, heros, autre = _projet_avec_scripts(tmp_path)
    refs = p.rename_sprite_id_refs(heros, "blesse", "touche")
    assert [(pth.name, n) for pth, n in refs.items()] == [("heros.lua", 2)]
    assert '"touche"' in (tmp_path / "assets/scripts/actors/heros.lua").read_text(encoding="utf-8")
    assert (tmp_path / "assets/scripts/actors/autre.lua").read_text(encoding="utf-8") == _SCRIPT


def test_la_commande_renomme_l_id_et_le_script_et_s_annule_des_deux(tmp_path):
    from core.history import RenameSpriteIdCmd
    p, heros, _autre = _projet_avec_scripts(tmp_path)
    comp = heros.components[1]
    script = tmp_path / "assets/scripts/actors/heros.lua"
    cmd = RenameSpriteIdCmd(p, heros, comp, "blesse", "touche")
    cmd.execute()
    assert comp.id == "touche" and "touche" in script.read_text(encoding="utf-8")
    cmd.undo()
    assert comp.id == "blesse" and script.read_text(encoding="utf-8") == _SCRIPT


# ── Validation : deux ids, une même constante ─────────────────────────

def test_deux_ids_qui_donnent_la_meme_constante_sont_une_erreur(tmp_path):
    from core.models.scene import Scene
    from core.validator import ValidationContext, _check_sprite_appearances
    hero = _acteur(("A", True), ("B", False))
    hero.components[0].id, hero.components[1].id = "a b", "a_b"
    p = _projet(tmp_path, A=("x",), B=("x",))
    p.scenes.items = [Scene(name="S", actors=[hero])]
    ctx = ValidationContext(p)
    _check_sprite_appearances(ctx)
    errs = [m.message for m in ctx._msgs if m.level == "error"]
    assert len(errs) == 1 and "same C constant" in errs[0]
