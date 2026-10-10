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
