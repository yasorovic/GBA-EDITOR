"""
tools/frame_overrun_probe/instrument_main_c.py — compte les VBlanks RÉELS dans la ROM.

    python tools/frame_overrun_probe/instrument_main_c.py <projet>/build/src/main.c

Patche le `main.c` GÉNÉRÉ d'un projet déjà construit (jamais le générateur) :

  - un gestionnaire d'interruption VBlank incrémente `g_probe_vblanks` ;
  - chaque tour de la boucle principale écrit, dans le canal de log de mGBA,
        PROBE tick=<_g_frame> dv=<VBlanks écoulés depuis le tour précédent>
    que `analyze_probe_log.py` rapproche du `frame us=` du budget de frame.

Ensuite, recompiler SANS repasser par l'éditeur (qui régénérerait main.c) :

    cd <projet>/build
    make EXTRA_CFLAGS=-DGBA_DEBUG_BUILD

Le drapeau compte : sans lui, le `make` direct compile les fonctions de log en
stubs vides (c'est l'éditeur qui le pose, d'après `debug_build` du projet).

La sonde remplace le gestionnaire VBlank : ne l'utiliser que sur un projet SANS
musique (maxmod y installe le sien).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def instrument(source: str) -> str:
    def replace_once(text: str, old: str, new: str) -> str:
        if text.count(old) != 1:
            raise SystemExit(f"motif attendu une fois, trouvé {text.count(old)} fois : {old[:60]!r}")
        return text.replace(old, new, 1)

    source = source.replace("\r\n", "\n")
    source = replace_once(
        source,
        "int main(void){\n    irqInit(); irqEnable(IRQ_VBLANK);",
        "static volatile unsigned int g_probe_vblanks = 0;\n"
        "static void probe_vblank(void) { g_probe_vblanks++; }\n"
        "int main(void){\n    irqInit(); irqEnable(IRQ_VBLANK);\n"
        "    irqSet(IRQ_VBLANK, probe_vblank);   /* SONDE : compte les VBlanks reels */")
    return replace_once(
        source,
        "        _g_frame++;\n",
        "        _g_frame++;\n"
        "        { static unsigned last_vb = 0; unsigned vb = g_probe_vblanks;   /* SONDE */\n"
        "          debug_write_str(\"PROBE tick=\"); debug_write_int((int)_g_frame);\n"
        "          debug_write_str(\" dv=\"); debug_write_int((int)(vb - last_vb));\n"
        "          debug_flush(); last_vb = vb; }\n")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    original = path.read_text(encoding="utf-8")
    if "g_probe_vblanks" in original:
        print("déjà instrumenté")
        return 0
    shutil.copyfile(path, path.with_suffix(".c.orig"))
    path.write_text(instrument(original), encoding="utf-8", newline="\n")
    print(f"{path} instrumenté (copie : {path.with_suffix('.c.orig').name})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
