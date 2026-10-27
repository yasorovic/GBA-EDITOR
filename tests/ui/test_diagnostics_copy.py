"""Le bouton « Copy » de l'onglet Diagnostics met la liste entière dans le presse-papiers, au format du journal."""
from __future__ import annotations

from core.diagnostic import ValidationMessage
from ui.common.build_panel import DiagnosticsView


def _view(qapp) -> DiagnosticsView:
    view = DiagnosticsView()
    view.set_diagnostics(
        [ValidationMessage("warning", "", 'Language "French": 5 of 5 entries are not translated')],
        [ValidationMessage("error", "", "Unknown method: textBox:clear()", file="SCR_Arena.lua", line=19)])
    return view


def test_copy_puts_every_message_on_the_clipboard_errors_first(qapp):
    view = _view(qapp)
    view._btn_copy.click()
    assert qapp.clipboard().text().splitlines() == [
        "[error] SCR_Arena.lua:19: Unknown method: textBox:clear()",
        '[warn]  Language "French": 5 of 5 entries are not translated',
    ]


def test_copy_confirms_with_a_changed_label(qapp):
    view = _view(qapp)
    before = view._btn_copy.text()
    view._btn_copy.click()
    assert view._btn_copy.text() != before          # « ✓ Copied » un instant
    assert view.text_for_clipboard()                # la liste n'a pas changé de contenu


def test_copy_with_no_message_copies_nothing_odd(qapp):
    view = DiagnosticsView()
    view.set_diagnostics([], [])
    view._btn_copy.click()
    assert qapp.clipboard().text() == ""


def test_the_copy_button_keeps_its_size_and_has_an_icon(qapp):
    view = _view(qapp)
    button = view._btn_copy
    assert not button.icon().isNull()                               # une icône, pas un caractère de police
    assert "⧉" not in button.text() and "✓" not in button.text()
    assert button.minimumWidth() == button.maximumWidth() > 0       # largeur fixe : « Copy » → « Copied » ne le fait pas bouger
    width = button.minimumWidth()
    button.click()
    assert button.text() == "Copied" and button.minimumWidth() == width
    view._rest_copy_button()
    assert button.text() == "Copy"
