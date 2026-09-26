"""L'autocomplétion ne peut proposer que ce qui existe — v0.27.

Le défaut qu'on rend impossible est précis, et daté : la sidebar a proposé
pendant des mois `scene_goto("X")` et `instantiate("X", x, y)`, deux noms qui
n'ont jamais existé dans le catalogue, donc du code que le checker refuse à
l'insertion même. La complétion DÉRIVE du catalogue justement pour que ça ne
puisse pas arriver — ces tests le garantissent, plutôt que de le supposer.
"""
from __future__ import annotations

import pytest

from scripting import completion as C
from scripting.api import (
    RUNTIME_API, RUNTIME_PROPS, HARDWARE_ENUMS,
    KNOWN_EVENTS, KNOWN_EVENTS_BY_KIND,
)


# ── 1. Un membre proposé est TOUJOURS une clé réelle du catalogue ──

@pytest.mark.parametrize("qual, sep, table_key", [
    ("self", ":", "actor:{}"),         # méthodes d'acteur (clés `actor:`, écrites `self:`)
    ("self", ".", "actor.{}"),         # propriétés d'acteur
    ("sfx",  ":", "sfx.{}"),            # un module : ses actions derrière « : »
    ("scene", ":", "scene.{}"),
    ("scene", ".", "scene.{}"),         # ... son état derrière « . »
    ("camera", ":", "camera.{}"),
    ("camera", ".", "camera.{}"),
    ("input", ":", "input.{}"),
    ("save", ":", "save.{}"),
    ("math", ".", "math.{}"),           # la seule bibliothèque : le point
    ("text", ":", "text.{}"),
])
def test_member_candidates_existent_dans_le_catalogue(qual, sep, table_key):
    cands = C.candidates_at(f"{qual}{sep}", context="actor")
    assert cands, f"{qual}{sep} devrait proposer quelque chose"
    for c in cands:
        key = table_key.format(c.insert)
        assert key in RUNTIME_API or key in RUNTIME_PROPS, \
            f"{key} proposé mais absent du catalogue"


# ── 2. `sfx:` ≠ `pas:` — le module n'expose pas les méthodes du handle ──
# La régression exacte trouvée en développant : `sfx:stop` (méthode du TYPE de
# référence rendu par `sfx:play`) fuyait dans les membres du module, qui n'en a
# qu'un — `play`.

def test_module_nexpose_pas_les_methodes_de_reference():
    inserts = {c.insert for c in C.candidates_at("sfx:")}
    assert inserts == {"play"}
    # Le point d'un module est son ÉTAT : `sfx` n'en a aucun, et `math` — la bibliothèque —
    # n'a que le point.
    assert C.candidates_at("sfx.") == []
    assert C.candidates_at("math:") == []
    assert {c.insert for c in C.candidates_at("camera.")} >= {"bound"}
    assert "follow" not in {c.insert for c in C.candidates_at("camera.")}



# ── 3. `self:` (méthode) et `self.` (champ) sont disjoints ──

def test_self_methode_et_champ_sont_disjoints():
    methods = {c.insert for c in C.candidates_at("self:")}
    props   = {c.insert for c in C.candidates_at("self.")}
    assert methods and props
    assert methods.isdisjoint(props)
    assert all(c.kind == C.KIND_FUNCTION for c in C.candidates_at("self:"))
    assert all(c.kind == C.KIND_PROPERTY for c in C.candidates_at("self."))


# ── 4. Les valeurs d'énumération, aux deux endroits où elles s'écrivent ──

def test_enum_dans_un_argument_dappel():
    # math.ease(a, b, num, den, kind) — le dernier argument est un EASE_KIND.
    got = {c.insert for c in C.candidates_at('math.ease(1, 2, 3, 4, "')}
    assert got == set(HARDWARE_ENUMS["ease"])


def test_enum_dans_une_affectation_de_propriete():
    got = {c.insert for c in C.candidates_at('self.obj_mode = "')}
    assert got == set(HARDWARE_ENUMS["obj_mode"])
    # La comparaison, pas seulement l'affectation.
    got_cmp = {c.insert for c in C.candidates_at('if self.obj_mode == "')}
    assert got_cmp == set(HARDWARE_ENUMS["obj_mode"])


