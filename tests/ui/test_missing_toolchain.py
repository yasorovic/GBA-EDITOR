"""Build & Run sans devkitPro ni mGBA : on dit ce qui manque et où l'installer,
puis on propose les réglages — la fenêtre de réglages ne surgit plus sans un mot.

Méthode RÉELLE de `MainWindow` sur une doublure légère ; la boîte est la vraie
`ToolchainMissingDialog` (jamais affichée), dont on lit le texte."""
from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtWidgets import QLabel

from core.toolchain import DEVKITPRO_URL, MGBA_URL


def _fenetre(monkeypatch, outils, demande_reglages):
    from ui.common import toolchain_dialog
    from window import MainWindow

    boites = []

    class _Boite(toolchain_dialog.ToolchainMissingDialog):
        def __init__(self, missing, parent=None):
            super().__init__(missing)        # la doublure de fenêtre n'est pas un QWidget

        def exec(self):
            boites.append(self)
            self.open_settings_requested = demande_reglages
            return 0

    monkeypatch.setattr(toolchain_dialog, "ToolchainMissingDialog", _Boite)
    ouverts = []
    fenetre = SimpleNamespace(
        toolchain=SimpleNamespace(check=lambda: outils),
        _open_settings=ouverts.append)
    fenetre._explain_missing_toolchain = MainWindow._explain_missing_toolchain.__get__(fenetre)
    return fenetre, ouverts, boites


def test_le_message_nomme_ce_qui_manque_et_ou_l_installer(qapp, monkeypatch):
    fenetre, _, boites = _fenetre(
        monkeypatch, {"grit": None, "make": "C:/dkp/make.exe", "mgba": None}, False)

    fenetre._explain_missing_toolchain()

    texte = " ".join(label.text() for label in boites[0].findChildren(QLabel))
    assert "grit" in texte and "mgba" in texte
    assert "make" not in texte.replace("Build & Run", "")        # ce qui est présent n'est pas cité
    assert DEVKITPRO_URL in texte and MGBA_URL in texte


def test_les_reglages_ne_s_ouvrent_que_si_on_les_demande(qapp, monkeypatch):
    fenetre, ouverts, _ = _fenetre(monkeypatch, {"grit": None}, False)
    fenetre._explain_missing_toolchain()
    assert ouverts == []

    fenetre, ouverts, _ = _fenetre(monkeypatch, {"grit": None}, True)
    fenetre._explain_missing_toolchain()
    assert ouverts == ["Toolchains"]
