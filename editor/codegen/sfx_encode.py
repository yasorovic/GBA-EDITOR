"""
codegen/sfx_encode.py — L'étape du build qui prépare les effets sonores pour mmutil.

Le travail sur un effet lui-même (découpe, ré-échantillonnage) est `core/sfx_render.py`, partagé avec l'écran Son : ce
qu'on y voit et ce qu'on y entend est ce que ce module écrit. Ici, seulement : quels effets il faut ré-encoder.

Le fichier de `assets/` n'est **jamais** réécrit. La sortie va dans le dossier de build, et c'est elle que mmutil
reçoit : remonter le taux ou rouvrir la découpe après coup se fait sans avoir rien perdu, exactement comme l'import non
destructif de la v0.2.

Le NOM du fichier rendu n'a pas d'importance pour le code généré : les constantes `SFX_*` viennent du nom de l'ASSET
(cf. `grit_conversion.MmutilAudio._number_ids`). Il porte celui de l'asset pour une seule raison — deux effets qui
pointent le même `.wav` avec des réglages différents ne doivent pas s'écrire dans le même fichier.
"""
from __future__ import annotations

import wave
from pathlib import Path

from core.diagnostic import build_warning
from core.sfx_render import WAV_BITS_OK_BYTES, effective_rate, fade_out_of, is_edited, is_trimmed, write_sfx

__all__ = ["effective_rate", "encode_sfx_for_build"]


def encode_sfx_for_build(project, sfx_items: list, emit=None) -> dict[str, Path]:
    """{nom de l'effet: fichier à passer à mmutil} pour ceux qu'on ré-encode.

    Les effets ni découpés ni ré-échantillonnés n'apparaissent pas : leur fichier d'origine part tel quel, et on ne le
    recopie pas pour rien.
    """
    out_dir = project.build_dir / "sfx"
    settings = project.settings
    encoded: dict[str, Path] = {}
    for sfx, src in sfx_items:
        target = effective_rate(sfx, settings)
        trimmed = is_trimmed(sfx)
        try:
            with wave.open(str(src)) as w:
                src_rate, src_frames, width = w.getframerate(), w.getnframes(), w.getsampwidth()
        except Exception:  # tolerated: unreadable WAV: check_audio_file reports it
            continue
        if width in WAV_BITS_OK_BYTES and not is_edited(sfx) and (target <= 0 or target == src_rate):
            continue
        dst = out_dir / f"{sfx.name}.wav"
        try:
            n = write_sfx(src, dst, sfx, target)
        except Exception as e:
            if emit:
                emit("diagnostic", build_warning(f"\"{sfx.name}\" not encoded: {e}", "sfx"))
            continue
        if n is None:
            # Une découpe qui ne laisse rien : le validateur la signale ; ici, l'effet part entier plutôt
            # qu'un son vide dont la constante `SFX_*` existerait sans rien jouer.
            if emit:
                emit("diagnostic", build_warning(
                    f"\"{sfx.name}\": the trim leaves nothing, the whole effect is kept.", "sfx"))
            continue
        encoded[sfx.name] = dst
        if emit:
            parts = []
            if trimmed:
                parts.append(f"trim {sfx.trim_start}–{sfx.trim_end or 'end'} ms")
            if fade_out_of(sfx):
                parts.append(f"fade out {fade_out_of(sfx)} fr")
            if target > 0 and target != src_rate:
                parts.append(f"{src_rate} → {target} Hz")
            emit("log_line", f"[sfx] \"{sfx.name}\" {', '.join(parts)}  ({src_frames} → {n} bytes in ROM)")
    return encoded
