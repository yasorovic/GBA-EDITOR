"""
Backstage — détection et configuration de la toolchain
Gère devkitPro (grit + make + devkitARM) et mgba.
Les chemins sont persistés dans un fichier JSON du dossier de config
utilisateur (voir CONFIG_FILE).
"""

import glob
import json
import os
import shutil
from pathlib import Path

from core.app_info import APP_NAME
from core.app_paths import IS_LINUX, IS_WINDOWS


def config_dir() -> Path:
    """
    Dossier de config utilisateur, par OS. PUBLIQUE : trois modules y posent
    leur fichier (`toolchain.json`, `external_tools.json`, `keybindings.json`,
    et maintenant `interface.json`). Le tiret bas d'origine disait « ne
    m'appelle pas de dehors » pendant que trois appelants le faisaient.

    Surtout PAS à côté du module : en build onefile, le module vit dans le
    dossier d'extraction temporaire, détruit à la fermeture — les chemins
    devkitPro saisis par l'utilisateur étaient donc reperdus à chaque
    lancement de l'exe.
    """
    if IS_WINDOWS:
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / APP_NAME.lower()


# Fichier de config persistant
CONFIG_FILE = config_dir() / "toolchain.json"

# Ancien emplacement (à côté du module). Encore lu une fois, pour ne pas
# faire reconfigurer devkitPro aux installations lancées depuis les sources
# avant le déplacement ; la sauvegarde suivante écrit dans CONFIG_FILE.
_LEGACY_CONFIG_FILE = Path(__file__).parent / "toolchain.json"

# Pages de téléchargement officielles (réutilisées par l'écran d'accueil
# et la doc — pas de lien direct vers un binaire précis pour éviter les
# URLs qui périment à chaque nouvelle version).
DEVKITPRO_URL = "https://devkitpro.org/wiki/Getting_Started"
MGBA_URL      = "https://mgba.io/downloads.html"

# Sous Linux, aucun installateur ne s'en charge : l'écran montre les commandes à
# copier, pour Debian/Ubuntu (les autres distributions : à venir, la clé est le
# nom de l'outil tel que l'interface l'affiche). Une commande par ligne ; sous
# Windows (ou macOS), la liste est vide et l'écran garde son lien de téléchargement.
# devkitPro : le script officiel de https://devkitpro.org/wiki/devkitPro_pacman
# ajoute le dépôt apt de devkitPro et installe `dkp-pacman`, qui fournit ensuite
# le groupe `gba-dev` (installé dans /opt/devkitpro, un emplacement connu).
# mGBA n'y figure pas : il s'obtient en exécutable sur le site officiel (MGBA_URL),
# que l'écran montre déjà ; des commandes de plus n'apporteraient rien.
_LINUX_INSTALL_COMMANDS = {
    "devkitPro": [
        "wget https://apt.devkitpro.org/install-devkitpro-pacman",
        "chmod +x ./install-devkitpro-pacman",
        "sudo ./install-devkitpro-pacman",
        "sudo dkp-pacman -S gba-dev",
    ],
}


def install_commands(tool: str) -> list[str]:
    """Les commandes qui installent `tool` ("devkitPro") sur ce système, dans
    l'ordre ; vide quand ce système a un installateur (Windows), que l'outil
    s'obtient autrement (mGBA) ou que le système n'est pas encore pris en charge."""
    return list(_LINUX_INSTALL_COMMANDS.get(tool, [])) if IS_LINUX else []

