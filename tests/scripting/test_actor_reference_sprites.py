"""`actor:get("Boss")` et `actor:spawn("Bullet", pos)` désignent un acteur par un littéral : le
Build connaît donc ses sprites, et un état cité sur la référence se juge dans SES sprites.

Avant : seul `self` et les enfants (`self.Canon`) avaient une bibliothèque ; tout autre acteur
était refusé (« can only be made on self »). Un prefab est un acteur, la bibliothèque est de
même nature. Un indice (`actor:get(i)`) ne désigne rien que le Build connaisse : refus, avec
le moyen d'y remédier.
"""

from __future__ import annotations

from scripting.api import SpriteLibrary


def _lib(**kw):
    return SpriteLibrary(**{k: tuple(tuple(x) if isinstance(x, list) else x for x in v)
                            for k, v in kw.items()})


_BOSS = {"Boss": _lib(anim_names=["idle", "rage"], sprite_ids=["calme", "feu"])}
_BULLET = {"Bullet": _lib(anim_names=["fly", "boom"])}
_EXPORTS = {"Boss": {"hp": {"type": "int", "values": None},
                     "state": {"type": "enum", "values": ["CALM", "RAGE"]},
                     "tint": {"type": "vec2", "values": None},
                     "target": {"type": "actor_ref", "values": None}}}
_SPAWN = {"Bullet": {"speed": {"type": "int", "values": None}}}


def _src(body: str, top: str = "") -> str:
    return f"{top}\nfunction on_update()\n{body}\nend\n"


def _errors(body: str, top: str = "", actor_sprites=_BOSS, prefab_sprites=_BULLET):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    ctx = BuildContext(actor_name="Ctrl", anim_names=["idle"], sprite_ids=["a"],
                       actor_names=["Boss"], prefab_names=["Bullet"],
                       pooled_prefab_names=["Bullet"],
                       actor_sprites=actor_sprites, prefab_sprites=prefab_sprites,
                       actor_exports=_EXPORTS, spawn_exports=_SPAWN)
    return [e.message for e in check(parse(_src(body, top)), ctx) if e.level == "error"]


def _c(body: str, top: str = "") -> str:
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    ctx = CodegenContext(actor_name="Ctrl", actor_sym="Ctrl", anim_names=["idle"],
                         sfx_names=[], music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=["Ctrl", "Boss"], scene_sym="Sc",
                         actor_sprites=_BOSS, prefab_sprites=_BULLET,
                         actor_exports=_EXPORTS, spawn_exports=_SPAWN)
    return generate(parse(_src(body, top)), ctx)[0]


# ── Un acteur de la scène, par un littéral ───────────────────────────

def test_etat_d_un_acteur_pris_par_get_emis_dans_ses_sprites():
    code = _c('local boss = actor:get("Boss")\nif boss then boss:play_anim("rage") end')
    assert "actor_play_anim(boss, 1)" in code
    assert "ANIM_CTRL_RAGE" not in code


def test_etat_d_un_acteur_en_chaine_directe():
    code = _c('actor:get("Boss"):play_anim("rage")')
    assert "actor_play_anim(actor_live(&g_actors[ACTOR_SC_BOSS]), 1)" in code


def test_id_d_apparence_d_un_acteur_pris_par_get():
    code = _c('local boss = actor:get("Boss")\nif boss then boss:activate_sprite("feu") end')
    assert "actor_set_appearance(boss, 1)" in code


def test_etat_absent_des_sprites_de_l_acteur_refuse_avec_son_nom():
    errs = _errors('local boss = actor:get("Boss")\nif boss then boss:play_anim("mort") end')
    assert len(errs) == 1 and "'mort'" in errs[0] and "boss" in errs[0] and "rage" in errs[0]


def test_etat_de_l_acteur_courant_ne_vaut_pas_pour_la_cible():
    """`idle` est un état de Ctrl (anim_names) ET de Boss ici ; `walk` n'est qu'à Ctrl."""
    errs = _errors('local boss = actor:get("Boss")\nif boss then boss:play_anim("walk") end',
                   actor_sprites={"Boss": _lib(anim_names=["rage"])})
    assert len(errs) == 1 and "'walk'" in errs[0]


