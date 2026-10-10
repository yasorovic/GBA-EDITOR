"""ui/scene_manager/canvas/canvas_raster.py — rasterisation des fonds et aperçus.

Extrait de `scene_canvas` (A3), le bloc le plus bas : rendu PAR TUILE d'un layer
BG dans le canvas (palette d'origine de l'asset + overrides de scène peints),
conversion PIL→Qt, et le choix de frame/flip d'aperçu d'un acteur. Ne dépend que
du modèle, de `grit_conversion` et de Qt ; aucun item/scène ne remonte ici.

`_pal_to_rgb16`, `_pil_to_qimage`, `_DIR_ID_LUT` restent privés (usage interne).
`bg_pixmap`/`preview_frame_for_actor`/`layer_png_path`/`build_bg_raster`/
`BgLayerRaster` traversent (façade + contrôleurs), d'où l'absence d'underscore.
"""
from __future__ import annotations

from typing import Optional

from core.models.tile_codec import unpack_se, hex_to_tile, hex_to_tile8, flip_h, flip_v
from core.project import Project
from codegen.grit_conversion import resolve_palette_bank
from PyQt6.QtGui import QImage, QPainter, QPixmap


def _pal_to_rgb16(colors_bgr555: list) -> list:
    """Banque BGR555 → 16 triplets (r,g,b), complétée à 16 (index manquants →
    noir). L'index 0 reste dans la liste mais est traité comme transparent au
    rendu (cf. BgLayerRaster)."""
    from core.models.gba_color import bgr555_to_rgb888
    out = []
    for i in range(16):
        out.append(bgr555_to_rgb888(colors_bgr555[i]) if i < len(colors_bgr555) else (0, 0, 0))
    return out


class BgLayerRaster:
    """État de rendu PAR TUILE d'un layer BG dans le canvas de scène.

    Base = **palette d'origine** de l'asset : chaque tuile est rendue depuis la
    représentation compressée (`tileset` + `tilemap` + `palettes` du
    BackgroundAsset), exactement comme le build. L'asset n'est JAMAIS modifié.

    Par-dessus, des **overrides de scène** réassignent la palette d'une tuile
    (`layer.tile_palette_overrides` → slot dans `scene.active_bg_palettes`) : on relit le
    MÊME index de pixel dans une autre banque de 16 couleurs (sémantique
    `SE_PALBANK` du GBA). Réversible — retirer l'override rend la palette
    d'origine. Patche un bloc 8×8 en place pendant la peinture."""

    TILE = 8

    def __init__(self, compiled: dict, bank_rgb_for):
        # compiled     : {tiles_w, tiles_h, tileset(list[hex]), tilemap(list[SE]),
        #                 palettes(list[list[int]] BGR555)} — palettes d'origine.
        # bank_rgb_for : callable(slot:int) -> list[(r,g,b)] (16) | None, banque
        #                active de la scène pour un override.
        self.tiles_w = compiled["tiles_w"]
        self.tiles_h = compiled["tiles_h"]
        self._tilemap = list(compiled["tilemap"])
        self._bpp = compiled.get("bpp", 4)
        if self._bpp == 8:
            # 8bpp : tuiles en octets, UNE palette de 256 couleurs (pas de banques,
            # pas d'override de scène — cf. _pal_for).
            from core.models.gba_color import bgr555_to_rgb888
            self._tiles = [hex_to_tile8(t) for t in compiled["tileset"]]
            pal = compiled["palettes"][0] if compiled["palettes"] else []
            self._pal_rgb = [[bgr555_to_rgb888(c) for c in pal]]
        else:
            self._tiles = [hex_to_tile(t) for t in compiled["tileset"]]
            self._pal_rgb = [_pal_to_rgb16(pal) for pal in compiled["palettes"]]
        self._bank_rgb_for = bank_rgb_for
        self._qimg = QImage(self.tiles_w * self.TILE, self.tiles_h * self.TILE,
                            QImage.Format.Format_RGBA8888)

    # ── Décodage d'une cellule ────────────────────────────────────
    def _cell_grid(self, cell: int):
        """Grille d'index 8×8 (list[64]) de la cellule, flips appliqués."""
        tid, pb, fh, fv = unpack_se(self._tilemap[cell])
        grid = tuple(self._tiles[tid]) if tid < len(self._tiles) else tuple([0] * 64)
        if fh:
            grid = flip_h(grid)
        if fv:
            grid = flip_v(grid)
        return grid, pb

    def _cell_block(self, cell: int, pal_rgb):
        """Bloc PIL RGBA 8×8 de la cellule avec la palette `pal_rgb` (index 0 =
        transparent)."""
        from PIL import Image
        grid, _ = self._cell_grid(cell)
        blk = Image.new("RGBA", (self.TILE, self.TILE), (0, 0, 0, 0))
        px = blk.load()
        for y in range(self.TILE):
            for x in range(self.TILE):
                idx = grid[y * self.TILE + x]
                if idx == 0 or idx >= len(pal_rgb):
                    continue
                r, g, b = pal_rgb[idx]
                px[x, y] = (r, g, b, 255)
        return blk

    def _pal_for(self, cell: int, slot):
        """Palette RGB à utiliser pour une cellule : override de scène si `slot`
        résolu (4bpp uniquement), sinon la palette d'origine de la tuile. En 8bpp,
        pas de banques ni d'override : toujours l'unique palette de 256."""
        if self._bpp != 8 and slot is not None:
            bank = self._bank_rgb_for(slot)
            if bank:
                return bank
        _, pb = self._cell_grid(cell)
        return self._pal_rgb[pb] if pb < len(self._pal_rgb) else self._pal_rgb[0]

    # ── Composition ───────────────────────────────────────────────
    def render(self, tile_palette_overrides: dict):
        """Recompose tout le layer : palettes d'origine + overrides de scène."""
        from PIL import Image
        out = Image.new("RGBA", (self.tiles_w * self.TILE, self.tiles_h * self.TILE),
                        (0, 0, 0, 0))
        for cell in range(len(self._tilemap)):
            col, row = cell % self.tiles_w, cell // self.tiles_w
            slot = tile_palette_overrides.get((col, row))
            blk = self._cell_block(cell, self._pal_for(cell, slot))
            out.paste(blk, (col * self.TILE, row * self.TILE))
        self._qimg = _pil_to_qimage(out)

    def patch_tile(self, col: int, row: int, slot):
        """Recolorise le bloc 8×8 (col,row) : override `slot`, ou palette
        d'origine si slot None."""
        if not (0 <= col < self.tiles_w and 0 <= row < self.tiles_h):
            return
        cell = row * self.tiles_w + col
        blk = self._cell_block(cell, self._pal_for(cell, slot))
        block_qimg = _pil_to_qimage(blk)
        painter = QPainter(self._qimg)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(col * self.TILE, row * self.TILE, block_qimg)
        painter.end()

    def to_pixmap(self) -> QPixmap:
        return QPixmap.fromImage(self._qimg)


