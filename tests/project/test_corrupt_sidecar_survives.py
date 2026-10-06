"""Un sidecar illisible ne doit jamais être écrasé en silence.

Le piège : le sidecar d'un sprite est corrompu, mais sa planche PNG existe. La
réconciliation à l'ouverture ne retrouve pas le sprite (lecture impossible) et
en recrée un neuf, aux valeurs par défaut, depuis la planche. La sauvegarde
suivante écrit ce sprite vierge PAR-DESSUS le fichier abîmé : découpage et
animations, peut-être encore récupérables à la main, sont perdus.

Invariant testé : après ouverture, rattrapage et sauvegarde, le texte du fichier
abîmé existe toujours quelque part dans le dossier.
"""
from __future__ import annotations

import os

from PIL import Image

from core.project import Project

CORRUPT = '{ "name": "hero", "frame_w": 16, "frame_h'      # tronqué


def _texts(directory) -> list[str]:
    return [p.read_text(encoding="utf-8", errors="replace")
            for p in directory.iterdir() if p.is_file() and p.suffix != ".png"]


def test_sprite_au_sidecar_illisible_n_est_pas_ecrase(tmp_path):
    root = tmp_path / "Jeu"
    project = Project.create(root, "Jeu")
    png = project.sprites_dir / "hero.png"
    Image.new("RGB", (16, 16), (200, 30, 30)).save(png)
    project = Project.open(root)                      # un projet créé ne diffère rien
    project.load_all_resources()                      # crée le sidecar de hero
    sidecar = project.sprites.path_of(project.sprites.get("hero"))
    assert sidecar.exists()

    sidecar.write_text(CORRUPT, encoding="utf-8")
    stat = png.stat()                                  # planche « touchée » : le
    os.utime(png, ns=(stat.st_atime_ns,                # rattrapage doit repasser
                      stat.st_mtime_ns + 2_000_000_000))

    reopened = Project.open(root)
    reopened.load_all_resources()
    reopened.save()

    assert CORRUPT in _texts(project.sprites_dir), \
        "le sidecar illisible a été écrasé sans copie de sauvegarde"
