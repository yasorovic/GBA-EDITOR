"""Préférences propres à l'affichage de l'éditeur."""
from __future__ import annotations

from core import interface_preferences as prefs


def test_interface_language_is_persisted(tmp_path, monkeypatch):
    config = tmp_path / "interface.json"
    monkeypatch.setattr(prefs, "CONFIG_FILE", config)
    monkeypatch.setattr(prefs, "_cache", None)

    assert prefs.interface_language() == ""
    prefs.set_interface_language("fr")

    monkeypatch.setattr(prefs, "_cache", None)
    assert prefs.interface_language() == "fr"
