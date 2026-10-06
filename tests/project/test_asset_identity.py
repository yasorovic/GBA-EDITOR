"""L'identité d'un asset à sidecar : le NOM DE FICHIER fait foi.

Un asset de la famille `assets/<famille>/` s'écrit dans `<name>.json` et se
relit par le STEM de son fichier source. Trois noms doivent donc rester
d'accord — celui du sidecar, le champ `name` qu'il contient, et le fichier
source qu'il cite. Quand ils divergent (planche renommée dans l'explorateur,
sidecar déplacé), rien ne les recollait : le rattrapage à l'ouverture ne
reconnaissait plus l'asset, en créait un SECOND, et laissait le premier à
l'écran en pointant sur un fichier disparu — d'où des polices en double dont
une moitié s'affiche vide.

Le cas a été rencontré sur un vrai projet (8 polices → 15 entrées).
"""
from __future__ import annotations

import json

from PIL import Image


def _sheet(path, cols=16, rows=14, cell=8):
    """Planche de police régulière : une grille de cases sur fond noir, avec
    un pixel d'encre par case pour que la découpe trouve des glyphes."""
    img = Image.new("RGB", (cols * cell, rows * cell), (0, 0, 0))
    for y in range(rows):
        for x in range(cols):
            img.putpixel((x * cell + 1, y * cell + 1), (255, 255, 255))
    img.save(path)


def _projet(tmp_path, *, fichier: str, nom_interne: str, planche_citee: str):
    from core.project import Project

    root = tmp_path / "jeu"
    fonts = root / "assets" / "fonts"
    fonts.mkdir(parents=True)
    _sheet(fonts / f"{fichier}.png")
    (fonts / f"{fichier}.json").write_text(json.dumps({
        "name": nom_interne,
        "asset": f"assets/fonts/{planche_citee}.png",
        "source_format": "png",
        "cell_w": 8, "cell_h": 8, "line_height": 8,
        "glyphs": [{"char": "A", "x": 0, "y": 0, "w": 8, "h": 8, "advance": 8}],
    }), encoding="utf-8")

    p = Project(root)
    p.load()
    # v0.24 : `load` n'indexe que les catalogues lourds ; leur matérialisation et
    # la réconciliation des sources (rattrapage, dépôts hors éditeur) sont un
    # geste explicite, celui qu'un écran ou une opération globale demande.
    p.load_all_resources()
    return p


def test_sidecar_renomme_ne_dedouble_pas(tmp_path):
    """Sidecar ET planche renommés sur le disque, champ `name` resté en
    arrière : une seule police, nommée par le fichier."""
    p = _projet(tmp_path, fichier="ma-police",
                nom_interne="Ma Police", planche_citee="Ma Police")
    assert [f.name for f in p.fonts] == ["ma-police"]
    assert p.asset_abs(p.fonts[0].asset).exists()


def test_planche_renommee_est_raccrochee(tmp_path):
    """Seule la planche a été renommée : la police garde son nom et retrouve
    son image, au lieu de s'afficher vide à côté d'une nouvelle police."""
    p = _projet(tmp_path, fichier="ma-police",
                nom_interne="ma-police", planche_citee="ancien-nom")
    assert [f.name for f in p.fonts] == ["ma-police"]
    assert p.fonts[0].asset == "assets/fonts/ma-police.png"


def test_cas_nominal_intact(tmp_path):
    """Rien de renommé : le sidecar est relu tel quel, glyphes compris (le
    rattrapage ne doit surtout pas ré-analyser la planche)."""
    p = _projet(tmp_path, fichier="ma-police",
                nom_interne="ma-police", planche_citee="ma-police")
    assert [f.name for f in p.fonts] == ["ma-police"]
    assert [g.char for g in p.fonts[0].glyphs] == ["A"]


def test_load_one_ne_rajoute_pas_un_double(tmp_path):
    """Rechargement d'un seul sidecar (watcher) : un champ `name` périmé ne
    doit pas faire entrer une deuxième fois la même ressource."""
    p = _projet(tmp_path, fichier="ma-police",
                nom_interne="ma-police", planche_citee="ma-police")
    path = p.fonts_dir / "ma-police.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    d["name"] = "Ma Police"
    path.write_text(json.dumps(d), encoding="utf-8")

    p.fonts.load_one("ma-police")
    assert [f.name for f in p.fonts] == ["ma-police"]


