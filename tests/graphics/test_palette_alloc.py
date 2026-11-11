"""Allocation des banques de palette — `codegen/palette_alloc.py`.

Deuxième module où une erreur ne dit rien : elle sort une ROM aux mauvaises
couleurs. Le module est en outre la **source de vérité unique** de deux
consommateurs qui ne se parlent pas (grit `-mp` dans `rom_build`, `g_pal_*` dans
`main_gen`) : ils ne restent d'accord que parce qu'ils rappellent la même
fonction et qu'elle est déterministe. C'est donc aussi ce que ces tests fixent.

Le pool BG sert de terrain d'essai — il exerce les deux modes d'allocation (slot
unique et BLOC contigu pour un fond compressé) là où le pool OBJ n'a que le
premier.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.models.background import BackgroundAsset, BackgroundLayer
from core.models.palette import OWN_PAL_BANK, PaletteBank, RESERVED_SLOT_COLOR
from core.models.scene import Scene
from core.palette_presets import DEFAULT_PAL_BANK_COLORS
from core.project import Project
from oam_fixtures import faire_naitre
from codegen.palette_alloc import (
    SceneBankLayout, scene_bank_layout, _find_free_block,
    _sprite_bank_content,
)


# ── Fabriques ─────────────────────────────────────────────────────

def _couleurs(graine: int) -> list[int]:
    """16 couleurs BGR555 distinctes et reproductibles — le CONTENU est ce qui
    déduplique une banque, il doit donc différer d'une graine à l'autre."""
    return [(graine * 97 + i * 31) & 0x7FFF for i in range(16)]


@pytest.fixture
def projet(tmp_path) -> Project:
    """Un projet vide, en mémoire. Aucun sidecar n'est lu : les registres se
    remplissent à la main, ce qui rend chaque cas lisible d'un bloc."""
    return Project(tmp_path)


def _ajouter_palette(p: Project, nom: str, graine: int) -> PaletteBank:
    bank = PaletteBank(name=nom, colors=_couleurs(graine))
    p.palettes.append(bank)
    return bank


def _ajouter_fond_compresse(p: Project, nom: str, sous_palettes: list[list[int]],
                            bpp: int = 4) -> BackgroundAsset:
    """Un fond COMPRESSÉ : il porte ses propres sous-palettes et réclame donc un
    bloc de banques contiguës, pas un slot."""
    ba = BackgroundAsset(name=nom, asset=f"{nom}.png", palettes=sous_palettes,
                         tileset=["0" * 64], tilemap=[0], tiles_w=1, tiles_h=1,
                         bpp=bpp)
    p.backgrounds.append(ba)
    return ba


def _scene_avec_fonds(*noms: str) -> Scene:
    s = Scene(name="Test")
    s.background_layers = [
        BackgroundLayer(background_name=nom, bg_slot=i, pal_bank=OWN_PAL_BANK)
        for i, nom in enumerate(noms)
    ]
    return s


# ── Recherche d'un bloc contigu ───────────────────────────────────

def test_find_free_block_prend_le_trou_le_plus_haut_assez_grand():
    """La recherche part du bout HAUT (les palettes propres descendent vers 0) :
    on prend le bloc contigu le plus proche de la banque 15 qui tient."""
    slots = [None] * 16
    slots[14] = _couleurs(1)
    slots[11] = _couleurs(2)
    assert _find_free_block(slots, 1) == 15    # 15 libre, le plus haut
    assert _find_free_block(slots, 2) == 12    # [12,14) — sous la banque 14 prise
    assert _find_free_block(slots, 4) == 7     # [12,16) coupé par 14, on descend


def test_find_free_block_exige_la_contiguite():
    """Les N sous-palettes d'un fond compressé occupent des banques CONSÉCUTIVES
    (le champ SE_PALBANK d'une tuile est un index de banque, pas une table
    d'indirection) : quatre trous épars ne valent pas un bloc de quatre."""
    slots = [None if i % 2 == 0 else _couleurs(i) for i in range(16)]
    assert _find_free_block(slots, 2) is None
    assert _find_free_block(slots, 1) == 14    # bout haut : la banque libre la plus haute


