"""Le contrat Lua et C de la première tranche du bus de signaux."""
from __future__ import annotations

import os
import subprocess

import pytest

from native_toolchain import compilateur_hote, environnement


def _lua(source: str, *, owner_kind: str = "actor"):
    from scripting.parser import parse
    from scripting.checker import BuildContext, check
    from scripting.codegen import CodegenContext, generate

    script = parse(source)
    errors = check(script, BuildContext(
        actor_name="Door", anim_names=["idle"], owner_kind=owner_kind,
    ))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Door", actor_sym="Door", anim_names=["idle"],
        sfx_names=[], music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Door"], signal_ids={"lever_pulled": 0},
    ))
    return [error.message for error in errors if error.level == "error"], code


def test_emit_and_handler_compile_to_a_static_dispatcher():
    errors, code = _lua(
        'function on_update()\n'
        '  signal:emit("lever_pulled", self, 2)\n'
        'end\n'
        'function on_signal_lever_pulled(emitter, value)\n'
        '  if emitter and value == 2 then self:hide() end\n'
        'end\n')

    assert errors == []
    assert "signal_emit(0, self, 2);" in code
    assert "static void Door_on_signal_lever_pulled(Actor* self, Actor* emitter, int value)" in code
    assert "void Door_on_signal(Actor* self, int signal, Actor* emitter, int value)" in code
    assert "case 0: Door_on_signal_lever_pulled(self, emitter, value); break;" in code


def test_emit_accepts_its_minimal_and_optional_forms():
    errors, code = _lua(
        'function on_update()\n'
        '  signal:emit("lever_pulled")\n'
        '  signal:emit("lever_pulled", self)\n'
        'end\n')

    assert errors == []
    assert "signal_emit(0, 0, 0);" in code
    assert "signal_emit(0, self, 0);" in code


def test_signal_handler_rejects_out_of_order_parameters():
    errors, _code = _lua("function on_signal_lever_pulled(value, emitter)\nend\n")

    assert any("emitter, value" in error for error in errors)


def test_area_scripts_do_not_receive_signals_in_this_tranche():
    errors, _code = _lua("function on_signal_lever_pulled()\nend\n", owner_kind="area")

    assert any("actor, prefab and scene" in error for error in errors)


def test_runtime_has_two_bounded_queues_and_a_safe_emitter():
    from codegen.runtime_codegen.signals import signal_runtime_lines

    code = "\n".join(signal_runtime_lines())
    assert "#define SIGNAL_CAPACITY 16" in code
    assert "g_signal_queue[2][SIGNAL_CAPACITY]" in code
    assert "int write = g_signal_read ^ 1;" in code
    assert "s->emitter && s->emitter->alive" in code


def test_validator_warns_when_a_signal_has_only_one_end(tmp_path):
    from core import validator
    from core.models.components import ScriptComponent
    from core.models.scene import Actor
    from core.project import Project

    project = Project.create(tmp_path / "Game", "Game")
    scripts = project.user_library_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    scene = project.scenes[0]
    actor = Actor(name="Door", components=[ScriptComponent(script="assets/scripts/Door.lua")])
    scene.actors.append(actor)
    script_path = scripts / "Door.lua"

    def messages():
        ctx = validator.ValidationContext(project)
        validator._check_signal_handlers(ctx, scene)
        return [message.message for message in ctx._msgs]

    script_path.write_text('function on_update()\n  signal:emit("open")\nend\n', encoding="utf-8")
    assert any('signal:emit("open") has no receiver' in message for message in messages())

    script_path.write_text('function on_signal_open(emitter, value)\nend\n', encoding="utf-8")
    assert any("on_signal_open will never be called" in message for message in messages())

    script_path.write_text(
        'function on_update()\n  signal:emit("open")\nend\n'
        'function on_signal_open(emitter, value)\nend\n', encoding="utf-8")
    assert messages() == []


def test_runtime_delivers_the_next_frame_and_bounds_its_queue(tmp_path):
    """La file C réelle garde son délai, sa saturation et les handles sûrs."""
    compiler = compilateur_hote()
    if compiler is None:
        message = "no host C compiler: signal runtime behavior was not verified"
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message)

    from codegen.runtime_codegen.signals import signal_runtime_lines

    probe = "\n".join([
        "#include <assert.h>",
        "typedef struct Actor { int alive; } Actor;",
        *signal_runtime_lines(),
        "int main(void) {",
        "    Actor live = {1}; Actor dead = {0};",
        "    int id, value; Actor* emitter;",
        "    signal_reset();",
        "    assert(signal_emit(3, &live, 7));",
        "    assert(!signal_next(&id, &emitter, &value));",
        "    signal_begin_frame();",
        "    assert(signal_next(&id, &emitter, &value));",
        "    assert(id == 3 && emitter == &live && value == 7);",
        "    assert(!signal_next(&id, &emitter, &value));",
        "    assert(signal_emit(4, &dead, 9));",
        "    signal_begin_frame();",
        "    assert(signal_next(&id, &emitter, &value));",
        "    assert(id == 4 && emitter == 0 && value == 9);",
        "    signal_reset();",
        "    for(int n = 0; n < SIGNAL_CAPACITY; n++) assert(signal_emit(n, 0, n));",
        "    assert(!signal_emit(99, 0, 0));",
        "    signal_reset();",
        "    signal_begin_frame();",
        "    assert(!signal_next(&id, &emitter, &value));",
        "    return 0;",
        "}",
    ])
    source = tmp_path / "signals_probe.c"
    binary = tmp_path / "signals_probe"
    source.write_text(probe, encoding="utf-8")
    env = environnement(compiler)
    # GCC reçoit les variables modifiées par conftest. Sa compilation doit
    # pourtant écrire ses temporaires près de cette sonde, pas dans un ancien
    # cache pytest éventuellement verrouillé.
    for variable in ("TMP", "TEMP", "TMPDIR"):
        env[variable] = str(tmp_path)
    build = subprocess.run(
        [compiler, "-std=c11", "-Wall", "-Werror", "-O0", "-o", str(binary), str(source)],
        capture_output=True, text=True, env=env)
    assert build.returncode == 0, build.stderr + probe
    run = subprocess.run([str(binary)], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
