"""codegen/iwram_plan.py — quelles phases du tick vont en IWRAM.

Le moteur est compilé en Thumb et exécuté depuis la ROM de la cartouche, dont chaque accès coûte des états d'attente
(cf. `memory_timing_init`) ; l'IWRAM n'en a pas, et du code ARM y va encore plus vite (mesuré sous mGBA sur un banc de
30 sprites affines : 2,53 ms en ROM, 2,10 ms en Thumb dans l'IWRAM, 1,80 ms en ARM). Le tick d'une scène est découpé en
quatre phases (`TICK_PHASES`) ; chacune peut être placée seule dans la section `.iwram`, que le démarrage
(crt0) recopie de la ROM. Elle y reste : la place est la somme de tout ce qui est placé, pour toutes les scènes.

Pourquoi pas les « overlays » `.iwram0` à `.iwram9` de devkitARM, qui permettraient de ne loger que la scène en cours :
le script de lien (gba_cart.ld) ouvre `.iwram` par `*(.iwram .iwram*)`, dont le motif avale aussi `.iwram0`... avant que
l'OVERLAY ne les voie. Ils resteraient vides. Un script de lien maison les ferait marcher ; à faire si un jeu à plusieurs
grosses scènes déborde.

Le générateur choisit un plan de départ (tout en ARM, sauf la physique quand elle est grosse) ; ce module le dégrade quand la
place manque, d'après les tailles réelles lues dans `main.o`. Un mode vaut 2 (ARM dans l'IWRAM) ou 0 (reste en ROM, en
Thumb) ; le compilateur le reçoit par `-DBS_IWRAM_<scène>_<phase>=<mode>`.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

IWRAM_TOTAL = 32 * 1024
# La pile et ce que le jeu pourrait encore prendre : jamais mangés par le code placé. La pile descend depuis le haut de l'IWRAM
# (juste sous les piles d'interruption) ; 4 Ko couvrent l'appel d'un script depuis le tick avec de la marge.
IWRAM_STACK_RESERVE = 4 * 1024

ARM, ROM = 2, 0

# Les phases du tick d'une scène, dans l'ordre où elles s'exécutent (cf. `gen_scene_tick`).
TICK_PHASES = ("hooks", "physics", "late", "render")

# Au-delà de ce que ce texte C suppose de code, la physique (paires de collision déroulées) ne part pas en IWRAM d'office :
# elle y prendrait la place de tout le reste. La mesure réelle (ce module) tranche ensuite, mais ce départ évite de compiler
# deux fois les projets ordinaires. Calibré sur les projets de test : environ 5 octets de code ARM par caractère de C.
PHYSICS_IWRAM_CHARS = 3000

# Ce que vaut une phase en IWRAM, en valeur relative : l'affichage est parcouru pour chaque acteur à chaque image ; la
# physique pèse aussi (les paires de collision) ; les deux autres ne sont que des boucles d'appel vers des scripts restés en
# ROM. Quand la place manque, on retire la phase qui rend le MOINS par octet (valeur / taille) : la physique, énorme, avant
# l'affichage, et les deux petites boucles en dernier.
VALUE = {"render": 8, "physics": 4, "hooks": 1, "late": 1}

_MACRO = re.compile(r"^#define\s+BS_IWRAM_(\w+?)_(hooks|physics|late|render)\s+(\d)\s*(?:/\*.*)?$", re.M)
_SYMBOL = re.compile(r"^\S+\s+([0-9a-fA-F]+)\s+[tT]\s+scene_tick_(\w+?)_(hooks|physics|late|render)$", re.M)


def macro_name(scene_sym: str, phase: str) -> str:
    return f"BS_IWRAM_{scene_sym}_{phase}"


def read_modes(main_c: str) -> dict[tuple[str, str], int]:
    """Les modes que le générateur a écrits dans main.c : {(scène, phase): mode}."""
    return {(m.group(1), m.group(2)): int(m.group(3)) for m in _MACRO.finditer(main_c)}


def read_sizes(nm_output: str) -> dict[tuple[str, str], int]:
    """La taille compilée de chaque phase, d'après `nm -S main.o` : {(scène, phase): octets}."""
    return {(m.group(2), m.group(3)): int(m.group(1), 16) for m in _SYMBOL.finditer(nm_output)}


_IWRAM_START, _IWRAM_END = 0x03000000, 0x04000000
_SYMBOL_AT = re.compile(r"^([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+[tT]\s+scene_tick_(\w+?)_(hooks|physics|late|render)$", re.M)


def read_placed(nm_output: str) -> set[tuple[str, str]]:
    """Les phases que le lien a réellement posées en IWRAM, d'après `nm -S rom.elf` : {(scène, phase)} dont l'adresse
    tombe dans l'IWRAM. C'est le binaire qui répond, pas le plan."""
    return {(m.group(2), m.group(3)) for m in _SYMBOL_AT.finditer(nm_output)
            if _IWRAM_START <= int(m.group(1), 16) < _IWRAM_END}


