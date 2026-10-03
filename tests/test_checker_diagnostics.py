"""Chaque diagnostic du checker a son test (chantier « La fiabilité du journal de build », tranche 5).

La mesure de couverture des diagnostics a montré qu'une soixantaine de messages du checker n'étaient
JAMAIS déclenchés par un test : ils pouvaient citer le mauvais objet, être en français, ou ne plus se
produire sans que personne ne le voie. Chaque cas ci-dessous écrit le plus petit script qui en provoque
un, avec le contexte de projet qu'il suppose, et dit ce que le message doit contenir.

Un cas = (script, contexte du projet, niveau attendu, morceau du message).
"""
from __future__ import annotations

import pytest

from scripting import checker
from scripting.checker import BuildContext, check
from scripting.parser import parse


def _messages(source: str, **ctx) -> list[tuple[str, str]]:
    ctx.setdefault("actor_name", "A")
    ctx.setdefault("owner_kind", "actor")
    return [(e.level, e.message) for e in check(parse(source), BuildContext(**ctx))]


def _handler(body: str, top: str = "") -> str:
    indented = "\n".join("    " + line for line in body.split("\n"))
    return f"{top}\nfunction on_update()\n{indented}\nend\n"


TABLES = {"T": (["a", "b"], 3), "E": (["a"], 0)}
EXPORTS = {"Bullet": {"team": {"type": "actor_ref", "values": []},
                      "speed": {"type": "int", "values": []}}}

