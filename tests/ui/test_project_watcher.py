"""Le ProjectWatcher : ce qu'il doit voir, et ce qu'il ne doit PAS croire voir.

Chaque cas travaille sur un vrai dossier de projet (`tmp_path`) et un vrai
`ProjectWatcher`. Les changements sont rattrapés par `rescan()` — le chemin que
l'application emprunte à chaque retour de focus — plutôt que par les événements
du système, qui varient d'une plateforme à l'autre : le test dit ce que le
watcher conclut d'un état du disque, pas quand l'OS le lui annonce. Les dépôts
sont rendus « terminés » en laissant passer le délai de stabilité.
"""
from __future__ import annotations

import os
import time

import pytest
from PyQt6.QtCore import QCoreApplication

from core.project_watcher import ProjectWatcher, pair_renames

SETTLE_S = 0.6      # > délai de stabilité (200 ms) × 2 passages


def pump(seconds: float = SETTLE_S):
    """Laisse tourner la boucle d'événements : timers et signaux Qt."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def write(path, data: bytes = b"x", mtime_ns: int | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime_ns is not None:
        os.utime(path, ns=(mtime_ns, mtime_ns))


class Spy:
    """Enregistre tout ce que le watcher émet, signal par signal."""

    NAMES = ("asset_appeared", "asset_removed", "asset_renamed", "asset_modified",
             "lua_changed", "scene_changed", "sidecar_changed")

    def __init__(self, watcher: ProjectWatcher):
        for name in self.NAMES:
            log: list = []
            setattr(self, name, log)
            getattr(watcher, name).connect(lambda *a, log=log: log.append(a))

    def names(self, signal: str) -> list[str]:
        return sorted(os.path.basename(a[0]) for a in getattr(self, signal))

    def silent(self) -> bool:
        return not any(getattr(self, n) for n in self.NAMES)


_KEPT: list[ProjectWatcher] = []


@pytest.fixture
def root(tmp_path):
    for sub in ("backgrounds", "sprites", "sfx", "music", "fonts", "scripts"):
        (tmp_path / "assets" / sub).mkdir(parents=True)
    (tmp_path / "project" / "scenes").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def watcher(qapp, root):
    w = ProjectWatcher()
    yield w
    w.unwatch()
    _KEPT.append(w)     # gardé en vie jusqu’à la fin du processus : le libérer en cours de session (deleteLater) faisait planter pytest en natif, de façon intermittente (cause non élucidée)


def start(watcher, root) -> Spy:
    watcher.watch_project(root)
    return Spy(watcher)


def settle(watcher):
    """Rattrape le disque, puis laisse la copie « finir »."""
    watcher.rescan()
    pump()
    watcher.rescan()
    pump()


# ── Dépôts ──────────────────────────────────────────────────────────


def test_un_fichier_depose_est_signale_une_fois(watcher, root):
    spy = start(watcher, root)
    write(root / "assets/backgrounds/a.png")
    settle(watcher)
    assert spy.names("asset_appeared") == ["a.png"]


def test_plusieurs_fichiers_deposes_ensemble_sont_tous_signales(watcher, root):
    spy = start(watcher, root)
    for n in ("a", "b", "c"):
        write(root / f"assets/backgrounds/{n}.png", mtime_ns=1_000_000_000 + hash(n) % 999)
    settle(watcher)
    assert spy.names("asset_appeared") == ["a.png", "b.png", "c.png"]


def test_fichier_pendant_une_importation_n_est_pas_absorbe(watcher, root):
    """Le bug des trois PNG : deux fichiers arrivent PENDANT l'import du premier."""
    spy = start(watcher, root)
    write(root / "assets/backgrounds/a.png")
    settle(watcher)
    with watcher.suspended():
        write(root / "assets/backgrounds/a.json", b"{}")      # notre écriture
        write(root / "assets/backgrounds/b.png", b"bb")       # dépôts externes
        write(root / "assets/backgrounds/c.png", b"ccc")
    pump()
    assert spy.names("asset_appeared") == ["a.png", "b.png", "c.png"]
    assert spy.sidecar_changed == []                          # notre sidecar : muet


def test_fichier_en_cours_de_copie_attend_la_fin(watcher, root):
    spy = start(watcher, root)
    f = root / "assets/backgrounds/gros.png"
    write(f, b"1")
    watcher.rescan()
    for i in range(4):                       # la copie grossit à chaque passage
        pump(0.08)       # moins que le délai de stabilité (200 ms)
        with open(f, "ab") as fh:
            fh.write(b"+" * 10)
        watcher.rescan()
    assert spy.asset_appeared == []          # jamais signalé en cours de route
    pump()
    watcher.rescan()
    pump()
    assert spy.names("asset_appeared") == ["gros.png"]