def test_find_free_block_rend_none_quand_rien_ne_tient():
    slots = [_couleurs(i) for i in range(16)]
    assert _find_free_block(slots, 1) is None


def test_find_free_block_couvre_les_seize_banques():
    """Un fond de 16 sous-palettes tient dans une scène vierge, et lui seul."""
    assert _find_free_block([None] * 16, 16) == 0
    presque = [None] * 16
    presque[15] = _couleurs(1)
    assert _find_free_block(presque, 16) is None


def test_find_free_block_traite_zero_comme_un():
    """Un asset sans sous-palette ne réclame pas « rien » : le rendre `0`
    donnerait un offset valide sur une banque occupée. La recherche part du bout
    haut (cf. `_find_free_block`), donc la banque libre la plus loin (15) est
    rendue — jamais la banque 0 occupée."""
    slots = [None] * 16
    slots[0] = _couleurs(1)
    assert _find_free_block(slots, 0) == 15


# ── Contenu d'une banque de palette propre ────────────────────────

def test_une_palette_de_sprite_reserve_le_slot_zero_dans_LES_DEUX_pools():
    """Le préfixe se décide sur la FORME de la source, pas sur le pool.

    Le BG legacy passe par `extract_palette_from_image`, qui porte déjà son
    slot 0. Un SPRITE, même posé en cible BG (image d'interface), vient des
    métadonnées, sans slot 0, alors que l'index 0 d'une tuile 4bpp est
    transparent en BG comme en OBJ. Il lui faut donc le préfixe.

    Ce que ça coûtait de se tromper : grit remappe les tuiles sur la forme
    16 slots rendue par `effective_palette_colors` (préfixée), la banque était
    écrite sans — chaque pixel lisait un cran plus loin, et l'image sortait aux
    couleurs de ses voisines."""
    cols = [1, 2, 3]
    assert _sprite_bank_content(cols) == [RESERVED_SLOT_COLOR, 1, 2, 3]


def test_le_sprite_d_une_image_d_UI_en_cible_BG_garde_son_slot_reserve(projet):
    """Le même piège, vu de bout en bout : la banque que la ROM écrira.

    Passe par `scene_bank_layout` plutôt que par le seul helper, parce que c'est
    l'assemblage qui se trompait — le pool BG mêle deux formes de liste et ne
    peut pas les traiter d'un seul geste."""
    from core.models.sprite import SpriteAsset
    from core.models.ui_region import UIImage, UILayout

    couleurs = _couleurs(7)[:8]          # forme « métadonnées » : sans slot 0
    projet.sprites.append(SpriteAsset(name="Selector", asset="selector.png",
                                      own_palette=list(couleurs)))
    lay = UILayout(name="Menu", elements=[UIImage(name="Cusor",
                                                 sprite_name="Selector")])
    projet.ui_layouts.append(lay)
    scene = Scene(name="Titre", ui_layouts=["Menu"])

    layout = scene_bank_layout(projet, scene, "bg")
    banque = layout.slot_colors[layout.bank_index(OWN_PAL_BANK, list(couleurs))]
    assert banque == [RESERVED_SLOT_COLOR] + list(couleurs)


# ── T5 : palettes propres des pools, per-scène ────────────────────

def test_pool_palette_propre_reservee_par_scene(projet):
    """Une scène ne réserve de banque OBJ que pour les prefabs
    QU'ELLE poole. Deux scènes qui poolent des prefabs différents ne se
    contaminent pas, et une scène qui n'en poole aucun n'en réserve aucune — fin
    du slot global réservé partout qu'imposait l'ancien `spawn_X`."""
    from core.models.sprite import SpriteAsset
    from core.models.components import SpriteComponent
    from core.models.scene import Prefab

    colsA, colsB = _couleurs(3)[:5], _couleurs(9)[:5]
    projet.sprites.append(SpriteAsset(name="SparkSpr", asset="a.png", own_palette=list(colsA)))
    projet.sprites.append(SpriteAsset(name="BulletSpr", asset="b.png", own_palette=list(colsB)))
    spark, bullet = Prefab(name="Spark"), Prefab(name="Bullet")
    spark.actor.components  = [SpriteComponent(sprite_name="SparkSpr")]
    bullet.actor.components = [SpriteComponent(sprite_name="BulletSpr")]
    projet.prefabs.items = [spark, bullet]

    fount, play, menu = Scene(name="Fountain"), Scene(name="Play"), Scene(name="Menu")
    faire_naitre(projet.root, fount, "Spark")
    faire_naitre(projet.root, play, "Bullet")
    projet.scenes.items = [fount, play, menu]

    lf = scene_bank_layout(projet, fount, "obj")
    lp = scene_bank_layout(projet, play, "obj")
    lm = scene_bank_layout(projet, menu, "obj")
    assert lf.bank_index(OWN_PAL_BANK, list(colsA)) is not None   # Fountain a Spark
    assert lf.bank_index(OWN_PAL_BANK, list(colsB)) is None       # mais pas Bullet
    assert lp.bank_index(OWN_PAL_BANK, list(colsB)) is not None   # Play a Bullet
    assert lp.bank_index(OWN_PAL_BANK, list(colsA)) is None       # mais pas Spark
    assert lm.bank_count() == 0                                    # Menu, aucune


