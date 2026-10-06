"""Le script de l'installateur Windows (`packaging/windows/installer.nsi`).

Il est en UTF-8 AVEC BOM : sans lui, makensis lit les accents avec la page de code
ANSI de la machine de build et l'installateur affiche « Ã© » à la place de « é »,
sur certaines machines seulement. Un éditeur qui retire le BOM le casse en silence."""
from __future__ import annotations

from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[2] / "packaging" / "windows" / "installer.nsi"
BOM = b"\xef\xbb\xbf"


def test_le_script_est_en_utf8_avec_bom():
    octets = INSTALLER.read_bytes()
    assert octets.startswith(BOM), "installer.nsi doit rester en UTF-8 avec BOM (cf. sa note d'encodage)"
    assert not octets[3:].startswith(BOM), "BOM doublé"
    octets[3:].decode("utf-8")           # lève si l'encodage est autre


def test_les_textes_francais_sont_accentues():
    """Le BOM n'a de sens que si les textes affichés l'utilisent : un « installe » sans accent
    reviendrait à l'ancien contournement ASCII."""
    texte = INSTALLER.read_text(encoding="utf-8-sig")
    assert "est installé" in texte
    assert "est installe" not in texte
