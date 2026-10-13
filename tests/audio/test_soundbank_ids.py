"""Les constantes `SFX_*` / `MOD_*` viennent du nom de l'ASSET, jamais du nom du fichier source.

mmutil numérote par position et nomme d'après le fichier : le build vérifie la numérotation, puis réécrit les noms
(`MmutilAudio._number_ids`). Deux assets sur un même `.wav` — le cas de la duplication — ont donc chacun la leur.
"""
import os
import shutil
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from codegen.grit_conversion import MmutilAudio
from codegen.sfx_encode import encode_sfx_for_build
from core.models.audio import Music, Sfx


def _audio(emitted: list) -> MmutilAudio:
    return MmutilAudio(None, None, lambda kind, payload=None: emitted.append((kind, payload)), None)


def _assets(sfx=(), music=()):
    return {"sfx": [(Sfx(name=n), Path(f"{n}.wav")) for n in sfx], "music": [(Music(name=n), Path(f"{n}.xm")) for n in music]}


def _header(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "soundbank.h"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _errors(emitted) -> list:
    return [payload for kind, payload in emitted if kind == "diagnostic"]


def test_the_header_gets_the_names_of_the_assets_in_the_order_they_were_given(tmp_path: Path):
    emitted = []
    header = _header(tmp_path, ["#define SFX_COIN\t0", "#define SFX_COIN\t1", "#define SFX_BOOM\t2",
                                "#define MOD_THEME\t0", "#define MSL_NSONGS\t1", "#define MSL_NSAMPS\t3"])

    ok = _audio(emitted)._number_ids(header, _assets(sfx=["coin", "coin_2", "Boom Box"], music=["Level One"]))

    assert ok and not _errors(emitted)
    assert header.read_text(encoding="utf-8").splitlines() == [
        "#define SFX_COIN 0", "#define SFX_COIN_2 1", "#define SFX_BOOM_BOX 2",
        "#define MOD_LEVEL_ONE 0", "#define MSL_NSONGS\t1", "#define MSL_NSAMPS\t3"]     # les lignes MSL_* restent telles quelles


def test_renaming_twice_changes_nothing_so_a_cached_build_can_check_the_header_again(tmp_path: Path):
    header = _header(tmp_path, ["#define SFX_A\t0", "#define SFX_A\t1"])
    audio = _audio([])
    assets = _assets(sfx=["a", "a_2"])

    assert audio._number_ids(header, assets)
    once = header.read_text(encoding="utf-8")
    assert audio._number_ids(header, assets) and header.read_text(encoding="utf-8") == once


@pytest.mark.parametrize("lines,what", [
    (["#define SFX_A\t0"], "expected 0..1"),                                         # un effet de moins que prévu
    (["#define SFX_A\t1", "#define SFX_B\t0"], "numbered [1, 0]"),                   # l'ordre n'est pas celui qu'on a donné
    (["#define SFX_A\t0", "#define SFX_B\t1", "#define SFX_C\t2"], "expected 0..1"),   # un de plus
])
def test_a_numbering_that_is_not_the_one_expected_blocks_the_build(tmp_path: Path, lines, what):
    emitted = []
    header = _header(tmp_path, lines)
    before = header.read_text(encoding="utf-8")

    assert not _audio(emitted)._number_ids(header, _assets(sfx=["a", "b"]))

    assert any(what in str(payload) for payload in _errors(emitted))
    assert header.read_text(encoding="utf-8") == before                             # rien n'est réécrit sur un doute


def test_two_assets_that_would_share_a_c_name_block_the_build(tmp_path: Path):
    emitted = []
    header = _header(tmp_path, ["#define SFX_X\t0", "#define SFX_Y\t1"])

    assert not _audio(emitted)._number_ids(header, _assets(sfx=["coin 2", "coin_2"]))

    assert any("would all be called SFX_COIN_2" in str(payload) for payload in _errors(emitted))


def _mmutil():
    for candidate in (shutil.which("mmutil"), Path(os.environ.get("DEVKITPRO", "")) / "tools" / "bin" / "mmutil.exe",
                      Path("C:/devkitPro/tools/bin/mmutil.exe"), Path("/opt/devkitpro/tools/bin/mmutil")):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


@pytest.mark.skipif(_mmutil() is None, reason="mmutil absent")
def test_the_real_mmutil_header_is_renamed_for_two_assets_on_the_same_source(tmp_path: Path):
    """Le fait qui impose la réécriture : mmutil écrit `SFX_<nom du fichier>`. Deux assets sur un même `coin.wav` lui arrivent
    sous le MÊME nom de fichier et sortent numérotés 0 et 1 — c'est le rang qui les distingue, pas le nom."""
    src = tmp_path / "assets" / "coin.wav"
    src.parent.mkdir(parents=True)
    with wave.open(str(src), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(bytes(16000))
    project = SimpleNamespace(build_dir=tmp_path / "build", settings=SimpleNamespace(sfx_sample_rate=0))
    items = [(Sfx(name="coin"), src), (Sfx(name="coin_2", trim_end=500), src), (Sfx(name="coin_3"), src)]
    encoded = encode_sfx_for_build(project, items)
    project.build_dir.mkdir(exist_ok=True)

    subprocess.run([_mmutil(), *(str(encoded.get(sfx.name, path)) for sfx, path in items), "-osb.bin", "-hsb.h"],
                   cwd=project.build_dir, check=True, capture_output=True)
    header = project.build_dir / "sb.h"
    assert header.read_text().count("SFX_COIN\t") == 2                              # mmutil : deux fois le même nom (coin.wav)

    emitted = []
    assert _audio(emitted)._number_ids(header, {"sfx": items, "music": []}) and not _errors(emitted)

    text = header.read_text()
    assert "#define SFX_COIN 0" in text and "#define SFX_COIN_2 1" in text and "#define SFX_COIN_3 2" in text