def test_pool_palette_propre_dedup_avec_un_acteur(projet):
    """Un prefab poolé et un acteur aux MÊMES couleurs partagent une banque — le
    prefab est un consommateur de palette propre comme un autre depuis T5."""
    from core.models.sprite import SpriteAsset
    from core.models.components import SpriteComponent
    from core.models.scene import Prefab, Actor

    cols = _couleurs(5)[:5]
    projet.sprites.append(SpriteAsset(name="Shared", asset="s.png", own_palette=list(cols)))
    pf = Prefab(name="Bullet"); pf.actor.components = [SpriteComponent(sprite_name="Shared")]
    projet.prefabs.items = [pf]
    a = Actor(name="Hero"); a.components = [SpriteComponent(sprite_name="Shared")]
    scene = Scene(name="S", actors=[a])
    faire_naitre(projet.root, scene, "Bullet")
    projet.scenes.items = [scene]

    lay = scene_bank_layout(projet, scene, "obj")
    assert lay.bank_count() == 1                                   # une seule banque
    assert lay.bank_index(OWN_PAL_BANK, list(cols)) is not None


# ── Lecture du résultat ───────────────────────────────────────────

def test_bank_index_d_une_palette_referencee():
    lay = SceneBankLayout([None] * 16, {})
    assert lay.bank_index(5, None) == 5
    assert lay.bank_index(0, None) == 0
    assert lay.bank_index(16, None) is None      # hors des 16 banques
    assert lay.bank_index(-2, None) is None      # ni OWN, ni un slot


def test_bank_index_d_une_palette_propre():
    cols = _couleurs(7)
    lay = SceneBankLayout([None] * 16, {tuple(cols): 3})
    assert lay.bank_index(OWN_PAL_BANK, cols) == 3
    assert lay.bank_index(OWN_PAL_BANK, _couleurs(8)) is None   # jamais allouée
    assert lay.bank_index(OWN_PAL_BANK, []) is None             # rien à allouer


def test_bank_count_ne_compte_que_les_banques_remplies():
    slots = [None] * 16
    slots[0], slots[9] = _couleurs(1), _couleurs(2)
    assert SceneBankLayout(slots, {}).bank_count() == 2


# ── Allocation d'une scène, de bout en bout ───────────────────────

def test_les_palettes_referencees_gardent_leur_index(projet):
    """Une palette référencée n'est pas allouée, elle est POSÉE : son index dans
    la sélection de la scène EST son index matériel."""
    ciel = _ajouter_palette(projet, "Ciel", 1)
    sol = _ajouter_palette(projet, "Sol", 2)
    scene = Scene(name="Test")
    scene.active_bg_palettes = ["Ciel", "", "Sol"]

    lay = scene_bank_layout(projet, scene, "bg")
    # Comparé à `bank.colors`, pas aux couleurs de la fabrique : `PaletteBank`
    # force son index 0 vers RESERVED_SLOT_COLOR, et c'est la banque telle
    # qu'elle EST qui doit atterrir dans le slot.
    assert lay.slot_colors[0] == ciel.colors
    assert lay.slot_colors[2] == sol.colors
    assert lay.slot_colors[1] is None
    assert lay.bank_index(2, None) == 2


