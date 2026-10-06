"""Le sous-ensemble Lua : ce qu'il refuse, et le fait qu'il le DISE.

Chacun de ces cas produisait auparavant l'un des deux silences que la v0.7.5
supprime :

  - un statement non géré rendait `None` — le bloc disparaissait du jeu, sans
    erreur de checker ni avertissement gcc ;
  - une expression non gérée rendait `ExprName("__unsupported_<Type>")`, ou un
    appel inconnu partait tel quel — donc un échec au `make`, sur la ligne
    générée et jamais sur sa cause.

C'est la définition d'un test ici (cf. `tests/` dans ARCHITECTURE) : une erreur
silencieuse, pas une exception.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]


def _errors(src: str, **ctx_kw) -> list[str]:
    """Les messages d'ERREUR d'un script, sans passer par le codegen."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext

    body = ctx_kw.pop("check_event_names", True)
    errs = check(parse(src), BuildContext(actor_name="Ball", **ctx_kw),
                 check_event_names=body)
    return [e.message for e in errs if e.level == "error"]


def _error_lines(src: str, **ctx_kw) -> list[int]:
    """Les lignes des erreurs d'un script (0 = la faute n'en a pas)."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    return [e.line for e in check(parse(src), BuildContext(actor_name="Ball", **ctx_kw))
            if e.level == "error"]


def _in_handler(body: str) -> str:
    return f"function on_update()\n{body}\nend\n"


# ── 1. Les constructions du langage qui disparaissaient ────────────
# Le corps de boucle n'arrivait pas jusqu'au C, et rien ne le disait : un jeu
# où la logique manque, sans une ligne de log pour le soupçonner.

@pytest.mark.parametrize("body, attendu", [
    ("for k, v in pairs(t) do n = n + v end", "for … in"),
    ("repeat n = n - 1 until n == 0",         "repeat … until"),
    ("goto fin\n::fin::",                     "goto"),
    ("do n = 1 end",                          "do … end"),
    ("local function f() return 1 end",       "function"),
    ("function f() return 1 end",             "function"),
])
def test_statement_refuse_avec_sa_ligne(body, attendu):
    errs = _errors(_in_handler(body))
    assert errs, f"« {body} » ne produit aucune erreur — il disparaît en silence"
    assert any(attendu in e for e in errs), errs
    assert any(_error_lines(_in_handler(body))), \
        f"le refus de « {body} » ne situe pas la faute : {errs}"


# ── 2. Les expressions qui partaient en C invalide ─────────────────

@pytest.mark.parametrize("expr, attendu", [
    ('local s = "a" .. "b"',            ".."),
    ("local f = function() return 1 end", "function"),
    ("local p = 2 ^ 8",                 "^"),
    ("local q = 5 // 2",                "//"),
    ("local r = 1 << 3",                "bitwise"),
    ("local r = 1 & 3",                 "bitwise"),
    ("local r = ~1",                    "bitwise"),
])
def test_expression_refusee(expr, attendu):
    errs = _errors(_in_handler(expr))
    assert any(attendu in e for e in errs), errs


def test_get_actor_chaine_directe_une_methode():
    """`actor:get("X"):méthode()` en CHAÎNE DIRECTE se transpile — sans imposer
    un `local u = actor:get(...)` intermédiaire. Auparavant le receveur (un
    appel, pas un nom) partait dans `/* invoke sur expression complexe ignoré */`
    et la méthode disparaissait en silence."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    # Un acteur appartient à sa scène : le TAG émis est qualifié par la scène
    # qui compile le script (ROADMAP « L'acteur appartient à sa scène »).
    src = _in_handler('    actor:get("Foe"):move_to(vec2(10, 20), 2)')
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Ball", actor_sym="Sc_Ball", scene_sym="Sc", anim_names=[],
        sfx_names=[], music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Ball", "Foe"]))
    assert "actor_move_to(actor_live(&g_actors[ACTOR_SC_FOE])" in code
    assert "ignoré" not in code


def test_actor_spawn_chaine_directe_une_methode():
    """Même chose pour l'instance rendue par `actor:spawn(...)` : on peut la
    piloter sans local (ROADMAP v0.17 T6)."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    src = _in_handler('    actor:spawn("Bul", vec2(0, 0)):move_to(vec2(1, 2), 3)')
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        scene_sym="Sc", all_actor_syms=["Ball"]))
    assert "actor_move_to(spawn_Sc_Bul(0, 0)" in code
    assert "ignoré" not in code


def test_invoke_sur_expression_sans_type_reste_refuse():
    """Un receveur dont le type est INCONNU (ni actor ni référence) reste
    ignoré : on n'invente pas `actor_<méthode>` sur n'importe quelle
    expression. Ici l'appel `inconnu()` ne rend pas un actor."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    src = _in_handler('    inconnu():move_to(vec2(1, 2), 3)')
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Ball"]))
    assert "invoke on complex expression ignored" in code


