"""
editor/grit_conversion.py — Conversion des assets bruts en fichiers C/headers.

Trois étapes indépendantes, chacune appelable séparément :

    GritBackground(emit, run_cmd).run(p, layers)      -> {asset}_bg{slot}.h/.c
    GritSprites(emit, run_cmd).run(p, sprites)        -> sprite_X.h/.c
    MmutilAudio(emit, run_cmd, toolchain).run(p, assets) -> soundbank.h/.bin

`emit(event, data)` et `run_cmd(cmd, prefix, cwd)` sont injectés depuis
BuildWorker pour que le pipeline reste découplé de l'UI.
"""
from __future__ import annotations

import math
import os
import shutil
import struct
from pathlib import Path
from typing import Optional, Callable

from core.app_info import APP_NAME
from core.tool_process import run_tool
from core.models.sprite import SpriteAsset
from core.models.background import BackgroundLayer
from core.project import Project
from core.diagnostic import build_error, build_warning
# `sym` importée sous le nom `c_sym` : « sym » est un nom de variable locale
# très courant dans la génération (`sym = bg_layer_sym(...)`), et une locale
# masquerait la fonction dans toute la portée où elle apparaît.
from codegen.c_names import sym as c_sym
import codegen.build_output as build_output
from codegen.asset_cache import AssetBuildCache, file_digest, tool_signature


# ── Helpers image ──────────────────────────────────────────────────────────────

def relative_arg(path: Path, cwd: Path) -> str:
    """Le chemin à PASSER à un outil externe qui tourne dans `cwd`.

    grit et mmutil sont des exécutables Windows « ANSI » : un dossier de projet
    dont le nom sort de la page de code (japonais, cyrillique…) leur arrive en
    `?`, et ils ne trouvent plus leurs fichiers. Le dossier de travail, lui, est
    passé en Unicode au système : un chemin RELATIF à `cwd` n'a donc plus rien
    de risqué tant que les noms de fichiers eux-mêmes le sont peu. Repli sur le
    chemin absolu si les deux n'ont pas de chemin relatif (autre lecteur)."""
    try:
        return os.path.relpath(path, cwd)
    except ValueError:
        return str(path)


def png_size(path: Path) -> tuple[int, int]:
    """Lit width/height depuis le header IHDR du PNG (bytes 16-23)."""
    try:
        with open(path, "rb") as f:
            f.seek(16)
            w, h = struct.unpack(">II", f.read(8))
        return w, h
    except Exception:  # tolerated: unreadable PNG: the validator reports it
        return 0, 0


def count_frames(p: Project, sprite: SpriteAsset) -> int:
    """Nombre de frames uniques (dédupliquées) que grit convertit réellement pour ce sprite."""
    _, ordered = sprite_unique_frames(sprite)
    return max(1, len(ordered))


# ── GritBackground ─────────────────────────────────────────────────────────────

def bg_layer_sym(asset_name: str, bg_slot: int) -> str:
    """Symbole C stable pour les Tiles/Map/Pal d'un layer — basé sur l'asset
    et le slot GBA, pas sur le nom d'image (peut contenir des caractères
    invalides) ni sur la scène (un BackgroundAsset peut être partagé par
    plusieurs scènes, comme un Prefab — cf. resolve_palette_bank côté
    pipeline.py)."""
    return c_sym(f"{asset_name}_bg{bg_slot}")


def bg_layer_sym_for(scene, layer) -> str:
    """Symbole d'un layer au build. Par défaut PARTAGÉ entre scènes
    (`bg_layer_sym`, dédup ROM). Mais si le layer porte des overrides de palette
    par tuile (`layer.tile_palette_overrides`), la map devient PROPRE À LA SCÈNE (la
    scène est la source de vérité) : symbole qualifié par le nom de scène. Les
    tuiles restant identiques, seule la map (SE_PALBANK) diffère — mais on émet
    tuiles+map ensemble par simplicité (surcoût ROM seulement pour un fond
    partagé ET peint dans plusieurs scènes)."""
    if getattr(layer, "tile_palette_overrides", None):
        return c_sym(f"{scene.name}_{layer.background_name}_bg{layer.bg_slot}")
    return bg_layer_sym(layer.background_name, layer.bg_slot)


def bg_map_geometry(w: int, h: int) -> tuple[int, int, int]:
    """tw/th (dimensions en tuiles) + ms (bits map_size grit/BGxCNT, 0-3)
    depuis les dimensions pixel d'une image de layer BG. Partagé entre
    main_gen.bg_info (codegen) et pipeline.py (garde-fou budget VRAM)."""
    tw = min(max(math.ceil(w / 8), 1), 64)
    th = min(max(math.ceil(h / 8), 1), 64)
    ms = (1 if tw > 32 else 0) | (2 if th > 32 else 0)
    return tw, th, ms


def bg_map_sbb_count(ms: int) -> int:
    """Nombre de SBB (2 Ko chacun) qu'une map de cette taille occupe."""
    return {0: 1, 1: 2, 2: 2, 3: 4}[ms]


def quantize_asset(path: Path, bank_colors: list[int], mode: str) -> "Image.Image":
    """Quantifie `path` vers `bank_colors`, retourne une image RGBA.
    mode="direct_index" : les index 'P' du fichier se calent sur la banque
    (sprites). mode="nearest" : chaque pixel prend la couleur la plus proche (BG)."""
    from core.models.gba_color import quantize_image_to_bank, direct_index_to_bank
    if mode == "direct_index":
        return direct_index_to_bank(path, bank_colors)
    from PIL import Image
    return quantize_image_to_bank(Image.open(path).convert("RGBA"), bank_colors)


