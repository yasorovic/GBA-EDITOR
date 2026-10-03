"""
core/project_templates.py — Registre des projets modèles téléchargeables.

Un template pointe vers un sous-dossier d'une archive zip (`APP_TEMPLATES_URL`,
cf. `core/app_info.py`). Un hébergeur de code ne sert pas de zip pour un
sous-dossier seul : on télécharge le zip entier et on n'en extrait que
`repo_subdir`. Une fois sur le disque, le dossier extrait est un projet comme
un autre — aucune notion de « template » ne survit à l'extraction, il
s'ouvre par le chemin standard (Project.load).

**Sans adresse (`APP_TEMPLATES_URL` vide), il n'y a aucun modèle** : la liste est
vide et le sélecteur de projet n'affiche pas l'onglet.
"""

from __future__ import annotations

import io
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from core.app_info import APP_TEMPLATES_URL

REPO_ZIP_URL = APP_TEMPLATES_URL


@dataclass(frozen=True)
class ProjectTemplate:
    id:           str
    display_name: str
    description:  str
    repo_subdir:  str   # chemin dans le dépôt, ex. "Project Demo/PongAdvanced"

    @property
    def folder_name(self) -> str:
        return Path(self.repo_subdir).name


TEMPLATES: list[ProjectTemplate] = [
    ProjectTemplate(
        id="pong",
        display_name="Pong Advanced",
        description="Complete game — scenes, sprites, scripts, music.",
        repo_subdir="Project Demo/PongAdvanced",
    ),
] if REPO_ZIP_URL else []


def target_dir(template: ProjectTemplate, projects_dir: Path) -> Path:
    return projects_dir / template.folder_name


def is_downloaded(template: ProjectTemplate, projects_dir: Path) -> bool:
    d = target_dir(template, projects_dir)
    return d.is_dir() and any(d.iterdir())


def download_template(
    template: ProjectTemplate,
    projects_dir: Path,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Path:
    """Télécharge le zip des modèles et n'en extrait que `repo_subdir`.

    Lève une exception (réseau, sous-dossier absent, extraction) — à
    l'appelant de l'afficher ; le dossier partiel est nettoyé avant de
    relancer l'exception."""
    if not REPO_ZIP_URL:
        raise RuntimeError("No template source is configured.")
    dest = target_dir(template, projects_dir)
    if dest.exists():
        raise FileExistsError(f"'{dest}' already exists.")

    if progress_cb:
        progress_cb("Downloading…")
    with urllib.request.urlopen(REPO_ZIP_URL, timeout=30) as resp:
        data = resp.read()

    if progress_cb:
        progress_cb("Extracting…")
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Le dossier racine d'un zip d'archive porte le nom du dépôt et de la
            # branche : on le LIT dans l'archive plutôt que de le recopier ici.
            root = zf.namelist()[0].split("/")[0]
            prefix = f"{root}/{template.repo_subdir}/"
            members = [m for m in zf.namelist() if m.startswith(prefix)]
            if not members:
                raise FileNotFoundError(
                    f"'{template.repo_subdir}' not found in the archive."
                )
            for member in members:
                rel = member[len(prefix):]
                if not rel:
                    continue
                out_path = dest / rel
                if member.endswith("/"):
                    out_path.mkdir(parents=True, exist_ok=True)
                else:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(out_path, "wb") as f:
                        shutil.copyfileobj(src, f)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise

    return dest
