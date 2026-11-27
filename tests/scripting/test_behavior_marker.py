"""Le rôle d'un script vient de son contenu, son import de son nom logique."""
import importlib.util
import json
from pathlib import Path

from core import disk_move, lua_scripts
from core.project import Project
from core.validator import validate_project

ROOT = Path(__file__).resolve().parents[2]

MODULE = "local M = {}\n\nfunction M.update(actor)\nend\n\nreturn M\n"


def _write(path: Path, text: str, *, raw: bytes | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw if raw is not None else text.encode("utf-8"))
    return path


def _project(tmp_path: Path) -> Project:
    return Project.create(tmp_path / "Jeu", "Jeu")


def _errors(project: Project) -> list[str]:
    project = Project.open(project.root)
    project.load_all_resources()
    return [str(m) for m in validate_project(project)[1]]


def test_the_marker_must_be_the_first_line_exactly(tmp_path: Path):
    marked = _write(tmp_path / "a.lua", "-- @behavior\n" + MODULE)
    crlf = _write(tmp_path / "b.lua", "", raw=b"-- @behavior\r\n" + MODULE.encode())
    bom = _write(tmp_path / "c.lua", "", raw=b"\xef\xbb\xbf-- @behavior\n" + MODULE.encode())
    late = _write(tmp_path / "d.lua", "-- header\n-- @behavior\n" + MODULE)
    other = _write(tmp_path / "e.lua", "-- @behaviors\n" + MODULE)
    plain = _write(tmp_path / "f.lua", MODULE)

    assert [lua_scripts.is_behavior(p) for p in (marked, crlf, bom)] == [True, True, True]
    assert [lua_scripts.is_behavior(p) for p in (late, other, plain)] == [False, False, False]
    assert lua_scripts.is_behavior(tmp_path / "missing.lua") is False


def test_scripts_and_behaviors_are_told_apart_wherever_they_are_stored(tmp_path: Path):
    p = _project(tmp_path)
    a = _write(p.user_library_dir / "Levels" / "Act1" / "ai.lua", "-- @behavior\n" + MODULE)
    b = _write(p.user_library_dir / "scripts" / "behaviors" / "plain.lua", MODULE)      # l'ancien dossier ne fait plus rien
    c = _write(p.user_library_dir / "Hero.lua", "function on_update()\nend\n")

    assert p.behavior_files() == [a]
    assert sorted(p.script_files()) == sorted([b, c])
    assert lua_scripts.behavior_paths(p) == {"ai": a}


def test_require_names_resolve_by_name_whatever_the_folder_prefix_says():
    assert lua_scripts.require_name("paddle_ai") == "paddle_ai"
    assert lua_scripts.require_name("behaviors/paddle_ai") == ""
    assert lua_scripts.require_name("modules/player_movement") == ""


def test_private_module_is_not_attachable_and_keeps_a_logical_name(tmp_path: Path):
    p = _project(tmp_path)
    private = _write(p.user_library_dir / "Hero" / "player_movement.lua", "-- @module\n" + MODULE)

    assert lua_scripts.is_private_module(private)
    assert private not in p.script_files()
    assert p.private_module_files() == [private]
    assert lua_scripts.library_paths(p) == {"player_movement": private}


def test_the_template_of_a_new_behavior_carries_the_marker(tmp_path: Path):
    from scripting.script_templates import ScriptTemplateContext, generate_script_template
    path = _write(tmp_path / "x.lua", generate_script_template(ScriptTemplateContext(kind="behavior", name="x")))
    assert lua_scripts.is_behavior(path)


def test_the_template_of_a_new_private_module_carries_its_marker(tmp_path: Path):
    from scripting.script_templates import ScriptTemplateContext, generate_script_template
    path = _write(tmp_path / "x.lua", generate_script_template(ScriptTemplateContext(kind="module", name="x")))
    assert lua_scripts.is_private_module(path)


def test_a_behavior_stored_anywhere_is_inlined_by_its_name(tmp_path: Path):
    from scripting.codegen import CodegenContext, generate
    from scripting.parser import parse
    src = 'local IA = require("ia")\nfunction on_update()\n    IA.update(self)\nend\n'
    behavior = _write(tmp_path / "Somewhere" / "ia.lua", "-- @behavior\n" + MODULE)
    ctx = CodegenContext(actor_name="Guard", actor_sym="Scene_Guard", anim_names=[], sfx_names=[],
                         music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=["Scene_Guard"], is_pooled=False,
                         behavior_paths={"ia": behavior})
    code, warnings, _ = generate(parse(src), ctx)
    assert "library_ia" in code and not any("not found" in w for w in warnings)


def test_private_modules_are_inlined_in_dependency_order(tmp_path: Path):
    from scripting.codegen import CodegenContext, generate
    from scripting.parser import parse

    movement = _write(tmp_path / "player_movement.lua",
                      "-- @module\nlocal M = {}\n\nfunction M.step(actor)\nend\n\nreturn M\n")
    combat = _write(tmp_path / "player_combat.lua",
                    "-- @module\nlocal M = {}\nlocal movement = require(\"player_movement\")\n\n"
                    "function M.update(actor)\n    movement.step(actor)\nend\n\nreturn M\n")
    src = ('local combat = require("player_combat")\n'
           'function on_update()\n    combat.update(self)\nend\n')
    ctx = CodegenContext(actor_name="Hero", actor_sym="Scene_Hero", anim_names=[], sfx_names=[],
                         music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Scene_Hero"],
                         is_pooled=False, module_paths={"player_movement": movement,
                                                        "player_combat": combat})

    code, warnings, _ = generate(parse(src), ctx)

    assert "library_player_movement_step" in code
    assert "library_player_combat_update" in code
    assert code.index("library_player_movement_step") < code.index("library_player_combat_update")
    assert not warnings


