"""`global.nom` et `const.nom` — l'accès pointé (chantier global/const).

`global.get("score")` / `global.set("score", v)` / `const.get("max")` ont
quitté `RUNTIME_API` : ce ne sont pas des appels, ce sont des accès d'état,
comme `self.position` (RUNTIME_PROPS) ou `data.Objets`. Le membre étant un nom
de PROJET et non un membre de langage fixe, ni l'un ni l'autre catalogue ne
convenait — le checker et le codegen les résolvent directement contre
`project.globals` / `.constants`.

Ce que ces tests protègent, et qui ne se voyait sinon qu'au `make` (ou pas du
tout) :

- l'accès compile en accès DIRECT (`g_score`, `CONST_MAX`), jamais en appel ;
- un nom inconnu est une ERREUR de checker — y compris dans un projet qui n'a
  déclaré AUCUNE constante, le cas où le C émis dirait `const.max` et où gcc
  échouerait sur le mot-clé `const` ;
- un tableau ne se lit pas nu, un scalaire ne s'indexe pas ;
- une constante ne s'écrit jamais ;
- les anciennes orthographes (`global.get`/`const.get`) sont refusées comme
  « module inconnu » — retrait sec, sans guide (ROADMAP v0.16, REMOVED_API vidé) ;
- un renommage de variable réécrit les DEUX formes pointées dans les scripts.
"""
from __future__ import annotations

import pytest


# ── Le projet de référence de ces tests ───────────────────────────
# Un scalaire, un tableau, une constante — de quoi poser les trois questions
# du chantier sans dépendre d'un projet sur disque.
_COUNTS = {"score": 1, "coffres": 400}
_TYPES = {"score": "int", "coffres": "bool"}
_CONSTS = ["max_vies"]


def _messages(src: str, level: str, **over) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    kw = dict(global_counts=_COUNTS, global_types=_TYPES, const_names=list(_CONSTS))
    kw.update(over)
    errs = check(parse(src), BuildContext(actor_name="Ball", **kw))
    return [e.message for e in errs if e.level == level]


def _check(src: str, **over) -> list[str]:
    return _messages(src, "error", **over)


def _warnings(src: str, **over) -> list[str]:
    return _messages(src, "warning", **over)


def _gen(src: str) -> str:
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    code, _w, _s = generate(parse(src), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(_COUNTS), const_names=set(_CONSTS),
        all_actor_syms=["Ball"]))
    return code


def _body(*lines: str) -> str:
    return "function on_update()\n" + "".join(f"    {l}\n" for l in lines) + "end\n"


# ── 1. L'accès compile en accès direct ────────────────────────────


def test_lecture_dun_scalaire_compile_en_variable_c():
    code = _gen(_body("local v = global.score"))
    assert "g_score" in code
    assert "_global_get" not in code and "global.get" not in code


def test_ecriture_dun_scalaire_compile_en_affectation_c():
    assert "g_score = 12" in _gen(_body("global.score = 12"))


def test_lecture_dune_constante_compile_en_symbole_c():
    code = _gen(_body("local v = const.max_vies"))
    assert "CONST_MAX_VIES" in code
    assert "const.max_vies" not in code   # jamais le nom Lua tel quel dans le C


def test_case_de_tableau_compile_indexee():
    """La forme indexée (ROADMAP v0.20) n'a jamais eu d'accesseur : elle ne
    bouge pas, et sa base est le MÊME accès pointé que le scalaire."""
    assert "g_coffres[" in _gen(_body("global.coffres[3] = 1"))


# ── 2. Un nom inconnu est une erreur, pas un `make` qui échoue ────


def test_global_inconnu_refuse_et_nomme_les_declarees():
    errs = _check(_body("local v = global.inexistant"))
    assert len(errs) == 1
    assert "global.inexistant" in errs[0] and "introuvable" in errs[0]
    assert "score" in errs[0]


def test_constante_inconnue_refusee():
    errs = _check(_body("local v = const.inexistante"))
    assert len(errs) == 1
    assert "const.inexistante" in errs[0] and "introuvable" in errs[0]


def test_constante_citee_dans_un_projet_sans_aucune_constante():
    """Le cas que `const_names=None` laissait passer jusqu'au `make` : sans
    constante déclarée, le C émis disait `const.max_vies` et gcc échouait sur
    le mot-clé `const`. `lua_compiler` passe désormais une LISTE même vide —
    « aucune déclarée » est une réponse, pas une absence de réponse."""
    errs = _check(_body("local v = const.max_vies"), const_names=[])
    assert len(errs) == 1
    assert "const.max_vies" in errs[0]
    assert "aucune constante" in errs[0]


def test_contexte_absent_relache_la_verification():
    """`const_names=None` reste « je ne sais pas » — même contrat que le reste
    de `BuildContext`, pour un appelant qui ne renseigne rien."""
    assert _check(_body("local v = const.max_vies"), const_names=None) == []


# ── 3. Tableau et scalaire ne se confondent pas ───────────────────


def test_un_tableau_ne_se_lit_pas_nu():
    errs = _check(_body("local v = global.coffres"))
    assert len(errs) == 1
    assert "TABLEAU" in errs[0] and "global.coffres[i]" in errs[0]


def test_un_scalaire_ne_sindexe_pas():
    errs = _check(_body("global.score[1] = 0"))
    assert len(errs) == 1
    assert "SIMPLE" in errs[0]
    # Le message guide vers la nouvelle forme, jamais vers les accesseurs.
    assert "global.get" not in errs[0] and "global.set" not in errs[0]


