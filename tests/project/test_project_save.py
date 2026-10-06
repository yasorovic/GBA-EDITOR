"""`atomic_write` saute l'écriture d'un contenu déjà sur disque.

Le défaut, et sa mesure : `project.save()` réécrivait les quatorze collections à
chaque Ctrl+S — temporaire + rename par asset —, alors qu'éditer un script n'en
change aucun. Sauter l'écriture d'un contenu identique fait passer 200 assets
intacts de ~950 ms à ~100 ms. Ce test garde le saut, pour qu'une régression ne
réintroduise pas la lenteur.
"""
from __future__ import annotations

import time

from core.resources.resource_store import atomic_write


def test_ecriture_identique_est_sautee(tmp_path):
    p = tmp_path / "asset.json"
    atomic_write(p, '{"name": "x"}')
    before = p.stat().st_mtime_ns

    time.sleep(0.02)                      # un vrai réécriture ferait avancer le mtime
    atomic_write(p, '{"name": "x"}')      # même contenu → sauté
    assert p.stat().st_mtime_ns == before


def test_ecriture_differente_est_effectuee(tmp_path):
    p = tmp_path / "asset.json"
    atomic_write(p, '{"name": "x"}')
    before = p.stat().st_mtime_ns

    time.sleep(0.02)
    atomic_write(p, '{"name": "y"}')      # contenu changé → écrit
    assert p.read_text(encoding="utf-8") == '{"name": "y"}'
    assert p.stat().st_mtime_ns != before


def test_fichier_absent_est_cree(tmp_path):
    p = tmp_path / "nouveau.json"
    atomic_write(p, "contenu")
    assert p.read_text(encoding="utf-8") == "contenu"
