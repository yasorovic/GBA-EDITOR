from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement


ENGINE = Path(__file__).resolve().parents[2] / "runtime" / "include" / "gba_engine.h"


def _oam_update_code() -> str:
    text = ENGINE.read_text(encoding="utf-8")
    start = text.index("static OBJATTR g_oam_sorted")
    end = text.index("\n}\n", start) + 3
    return text[start:end]


def test_la_copie_oam_est_stablement_ordonnee_par_priorite_sans_deplacer_les_matrices(tmp_path):
    compiler = compilateur_hote()
    if compiler is None:
        pytest.skip("aucun compilateur C hôte (cc/gcc/clang, ou CC=...) ; la CI le joue")
    source = tmp_path / "oam_priority.c"
    source.write_text(
        r"""
#include <stdint.h>
#include <string.h>
typedef uint16_t u16;
typedef struct { u16 attr0, attr1, attr2, dummy; } OBJATTR;
static OBJATTR shadow_oam[128], hardware_oam[128];
#define OAM hardware_oam
#define COPY32 0
static void CpuFastSet(const void *src, void *dst, unsigned mode) {
    (void)mode; memcpy(dst, src, sizeof hardware_oam);
}
""" + _oam_update_code() + r"""
int main(void) {
    for (int i = 0; i < 128; i++) {
        shadow_oam[i].attr0 = 0x0200;
        shadow_oam[i].attr2 = 3 << 10;
        shadow_oam[i].dummy = 1000 + i;
    }
    int priority[4] = { 1, 0, 1, 0 };
    for (int i = 0; i < 4; i++) {
        shadow_oam[i].attr0 = 0;
        shadow_oam[i].attr1 = (i + 1) * 10;
        shadow_oam[i].attr2 = priority[i] << 10;
    }
    oam_update();
    int expected[4] = { 20, 40, 10, 30 };
    for (int i = 0; i < 4; i++) if (hardware_oam[i].attr1 != expected[i]) return 1;
    for (int i = 0; i < 128; i++) if (hardware_oam[i].dummy != 1000 + i) return 2;
    for (int i = 0; i < 4; i++) if (shadow_oam[i].attr1 != (i + 1) * 10) return 3;
    return 0;
}
""",
        encoding="utf-8",
    )
    binary = tmp_path / "oam_priority"
    env = environnement(compiler)
    built = subprocess.run([compiler, "-std=c11", "-O0", "-Wall", "-o", str(binary), str(source)],
                           capture_output=True, text=True, env=env)
    assert built.returncode == 0, built.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True, env=env)
    assert run.returncode == 0