def test_argument_de_domaine_projet_attend_la_phase_3():
    # sfx:play("…") cite un asset du PROJET (DOMAIN_SFX), pas un enum matériel :
    # rien tant que la phase 3 n'a pas branché l'univers du projet.
    assert C.candidates_at('sfx:play("') == []


# ── 5. Ce qui NE doit pas se compléter ──

def test_pas_de_completion_dans_un_commentaire():
    assert C.candidates_at("-- self:") == []
    assert C.candidates_at("x = 1  -- sfx.") == []


def test_les_mots_cles_refuses_ne_sont_pas_proposes():
    # `repeat`, `until`, `goto` sont REFUSÉS par lua_subset en le disant : les
    # proposer enseignerait l'erreur.
    for banned in ("repeat", "until", "goto"):
        assert banned not in C.KEYWORDS


# ── 6. La dérivation : un module du catalogue apparaît sans qu'on y touche ──

def test_modules_derivent_du_catalogue():
    expected = {k.split(".", 1)[0] for k in list(RUNTIME_API) + list(RUNTIME_PROPS)
                if "." in k and ":" not in k and not k.startswith("self.")}
    assert set(C.MODULES) == expected


def test_handlers_filtres_par_contexte():
    # Un script de caméra n'a pas tous les handlers d'un actor.
    actor_events  = {c.insert for c in C.candidates_at("", context="actor")
                     if c.kind == C.KIND_EVENT}
    camera_events = {c.insert for c in C.candidates_at("", context="camera")
                     if c.kind == C.KIND_EVENT}
    assert actor_events == set(KNOWN_EVENTS_BY_KIND.get("actor", KNOWN_EVENTS))
    assert camera_events == set(KNOWN_EVENTS_BY_KIND.get("camera", KNOWN_EVENTS))


# ── 7. Aucune entrée ne fait planter le modèle ──

@pytest.mark.parametrize("junk", [
    "", "   ", '"', "a.", "a:", ".", "((", "))", 'foo("x", "',
    "self.position.", "3 + ", ") ) (", 'nested(inner("',
])
def test_aucune_entree_ne_leve(junk):
    cands = C.candidates_at(junk, context="scene")
    assert all(isinstance(c.insert, str) and isinstance(c.tooltip, str) for c in cands)


# ── 8. Phase 2 — les noms déclarés par le script (l'AST) ──

_SRC = """function on_start()
    local health = 100
    local speed = 2
end

function on_collide(other, my_box)
    for i = 1, 10 do
        local tmp = i
    end
end"""


def _locals(prefix, source, line):
    return {c.insert for c in C.candidates_at(prefix, context="actor",
                                              source=source, line=line)
            if c.kind == C.KIND_LOCAL}


def test_locals_conformes_au_checker():
    # La ligne 4 est vide : la neutraliser ne change rien, le parse tient, et
    # l'ensemble proposé est EXACTEMENT celui que le checker refuserait sinon —
    # même source, `parser.local_names`.
    from scripting.parser import parse, local_names
    assert _locals("    x", _SRC, line=4) == local_names(parse(_SRC))
    assert {"health", "speed", "other", "my_box", "i", "tmp"} == local_names(parse(_SRC))


def test_locals_absents_sans_source():
    # Phase 1 préservée : sans le script, aucun local — que le catalogue.
    assert not any(c.kind == C.KIND_LOCAL for c in C.candidates_at("    h", context="actor"))


def test_locals_seulement_sur_un_mot_nu():
    # Ni après un `.`/`:` (membre), ni dans une chaîne.
    assert not any(c.kind == C.KIND_LOCAL
                   for c in C.candidates_at("    self:", context="actor", source=_SRC, line=1))
    assert not any(c.kind == C.KIND_LOCAL
                   for c in C.candidates_at('    sfx:play("', context="actor", source=_SRC, line=1))


