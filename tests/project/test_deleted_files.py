"""`.temp/` : le dossier où va ce que l'auteur supprime.

Le magasin le branche (cf. test_soft_delete_name_reuse) ; ici on éprouve la
corbeille elle-même : où elle range, ce qu'elle refuse de toucher, et ce qu'elle
fait quand un déplacement échoue.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.history import Command, RefreshAfterCmd
from core.resources.deleted_files import DeletedFilesBin, TEMP_FOLDER_NAME


@pytest.fixture
def bin_(tmp_path):
    root = (tmp_path / "Jeu").resolve()
    root.mkdir()
    return DeletedFilesBin(root)


def make(bin_, relative: str, data: bytes = b"x") -> Path:
    path = bin_.project_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_le_fichier_est_range_sous_son_chemin_relatif(bin_):
    f = make(bin_, "assets/sfx/boom.wav")
    bin_.stash([f])
    assert not f.exists()
    assert (bin_.folder / "assets" / "sfx" / "boom.wav").is_file()
    assert bin_.folder.name == TEMP_FOLDER_NAME


def test_un_fichier_absent_est_ignore(bin_):
    bin_.stash([bin_.project_root / "assets" / "nope.png"])
    assert not bin_.folder.exists()


def test_un_fichier_hors_du_projet_n_est_jamais_touche(bin_, tmp_path):
    dehors = tmp_path / "ailleurs.png"
    dehors.write_bytes(b"x")
    bin_.stash([dehors])
    assert dehors.exists()
    assert not bin_.folder.exists()


def test_restaurer_remet_le_fichier_et_son_contenu(bin_):
    f = make(bin_, "assets/sfx/boom.wav", b"contenu")
    bin_.stash([f])
    bin_.restore([f])
    assert f.read_bytes() == b"contenu"
    assert not any(bin_.folder.rglob("boom.wav"))


def test_restaurer_ne_remplace_jamais_un_fichier_qui_a_repris_le_nom(bin_):
    f = make(bin_, "assets/sfx/boom.wav", b"ancien")
    bin_.stash([f])
    f.write_bytes(b"nouveau")               # un autre fichier prend le nom
    bin_.restore([f])
    assert f.read_bytes() == b"nouveau"
    assert (bin_.folder / "assets" / "sfx" / "boom.wav").read_bytes() == b"ancien"


def test_restaurer_ce_qui_n_a_pas_ete_range_est_sans_effet(bin_):
    f = make(bin_, "assets/sfx/boom.wav")
    bin_.restore([f])
    assert f.is_file()


def test_deux_suppressions_du_meme_nom_s_empilent(bin_):
    f = make(bin_, "assets/sfx/boom.wav", b"un")
    bin_.stash([f])
    make(bin_, "assets/sfx/boom.wav", b"deux")
    bin_.stash([f])
    assert (bin_.folder / "assets" / "sfx" / "boom.wav").read_bytes() == b"un"
    assert (bin_.folder / "assets" / "sfx" / "boom~2.wav").read_bytes() == b"deux"
    bin_.restore([f])                       # la plus récente d'abord
    assert f.read_bytes() == b"deux"


def test_un_deplacement_refuse_laisse_le_fichier_en_place(bin_, monkeypatch):
    f = make(bin_, "assets/sfx/boom.wav")

    def refuse(*_a, **_k):
        raise PermissionError("verrouillé")

    monkeypatch.setattr("core.resources.deleted_files.shutil.move", refuse)
    bin_.stash([f])
    assert f.is_file()
    bin_.restore([f])                       # rien n'a été rangé : sans effet
    assert f.is_file()


def test_purger_detruit_tout(bin_):
    f = make(bin_, "assets/sfx/boom.wav")
    bin_.stash([f])
    bin_.purge()
    assert not bin_.folder.exists()
    bin_.restore([f])                       # plus rien à rendre
    assert not f.exists()


def test_purger_sans_dossier_ne_plante_pas(bin_):
    bin_.purge()


def test_le_surveillant_est_suspendu_et_informe(bin_):
    f = make(bin_, "assets/sfx/boom.wav")
    calls: list = []

    class FauxSurveillant:
        def suspended(self):
            from contextlib import contextmanager

            @contextmanager
            def ctx():
                calls.append("suspendu")
                yield
                calls.append("repris")
            return ctx()

        def claim(self, path):
            calls.append(("revendique", path))

    bin_.attach_watcher(FauxSurveillant())
    bin_.stash([f])
    assert calls == ["suspendu", ("revendique", f), "repris"]


# ── L'historique ────────────────────────────────────────────────────


class _Compte(Command):
    label = "x"

    def __init__(self):
        self.log: list[str] = []

    def execute(self):
        self.log.append("execute")

    def undo(self):
        self.log.append("undo")


def test_refresh_after_cmd_rafraichit_apres_chaque_sens():
    inner, refreshed = _Compte(), []
    cmd = RefreshAfterCmd(inner, lambda: refreshed.append(len(inner.log)))
    cmd.execute()
    cmd.undo()
    cmd.execute()
    assert inner.log == ["execute", "undo", "execute"]
    assert refreshed == [1, 2, 3]           # toujours APRÈS la commande
    assert cmd.label == "x"
