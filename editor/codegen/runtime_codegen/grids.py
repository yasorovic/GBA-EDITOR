"""runtime_codegen/grids.py : les grilles de valeurs des scènes, en ROM.

Émet `grids.h` (une déclaration et ses macros par grille) et `grids.c` (les
cases, en `const`). Un script les lira par `data.grid.<Nom>`, résolu AU BUILD
dans la scène où il tourne : il n'y a donc ni pointeur actif ni descripteur à
l'exécution, contrairement à la carte de collision, que la physique partage
entre toutes les scènes.

Même forme que `data_tables.py`, et pour les mêmes raisons :

- `grids.h` est écrit MÊME SANS GRILLE, pour qu'une unité qui l'inclut n'ait
  jamais à le faire sous condition ;
- `grids.c` n'existe que s'il y a quelque chose dedans, une unité de traduction
  vide n'étant pas du C standard ;
- l'en-tête n'inclut rien et dit `unsigned char` plutôt que `u8` : il reste
  lisible par une unité qui n'a pas les types de libgba, et l'octet en ROM est
  le même.

**Un octet par case**, mis à plat en rangées concaténées, comme `g_cmap_*`. Une
grille au pas de 16 px sur la scène de la démo publique pèse 544 octets.

**Une grille déclarée est toujours émise**, même toute à zéro. C'est la
différence avec la carte de collision, dont l'absence veut dire « aucune
collision » : une grille, elle, est résolue par son nom au build, et 0 est une
valeur comme une autre. Seule une grille qui n'a jamais reçu de cases est sautée.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codegen.c_names import c_ident, grid_macro, grid_sym
from core.app_info import APP_NAME
import codegen.build_output as build_output


def array_name(scene, grid) -> str:
    """Le tableau des cases : son nom dit la scène d'où il vient.

    Pour une grille RAM, ce nom désigne le tampon RAM que les scripts lisent ET
    écrivent (non `const`) ; son germe peint, lui, prend le suffixe `_seed`."""
    return grid_sym(scene.name, grid.name)


def seed_name(scene, grid) -> str:
    """Le germe ROM d'une grille RAM : recopié dans le tampon RAM à l'entrée de
    scène. N'existe que si la grille a des cases non nulles peintes."""
    return f"{array_name(scene, grid)}_seed"


def _has_seed(grid) -> bool:
    """La grille porte-t-elle un contenu peint non nul ? Sinon le tampon RAM part
    de zéro, et aucun germe n'est émis (ni ROM gaspillée, ni tableau inutilisé)."""
    return any(v != 0 for row in grid.cells for v in row)


def width_macro(scene, grid) -> str:
    return grid_macro("W", scene.name, grid.name)


def height_macro(scene, grid) -> str:
    return grid_macro("H", scene.name, grid.name)


def step_macro(scene, grid) -> str:
    return grid_macro("STEP", scene.name, grid.name)


def shift_macro(scene, grid) -> str:
    """Le décalage de bits qui passe d'un pixel à une case.

    Émis à côté du pas pour que la lecture par pixel n'ait ni division ni calcul :
    la GBA n'a pas d'instruction de division."""
    return grid_macro("SHIFT", scene.name, grid.name)


def value_macro(scene, grid, value_name: str) -> str:
    """La constante d'une valeur nommée de la légende, qualifiée par la scène.

    L'origine d'abord, ce qu'elle est ensuite : `GRID_VALUE_<SCÈNE>_<GRILLE>_<VALEUR>`."""
    return f"{grid_macro('VALUE', scene.name, grid.name)}_{c_ident(value_name)}"


