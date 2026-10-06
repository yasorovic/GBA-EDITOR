"""Le MÊME petit morceau, écrit dans les quatre formats de module.

Aucun `.xm`, `.it` ni `.s3m` n'existe dans le dépôt, et un lecteur qu'on ne
fait jamais lire ne prouve rien. Ces quatre fonctions écrivent donc un fichier
minimal mais VALIDE par format, portant exactement la même musique :

    un échantillon — une onde carrée de 32 points BOUCLÉE, base 8363 Hz ;
    un pattern de 4 lignes, une note C-5 sur le premier canal, ligne 0 ;
    vitesse 6, tempo 125.

Ce que ça permet de vérifier n'est pas « le lecteur lit son propre format »
(il lirait n'importe quoi de la même façon), mais que **les quatre lecteurs
tombent d'accord** : même durée, même hauteur, même nombre de canaux. Un
décalage d'octave dans la table de notes d'un format se voit alors tout de
suite, puisque les trois autres ne l'ont pas.

Ce qu'elles ne remplacent pas : un vrai module écrit par un tracker, avec ses
enveloppes et ses effets. Les fixtures valident la STRUCTURE et la hauteur,
pas la fidélité musicale d'un morceau réel.
"""

from __future__ import annotations

import struct

# L'onde carrée : 16 points hauts, 16 bas. Assez courte pour tenir dans un
# fichier de test, assez longue pour que sa fréquence se mesure.
SQUARE_LEN = 32
SQUARE_I8 = bytes([100] * 16 + [(256 - 100)] * 16)   # int8 : +100 / −100

NOTE_C5 = 60          # la numérotation du modèle
ROWS = 4
SPEED = 6
BPM = 125


def _pad(buf: bytearray, alignment: int) -> None:
    while len(buf) % alignment:
        buf.append(0)


