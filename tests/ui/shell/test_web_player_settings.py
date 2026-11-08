"""La carte « WEB build » des paramètres du projet : deux modes exclusifs."""
from core.project import Project
from ui.scene_manager.inspectors.project_settings_dialog import BuildPanel


def _project(tmp_path):
    root = tmp_path / "projet"
    root.mkdir()
    return Project(root)


def test_les_deux_modes_montrent_chacun_leur_panneau(qapp, tmp_path):
    project = _project(tmp_path)
    panel = BuildPanel(project)
    card = panel._web
    assert card._mode_buttons["builtin"].isChecked()
    assert not card._builtin.isHidden() and card._custom.isHidden()

    card._mode_buttons["custom"].click()
    assert project.settings.web_player_mode == "custom"
    assert card._mode_buttons["custom"].isChecked()
    assert card._builtin.isHidden() and not card._custom.isHidden()
    panel.close()


def test_l_image_du_contour_ne_s_affiche_que_pour_le_contour_image(qapp, tmp_path):
    project = _project(tmp_path)
    panel = BuildPanel(project)
    card = panel._web
    frame_row = card._frame_image.parentWidget()
    assert card._combo_frame.currentData() == "backstage"
    assert frame_row.isHidden()
    card._combo_frame.setCurrentIndex(card._combo_frame.findData("backstage-light"))
    card._combo_frame.activated.emit(card._combo_frame.currentIndex())
    assert project.settings.web_frame == "backstage-light"
    assert frame_row.isHidden()
    card._combo_frame.setCurrentIndex(card._combo_frame.findData("image"))
    card._combo_frame.activated.emit(card._combo_frame.currentIndex())
    assert project.settings.web_frame == "image"
    assert not frame_row.isHidden()
    panel.close()


def test_une_image_hors_du_projet_est_copiee_sans_ecraser(qapp, tmp_path):
    project = _project(tmp_path)
    panel = BuildPanel(project)
    first = tmp_path / "a" / "fond.png"
    second = tmp_path / "b" / "fond.png"
    for path, data in ((first, b"1"), (second, b"2")):
        path.parent.mkdir()
        path.write_bytes(data)
    assert panel._web._import_image(first) == "web_theme/fond.png"
    assert panel._web._import_image(first) == "web_theme/fond.png"
    assert panel._web._import_image(second) == "web_theme/fond_2.png"
    assert (project.root / "web_theme" / "fond.png").read_bytes() == b"1"
    panel.close()


def test_une_couleur_se_tape_ou_se_choisit_sans_fenetre(qapp, tmp_path):
    from PyQt6.QtCore import QPointF
    project = _project(tmp_path)
    panel = BuildPanel(project)
    field = panel._web._color_fields["web_player_color"]
    field._open()
    hex_field = field._popup._hex
    assert hex_field.text() == "#171717"

    hex_field.setText("AABBCC")
    hex_field.editingFinished.emit()
    assert project.settings.web_player_color == "#aabbcc"

    commits = []
    field.committed.connect(commits.append)
    square = field._popup._square
    square._pick(QPointF(square.width(), 0))      # saturation et valeur maximales
    assert len(commits) == 0                       # aperçu seulement pendant le glissé
    square.released.emit()
    assert len(commits) == 1
    assert project.settings.web_player_color == commits[0] != "#aabbcc"
    field._popup.close()
    panel.close()
