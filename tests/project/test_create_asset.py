"""*Create asset* : un asset naît du geste de l'auteur, à côté de sa source, qu'il POINTE sans la posséder."""
import wave
from pathlib import Path

import pytest
from PIL import Image

from core import asset_creation
from core.history import CommandHistory, CreateAssetCmd, DeleteResourceCmd
from core.models.palette import PaletteBank
from core.project import Project


def _wav(path: Path, bits: int = 8) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(bits // 8)
        out.setframerate(8000)
        out.writeframes(bytes(800 * bits // 8))
    return path


def _png(path: Path, size=(16, 16), colour=(200, 30, 30)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)
    return path


def _sheet(path: Path, cols=16, rows=14, cell=8) -> Path:
    img = Image.new("RGB", (cols * cell, rows * cell), (0, 0, 0))
    for y in range(rows):
        for x in range(cols):
            img.putpixel((x * cell + 1, y * cell + 1), (255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "Jeu", "Jeu")
    p = Project.open(p.root)
    p.load_all_resources()
    return p


def test_each_source_format_offers_the_types_it_can_become_most_common_first(tmp_path: Path):
    assert asset_creation.candidate_families("a.png") == ("sprites", "backgrounds", "fonts")
    assert asset_creation.candidate_families("a.WAV") == ("sfx", "music", "jingles")
    assert asset_creation.candidate_families("a.mod") == ("music", "jingles")
    assert asset_creation.candidate_families("a.ttf") == ("fonts",)
    assert asset_creation.candidate_families("a.hex") == ("palettes",)
    assert asset_creation.candidate_families("a.txt") == ()


def test_a_file_dropped_under_assets_is_not_an_asset_until_the_author_creates_it(tmp_path: Path):
    p = _project(tmp_path)
    _png(p.sprites_dir / "hero.png")
    _wav(p.sfx_dir / "boom.wav")
    _png(p.backgrounds_dir / "sky.png")

    reopened = Project.open(p.root)
    reopened.load_all_resources()

    assert not list(reopened.sprites) and not list(reopened.sfx) and not list(reopened.backgrounds)
    assert not list(p.sprites_dir.glob("*.sprite"))                                # aucun sidecar n'a été écrit non plus


@pytest.mark.parametrize("family,builder,expected", [
    ("sprites", lambda p, d: _png(d / "hero.png"), "hero.sprite"),
    ("backgrounds", lambda p, d: _png(d / "sky.png", (32, 32)), "sky.background"),
    ("sfx", lambda p, d: _wav(d / "boom.wav"), "boom.sfx"),
    ("music", lambda p, d: _wav(d / "theme.wav"), "theme.music"),
    ("jingles", lambda p, d: _wav(d / "win.wav"), "win.jingle"),
    ("fonts", lambda p, d: _sheet(d / "chunky.png"), "chunky.font"),
])
def test_an_asset_is_created_next_to_its_source_and_points_at_it(tmp_path: Path, family, builder, expected):
    p = _project(tmp_path)
    folder = p.assets_dir / "Anywhere" / "Deep"                                   # n'importe où : pas le dossier de la famille
    folder.mkdir(parents=True)
    source = builder(p, folder)
    before = source.read_bytes()

    result = asset_creation.create_from_source(p, family, source)

    assert result.error is None and (folder / expected).is_file()
    assert result.item.asset == p.asset_rel(source)                                # le chemin explicite, rien d'implicite
    assert source.read_bytes() == before                                           # la source n'est jamais modifiée
    reopened = Project.open(p.root)
    reopened.load_all_resources()
    assert getattr(reopened, family).get(result.item.name).asset == p.asset_rel(source)


def test_a_palette_is_created_from_a_hex(tmp_path: Path):
    p = _project(tmp_path)
    hexfile = p.assets_dir / "Colours" / "dusk.hex"
    hexfile.parent.mkdir()
    hexfile.write_text("#000000\n#ff8800\n", encoding="utf-8")

    result = asset_creation.create_from_source(p, "palettes", hexfile)

    assert result.error is None and len(result.item.colors) == 2
    assert result.item.asset == "assets/Colours/dusk.hex" and (hexfile.parent / "dusk.palette").is_file()


def test_the_name_comes_from_the_file_and_is_made_unique_in_its_type(tmp_path: Path):
    p = _project(tmp_path)
    one = _wav(p.assets_dir / "a" / "coin.wav")
    two = _wav(p.assets_dir / "b" / "coin.wav")
    other_type = _wav(p.assets_dir / "c" / "coin.wav")

    first = asset_creation.create_from_source(p, "sfx", one)
    second = asset_creation.create_from_source(p, "sfx", two)
    music = asset_creation.create_from_source(p, "music", other_type)

    assert (first.item.name, second.item.name) == ("coin", "coin_2")
    assert music.item.name == "coin"                                               # un autre type : pas de conflit
    assert asset_creation.asset_name(p, "sfx", one) == "coin_3"                    # le nom que le bouton annoncerait


def test_nothing_is_created_for_a_file_that_does_not_fit(tmp_path: Path):
    p = _project(tmp_path)
    png = _png(p.assets_dir / "x" / "hero.png")
    notes = p.assets_dir / "x" / "notes.txt"
    notes.write_text("hi", encoding="utf-8")
    broken = p.assets_dir / "x" / "deep.wav"
    broken.write_bytes(b"not a wav")                                               # ni PCM ni lisible
    asset_creation.create_from_source(p, "sprites", png)

    assert asset_creation.create_from_source(p, "sprites", notes).error
    assert asset_creation.create_from_source(p, "sfx", png).error                  # un PNG ne devient pas un effet
    refused = asset_creation.create_from_source(p, "sfx", broken)
    assert refused.error and "not recognised" in refused.error and not list(p.sfx)
    assert asset_creation.can_create_from(p, broken)


def test_deleting_an_asset_never_deletes_its_source(tmp_path: Path):
    p = _project(tmp_path)
    source = _png(p.assets_dir / "Art" / "hero.png")
    sprite = asset_creation.create_from_source(p, "sprites", source).item

    p.sprites.soft_delete(sprite)
    p.commit_all_removals()

    assert source.is_file()                                                        # la source reste
    assert not (source.parent / "hero.sprite").exists()                            # l'asset est bien parti
    reopened = Project.open(p.root)
    reopened.load_all_resources()
    assert not list(reopened.sprites)                                              # et rien ne le ressuscite
    assert asset_creation.can_create_from(reopened, source)                        # la source est de nouveau libre


def test_creating_is_undoable_and_redoable_and_never_touches_the_source(tmp_path: Path):
    p = _project(tmp_path)
    source = _wav(p.assets_dir / "Sounds" / "boom.wav")
    creation = asset_creation.build_from_source(p, "sfx", source)
    assert creation.error is None and not list(p.sfx)                              # construit, pas encore rangé
    history = CommandHistory()

    history.push(CreateAssetCmd(creation.store, creation.item, creation.folder))
    assert [s.name for s in p.sfx] == ["boom"] and (source.parent / "boom.sfx").is_file()

    history.undo()
    assert not list(p.sfx) and source.is_file()                                    # annulé : l'asset part, pas la source

    history.redo()
    assert [s.name for s in p.sfx] == ["boom"]
    assert p.sfx.path_of(p.sfx.get("boom")) == source.parent / "boom.sfx"          # refait : au même endroit


def test_deleting_is_undoable_and_the_asset_comes_back_where_it_was(tmp_path: Path):
    p = _project(tmp_path)
    source = _png(p.assets_dir / "Art" / "hero.png")
    sprite = asset_creation.create_from_source(p, "sprites", source).item
    history = CommandHistory()

    history.push(DeleteResourceCmd(p.sprites, sprite))
    assert not list(p.sprites) and source.is_file()

    history.undo()
    assert [s.name for s in p.sprites] == ["hero"]
    assert (source.parent / "hero.sprite").is_file()


def test_a_blank_asset_is_created_in_the_folder_it_is_given_and_undone_with_its_file(tmp_path: Path):
    from core.models.scene import Prefab
    p = _project(tmp_path)
    folder = p.assets_dir / "Enemies"
    folder.mkdir()
    prefab = Prefab(name="Crate")
    history = CommandHistory()

    history.push(CreateAssetCmd(p.prefabs, prefab, folder))
    assert (folder / "Crate.prefab").is_file()

    history.undo()
    p.commit_all_removals()
    assert not (folder / "Crate.prefab").exists() and p.prefabs.get("Crate") is None


def test_a_blank_palette_gets_its_hex_next_to_its_palette_file(tmp_path: Path):
    p = _project(tmp_path)
    folder = p.assets_dir / "Colours"
    folder.mkdir()
    bank = PaletteBank(name="Fresh", colors=[0, 0x1234])

    asset_creation.store_asset(p.palettes, bank, folder)

    assert (folder / "Fresh.palette").is_file()
    assert p.palettes.hex_path(bank).is_file()


def test_one_source_can_give_several_assets_of_the_same_or_of_other_types(tmp_path: Path):
    p = _project(tmp_path)
    source = _png(p.assets_dir / "Art" / "hero.png")

    first = asset_creation.create_from_source(p, "sprites", source)
    second = asset_creation.create_from_source(p, "sprites", source)                 # un second sprite, découpé autrement
    background = asset_creation.create_from_source(p, "backgrounds", source)         # et un fond tiré de la même image

    assert [r.error for r in (first, second, background)] == [None, None, None]
    assert [s.name for s in p.sprites] == ["hero", "hero_2"] and [b.name for b in p.backgrounds] == ["hero"]
    assert {first.item.asset, second.item.asset, background.item.asset} == {"assets/Art/hero.png"}
    assert asset_creation.can_create_from(p, source)                                  # et on peut continuer
    assert asset_creation.asset_name(p, "sprites", source) == "hero_3"                # le bouton annonce le nom définitif
    reopened = Project.open(p.root)
    reopened.load_all_resources()
    assert [s.name for s in reopened.sprites] == ["hero", "hero_2"] and len(list(reopened.backgrounds)) == 1


def test_a_source_with_assets_is_listed_with_all_of_them_in_the_disk_tree(tmp_path: Path):
    from core import disk_tree
    p = _project(tmp_path)
    source = _png(p.assets_dir / "Art" / "hero.png")
    asset_creation.create_from_source(p, "sprites", source)
    asset_creation.create_from_source(p, "backgrounds", source)

    node = next(n for n in disk_tree.build_disk_tree(p).walk() if n.path == source)

    assert node.kind == disk_tree.LINKED_SOURCE and node.owner == "hero, hero"        # un sprite et un fond, tous deux nommés


def test_retouching_a_shared_source_re_encodes_every_asset_that_points_at_it(tmp_path: Path):
    from core.resources import asset_reconciliation
    p = _project(tmp_path)
    source = _png(p.assets_dir / "Art" / "hero.png", colour=(200, 30, 30))
    first = asset_creation.create_from_source(p, "sprites", source).item
    second = asset_creation.create_from_source(p, "sprites", source).item
    before = (list(first.palettes), list(second.palettes))
    Image.new("RGB", (16, 16), (30, 30, 200)).save(source)                           # retouchée hors de l'éditeur

    asset_reconciliation.resync_sprite_png(p, source)

    assert first.palettes != before[0] and second.palettes != before[1]               # les DEUX suivent, pas seulement le premier


def test_a_palette_is_the_one_exception_its_colours_live_in_the_hex(tmp_path: Path):
    p = _project(tmp_path)
    hexfile = p.assets_dir / "Colours" / "dusk.hex"
    hexfile.parent.mkdir()
    hexfile.write_text("#000000\n#ff8800\n", encoding="utf-8")
    assert asset_creation.create_from_source(p, "palettes", hexfile).error is None

    count = len(list(p.palettes))
    again = asset_creation.create_from_source(p, "palettes", hexfile)

    assert again.error and "colours" in again.error and len(list(p.palettes)) == count
    assert not asset_creation.can_create_from(p, hexfile)                             # rien d'autre à en tirer
    assert asset_creation.families_for(p, hexfile) == ()
