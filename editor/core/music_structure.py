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
    CUE_SFX, CUE_SOUND_ACTION, UNIT_MS, UNIT_ORDER, Jingle, Music, MusicCue, pitch_to_module, tempo_to_module,
)
from core.module_trim import is_order_cut, order_problem
from core.wav_edit import fade_in_of, fade_out_of, is_trimmed, trim_of, trim_problem
from core.wav_module import (
    CUT_WAIT_SECONDS, MUSIC_SAMPLE_RATE_MIN, WAV_MUSIC_RATE, WavPlan, effective_rate, plan_wav,
    wav_kept_seconds, wav_to_xm,
)

ERROR = "error"
WARNING = "warning"

# La cadence de la console : 16 777 216 Hz / 280 896 cycles par image. La ROM compte des IMAGES, pas des secondes — un jingle
# dont les repères sont en temps les convertit avec ce chiffre-là (le deck de l'aperçu, lui, tourne à 60 par commodité).
VBLANK_HZ = 16777216 / 280896
# Ce qu'un jingle peut déclencher : un effet, ou une action de SoundBox. Pas un autre jingle — il remplacerait celui qui sonne.
JINGLE_CUE_KINDS = (CUE_SFX, CUE_SOUND_ACTION)
# Un repère de jingle tient dans un s16 de la table C : plus de 9 minutes d'images n'est plus un jingle.
_MAX_CUE_FRAME = 32767

# Une section WAV ne peut pas être plus courte : elle tiendrait en moins de quelques lignes du module
# (une ligne = ~11 ms) et l'oreille n'y trouverait plus de musique. L'éditeur le tient aux poignées comme au tableau.
MIN_SECTION_MS = 50
# Le plus de sections qu'une musique en propose : l'éditeur les tient toutes à l'écran, sans défilement.
MAX_SECTIONS = 6


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
    if (music.fade_in or music.fade_out) and not is_wav_asset(music.asset):
        ignored.append("fades")          # un jingle WAV a les siens, cuits dans la piste (cf. `wav_cut`)
    if is_trimmed(music) and not is_wav_asset(music.asset):
        ignored.append("trim")           # un module ne se rogne pas
    return ignored


# ── Ce que la ROM lit des réglages d'une musique ──────────────────────────────
#
# Une ligne par module : la section de boucle (en positions d'ordre), le tempo et la
# hauteur (facteurs Q10 de maxmod), les deux fondus (en frames). ZÉRO PARTOUT = le
# fichier tel qu'il est. Définie ICI, et non dans l'émetteur C, parce que l'aperçu de
# l'éditeur la lit aussi : un seul calcul pour la ROM et pour ce qu'on entend, sinon
# l'un des deux finit par régler autre chose que l'autre (cf. ROADMAP « L'asset .music »).

def music_info_row(m, path=None) -> tuple[int, int, int, int, int, int]:
    """(début de boucle, fin de boucle, tempo, hauteur, fondu d'entrée, fondu de sortie).

    `path` est le fichier de la musique : un WAV en a besoin, parce que ses sections sont en millisecondes
    et que la ROM les lit en positions d'ordre (`wav_section_orders`). Un module tracker n'en a pas besoin.

    Ce qu'un WAV n'a PAS ici, et pourquoi : son tempo comme sa hauteur sont des réglages du MODULE, et
    celui d'un WAV est calé sur la durée de la piste — les changer décalerait les segments les uns par
    rapport aux autres (les lignes iraient plus vite, pas les échantillons)."""
    wav = is_wav_asset(m.asset)
    start = end = 0
    if m.loop_section:
        for name, first, last in music_section_rows(m, path):
            if name == m.loop_section:
                start, end = first, last
    tempo = 0 if wav or m.tempo == 100 else tempo_to_module(m.tempo)
    pitch = 0 if wav or m.pitch == 100 else pitch_to_module(m.pitch)
    fade_in = max(0, min(FADE_MAX_FRAMES, int(m.fade_in)))
    fade_out = max(0, min(FADE_MAX_FRAMES, int(m.fade_out)))
    return start, end, tempo, pitch, fade_in, fade_out


