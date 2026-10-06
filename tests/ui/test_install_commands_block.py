"""Les commandes d'installation montrées sous Linux (`ui/common/install_commands.py`).

Une seule source de commandes (`core.toolchain.install_commands`) ; ce bloc les affiche
avec « Copier ». Sous Windows il reste invisible : l'installateur s'en charge."""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from core import toolchain
from ui.common import install_commands as block_module
from ui.common.install_commands import InstallCommands
from ui.common.toolchain_dialog import ToolchainMissingDialog


def _sous_linux(monkeypatch, est_linux: bool):
    monkeypatch.setattr(toolchain, "IS_LINUX", est_linux)


def _dans_un_parent(bloc) -> QWidget:
    """Comme dans l'application : le bloc est un enfant, c'est le parent qui s'affiche."""
    parent = QWidget()
    QVBoxLayout(parent).addWidget(bloc)
    parent.show()
    return parent


def _textes(widget) -> str:
    return "\n".join(label.text() for label in widget.findChildren(QLabel))


def test_le_bloc_montre_les_commandes_sous_linux(qapp, monkeypatch):
    _sous_linux(monkeypatch, True)
    bloc = InstallCommands("devkitPro")
    parent = _dans_un_parent(bloc)
    assert bloc.isVisible()
    assert "sudo dkp-pacman -S gba-dev" in _textes(bloc)


def test_le_bloc_est_invisible_hors_linux(qapp, monkeypatch):
    _sous_linux(monkeypatch, False)
    bloc = InstallCommands("devkitPro")
    parent = _dans_un_parent(bloc)
    assert not bloc.isVisible()


def test_set_needed_masque_le_bloc_d_un_outil_present(qapp, monkeypatch):
    _sous_linux(monkeypatch, True)
    bloc = InstallCommands("devkitPro")
    parent = _dans_un_parent(bloc)
    bloc.set_needed(False)
    assert not bloc.isVisible()
    bloc.set_needed(True)
    assert bloc.isVisible()


def test_set_needed_ne_montre_jamais_un_bloc_sans_commandes(qapp, monkeypatch):
    _sous_linux(monkeypatch, False)
    bloc = InstallCommands("devkitPro")
    parent = _dans_un_parent(bloc)
    bloc.set_needed(True)
    assert not bloc.isVisible()


def test_copier_met_les_commandes_dans_le_presse_papiers(qapp, monkeypatch):
    _sous_linux(monkeypatch, True)
    monkeypatch.setattr(block_module.QTimer, "singleShot", lambda *_: None)   # pas d'attente
    bloc = InstallCommands("devkitPro")
    bloc._copy.click()
    copie = QApplication.clipboard().text().splitlines()
    assert copie[0].startswith("wget https://apt.devkitpro.org/")
    assert copie[-1] == "sudo dkp-pacman -S gba-dev"


def test_la_boite_construction_impossible_propose_les_commandes_de_devkitpro(qapp, monkeypatch):
    _sous_linux(monkeypatch, True)
    boite = ToolchainMissingDialog(["grit", "mgba"])
    assert "sudo dkp-pacman -S gba-dev" in _textes(boite)


def test_la_boite_ne_propose_pas_de_commandes_pour_mgba_ni_pour_ce_qui_est_present(qapp, monkeypatch):
    _sous_linux(monkeypatch, True)
    boite = ToolchainMissingDialog(["mgba"])          # devkitPro complet
    assert "dkp-pacman" not in _textes(boite)
    assert "apt install" not in _textes(boite)
