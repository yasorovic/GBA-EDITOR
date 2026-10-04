#!/usr/bin/env python3
"""
Build Nuitka de Backstage — Windows et Linux.

Une seule définition de la commande de build, utilisée par la CI comme en
local : c'est ce qui évite que les options divergent entre les deux et
qu'un problème n'apparaisse qu'au moment de publier.

Nom, auteur et version viennent de `editor/core/app_info.py` (source unique) :
`--version`, s'il est donné, doit EGALER `APP_VERSION` — c'est la garde qui
fait échouer une release dont le tag n'est pas celui du dépôt.

Usage :
    python packaging/nuitka_build.py --output-dir build-out
    python packaging/nuitka_build.py --print-version     # pour le workflow

Produit un dossier <output-dir>/Backstage/ contenant l'exécutable et ses
données. C'est ce dossier qui est ensuite zippé (portable) et empaqueté
par NSIS (installateur) — voir .github/workflows/release.yml.

Mode standalone et non onefile : l'installateur pose de toute façon un
dossier, et le onefile ré-extrait tout dans un dossier temporaire à chaque
lancement, ce qui ne fait que ralentir le démarrage sans rien apporter ici.

Prérequis : `pip install nuitka` + un compilateur C (MSVC sous Windows,
gcc sous Linux ; à défaut Nuitka télécharge MinGW64 avec
--assume-yes-for-downloads).
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EDITOR_DIR = REPO_ROOT / "editor"
IS_WINDOWS = sys.platform.startswith("win")


def _load_app_info():
    """`core/app_info.py` chargé PAR SON CHEMIN : l'importer comme `core.app_info`
    exigerait `editor/` dans le sys.path, donc le paquet `core` et ses effets
    de bord — ce script tourne sur un Python nu."""
    spec = importlib.util.spec_from_file_location(
        "app_info", EDITOR_DIR / "core" / "app_info.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


APP = _load_app_info()
APP_NAME = APP.APP_NAME           # « Backstage » : exe, dossier, produit
COMPANY = APP.APP_AUTHOR          # aligné sur PUBLISHER dans installer.nsi
APP_EXE = APP_NAME + (".exe" if IS_WINDOWS else "")


def numeric_version(version: str) -> str:
    """
    Normalise un tag en version numérique 4 champs pour les métadonnées
    Windows, qui n'acceptent que des chiffres : "v0.3.2" → "0.3.2.0",
    "1.0.0-rc1" → "1.0.0.0".
    """
    parts = re.findall(r"\d+", version)[:4]
    parts += ["0"] * (4 - len(parts))
    return ".".join(parts)


def staged_plugins_path(output_dir: Path) -> Path:
    """Emplacement du staging de plugins/ (voir stage_plugins)."""
    return output_dir / "_staging" / "plugins"


def stage_plugins(output_dir: Path) -> Path:
    """
    Recopie editor/plugins/ dans le staging, sans __pycache__.

    --include-raw-dir copie verbatim : sans ce filtrage, les .pyc du poste
    de build partiraient dans la distribution. On passe par un staging
    plutôt que de nettoyer editor/plugins/ — un script de build n'a pas à
    supprimer des fichiers dans l'arbre source.
    """
    staged = staged_plugins_path(output_dir)
    if staged.exists():
        shutil.rmtree(staged)
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        EDITOR_DIR / "plugins", staged,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return staged


def build_command(version: str, output_dir: Path) -> list[str]:
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--remove-output",              # jette le .build, garde le .dist
        "--enable-plugin=pyqt6",
        f"--output-dir={output_dir}",
        f"--output-filename={APP_EXE}",
    ]

    # Qt : "sensible" couvre platforms/styles/imageformats/iconengines, mais
    # pas les backends multimédia — or ui/sound_mixer/ utilise QtMultimedia
    # pour la préécoute des sons.
    cmd.append("--include-qt-plugins=sensible,multimedia")

    # editor/ est la racine du path à l'exécution (cf. main.py) : les modules
    # s'importent à plat. On force l'inclusion des paquets plutôt que de
    # compter sur le suivi statique — certains écrans ne sont atteints que
    # par des registres ou des imports différés dans les méthodes.
    for pkg in ("core", "ui", "codegen", "scripting", "plugins"):
        cmd.append(f"--include-package={pkg}")
    cmd.append("--include-module=window")

    # Bindings Qt concurrents : qtpy (via qtawesome) les teste en
    # try/except. Sans ça, une machine de dev qui a PySide6 installé le
    # ferait compiler dans la distribution.
    for mod in ("PySide6", "PySide2", "PyQt5", "shiboken6", "tkinter"):
        cmd.append(f"--nofollow-import-to={mod}")

    # ── Données ───────────────────────────────────────────────────
    # La disposition doit reproduire l'arborescence des sources : les
    # modules résolvent leurs données via Path(__file__).parent, et Nuitka
    # donne aux modules compilés un __file__ cohérent dans la distribution.

    # runtime/ — sources C du moteur (Makefile + include/*.h). Emporte aussi
    # runtime/LICENSE (zlib), qui doit voyager avec le moteur : c'est lui qui
    # répond à « ai-je le droit de vendre mon jeu ? ».
    cmd.append(f"--include-data-dir={REPO_ROOT / 'runtime'}=runtime")

    # Licence et notices tierces. Ce n'est pas de la courtoisie : la GPL de
    # l'éditeur et la LGPL de Qt exigent toutes deux que ces textes ACCOMPAGNENT
    # le binaire distribué. Les laisser dans le dépôt ne remplit pas
    # l'obligation — l'utilisateur d'un ZIP portable n'a que ce dossier.
    for notice in ("LICENSE", "THIRD-PARTY-NOTICES.md"):
        cmd.append(f"--include-data-files={REPO_ROOT / notice}={notice}")

    # plugins/ — chargés par importlib.util.spec_from_file_location, donc
    # ils doivent exister comme .py REELS sur disque, pas seulement compilés.
    #
    # Surtout pas --include-data-dir ici : cette option ne copie que les
    # fichiers *non-code* et ignore silencieusement les .py (elle se contente
    # d'un « No data files in directory » dans le log). Le dossier plugins/
    # se retrouvait entièrement absent de la distribution. --include-raw-dir
    # copie le dossier verbatim, .py compris — et exige une cible '=', que
    # son propre --help omet de mentionner.
    cmd.append(f"--include-raw-dir={staged_plugins_path(output_dir)}=plugins")

    # Référence de l'API de scripting (scripting/api_reference.py la lit).
    cmd.append(
        f"--include-data-files={EDITOR_DIR / 'scripting' / 'api_reference.json'}"
        f"=scripting/api_reference.json"
    )

    # Illustrations SVG (icône de fenêtre, mascotte du bouton Build) : lues par chemin.
    cmd.append(
        f"--include-data-dir={EDITOR_DIR / 'ui' / 'common' / 'CustomIcons'}"
        f"=ui/common/CustomIcons"
    )

    # Catalogue des notices (ui/common/notice.py le lit par Path(__file__)).
    # `--include-package=ui` n'embarque que du code : sans ce dossier, CHAQUE
    # message informatif de l'éditeur retombe sur sa clé (« ui.text.footprint_bg »
    # affiché tel quel). Les sides de langue partiront d'ici aussi (v0.11).
    cmd.append(
        f"--include-data-dir={EDITOR_DIR / 'ui' / 'common' / 'notices'}"
        f"=ui/common/notices"
    )

    # Catalogue des libellés (ui/common/labels.py le lit par Path(__file__)), frère
    # des notices. Sans ce dossier, l'interface entière s'affiche en clés brutes
    # (« home.create_project » au lieu du bouton) : `--include-package=ui`
    # n'embarque que du code.
    cmd.append(
        f"--include-data-dir={EDITOR_DIR / 'ui' / 'common' / 'labels'}"
        f"=ui/common/labels"
    )

    # Starter local : les palettes initiales doivent exister dans une version
    # distribuée aussi, pas seulement depuis un checkout de développement.
    cmd.append(
        f"--include-data-dir={EDITOR_DIR / 'project_starters'}=project_starters"
    )

    # Les flèches ▲▼ des QSpinBox venaient d'assets PNG livrés ici ; elles
    # sortent maintenant de qtawesome comme le reste des icônes (ui.common.
    # icons.qss_image les rend au démarrage dans un cache temporaire).

    # Les fontes d'icônes de qtawesome sont couvertes par une règle interne
    # de Nuitka ; un --include-package-data=qtawesome explicite ferait
    # doublon et produirait 24 avertissements dans le log.

    # ── Métadonnées / apparence ───────────────────────────────────
    # COMPANY doit rester aligné avec !define PUBLISHER dans
    # packaging/windows/installer.nsi.
    num = numeric_version(version)
    cmd += [
        f"--product-name={APP_NAME}",
        f"--file-description={APP_NAME}",
        f"--company-name={COMPANY}",
        f"--product-version={num}",
        f"--file-version={num}",
    ]
    if IS_WINDOWS:
        cmd.append("--windows-console-mode=disable")
        cmd.append(f"--windows-icon-from-ico={REPO_ROOT / 'packaging' / 'icon.ico'}")
    else:
        cmd.append(f"--linux-icon={REPO_ROOT / 'packaging' / 'icon.png'}")

    cmd.append(str(EDITOR_DIR / "main.py"))
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser(description=f"Build Nuitka de {APP_NAME}")
    ap.add_argument("--version", default=None,
                    help="version annoncée (tag de release) : doit égaler "
                         f"APP_VERSION ({APP.APP_VERSION}) ; par défaut, elle")
    ap.add_argument("--print-version", action="store_true",
                    help="affiche APP_VERSION et sort (job `version` de la CI)")
    ap.add_argument("--output-dir", default="build-out", type=Path,
                    help="dossier de sortie du build")
    ap.add_argument("--dry-run", action="store_true",
                    help="affiche la commande sans compiler")
    args = ap.parse_args()

    if args.print_version:
        print(APP.APP_VERSION)
        return 0
    version = args.version or APP.APP_VERSION
    if version.lstrip("v") != APP.APP_VERSION:
        print(f"!! la version demandée ({version}) n'est pas celle du dépôt "
              f"({APP.APP_VERSION}, editor/core/app_info.py) : changez l'une ou "
              f"l'autre avant de publier.", file=sys.stderr)
        return 2

    output_dir = args.output_dir.resolve()
    cmd = build_command(version, output_dir)

    print("$ " + " ".join(f'"{c}"' if " " in c else c for c in cmd), flush=True)
    if args.dry_run:
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    stage_plugins(output_dir)
    try:
        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    finally:
        shutil.rmtree(output_dir / "_staging", ignore_errors=True)

    # Nuitka nomme le dossier d'après le script principal (main.dist) —
    # on le renomme pour que la CI et le .nsi aient un chemin stable.
    produced = output_dir / "main.dist"
    final = output_dir / APP_NAME
    if not produced.is_dir():
        print(f"!! dossier attendu introuvable : {produced}", file=sys.stderr)
        return 1
    if final.exists():
        shutil.rmtree(final)
    produced.rename(final)

    exe = final / APP_EXE
    if not exe.exists():
        print(f"!! exécutable introuvable : {exe}", file=sys.stderr)
        return 1

    print(f"\nDistribution : {final}")
    print(f"Exécutable   : {exe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
