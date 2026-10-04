"""Le choix de langue de l'interface dans les réglages."""
from __future__ import annotations

from core import interface_preferences as prefs
from ui.common import catalog
from ui.common.labels import label
from ui.common.settings_dialog import InterfacePanel
from ui.common.settings_dialog import ShortcutsPanel


def test_interface_panel_defers_language_until_restart(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(prefs, "CONFIG_FILE", tmp_path / "interface.json")
    monkeypatch.setattr(prefs, "_cache", None)
    catalog.set_language("")

    panel = InterfacePanel()
    french_index = panel._language.findData("fr")
    assert french_index >= 0

    panel._language.setCurrentIndex(french_index)

    assert prefs.interface_language() == "fr"
    assert label("settings.window_title") == "Settings"
    # Even a panel constructed after changing the preference stays in English.
    shortcuts = ShortcutsPanel()
    assert "file.new" in shortcuts._edits
    assert shortcuts._binding_label("file.new") == "New project"
    # The startup entry point applies the persisted preference.
    catalog.set_language(prefs.interface_language())
    assert label("settings.window_title") == "Réglages"
    catalog.set_language("")


def test_shortcuts_table_is_french(qapp):
    catalog.set_language("fr")
    panel = ShortcutsPanel()

    assert panel._context_label("global") == "Raccourcis communs"
    assert panel._binding_label("file.new") == "Nouveau projet"
    assert panel._context_label("scene_canvas") == "Canvas de scène"
    assert panel._binding_label("canvas.tool_select") == "Outil de sélection"
    catalog.set_language("")