def test_etat_connu_accepte():
    assert _errors('local boss = actor:get("Boss")\nif boss then boss:play_anim("RAGE") end') == []


# ── Un prefab, par un littéral ───────────────────────────────────────

def test_etat_d_un_prefab_spawne_emis_dans_les_sprites_du_prefab():
    code = _c('local b = actor:spawn("Bullet", vec2(1, 1))\nif b then b:play_anim("boom") end')
    assert "actor_play_anim(b, 1)" in code


def test_etat_absent_du_prefab_spawne_refuse():
    errs = _errors('local b = actor:spawn("Bullet", vec2(1, 1))\nif b then b:play_anim("rage") end')
    assert len(errs) == 1 and "'rage'" in errs[0] and "fly" in errs[0]


# ── Lecture par propriété ────────────────────────────────────────────

def test_lecture_de_l_etat_d_un_acteur_emise_par_son_rang():
    code = _c('local boss = actor:get("Boss")\n'
              'if boss and boss.anim == "rage" then self:destroy() end')
    assert "(actor_get_anim(boss) == 1)" in code


def test_lecture_d_un_etat_absent_refusee():
    errs = _errors('local boss = actor:get("Boss")\n'
                   'if boss and boss.anim == "mort" then self:destroy() end')
    assert len(errs) == 1 and "'mort'" in errs[0]


# ── Ce que le Build ne connaît pas ───────────────────────────────────

def test_indice_ne_designe_aucun_acteur_connu_et_le_message_dit_comment_faire():
    errs = _errors('local u = actor:get(1)\nif u then u:play_anim("rage") end')
    assert len(errs) == 1
    assert 'actor:get("Name")' in errs[0] and "actor:get(i)" in errs[0]


def test_variable_reaffectee_a_un_autre_acteur_perd_sa_bibliotheque():
    """On ne sait plus de quel acteur on parle : refus plutôt qu'une constante au hasard."""
    errs = _errors('local a = actor:get("Boss")\n'
                   'a = actor:spawn("Bullet", vec2(1, 1))\n'
                   'if a then a:play_anim("rage") end')
    assert errs


def test_methode_sans_nom_d_etat_reste_permise_sur_un_indice():
    assert _errors('local u = actor:get(1)\nif u then u:hide() end') == []


# ── Une référence qui survit à l'image ───────────────────────────────

def test_variable_de_tete_ne_peut_pas_demarrer_sur_un_acteur():
    """L'initialiseur d'une variable statique est une constante, la scène n'existe pas encore."""
    errs = _errors('', top='local boss = actor:get("Boss")')
    assert len(errs) == 1 and "boss" in errs[0] and "nil" in errs[0]


_LAST = 'local last = nil'


def test_variable_de_tete_tient_une_reference_rangee_et_resolue():
    code = _c('last = actor:spawn("Bullet", vec2(1, 1))\nif last then last:hide() end', top=_LAST)
    assert "last = actor_ref_make(spawn_Sc_Bullet(1, 1));" in code
    assert "if (actor_ref_get(last))" in code
    assert ('if (actor_active_warn(actor_ref_get(last), "hide()")) '
            'actor_set_visible(actor_ref_get(last), 0);') in code


def test_nil_vide_la_reference():
    assert "last = 0;" in _c('last = nil', top=_LAST)


def test_la_reference_de_tete_porte_la_bibliotheque_du_prefab():
    body = 'last = actor:spawn("Bullet", vec2(1, 1))\nif last then last:play_anim("%s") end'
    assert _errors(body % "boom", top=_LAST) == []
    errs = _errors(body % "rage", top=_LAST)
    assert len(errs) == 1 and "'rage'" in errs[0] and "fly" in errs[0]
    assert "actor_play_anim(actor_ref_get(last), 1)" in _c(body % "boom", top=_LAST)


def test_export_d_une_reference_de_tete():
    code = _c('last = actor:spawn("Bullet", vec2(1, 1))\nlast.speed = 3', top=_LAST)
    assert "Sc_Bullet_set_speed(actor_ref_get(last), 3);" in code


def test_propriete_d_une_reference_de_tete_est_resolue():
    code = _c('last = actor:get("Boss")\nlocal x = last.position.x', top=_LAST)
    assert "actor_get_position(actor_ref_get(last))" in code