@dataclass
class Plan:
    modes: dict[tuple[str, str], int]       # le mode retenu de chaque phase
    placed: int                             # octets de code placés en IWRAM
    budget: int                             # octets que le code placé a le droit de prendre
    dropped: list[tuple[str, str]]          # les phases renvoyées en ROM

    @property
    def changed(self) -> bool:
        return bool(self.dropped)


def make_plan(modes: dict[tuple[str, str], int], sizes: dict[tuple[str, str], int], static_bytes: int) -> Plan:
    """Dégrade `modes` jusqu'à ce que le code placé tienne dans ce que l'IWRAM laisse libre.

    `sizes` : les tailles AU MODE ACTUEL (celles de `main.o`). `static_bytes` : l'IWRAM prise par le reste (données
    initialisées, .bss, bibliothèques), code placé exclu. On retire la phase qui rend le moins par octet (cf. `VALUE`)
    jusqu'à ce que ça tienne."""
    modes = dict(modes)
    budget = max(0, IWRAM_TOTAL - IWRAM_STACK_RESERVE - static_bytes)
    dropped: list[tuple[str, str]] = []

    def placed() -> int:
        return sum(sizes.get(key, 0) for key, mode in modes.items() if mode != ROM)

    while placed() > budget:
        candidates = [key for key, mode in modes.items() if mode != ROM]
        if not candidates:
            break
        victim = min(candidates, key=lambda key: VALUE[key[1]] / max(1, sizes.get(key, 0)))
        modes[victim] = ROM
        dropped.append(victim)
    return Plan(modes, placed(), budget, dropped)


# Ce que les bibliothèques (libgba, maxmod) prennent en IWRAM et qu'on ne voit pas sans lien : une estimation, que le contrôle
# après lien remplace par la mesure.
LIBRARIES_IWRAM_ESTIMATE = 3 * 1024


def static_from_objects(size_outputs: list[str], placed: int) -> int:
    """L'IWRAM prise par le reste du jeu quand le lien a échoué : les `.bss`, `.data` et `.iwram` des objets (`size -A`, un
    texte par objet), moins le code placé que `main.o` y met déjà, plus l'estimation des bibliothèques."""
    total = 0
    for text in size_outputs:
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] in (".bss", ".data", ".iwram") and parts[1].isdigit():
                total += int(parts[1])
    return max(0, total - placed) + LIBRARIES_IWRAM_ESTIMATE


def overflowed(link_output: str) -> bool:
    """Le lien a-t-il échoué parce que l'IWRAM déborde ?"""
    return bool(re.search(r"region .iwram. overflowed|not within region .iwram.", link_output))


def dropped_cflags(dropped: list[tuple[str, str]]) -> str:
    return " ".join(f"-D{macro_name(scene, phase)}={ROM}" for scene, phase in dropped)


def cflags(plan: Plan) -> str:
    """Les `-D` qui imposent le plan au compilateur : seulement les phases renvoyées en ROM."""
    return dropped_cflags(plan.dropped)


# ── Mémoire du plan entre deux builds ────────────────────────────────────────────────────────────────────────────────
# Un plan mesuré n'est valable que pour le C qu'il a mesuré : l'empreinte couvre tout ce que `make` compile.

def fingerprint(directories: list[Path], salt: str = "") -> str:
    """Empreinte du C que `make` compile (`.c`, `.h`, `.s` des dossiers donnés) et de `salt` (options, Makefile)."""
    digest = hashlib.sha1(salt.encode("utf-8"))
    for directory in directories:
        for path in sorted(directory.glob("*")):
            if path.suffix in (".c", ".h", ".s") and path.is_file():
                digest.update(path.name.encode("utf-8"))
                digest.update(path.read_bytes())
    return digest.hexdigest()


def load_memo(path: Path, current: str) -> list[tuple[str, str]] | None:
    """Les phases renvoyées en ROM par le dernier build qui tenait, ou None si rien n'est mémorisé pour cette empreinte."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["fingerprint"] != current:
            return None
        return [(scene, phase) for scene, phase in data["dropped"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_memo(path: Path, current: str, dropped: list[tuple[str, str]]) -> None:
    path.write_text(json.dumps({"fingerprint": current, "dropped": [list(key) for key in dropped]}), encoding="utf-8")


def iwram_macros(sym: str, phases: dict[str, list[str]]) -> list[str]:
    """Pour chaque phase, le mode de départ et l'attribut qui en découle. Le build peut renvoyer une phase en ROM
    par `-DBS_IWRAM_<scène>_<phase>=0` quand la place manque (cf. `iwram_plan`)."""
    out: list[str] = []
    for name in TICK_PHASES:
        text = "".join(phases[name])
        mode = ROM if (name == "physics" and len(text) > PHYSICS_IWRAM_CHARS) else ARM
        mac = macro_name(sym, name)
        out += [f"#ifndef {mac}",
                f"#define {mac} {mode}   /* 2 = ARM in IWRAM, 0 = ROM */",
                "#endif",
                f"#if {mac} == 2",
                f'#define BS_ATTR_{sym}_{name} __attribute__((noinline, section(".iwram"), target("arm"), long_call))',
                "#else",
                f"#define BS_ATTR_{sym}_{name}",
                "#endif"]
    return out + [""]
