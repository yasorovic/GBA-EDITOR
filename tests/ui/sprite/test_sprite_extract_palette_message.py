"""« Extract from PNG » dit ce qu'il a fait : palette créée, mise à jour, ou pas d'image à lire."""
from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from core.models.scene import Scene  # noqa: F401  (charge les modèles dans le même ordre que l'éditeur)
from core.models.sprite import AnimState, SpriteAsset
from core.project import Project
from ui.sprite_editor import sprite_right_panel as module


def _panel(tmp_path, monkeypatch, with_image=True):
    project = Project(tmp_path / "jeu")
    project.root.mkdir(parents=True, exist_ok=True)
    image = project.root / "hero.png"
    if with_image:
        Image.new("RGB", (16, 16), (200, 30, 30)).save(image)
    sprite = SpriteAsset(name="Hero", asset="hero.png", states=[AnimState(name="Idle")])
    project.sprites.append(sprite)
    told = []
    saved = []
    monkeypatch.setattr(module, "get_dispatcher",
                        lambda: SimpleNamespace(status=told.append, save_palette=lambda bank: (
                            project.palettes.append(bank) if project.palettes.get(bank.name) is None else None,
                            saved.append(bank.name))))
    panel = module.SpriteRightPanel()
    panel._project, panel._sprite = project, sprite
    return panel, told, saved


def test_la_premiere_extraction_dit_que_la_palette_est_creee(qapp, tmp_path, monkeypatch):
    panel, told, saved = _panel(tmp_path, monkeypatch)

    panel._on_extract_palette()

    assert saved == ["pal_Hero"] and len(told) == 1 and "created" in told[0] and "pal_Hero" in told[0]


def test_la_seconde_extraction_dit_que_la_palette_est_mise_a_jour(qapp, tmp_path, monkeypatch):
    panel, told, saved = _panel(tmp_path, monkeypatch)
    panel._on_extract_palette()

    panel._on_extract_palette()

    assert "updated" in told[-1]


def test_sans_image_le_bouton_le_dit(qapp, tmp_path, monkeypatch):
    panel, told, saved = _panel(tmp_path, monkeypatch, with_image=False)

    panel._on_extract_palette()

    assert saved == [] and len(told) == 1