def test_une_scene_vide_n_invente_aucune_couleur(projet):
    """La banque 0 de secours ne se remplit que si la scène a du contenu :
    sinon l'émission de `main_gen` paierait une palette que rien ne lit."""
    lay = scene_bank_layout(projet, Scene(name="Vide"), "bg")
    assert all(c is None for c in lay.slot_colors)
    assert lay.bank_count() == 0


def test_la_banque_zero_reste_libre_sans_debordement(projet):
    """La banque 0 porte le backdrop de la scène (index 0 de PAL_BG_RAM) : tant
    que rien ne déborde, on la laisse LIBRE — les palettes propres descendent du
    bout haut, jamais sur elle (cf. `_find_free_block`)."""
    sol = _ajouter_palette(projet, "Sol", 2)
    scene = Scene(name="Test")
    scene.active_bg_palettes = ["", "Sol"]

    lay = scene_bank_layout(projet, scene, "bg")
    assert lay.slot_colors[0] is None          # backdrop, non écrasé
    assert lay.slot_colors[1] == sol.colors


def test_la_banque_zero_de_secours_se_remplit_au_debordement(projet):
    """Un asset qui DÉBORDE (aucune banque ne l'accueille) retombe sur la banque 0
    au codegen : si elle est encore libre, on la remplit de couleurs PRÉVISIBLES
    plutôt que de laisser l'asset afficher le backdrop ou du garbage."""
    # Banques 1..15 référencées : il ne reste que la banque 0, libre pour le
    # backdrop. Un fond compressé de 2 sous-palettes réclame 2 banques contiguës
    # — impossible — donc il déborde.
    scene = _scene_avec_fonds("Foret")
    scene.active_bg_palettes = [""] + [f"P{i}" for i in range(1, 16)]
    for i in range(1, 16):
        _ajouter_palette(projet, f"P{i}", i + 10)
    _ajouter_fond_compresse(projet, "Foret", [_couleurs(20), _couleurs(21)])

    lay = scene_bank_layout(projet, scene, "bg")
    assert [r.cause for r in lay.refusals] == ["not_enough_banks"]
    assert lay.slot_colors[0] == list(DEFAULT_PAL_BANK_COLORS)
    assert lay.slot_owners[0] == [("fallback colours", "")]


def test_un_fond_compresse_obtient_un_bloc_contigu(projet):
    sous = [_couleurs(10), _couleurs(11), _couleurs(12)]
    ba = _ajouter_fond_compresse(projet, "Foret", sous)

    lay = scene_bank_layout(projet, _scene_avec_fonds("Foret"), "bg")
    banques = lay.bg_banks(ba)
    debut = banques[0]
    assert banques == [debut, debut + 1, debut + 2]
    assert lay.slot_colors[debut:debut + 3] == sous
    assert lay.refusals == []
    assert lay.slot_owners[debut] == [("background", "Foret")]


def test_deux_fonds_aux_memes_couleurs_partagent_leur_bloc(projet):
    """Dédup par CONTENU exact : deux fonds identiques ne paient qu'une fois."""
    sous = [_couleurs(20), _couleurs(21)]
    a = _ajouter_fond_compresse(projet, "Foret", sous)
    b = _ajouter_fond_compresse(projet, "ForetNuit", [list(p) for p in sous])

    lay = scene_bank_layout(projet, _scene_avec_fonds("Foret", "ForetNuit"), "bg")
    assert lay.bg_banks(a) == lay.bg_banks(b)
    assert lay.bank_count() == 2


def test_un_fond_compresse_deborde_faute_de_place(projet):
    """Douze banques référencées, un fond qui en réclame six : il n'en reste que
    quatre, et le dire est tout ce que le module peut faire."""
    scene = _scene_avec_fonds("Foret")
    noms = []
    for i in range(12):
        _ajouter_palette(projet, f"P{i}", i + 1)
        noms.append(f"P{i}")
    scene.active_bg_palettes = noms
    ba = _ajouter_fond_compresse(projet, "Foret", [_couleurs(30 + i) for i in range(6)])

    lay = scene_bank_layout(projet, scene, "bg")
    assert lay.bg_banks(ba) is None
    [refus] = lay.refusals
    assert refus.cause == "not_enough_banks"
    assert refus.request.owners == [("background", "Foret")]
    assert refus.request.banks == 6
    assert refus.free_banks == [12, 13, 14, 15]
    assert lay.slot_owners[0] == [("scene palette", "P0")]