class GritBackground:
    """Convertit les tilesets BG via grit -> {asset}_bg{slot}.h/.c, un appel
    grit indépendant par layer (comme GritSprites, un appel par sprite)."""

    def __init__(self, grit_path: Path, emit: Callable, run_cmd: Callable,
                 asset_cache: AssetBuildCache | None = None):
        self._grit    = grit_path
        self._emit    = emit
        self._run_cmd = run_cmd
        self._cache   = asset_cache

    def run(
        self,
        p: Project,
        layers: list[tuple["BackgroundAsset", BackgroundLayer, Optional[list], Optional[int]]],
    ) -> bool:
        """
        layers : liste dédupliquée globalement par (asset.name, layer.bg_slot)
        — construite par pipeline.py. Chaque entrée = (asset, layer, couleurs
        effectives, mp_slot). Les couleurs effectives = palette propre du PNG
        (mode « None ») ou palette référencée résolue. `mp_slot` = index de
        banque hardware alloué (cf. palette_alloc) forcé dans le champ
        SE_PALBANK de la map via `-mp`. Couleurs None : legacy (grit choisit
        sa palette, non copiée en VRAM).
        """
        if not layers:
            return True
        if not self._grit:
            self._emit("diagnostic", build_error("not found", "grit")); return False

        cache_hits = 0
        for asset, layer, colors, mp_slot in layers:
            if not layer.background_name:
                continue
            png_name = asset.asset if asset and asset.asset else f"{layer.background_name}.png"
            ap = p.background_images_dir / png_name
            if not ap.exists():
                self._emit("diagnostic", build_error(f"image missing: {layer.background_name}", "grit"))
                return False

            quantize = bool(colors)
            sym = bg_layer_sym(asset.name, layer.bg_slot)
            outputs = [p.grit_out_dir / f"{sym}.c", p.grit_out_dir / f"{sym}.h"]
            fingerprint = (self._cache.fingerprint({
                "source": file_digest(ap),
                "asset": asset.to_dict(),
                # La sortie grit legacy ne dépend du layer que par son asset
                # référencé et son CBB ; scroll/overrides sont consommés plus
                # tard par l'émission de scène, pas par cette conversion.
                "layer": {"background_name": layer.background_name,
                          "bg_slot": layer.bg_slot},
                "palette": colors or [],
                "palette_slot": mp_slot,
                "grit": tool_signature(self._grit),
            }) if self._cache else "")
            if self._cache and self._cache.hit(f"background:{sym}", fingerprint, outputs):
                cache_hits += 1
                continue
            tmp = p.grit_out_dir / f"{sym}.png"
            # Quantification nearest vers la banque du layer (le BG n'a pas
            # encore de compression own_palette propre).
            mode = "nearest"
            if quantize:
                try:
                    quantize_asset(ap, colors, mode).save(tmp)
                except ValueError as e:
                    self._emit("diagnostic", build_error(str(e), "grit"))
                    return False
                self._emit("log_line",
                           f"[palette] BG '{asset.name}' BG{layer.bg_slot} -> bank {mp_slot} ({len(colors)} colours, mode "
                           f"{mode})")
            else:
                shutil.copy2(ap, tmp)
            self._emit("log_line", f"[grit BG] {asset.name} BG{layer.bg_slot} <- {layer.background_name}")

            scratch = p.grit_out_dir / "_grit"
            scratch.mkdir(parents=True, exist_ok=True)
            out_base = str(scratch / sym)
            cmd = [
                str(self._grit), relative_arg(tmp, p.grit_out_dir),
                "-gt", "-gB4", "-mRtf", "-mLf",
                "-p", "-pn16", "-ftc",
                "-o", relative_arg(Path(out_base), p.grit_out_dir), "-s", sym,
            ]
            if quantize and mp_slot is not None:
                cmd.append(f"-mp{mp_slot}")
            if not self._run_cmd(cmd, "[grit BG]", cwd=p.grit_out_dir):
                return False

            if quantize:
                if not remap_tiles_to_bank(Path(out_base + ".c"), colors, self._emit):
                    return False
            # grit écrit dans son bac à sable : on republie ses deux sorties par
            # build_output, qui neutralise l'horodatage et conserve la date si
            # leur contenu n'a pas changé.
            for ext in (".c", ".h"):
                src_f = Path(out_base + ext)
                if src_f.exists():
                    build_output.write(p.grit_out_dir / f"{sym}{ext}",
                                       src_f.read_text(encoding="utf-8", errors="replace"))
            if self._cache and all(path.is_file() for path in outputs):
                self._cache.store(f"background:{sym}", fingerprint)
        if cache_hits:
            self._emit("log_line", f"[cache] backgrounds: {cache_hits} hit(s), "
                                   f"{len(layers) - cache_hits} reconverted")
        return True


# ── Sprite sheet reconstruction ────────────────────────────────────────────────

def _frame_key(frame: "AnimFrame") -> tuple:
    """Clé hashable identifiant la composition d'une frame (tuiles + positions
    + flip par tuile — deux frames identiques sauf pour une tuile retournée
    doivent être traitées comme distinctes)."""
    return tuple(sorted(
        (t.src_col, t.src_row, t.dst_col, t.dst_row, t.flip_h, t.flip_v)
        for t in frame.tiles
    ))


