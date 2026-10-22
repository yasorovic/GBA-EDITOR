"""L'identité d'un asset : le nom de son fichier fait foi, et le watcher apparie un renommage de fichier brut.

Un asset de la famille `assets/<famille>/` s'écrit dans `<name>.<extension de son type>` et se
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
    (fonts / f"{fichier}.font").write_text(json.dumps({
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
    path = (p.user_library_dir / "fonts") / "ma-police.font"
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
