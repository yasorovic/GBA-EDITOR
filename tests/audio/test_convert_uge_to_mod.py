"""`tools/convert_uge_to_mod.py` : un morceau hUGETracker devient un MOD que l'éditeur relit.

Le `.uge` de test est écrit ICI, champ par champ, d'après le manuel du format (« uge-format.md », v5) — pas
avec le lecteur de l'outil : un lecteur et un écrivain qui se trompent de la même façon ne se détecteraient pas.
On vérifie ensuite ce qui compte pour l'auteur : le fichier est un MOD valide, il dure ce que durait le morceau
(donc le tempo est juste), les notes tombent sur la bonne période, et les sources ne sont jamais touchées.
"""
from __future__ import annotations

import hashlib
import importlib.util
import struct
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))

from core.engine_emulation.module_model import load_module          # noqa: E402
from core.engine_emulation.module_render import GBA_MIX_RATE, render_module   # noqa: E402

_spec = importlib.util.spec_from_file_location("convert_uge_to_mod", REPO_DIR / "tools" / "convert_uge_to_mod.py")
tool = importlib.util.module_from_spec(_spec)
sys.modules["convert_uge_to_mod"] = tool            # un @dataclass relit son module par son nom
_spec.loader.exec_module(tool)


def _short(text: str = "") -> bytes:
    raw = text.encode("latin-1")
    return bytes([len(raw)]) + raw.ljust(255, b"\x00")


def _instrument(kind: int) -> bytes:
    """Un instrument v5, dans l'ordre exact du manuel."""
    out = struct.pack("<I", kind) + _short(f"instr {kind}") + struct.pack("<I", 0) + b"\x00"
    if kind == 0:                   # carré : volume 15, enveloppe -1/tick, rapport cyclique 50 %
        out += bytes([15]) + struct.pack("<I", 1) + bytes([1]) + struct.pack("<III", 0, 0, 0) + bytes([2])
        out += struct.pack("<II", 0, 0) + struct.pack("<I", 0) + struct.pack("<I", 0) + struct.pack("<I", 0)
    elif kind == 1:                 # onde : volume 100 %, onde 0
        out += b"\x00" + struct.pack("<I", 0) + b"\x00" + struct.pack("<III", 0, 0, 0) + b"\x00"
        out += struct.pack("<II", 1, 0) + struct.pack("<I", 0) + struct.pack("<I", 0) + struct.pack("<I", 0)
    else:                           # bruit : volume 15, enveloppe -2, 15 bits
        out += bytes([15]) + struct.pack("<I", 1) + bytes([2]) + struct.pack("<III", 0, 0, 0) + b"\x00"
        out += struct.pack("<II", 0, 0) + struct.pack("<I", 0) + struct.pack("<I", 0) + struct.pack("<I", 0)
    return out + bytes(6)            # v5 : six octets de plus par instrument


def _uge(rows_by_pattern: list, ticks: int = 6, orders=None) -> bytes:
    """`rows_by_pattern[i]` : {ligne: (note, instrument, effet, paramètre)} du pattern i."""
    out = struct.pack("<I", 5) + _short("Test song") + _short() + _short()
    for kind in (0, 1, 2):
        out += b"".join(_instrument(kind) for _ in range(15))
    out += bytes([(i * 3) % 16 for i in range(32)]) * 16
    out += struct.pack("<II", ticks, len(rows_by_pattern))
    for index, rows in enumerate(rows_by_pattern):
        out += struct.pack("<I", index)
        for row in range(64):
            note, instrument, effect, param = rows.get(row, (90, 0, 0, 0))
            out += struct.pack("<III", note, instrument, effect) + bytes([param])
    for channel in range(4):
        order = (orders or [[0]] * 4)[channel]
        out += struct.pack("<I", len(order) + 1) + b"".join(struct.pack("<I", o) for o in order) + struct.pack("<I", 0)
    return out + struct.pack("<I", 0) * 16      # les 16 routines, vides


@pytest.fixture
def song_bytes() -> bytes:
    # Un seul pattern, quatre canaux, qui joue une note sur chacun.
    return _uge([{0: (12, 1, 0, 0), 8: (24, 1, 0xB, 0)}])


def test_un_uge_devient_un_mod_que_l_editeur_relit(tmp_path, song_bytes):
    data, info = tool.convert(tool.parse_uge(song_bytes))
    assert data[1080:1084] == b"M.K."
    path = tmp_path / "t.mod"
    path.write_bytes(data)
    module = load_module(path)
    assert module.num_channels == 4 and info["orders"] == 2          # le pattern + l'amorce
    assert module.restart == 1                                       # reboucle sans rejouer l'amorce


def test_la_duree_du_morceau_est_conservee(tmp_path):
    """64 lignes à 6 ticks, un tick Game Boy = 1/59,7275 s : 6,43 s. C'est ce que l'amorce (149 BPM) garantit —
    sans elle un MOD joue à 125 BPM et le morceau dure 19 % de trop."""
    song = tool.parse_uge(_uge([{0: (12, 1, 0, 0)}], ticks=6))
    data, _info = tool.convert(song)
    path = tmp_path / "d.mod"
    path.write_bytes(data)
    seconds = len(render_module(load_module(path))) / GBA_MIX_RATE
    assert abs(seconds - 64 * 6 / 59.7275) < 0.15


def test_une_note_tombe_sur_la_bonne_periode(tmp_path):
    """La note 12 de hUGETracker sonne à 130,8 Hz ; sa moitié basse la joue 12 demi-tons au-dessus de C-1,
    c'est-à-dire sur C-2 (période 428)."""
    data, _info = tool.convert(tool.parse_uge(_uge([{0: (12, 1, 0, 0)}])))
    first_pattern = 1084
    amorce = 64 * 4 * 4
    cell = data[first_pattern + amorce:first_pattern + amorce + 4]
    assert (((cell[0] & 0x0F) << 8) | cell[1]) == 428
    assert ((cell[0] & 0xF0) | (cell[2] >> 4)) >= 1                  # un échantillon est désigné


def test_un_saut_de_position_suit_le_decalage_de_l_amorce(song_bytes):
    data, _info = tool.convert(tool.parse_uge(song_bytes))
    first_pattern = 1084
    jump = None
    for row in range(64):
        cell = data[first_pattern + 64 * 4 * 4 + row * 16: first_pattern + 64 * 4 * 4 + row * 16 + 4]
        if cell[2] & 0x0F == 0xB:
            jump = cell[3]
    assert jump == 1                                                  # B00 devient B01 : l'amorce occupe l'ordre 0


def test_une_version_inconnue_est_refusee():
    with pytest.raises(ValueError, match="version 3"):
        tool.parse_uge(struct.pack("<I", 3) + bytes(2000))


def test_la_ligne_de_commande_ecrit_a_cote_sans_toucher_aux_sources(tmp_path, song_bytes):
    source = tmp_path / "morceaux"
    source.mkdir()
    (source / "a.uge").write_bytes(song_bytes)
    before = hashlib.sha256((source / "a.uge").read_bytes()).hexdigest()
    assert tool.main([str(source)]) == 0
    assert (source / "mod" / "a.mod").is_file()
    assert hashlib.sha256((source / "a.uge").read_bytes()).hexdigest() == before
