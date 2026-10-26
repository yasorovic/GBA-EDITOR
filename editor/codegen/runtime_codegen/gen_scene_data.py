"""runtime_codegen/gen_scene_data.py — les tableaux ROM propres à chaque scène : carte de collision à plat et
palettes OBJ/BG actives (16 banques de 16 couleurs, résolues depuis le catalogue du projet)."""
from __future__ import annotations

from codegen.c_names import sym as c_sym
from codegen.palette_alloc import scene_bank_layout
from codegen.runtime_codegen.gen_palette import scene_bg_palette_words, scene_obj_palette_words


def scene_data_lines(p, all_scene_data: list[dict]) -> list[str]:
    """Pour toutes les scènes : les cartes de collision, puis les palettes OBJ, puis les palettes BG."""
    L: list[str] = []
    # ── Cmap flat arrays par scène ────────────────────────────────
    for d in all_scene_data:
        sc = d["scene"]
        sym = c_sym(sc.name)
        cmap = sc.collision_map or []
        if cmap and any(v != 0 for row in cmap for v in row):
            rows = len(cmap)
            cols = max(len(row) for row in cmap)
            flat = []
            for row in cmap:
                flat += list(row) + [0] * (cols - len(row))
            L += [
                f"#define CMAP_W_{sym.upper()} {cols}",
                f"#define CMAP_H_{sym.upper()} {rows}",
                f"static const u8 g_cmap_{sym}[{rows*cols}] = {{",
                "    " + ", ".join(str(v) for v in flat),
                "};",
                "",
            ]

    # ── Palettes OBJ actives par scène (16 banques x 16 couleurs, résolues
    #    depuis Scene.active_obj_palettes -> project.palettes) ────────────
    # Émis uniquement si au moins un slot est réellement occupé — sinon la
    # boucle copy16 correspondante dans gen_scene_init ne référence jamais
    # ce tableau ("defined but not used", en plus de gaspiller 512 octets
    # de ROM par scène sans palette OBJ active, ex. INTRO/VICTORY).
    for d in all_scene_data:
        sc = d["scene"]
        sym = c_sym(sc.name)
        if scene_bank_layout(p, sc, "obj").bank_count() > 0:
            words = scene_obj_palette_words(p, sc)
            L += [
                f"static const unsigned short g_pal_obj_{sym}[256] __attribute__((aligned(4))) = {{",
                "    " + ", ".join(f"0x{v:04X}" for v in words),
                "};",
                "",
            ]

    # ── Palettes BG actives par scène (16 banques x 16 couleurs, résolues
    #    depuis Scene.active_bg_palettes -> project.palettes) ──────────────
    # Même garde qu'OBJ ci-dessus — le backdrop (PAL_BG_RAM[0]) est écrit à
    # part comme constante littérale (resolve_backdrop_color), pas depuis
    # ce tableau, donc rien ne le référence si aucun slot BG n'est occupé.
    for d in all_scene_data:
        sc = d["scene"]
        sym = c_sym(sc.name)
        # Émis si un slot BG est occupé (référencé, bloc de fond compressé, ou
        # palette propre) ; le backdrop (PAL_BG_RAM[0]) est écrit séparément.
        if scene_bank_layout(p, sc, "bg").bank_count() > 0:
            words = scene_bg_palette_words(p, sc)
            L += [
                f"static const unsigned short g_pal_bg_{sym}[256] __attribute__((aligned(4))) = {{",
                "    " + ", ".join(f"0x{v:04X}" for v in words),
                "};",
                "",
            ]
    return L
