"""Le bouton « copier la clé » d'une entrée de texte s'allume et dit « Copied » un instant, puis revient."""
from __future__ import annotations

from types import SimpleNamespace

from ui.common.labels import label
from ui.text_editor.text_entry import TextEntry


def _entry(qapp) -> TextEntry:
    text = SimpleNamespace(key="scr_score_player", id="t1")
    return TextEntry(text, "Score", None)


def test_copy_puts_the_key_on_the_clipboard_and_lights_the_button(qapp):
    entry = _entry(qapp)
    rest_style, rest_tip = entry._copy_btn.styleSheet(), entry._copy_btn.toolTip()
    entry._copy_btn.click()
    assert qapp.clipboard().text() == "scr_score_player"
    assert entry._copy_btn.toolTip() == label("common.copied")
    assert entry._copy_btn.styleSheet() != rest_style              # surbrillance
    assert entry._copy_btn._restore_timer.isActive()


def test_the_button_comes_back_to_rest(qapp):
    entry = _entry(qapp)
    rest_style, rest_tip = entry._copy_btn.styleSheet(), entry._copy_btn.toolTip()
    entry._copy_btn.click()
    entry._copy_btn._rest()                                        # ce que le minuteur appelle après 900 ms
    assert (entry._copy_btn.styleSheet(), entry._copy_btn.toolTip()) == (rest_style, rest_tip)
