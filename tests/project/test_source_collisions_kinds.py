"""Une copie ne change de nom que pour un fichier de MÊME extension : `village.xm` côtoie `village.png`."""
from __future__ import annotations

from core import source_collisions


def test_un_autre_type_de_fichier_ne_prend_pas_le_nom(tmp_path):
    folder = tmp_path / "assets"
    folder.mkdir()
    (folder / "village.png").write_bytes(b"png")
    music = tmp_path / "village.xm"
    music.write_bytes(b"xm")

    assert source_collisions.destination(music, folder, overwrite=False) == folder / "village.xm"


def test_meme_extension_reste_suffixee_et_le_lot_compte(tmp_path):
    folder = tmp_path / "assets"
    folder.mkdir()
    (folder / "coin.wav").write_bytes(b"a")
    other = tmp_path / "x" / "coin.wav"
    other.parent.mkdir()
    other.write_bytes(b"b")

    first = source_collisions.destination(other, folder, overwrite=False)
    second = source_collisions.destination(other, folder, overwrite=False, taken_names={first.name})

    assert (first.name, second.name) == ("coin_2.wav", "coin_3.wav")
