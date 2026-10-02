"""
core/diagnostics.py — le rapport qu'on colle dans un compte rendu de bug.

Tout ce qu'une personne qui reçoit « ça ne marche pas » demanderait en premier :
la machine, la toolchain, le projet ouvert, la fin du journal. Une seule
fonction, sans Qt : l'interface la copie dans le presse-papiers, un test la lit.

Ce que le rapport ne contient JAMAIS : le contenu du projet (scènes, scripts,
textes). Il dit combien de fichiers sont illisibles, pas ce qu'ils contiennent.
Les chemins y figurent, et peuvent porter un nom d'utilisateur : le rapport est
relu par la personne avant d'être collé (cf. `win.copy_diagnostics`).
"""
from __future__ import annotations

import datetime
import platform
import sys
from importlib import metadata
from pathlib import Path

from core import crash_log
from core.app_info import APP_AUTHOR, APP_NAME, APP_VERSION
from core.app_paths import IS_FROZEN

JOURNAL_LINES = 40     # lignes de `crash.log` reprises : la fin, là où est la dernière panne


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "inconnue"


def _tail(path: Path, lines: int) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    except OSError:
        return []


def _toolchain_lines(toolchain) -> list[str]:
    if toolchain is None:
        return ["  (toolchain non lue)"]
    out = [f"  devkitPro : {toolchain.devkitpro_path or 'non configuré'}"]
    for tool, path in toolchain.check().items():
        out.append(f"  {tool} : {path or 'INTROUVABLE'}")
    return out


def _project_lines(project) -> list[str]:
    if project is None:
        return ["  (aucun projet ouvert)"]
    from core.project_paths import PROJECT_FORMAT_VERSION
    out = [f"  nom : {project.settings.name}",
           f"  dossier : {project.root}",
           f"  format lu par cet éditeur : {PROJECT_FORMAT_VERSION}",
           f"  scènes : {len(project.scenes)}"]
    unreadable = project.unreadable_files()
    out.append(f"  fichiers illisibles : {len(unreadable)}")
    out += [f"    - {name} ({reason})" for name, reason in unreadable]
    out += [f"    + copie conservée : {name} → {backup}"
            for name, backup in project.preserved_files()]
    return out


def diagnostic_report(project=None, toolchain=None, journal_lines: int = JOURNAL_LINES) -> str:
    """Le rapport complet, en texte brut."""
    out = [
        f"{APP_NAME} — diagnostic",
        f"date : {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"version de l'éditeur : {APP_VERSION} ({APP_NAME}, {APP_AUTHOR})",
        "",
        "Machine",
        f"  système : {platform.platform()}",
        f"  Python : {sys.version.split()[0]} ({'distribution compilée' if IS_FROZEN else 'sources'})",
        f"  PyQt6 : {_package_version('PyQt6')}",
        "",
        "Toolchain",
        *_toolchain_lines(toolchain),
        "",
        "Projet",
        *_project_lines(project),
        "",
        f"Journal ({crash_log.LOG_FILE}, {journal_lines} dernières lignes)",
    ]
    tail = _tail(crash_log.LOG_FILE, journal_lines)
    out += [f"  {line}" for line in tail] if tail else ["  (vide : aucune panne enregistrée)"]
    native = _tail(crash_log.NATIVE_LOG_FILE, journal_lines)
    if native:
        out += ["", f"Journal natif ({crash_log.NATIVE_LOG_FILE})"] + [f"  {line}" for line in native]
    return "\n".join(out) + "\n"