def test_aucun_identifiant_unsupported_dans_le_c():
    """L'ancien marqueur ne doit plus exister nulle part : il n'était pas un
    diagnostic, c'était un identifiant C inexistant qui voyageait jusqu'à gcc."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    script = parse(_in_handler('local s = "a" .. "b"'))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Ball"]))
    assert "__unsupported" not in code
    assert "not translated" in code       # le trou est écrit, pas caché


def test_zero_est_faux_pas_comme_le_vrai_lua():
    """Décision volontaire (2026-09-27, cf. `lua_subset.ACCEPTED["Nil"]`) : en
    vrai Lua, seuls `nil`/`false` sont faux et `0` est VRAI. Ici, `if`/`not`
    se traduisent tels quels vers le C (`if`/`!`), où `0` est FAUX — pour que
    `if not hp then` marche comme attendu d'un `hp` qui peut valoir 0. Ce test
    fige ce choix : il doit échouer si quelqu'un « corrige » le codegen pour
    restaurer la vérité du vrai Lua en pensant réparer un bug."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    src = _in_handler(
        "    local hp = 0\n"
        "    if not hp then hp = 1 end\n"
        "    if hp then hp = hp - 1 end\n"
    )
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Ball"]))
    assert "if ((!hp))" in code or "if (!hp)" in code
    assert "if (hp)" in code


def test_data_objets_longueur_accepte_par_le_checker():
    """`#data.Objets` — le nombre de lignes d'une table de données — était listé
    comme « Ouvert, absent » dans ROADMAP.md ; en réalité déjà validé
    (`checker._check_length`, commentaire « #data.Objets — validée par ailleurs »).
    Ce test fige que le checker ne le refuse PAS."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext

    src = _in_handler("    local n = #data.Objets")
    errs = check(parse(src), BuildContext(
        actor_name="Ball", data_tables={"Objets": (["prix"], 4)}))
    assert [e.message for e in errs if e.level == "error"] == []


def test_data_objets_longueur_est_une_constante_de_build():
    """Le nombre de lignes de la table est connu au build, comme `#t` sur un
    tableau local — aucun appel runtime, un littéral C."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    src = _in_handler("    local n = #data.Objets")
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Ball"], data_tables={"Objets": (["prix"], 4)}))
    assert "int n = 4;" in code


