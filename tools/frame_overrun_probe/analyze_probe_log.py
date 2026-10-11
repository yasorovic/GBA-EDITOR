"""
tools/frame_overrun_probe/analyze_probe_log.py — lit la sortie de mgba-sdl.

    mgba-sdl -l 8 rom.gba > log.txt          (fermer la fenêtre pour vider le tampon)
    python tools/frame_overrun_probe/analyze_probe_log.py log.txt

Rapproche, pour chaque tour N, le travail mesuré par le moteur (`frame us=`, ligne
du budget de frame) du nombre de VBlanks écoulés avant le tour N+1 (`dv=`, ligne
de la sonde, cf. instrument_main_c.py). La question : le jeu ralentit-il, saute-t-il
des tours, ou rattrape-t-il ?

  dv >= 2  le tour a duré plus d'une image : la logique n'avance pas pendant ce temps
  dv == 0  deux tours dans un même VBlank : un RATTRAPAGE (n'a jamais été observé)
"""
from __future__ import annotations

import collections
import math
import re
import sys
from pathlib import Path

FRAME_US = 16743          # 280 896 cycles / 16,78 MHz


def read_ticks(text: str) -> dict[int, list]:
    ticks: dict[int, list] = {}
    current = None
    for line in text.splitlines():
        m = re.search(r"PROBE tick=(\d+) dv=(\d+)", line)
        if m:
            current = int(m.group(1))
            ticks[current] = [int(m.group(2)), None]
            continue
        m = re.search(r"frame us=(\d+)", line)
        if m and current is not None and ticks[current][1] is None:
            ticks[current][1] = int(m.group(1))
    return ticks


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    ticks = read_ticks(Path(argv[1]).read_text(encoding="utf-8", errors="replace"))
    if not ticks:
        print("aucune ligne PROBE : ROM non instrumentée, ou drapeau -DGBA_DEBUG_BUILD absent")
        return 1
    order = sorted(ticks)
    rows = [(a, ticks[a][1], ticks[b][0]) for a, b in zip(order, order[1:]) if ticks[a][1] is not None]

    print(f"{len(order)} tours ; numéros consécutifs : {order == list(range(order[0], order[-1] + 1))}")
    hist = collections.Counter(dv for _, _, dv in rows)
    print("VBlanks entre deux tours :", dict(sorted(hist.items())))
    print(f"dv == 0 (rattrapage) : {hist.get(0, 0)} fois")

    exact = over = under = 0
    margins = []
    for _, us, dv in rows:
        predicted = max(1, math.ceil(us / FRAME_US))
        if dv == predicted:
            exact += 1
        elif dv > predicted:
            over += 1
            margins.append(predicted * FRAME_US - us)
        else:
            under += 1
    print(f"dv == ceil(travail / {FRAME_US} µs) : {exact} sur {len(rows)}")
    if margins:
        print(f"  {over} tours d'une image de plus, toujours à {min(margins)}–{max(margins)} µs sous "
              "une frontière (temps de boucle hors de la fenêtre chronométrée)")
    print(f"  {under} tours plus rapides que le travail ne le permet")

    print("\nTravail du tour N  ->  VBlanks avant le tour N+1")
    for tick, us, dv in rows[:: max(1, len(rows) // 18)]:
        print(f"  tour {tick:4d}   {us:6d} µs ({us / FRAME_US:4.2f} image)   ->   dv = {dv}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
