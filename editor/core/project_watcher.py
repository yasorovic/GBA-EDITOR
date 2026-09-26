"""
project_watcher.py — Surveillance des fichiers projet en temps réel.

Principe :
  - assets/  → surveillé par LISTE de sous-dossiers (cf. watch_project), pas
               récursivement : QFileSystemWatcher ne descend pas tout seul, et
               un sous-dossier créé après coup n'est donc pas suivi. Tout
               fichier déposé ou supprimé dans les dossiers listés est notifié
               via asset_appeared / asset_removed, à condition que son
               extension soit dans _ASSET_SUFFIXES. Les .lua émettent
               lua_changed directement. Une disparition et une apparition de
               MÊME empreinte dans le même événement sont un RENOMMAGE, et
               n'émettent ni l'un ni l'autre mais asset_renamed (cf.
               pair_renames) — un asset renommé doit suivre son fichier, pas
               mourir et renaître vierge.
  - les sidecars `.json` d'assets (sprites, backgrounds, fonts, sfx, music)
               vivent DANS assets/, à côté de leur fichier source, et sont
               surveillés eux aussi — sidecar_changed. Ils ne l'étaient pas :
               éditer une police à la main hors de l'éditeur ne se voyait pas.
  - project/ → seuls les JSONs de scènes et prefabs sont surveillés (éditeur
               interne).

Signaux principaux
------------------
asset_appeared(path)  — nouveau fichier brut dans assets/ (PNG, WAV, MOD…)
asset_removed(path)   — fichier supprimé de assets/
asset_renamed(a, b)   — fichier brut renommé dans assets/ : `a` est devenu `b`
asset_modified(path)  — fichier existant modifié dans assets/ (ex. PNG mis à jour)
lua_changed(path)     — .lua modifié ou créé dans assets/scripts/
scene_changed(path)   — .json de scène modifié dans project/scenes/
sidecar_changed(path) — .json d'asset créé ou modifié dans assets/<famille>/

Notes QFileSystemWatcher :
- fileChanged peut supprimer le fichier de la liste après un save atomique
  (delete+create) — on le re-ajoute systématiquement.
- Debounce par fichier (200 ms) pour ne pas spammer sur les sauvegardes en rafales.
"""

from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QFileSystemWatcher


# Extensions considérées comme des assets bruts utilisateur — DÉRIVÉES de ce
# que chaque type d'asset déclare accepter, jamais réépelées ici.
#
# Cette liste était tenue à la main, et elle avait divergé en silence : elle
# portait `.mp3`/`.ogg`, que rien n'importe, et ignorait le `.fnt` que
# `FONT_FILE_EXTS` annonce. Conséquence : déposer un descripteur de police dans
# assets/fonts/ ne déclenchait rien, et le dossier passait pour non surveillé
# alors qu'il l'était. Seul le `.png` traversait, par coïncidence entre les
# deux listes.
#
# C'est exactement la panne que la table de routage de `window.py` a déjà connue
# (cf. son commentaire `_ASSET_ROUTES`) : une seconde liste que rien ne
# confronte à la première. Une union dérivée ne peut plus diverger.
from core.models.audio import SFX_FILE_EXTS, MUSIC_FILE_EXTS
from core.models.font import FONT_FILE_EXTS
from core.models.sprite import IMAGE_FILE_EXTS

_ASSET_SUFFIXES = IMAGE_FILE_EXTS | SFX_FILE_EXTS | MUSIC_FILE_EXTS | FONT_FILE_EXTS

# Les familles dont le sidecar `.json` vit DANS assets/, à côté du fichier
# source — le nom du dossier est aussi celui du `ResourceStore` correspondant
# (`project.fonts`, `project.sprites`…), ce qui évite une table de
# correspondance de plus.
_SIDECAR_DIRS = frozenset({"sprites", "backgrounds", "fonts", "sfx", "music"})
_LUA_SUFFIX     = ".lua"
_JSON_SUFFIX    = ".json"


