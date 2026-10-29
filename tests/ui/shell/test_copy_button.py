"""Le modèle de bouton « copier dans le presse-papiers » : copie, s'allume, dit « Copied », puis revient."""
from __future__ import annotations

from ui.common.copy_button import CopyButton
from ui.common.labels import label


def test_click_copies_lights_up_and_says_copied(qapp):
    button = CopyButton(lambda: "scr_score_player", "Text key")
    rest_style = button.styleSheet()
    button.click()
    assert qapp.clipboard().text() == "scr_score_player"
    assert button.toolTip() == label("common.copied")
    assert button.styleSheet() != rest_style                       # surbrillance
    assert button._restore_timer.isActive()


def test_the_button_comes_back_to_rest(qapp):
    button = CopyButton(lambda: "x", "Text key")
    rest = (button.styleSheet(), button.toolTip())
    button.click()
    button._rest()                                                 # ce que le minuteur appelle après 900 ms
    assert (button.styleSheet(), button.toolTip()) == rest


def test_nothing_to_copy_does_nothing(qapp):
    qapp.clipboard().setText("avant")
    button = CopyButton(lambda: None, "Text key")
    button.click()
    assert qapp.clipboard().text() == "avant"
    assert not button._restore_timer.isActive() and button.toolTip() == "Text key"


def test_a_new_rest_tip_is_kept_after_the_feedback(qapp):
    button = CopyButton(lambda: "x", "old")
    button.click()
    button.set_tip("new")                                          # pendant le retour d'information
    assert button.toolTip() == label("common.copied")
    button._rest()
    assert button.toolTip() == "new"
