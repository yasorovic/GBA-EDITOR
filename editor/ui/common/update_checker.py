"""
ui/common/update_checker.py — l'état « une version plus récente existe-t-elle ? » de la session.

UN SEUL objet par fenêtre principale (`MainWindow.update_checker`) : la vérification
automatique du démarrage, le point discret du menu et la fenêtre « Updates » lisent
tous le même état. La vérification elle-même est `core/update_check` ; ici on la lance
hors du fil de l'interface et on garde ce qu'elle a trouvé dans les réglages (groupe
`Updates`), pour que le point reste affiché d'un lancement à l'autre sans réinterroger
GitHub avant un jour.

Une version « importante » (`update.json`) trouvée par la vérification AUTOMATIQUE émet
`important_found`, une seule fois par version (`notified_version`) ; l'appelant en fait
une pop-up. « Ignorer cette version » (`ignore`) retire le point pour elle seule.

`download()` récupère la version (cf. `core/update_install` pour ce que chaque forme de
distribution en fait) : l'installateur Windows est annoncé par `installer_ready`, que la
fenêtre principale transforme en fermeture puis lancement ; un ZIP portable ou une AppImage
atterrissent dans `download_dir` (le dossier choisi par l'utilisateur, « Téléchargements »
du système par défaut), dossier que l'on ouvre. `cancel_download()` l'interrompt.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QStandardPaths, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices

from core.app_info import APP_NAME, APP_VERSION
from core.update_check import (
    CHECK_FREQUENCIES, DEFAULT_CHECK_FREQUENCY, LatestRelease, fetch_latest_release, is_due,
    version_key,
)
from core.update_install import download_release, install_kind, installer_folder


def update_frequency() -> str:
    """La fréquence de la vérification automatique (réglages, catégorie Updates). Lue dans les
    réglages à chaque appel : la catégorie et le vérificateur n'ont pas à se connaître."""
    settings = QSettings(APP_NAME, "Updates")
    stored = settings.value("frequency", "")
    if stored in CHECK_FREQUENCIES:
        return stored
    # Avant la fréquence, une case à cocher : décochée, elle devient « jamais ».
    return DEFAULT_CHECK_FREQUENCY if settings.value("auto_check", True, type=bool) else "never"


def set_update_frequency(frequency: str):
    QSettings(APP_NAME, "Updates").setValue("frequency", frequency)


class _Fetch(QThread):
    found = pyqtSignal(object)   # LatestRelease
    failed = pyqtSignal()

    def run(self):
        try:
            self.found.emit(fetch_latest_release())
        except Exception:
            self.failed.emit()


class _Download(QThread):
    progress = pyqtSignal(int)
    done = pyqtSignal(object)   # Path
    failed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, release: LatestRelease, kind: str, folder: Path, parent=None):
        super().__init__(parent)
        self._release, self._kind, self._folder = release, kind, folder

    def run(self):
        try:
            self.done.emit(download_release(
                self._release, self._kind, self._folder, self.progress.emit,
                self.isInterruptionRequested))
        except InterruptedError:
            self.cancelled.emit()
        except Exception:
            self.failed.emit()


class UpdateChecker(QObject):
    changed = pyqtSignal()   # l'état (en cours, trouvé, échec) a bougé
    important_found = pyqtSignal(object)   # LatestRelease
    installer_ready = pyqtSignal(object)   # Path de l'installateur vérifié

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings(APP_NAME, "Updates")
        self._fetch: _Fetch | None = None
        self.checking = False
        self.failed = False
        self.checked = False   # une vérification a abouti depuis le lancement
        self._automatic = False
        self._download: _Download | None = None
        self.kind = install_kind()   # installer | portable | appimage | None (sources)
        self.downloading = False
        self.progress = 0
        self.download_failed = False
        self.downloaded: Path | None = None   # ZIP / AppImage récupéré, hors installateur
        self.available = self._stored_release()

    @property
    def download_dir(self) -> Path:
        default = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        return Path(self._settings.value("download_dir", default))

    @download_dir.setter
    def download_dir(self, folder: Path):
        self._settings.setValue("download_dir", str(folder))
        self.changed.emit()

    @property
    def badge(self) -> bool:
        """Faut-il montrer le point discret ?"""
        return (self.available is not None
                and self.available.version != self._settings.value("ignored_version", ""))

    def ignore(self):
        if self.available:
            self._settings.setValue("ignored_version", self.available.version)
            self.changed.emit()

    def check_if_due(self):
        """Au démarrage : une vérification si la fréquence choisie (Réglages > Updates) l'exige."""
        last = self._settings.value("last_check", 0.0, type=float)
        if is_due(last, time.time(), update_frequency()):
            self.check(automatic=True)

    def check(self, automatic: bool = False):
        if self.checking:
            return
        self.checking, self.failed, self._automatic = True, False, automatic
        self._fetch = _Fetch(self)
        self._fetch.found.connect(self._on_found)
        self._fetch.failed.connect(self._on_failed)
        self._fetch.start()
        self.changed.emit()

    def _on_found(self, release: LatestRelease):
        self.checking, self.checked = False, True
        self.available = release if release.is_newer else None
        self._settings.setValue("last_check", time.time())
        self._settings.setValue("release", (
            [release.version, release.notes, release.page_url, release.major,
             json.dumps(release.assets)]
            if self.available else None))
        self.changed.emit()
        if (self._automatic and release.is_newer and release.major
                and release.version != self._settings.value("notified_version", "")):
            self._settings.setValue("notified_version", release.version)
            self.important_found.emit(release)

    def download(self):
        if self.downloading or not self.available or not self.kind:
            return
        self.downloading, self.download_failed, self.progress, self.downloaded = True, False, 0, None
        folder = installer_folder() if self.kind == "installer" else self.download_dir
        self._download = _Download(self.available, self.kind, folder, self)
        self._download.progress.connect(self._on_progress)
        self._download.done.connect(self._on_downloaded)
        self._download.failed.connect(self._on_download_failed)
        self._download.cancelled.connect(self._on_download_cancelled)
        self._download.start()
        self.changed.emit()

    def cancel_download(self):
        """Interrompt le téléchargement en cours ; le fichier partiel est supprimé par le fil."""
        if self.downloading and self._download:
            self._download.requestInterruption()

    def _on_download_cancelled(self):
        self.downloading = False
        self.changed.emit()

    def _on_progress(self, percent: int):
        self.progress = percent
        self.changed.emit()

    def _on_downloaded(self, path: Path):
        self.downloading = False
        if self.kind == "installer":
            self.installer_ready.emit(path)
        else:
            self.downloaded = path
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        self.changed.emit()

    def _on_download_failed(self):
        self.downloading, self.download_failed = False, True
        self.changed.emit()

    def _on_failed(self):
        self.checking, self.failed = False, True
        self.changed.emit()

    def _stored_release(self) -> LatestRelease | None:
        """La mise à jour trouvée au lancement précédent, si elle reste plus récente que nous
        (l'utilisateur a pu s'être mis à jour depuis)."""
        stored = self._settings.value("release")
        if not isinstance(stored, list) or len(stored) != 5:
            return None
        version, notes, page_url, major, assets = stored
        try:
            if version_key(version) <= version_key(APP_VERSION):
                return None
        except ValueError:
            return None
        return LatestRelease(version, notes, page_url, True, major in (True, "true"),
                             tuple(tuple(pair) for pair in json.loads(assets)))