def test_text_draw_litteral_interpole_une_locale():
    """`$hp` dans un littéral reste lisible dans Lua et devient une valeur
    runtime, sans passer artificiellement par une globale."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    src = _in_handler('    local hp = 7\n    text:draw(2, 2, "PV : $hp")')
    assert not _errors(src, global_names=[], const_names=[], text_keys=[])
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=[], const_names=[], text_keys=[],
        all_actor_syms=["Ball"]))
    assert "text_arg_set(0, hp)" in code
    assert "text_draw(2, 2, TEXT__LIT_" in code


def test_text_draw_litteral_refuse_une_valeur_inconnue():
    errs = _errors(_in_handler('    text:draw(2, 2, "PV : $hp")'),
                   global_names=[], const_names=[], text_keys=[])
    assert any("neither a locale" in err for err in errs), errs


def test_text_draw_litteral_limite_les_locales_a_quatre():
    src = _in_handler("\n".join(f"    local v{i} = {i}" for i in range(5))
                      + '\n    text:draw(2, 2, "$v0 $v1 $v2 $v3 $v4")')
    errs = _errors(src, global_names=[], const_names=[], text_keys=[])
    assert any("at most 4 interpolated" in err for err in errs), errs


def test_text_draw_in_litteral_interpole_une_locale():
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    src = _in_handler('    local hp = 7\n    interface:get("hud"):draw("PV : $hp!3")')
    kinds = {"hud": "text_region"}
    assert not _errors(src, global_names=[], const_names=[], text_keys=[],
                       element_names=["hud"], ref_kinds=kinds)
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=[], const_names=[], text_keys=[],
        region_names=["hud"], element_names=["hud"], ref_kinds=kinds,
        all_actor_syms=["Ball"]))
    assert "text_arg_set(0, hp)" in code
    assert "text_draw_in(REGION_HUD, TEXT__LIT_" in code


def test_marqueur_de_valeur_accepte_une_limite_de_neuf_caracteres():
    from core.text_markup import display_text, parse
    marker = parse("Score : $score!3").of_kind("value")[0]
    assert marker.value == "score" and marker.limit == 3
    assert display_text("Score : $score!3", {"score": 12345}) == "Score : 123"
    assert parse("$score!9").of_kind("value")[0].limit == 9


# ── 3. La bibliothèque standard de Lua ─────────────────────────────
# Elle n'existe pas, et le nom est pourtant JUSTE — d'où un message par nom
# plutôt qu'un « fonction inconnue » qui ferait chercher une faute de frappe.

@pytest.mark.parametrize("appel, attendu", [
    ("print(1)",              "console"),
    ("table.insert(t, 1)",    "fixed size"),
    ("string.format(\"%d\")", "string it can manipulate"),
    ("os.time()",             "system clock"),
    ("io.open(\"a\")",        "file system"),
    ("coroutine.create(f)",   "coroutine"),
    ("pairs(t)",              "index"),
    ("tostring(1)",           "value marker"),
    ("pcall(f)",              "exceptions"),
    ("setmetatable(t, t)",    "metatable"),
    ("collectgarbage()",      "allocated"),
])
def test_bibliotheque_standard_refusee(appel, attendu):
    errs = _errors(_in_handler(f"    {appel}"))
    assert any(attendu in e for e in errs), errs


@pytest.mark.parametrize("appel, attendu", [
    ("math.floor(1)",   "entirely integer"),
    ("math.random(1, 2)", "math.rand"),
    ("math.pow(2, 3)",  "multiplying"),
    ("math.fmod(5, 2)", "%"),
    # Sans entrée dédiée : le message LISTE ce que le module offre vraiment.
    ("math.tan(1)",     "abs, atan2, clamp"),
])
def test_math_est_un_faux_ami(appel, attendu):
    errs = _errors(_in_handler(f"    local x = {appel}"))
    assert any(attendu in e for e in errs), errs


# ── 4. Les appels inconnus, tolérés jusqu'ici ──────────────────────

def test_fonction_inconnue_refusee():
    errs = _errors(_in_handler("    aide(3)"))
    assert any("unknown function" in e.lower() for e in errs), errs


def test_module_inconnu_refuse():
    errs = _errors(_in_handler("    machin.truc()"))
    assert any("machin" in e for e in errs), errs


def test_propriete_appelee_comme_une_fonction():
    """`self.position()` : la v0.7.4 a fait des états des propriétés, et le
    point suivi de parenthèses est l'erreur que cette migration provoque."""
    errs = _errors(_in_handler("    local p = self.position()"))
    assert any("PROPERTY" in e for e in errs), errs


def test_methode_appelee_avec_un_point():
    errs = _errors(_in_handler('    self.play_anim("idle")'))
    assert any("COLON" in e for e in errs), errs


