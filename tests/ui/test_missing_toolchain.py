"""Build & Run sans devkitPro ni mGBA : on dit ce qui manque et où l'installer,
puis on propose les réglages — la fenêtre de réglages ne surgit plus sans un mot.

Mêmes méthodes RÉELLES de `MainWindow` que `test_close_persists_pending` : sur une
doublure légère, avec une fausse boîte de dialogue qui note ce qu'on lui demande."""
from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtWidgets import QMessageBox

from core.toolchain import DEVKITPRO_URL, MGBA_URL


class _FausseBoite:
    """Prend la place de `QMessageBox` dans `window` : note le texte, répond au clic."""
    Icon = QMessageBox.Icon
    ButtonRole = QMessageBox.ButtonRole
    StandardButton = QMessageBox.StandardButton
    clic_sur_reglages = False
    derniere: "_FausseBoite | None" = None

    def __init__(self, parent=None):
        self.texte = self.titre = ""
        self._reglages = object()
        _FausseBoite.derniere = self

    def setIcon(self, icon): ...
    def setWindowTitle(self, title): self.titre = title
    def setText(self, text): self.texte = text

    def addButton(self, *args):
        if isinstance(args[0], str):
            return self._reglages
        return object()

    def exec(self): ...

    def clickedButton(self):
        return self._reglages if _FausseBoite.clic_sur_reglages else object()


def _fenetre(monkeypatch, outils):
    import window
    from window import MainWindow

    monkeypatch.setattr(window, "QMessageBox", _FausseBoite)
    ouverts = []
    fenetre = SimpleNamespace(
        toolchain=SimpleNamespace(check=lambda: outils),
        _open_settings=ouverts.append)
    fenetre._explain_missing_toolchain = MainWindow._explain_missing_toolchain.__get__(fenetre)
    return fenetre, ouverts


def test_le_message_nomme_ce_qui_manque_et_ou_l_installer(monkeypatch):
    fenetre, _ = _fenetre(monkeypatch, {"grit": None, "make": "C:/dkp/make.exe", "mgba": None})
    _FausseBoite.clic_sur_reglages = False

    fenetre._explain_missing_toolchain()

    texte = _FausseBoite.derniere.texte
    assert "grit" in texte and "mgba" in texte
    assert "make" not in texte.replace("Build & Run", "")        # ce qui est présent n'est pas cité
    assert DEVKITPRO_URL in texte and MGBA_URL in texte


def test_les_reglages_ne_s_ouvrent_que_si_on_les_demande(monkeypatch):
    fenetre, ouverts = _fenetre(monkeypatch, {"grit": None})

    _FausseBoite.clic_sur_reglages = False
    fenetre._explain_missing_toolchain()
    assert ouverts == []

    _FausseBoite.clic_sur_reglages = True
    fenetre._explain_missing_toolchain()
    assert ouverts == ["Toolchains"]
