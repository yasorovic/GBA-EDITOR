"""Le point de contrôle d'un rendu de module (`render_module_detailed(..., checkpoint=)`) : il laisse un appelant
abandonner le rendu en route, sans rien changer à ce que le rendu produit."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F                                            # noqa: E402
from core.engine_emulation.module_render import (                      # noqa: E402
    GBA_MIX_RATE, RenderCancelled, render_module_detailed)
from core.engine_emulation.xm_file import parse_xm                     # noqa: E402


def _xm():
    return parse_xm(F.make_xm(orders=[0] * 4))      # 96 ticks : trois passages du point de contrôle


def test_le_point_de_controle_ne_change_pas_le_rendu():
    reference = render_module_detailed(_xm(), GBA_MIX_RATE)
    calls = []
    watched = render_module_detailed(_xm(), GBA_MIX_RATE, checkpoint=lambda: calls.append(1))
    assert np.array_equal(watched.pcm, reference.pcm)
    assert watched.marks == reference.marks
    assert len(calls) == 3


def test_lever_render_cancelled_abandonne_le_rendu():
    calls = []

    def checkpoint():
        calls.append(1)
        raise RenderCancelled

    with pytest.raises(RenderCancelled):
        render_module_detailed(_xm(), GBA_MIX_RATE, checkpoint=checkpoint)
    assert len(calls) == 1          # abandonné au premier passage : rien n'a continué après
