"""ui/common/notes_tooltip.py : un tooltip qui mène par la note de l'auteur.

Un seul endroit décide de l'ordre « note d'abord, détail matériel ensuite » et
du séparateur, pour que tous les items du canvas et du graphe le composent
pareil. Une note absente ne laisse que le détail ; un détail absent ne laisse
que la note ; les deux absents laissent une chaîne vide — Qt ne montre alors
aucun tooltip, ce qui est le comportement voulu (un item sans note ni info
technique n'a rien à dire au survol)."""
from __future__ import annotations


def notes_tooltip(notes: str, detail: str = "") -> str:
    """Le texte de survol d'un item : sa note libre en tête, l'info technique
    ensuite. L'un ou l'autre peut manquer ; les deux manquants → chaîne vide."""
    note = (notes or "").strip()
    detail = (detail or "").strip()
    if note and detail:
        return f"{note}\n\n{detail}"
    return note or detail
