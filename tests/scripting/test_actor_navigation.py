"""`a.parent` et `a.root` : un prefab à parties naît en groupe, et chaque partie sait de quelle instance elle est. Les deux
méthodes rendent un acteur ou nil, donc leur résultat se teste, et une action posée dessus est gardée comme sur un `actor:get`."""
from __future__ import annotations

from scripting.api import RUNTIME_API, RUNTIME_PROPS
from scripting.checker import check, BuildContext
from scripting.codegen import generate, CodegenContext
from scripting.parser import parse


def _c(body: str, top: str = "") -> str:
    script = parse(f"{top}\nfunction on_collision_enter(other)\n{body}\nend\n")
    code, _w, _n = generate(script, CodegenContext(
        actor_name="Gun", actor_sym="Sc_Gun", anim_names=[], sfx_names=[], music_names=[],
        global_names=set(), const_names=set(), all_actor_syms=["Sc_Gun"], is_pooled=False))
    return code


def _erreurs(body: str, top: str = "") -> list[str]:
    script = parse(f"{top}\nfunction on_collision_enter(other)\n{body}\nend\n")
    return [e.message for e in check(script, BuildContext(actor_names=["Boss"], prefab_names=["Boss"])) if e.level == "error"]


def test_root_et_parent_sont_des_appels_c():
    code = _c("local boss = other.root\nlocal p = other.parent")
    assert "Actor* boss = actor_root(other);" in code
    assert "Actor* p = actor_parent(other);" in code


def test_le_resultat_se_teste_comme_un_get():
    code = _c("local boss = other.root\nif boss then\n    boss:hide()\nend")
    assert "if (boss)" in code and "actor_set_visible(boss, 0);" in code


def test_une_action_posee_sur_un_parent_est_gardee_contre_nil():
    """`other.parent:hide()` : le parent peut manquer (racine, partie détruite) ; l'appel est sauté, il ne plante pas."""
    code = _c("other.parent:hide()")
    assert 'actor_active_warn(actor_parent(other), "hide()")' in code
    assert "actor_set_visible(actor_parent(other), 0);" in code


def test_une_chaine_root_parent_est_gardee_de_bout_en_bout():
    code = _c("other.root.parent:hide()")
    assert "actor_parent(actor_root(other))" in code and "actor_active_warn(" in code


def test_un_acteur_pris_par_root_se_garde_d_une_image_a_l_autre_en_reference():
    """Une variable de tête qui reçoit `a.root` range une RÉFÉRENCE (génération + indice), pas un pointeur périmé."""
    code = _c("boss = other.root", top="local boss = nil")
    assert "boss = actor_ref_make(actor_root(other));" in code


def test_parent_et_root_sont_des_proprietes_pas_des_methodes():
    """Une relation lue sans argument est un état : une propriété (un concept, un nom). La forme appel n'existe plus."""
    assert "actor:parent" not in RUNTIME_API and "actor:root" not in RUNTIME_API
    assert RUNTIME_PROPS["actor.parent"].read_only and RUNTIME_PROPS["actor.root"].read_only
    assert any("parent" in e for e in _erreurs("local p = other:parent()"))


def test_on_n_ecrit_pas_parent_ni_root():
    assert any("read-only" in e for e in _erreurs("other.parent = other"))


def test_une_globale_qui_porte_le_nom_d_une_propriete_d_acteur_reste_une_globale():
    """`global.parent` n'est pas `a.parent`, et `global.frame` n'est pas `a.frame` : un espace de noms du projet n'est pas un acteur.
    Le codegen émettait `actor_get_frame(global)`, du C invalide, pour toute globale nommée comme une propriété d'acteur."""
    ctx = CodegenContext(actor_name="Gun", actor_sym="Sc_Gun", anim_names=[], sfx_names=[], music_names=[],
                         global_names={"parent", "root", "frame", "priority"}, const_names=set(), all_actor_syms=["Sc_Gun"],
                         is_pooled=False)
    src = ("function on_update()\n    local a = global.parent\n    local b = global.root\n"
           "    local c = global.frame\n    local d = global.priority\nend\n")
    code = generate(parse(src), ctx)[0]
    for nom in ("parent", "root", "frame", "priority"):
        assert f"g_{nom}" in code
    assert "actor_parent" not in code and "actor_get_frame" not in code