def pair_renames(before: dict[str, tuple[int, int]],
                 after: dict[str, tuple[int, int]]) -> list[tuple[str, str]]:
    """Les renommages entre deux instantanés de dossier, en [(avant, après)].

    Un renommage arrive comme une disparition ET une apparition dans le MÊME
    événement, et il ne touche ni au contenu ni à la date : deux fichiers dont
    l'un s'en va et l'autre arrive avec la même taille et la même date à la
    nanoseconde sont le même fichier sous un autre nom. Deux fichiers
    DIFFÉRENTS qui partageraient les deux, ça ne se produit pas.

    Seuls les fichiers SOURCES sont appariés : un `.lua` est déjà suivi par son
    chemin, et un sidecar `.json` renommé à la main se rattrape au chargement
    (cf. `ResourceStore.load`) — ni l'un ni l'autre ne mérite un second signal.

    Écrite à part et non dans `_on_dir_changed` : c'est la seule règle du
    module qui se juge sur deux dictionnaires, sans dossier réel ni Qt autour.
    """
    def sources(snap):
        return {p: st for p, st in snap.items()
                if Path(p).suffix.lower() in _ASSET_SUFFIXES}

    gone = {p: st for p, st in sources(before).items() if p not in after}
    born = {p: st for p, st in sources(after).items() if p not in before}

    pairs: list[tuple[str, str]] = []
    for new_path, stamp in born.items():
        old_path = next((p for p, s in gone.items() if s == stamp), None)
        if old_path is None:
            continue
        del gone[old_path]      # un fichier disparu n'est renommé qu'une fois
        pairs.append((old_path, new_path))
    return pairs


def _script_dirs(assets_root: Path) -> list[Path]:
    """`scripts/` et tous ses sous-dossiers, quels qu'ils soient : un script vit à plat, mais
    `behaviors/` et les rangements hérités d'anciens projets doivent rester surveillés."""
    scripts = assets_root / "scripts"
    if not scripts.is_dir():
        return [scripts]
    return [scripts, *sorted(d for d in scripts.rglob("*") if d.is_dir())]


