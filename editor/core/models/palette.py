"""PaletteBank — une banque de 16 (ou 256) couleurs GBA (pool illimité, catalogue projet)."""

from dataclasses import dataclass, field
from typing import NamedTuple

from core.models.resource import Resource
# La réserve de l'index 0 et l'encodage des couleurs vivent dans gba_color (le
# module de format) ; palette les emploie pour se sérialiser. Import de haut
# niveau : gba_color n'importe plus rien de palette, il n'y a plus de cycle.
from core.models.gba_color import (
    RESERVED_SLOT_COLOR, bgr555_to_hex, hex_to_bgr555, read_colors, write_colors,
)


class PaletteUsage(NamedTuple):
    """Un usage d'une PaletteBank dans le projet — produit par
    `Project.palette_usages()`, affiché par la carte « USAGE » du Palette
    Editor.

    `kind` ∈ {"sprite", "background", "prefab", "scene"} : c'est à la fois le
    type d'élément et la clé de navigation (quel écran ouvrir au clic).
    `detail` explique COMMENT la palette est utilisée (slot, banque, scène
    d'ancrage) — jamais un chemin de fichier."""
    kind: str
    name: str
    detail: str

# Palette des éléments d'interface par défaut : celle qu'une scène neuve active
# et que son texte libre lit tant que l'auteur n'a pas choisi une autre banque
# (cf. `Project.seed_default_ui_palette`). Un nom du catalogue, pas une copie : si
# le projet ne l'a pas (supprimée, projet ancien), le défaut ne s'applique pas.
DEFAULT_UI_PALETTE = "_Microsoft Windows 16"


@dataclass
class PaletteBank(Resource):
    """Une palette nommée de 16 couleurs, catalogue illimité et unifié au
    niveau projet (assets/palettes/*.hex, un fichier visible par palette ; le
    JSON voisin ne contient que les métadonnées) — partagé entre OBJ et BG, une même palette peut servir
    aux deux. Une Scene en active jusqu'à 16 par pool (Scene.active_obj_palettes
    / active_bg_palettes) ; c'est cette sélection, pas le catalogue, qui
    occupe les banques hardware (physiquement séparées OBJ/BG) au build."""
    name: str = ""
    colors: list[int] = field(default_factory=list)  # valeurs BGR555 GBA
    size: int = 16   # capacité de la palette : 16 (4bpp / une banque) ou 256 (8bpp).
                     # Persisté dans le .json ; absent d'un ancien fichier -> 16.

    def __post_init__(self):
        """Normalise `size` (16 ou 256) et force l'index 0 vers
        RESERVED_SLOT_COLOR — point d'application unique, déclenché à la fois par
        une construction directe (presets, "Ajouter palette" côté UI) et par le
        chargement depuis disque (Resource.from_dict construit via cls(**kwargs)).
        Pas besoin de pas de migration séparé : les anciens fichiers JSON gardent
        leur ancienne valeur d'index 0 tant qu'ils ne sont pas re-sauvegardés,
        mais cette valeur est de toute façon écrasée à chaque chargement — sans
        incidence puisqu'elle n'est jamais affichée pour une tuile (index de
        palette 0 = toujours transparent au niveau hardware, OBJ comme BG)."""
        if self.size not in (16, 256):
            self.size = 16
        if self.colors:
            # On tronque défensivement à la capacité de la banque (un fichier édité
            # à la main pourrait déborder) : en 16, garantit que grit
            # (quantification sur toutes les couleurs) et main_gen (`colors[:16]`)
            # ne divergent jamais (indices >15 impossibles en 4bpp -> tuiles
            # corrompues) ; en 256, borne au maximum 8bpp.
            if len(self.colors) > self.size:
                self.colors = self.colors[:self.size]
            self.colors[0] = RESERVED_SLOT_COLOR

    # ROADMAP v0.24 : les couleurs s'écrivent en #RRGGBB. Seule raison de
    # surcharger les deux méthodes génériques de Resource — le reste de la
    # palette (`name`, `size`) se sérialise très bien tout seul.
    # Une couleur par ligne, et non les seize sur une seule : deux personnes
    # qui retouchent deux couleurs d'une même palette doivent pouvoir fusionner.
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["colors"] = write_colors(self.colors)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PaletteBank":
        return super().from_dict({**d, "colors": read_colors(d.get("colors", []))})

    # La persistance actuelle découpe une palette en deux fichiers : les
    # couleurs, lisibles par un humain, dans le .hex ; les rares métadonnées
    # de l'éditeur dans le sidecar JSON. Ces trois méthodes définissent ce
    # FORMAT de palette, sans savoir où il se trouve sur le disque.
    def to_metadata_dict(self) -> dict:
        return {"name": self.name, "size": self.size}

    def to_hex(self) -> str:
        """Forme canonique : une couleur #RRGGBB par ligne."""
        return "\n".join(bgr555_to_hex(color) for color in self.colors) + "\n"

    @classmethod
    def from_hex(cls, name: str, text: str, metadata: dict | None = None) -> "PaletteBank":
        """Construit une banque depuis sa source .hex et son sidecar éventuel."""
        colors: list[int] = []
        for line_number, raw in enumerate(text.splitlines(), 1):
            value = raw.strip()
            if not value:
                continue
            candidate = value[1:] if value.startswith("#") else value
            if len(candidate) != 6 or any(char not in "0123456789abcdefABCDEF" for char in candidate):
                raise ValueError(f"line {line_number}: colour expected in the form #RRGGBB")
            colors.append(hex_to_bgr555(value))
        if not colors:
            raise ValueError("the file contains no colour")

        requested_size = (metadata or {}).get("size")
        size = requested_size if requested_size in (16, 256) and len(colors) <= requested_size \
            else (256 if len(colors) > 16 else 16)
        return cls(name=name, colors=colors, size=size)


# Sentinel Actor/Prefab.pal_bank et BackgroundLayer.pal_bank : "Sans palette"
# — l'asset utilise SA PROPRE palette (couleurs du PNG, index 0 transparent),
# extraite à la volée et auto-allouée à une banque libre de la scène au build
# (cf. codegen/palette_alloc.py). C'est le défaut : un asset affiche ses
# couleurs d'origine tant qu'aucune palette du catalogue n'est explicitement
# assignée à ce slot.
OWN_PAL_BANK = -1