def test_un_acteur_pris_par_root_ne_peut_pas_initialiser_une_variable_de_tete():
    erreurs = _erreurs("local x = 0", top="local boss = other.root")
    assert any("top-level" in e.lower() or "top level" in e.lower() or "initialis" in e.lower() for e in erreurs), erreurs


# ── boss.Canon : une partie, depuis une RÉFÉRENCE à un prefab connu ──────────────────────────────

def _lib(**kw):
    from scripting.api import SpriteLibrary
    return SpriteLibrary(**{k: tuple(tuple(x) if isinstance(x, list) else x for x in v) for k, v in kw.items()})


_CHILDREN = {"Boss": {"Canon": 1, "Voyant": 2}}
_CHILD_LIBS = {"Boss": {"Canon": _lib(anim_names=["idle", "fire"]), "Voyant": _lib(anim_names=["on"])}}


def _cc(body: str, top: str = "") -> str:
    ctx = CodegenContext(actor_name="Ctrl", actor_sym="Ctrl", anim_names=["idle"], sfx_names=[], music_names=[],
                         global_names=set(), const_names=set(), all_actor_syms=["Ctrl"], scene_sym="Sc",
                         prefab_children=_CHILDREN, prefab_child_sprites=_CHILD_LIBS)
    return generate(parse(f"{top}\nfunction on_update()\n{body}\nend\n"), ctx)[0]


def _ce(body: str, top: str = "") -> list[str]:
    ctx = BuildContext(actor_name="Ctrl", anim_names=["idle"], sprite_ids=["a"], actor_names=[], prefab_names=["Boss"],
                       pooled_prefab_names=["Boss"], prefab_children=_CHILDREN, prefab_child_sprites=_CHILD_LIBS)
    return [e.message for e in check(parse(f"{top}\nfunction on_update()\n{body}\nend\n"), ctx) if e.level == "error"]


def test_une_partie_se_nomme_depuis_une_reference_au_prefab():
    code = _cc('local boss = actor:spawn("Boss", vec2(1, 1))\nif boss then boss.Canon:hide() end')
    assert 'actor_active_warn(actor_child(boss, 1), "hide()")' in code
    assert "actor_set_visible(actor_child(boss, 1), 0);" in code


def test_le_rang_vient_du_prefab_pas_du_nom():
    code = _cc('local boss = actor:spawn("Boss", vec2(1, 1))\nif boss then boss.Voyant:hide() end')
    assert "actor_child(boss, 2)" in code


def test_une_variable_de_tete_range_une_reference_et_la_partie_se_resout_apres_elle():
    code = _cc('boss = actor:spawn("Boss", vec2(1, 1))\nif boss then boss.Canon:hide() end', top="local boss = nil")
    assert "actor_child(actor_ref_get(boss), 1)" in code


def test_la_partie_se_garde_dans_un_local_qui_se_teste():
    code = _cc('local boss = actor:spawn("Boss", vec2(1, 1))\nlocal c = boss.Canon\nif c then c:hide() end')
    assert "Actor* c = actor_child(boss, 1);" in code and "actor_set_visible(c, 0);" in code


def test_un_etat_cite_sur_la_partie_se_juge_dans_les_sprites_de_la_partie():
    code = _cc('local boss = actor:spawn("Boss", vec2(1, 1))\nif boss then boss.Canon:play_anim("fire") end')
    assert "actor_play_anim(actor_child(boss, 1), 1)" in code              # "fire" est le 2e état du Canon
    erreurs = _ce('local boss = actor:spawn("Boss", vec2(1, 1))\nif boss then boss.Canon:play_anim("mort") end')
    assert len(erreurs) == 1 and "'mort'" in erreurs[0] and "fire" in erreurs[0]


def test_la_partie_atteinte_par_get_avec_un_indice_aussi():
    code = _cc('local boss = actor:get("Boss", 1)\nif boss then boss.Canon:hide() end')
    assert "actor_child(boss, 1)" in code


