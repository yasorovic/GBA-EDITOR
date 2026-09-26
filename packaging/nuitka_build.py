#!/usr/bin/env python3
"""
Build Nuitka de GBA Editor — Windows et Linux.

Une seule définition de la commande de build, utilisée par la CI comme en
local : c'est ce qui évite que les options divergent entre les deux et
qu'un problème n'apparaisse qu'au moment de publier.

Usage :
    python packaging/nuitka_build.py --version 0.3.2 --output-dir build-out

Produit un dossier <output-dir>/GBAEditor/ contenant l'exécutable et ses
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
import re
import shutil
import subprocess
import sys
from pathlib import Path

COMPANY = "Yasor Rovic"

REPO_ROOT = Path(__file__).resolve().parent.parent
EDITOR_DIR = REPO_ROOT / "editor"
IS_WINDOWS = sys.platform.startswith("win")


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
        "--output-filename=" + ("GBA Editor.exe" if IS_WINDOWS else "GBA Editor"),
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

    # Catalogue des notices (ui/common/notice.py le lit par Path(__file__)).
    # `--include-package=ui` n'embarque que du code : sans ce dossier, CHAQUE
    # message informatif de l'éditeur retombe sur sa clé (« ui.text.footprint_bg »
    # affiché tel quel). Les sides de langue partiront d'ici aussi (v0.11).
    cmd.append(
        f"--include-data-dir={EDITOR_DIR / 'ui' / 'common' / 'notices'}"
        f"=ui/common/notices"
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
        "--product-name=GBA Editor",
        "--file-description=GBA Editor",
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
    ap = argparse.ArgumentParser(description="Build Nuitka de GBA Editor")
    ap.add_argument("--version", default="0.0.0",
                    help="version de la release (tag), pour les métadonnées")
    ap.add_argument("--output-dir", default="build-out", type=Path,
                    help="dossier de sortie du build")
    ap.add_argument("--dry-run", action="store_true",
                    help="affiche la commande sans compiler")
    args = ap.parse_args()

    output_dir = args.output_dir.resolve()
    cmd = build_command(args.version, output_dir)

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
    final = output_dir / "GBAEditor"
    if not produced.is_dir():
        print(f"!! dossier attendu introuvable : {produced}", file=sys.stderr)
        return 1
    if final.exists():
        shutil.rmtree(final)
    produced.rename(final)

    exe = final / ("GBA Editor.exe" if IS_WINDOWS else "GBA Editor")
    if not exe.exists():
        print(f"!! exécutable introuvable : {exe}", file=sys.stderr)
        return 1

    print(f"\nDistribution : {final}")
    print(f"Exécutable   : {exe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
