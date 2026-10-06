"""La règle unique du tooltip « note d'abord, détail ensuite »."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "editor"))

from ui.common.notes_tooltip import notes_tooltip


def test_les_deux_absents_donnent_une_chaine_vide():
    # Vide → Qt ne montre aucun tooltip, comportement voulu.
    assert notes_tooltip("", "") == ""
    assert notes_tooltip("   ", "  ") == ""


def test_note_seule():
    assert notes_tooltip("attention au spawn", "") == "attention au spawn"


def test_detail_seul():
    assert notes_tooltip("", "OBJ · 32×16 tiles") == "OBJ · 32×16 tiles"


def test_note_en_tete_puis_detail():
    assert notes_tooltip("boss", "OBJ") == "boss\n\nOBJ"
