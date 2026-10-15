"""
core/module_trim.py — couper un MODULE tracker aux positions d'ordre.

Un jingle en module ne se rogne pas en millisecondes (cf. `core/wav_edit.py`, qui vaut pour les WAV) : sa plus petite
unité est l'ORDRE, une entrée de la table qui dit quel motif joue ensuite. `Jingle.order_start` / `order_end` disent
quelle plage de cette table le jingle joue (`end` exclu, 0 = jusqu'au bout) ; le fichier source n'est jamais réécrit.

Pourquoi au BUILD et pas à l'exécution : maxmod ne sait ni démarrer ni arrêter la couche jingle à une position
(`mmPosition` et `mmGetPosition` ne parlent qu'à la couche principale, lu dans `libmm.a` le 2026-10-14). On écrit donc le
module tel que la console le jouera, avec une table d'ordres plus courte, et l'aperçu lit CE MÊME module : une seule
fonction, `cut_orders`, pour le build et pour l'écoute.

Les positions sont celles de `Module.order` : la table BRUTE, marqueurs (« +++ » 254, « --- » 255) compris — celles que
`mmGetPosition()` rend et qu'une section d'une musique indexe.

Ce que la coupe ne fait pas : elle ne renumérote pas les SAUTS écrits dans les motifs (Bxx, « position jump »). Un jingle qui
saute à un ordre précis, une fois son début coupé, saute à côté. Un jingle court n'en a presque jamais.
"""
from __future__ import annotations

import struct

from core.engine_emulation.module_model import ORDER_END, detect_format

_MOD_LENGTH_AT, _MOD_TABLE_AT, _MOD_TABLE_SIZE, _MOD_TAG_AT = 950, 952, 128, 1080
_MOD_PATTERN_ROWS = 64
_XM_SONG_LENGTH_AT, _XM_RESTART_AT, _XM_TABLE_AT, _XM_TABLE_SIZE = 0x40, 0x42, 0x50, 256
_IT_TABLE_AT, _S3M_TABLE_AT, _ORDNUM_AT = 0xC0, 0x60, 0x20


def order_of(asset) -> tuple[int, int]:
    """`(début, fin)` en positions d'ordre, tels que l'asset les porte. Fin à 0 : jusqu'au bout de la table."""
    return max(0, int(getattr(asset, "order_start", 0) or 0)), max(0, int(getattr(asset, "order_end", 0) or 0))


def is_order_cut(asset) -> bool:
    start, end = order_of(asset)
    return start > 0 or end > 0


def order_window(asset, length: int) -> tuple[int, int]:
    """La plage jouée, bornée à la table : `(début, fin)` avec `fin` jamais à 0. Ce que l'écran dessine."""
    start, end = order_of(asset)
    end = length if end == 0 else min(end, length)
    return min(start, end), end


def order_problem(asset, length: int) -> str | None:
    """Pourquoi la plage ne tient pas dans une table de `length` entrées, ou None."""
    start, end = order_of(asset)
    if not is_order_cut(asset):
        return None
    if start >= length:
        return f"the order range starts at {start}, past the last order ({length - 1})"
    if end and end <= start:
        return f"the order range ends at {end}, before it starts at {start}"
    return None


def cut_orders(data: bytes, start: int, end: int) -> bytes:
    """Le module `data` dont la table d'ordres ne garde que les entrées `[start, end)` (`end` à 0 = jusqu'au bout).

    Lève `ValueError` pour un format inconnu, un module abîmé ou une plage qui ne garde rien."""
    kind = detect_format(data)
    cutter = _CUTTERS.get(kind)
    if cutter is None:
        raise ValueError("only a MOD, S3M, XM or IT module can be cut by orders")
    return cutter(data, max(0, int(start)), max(0, int(end)))


def _kept(table: list, start: int, end: int) -> list:
    stop = len(table) if end == 0 else min(end, len(table))
    kept = table[start:stop]
    if not kept:
        raise ValueError("the order range keeps nothing")
    return kept