def test_fichier_disparu_avant_la_fin_de_la_copie_n_emet_rien(watcher, root):
    spy = start(watcher, root)
    f = root / "assets/backgrounds/fugace.png"
    write(f)
    watcher.rescan()
    f.unlink()
    pump()
    watcher.rescan()
    pump()
    assert spy.silent()


def test_extension_inconnue_est_ignoree(watcher, root):
    spy = start(watcher, root)
    for n in ("notes.txt", "tmp.psd", "~$a.tmp", "x.crdownload"):
        write(root / "assets/backgrounds" / n)
    settle(watcher)
    assert spy.silent()


def test_fichier_dans_la_mauvaise_famille_est_quand_meme_signale(watcher, root):
    """Le watcher ne connaît pas les routes : c'est `MainWindow` qui avertit."""
    spy = start(watcher, root)
    write(root / "assets/backgrounds/boom.wav")
    settle(watcher)
    assert spy.names("asset_appeared") == ["boom.wav"]


def test_script_lua_est_signale_sans_delai_de_stabilite(watcher, root):
    spy = start(watcher, root)
    write(root / "assets/scripts/hero.lua", b"-- x")
    watcher.rescan()
    assert [os.path.basename(a[0]) for a in spy.lua_changed] == ["hero.lua"]


def test_sous_dossier_de_scripts_est_surveille(watcher, root):
    (root / "assets/scripts/behaviors").mkdir()
    spy = start(watcher, root)
    write(root / "assets/scripts/behaviors/walk.lua", b"-- x")
    watcher.rescan()
    assert [os.path.basename(a[0]) for a in spy.lua_changed] == ["walk.lua"]


def test_sidecar_json_cree_a_la_main(watcher, root):
    spy = start(watcher, root)
    write(root / "assets/fonts/ui.json", b"{}")
    watcher.rescan()
    assert [os.path.basename(a[0]) for a in spy.sidecar_changed] == ["ui.json"]


def test_json_de_project_backgrounds_n_est_pas_un_sidecar(watcher, root):
    (root / "project/backgrounds").mkdir()
    spy = start(watcher, root)
    write(root / "project/backgrounds/x.json", b"{}")
    watcher.rescan()
    assert spy.sidecar_changed == []


# ── Suppressions et renommages ──────────────────────────────────────


def test_suppression(watcher, root):
    write(root / "assets/sprites/hero.png")
    spy = start(watcher, root)
    (root / "assets/sprites/hero.png").unlink()
    watcher.rescan()
    assert spy.names("asset_removed") == ["hero.png"]


def test_renommage_n_emet_que_asset_renamed(watcher, root):
    write(root / "assets/sprites/old.png", b"abc", mtime_ns=5_000_000_000)
    spy = start(watcher, root)
    (root / "assets/sprites/old.png").rename(root / "assets/sprites/new.png")
    watcher.rescan()
    pump()
    assert [(os.path.basename(a), os.path.basename(b))
            for a, b in spy.asset_renamed] == [("old.png", "new.png")]
    assert spy.asset_appeared == [] and spy.asset_removed == []


def test_renommage_avec_contenu_modifie_est_une_suppression_et_une_creation(watcher, root):
    write(root / "assets/sprites/old.png", b"abc", mtime_ns=5_000_000_000)
    spy = start(watcher, root)
    (root / "assets/sprites/old.png").unlink()
    write(root / "assets/sprites/new.png", b"different")
    settle(watcher)
    assert spy.asset_renamed == []
    assert spy.names("asset_removed") == ["old.png"]
    assert spy.names("asset_appeared") == ["new.png"]


def test_deux_fichiers_identiques_un_seul_renomme(watcher, root):
    """Même empreinte des deux côtés : chaque disparu n'est apparié qu'une fois."""
    before = {"a": (3, 7), "b": (3, 7)}
    after = {"c": (3, 7), "d": (3, 7)}
    pairs = pair_renames({f"{k}.png": v for k, v in before.items()},
                         {f"{k}.png": v for k, v in after.items()})
    assert sorted(pairs) == [("a.png", "c.png"), ("b.png", "d.png")]


def test_renommage_vers_une_extension_inconnue_est_une_disparition(watcher, root):
    write(root / "assets/sprites/old.png", b"abc", mtime_ns=5_000_000_000)
    spy = start(watcher, root)
    (root / "assets/sprites/old.png").rename(root / "assets/sprites/old.psd")
    watcher.rescan()
    pump()
    assert spy.names("asset_removed") == ["old.png"]
    assert spy.asset_renamed == []