@dataclass(frozen=True)
class GridAccess:
    """Ce qu'un script a besoin de savoir d'une grille, pour la lire.

    Construit par `lua_compiler` (qui tient la scène) et lu par le vérificateur et le
    traducteur Lua vers C. Les noms C sont portés ici plutôt que rederivés là-bas : un
    nom de scène qui commence par un chiffre gagne un `_` dans son symbole et pas dans
    sa macro (`c_names.sym` contre `c_ident`), donc les deux ne se déduisent pas l'un de
    l'autre."""
    name: str          # le nom d'auteur, celui que le script écrit
    cols: int
    rows: int
    step: int          # pixels par case
    sym: str           # g_grid_<Scène>_<Grille>
    width: str         # GRID_W_<SCÈNE>_<GRILLE>
    height: str        # GRID_H_...
    shift: str         # GRID_SHIFT_...
    ram: bool          # grille RAM : lisible ET inscriptible par les scripts


def grid_access(scene, grid) -> GridAccess:
    """La fiche d'accès d'une grille, telle que les scripts la liront."""
    return GridAccess(
        name=grid.name, cols=grid.cols, rows=grid.rows, step=grid.step,
        sym=array_name(scene, grid), width=width_macro(scene, grid),
        height=height_macro(scene, grid), shift=shift_macro(scene, grid),
        ram=bool(getattr(grid, "ram", False)),
    )


def scene_grid_access(scene) -> dict:
    """{nom d'auteur → `GridAccess`} des grilles lisibles de cette scène.

    Une grille jamais dimensionnée n'y est pas : rien n'est émis pour elle, donc rien
    n'est lisible, et le vérificateur dira qu'elle est absente."""
    return {grid.name: grid_access(scene, grid)
            for grid in getattr(scene, "grids", [])
            if grid.cells and grid.cols}


@dataclass(frozen=True)
class RamGridInit:
    """Ce dont l'entrée de scène a besoin pour germer une grille RAM : le tampon,
    son germe (ou None si vide), et les macros de géométrie pour la boucle."""
    sym: str
    seed: str | None       # None : germer à zéro
    width: str
    height: str


def scene_ram_grids(scene) -> list[RamGridInit]:
    """Les grilles RAM émises de cette scène, à germer à l'entrée de scène.

    Même filtre que `scene_grid_access` : une grille jamais dimensionnée n'émet
    rien, donc rien à germer."""
    out: list[RamGridInit] = []
    for grid in getattr(scene, "grids", []):
        if not (grid.cells and grid.cols and getattr(grid, "ram", False)):
            continue
        out.append(RamGridInit(
            sym=array_name(scene, grid),
            seed=seed_name(scene, grid) if _has_seed(grid) else None,
            width=width_macro(scene, grid), height=height_macro(scene, grid),
        ))
    return out


def project_has_ram_grid(p) -> bool:
    """Un projet a-t-il au moins une grille RAM émise ? main.c inclut alors
    grids.h (pour les `extern` des tampons et les macros de germination)."""
    return any(getattr(grid, "ram", False)
               for scene, grid in emitted_grids(p))


def emitted_grids(p) -> list[tuple]:
    """[(scène, grille)] de ce que le build émet, dans l'ordre des scènes.

    Une grille sans aucune case n'a rien à émettre : elle n'a jamais été
    dimensionnée, donc aucun script ne peut en lire quoi que ce soit."""
    return [(scene, grid)
            for scene in getattr(p, "scenes", [])
            for grid in getattr(scene, "grids", [])
            if grid.cells and grid.cols]


def _flat(grid) -> list[int]:
    """Les cases en rangées concaténées, complétées à la largeur de la grille."""
    cols = grid.cols
    out: list[int] = []
    for row in grid.cells:
        out += list(row) + [0] * (cols - len(row))
    return out