def _pil_to_qimage(img) -> QImage:
    """PIL RGBA → QImage indépendant (copié, buffer non partagé)."""
    data = bytes(img.tobytes("raw", "RGBA"))
    return QImage(data, img.width, img.height,
                  QImage.Format.Format_RGBA8888).copy()


def build_bg_raster(p: Project, scene, layer, ap) -> Optional["BgLayerRaster"]:
    """Construit le `BgLayerRaster` d'un layer depuis sa palette d'origine
    (représentation compressée de l'asset). Peignable pour TOUT layer ayant une
    image — indépendant de `layer.pal_bank` (plus de banque de base requise :
    c'est ça qui rend les layers « Sans palette » peignables). None si pas
    d'image/asset exploitable."""
    if not layer.background_name or not ap.is_file():
        return None
    ba = p.get_background(layer.background_name)
    from core.bg_import import compiled_background
    # `p` transmis : le canvas montre aussi les fonds animés posés sur ce fond
    # dans le Background Editor, figés sur leur première image.
    compiled = compiled_background(ba, ap, p)
    if not compiled or not compiled.get("tilemap"):
        return None

    def _bank_rgb_for(slot: int):
        b = resolve_palette_bank(p, scene.active_bg_palettes, slot)
        return _pal_to_rgb16(b.colors) if b and b.colors else None

    raster = BgLayerRaster(compiled, _bank_rgb_for)
    raster.render(getattr(layer, "tile_palette_overrides", {}) or {})
    return raster


def bg_pixmap(p: Project, scene, layer, ap) -> Optional[QPixmap]:
    """Pixmap d'un layer BG pour le canvas — rendu PAR TUILE depuis la palette
    d'origine de l'asset + overrides de scène peints (`layer.tile_palette_overrides`).
    Repli sur le PNG brut si l'asset n'a pas de représentation exploitable."""
    # layer.background_name vide -> `ap` pointe sur le DOSSIER background_images_dir
    # (pas un fichier) : ne rien afficher (l'ancien QPixmap(dir) échouait
    # silencieusement, mais Image.open(dir) lève PermissionError).
    if not layer.background_name or not ap.is_file():
        return None
    raster = build_bg_raster(p, scene, layer, ap)
    if raster is not None:
        return raster.to_pixmap()
    return QPixmap(str(ap))


# dir_x/dir_y (-1|0|1) → dir id 1-8, identique au _dlut du runtime
# (NW=8,N=1,NE=2,W=7,omni=0,E=3,SW=6,S=5,SE=4).
_DIR_ID_LUT = {
    (-1, -1): 8, (0, -1): 1, (1, -1): 2,
    (-1,  0): 7, (0,  0): 0, (1,  0): 3,
    (-1,  1): 6, (0,  1): 5, (1,  1): 4,
}


def preview_frame_for_actor(sprite, sprite_comp, actor):
    """
    Frame statique + flip à afficher pour un actor dans le canvas de scène.
    Choisit la direction correspondant à dir_x/dir_y de l'actor (comme le
    runtime) ; pour une direction miroir, retourne la frame de la direction
    source + le flip du miroir (à composer avec le flip du component).
    Repli identique au runtime : direction demandée absente → omni (dir 0) →
    première direction. Retourne (frame|None, flip_h, flip_v).
    """
    state_name = getattr(sprite_comp, "initial_state", None) if sprite_comp else None
    state = next((s for s in sprite.states if s.name == state_name), None)
    state = state or (sprite.states[0] if sprite.states else None)
    if not state or not state.directions:
        return None, False, False
    dir_map = {sd.dir: sd for sd in state.directions}
    dx = max(-1, min(1, getattr(actor, "dir_x", 0)))
    dy = max(-1, min(1, getattr(actor, "dir_y", 0)))
    want = _DIR_ID_LUT.get((dx, dy), 0)
    sd = dir_map.get(want) or dir_map.get(0) or state.directions[0]
    if sd.mirror_of is not None:
        # Miroir : les frames vivent sur la direction source, retournées.
        src = dir_map.get(sd.mirror_of, sd)
        frame = src.frames[0] if src.frames else None
        return frame, sd.flip_h, sd.flip_v
    return (sd.frames[0] if sd.frames else None), False, False


def layer_png_path(project: Project, layer):
    """Chemin du PNG source d'un layer (via son BackgroundAsset sidecar)."""
    ba = project.get_background(layer.background_name)
    return project.background_image_path(ba, layer.background_name)
