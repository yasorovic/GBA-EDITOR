"""
codegen/rom_report.py — Ce que la ROM contient, mesuré sur les artefacts du build.

Tout ici est LU, jamais estimé. C'est la règle de la maison (ROADMAP v0.14,
« le budget se mesure sur la CIBLE »), et elle a une raison mesurée : la taille
des fichiers source prédit **douze fois trop** le coût ROM d'un module tracker,
mmutil mutualisant les échantillons entre les modules d'un même soundbank.

Trois sources, toutes produites par le build :

    rom.elf        sections (`size -A`) → ce qui part réellement en ROM
    rom.elf        symboles (`nm --print-size`) → l'attribution par asset
    soundbank.bin  sa table d'offsets → le poids de chaque son, un par un

Le total affiché reste celui du fichier `.gba` ; ce que l'attribution ne sait
pas nommer apparaît en « reste », jamais absorbé dans une catégorie voisine.
Une barre qui boucle à 100 % en cachant son ignorance ment là où on la consulte.
"""
from __future__ import annotations

import re
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Capacités de cartouche ────────────────────────────────────────────
# Les tailles réellement produites en cartouche masquée sur GBA. L'espace
# d'adressage de la console s'arrête à 32 Mio.
CARTRIDGE_SIZES_MIB = (4, 8, 16, 32)
DEFAULT_CARTRIDGE_MIB = 4


# ── Catégories ────────────────────────────────────────────────────────
# L'ordre est celui de l'affichage : les assets d'abord (ce sur quoi l'auteur
# peut agir), le moteur ensuite, le reste en dernier.
CATEGORY_ORDER = (
    "Audio", "Polices", "Fonds", "Sprites", "Palettes", "Textes",
    "Interface", "Tables de données", "Collision", "Code", "Reste",
)

# Chaque règle est (catégorie, motif). Les motifs suivent les générateurs de
# noms (`c_names.sym`, `grit_conversion.bg_layer_sym`, `font_emit`,
# `main_gen`) — c'est là qu'il faut revenir si un symbole se met à tomber
# dans « Reste ».
_SYMBOL_RULES: tuple[tuple[str, re.Pattern], ...] = (
    # `g_fsub_*` = sous-ensemble de police réservé par une scène (font_emit) :
    # c'est de la police, même si le nom ne commence pas par `g_font_`.
    ("Polices",           re.compile(r"^g_font_|^g_fonts$|^g_fsub_")),
    ("Sprites",           re.compile(r"^sprite_.*(Tiles|Pal|Map)$")),
    ("Fonds",             re.compile(r"_bg\d+(Tiles|Map|Pal)$")),
    ("Palettes",          re.compile(r"^g_pal(ettes)?(_bg_|_obj_|$)")),
    ("Collision",         re.compile(r"^g_cmap_")),
    ("Textes",            re.compile(r"^g_text|^g_str")),
    ("Interface",         re.compile(r"^g_ui_")),
    ("Tables de données", re.compile(r"^g_data_|^data_table_")),
)

# Sections qui ne portent PAS d'assets : leur taille vient de `size -A`, qui
# fait autorité, plutôt que d'une somme de symboles — beaucoup de code de
# libgba et de la libc arrive en assembleur, sans directive `.size`, et une
# somme de symboles le sous-estimerait de plusieurs kilo-octets.
_ASSET_SECTION = ".rodata"
_NOT_IN_ROM = (".bss", ".sbss")

# Symboles qui n'ont PAS de taille dans l'ELF et dont on dérive le poids d'une
# borne à l'autre. `bin2s` produit de l'assembleur sans directive `.size` :
# sans ce rattrapage, l'attribution perd 81 % de la ROM de la démo — en
# silence, ce qui est le pire des deux.
_SPAN_SYMBOLS = (("Audio", "soundbank_bin", "soundbank_bin_end"),)

# Au-delà, ce n'est plus une donnée mais un marqueur de section du linker
# (`__iwram_top`, `__eheap_end`, `_stack` : jusqu'à 100 Mo annoncés).
_ABSURD_SIZE = 8 * 1024 * 1024


@dataclass
class SoundEntry:
    """Un son dans le soundbank, avec ce qu'il pèse réellement."""
    name: str                 # nom de la ressource, "" si non rapproché
    kind: str                 # "sfx" | "music"
    own_bytes: int            # ses données propres (échantillon, ou bloc MAS)
    shared_bytes: int = 0     # échantillons partagés (musiques seulement)
    shared_with: int = 0      # nombre d'autres pistes qui les partagent


@dataclass
class SoundbankReport:
    total: int
    header: int
    sfx_bytes: int
    music_data_bytes: int      # les blocs MAS
    music_sample_bytes: int    # les échantillons des modules, mutualisés
    entries: list[SoundEntry] = field(default_factory=list)