def test_un_fond_prend_des_banques_disjointes_et_sa_carte_les_cite(projet, tmp_path):
    """Il reste DEUX banques (3 et 9), le fond en demande deux : chaque case d'une
    carte 4 bpp désigne sa propre banque, le fond n'a donc pas besoin d'un bloc.
    La carte émise envoie la sous-palette 0 en banque 3 et la 1 en banque 9."""
    from core.models.tile_codec import pack_se, unpack_se
    from codegen import BuildWorker
    from core.toolchain import Toolchain

    scene = _scene_avec_fonds("Foret")
    noms = []
    for i in range(16):
        if i in (3, 9):
            noms.append("")
            continue
        _ajouter_palette(projet, f"P{i}", i + 1)
        noms.append(f"P{i}")
    scene.active_bg_palettes = noms
    sous = [_couleurs(30), _couleurs(31)]
    ba = _ajouter_fond_compresse(projet, "Foret", sous)
    ba.tilemap = [pack_se(0, 0, 0, 0), pack_se(0, 1, 0, 0)]
    ba.tiles_w = 2

    lay = scene_bank_layout(projet, scene, "bg")
    assert lay.refusals == []
    assert lay.bg_banks(ba) == [3, 9]
    assert (lay.slot_colors[3], lay.slot_colors[9]) == (sous[0], sous[1])

    worker = BuildWorker(projet, Toolchain())
    carte = worker._bg_final_tilemap(projet, scene, ba, scene.background_layers[0], lay.bg_banks(ba))
    assert [unpack_se(se)[1] for se in carte] == [3, 9]


def test_une_carte_n_est_partagee_qu_entre_scenes_aux_memes_banques(projet):
    """La carte d'un fond grave ses banques : deux scènes qui le rangent dans des
    banques différentes ne peuvent pas lire la même. Avant, la seconde lisait en
    silence les banques de la première."""
    from codegen.grit_conversion import bg_layer_sym_for

    _ajouter_fond_compresse(projet, "Foret", [_couleurs(70), _couleurs(71)])
    _ajouter_fond_compresse(projet, "Collines", [_couleurs(72), _couleurs(73)])
    seule = Scene(name="Seule", background_layers=[BackgroundLayer(background_name="Foret", bg_slot=0)])
    jumelle = Scene(name="Jumelle", background_layers=[BackgroundLayer(background_name="Foret", bg_slot=0)])
    apres = Scene(name="Apres", background_layers=[
        BackgroundLayer(background_name="Collines", bg_slot=1),
        BackgroundLayer(background_name="Foret", bg_slot=0)])
    autre = Scene(name="Autre", background_layers=[
        BackgroundLayer(background_name="Collines", bg_slot=1),
        BackgroundLayer(background_name="Foret", bg_slot=0)])
    scenes = (seule, jumelle, apres, autre)
    for scene in scenes:
        projet.scenes.append(scene)

    assert scene_bank_layout(projet, seule, "bg").bg_banks(projet.get_background("Foret")) == [14, 15]
    assert scene_bank_layout(projet, apres, "bg").bg_banks(projet.get_background("Foret")) == [12, 13]
    sym = {s.name: bg_layer_sym_for(projet, s, next(L for L in s.background_layers
                                                      if L.background_name == "Foret"))
           for s in scenes}
    assert sym["Seule"] == sym["Jumelle"]
    assert sym["Apres"] == sym["Autre"] != sym["Seule"]


def test_un_refus_nomme_tous_ceux_qui_partagent_les_couleurs(projet):
    """La dédup par contenu regroupe deux fonds identiques en UNE demande : le
    refus doit nommer les deux, sinon le second disparaît du diagnostic."""
    scene = _scene_avec_fonds("Foret", "ForetNuit")
    scene.active_bg_palettes = [f"P{i}" for i in range(15)]
    for i in range(15):
        _ajouter_palette(projet, f"P{i}", i + 1)
    sous = [_couleurs(50), _couleurs(51)]
    _ajouter_fond_compresse(projet, "Foret", sous)
    _ajouter_fond_compresse(projet, "ForetNuit", [list(p) for p in sous])

    [refus] = scene_bank_layout(projet, scene, "bg").refusals
    assert refus.request.owners == [("background", "Foret"), ("background", "ForetNuit")]


