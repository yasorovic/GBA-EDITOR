"""codegen/runtime_codegen/gen_palette.py — les palettes en RAM et le catalogue.

Extrait de `main_gen` (A3). Les mots PAL_OBJ_RAM/PAL_BG_RAM d'une scène (dérivés
du layout de banques, cf. `palette_alloc`) et la table `g_palettes` du catalogue.
`palettes_lines` émet le catalogue ENTIER dans l'ordre dont `lua_compiler` dérive
les `#define PAL_*` — les deux doivent voir la même liste.
"""
from __future__ import annotations

from core.models.scene import Scene
from core.project import Project
from codegen.palette_alloc import scene_bank_layout


def _layout_palette_words(layout) -> list[int]:
    """256 valeurs BGR555 (16 banques x 16 couleurs) depuis un SceneBankLayout
    — inclut les palettes référencées ET les palettes propres auto-allouées
    (cf. codegen/palette_alloc.py)."""
    words = [0] * 256
    for i, colors in enumerate(layout.slot_colors):
        if not colors:
            continue
        for j, c in enumerate(colors[:16]):
            words[i * 16 + j] = c
    return words


def resolve_backdrop_color(p: Project, scene: Scene) -> int:
    """Scene.backdrop_color surcharge ProjectSettings.backdrop_color si
    défini (None = hérite du projet)."""
    v = getattr(scene, "backdrop_color", None)
    return v if v is not None else p.settings.backdrop_color


def scene_obj_palette_words(p: Project, scene: Scene) -> list[int]:
    """PAL_OBJ_RAM de la scène — layout OBJ (référencées + propres allouées)."""
    return _layout_palette_words(scene_bank_layout(p, scene, "obj"))


def scene_bg_palette_words(p: Project, scene: Scene) -> list[int]:
    """PAL_BG_RAM de la scène — layout BG (référencées + propres, y compris
    les blocs de banques des fonds compressés, cf. palette_alloc). words[0]
    forcé à la couleur de backdrop."""
    words = _layout_palette_words(scene_bank_layout(p, scene, "bg"))
    words[0] = resolve_backdrop_color(p, scene)
    return words


def palettes_lines(p, emit=None) -> list[str]:
    """Table `g_palettes` — le catalogue de couleurs, pour `palette.set_bg/obj`.

    Le catalogue ENTIER, dans son ordre, celui-là même dont `lua_compiler` dérive
    les `#define PAL_*` : les deux doivent voir la même liste ou l'index désigne
    une autre palette.

    Émis en entier plutôt que dérivé des scripts — contrairement aux polices, où
    la réservation doit être calculée parce qu'elle coûte de la mémoire vidéo.
    Une palette pèse 32 octets en ROM ; réserver pour tout le catalogue est moins
    cher que le risque de réserver trop peu, qui ferait basculer vers une palette
    absente sans erreur avant l'exécution."""
    banks = list(getattr(p, "palettes", []))
    L = ["", "/* Palettes du catalogue — palette.set_bg / palette.set_obj */"]
    L.append(f"const unsigned short g_palettes[{max(1, len(banks))}][16] = {{")
    for b in banks:
        cols = list(b.colors or [])[:16]
        cols += [0] * (16 - len(cols))
        L.append("    {" + ",".join(f"0x{c & 0xFFFF:04X}" for c in cols) + "},")
    if not banks:
        L.append("    {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},")
    L.append("};")
    L.append(f"const int g_palette_count = {max(1, len(banks))};")
    L.append("")
    if emit and banks:
        emit("log_line", f"[palette] {len(banks)} catalogue palette(s) in ROM "
                         f"({len(banks) * 32} bytes)")
    return L
