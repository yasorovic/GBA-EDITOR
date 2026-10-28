"""tools/run_perf_bench.py — mesure le coût CPU des fonctions et des patrons de l'API Lua dans mGBA.

    python tools/run_perf_bench.py [--mgba CHEMIN] [--seconds 22] [--output FICHIER.json]

Copie `Project Test/PerfBench` dans un dossier temporaire, le construit comme l'éditeur (build debug, le seul qui
porte le chronomètre `frame us=`), lance `mgba-sdl -l 8`, puis lit le log. Le scénario (`assets/scripts/Bench.lua`) joue des
phases de 70 images et écrit "PHASE <nom> <n>" au début de chacune ; le runtime écrit "frame us=... oam=..." à chaque image.

Le coût d'une phase est la médiane de ses durées d'image, sans les premières (pose des acteurs, mise en route). Le surcoût
est la différence avec la phase "vide" : la part fixe du build debug (journal, comptage OAM) s'y retrouve et s'annule. Le coût
par instance (ou par appel) est ce surcoût divisé par n. Mesuré sous mGBA (BIOS émulé) : une comparaison entre patrons, pas
une durée promise sur console.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "editor"))

MGBA_PAR_DEFAUT = r"C:\Program Files\mGBA\mgba-sdl.exe"
SORTIE_PAR_DEFAUT = ROOT / "internal" / "development" / "perf_bench.json"
IMAGE_US = 16743                # une image GBA à 59,7275 Hz
IMAGES_IGNOREES = 10            # pose des acteurs et mise en route, au début de chaque phase
ECHANTILLONS_MIN = 20

_PHASE = re.compile(r"^PHASE (\S+) (\d+)$")
_IMAGE = re.compile(r"^frame us=(\d+) oam=\d+$")        # une ligne coupée par la fin du tampon est écartée


def analyser(lignes: list[str]) -> dict:
    """Range les durées d'image par phase et calcule surcoût et coût par instance. `lignes` : les messages du log."""
    phases: list[dict] = []
    for ligne in lignes:
        m = _PHASE.match(ligne)
        if m:
            phases.append({"name": m.group(1), "n": int(m.group(2)), "frames": []})
            continue
        m = _IMAGE.match(ligne)
        if m and phases:
            phases[-1]["frames"].append(int(m.group(1)))

    mesures = []
    for ph in phases:
        echantillons = ph["frames"][IMAGES_IGNOREES:]
        if ph["name"] == "fin" or len(echantillons) < ECHANTILLONS_MIN:
            continue
        mesures.append({"name": ph["name"], "n": ph["n"], "samples": len(echantillons),
                        "median_us": statistics.median(echantillons), "min_us": min(echantillons), "max_us": max(echantillons)})

    vide = next((m for m in mesures if m["name"] == "vide"), None)
    if vide is None:
        raise ValueError("phase 'vide' absente : pas de ligne de base")
    base = vide["median_us"]
    for m in mesures:
        if m is vide:
            continue
        m["overhead_us"] = m["median_us"] - base
        m["per_unit_us"] = round(m["overhead_us"] / m["n"], 2) if m["n"] else None
    return {"frame_us": IMAGE_US, "baseline_us": base, "phases": mesures}


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


def jouer(rom: Path, mgba: str, secondes: int) -> list[str]:
    try:
        sortie = subprocess.run([mgba, "-l", "8", str(rom)], capture_output=True, text=True, timeout=secondes).stdout
    except subprocess.TimeoutExpired as fin:       # attendu : l'émulateur ne s'arrête pas tout seul
        sortie = fin.stdout.decode("utf-8", "replace") if isinstance(fin.stdout, bytes) else (fin.stdout or "")
    return [l.split("GBA Debug: ", 1)[1] for l in sortie.splitlines() if "GBA Debug: " in l]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mgba", default=MGBA_PAR_DEFAUT)
    ap.add_argument("--seconds", type=int, default=22)
    ap.add_argument("--output", type=Path, default=SORTIE_PAR_DEFAUT)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="perf_bench_") as tmp:
        copie = Path(tmp) / "PerfBench"
        shutil.copytree(ROOT / "Project Test" / "PerfBench", copie, ignore=shutil.ignore_patterns("build"))
        if not construire(copie):
            print("Build en échec.")
            return 1
        lignes = jouer(copie / "build" / "rom.gba", args.mgba, args.seconds)

    try:
        resultat = analyser(lignes)
    except ValueError as err:
        print(f"Mesure inutilisable : {err} (délai trop court, ou mGBA introuvable ?)")
        return 1
    resultat.update({"emulator": "mGBA, BIOS émulé", "build": "debug"})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(resultat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"ligne de base (scène vide) : {resultat['baseline_us']:.0f} µs sur {IMAGE_US}")
    print(f"{'phase':26} {'n':>4} {'médiane µs':>11} {'surcoût µs':>11} {'µs / unité':>11}")
    for m in resultat["phases"]:
        if "overhead_us" in m:
            print(f"{m['name']:26} {m['n']:>4} {m['median_us']:>11.0f} {m['overhead_us']:>11.0f} {m['per_unit_us']:>11}")
    print(f"\nÉcrit dans {args.output}")
    attendues = {"balles_immobiles", "spinners_affines", "poursuite_directe", "poursuite_en_cache", "poursuite_un_quart",
                 "poursuite_manuelle", "parcours_get_i", "spawn_destroy", "count"}
    manquantes = attendues - {m["name"] for m in resultat["phases"]}
    if manquantes:
        print(f"Phases absentes ou trop courtes : {', '.join(sorted(manquantes))}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
