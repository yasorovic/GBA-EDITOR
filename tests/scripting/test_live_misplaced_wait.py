"""Une attente dans un `if` est refusée par le Build ET montrée par le diagnostic en direct (« No problems » était faux)."""
from __future__ import annotations

from core.models.scene import Scene
from core.project import Project
from core.validator import ValidationContext, _check_scripts_parse

SEQUENCE_IN_IF = """
function on_sequence_intro()
    wait(10)
    if global.talking == 1 then
        wait_until(input:pressed("a"))
    end
end

function on_start()
    sequence:start("intro")
end
"""

CLEAN = """
function on_sequence_intro()
    wait(10)
    wait_until(input:pressed("a"))
end

function on_start()
    sequence:start("intro")
end
"""


def _context(tmp_path, source: str):
    project = Project(tmp_path / "jeu")
    scripts = project.root / "assets" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "main.lua").write_text(source, encoding="utf-8")
    project.scenes.append(Scene(name="Village", script="assets/scripts/main.lua"))
    ctx = ValidationContext(project)
    _check_scripts_parse(ctx)
    return ctx


def test_une_attente_dans_un_if_est_une_erreur_du_diagnostic_en_direct(tmp_path):
    ctx = _context(tmp_path, SEQUENCE_IN_IF)

    messages = [m for m in ctx.errors if "wait_until()" in m.message and "not in an `if`" in m.message]
    assert len(messages) == 1 and messages[0].file == "main.lua" and messages[0].line == 5


def test_une_sequence_valide_ne_dit_rien(tmp_path):
    assert [m.message for m in _context(tmp_path, CLEAN).errors] == []
