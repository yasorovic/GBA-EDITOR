"""L'inspecteur Données montre ce que la cellule désigne, et laisse corriger le texte cité."""
import pytest
from PyQt6.QtGui import QImage, QColor

from core.history import CommandHistory
from core.models.data_table import DataColumn
from core.models.palette import PaletteBank
from core.models.sprite import SpriteAsset
from core.project import Project
from ui.data_editor import data_editor_screen
from ui.data_editor.data_editor_screen import DataEditorScreen


@pytest.fixture
def screen(qapp, tmp_path, monkeypatch):
    history = CommandHistory()
    monkeypatch.setattr(data_editor_screen, "get_history", lambda: history)
    monkeypatch.setattr(data_editor_screen, "schedule_unwatched", lambda _key, write: write())
    project = Project.create(tmp_path / "Game", "Game")
    widget = DataEditorScreen()
    widget.load_project(project)
    widget.resize(1200, 600)
    widget.show()
    qapp.processEvents()
    yield widget, project, history
    widget.close()


def _show(widget, project, column_type, value):
    widget._inspector.set_selection(DataColumn(name="cell", type=column_type), value)


def test_un_texte_se_relit_et_se_corrige_en_un_pas(screen, qapp):
    widget, project, history = screen
    entry = project.new_text(content="Hello", path=["Main", "01"])
    _show(widget, project, "text", entry.key)
    preview = widget._inspector._preview
    assert not preview._text.isHidden() and preview._text.toPlainText() == "Hello"

    preview._text.setPlainText("Bonjour")
    assert entry.content == "Hello"          # rien n'est écrit à la frappe
    _show(widget, project, "text", "")       # changer de sélection valide la correction
    assert entry.content == "Bonjour"
    history.undo()
    assert entry.content == "Hello"
    history.redo()
    assert entry.content == "Bonjour"


def test_une_correction_externe_est_relue(screen, qapp):
    widget, project, _history = screen
    entry = project.new_text(content="Hello", path=["Main", "01"])
    _show(widget, project, "text", entry.key)
    entry.content = "Changed elsewhere"
    widget.refresh_text()
    assert widget._inspector._preview._text.toPlainText() == "Changed elsewhere"


def test_une_palette_montre_ses_couleurs(screen):
    widget, project, _history = screen
    project.palettes.append(PaletteBank(name="Warm", colors=[0x001F, 0x03E0, 0x7C00, 0x7FFF]))
    _show(widget, project, "palette", "Warm")
    preview = widget._inspector._preview
    assert not preview._swatches.isHidden() and not preview._swatches.pixmap().isNull()


def test_un_sprite_montre_son_image(screen, tmp_path):
    widget, project, _history = screen
    image = QImage(32, 16, QImage.Format.Format_RGBA8888)
    image.fill(QColor("red"))
    path = project.root / "assets" / "hero.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(path))
    project.sprites.append(SpriteAsset(name="Hero", asset="assets/hero.png"))
    _show(widget, project, "sprite", "Hero")
    preview = widget._inspector._preview
    assert not preview._image.isHidden() and not preview._image.pixmap().isNull()
    assert "32" in preview._caption.text()


def test_rien_a_montrer_pour_un_entier_ou_une_cible_absente(screen):
    widget, project, _history = screen
    for column_type, value in (("int", 3), ("text", "unknown_key"), ("sprite", "Missing"), ("palette", "")):
        _show(widget, project, column_type, value)
        assert widget._inspector._preview.isHidden()


def test_le_champ_de_texte_grandit_avec_son_contenu(screen, qapp):
    widget, project, _history = screen
    entry = project.new_text(content="Short", path=["Main", "01"])
    _show(widget, project, "text", entry.key)
    field = widget._inspector._preview._text
    short = field.height()
    field.setPlainText("\n".join(f"line {n}" for n in range(6)))
    qapp.processEvents()
    assert field.height() > short
    field.setPlainText("\n".join(f"line {n}" for n in range(100)))
    qapp.processEvents()
    capped = field.height()
    field.setPlainText("\n".join(f"line {n}" for n in range(200)))
    qapp.processEvents()
    assert field.height() == capped
    field.setPlainText("x")
    qapp.processEvents()
    assert field.height() == short
