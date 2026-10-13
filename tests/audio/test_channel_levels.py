"""Le pic de chaque canal, tick par tick (`ChannelLevels`) : recueilli dans le MÊME parcours que le mix, sur la même
frise que lui, et sans rien changer à ce que le mix rend."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F                                            # noqa: E402
from core.engine_emulation.mod_file import parse_mod                   # noqa: E402
from core.engine_emulation.module_render import (                      # noqa: E402
    GBA_MIX_RATE, render_module_detailed, render_module_marked)
from core.engine_emulation.xm_file import parse_xm                     # noqa: E402


def _xm():
    return parse_xm(F.make_xm(orders=[0] * 4))


def test_le_detail_ne_change_pas_le_mix():
    mod = _xm()
    pcm, marks = render_module_marked(mod, GBA_MIX_RATE)
    detailed = render_module_detailed(mod, GBA_MIX_RATE)
    assert np.array_equal(detailed.pcm, pcm)
    assert detailed.marks == marks


def test_les_ticks_pavent_exactement_le_pcm():
    rendered = render_module_detailed(_xm(), GBA_MIX_RATE)
    starts = rendered.levels.starts
    assert starts[0] == 0
    assert np.all(np.diff(starts) > 0)
    assert starts[-1] < rendered.pcm.shape[0]
    assert rendered.levels.peaks.shape == (starts.size, _xm().num_channels)


def test_un_canal_qui_joue_a_un_pic_et_la_polyphonie_le_compte():
    levels = render_module_detailed(_xm(), GBA_MIX_RATE).levels
    assert float(levels.peaks.max()) > 0.0
    assert int(levels.active_counts().max()) == 1


def test_un_module_vide_n_a_pas_de_niveaux():
    mod = _xm()
    mod.order = []
    levels = render_module_detailed(mod, GBA_MIX_RATE).levels
    assert levels.peaks.shape[0] == 0 and levels.channel_count == max(1, mod.num_channels)


def test_un_module_a_quatre_canaux_a_quatre_colonnes():
    mod = parse_mod(F.make_mod())
    levels = render_module_detailed(mod, GBA_MIX_RATE).levels
    assert levels.channel_count == mod.num_channels == 4

