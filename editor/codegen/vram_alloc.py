"""editor/codegen/vram_alloc.py — allocation de la VRAM BG, par scène.

**Le problème.** 64 Ko de VRAM BG sont découpés de DEUX façons qui se
recouvrent : 4 charblocks de 16 Ko (les tuiles) et 32 screenblocks de 2 Ko (les
maps). Le screenblock *n* vit dans le charblock *n/8* — poser une map, c'est
manger de la place à tuiles. Tout raisonner en **blocs de 2 Ko** (= 64 tuiles
4bpp) est la seule façon de voir les deux à la fois ; c'est l'unité de ce module.

**L'asymétrie qui dicte tout.** Un fond ne peut PAS commencer où il veut : le
champ CharBlock de `BGxCNT` fait 2 bits (4 valeurs), et grit numérote ses tuiles
à partir de 0 sans décalage. Un fond est donc collé à la base de son charblock.
Le TEXTE, lui, se pose où on veut : c'est nous qui écrivons ses entrées de map,
en y ajoutant `g_text_tile_base`. Le texte est le locataire souple, le fond le
locataire rigide — donc c'est le texte qu'on glisse dans les trous.

**La portée.** L'index de tuile d'une entrée de map fait 10 bits : un layer voit
1024 tuiles depuis la base de SON charblock, soit deux charblocks. Il peut donc
déborder sur le suivant — à condition que rien n'occupe l'espace au-dessus, la
croissance étant contiguë. C'est là que le placement historique échouait : la
map d'un layer, posée à la fin de son propre charblock, murait sa croissance.

**Garde-fou.** Le placement calculé n'est retenu que s'il donne à CHAQUE layer au
moins ce que lui donnait le placement historique. Sinon on retombe entièrement
sur ce dernier. Une allocation plus fine ne doit jamais casser un projet qui
passait.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Géométrie ─────────────────────────────────────────────────────
BLOCK_BYTES     = 2048              # 1 screenblock
BLOCK_TILES     = BLOCK_BYTES // 32  # 64 tuiles 4bpp
BLOCKS          = 32                 # 64 Ko de VRAM BG
BLOCKS_PER_CBB  = 8                  # 16 Ko
REACH_TILES     = 1024               # index de tuile sur 10 bits
REACH_BLOCKS    = REACH_TILES // BLOCK_TILES   # 16 blocs


def tiles_to_blocks(n: int) -> int:
    return (max(0, n) + BLOCK_TILES - 1) // BLOCK_TILES


@dataclass
class VramLayout:
    """Résultat d'allocation pour une scène."""
    map_sbb:   dict = field(default_factory=dict)  # bg_slot -> SBB de sa map
    budget:    dict = field(default_factory=dict)  # bg_slot -> tuiles dispo
    text_cbb:  int = 0
    text_base: int = 1     # tuile de départ du texte, RELATIVE à text_cbb
    text_sbb:  int = 7     # SBB de la map du slot d'UI PRIMAIRE (= ui_sbb[primary])
    # Un SBB de map par slot BG d'UI utilisé par la scène (v0.12). Les glyphes,
    # eux, restent dans UN seul charblock (`text_cbb`) que tous les slots partagent
    # via leur BGxCNT — d'où plusieurs maps mais un seul jeu de tuiles.
    ui_sbb:    dict = field(default_factory=dict)   # slot d'UI -> SBB de sa map
    legacy:    bool = True  # True = placement historique (repli ou pas de gain)
    used_blocks: int = 0    # blocs de 2 Kio occupés (tuiles des fonds + maps + texte)
    note:      str = ""     # pourquoi ce placement — pour le log de build


# ── Placement historique ──────────────────────────────────────────

def _ui_slot_list(text_bg: int, ui_slots) -> list:
    """Slots d'UI à réserver : la liste donnée, sinon le seul `text_bg` (l'ancien
    comportement mono-slot). Bornés à 0-3."""
    src = ui_slots if ui_slots is not None else [text_bg]
    return [s for s in src if s in (0, 1, 2, 3)]


def _legacy_layout(slots: dict, map_blocks: dict, text_bg: int,
                   text_tiles: int, ui_slots=None) -> VramLayout:
    """Ce que faisait le code avant l'allocateur : CBB = bg_slot, map dans les
    derniers SBB de son propre charblock, texte à la tuile 1 de SON charblock.
    Multi-slot (v0.12) : chaque slot d'UI a sa map dans son propre charblock ; les
    glyphes restent dans celui du slot primaire (`text_bg`)."""
    lay = VramLayout(legacy=True, note="placement historique")
    # Même comptage que le placement calculé : tuiles de chaque fond, sa map, une
    # map par slot d'UI, le texte. Le placement historique ne les chevauche pas
    # quand il passe ; sinon le garde-fou du build bloque avant.
    lay.used_blocks = (sum(tiles_to_blocks(n) for n in slots.values())
                       + sum(map_blocks[s] for s in slots)
                       + len(_ui_slot_list(text_bg, ui_slots))
                       + tiles_to_blocks(text_tiles))
    for slot in slots:
        n = map_blocks[slot]
        lay.map_sbb[slot] = slot * BLOCKS_PER_CBB + (BLOCKS_PER_CBB - n)
        lay.budget[slot] = (BLOCKS_PER_CBB - n) * BLOCK_TILES
    for us in _ui_slot_list(text_bg, ui_slots):
        lay.ui_sbb[us] = us * BLOCKS_PER_CBB + (BLOCKS_PER_CBB - 1)
    if text_bg in (0, 1, 2, 3):
        lay.text_cbb = text_bg
        lay.text_base = 1
        lay.text_sbb = lay.ui_sbb.get(text_bg, text_bg * BLOCKS_PER_CBB + (BLOCKS_PER_CBB - 1))
    return lay


