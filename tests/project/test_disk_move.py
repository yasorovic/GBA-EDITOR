"""Déplacer un fichier ou un dossier de `assets/` : l'asset suit, rien n'est écrasé, le protégé ne bouge pas."""
import wave
from pathlib import Path

from PIL import Image

from asset_fixtures import create_all
from core import disk_move
from core.project import Project
from core.validator import validate_project


def _wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(bytes(800))


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "Jeu", "Jeu")
    Image.new("RGB", (16, 16), (200, 30, 30)).save(p.sprites_dir / "hero.png")
    _wav(p.sfx_dir / "boom.wav")
    Image.new("RGB", (32, 32), (10, 20, 30)).save(p.backgrounds_dir / "sky.png")
    p = Project.open(p.root)
    p.load_all_resources()
    create_all(p, ("sprites", p.sprites_dir / "hero.png"), ("sfx", p.sfx_dir / "boom.wav"),
               ("backgrounds", p.backgrounds_dir / "sky.png"))
    return p


def _reopen(root: Path) -> Project:
    p = Project.open(root)
    p.load_all_resources()
    return p


def _errors(p: Project) -> list[str]:
    return [str(m) for m in validate_project(p)[1]]


def _folder(p: Project, name: str) -> Path:
    folder = p.assets_dir / name
    folder.mkdir()
    return folder


def test_a_sidecar_moves_alone_and_the_asset_is_still_found(tmp_path: Path):
    p = _project(tmp_path)
    sidecar = p.sfx.path_of(p.sfx.get("boom"))
    target = _folder(p, "Audio")

    result = disk_move.move_to_folder(p, [sidecar], target)

    assert result.refused == [] and [new for _, new in result.moved] == [target.resolve() / "boom.sfx"]
    assert not sidecar.exists() and (target / "boom.sfx").is_file()
    assert (p.sfx_dir / "boom.wav").is_file()                                   # la source n'a pas bougé
    reopened = _reopen(p.root)
    assert reopened.sfx.get("boom").asset == "assets/sfx/boom.wav"
    assert not any("source file not found" in e for e in _errors(reopened))


def test_a_source_moves_and_its_asset_follows(tmp_path: Path):
    p = _project(tmp_path)
    boom = p.sfx.get("boom")
    identity = boom.id
    target = _folder(p, "Audio")

    result = disk_move.move_to_folder(p, [p.sfx_dir / "boom.wav"], target)

    assert result.refused == []
    assert boom.asset == "assets/Audio/boom.wav"
    reopened = _reopen(p.root)
    assert (reopened.sfx.get("boom").asset, reopened.sfx.get("boom").id) == ("assets/Audio/boom.wav", identity)
    assert not any("source file not found" in e for e in _errors(reopened))


def test_the_sidecar_stays_where_it_is_when_only_its_source_moves(tmp_path: Path):
    p = _project(tmp_path)
    sidecar = p.sfx.path_of(p.sfx.get("boom"))
    disk_move.move_to_folder(p, [p.sfx_dir / "boom.wav"], _folder(p, "Audio"))
    assert sidecar.is_file()                                                      # réécrit sur place, pas ramené ailleurs


def test_a_folder_moves_with_everything_in_it_and_every_path_is_rewritten(tmp_path: Path):
    p = _project(tmp_path)
    inner = p.assets_dir / "Pack" / "audio"
    inner.mkdir(parents=True)
    disk_move.move_to_folder(p, [p.sfx_dir / "boom.wav"], inner)                 # d'abord la source dans Pack/audio
    disk_move.move_to_folder(p, [p.sfx.path_of(p.sfx.get("boom"))], inner)
    target = _folder(p, "Archive")

    result = disk_move.move_to_folder(p, [p.assets_dir / "Pack"], target)

    assert result.refused == []
    assert p.sfx.get("boom").asset == "assets/Archive/Pack/audio/boom.wav"
    assert (target / "Pack" / "audio" / "boom.sfx").is_file() and not (p.assets_dir / "Pack").exists()
    reopened = _reopen(p.root)
    assert reopened.sfx.get("boom").asset == "assets/Archive/Pack/audio/boom.wav"
    assert not any("source file not found" in e for e in _errors(reopened))


def test_a_sprite_source_moves_and_is_not_re_encoded(tmp_path: Path):
    p = _project(tmp_path)
    hero = p.sprites.get("hero")
    palettes = list(hero.palettes)
    disk_move.move_to_folder(p, [p.sprites_dir / "hero.png"], _folder(p, "Art"))
    assert hero.asset == "assets/Art/hero.png" and list(hero.palettes) == palettes


