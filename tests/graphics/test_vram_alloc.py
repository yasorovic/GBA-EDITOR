"""Allocation de la VRAM BG — `codegen/vram_alloc.py`.

Ce module décide où atterrissent, dans 64 Ko découpés de deux façons qui se
recouvrent, les tuiles des fonds, leurs cartes, et celles du texte. Une erreur
n'y produit ni exception ni message : elle donne une ROM dont un décor se
repeint tout seul quelques tuiles trop loin. C'est le premier des trois modules
où se tromper est SILENCIEUX — d'où ces tests.

Deux familles d'assertions :

- des **cas nommés**, qui figent ce que le module promet en toutes lettres ;
- un **balayage** de ~3000 scènes tirées au sort (graine fixe), qui vérifie les
  trois invariants que le placement ne doit jamais violer : le garde-fou
  « jamais pire que l'historique », l'absence de recouvrement, et la tuile 0
  laissée libre au texte.

Le balayage vaut plus que sa taille ne le suggère : les cas de bord de cet
allocateur ne sont pas des valeurs rondes mais des RENCONTRES — une carte de 4
blocs et un fond de 1024 tuiles dans le même charblock, que personne n'écrit à
la main.
"""
from __future__ import annotations

import random

import pytest

from codegen.vram_alloc import (
    BLOCKS, BLOCKS_PER_CBB, BLOCK_TILES, REACH_BLOCKS,
    VramLayout, scene_layout, tiles_to_blocks, _legacy_layout, _free_run_high,
)


# ── Géométrie de base ─────────────────────────────────────────────

@pytest.mark.parametrize("tiles, blocks", [
    (0, 0), (1, 1), (63, 1), (64, 1), (65, 2), (128, 2), (1024, 16),
    (-5, 0),        # une taille négative ne réserve rien, elle ne plante pas
])
def test_tiles_to_blocks(tiles, blocks):
    assert tiles_to_blocks(tiles) == blocks


def test_geometrie_gba():
    """Les constantes DÉCRIVENT le matériel : si l'une bouge, c'est une erreur
    de frappe, pas une évolution."""
    assert BLOCK_TILES == 64            # 2 Ko / 32 octets par tuile 4bpp
    assert BLOCKS == 32                 # 64 Ko de VRAM BG
    assert BLOCKS_PER_CBB == 8          # charblock de 16 Ko
    assert REACH_BLOCKS == 16           # index de tuile sur 10 bits


# ── Recherche d'un trou ───────────────────────────────────────────

def test_free_run_high_sert_par_le_haut():
    """Servir par le haut est ce qui laisse le bas des charblocks aux fonds,
    qui n'ont pas le choix de leur base."""
    libre = [None] * 8
    assert _free_run_high(libre, 0, 8, 2) == 6


def test_free_run_high_saute_les_blocs_pris():
    occupied = [None, None, "x", None, None, None, "y", None]
    assert _free_run_high(occupied, 0, 8, 3) == 3    # [3,6) — au-dessus, 7 seul
    assert _free_run_high(occupied, 0, 8, 1) == 7


def test_free_run_high_rend_none_si_ca_ne_tient_pas():
    occupied = [None, "x", None, "y", None]
    assert _free_run_high(occupied, 0, 5, 2) is None


# ── Placement historique ──────────────────────────────────────────

def test_placement_historique_colle_la_map_a_la_fin_de_son_charblock():
    """C'est le défaut que l'allocateur corrige : la carte du layer 0, posée à
    la fin du charblock 0, mure la croissance du fond qu'elle sert."""
    lay = _legacy_layout({0: 512}, {0: 2}, text_bg=1, text_tiles=64)
    assert lay.legacy is True
    assert lay.map_sbb[0] == 6                       # 8 - 2, dans le CBB 0
    assert lay.budget[0] == 6 * BLOCK_TILES          # 384 tuiles, pas 1024
    assert (lay.text_cbb, lay.text_base, lay.text_sbb) == (1, 1, 15)


def test_sans_layer_de_texte_on_reste_en_historique():
    """`text_bg == -1` : rien à glisser dans les trous, donc rien à recalculer."""
    lay = scene_layout({0: 256}, {0: 1}, text_bg=-1, text_tiles=0)
    assert lay.legacy is True


# ── Ce que le placement calculé apporte ───────────────────────────

def test_le_calcule_debloque_la_croissance_du_fond():
    """Même scène qu'au-dessus : en sortant la carte du charblock 0, le fond
    récupère sa portée de 10 bits au lieu de buter sur elle."""
    lay = scene_layout({0: 512}, {0: 2}, text_bg=1, text_tiles=64)
    assert lay.legacy is False
    assert lay.budget[0] > _legacy_layout({0: 512}, {0: 2}, 1, 64).budget[0]
    assert lay.map_sbb[0] >= BLOCKS_PER_CBB          # sortie du CBB 0


def test_budget_borne_par_la_portee_10_bits():
    """Un layer voit 1024 tuiles depuis SA base — 16 blocs, jamais plus, même
    si toute la VRAM au-dessus est libre."""
    lay = scene_layout({0: 64}, {0: 1}, text_bg=3, text_tiles=0)
    assert lay.budget[0] <= REACH_BLOCKS * BLOCK_TILES


