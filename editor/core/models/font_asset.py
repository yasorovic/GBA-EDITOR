"""FontAsset — police logique utilisée par les scènes et les mises en page.

Une ``Font`` décrit une SOURCE : une planche bitmap, un descripteur BMFont ou,
à terme, une face vectorielle. Un ``FontAsset`` décrit comment le projet
l'emploie : quelles sources couvrent ses caractères, à quelle taille les
rastériser et quel rendu GBA produire. Les deux ne doivent pas se confondre :
la même source peut servir à un texte de dialogue 8 px et à un titre 16 px.

Ce module ne rasterise rien. Il ne contient que les choix persistés de
l'auteur ; ``core.font_rasterizer`` les résoudra au build et dans l'aperçu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.models.font import color_from_hex, color_to_hex
from core.models.resource import Resource
from core.models import asset_extensions


FONT_VARIANTS = ("regular", "bold", "italic", "bold_italic")
HINTING_MODES = ("normal", "light", "mono", "none")
RASTER_MODES = ("binary", "coverage", "dither")
DITHER_PATTERNS = ("none", "bayer_2x2", "bayer_4x4")
# ``auto`` reste une recette dynamique : une famille peut contenir une strike
# bitmap à 5 px mais pas à 8 px. La résolution se fait donc face ouverte.
PIXEL_FIT_MODES = ("auto", "native", "grid_fit", "bitmap_strike")


@dataclass(frozen=True)
class FontFace:
    """Une face native : aucune synthèse de poids ou d'italique."""
    source_name: str
    weight: int = 400
    italic: bool = False

    def to_dict(self) -> dict:
        return {"source_name": self.source_name, "weight": self.weight,
                **({"italic": True} if self.italic else {})}

    @classmethod
    def from_dict(cls, data: dict):
        name = str(data.get("source_name", ""))
        return cls(name, max(1, int(data.get("weight", 400))), bool(data.get("italic", False))) if name else None


def _faces(value) -> list[FontFace]:
    if not isinstance(value, list):
        return []
    seen, out = set(), []
    for data in value:
        face = FontFace.from_dict(data) if isinstance(data, dict) else None
        if face and face.source_name not in seen:
            seen.add(face.source_name); out.append(face)
    return out


def _variant_sources(value) -> dict[str, list[str]]:
    """Relit une table de sources sans laisser une valeur JSON invalide
    empoisonner le modèle.

    Les variantes absentes restent absentes : elles signifient « cette face
    n'existe pas », jamais « synthétise-la depuis regular ».
    """
    if not isinstance(value, dict):
        return {}
    out: dict[str, list[str]] = {}
    for variant, names in value.items():
        if variant not in FONT_VARIANTS or not isinstance(names, list):
            continue
        clean = [str(name) for name in names if isinstance(name, str) and name]
        if clean:
            out[variant] = clean
    return out


@dataclass
class FontAsset(Resource):
    """Une police logique et sa recette de rasterisation GBA.

    ``sources`` est une chaîne de couverture par variante : le premier nom est
    la source primaire, les suivants sont les fallbacks. Les noms référencent
    des ``Font`` dans ``assets/fonts/`` ; ils ne sont pas des chemins afin que
    les renommages de ressources restent possibles.
    """
    sidecar_extension = asset_extensions.FONT_ASSET

    name: str = "font_asset"
    sources: dict[str, list[str]] = field(default_factory=dict)
    faces: list[FontFace] = field(default_factory=list)
    auto_family: str = ""                 # famille dont les faces se réconcilient

    # Les valeurs sont exprimées dans le vocabulaire de l'auteur (pixels), pas
    # dans celui de FreeType. Le rasterizer déduira le ppem de ``pixel_height``.
    pixel_height: int = 8
    line_height: int = 8
    pixel_fit: str = "auto"
    hinting: str = "normal"
    raster_mode: str = "binary"
    coverage_threshold: int = 128
    dither_pattern: str = "none"
    offset_x: int = 0
    offset_y: int = 0
    prefer_bitmap_strike: bool = True

    # Ces couleurs disent COMMENT une planche bitmap est lue ; elles ne sont
    # pas intrinsèques à une police vectorielle. Elles migreront les anciens
    # ``Font.bg_color`` / ``Font.space_color`` quand la consommation basculera
    # vers FontAsset. Un asset qui n'emploie que des sources vectorielles les
    # laisse simplement à None.
    bg_color: Optional[tuple] = None
    space_color: Optional[tuple] = None

    def source_names(self, variant: str = "regular") -> list[str]:
        """La chaîne de couverture de ``variant``, sans synthèse implicite."""
        return list(self.sources.get(variant, ())) if variant in FONT_VARIANTS else []

    def primary_source_name(self, variant: str = "regular") -> str:
        """La première source de la chaîne, ou ``""`` si la face est absente."""
        names = self.source_names(variant)
        return names[0] if names else ""

    def key_colors(self) -> list[tuple]:
        """Couleurs bitmap transparentes, dans le même ordre que ``Font``."""
        out: list[tuple] = []
        for color in (self.bg_color, self.space_color):
            if color is not None and tuple(color) not in out:
                out.append(tuple(color))
        return out

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "sources": {variant: list(names) for variant, names in self.sources.items()},
            **({"faces": [face.to_dict() for face in self.faces]} if self.faces else {}),
            **({"auto_family": self.auto_family} if self.auto_family else {}),
            "pixel_height": self.pixel_height,
            "line_height": self.line_height,
            "pixel_fit": self.pixel_fit,
            "hinting": self.hinting,
            "raster_mode": self.raster_mode,
            "coverage_threshold": self.coverage_threshold,
            "dither_pattern": self.dither_pattern,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "prefer_bitmap_strike": self.prefer_bitmap_strike,
            **({"bg_color": color_to_hex(self.bg_color)} if self.bg_color else {}),
            **({"space_color": color_to_hex(self.space_color)} if self.space_color else {}),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FontAsset":
        def choice(key: str, choices: tuple[str, ...], default: str) -> str:
            value = data.get(key, default)
            return value if value in choices else default

        return cls(
            name=str(data.get("name", "font_asset")),
            sources=_variant_sources(data.get("sources")),
            faces=_faces(data.get("faces")),
            auto_family=str(data.get("auto_family", "")),
            pixel_height=max(1, int(data.get("pixel_height", 8))),
            line_height=max(1, int(data.get("line_height", data.get("pixel_height", 8)))),
            pixel_fit=choice("pixel_fit", PIXEL_FIT_MODES, "auto"),
            hinting=choice("hinting", HINTING_MODES, "normal"),
            raster_mode=choice("raster_mode", RASTER_MODES, "binary"),
            coverage_threshold=max(0, min(255, int(data.get("coverage_threshold", 128)))),
            dither_pattern=choice("dither_pattern", DITHER_PATTERNS, "none"),
            offset_x=int(data.get("offset_x", 0)),
            offset_y=int(data.get("offset_y", 0)),
            prefer_bitmap_strike=bool(data.get("prefer_bitmap_strike", True)),
            bg_color=color_from_hex(data.get("bg_color")),
            space_color=color_from_hex(data.get("space_color")),
        )