# Emplacements Windows typiques
_WIN_DEFAULTS = [
    Path("C:/devkitPro"),
    Path("D:/devkitPro"),
    Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "devkitPro",
]
_MGBA_WIN_DEFAULTS = [
    Path("C:/Program Files/mGBA"),
    Path("C:/Program Files (x86)/mGBA"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "mGBA",
]

# mGBA sous Linux : l'AppImage officielle n'est pas dans le PATH (elle se
# télécharge dans un dossier, nom versionné), et Flatpak/Snap exposent un
# lanceur dans un dossier d'exports. Chaque motif est un glob.
_MGBA_UNIX_GLOBS = [
    str(Path.home() / ".local/share/flatpak/exports/bin/io.mgba.mGBA"),
    "/var/lib/flatpak/exports/bin/io.mgba.mGBA",
    "/snap/bin/mgba*",
    "/usr/games/mgba*",
    "/Applications/mGBA.app/Contents/MacOS/mGBA",
    *(str(Path.home() / d / pattern)
      for d in ("Applications", "Downloads", "Desktop", "bin", ".local/bin")
      for pattern in ("mGBA*.appimage", "mGBA*.AppImage", "mgba*.appimage", "mgba*.AppImage")),
    *(f"/opt/{pattern}" for pattern in ("mGBA*.AppImage", "mgba*.AppImage", "mgba/mgba*")),
]

# Emplacements Linux/macOS typiques
_UNIX_DEFAULTS = [
    Path("/opt/devkitpro"),
    Path.home() / "devkitpro",
    Path("/usr/local/devkitpro"),
]


# Les trois outils sans lesquels aucune ROM ne se construit, et les états qu'en tire
# `Toolchain.devkitpro_state`.
DEVKITPRO_TOOLS = ("grit", "make", "arm-none-eabi-gcc")
DEVKITPRO_OK = "ok"
DEVKITPRO_INCOMPLETE = "incomplete"
DEVKITPRO_MISSING = "missing"


class Toolchain:
    """
    Détecte et stocke les chemins vers devkitPro et mgba.
    Utilise shutil.which() en priorité, puis les emplacements connus,
    puis le fichier de config sauvegardé par l'utilisateur.
    """

    def __init__(self):
        self._config: dict = self._load_config()
        self._status: dict[str, Path | None] | None = None

    # ── Chargement / sauvegarde config ────────────────────────────

    def _load_config(self) -> dict:
        for path in (CONFIG_FILE, _LEGACY_CONFIG_FILE):
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return {}

    def save(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(self._config, indent=2),
            encoding="utf-8"
        )

    # ── Accesseurs / setters ───────────────────────────────────────

    @property
    def devkitpro_path(self) -> Path | None:
        if p := self._config.get("devkitpro"):
            return Path(p)
        return None

    @property
    def devkitpro_root(self) -> Path | None:
        """Le dossier devkitPro réellement utilisable : celui de la config s'il existe, sinon
        `$DEVKITPRO`, sinon le premier emplacement connu qui existe. `devkitpro_path`
        ne dit que ce que l'utilisateur a choisi ; un devkitPro installé à
        `/opt/devkitpro` sans rien configurer n'y figure pas."""
        if self.devkitpro_path and self.devkitpro_path.is_dir():
            return self.devkitpro_path
        candidates = [Path(e) for e in (os.environ.get("DEVKITPRO"),) if e]
        candidates += _WIN_DEFAULTS + _UNIX_DEFAULTS
        return next((c for c in candidates if c.is_dir()), None)

    @devkitpro_path.setter
    def devkitpro_path(self, path: Path):
        self._config["devkitpro"] = str(path)
        self.save()
        self.recheck()

    @property
    def mgba_path(self) -> Path | None:
        if p := self._config.get("mgba"):
            return Path(p)
        return None

    @mgba_path.setter
    def mgba_path(self, path: Path):
        self._config["mgba"] = str(path)
        self.save()
        self.recheck()

    # ── Résolution des exécutables ────────────────────────────────

    def resolve_grit(self) -> Path | None:
        """Retourne le chemin absolu de grit, ou None."""
        # 1. PATH système
        if p := shutil.which("grit"):
            return Path(p)
        # 2. Config utilisateur
        if dkp := self.devkitpro_path:
            for candidate in [
                dkp / "tools" / "bin" / "grit.exe",
                dkp / "tools" / "bin" / "grit",
                dkp / "msys2" / "usr" / "bin" / "grit.exe",
            ]:
                if candidate.exists():
                    return candidate
        # 3. Emplacements connus
        for base in _WIN_DEFAULTS + _UNIX_DEFAULTS:
            for sub in ["tools/bin/grit.exe", "tools/bin/grit"]:
                c = base / sub
                if c.exists():
                    return c
        return None

    def resolve_make(self) -> Path | None:
        """Retourne le chemin absolu de make, ou None."""
        if p := shutil.which("make"):
            return Path(p)
        if dkp := self.devkitpro_path:
            for candidate in [
                dkp / "msys2" / "usr" / "bin" / "make.exe",
                dkp / "msys2" / "mingw64" / "bin" / "make.exe",
            ]:
                if candidate.exists():
                    return candidate
        for base in _WIN_DEFAULTS:
            for sub in ["msys2/usr/bin/make.exe"]:
                c = base / sub
                if c.exists():
                    return c
        return None

    def resolve_arm_gcc(self) -> Path | None:
        """Retourne le chemin de arm-none-eabi-gcc, ou None."""
        # 1. PATH système
        if p := shutil.which("arm-none-eabi-gcc"):
            return Path(p)

        # 2. Bases à scanner : config utilisateur + emplacements connus
        bases = []
        if dkp := self.devkitpro_path:
            bases.append(Path(dkp))          # Path() normalise \ et /
        bases += [Path(b) for b in _WIN_DEFAULTS + _UNIX_DEFAULTS]

        for base in bases:
            for exe in ("arm-none-eabi-gcc.exe", "arm-none-eabi-gcc"):
                candidate = base / "devkitARM" / "bin" / exe
                if candidate.exists():
                    return candidate

        return None

    def resolve_binutil(self, tool: str) -> Path | None:
        """Un binutil devkitARM (`nm`, `size`, `objdump`…) par son nom court.

        Même recherche que `resolve_arm_gcc`, dont ces outils partagent le
        dossier et le préfixe. Écrit une fois plutôt qu'une méthode par outil :
        ils ne se distinguent que par leur nom.
        """
        exe = f"arm-none-eabi-{tool}"
        if p := shutil.which(exe):
            return Path(p)
        bases = []
        if dkp := self.devkitpro_path:
            bases.append(Path(dkp))
        bases += [Path(b) for b in _WIN_DEFAULTS + _UNIX_DEFAULTS]
        for base in bases:
            for name in (f"{exe}.exe", exe):
                candidate = base / "devkitARM" / "bin" / name
                if candidate.exists():
                    return candidate
        return None

    def resolve_mgba(self) -> Path | None:
        """Retourne le chemin de mgba, ou None."""
        for name in ("mgba", "mgba-qt", "mGBA"):
            if p := shutil.which(name):
                return Path(p)
        # Config utilisateur (chemin choisi manuellement dans l'éditeur)
        if p := self.mgba_path:
            if p.exists():
                return p
        # Emplacements connus Windows
        for base in _MGBA_WIN_DEFAULTS:
            for exe in ["mGBA.exe", "mgba.exe", "mgba-qt.exe"]:
                c = base / exe
                if c.exists():
                    return c
        # Emplacements connus Linux/macOS
        for pattern in _MGBA_UNIX_GLOBS:
            for c in sorted(glob.glob(pattern), reverse=True):
                if os.path.isfile(c) and os.access(c, os.X_OK):
                    return Path(c)
        return None

    def resolve_mmutil(self) -> Path | None:
        """mmutil — convertit WAV/MOD en soundbank maxmod."""
        if p := shutil.which("mmutil"):
            return Path(p)
        if dkp := self.devkitpro_path:
            for c in [dkp / "tools" / "bin" / "mmutil.exe",
                      dkp / "tools" / "bin" / "mmutil"]:
                if c.exists(): return c
        for base in _WIN_DEFAULTS + _UNIX_DEFAULTS:
            for sub in ["tools/bin/mmutil.exe", "tools/bin/mmutil"]:
                c = base / sub
                if c.exists(): return c
        return None

    def resolve_bin2s(self) -> Path | None:
        """bin2s — convertit un binaire en .s assembleur linkable."""
        if p := shutil.which("bin2s"):
            return Path(p)
        if dkp := self.devkitpro_path:
            for c in [dkp / "tools" / "bin" / "bin2s.exe",
                      dkp / "tools" / "bin" / "bin2s"]:
                if c.exists(): return c
        for base in _WIN_DEFAULTS + _UNIX_DEFAULTS:
            for sub in ["tools/bin/bin2s.exe", "tools/bin/bin2s"]:
                c = base / sub
                if c.exists(): return c
        return None

    # ── Status global ─────────────────────────────────────────────

    def check(self) -> dict[str, Path | None]:
        """Retourne un dict {outil: path|None} pour tous les outils.

        Une détection balaie le PATH et tous les emplacements connus (~200 ms) ;
        l'interface la demande à chaque rafraîchissement, d'où le cache. Il ne
        s'invalide que par `recheck()` (réglages modifiés, bouton « Vérifier »,
        clic sur Build) : le build, lui, résout ses outils par `resolve_*`."""
        if self._status is None:
            self._status = {
                "grit":         self.resolve_grit(),
                "make":         self.resolve_make(),
                "arm-none-eabi-gcc": self.resolve_arm_gcc(),
                "mgba":         self.resolve_mgba(),
            }
        return dict(self._status)

    def recheck(self):
        """Oublie la détection : la prochaine lecture refait l'inventaire."""
        self._status = None

    def devkitpro_missing_tools(self) -> list[str]:
        """Les outils devkitPro (grit, make, arm-none-eabi-gcc) introuvables."""
        s = self.check()
        return [tool for tool in DEVKITPRO_TOOLS if not s[tool]]

    @property
    def devkitpro_ok(self) -> bool:
        return not self.devkitpro_missing_tools()

    @property
    def devkitpro_state(self) -> str:
        """`DEVKITPRO_OK`, `DEVKITPRO_INCOMPLETE` ou `DEVKITPRO_MISSING`.

        « Incomplet » : on trouve un dossier devkitPro (celui des réglages ou un
        emplacement connu) ou l'un de ses outils propres (grit, arm-none-eabi-gcc),
        mais pas tous — typiquement
        une installation dont les paquets GBA n'ont pas été téléchargés jusqu'au bout.
        Ce n'est pas la même consigne que « introuvable » : réinstaller ou vérifier,
        et non chercher le dossier."""
        missing = self.devkitpro_missing_tools()
        if not missing:
            return DEVKITPRO_OK
        # `make` ne prouve rien : un Linux ou un Windows avec MSYS l'a sans devkitPro.
        found_own_tool = any(tool not in missing for tool in DEVKITPRO_TOOLS if tool != "make")
        if found_own_tool or self._devkitpro_folder_found():
            return DEVKITPRO_INCOMPLETE
        return DEVKITPRO_MISSING

    def _devkitpro_folder_found(self) -> bool:
        bases = [self.devkitpro_path] if self.devkitpro_path else []
        bases += _WIN_DEFAULTS + _UNIX_DEFAULTS
        return any(Path(base).is_dir() for base in bases)

    @property
    def mgba_ok(self) -> bool:
        return self.check()["mgba"] is not None