# ── Placement calculé ─────────────────────────────────────────────

def _free_run_high(occupied: list, start: int, stop: int, n: int):
    """Indice du run libre de `n` blocs le PLUS HAUT dans [start, stop).
    None si aucun. On sert par le haut pour laisser le bas — d'où partent les
    fonds — aussi contigu que possible."""
    for base in range(stop - n, start - 1, -1):
        if base < start:
            break
        if all(occupied[b] is None for b in range(base, base + n)):
            return base
    return None


def scene_layout(slots: dict, map_blocks: dict, text_bg: int,
                 text_tiles: int, ui_slots=None) -> VramLayout:
    """Alloue la VRAM BG d'une scène.

    `slots`      : {bg_slot: nombre de tuiles du fond} — layers porteurs d'image.
    `map_blocks` : {bg_slot: nombre de blocs qu'occupe sa map} (1, 2 ou 4).
    `text_bg`    : slot d'UI PRIMAIRE (0-3), ou -1 — celui qui porte les glyphes.
    `text_tiles` : tuiles à réserver au texte (glyphes ou surface).
    `ui_slots`   : TOUS les slots BG d'UI de la scène (v0.12) ; None = `[text_bg]`
                   (mono-slot, l'ancien comportement). Chacun reçoit sa propre map
                   (SBB) ; les glyphes restent partagés dans `text_cbb`.

    Un slot d'UI ne porte jamais d'image (garanti par le validateur), donc il n'est
    jamais dans `slots`."""
    legacy = _legacy_layout(slots, map_blocks, text_bg, text_tiles, ui_slots)
    if text_bg not in (0, 1, 2, 3):
        return legacy
    ui = _ui_slot_list(text_bg, ui_slots)

    occupied: list = [None] * BLOCKS

    # 1. Tuiles des fonds — ANCRÉES à la base de leur charblock (hardware).
    for slot, n_tiles in slots.items():
        base = slot * BLOCKS_PER_CBB
        for b in range(base, base + tiles_to_blocks(n_tiles)):
            if b < BLOCKS:
                occupied[b] = f"tiles{slot}"

    # 2. Maps — servies par le HAUT, hors du chemin de croissance des fonds.
    #    C'est tout le correctif : posées à la fin de leur propre charblock,
    #    elles muraient la croissance du layer qu'elles servent.
    lay = VramLayout(legacy=False, note="per-scene allocation")
    for slot in sorted(slots, reverse=True):
        n = map_blocks[slot]
        pos = _free_run_high(occupied, 0, BLOCKS, n)
        if pos is None:
            return legacy                     # VRAM saturée : on ne bricole pas
        for b in range(pos, pos + n):
            occupied[b] = f"map{slot}"
        lay.map_sbb[slot] = pos

    # 3. Une map par slot d'UI (toujours 32×32, donc 1 bloc chacune). Les glyphes
    #    (étape 4) restent partagés : plusieurs maps, un seul jeu de tuiles.
    for us in ui:
        pos = _free_run_high(occupied, 0, BLOCKS, 1)
        if pos is None:
            return legacy
        occupied[pos] = f"uimap{us}"
        lay.ui_sbb[us] = pos
    lay.text_sbb = lay.ui_sbb.get(text_bg, lay.text_sbb)   # SBB du slot primaire

    # 4. Tuiles du texte — le locataire SOUPLE : on le glisse dans le trou le
    #    plus haut, pour laisser le bas des charblocks aux fonds. Il doit tenir
    #    dans la portée de son propre charblock (base + n < 1024 tuiles).
    n_text = tiles_to_blocks(text_tiles)
    if n_text:
        pos = _free_run_high(occupied, 0, BLOCKS, n_text)
        if pos is None:
            return legacy
        for b in range(pos, pos + n_text):
            occupied[b] = "tilestext"
        lay.text_cbb = pos // BLOCKS_PER_CBB
        lay.text_base = (pos % BLOCKS_PER_CBB) * BLOCK_TILES
        # La tuile 0 du bloc du texte doit rester vide en mono : c'est elle que
        # pose `text_clear`. Un texte pile à la base du charblock la mangerait.
        if lay.text_base == 0:
            lay.text_base = 1
    else:
        lay.text_cbb = text_bg
        lay.text_base = 1

    lay.used_blocks = sum(1 for o in occupied if o is not None)

    # 5. Budget de chaque fond : de sa base jusqu'au premier bloc occupé
    #    au-dessus, borné par la portée 10 bits ET par la fin de la VRAM BG
    #    (au-delà du charblock 3 commence la VRAM des sprites).
    for slot in slots:
        base = slot * BLOCKS_PER_CBB
        stop = min(base + REACH_BLOCKS, BLOCKS)
        b = base
        while b < stop and (occupied[b] is None or occupied[b] == f"tiles{slot}"):
            b += 1
        lay.budget[slot] = (b - base) * BLOCK_TILES

    # 6. Garde-fou : jamais pire que l'existant.
    for slot in slots:
        if lay.budget[slot] < legacy.budget[slot]:
            legacy.note = ("historical fallback — the computed placement reduced the "
                           f"budget of BG{slot}")
            return legacy
    return lay
