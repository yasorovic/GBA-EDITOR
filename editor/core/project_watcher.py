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
        # Fichiers que l'éditeur déplace LUI-MÊME pendant une suspension
        # (suppression vers `.temp/`, Ctrl+Z qui les rend) : à la sortie, ils
        # font partie de la référence au lieu d'être pris pour des dépôts
        # externes. Vidés quand la dernière suspension imbriquée se termine.
        self._claimed: set[str] = set()
        self._suspend_depth = 0
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

        # Fichiers sources APPARUS mais dont la copie n'est peut-être pas finie :
        # chemin -> dernière empreinte vue. Ils restent hors de la référence du
        # dossier tant que leur empreinte bouge (cf. `_settle_check`) — un PNG
        # lu à moitié copié serait un import corrompu.
        self._settling: dict[str, tuple[int, int]] = {}
        # Ceux dont l'empreinte vient de se stabiliser : `_on_dir_changed` les
        # accepte le temps d'un passage, puis la liste est vidée.
        self._settled: set[str] = set()
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(self._DEBOUNCE_MS)
        self._settle_timer.timeout.connect(self._settle_check)

    # ── API publique ────────────────────────────────────────────────

    def watch_project(self, project_path: Path):
        """Lance la surveillance d'un projet."""
        self._clear()
        self._project_root = project_path

        for d in self._watched_dirs(project_path):
            if d.exists():
                self._watcher.addPath(str(d))
                self._dir_snapshots[str(d)] = self._scan_dir(d)

        self._index_files(project_path)

    def rescan(self):
        """Rattrape tout ce qui a changé sur le disque depuis le dernier état
        connu, sans compter sur les événements du système.

        `QFileSystemWatcher` rate des choses sous Windows : le watch d'un
        fichier tombe après un rename ou une suppression dans l'Explorateur, un
        dossier créé après coup n'est jamais suivi, une modif peut ne rien
        émettre. Au retour du focus de l'application, on compare donc le disque
        aux empreintes gardées et on émet les MÊMES signaux que le chemin
        temps réel (apparu / disparu / renommé / modifié)."""
        root = self._project_root
        if root is None:
            return
        self._suppress = False
        self._suppress_timer.stop()
        for d in self._watched_dirs(root):
            if not d.exists():
                if str(d) in self._dir_snapshots:
                    self._on_dir_changed(str(d))    # dossier disparu
                continue
            if str(d) not in self._dir_snapshots:
                self._watcher.addPath(str(d))       # dossier apparu depuis
            self._on_dir_changed(str(d))            # diff contre l'ancien état
        self._index_files(root)                     # ré-arme les watches tombés

    def _watched_dirs(self, project_path: Path) -> list[Path]:
        assets_root = project_path / "assets"
        return [
            assets_root,
            assets_root / "sprites",
            assets_root / "backgrounds",
            assets_root / "sounds",
            assets_root / "sfx",
            assets_root / "music",
            assets_root / "fonts",
            *_script_dirs(assets_root),
            # project/ (éditeur uniquement)
            project_path / "project" / "scenes",
            project_path / "project" / "prefab",
            project_path / "project" / "backgrounds",
        ]

    def unwatch(self):
        self._clear()
        # Sans racine, `rescan()` ne ressuscite pas le projet fermé au retour du
        # focus (il verrait tous ses fichiers comme apparus).
        self._project_root = None

    def claim(self, path: Path):
        """Déclare qu'un fichier source vient d'être déplacé par l'éditeur
        lui-même pendant la suspension en cours (cf. `_claimed`)."""
        self._claimed.add(str(path))

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
        self._suspend_depth += 1
        before = {d: dict(snap) for d, snap in self._dir_snapshots.items()}
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
            # Nos propres écritures deviennent l'état de référence : sans ça,
            # le prochain rescan les prendrait pour des modifs externes.
            #
            # Sauf les fichiers SOURCES que nous n'avons pas écrits nous-mêmes :
            # dépôts externes arrivés pendant l'import en cours (trois PNG
            # glissés d'un coup : le watcher ne voit le dossier qu'après le
            # premier, et la photo prise ici absorbait les deux autres comme
            # « déjà connus »), ou source retouchée dehors pendant la fenêtre.
            # Ils restent à leur ancien état dans la référence et on re-diffe
            # le dossier juste après. Les sidecars, eux, sont NOS écritures.
            leftover = False
            for dir_str in self._dir_snapshots:
                snap = self._scan_dir(Path(dir_str))
                known = before.get(dir_str, {})
                for p in list(snap):
                    if (Path(p).suffix.lower() not in _ASSET_SUFFIXES
                            or p in self._claimed):
                        continue
                    if p not in known:
                        del snap[p]
                        leftover = True
                    elif known[p] != snap[p]:
                        snap[p] = known[p]
                        leftover = True
                self._dir_snapshots[dir_str] = snap
            self._suspend_depth -= 1
            if self._suspend_depth == 0:
                self._claimed.clear()
            if leftover:
                QTimer.singleShot(0, self._rediff_dirs)
            # Ré-arme le délai : chaque sortie de suspended() repousse la levée
            # de suppression, donc la fenêtre ne se ferme que 350 ms après la
            # toute dernière sauvegarde de la rafale (cf. _suppress_timer).
            self._suppress_timer.start(self._DEBOUNCE_MS + 150)

    # ── Interne ─────────────────────────────────────────────────────

    def _settle_check(self):
        """Fin du délai : un fichier source apparu dont l'empreinte n'a pas
        bougé depuis le dernier passage est une copie terminée — on le laisse
        entrer ; un autre est encore en train d'être écrit, on attend."""
        ready: set[Path] = set()
        waiting = False
        for path_str, stamp in list(self._settling.items()):
            try:
                st = Path(path_str).stat()
            except OSError:
                del self._settling[path_str]    # disparu avant d'être fini
                continue
            now = (st.st_size, st.st_mtime_ns)
            if now == stamp:
                del self._settling[path_str]
                self._settled.add(path_str)
                ready.add(Path(path_str).parent)
            else:
                self._settling[path_str] = now
                waiting = True
        for d in ready:
            self._on_dir_changed(str(d))
        self._settled.clear()
        if waiting:
            self._settle_timer.start()

    def _rediff_dirs(self):
        """Rejoue le diff de chaque dossier suivi contre son état de référence."""
        for dir_str in list(self._dir_snapshots):
            self._on_dir_changed(dir_str)

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
        self._settle_timer.stop()
        self._settling.clear()
        self._settled.clear()
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
        renames = pair_renames(old_snap, new_snap)
        renamed_to = {new for _, new in renames}

        # Source apparue : on ne la rapporte qu'une fois sa copie finie. Un
        # renommage n'est pas concerné (même empreinte qu'un fichier déjà
        # complet), ni un fichier que `_settle_check` vient de valider.
        for path_str in [p for p in new_snap
                         if p not in old_snap
                         and p not in renamed_to
                         and p not in self._settled
                         and Path(p).suffix.lower() in _ASSET_SUFFIXES]:
            self._settling[path_str] = new_snap.pop(path_str)
            self._settle_timer.start()
        self._dir_snapshots[dir_str] = new_snap

        appeared = [p for p in new_snap if p not in old_snap]
        vanished = [p for p in old_snap if p not in new_snap]

        # Renommages — retirés des deux listes AVANT qu'elles ne soient
        # parcourues : un renommage n'est ni une création ni une suppression,
        # et le traiter comme les deux revenait à détruire l'asset pour en
        # créer un neuf sous le nouveau nom.
        for old_path, new_path in renames:
            appeared.remove(new_path)
            vanished.remove(old_path)
            self._watcher.removePath(old_path)
            self._watcher.addPath(new_path)
            self.asset_renamed.emit(old_path, new_path)

        # Fichiers modifiés en place (même nom, autre empreinte)
        for path_str, stamp in new_snap.items():
            if path_str in old_snap and old_snap[path_str] != stamp:
                self._dispatch_modified(path_str)

        # Fichiers apparus
        for path_str in appeared:
            path = Path(path_str)
            self._watcher.addPath(path_str)
            if path.suffix.lower() == _LUA_SUFFIX:
                self.lua_changed.emit(path_str)
            elif path.suffix.lower() in _ASSET_SUFFIXES:
                self.asset_appeared.emit(path_str)
            elif self._is_sidecar_json(path):
                self.sidecar_changed.emit(path_str)

        # Fichiers disparus
        for path_str in vanished:
            path = Path(path_str)
            self._watcher.removePath(path_str)
            if path.suffix.lower() in _ASSET_SUFFIXES:
                self.asset_removed.emit(path_str)

    @staticmethod
    def _is_sidecar_json(path: Path) -> bool:
        """Un sidecar d'asset vit dans assets/<famille>/ — `project/backgrounds/`
        porte le même nom de dossier mais n'en est pas un."""
        return (path.suffix.lower() == _JSON_SUFFIX
                and path.parent.name in _SIDECAR_DIRS
                and path.parent.parent.name == "assets")

    def _emit_modified(self, path_str: str):
        """Fin du debounce d'un fichier : n'émet que si l'empreinte diffère de
        celle déjà rapportée (le scan de dossier a pu la voir avant), et jamais
        pour un fichier disparu (le scan de dossier s'en charge)."""
        path = Path(path_str)
        try:
            st = path.stat()
        except OSError:
            return
        stamp = (st.st_size, st.st_mtime_ns)
        snap = self._dir_snapshots.get(str(path.parent))
        if snap is not None:
            if path_str not in snap:
                return      # inconnu : son apparition (ou sa copie en cours) est l'affaire du scan
            if snap.get(path_str) == stamp:
                return
            snap[path_str] = stamp
        self._dispatch_modified(path_str)

    def _dispatch_modified(self, path_str: str):
        """Émet le bon signal pour un fichier modifié."""
        path = Path(path_str)
        suffix = path.suffix.lower()

        if suffix == _LUA_SUFFIX:
            self.lua_changed.emit(path_str)
        elif suffix == _JSON_SUFFIX:
            if path.parent.name == "scenes":
                self.scene_changed.emit(path_str)
            elif self._is_sidecar_json(path):
                self.sidecar_changed.emit(path_str)
        elif suffix in _ASSET_SUFFIXES:
            self.asset_modified.emit(path_str)