def music_section_rows(music: Music, path=None) -> list[tuple[str, int, int]]:
    """Les sections que `music.set_section` peut atteindre, en (nom, début, fin) — des positions d'ordre.

    Pour un module tracker c'est le modèle tel quel. Pour un WAV, les millisecondes du modèle sont
    traduites par le plan du build (`wav_section_orders`), qui a besoin du fichier : sans `path`, un WAV
    n'a pas de ligne. Une plage vide, inversée ou d'une autre unité n'en est pas une — le validateur la
    signale."""
    if is_wav_asset(music.asset):
        return wav_section_orders(music, path) if path is not None else []
    if music.unit != UNIT_ORDER:
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
        if isinstance(m, Jingle):
            continue
        if m.unit == (UNIT_MS if is_wav_asset(m.asset) else UNIT_ORDER):
            names.update(s.name for s in m.sections if 0 <= s.start < s.end)
    return sorted(names)


def wav_cut(music: Music) -> tuple[tuple[int, int], tuple[int, int]]:
    """Ce que le build fait au SIGNAL d'une piste WAV avant de l'encapsuler : `(plage gardée, fondus cuits)`.

    Lu par le build, l'aperçu et le poids ROM : c'est l'unique endroit où les réglages d'une musique deviennent des arguments de
    `wav_to_xm`. La plage est celle de `core/wav_edit.py` (ms depuis le début du fichier). Les fondus ne sont cuits que pour
    un JINGLE, qui n'en a pas à l'exécution : ceux d'une musique sont appliqués par la console (cf. `music_info_row`), les cuire
    les ferait deux fois."""
    fades = (fade_in_of(music), fade_out_of(music)) if isinstance(music, Jingle) else (0, 0)
    return trim_of(music), fades


def retrim(music: Music, start: int, end: int, total_ms: float) -> list[str]:
    """Change la plage gardée de `music` pour `(start, end)` (ms depuis le début du FICHIER, `end` à 0 = jusqu'au bout) et fait
    suivre ses sections : elles sont dans le temps de la plage gardée, donc elles glissent avec le son. Rend les noms des
    sections que la nouvelle plage a fait disparaître (hors d'elle, ou réduites sous `MIN_SECTION_MS`).

    `total_ms` est la durée du fichier entier. Une plage qui couvre tout le fichier s'écrit « pas de découpe » (0, 0) : la fin à
    0 suit un fichier qu'on remplacerait par un plus long. Une section écartée emporte la boucle qui la citait (`remove_section`)."""
    from core.wav_edit import trim_window
    old_start, _old_end = trim_window(music, total_ms)
    total = max(0, round(total_ms))
    start = max(0, min(int(start), total))
    end = total if end <= 0 else max(start, min(int(end), total))
    shift = start - old_start
    kept = end - start
    music.trim_start = start
    music.trim_end = 0 if end >= total else end
    gone = []
    for section in list(music.sections):
        section.start, section.end = max(0, section.start - shift), min(kept, section.end - shift)
        if section.end - section.start < MIN_SECTION_MS:
            music.remove_section(section.name)
            gone.append(section.name)
    # Un repère glisse avec le son, et disparaît avec lui : il n'a pas de nom à rendre, la plage rognée l'emporte.
    for cue in list(music.cues):
        cue.position -= shift
        if not 0 <= cue.position < kept:
            music.remove_cue(cue)
    return gone


def wav_boundaries(music: Music) -> list[int]:
    """Les frontières (début ET fin de chaque section) où le build coupe une piste WAV, en millisecondes.

    Lues par le build et par l'aperçu : c'est l'unique endroit où des sections deviennent des segments. Une
    section dans une autre unité ou vide n'en pose pas — le validateur la signale, le build n'invente rien."""
    if music.unit != UNIT_MS:
        return []
    bounds: set = set()
    for section in music.sections:
        if 0 <= section.start < section.end:
            bounds.update((section.start, section.end))
    # Un repère tombe à la LIGNE près, comme une section : sans frontière il se déclencherait au début du pattern
    # qui le contient, jusqu'à une pleine position d'ordre trop tôt.
    if not isinstance(music, Jingle):               # ceux d'un jingle sont en temps, comptés en images par la ROM
        bounds.update(cue.position for cue in music.cues if cue.position > 0)
    return sorted(bounds)


def wav_plan(music: Music, path) -> Optional[WavPlan]:
    """Le plan de découpe de la piste WAV de `music` (où tombent ses segments), ou None si le fichier n'est
    pas convertible — le validateur en dit la cause."""
    try:
        return plan_wav(wav_kept_seconds(path, trim_of(music)), effective_rate(music.sample_rate), wav_boundaries(music))
    except ValueError:
        return None


