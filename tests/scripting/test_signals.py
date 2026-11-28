"""Le contrat Lua et C de la première tranche du bus de signaux."""
from __future__ import annotations


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
