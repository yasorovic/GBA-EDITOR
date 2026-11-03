"""Les diagnostics de `codegen/grit_conversion.py` qu'aucun test ne déclenchait (la liste d'exemptions de la couverture : cf.
`tools/diagnostic_coverage_exemptions.json`) : fonds, sprites, planches indexées et audio.

Les outils (grit, mmutil, bin2s) ne tournent pas : on leur donne une commande factice, ou une erreur d'entrée, et on lit
ce que le journal en dit (cf. `test_codegen_diagnostics.py`)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from codegen import grit_conversion
from core.models.audio import Jingle, Music, Sfx
from core.models.background import BackgroundAsset, BackgroundLayer
from core.models.sprite import SpriteAsset
from core.project import Project


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


class Journal:
    """Ce que l'étape a émis : `emit` se passe en argument comme au vrai build."""

    def __init__(self):
        self.events: list[tuple[str, tuple]] = []

    def __call__(self, event, *args):
        self.events.append((event, args))

    def says(self, level: str, fragment: str) -> bool:
        return any(event == "diagnostic" and args[0].level == level and fragment in args[0].message
                   for event, args in self.events)


def _png(path: Path, mode: str = "RGB", size=(16, 16)) -> Path:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size).save(path)
    return path


def _command_succeeds(*_args, **_kwargs) -> bool:
    return True


# ── grit : fonds ──────────────────────────────────────────────────────────


def _background(project, png: bool = True):
    asset = BackgroundAsset(name="sky", asset="sky.png")
    layer = BackgroundLayer(background_name="sky", bg_slot=0)
    if png:
        _png(project.background_image_path(asset, "sky"))
    return asset, layer


def test_une_image_de_fond_absente_arrete_la_conversion(project):
    journal = Journal()
    asset, layer = _background(project, png=False)
    conversion = grit_conversion.GritBackground(Path("grit"), journal, _command_succeeds)
    assert conversion.run(project, [(asset, layer, None, None)]) is False
    assert journal.says("error", "image missing: sky")


