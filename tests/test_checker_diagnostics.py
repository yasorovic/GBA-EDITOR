"""Un échantillon des diagnostics du checker (chantier « La fiabilité du journal de build », tranche 5).

Un cas par famille de faute — fonctions privées, tableaux, tables de données, vecteurs, références
nommées, sauvegarde, spawn : le plus petit script qui la provoque, avec le contexte de projet qu'il
suppose, et ce que le message doit contenir. Ce n'est PAS un test par message : la couverture
exhaustive a été essayée puis retirée, elle vérifiait qu'un texte sort, pas qu'il est juste.

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
    ("tableau-taille-calculee", "local t = array(foo)\nfunction on_update()\nend", {}, "error",
     "one or two sizes expected"),
    ("indice-hors-bornes", "t[9] = 1", {"top": "local t = array(3)"}, "error", "out of bounds"),
    ("table-hors-bornes", "local x = data.T[9].a", {"data_tables": TABLES}, "error", "out of bounds"),
    ("modulo-d-un-vecteur", "local v = vec2(1, 2)\nlocal w = v % 2", {}, "error", "is not defined on a vec2/vec3"),
    ("vec2-plus-vec3", "local v = vec2(1, 2)\nlocal w = v + vec3(1, 2, 3)", {}, "error", "same type"),
    ("enfant-inconnu", "local c = self.nope", {"child_names": []}, "error", "neither an actor property nor a child"),
    ("pas-de-for-calcule", "for i = 1, 10, n do\nend", {"top": "local n = 2"}, "error", "plain number"),
    ("animation-inconnue", 'self:play_anim("nope")', {"anim_names": ["idle"]}, "warning", "not found in the linked sprite"),
    ("scene-inconnue", 'scene:switch("nope")', {"scene_names": ["Level1"]}, "error", "scene 'nope' not found"),
    ("prefab-inconnu", 'actor:spawn("Nope", vec2(0, 0))', {"prefab_names": ["Bullet"]}, "error", "prefab 'Nope' not found"),
    ("emplacement-inexistant", "save:write(5)", {"has_persistent": True, "save_slots": 1}, "error", "save slot"),
    ("spawn-nom-attendu", 'actor:spawn("Bullet", vec2(0, 0), { team = 5 })', {"spawn_exports": EXPORTS}, "error",
     "must be a quoted name"),
    ("animation-d-un-autre-acteur",
     'function on_collision_enter(other, my_box, other_box)\n if other.anim == "Walk" then\n end\nend', {},
     "error", "can only be made on self"),
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