def test_un_fond_8bpp_occupe_les_seize_banques(projet):
    """En 8bpp le `pal_bank` d'une tuile est IGNORÉ par le hardware : la palette
    de 256 couleurs s'étale sur toute PAL_BG_RAM, découpée en 16 tranches."""
    pal256 = [(i * 7) & 0x7FFF for i in range(256)]
    ba = _ajouter_fond_compresse(projet, "Photo", [pal256], bpp=8)

    lay = scene_bank_layout(projet, _scene_avec_fonds("Photo"), "bg")
    assert lay.bg_banks(ba) == [0]
    assert lay.bank_count() == 16
    assert lay.slot_colors[0] == pal256[:16]
    assert lay.slot_colors[15] == pal256[240:]


def test_un_fond_8bpp_ne_cohabite_avec_rien(projet):
    """Il prend les 16 banques ou rien : une seule palette référencée suffit à
    rendre la scène impossible, et ça doit se voir au build."""
    _ajouter_palette(projet, "Ciel", 1)
    scene = _scene_avec_fonds("Photo")
    scene.active_bg_palettes = ["Ciel"]
    ba = _ajouter_fond_compresse(projet, "Photo",
                                 [[(i * 7) & 0x7FFF for i in range(256)]], bpp=8)

    lay = scene_bank_layout(projet, scene, "bg")
    assert lay.bg_banks(ba) is None
    [refus] = lay.refusals
    assert refus.cause == "needs_whole_pool"
    assert refus.request.banks == 16


def test_apres_un_fond_8bpp_plus_rien_ne_trouve_de_place(projet):
    """L'autre sens du conflit : le fond 8 bpp a pris les 16 banques, le fond
    suivant est refusé, et la cause reste le 8 bpp, pas un simple manque."""
    scene = _scene_avec_fonds("Photo", "Foret")
    _ajouter_fond_compresse(projet, "Photo",
                            [[(i * 7) & 0x7FFF for i in range(256)]], bpp=8)
    _ajouter_fond_compresse(projet, "Foret", [_couleurs(60)])

    lay = scene_bank_layout(projet, scene, "bg")
    [refus] = lay.refusals
    assert refus.cause == "needs_whole_pool"
    assert refus.request.owners == [("background", "Foret")]
    assert lay.slot_owners[15] == [("8bpp background", "Photo")]


def test_l_allocation_est_deterministe(projet):
    """La promesse dont dépend la cohérence entre grit et `main_gen` : ils
    n'échangent rien, ils rappellent cette fonction chacun de leur côté."""
    _ajouter_palette(projet, "Ciel", 1)
    scene = _scene_avec_fonds("Foret", "Roche")
    scene.active_bg_palettes = ["Ciel"]
    _ajouter_fond_compresse(projet, "Foret", [_couleurs(40), _couleurs(41)])
    _ajouter_fond_compresse(projet, "Roche", [_couleurs(42)])

    a = scene_bank_layout(projet, scene, "bg")
    b = scene_bank_layout(projet, scene, "bg")
    assert a.slot_colors == b.slot_colors
    assert a.bank_count() == b.bank_count()


# ── Inclusion : une palette de sprite contenue dans une autre partage sa banque ──

def _sprite(p: Project, nom: str, couleurs: list[int]):
    from core.models.sprite import SpriteAsset
    sp = SpriteAsset(name=nom, asset=f"{nom}.png", own_palette=list(couleurs))
    p.sprites.append(sp)
    return sp


def _scene_avec_acteurs(*sprites: str, nom_scene: str = "Test") -> Scene:
    from core.models.components import SpriteComponent
    from core.models.scene import Actor
    acteurs = []
    for nom in sprites:
        a = Actor(name=f"Acteur{nom}")
        a.components.append(SpriteComponent(id="s0", sprite_name=nom, active=True))
        acteurs.append(a)
    return Scene(name=nom_scene, actors=acteurs)


