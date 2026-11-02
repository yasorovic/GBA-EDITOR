"""
core/mgba_keys.py — les touches clavier que l'éditeur transmet à mGBA.

mGBA garde ses touches dans son propre `config.ini`, section `[gba.input.QT_K]`, une clé par bouton
(`keyA=88`) dont la valeur est un code `Qt.Key`. L'éditeur ne change que ces lignes, au lancement de
l'émulateur : le reste du fichier (manettes, profils, vidéo) est rendu tel quel. Tant que l'utilisateur n'a
rien choisi, le fichier n'est pas touché.

Stdlib seule.
"""
from __future__ import annotations

import os
from pathlib import Path

from core.app_paths import IS_LINUX, IS_WINDOWS

SECTION = "gba.input.QT_K"

# Les dix boutons de la GBA, dans l'ordre d'affichage : (clé du config.ini, libellé).
GBA_BUTTONS = (
    ("Up", "Up"), ("Down", "Down"), ("Left", "Left"), ("Right", "Right"),
    ("A", "A"), ("B", "B"), ("L", "L"), ("R", "R"),
    ("Start", "Start"), ("Select", "Select"),
)

# Les touches d'origine de mGBA (codes Qt.Key) : ce que montre l'écran tant que rien n'est choisi.
DEFAULT_KEYS = {
    "Up": 0x01000013, "Down": 0x01000015, "Left": 0x01000012, "Right": 0x01000014,
    "A": 0x58, "B": 0x5A, "L": 0x41, "R": 0x53,
    "Start": 0x01000004, "Select": 0x01000003,
}


def mgba_config_file(mgba_exe: Path | None) -> Path | None:
    """Le `config.ini` que cette installation de mGBA lira, ou None si la plateforme n'est pas prise en charge.
    Un `portable.ini` à côté de l'exécutable range la config à côté de lui."""
    if mgba_exe is not None and (mgba_exe.parent / "portable.ini").exists():
        return mgba_exe.parent / "config.ini"
    if IS_WINDOWS:
        base = os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Roaming") / "mGBA" / "config.ini"
    if IS_LINUX:
        if mgba_exe is not None and "io.mgba" in str(mgba_exe).lower():     # Flatpak
            return Path.home() / ".var/app/io.mgba.mGBA/config/mgba/config.ini"
        xdg = os.environ.get("XDG_CONFIG_HOME")
        return (Path(xdg) if xdg else Path.home() / ".config") / "mgba" / "config.ini"
    return None


def write_keys(config_file: Path, keys: dict[str, int]) -> None:
    """Pose `keys` (clé de bouton → code Qt.Key) dans la section clavier de `config_file`, créé au besoin.
    Édition ligne à ligne : les autres sections et clés, et le style de fin de ligne, restent intacts."""
    # En octets : `read_text` convertirait les fins de ligne avant qu'on ait pu les reconnaître.
    text = config_file.read_bytes().decode("utf-8", errors="replace") if config_file.exists() else ""
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    wanted = {f"key{name}": str(code) for name, code in keys.items()}

    start = next((i for i, line in enumerate(lines) if line.strip() == f"[{SECTION}]"), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"[{SECTION}]")
        lines += [f"{key}={value}" for key, value in wanted.items()]
    else:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
        pending = dict(wanted)
        for i in range(start + 1, end):
            key = lines[i].partition("=")[0].strip()
            if key in pending:
                lines[i] = f"{key}={pending.pop(key)}"
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1                                    # avant la ligne vide qui clôt la section
        lines[insert_at:insert_at] = [f"{key}={value}" for key, value in pending.items()]

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_bytes((eol.join(lines) + eol).encode("utf-8"))