def seq_key(src_sd: "StateDirection", flip_h: bool, flip_v: bool) -> tuple:
    """Clé hashable d'une séquence d'animation : compositions de ses frames
    (dans l'ordre) + flip appliqué. Deux directions produisant exactement la
    même suite de frames retournées de la même façon partagent un bloc."""
    return (tuple(_frame_key(f) for f in src_sd.frames), flip_h, flip_v)


def sprite_unique_frames(sprite: SpriteAsset) -> tuple[dict, list]:
    """Layout du sheet reconstruit : chaque séquence (state,direction) occupe un
    bloc CONTIGU de frames. C'est impératif — le runtime joue une direction via
    `frame = start + k` (k = 0..count-1) sur une plage contiguë ; dédupliquer au
    niveau frame casserait cette contiguïté (séquences non séquentielles →
    frames erronées / hors limites dans la loop). On déduplique donc au niveau
    séquence entière : deux directions identiques (mêmes frames + même flip,
    ex. une source et son omni) partagent le même bloc, mais une frame répétée
    dans une même séquence (ping-pong A,B,C,B) est stockée telle quelle pour
    rester contiguë.

    Fait autorité sur l'ordre des frames pour le sheet reconstruit
    (build_sprite_sheet_indexed) ET les tables d'animation C
    (gen_sprite.anim_tables_for) — les deux partagent ce layout.

    Retourne (seq_starts, ordered) où seq_starts[seq_key] = offset de départ du
    bloc dans ordered, et ordered = [(AnimFrame, flip_h, flip_v), ...] dans
    l'ordre du sheet."""
    seq_starts: dict[tuple, int] = {}
    ordered: list = []
    for state in sprite.states:
        dir_map = {sd.dir: sd for sd in state.directions}
        for sd in state.directions:
            src_sd = dir_map.get(sd.mirror_of, sd) if sd.mirror_of is not None else sd
            key = seq_key(src_sd, sd.flip_h, sd.flip_v)
            if key not in seq_starts:
                seq_starts[key] = len(ordered)
                for f in src_sd.frames:
                    ordered.append((f, sd.flip_h, sd.flip_v))
    return seq_starts, ordered


# ── Sprite sheet reconstruction — mode 'P' ─────────────────────────────────────
# Compose les frames en préservant les index de palette (crop/flip par index,
# pas de couleur). Alimenté par un PNG 'P' issu de render_indexed(source,
# own_palette) — cf. GritSprites.run.

def _paste_indexed(dst, src, pos: tuple[int, int]):
    """Colle `src` (mode 'P') sur `dst` (mode 'P') à `pos`, en sautant les
    pixels d'index 0 de `src` (transparent par convention) pour ne jamais
    écraser le contenu déjà posé sur `dst` — miroir du paste(mask=piece) RGBA,
    qu'on ne peut pas faire directement en mode 'P' (pas un masque valide)."""
    dst_px = dst.load()
    src_px = src.load()
    ox, oy = pos
    sw, sh = src.size
    for y in range(sh):
        for x in range(sw):
            idx = src_px[x, y]
            if idx != 0:
                dst_px[ox + x, oy + y] = idx