# (id, script, contexte, niveau, fragment du message)
CASES = [
    # ── fonctions privées et exports ──
    ("helper-nom-d-api", "function vec2(a)\nend\nfunction on_update()\nend", {}, "error",
     "already belongs to the API"),
    ("helper-avec-self", "function aide(self)\nend\nfunction on_update()\naide()\nend", {}, "error",
     "`self` is implicit"),
    ("helper-declare-deux-fois", "function aide()\nend\nfunction aide()\nend\nfunction on_update()\nend",
     {}, "error", "declared 2 times"),
    ("export-type-non-cable", 'exports = { x = { type = "weird", default = 1 } }\nfunction on_update()\nend',
     {}, "warning", "not applied at build yet"),
    ("fonction-qualifiee-inconnue", "local M = {}\nfunction M.f(a)\nend\nfunction on_update()\nend", {},
     "error", "Unknown function"),
    ("helper-rend-deux-valeurs", "function f()\n return 1, 2\nend\nfunction on_update()\n f()\nend", {},
     "error", "at most one integer value"),
    ("helper-rend-un-vecteur", "function f()\n return vec2(1, 2)\nend\nfunction on_update()\n f()\nend", {},
     "error", "only returns an integer or a boolean"),
    # ── tableaux ──
    ("tableau-taille-calculee", "local t = array(foo)\nfunction on_update()\nend", {}, "error",
     "one or two sizes expected"),
    ("tableau-vide", "local t = {}\nfunction on_update()\nend", {}, "error", "no element"),
    ("tableau-de-chaines", 'local t = {"a", "b"}\nfunction on_update()\nend', {}, "error",
     "only holds integers"),
    ("indice-sur-un-nom-inconnu", "inconnu[1] = 2", {}, "warning", "is not an array declared"),
    ("trop-d-indices", "t[1][2] = 1", {"top": "local t = array(3)"}, "error", "dimension(s)"),
    ("indice-hors-bornes", "t[9] = 1", {"top": "local t = array(3)"}, "error", "out of bounds"),
    ("taille-d-un-non-tableau", "local n = #foo", {}, "error", "'#' only applies to an array"),
    # ── tables de données et globales ──
    ("table-inconnue", "local x = data.Missing[1].a", {"data_tables": TABLES}, "error", "data table not found"),
    ("table-deux-indices", "local x = data.T[1][2].a", {"data_tables": TABLES}, "error", "indexed by its ROW"),
    ("table-hors-bornes", "local x = data.T[9].a", {"data_tables": TABLES}, "error", "out of bounds"),
    ("table-vide-hors-bornes", "local x = data.E[1].a", {"data_tables": TABLES}, "error", "empty — no rows"),
    ("colonne-inconnue", "local x = data.T[1].zzz", {"data_tables": TABLES}, "error", "no column"),
    ("globale-indexee-inconnue", "global.nope[1] = 1", {"global_counts": {"score": 1, "arr": 3}}, "error",
     "global variable not found"),
    # ── opérations sur les vecteurs ──
    ("rect-n-est-pas-un-nombre", "local r = rect(0, 0, 1, 1)\nlocal q = r + 1", {}, "error", "is not a number"),
    ("division-d-un-vecteur", "local v = vec2(1, 2)\nlocal w = v / 2", {}, "error", "is not defined on a vec2/vec3"),
    ("produit-de-deux-vecteurs", "local v = vec2(1, 2)\nlocal w = v * v", {}, "error", "does not exist"),
    ("vec2-plus-vec3", "local v = vec2(1, 2)\nlocal w = v + vec3(1, 2, 3)", {}, "error", "same type"),
    ("vecteur-plus-scalaire", "local v = vec2(1, 2)\nlocal w = v + 1", {}, "error", "and a scalar does not exist"),
    ("champ-d-un-vecteur", "local v = vec2(1, 2)\nlocal z = v.z", {}, "error", "has no field"),
    ("constructeur-mauvais-arite", "local v = vec2(1)", {}, "error", "vec2"),
    # ── propriétés et appels ──
    ("enfant-inconnu", "local c = self.nope", {"child_names": []}, "error", "neither an actor property nor a child"),
    ("pas-de-for-calcule", "for i = 1, 10, n do\nend", {"top": "local n = 2"}, "error", "plain number"),
    ("play-sfx-sans-composant", "self:play_sfx()", {}, "warning", "no SoundFX component"),
    # ── noms du projet cités dans un appel ──
    ("animation-inconnue", 'self:play_anim("nope")', {"anim_names": ["idle"]}, "warning", "not found in the linked sprite"),
    ("etat-de-boite-inconnu", 'sound_box:set_state("nope")', {"sound_box_state_names": ["sand"]}, "error",
     "no state with this name"),
    ("declencheur-musical-inconnu", 'music_box:trigger("nope")', {"music_box_trigger_names": []}, "warning",
     "no music transition listens"),
    ("musique-inconnue", 'music:play("nope")', {"music_names": ["theme"]}, "warning", "not found in the project"),
    ("texte-litteral-ressemblant-a-une-cle", 'text:draw(1, 1, "no_such_key")', {"text_keys": []}, "warning",
     "no entry with this name in the table"),
    ("texte-inconnu", 'text:length("nope")', {"text_keys": ["hello"]}, "error", "not found in the project table"),
    ("police-inconnue", 'text:set_font("nope")', {"font_names": ["Pixel"]}, "error", "not found or without glyphs"),
    ("palette-inconnue", 'palette:set_bg(0, "nope")', {"palette_names": ["Night"]}, "error", "not found in the colour catalogue"),
    ("scene-inconnue", 'scene:switch("nope")', {"scene_names": ["Level1"]}, "error", "scene 'nope' not found"),
    ("prefab-inconnu", 'actor:spawn("Nope", vec2(0, 0))', {"prefab_names": ["Bullet"]}, "error", "prefab 'Nope' not found"),
    ("acteur-inconnu", 'actor:get("Nope")', {"actor_names": ["A"]}, "warning", "no actor named 'Nope'"),
    ("argument-d-enumeration-en-nombre", "blend:set_obj(2, true)", {}, "error", "written by its name"),
    # ── sauvegarde ──
    ("sauvegarde-sans-variable-persistante", "save:write(0)", {"has_persistent": False}, "warning",
     "no global variable is marked persistent"),
    ("emplacement-inexistant", "save:write(5)", {"has_persistent": True, "save_slots": 1}, "error", "save slot"),
    ("lecture-d-une-variable-non-persistante", 'save:read(0, "score")',
     {"global_names": ["score"], "global_persist": {"score": False}}, "warning", 'not ticked "persist"'),
    ("variable-globale-inconnue", 'save:read(0, "nope")', {"global_names": ["score"]}, "warning",
     "is not declared in the project"),
    # ── actor:spawn avec une table de valeurs ──
    ("spawn-table-sans-cles", 'actor:spawn("Bullet", vec2(0, 0), { 1, 2 })', {"spawn_exports": EXPORTS}, "error",
     "named entries"),
    ("spawn-melange-nomme-et-positionnel", 'actor:spawn("Bullet", vec2(0, 0), { speed = 8, 3 })',
     {"spawn_exports": EXPORTS}, "error", "named entries"),
    ("spawn-nom-attendu", 'actor:spawn("Bullet", vec2(0, 0), { team = 5 })', {"spawn_exports": EXPORTS}, "error",
     "must be a quoted name"),
    ("spawn-3e-argument-pas-une-table", 'actor:spawn("Bullet", vec2(0, 0), 5)', {"spawn_exports": EXPORTS}, "error",
     "not an array"),
    ("methode-inconnue-sur-un-spawn", 'actor:spawn("Bullet", vec2(0, 0)):bogus()', {}, "error", "Unknown method on a actor reference"),
    ("attente-mauvais-nombre-d-arguments", "function on_sequence_a()\n wait(1, 2)\nend", {}, "error",
     "expects exactly one argument"),
    ("animation-d-un-autre-acteur",
     'function on_collision_enter(other, my_box, other_box)\n if other.anim == "Walk" then\n end\nend', {},
     "error", "can only be made on self"),
    ("spawn-litteral-attendu", 'actor:spawn("Bullet", vec2(0, 0), { speed = self.x })', {"spawn_exports": EXPORTS},
     "error", "must be a literal"),
]


@pytest.mark.parametrize("name, body, ctx, level, fragment", CASES, ids=[c[0] for c in CASES])
def test_le_diagnostic_du_checker(name, body, ctx, level, fragment):
    ctx = dict(ctx)
    top = ctx.pop("top", "")
    whole_script = body.startswith("function") or "function on_update" in body \
        or body.startswith(("local", "exports")) and "\nfunction" in body
    source = body if whole_script else _handler(body, top)
    found = _messages(source, **ctx)
    assert any(lvl == level and fragment in msg for lvl, msg in found), found


# ── Les messages d'API retirée : le catalogue est vide, le mécanisme reste ──


def test_une_fonction_retiree_dit_ce_qu_il_faut_ecrire(monkeypatch):
    monkeypatch.setattr(checker, "REMOVED_API", {"ancienne": "ancienne() was removed: write nouvelle()."})
    found = _messages(_handler("ancienne(1)"))
    assert ("error", "ancienne() was removed: write nouvelle().") in found


def test_une_methode_d_acteur_retiree_est_dite_sur_tout_recepteur(monkeypatch):
    monkeypatch.setattr(checker, "REMOVED_API", {"actor:old": "self.old was removed."})
    found = _messages("function on_collision_enter(other, my_box, other_box)\n other:old()\nend")
    assert any("other:old(): self.old was removed." in msg for _lvl, msg in found), found