def test_deux_acteurs_possibles_ne_donnent_aucune_bibliotheque():
    errs = _errors('last = actor:get("Boss")\nlast = actor:spawn("Bullet", vec2(1, 1))\n'
                   'if last then last:play_anim("rage") end', top=_LAST)
    assert errs


def test_une_variable_du_meme_nom_declaree_dans_un_handler_n_est_pas_une_reference():
    code = _c('local last = actor:spawn("Bullet", vec2(1, 1))\nif last then last:hide() end',
              top=_LAST)
    assert "actor_ref_make" not in code


def test_affectation_d_un_acteur_a_un_element_de_tableau_refusee():
    errs = _errors('bs[1] = actor:spawn("Bullet", vec2(1, 1))', top='local bs = {0, 0, 0}')
    assert len(errs) == 1 and "bs" in errs[0]


def test_local_de_handler_peut_tenir_un_acteur():
    assert _errors('local b = actor:spawn("Bullet", vec2(1, 1))\nif b then b:hide() end') == []


# ── Une action sur la référence d'un acteur qui a pu disparaître ─────

def test_action_sur_une_reference_est_gardee_et_signalee():
    code = _c('local boss = actor:get("Boss")\nboss:hide()')
    assert 'if (actor_active_warn(boss, "hide()")) actor_set_visible(boss, 0);' in code


def test_action_sur_un_get_en_chaine_est_gardee():
    code = _c('actor:get("Boss"):hide()')
    guard = "actor_live(&g_actors[ACTOR_SC_BOSS])"
    assert f'if (actor_active_warn({guard}, "hide()")) actor_set_visible({guard}, 0);' in code


def test_action_sur_self_n_est_pas_gardee():
    assert "_warn" not in _c('self:hide()')


def test_les_verbes_du_cycle_de_vie_exigent_l_existence_pas_l_activite():
    """Un acteur désactivé se réactive, se désactive encore et se détruit : seul un acteur détruit ou nil
    est sauté."""
    for verbe, c_call in (("activate", "actor_set_active(boss, 1)"), ("deactivate", "actor_set_active(boss, 0)")):
        code = _c('local boss = actor:get("Boss")\nboss:%s()' % verbe)
        assert f'if (actor_exists_warn(boss, "{verbe}()")) {c_call};' in code
        assert "actor_active_warn" not in code
    code = _c('local boss = actor:get("Boss")\nboss:destroy()')
    assert 'if (actor_exists_warn(boss, "destroy()")) actor_destroy_with_sfx(boss);' in code


def test_spawn_n_est_jamais_evalue_deux_fois():
    code = _c('actor:spawn("Bullet", vec2(1, 1)):hide()')
    assert "actor_active_warn" not in code


# ── Lire et écrire les exports d'une autre instance ──────────────────

_BOSS_LOCAL = 'local boss = actor:get("Boss")\n'


def test_lecture_d_un_export_passe_par_le_getter_de_l_acteur():
    code = _c(_BOSS_LOCAL + "local n = boss.hp")
    assert '(actor_exists_warn(boss, "reading hp") ? Sc_Boss_get_hp(boss) : 0)' in code
    assert "extern int Sc_Boss_get_hp(Actor* self);" in code


def test_ecriture_d_un_export_passe_par_le_setter_et_est_gardee():
    code = _c(_BOSS_LOCAL + "boss.hp = 3")
    assert 'if (actor_exists_warn(boss, "writing hp")) Sc_Boss_set_hp(boss, 3);' in code
    assert "extern void Sc_Boss_set_hp(Actor* self, int v);" in code


def test_etiquette_d_enum_ecrite_par_son_rang():
    assert "Sc_Boss_set_state(boss, 1);" in _c(_BOSS_LOCAL + 'boss.state = "RAGE"')


def test_etiquette_d_enum_comparee_par_son_rang():
    code = _c(_BOSS_LOCAL + 'if boss.state == "RAGE" then self:destroy() end')
    assert "Sc_Boss_get_state(boss)) == 1" in code.replace(" : 0", "")


def test_export_d_un_prefab_spawne_ecrit_par_son_setter():
    code = _c('local b = actor:spawn("Bullet", vec2(1, 1))\nif b then b.speed = 4 end')
    assert "Sc_Bullet_set_speed(b, 4);" in code


