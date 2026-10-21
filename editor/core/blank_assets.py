"""
core/blank_assets.py — les assets VIERGES qu'on peut créer sans source.

Un asset vierge n'a pas de fichier source : une scène, un prefab, une mise en page d'interface, une boîte sonore, une
table de données, une palette ou un fond tuilé. (Un sprite, un son ou une police n'existent pas sans fichier : ils se
créent depuis une source, cf. `core.asset_creation`.) Chaque fabrique construit l'asset, nommé d'office et unique dans
son type, SANS le ranger : l'historique le range (`core.history.CreateAssetCmd`).

Les scripts et les behaviors sont des fichiers `.lua`, pas des assets d'un catalogue : `script_source` en donne le
contenu et `core.disk_commands.CreateFileCmd` les écrit.
"""
from __future__ import annotations

from core.models.unique_name import unique_name

# (clé, famille du catalogue, nom de base) — dans l'ordre où le menu les propose.
BLANK_KINDS = (
    ("scene",       "scenes",       "Scene"),
    ("prefab",      "prefabs",      "Prefab"),
    ("ui_layout",   "ui_layouts",   "Layout"),
    ("music_box",   "music_boxes",  "MusicBox"),
    ("jingle_box",  "jingle_boxes", "JingleBox"),
    ("sound_box",   "sound_boxes",  "SoundBox"),
    ("data_table",  "data_tables",  "Table"),
    ("palette",     "palettes",     "Palette"),
    ("font_asset",  "font_assets",  "Font"),
)
SCRIPT_KINDS = ("script", "behavior")


def _build(project, kind: str, name: str, **options):
    if kind == "scene":
        from core.models.scene import Scene
        scene = Scene(name=name)
        project.seed_default_ui_palette(scene)
        project.seed_default_camera(scene)
        return scene
    if kind == "prefab":
        from core.models.scene import Prefab
        return Prefab(name=name)
    if kind == "ui_layout":
        from core.models.ui_region import UILayout
        return UILayout(name=name)
    if kind in ("music_box", "jingle_box", "sound_box"):
        from core.models import sound_box
        return {"music_box": sound_box.MusicBox, "jingle_box": sound_box.JingleBox,
                "sound_box": sound_box.SoundBox}[kind](name=name)
    if kind == "data_table":
        from core.models.data_table import DataTable, DataColumn
        # Une colonne d'office : une grille sans colonne n'a nulle part où poser une ligne.
        return DataTable(name=name, columns=[DataColumn(name="valeur", type="int")], rows=[])
    if kind == "palette":
        from core.models.palette import PaletteBank
        from core.palette_presets import hsb_ramp_bgr555
        size = options.get("size", 16)         # 16 (4bpp) ou 256 (8bpp)
        return PaletteBank(name=name, colors=hsb_ramp_bgr555(0, 0, steps=size), size=size)
    if kind == "font_asset":
        from core.models.font_asset import FontAsset
        asset = FontAsset(name=name)
        if project.fonts:                       # préliée à la première source disponible
            asset.sources = {"regular": [project.fonts[0].name]}
        return asset
    if kind == "background":
        from core.models.background import BackgroundAsset
        # Un écran GBA complet, vide mais immédiatement peignable. La tuile 0
        # reste transparente ; le pinceau de tiles crée/réutilise sa tuile
        # pleine dans le sidecar sans jamais demander de PNG source.
        width, height = options.get("size", (240, 160))
        width, height = max(8, int(width) // 8 * 8), max(8, int(height) // 8 * 8)
        colors = list(options.get("colors", [0x0000, 0x7FFF]))[:16]
        colors += [0] * (16 - len(colors))
        colors[0] = 0x0000
        return BackgroundAsset(
            name=name,
            palettes=[colors],
            tileset=["0" * 64],
            tilemap=[0] * ((width // 8) * (height // 8)),
            tiles_w=width // 8,
            tiles_h=height // 8,
        )
    raise ValueError(f"unknown blank asset kind: {kind}")


def build_blank(project, kind: str, name: str | None = None, **options):
    """`(catalogue, asset)` : l'asset vierge de ce type, nommé et unique, ni rangé ni écrit. `name` : le nom voulu
    (suffixé s'il est pris), sinon le nom de base du type."""
    family, base = next((f, b) for k, f, b in BLANK_KINDS if k == kind)
    store = getattr(project, family)
    name = unique_name(name or base, {item.name for item in store})
    return store, _build(project, kind, name, **options)


def script_source(kind: str, name: str) -> str:
    """Le contenu d'un script neuf (`kind` : "script", "behavior" — qui porte le marqueur — ou "actor", le point
    d'entrée d'un script d'acteur)."""
    from scripting.script_templates import ScriptTemplateContext, generate_script_template
    return generate_script_template(ScriptTemplateContext(kind=kind if kind in ("behavior", "actor") else "empty", name=name))
