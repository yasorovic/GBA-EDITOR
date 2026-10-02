"""
editor/scripting/globals.py — Génère globals.c + globals.h depuis la liste
des GlobalVar déclarées explicitement dans le projet.

Plus de détection automatique depuis les scripts : les variables globales
sont une ressource explicite du projet (project.globals).
"""

from __future__ import annotations
from pathlib import Path
from core.app_info import APP_NAME
import codegen.build_output as build_output


_C_TYPES = {
    "int":  "int",
    "bool": "bool",
    "u8":   "u8",
    "u16":  "u16",
    "s8":   "s8",
    "s16":  "s16",
}

# Ce qu'une case COÛTE EN SAUVEGARDE, en bits (ROADMAP v0.20). Rien à voir avec
# sa taille en mémoire vive, où chaque type garde son type C : un `bool` occupe
# un octet en RAM et un BIT en SRAM. C'est la définition même de « le paquetage
# est une décision d'émission » — l'auteur n'en entend jamais parler.
_SAVE_BITS = {"bool": 1, "u8": 8, "s8": 8, "u16": 16, "s16": 16, "int": 32}


def save_bits(g) -> int:
    return _SAVE_BITS.get(getattr(g, "type", "int"), 32)


def _count(g) -> int:
    """Le nombre de cases. 1 = scalaire, et c'est le cas de toute variable
    déclarée avant la v0.20."""
    return max(1, int(getattr(g, "count", 1) or 1))


def generate_globals_h(globals_) -> str:
    """globals_ : list[GlobalVar] (duck-typed: .name, .type)"""
    lines = [
        "/* globals.h — variables globales partagées entre les scripts acteur */",
        f"/* Généré par {APP_NAME} — ne pas éditer */",
        "",
        "#ifndef GLOBALS_H",
        "#define GLOBALS_H",
        "",
    ]
    if globals_:
        for g in globals_:
            c_type = _C_TYPES.get(g.type, "int")
            n = _count(g)
            # Un tableau reste un tableau C ORDINAIRE en mémoire vive : c'est
            # `global.coffres[i]` qui s'y indexe directement, au même prix qu'un
            # scalaire (ROADMAP v0.20). Le paquetage — huit booléens par octet —
            # ne concerne QUE la SRAM, et c'est l'émetteur de sauvegarde qui le
            # décide (cf. main_gen). Sans quoi on réintroduirait les opérateurs
            # binaires par la porte de la sauvegarde après les avoir refusés par
            # celle du langage.
            lines.append(f"extern {c_type} g_{g.name}"
                         + (f"[{n}];" if n > 1 else ";"))
        # ── Index ────────────────────────────────────────────────
        # Chaque variable garde SON type (un u8 coûte un octet) et reçoit en
        # plus un index stable. Les deux servent à deux choses distinctes : un
        # script écrit `g_score` et paie le prix d'un accès direct ; ce qui ne
        # connaît la variable que par une DONNÉE (valeur interpolée dans un
        # texte) passe par l'index, sans jamais avoir vu son nom.
        lines += ["", "/* Index — l'accès quand le nom n'est pas connu à l'écriture. */"]
        for i, g in enumerate(globals_):
            lines.append(f"#define GLOBAL_{g.name.upper()} {i}")
        lines.append(f"#define GLOBAL_COUNT {len(globals_)}")
    else:
        lines.append("/* aucune variable globale déclarée dans ce projet */")
        lines += ["", "#define GLOBAL_COUNT 0"]
    # Toujours déclarés, même sans variable : le moteur les appelle pour les
    # valeurs interpolées, et une déclaration manquante ne se verrait qu'à
    # l'édition de liens.
    lines += [
        "",
        "/* Lecture/écriture PAR INDEX. Un switch et non une table de pointeurs :",
        "   les variables n'ont pas toutes le même type, donc aucun tableau ne",
        "   peut les contenir sans mentir sur l'une d'elles. Le compilateur, lui,",
        "   sait convertir chaque cas. */",
        "extern int  global_read (int i);",
        "extern void global_write(int i, int v);",
        "/* Les mêmes, CASE PAR CASE (ROADMAP v0.20). Seuls la sauvegarde et",
        "   l'interpolation de texte en ont besoin : un script, lui, écrit",
        "   `global.coffres[i]`, que le codegen traduit en accès direct au",
        "   tableau C — au même prix qu'un scalaire. Sur un scalaire, `k` est",
        "   ignoré, ce qui fait de global_read(i) exactement global_read_at(i, 0). */",
        "extern int  global_read_at (int i, int k);",
        "extern void global_write_at(int i, int k, int v);",
    ]
    lines += ["", "#endif /* GLOBALS_H */", ""]
    return "\n".join(lines)


def generate_globals_c(globals_) -> str:
    lines = [
        "/* globals.c — définitions des variables globales partagées */",
        f"/* Généré par {APP_NAME} — ne pas éditer */",
        "",
        '#include "globals.h"',
        "",
    ]
    if globals_:
        for g in globals_:
            c_type = _C_TYPES.get(g.type, "int")
            n = _count(g)
            if n > 1:
                # Une seule valeur par défaut pour toutes les cases : le C
                # répète la première et complète à zéro, ce qui n'irait pas
                # pour un défaut non nul. On l'écrit donc en clair — 400 zéros
                # ne coûtent rien en ROM (le compilateur les range en .bss),
                # et le fichier reste lisible.
                init = ", ".join([str(int(g.default))] * n)
                lines.append(f"{c_type} g_{g.name}[{n}] = {{{init}}};")
            else:
                lines.append(f"{c_type} g_{g.name} = {int(g.default)};")
    else:
        lines.append("/* aucune variable globale */")

    lines += ["", "int global_read_at(int i, int k) {", "    (void)k;",
              "    switch (i) {"]
    for i, g in enumerate(globals_):
        ref = f"g_{g.name}[k]" if _count(g) > 1 else f"g_{g.name}"
        lines.append(f"    case {i}: return (int){ref};")
    lines += ["    default: return 0;", "    }", "}", ""]
    lines += ["void global_write_at(int i, int k, int v) {", "    (void)k;",
              "    switch (i) {"]
    for i, g in enumerate(globals_):
        c_type = _C_TYPES.get(g.type, "int")
        ref = f"g_{g.name}[k]" if _count(g) > 1 else f"g_{g.name}"
        lines.append(f"    case {i}: {ref} = ({c_type})v; break;")
    lines += ["    default: (void)v; break;", "    }", "}", ""]
    lines += ["int  global_read (int i)        { return global_read_at(i, 0); }",
              "void global_write(int i, int v) { global_write_at(i, 0, v); }"]
    lines.append("")
    return "\n".join(lines)


def write_globals(src_dir: Path, globals_) -> list[str]:
    """
    Écrit globals.h et globals.c dans src_dir depuis la liste de GlobalVar.
    Retourne la liste des noms (utile pour CodegenContext).
    """
    build_output.write(src_dir / "globals.h", generate_globals_h(globals_))
    build_output.write(src_dir / "globals.c", generate_globals_c(globals_))
    return [g.name for g in globals_]
