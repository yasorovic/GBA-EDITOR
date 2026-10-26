"""tools/run_pool_ingame.py — joue le scénario de `Project Test/PoolIngame` dans mGBA et rend son verdict.

    python tools/run_pool_ingame.py [--project PoolIngame|PoolPlaced] [--mgba CHEMIN] [--seconds 15]

Copie le projet dans un dossier temporaire (le build ne touche jamais le projet source), le construit comme
l'éditeur, lance `mgba-sdl -l 8` pendant quelques secondes, puis lit les lignes PASS / FAIL que le scénario
(`assets/scripts/Tests.lua`) écrit dans le log. Code de sortie 0 si tout passe, 1 sinon.

Le scénario couvre le pool partagé : un boss né qui perd un bras, des spawns en rafale jusqu'au refus, une
référence conservée qui devient nulle, la libération d'un groupe, un blocage entre acteurs nés, un modèle
affine né au-delà des 32 matrices. Il ne couvre PAS l'interaction (aucune entrée manette en ligne de commande)
ni le rendu visuel de la rotation.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "editor"))

MGBA_PAR_DEFAUT = r"C:\Program Files\mGBA\mgba-sdl.exe"


def construire(projet: Path) -> bool:
    from codegen import BuildWorker
    from core.project import Project
    from core.toolchain import Toolchain

    ouvrier = BuildWorker(Project.open(projet), Toolchain())
    ouvrier._step_launch_mgba = lambda _p: True          # on lance mGBA nous-mêmes
    verdict = {}
    ouvrier.on("error_line", lambda ligne: print("  ERR", ligne))
    ouvrier.on("finished", lambda ok: verdict.setdefault("ok", ok))
    ouvrier.run()
    return bool(verdict.get("ok"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", default="PoolIngame", help="dossier de Project Test à jouer (PoolIngame, PoolPlaced)")
    ap.add_argument("--mgba", default=MGBA_PAR_DEFAUT)
    ap.add_argument("--seconds", type=int, default=15)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="pool_ingame_") as tmp:
        copie = Path(tmp) / args.project
        shutil.copytree(ROOT / "Project Test" / args.project, copie, ignore=shutil.ignore_patterns("build"))
        if not construire(copie):
            print("Build en échec.")
            return 1
        try:
            sortie = subprocess.run([args.mgba, "-l", "8", str(copie / "build" / "rom.gba")], capture_output=True,
                                    text=True, timeout=args.seconds).stdout
        except subprocess.TimeoutExpired as fin:       # attendu : l'émulateur ne s'arrête pas tout seul
            sortie = (fin.stdout or b"").decode("utf-8", "replace") if isinstance(fin.stdout, bytes) else (fin.stdout or "")
    lignes = [ligne.split("GBA Debug: ", 1)[1] for ligne in sortie.splitlines() if "GBA Debug: " in ligne]
    verdicts = [l for l in lignes if l.startswith(("PASS ", "FAIL "))]
    for ligne in verdicts:
        print(ligne)
    echecs = [l for l in verdicts if l.startswith("FAIL ")]
    fini = any(l == "FIN" for l in lignes)
    print(f"\n{len(verdicts) - len(echecs)} réussis, {len(echecs)} échoués" + ("" if fini else " — le scénario n'a pas fini (délai trop court ?)"))
    return 0 if verdicts and not echecs and fini else 1


if __name__ == "__main__":
    raise SystemExit(main())
