"""Assets manquants ou illisibles : le build le DIT, il ne livre pas un jeu amputé.

Chaque cas est un fichier supprimé ou abîmé sur le disque, projet fermé, puis
rouvert comme le ferait l'utilisateur. Les fichiers eux-mêmes ne doivent jamais
être détruits.
"""
from __future__ import annotations

import wave

from PIL import Image

from core.models.components import SpriteComponent
from core.models.scene import Actor
from core.project import Project
from core.validator import validate_project

BROKEN = "{ tronqu"


def _projet(tmp_path) -> Project:
    """Un projet avec un sprite cité par un acteur, et un effet sonore."""
    root = tmp_path / "Jeu"
    p = Project.create(root, "Jeu")
    Image.new("RGB", (16, 16), (200, 30, 30)).save(p.sprites_dir / "hero.png")
    with wave.open(str(p.sfx_dir / "boom.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(8000)
        w.writeframes(bytes(800))
    p = Project.open(root)
    p.load_all_resources()
    hero = Actor(name="Hero")
    hero.components.append(SpriteComponent(sprite_name="hero"))
    p.scenes[0].actors.append(hero)
    p.save()
    return p


def _rouvrir_et_valider(root):
    p = Project.open(root)
    warnings, errors = validate_project(p)
    return p, [str(m) for m in warnings], [str(m) for m in errors]


def test_acteur_qui_cite_un_sprite_disparu_est_un_avertissement(tmp_path):
    p = _projet(tmp_path)
    p.sprites.path_of(p.sprites.get("hero")).unlink()

    _, warnings, errors = _rouvrir_et_valider(p.root)

    assert any("Sprite 'hero' not found" in w for w in warnings)
    assert not any("hero" in e for e in errors)


def test_sprite_sans_nom_reste_un_simple_avertissement(tmp_path):
    p = _projet(tmp_path)
    p.scenes[0].actors[0].components[0].sprite_name = ""
    p.save()

    _, warnings, errors = _rouvrir_et_valider(p.root)

    assert any("no sprite_name" in w for w in warnings)
    assert not any("Sprite" in e for e in errors)


def test_sidecar_de_sprite_illisible_bloque_le_build_et_reste_intact(tmp_path):
    p = _projet(tmp_path)
    sidecar = p.sprites.path_of(p.sprites.get("hero"))
    sidecar.write_text(BROKEN, encoding="utf-8")

    _, _, errors = _rouvrir_et_valider(p.root)

    assert any("hero.json" in e and "unreadable" in e for e in errors)
    assert sidecar.read_text(encoding="utf-8") == BROKEN


def test_sidecar_audio_illisible_est_vu_malgre_le_chargement_differe(tmp_path):
    p = _projet(tmp_path)
    p.sfx.path_of(p.sfx.get("boom")).write_text(BROKEN, encoding="utf-8")

    reopened = Project.open(p.root)
    assert reopened.unreadable_files() == []         # différé : pas encore lu
    _, errors = validate_project(reopened)

    assert any("boom.json" in str(e) and "unreadable" in str(e) for e in errors)


def test_sidecar_de_palette_abime_garde_la_palette_et_une_copie(tmp_path):
    p = _projet(tmp_path)
    name = next(iter(p.palettes)).name
    sidecar = p.palettes._path(name)
    sidecar.write_text(BROKEN, encoding="utf-8")

    reopened, warnings, _ = _rouvrir_et_valider(p.root)

    assert reopened.palettes.get(name) is not None            # le .hex fait foi
    assert sidecar.with_name(sidecar.name + ".corrupt").read_text(encoding="utf-8") == BROKEN
    assert any(f"{name}.json" in w and ".corrupt" in w for w in warnings)


def test_hex_de_palette_illisible_est_signale_sans_etre_modifie(tmp_path):
    p = _projet(tmp_path)
    name = next(iter(p.palettes)).name
    source = p.palettes.source_path(name)
    source.write_text("pas une palette", encoding="utf-8")

    _, _, errors = _rouvrir_et_valider(p.root)

    assert any(f"{name}.hex" in e and "unreadable" in e for e in errors)
    assert source.read_text(encoding="utf-8") == "pas une palette"
