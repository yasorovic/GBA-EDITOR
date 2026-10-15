"""Gestion partagée des sous-palettes d'un asset (BackgroundAsset/SpriteAsset)."""
from core.models.tile_codec import pack_se, unpack_se


def decode_palette_overrides(raw) -> dict:
    """Relit palette_overrides du JSON ({"idx": "nom_catalogue"}) en dict[int, str].
    Tolère l'absence (None) et les clés mal formées (ignorées)."""
    out: dict[int, str] = {}
    if not raw:
        return out
    for key, name in raw.items():
        try:
            out[int(key)] = str(name)
        except (ValueError, TypeError):
            continue
    return out


class SubPaletteAssetMixin:
    """Gestion partagée des SOUS-PALETTES d'un asset (sa PAL_BANK), sur le modèle
    scène : palettes dérivées du PNG grisées + override catalogue + « + ».

    Les FIELDS `palettes` / `source_palettes` / `palette_overrides` sont déclarés
    par chaque dataclass consommatrice (BackgroundAsset, SpriteAsset). `palettes`
    = couleurs EFFECTIVES (rendu/build) ; `source_palettes` = baseline PNG
    restaurable ; `palette_overrides` = {idx dérivé -> nom banque catalogue}.
    `remove_palette` ne remappe la tilemap que si l'asset en a une (fonds) —
    inopérant pour les sprites (OAM, pas de tilemap)."""

    def add_palette_colors(self, colors: list) -> int:
        """Ajoute une sous-palette (copie de ≤16 couleurs BGR555, ex: depuis une
        PaletteBank du catalogue). Retourne son index, ou -1 si déjà 16 palettes."""
        if len(self.palettes) >= 16:
            return -1
        pal = list(colors[:16])
        pal += [0] * (16 - len(pal))
        self.palettes.append(pal)
        return len(self.palettes) - 1

    def replace_palette(self, idx: int, colors: list) -> None:
        """Remplace les couleurs de la sous-palette `idx`."""
        if 0 <= idx < len(self.palettes):
            pal = list(colors[:16])
            pal += [0] * (16 - len(pal))
            self.palettes[idx] = pal

    def clear_palette(self, idx: int) -> None:
        """Vide la sous-palette `idx` (ne garde que l'index 0 réservé). Ne retire
        pas la palette (indices inchangés), contrairement à remove_palette."""
        if 0 <= idx < len(self.palettes):
            from core.models.gba_color import RESERVED_SLOT_COLOR
            self.palettes[idx] = [RESERVED_SLOT_COLOR] + [0] * 15

    def remove_palette(self, idx: int) -> None:
        """Supprime la sous-palette `idx` et réconcilie les références : toute
        tuile/override pointant sur `idx` retombe sur 0, les index `> idx` sont
        décrémentés. Le remap de la baseline tuilée n'agit que sur un asset à
        tilemap (fonds)."""
        if not (0 <= idx < len(self.palettes)):
            return
        self.palettes.pop(idx)

        def _remap(v: int) -> int:
            return 0 if v == idx else (v - 1 if v > idx else v)

        # Overrides d'inpainting par tuile + baseline tilemap : fonds uniquement.
        if getattr(self, "tile_palette_overrides", None):
            self.tile_palette_overrides = {
                k: _remap(s) for k, s in self.tile_palette_overrides.items()
            }
        tilemap = getattr(self, "tilemap", None)
        if tilemap:
            for cell, se in enumerate(tilemap):
                tid, pb, fh, fv = unpack_se(se)
                tilemap[cell] = pack_se(tid, _remap(pb), fh, fv)
        if getattr(self, "tile_paint", None):
            self.tile_paint = {k: (c, _remap(p)) for k, (c, p) in self.tile_paint.items()}
        # Origine/override suivent le décalage d'index (retirer une dérivée
        # raccourcit la baseline ; l'override d'une dérivée disparue est levé).
        if idx < len(self.source_palettes):
            self.source_palettes.pop(idx)
        self.palette_overrides = {
            _remap(k): n for k, n in self.palette_overrides.items() if k != idx
        }

    # ── Origine des palettes (modèle scène : grisé + override) ────
    def derived_count(self) -> int:
        """Nb de sous-palettes DÉRIVÉES du PNG (baseline). Les indices
        `< derived_count` sont grisés/overridables ; les suivants sont ajoutés
        du catalogue (éditables)."""
        return len(self.source_palettes)

    def is_derived(self, idx: int) -> bool:
        """La sous-palette `idx` provient-elle du PNG (grisée/overridable) ?"""
        return 0 <= idx < len(self.source_palettes)

    def is_overridden(self, idx: int) -> bool:
        return idx in self.palette_overrides

    def override_palette(self, idx: int, name: str, colors: list) -> None:
        """Override une sous-palette DÉRIVÉE par une banque du catalogue : ses
        couleurs effectives deviennent `colors`, l'origine PNG reste dans
        `source_palettes` (restaurable). No-op si `idx` n'est pas dérivée."""
        if not self.is_derived(idx):
            return
        self.replace_palette(idx, colors)
        self.palette_overrides[idx] = name

    def restore_palette(self, idx: int) -> None:
        """Restaure une sous-palette dérivée overridée à ses couleurs PNG d'origine."""
        if idx in self.palette_overrides and self.is_derived(idx):
            self.replace_palette(idx, self.source_palettes[idx])
            self.palette_overrides.pop(idx, None)
