"""`self.Canon:play_anim("tir")` nomme un état du sprite de l'ENFANT.

Avant : le codegen rangeait le nom avec l'acteur propriétaire du script
(`ANIM_<PARENT>_TIR`), constante qui n'existe pas, et le checker se taisait : l'erreur
sortait de gcc. Le contrat : l'état se range dans la bibliothèque de sprites de
l'enfant, et un état absent est refusé par le checker, avec le nom de l'enfant.
"""

from __future__ import annotations

from scripting.api import SpriteLibrary

_SRC = 'function on_update()\n    {call}\nend\n'


def _lib(**kw):
    return SpriteLibrary(**{k: tuple(tuple(x) if isinstance(x, list) else x for x in v)
                            for k, v in kw.items()})


def _errors(call: str, child_sprites):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    ctx = BuildContext(actor_name="Tourelle", anim_names=["idle"], sprite_ids=["a"],
                       child_names=["Canon"], child_sprites=child_sprites)
    return [e.message for e in check(parse(_SRC.format(call=call)), ctx) if e.level == "error"]


def _c(call: str, child_sprites):
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    ctx = CodegenContext(actor_name="Tourelle", actor_sym="Tourelle", anim_names=["idle"],
                         sfx_names=[], music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=["Tourelle", "Canon"],
                         child_refs={"Canon": "&g_actors[ACTOR_CANON]"},
                         child_sprites=child_sprites)
    return generate(parse(_SRC.format(call=call)), ctx)[0]


def test_etat_de_l_enfant_emis_par_son_rang_dans_le_sprite_de_l_enfant():
    code = _c('self.Canon:play_anim("tir")',
              {"Canon": _lib(anim_names=["idle", "tir"])})
    assert "actor_play_anim(&g_actors[ACTOR_CANON], 1)" in code
    assert "ANIM_TOURELLE_TIR" not in code


def test_enfant_a_plusieurs_apparences_lit_l_apparence_affichee():
    lib = _lib(anim_names=["idle", "tir"], anim_maps=[[0, 1], [255, 0]])
    code = _c('self.Canon:play_anim("tir")', {"Canon": lib})
    assert ("actor_play_anim(&g_actors[ACTOR_CANON], ((const unsigned char[]){1,0})"
            "[actor_get_appearance(&g_actors[ACTOR_CANON])])") in code


def test_id_d_apparence_de_l_enfant():
    code = _c('self.Canon:activate_sprite("feu")',
              {"Canon": _lib(sprite_ids=["calme", "feu"])})
    assert "actor_set_appearance(&g_actors[ACTOR_CANON], 1)" in code


def test_etat_absent_du_sprite_de_l_enfant_refuse_par_le_checker():
    errs = _errors('self.Canon:play_anim("tir")', {"Canon": _lib(anim_names=["idle"])})
    assert len(errs) == 1
    assert "'tir'" in errs[0] and "Canon" in errs[0] and "idle" in errs[0]


def test_etat_du_parent_ne_vaut_pas_pour_l_enfant():
    """`idle` existe chez le parent (anim_names), pas chez l'enfant."""
    assert _errors('self.Canon:play_anim("idle")', {"Canon": _lib(anim_names=["tir"])})


def test_id_inconnu_de_l_enfant_refuse():
    assert _errors('self.Canon:activate_sprite("a")', {"Canon": _lib(sprite_ids=["feu"])})


def test_etat_connu_de_l_enfant_accepte():
    assert _errors('self.Canon:play_anim("TIR")', {"Canon": _lib(anim_names=["tir"])}) == []


def test_acteur_obtenu_par_get_ne_peut_pas_nommer_un_etat():
    """Son sprite n'est pas connu du script : refus net, plus de C faux."""
    errs = _errors('actor:get("Canon"):play_anim("tir")', None)
    assert errs and "self" in errs[0]


# ── Lecture par propriété : `self.Canon.anim == "tir"` ───────────────

_IF = 'if self.Canon.{prop} == "{name}" then self:destroy() end'


def test_lecture_de_l_etat_d_un_enfant_emise_par_son_rang():
    code = _c(_IF.format(prop="anim", name="tir"), {"Canon": _lib(anim_names=["idle", "tir"])})
    assert "(actor_get_anim(&g_actors[ACTOR_CANON]) == 1)" in code


def test_lecture_de_l_apparence_d_un_enfant():
    code = _c(_IF.format(prop="active_sprite", name="feu"),
              {"Canon": _lib(sprite_ids=["calme", "feu"])})
    assert "(actor_get_appearance(&g_actors[ACTOR_CANON]) == 1)" in code


def test_lecture_d_un_etat_absent_de_l_enfant_refusee():
    errs = _errors(_IF.format(prop="anim", name="tir"), {"Canon": _lib(anim_names=["idle"])})
    assert len(errs) == 1 and "'tir'" in errs[0] and "Canon" in errs[0]


def test_lecture_d_un_etat_connu_de_l_enfant_acceptee():
    assert _errors(_IF.format(prop="anim", name="tir"),
                   {"Canon": _lib(anim_names=["tir"])}) == []
