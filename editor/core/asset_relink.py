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


def compatible_files(project, family: str) -> list[Path]:
    """Les fichiers de `assets/` qu'une asset de cette famille peut prendre pour source : ceux dont le format est le
    sien, quel que soit le dossier. Triés par chemin."""
    wanted = {ext.lower() for ext in FAMILY_EXTENSIONS[family]}
    return sorted((p for p in project.assets_dir.rglob("*") if p.is_file() and p.suffix.lower() in wanted),
                  key=lambda p: p.as_posix().lower())


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
        # L'import NATIF de la nouvelle image : recadrage, taille et réglages de compression de l'ancienne ne valent
        # plus pour elle, le mode (tuilé / bitmap, 4 / 8 bpp) se détecte de nouveau, et la taille du fond suit
        # l'image. La peinture et les repeints de palette, eux, sont gardés : s'ils ne tombent plus où il faut,
        # le canvas le montre tout de suite.
        from core.bg_import import detect_import_mode, encode_by_mode
        from core.models.background import BackgroundCompression, KIND_SCENE
        item.import_crop = item.import_size = item.mirror_x = item.mirror_y = None
        item.mirror_flip_x = item.mirror_flip_y = False
        item.compression = BackgroundCompression()
        token = detect_import_mode(path)["token"]
        if item.kind != KIND_SCENE and token.startswith("bitmap"):
            token = "tiled8"                    # un cadre ou une planche sont des tuiles (cf. l'import)
        reconcile.apply_bg_encoding(item, encode_by_mode(path, token, item.quantize_method, item.dither, None, item.compression))
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


class RelinkSourceCmd:
    """« Relink source… » comme entrée d'historique (`core.history.Command`) : Ctrl+Z rend l'asset TEL QU'IL ÉTAIT — le
    champ relié et tout ce que l'éditeur en déduit (palettes, tuiles) —, Ctrl+Y le rend tel que le relien l'a fait,
    sans relire le fichier. Le premier `execute` relie pour de bon et laisse monter la `ValueError` d'un fichier
    refusé : `History.push` n'enregistre alors rien."""

    def __init__(self, project, family: str, item, new_path, after=None):
        self._project, self._family, self._item, self._new_path = project, family, item, new_path
        self._after = after            # rafraîchit ce qui montre l'asset, dans les deux sens
        self._before = self._snapshot()
        self._done = None
        self.label = f"Relink {getattr(item, 'name', '')}"

    def _snapshot(self) -> dict:
        import copy
        return copy.deepcopy(vars(self._item))

    def _restore(self, state: dict) -> None:
        import copy
        vars(self._item).clear()
        vars(self._item).update(copy.deepcopy(state))
        store = next(s for f, s, _ in self._project.source_families() if f == self._family)
        store.save(self._item)

    def execute(self):
        if self._done is None:
            relink_source(self._project, self._family, self._item, self._new_path)
            self._done = self._snapshot()
        else:
            self._restore(self._done)
        if self._after:
            self._after()

    def undo(self):
        self._restore(self._before)
        if self._after:
            self._after()

    def merge(self, newer) -> bool:
        return False
