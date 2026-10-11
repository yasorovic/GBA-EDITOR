"""
core/music_structure.py — ce que les réglages d'une musique ont le droit de dire,
mis en face du fichier qu'ils décrivent.

Le sidecar `.music` surcharge, le fichier propose (ROADMAP « L'asset .music ») :
les sections sont des plages posées PAR-DESSUS un morceau, et un morceau peut
être remplacé, raccourci, ou changer de famille. Un sidecar d'hier n'a donc rien
promis sur le fichier d'aujourd'hui — c'est ici qu'on le vérifie, avant que le
build ne saute sur une position qui n'existe pas.

Aucune dépendance à Qt ni au projet : le validateur passe le chemin et, pour un
module, sa propre lecture mise en cache (`ctx.module`). Rend des couples
(niveau, message) pour qu'un appelant sans validateur — l'écran Son, plus tard —
les lise de la même façon.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from core.models.audio import (
    FADE_MAX_FRAMES, PITCH_MAX, PITCH_MIN, TEMPO_MAX, TEMPO_MIN,
    UNIT_MS, UNIT_ORDER, Music, pitch_to_module, tempo_to_module,
)
from core.wav_module import CUT_WAIT_SECONDS, MUSIC_SAMPLE_RATE_MIN, WAV_MUSIC_RATE

ERROR = "error"
WARNING = "warning"


def is_wav_asset(asset: Optional[str]) -> bool:
    """Une musique WAV se reconnaît à son extension (cf. `models/audio.WAV_MUSIC_EXT`)."""
    return bool(asset) and str(asset).lower().endswith(".wav")


def jingle_ignored_settings(music: Music) -> list[str]:
    """Les réglages d'un jingle que le build n'applique pas, par leur nom.

    Un jingle joue sur la SECONDE couche de maxmod (`mmJingle`), avec son propre
    volume : ni section de boucle (il ne boucle pas), ni tempo ni hauteur (ils règlent
    la couche principale), ni fondus (ils passent par le stepper de la musique)."""
    ignored = []
    if music.sections or music.loop_section:
        ignored.append("sections")
    if music.tempo != 100:
        ignored.append("tempo")
    if music.pitch != 100:
        ignored.append("pitch")
    if music.fade_in or music.fade_out:
        ignored.append("fades")
    return ignored


# ── Ce que la ROM lit des réglages d'une musique ──────────────────────────────
#
# Une ligne par module : la section de boucle (en positions d'ordre), le tempo et la
# hauteur (facteurs Q10 de maxmod), les deux fondus (en frames). ZÉRO PARTOUT = le
# fichier tel qu'il est. Définie ICI, et non dans l'émetteur C, parce que l'aperçu de
# l'éditeur la lit aussi : un seul calcul pour la ROM et pour ce qu'on entend, sinon
# l'un des deux finit par régler autre chose que l'autre (cf. ROADMAP « L'asset .music »).

def music_info_row(m) -> tuple[int, int, int, int, int, int]:
    """(début de boucle, fin de boucle, tempo, hauteur, fondu d'entrée, fondu de sortie).

    Ce qu'un WAV n'a PAS ici, et pourquoi : sa boucle est dans le module lui-même
    (l'échantillon boucle, cf. `wav_module`), et son tempo comme sa hauteur sont des
    réglages du MODULE — qui n'a qu'une note, calée sur la durée de la piste : les
    changer la couperait avant sa fin ou la laisserait finir en silence."""
    wav = is_wav_asset(m.asset)
    start = end = 0
    section = m.section(m.loop_section) if m.loop_section else None
    if section is not None and not wav and m.unit == UNIT_ORDER and 0 <= section.start < section.end:
        start, end = section.start, section.end
    tempo = 0 if wav or m.tempo == 100 else tempo_to_module(m.tempo)
    pitch = 0 if wav or m.pitch == 100 else pitch_to_module(m.pitch)
    fade_in = max(0, min(FADE_MAX_FRAMES, int(m.fade_in)))
    fade_out = max(0, min(FADE_MAX_FRAMES, int(m.fade_out)))
    return start, end, tempo, pitch, fade_in, fade_out


def music_section_rows(music: Music) -> list[tuple[str, int, int]]:
    """Les sections d'un module que `music.set_section` peut atteindre, en (nom, début, fin).

    Des positions d'ordre : un WAV n'a qu'une boucle, posée au build, et ne change pas
    de section à l'exécution. Une plage vide, inversée ou d'une autre unité n'en est pas
    une — le validateur la signale."""
    if is_wav_asset(music.asset) or music.unit != UNIT_ORDER:
        return []
    return [(s.name, s.start, s.end) for s in music.sections if 0 <= s.start < s.end]


def music_section_names(musics) -> list[str]:
    """Tous les noms de section du projet, triés et sans doublon — l'ORDRE fait foi.

    L'index dans cette liste est la constante `MSEC_*` que le script émet ET la clé de
    la table que `main.c` lit : les deux la dérivent d'ici, jamais de deux listes. Les
    jingles n'en ont pas (leurs réglages ne sont pas appliqués)."""
    from core.models.audio import Jingle
    names: set = set()
    for m in musics:
        if not isinstance(m, Jingle):
            names.update(name for name, _s, _e in music_section_rows(m))
    return sorted(names)


def wav_loop_region(music: Music) -> Optional[tuple[int, int]]:
    """La section de boucle d'une musique WAV, en millisecondes, ou None.

    Lue par le build (`wav_module.encode_music_for_build`) et par rien d'autre : c'est
    l'unique endroit où une section devient un réglage du module. Une section dans
    une autre unité, vide ou inconnue n'est pas une région — le validateur la signale,
    le build n'invente rien."""
    section = music.section(music.loop_section) if music.loop_section else None
    if section is None or music.unit != UNIT_MS or not 0 <= section.start < section.end:
        return None
    return section.start, section.end


def cut_problems(src_name: str, dst_name: str, src_module, dst_module, *,
                 src_wav: bool = False, dst_wav: bool = False,
                 dst_loop: bool = True) -> list[str]:
    """Ce qui cloche quand `music.cut_to(dst)` coupe depuis `src` — liste de messages.

    La coupe lit `mmGetPosition()` sur la source et rejoue la cible à ce MÊME
    index d'ordre (`mmPosition`). Ce qu'il faut tenir est donc : chaque position
    où la source peut se trouver désigne un PATTERN dans la cible. La longueur
    des deux tables n'est ni suffisante (un séparateur au mauvais index) ni
    nécessaire (une cible plus longue que la source ne risque rien).

    Ce qui se passe sur un index qui ne désigne pas de pattern a été MESURÉ sur
    ROM le 2026-10-11 (ROADMAP « L'asset .music ») :
        séparateur (254)        la lecture tombe sur le pattern SUIVANT ;
        fin (255) ou hors table  avec `MM_PLAY_LOOP` la cible REDÉMARRE à sa
                                position de restart ; avec `MM_PLAY_ONCE` elle
                                s'ARRÊTE, et c'est un silence.
    Un module None (illisible, signalé ailleurs) : on ne dit rien de la structure.
    """
    out: list[str] = []
    if dst_wav:
        out.append(f"the cut to \"{dst_name}\" targets a WAV track — it resumes mid-module, where a "
                   "WAV track has no note, so it stays silent. Use a fade.")
    if src_wav:
        out.append(f"the cut from \"{src_name}\" leaves a WAV track, which has no pattern boundary "
                   f"of its own: it waits for the end of its {CUT_WAIT_SECONDS:.0f} s pattern. Use a "
                   "fade, or a module with real patterns.")
    if src_wav or dst_wav or src_module is None or dst_module is None:
        return out

    from core.engine_emulation.module_model import ORDER_END, ORDER_SKIP, is_pattern_order
    # Les positions où la source peut sonner : ce qui suit un 255 n'est jamais joué.
    positions: list[int] = []
    for i, entry in enumerate(src_module.order):
        if entry == ORDER_END:
            break
        if is_pattern_order(entry):
            positions.append(i)

    n_dst = len(dst_module.order)
    gone = [p for p in positions
            if p >= n_dst or dst_module.order[p] == ORDER_END]
    skipped = [p for p in positions if p < n_dst and dst_module.order[p] == ORDER_SKIP]
    if gone:
        consequence = ("it restarts from its beginning" if dst_loop
                       else "it stops, and the music goes silent")
        out.append(f"the cut from \"{src_name}\" to \"{dst_name}\" resumes at the same order "
                   f"position, but \"{dst_name}\" has no music from position {gone[0]} "
                   f"({len(gone)} of {len(positions)} positions of \"{src_name}\") — {consequence}.")
    if skipped:
        out.append(f"the cut from \"{src_name}\" to \"{dst_name}\" lands on a separator of "
                   f"\"{dst_name}\"'s order table at position {skipped[0]} ({len(skipped)} "
                   f"position(s)) — it resumes on the next pattern instead.")
    return out


def source_unit(path) -> Optional[str]:
    """L'unité dans laquelle ce fichier se découpe, ou None s'il est illisible.

    Lue sur le CONTENU, jamais sur l'extension (même règle que le reste de la
    chaîne audio, cf. `module_model.detect_format`)."""
    from core.engine_emulation.module_model import detect_format
    try:
        with open(path, "rb") as f:
            head = f.read(2048)
    except OSError:
        return None
    kind = detect_format(head)
    if kind is None:
        return None
    return UNIT_MS if kind == "wav" else UNIT_ORDER


def _wav_milliseconds(path) -> Optional[int]:
    import wave
    try:
        with wave.open(str(path)) as w:
            return w.getnframes() * 1000 // max(1, w.getframerate())
    except Exception:  # tolerated: `check_audio_file` already says why the WAV is unreadable
        return None


def music_problems(music: Music, path,
                   module_of: Optional[Callable] = None) -> list[tuple[str, str]]:
    """Tout ce qui cloche dans les réglages de `music`, ce fichier étant le sien.

    `module_of(path)` rend un `Module` ou None ; le validateur passe `ctx.module`,
    qui mémorise la lecture (un module coûte ~9 ms à analyser)."""
    problems: list[tuple[str, str]] = []

    # ── Les valeurs seules, sans le fichier ──
    if not TEMPO_MIN <= music.tempo <= TEMPO_MAX:
        problems.append((WARNING, f"tempo {music.tempo} % is outside {TEMPO_MIN}–{TEMPO_MAX} % "
                                  "(maxmod plays 0.5× to 2×) — it will be clamped."))
    if not PITCH_MIN <= music.pitch <= PITCH_MAX:
        problems.append((WARNING, f"pitch {music.pitch} % is outside {PITCH_MIN}–{PITCH_MAX} % "
                                  "(maxmod plays 0.5× to 2×) — it will be clamped."))
    for what, frames in (("fade in", music.fade_in), ("fade out", music.fade_out)):
        if not 0 <= frames <= FADE_MAX_FRAMES:
            problems.append((WARNING, f"{what} of {frames} frames is outside 0–{FADE_MAX_FRAMES} "
                                      "(10 s) — a longer one is a transition, not a fade."))

    unit = source_unit(path) if path else None
    if unit is None:
        return problems          # fichier absent ou illisible : signalé ailleurs

    # ── Les valeurs qui n'ont de sens que pour une famille de fichier ──
    if music.sample_rate:
        if unit != UNIT_MS:
            problems.append((WARNING, "a sample rate only applies to a WAV: this file is a "
                                      "module, which keeps its own samples."))
        elif not MUSIC_SAMPLE_RATE_MIN <= music.sample_rate <= WAV_MUSIC_RATE:
            problems.append((ERROR, f"sample rate {music.sample_rate} Hz is outside "
                                    f"{MUSIC_SAMPLE_RATE_MIN}–{WAV_MUSIC_RATE} Hz (the console's mixer "
                                    "plays about 16 kHz at most)."))

    if unit == UNIT_MS and (music.tempo != 100 or music.pitch != 100):
        problems.append((WARNING, "tempo and pitch do not apply to a WAV track: it is a module of one "
                                  "note, timed to the length of the track — changing them would cut "
                                  "it short or let it finish in silence. They are ignored."))
    if music.loop_section and not music.loop:
        problems.append((WARNING, f"the loop flag is off but the loop section \"{music.loop_section}\" "
                                  "is set: a module with a loop section never ends, so it loops "
                                  "anyway."))

    if not music.sections and not music.loop_section:
        return problems

    # ── Les sections, mises en face du fichier ──
    if music.unit != unit:
        problems.append((ERROR, f"sections are written in \"{music.unit}\" but this file is cut in "
                                f"\"{unit}\" (it was probably replaced by another kind of file) — "
                                "reset them."))
        return problems

    table: Optional[list] = None
    if unit == UNIT_MS:
        extent = _wav_milliseconds(path)
        unit_label = "ms"
    else:
        mod = module_of(path) if module_of else None
        if mod is None:
            return problems
        table = mod.order
        extent = len(table)
        unit_label = "order positions"
    if extent is None:
        return problems

    from core.engine_emulation.module_model import is_pattern_order
    seen: set = set()
    for sec in music.sections:
        if not sec.name.strip():
            problems.append((ERROR, "a section has no name."))
        elif sec.name in seen:
            problems.append((ERROR, f"two sections are named \"{sec.name}\" — the call would be "
                                    "ambiguous. Rename one."))
        seen.add(sec.name)

        if sec.start < 0 or sec.end <= sec.start:
            problems.append((ERROR, f"section \"{sec.name}\": the range [{sec.start}, {sec.end}) is "
                                    "empty or reversed."))
        elif sec.end > extent + (1 if unit == UNIT_MS else 0):
            problems.append((ERROR, f"section \"{sec.name}\" ends at {sec.end} but the file has only "
                                    f"{extent} {unit_label}."))
        elif table is not None and not is_pattern_order(table[sec.start]):
            problems.append((ERROR, f"section \"{sec.name}\" starts at position {sec.start}, which "
                                    "is a marker in the file's order table, not a pattern — a "
                                    "jump there would not land on music."))

    if music.loop_section:
        sec = music.section(music.loop_section)
        if sec is None:
            problems.append((ERROR, f"the loop section \"{music.loop_section}\" does not exist."))
        elif not sec.loop:
            problems.append((WARNING, f"\"{sec.name}\" is the loop section but its loop flag is off "
                                      "— it will not loop."))

    if unit == UNIT_MS:
        loops = [s.name for s in music.sections if s.loop]
        if len(loops) > 1:
            problems.append((ERROR, f"a WAV has one native loop, and {len(loops)} sections have "
                                    f"loop on ({', '.join(loops)})."))
    return problems
