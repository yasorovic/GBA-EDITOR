"""Les exports d'un acteur POSÉ sont émis en variables C initialisées à la valeur
de l'INSTANCE (chantier « Les exports de script, câblés au jeu », étape 1).

Avant : `ScriptComponent.exports_values` était authoré et stocké, mais le codegen
ne le lisait nulle part — toutes les instances tombaient sur le `default` du
script. Ici on verrouille que la valeur d'instance atteint le C, et que bool/enum
se résolvent en entier (le moteur est entièrement entier)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


_SRC = (
    "exports = {\n"
    '    speed = { type = "int", default = 5 },\n'
    '    angry = { type = "bool", default = false },\n'
    '    team  = { type = "enum", default = "RED", values = {"RED", "BLUE"} },\n'
    "}\n"
    "function on_update()\n"
    "    speed = speed + 1\n"
    "end\n"
)


def _gen(export_inits: dict) -> str:
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    script = parse(_SRC)
    code, _w, _n = generate(script, CodegenContext(
        actor_name="Guard", actor_sym="Scene_Guard", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Scene_Guard"], is_pooled=False,
        export_inits=export_inits))
    return code


def test_valeur_dinstance_atteint_le_c():
    # Ce que lua_compiler poserait pour un acteur dont l'éditeur a réglé
    # speed=12, angry=true, team="BLUE".
    code = _gen({"speed": "12", "angry": "1", "team": "1"})
    assert "speed = 12;" in code
    assert "angry = 1;" in code
    assert "team = 1;" in code


def test_sans_override_les_valeurs_par_defaut_du_script():
    # export_inits calculé depuis les defaults : speed=5, angry=false→0, team=RED→0.
    code = _gen({"speed": "5", "angry": "0", "team": "0"})
    assert "speed = 5;" in code
    assert "angry = 0;" in code
    assert "team = 0;" in code


# ── La résolution d'une valeur en littéral C ──────────────────────

def test_poole_init_depuis_le_template(tmp_path):
    """Cas POOLÉ (D2, tranche 1) : l'init d'un export vient de export_inits (repli
    template prefab → défaut), qu'il soit muté (champ d'état par instance) ou lu
    seulement (constante partagée)."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = (
        'exports = { hp = { type = "int", default = 1 }, dmg = { type = "int", default = 1 } }\n'
        "function on_update()\n"
        "    hp = hp - dmg\n"   # hp muté → état ; dmg lu seulement → partagé
        "end\n"
    )
    code, _w, _n = generate(parse(src), CodegenContext(
        actor_name="Bullet", actor_sym="Arena_Bullet", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Arena_Bullet"], is_pooled=True, pool_size=8,
        export_inits={"hp": "20", "dmg": "5"}))   # valeurs du template prefab
    # Uniformisation T3 : sur un prefab poolé, TOUT export réglable est par
    # instance, même lu seulement (dmg). Les deux sont donc des champs d'état.
    assert ".hp = 20" in code
    assert ".dmg = 5" in code


def _gen_pooled(src, **kw):
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    base = dict(actor_name="Bullet", actor_sym="Arena_Bullet", anim_names=[],
                sfx_names=[], music_names=[], global_names=set(), const_names=set(),
                all_actor_syms=["Arena_Bullet"], is_pooled=True, pool_size=8,
                scene_sym="Arena")
    base.update(kw)
    code, _w, _n = generate(parse(src), CodegenContext(**base))
    return code


def test_poole_emet_un_setter_par_export():
    """Tranche poolé T2/T3 : chaque export réglable d'un prefab poolé reçoit un
    setter extern — le seul point d'accès de l'état depuis le spawner."""
    src = ('exports = { hp = { type = "int", default = 1 } }\n'
           "function on_update()\n    hp = hp - 1\nend\n")
    code = _gen_pooled(src, export_inits={"hp": "20"})
    assert "void Arena_Bullet_set_hp(Actor* self, int v)" in code


