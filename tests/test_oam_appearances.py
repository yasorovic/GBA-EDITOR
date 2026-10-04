"""Marche 3a de « La struct Actor allégée » : l'apparence est une donnée du build.

Un acteur affiche UN sprite (une entrée OAM) mais peut en porter plusieurs ;
`OamEntry.appearance` dit lequel. Le C reste déroulé par entrée, et l'est désormais
par apparence. Un acteur à UNE apparence émet le C d'avant, sans `switch` —
vérifié aussi octet pour octet sur les projets démo au moment de la refonte."""
from codegen.runtime_codegen.gen_sprite import (
    Appearance, anim_tick_lines, anim_tick_variants, oam_write_lines,
)
from core.models.sprite import SpriteAsset


def _sprite(nom="Hero", **kw):
    return SpriteAsset(name=nom, asset=f"{nom}.png", **kw)


def _deux():
    return [Appearance(_sprite("Hero"), 0), Appearance(_sprite("Hurt"), 16, origin_x=2)]


# ── Écriture OAM ──────────────────────────────────────────────────────

def test_une_apparence_n_emet_ni_switch_ni_lecture_du_champ():
    code = "\n".join(oam_write_lines(3, 1, [Appearance(_sprite(), 8)]))
    assert "switch" not in code and "appearance" not in code
    assert "u16 ti=(u16)(8+g_oam_entries[1].frame*" in code
    assert "shadow_oam[1].attr0=0x0200;" in code           # branche « caché »


def test_deux_apparences_se_choisissent_par_le_champ_de_l_entree():
    code = "\n".join(oam_write_lines(3, 1, _deux()))
    assert "switch(g_oam_entries[1].appearance)" in code
    assert code.index("case 0:") < code.index("case 1:")
    # chaque cas a SES constantes : base de tuiles et origine
    assert "u16 ti=(u16)(0+g_oam_entries[1].frame" in code
    assert "u16 ti=(u16)(16+g_oam_entries[1].frame" in code
    assert "-cam_x-2" in code                                # origin_x de la 2e apparence
    # une apparence inconnue ne dessine rien
    assert "default: shadow_oam[1].attr0=0x0200; break;" in code


def test_l_acteur_et_l_entree_restent_deux_indices_distincts():
    code = "\n".join(oam_write_lines(7, 2, _deux()))
    assert "g_actors[7].x" in code and "shadow_oam[2]" in code
    assert "g_actors[2]" not in code and "shadow_oam[7]" not in code


def test_l_ecran_ne_suit_pas_la_camera():
    code = "\n".join(oam_write_lines(0, 0, [Appearance(_sprite(), 0)], screen_space=True))
    assert "cam_x" not in code and "cam_y" not in code


# ── Tick d'animation ──────────────────────────────────────────────────

_KW = dict(sym="sprite_Hero", has_frame_sfx=False, has_frame_direct_sfx=False,
           event_lines=None, has_frame_events=False, actor_sym="a")


def test_le_tick_d_une_apparence_est_le_bloc_d_avant():
    assert anim_tick_variants(4, 1, [_KW]) == anim_tick_lines(4, entry=1, **_KW)


def test_les_quatre_premieres_lignes_du_tick_sont_le_recalcul_de_direction():
    """`anim_tick_variants` les partage entre apparences en les découpant : si le
    bloc bouge, ce test l'annonce au lieu de laisser émettre un tick tronqué."""
    tete = anim_tick_lines(4, entry=1, **_KW)[:4]
    assert "auto_dir" in tete[0] and "dir_x=" in tete[1] and "dir_y=" in tete[2]
    assert tete[3].strip() == "}"
    assert "static const s8 _dlut" not in "\n".join(tete)


def test_deux_apparences_partagent_la_direction_et_ont_chacune_leurs_tables():
    code = "\n".join(anim_tick_variants(4, 1, [_KW, {**_KW, "sym": "sprite_Hurt"}]))
    assert code.count("if(g_oam_entries[1].auto_dir") == 1          # commun, une seule fois
    assert "switch(g_oam_entries[1].appearance)" in code
    assert "sprite_Hero_state_start" in code and "sprite_Hurt_state_start" in code
    # Chaque apparence choisit sa direction dans SES tables (plus d'étiquette `goto` : le
    # repli est un `if` imbriqué) ; le côté regardé, lui, est mis à jour une seule fois.
    assert "goto" not in code
    assert code.count("int _hd=") == 2
    assert code.count(".face_x=g_actors[4].dir_x;") == 1
