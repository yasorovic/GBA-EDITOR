"""Les commandes d'installation montrées aux utilisateurs Linux : une seule source
(`core.toolchain.install_commands`), vide là où un installateur s'en charge."""
from __future__ import annotations

from core import toolchain as tc


def test_linux_donne_les_commandes_de_devkitpro_dans_l_ordre(monkeypatch):
    monkeypatch.setattr(tc, "IS_LINUX", True)
    commands = tc.install_commands("devkitPro")
    assert commands[0].startswith("wget https://apt.devkitpro.org/")
    assert commands[-1] == "sudo dkp-pacman -S gba-dev"


def test_mgba_n_a_pas_de_commandes(monkeypatch):
    """mGBA s'obtient en exécutable sur son site officiel, que l'écran montre déjà."""
    monkeypatch.setattr(tc, "IS_LINUX", True)
    assert tc.install_commands("mGBA") == []


def test_hors_linux_aucune_commande(monkeypatch):
    """Windows a son installateur : l'écran garde le lien de téléchargement."""
    monkeypatch.setattr(tc, "IS_LINUX", False)
    assert tc.install_commands("devkitPro") == []


def test_outil_inconnu_aucune_commande(monkeypatch):
    monkeypatch.setattr(tc, "IS_LINUX", True)
    assert tc.install_commands("autre") == []


def test_la_liste_rendue_n_est_pas_la_table_interne(monkeypatch):
    """Un appelant qui modifie la liste ne doit pas altérer les commandes suivantes."""
    monkeypatch.setattr(tc, "IS_LINUX", True)
    tc.install_commands("devkitPro").append("rm -rf /")
    assert "rm -rf /" not in tc.install_commands("devkitPro")
