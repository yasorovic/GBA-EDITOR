"""
core/update_install.py — récupérer la version annoncée par `core/update_check`.

Trois formes de distribution (cf. `release.yml`), trois comportements :

- **installateur Windows** : téléchargé dans le dossier temporaire, puis lancé en
  silencieux (`/S`) après la fermeture de l'éditeur ; il remplace les fichiers et relance
  (`BACKSTAGE_RELAUNCH`, cf. `packaging/windows/installer.nsi`) ;
- **ZIP portable** et **AppImage** : téléchargés dans le dossier que l'appelant donne (celui
  de l'utilisateur), rien de plus — ils ne peuvent pas se remplacer eux-mêmes ;
- **lancé depuis les sources**, ou Linux hors AppImage : `install_kind()` rend `None`.

Tout fichier est vérifié contre le `SHA256SUMS` joint à la release avant d'être gardé ou
exécuté ; sans lui, rien n'est installé. Bloquant (réseau) : hors du fil de l'interface.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from core.app_info import APP_NAME, APP_VERSION
from core.app_paths import APP_DIR, IS_FROZEN, IS_LINUX, IS_WINDOWS
from core.update_check import LatestRelease

# Le suffixe du fichier de release que chaque forme attend (cf. `release.yml`).
_ASSET_SUFFIX = {
    "installer": "-windows-setup.exe",
    "portable": "-windows-portable.zip",
    "appimage": ".AppImage.tar.gz",
}


def install_kind() -> str | None:
    if not IS_FROZEN:
        return None
    if IS_WINDOWS:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\{APP_NAME}") as key:
                installed = Path(winreg.QueryValueEx(key, "InstallDir")[0]).resolve() == APP_DIR
        except OSError:
            installed = False
        return "installer" if installed else "portable"
    return "appimage" if IS_LINUX and os.environ.get("APPIMAGE") else None


def installer_folder() -> Path:
    return Path(tempfile.gettempdir()) / f"{APP_NAME}Update"


def parse_sums(text: str) -> dict[str, str]:
    """Le contenu d'un `sha256sum` (« empreinte  nom » par ligne) → {nom: empreinte}."""
    sums = {}
    for line in text.splitlines():
        digest, _, name = line.strip().partition(" ")
        if digest and name.strip():
            sums[name.strip().lstrip("*")] = digest.lower()
    return sums


def _open(url: str):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"}), timeout=30)


def download_release(release: LatestRelease, kind: str, folder: Path,
                     progress: Callable[[int], None] = lambda percent: None) -> Path:
    """Télécharge et vérifie dans `folder` le fichier de `kind` ; rend son chemin. Lève sur toute anomalie
    (fichier absent de la release, `SHA256SUMS` absent, empreinte fausse, réseau)."""
    assets = dict(release.assets)
    name = next((n for n in assets if n.endswith(_ASSET_SUFFIX[kind])), None)
    if name is None or "SHA256SUMS" not in assets:
        raise LookupError("The release has no matching file or no SHA256SUMS.")
    with _open(assets["SHA256SUMS"]) as response:
        expected = parse_sums(response.read().decode("utf-8")).get(name)
    if expected is None:
        raise LookupError(f"{name} is not listed in SHA256SUMS.")

    folder.mkdir(parents=True, exist_ok=True)
    final, partial = folder / name, folder / f"{name}.part"
    digest = hashlib.sha256()
    with _open(assets[name]) as response, open(partial, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(256 * 1024):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if total:
                progress(done * 100 // total)
    if digest.hexdigest() != expected:
        partial.unlink()
        raise ValueError(f"{name} does not match its SHA-256.")
    partial.replace(final)
    return final


def launch_installer(installer: Path) -> None:
    """Lance l'installateur en silencieux, détaché : il survit à la fermeture de l'éditeur,
    attend que `Backstage.exe` se libère, installe puis relance l'éditeur."""
    subprocess.Popen(
        [str(installer), "/S"], env={**os.environ, "BACKSTAGE_RELAUNCH": "1"}, close_fds=True,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