def test_budget_borne_par_la_fin_de_la_vram_bg():
    """Au-delà du charblock 3 commence la VRAM des sprites : le layer 2 ne peut
    pas croître de 16 blocs, il n'en reste que 16 au total au-dessus de lui."""
    lay = scene_layout({2: 64}, {2: 1}, text_bg=0, text_tiles=0)
    assert lay.budget[2] <= (BLOCKS - 2 * BLOCKS_PER_CBB) * BLOCK_TILES


def test_un_fond_trop_gros_rend_un_budget_insuffisant():
    """Ce module n'a pas de mot pour « impossible » : à un fond qui ne rentre
    pas, il rend un budget PLUS PETIT que demandé. C'est ce signal, et lui seul,
    que `rom_build._check_bg_tile_budget` transforme en build bloqué — d'où
    l'importance qu'il ne soit jamais optimiste.

    900 tuiles sur BG3 : son charblock est le dernier, rien ne peut croître
    au-dessus, le plafond est de 512."""
    lay = scene_layout({3: 900}, {3: 4}, text_bg=1, text_tiles=64)
    assert lay.budget[3] < 900
    assert lay.budget[3] <= _plafond_physique(3)


def test_la_tuile_zero_du_bloc_de_texte_reste_libre():
    """`text_clear` pose la tuile 0 du bloc du texte : un texte calé pile sur la
    base du charblock la mangerait."""
    for text_tiles in (32, 64, 200, 512):
        lay = scene_layout({}, {}, text_bg=0, text_tiles=text_tiles)
        assert lay.text_base >= 1


# ── Multi-slot d'UI (v0.12) ───────────────────────────────────────

def test_multi_slot_ui_une_map_par_slot_glyphes_partages():
    """Deux slots d'UI dans une scène : chacun reçoit SA map (SBB distinct), mais
    les glyphes restent dans UN seul charblock partagé (`text_cbb`)."""
    lay = scene_layout({}, {}, text_bg=1, text_tiles=64, ui_slots=[1, 2])
    assert set(lay.ui_sbb) == {1, 2}
    assert lay.ui_sbb[1] != lay.ui_sbb[2]      # deux maps distinctes
    assert lay.text_sbb == lay.ui_sbb[1]       # le primaire est text_bg


def test_mono_slot_reste_identique_sans_ui_slots():
    """`ui_slots=None` reproduit le comportement mono-slot : `ui_sbb` ne porte que
    le slot primaire, à la place de `text_sbb`."""
    a = scene_layout({0: 256}, {0: 1}, text_bg=1, text_tiles=64)
    b = scene_layout({0: 256}, {0: 1}, text_bg=1, text_tiles=64, ui_slots=[1])
    assert a.ui_sbb == {1: a.text_sbb}
    assert (a.text_sbb, a.text_cbb) == (b.text_sbb, b.text_cbb)


# ── Invariants, sur un balayage de scènes tirées au sort ──────────

def _occupancy(lay: VramLayout, slots: dict, map_blocks: dict,
               text_tiles: int) -> list:
    """Reconstruit qui occupe chacun des 32 blocs de 2 Ko, d'après le plan.

    Le plan ne dit pas explicitement où tout atterrit : les tuiles d'un fond
    sont ANCRÉES à la base de leur charblock (le champ CharBlock de BGxCNT ne
    fait que 2 bits), et celles du texte se déduisent de `text_cbb`+`text_base`.
    Rejouer ce calcul ici est ce qui permet de constater un recouvrement.

    Un fond occupe ce que le plan lui ACCORDE, pas ce que l'appelant a demandé :
    au-delà du budget le build est bloqué en amont, donc cette VRAM-là n'existe
    dans aucune ROM (cf. `test_un_fond_trop_gros_rend_un_budget_insuffisant`)."""
    occ: list = [None] * BLOCKS
    conflits = []

    def poser(debut, n, quoi):
        for b in range(debut, debut + n):
            if not 0 <= b < BLOCKS:
                conflits.append(f"{quoi} sort de la VRAM BG (bloc {b})")
                continue
            if occ[b] is not None:
                conflits.append(f"{quoi} recouvre {occ[b]} au bloc {b}")
            occ[b] = quoi

    for slot, n_tiles in slots.items():
        tenu = min(n_tiles, lay.budget[slot])
        poser(slot * BLOCKS_PER_CBB, tiles_to_blocks(tenu), f"tuiles BG{slot}")
    for slot, n in map_blocks.items():
        if slot in slots:
            poser(lay.map_sbb[slot], n, f"carte BG{slot}")
    poser(lay.text_sbb, 1, "carte texte")
    if text_tiles:
        debut = lay.text_cbb * BLOCKS_PER_CBB + lay.text_base // BLOCK_TILES
        poser(debut, tiles_to_blocks(text_tiles), "tuiles texte")
    return conflits