def test_une_partie_inconnue_du_prefab_est_refusee():
    erreurs = _ce('local boss = actor:spawn("Boss", vec2(1, 1))\nif boss then boss.Tourelle:hide() end')
    assert erreurs and any("Tourelle" in e for e in erreurs)


def test_sans_prefab_connu_pas_de_partie_par_le_nom():
    """`actor:get(i)` ne désigne aucun prefab que le build connaisse : on ne devine pas ses parties."""
    erreurs = _ce('local boss = actor:get(1)\nif boss then boss.Canon:hide() end')
    assert erreurs and any("Canon" in e for e in erreurs)


def test_la_partie_d_une_partie_navigue_aussi():
    code = _cc('local boss = actor:spawn("Boss", vec2(1, 1))\nif boss then boss.Canon.root:hide() end')
    assert "actor_root(actor_child(boss, 1))" in code


# ── chef.Bras : l'enfant de scène d'un acteur POSÉ, depuis une référence ──────────────────────────

_PLACED = {"Chef": {"Bras": "&g_actors[ACTOR_SC_BRAS]"}}
_PLACED_LIBS = {"Chef": {"Bras": _lib(anim_names=["idle", "tir"])}}


def _cp(body: str, top: str = "") -> str:
    ctx = CodegenContext(actor_name="Ctrl", actor_sym="Ctrl", anim_names=["idle"], sfx_names=[], music_names=[],
                         global_names=set(), const_names=set(), all_actor_syms=["Ctrl", "Chef", "Bras"], scene_sym="Sc",
                         actor_children=_PLACED, actor_child_sprites=_PLACED_LIBS)
    return generate(parse(f"{top}\nfunction on_update()\n{body}\nend\n"), ctx)[0]


def _cpe(body: str, top: str = "") -> list[str]:
    ctx = BuildContext(actor_name="Ctrl", anim_names=["idle"], sprite_ids=["a"], actor_names=["Chef", "Bras"],
                       actor_children=_PLACED, actor_child_sprites=_PLACED_LIBS)
    return [e.message for e in check(parse(f"{top}\nfunction on_update()\n{body}\nend\n"), ctx) if e.level == "error"]


def test_l_enfant_d_un_acteur_pose_se_nomme_depuis_sa_reference():
    code = _cp('local chef = actor:get("Chef")\nif chef then chef.Bras:hide() end')
    assert "actor_placed_child(chef, &g_actors[ACTOR_SC_BRAS])" in code
    assert 'actor_active_warn(actor_placed_child(chef, &g_actors[ACTOR_SC_BRAS]), "hide()")' in code


def test_l_enfant_se_nomme_aussi_en_chaine_directe():
    code = _cp('actor:get("Chef").Bras:hide()')
    assert "actor_placed_child(actor_live(&g_actors[ACTOR_SC_CHEF]), &g_actors[ACTOR_SC_BRAS])" in code
    assert "actor_active_warn(" in code                     # nil si le chef a disparu : l'appel est sauté


def test_un_etat_cite_sur_l_enfant_pose_se_juge_dans_ses_sprites():
    code = _cp('local chef = actor:get("Chef")\nif chef then chef.Bras:play_anim("tir") end')
    assert "actor_play_anim(actor_placed_child(chef, &g_actors[ACTOR_SC_BRAS]), 1)" in code
    erreurs = _cpe('local chef = actor:get("Chef")\nif chef then chef.Bras:play_anim("mort") end')
    assert len(erreurs) == 1 and "'mort'" in erreurs[0] and "tir" in erreurs[0]


def test_un_enfant_pose_inconnu_est_refuse():
    erreurs = _cpe('local chef = actor:get("Chef")\nif chef then chef.Jambe:hide() end')
    assert erreurs and any("Jambe" in e for e in erreurs)


def test_le_nom_d_un_acteur_pose_n_ouvre_pas_les_parties_d_un_prefab_du_meme_nom():
    """`actor:get("Chef")` vise l'acteur posé ; les parties d'un PREFAB « Chef » ne répondent qu'à `actor:spawn("Chef")`."""
    ctx = CodegenContext(actor_name="Ctrl", actor_sym="Ctrl", anim_names=["idle"], sfx_names=[], music_names=[],
                         global_names=set(), const_names=set(), all_actor_syms=["Ctrl", "Chef"], scene_sym="Sc",
                         prefab_children={"Chef": {"Canon": 1}}, prefab_child_sprites={"Chef": {"Canon": _lib(anim_names=["a"])}})
    code = generate(parse('function on_update()\nlocal c = actor:spawn("Chef", vec2(1, 1))\nif c then c.Canon:hide() end\nend\n'), ctx)[0]
    assert "actor_child(c, 1)" in code