def test_static_import_cycle_is_a_build_error(tmp_path: Path):
    p = _project(tmp_path)
    a = _write(p.user_library_dir / "a.lua", "-- @module\nlocal M = {}\nlocal b = require(\"b\")\nfunction M.go(actor) end\nreturn M\n")
    _write(p.user_library_dir / "b.lua", "-- @module\nlocal M = {}\nlocal a = require(\"a\")\nfunction M.go(actor) end\nreturn M\n")
    actor_script = _write(p.user_library_dir / "Hero.lua", "local a = require(\"a\")\nfunction on_update() a.go(self) end\n")
    from core.models.scene import Scene
    scene = Scene(name="Level")
    scene.script = p.asset_rel(actor_script)
    p.scenes.append(scene)
    p.save_scene(scene)

    errors = _errors(p)

    assert any("Static import cycle" in error and "a -> b -> a" in error for error in errors)


def test_a_missing_behavior_is_reported_with_the_way_to_make_one():
    from scripting.codegen import CodegenContext, generate
    from scripting.parser import parse
    src = 'local IA = require("ia")\nfunction on_update()\n    IA.update(self)\nend\n'
    ctx = CodegenContext(actor_name="Guard", actor_sym="Scene_Guard", anim_names=[], sfx_names=[],
                         music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=["Scene_Guard"], is_pooled=False, behavior_paths={})
    _code, warnings, _ = generate(parse(src), ctx)
    assert any("'ia'" in w and "not found" in w for w in warnings)


def test_two_static_libraries_with_the_same_name_are_a_build_error(tmp_path: Path):
    p = _project(tmp_path)
    _write(p.user_library_dir / "A" / "ia.lua", "-- @behavior\n" + MODULE)
    _write(p.user_library_dir / "B" / "ia.lua", "-- @module\n" + MODULE)

    errors = [e for e in _errors(p) if "Static library \"ia\"" in e]

    assert len(errors) == 1 and "A/ia.lua" in errors[0] and "B/ia.lua" in errors[0]


def test_a_behavior_outside_the_old_folder_is_still_checked_as_a_blocking_script(tmp_path: Path):
    p = _project(tmp_path)
    _write(p.user_library_dir / "Levels" / "broken.lua", "-- @behavior\nlocal M = {\n")

    errors = [e for e in _errors(p) if "broken.lua" in e]
    assert len(errors) == 1 and "incomplete or malformed" in errors[0]


def test_a_behavior_using_self_is_refused_wherever_it_lives(tmp_path: Path):
    p = _project(tmp_path)
    _write(p.user_library_dir / "Elsewhere" / "bad.lua",
           "-- @behavior\nlocal M = {}\n\nfunction M.update(actor)\n    self.x = 1\nend\n\nreturn M\n")

    assert any("Behavior \"bad\"" in e and "`self` is reserved" in e for e in _errors(p))


def test_moving_a_script_keeps_its_logical_reference(tmp_path: Path):
    from core.models.scene import Scene
    p = _project(tmp_path)
    script = _write((p.user_library_dir / "scripts") / "Level.lua", "function on_start()\nend\n")
    scene = Scene(name="Level")
    scene.script = p.script_reference(script)
    p.scenes.append(scene)
    p.save_scene(scene)
    target = p.user_library_dir / "Levels"
    target.mkdir()

    result = disk_move.move_to_folder(p, [script], target)

    assert result.refused == [] and (target / "Level.lua").is_file()
    assert scene.script == "Level"
    reopened = Project.open(p.root)
    assert reopened.scenes.get("Level").script == "Level"


def _migration():
    spec = importlib.util.spec_from_file_location(
        "migrate_behavior_markers", ROOT / "tools" / "migrate_behavior_markers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_marks_the_files_of_the_old_behaviors_folder_once(tmp_path: Path):
    old = tmp_path / "assets" / "scripts" / "behaviors"
    _write(old / "lf.lua", MODULE)
    _write(old / "crlf.lua", "", raw=MODULE.replace("\n", "\r\n").encode())
    _write(old / "done.lua", "-- @behavior\n" + MODULE)
    _write(tmp_path / "assets" / "scripts" / "Hero.lua", "function on_update()\nend\n")        # un script : intact

    assert _migration().migrate(tmp_path, dry_run=True) == 2
    assert not lua_scripts.is_behavior(old / "lf.lua")                                          # le dry-run ne touche à rien

    assert _migration().migrate(tmp_path, dry_run=False) == 2

    assert (old / "lf.lua").read_text(encoding="utf-8").startswith("-- @behavior\nlocal M")
    assert (old / "crlf.lua").read_bytes().startswith(b"-- @behavior\r\nlocal M")
    assert not lua_scripts.is_behavior(tmp_path / "assets" / "scripts" / "Hero.lua")
    assert _migration().migrate(tmp_path, dry_run=False) == 0                                   # idempotent
    assert json.dumps(sorted(p.name for p in old.glob("*.lua"))) == '["crlf.lua", "done.lua", "lf.lua"]'
