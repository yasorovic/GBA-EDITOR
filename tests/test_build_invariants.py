"""Des invariants du journal, vérifiés sur des pannes en masse (chantier « La fiabilité du journal
de build », tranche 4).

Une matrice de pannes écrites à la main ne couvre que ce qu'on a pensé à écrire. Ici, on abîme un à un
les fichiers d'une copie de la démo — tronqué, vidé, remplacé par du bruit, clé JSON retirée, valeur du
mauvais type, jeton de script supprimé — et on exige, pour CHAQUE panne, ce qu'un journal fiable doit
toujours à l'auteur :

- I1. aucun « internal error » : une panne prévisible n'est pas un bogue de l'éditeur ;
- I2. un build en échec porte au moins une erreur (ni échec muet, ni succès avec erreur) ;
- I3. aucun message en français, aucun chemin du projet recopié, aucune trace Python brute ;
- I4. un build en échec NOMME le fichier abîmé : sans cela l'auteur ne sait pas où regarder ;
- I5. un fichier dont les octets sont cassés (tronqué, vidé, bruit) n'est jamais ignoré SANS UN MOT :
  réussi ou non, le build le nomme dans un avertissement ou une erreur.

Le projet de la démo est copié une fois ; chaque cas abîme un fichier puis le restaure. Par défaut, un
fichier reçoit UNE panne, tournante et déterministe (une trentaine de builds) ; `FUZZ_FULL=1` les joue
toutes. Un cas qui viole un invariant sans pouvoir être corrigé se range dans `KNOWN_GAPS`, avec sa raison.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import zlib
from pathlib import Path

import pytest

from codegen import BuildWorker
from core.project import Project
from core.toolchain import Toolchain

DEMO = Path(__file__).resolve().parent.parent / "Project Demo" / "PongAdvanced"
pytestmark = [pytest.mark.slow,
              pytest.mark.skipif(not DEMO.exists(), reason="projet de démo absent"),
              pytest.mark.skipif(not Toolchain().devkitpro_ok, reason="devkitPro absent : le build ne peut pas tourner")]

# Les fichiers que l'on abîme (relatifs à la racine de la démo). Les gros lots homogènes
# (105 musiques, 20 palettes) sont représentés par un seul fichier.
FILES = [
    "PongAdvanced.project",
    "project/scenes/SCR_Arena.json", "project/scenes/SCR_Main.json", "project/scenes/SCR_Victory.json",
    "project/texts.json", "project/texts_jap.json", "project/variables.json",
    "project/ui_layouts/SCR_Main.json", "project/ui_layouts/SCR_Victory.json",
    "project/fonts_assets/Font8x8 Latin.json", "project/fonts_assets/Misaki Gothic 8.json",
    "project/music_boxes/musics.json",
    "assets/scripts/Ball.lua", "assets/scripts/PaddleAuto.lua", "assets/scripts/PaddlePlayer.lua",
    "assets/scripts/SCR_Arena.lua", "assets/scripts/SCR_Main.lua", "assets/scripts/SCR_Victory.lua",
    "assets/sprites/Ball.json", "assets/sprites/Ball.png", "assets/sprites/Paddle.json",
    "assets/sprites/Paddle.png",
    "assets/backgrounds/Background.json", "assets/backgrounds/Background.png",
    "assets/fonts/Font8x8 Latin.json", "assets/fonts/font8x8-latin.png",
    "assets/fonts/misaki-gothic.json",
    "assets/palettes/_Microsoft Windows 16.json", "assets/palettes/_Microsoft Windows 16.hex",
    "assets/music/Claimed DX.mod", "assets/music/Claimed DX.json",
]

# (fichier, panne) → pourquoi l'invariant n'est pas tenu. Vide, c'est l'état voulu ; une entrée est une
# dette datée, pas une habitude.
KNOWN_GAPS: dict[tuple[str, str], str] = {}


# ── Les pannes ────────────────────────────────────────────────────


def _leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, path + (key,))
    elif isinstance(node, list):
        for i, value in enumerate(node[:6]):
            yield from _leaves(value, path + (i,))
    else:
        yield path, node


def _walk(node, path):
    for step in path:
        node = node[step]
    return node


def _truncate_half(data: bytes, rng) -> bytes:
    return data[: len(data) // 2]


def _empty(data: bytes, rng) -> bytes:
    return b""


def _noise(data: bytes, rng) -> bytes:
    return bytes(rng.randrange(256) for _ in range(min(max(len(data), 1), 64)))


def _drop_key(data: bytes, rng):
    doc = json.loads(data.decode("utf-8"))
    paths = [p for p, _ in _leaves(doc) if p and isinstance(p[-1], str)]
    if not paths:
        return None
    path = rng.choice(paths)
    del _walk(doc, path[:-1])[path[-1]]
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


def _wrong_type(data: bytes, rng):
    doc = json.loads(data.decode("utf-8"))
    leaves = [(p, v) for p, v in _leaves(doc) if p]
    if not leaves:
        return None
    path, value = rng.choice(leaves)
    swap = {str: 0, int: "x", float: "x", bool: "x", type(None): "x"}.get(type(value), None)
    _walk(doc, path[:-1])[path[-1]] = swap
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


def _drop_token(data: bytes, rng):
    lines = data.decode("utf-8").split("\n")
    code = [i for i, l in enumerate(lines) if l.strip() and not l.strip().startswith("--")]
    i = rng.choice(code)
    tokens = list(re.finditer(r"[A-Za-z_]\w*|\S", lines[i]))
    if not tokens:
        return None
    m = rng.choice(tokens)
    lines[i] = lines[i][: m.start()] + lines[i][m.end():]
    return "\n".join(lines).encode("utf-8")


def _stray_semicolon(data: bytes, rng):
    lines = data.decode("utf-8").split("\n")
    code = [i for i, l in enumerate(lines) if l.strip() and not l.strip().startswith("--")]
    i = rng.choice(code)
    lines[i] = lines[i].rstrip() + "; ADFZ"
    return "\n".join(lines).encode("utf-8")


COMMON = {"truncate": _truncate_half, "empty": _empty, "noise": _noise}
BY_KIND = {
    ".json": {**COMMON, "drop_key": _drop_key, "wrong_type": _wrong_type},
    ".project": {**COMMON, "drop_key": _drop_key, "wrong_type": _wrong_type},
    ".lua": {**COMMON, "drop_token": _drop_token, "stray_semicolon": _stray_semicolon},
}


def _mutators(file: str) -> dict:
    return BY_KIND.get(Path(file).suffix, COMMON)


def _cases():
    full = bool(os.environ.get("FUZZ_FULL"))
    for file in FILES:
        names = sorted(_mutators(file))
        # tournant et stable : le même fichier reçoit toujours la même panne par défaut
        chosen = names if full else [names[zlib.crc32(file.encode()) % len(names)]]
        for name in chosen:
            yield pytest.param(file, name, id=f"{file}::{name}")


# ── Le projet et le build ─────────────────────────────────────────


@pytest.fixture(autouse=True)
def _own_crash_log(tmp_path, monkeypatch):
    """Les pannes provoquées ici sont voulues : elles n'ont pas à remplir le vrai `crash.log`."""
    from core import crash_log
    monkeypatch.setattr(crash_log, "LOG_FILE", tmp_path / "crash.log")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("fuzz") / "Demo"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns("build"))
    return root


