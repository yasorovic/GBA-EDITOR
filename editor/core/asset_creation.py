"""
core/asset_creation.py — créer un asset : depuis une source, ou vierge.

Un asset POINTE sa source par un chemin explicite : le créer est un geste
de l'auteur, jamais la conséquence de l'apparition d'un fichier. Deux chemins :

- **depuis une source** (`create_from_source`) : le fichier choisi devient la source d'un asset, créé à côté
  d'elle. Un format peut convenir à plusieurs types (`SOURCE_FAMILIES`) : l'appelant choisit, `candidate_families`
  donne la liste, le premier est le plus courant.
- **vierge** (`create_blank`) : un asset sans source (scène, prefab, boîte…), dans un dossier donné.

Chaque geste rend UNE commande annulable (`Gesture.command`) que l'appelant pousse dans l'historique ; le module
construit l'asset, `core.history.CreateAssetCmd` le range dans son catalogue et l'écrit.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.models.unique_name import unique_name

# Quels types d'asset un format de source peut devenir, le plus courant d'abord.
SOURCE_FAMILIES: dict[str, tuple[str, ...]] = {
    ".png": ("sprites", "backgrounds", "fonts"),
    ".wav": ("sfx", "music", "jingles"),
    ".mod": ("music", "jingles"),
    ".xm":  ("music", "jingles"),
    ".s3m": ("music", "jingles"),
    ".it":  ("music", "jingles"),
    ".ttf": ("fonts",),
    ".otf": ("fonts",),
    ".fnt": ("fonts",),
    ".hex": ("palettes",),
}

# Le mot que l'auteur lit pour chaque type dans les menus.
FAMILY_WORDS = {"sprites": "Sprite", "backgrounds": "Background", "sfx": "Sound effect", "music": "Music",
                "jingles": "Jingle", "fonts": "Font", "palettes": "Palette"}


@dataclass
class Creation:
    """Ce que `create_from_source` a produit : l'asset et son catalogue, ou `error` si le fichier ne convient
    pas (rien n'est alors créé). `warning` : un constat d'import qui n'empêche pas la création."""
    family: str = ""
    store: object = None
    item: object = None
    folder: Optional[Path] = None
    warning: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Gesture:
    """Ce qu'un geste de création a préparé : `command` (à pousser dans l'historique, None si rien n'est créé), les
    noms et les assets créés, les constats d'import (`warnings`) et les fichiers refusés (`errors`)."""
    command: object = None
    names: list = field(default_factory=list)
    items: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def candidate_families(path) -> tuple[str, ...]:
    """Les types d'asset que ce fichier peut devenir (vide : format non pris en charge)."""
    return SOURCE_FAMILIES.get(Path(path).suffix.lower(), ())


def _store(project, family: str):
    return getattr(project, family)


def palette_is_taken(project, path) -> bool:
    """Une palette dont ce `.hex` porte déjà les couleurs ? Elles vivent dans le `.hex`, jamais dans la palette : une
    seconde palette sur le même fichier partagerait — et réécrirait — les mêmes couleurs."""
    key = Path(path).resolve()
    return any(Path(project.palettes.hex_path(bank)).resolve() == key for bank in project.palettes)


def families_for(project, path) -> tuple[str, ...]:
    """Les types que ce fichier peut devenir MAINTENANT. Une source peut donner plusieurs assets (un sprite et un fond tirés
    du même PNG, deux sprites découpés autrement) — sauf une palette, dont le `.hex` est la donnée."""
    families = candidate_families(path)
    if "palettes" in families and palette_is_taken(project, path):
        return tuple(f for f in families if f != "palettes")
    return families


def can_create_from(project, path) -> bool:
    return Path(path).is_file() and bool(families_for(project, path))


def asset_name(project, family: str, path) -> str:
    """Le nom que l'asset prendra : celui du fichier, rendu unique dans son type (`coin`, `coin_2`…)."""
    return unique_name(Path(path).stem, {item.name for item in _store(project, family)})


# ── Constructeurs, un par type : l'asset neuf qui POINTE `path`, rien n'est rangé ni écrit ──

def _new_sprite(project, name: str, path: Path):
    from core.resources.asset_reconciliation import encode_sprite_asset
    from core.models.sprite import SpriteAsset
    sprite = SpriteAsset(name=name, asset=project.asset_rel(path), frame_w=8, frame_h=8)
    warning = None
    try:
        warning = encode_sprite_asset(sprite, path)
    except Exception:
        pass                      # l'encodage se refera à l'ouverture (reconcile_sprite)
    return sprite, warning, None


def _new_background(project, name: str, path: Path, encode: bool = True):
    from core.resources.asset_reconciliation import encode_background_asset, catalogue_lookup
    from core.models.background import BackgroundAsset
    ba = BackgroundAsset(name=name, asset=project.asset_rel(path))
    if not encode:
        return ba, None, None       # l'appelant détecte le mode et compresse (hors-thread), cf. l'écran Background
    warning = None
    try:
        from core.bg_import import detect_import_mode
        d = detect_import_mode(path)
        ba.choose_layout(d["token"])        # l'import décide du layout À LA PLACE de l'auteur, comme réglage
        warning = d["warning"]
    except Exception:
        pass
    encode_background_asset(ba, path, lookup=catalogue_lookup(project))
    return ba, warning, None


def _new_sound(family: str):
    def build(project, name: str, path: Path):
        from core.resources.asset_reconciliation import check_audio_file
        from core.models import audio
        reason = check_audio_file(path, into=family)
        if reason:
            return None, None, f"{path.name}: {reason}"
        cls = {"sfx": audio.Sfx, "music": audio.Music, "jingles": audio.Jingle}[family]
        return cls(name=name, asset=project.asset_rel(path)), None, None
    return build


def _new_font(project, name: str, path: Path):
    from core.models.font import Font
    from core import font_import
    font = Font(name=name)
    suffix = path.suffix.lower()
    try:
        if suffix == ".fnt":
            fields = font_import.import_font_fnt(path)
            page = fields.pop("page_path", None)
            if page is None:
                return None, None, (f"{path.name}: the descriptor does not reference any PNG sheet that can be "
                                    "found — put the sheet next to the .fnt.")
            font.asset = project.asset_rel(page)
            font.descriptor = project.asset_rel(path)
        elif suffix == ".png":
            font.bg_color = font_import.detect_bg_color(path)
            fields = font_import.import_font_png(path, keys=font.key_colors(), space_color=font.space_color)
            font.asset = project.asset_rel(path)
        else:
            from core.font_metadata import vector_font_metadata
            font.asset = project.asset_rel(path)
            fields = {"source_format": suffix.lstrip("."), **vector_font_metadata(path)}
        font_import.apply_font_import(font, fields)
    except Exception as exc:
        return None, None, f"{path.name}: import failed ({exc})."
    warning = None
    if not font.glyphs and font.source_format in ("png", "fnt"):
        warning = f"Font \"{name}\": no glyph detected — check the cell size in the Font screen."
    return font, warning, None


def _new_palette(project, name: str, path: Path):
    from core.models.palette import PaletteBank
    try:
        bank = PaletteBank.from_hex(name, path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, None, f"{path.name}: {exc}"
    bank.asset = project.asset_rel(path)
    return bank, None, None


_BUILDERS = {"sprites": _new_sprite, "backgrounds": _new_background, "sfx": _new_sound("sfx"),
             "music": _new_sound("music"), "jingles": _new_sound("jingles"), "fonts": _new_font,
             "palettes": _new_palette}


def build_from_source(project, family: str, path, name: str | None = None, defer_encoding: bool = False) -> Creation:
    """L'asset de type `family` qui POINTERAIT `path`, construit mais NI rangé NI écrit : l'historique le range
    (`core.history.CreateAssetCmd`), pour que le geste s'annule. Un fichier qui ne convient pas (format,
    contenu illisible, source déjà citée) ne produit rien : `error` le dit. `defer_encoding` (fonds seulement) : le fond
    naît sans layout ni encodage, l'appelant les calcule — l'écran Background compresse hors du thread de l'interface."""
    path = Path(path)
    project.load_all_resources()
    if family not in families_for(project, path):
        reason = ("its colours already belong to a palette" if family == "palettes" and palette_is_taken(project, path)
                  else f"it cannot become a {FAMILY_WORDS.get(family, family).lower()}")
        return Creation(error=f"{path.name}: {reason}.")
    name = name or asset_name(project, family, path)
    if defer_encoding and family == "backgrounds":
        item, warning, error = _new_background(project, name, path, encode=False)
    else:
        item, warning, error = _BUILDERS[family](project, name, path)
    if error:
        return Creation(error=error)
    return Creation(family, _store(project, family), item, path.parent, warning)


def import_folder(project, shown: str | None) -> Path:
    """Où va un fichier importé : le dossier que l'onglet Disk affiche s'il est sous `assets/`, sinon `assets/`
    elle-même. Aucun dossier de famille n'est imposé — l'auteur range où il veut."""
    if shown:
        folder = Path(shown)
        try:
            folder.resolve().relative_to(project.user_library_dir.resolve())
            return folder
        except ValueError:
            pass
    return project.user_library_dir


def create_from_source(project, family: str, paths, folder: Path | None = None, defer_encoding: bool = False) -> Gesture:
    """*Create from source* : un asset de type `family` par source, UNE commande pour le lot. L'asset naît à côté de sa
    source (ou dans `folder`). Les noms sont uniques entre eux aussi (deux `coin.wav` de deux dossiers donnent `coin`
    et `coin_2`) ; une source qui ne convient pas est signalée dans `errors`, les autres sont créées. `defer_encoding` :
    cf. `build_from_source`."""
    from core.history import CreateAssetCmd, MacroCmd
    project.load_all_resources()
    taken = {item.name for item in _store(project, family)}
    gesture, commands = Gesture(), []
    for path in map(Path, paths):
        name = unique_name(path.stem, taken)
        creation = build_from_source(project, family, path, name, defer_encoding)
        if creation.error is not None:
            gesture.errors.append(creation.error)
            continue
        taken.add(name)
        commands.append(CreateAssetCmd(creation.store, creation.item, folder or creation.folder))
        gesture.names.append(name)
        gesture.items.append(creation.item)
        if creation.warning:
            gesture.warnings.append(creation.warning)
    if commands:
        gesture.command = commands[0] if len(commands) == 1 else MacroCmd(commands, f"Créer {len(commands)} assets")
    return gesture


def create_blank(project, kind: str, folder, around=nullcontext, **options) -> Gesture:
    """*Create blank* : un asset sans source — ou un script, un behavior —, nommé d'office et unique, dans `folder`.
    `around` entoure l'écriture d'un script (la fenêtre y suspend le surveillant) ; `options` : cf. `blank_assets.build_blank`
    (`name` : le nom voulu, suffixé s'il est pris). Pour un script, `template` choisit un autre modèle que `kind` (« actor »)."""
    from core import blank_assets
    from core.history import CreateAssetCmd
    folder = Path(folder)
    if kind in blank_assets.SCRIPT_KINDS:
        from core.disk_commands import CreateFileCmd
        from core.lua_scripts import lua_files
        name = unique_name(options.get("name") or ("Behavior" if kind == "behavior" else "Script"),
                           {p.stem for p in lua_files(project)})   # un behavior se retrouve par son nom
        content = blank_assets.script_source(options.get("template") or kind, name).encode("utf-8")
        return Gesture(CreateFileCmd(folder / f"{name}.lua", content, around=around), [name])
    store, item = blank_assets.build_blank(project, kind, **options)
    return Gesture(CreateAssetCmd(store, item, folder), [item.name], [item])


def create_interface(project, scene, folder, persist=None) -> Gesture:
    """Un nœud `Interface` : une mise en page vierge, nommée d'après la scène, et le nœud qui la pose dans `scene` —
    UNE commande. `persist` : ce qui écrit la scène et remet les vues d'accord, après chaque sens."""
    from core import blank_assets
    from core.history import AddListItemCmd, CreateAssetCmd, MacroCmd
    from core.models.ui_region import InterfaceNode
    store, layout = blank_assets.build_blank(project, "ui_layout", name=scene.name or "ui")
    node = AddListItemCmd(scene.ui_layouts, InterfaceNode(layout_name=layout.name), persist_fn=persist,
                          label=f"Add interface {layout.name}")
    return Gesture(MacroCmd([CreateAssetCmd(store, layout, folder), node], f"Créer {layout.name}"),
                   [layout.name], [layout])