def generate_grids_h(pairs: list[tuple]) -> str:
    lines = [
        "/* grids.h - value grids of the scenes */",
        f"/* Generated by {APP_NAME} - do not edit */",
        "",
        "#ifndef GRIDS_H",
        "#define GRIDS_H",
        "",
    ]
    if not pairs:
        lines.append("/* no value grid in this project */")
    for scene, grid in pairs:
        cols, rows = grid.cols, grid.rows
        kind = "RAM, runtime-writable" if getattr(grid, "ram", False) else "ROM, read-only"
        lines += [
            f"/* {scene.name} / {grid.name} - {cols}x{rows} cell(s) of {grid.step} px"
            f" = {cols * rows} byte(s), {kind} */",
            f"#define {width_macro(scene, grid)} {cols}",
            f"#define {height_macro(scene, grid)} {rows}",
            f"#define {step_macro(scene, grid)} {grid.step}",
            f"#define {shift_macro(scene, grid)} {grid.step.bit_length() - 1}",
        ]
        lines += [f"#define {value_macro(scene, grid, v.name)} {v.value}"
                  for v in grid.values if v.name]
        if getattr(grid, "ram", False):
            # Tampon RAM non `const` : les scripts le lisent ET l'écrivent. Son
            # germe ROM (s'il y a du contenu peint) est recopié à l'entrée de
            # scène par main.c. Déclaré `extern` ici, défini dans grids.c.
            lines.append(f"extern unsigned char {array_name(scene, grid)}[{cols * rows}];")
            if _has_seed(grid):
                lines.append(f"extern const unsigned char {seed_name(scene, grid)}[{cols * rows}];")
        else:
            lines.append(f"extern const unsigned char {array_name(scene, grid)}[{cols * rows}];")
        lines.append("")
    lines += ["#endif /* GRIDS_H */", ""]
    return "\n".join(lines)


def _rows_of(lines: list[str], scene, grid) -> None:
    """Les cases d'une grille, une rangée par ligne : le C émis se relit comme la
    carte dans le fichier de scène (cf. models/project_json.py, même raison)."""
    cols = grid.cols
    flat = _flat(grid)
    for start in range(0, len(flat), cols):
        lines.append("    " + ", ".join(str(v) for v in flat[start:start + cols]) + ",")


def generate_grids_c(pairs: list[tuple]) -> str:
    lines = [
        "/* grids.c - cells of the value grids */",
        f"/* Generated by {APP_NAME} - do not edit */",
        "",
        '#include "grids.h"',
    ]
    # Une grille RAM se définit avec EWRAM_BSS (sinon le .bss part en IWRAM, les
    # 32 Kio précieux) : il faut alors le macro, apporté par gba_engine.h, comme
    # dans main.c. On ne l'inclut que si une grille RAM existe, pour garder
    # grids.c sans dépendance libgba quand tout est en ROM.
    if any(getattr(grid, "ram", False) for _scene, grid in pairs):
        lines.append('#include "gba_engine.h"')
    lines.append("")
    for scene, grid in pairs:
        n = grid.cols * grid.rows
        if getattr(grid, "ram", False):
            # Le tampon RAM, non initialisé (germé à l'entrée de scène), plus son
            # germe ROM s'il y a du contenu peint.
            lines.append(f"unsigned char {array_name(scene, grid)}[{n}] EWRAM_BSS;")
            if _has_seed(grid):
                lines.append(f"const unsigned char {seed_name(scene, grid)}[{n}] = {{")
                _rows_of(lines, scene, grid)
                lines.append("};")
            lines.append("")
            continue
        lines.append(f"const unsigned char {array_name(scene, grid)}[{n}] = {{")
        _rows_of(lines, scene, grid)
        lines += ["};", ""]
    return "\n".join(lines)


def write_grids(src_dir: Path, p, emit=None) -> list[str]:
    """Écrit les deux fichiers et rend les noms qualifiés des grilles émises."""
    pairs = emitted_grids(p)
    build_output.write(src_dir / "grids.h", generate_grids_h(pairs))
    c_path = src_dir / "grids.c"
    if pairs:
        build_output.write(c_path, generate_grids_c(pairs))
        if emit:
            total = sum(grid.cols * grid.rows for _scene, grid in pairs)
            emit("log_line", f"[grid] {len(pairs)} value grid(s) in ROM ({total} byte(s))")
    elif c_path.exists():
        c_path.unlink()
    return [f"{scene.name}/{grid.name}" for scene, grid in pairs]