ROUGE, VERT, BLEU, JAUNE = 0x001F, 0x03E0, 0x7C00, 0x03FF


def test_un_sprite_contenu_dans_un_autre_partage_sa_banque(projet):
    petit = _sprite(projet, "Petit", [ROUGE, BLEU])
    grand = _sprite(projet, "Grand", [VERT, ROUGE, BLEU])

    lay = scene_bank_layout(projet, _scene_avec_acteurs("Petit", "Grand"), "obj")
    assert lay.bank_count() == 1
    banque = lay.bank_index(OWN_PAL_BANK, petit.own_palette)
    assert banque == lay.bank_index(OWN_PAL_BANK, grand.own_palette)
    assert lay.slot_colors[banque] == [RESERVED_SLOT_COLOR, VERT, ROUGE, BLEU]
    assert lay.slot_owners[banque] == [("actor", "ActeurPetit"), ("actor", "ActeurGrand")]


def test_une_chaine_d_inclusions_remonte_a_la_plus_grande(projet):
    """A dans B dans C : A et B prennent C, même dans une scène où C n'est pas."""
    _sprite(projet, "A", [ROUGE])
    _sprite(projet, "B", [ROUGE, VERT])
    _sprite(projet, "C", [BLEU, ROUGE, VERT])

    lay = scene_bank_layout(projet, _scene_avec_acteurs("A", "B"), "obj")
    assert lay.bank_count() == 1
    assert [RESERVED_SLOT_COLOR, BLEU, ROUGE, VERT] in lay.slot_colors


def test_les_memes_couleurs_dans_un_autre_ordre_partagent_leur_banque(projet):
    _sprite(projet, "Avant", [ROUGE, VERT])
    _sprite(projet, "Apres", [VERT, ROUGE])

    lay = scene_bank_layout(projet, _scene_avec_acteurs("Avant", "Apres"), "obj")
    assert lay.bank_count() == 1


def test_une_scene_sans_l_englobante_ne_prend_pas_plus_de_banques(projet):
    """L'englobante vaut pour tout le projet : sa banque en reçoit les couleurs
    même quand le sprite qui la porte n'est pas dans la scène, sans coûter de
    banque de plus que la palette d'origine."""
    petit = _sprite(projet, "Petit", [ROUGE, BLEU])
    _sprite(projet, "Grand", [VERT, ROUGE, BLEU, JAUNE])
    _sprite(projet, "Autre", [JAUNE, VERT])

    lay = scene_bank_layout(projet, _scene_avec_acteurs("Petit", "Autre"), "obj")
    assert lay.bank_count() == 1    # Autre est aussi dans Grand
    assert lay.slot_colors[lay.bank_index(OWN_PAL_BANK, petit.own_palette)] == \
        [RESERVED_SLOT_COLOR, VERT, ROUGE, BLEU, JAUNE]


def test_un_groupe_garde_l_ordre_de_son_premier_membre(projet):
    from codegen.palette_alloc import sprite_palette_groups
    _sprite(projet, "A", [ROUGE])
    _sprite(projet, "B", [VERT, ROUGE])
    _sprite(projet, "C", [ROUGE, VERT])          # même taille, autre ordre : l'ordre des couleurs tranche
    _sprite(projet, "D", [BLEU])                 # ne croise personne : reste seul
    groupes = sprite_palette_groups(projet)
    assert groupes[(ROUGE,)] == groupes[(VERT, ROUGE)] == groupes[(ROUGE, VERT)] == [ROUGE, VERT]
    assert groupes[(BLEU,)] == [BLEU]


# ── Regroupement : de petites palettes qui se croisent partagent une banque ──

def _couleurs_distinctes(debut: int, nombre: int) -> list[int]:
    return [0x0400 + debut + i for i in range(nombre)]


def test_deux_petites_palettes_qui_se_croisent_partagent_une_banque(projet):
    _sprite(projet, "A", [ROUGE, VERT])
    _sprite(projet, "B", [BLEU, JAUNE])
    scene = _scene_avec_acteurs("A", "B")
    projet.scenes.items = [scene]

    lay = scene_bank_layout(projet, scene, "obj")
    assert lay.bank_count() == 1
    assert lay.slot_colors[15] == [RESERVED_SLOT_COLOR, ROUGE, VERT, BLEU, JAUNE]


