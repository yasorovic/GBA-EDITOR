"""codegen/memory_timing.py — les temps d'accès de la ROM (`REG_WAITCNT`) que le jeu pose au démarrage.

Le moteur est compilé en Thumb et exécuté depuis la ROM : chaque lecture coûte des états d'attente (wait states). Un accès
« N » (non séquentiel, le premier) et un accès « S » (séquentiel, les suivants) ont chacun le leur ; le tampon de lecture
anticipée (prefetch) cache une partie de ce coût. Le BIOS laisse 4/2 sans prefetch ; les jeux du commerce posent 3/1 avec.
Passer de l'un à l'autre change la vitesse du jeu d'environ 2x : l'auteur doit tester dans le mode qu'il livre.

La SRAM de sauvegarde reste à 8 cycles, la valeur sûre pour la SRAM comme pour la Flash : elle n'est pas un réglage.
"""
from __future__ import annotations

# Valeurs permises par le registre. Les fenêtres WS0/WS1 n'ont pas les mêmes choix pour S.
FIRST_ACCESS = (4, 3, 2, 8)          # cycles au premier accès (WS0), dans l'ordre des codes 0 à 3
SECOND_ACCESS = (2, 1)               # cycles aux accès suivants (WS0), codes 0 et 1
_WS1_SECOND = (4, 1)

# Au-delà de cette taille la ROM déborde de la fenêtre WS0 (16 Mio) sur la fenêtre WS1.
WS0_WINDOW_MIB = 16

PRESETS = {
    "fast":       (3, 1, True),      # le réglage des jeux commerciaux
    "compatible": (4, 2, False),     # celui que laisse le BIOS
}
DEFAULT_PRESET = "fast"
CUSTOM = "custom"

SRAM_8_CYCLES = 0x0003
PREFETCH_BIT = 0x4000
# Les bits que le jeu écrit : SRAM, WS0, WS1 et prefetch. WS2 et les bits en lecture seule restent comme le BIOS les a laissés.
WRITE_MASK = 0x40FF


def preset_values(name: str) -> tuple[int, int, bool]:
    return PRESETS[name]


def preset_of(first: int, second: int, prefetch: bool) -> str:
    """Le nom du préréglage qui correspond aux trois valeurs, ou `custom`."""
    for name, values in PRESETS.items():
        if values == (first, second, bool(prefetch)):
            return name
    return CUSTOM


def second_choices(first: int) -> tuple[int, ...]:
    """Les accès suivants qu'on peut associer à ce premier accès : toujours plus rapides que lui (2 cycles ne se combine
    qu'avec 1)."""
    return tuple(s for s in SECOND_ACCESS if s < first)


def is_valid(first: int, second: int) -> bool:
    return first in FIRST_ACCESS and second in second_choices(first)


def normalised(first, second, prefetch) -> tuple[int, int, bool]:
    """Les trois valeurs ramenées dans ce que le registre accepte ; un projet abîmé retombe sur le préréglage par défaut."""
    try:
        first, second = int(first), int(second)
    except (TypeError, ValueError):
        return PRESETS[DEFAULT_PRESET]
    if not is_valid(first, second):
        return PRESETS[DEFAULT_PRESET]
    return first, second, bool(prefetch)


def waitcnt_value(first: int, second: int, prefetch: bool, cartridge_mib: int) -> int:
    """La valeur à écrire dans `REG_WAITCNT` (sous `WRITE_MASK`).

    Une ROM de plus de 16 Mio déborde de WS0 sur WS1 : WS1 reprend alors le réglage de WS0 (ou le plus proche en plus lent,
    WS1 n'offrant pas 2 cycles pour S), sinon la moitié haute de la cartouche tournerait à la vitesse du BIOS."""
    value = SRAM_8_CYCLES | (FIRST_ACCESS.index(first) << 2) | (SECOND_ACCESS.index(second) << 4)
    if cartridge_mib > WS0_WINDOW_MIB:
        ws1_second = second if second in _WS1_SECOND else _WS1_SECOND[0]
        value |= (FIRST_ACCESS.index(first) << 5) | (_WS1_SECOND.index(ws1_second) << 7)
    if prefetch:
        value |= PREFETCH_BIT
    return value