def test_helper_prive_accepte_et_recoit_self_implicite():
    """Un helper de script est un symbole C private, appelé avec self ajouté."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    src = ("function tirer(degats)\n"
           "    self:play_anim(\"idle\")\n"
           "    return degats + 1\n"
           "end\n\n"
           "function on_update()\n"
           "    local total = tirer(3)\n"
           "end\n")
    assert _errors(src, anim_names=["idle"]) == []
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=["idle"], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Ball"]))
    assert "static int Ball_tirer(Actor* self, int degats);" in code
    assert "return (degats + 1);" in code
    assert "int total = Ball_tirer(self, 3);" in code


def test_helper_prive_verifie_arite_et_recursion():
    arity = _errors("function aide(n) end\nfunction on_update() aide() end\n")
    assert any("1 argument" in e for e in arity), arity
    recursive = _errors("function aide() aide() end\nfunction on_update() aide() end\n")
    assert any("Recursion is not allowed" in e for e in recursive), recursive


# ── 5. Ce qui doit continuer de passer ─────────────────────────────
# Le refus des appels inconnus ne doit pas emporter les deux espaces de noms
# légitimes hors catalogue : l'alias d'un behavior, et la table de module d'un
# behavior lui-même.

def test_alias_de_behavior_accepte():
    src = ('local IA = require("behaviors/ia")\n'
           'function on_update()\n    IA.update(self, 3)\nend\n')
    assert _errors(src) == []


def test_table_de_module_de_behavior_acceptee():
    """Le template de behavior qu'écrit l'éditeur lui-même (`local M = {}` …
    `return M`) récoltait « un tableau vide n'a pas de taille » : la forme de
    module était lue comme un tableau raté."""
    src = ("local M = {}\n\nfunction M.update(actor)\n    M.aide(actor)\nend\n\n"
           "function M.aide(actor)\nend\n\nreturn M\n")
    assert _errors(src, check_event_names=False) == []


def test_fonction_absente_du_module_refusee():
    src = ("local M = {}\n\nfunction M.update(actor)\n    M.aid(actor)\nend\n\n"
           "function M.aide(actor)\nend\n\nreturn M\n")
    errs = _errors(src, check_event_names=False)
    assert any("aide" in e for e in errs), errs


def test_les_scripts_de_la_demo_restent_valides():
    """Le filet le plus large : un projet réel, complet, qui doit rester vert.

    Ce filet juge le LANGAGE, pas l'authoring : le contexte de build réel est
    construit par owner dans `lua_compiler.transpile_all`, et le refaire ici en
    fouillant les JSON de la démo en ferait une seconde source qui dériverait au
    premier champ ajouté. Les garde-fous qui dépendent d'une case cochée dans
    l'éditeur sont donc ouverts — `Ball` a bien « Affine transform » coché
    (`project/prefab/Ball.json`), et c'est le build qui le vérifie. Le refus,
    lui, est scellé juste en dessous."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext

    racine = REPO_DIR / "Project Demo" / "Pong" / "assets" / "scripts"
    if not racine.exists():
        pytest.skip("projet de démo absent")
    for chemin in racine.rglob("*.lua"):
        errs = [e.message for e in check(
            parse(chemin.read_text(encoding="utf-8")),
            BuildContext(affine_transform=True),
            check_event_names=(chemin.parent.name != "behaviors"))
            if e.level == "error"]
        assert errs == [], f"{chemin.name} : {errs}"


def test_transform_affine_avertit_sans_la_case_cochee():
    """Le pendant du filet ci-dessus : sans « Affine transform » sur le sprite,
    aucun slot de matrice n'est réservé au build, et rien n'affiche
    self.rotation/scale. Un AVERTISSEMENT et non un refus — la valeur, elle,
    s'écrit et se relit (les accesseurs runtime ne consultent plus le slot).
    Le message nomme la case à cocher, pas le matériel."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext

    for prop in ("rotation", "scale", "sprite_rotation", "sprite_scale",
                 "sprite_offset"):
        src = _in_handler(f"local v = self.{prop}")
        found = check(parse(src), BuildContext(actor_name="Ball"))
        assert any("Affine transform" in e.message and e.level == "warning"
                   for e in found), (prop, [str(e) for e in found])
        assert _errors(src) == [], prop
        assert check(parse(src),
                     BuildContext(actor_name="Ball", affine_transform=True)) == []


# ── 6. Les deux listes qui ne doivent pas diverger ─────────────────

def test_tout_noeud_de_luaparser_est_classe():
    """Le contrôle de couverture, joué hors du validateur de projet : une mise à
    jour de luaparser qui ajoute un nœud doit se voir ici aussi, et pas
    seulement au moment d'ouvrir un projet."""
    import inspect
    from luaparser import astnodes
    from scripting import lua_subset

    abstraites = {"Expression", "Statement", "Op", "BinaryOp", "AriOp",
                  "BitOp", "RelOp", "LoOp", "UnaryOp", "Lhs"}
    univers = {name for name, cls in vars(astnodes).items()
               if inspect.isclass(cls) and issubclass(cls, astnodes.Expression)
               and name not in abstraites}
    assert univers - lua_subset.covered_nodes() == set()
    assert lua_subset.covered_nodes() - univers == set()


def test_chaque_refus_est_documente():
    """La documentation ne peut pas prendre de retard sur la table : un refus
    que la référence de scripting ne montre pas est un utilisateur bloqué par un message
    dont le document ne parle pas."""
    from scripting import lua_subset

    doc = (REPO_DIR / "docs" / "scripting-reference.md").read_text(encoding="utf-8")
    refus = [*lua_subset.REFUSED.values(), lua_subset.NESTED_FUNCTION,
             *lua_subset.STDLIB_MODULES.values(), *lua_subset.STDLIB.values()]
    absents = sorted({r.lua for r in refus if r.lua not in doc})
    assert absents == [], (
        f"Refus non documentés dans la référence de scripting : {absents}")