@dataclass
class RomReport:
    rom_bytes: int
    cartridge_bytes: int
    categories: dict[str, int]
    soundbank: Optional[SoundbankReport] = None
    # Mémoires de travail, mesurées sur le même build : données statiques placées
    # en EWRAM / IWRAM par le linker (la pile et le tas n'y sont pas).
    ewram_bytes: int = 0
    iwram_bytes: int = 0
    # Ce qui remplit l'IWRAM, pour l'infobulle : {section: octets} et les plus
    # gros symboles [(nom, octets)]. L'IWRAM est la mémoire dont la marge
    # protège la pile, donc celle dont on veut savoir « qu'est-ce qui occupe ? ».
    iwram_sections: dict[str, int] = field(default_factory=dict)
    iwram_top: list[tuple[str, int]] = field(default_factory=list)
    # Blocs de 2 Kio de VRAM BG occupés par scène (tuiles des fonds, maps,
    # glyphes), tels que l'allocateur les a posés à CE build (`VramLayout`).
    bg_vram_blocks: dict[str, int] = field(default_factory=dict)

    @property
    def over_capacity(self) -> bool:
        return self.rom_bytes > self.cartridge_bytes

    @property
    def fill_ratio(self) -> float:
        return self.rom_bytes / self.cartridge_bytes if self.cartridge_bytes else 0.0


# ── Lecture des artefacts ─────────────────────────────────────────────

def _run(tool: Path, args: list[str], elf: Path) -> Optional[str]:
    """Lance `tool args elf` DANS le dossier de l'ELF, avec son seul nom : les
    binutils sont des exécutables « ANSI », un dossier de projet hors de la page
    de code leur arrive en `?` et le rapport de poids disparaissait sans un mot."""
    try:
        proc = subprocess.run([str(tool)] + args + [elf.name], cwd=str(elf.parent),
                              capture_output=True, text=True, errors="replace")
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def read_symbols(nm: Path, elf: Path) -> dict[str, tuple[int, int, str]]:
    """{nom: (adresse, taille, type)} — taille 0 quand l'ELF n'en porte pas."""
    out = _run(nm, ["--print-size", "--radix=d"], elf)
    if out is None:
        return {}
    syms: dict[str, tuple[int, int, str]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4:
            addr, size, typ, name = parts
            syms[name] = (int(addr), int(size), typ)
        elif len(parts) == 3:
            addr, typ, name = parts
            if addr.isdigit():
                syms[name] = (int(addr), 0, typ)
    return syms


def read_sections(size_tool: Path, elf: Path) -> dict[str, int]:
    """{section: taille}, **sections chargées seulement**.

    `size -A` liste aussi `.debug_*`, `.comment` et `.ARM.attributes`, qui
    vivent dans l'ELF et ne partent JAMAIS en cartouche : 11 486 o sur la démo,
    soit exactement de quoi faire dépasser 100 % à une barre qui les compterait.
    Elles se reconnaissent à leur adresse nulle — une section non allouée n'a
    pas de place en mémoire.
    """
    out = _run(size_tool, ["-A", "-d"], elf)
    if out is None:
        return {}
    sections: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].startswith("."):
            try:
                size, addr = int(parts[1]), int(parts[2])
            except ValueError:
                continue
            if addr:
                sections[parts[0]] = size
    return sections


# Fenêtres d'adresses du matériel : le linker place chaque section d'après elles.
_EWRAM = (0x02000000, 256 * 1024)
_IWRAM = (0x03000000, 32 * 1024)


def read_ram_use(size_tool: Path, elf: Path) -> tuple[int, int, dict[str, int]]:
    """(EWRAM, IWRAM, sections de l'IWRAM) occupées par l'ELF, en octets.

    On classe par ADRESSE et non par nom de section : `.bss`, `.data`, `.iwram`,
    `.ewram`, `.sbss`… dépendent du script de link, l'adresse est ce que le
    matériel voit. Les sections de code placées en RAM (`.iwram`) comptent aussi."""
    out = _run(size_tool, ["-A", "-d"], elf)
    if out is None:
        return 0, 0, {}
    ewram = iwram = 0
    iwram_sections: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].startswith("."):
            try:
                size, addr = int(parts[1]), int(parts[2])
            except ValueError:
                continue
            if _EWRAM[0] <= addr < _EWRAM[0] + _EWRAM[1]:
                ewram += size
            elif _IWRAM[0] <= addr < _IWRAM[0] + _IWRAM[1]:
                iwram += size
                if size:
                    iwram_sections[parts[0]] = iwram_sections.get(parts[0], 0) + size
    return ewram, iwram, iwram_sections