def make_mod() -> bytes:
    """ProTracker, 4 canaux, tag M.K."""
    b = bytearray()
    b += b"FIXTURE".ljust(20, b"\x00")
    for i in range(31):
        b += (b"square" if i == 0 else b"").ljust(22, b"\x00")
        if i == 0:
            b += struct.pack(">H", SQUARE_LEN // 2)   # longueur en MOTS
            b += bytes([0, 64])                        # finetune, volume
            # Bouclée sur toute sa longueur : sans ça l'onde s'éteint en 4 ms
            # et il n'y a plus de hauteur à mesurer.
            b += struct.pack(">HH", 0, SQUARE_LEN // 2)
        else:
            b += struct.pack(">H", 0) + bytes([0, 0]) + struct.pack(">HH", 0, 0)
    b += bytes([1, 0])              # longueur de morceau, restart
    b += bytes([0] * 128)           # table d'ordre — position 0 = pattern 0
    b += b"M.K."
    # Un pattern ProTracker fait TOUJOURS 64 lignes.
    for row in range(64):
        for ch in range(4):
            if row == 0 and ch == 0:
                period = 428        # C-5 dans la table ProTracker
                # Le numéro d'instrument est coupé en deux : quartet haut dans
                # le premier octet, quartet bas dans le troisième.
                b += bytes([(period >> 8) & 0x0F, period & 0xFF, 0x10, 0x00])
            else:
                b += bytes([0, 0, 0, 0])
    b += SQUARE_I8
    return bytes(b)


def make_s3m() -> bytes:
    """ScreamTracker 3, un canal actif."""
    header = bytearray(0x60)
    header[0:8] = b"FIXTURE\x00"
    header[0x1C] = 0x1A
    header[0x1D] = 16                    # type : module
    struct.pack_into("<HHH", header, 0x20, 1, 1, 1)      # ordres, instruments, patterns
    struct.pack_into("<HHH", header, 0x26, 0, 0x1320, 2)  # flags, cwtv, ffv (2 = non signé)
    header[0x2C:0x30] = b"SCRM"
    header[0x30] = 64                    # volume global
    header[0x31] = SPEED
    header[0x32] = BPM
    header[0x33] = 0x30                  # master volume, mono
    header[0x35] = 0                     # pas de table de panoramique
    header[0x40] = 0                     # canal 0 actif (gauche)
    for c in range(1, 32):
        header[0x40 + c] = 0xFF          # les autres, coupés

    b = bytearray(header)
    b += bytes([0])                      # table d'ordre : position 0
    ins_ptr_at = len(b); b += b"\x00\x00"
    pat_ptr_at = len(b); b += b"\x00\x00"

    _pad(b, 16)
    ins_at = len(b)
    ins = bytearray(0x50)
    ins[0] = 1                           # type : échantillon
    ins[0x1F] = 0x01                     # drapeaux : bouclé
    ins[0x30:0x34] = b"tone"
    ins[0x4C:0x50] = b"SCRS"
    b += ins

    _pad(b, 16)
    smp_at = len(b)
    # ST3 écrit ses échantillons NON signés.
    b += bytes([(v + 128) & 0xFF for v in
                [100] * 16 + [-100] * 16])

    _pad(b, 16)
    pat_at = len(b)
    body = bytearray()
    body += bytes([0x20 | 0x80 | 0])     # canal 0 : note+instrument, et commande
    body += bytes([(4 << 4) | 0, 1])     # C-4 en ST3 = notre C-5, instrument 1
    body += bytes([0, 0])                # commande vide
    body += bytes([0])                   # fin de ligne 0
    for _ in range(ROWS - 1):
        body += bytes([0])
    pat = struct.pack("<H", len(body)) + bytes(body)
    b += pat

    struct.pack_into("<H", b, ins_ptr_at, ins_at // 16)
    struct.pack_into("<H", b, pat_ptr_at, pat_at // 16)
    struct.pack_into("<I", b, ins_at + 0x10, SQUARE_LEN)          # longueur
    struct.pack_into("<II", b, ins_at + 0x14, 0, SQUARE_LEN)      # boucle
    struct.pack_into("<I", b, ins_at + 0x20, 8363)                # C2SPD
    b[ins_at + 0x1C] = 64                                          # volume
    b[ins_at + 0x0D] = (smp_at // 16) >> 16
    struct.pack_into("<H", b, ins_at + 0x0E, (smp_at // 16) & 0xFFFF)
    return bytes(b)


def make_xm(linear: bool = True) -> bytes:
    """FastTracker II, un canal, un instrument à un échantillon."""
    b = bytearray()
    b += b"Extended Module: "
    b += b"FIXTURE".ljust(20, b" ")
    b += bytes([0x1A])
    b += b"fixtures".ljust(20, b" ")
    b += struct.pack("<H", 0x0104)
    b += struct.pack("<I", 20 + 256)          # taille d'en-tête
    b += struct.pack("<HHHHHHHH", 1, 0, 1, 1, 1, 1 if linear else 0, SPEED, BPM)
    b += bytes([0] * 256)                     # table d'ordre : tout sur le pattern 0

    # ── Pattern ───────────────────────────────────────────────────
    packed = bytearray()
    # Ligne 0 : note + instrument, empaquetés.
    packed += bytes([0x80 | 0x01 | 0x02, NOTE_C5 - 11, 1])
    for _ in range(ROWS - 1):
        packed += bytes([0x80])               # une ligne vide = un octet
    b += struct.pack("<IBHH", 9, 0, ROWS, len(packed))
    b += packed

    # ── Instrument ────────────────────────────────────────────────
    inst = bytearray()
    inst += struct.pack("<I", 263)            # taille d'en-tête d'instrument
    inst += b"tone".ljust(22, b"\x00")
    inst += bytes([0])                        # type
    inst += struct.pack("<H", 1)              # un échantillon
    inst += struct.pack("<I", 40)             # taille d'un en-tête d'échantillon
    inst += bytes([0] * 96)                   # carte note → échantillon 0
    inst += bytes([0] * 48)                   # enveloppe de volume
    inst += bytes([0] * 48)                   # enveloppe de panoramique
    inst += bytes([0] * 10)                   # nombres de points, maintiens, boucles
    inst += bytes([0, 0])                     # types d'enveloppe : aucune
    inst += bytes([0, 0, 0, 0])               # vibrato d'instrument
    inst += struct.pack("<H", 0)              # fadeout
    inst += bytes([0] * (263 - len(inst)))
    b += inst

    # En-tête d'échantillon, puis les données EN DELTA.
    b += struct.pack("<III", SQUARE_LEN, 0, SQUARE_LEN)
    b += bytes([64])                          # volume
    b += bytes([0])                           # finetune
    b += bytes([1])                           # type : boucle avant, 8 bits
    b += bytes([128])                         # panoramique centré
    b += bytes([0])                           # note relative
    b += bytes([0])
    b += b"tone".ljust(22, b"\x00")

    values = [100] * 16 + [-100] * 16
    delta = bytearray()
    prev = 0
    for v in values:
        delta.append((v - prev) & 0xFF)
        prev = v
    b += delta
    return bytes(b)


def _compress_it8(values: list) -> bytes:
    """Compresse en IT214, un seul bloc, largeur fixe à 9 bits.

    C'est le cas le plus simple que le format autorise, et il suffit à
    éprouver le lecteur de bits : à largeur 9, un mot dont le bit 8 est à zéro
    porte un delta signé sur 8 bits, et le décodeur doit le retrouver tel quel.
    Les changements de largeur — la vraie compression — ne sont pas produits
    ici : les écrire demanderait un compresseur complet, alors qu'on cherche à
    vérifier un décodeur.
    """
    bits = []
    prev = 0
    for v in values:
        delta = (v - prev) & 0xFF
        prev = v
        for i in range(9):
            bits.append((delta >> i) & 1 if i < 8 else 0)
    out = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j, bit in enumerate(bits[i:i + 8]):
            byte |= bit << j
        out.append(byte)
    return struct.pack("<H", len(out)) + bytes(out)


def make_it(compressed: bool = False) -> bytes:
    """Impulse Tracker, un canal, sans couche d'instrument."""
    b = bytearray(0xC0)
    b[0:4] = b"IMPM"
    b[4:11] = b"FIXTURE"
    struct.pack_into("<HHHH", b, 0x20, 1, 0, 1, 1)     # ordres, instr, samples, patterns
    struct.pack_into("<HHHH", b, 0x28, 0x0214, 0x0214, 0x08, 0)   # cwtv, cmwt, flags(linéaire)
    b[0x30] = 128        # volume global
    b[0x31] = 48         # volume de mixage
    b[0x32] = SPEED
    b[0x33] = BPM
    for c in range(64):
        b[0x40 + c] = 32          # panoramique centré
        b[0x80 + c] = 64          # volume de canal

    b += bytes([0])               # table d'ordre
    smp_off_at = len(b); b += b"\x00" * 4
    pat_off_at = len(b); b += b"\x00" * 4

    smp_hdr_at = len(b)
    hdr = bytearray(0x50)
    hdr[0:4] = b"IMPS"
    hdr[0x11] = 64                # volume global de l'échantillon
    hdr[0x12] = 0x19 if compressed else 0x11   # présent, bouclé, (compressé)
    hdr[0x13] = 64                # volume
    hdr[0x14:0x18] = b"tone"
    hdr[0x2E] = 0x01              # converti : données SIGNÉES
    struct.pack_into("<IIII", hdr, 0x30, SQUARE_LEN, 0, SQUARE_LEN, 8363)
    b += hdr

    smp_data_at = len(b)
    values = [100] * 16 + [-100] * 16
    if compressed:
        b += _compress_it8(values)
    else:
        b += bytes([(v & 0xFF) for v in values])
    struct.pack_into("<I", b, smp_hdr_at + 0x48, smp_data_at)
    struct.pack_into("<I", b, smp_off_at, smp_hdr_at)

    pat_at = len(b)
    body = bytearray()
    body += bytes([0x81])                 # canal 0, un masque suit
    body += bytes([0x03])                 # note + instrument
    body += bytes([NOTE_C5, 1])
    body += bytes([0])                    # fin de ligne 0
    for _ in range(ROWS - 1):
        body += bytes([0])
    b += struct.pack("<HH", len(body), ROWS) + b"\x00" * 4 + bytes(body)
    struct.pack_into("<I", b, pat_off_at, pat_at)
    return bytes(b)