def test_repli_regex_sur_tampon_desequilibre():
    # Une fonction pas encore refermée : `parse` échoue, le balayage textuel
    # prend le relais et n'oublie pas les locals déjà écrits.
    broken = "function on_update()\n    local score = 0\n    local lives = 3\n    sc"
    got = C._script_locals(broken, cursor_line=3)
    assert {"score", "lives"} <= got


def test_repli_capture_tous_les_noms_dun_multi_local():
    # `local a, b, c` déclare les trois (correctif multi-local) : le repli les
    # propose tous, jamais les valeurs de droite.
    src = "function on_update()\n    local a, b, c = 1, 2, 3\n    a"   # non refermée → repli
    assert C._script_locals(src, cursor_line=2) == {"a", "b", "c"}


# ── 9. Phase 3 — les noms du projet dans un argument chaîne ──

from types import SimpleNamespace as _NS

_PROJECT = _NS(
    scenes=[_NS(name="Arena"), _NS(name="Title")],
    sfx=[_NS(name="Hit"), _NS(name="Jump")],
    music=[], prefabs=[_NS(name="Bullet")], fonts=[_NS(name="Main")],
    palettes=[], globals=[_NS(name="score")],
    active_scene=_NS(actors=[_NS(name="Hero"), _NS(name="Boss")]),
)


def _nbd():
    from scripting.project_names import names_by_domain
    return names_by_domain(_PROJECT)


def _refs(prefix):
    return {c.insert for c in C.candidates_at(prefix, context="actor", project_names=_nbd())
            if c.kind == C.KIND_REF}


def test_argument_projet_propose_les_noms():
    assert _refs('sfx:play("') == {"Hit", "Jump"}
    assert _refs('scene:switch("') == {"Arena", "Title"}
    assert _refs('actor:spawn("') == {"Bullet"}       # DOMAIN_PREFAB
    assert _refs('actor:get("') == {"Hero", "Boss"}   # DOMAIN_ACTOR — scène active


def test_argument_enum_reste_prioritaire_sur_le_projet():
    # Un domaine d'énumération matérielle garde ses valeurs fixes, même avec un
    # projet fourni : les deux sources ne se marchent pas dessus.
    got = {c.insert for c in C.candidates_at('math.ease(1,2,3,4,"', context="actor",
                                             project_names=_nbd())}
    assert got == {"in", "out", "in_out"}


def test_sans_projet_aucun_nom_projet():
    # Phase 1/2 préservées : sans project_names, un argument de domaine projet
    # ne propose rien (il reste à la charge de l'auteur).
    assert C.candidates_at('sfx:play("', context="actor") == []


def test_names_by_domain_omet_les_domaines_vides():
    nbd = _nbd()
    from scripting.api import DOMAIN_MUSIC, DOMAIN_SCENE
    assert DOMAIN_MUSIC not in nbd            # music=[] → absent
    assert nbd[DOMAIN_SCENE] == ["Arena", "Title"]


def test_global_et_const_pointes_proposent_le_projet():
    # `global.nom` / `const.nom` sont des accès pointés aux scalaires déclarés —
    # pas des modules du catalogue.
    from scripting.project_names import names_by_domain
    proj = _NS(scenes=[], sfx=[], music=[], prefabs=[], fonts=[], palettes=[],
               globals=[_NS(name="score"), _NS(name="lives")],
               constants=[_NS(name="MAX_HP")], active_scene=None)
    nbd = names_by_domain(proj)

    def members(prefix):
        return {c.insert for c in C.candidates_at(prefix, context="actor", project_names=nbd)
                if c.kind == C.KIND_REF}

    assert members("    x = global.") == {"score", "lives"}
    assert members("    debug:log(global.") == {"score", "lives"}   # même dans un argument
    assert members("    y = const.") == {"MAX_HP"}


def test_global_pointe_vide_sans_projet():
    # Sans project_names, `global.` ne propose rien (pas de plantage, pas de
    # fausse suggestion).
    assert C.candidates_at("    global.", context="actor") == []