def test_export_inconnu_refuse_avec_la_liste_des_exports():
    errs = _errors(_BOSS_LOCAL + "boss.mana = 3")
    assert len(errs) == 1 and "mana" in errs[0]
    assert "hp" in errs[0] and "state" in errs[0] and "tint" in errs[0] and "target" in errs[0]


def test_etiquette_inconnue_refusee_en_ecriture_et_en_comparaison():
    assert _errors(_BOSS_LOCAL + 'boss.state = "SLEEP"')
    assert _errors(_BOSS_LOCAL + 'if boss.state == "SLEEP" then self:destroy() end')
    assert _errors(_BOSS_LOCAL + 'boss.state = "RAGE"') == []


def test_texte_dans_un_export_numerique_refuse():
    assert _errors(_BOSS_LOCAL + 'boss.hp = "beaucoup"')


def test_export_d_un_acteur_pris_par_indice_reste_refuse():
    errs = _errors("local u = actor:get(1)\nlocal n = u.hp")
    assert errs and "no field" in errs[0]


def test_export_connu_accepte_en_lecture_et_en_ecriture():
    assert _errors(_BOSS_LOCAL + "boss.hp = boss.hp - 1") == []


_EXPORTS_SCRIPT = ('exports = {\n'
                   '  hp = { type = "int", default = 5 },\n'
                   '  state = { type = "enum", default = "CALM", values = {"CALM", "RAGE"} },\n'
                   '}\n')


def test_un_acteur_pose_definit_les_accesseurs_de_ses_exports():
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    ctx = CodegenContext(actor_name="Boss", actor_sym="Sc_Boss", anim_names=[], sfx_names=[],
                         music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=["Sc_Boss"], scene_sym="Sc")
    code = generate(parse(_EXPORTS_SCRIPT + _src("")), ctx)[0]
    assert "int Sc_Boss_get_hp(Actor* self __attribute__((unused))) { return hp; }" in code
    assert "void Sc_Boss_set_state(Actor* self __attribute__((unused)), int v) { state = v; }" in code


def test_un_prefab_poole_definit_aussi_le_getter_a_cote_du_setter():
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    ctx = CodegenContext(actor_name="Bullet", actor_sym="Sc_Bullet", anim_names=[], sfx_names=[],
                         music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=["Sc_Bullet"], scene_sym="Sc", is_pooled=True, pool_size=4)
    code = generate(parse(_EXPORTS_SCRIPT + _src("")), ctx)[0]
    assert "void Sc_Bullet_set_hp(Actor* self, int v)" in code
    assert ("int Sc_Bullet_get_hp(Actor* self) { return "
            "g_state_Sc_Bullet[Sc_Bullet_pool_slot(self)].hp; }") in code


# ── Exports composites et références ─────────────────────────────────

def test_lecture_d_un_composite_rend_un_vec2_dans_une_variable_locale():
    code = _c(_BOSS_LOCAL + "local t = boss.tint")
    assert ('Vec2 t = (actor_exists_warn(boss, "reading tint") ? Sc_Boss_get_tint(boss) '
            ': (Vec2){0});') in code
    assert "extern Vec2 Sc_Boss_get_tint(Actor* self);" in code


def test_champ_d_un_composite_se_lit_sur_le_resultat():
    code = _c(_BOSS_LOCAL + "local x = boss.tint.x")
    assert "Sc_Boss_get_tint(boss) : (Vec2){0}).x" in code


def test_ecriture_d_un_composite_par_son_constructeur():
    code = _c(_BOSS_LOCAL + "boss.tint = vec2(1, 2)")
    assert 'if (actor_exists_warn(boss, "writing tint")) Sc_Boss_set_tint(boss, (Vec2){1, 2});' in code
    assert "extern void Sc_Boss_set_tint(Actor* self, Vec2 v);" in code


def test_ecriture_d_un_champ_de_composite_relit_modifie_reecrit():
    code = _c(_BOSS_LOCAL + "boss.tint.x = 3")
    assert ("{ Vec2 _field = Sc_Boss_get_tint(boss); _field.x = 3; "
            "Sc_Boss_set_tint(boss, _field); }") in code