def _image(path, w=16, h=16):
    img = Image.new("RGB", (w, h), (0, 0, 0))
    for x in range(w):
        img.putpixel((x, x % h), (255, 0, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def _projet_avec(tmp_path, famille: str, *, fichier: str, cite: str, **champs):
    """Un projet dont l'unique asset de `famille` cite `cite`, alors que le
    fichier réellement présent est `fichier`."""
    from core.project import Project

    root = tmp_path / "jeu"
    d = root / "assets" / famille
    _image(d / f"{fichier}.png")
    (d / f"{fichier}.json").write_text(
        json.dumps({"name": fichier, "asset": cite, **champs}), encoding="utf-8")

    p = Project(root)
    p.load()
    p.load_all_resources()   # v0.24 : matérialisation + réconciliation explicites
    return p


def test_sprite_raccroche_sa_planche_renommee(tmp_path):
    """Planche de sprite renommée éditeur fermé : le sprite la retrouve, et
    aucun second sprite ne naît du fichier renommé — ce qui reviendrait à
    perdre la découpe en frames et les états déjà posés."""
    p = _projet_avec(tmp_path, "sprites", fichier="hero",
                     cite="assets/sprites/ancien-nom.png",
                     frame_w=16, frame_h=16)
    assert [s.name for s in p.sprites] == ["hero"]
    assert p.sprites[0].asset == "assets/sprites/hero.png"
    assert p.sprites[0].frame_w == 16      # l'authoring est intact


def test_fond_raccroche_son_image_renommee(tmp_path):
    """Idem pour un fond — qui cite son image par son seul nom de fichier."""
    p = _projet_avec(tmp_path, "backgrounds", fichier="ciel",
                     cite="ancien-nom.png")
    assert [b.name for b in p.backgrounds] == ["ciel"]
    assert p.backgrounds[0].asset == "ciel.png"


def test_un_png_depose_editeur_ferme_cree_son_sprite(tmp_path):
    """Le rattrapage des sprites ne balayait pas leur dossier : un PNG déposé
    hors éditeur n'était vu par personne (le watcher, lui, ne tourne que
    pendant la session). Pendant de `reconcile_backgrounds`."""
    from core.project import Project

    root = tmp_path / "jeu"
    _image(root / "assets" / "sprites" / "ennemi.png")
    p = Project(root)
    p.load()
    p.load_all_resources()   # v0.24 : matérialisation + réconciliation explicites
    assert [s.name for s in p.sprites] == ["ennemi"]
    assert (root / "assets" / "sprites" / "ennemi.json").exists()


# ── Le renommage, vu par le watcher ───────────────────────────────
# Un renommage arrive comme une disparition ET une apparition dans le même
# événement. Non apparié, il coûtait l'asset : détruit avec tout ce qui avait
# été authoré dessus, remplacé par un asset vierge sous le nouveau nom.


def test_meme_empreinte_donc_renommage():
    from core.project_watcher import pair_renames
    avant = {"d/hero.png": (120, 42), "d/autre.png": (7, 7)}
    apres = {"d/heros.png": (120, 42), "d/autre.png": (7, 7)}
    assert pair_renames(avant, apres) == [("d/hero.png", "d/heros.png")]


def test_empreintes_differentes_donc_deux_gestes():
    """Un fichier supprimé et un autre déposé dans le même événement ne sont
    pas un renommage — c'est ce que l'empreinte tranche."""
    from core.project_watcher import pair_renames
    assert pair_renames({"d/a.png": (120, 42)}, {"d/b.png": (120, 43)}) == []


def test_un_lua_n_est_pas_apparie():
    """Un script est suivi par son chemin, pas par un asset : l'appariement ne
    le concerne pas (et un sidecar `.json` non plus)."""
    from core.project_watcher import pair_renames
    assert pair_renames({"d/a.lua": (1, 2)}, {"d/b.lua": (1, 2)}) == []
    assert pair_renames({"d/a.json": (1, 2)}, {"d/b.json": (1, 2)}) == []


def test_sprite_renomme_garde_sa_decoupe_et_ses_references(tmp_path):
    """Le geste complet : le sprite suit son fichier — nom, sidecar, planche,
    et la référence que porte une scène."""
    from core.resources import asset_reconciliation
    from core.models.components import SpriteComponent
    from core.models.scene import Actor, Scene
    from core.project import Project

    root = tmp_path / "jeu"
    _image(root / "assets" / "sprites" / "hero.png")
    p = Project(root)
    p.load()
    p.load_all_resources()   # v0.24 : crée le sidecar du PNG déposé hors éditeur
    sprite = p.sprites.get("hero")
    sprite.frame_w = sprite.frame_h = 16          # de l'authoring à préserver

    actor = Actor(name="Joueur")
    actor.components.append(SpriteComponent(sprite_name="hero"))
    scene = Scene(name="niveau")
    scene.actors.append(actor)
    p.scenes.append(scene)

    old = root / "assets" / "sprites" / "hero.png"
    new = old.with_name("heros.png")
    old.rename(new)
    asset_reconciliation.rename_sprite_png(p, old, new)

    assert [s.name for s in p.sprites] == ["heros"]
    assert p.sprites[0].asset == "assets/sprites/heros.png"
    assert p.sprites[0].frame_w == 16
    assert actor.components[0].sprite_name == "heros"
    assert (root / "assets" / "sprites" / "heros.json").exists()
    assert not (root / "assets" / "sprites" / "hero.json").exists()


def test_police_renommee_suit_sa_planche(tmp_path):
    """Une police garde ses glyphes — c'est-à-dire le travail case par case de
    l'écran Police — quand sa planche est renommée."""
    from core.resources import asset_reconciliation

    p = _projet(tmp_path, fichier="ma-police",
                nom_interne="ma-police", planche_citee="ma-police")
    old = p.fonts_dir / "ma-police.png"
    new = old.with_name("ma-jolie-police.png")
    old.rename(new)
    asset_reconciliation.rename_font_file(p, old, new)

    assert [f.name for f in p.fonts] == ["ma-jolie-police"]
    assert p.fonts[0].asset == "assets/fonts/ma-jolie-police.png"
    assert [g.char for g in p.fonts[0].glyphs] == ["A"]


def test_un_fichier_inconnu_renomme_est_une_apparition(tmp_path):
    """Renommer un fichier qu'aucun asset ne connaissait n'a rien à renommer :
    c'est une arrivée, et elle crée l'asset."""
    from core.resources import asset_reconciliation
    from core.project import Project

    root = tmp_path / "jeu"
    p = Project(root)
    p.load()
    new = root / "assets" / "sprites" / "ennemi.png"
    _image(new)
    asset_reconciliation.rename_sprite_png(p, new.with_name("brouillon.png"), new)
    assert [s.name for s in p.sprites] == ["ennemi"]


# ── Suppression définitive à la fermeture ─────────────────────────
# Supprimer un asset depuis le finder le `soft_delete` : il quitte la liste, son
# sidecar est effacé à la fermeture (commit_all_removals). Mais le fichier SOURCE
# restait, et `reconcile_*` le ressuscitait au rechargement suivant. La
# suppression définitive doit donc emporter aussi la source — et elle seule, à la
# fermeture : pendant la session le fichier reste, pour que Ctrl+Z (restore) ramène
# l'asset sans avoir rien à ressortir du disque.


def _recharge(root):
    from core.project import Project
    p = Project(root)
    p.load()
    # Matérialisation explicite : c'est elle qui relancerait la réconciliation
    # (donc ressusciterait un asset depuis une source restée sur le disque) —
    # tester la NON-résurrection sans elle ne prouverait rien (v0.24).
    p.load_all_resources()
    return p


def test_police_supprimee_ne_ressuscite_pas(tmp_path):
    """Police supprimée puis éditeur fermé : ni le sidecar ni la planche ne
    restent, donc le rattrapage ne la recrée pas au rechargement."""
    p = _projet(tmp_path, fichier="ma-police",
                nom_interne="ma-police", planche_citee="ma-police")
    planche = p.asset_abs(p.fonts[0].asset)
    p.fonts.soft_delete(p.fonts[0])
    p.commit_all_removals()
    assert not planche.exists()

    assert [f.name for f in _recharge(p.root).fonts] == []


def test_sprite_supprime_ne_ressuscite_pas(tmp_path):
    """Idem pour un sprite, adossé à sa seule planche PNG."""
    p = _projet_avec(tmp_path, "sprites", fichier="hero",
                     cite="assets/sprites/hero.png", frame_w=16, frame_h=16)
    planche = p.asset_abs(p.sprites[0].asset)
    p.sprites.soft_delete(p.sprites[0])
    p.commit_all_removals()
    assert not planche.exists()

    assert [s.name for s in _recharge(p.root).sprites] == []


def test_undo_avant_fermeture_epargne_la_source(tmp_path):
    """La source part dans `.temp/` pendant la session et n'est détruite qu'à la
    fermeture : un restore (Ctrl+Z) ramène la police ET sa planche à leur place."""
    p = _projet(tmp_path, fichier="ma-police",
                nom_interne="ma-police", planche_citee="ma-police")
    font = p.fonts[0]
    planche = p.asset_abs(font.asset)
    p.fonts.soft_delete(font)
    assert not planche.exists()      # rangée dans .temp/, plus à sa place
    assert (p.root / ".temp" / "assets" / "fonts" / planche.name).is_file()
    p.fonts.restore(font)
    assert planche.exists()
    p.commit_all_removals()
    assert planche.exists()

    assert [f.name for f in _recharge(p.root).fonts] == ["ma-police"]
