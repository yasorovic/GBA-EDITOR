"""Mise en page du texte, côté aperçu — `core/engine_emulation/text_layout.py`.

Troisième module où se tromper est silencieux, et le plus retors des trois : il
n'y a pas de bug ici, seulement un ÉCART possible avec le moteur C. Ce que
l'aperçu montre n'est jamais faux en soi — c'est juste que la console pourrait
faire autrement, et personne ne le saurait avant d'avoir construit la ROM.

Ce fichier fixe ce que fait l'implémentation Python, cas par cas.
`test_text_layout_native.py` fait l'autre moitié du travail : il rejoue les mêmes
cas dans le vrai moteur et compare. Les deux sont nécessaires — celui-ci dit ce
que le placement DOIT être, celui-là que les deux implémentations le disent
pareil.
"""
from __future__ import annotations

import pytest

from core.engine_emulation.text_layout import layout_text, layout_marked_text
from codegen.font_emit import font_line_px, glyph_advance_px, render_composited
from text_layout_cases import CAS, police_mono, police_proportionnelle


def _pose(font, texte, largeur, hauteur=160, align="left"):
    """Placements sous forme comparable : (caractère, x, y)."""
    out, over = layout_text(font, texte, largeur, hauteur, align)
    return [(g.char, x, y) for g, x, y in out], over


# ── Avance et retour à la ligne ───────────────────────────────────

def test_les_glyphes_avancent_de_leur_chasse():
    pose, over = _pose(police_mono(), "ABC", 240)
    assert pose == [("A", 0, 0), ("B", 8, 0), ("C", 16, 0)]
    assert over is False


def test_la_coupe_se_fait_au_mot():
    """L'espace qui provoque la coupe DISPARAÎT : le laisser mettrait un blanc en
    début de ligne, que personne n'a écrit."""
    pose, _ = _pose(police_mono(), "AB CD", 32, 32)
    assert pose == [("A", 0, 0), ("B", 8, 0), ("C", 0, 8), ("D", 8, 8)]


def test_un_mot_plus_long_que_la_boite_est_coupe_au_glyphe():
    """Filet de sécurité : sans lui, un mot trop long ne tiendrait sur aucune
    ligne et la mise en page n'avancerait jamais."""
    pose, _ = _pose(police_mono(), "ABCDEF GH", 32, 32)
    assert pose == [("A", 0, 0), ("B", 8, 0), ("C", 16, 0), ("D", 24, 0),
                    ("E", 0, 8), ("F", 8, 8), ("G", 0, 16), ("H", 8, 16)]


def test_le_retour_a_la_ligne_explicite_est_respecte():
    pose, _ = _pose(police_mono(), "AB\nCD", 64, 32)
    assert pose == [("A", 0, 0), ("B", 8, 0), ("C", 0, 8), ("D", 8, 8)]


def test_le_debordement_vertical_arrete_la_mise_en_page():
    """Une ligne qui ne tient pas entière arrête tout : les suivantes ne
    tiendraient pas davantage."""
    pose, over = _pose(police_mono(), "AB CD EF", 24, 16)
    assert over is True
    assert [y for _, _, y in pose] == [0, 0, 8, 8]      # rien au-delà de 16 px


def test_l_interligne_suit_la_police():
    """La proportionnelle déclare `line_height` ; la mono arrondit sa cellule à
    la tuile. Deux règles, une seule source : `font_emit.font_line_px`."""
    prop = police_proportionnelle()
    assert font_line_px(prop) == 10
    pose, _ = _pose(prop, "AB\nCD", 64, 40)
    assert [y for _, _, y in pose] == [0, 0, 10, 10]


def test_le_balisage_font_change_la_police_sans_changer_l_interligne():
    """La zone conserve sa hauteur de ligne ; seul le glyphe et sa chasse
    viennent de la police active, comme `TEXT_EV_FONT` dans le runtime."""
    base = police_mono()
    titre = police_proportionnelle()
    titre.name = "Titre"

    placed, over = layout_marked_text(
        base, "A[font=Titre]B[/font]C", {"Titre": titre}, width=40, height=16)

    assert [(f.name, g.char, x, y) for f, g, x, y in placed] == [
        ("Mono", "A", 0, 0), ("Titre", "B", 8, 0), ("Mono", "C", 14, 0),
    ]
    assert over is False


# ── Correspondance des glyphes ────────────────────────────────────

def test_la_ligature_est_prise_au_plus_long():
    """Une police qui a « . » et « ... » doit rendre la ligature, pas trois
    points — sinon elle avancerait de trois chasses au lieu d'une."""
    pose, _ = _pose(police_mono(), "A...B", 80, 32)
    assert pose == [("A", 0, 0), ("...", 8, 0), ("B", 16, 0)]