def _run(root: Path):
    """(refus, diagnostics, verdict) : `refus` est le message d'un projet qui refuse de s'ouvrir."""
    from core.project import ProjectFileError, ProjectManifestError, ProjectNotFoundError
    try:
        project = Project.open(root)
    except (ProjectFileError, ProjectManifestError, ProjectNotFoundError) as exc:
        return str(exc), [], None
    worker = BuildWorker(project, Toolchain())
    worker._step_make = lambda _p: True
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()
    return None, diagnostics, verdict[-1]


# ── Les invariants ────────────────────────────────────────────────

_ACCENTS = re.compile(r"[éèêàâçùûôîï«»]")
_FRENCH_WORDS = re.compile(r"\b(le|la|les|une|des|du|est|pas|pour|dans|sur|avec|aucun|aucune|introuvable)\b",
                           re.IGNORECASE)
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'|`[^`]*`")
_PYTHON_NOISE = re.compile(r"Traceback|<class |object at 0x|\bNoneType\b")


def _is_french(text: str) -> bool:
    """Sans les passages cités : un nom d'asset ou une clé de texte de l'auteur peut l'être."""
    bare = _QUOTED.sub("", text)
    return bool(_ACCENTS.search(bare) or _FRENCH_WORDS.search(bare))


BROKEN_BYTES = {"truncate", "empty", "noise"}
# Couper ces formats donne un fichier ENCORE VALIDE, seulement plus court : un script coupé entre deux
# fonctions, une palette à moins de couleurs, un module à moins de motifs. Rien n'y est « cassé »
# au sens de l'I5 ; seuls `empty` et `noise` le sont.
STILL_VALID_WHEN_CUT = {".lua", ".hex", ".mod"}


