"""Contrat du rendu commun des infobulles."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "editor"))

from ui.common.tooltip import tooltip


def test_raccourci_en_gras_puis_effet_en_italique():
    result = tooltip(title="Rechercher", shortcut="Ctrl+F")
    assert result == "<b>Ctrl+F</b> | <i>Rechercher</i>"


def test_sans_raccourci_le_titre_est_en_gras():
    assert tooltip(title="Rechercher") == "<b>Rechercher</b>"


def test_precisions_et_avertissement_sont_secondaires():
    result = tooltip(title="Restaurer", body="Revient à la première importation.",
                     note="Le PNG source est recompressé.",
                     warning="La peinture sera perdue.")
    assert "<i>Le PNG source est recompressé.</i>" in result
    assert "⚠ <i>La peinture sera perdue.</i>" in result


def test_le_texte_du_catalogue_est_echappe():
    result = tooltip(title="A < B", body="Entrée\nÉchap")
    assert result == "<b>A &lt; B</b><br>Entrée<br>Échap"
