"""L'entrée interne `interact` (tranche 1 du chantier « Interagir avec un acteur ») : elle existe dans
tout projet sans être déclarée, son réglage est un accord de boutons (A par défaut), son nom est refusé
à l'auteur, et elle ne se sauve que si elle a bougé."""
from __future__ import annotations

import json
from types import SimpleNamespace

from core.models.settings import (
    DEFAULT_INTERACT_BUTTONS, INTERACT_INPUT_NAME, InputAxis, InputBinding, InputSequence,
    ProjectSettings,
)


def _layout(settings):
    from codegen.runtime_codegen.input_layout import compute_input_layout
    return compute_input_layout(SimpleNamespace(settings=settings, scenes=[], prefabs=[]))


def test_un_projet_neuf_a_interact_sur_a():
    assert INTERACT_INPUT_NAME == "interact"
    assert ProjectSettings().interact_buttons == list(DEFAULT_INTERACT_BUTTONS) == ["a"]
    assert _layout(ProjectSettings()).masks["interact"] == "BTN_A"


def test_interact_se_regle_sur_un_accord():
    s = ProjectSettings()
    s.interact_buttons = ["up", "a"]
    assert _layout(s).masks["interact"] == "BTN_A | BTN_UP"


def test_un_accord_de_l_auteur_ne_redefinit_pas_interact():
    s = ProjectSettings()
    s.inputs = [InputBinding(name="interact", buttons=["b"]), InputBinding(name="jump", buttons=["b"])]
    masks = _layout(s).masks
    assert masks["interact"] == "BTN_A" and masks["jump"] == "BTN_B"


def test_un_script_lit_interact_sans_l_avoir_declare():
    """`interact` est parmi les noms d'entrée que reçoit le vérificateur : `input:pressed("interact")`
    s'écrit sans déclaration."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    layout = _layout(ProjectSettings())
    script = parse('function on_update()\n if input:pressed("interact") then end\nend\n')
    errors = check(script, BuildContext(
        actor_name="Ball", input_names=list(layout.masks),
        input_sequence_names=layout.sequence_names, axis_names=layout.axis_names))
    assert [e for e in errors if e.level == "error"] == []


def _erreurs_de_nom_reserve(settings):
    from core.validator import _check_reserved_input_names
    messages = []
    ctx = SimpleNamespace(project=SimpleNamespace(settings=settings),
                          error=lambda _owner, message, *a, **k: messages.append(message))
    _check_reserved_input_names(ctx)
    return messages


def test_le_nom_interact_est_refuse_a_une_entree_un_axe_ou_une_sequence():
    s = ProjectSettings()
    assert _erreurs_de_nom_reserve(s) == []
    s.inputs = [InputBinding(name="interact", buttons=["b"])]
    s.axes = [InputAxis(name="interact", negative="left", positive="right")]
    s.sequences = [InputSequence(name="interact", expression="down + a")]
    messages = _erreurs_de_nom_reserve(s)
    assert len(messages) == 3
    assert all("reserved" in m and "Rename" in m for m in messages)
    assert any("input" in m for m in messages) and any("axis" in m for m in messages)
    assert any("sequence" in m for m in messages)


def _manifeste(projet) -> dict:
    from core.project_paths import find_manifest
    return json.loads(find_manifest(projet.root).read_text(encoding="utf-8"))


def test_interact_ne_s_ecrit_que_deplace_et_se_relit(tmp_path):
    from core.project import Project
    projet = Project.create(tmp_path / "Game", "Game")
    projet.save_settings()
    assert "interact_buttons" not in _manifeste(projet)            # défaut : aucune clé

    projet.settings.interact_buttons = ["b", "up"]
    projet.save_settings()
    assert _manifeste(projet)["interact_buttons"] == ["b", "up"]

    projet.settings.interact_buttons = []
    projet.load_settings()
    assert projet.settings.interact_buttons == ["up", "b"]         # ordre du boîtier


def test_un_accord_vide_ou_inconnu_retombe_sur_le_defaut(tmp_path):
    from core.project import Project
    from core.project_paths import find_manifest
    projet = Project.create(tmp_path / "Game", "Game")
    projet.save_settings()
    manifeste = find_manifest(projet.root)
    donnees = json.loads(manifeste.read_text(encoding="utf-8"))
    donnees["interact_buttons"] = ["turbo"]
    manifeste.write_text(json.dumps(donnees), encoding="utf-8", newline="\n")
    projet.load_settings()
    assert projet.settings.interact_buttons == ["a"]


def test_la_portee_de_la_visee_vaut_4_et_ne_s_ecrit_que_deplacee(tmp_path):
    from core.project import Project
    projet = Project.create(tmp_path / "Game", "Game")
    assert projet.settings.interact_reach == 4
    projet.save_settings()
    assert "interact_reach" not in _manifeste(projet)

    projet.settings.interact_reach = 9
    projet.save_settings()
    assert _manifeste(projet)["interact_reach"] == 9

    projet.settings.interact_reach = 0
    projet.load_settings()
    assert projet.settings.interact_reach == 9


def test_une_portee_hors_limites_est_ramenee_dans_les_bornes(tmp_path):
    from core.models.settings import MAX_INTERACT_REACH
    from core.project import Project
    from core.project_paths import find_manifest
    projet = Project.create(tmp_path / "Game", "Game")
    projet.save_settings()
    manifeste = find_manifest(projet.root)
    for ecrit, attendu in ((9999, MAX_INTERACT_REACH), (-5, 0), ("x", 4)):
        donnees = json.loads(manifeste.read_text(encoding="utf-8"))
        donnees["interact_reach"] = ecrit
        manifeste.write_text(json.dumps(donnees), encoding="utf-8")
        projet.load_settings()
        assert projet.settings.interact_reach == attendu