def test_a_file_with_the_same_name_is_never_overwritten_and_blocks_only_that_move(tmp_path: Path):
    p = _project(tmp_path)
    target = _folder(p, "Audio")
    _wav(target / "boom.wav")                                                     # un homonyme est déjà là
    before = (target / "boom.wav").read_bytes()

    result = disk_move.move_to_folder(p, [p.sfx_dir / "boom.wav", p.sprites_dir / "hero.png"], target)

    assert result.refused == [((p.sfx_dir / "boom.wav").resolve(), disk_move.EXISTS)]
    assert (p.sfx_dir / "boom.wav").is_file() and (target / "boom.wav").read_bytes() == before
    assert (target / "hero.png").is_file()                                       # l'autre déplacement a eu lieu
    assert p.sfx.get("boom").asset == "assets/sfx/boom.wav"


def test_a_folder_cannot_be_moved_into_itself(tmp_path: Path):
    p = _project(tmp_path)
    outer = _folder(p, "Outer")
    inner = outer / "Inner"
    inner.mkdir()
    for destination in (outer, inner):
        result = disk_move.move_to_folder(p, [outer], destination)
        assert result.refused == [(outer.resolve(), disk_move.INTO_ITSELF)]
        assert outer.is_dir()


def test_dropping_into_the_folder_it_is_already_in_does_nothing_and_is_not_a_refusal(tmp_path: Path):
    p = _project(tmp_path)
    result = disk_move.move_to_folder(p, [p.sfx_dir / "boom.wav"], p.sfx_dir)
    assert result.moved == [] and result.refused == []


def test_nothing_leaves_assets_or_moves_assets_itself(tmp_path: Path):
    p = _project(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (tmp_path / "stray.wav").write_bytes(b"x")

    to_outside = disk_move.move_to_folder(p, [p.sfx_dir / "boom.wav"], outside)
    from_outside = disk_move.move_to_folder(p, [tmp_path / "stray.wav"], p.sfx_dir)
    root_itself = disk_move.move_to_folder(p, [p.assets_dir], p.sfx_dir)

    assert [reason for _, reason in to_outside.refused] == [disk_move.OUTSIDE]
    assert [reason for _, reason in from_outside.refused] == [disk_move.OUTSIDE]
    assert [reason for _, reason in root_itself.refused] == [disk_move.OUTSIDE]
    assert (p.sfx_dir / "boom.wav").is_file() and (tmp_path / "stray.wav").is_file()


def test_what_the_rest_of_the_code_looks_for_at_a_fixed_place_does_not_move(tmp_path: Path):
    p = _project(tmp_path)
    p.save()
    target = _folder(p, "Misc")

    for protected in (p.texts_file,):
        if not protected.exists():
            continue
        result = disk_move.move_to_folder(p, [protected], target)
        assert [reason for _, reason in result.refused] == [disk_move.PROTECTED], protected
        assert protected.exists()

    assert list(target.iterdir()) == []


def test_the_drag_question_is_answered_without_touching_anything(tmp_path: Path):
    p = _project(tmp_path)
    p.save()
    target = _folder(p, "Audio")
    before = sorted(x.relative_to(p.root).as_posix() for x in p.root.rglob("*"))

    movable = disk_move.drop_verdict(p, [p.sfx_dir / "boom.wav"], target)
    texts = disk_move.drop_verdict(p, [p.texts_file], target)
    nothing_to_do = disk_move.drop_verdict(p, [p.sfx_dir / "boom.wav"], p.sfx_dir)
    mixed = disk_move.drop_verdict(p, [p.texts_file, p.sfx_dir / "boom.wav"], target)

    assert movable == (True, None)
    assert texts == (False, (p.texts_file.resolve(), disk_move.PROTECTED))      # texts.json : on le dit dès le survol
    assert nothing_to_do == (False, None)                                      # déjà là : rien à faire, pas un refus
    assert mixed == (True, (p.texts_file.resolve(), disk_move.PROTECTED))      # un lot en partie déplaçable reste déposable
    assert sorted(x.relative_to(p.root).as_posix() for x in p.root.rglob("*")) == before


def test_a_background_image_moves_freely_and_its_asset_keeps_pointing_at_it(tmp_path: Path):
    p = _project(tmp_path)
    sky = p.backgrounds.get("sky")
    target = _folder(p, "Levels")

    result = disk_move.move_to_folder(p, [p.backgrounds_dir / "sky.png"], target)

    assert result.refused == []
    assert sky.asset == "assets/Levels/sky.png"
    assert p.background_image_path(sky) == (target / "sky.png").resolve()
    reopened = _reopen(p.root)
    assert reopened.backgrounds.get("sky").asset == "assets/Levels/sky.png"
    assert not any("source file not found" in e for e in _errors(reopened))


def test_renaming_a_background_does_not_rename_its_image(tmp_path: Path):
    p = _project(tmp_path)
    sky = p.backgrounds.get("sky")

    p.rename_background(sky, "heaven")

    assert (p.backgrounds_dir / "sky.png").is_file() and sky.asset == "assets/backgrounds/sky.png"
    assert not (p.backgrounds_dir / "heaven.png").exists()
    reopened = _reopen(p.root)
    assert [b.name for b in reopened.backgrounds] == ["heaven"]                  # pas de second fond né de l'ancien PNG