class ProjectWatcher(QObject):
    """
    Surveille le répertoire d'un projet et notifie les changements de fichiers.

    assets/   → asset_appeared / asset_removed / asset_modified / lua_changed
    project/  → scene_changed
    """

    asset_appeared = pyqtSignal(str)   # nouveau fichier brut dans assets/
    asset_removed  = pyqtSignal(str)   # fichier supprimé de assets/
    asset_renamed  = pyqtSignal(str, str)  # fichier brut renommé : (avant, après)
    asset_modified = pyqtSignal(str)   # fichier existant modifié dans assets/
    lua_changed    = pyqtSignal(str)   # .lua créé ou modifié dans assets/scripts/
    scene_changed  = pyqtSignal(str)   # .json de scène modifié dans project/scenes/
    sidecar_changed = pyqtSignal(str)  # .json d'asset créé/modifié dans assets/<famille>/

    _DEBOUNCE_MS = 200

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._timers: dict[str, QTimer] = {}
        self._project_root: Optional[Path] = None
        self._suppress = False
        # Timer unique et ré-armable qui lève la suppression. Réutilisé (plutôt
        # que QTimer.singleShot) pour qu'une rafale de sauvegardes internes
        # (maintien d'une flèche = nudge répété, molette continue sur un spinbox)
        # garde le watcher suppressé jusqu'à 350 ms APRÈS la DERNIÈRE écriture.
        # Sinon la 1re sauvegarde ré-arme le watcher en plein milieu de la rafale
        # et une écriture suivante est vue comme « modif externe » → rechargement
        # de la scène qui recrée les items en cours de manipulation → crash.
        self._suppress_timer = QTimer(self)
        self._suppress_timer.setSingleShot(True)
        self._suppress_timer.timeout.connect(self._clear_suppress)

        # snapshot des fichiers connus dans chaque dossier surveillé
        # dir_str -> {file_str: (taille, date_ns)} — cf. _scan_dir
        self._dir_snapshots: dict[str, dict[str, tuple[int, int]]] = {}

    # ── API publique ────────────────────────────────────────────────

    def watch_project(self, project_path: Path):
        """Lance la surveillance d'un projet."""
        self._clear()
        self._project_root = project_path

        # Dossiers à surveiller dans assets/
        assets_root = project_path / "assets"
        asset_dirs = [
            assets_root,
            assets_root / "sprites",
            assets_root / "backgrounds",
            assets_root / "sounds",
            assets_root / "sfx",
            assets_root / "music",
            assets_root / "fonts",
            *_script_dirs(assets_root),
        ]

        # Dossiers project/ (éditeur uniquement)
        project_dirs = [
            project_path / "project" / "scenes",
            project_path / "project" / "prefab",
            project_path / "project" / "backgrounds",
        ]

        for d in asset_dirs + project_dirs:
            if d.exists():
                self._watcher.addPath(str(d))
                self._dir_snapshots[str(d)] = self._scan_dir(d)

        self._index_files(project_path)

    def unwatch(self):
        self._clear()

    @contextmanager
    def suspended(self):
        """Désactive temporairement les notifications pendant une sauvegarde interne."""
        paths = list(self._watcher.files())
        dirs  = list(self._watcher.directories())
        if paths:
            self._watcher.removePaths(paths)
        if dirs:
            self._watcher.removePaths(dirs)
        self._suppress = True
        try:
            yield
        finally:
            for t in list(self._timers.values()):
                t.stop()
            self._timers.clear()
            if paths:
                self._watcher.addPaths(paths)
            if dirs:
                self._watcher.addPaths(dirs)
            # Ré-arme le délai : chaque sortie de suspended() repousse la levée
            # de suppression, donc la fenêtre ne se ferme que 350 ms après la
            # toute dernière sauvegarde de la rafale (cf. _suppress_timer).
            self._suppress_timer.start(self._DEBOUNCE_MS + 150)

    # ── Interne ─────────────────────────────────────────────────────

    def _scan_dir(self, d: Path) -> dict[str, tuple[int, int]]:
        """Les fichiers pertinents présents dans `d` (non-récursif), chacun avec
        sa TAILLE et sa DATE à la nanoseconde.

        Ces deux nombres ne servent qu'à une chose : reconnaître un RENOMMAGE.
        Renommer ne touche ni au contenu ni à la date — un fichier qui disparaît
        et un fichier qui apparaît dans le même événement avec la même empreinte
        sont le même fichier sous un autre nom (cf. `_on_dir_changed`). Deux
        fichiers DIFFÉRENTS qui partageraient la taille ET la date à la
        nanoseconde près, ça ne se produit pas.

        Une empreinte, pas un hachage : lire le contenu de chaque fichier à
        chaque frémissement d'un dossier d'assets coûterait à chaque
        sauvegarde, pour la même réponse."""
        out: dict[str, tuple[int, int]] = {}
        if not d.exists():
            return out
        for f in d.iterdir():
            if not (f.is_file()
                    and f.suffix.lower() in (_ASSET_SUFFIXES | {_LUA_SUFFIX, _JSON_SUFFIX})):
                continue
            try:
                st = f.stat()
            except OSError:
                continue    # disparu entre l'itération et le stat
            out[str(f)] = (st.st_size, st.st_mtime_ns)
        return out

    def _clear(self):
        paths = self._watcher.files() + self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)
        for t in self._timers.values():
            t.stop()
        self._timers.clear()
        self._suppress_timer.stop()
        self._suppress = False
        self._dir_snapshots.clear()

    def _index_files(self, project_path: Path):
        """Ajoute tous les fichiers pertinents à la surveillance."""
        assets_root = project_path / "assets"
        asset_dirs = [assets_root / sub for sub in
                      ("sprites", "backgrounds", "sounds", "sfx", "music", "fonts")]
        for d in asset_dirs + _script_dirs(assets_root):
            if d.exists():
                for f in d.iterdir():
                    # Le `.json` d'un sidecar est suivi comme le fichier source :
                    # sans lui, éditer une police ou un fond à la main hors de
                    # l'éditeur ne se voyait jamais.
                    if f.is_file() and f.suffix.lower() in (
                            _ASSET_SUFFIXES | {_LUA_SUFFIX, _JSON_SUFFIX}):
                        self._watcher.addPath(str(f))

        # JSONs de scènes (éditeur)
        scenes_dir = project_path / "project" / "scenes"
        if scenes_dir.exists():
            for f in scenes_dir.glob("*.json"):
                self._watcher.addPath(str(f))

    def _clear_suppress(self):
        self._suppress = False

    def _on_file_changed(self, path_str: str):
        """Fichier existant modifié (éditeur externe)."""
        path = Path(path_str)
        if path.exists():
            self._watcher.addPath(path_str)

        if self._suppress:
            return

        if path_str in self._timers:
            self._timers[path_str].stop()

        t = QTimer(self)
        t.setSingleShot(True)
        t.setInterval(self._DEBOUNCE_MS)
        t.timeout.connect(lambda p=path_str: self._emit_modified(p))
        self._timers[path_str] = t
        t.start()

    def _on_dir_changed(self, dir_str: str):
        """Un fichier a été créé ou supprimé dans un répertoire surveillé."""
        d = Path(dir_str)
        old_snap = self._dir_snapshots.get(dir_str, {})

        if not d.exists():
            # Dossier lui-même supprimé
            for path_str in old_snap:
                self.asset_removed.emit(path_str)
            self._dir_snapshots.pop(dir_str, None)
            return

        new_snap = self._scan_dir(d)
        self._dir_snapshots[dir_str] = new_snap

        appeared = [p for p in new_snap if p not in old_snap]
        vanished = [p for p in old_snap if p not in new_snap]

        # Renommages — retirés des deux listes AVANT qu'elles ne soient
        # parcourues : un renommage n'est ni une création ni une suppression,
        # et le traiter comme les deux revenait à détruire l'asset pour en
        # créer un neuf sous le nouveau nom.
        for old_path, new_path in pair_renames(old_snap, new_snap):
            appeared.remove(new_path)
            vanished.remove(old_path)
            self._watcher.removePath(old_path)
            self._watcher.addPath(new_path)
            self.asset_renamed.emit(old_path, new_path)

        # Fichiers apparus
        for path_str in appeared:
            path = Path(path_str)
            self._watcher.addPath(path_str)
            if path.suffix.lower() == _LUA_SUFFIX:
                self.lua_changed.emit(path_str)
            elif path.suffix.lower() in _ASSET_SUFFIXES:
                self.asset_appeared.emit(path_str)
            elif (path.suffix.lower() == _JSON_SUFFIX
                  and path.parent.name in _SIDECAR_DIRS):
                self.sidecar_changed.emit(path_str)

        # Fichiers disparus
        for path_str in vanished:
            path = Path(path_str)
            self._watcher.removePath(path_str)
            if path.suffix.lower() in _ASSET_SUFFIXES:
                self.asset_removed.emit(path_str)

    def _emit_modified(self, path_str: str):
        """Émet le bon signal pour un fichier modifié."""
        path = Path(path_str)
        suffix = path.suffix.lower()

        if suffix == _LUA_SUFFIX:
            self.lua_changed.emit(path_str)
        elif suffix == _JSON_SUFFIX:
            parent = path.parent.name
            if parent == "scenes":
                self.scene_changed.emit(path_str)
            elif parent in _SIDECAR_DIRS:
                self.sidecar_changed.emit(path_str)
        elif suffix in _ASSET_SUFFIXES:
            self.asset_modified.emit(path_str)