def pad_sprite_png_indexed(
    src: Path,
    frame_w: int,
    frame_h: int,
    out_dir: Path,
    emit: Callable,
) -> Optional[Path]:
    """Padde un PNG 'P' à des multiples de frame_w×frame_h en préservant
    palette et index (pas de conversion couleur)."""
    try:
        from PIL import Image
        img = Image.open(src)
        if img.mode != "P":
            emit("diagnostic", build_error(f"not an indexed PNG (mode {img.mode!r})", "pad", src.name))
            return None
        w, h = img.size
        target_w = ((w + frame_w - 1) // frame_w) * frame_w
        target_h = ((h + frame_h - 1) // frame_h) * frame_h
        out = out_dir / f"_padidx_{src.name}"
        if w == target_w and h == target_h:
            img.save(out)
            return out
        emit("log_line",
             f"[pad] {src.name} {w}×{h} -> {target_w}×{target_h} (frame {frame_w}×{frame_h}, indexed)")
        padded = Image.new("P", (target_w, target_h), 0)
        padded.putpalette(img.getpalette())
        _paste_indexed(padded, img, (0, 0))
        padded.save(out)
        return out
    except Exception as e:
        emit("diagnostic", build_error(f"indexed padding error: {e}", "pad", src.name))
        return None


def _compose_frame_indexed(src_img, frame: "AnimFrame", fw: int, fh: int):
    """Compose une frame fw×fh tuile par tuile en mode 'P' (crop/flip/collage
    par index, pas de calcul couleur)."""
    from PIL import Image
    out = Image.new("P", (fw, fh), 0)
    out.putpalette(src_img.getpalette())
    sw, sh = src_img.size
    for t in frame.tiles:
        sx, sy = t.src_col * 8, t.src_row * 8
        if sx < 0 or sy < 0 or sx + 8 > sw or sy + 8 > sh:
            continue
        piece = src_img.crop((sx, sy, sx + 8, sy + 8))
        if t.flip_h:
            piece = piece.transpose(Image.FLIP_LEFT_RIGHT)
        if t.flip_v:
            piece = piece.transpose(Image.FLIP_TOP_BOTTOM)
        dx, dy = t.dst_col * 8, t.dst_row * 8
        _paste_indexed(out, piece, (dx, dy))
    return out


def build_sprite_sheet_indexed(
    src: Path,
    sprite: SpriteAsset,
    out_dir: Path,
    emit: Callable,
) -> Optional[Path]:
    """Reconstruit le spritesheet compact d'un sprite en mode 'P' (palette et
    index préservés à travers la recomposition multi-frame). Alimenté par
    render_indexed(source, own_palette)."""
    try:
        from PIL import Image
        fw, fh = sprite.frame_w, sprite.frame_h
        src_img = Image.open(src)
        if src_img.mode != "P":
            emit("diagnostic", build_error(
                f"not an indexed PNG (mode {src_img.mode!r})", "sheet", src.name))
            return None

        _, ordered = sprite_unique_frames(sprite)
        if not ordered:
            return pad_sprite_png_indexed(src, fw, fh, out_dir, emit)

        all_frames: list = []
        for f, flip_h, flip_v in ordered:
            tile = _compose_frame_indexed(src_img, f, fw, fh)
            if flip_h:
                tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
            if flip_v:
                tile = tile.transpose(Image.FLIP_TOP_BOTTOM)
            all_frames.append(tile)

        sheet = Image.new("P", (fw * len(all_frames), fh), 0)
        sheet.putpalette(src_img.getpalette())
        for i, tile in enumerate(all_frames):
            _paste_indexed(sheet, tile, (i * fw, 0))

        out = out_dir / f"_sheetidx_{src.stem}.png"
        sheet.save(out)
        emit("log_line",
             f"[sheet] {src.name} -> {len(all_frames)} frames ({fw}x{fh}px, indexed) -> {out.name}")
        return out
    except Exception as e:
        emit("diagnostic", build_error(f"indexed reconstruction error: {e}", "sheet", src.name))
        return None


# ── GritSprites ────────────────────────────────────────────────────────────────

_ARRAY_RE = r'(\w+{suffix})\[(\d+)\][^=]*=\s*\{{([^}}]*)\}}'


def remap_tiles_to_bank(c_path: Path, bank_colors: list[int], emit: Callable) -> bool:
    """Réécrit en place un .c généré par grit en 4bpp (sprite OU tileset BG,
    format de tableau identique) : les index de tuiles (nibbles) sont
    remappés vers l'ordre canonique de `bank_colors`, et la palette locale
    est remplacée par `bank_colors` telle quelle. Permet à plusieurs assets
    assignés à la même banque de partager des index de palette identiques
    (condition nécessaire pour être copiés une seule fois dans PAL_OBJ_RAM/
    PAL_BG_RAM par main_gen.py). Ne touche jamais un éventuel tableau de map
    (suffixe différent de Tiles/Pal)."""
    import re

    text = c_path.read_text()
    tiles_m = re.search(_ARRAY_RE.format(suffix="Tiles"), text)
    pal_m   = re.search(_ARRAY_RE.format(suffix="Pal"), text)
    if not tiles_m or not pal_m:
        emit("diagnostic", build_error("unexpected grit format", "palette", c_path.name))
        return False

    tiles_vals = [int(x, 16) for x in tiles_m.group(3).split(",") if x.strip()]
    pal_vals   = [int(x, 16) for x in pal_m.group(3).split(",") if x.strip()]

    remap: dict[int, int] = {}
    for local_idx, color in enumerate(pal_vals):
        remap[local_idx] = next(
            (canon_idx for canon_idx, bc in enumerate(bank_colors) if bc == color),
            local_idx,  # slot de padding grit (couleur inutilisée) — jamais référencé par Tiles
        )

    new_tiles = []
    for word in tiles_vals:
        new_word = 0
        for i in range(8):
            nibble = (word >> (4 * i)) & 0xF
            new_word |= (remap.get(nibble, nibble) & 0xF) << (4 * i)
        new_tiles.append(new_word)

    new_tiles_str = ",".join(f"0x{v:08X}" for v in new_tiles) + ","
    new_pal_str   = ",".join(f"0x{c:04X}" for c in (bank_colors + [0] * 16)[:16]) + ","

    text = text[:tiles_m.start(3)] + new_tiles_str + text[tiles_m.end(3):]
    pal_m2 = re.search(_ARRAY_RE.format(suffix="Pal"), text)
    text = text[:pal_m2.start(3)] + new_pal_str + text[pal_m2.end(3):]

    build_output.write(c_path, text)
    return True


def resolve_palette_bank(p: Project, active_names: list, slot: int):
    """Résout la PaletteBank référencée par `active_names[slot]` dans le
    catalogue unifié du projet (project.palettes, partagé OBJ/BG). None si
    le slot est hors limites, vide, ou si la palette a été supprimée du
    catalogue depuis — l'appelant garde alors son comportement legacy."""
    if not (0 <= slot < len(active_names)):
        return None
    name = active_names[slot]
    return p.get_palette(name) if name else None


def resolve_obj_palette_bank(p: Project, entity, scene: Optional["Scene"]):
    """Résout la PaletteBank OBJ RÉFÉRENCÉE par `entity.pal_bank` (Actor ou
    Prefab) via les palettes OBJ actives de `scene` — pal_bank est un slot
    (0-15) dans scene.active_obj_palettes. None si OWN_PAL_BANK (l'asset
    utilise sa propre palette, gérée par palette_alloc), scène absente, slot
    vide, ou palette supprimée du catalogue."""
    from core.models.palette import OWN_PAL_BANK
    pal_bank = getattr(entity, "pal_bank", OWN_PAL_BANK)
    if scene is None or pal_bank == OWN_PAL_BANK:
        return None
    return resolve_palette_bank(p, getattr(scene, "active_obj_palettes", []), pal_bank)


class GritSprites:
    """Convertit les sprites OBJ (acteurs + prefabs) via grit -> sprite_X.h/.c."""

    def __init__(self, grit_path: Path, emit: Callable, run_cmd: Callable,
                 asset_cache: AssetBuildCache | None = None):
        self._grit    = grit_path
        self._emit    = emit
        self._run_cmd = run_cmd
        self._cache   = asset_cache

    def run(
        self,
        p: Project,
        sprites: list[tuple[any, Optional[SpriteAsset], Optional[list]]],
    ) -> bool:
        """
        sprites : liste de (actor_ou_prefab, SpriteAsset, couleurs effectives
        ou None). Les couleurs effectives = palette propre du PNG (mode « None »)
        ou palette référencée résolue — calculées par l'appelant (pipeline.py).
        Un même SpriteAsset n'est converti qu'une fois (dédup par nom).
        """
        if not sprites:
            return True
        if not self._grit:
            self._emit("diagnostic", build_error("not found", "grit")); return False

        done: set[str] = set()
        cache_hits = 0
        for actor_or_pf, sprite, colors in sprites:
            if not sprite or not sprite.asset or sprite.name in done:
                continue
            done.add(sprite.name)

            ap = p.asset_abs(sprite.asset)
            if not ap or not ap.exists():
                self._emit("diagnostic", build_error(f"asset missing: {sprite.asset}", "grit"))
                return False

            # Résolution INDEXÉE universelle : le sprite est
            # rendu via SA own_palette (compression décidée dans son .json), puis
            # ses index se calent sur la banque finale `colors` (OWN -> own_palette ;
            # référencé -> banque). Fallback sur own_palette si banque non résolue.
            own_pal = list(getattr(sprite, "own_palette", []) or [])
            # own_pal est SANS le slot 0 réservé (cf. own_palette_from_source) —
            # render_indexed() l'attend tel quel (voir plus bas), mais bank_colors
            # (utilisé par quantize_asset direct_index + remap_tiles_to_bank, qui
            # eux exportent une banque matérielle 16 slots) doit l'inclure — le
            # cas normal passe déjà par `colors` (préfixé dans
            # palette_alloc.effective_palette_colors), ce fallback ne sert que si
            # la résolution en amont a échoué.
            from core.models.gba_color import RESERVED_SLOT_COLOR
            bank_colors = list(colors) if colors else ([RESERVED_SLOT_COLOR] + own_pal if own_pal else [])

            sym = f"sprite_{c_sym(sprite.name)}"
            outputs = [p.grit_out_dir / f"{sym}.c", p.grit_out_dir / f"{sym}.h"]
            fingerprint = (self._cache.fingerprint({
                "source": file_digest(ap),
                "sprite": sprite.to_dict(),
                "palette": bank_colors,
                "grit": tool_signature(self._grit),
            }) if self._cache else "")
            if self._cache and self._cache.hit(f"sprite:{sprite.name}", fingerprint, outputs):
                cache_hits += 1
                continue

            from core.models.gba_color import render_indexed
            p.grit_out_dir.mkdir(parents=True, exist_ok=True)
            p_src = p.grit_out_dir / f"_srcidx_{c_sym(sprite.name)}.png"
            render_indexed(ap, own_pal).save(p_src, transparency=0)
            grit_src = build_sprite_sheet_indexed(p_src, sprite, p.grit_out_dir, self._emit)
            if grit_src is None:
                return False

            if bank_colors:
                try:
                    quantize_asset(grit_src, bank_colors, "direct_index").save(grit_src)
                except ValueError as e:
                    self._emit("diagnostic", build_error(str(e), "grit"))
                    return False
                self._emit("log_line",
                           f"[palette] {sprite.name} -> {len(bank_colors)} colours (indexed)")

            # grit écrit LUI-MÊME ses fichiers, donc il en date la sortie à
            # chaque passage — et il y estampille l'heure d'export, ce qui la
            # rend différente même à donnée identique (cf. build_output).
            # On le fait donc écrire à côté, puis on republie par
            # `build_output.write` : le fichier définitif ne bouge que si son
            # contenu bouge, et `make` le saute sinon (ROADMAP v0.24).
            scratch = p.grit_out_dir / "_grit"
            scratch.mkdir(parents=True, exist_ok=True)
            out_base = str(scratch / sym)
            self._emit("log_line",
                       f"[grit Actor] {sprite.name} <- {ap.name} "
                       f"({sprite.frame_w}x{sprite.frame_h}px)")
            cmd = [
                str(self._grit), relative_arg(grit_src, p.grit_out_dir),
                "-gt", "-gB4",
                f"-Mw{sprite.tile_w}", f"-Mh{sprite.tile_h}",
                "-m!", "-p", "-pn16", "-ftc",
                "-o", relative_arg(Path(out_base), p.grit_out_dir),
            ]
            if not self._run_cmd(cmd, f"[grit:{sprite.name}]", cwd=p.grit_out_dir):
                return False

            if bank_colors:
                if not remap_tiles_to_bank(Path(out_base + ".c"), bank_colors, self._emit):
                    return False
            for ext in (".c", ".h"):
                src_f = Path(out_base + ext)
                if src_f.exists():
                    build_output.write(p.grit_out_dir / f"{sym}{ext}",
                                       src_f.read_text(encoding="utf-8", errors="replace"))
            if self._cache and all(path.is_file() for path in outputs):
                self._cache.store(f"sprite:{sprite.name}", fingerprint)
        if cache_hits:
            self._emit("log_line",
                       f"[cache] sprites : {cache_hits} hit(s), "
                       f"{len(done) - cache_hits} reconverti(s)")
        return True


# ── MmutilAudio ────────────────────────────────────────────────────────────────

def referenced_sound_names(p: Project) -> tuple[set[str], set[str]]:
    """(noms de sfx, noms de musiques) que le projet peut réellement jouer.

    Cette liste est EXHAUSTIVE, et ça tient à une propriété du langage plutôt
    qu'à la qualité du parcours : le sous-ensemble Lua n'a pas de chaîne
    manipulable (docs/scripting-reference.md, « Le langage »). Une chaîne y est toujours
    un nom cité du projet, résolu au build — il n'existe donc aucun moyen de
    ranger un nom de piste dans une variable. Le problème des « cibles
    dynamiques » laissé ouvert pour le graphe des scènes (ROADMAP v0.12) ne se
    pose pas ici, et aucun drapeau « garde-le quand même » n'est nécessaire.

    Cinq sources, parce qu'un son se cite de cinq façons :
      ① un littéral d'appel — `sfx:play("GOAL")`, `music:play("Dreamy DX")` ;
      ② un `SoundFxComponent` posé sur un acteur ou un prefab, que
         `self:play_sfx()` joue sans jamais nommer le son dans le script ;
      ③ le MAPPING d'un état d'une boîte sonore (ROADMAP v0.8.7) ;
      ④ la musique nommée par une scène ;
      ⑤ `AnimFrame.direct_sfx_name` (ROADMAP v0.8.9) — un Sfx joué DIRECTEMENT
         en arrivant sur une frame.

    `AnimFrame.action_name`, lui, n'est PAS une source : depuis la v0.8.7 il
    nomme un EMPLACEMENT (« pas »), pas un effet. Ce sont les mappings des
    états qui disent vers quel échantillon cet emplacement se résout — d'où
    ③. `direct_sfx_name` est la différence : un nom de Sfx DIRECT, comme ②,
    donc une source au même titre.
    """
    from scripting.api import DOMAIN_SFX, DOMAIN_MUSIC
    from scripting.refactor import index_refs_in_project
    from core.models.components import component_type_name

    sfx_names   = set(index_refs_in_project(p, DOMAIN_SFX))
    music_names = set(index_refs_in_project(p, DOMAIN_MUSIC))

    # ② Le composant ne passe pas par un littéral de script : `self:play_sfx()`
    # ne nomme rien, c'est le codegen qui va chercher le nom dans le composant.
    entities = list(p.prefabs)
    for scene in p.scenes:
        entities.extend(getattr(scene, "actors", []) or [])
    for ent in entities:
        for comp in getattr(ent, "components", []) or []:
            try:
                if component_type_name(comp) == "sound_fx" and comp.sfx_name:
                    sfx_names.add(comp.sfx_name)
            except ValueError:
                continue

    # ③ Ce que les trois boîtes citent. Un emplacement posé sur une frame ne
    # nomme aucun asset ; c'est l'état qui dit vers quoi il pointe. Un effet
    # cité seulement là doit tout de même entrer en ROM, sinon sa constante
    # `SFX_*` n'existe pas et le C échoue sur un message obscur.
    for box in getattr(p, "sound_boxes", []):
        sfx_names |= box.referenced_assets()
    for box in getattr(p, "jingle_boxes", []):
        music_names |= box.referenced_assets()
    for box in getattr(p, "music_boxes", []):
        music_names |= box.referenced_music()

    # ④ `Scene.music` — une scène nomme sa piste sans qu'aucun script ne la
    # cite. Remplace le `mmStart(music[0])` du boot, qui référençait la
    # première musique du projet faute de mieux (ROADMAP v0.8.2).
    from core.models.scene import MUSIC_INHERIT, MUSIC_NONE
    for scene in p.scenes:
        want = getattr(scene, "music", MUSIC_INHERIT) or MUSIC_INHERIT
        if want not in (MUSIC_INHERIT, MUSIC_NONE):
            music_names.add(want)

    # ⑤ `AnimFrame.direct_sfx_name` — direct, comme ②, sinon un Sfx cité
    # seulement par une frame serait laissé hors ROM et sa constante `SFX_*`
    # n'existerait pas au moment où le stepper d'anim tente de l'émettre.
    for spr in getattr(p, "sprites", []):
        for stt in getattr(spr, "states", []) or []:
            for sd in getattr(stt, "directions", []) or []:
                for fr in getattr(sd, "frames", []) or []:
                    name = getattr(fr, "direct_sfx_name", "") or ""
                    if name:
                        sfx_names.add(name)

    return sfx_names, music_names


def resolve_sound_assets(p: Project) -> dict:
    """Retourne {'sfx': [(Sfx, Path)], 'music': [(Music, Path)], 'skipped': [...]}.

    Ne retient que ce que le projet peut jouer. Tout embarquer paraissait
    inoffensif ; mesuré sur la démo, c'était 101 modules jamais joués sur 105,
    soit 5 408 Kio de ROM — la ROM de Pong était à 91,6 % de son, presque
    entièrement mort.

    Un asset écarté n'est pas supprimé : son fichier reste dans assets/ et sa
    ressource dans le projet. Il est seulement absent de la ROM, et le build le
    NOMME (`skipped`) — sans quoi ce serait la dégradation silencieuse refusée
    partout ailleurs.
    """
    ref_sfx, ref_music = referenced_sound_names(p)
    sfx_list, music_list, skipped = [], [], []
    for kind, store, keep, out in (("sfx", p.sfx, ref_sfx, sfx_list),
                                   ("music", p.music, ref_music, music_list)):
        for item in store:
            ap = p.asset_abs(item.asset) if item.asset else None
            if not (ap and ap.exists()):
                continue
            if item.name in keep:
                out.append((item, ap))
            else:
                skipped.append((kind, item.name, ap.stat().st_size))
    return {"sfx": sfx_list, "music": music_list, "skipped": skipped}


def silent_sound_symbols(p: Project) -> list[str]:
    """Les constantes C des sons dont le FICHIER manque : `resolve_sound_assets` ne les
    embarque pas, donc `soundbank.h` ne les définit pas.

    Un son sans fichier — l'utilisateur l'a sans doute retiré lui-même — ne doit pas faire
    échouer la compilation de ce qui le cite (script, composant, boîte, scène) : le jeu se
    joue sans lui. Chaque constante vaut alors -1, « aucun son », que les fonctions de lecture
    ignorent (cf. `headers.generate_runtime_api`). Le validateur, lui, le dit par un avertissement.
    """
    from scripting.api import sfx_constant, music_constant

    def missing(item) -> bool:
        path = p.asset_abs(item.asset) if item.asset else None
        return not (path and path.exists())

    symbols: list[str] = []
    for sfx in getattr(p, "sfx", []):
        if missing(sfx):
            symbols.append(sfx_constant(sfx.name))
    for music in getattr(p, "music", []):
        if missing(music):
            symbols += [music_constant(music.name), f"MOD_{c_sym(music.name).upper()}"]
    return symbols


class MmutilAudio:
    """Lance mmutil + bin2s pour produire soundbank.h/.bin/.s."""

    def __init__(self, mmutil_path, bin2s_path, emit: Callable, run_cmd: Callable,
                 asset_cache: AssetBuildCache | None = None):
        self._mmutil  = mmutil_path
        self._bin2s   = bin2s_path
        self._emit    = emit
        self._run_cmd = run_cmd
        self._cache   = asset_cache

    def _check_ids(self, soundbank_h: Path, sound_assets: dict) -> bool:
        """Vérifie que mmutil a numéroté dans l'ordre où on lui a passé les
        fichiers — l'hypothèse dont dépendent les `#define SFX_*` / `MUSIC_*`
        émis par le transpileur Lua.

        Elle n'était écrite nulle part, et elle a lâché en silence : tant que
        le build émettait TOUT le catalogue, le rang dans le projet et l'id du
        soundbank coïncidaient. Le jour où le build a filtré, `music.play` s'est
        mis à jouer un autre module — sans symbole manquant, donc sans erreur de
        compilation, donc invisible jusqu'à ce qu'on écoute. Une hypothèse qui
        se trompe en silence doit devenir un contrôle qui bloque.
        """
        import re
        try:
            text = soundbank_h.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            self._emit("diagnostic", build_error(f"soundbank.h unreadable: {e}", "mmutil"))
            return False
        found = {m.group(1): int(m.group(2))
                 for m in re.finditer(r"#define\s+(\w+)\s+(\d+)", text)}
        bad = []
        for prefix, key in (("SFX_", "sfx"), ("MOD_", "music")):
            for expected, (item, _ap) in enumerate(sound_assets.get(key, [])):
                sym = f"{prefix}{c_sym(item.name).upper()}"
                got = found.get(sym)
                if got is None:
                    bad.append(f"{sym} absent de soundbank.h")
                elif got != expected:
                    bad.append(f"{sym} is {got}, expected {expected}")
        for msg in bad:
            self._emit("diagnostic", build_error(f"unexpected numbering: {msg}", "mmutil"))
        if bad:
            self._emit("diagnostic", build_error(
                "the SFX_*/MUSIC_* constants of the generated code "
                "would be wrong — build interrupted rather than a ROM with "
                "shifted sound.", "mmutil"))
        return not bad

    def run(self, p: Project, sound_assets: dict) -> bool:
        if not self._mmutil:
            self._emit("diagnostic", build_warning("not found — audio skipped", "mmutil")); return True

        # Ré-échantillonnage éventuel des effets, vers le dossier de build.
        # L'ORDRE de `all_files` est intouchable : c'est lui qui fixe les
        # identifiants SFX_*/MUSIC_*. On substitue des chemins, jamais des rangs.
        from codegen.sfx_encode import encode_sfx_for_build
        try:
            encoded = encode_sfx_for_build(p, sound_assets["sfx"], self._emit)
        except Exception as e:
            self._emit("diagnostic", build_warning(f"resampling ignored: {e}", "sfx"))
            encoded = {}

        all_files = (
            [relative_arg(encoded.get(s.name, ap), p.build_dir) for s, ap in sound_assets["sfx"]] +
            [relative_arg(ap, p.build_dir) for _, ap in sound_assets["music"]]
        )
        if not all_files:
            return True

        soundbank_bin = p.build_dir / "soundbank.bin"
        soundbank_h   = p.build_dir / "soundbank.h"
        outputs = [soundbank_bin, soundbank_h, p.src_dir / "soundbank.h",
                   p.src_dir / "soundbank.s", p.src_dir / "soundbank.bin.h"]
        fingerprint = (self._cache.fingerprint({
            "sfx": [(item.to_dict(), file_digest(path))
                    for item, path in sound_assets["sfx"]],
            "music": [(item.to_dict(), file_digest(path))
                      for item, path in sound_assets["music"]],
            "project_sample_rate": int(getattr(p.settings, "sfx_sample_rate", 0) or 0),
            "mmutil": tool_signature(self._mmutil),
            "bin2s": tool_signature(self._bin2s),
        }) if self._cache else "")
        if self._cache and self._cache.hit("audio", fingerprint, outputs):
            self._emit("log_line", "[cache] audio — unchanged")
            return self._check_ids(soundbank_h, sound_assets)
        cmd = [str(self._mmutil)] + all_files + ["-osoundbank.bin", "-hsoundbank.h"]
        self._emit("log_line",
                   f"[mmutil] {len(sound_assets['sfx'])} sfx + "
                   f"{len(sound_assets['music'])} music")
        # Ce qui n'entre pas dans la ROM doit se lire dans le journal : un asset
        # qui disparaît sans un mot, c'est le défaut qu'on vient de corriger.
        #
        # On annonce un NOMBRE, pas un gain en octets. La taille des fichiers
        # source ne prédit pas le coût ROM : mmutil partage les échantillons
        # entre les modules d'un même soundbank, et un catalogue de variantes
        # d'un même morceau (DRUMLESS/FAST/SLOW) n'en porte donc qu'un jeu.
        # Mesuré sur la démo : 5 351 Kio de .mod écartés n'ont retiré que
        # 437 Kio de soundbank. Annoncer la taille source ferait croire à un
        # gain douze fois trop grand.
        if skipped := sound_assets.get("skipped"):
            self._emit("log_line",
                       f"[mmutil] {len(skipped)} unreferenced sound(s) — left out of the ROM, "
                       "files kept in assets/")
            for kind, name, _size in sorted(skipped, key=lambda s: -s[2])[:10]:
                self._emit("log_line", f"           · {kind} \"{name}\"")
            if len(skipped) > 10:
                self._emit("log_line", f"           · … and {len(skipped) - 10} more")
        ok = self._run_cmd(cmd, "[mmutil]", cwd=p.build_dir)
        if ok and soundbank_h.exists():
            ok = self._check_ids(soundbank_h, sound_assets) and ok
        if ok and soundbank_h.exists():
            # mmutil écrit soundbank.h dans build/ — le Makefile ne compile
            # que depuis build/src/ (-Isrc), donc le header doit y être copié
            # pour que le #include "soundbank.h" de main.c le trouve.
            build_output.copy(soundbank_h, p.src_dir / "soundbank.h")
            self._emit("log_line", "[mmutil] -> src/soundbank.h")
        if ok:
            bin2s = self._bin2s
            if bin2s and soundbank_bin.exists():
                # bin2s écrit l'assembleur sur stdout (pas de flag -o) : on doit
                # capturer nous-mêmes la sortie pour la sauver dans src/soundbank.s.
                # _run_cmd() générique se contente de logger stdout/stderr et
                # renvoie un bool, ce qui perdait ce contenu (symbole
                # "soundbank_bin" jamais linké → undefined reference au link).
                self._emit("log_line", f"[bin2s] {bin2s} soundbank.bin")
                try:
                    proc = run_tool([str(bin2s), "soundbank.bin"], cwd=str(p.build_dir))
                except FileNotFoundError as e:
                    self._emit("diagnostic", build_warning(f"not found: {e}", "bin2s"))
                    proc = None
                if proc is not None:
                    for line in proc.stderr.splitlines():
                        self._emit("error_line" if proc.returncode != 0 else "log_line", f"  {line}")
                if proc is not None and proc.returncode == 0:
                    s_dst = p.src_dir / "soundbank.s"
                    build_output.write(s_dst, proc.stdout)
                    self._emit("log_line", "[bin2s] -> src/soundbank.s")
                    # bin2s ne génère pas de header : déclarer nous-mêmes le
                    # symbole "soundbank_bin" (dérivé de "soundbank.bin" par
                    # bin2s) que main.c référence via mmInitDefault().
                    h_dst = p.src_dir / "soundbank.bin.h"
                    build_output.write(
                        h_dst,
                        f"/* Generated by {APP_NAME} — declares the symbol produced by bin2s */\n"
                        "#ifndef SOUNDBANK_BIN_H\n"
                        "#define SOUNDBANK_BIN_H\n"
                        "extern const unsigned char soundbank_bin[];\n"
                        "#endif\n",
                    )
                    self._emit("log_line", "[bin2s] -> src/soundbank.bin.h")
                    if self._cache and all(path.is_file() for path in outputs):
                        self._cache.store("audio", fingerprint)
            else:
                self._emit("diagnostic", build_warning("not found — soundbank not linked", "bin2s"))
        return ok