def _violations(root: Path, file: str, fault: str, refusal, diagnostics, verdict) -> list[str]:
    out: list[str] = []
    messages = [d.console_line() for d in diagnostics]
    if refusal is not None:
        messages.append(refusal)
    errors = [d for d in diagnostics if d.level == "error"]

    # I1
    out += [f"I1 internal error: {m}" for m in messages if "internal error" in m]
    # I2
    if verdict is False and not errors:
        out.append("I2 the build failed without any error diagnostic")
    if verdict is True and errors:
        out.append("I2 the build succeeded although it reported errors")
    # I3
    for m in messages:
        if _is_french(m):
            out.append(f"I3 not English: {m[:140]}")
        if str(root) in m or str(root.parent) in m:
            out.append(f"I3 copies the project path: {m[:140]}")
        if _PYTHON_NOISE.search(m):
            out.append(f"I3 raw Python noise: {m[:140]}")
    # I4 : un échec nomme le fichier abîmé (son nom, son radical, ou — pour le manifeste — le projet)
    failed = refusal is not None or verdict is False
    if failed:
        path = Path(file)
        needles = {path.name, path.stem}
        named = any(any(n in m for n in needles) or d_file in needles
                    for m, d_file in [(d.console_line(), d.file) for d in errors]
                    + ([(refusal, "")] if refusal else []))
        if not named:
            out.append(f"I4 no error names {path.name}: "
                       + " | ".join(m[:90] for m in [d.console_line() for d in errors][:3] or [refusal or ""]))
    # I5 : octets cassés, build réussi — le fichier a été ignoré, il doit au moins l'être à voix haute
    cut_but_valid = fault == "truncate" and Path(file).suffix in STILL_VALID_WHEN_CUT
    if not failed and fault in BROKEN_BYTES and not cut_but_valid:
        path = Path(file)
        needles = {path.name, path.stem}
        if not any(any(n in d.console_line() for n in needles) or d.file in needles for d in diagnostics):
            out.append(f"I5 {path.name} is broken ({fault}) and the build ignored it without a word")
    return out


def test_la_demo_saine_ne_produit_aucune_erreur(demo):
    """Le témoin : sans panne, le même chemin ne dit rien d'anormal. Un contrôle trop zélé (une
    police vectorielle prise pour une planche PNG) fait échouer TOUS les cas ci-dessous pour une
    seule raison, et ce test la désigne."""
    refusal, diagnostics, verdict = _run(demo)
    assert refusal is None
    assert verdict is True
    assert [d.console_line() for d in diagnostics if d.level == "error"] == []


@pytest.mark.parametrize("file, fault", list(_cases()))
def test_une_panne_laisse_un_journal_fiable(demo, file, fault):
    path = demo / file
    original = path.read_bytes()
    mutated = _mutators(file)[fault](original, random.Random(f"{file}:{fault}"))
    if mutated is None or mutated == original:
        pytest.skip("la panne ne s'applique pas à ce fichier")
    path.write_bytes(mutated)
    try:
        refusal, diagnostics, verdict = _run(demo)
    finally:
        path.write_bytes(original)

    violations = _violations(demo, file, fault, refusal, diagnostics, verdict)
    if (file, fault) in KNOWN_GAPS:
        pytest.xfail(KNOWN_GAPS[(file, fault)])
    assert not violations, f"{file} / {fault}:\n  " + "\n  ".join(violations)