def wav_section_orders(music: Music, path) -> list[tuple[str, int, int]]:
    """Les sections d'une musique WAV, en (nom, début, fin) de POSITIONS D'ORDRE — ce que la ROM lit.

    La seule traduction des millisecondes du modèle en ordres : `music_info_row`, la table des sections de
    `main.c` et l'aperçu passent tous par ici, comme le build passe par le même plan. Une section dont les
    deux bords tombent sur la même ligne (moins de ~11 ms) est vide et disparaît."""
    plan = wav_plan(music, path)
    if plan is None or music.unit != UNIT_MS:
        return []
    rows = []
    for section in music.sections:
        if 0 <= section.start < section.end:
            first, last = plan.order_at(section.start), plan.order_at(section.end)
            if first < last:
                rows.append((section.name, first, last))
    return rows


def music_cue_rows(music: Music, path=None) -> list[tuple[int, "MusicCue"]]:
    """Les repères d'une musique, en (position d'ordre, repère) — ce que la ROM lit et ce que l'aperçu observera.

    Un module tracker : la position du modèle telle quelle. Un WAV : ses millisecondes passent par le plan du build
    (`wav_plan`, qui a une frontière à chaque repère), comme `wav_section_orders` pour les sections ; sans `path`, un
    WAV n'a pas de ligne. Un repère d'une autre unité que le fichier n'en est pas un — le validateur le signale."""
    if not music.cues or isinstance(music, Jingle):      # un jingle a ses repères en temps (cf. `jingle_cue_frames`)
        return []
    if is_wav_asset(music.asset):
        plan = wav_plan(music, path) if path is not None else None
        if plan is None or music.unit != UNIT_MS:
            return []
        return [(plan.order_at(cue.position), cue) for cue in music.cues if cue.position >= 0]
    if music.unit != UNIT_ORDER:
        return []
    return [(cue.position, cue) for cue in music.cues if cue.position >= 0]


def jingle_cue_frames(jingle: Jingle) -> list[tuple[int, "MusicCue"]]:
    """Les repères d'un jingle, en (image depuis le début du jingle, repère) — ce que la ROM lit.

    Les repères d'un jingle sont TOUJOURS en millisecondes, module ou WAV : maxmod ne donne aucune position sur la couche
    jingle (`mmGetPosition` ne lit que la principale), donc la ROM COMPTE les images depuis `mmJingle`. Et un ordre ne dit rien
    d'un jingle d'un seul pattern (13 des 19 de la démo) : il ne pourrait viser que son début. Aucun rendu n'est nécessaire,
    la conversion est un produit. Une nature interdite (un jingle qui en lance un autre) ou un repère trop loin n'a pas de
    ligne — le validateur le dit."""
    rows: list[tuple[int, MusicCue]] = []
    for cue in jingle.cues:
        frame = round(cue.position / 1000.0 * VBLANK_HZ)
        if cue.kind in JINGLE_CUE_KINDS and 0 <= frame <= _MAX_CUE_FRAME:
            rows.append((frame, cue))
    return sorted(rows, key=lambda row: row[0])


def cue_problems(music: Music, unit: Optional[str], extent: Optional[int], table=None) -> list[tuple[str, str]]:
    """Ce qui cloche dans la POSITION des repères d'une musique, ce fichier étant le sien (leurs noms visés, eux, se
    vérifient contre le projet : `validator._check_sound_boxes`). `unit`/`extent`/`table` sont ceux des sections."""
    out: list[tuple[str, str]] = []
    if not music.cues or unit is None:
        return out
    if not isinstance(music, Jingle) and music.unit != unit:      # un jingle est toujours en ms
        out.append((ERROR, f"cues are written in \"{music.unit}\" but this file is cut in \"{unit}\" — reset them."))
        return out
    from core.engine_emulation.module_model import is_pattern_order
    for cue in music.cues:
        if isinstance(music, Jingle) and cue.kind not in JINGLE_CUE_KINDS:
            out.append((WARNING, f"a cue at {cue.position} plays a jingle from a jingle, which would replace the one "
                                 "that is sounding — it will play nothing."))
        if cue.position < 0 or (extent is not None and cue.position >= extent):
            out.append((ERROR, f"a cue at {cue.position} is outside the file ({extent} "
                               f"{'ms' if unit == UNIT_MS else 'order positions'})."))
        elif table is not None and not isinstance(music, Jingle) and not is_pattern_order(table[cue.position]):
            out.append((WARNING, f"a cue at position {cue.position} sits on a marker of the order table, not a "
                                 "pattern — it would never fire."))
        if not cue.target:
            out.append((WARNING, f"a cue at {cue.position} points to nothing — it will play nothing."))
    return out


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


