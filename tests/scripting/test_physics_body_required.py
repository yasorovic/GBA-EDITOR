"""`self:physics_body()` ne rend jamais nil : sans composant PhysicsBody, le build refuse l'appel."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "editor"))

from scripting.checker import check, BuildContext
from scripting.parser import parse

SRC = "function on_update()\n    local body = self:physics_body()\n    body.velocity = vec2(0, 0)\nend\n"


def _errors(**kw):
    return [e for e in check(parse(SRC), BuildContext(actor_name="T", owner_kind="actor", **kw))
            if e.level == "error"]


def test_refused_without_component():
    errs = _errors(has_physics_body=False)
    assert any("no PhysicsBody component" in e.message for e in errs)


def test_accepted_with_component():
    assert not any("PhysicsBody" in e.message for e in _errors(has_physics_body=True))


def test_relaxed_without_context():
    assert not any("PhysicsBody" in e.message for e in _errors())
