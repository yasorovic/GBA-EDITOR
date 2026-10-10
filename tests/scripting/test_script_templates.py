"""Les scripts proposés par l'éditeur restent valides pour chaque propriétaire."""

import pytest

from scripting.checker import BuildContext, check
from scripting.parser import parse
from scripting.script_templates import ScriptTemplateContext, generate_script_template
from scripting.api import EVENT_REGISTRY


@pytest.mark.parametrize("kind, owner_kind", [
    ("actor", "actor"),
    ("scene", "scene"),
    ("camera", "camera"),
])
def test_event_template_is_minimal_and_valid(kind, owner_kind):
    source = generate_script_template(ScriptTemplateContext(
        kind=kind,
        name="Example",
        actor_name="Actor",
        component_labels=["Sprite", "CollisionBox(body)"],
        has_sprite=True,
        has_sfx=True,
        collision_tags=["body"],
    ))

    assert source == "function on_update()\nend\n"
    assert not [error for error in check(parse(source), BuildContext(
        actor_name="Actor", owner_kind=owner_kind,
    )) if error.level == "error"]


def test_behavior_template_keeps_only_the_module_contract():
    source = generate_script_template(ScriptTemplateContext(kind="behavior", name="ai"))

    assert source == "-- @behavior\nlocal M = {}\n\nfunction M.update(actor)\nend\n\nreturn M\n"
    assert not [error for error in check(
        parse(source), BuildContext(owner_kind="behavior"), check_event_names=False,
    ) if error.level == "error"]


def test_empty_template_is_empty():
    assert generate_script_template(ScriptTemplateContext()) == ""


def test_event_stubs_are_minimal_and_valid_for_an_actor():
    for name, meta in EVENT_REGISTRY.items():
        source = meta["stub"]
        assert "    \n" not in source
        assert source.startswith(f"function {name}(")
        assert not [error for error in check(parse(source), BuildContext(
            actor_name="Actor", owner_kind="actor",
        )) if error.level == "error"]
