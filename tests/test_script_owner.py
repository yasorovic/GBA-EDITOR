"""Un script n'a pas de type : son attache lui donne son contexte.

Trois refus, tous au build : `self` hors acteur/prefab, un événement d'une autre
famille de propriétaire, un fichier attaché à deux familles. Et le pendant côté
éditeur : la complétion ne propose que ce que le build accepterait.
"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from scripting.parser import parse
from scripting.checker import check, BuildContext


def _errors(src: str, owner_kind: str, **kw) -> list[str]:
    ctx = BuildContext(actor_name="X", owner_kind=owner_kind, **kw)
    return [e.message for e in check(parse(src), ctx) if e.level == "error"]


# ── `self` ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["scene", "camera"])
@pytest.mark.parametrize("src", [
    "function on_update()\n    self.position = vec2(1, 2)\nend\n",
    "function on_update()\n    self:play_anim(\"idle\")\nend\n",
    "function on_update()\n    local p = self.position\nend\n",
])
def test_self_refuse_hors_acteur(kind, src):
    errs = _errors(src, kind)
    assert any("`self` n'existe pas" in m for m in errs), errs


@pytest.mark.parametrize("kind", ["actor", "prefab", ""])
def test_self_admis_pour_acteur_prefab_et_contexte_relache(kind):
    errs = _errors("function on_update()\n    self.position = vec2(1, 2)\nend\n", kind)
    assert not any("`self` n'existe pas" in m for m in errs), errs


def test_script_de_scene_sans_self_reste_valide():
    assert _errors("function on_start()\nend\nfunction on_update()\nend\n", "scene") == []


# ── Behavior : pas de `self` ───────────────────────────────────────

_BEHAVIOR_SELF_EN_CORPS = (
    "local M = {}\nfunction M.update(actor)\n    self.position = actor.position\nend\nreturn M\n")
_BEHAVIOR_SELF_PARAMETRE = (
    "local M = {}\nfunction M.update(self)\n    self:destroy()\nend\nreturn M\n")


@pytest.mark.parametrize("src", [_BEHAVIOR_SELF_EN_CORPS, _BEHAVIOR_SELF_PARAMETRE])
def test_behavior_refuse_self_en_corps_et_en_parametre(src):
    errs = [e.message for e in check(parse(src), BuildContext(owner_kind="behavior"),
                                     check_event_names=False) if e.level == "error"]
    assert any("`self` n'existe pas" in m and "de behavior" in m for m in errs), errs


def test_behavior_avec_parametre_actor_est_valide():
    src = "local M = {}\nfunction M.update(actor)\n    actor.position = vec2(1, 2)\nend\nreturn M\n"
    assert not [e for e in check(parse(src), BuildContext(owner_kind="behavior"),
                                 check_event_names=False) if e.level == "error"]


def test_validateur_bloque_un_behavior_qui_ecrit_self(tmp_path):
    from core.validator import _check_behaviors_without_self
    (tmp_path / "bon.lua").write_text("local M = {}\nfunction M.f(actor)\nend\nreturn M\n")
    (tmp_path / "mauvais.lua").write_text(_BEHAVIOR_SELF_PARAMETRE)
    msgs: list[str] = []
    _check_behaviors_without_self(NS(project=NS(scripts_behaviors_dir=tmp_path),
                                     error=lambda _o, m, *_: msgs.append(m)))
    assert len(msgs) == 1 and "mauvais" in msgs[0]


# ── Événements par famille ──────────────────────────────────────────

def test_evenement_d_acteur_refuse_dans_une_camera():
    errs = _errors("function on_collision_enter(other, a, b)\nend\n", "camera")
    assert len(errs) == 1 and "on_collision_enter" in errs[0] and "de caméra" in errs[0]


def test_on_late_update_refuse_dans_une_camera_admis_dans_une_scene():
    src = "function on_late_update()\nend\n"
    assert _errors(src, "scene") == []
    assert any("on_late_update" in m for m in _errors(src, "camera"))


def test_evenement_de_scene_ordinaire_admis_pour_un_acteur():
    assert _errors("function on_start()\nend\n", "actor") == []


def test_fonction_privee_n_est_pas_prise_pour_un_evenement():
    errs = _errors("function aide()\n    return 1\nend\nfunction on_update()\n    aide()\nend\n",
                   "scene")
    assert errs == []


# ── Complétion ──────────────────────────────────────────────────────

def test_completion_ne_propose_pas_self_hors_acteur():
    import scripting.completion as C
    assert C.candidates_at("self.", context="camera") == []
    assert C.candidates_at("self:", context="scene") == []
    assert C.candidates_at("self:", context="actor") != []


def test_completion_ne_propose_pas_les_evenements_d_acteur_a_une_camera():
    import scripting.completion as C
    proposes = {c.insert for c in C.candidates_at("", context="camera") if c.kind == C.KIND_EVENT}
    assert "on_collision_enter" not in proposes and "on_update" in proposes


# ── Un fichier, une famille ─────────────────────────────────────────

def _script_comp(path, active=True):
    return NS(script=path, active=active)


def _project(scene_script="", actor_scripts=(), camera_scripts=(), prefab_scripts=()):
    actors = [NS(name=f"A{i}", get_component=lambda _n, c=_script_comp(s): c)
              for i, s in enumerate(actor_scripts)]
    cams = [NS(name=f"C{i}", script=s) for i, s in enumerate(camera_scripts)]
    scene = NS(name="S", script=scene_script, actors=actors, cameras=cams)
    prefabs = [NS(name=f"P{i}", get_component=lambda _n, c=_script_comp(s): c)
               for i, s in enumerate(prefab_scripts)]
    return NS(scenes=[scene], prefabs=prefabs)


def _refus(project) -> list[str]:
    from core.validator import _check_script_owner_families
    msgs: list[str] = []
    _check_script_owner_families(NS(project=project, error=lambda _o, m, *_: msgs.append(m)))
    return msgs


def test_meme_fichier_sur_acteur_et_scene_refuse():
    (msg,) = _refus(_project(scene_script="s/x.lua", actor_scripts=["s/x.lua"]))
    assert "s/x.lua" in msg and "plusieurs familles" in msg


def test_meme_fichier_sur_acteur_et_camera_refuse():
    assert len(_refus(_project(actor_scripts=["s/x.lua"], camera_scripts=["s/x.lua"]))) == 1


def test_acteurs_et_prefab_partagent_une_famille():
    assert _refus(_project(actor_scripts=["s/x.lua", "s/x.lua"], prefab_scripts=["s/x.lua"])) == []


def test_scripts_distincts_par_famille_sans_refus():
    assert _refus(_project(scene_script="s/a.lua", actor_scripts=["s/b.lua"],
                           camera_scripts=["s/c.lua"])) == []
