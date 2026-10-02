"""Fermer la fenêtre n'abandonne aucune modification en attente.

Les écritures différées (debounce de 400 ms, cadrage caméra, texte du Script
Editor) ne partent pas toutes seules si la fenêtre se ferme avant leur
minuterie. `_confirm_close` les vide avant de laisser fermer, et, si le disque
refuse, laisse l'utilisateur choisir au lieu de perdre le travail en silence.

Même méthode que `test_screen_revisit_refresh` : les VRAIES méthodes de
`MainWindow` sur un stub léger, sans widget construit."""
from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtWidgets import QMessageBox


class _Recorder:
    """Note l'ordre des appels dans une liste partagée."""
    def __init__(self, log, name, fail=None):
        self.log, self.name, self.fail = log, name, fail

    def _hit(self, what):
        self.log.append(f"{self.name}.{what}")

    def stop(self):
        self._hit("stop")

    def flush_camera_pos(self):
        self._hit("flush_camera_pos")

    def flush_pending_edits(self):
        self._hit("flush_pending_edits")

    def save(self):
        self._hit("save")
        if self.fail:
            raise self.fail


def _make_window(log, *, project=True, save_error=None):
    from window import MainWindow

    win = SimpleNamespace(
        project=_Recorder(log, "project", fail=save_error) if project else None,
        _save_timer=_Recorder(log, "timer"),
        scene_editor=_Recorder(log, "scene"),
        _script_editor=_Recorder(log, "script"),
    )
    win._persist_project = MainWindow._persist_project.__get__(win)
    win._confirm_close = MainWindow._confirm_close.__get__(win)
    return win


def test_fermer_vide_les_ecritures_en_attente_puis_sauvegarde():
    log = []
    win = _make_window(log)

    assert win._confirm_close() is True
    assert log == ["timer.stop", "scene.flush_camera_pos",
                   "script.flush_pending_edits", "project.save"]


def test_fermer_sans_projet_ne_touche_a_rien():
    log = []
    win = _make_window(log, project=False)

    assert win._confirm_close() is True
    assert log == []


def test_echec_d_ecriture_puis_refus_garde_la_fenetre_ouverte(monkeypatch):
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: asked.append(args) or QMessageBox.StandardButton.No)
    win = _make_window([], save_error=PermissionError("disque verrouillé"))

    assert win._confirm_close() is False
    assert len(asked) == 1
    assert "disque verrouillé" in asked[0][2]       # l'utilisateur voit la cause


def test_echec_d_ecriture_puis_accord_ferme_quand_meme(monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    win = _make_window([], save_error=PermissionError("disque verrouillé"))

    assert win._confirm_close() is True