def _gen_spawner(src, meta):
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    code, _w, _n = generate(parse(src), CodegenContext(
        actor_name="Cursor", actor_sym="Arena_Cursor", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Arena_Cursor"], scene_sym="Arena", spawn_exports=meta))
    return code


_SPAWN_META = {"Bullet": {"speed": {"type": "int", "values": []},
                          "team":  {"type": "enum", "values": ["RED", "BLUE"]}}}


def test_spawn_avec_table_ecrit_les_exports():
    src = ("function on_update()\n"
           '    local b = actor:spawn("Bullet", vec2(10, 20), { speed = 8, team = "BLUE" })\n'
           "end\n")
    code = _gen_spawner(src, _SPAWN_META)
    assert "extern void Arena_Bullet_set_speed(Actor* self, int v);" in code
    assert "Arena_Bullet_set_speed(b, 8);" in code
    assert "Arena_Bullet_set_team(b, 1);" in code   # "BLUE" → index 1


def test_spawn_nu_avec_table_utilise_un_temporaire():
    src = ("function on_update()\n"
           '    actor:spawn("Bullet", vec2(10, 20), { speed = 3 })\n'
           "end\n")
    code = _gen_spawner(src, _SPAWN_META)
    assert "Actor* _spawn0 = spawn_Arena_Bullet(10, 20);" in code
    assert "Arena_Bullet_set_speed(_spawn0, 3);" in code


def test_spawn_sans_table_inchange():
    src = ("function on_update()\n"
           '    local b = actor:spawn("Bullet", vec2(10, 20))\n'
           "end\n")
    code = _gen_spawner(src, _SPAWN_META)
    assert "spawn_Arena_Bullet(10, 20)" in code
    assert "_set_" not in code   # aucun setter, aucune table


# ── Émission C d'un acteur posé : types non-entiers ───────────────

def test_pose_emet_string_refs_et_composites():
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = _SRC_TYPED + "function on_update()\nend\n"
    code, _w, _n = generate(parse(src), CodegenContext(
        actor_name="Guard", actor_sym="Scene_Guard", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Scene_Guard"], is_pooled=False,
        export_inits={"label": "TEXT_HELLO", "boom": "SFX_BOOM",
                      "next": "SCENE_IDX_WIN", "target": "TAG_SCENE_BOSS",
                      "home": "{ 3, 4 }", "box": "{ 0, 0, 16, 16 }"}))
    assert "label = TEXT_HELLO;" in code      # string → index de texte (int)
    assert "boom = SFX_BOOM;" in code         # sfx_ref → SFX_*
    assert "target = TAG_SCENE_BOSS;" in code # actor_ref → TAG_*
    assert "Vec2 " in code and "home = { 3, 4 };" in code
    assert "Rect " in code and "box = { 0, 0, 16, 16 };" in code


# ── Table de spawn : refs et composites ───────────────────────────

_SPAWN_META2 = {"Bullet": {
    "vel":  {"type": "vec2",      "values": []},
    "boom": {"type": "sfx_ref",   "values": []},
    "tgt":  {"type": "actor_ref", "values": []},
}}


def test_spawn_table_refs_et_vec():
    src = ("function on_update()\n"
           '    local b = actor:spawn("Bullet", vec2(0, 0), '
           '{ vel = vec2(1, 2), boom = "Pop", tgt = "Enemy" })\n'
           "end\n")
    code = _gen_spawner(src, _SPAWN_META2)
    # Externs typés — un composite passe un Vec2, une réf un int.
    assert "extern void Arena_Bullet_set_vel(Actor* self, Vec2 v);" in code
    assert "extern void Arena_Bullet_set_boom(Actor* self, int v);" in code
    # Valeurs résolues au site du spawn, dans la scène du spawner.
    assert "Arena_Bullet_set_vel(b, (Vec2){1, 2});" in code
    assert "Arena_Bullet_set_boom(b, SFX_POP);" in code
    assert "Arena_Bullet_set_tgt(b, TAG_ARENA_ENEMY);" in code


def test_poole_setter_composite_typé():
    """Un export composite d'un prefab poolé reçoit un setter Vec2, pas int."""
    src = ('exports = { vel = { type = "vec2", default = {0, 0} } }\n'
           "function on_update()\n    vel = vel\nend\n")
    code = _gen_pooled(src, export_inits={"vel": "{ 0, 0 }"})
    assert "void Arena_Bullet_set_vel(Actor* self, Vec2 v)" in code
    assert "Vec2 vel;" in code


# ── Checker : la table de spawn accepte les nouveaux types ─────────

def _spawn_errors2(src, meta=_SPAWN_META2, **ctx):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    errs = check(parse(src), BuildContext(actor_name="Cursor",
                 prefab_names=["Bullet"], spawn_exports=meta,
                 sfx_names=["Pop"], scene_names=["Victory"],
                 actor_names=["Enemy"], **ctx))
    return [e.message for e in errs]


def test_checker_accepte_vec_et_refs():
    src = ('function on_update()\n'
           '    local b = actor:spawn("Bullet", vec2(0,0), '
           '{ vel = vec2(1,2), boom = "Pop", tgt = "Enemy" })\n'
           'end\n')
    assert [m for m in _spawn_errors2(src)] == []


def test_checker_refuse_vec_sans_constructeur():
    src = ('function on_update()\n'
           '    local b = actor:spawn("Bullet", vec2(0,0), { vel = 5 })\n'
           'end\n')
    assert any("vec2(...)" in m for m in _spawn_errors2(src))


def test_checker_avertit_ref_inconnue():
    src = ('function on_update()\n'
           '    local b = actor:spawn("Bullet", vec2(0,0), { boom = "Absent" })\n'
           'end\n')
    assert any("Absent" in m for m in _spawn_errors2(src))


# ── Checker de la table de spawn ──────────────────────────────────

def _spawn_errors(src):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    errs = check(parse(src), BuildContext(actor_name="Cursor",
                 prefab_names=["Bullet"], spawn_exports=_SPAWN_META))
    return [e.message for e in errs if e.level == "error"]


def test_checker_refuse_une_cle_inconnue():
    src = ('function on_update()\n'
           '    local b = actor:spawn("Bullet", vec2(0,0), { vitesse = 8 })\n'
           'end\n')
    assert any("vitesse" in m and "réglable" in m for m in _spawn_errors(src))


def test_checker_refuse_la_table_hors_statement():
    src = ('function on_update()\n'
           '    local n = foo(actor:spawn("Bullet", vec2(0,0), { speed = 8 }))\n'
           'end\n')
    assert any("début de ligne" in m for m in _spawn_errors(src))


def test_checker_accepte_une_table_valide():
    src = ('function on_update()\n'
           '    local b = actor:spawn("Bullet", vec2(0,0), { speed = 8, team = "RED" })\n'
           'end\n')
    assert _spawn_errors(src) == []


def test_export_c_literal():
    from codegen.runtime_codegen.lua_compiler import _export_c_literal
    assert _export_c_literal("int", 12, []) == "12"
    assert _export_c_literal("float", 3.9, []) == "3"          # pas de flottant au runtime
    assert _export_c_literal("bool", True, []) == "1"
    assert _export_c_literal("bool", False, []) == "0"
    assert _export_c_literal("enum", "BLUE", ["RED", "BLUE"]) == "1"
    assert _export_c_literal("enum", "RED", ["RED", "BLUE"]) == "0"
    assert _export_c_literal("enum", "GONE", ["RED", "BLUE"]) == "0"   # introuvable → 0
    assert _export_c_literal("int", None, []) == "0"                   # défaut manquant → 0


# ── L'override d'instance prime sur le défaut du script ───────────

def _int_resolver():
    """Un résolveur scène-scopé sans projet : suffit aux types entiers (le
    résolveur n'utilise `p` nulle part, et ces cas ne citent ni ref ni texte)."""
    from codegen.runtime_codegen.lua_compiler import _make_export_resolver
    return _make_export_resolver(None, "Scene", [])


def test_override_prime_sur_defaut():
    from scripting.parser import parse
    from codegen.runtime_codegen.lua_compiler import _export_inits
    script = parse(_SRC)

    comp = SimpleNamespace(exports_values={"speed": 12, "team": "BLUE"})
    actor = SimpleNamespace(get_component=lambda k: comp if k == "script" else None)

    inits = _export_inits(actor, script, _int_resolver())
    assert inits["speed"] == "12"   # override
    assert inits["team"] == "1"     # override "BLUE" → index 1
    assert inits["angry"] == "0"    # pas d'override → défaut false → 0


def test_export_inits_sans_override_lit_les_defauts():
    # Sans aucune valeur d'instance : les défauts du script, enum résolu par index.
    from scripting.parser import parse
    from codegen.runtime_codegen.lua_compiler import _export_inits
    script = parse(_SRC)
    actor = SimpleNamespace(get_component=lambda k: SimpleNamespace(exports_values={}))
    inits = _export_inits(actor, script, _int_resolver())
    assert inits["speed"] == "5"    # défaut int
    assert inits["angry"] == "0"    # défaut false
    assert inits["team"] == "0"     # défaut "RED" → index 0 (enum résolu, plus de 0 par défaut)


# ── Les types non-entiers : string, *_ref, vec/rect ───────────────

_SRC_TYPED = (
    "exports = {\n"
    '    label  = { type = "string",    default = "Hello" },\n'
    '    boom   = { type = "sfx_ref",   default = "" },\n'
    '    next   = { type = "scene_ref", default = "" },\n'
    '    target = { type = "actor_ref", default = "" },\n'
    '    home   = { type = "vec2",      default = {3, 4} },\n'
    '    box    = { type = "rect",      default = {0, 0, 16, 16} },\n'
    "}\n"
)


def test_resolveur_string_vers_index_de_texte():
    from scripting.parser import parse
    from codegen.runtime_codegen.lua_compiler import (_export_inits,
                                                      _make_export_resolver)
    from scripting.api import anon_text_key, text_constant
    script = parse(_SRC_TYPED)
    # La table de textes du build connaît l'entrée anonyme du littéral.
    text_keys = [anon_text_key("Hello")]
    res = _make_export_resolver(None, "Scene", text_keys)
    actor = SimpleNamespace(get_component=lambda k: SimpleNamespace(exports_values={}))
    inits = _export_inits(actor, script, res)
    assert inits["label"] == text_constant(anon_text_key("Hello"))


def test_resolveur_refs_et_composites():
    from scripting.parser import parse
    from codegen.runtime_codegen.lua_compiler import (_export_inits,
                                                      _make_export_resolver)
    script = parse(_SRC_TYPED)
    res = _make_export_resolver(None, "Arena", [])
    comp = SimpleNamespace(exports_values={
        "boom": "Explosion", "next": "Victory", "target": "Boss",
        "home": [10, 20]})
    actor = SimpleNamespace(get_component=lambda k: comp)
    inits = _export_inits(actor, script, res)
    assert inits["boom"] == "SFX_EXPLOSION"
    assert inits["next"] == "SCENE_IDX_VICTORY"
    assert inits["target"] == "TAG_ARENA_BOSS"     # qualifié par la scène
    assert inits["home"] == "{ 10, 20 }"           # override vec2
    assert inits["box"] == "{ 0, 0, 16, 16 }"      # défaut rect
    assert inits["boom"] and inits["target"]       # non vides


def test_resolveur_ref_vide_tombe_sur_zero():
    from scripting.parser import parse
    from codegen.runtime_codegen.lua_compiler import (_export_inits,
                                                      _make_export_resolver)
    script = parse(_SRC_TYPED)
    res = _make_export_resolver(None, "Scene", [])
    actor = SimpleNamespace(get_component=lambda k: SimpleNamespace(exports_values={}))
    inits = _export_inits(actor, script, res)
    assert inits["boom"] == "0"      # défaut "" → pas de référence
    assert inits["target"] == "0"


# ── Le checker : un nom d'export ne masque rien ───────────────────

def _errors(src: str, **ctx):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    errs = check(parse(src), BuildContext(actor_name="Guard", **ctx))
    return [e.message for e in errs if e.level == "error"]


def _warnings(src: str, **ctx):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    errs = check(parse(src), BuildContext(actor_name="Guard", **ctx))
    return [e.message for e in errs if e.level == "warning"]


def test_export_ne_peut_masquer_un_champ_actor():
    msgs = _errors('exports = { position = { type = "int", default = 0 } }\n')
    assert any("position" in m and "Actor" in m for m in msgs)


def test_export_ne_peut_masquer_un_global():
    msgs = _errors('exports = { score = { type = "int", default = 0 } }\n',
                   global_names=["score"])
    assert any("score" in m and "globale" in m for m in msgs)


def test_export_ne_peut_masquer_un_mot_dapi():
    msgs = _errors('exports = { input = { type = "int", default = 0 } }\n')
    assert any("input" in m for m in msgs)


def test_un_nom_dexport_libre_passe():
    assert _errors('exports = { speed = { type = "int", default = 5 } }\n') == []


def test_export_composite_est_un_vec_pour_le_checker():
    # Régression (validation ROM 2026-09-21) : un export vec2/rect porte son type
    # dès la déclaration, donc `home + vec2(1,0)` et `box.x` se valident comme sur
    # un vrai vec — sans ce semage, le checker croyait `home` scalaire et refusait
    # « + entre un vec2 et un scalaire ».
    src = ('exports = { home = { type = "vec2", default = {0,0} },\n'
           '            box  = { type = "rect", default = {0,0,8,8} } }\n'
           'function on_update()\n'
           '    home = home + vec2(1, 0)\n'
           '    local n = box.x + home.y\n'
           'end\n')
    assert _errors(src) == []


def test_tous_les_types_cables_sans_avertissement():
    # Tous les types d'export sont désormais câblés jusqu'au C : plus d'avertissement
    # « valeur d'instance non appliquée » (chantier « Les exports de script »).
    for typ, dflt in (("string", '"hi"'), ("sfx_ref", '""'),
                      ("actor_ref", '""'), ("vec2", "{0, 0}"),
                      ("rect", "{0, 0, 8, 8}")):
        src = f'exports = {{ v = {{ type = "{typ}", default = {dflt} }} }}\n'
        assert _errors(src) == [], typ
        assert not any("instance" in w for w in _warnings(src)), typ
