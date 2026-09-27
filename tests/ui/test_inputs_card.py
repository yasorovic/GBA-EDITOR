"""L'écran des inputs personnalisés, après la décision de Victor du
2026-09-27 : InputsCard redevient des boutons à bascule à icônes (accords
simples — les MÊMES icônes que les events `on_button_*` du Script Editor),
SequencesCard porte le mini-langage complet (get_sequence), et AxesCard ne
propose jamais une séquence comme côté d'axe — les trois espaces sont
distincts.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QLineEdit, QSpinBox

from core.models.settings import InputAxis, InputBinding, InputSequence, ProjectSettings
from ui.common.widgets import HoverIconButton
from ui.scene_manager.inspectors.axes_card import AxesCard
from ui.scene_manager.inspectors.inputs_card import InputsCard, _BUTTON_ICONS
from ui.scene_manager.inspectors.sequences_card import SequencesCard, render_preview
from core.models.input_expression import parse_input_expression


class _FakeProject:
    def __init__(self, settings: ProjectSettings):
        self.settings = settings


def _row_buttons(card, i) -> list:
    """Les boutons à bascule de boutons GBA — pas le bouton × (danger), lui
    aussi un `HoverIconButton` mais non cochable."""
    host = card._rows.itemAt(i).widget()
    return [b for b in host.findChildren(HoverIconButton) if b.isCheckable()]


def _row_preview(card, i) -> str:
    host = card._rows.itemAt(i).widget()
    return host.findChildren(QLabel)[-1].text()


def _row_window_hidden(card, i) -> bool:
    host = card._rows.itemAt(i).widget()
    return host.findChildren(QSpinBox)[0].isHidden()


# ── InputsCard : boutons à bascule à icônes, un accord simple ────────

def test_inputs_card_affiche_un_bouton_par_touche(qapp):
    settings = ProjectSettings(inputs=[InputBinding(name="dash", buttons=["right", "a"])])
    card = InputsCard()
    card.load(_FakeProject(settings))

    buttons = _row_buttons(card, 0)
    assert len(buttons) == len(_BUTTON_ICONS)
    checked_keys = {k for (k, _icon), b in zip(_BUTTON_ICONS, buttons) if b.isChecked()}
    assert checked_keys == {"right", "a"}


def test_inputs_card_case_cochee_met_a_jour_buttons(qapp):
    settings = ProjectSettings(inputs=[InputBinding(name="dash")])
    card = InputsCard()
    card.load(_FakeProject(settings))
    received = []
    card.input_field_changed.connect(lambda b, f, v: received.append((f, v)))

    card._commit_button(0, "a", True)

    assert received == [("buttons", ["a"])]


# ── SequencesCard : mini-langage, aperçu, fenêtre ────────────────────

def test_sequence_preview_et_fenetre(qapp):
    settings = ProjectSettings(sequences=[
        InputSequence(name="qcf", expression="quarter_circle_right", window=15)])
    card = SequencesCard()
    card.load(_FakeProject(settings))

    assert _row_preview(card, 0) == "↓ ➜ ↘ ➜ →"
    assert not _row_window_hidden(card, 0)


def test_sequence_expression_invalide_affiche_l_erreur(qapp):
    settings = ProjectSettings(sequences=[InputSequence(name="bad", expression="a +")])
    card = SequencesCard()
    card.load(_FakeProject(settings))

    assert "Invalid expression" in _row_preview(card, 0)


def test_sequences_dupliquees_s_avertissent_l_une_l_autre(qapp):
    settings = ProjectSettings(sequences=[
        InputSequence(name="dup1", expression="down - right"),
        InputSequence(name="dup2", expression="down - right"),
    ])
    card = SequencesCard()
    card.load(_FakeProject(settings))

    assert "dup2" in _row_preview(card, 0)
    assert "dup1" in _row_preview(card, 1)


def test_render_preview_accord_simple():
    expr = parse_input_expression("down + a")[0]
    assert render_preview(expr) == "↓+Ⓐ"


# ── AxesCard : jamais une séquence comme côté ────────────────────────

def test_axe_ne_propose_que_des_accords(qapp):
    settings = ProjectSettings(
        inputs=[InputBinding(name="dash", buttons=["right", "a"])],
        sequences=[InputSequence(name="qcf", expression="quarter_circle_right")],
    )
    card = AxesCard()
    card.load(_FakeProject(settings))

    choices = card._side_choices()
    assert "dash" in choices
    assert "qcf" not in choices


def test_axe_refuse_un_nom_reserve(qapp):
    settings = ProjectSettings(axes=[InputAxis(name="look", negative="l", positive="r")])
    card = AxesCard()
    card.load(_FakeProject(settings))
    received = []
    card.axis_field_changed.connect(lambda axis, field, value: received.append((field, value)))

    card._commit_name(0, "horizontal")

    assert received == []
    assert settings.axes[0].name == "look"
