"""Les quatre formats de module, et ce qui ne se verrait pas autrement.

L'aperçu du Sound Mixer ne sait pas échouer bruyamment : un lecteur qui se
trompe d'octave, qui rate la décompression ou qui lit une case de travers rend
un son — juste pas le bon. Et comme la ROM, elle, est construite par mmutil,
l'écart ne se voit qu'en comparant à l'oreille ce que l'éditeur joue et ce que
la console joue. C'est exactement la panne silencieuse que `tests/` existe pour
attraper (cf. ARCHITECTURE).

D'où la forme de ces tests : le MÊME morceau, écrit dans les quatre formats
(cf. module_fixtures.py), doit produire la MÊME musique. Un décalage d'octave
dans la table de notes d'un format ne se prouve pas contre lui-même — il se
prouve contre les trois autres.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F        # noqa: E402


def _parse(kind: str, data: bytes):
    from core.engine_emulation.mod_file import parse_mod
    from core.engine_emulation.s3m_file import parse_s3m
    from core.engine_emulation.xm_file import parse_xm
    from core.engine_emulation.it_file import parse_it
    return {"mod": parse_mod, "s3m": parse_s3m, "xm": parse_xm, "it": parse_it}[kind](data)


def _fundamental(audio) -> float:
    """La fréquence dominante du rendu, par transformée de Fourier."""
    from core.engine_emulation.module_render import GBA_MIX_RATE

    mono = audio[:, 0].astype(float) + audio[:, 1].astype(float)
    mono = mono[:8192]
    if not mono.any():
        return 0.0
    spectrum = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
    return float(np.argmax(spectrum) * GBA_MIX_RATE / len(mono))


ALL_KINDS = ("mod", "s3m", "xm", "it")


def _data(kind: str) -> bytes:
    return {"mod": F.make_mod, "s3m": F.make_s3m,
            "xm": F.make_xm, "it": F.make_it}[kind]()


# ── 1. Le format se reconnaît au CONTENU ──────────────────────────


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_le_format_se_reconnait_a_sa_signature(kind):
    """La v0.8.1 a mesuré que le tri par extension laisse passer un fichier
    renommé et refuse un fichier valide mal nommé. Le dispatch lit donc la
    signature — et un `.mod` qui n'en est pas un doit se faire refuser à
    l'import, seul endroit où quelque chose sait dire non (mmutil, lui, ne le
    dit jamais)."""
    from core.engine_emulation.module_model import detect_format

    assert detect_format(_data(kind)) == kind


def test_un_fichier_qui_nest_pas_un_module_est_refuse():
    from core.engine_emulation.module_model import detect_format

    assert detect_format(b"ceci n'est pas un module" * 100) is None


# ── 2. Les quatre lecteurs lisent le MÊME morceau ─────────────────


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_chaque_lecteur_retrouve_la_note_et_lechantillon(kind):
    mod = _parse(kind, _data(kind))
    assert mod.order == [0]
    assert mod.speed == F.SPEED and mod.bpm == F.BPM
    assert mod.patterns[0][0][0].note == F.NOTE_C5, "la note n'est pas un C-5"
    playable = [s for s in mod.samples if s.data.size]
    assert len(playable) == 1
    assert playable[0].data.size == F.SQUARE_LEN
    assert playable[0].loops, "l'onde carrée doit boucler"


def test_les_quatre_formats_sonnent_a_la_meme_hauteur():
    """Le test qui attrape un décalage d'octave, et le seul qui le puisse.

    Écart admis : les formats à période Amiga (MOD, S3M) portent le désaccord
    de l'horloge PAL — 8287 Hz au lieu de 8363 —, soit 0,9 %. Les formats
    linéaires (XM, IT) jouent le taux nominal. Un demi-ton, lui, ferait 6 %.
    """
    from core.engine_emulation.module_render import render_module

    pitches = {k: _fundamental(render_module(_parse(k, _data(k)))) for k in ALL_KINDS}
    assert all(p > 0 for p in pitches.values()), f"un format ne rend rien : {pitches}"
    low, high = min(pitches.values()), max(pitches.values())
    assert high / low < 1.02, f"les quatre formats ne s'accordent pas : {pitches}"
    # 8363 Hz / 32 points d'onde carrée ≈ 261 Hz.
    assert 250 < low < 270, f"hauteur absolue fausse : {pitches}"


def test_la_duree_suit_les_lignes_et_le_tempo():
    """Une ligne dure `speed` ticks, un tick `2,5 / bpm` seconde. Les patterns
    XM et IT font 4 lignes ; ceux du MOD en font toujours 64, et ceux de ST3
    aussi — c'est le format qui l'impose, pas la fixture."""
    from core.engine_emulation.module_render import render_module, GBA_MIX_RATE

    per_tick = round(GBA_MIX_RATE * 2.5 / F.BPM)
    attendu = {"mod": 64, "s3m": 64, "xm": F.ROWS, "it": F.ROWS}
    for kind, rows in attendu.items():
        audio = render_module(_parse(kind, _data(kind)))
        assert audio.shape[0] == rows * F.SPEED * per_tick, kind


# ── 3. La décompression d'Impulse Tracker ─────────────────────────


def test_un_echantillon_it_compresse_redonne_loriginal():
    """IT214 est le format d'échantillon par défaut d'Impulse Tracker et
    d'OpenMPT : sans décompression, la moitié des modules livrés par un
    compositeur seraient muets — et muets SANS message, puisque le fichier est
    par ailleurs valide."""
    clair = _parse("it", F.make_it(compressed=False)).samples[0].data
    compresse = _parse("it", F.make_it(compressed=True)).samples[0].data
    assert compresse.size == clair.size
    assert np.allclose(compresse, clair), "les deux lectures divergent"


def test_le_lecteur_de_bits_ne_deborde_pas_sur_des_donnees_absurdes():
    """Un fichier tronqué ou corrompu ne doit pas faire tomber l'éditeur : il
    doit rendre ce qu'il a pu lire. C'est la même règle que pour un `.mod`
    amputé, qui se complète en silence."""
    from core.engine_emulation.it_file import _decompress

    arr, _end = _decompress(b"\x04\x00\xff\xff\xff\xff", 0, 64, wide=False, it215=False)
    assert arr.size == 64


# ── 4. Ce que le rendu partage entre les formats ──────────────────


def test_le_panoramique_du_mod_reste_cable_a_gauche_et_a_droite():
    """ProTracker n'a pas d'effet de panoramique : ses canaux sont branchés
    0/3 à gauche, 1/2 à droite. La note de la fixture est sur le canal 0, donc
    tout doit sortir à gauche — si le rendu centrait par défaut, la moitié du
    signal partirait à droite sans que rien ne le dise."""
    from core.engine_emulation.module_render import render_module

    audio = render_module(_parse("mod", F.make_mod()))
    gauche = np.abs(audio[:, 0].astype(float)).sum()
    droite = np.abs(audio[:, 1].astype(float)).sum()
    assert gauche > 0 and droite == 0


def test_un_module_sans_echantillon_est_refuse_a_limport():
    """`check_audio_file` est le SEUL refus possible : mmutil construirait la
    ROM sans un mot (ROADMAP v0.8.1)."""
    import tempfile
    from core.resources.asset_reconciliation import check_audio_file

    vide = bytearray(F.make_it())
    # Effacer le drapeau « l'échantillon existe » : le module reste valide,
    # mais il ne porte plus rien à jouer.
    i = vide.index(b"IMPS")
    vide[i + 0x12] = 0x00
    path = Path(tempfile.mkdtemp()) / "muet.it"
    path.write_bytes(bytes(vide))
    assert "sample" in (check_audio_file(path) or "")
