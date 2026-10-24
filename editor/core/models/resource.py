"""Resource — base commune à tous les objets moteur identifiés par un nom et
stockés en JSON (cf. core/resource_store.ResourceStore pour la persistance)."""

import dataclasses
from dataclasses import dataclass, fields
from typing import TypeVar


@dataclass
class Resource:
    """
    Base pour tout objet identifié par un nom et stocké en JSON.
    to_dict/from_dict génériques via dataclasses ; les types avec des
    champs imbriqués non-dataclass-natifs (listes d'autres dataclasses)
    peuvent surcharger ces deux méthodes.
    """
    name: str = "resource"
    # L'identité stable de l'asset (cf. models/ids.py) : écrite et relue par le ResourceStore, qui la place
    # juste après le nom dans le JSON. Un attribut et non un champ : aucun modèle n'a à la porter dans sa
    # propre sérialisation (une douzaine ont la leur), et `asdict` ne la voit pas. Vide tant que l'asset
    # n'a jamais été enregistré. Aucune sous-classe ne doit avoir de champ `id` de premier niveau.
    id = ""
    # L'extension du fichier où l'asset vit (cf. models/asset_extensions.py) : chaque type d'asset stocké déclare la sienne,
    # le type se lit ainsi dans le nom du fichier. `.json` pour ce qui n'est pas un asset à part entière.
    sidecar_extension = ".json"
    # Le nom de l'attribut qui porte le chemin du fichier SOURCE (PNG, WAV, .hex…), "" pour un asset qui n'en a pas
    # (scène, prefab, table). Sur disque il s'écrit toujours `source`, dans l'en-tête.
    source_field = ""

    def header(self) -> dict:
        """L'en-tête commun de tout sidecar : `name`, `id`, puis `source` si l'asset en a une. Le seul endroit
        qui le compose : chaque store l'écrit en tête du JSON, avant le corps propre au type."""
        head = {"name": self.name, "id": self.id}
        source = getattr(self, self.source_field, None) if self.source_field else None
        if source:
            head["source"] = source
        return head

    @classmethod
    def from_header(cls, d: dict) -> dict:
        """Le dictionnaire du sidecar prêt pour `from_dict` : `source` redevient l'attribut du modèle. Un sidecar
        d'avant l'en-tête commun, qui disait `asset`, se lit tel quel."""
        if cls.source_field and "source" in d:
            d = {k: v for k, v in d.items() if k != "source"} | {cls.source_field: d["source"]}
        return d

    def body(self) -> dict:
        """Le corps du sidecar : `to_dict` privé de ce que l'en-tête porte déjà."""
        skip = {"name", "id", "source", self.source_field}
        return {k: v for k, v in self.to_dict().items() if k not in skip}

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict):
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in valid})


T = TypeVar("T", bound=Resource)


# Mime types pour le drag&drop interne à l'éditeur (utilisés par window.py
# et scene_editor.py — définis ici pour éviter un import circulaire entre eux).
MIME_PREFAB_TEMPLATE = "application/x-gba-prefab-template"  # drag Prefab → instancier + placer dans scène
MIME_CANVAS_ACTOR    = "application/x-gba-canvas-actor"  # drag Actor (canvas) → dossier de l'onglet Disk : en faire un prefab
MIME_UI_LAYOUT       = "application/x-gba-ui-layout"   # drag Layout (Interface) → l'ajouter à la scène active
MIME_SCRIPT          = "application/x-gba-script"
MIME_ANIMATED_BG     = "application/x-gba-animated-background"  # drag fond animé → poser sur un fond hôte
MIME_MUSIC           = "application/x-gba-music"       # drag musique → état de la MusicBox