def test_dossier_supprime_signale_chaque_fichier(watcher, root):
    write(root / "assets/sfx/a.wav")
    write(root / "assets/sfx/b.wav")
    spy = start(watcher, root)
    for f in (root / "assets/sfx").iterdir():
        f.unlink()
    (root / "assets/sfx").rmdir()
    watcher.rescan()
    assert spy.names("asset_removed") == ["a.wav", "b.wav"]


def test_dossier_cree_apres_coup_est_suivi_au_rescan(watcher, root):
    (root / "assets/music").rmdir()
    spy = start(watcher, root)
    write(root / "assets/music/theme.mod")
    settle(watcher)
    assert spy.names("asset_appeared") == ["theme.mod"]


def test_deplacement_entre_familles_est_une_disparition_et_une_apparition(watcher, root):
    write(root / "assets/sprites/x.png", b"abc", mtime_ns=5_000_000_000)
    spy = start(watcher, root)
    (root / "assets/sprites/x.png").rename(root / "assets/backgrounds/x.png")
    settle(watcher)
    assert spy.names("asset_removed") == ["x.png"]
    assert spy.names("asset_appeared") == ["x.png"]


# ── Modifications ───────────────────────────────────────────────────


def test_source_modifiee_en_place(watcher, root):
    write(root / "assets/backgrounds/a.png", b"1", mtime_ns=1_000_000_000)
    spy = start(watcher, root)
    write(root / "assets/backgrounds/a.png", b"22", mtime_ns=2_000_000_000)
    watcher.rescan()
    assert spy.names("asset_modified") == ["a.png"]


def test_sauvegarde_atomique_supprime_puis_recree(watcher, root):
    f = root / "assets/backgrounds/a.png"
    write(f, b"1", mtime_ns=1_000_000_000)
    spy = start(watcher, root)
    f.unlink()
    write(f, b"22", mtime_ns=2_000_000_000)
    watcher.rescan()
    assert spy.names("asset_modified") == ["a.png"]
    assert spy.asset_removed == [] and spy.asset_appeared == []


def test_modification_sans_changement_d_empreinte_est_invisible(watcher, root):
    """Limite connue : même taille ET même date, rien ne distingue le fichier."""
    f = root / "assets/backgrounds/a.png"
    write(f, b"1", mtime_ns=1_000_000_000)
    spy = start(watcher, root)
    write(f, b"2", mtime_ns=1_000_000_000)
    watcher.rescan()
    assert spy.silent()


def test_sidecar_modifie_a_la_main(watcher, root):
    write(root / "assets/fonts/ui.json", b"{}", mtime_ns=1_000_000_000)
    spy = start(watcher, root)
    write(root / "assets/fonts/ui.json", b'{"a":1}', mtime_ns=2_000_000_000)
    watcher.rescan()
    assert [os.path.basename(a[0]) for a in spy.sidecar_changed] == ["ui.json"]


def test_scene_modifiee(watcher, root):
    write(root / "project/scenes/Scene_01.json", b"{}", mtime_ns=1_000_000_000)
    spy = start(watcher, root)
    write(root / "project/scenes/Scene_01.json", b'{"a":1}', mtime_ns=2_000_000_000)
    watcher.rescan()
    assert [os.path.basename(a[0]) for a in spy.scene_changed] == ["Scene_01.json"]


def test_rescan_sans_changement_ne_dit_rien(watcher, root):
    write(root / "assets/backgrounds/a.png")
    spy = start(watcher, root)
    watcher.rescan()
    watcher.rescan()
    pump()
    assert spy.silent()


# ── Nos propres écritures ───────────────────────────────────────────


def test_sidecar_ecrit_par_l_editeur_reste_muet(watcher, root):
    spy = start(watcher, root)
    with watcher.suspended():
        write(root / "assets/backgrounds/a.json", b"{}")
    pump()
    watcher.rescan()
    pump()
    assert spy.silent()


def test_source_modifiee_dehors_pendant_une_suspension_est_rattrapee(watcher, root):
    write(root / "assets/backgrounds/a.png", b"1", mtime_ns=1_000_000_000)
    spy = start(watcher, root)
    with watcher.suspended():
        write(root / "assets/backgrounds/a.png", b"22", mtime_ns=2_000_000_000)
    pump()
    assert spy.names("asset_modified") == ["a.png"]