def _cut_mod(data: bytes, start: int, end: int) -> bytes:
    """ProTracker : la longueur du morceau et 128 entrées, puis des motifs de taille fixe, puis les échantillons. Garder des
    entrées sans toucher aux motifs ferait lire le nombre de motifs autrement (le plus grand numéro de la table) et
    décalerait les échantillons : on réécrit donc aussi les motifs, ceux que la plage garde, renumérotés à partir de 0."""
    from core.engine_emulation.mod_file import parse_mod
    channels = parse_mod(data).num_channels
    length = data[_MOD_LENGTH_AT]
    table = list(data[_MOD_TABLE_AT:_MOD_TABLE_AT + _MOD_TABLE_SIZE])[:length]
    kept = _kept(table, start, end)

    sample_bytes = sum(struct.unpack(">H", data[20 + i * 30 + 22:20 + i * 30 + 24])[0] * 2 for i in range(31))
    pattern_size = _MOD_PATTERN_ROWS * channels * 4
    patterns_at = _MOD_TAG_AT + 4
    count, rest = divmod(len(data) - patterns_at - sample_bytes, pattern_size)
    if rest or count <= 0:                                     # un fichier à queue ou tronqué : la règle de ProTracker
        count = max(data[_MOD_TABLE_AT:_MOD_TABLE_AT + _MOD_TABLE_SIZE]) + 1
    if max(kept) >= count:
        raise ValueError("the order table points at a pattern the file does not hold")

    used: list = []
    for number in kept:
        if number not in used:
            used.append(number)
    chunks = [data[patterns_at + n * pattern_size:patterns_at + (n + 1) * pattern_size] for n in used]
    table_out = bytes(used.index(n) for n in kept) + bytes(_MOD_TABLE_SIZE - len(kept))
    tail = data[patterns_at + count * pattern_size:]
    return data[:_MOD_LENGTH_AT] + bytes([len(kept), 127]) + table_out + data[_MOD_TAG_AT:patterns_at] \
        + b"".join(chunks) + tail


def _cut_xm(data: bytes, start: int, end: int) -> bytes:
    """FastTracker : le nombre de motifs est écrit à part, la table peut donc simplement raccourcir."""
    length = struct.unpack_from("<H", data, _XM_SONG_LENGTH_AT)[0]
    kept = _kept(list(data[_XM_TABLE_AT:_XM_TABLE_AT + length]), start, end)
    out = bytearray(data)
    struct.pack_into("<HH", out, _XM_SONG_LENGTH_AT, len(kept), 0)          # longueur, puis restart au début
    out[_XM_TABLE_AT:_XM_TABLE_AT + _XM_TABLE_SIZE] = bytes(kept) + bytes(_XM_TABLE_SIZE - len(kept))
    return bytes(out)


def _cut_table_in_place(data: bytes, start: int, end: int, table_at: int) -> bytes:
    """Impulse Tracker et ScreamTracker : les tables qui suivent la table d'ordres sont des adresses ABSOLUES dans le fichier,
    donc sa taille ne bouge pas. Les entrées gardées d'abord, puis le marqueur de fin (255) jusqu'au bout de la place."""
    size = struct.unpack_from("<H", data, _ORDNUM_AT)[0]
    kept = _kept(list(data[table_at:table_at + size]), start, end)
    out = bytearray(data)
    out[table_at:table_at + size] = bytes(kept) + bytes([ORDER_END]) * (size - len(kept))
    return bytes(out)


_CUTTERS = {
    "mod": _cut_mod,
    "xm": _cut_xm,
    "it": lambda data, start, end: _cut_table_in_place(data, start, end, _IT_TABLE_AT),
    "s3m": lambda data, start, end: _cut_table_in_place(data, start, end, _S3M_TABLE_AT),
}