def test_composite_d_un_autre_type_refuse():
    assert _errors(_BOSS_LOCAL + "boss.tint = 3")
    assert _errors(_BOSS_LOCAL + "boss.tint = vec3(1, 2, 3)")
    assert _errors(_BOSS_LOCAL + "boss.tint = vec2(1, 2)") == []


def test_reference_ecrite_et_comparee_par_son_nom():
    code = _c(_BOSS_LOCAL + 'boss.target = "Boss"\nif boss.target == "Boss" then self:destroy() end')
    assert "Sc_Boss_set_target(boss, ACTOR_SC_BOSS);" in code
    assert "Sc_Boss_get_target(boss) : 0) == ACTOR_SC_BOSS" in code


def test_reference_exige_un_nom_entre_guillemets():
    assert _errors(_BOSS_LOCAL + "boss.target = 3")
    assert _errors(_BOSS_LOCAL + 'boss.target = "Boss"') == []


def test_un_prefab_poole_definit_le_getter_d_un_composite():
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    ctx = CodegenContext(actor_name="Bullet", actor_sym="Sc_Bullet", anim_names=[], sfx_names=[],
                         music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=["Sc_Bullet"], scene_sym="Sc", is_pooled=True, pool_size=4,
                         export_inits={"tint": "{0, 0}"})
    src = 'exports = {\n  tint = { type = "vec2", default = {0, 0} },\n}\n' + _src("")
    code = generate(parse(src), ctx)[0]
    assert "void Sc_Bullet_set_tint(Actor* self, Vec2 v)" in code
    assert ("Vec2 Sc_Bullet_get_tint(Actor* self) { return "
            "g_state_Sc_Bullet[Sc_Bullet_pool_slot(self)].tint; }") in code


# ── Les instances d'un modèle : actor:count("Bullet"), actor:get("Bullet", i) ────────

_POOL = "g_model_Sc_Bullet, MODEL_SC_BULLET_COUNT"


def test_le_nombre_d_instances_vivantes_d_un_modele():
    code = _c('local n = actor:count("Bullet")')
    assert f"int n = actor_model_count({_POOL});" in code


def test_la_ieme_instance_vivante_se_prend_a_partir_de_1():
    code = _c('local b = actor:get("Bullet", 1)')
    assert f"Actor* b = actor_model_nth({_POOL}, 0);" in code
    code = _c('local i = 3\nlocal b = actor:get("Bullet", i)')
    assert f"actor_model_nth({_POOL}, (i) - 1)" in code


def test_une_instance_de_modele_porte_la_bibliotheque_et_les_exports_du_prefab():
    body = 'local b = actor:get("Bullet", 1)\nif b then b:play_anim("%s") end'
    assert _errors(body % "boom") == []
    errs = _errors(body % "rage")
    assert len(errs) == 1 and "'rage'" in errs[0] and "fly" in errs[0]
    assert "Sc_Bullet_set_speed(b, 4);" in _c('local b = actor:get("Bullet", 1)\nif b then b.speed = 4 end')


def test_une_boucle_sur_les_instances_d_un_modele():
    src = ('for i = 1, actor:count("Bullet") do\n'
           '    local b = actor:get("Bullet", i)\n'
           '    if b then b:hide() end\n'
           'end')
    assert _errors(src) == []
    code = _c(src)
    assert f"actor_model_count({_POOL})" in code and f"actor_model_nth({_POOL}, (i) - 1)" in code


def test_un_modele_sans_instance_dans_la_scene_est_refuse():
    errs = _errors('local b = actor:get("Boss", 1)')
    assert len(errs) == 1 and "'Boss'" in errs[0] and "Bullet" in errs[0]
    assert _errors('local n = actor:count("Boss")')


def test_les_formes_ordinaires_de_get_et_count_ne_changent_pas():
    assert _errors('local b = actor:get("Boss")\nlocal n = actor:count()\nlocal u = actor:get(1)') == []


def test_la_forme_instance_exige_un_nom_ecrit_et_deux_arguments_au_plus():
    assert _errors('local b = actor:get(1, 2)')
    assert _errors('local b = actor:get("Bullet", 1, 2)')
    assert _errors('local n = actor:count("Bullet", 1)')
