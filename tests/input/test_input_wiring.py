"""Le câblage catalogue + checker + codegen des inputs personnalisés (ROADMAP
« Les inputs personnalisés »), après la décision de l'auteur du 2026-09-27 de
séparer ACCORDS (`InputBinding`, cases à cocher, `held`/`pressed`/`released`/
`buffered`) et SÉQUENCES (`InputSequence`, mini-langage complet, `get_sequence`
seul) : deux espaces de noms distincts, jamais l'un pour l'autre. Le C
réellement émis pour un accord, une séquence et un axe.
"""
from __future__ import annotations

import pytest


def _layout(masks=None, sequences=None, axes=()):
    """Un `InputLayout` minimal, sans scanner de scripts (les tests de
    `buffered` posent `buffered_bits` directement)."""
    from codegen.runtime_codegen.input_layout import InputLayout

    layout = InputLayout()
    layout.masks = dict(masks or {})
    for name, (tables, lens, window) in (sequences or {}).items():
        layout.sequences[name] = (tables, lens, window)
        layout.sequence_names = layout.sequence_names | {name}
    layout.axes["horizontal"] = ("BTN_LEFT", "BTN_RIGHT")
    layout.axes["vertical"] = ("BTN_UP", "BTN_DOWN")
    layout.axis_names = ["horizontal", "vertical"] + [n for n, _ in axes]
    for name, pair in axes:
        layout.axes[name] = pair
    return layout


def _lua(src: str, layout, buffered_bits=None):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(
        actor_name="Ball", input_names=list(layout.masks),
        input_sequence_names=layout.sequence_names, axis_names=layout.axis_names))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Ball"],
        input_masks=layout.masks, input_sequences=layout.sequences, input_axes=layout.axes,
        input_buffered_bits=buffered_bits or {}))
    return errors, code


def _errors(src, layout, **kw):
    return [e.message for e in _lua(src, layout, **kw)[0] if e.level == "error"]


def _body(src):
    return f"function on_update()\n{src}\nend\n"


_DASH = {"dash": "BTN_A | BTN_B"}
_QCF = {"qcf": (["_SEQ_qcf"], [3], 15)}


# ── Accords et séquences : deux espaces de noms séparés ─────────────────

def test_held_accepte_un_accord():
    layout = _layout(masks=_DASH)
    errs = _errors(_body('if input:held("dash") then end'), layout)
    assert errs == []


def test_held_refuse_une_sequence_comme_action_inconnue():
    # "qcf" n'est plus DANS input_names : held() la traite comme un nom
    # inconnu, exactement comme un bouton mal orthographié.
    layout = _layout(sequences=_QCF)
    errs = _errors(_body('if input:held("qcf") then end'), layout)
    assert errs and "unknown" in errs[0]


def test_pressed_refuse_une_sequence_comme_action_inconnue():
    layout = _layout(sequences=_QCF)
    errs = _errors(_body('if input:pressed("qcf") then end'), layout)
    assert errs and "unknown" in errs[0]


def test_get_sequence_accepte_une_sequence():
    layout = _layout(sequences=_QCF)
    errs = _errors(_body('if input:get_sequence("qcf") then end'), layout)
    assert errs == []


def test_get_sequence_refuse_un_accord():
    layout = _layout(masks=_DASH)
    errs = _errors(_body('if input:get_sequence("dash") then end'), layout)
    assert errs and "unknown" in errs[0]


# ── held(n) / buffered(frames) : bornes et littéral obligatoire ─────────

def test_held_avec_frames_hors_bornes():
    layout = _layout(masks=_DASH)
    errs = _errors(_body('if input:held("dash", 256) then end'), layout)
    assert any("255" in e for e in errs), errs


def test_held_avec_trop_darguments():
    layout = _layout(masks=_DASH)
    errs = _errors(_body('if input:held("dash", 3, 4) then end'), layout)
    assert errs, "held() à 3 arguments doit être refusé"


def test_buffered_frames_non_litteral_refuse():
    layout = _layout(masks=_DASH)
    errs = _errors(_body('local n = 4\nif input:buffered("dash", n) then end'), layout)
    assert any("literal" in e.lower() or "plain" in e.lower() for e in errs), errs


def test_buffered_frames_litteral_ok():
    layout = _layout(masks=_DASH)
    errs = _errors(_body('if input:buffered("dash", 6) then end'), layout)
    assert errs == []


# ── get_axis : arité et noms d'axe ───────────────────────────────────

def test_get_axis_horizontal_seul():
    layout = _layout()
    errs = _errors(_body('local x = input:get_axis("horizontal")'), layout)
    assert errs == []


def test_get_axis_axe_inconnu():
    layout = _layout()
    errs = _errors(_body('local v = input:get_axis("diagonale")'), layout)
    assert any("axe" in e.lower() for e in errs), errs


def test_get_axis_trop_darguments():
    layout = _layout()
    errs = _errors(_body('local v = input:get_axis("horizontal", "vertical", "z")'), layout)
    assert errs, "get_axis() à 3 arguments doit être refusé"


# ── Le C réellement émis ──────────────────────────────────────────────

def test_emet_input_held_pour_un_accord():
    layout = _layout(masks=_DASH)
    _, code = _lua(_body('if input:held("dash") then end'), layout)
    assert "input_held(BTN_A | BTN_B)" in code, code


def test_emet_input_pressed_pour_un_accord():
    layout = _layout(masks=_DASH)
    _, code = _lua(_body('if input:pressed("dash") then end'), layout)
    assert "input_pressed(BTN_A | BTN_B)" in code, code


def test_emet_input_seq_pressed_pour_get_sequence():
    layout = _layout(sequences=_QCF)
    _, code = _lua(_body('if input:get_sequence("qcf") then end'), layout)
    assert "input_seq_pressed(_SEQ_qcf, 3, 15)" in code, code


def test_emet_input_buffered_avec_son_bit():
    layout = _layout(masks=_DASH)
    _, code = _lua(_body('if input:buffered("dash", 6) then end'), layout,
                   buffered_bits={"dash": 2})
    assert "input_buffered(2, BTN_A | BTN_B, 6)" in code, code


def test_emet_input_get_axis_scalaire():
    layout = _layout()
    _, code = _lua(_body('local x = input:get_axis("horizontal")'), layout)
    assert "input_get_axis(BTN_LEFT, BTN_RIGHT)" in code, code


def test_emet_input_get_vector_pour_deux_axes():
    layout = _layout()
    _, code = _lua(_body('local v = input:get_axis("horizontal", "vertical")'), layout)
    assert "input_get_vector(BTN_LEFT, BTN_RIGHT, BTN_UP, BTN_DOWN)" in code, code


def test_axe_personnalise_resout_ses_masques():
    layout = _layout(axes=[("look", ("BTN_L", "BTN_R"))])
    errs = _errors(_body('local x = input:get_axis("look")'), layout)
    assert errs == []
    _, code = _lua(_body('local x = input:get_axis("look")'), layout)
    assert "input_get_axis(BTN_L, BTN_R)" in code, code
