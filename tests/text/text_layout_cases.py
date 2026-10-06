"""Polices et textes d'essai, partagés par les deux tests de mise en page.

`test_text_layout.py` les passe à l'implémentation Python, `test_text_layout_native.py`
aux deux, et compare. Les décrire ici une seule fois est ce qui garantit que la
comparaison porte bien sur la même chose — un cas ajouté d'un seul côté ne
prouverait rien.

Les métriques ne sont jamais écrites à la main : elles sortent de
`codegen.font_emit`, l'ÉMETTEUR. C'est le point qui donne sa valeur au test —
le moteur C lit des chasses déjà résolues en pixels, l'aperçu Python appelle les
mêmes fonctions pour les résoudre, et ce qu'on compare est donc l'ALGORITHME de
mise en page, pas deux façons de mesurer une police.
"""
from __future__ import annotations

from core.models.font import Font, Glyph
from codegen.font_emit import (font_fallback_adv_px, font_line_px,
                               glyph_advance_px, glyph_tiles_w,
                               render_composited)


# ── Polices d'essai ───────────────────────────────────────────────

def police_mono() -> Font:
    """Planche 8×8 sans couleur d'espacement : la police est MONO, quoi que
    disent les chasses stockées (règle d'autorité, cf. `advances_declared`).
    Chemin tilemap, donc l'alignement se cale sur la grille de tuiles."""
    lettres = "ABCDEFGHIJKLMNOPQRSTUVWXYZ .!"
    glyphes = [Glyph(char=c, x=i * 8, y=0, w=8, h=8, advance=8)
               for i, c in enumerate(lettres)]
    # Une ligature : elle doit être reconnue AU PLUS LONG, des deux côtés.
    glyphes.append(Glyph(char="...", x=len(lettres) * 8, y=0, w=8, h=8, advance=8))
    return Font(name="Mono", cell_w=8, cell_h=8, line_height=8, glyphs=glyphes)


def police_a_glyphe_large() -> Font:
    """Une police mono dont un glyphe fait DEUX tuiles de large : sa chasse vaut
    16 px. Elle sert à éclairer un seul cas — une boîte plus étroite qu'un
    glyphe (cf. `test_boite_plus_etroite_qu_un_glyphe`)."""
    return Font(name="Large", cell_w=8, cell_h=8, line_height=8, glyphs=[
        Glyph(char="W", x=0,  y=0, w=16, h=8, advance=16),
        Glyph(char="A", x=16, y=0, w=8,  h=8, advance=8),
    ])


def police_proportionnelle() -> Font:
    """Chasses déclarées (une couleur d'espacement est désignée) et réellement
    variables : le rendu passe en composition pixel, où l'alignement ne se cale
    plus sur la tuile."""
    chasses = {"A": 7, "B": 6, "C": 6, "D": 6, "E": 5, "I": 3, "L": 5, "M": 8,
               "N": 6, "O": 7, "R": 6, "S": 5, "T": 5, "U": 6, " ": 4, ".": 2}
    glyphes = [Glyph(char=c, x=i * 8, y=0, w=8, h=8, advance=a)
               for i, (c, a) in enumerate(chasses.items())]
    return Font(name="Proportionnelle", cell_w=8, cell_h=8, line_height=10,
                space_color=(255, 0, 255), glyphs=glyphes)


# ── Table telle que le moteur la lit ──────────────────────────────

def table_runtime(font: Font) -> dict:
    """Les tables parallèles qu'un `FontInfo` porte en ROM.

    Miroir de `font_emit.encode_font`, dont on ne peut pas se servir directement :
    elle rastérise une planche PNG, que ces polices d'essai n'ont pas. Seul
    l'ORDRE est reproduit ici — 1er codepoint croissant (le moteur cherche par
    dichotomie), puis séquence la plus longue d'abord (il prend la première
    correspondance complète du groupe, qui est donc la plus longue). Toutes les
    valeurs, elles, viennent de l'émetteur."""
    entrees = []
    for g in font.glyphs:
        seq = [ord(c) for c in g.char if ord(c) < 0x10000]
        if not seq:
            continue
        entrees.append({"seq": seq, "adv": glyph_advance_px(g, font),
                        "gw": glyph_tiles_w(g), "gh": max(1, (g.h + 7) // 8)})
    entrees.sort(key=lambda e: (e["seq"][0], -len(e["seq"])))

    seq_plat: list[int] = []
    seq_off: list[int] = []
    for e in entrees:
        seq_off.append(len(seq_plat))
        seq_plat += e["seq"]

    return {
        "line_h":     font_line_px(font),
        "cell_w":     font_fallback_adv_px(font),
        "composited": int(render_composited(font)),
        "cp":         [e["seq"][0] for e in entrees],
        "adv":        [e["adv"] for e in entrees],
        "gw":         [e["gw"] for e in entrees],
        "gh":         [e["gh"] for e in entrees],
        "seq":        seq_plat,
        "seq_off":    seq_off,
        "seq_len":    [len(e["seq"]) for e in entrees],
        "glyphes":    [e["seq"] for e in entrees],   # pour retrouver l'index côté Python
    }


# ── Cas ───────────────────────────────────────────────────────────
#
# `largeur` est un multiple de 8 : le moteur exprime sa boîte en TUILES
# (`wrap`), l'aperçu en pixels. Hors de la grille, les deux ne décriraient pas
# la même boîte et la comparaison n'aurait plus de sens — ce qui est sans perte,
# les cadres d'une zone d'UI étant alignés à la tuile par construction.
#
# `TEXT_ANIM_MAX` (32) borne les textes : au-delà, la capture qui permet de lire
# les positions déborde et le moteur se remettrait à écrire en VRAM.

CAS = [
    # (nom, police, texte, largeur, hauteur, alignement)
    ("mono ligne simple",        police_mono,            "ABC",        240, 160, "left"),
    ("mono coupe au mot",        police_mono,            "AB CD",       32,  32, "left"),
    ("mono mot trop long",       police_mono,            "ABCDEF GH",   32,  32, "left"),
    ("mono retour a la ligne",   police_mono,            "AB\nCD",      64,  32, "left"),
    ("mono debordement vertical", police_mono,           "AB CD EF",    24,  16, "left"),
    ("mono ligature",            police_mono,            "A...B",       80,  32, "left"),
    ("mono glyphe absent",       police_mono,            "A?B",         80,  32, "left"),
    ("mono centre",              police_mono,            "ABC",         80,  32, "center"),
    ("mono ferre a droite",      police_mono,            "ABC",         80,  32, "right"),
    ("mono centre deux lignes",  police_mono,            "AB CDE",      40,  32, "center"),
    ("mono boite pile juste",    police_mono,            "ABCD",        32,  32, "left"),
    ("mono espaces multiples",   police_mono,            "A  B",        80,  32, "left"),

    ("prop ligne simple",        police_proportionnelle, "ABC",        240, 160, "left"),
    ("prop coupe au mot",        police_proportionnelle, "MOT MOT",     40,  40, "left"),
    ("prop centre sans calage",  police_proportionnelle, "III",         80,  40, "center"),
    ("prop ferre a droite",      police_proportionnelle, "III",         80,  40, "right"),
    ("prop interligne dix",      police_proportionnelle, "AB\nCD",      64,  40, "left"),
    ("prop chasses melangees",   police_proportionnelle, "MIMI",        80,  40, "left"),
]