def _wav_milliseconds(path, trim: tuple[int, int] = (0, 0)) -> Optional[int]:
    """La durée de la plage gardée d'un WAV (le fichier entier sans `trim`), en ms ; None s'il est illisible ou si la
    découpe ne laisse rien."""
    try:
        return int(wav_kept_seconds(path, trim) * 1000)
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

    if is_trimmed(music):
        if unit != UNIT_MS:
            problems.append((WARNING, "a trim only applies to a WAV: this file is a module, whose parts are "
                                      "sections in order positions. It is ignored."))
        else:
            problem = trim_problem(music, (_wav_milliseconds(path) or 0))
            if problem:
                problems.append((ERROR, problem))

    if unit == UNIT_MS and (music.tempo != 100 or music.pitch != 100):
        problems.append((WARNING, "tempo and pitch do not apply to a WAV track: its sections are samples "
                                  "chained by the module's lines — speeding the lines up would not speed "
                                  "the samples, and the sections would drift apart. They are ignored."))
    if len(music.sections) > MAX_SECTIONS:
        problems.append((WARNING, f"{len(music.sections)} sections: the editor offers {MAX_SECTIONS} at most "
                                  "and will not let a new one be added."))
    if music.loop_section and not music.loop:
        problems.append((WARNING, f"the loop flag is off but the loop section \"{music.loop_section}\" "
                                  "is set: a module with a loop section never ends, so it loops "
                                  "anyway."))

    if isinstance(music, Jingle):
        # Ses sections sont ignorées (`jingle_ignored_settings`) ; ses repères sont en ms quelle que soit la famille du fichier.
        extent = _wav_milliseconds(path, trim_of(music)) if unit == UNIT_MS else None   # un module : durée inconnue sans rendu
        if is_order_cut(music):
            if unit == UNIT_MS:
                problems.append((WARNING, "an order range only applies to a module: this file is a WAV, which is "
                                          "trimmed in milliseconds. It is ignored."))
            elif (mod := module_of(path) if module_of else None) is not None:
                if problem := order_problem(music, len(mod.order)):
                    problems.append((ERROR, problem))
        return problems + cue_problems(music, UNIT_MS, extent)
    if not music.sections and not music.loop_section and not music.cues:
        return problems

    # ── Les sections et les repères, mis en face du fichier ──
    if music.unit != unit:
        problems.append((ERROR, f"sections and cues are written in \"{music.unit}\" but this file is cut in "
                                f"\"{unit}\" (it was probably replaced by another kind of file) — "
                                "reset them."))
        return problems

    table: Optional[list] = None
    if unit == UNIT_MS:
        extent = _wav_milliseconds(path, trim_of(music))        # les sections sont dans le temps de la plage GARDÉE
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
    problems += cue_problems(music, unit, extent, table)

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
        try:
            plan = plan_wav(wav_kept_seconds(path, trim_of(music)), effective_rate(music.sample_rate),
                            wav_boundaries(music))
        except ValueError as exc:
            problems.append((ERROR, str(exc)))
        else:
            kept = {name for name, _a, _b in wav_section_orders(music, path)}
            for sec in music.sections:
                if 0 <= sec.start < sec.end and sec.name not in kept:
                    problems.append((ERROR, f"section \"{sec.name}\" is shorter than one line of the "
                                            "module (about 11 ms): it would be empty."))
    return problems


# ── Le poids en ROM ──────────────────────────────────────────────

# Au-delà de ces tailles, UNE musique pèse lourd dans une cartouche de jeu : la pastille de l'éditeur
# vire à l'orange puis au rouge.
WEIGHT_WARN_BYTES = 1 << 20
WEIGHT_HIGH_BYTES = 2 << 20


def weight_level(size: int) -> str:
    """"ok", "warn" ou "high" : la gravité du poids d'une musique."""
    if size > WEIGHT_HIGH_BYTES:
        return "high"
    return "warn" if size > WEIGHT_WARN_BYTES else "ok"


def wav_rom_bytes(music: Music, path: Path) -> Optional[int]:
    """Ce que pèsera une musique WAV en ROM, sans build : c'est le module que le build écrit, au taux et
    avec les sections que le build utilisera (`wav_to_xm`). None si le WAV n'est pas convertible — le
    validateur en dit la cause."""
    try:
        trim, fades = wav_cut(music)
        return len(wav_to_xm(path, effective_rate(music.sample_rate), wav_boundaries(music), trim=trim, fades=fades))
    except ValueError:
        return None