def test_un_rang_hors_bornes_ecrit_en_clair_est_refuse():
    errs = _check(_body("global.coffres[401] = 1"))
    assert len(errs) == 1 and "401" in errs[0]


# ── 4. Une constante ne s'écrit jamais ────────────────────────────


def test_ecrire_une_constante_est_refuse():
    assert any("ne s'écrit jamais" in e for e in _check(_body("const.max_vies = 4")))


def test_ecrire_une_constante_inconnue_dit_les_deux_fautes():
    """Le nom vient de `_check_const_scalar` (via la CIBLE), l'écriture de
    `_check_const_write` : deux contrôles, deux messages, aucun n'avale
    l'autre."""
    assert len(_check(_body("const.inexistante = 4"))) == 2


# ── 5. La valeur écrite reste bornée par le type déclaré ──────────


def test_valeur_hors_plage_avertit_dans_la_grammaire_pointee():
    """L'avertissement de plage était accroché à l'appel `global.set` ; il suit
    désormais la valeur à l'ASSIGNATION, et son message parle la langue
    d'aujourd'hui."""
    warns = _warnings(_body("global.score = 70000"), global_types={"score": "u16"})
    assert len(warns) == 1
    assert "global.score = 70000" in warns[0]
    assert "global.set" not in warns[0]


# ── 6. Les anciennes orthographes sont bloquées (retrait sec) ─────


@pytest.mark.parametrize("src", [
    'local v = global.get("score")',
    'global.set("score", 1)',
    'local v = const.get("max_vies")',
])
def test_les_accesseurs_retires_sont_bloques(src):
    """Retrait sec (ROADMAP v0.16, REMOVED_API vidé) : `global.get`/`const.get`
    ne guident plus vers l'accès pointé — ils sont refusés comme un module
    inexistant. Le blocage tient au checker (module hors catalogue), pas à
    REMOVED_API."""
    errs = _check(_body(src))
    assert errs and "n'existe pas" in errs[0]


def test_les_accesseurs_ont_quitte_le_catalogue():
    """Un domaine sans site serait un orphelin (`validator._check_api_domains`)
    — d'où la disparition de `DOMAIN_CONST` avec son dernier appel littéral."""
    from scripting import api
    assert "global.get" not in api.RUNTIME_API
    assert "global.set" not in api.RUNTIME_API
    assert "const.get" not in api.RUNTIME_API
    assert not hasattr(api, "DOMAIN_CONST")


def test_save_read_garde_son_nom_litteral():
    """Le seul site qui cite encore une globale entre guillemets : le premier
    argument est l'emplacement, pas le récepteur, et c'est `GLOBAL_NOM` (l'id
    de sauvegarde) qu'il faut, pas `g_nom` (la variable en RAM)."""
    code = _gen(_body('local v = save:read(0, "score")'))
    assert "save_read_var(0, GLOBAL_SCORE)" in code


# ── 7. Un renommage réécrit les formes pointées ───────────────────


class _FakeProject:
    """Le minimum que `refactor.script_paths` sait parcourir : un `scripts_dir`."""

    def __init__(self, scripts_dir):
        self.scripts_dir = scripts_dir


def _scripts(tmp_path, src: str) -> _FakeProject:
    actors = tmp_path / "actors"
    actors.mkdir()
    (actors / "actor_Ball.lua").write_text(src, encoding="utf-8")
    return _FakeProject(actors)


def _read(tmp_path) -> str:
    return (tmp_path / "actors" / "actor_Ball.lua").read_text(encoding="utf-8")


def test_renommer_une_globale_reecrit_les_formes_nue_et_indexee(tmp_path):
    from scripting.refactor import rename_var_in_project
    src = _body("global.score = global.score + 1",
                "global.coffres[1] = 1",
                "local score = 3",                    # homonyme LOCAL : intouchable
                'local v = save:read(0, "score")')
    project = _scripts(tmp_path, src)
    changed = rename_var_in_project(project, "global", "score", "points")

    out = _read(tmp_path)
    assert sum(changed.values()) == 2               # les deux citations pointées
    assert "global.points = global.points + 1" in out
    assert "local score = 3" in out                 # le local n'a pas bougé
    assert 'save:read(0, "score")' in out           # le littéral non plus (autre chemin)
    assert "global.coffres[1] = 1" in out           # une autre globale non plus


def test_renommer_une_globale_indexee_reecrit_sa_base(tmp_path):
    from scripting.refactor import rename_var_in_project
    project = _scripts(tmp_path, _body("global.coffres[i] = 1",
                                       "local v = global.coffres[2]"))
    changed = rename_var_in_project(project, "global", "coffres", "sacs")

    out = _read(tmp_path)
    assert sum(changed.values()) == 2
    assert "global.sacs[i] = 1" in out and "global.sacs[2]" in out


def test_renommer_une_constante_reecrit_ses_citations(tmp_path):
    from scripting.refactor import rename_var_in_project
    project = _scripts(tmp_path, _body("local v = const.max_vies + const.max_vies"))
    changed = rename_var_in_project(project, "const", "max_vies", "vies_max")

    out = _read(tmp_path)
    assert sum(changed.values()) == 2
    assert "const.vies_max + const.vies_max" in out
