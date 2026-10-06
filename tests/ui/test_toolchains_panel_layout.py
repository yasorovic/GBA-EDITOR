"""La disposition du panneau « Toolchains » des réglages : titres au-dessus des champs
(pas de colonne à gauche qui rétrécit les textes), une seule astuce en bas de page,
chemins habituels en gras, aucune commande d'installation pour mGBA."""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QLineEdit

from core import toolchain
from ui.common.install_commands import InstallCommands
from ui.common.notice import NoticeBox
from ui.common.settings_dialog import ToolchainsPanel


def _panneau(monkeypatch, tmp_path):
    monkeypatch.setattr(toolchain, "IS_LINUX", True)
    monkeypatch.setattr(toolchain.Toolchain, "_load_config", lambda self: {})
    outils = toolchain.Toolchain()
    outils._status = {"grit": None, "make": None, "arm-none-eabi-gcc": None, "mgba": None}
    panneau = ToolchainsPanel(outils)
    panneau.resize(600, 700)
    panneau.show()
    return panneau


def _titre(panneau, texte) -> QLabel:
    return next(l for l in panneau.findChildren(QLabel) if l.text() == texte)


def test_les_titres_sont_au_dessus_des_champs(qapp, monkeypatch, tmp_path):
    panneau = _panneau(monkeypatch, tmp_path)
    champs = panneau.findChildren(QLineEdit)
    for titre, champ in zip(("devkitPro", "mgba"), champs):
        t, c = _titre(panneau, titre), champ
        assert t.mapTo(panneau, t.rect().topLeft()).y() < c.mapTo(panneau, c.rect().topLeft()).y()
        assert t.mapTo(panneau, t.rect().topLeft()).x() == c.mapTo(panneau, c.rect().topLeft()).x()


def test_une_seule_astuce_en_bas_avec_les_chemins_en_gras(qapp, monkeypatch, tmp_path):
    panneau = _panneau(monkeypatch, tmp_path)
    astuces = panneau.findChildren(NoticeBox)
    assert len(astuces) == 1
    corps = astuces[0]._body.text()
    assert "<b>C:\\devkitPro</b>" in corps and "<b>/opt/devkitpro</b>" in corps
    derniere_ligne = max(w.mapTo(panneau, w.rect().bottomLeft()).y()
                         for w in (*panneau.findChildren(QLineEdit), *panneau.findChildren(InstallCommands)))
    assert astuces[0].mapTo(panneau, astuces[0].rect().topLeft()).y() > derniere_ligne


def test_seul_devkitpro_a_des_commandes_d_installation(qapp, monkeypatch, tmp_path):
    panneau = _panneau(monkeypatch, tmp_path)
    visibles = [b for b in panneau.findChildren(InstallCommands) if b.isVisible()]
    assert len(visibles) == 1
    assert "dkp-pacman" in "\n".join(l.text() for l in visibles[0].findChildren(QLabel))