def _plafond_physique(slot: int) -> int:
    """Tuiles qu'un layer peut au MIEUX occuper : de la base de son charblock
    jusqu'à la fin de la VRAM BG, sans dépasser sa portée de 10 bits."""
    return min(REACH_BLOCKS, BLOCKS - slot * BLOCKS_PER_CBB) * BLOCK_TILES


def _scenes_au_hasard(n: int):
    """Scènes plausibles : jusqu'à 3 layers porteurs d'image, un layer d'UI, des
    fonds de toutes tailles. Graine fixe — un échec se rejoue à l'identique.

    Les tailles sont bornées au plafond physique du layer : au-delà, la scène
    n'est pas allouable du tout et ce n'est pas ce module qui le dit (cf.
    `test_un_fond_trop_gros_rend_un_budget_insuffisant`)."""
    rng = random.Random(20260813)
    for _ in range(n):
        text_bg = rng.choice([0, 1, 2, 3])
        candidats = [s for s in (0, 1, 2, 3) if s != text_bg]
        rng.shuffle(candidats)
        porteurs = candidats[:rng.randint(0, 3)]
        slots = {s: min(rng.choice([32, 64, 200, 256, 512, 900, 1024]),
                        _plafond_physique(s))
                 for s in porteurs}
        map_blocks = {s: rng.choice([1, 2, 4]) for s in porteurs}
        text_tiles = rng.choice([0, 32, 64, 240, 512])
        yield slots, map_blocks, text_bg, text_tiles


CAS = list(_scenes_au_hasard(3000))


def test_garde_fou_jamais_pire_que_l_historique():
    """L'invariant que le module s'impose en toutes lettres : « une allocation
    plus fine ne doit jamais casser un projet qui passait »."""
    for slots, map_blocks, text_bg, text_tiles in CAS:
        lay = scene_layout(slots, map_blocks, text_bg, text_tiles)
        ref = _legacy_layout(slots, map_blocks, text_bg, text_tiles)
        for slot in slots:
            assert lay.budget[slot] >= ref.budget[slot], (
                f"BG{slot} perd du budget : {lay.budget[slot]} < "
                f"{ref.budget[slot]} — {slots=} {map_blocks=} {text_bg=} "
                f"{text_tiles=} ({lay.note})")


def test_aucun_recouvrement_dans_un_plan_calcule():
    """Deux locataires dans le même bloc de 2 Ko, c'est un décor qui se repeint
    à l'exécution. Seul le plan CALCULÉ est jugé : l'historique se recouvre
    lui-même par endroits, c'est précisément ce qu'il coûte."""
    for slots, map_blocks, text_bg, text_tiles in CAS:
        lay = scene_layout(slots, map_blocks, text_bg, text_tiles)
        if lay.legacy:
            continue
        conflits = _occupancy(lay, slots, map_blocks, text_tiles)
        assert not conflits, (f"{conflits} — {slots=} {map_blocks=} "
                              f"{text_bg=} {text_tiles=}")


def test_le_budget_annonce_est_reellement_libre():
    """Le budget est ce que le build donnera au fond : s'il couvre un bloc pris
    par une carte, le dépassement ne se verra qu'à l'écran."""
    for slots, map_blocks, text_bg, text_tiles in CAS:
        lay = scene_layout(slots, map_blocks, text_bg, text_tiles)
        if lay.legacy:
            continue
        occ: list = [None] * BLOCKS
        for slot, n in map_blocks.items():
            if slot in slots:
                for b in range(lay.map_sbb[slot], lay.map_sbb[slot] + n):
                    occ[b] = f"carte BG{slot}"
        occ[lay.text_sbb] = "carte texte"
        if text_tiles:
            debut = lay.text_cbb * BLOCKS_PER_CBB + lay.text_base // BLOCK_TILES
            for b in range(debut, debut + tiles_to_blocks(text_tiles)):
                if b < BLOCKS:
                    occ[b] = "tuiles texte"
        for slot in slots:
            base = slot * BLOCKS_PER_CBB
            for b in range(base, base + tiles_to_blocks(lay.budget[slot])):
                assert b < BLOCKS, f"budget de BG{slot} au-delà de la VRAM BG"
                assert occ[b] is None, (
                    f"le budget de BG{slot} couvre {occ[b]} au bloc {b} — "
                    f"{slots=} {map_blocks=} {text_bg=} {text_tiles=}")


def test_le_plan_reste_dans_la_vram_bg():
    """Cartes et tuiles de texte, elles, ne sont bornées par rien d'autre que
    cet invariant : au-delà du bloc 31 on écrit dans la VRAM des sprites."""
    for slots, map_blocks, text_bg, text_tiles in CAS:
        lay = scene_layout(slots, map_blocks, text_bg, text_tiles)
        assert 0 <= lay.text_sbb < BLOCKS
        assert 0 <= lay.text_cbb <= 3
        assert lay.text_base < BLOCK_TILES * BLOCKS_PER_CBB
        for slot in slots:
            assert 0 <= lay.map_sbb[slot] < BLOCKS
            assert lay.map_sbb[slot] + map_blocks[slot] <= BLOCKS
