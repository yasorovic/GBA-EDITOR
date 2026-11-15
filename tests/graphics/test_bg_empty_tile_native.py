from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from codegen.bg_emit import emit_bg_c
from native_toolchain import compilateur_hote, environnement


ENGINE = Path(__file__).resolve().parents[2] / "runtime" / "include" / "gba_engine.h"


def _map_code() -> str:
    text = ENGINE.read_text(encoding="utf-8")
    start = text.index("static int bg_block_ofs")
    end = text.index("/* ── Fonds ANIMÉS", start)
    return text[start:end]


def test_l_emission_reserve_une_vraie_tuile_vide_en_4_et_8_bpp():
    for bpp, opaque, bytes_per_tile in ((4, "1" * 64, 32), (8, "01" * 64, 64)):
        source, header = emit_bg_c("Fond", [opaque], [0], bpp=bpp)
        assert "#define FondBlankTile 1" in header
        assert f"#define FondTilesLen {2 * bytes_per_tile}" in header
        words = re.search(r"FondTiles\[\d+\].*?\{(.*?)\};", source, re.S).group(1).split(",")
        assert all(int(word, 16) == 0 for word in words[-bytes_per_tile // 4:])


def test_chargement_et_streaming_emploient_l_entree_vide_emise(tmp_path):
    compiler = compilateur_hote()
    if compiler is None:
        pytest.skip("aucun compilateur C hôte (cc/gcc/clang, ou CC=...) ; la CI le joue")
    source = tmp_path / "bg_empty.c"
    source.write_text(
        """
#include <stdint.h>
#include <stdio.h>
typedef uint16_t u16; typedef volatile uint16_t vu16;
""" + _map_code() + r"""
int main(void) {
    u16 map[1] = { 0 }, vram[4096] = { 0 };
    load_map(vram, map, 1, 1, 32, 32, 7);
    if (vram[0] != 0 || vram[1] != 7 || vram[32] != 7) return 1;
    bg_stream_init(vram, map, 1, 1, 64, 64, 7);
    if (vram[0] != 0 || vram[1] != 7 || vram[0x400] != 7) return 2;
    bg_stream_update(vram, map, 1, 1, 64, 64, 1, 1, 8, 8, 7);
    for (int i = 0; i < 4096; i++) if (vram[i] != 0 && vram[i] != 7) return 3;
    puts("ok");
    return 0;
}
""",
        encoding="utf-8",
    )
    binary = tmp_path / "bg_empty"
    env = environnement(compiler)
    built = subprocess.run([compiler, "-std=c11", "-O0", "-Wall", "-o", str(binary), str(source)],
                           capture_output=True, text=True, env=env)
    assert built.returncode == 0, built.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True, env=env)
    assert run.returncode == 0 and run.stdout.strip() == "ok"