def test_deux_palettes_qui_ne_se_croisent_jamais_ne_sont_pas_groupees(projet):
    """Les grouper ne libérerait aucune banque, et forcerait la reconversion de
    leurs tuiles pour rien."""
    from codegen.palette_alloc import sprite_palette_groups
    _sprite(projet, "A", [ROUGE, VERT])
    _sprite(projet, "B", [BLEU, JAUNE])
    projet.scenes.items = [_scene_avec_acteurs("A", nom_scene="Un"),
                           _scene_avec_acteurs("B", nom_scene="Deux")]

    groupes = sprite_palette_groups(projet)
    assert groupes[(ROUGE, VERT)] == [ROUGE, VERT]
    assert groupes[(BLEU, JAUNE)] == [BLEU, JAUNE]


def test_le_regroupement_suit_les_palettes_qui_se_croisent(projet):
    """La scène 1 a A et B (8 couleurs chacun, ils ne tiennent pas ensemble), la
    scène 2 a C et D (4 couleurs). Grouper A avec C ne libérerait rien : c'est C
    avec D qu'il faut grouper, et la scène 2 n'utilise plus qu'une banque."""
    _sprite(projet, "A", _couleurs_distinctes(0, 8))
    _sprite(projet, "B", _couleurs_distinctes(8, 8))
    _sprite(projet, "C", _couleurs_distinctes(16, 4))
    _sprite(projet, "D", _couleurs_distinctes(20, 4))
    un = _scene_avec_acteurs("A", "B", nom_scene="Un")
    deux = _scene_avec_acteurs("C", "D", nom_scene="Deux")
    projet.scenes.items = [un, deux]

    assert scene_bank_layout(projet, un, "obj").bank_count() == 2
    assert scene_bank_layout(projet, deux, "obj").bank_count() == 1


def test_un_groupe_ne_depasse_pas_quinze_couleurs(projet):
    _sprite(projet, "A", _couleurs_distinctes(0, 8))
    _sprite(projet, "B", _couleurs_distinctes(8, 8))
    scene = _scene_avec_acteurs("A", "B")
    projet.scenes.items = [scene]

    assert scene_bank_layout(projet, scene, "obj").bank_count() == 2


def test_la_conversion_recale_les_pixels_sur_l_englobante(projet, monkeypatch):
    """Les tuiles d'un sprite sont converties une fois pour tout le projet : elles
    doivent viser les positions de ses couleurs DANS l'englobante, celle que sa
    banque recevra. grit est remplacé par un .c au format qu'il écrit, dont la
    palette suit l'ordre propre du sprite (index 1 = ROUGE, 2 = BLEU)."""
    from PIL import Image
    from codegen import grit_conversion

    petit = _sprite(projet, "Petit", [ROUGE, BLEU])
    _sprite(projet, "Grand", [VERT, ROUGE, BLEU])
    png = projet.asset_abs(petit.asset)
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(png)
    monkeypatch.setattr(grit_conversion, "build_sprite_sheet_indexed", lambda src, *_a: src)
    monkeypatch.setattr(grit_conversion, "quantize_asset", lambda *_a: Image.new("RGBA", (8, 8)))

    def grit(cmd, _label, cwd):
        out = Path(cwd) / (cmd[cmd.index("-o") + 1] + ".c")
        out.write_text(
            "const unsigned int sprite_PetitTiles[1] __attribute__((aligned(4)))= {\n0x00000021,\n};\n"
            f"const unsigned short sprite_PetitPal[3] __attribute__((aligned(4)))= {{\n"
            f"0x{RESERVED_SLOT_COLOR:04X},0x{ROUGE:04X},0x{BLEU:04X},\n}};\n", encoding="utf-8")
        return True

    conversion = grit_conversion.GritSprites(Path("grit"), lambda *_a: None, grit)
    assert conversion.run(projet, [(None, petit, [RESERVED_SLOT_COLOR, ROUGE, BLEU])]) is True
    texte = (projet.grit_out_dir / "sprite_Petit.c").read_text(encoding="utf-8")
    assert "0x00000032" in texte    # ROUGE est en 2, BLEU en 3 dans [réservé, VERT, ROUGE, BLEU]