def test_suspensions_imbriquees(watcher, root):
    spy = start(watcher, root)
    with watcher.suspended():
        with watcher.suspended():
            write(root / "assets/backgrounds/a.json", b"{}")
        write(root / "assets/backgrounds/b.json", b"{}")
    pump()
    watcher.rescan()
    pump()
    assert spy.silent()


# ── La corbeille `.temp/` (cf. core/resources/deleted_files) ────────


def _corbeille(watcher, root):
    from core.resources.deleted_files import DeletedFilesBin
    bin_ = DeletedFilesBin(root.resolve())
    bin_.attach_watcher(watcher)
    return bin_


def test_ranger_dans_temp_n_est_pas_une_suppression_externe(watcher, root):
    f = root / "assets/backgrounds/a.png"
    write(f, b"1", mtime_ns=1_000_000_000)
    spy = start(watcher, root)
    bin_ = _corbeille(watcher, root)
    bin_.stash([f])
    pump()
    watcher.rescan()
    pump()
    assert spy.silent()


def test_rendre_depuis_temp_n_est_pas_un_depot_externe(watcher, root):
    f = root / "assets/backgrounds/a.png"
    write(f, b"1", mtime_ns=1_000_000_000)
    spy = start(watcher, root)
    bin_ = _corbeille(watcher, root)
    bin_.stash([f])
    bin_.restore([f])
    pump()
    watcher.rescan()
    pump()
    assert spy.silent()


def test_un_depot_externe_pendant_un_rangement_reste_signale(watcher, root):
    a = root / "assets/backgrounds/a.png"
    write(a, b"1", mtime_ns=1_000_000_000)
    spy = start(watcher, root)
    bin_ = _corbeille(watcher, root)
    with watcher.suspended():
        bin_.stash([a])
        write(root / "assets/backgrounds/b.png", b"bb")      # dehors, pas à nous
    pump()
    assert spy.names("asset_appeared") == ["b.png"]


def test_temp_n_est_pas_surveille(watcher, root):
    spy = start(watcher, root)
    write(root / ".temp/assets/backgrounds/x.png")
    watcher.rescan()
    pump()
    assert spy.silent()


# ── Cycle de vie ────────────────────────────────────────────────────


def test_unwatch_fait_taire_le_watcher(watcher, root):
    spy = start(watcher, root)
    watcher.unwatch()
    write(root / "assets/backgrounds/a.png")
    watcher.rescan()
    pump()
    assert spy.silent()


def test_changer_de_projet_oublie_l_ancien_etat(watcher, root, tmp_path_factory):
    write(root / "assets/backgrounds/a.png")
    start(watcher, root)
    other = tmp_path_factory.mktemp("autre")
    (other / "assets/backgrounds").mkdir(parents=True)
    spy = Spy(watcher)
    watcher.watch_project(other)
    pump()
    assert spy.silent()                      # l'ancien projet n'est pas « supprimé »
    write(other / "assets/backgrounds/b.png")
    settle(watcher)
    assert spy.names("asset_appeared") == ["b.png"]


def test_changer_de_projet_pendant_une_copie_n_emet_rien(watcher, root, tmp_path_factory):
    start(watcher, root)
    write(root / "assets/backgrounds/a.png")
    watcher.rescan()                         # a.png en attente de stabilité
    other = tmp_path_factory.mktemp("autre")
    (other / "assets/backgrounds").mkdir(parents=True)
    spy = Spy(watcher)
    watcher.watch_project(other)
    pump()
    assert spy.silent()


def test_projet_sans_dossier_assets(watcher, tmp_path):
    spy = start(watcher, tmp_path)
    watcher.rescan()
    assert spy.silent()


# ── L'avertissement de dossier erroné (côté fenêtre) ────────────────


def test_fichier_dans_la_mauvaise_famille_avertit_dans_la_barre_de_statut(qapp, tmp_path):
    from types import SimpleNamespace
    from pathlib import Path
    from window import MainWindow

    shown: list[str] = []
    fake = SimpleNamespace(
        project=object(),
        _status=SimpleNamespace(showMessage=lambda text, ms=0: shown.append(text)))
    fake._match_asset_route = lambda p: MainWindow._match_asset_route(fake, p)
    fake._ASSET_ROUTES = MainWindow._ASSET_ROUTES

    MainWindow._on_asset_appeared(fake, str(tmp_path / "backgrounds" / "boom.wav"))

    assert len(shown) == 1
    assert "boom.wav" in shown[0] and "backgrounds" in shown[0] and ".wav" in shown[0]
