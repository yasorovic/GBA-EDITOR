"""Les textes visibles du sélecteur de projet en français."""
from __future__ import annotations

from PyQt6.QtWidgets import QPushButton

from ui.common import catalog
from ui.home import project_picker
from ui.home.project_picker import HomeScreen, NewProjectDialog


def test_home_screen_is_french(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(project_picker, "load_recent", lambda: [])
    catalog.set_language("fr")

    home = HomeScreen(tmp_path)

    assert home.windowTitle() == "Backstage — Ouvrir un projet"
    assert home._tab_bar.tabText(0) == "Projets"
    # L'onglet « Modèles » n'existe que si une source de modèles est configurée.
    assert (home._tab_bar.count() == 2) == bool(project_picker.TEMPLATES)
    if project_picker.TEMPLATES:
        assert home._tab_bar.tabText(1) == "Modèles"
    assert home._empty_lbl.text().startswith("Aucun projet récent")
    # Le bouton porte une icône et un espace avant son texte.
    assert "Nouveau projet" in {button.text().strip() for button in home.findChildren(QPushButton)}
    catalog.set_language("")


def test_new_project_dialog_is_french(qapp, tmp_path):
    catalog.set_language("fr")
    dialog = NewProjectDialog(tmp_path)

    assert dialog.windowTitle() == "Nouveau projet"
    assert dialog._name_edit.placeholderText() == "MonJeu"
    catalog.set_language("")