def test_une_palette_que_la_quantification_refuse_arrete_la_conversion(project, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise ValueError("bank is too small")

    monkeypatch.setattr(grit_conversion, "quantize_asset", refuse)
    journal = Journal()
    asset, layer = _background(project)
    conversion = grit_conversion.GritBackground(Path("grit"), journal, _command_succeeds)
    assert conversion.run(project, [(asset, layer, [0x7FFF], 1)]) is False
    assert journal.says("error", "bank is too small")


# ── Planches de sprites indexées ──────────────────────────────────────────


def test_un_png_non_indexe_est_refuse_au_remplissage_et_a_la_planche(tmp_path):
    rgb = _png(tmp_path / "hero.png", mode="RGB")
    journal = Journal()
    assert grit_conversion.pad_sprite_png_indexed(rgb, 16, 16, tmp_path, journal) is None
    assert journal.says("error", "not an indexed PNG (mode 'RGB')")
    journal = Journal()
    assert grit_conversion.build_sprite_sheet_indexed(rgb, SpriteAsset(name="Hero"), tmp_path, journal) is None
    assert journal.says("error", "not an indexed PNG (mode 'RGB')")


def test_un_png_illisible_est_une_erreur_au_remplissage_et_a_la_planche(tmp_path):
    missing = tmp_path / "gone.png"
    journal = Journal()
    assert grit_conversion.pad_sprite_png_indexed(missing, 16, 16, tmp_path, journal) is None
    assert journal.says("error", "indexed padding error")
    journal = Journal()
    assert grit_conversion.build_sprite_sheet_indexed(missing, SpriteAsset(name="Hero"), tmp_path, journal) is None
    assert journal.says("error", "indexed reconstruction error")


# ── grit : sprites ────────────────────────────────────────────────────────


def test_grit_introuvable_arrete_la_conversion_des_sprites(project):
    journal = Journal()
    sprite = SpriteAsset(name="Hero", asset="assets/sprites/hero.png")
    conversion = grit_conversion.GritSprites(None, journal, _command_succeeds)
    assert conversion.run(project, [(None, sprite, None)]) is False
    assert journal.says("error", "not found")


def test_un_sprite_dont_le_png_manque_arrete_la_conversion(project):
    journal = Journal()
    sprite = SpriteAsset(name="Hero", asset="assets/sprites/gone.png")
    conversion = grit_conversion.GritSprites(Path("grit"), journal, _command_succeeds)
    assert conversion.run(project, [(None, sprite, None)]) is False
    assert journal.says("error", "asset missing: assets/sprites/gone.png")


def test_une_banque_que_la_quantification_refuse_arrete_la_conversion_du_sprite(project, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise ValueError("bank is too small")

    monkeypatch.setattr(grit_conversion, "quantize_asset", refuse)
    _png(project.root / "assets" / "sprites" / "hero.png", mode="RGBA")
    sprite = SpriteAsset(name="Hero", asset="assets/sprites/hero.png", frame_w=16, frame_h=16)
    journal = Journal()
    conversion = grit_conversion.GritSprites(Path("grit"), journal, _command_succeeds)
    assert conversion.run(project, [(None, sprite, [0x7FFF])]) is False
    assert journal.says("error", "bank is too small")


# ── mmutil, bin2s ─────────────────────────────────────────────────────────


def _audio(journal, mmutil="mmutil", bin2s="bin2s"):
    return grit_conversion.MmutilAudio(mmutil, bin2s, journal, _command_succeeds)


def _sounds(sfx=(), music=()) -> dict:
    return {"sfx": list(sfx), "music": list(music), "skipped": []}


def test_un_soundbank_illisible_est_une_erreur(tmp_path):
    journal = Journal()
    unreadable = tmp_path / "soundbank.h"
    unreadable.mkdir()                                       # un dossier : la lecture échoue
    assert _audio(journal)._number_ids(unreadable, _sounds()) is False
    assert journal.says("error", "soundbank.h unreadable")


def test_mmutil_introuvable_saute_l_audio_avec_un_avertissement(project):
    journal = Journal()
    assert _audio(journal, mmutil=None).run(project, _sounds()) is True
    assert journal.says("warning", "not found — audio skipped")


def test_un_reechantillonnage_qui_echoue_est_ignore_et_dit(project, monkeypatch):
    from codegen import sfx_encode

    def fail(*_args, **_kwargs):
        raise RuntimeError("no resampler")

    monkeypatch.setattr(sfx_encode, "encode_sfx_for_build", fail)
    journal = Journal()
    assert _audio(journal).run(project, _sounds()) is True
    assert journal.says("warning", "resampling ignored: no resampler")


def test_une_musique_wav_que_l_encodage_refuse_est_une_erreur(project, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise ValueError("the track is too long")

    monkeypatch.setattr(grit_conversion, "wav_cut", lambda _music: (None, None))
    monkeypatch.setattr(grit_conversion, "encode_music_for_build", refuse)
    journal = Journal()
    theme = (Music(name="Theme"), project.root / "assets" / "music" / "theme.wav")
    assert _audio(journal).run(project, _sounds(music=[theme])) is False
    assert journal.says("error", '"Theme": the track is too long')


def test_un_jingle_dont_la_coupe_echoue_est_une_erreur(project, monkeypatch):
    monkeypatch.setattr(grit_conversion, "is_order_cut", lambda _jingle: True)
    journal = Journal()
    fanfare = (Jingle(name="Fanfare"), project.root / "assets" / "jingles" / "gone.mod")    # le fichier n'existe pas
    assert _audio(journal).run(project, _sounds(music=[fanfare])) is False
    assert journal.says("error", '"Fanfare":')


def _built_soundbank(project, monkeypatch):
    """Un soundbank déjà produit : mmutil « réussit », le header est numéroté comme les effets, bin2s reste à lancer."""
    from codegen import sfx_encode
    monkeypatch.setattr(sfx_encode, "encode_sfx_for_build", lambda *_args, **_kwargs: {})
    project.build_dir.mkdir(parents=True, exist_ok=True)
    (project.build_dir / "soundbank.h").write_text("#define SFX_BOOM 0\n", encoding="utf-8")
    (project.build_dir / "soundbank.bin").write_bytes(b"\0")
    boom = project.build_dir / "boom.wav"
    boom.write_bytes(b"RIFF")
    return _sounds(sfx=[(Sfx(name="Boom"), boom)])


def test_bin2s_introuvable_est_un_avertissement(project, monkeypatch):
    sounds = _built_soundbank(project, monkeypatch)

    def missing_tool(*_args, **_kwargs):
        raise FileNotFoundError("bin2s.exe")

    monkeypatch.setattr(grit_conversion, "run_tool", missing_tool)
    journal = Journal()
    assert _audio(journal).run(project, sounds) is True
    assert journal.says("warning", "not found: bin2s.exe")


def test_sans_bin2s_le_soundbank_n_est_pas_lie_et_c_est_dit(project, monkeypatch):
    sounds = _built_soundbank(project, monkeypatch)
    journal = Journal()
    assert _audio(journal, bin2s=None).run(project, sounds) is True
    assert journal.says("warning", "not found — soundbank not linked")
