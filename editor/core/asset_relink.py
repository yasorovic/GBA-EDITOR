"""
core/asset_relink.py — l'asset dont la source manque, et le geste qui le répare.

Un asset garde un chemin vers son fichier source (`asset`, et `descriptor` pour une police
importée d'un `.fnt`). Si le fichier disparaît — déplacé, renommé, supprimé hors de l'éditeur —
l'asset reste dans le projet, SANS source : le build s'arrête sur une erreur claire
(`core.validator`) plutôt que de livrer un jeu amputé. L'auteur le relie alors à un autre
fichier (`relink_source`) ou le supprime. Rien n'est jamais recréé : l'asset garde son nom,
son id et tout ce que l'auteur y a réglé.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.models.audio import MUSIC_FILE_EXTS, SFX_FILE_EXTS
from core.models.font import FONT_FILE_EXTS
from core.models.sprite import IMAGE_FILE_EXTS

# Les formats qu'une famille accepte comme source — les listes de chaque famille, réunies ici.
FAMILY_EXTENSIONS = {
    "sprites":     IMAGE_FILE_EXTS,
    "backgrounds": IMAGE_FILE_EXTS,
    "sfx":         SFX_FILE_EXTS,
    "music":       MUSIC_FILE_EXTS,
    "jingles":     MUSIC_FILE_EXTS,
    "fonts":       FONT_FILE_EXTS,
    "palettes":    {".hex"},
}

FAMILY_LABELS = {"sprites": "Sprite", "backgrounds": "Background", "sfx": "SFX",
                 "music": "Music", "jingles": "Jingle", "fonts": "Font", "palettes": "Palette"}


@dataclass(frozen=True)
class MissingSource:
    family: str
    item: object
    path: Path          # le fichier qui devrait exister


def missing_sources(project) -> list[MissingSource]:
    """Chaque fichier source cité par un asset et absent du disque. Un asset qui ne cite AUCUN
    fichier n'est pas « sans source » ici : c'est un autre cas, que chaque famille signale à sa façon."""
    out: list[MissingSource] = []
    for family, store, source_paths in project.source_families():
        for item in store:
            out += [MissingSource(family, item, path)
                    for path in source_paths(project, item) if not path.exists()]
    return out


def _slot(project, family: str, item) -> str:
    """Le champ du fichier à relier : celui qui manque. Une police importée d'un `.fnt` en a deux ;
    les autres familles n'en ont qu'un (`asset`)."""
    if family == "fonts" and getattr(item, "descriptor", None):
        descriptor = project.asset_abs(item.descriptor)
        sheet = project.asset_abs(item.asset) if item.asset else None
        if (descriptor is None or not descriptor.exists()) and (sheet is None or sheet.exists()):
            return "descriptor"
    return "asset"


def _stored(project, family: str, path: Path) -> str:
    """Comment l'asset désigne `path` : un chemin relatif au projet, pour toutes les familles."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(project.root.resolve()).as_posix()
    except ValueError:
        raise ValueError("the file must be inside the project folder") from None


def _refresh_derived(project, family: str, item, path: Path) -> None:
    """Ce que l'éditeur déduit de l'image (palettes, tuiles) se refait depuis le NOUVEAU fichier, par
    asset : la réconciliation des fichiers déposés retrouve un asset par le nom du fichier, ce qui ne
    vaut plus ici — le fichier relié peut s'appeler autrement."""
    from core.resources import asset_reconciliation as reconcile
    if family == "sprites":
        from core.sprite_import import encode_sprite
        reconcile.apply_sprite_encoding(item, encode_sprite(path, item.quantize_method))
        item.source_stamp = reconcile.file_stamp(path)
    elif family == "backgrounds":
        reconcile.encode_background_asset(item, path)
        item.source_stamp = reconcile.file_stamp(path)
    elif family == "palettes":
        from core.models.palette import PaletteBank
        fresh = PaletteBank.from_hex(item.name, path.read_text(encoding="utf-8"))   # les couleurs viennent du NOUVEAU fichier
        item.colors, item.size = fresh.colors, fresh.size


def relink_source(project, family: str, item, new_path) -> str:
    """Relie `item` à `new_path` et rend le champ relié (`asset` ou `descriptor`). `ValueError` — avec
    un message lisible, et l'asset INCHANGÉ — si le fichier ne convient pas."""
    new_path = Path(new_path)
    if not new_path.is_file():
        raise ValueError(f"{new_path.name} is not a file")
    suffix = new_path.suffix.lower()
    if suffix not in FAMILY_EXTENSIONS[family]:
        raise ValueError(f"{suffix or 'this file'} is not a source format for this kind of asset")
    slot = _slot(project, family, item)
    if family == "fonts" and (suffix == ".fnt") != (slot == "descriptor"):
        raise ValueError("a font descriptor is a .fnt file; its sheet or outline file is not")
    previous = getattr(item, slot)
    setattr(item, slot, _stored(project, family, new_path))
    try:
        _refresh_derived(project, family, item, new_path)
    except Exception as error:
        setattr(item, slot, previous)
        raise ValueError(f"{new_path.name} could not be read ({error})") from error
    store = next(s for f, s, _ in project.source_families() if f == family)
    store.save(item)
    return slot
