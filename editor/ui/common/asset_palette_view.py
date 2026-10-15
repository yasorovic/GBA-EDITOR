"""editor/ui/common/asset_palette_view.py — vues tier-ASSET pour PaletteSlotGridAsset.

`PaletteSlotGridAsset` (ui/common/palette_slot_grid) consomme une vue duck-typée
(`scene_entries` / `asset_entries` / `can_add()`). Le Scene Inspector fournit une
`codegen.palette_alloc.ScenePaletteView` ; ce module fournit l'équivalent au tier
ASSET (représentation de la PAL_BANK d'un objet C), sur le même modèle :

- palettes DÉRIVÉES du PNG           -> entrées « own » grisées (overridables) ;
- une dérivée OVERRIDÉE (catalogue)  -> entrée « override » (marqueur + couleurs
  et nom du catalogue portés directement par l'entrée : ref_colors / ref_name) ;
- palettes AJOUTÉES du catalogue      -> scene_entries éditables (clic = remplacer).

Chaque entrée porte son `idx` = index réel dans `ba.palettes` (les tuiles y
réfèrent), pour que le consommateur mappe les signaux vers le modèle.
"""
from __future__ import annotations
from ui.common.labels import label
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _Inst:
    """Étiquette (le widget lit `entry.instances[*].label` pour les tooltips)."""
    label: str


@dataclass
class SceneEntryView:
    slot: int          # index réel dans ba.palettes
    name: str
    colors: list


@dataclass
class AssetEntryView:
    idx: int                       # index réel dans ba.palettes
    own_colors: list               # couleurs d'ORIGINE (grisées / restauration)
    instances: list                # list[_Inst]
    state: str = "own"             # "own" | "override"
    ref_slot: Optional[int] = None
    ref_name: Optional[str] = None   # override : nom de la banque catalogue ciblée
    ref_colors: Optional[list] = None  # override : couleurs effectives (catalogue)
    bank_span: int = 1
    overridable: bool = True


@dataclass
class AssetPaletteGridView:
    scene_entries: list
    asset_entries: list
    cap: int = 16
    allow_add: bool = True   # False en lecture seule (8bpp/bitmap)

    def can_add(self) -> bool:
        if not self.allow_add:
            return False
        used = len(self.scene_entries) + sum(
            max(1, e.bank_span) for e in self.asset_entries)
        return used < self.cap


def asset_palette_view(asset, read_only: bool = False) -> AssetPaletteGridView:
    """Vue des sous-palettes d'un asset à SubPaletteAssetMixin (BackgroundAsset,
    SpriteAsset) pour PaletteSlotGridAsset — dérivées PNG grisées/overridables +
    ajoutées catalogue éditables.

    `read_only` (ex. fond 8bpp/bitmap) : toutes les palettes en « own »
    non-overridables, aucun ajout possible."""
    palettes = list(getattr(asset, "palettes", []) or [])
    if read_only:
        return AssetPaletteGridView(
            scene_entries=[],
            asset_entries=[
                AssetEntryView(idx=i, own_colors=list(cols),
                               instances=[_Inst(label('common.palette_i', i=i))],
                               overridable=False)
                for i, cols in enumerate(palettes)
            ],
            allow_add=False,
        )

    source_palettes = list(getattr(asset, "source_palettes", []) or [])
    derived = len(source_palettes)
    overrides = getattr(asset, "palette_overrides", {}) or {}
    added_names = list(getattr(asset, "added_palettes", []) or [])    # les ajoutées sont des références au catalogue
    scene_entries: list = []
    asset_entries: list = []
    for idx, cols in enumerate(palettes):
        if idx < derived:
            if idx in overrides:
                src = source_palettes[idx] if idx < len(source_palettes) else cols
                asset_entries.append(AssetEntryView(
                    idx=idx, own_colors=list(src),
                    instances=[_Inst(label('asspalview.palette_idx_png', idx=idx))],
                    state="override", ref_name=overrides[idx], ref_colors=list(cols),
                ))
            else:
                asset_entries.append(AssetEntryView(
                    idx=idx, own_colors=list(cols),
                    instances=[_Inst(label('asspalview.palette_idx_png', idx=idx))],
                ))
        else:
            position = idx - derived
            name = added_names[position] if position < len(added_names) else label('asspalview.palette_idx', idx=idx)
            scene_entries.append(SceneEntryView(slot=idx, name=name, colors=list(cols)))
    return AssetPaletteGridView(scene_entries, asset_entries)


def background_palette_view(ba, read_only: bool = False) -> AssetPaletteGridView:
    """Vue des sous-palettes d'un BackgroundAsset (cf. asset_palette_view)."""
    return asset_palette_view(ba, read_only)


def sprite_palette_view(sprite, read_only: bool = False) -> AssetPaletteGridView:
    """Vue des sous-palettes (PAL_BANK) d'un SpriteAsset (cf. asset_palette_view)."""
    return asset_palette_view(sprite, read_only)
