"""Après un import par le « + », la ressource créée est sélectionnée, visible (section dépliée) et montrée à l'inspecteur."""
from __future__ import annotations

import wave

from PIL import Image
from PyQt6.QtWidgets import QFileDialog


def _project(tmp_path):
    from core.project import Project
    project = Project(tmp_path / "jeu")
    project.root.mkdir(parents=True, exist_ok=True)
    return project


def test_importer_un_sprite_le_selectionne_et_deplie_la_section(qapp, tmp_path, monkeypatch):
    from ui.common.asset_kinds import SPRITES
    from ui.sprite_editor.sprite_library_panel import SpriteLibraryPanel

    project = _project(tmp_path)
    source = tmp_path / "hero.png"
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(source)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(source)], ""))
    panel = SpriteLibraryPanel()
    panel.load_project(project)
    panel.show()
    panel._sprites._sections[SPRITES.label].set_expanded(False)
    chosen = []
    panel.sprite_selected.connect(chosen.append)

    panel._import_sprite()
    qapp.processEvents()

    hero = project.sprites.get("hero")
    assert hero is not None
    assert panel._sprites.current(SPRITES.label) is hero          # sélectionné dans la liste
    assert chosen and chosen[-1] is hero                           # l'inspecteur et le canvas reçoivent ce sprite
    assert panel._sprites._sections[SPRITES.label]._expanded       # et la liste est dépliée


def test_importer_un_son_par_le_plus_le_selectionne_et_deplie_la_section(qapp, tmp_path, monkeypatch):
    from ui.common.asset_kinds import SFX
    from ui.common.asset_library import AssetLibrary

    project = _project(tmp_path)
    source = tmp_path / "coin.wav"
    with wave.open(str(source), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(bytes(800))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(source)], ""))
    library = AssetLibrary("Library", [SFX])
    library.load_project(project)
    library.show()
    library._sections[SFX.label].set_expanded(False)
    heard = []
    library.selected.connect(lambda kind, obj: heard.append(obj))

    library._add_asset(SFX)
    qapp.processEvents()
    qapp.processEvents()

    coin = project.sfx.get("coin")
    assert coin is not None
    assert library.current(SFX.label) is coin
    assert heard and heard[-1] is coin
    assert library._sections[SFX.label]._expanded
