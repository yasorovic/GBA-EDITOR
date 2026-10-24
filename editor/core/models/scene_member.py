"""SceneMember — l'en-tête commun de tout ce qui est POSÉ dans une scène.

Même grammaire que le sidecar d'un asset (cf. `Resource.header`), lue à l'intérieur de la scène :

    "name":   son nom de référence dans la scène (ce que les scripts citent)
    "id":     son identifiant unique dans la scène, qui ne change jamais
    "source": facultatif, l'id de l'asset dont il est l'instance (un prefab, un fond, une mise en page)

`source` désigne donc une ORIGINE, comme dans un sidecar : un chemin de fichier là-bas, un id d'asset ici.
Le nom reste la poignée du code écrit à la main, l'id celle des fichiers de données : renommer le prefab ne
réécrit aucune scène.

Les membres sont les acteurs, les calques de fond, les caméras, les fenêtres et les interfaces. Ils n'ont pas de
fichier à eux : leur scène les porte, et c'est elle qui leur donne leur id (`assign_member_ids`). L'id n'entre
jamais dans la ROM, comme tous les ids (cf. ids.py).
"""
from __future__ import annotations

from core.models.ids import is_id, new_id


class SceneMember:
    """Le jeu d'attributs d'un membre de scène. Des attributs de classe et non des champs : aucun modèle n'a
    à les porter dans sa propre sérialisation, et `asdict` ne les voit pas (même parti que `Resource.id`)."""
    id = ""
    source = ""

    def member_header(self) -> dict:
        head = {"name": self.name, "id": self.id}
        if self.source:
            head["source"] = self.source
        return head

    def read_member_header(self, d: dict) -> None:
        self.id = str(d.get("id") or "")
        self.source = str(d.get("source") or "")


def assign_member_ids(members) -> None:
    """Donne un id à chaque membre qui n'en a pas, ou qui porte celui d'un autre (la copie d'un acteur garde
    l'id de son original) : le premier dans l'ordre garde le sien."""
    members = list(members)
    kept: set[str] = set()
    pending = []
    for member in members:
        if is_id(member.id) and member.id not in kept:
            kept.add(member.id)
        else:
            pending.append(member)
    for member in pending:
        member.id = new_id(kept)
        kept.add(member.id)
