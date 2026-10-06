"""Contrat de la réconciliation incrémentale (`core.reconcile_manifest`).

La porte doit répondre juste à « le dossier a-t-il bougé depuis le dernier
rattrapage ? » — et la passe de réconciliation doit se sauter quand la réponse
est non, sans jamais rater un changement hors ligne.
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from core.reconcile_manifest import ReconcileManifest

IMG_EXTS = {".png"}


def _png(path: Path, color=(0, 0, 0)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color).save(path)


def _dir(tmp_path: Path) -> Path:
    d = tmp_path / "assets" / "sprites"
    _png(d / "a.png")
    _png(d / "b.png")
    return d


# ── Le store ───────────────────────────────────────────────────────

def test_manifeste_absent_ne_coincide_pas(tmp_path):
    """Jamais enregistré → la passe doit tourner."""
    d = _dir(tmp_path)
    m = ReconcileManifest(tmp_path)
    assert m.matches(d, IMG_EXTS) is False


def test_record_puis_matches(tmp_path):
    d = _dir(tmp_path)
    m = ReconcileManifest(tmp_path)
    m.record(d, IMG_EXTS)
    assert m.matches(d, IMG_EXTS) is True


def test_empreinte_persiste_entre_instances(tmp_path):
    """Le manifeste survit à la fermeture : une seconde instance le relit."""
    d = _dir(tmp_path)
    ReconcileManifest(tmp_path).record(d, IMG_EXTS)
    assert ReconcileManifest(tmp_path).matches(d, IMG_EXTS) is True


def test_mtime_touchee_invalide(tmp_path):
    d = _dir(tmp_path)
    m = ReconcileManifest(tmp_path)
    m.record(d, IMG_EXTS)
    st = (d / "a.png").stat()
    os.utime(d / "a.png", ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert m.matches(d, IMG_EXTS) is False


def test_fichier_ajoute_invalide(tmp_path):
    d = _dir(tmp_path)
    m = ReconcileManifest(tmp_path)
    m.record(d, IMG_EXTS)
    _png(d / "c.png")
    assert m.matches(d, IMG_EXTS) is False


def test_fichier_retire_invalide(tmp_path):
    d = _dir(tmp_path)
    m = ReconcileManifest(tmp_path)
    m.record(d, IMG_EXTS)
    (d / "b.png").unlink()
    assert m.matches(d, IMG_EXTS) is False


def test_fichier_renomme_invalide(tmp_path):
    d = _dir(tmp_path)
    m = ReconcileManifest(tmp_path)
    m.record(d, IMG_EXTS)
    (d / "b.png").rename(d / "z.png")
    assert m.matches(d, IMG_EXTS) is False


def test_seules_les_extensions_visees_comptent(tmp_path):
    """Un fichier hors périmètre (un .json sidecar) déposé à côté ne casse pas
    l'empreinte des images."""
    d = _dir(tmp_path)
    m = ReconcileManifest(tmp_path)
    m.record(d, IMG_EXTS)
    (d / "a.json").write_text("{}", encoding="utf-8")
    assert m.matches(d, IMG_EXTS) is True


def test_dossier_absent_est_vide(tmp_path):
    d = tmp_path / "assets" / "sprites"  # jamais créé
    m = ReconcileManifest(tmp_path)
    m.record(d, IMG_EXTS)
    assert m.matches(d, IMG_EXTS) is True


def test_manifeste_illisible_ne_coincide_pas(tmp_path):
    d = _dir(tmp_path)
    path = tmp_path / "project" / "editor" / "reconcile-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ pas du json", encoding="utf-8")
    assert ReconcileManifest(tmp_path).matches(d, IMG_EXTS) is False


# ── La porte dans la passe ─────────────────────────────────────────

def test_reconcile_sprites_saute_quand_rien_ne_change(tmp_path):
    """Empreinte inchangée → aucun `sync_sprite_png` n'est appelé."""
    from core.project import Project
    from core.resources import asset_reconciliation as AR

    root = tmp_path / "jeu"
    _png(root / "assets" / "sprites" / "ennemi.png")
    p = Project(root)
    p.load()
    p.load_all_resources()          # premier rattrapage : crée le sprite, écrit l'empreinte
    assert [s.name for s in p.sprites] == ["ennemi"]

    calls = []
    original = AR.sync_sprite_png
    AR.sync_sprite_png = lambda proj, f: calls.append(f) or original(proj, f)
    try:
        AR.reconcile_sprites(p)     # rien n'a bougé sur le disque
    finally:
        AR.sync_sprite_png = original
    assert calls == []              # la passe a été sautée


def test_reconcile_sprites_rattrape_un_png_depose_apres_coup(tmp_path):
    """Empreinte changée (un PNG déposé après le premier rattrapage) → la passe
    tourne et crée le sprite manquant."""
    from core.project import Project
    from core.resources import asset_reconciliation as AR

    root = tmp_path / "jeu"
    _png(root / "assets" / "sprites" / "ennemi.png")
    p = Project(root)
    p.load()
    p.load_all_resources()
    assert {s.name for s in p.sprites} == {"ennemi"}

    _png(p.sprites_dir / "boss.png")   # déposé « éditeur fermé »
    AR.reconcile_sprites(p)
    assert {s.name for s in p.sprites} == {"ennemi", "boss"}