def iwram_largest(symbols: dict[str, tuple[int, int, str]], count: int = 5) -> list[tuple[str, int]]:
    """Les `count` plus gros symboles posés en IWRAM — ce qui remplit la mémoire
    rapide, nommé comme dans le code généré."""
    low, span = _IWRAM
    inside = [(name, size) for name, (addr, size, _typ) in symbols.items()
              if low <= addr < low + span and 0 < size < _ABSURD_SIZE]
    return sorted(inside, key=lambda item: -item[1])[:count]


def read_soundbank(path: Path, sfx_names: list[str], music_names: list[str]) -> Optional[SoundbankReport]:
    """Décompose `soundbank.bin` grâce à sa propre table d'offsets.

    En-tête : `u16 nsamples`, `u16 nsongs`, la signature `*maxmod*`, puis un
    `u32` d'offset par entrée — les échantillons d'abord, les modules ensuite,
    dans l'ordre où mmutil les a reçus. La taille d'une entrée est l'écart
    jusqu'à la suivante ; vérifié sur la démo, la somme retombe sur la taille
    du fichier à l'octet près.

    Les `len(sfx_names)` premiers échantillons sont les wav des effets (le
    build les passe avant les modules) ; les suivants appartiennent aux
    modules, qui se les partagent.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 12 or data[4:12] != b"*maxmod*":
        return None
    n_samp, n_song = struct.unpack("<HH", data[0:4])
    n = n_samp + n_song
    need = 12 + 4 * n
    if len(data) < need:
        return None
    offsets = list(struct.unpack(f"<{n}I", data[12:need]))
    bounds = offsets + [len(data)]
    sizes = [bounds[i + 1] - bounds[i] for i in range(n)]

    n_sfx = min(len(sfx_names), n_samp)
    sfx_sizes = sizes[:n_sfx]
    mod_sample_sizes = sizes[n_sfx:n_samp]
    mod_sizes = sizes[n_samp:]

    shared_total = sum(mod_sample_sizes)
    n_mods = len(mod_sizes)
    entries: list[SoundEntry] = []
    for i, sz in enumerate(sfx_sizes):
        entries.append(SoundEntry(
            name=sfx_names[i] if i < len(sfx_names) else "",
            kind="sfx", own_bytes=sz))
    for i, sz in enumerate(mod_sizes):
        entries.append(SoundEntry(
            name=music_names[i] if i < len(music_names) else "",
            kind="music", own_bytes=sz,
            # Les échantillons sont mutualisés : aucun module ne les possède.
            # On les rapporte tels quels, avec le nombre de pistes concernées —
            # les répartir au prorata inventerait une propriété qui n'existe pas.
            shared_bytes=shared_total,
            shared_with=max(0, n_mods - 1)))

    return SoundbankReport(
        total=len(data),
        header=offsets[0] if offsets else 0,
        sfx_bytes=sum(sfx_sizes),
        music_data_bytes=sum(mod_sizes),
        music_sample_bytes=shared_total,
        entries=entries,
    )


# ── Assemblage ────────────────────────────────────────────────────────

def _categorize(symbols: dict[str, tuple[int, int, str]],
                sections: dict[str, int]) -> dict[str, int]:
    """Le poids par catégorie, en combinant DEUX niveaux de précision.

    Les sections font autorité sur les totaux — c'est le linker qui les écrit.
    Les symboles ne servent qu'à découper `.rodata`, là où vivent les assets.
    Sommer les symboles pour obtenir le code donnerait un chiffre trop bas et
    faux en silence : l'assembleur de libgba et de la libc n'émet pas de
    directive `.size`.
    """
    cats: dict[str, int] = {}

    # ── Assets : découpage de .rodata par symbole ─────────────────
    for name, (_addr, size, typ) in symbols.items():
        if typ not in "Rr":               # seul .rodata porte des assets
            continue
        if size <= 0 or size >= _ABSURD_SIZE:
            continue
        for cat, pattern in _SYMBOL_RULES:
            if pattern.search(name):
                cats[cat] = cats.get(cat, 0) + size
                break

    # Le soundbank n'a pas de taille (bin2s) : on la dérive de ses bornes.
    for cat, start, end in _SPAN_SYMBOLS:
        s, e = symbols.get(start), symbols.get(end)
        if s and e and e[0] > s[0]:
            cats[cat] = cats.get(cat, 0) + (e[0] - s[0])

    # ── Code : toutes les sections en ROM sauf celle des assets ────
    code = sum(size for sec, size in sections.items()
               if sec not in _NOT_IN_ROM and sec != _ASSET_SECTION)
    if code:
        cats["Code"] = code

    # ── Ce que le découpage de .rodata n'a pas su nommer ───────────
    rodata = sections.get(_ASSET_SECTION, 0)
    named = sum(v for c, v in cats.items() if c != "Code")
    if rodata > named:
        cats["Reste"] = cats.get("Reste", 0) + (rodata - named)
    return cats


def measure(project, toolchain, sfx_names: list[str], music_names: list[str],
            cartridge_mib: int = DEFAULT_CARTRIDGE_MIB) -> Optional[RomReport]:
    """Le rapport de poids, ou None si les outils ou la ROM manquent.

    `sfx_names` / `music_names` sont les listes RÉELLEMENT passées à mmutil,
    dans leur ordre — les mêmes que celles dont dérivent les `#define`
    `SFX_*`/`MUSIC_*`. C'est ce qui permet de rendre un nom à chaque entrée du
    soundbank, qui n'en porte aucun.
    """
    rom = getattr(project, "rom_path", None)
    elf = project.build_dir / "rom.elf"
    if not rom or not Path(rom).exists() or not elf.exists():
        return None
    nm = toolchain.resolve_binutil("nm")
    size_tool = toolchain.resolve_binutil("size")
    if nm is None or size_tool is None:
        return None

    symbols = read_symbols(nm, elf)
    sections = read_sections(size_tool, elf)
    if not symbols or not sections:
        return None
    cats = _categorize(symbols, sections)

    rom_bytes = Path(rom).stat().st_size
    attributed = sum(cats.values())
    # Le total fait foi : c'est le fichier qui part sur la cartouche. L'écart
    # restant (en-tête GBA, alignement du `.gba` par objcopy) est montré, pas
    # dissous dans une catégorie voisine.
    if rom_bytes > attributed:
        cats["Reste"] = cats.get("Reste", 0) + (rom_bytes - attributed)

    ordered = {c: cats[c] for c in CATEGORY_ORDER if cats.get(c)}
    for c, v in cats.items():                 # rien ne doit disparaître
        if c not in ordered and v:
            ordered[c] = v

    ewram, iwram, iwram_sections = read_ram_use(size_tool, elf)
    return RomReport(
        rom_bytes=rom_bytes,
        cartridge_bytes=cartridge_mib * 1024 * 1024,
        categories=ordered,
        soundbank=read_soundbank(project.build_dir / "soundbank.bin",
                                 sfx_names, music_names),
        ewram_bytes=ewram,
        iwram_bytes=iwram,
        iwram_sections=iwram_sections,
        iwram_top=iwram_largest(symbols),
        # `generate_main` pose `_vram_layout` sur chaque scène à chaque build :
        # c'est le placement RÉEL de ce build, pas une relecture.
        bg_vram_blocks={s.name: lay.used_blocks for s in project.scenes
                        if (lay := getattr(s, "_vram_layout", None)) is not None},
    )


def sound_weights(project, sfx_names: list[str], music_names: list[str]) -> dict[tuple[str, str], SoundEntry]:
    """{(genre, nom): poids} d'après le DERNIER build, ou {} s'il n'y en a pas.

    Sert l'affichage dans l'écran Son. C'est bien une mesure et non une
    prévision : tant qu'aucun build n'a eu lieu, l'éditeur ne dit rien plutôt
    que d'annoncer un chiffre qu'il aurait deviné.
    """
    sb = read_soundbank(project.build_dir / "soundbank.bin", sfx_names, music_names)
    if sb is None:
        return {}
    return {(e.kind, e.name): e for e in sb.entries if e.name}


def format_report(report: RomReport) -> list[str]:
    """Résumé textuel de la répartition ROM dans le journal de build.

    Le bandeau ``RomBudgetBar`` est la visualisation graphique persistante ;
    le journal ne répète donc pas une seconde jauge ASCII.
    """
    total = max(1, report.rom_bytes)
    lines = ["", "── Poids de la ROM ─────────────────────────────────────"]

    def kio(n: int) -> str:
        return f"{n / 1024:,.1f} KiB".replace(",", " ")

    for cat, size in report.categories.items():
        lines.append(f"  {cat} — {kio(size)} ({100 * size / total:.1f} %)")

    cap_mib = report.cartridge_bytes // (1024 * 1024)
    lines.append(f"  Total — {kio(report.rom_bytes)} / {cap_mib} MiB "
                 f"({100 * report.fill_ratio:.1f} %)")
    if report.over_capacity:
        over = report.rom_bytes - report.cartridge_bytes
        lines.append(f"  DÉPASSEMENT de {kio(over)} — cette ROM ne tient pas "
                     f"sur une cartouche de {cap_mib} MiB.")

    sb = report.soundbank
    if sb:
        lines.append("")
        lines.append(f"  Audio — SFX {kio(sb.sfx_bytes)}, modules {kio(sb.music_data_bytes)}, "
                     f"échantillons partagés {kio(sb.music_sample_bytes)}")
    return lines