def test_un_caractere_absent_avance_sans_rien_poser():
    """Un trou plutôt qu'un décalage : décaler la suite ferait bouger tout le
    reste de la ligne pour un caractère que la police n'a simplement pas."""
    pose, _ = _pose(police_mono(), "A?B", 80, 32)
    assert pose == [("A", 0, 0), ("B", 16, 0)]          # 8 px sautés, rien posé


# ── Alignement ────────────────────────────────────────────────────

def test_le_centrage_mono_se_cale_sur_la_tuile():
    """Chemin tilemap : un glyphe se pose à la case. Centrer au pixel promettrait
    un placement que la ROM ne tiendrait pas — 28 px deviendraient 24 en
    silence."""
    font = police_mono()
    assert render_composited(font) is False
    pose, _ = _pose(font, "ABC", 80, 32, "center")
    assert pose[0] == ("A", 24, 0)                      # (80-24)//2 = 28, calé à 24


def test_le_centrage_proportionnel_garde_le_pixel():
    """Chemin composé : les pixels sont écrits un à un, il n'y a pas de grille à
    respecter."""
    font = police_proportionnelle()
    assert render_composited(font) is True
    pose, _ = _pose(font, "III", 80, 40, "center")
    assert pose[0] == ("I", 35, 0)                      # (80-9)//2 = 35, tel quel


def test_le_ferrage_a_droite_colle_au_bord():
    pose, _ = _pose(police_mono(), "ABC", 80, 32, "right")
    assert pose == [("A", 56, 0), ("B", 64, 0), ("C", 72, 0)]


def test_chaque_ligne_est_alignee_pour_elle_meme():
    """Deux lignes de largeurs différentes reçoivent deux décalages différents —
    l'alignement porte sur la ligne, pas sur le bloc."""
    pose, _ = _pose(police_mono(), "AB CDE", 40, 32, "center")
    assert pose[0] == ("A", 8, 0)                       # (40-16)//2 = 12, calé à 8
    assert pose[2] == ("C", 8, 8)                       # (40-24)//2 = 8

def test_l_alignement_ne_change_ni_la_coupe_ni_le_debordement():
    """Il n'agit que sur les positions : mesurer un texte ne dépend donc pas de
    son ferrage, et l'aperçu peut mesurer à gauche par défaut."""
    font = police_mono()
    gauche, over_g = _pose(font, "AB CD EF", 24, 16, "left")
    centre, over_c = _pose(font, "AB CD EF", 24, 16, "center")
    assert over_g == over_c
    assert [c for c, _, _ in gauche] == [c for c, _, _ in centre]
    assert [y for _, _, y in gauche] == [y for _, _, y in centre]


def test_une_ligne_plus_large_que_sa_boite_n_est_pas_decalee():
    """Jamais de décalage négatif : à gauche de l'origine, rien n'a été préparé
    ni effacé — le texte irait repeindre ce qui s'y trouve."""
    pose, _ = _pose(police_mono(), "ABCD", 32, 32, "center")
    assert pose[0] == ("A", 0, 0)


# ── Espaces ───────────────────────────────────────────────────────

def test_les_espaces_qui_ne_coupent_pas_sont_poses():
    """Un espace n'est un séparateur que lorsqu'il provoque la coupe ; ailleurs
    c'est un glyphe comme un autre, qui occupe sa chasse."""
    pose, _ = _pose(police_mono(), "A  B", 80, 32)
    assert pose == [("A", 0, 0), (" ", 8, 0), (" ", 16, 0), ("B", 24, 0)]


# ── Invariants, sur tous les cas partagés ─────────────────────────

@pytest.mark.parametrize("cas", CAS, ids=[c[0] for c in CAS])
def test_les_lignes_descendent_par_pas_d_interligne(cas):
    _, fabrique, texte, largeur, hauteur, align = cas
    font = fabrique()
    ligne = font_line_px(font)
    pose, _ = _pose(font, texte, largeur, hauteur, align)
    ys = [y for _, _, y in pose]
    assert all(y % ligne == 0 for y in ys)
    assert ys == sorted(ys)
    assert all(y + ligne <= hauteur for y in ys)


@pytest.mark.parametrize("cas", CAS, ids=[c[0] for c in CAS])
def test_aucun_glyphe_ne_sort_de_la_boite(cas):
    """Ce qui déborde de la boîte va écrire chez le voisin : sur la console, ce
    n'est pas un glyphe mal placé mais du décor repeint."""
    _, fabrique, texte, largeur, hauteur, align = cas
    font = fabrique()
    pose, _ = _pose(font, texte, largeur, hauteur, align)
    chasses = {g.char: glyph_advance_px(g, font) for g in font.glyphs}
    for char, x, _ in pose:
        assert x >= 0
        assert x + chasses[char] <= largeur, f"{char!r} à x={x} sort de {largeur}"