def test_l_enfant_pose_atteint_par_une_reference_a_a_son_tour_ses_propres_enfants():
    """`chef.Bras` est l'acteur posé « Bras » : on connaît son identité, donc ses propres enfants se nomment (`bras.Pointe`)."""
    placed = {"Chef": {"Bras": "&g_actors[ACTOR_SC_BRAS]"}, "Bras": {"Pointe": "&g_actors[ACTOR_SC_POINTE]"}}
    ctx = CodegenContext(actor_name="Ctrl", actor_sym="Ctrl", anim_names=["idle"], sfx_names=[], music_names=[],
                         global_names=set(), const_names=set(), all_actor_syms=["Ctrl", "Chef", "Bras", "Pointe"],
                         scene_sym="Sc", actor_children=placed)
    code = generate(parse('function on_update()\nlocal chef = actor:get("Chef")\nlocal bras = chef.Bras\n'
                          'local pointe = bras.Pointe\nif pointe then pointe:hide() end\nend\n'), ctx)[0]
    assert "Actor* bras = actor_placed_child(chef, &g_actors[ACTOR_SC_BRAS]);" in code
    assert "Actor* pointe = actor_placed_child(bras, &g_actors[ACTOR_SC_POINTE]);" in code


# ── La garde sur nil : lire ou écrire une propriété d'un acteur qui a disparu ───────────────────

def test_une_lecture_sur_une_reference_rend_0_si_l_acteur_a_disparu():
    code = _cc('local boss = actor:spawn("Boss", vec2(1, 1))\nlocal c = boss.Canon\nlocal v = c.visible')
    assert 'int v = (actor_exists_warn(c, "reading visible") ? actor_get_visible(c) : 0);' in code


def test_un_composite_lu_rend_le_vecteur_nul():
    code = _cc('local boss = actor:spawn("Boss", vec2(1, 1))\nlocal p = boss.Canon.position')
    assert ('Vec2 p = (actor_exists_warn(actor_child(boss, 1), "reading position") '
            '? actor_get_position(actor_child(boss, 1)) : (Vec2){0});') in code


def test_une_ecriture_sur_une_reference_est_sautee_si_l_acteur_a_disparu():
    code = _cc('local boss = actor:spawn("Boss", vec2(1, 1))\nboss.Canon.position = vec2(3, 4)')
    assert ('if (actor_exists_warn(actor_child(boss, 1), "setting position")) '
            'actor_set_position(actor_child(boss, 1), (Vec2){3, 4});') in code


def test_l_ecriture_d_un_champ_de_composite_est_gardee_aussi():
    code = _cc('local boss = actor:spawn("Boss", vec2(1, 1))\nboss.Canon.position.x = 7')
    assert 'if (actor_exists_warn(actor_child(boss, 1), "setting position")) { Vec2 _field = ' in code


def test_self_other_et_les_enfants_de_self_ne_sont_jamais_gardes():
    """Le contexte du handler est vivant, et `self.Bras` est une adresse du build : pas de test de vie, pas de coût."""
    code = _c("other.position = vec2(1, 2)\nlocal x = other.position.x\nlocal y = self.position.y")
    assert "actor_set_position(other, (Vec2){1, 2});" in code
    assert "actor_exists_warn" not in code.split("on_collision_enter")[1].split("}")[0]


def test_une_chaine_de_parent_est_gardee():
    code = _c("local x = other.parent.position.x")
    assert 'actor_exists_warn(actor_parent(other), "reading position")' in code


def test_une_comparaison_nommee_sur_une_reference_est_gardee():
    code = _cc('local boss = actor:spawn("Boss", vec2(1, 1))\nif boss.Canon.anim == "fire" then boss.Canon:hide() end')
    assert 'actor_exists_warn(actor_child(boss, 1), "reading anim")' in code
