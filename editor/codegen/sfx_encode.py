"""
codegen/sfx_encode.py — Ré-échantillonnage des effets sonores pour la cible.

C'est de l'ENCODAGE, pas de la conversion de format : le même geste que
découper un PNG en tuiles et lui allouer une palette avant de l'envoyer en ROM.
L'éditeur continue de refuser de transcoder un `.ogg` (ROADMAP v0.8.1) — ça,
c'est le travail de l'outil audio de l'auteur.

Le fichier de `assets/` n'est **jamais** réécrit. La sortie va dans le dossier
de build, et c'est elle que mmutil reçoit : remonter le taux après coup se fait
sans avoir rien perdu, exactement comme l'import non destructif de la v0.2.

Pourquoi ça vaut le détour, mesuré sur la démo : mmutil convertit en 8 bits
mono mais **conserve le taux d'échantillonnage**. Cinq bruitages en 44,1 kHz
pèsent 222,7 Kio ; à 16 kHz — au-dessus de ce que le mixeur Maxmod restitue —
ils tombent à ~83 Kio.
"""
from __future__ import annotations

import wave
from core.validator import build_warning
from pathlib import Path
from typing import Optional

import numpy as np


def effective_rate(sfx, settings) -> int:
    """Le taux visé pour cet effet : le sien, sinon celui du projet, sinon 0.

    0 signifie « garde le fichier tel quel ». C'est le défaut, et il est
    délibéré : ré-échantillonner d'office dégraderait un projet existant sans
    que personne ne l'ait demandé.
    """
    own = int(getattr(sfx, "sample_rate", 0) or 0)
    if own > 0:
        return own
    return max(0, int(getattr(settings, "sfx_sample_rate", 0) or 0))


def _read_wav(path: Path) -> Optional[tuple[np.ndarray, int, int]]:
    """(échantillons float32 mono-canal entrelacés, taux, nb de canaux)."""
    with wave.open(str(path)) as w:
        rate, ch, width, n = (w.getframerate(), w.getnchannels(),
                              w.getsampwidth(), w.getnframes())
        raw = w.readframes(n)
    if width == 1:
        # WAV 8 bits : non signé, centré sur 128.
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0
        data /= 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    else:
        return None
    return data, rate, ch


def resample_wav(src: Path, dst: Path, target_rate: int) -> Optional[int]:
    """Écrit `src` ré-échantillonné à `target_rate` dans `dst`.

    Rend le nombre de frames écrites, ou None si le fichier n'est pas
    convertible (le validateur a déjà refusé ces cas à l'import).

    Sortie en **16 bits mono** : mmutil descendra lui-même en 8 bits, et lui
    laisser cette étape évite de quantifier deux fois. Le mono est acquis de
    toute façon — mmutil ne mixe que des échantillons mono.
    """
    got = _read_wav(src)
    if got is None:
        return None
    data, rate, ch = got
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    if data.size == 0:
        return None

    if target_rate > 0 and target_rate != rate:
        ratio = target_rate / rate
        if ratio < 1.0:
            # Moyenne glissante avant décimation. Sans ce filtre, tout ce qui
            # dépasse la moitié du nouveau taux se replie en sifflements —
            # une dégradation qui S'ENTEND, et qu'on ne pourrait pas expliquer
            # à l'auteur puisqu'elle n'existe pas dans son fichier.
            k = max(1, int(round(1 / ratio)))
            kernel = np.ones(k, dtype=np.float32) / k
            data = np.convolve(data, kernel, mode="same")
        n_out = max(1, int(round(data.size * ratio)))
        # Positions des nouveaux échantillons sur l'ancienne grille.
        pos = np.linspace(0, data.size - 1, n_out, dtype=np.float32)
        data = np.interp(pos, np.arange(data.size, dtype=np.float32), data)
        rate = target_rate

    pcm = np.clip(data * 32767.0, -32768, 32767).astype("<i2")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm.tobytes())
    return int(pcm.size)


def encode_sfx_for_build(project, sfx_items: list, emit=None) -> dict[str, Path]:
    """{nom de l'effet: fichier à passer à mmutil} pour ceux qu'on ré-encode.

    Les effets sans taux visé n'apparaissent pas : leur fichier d'origine part
    tel quel, et on ne les recopie pas pour rien.
    """
    out_dir = project.build_dir / "sfx"
    settings = project.settings
    encoded: dict[str, Path] = {}
    for sfx, src in sfx_items:
        target = effective_rate(sfx, settings)
        if target <= 0:
            continue
        try:
            with wave.open(str(src)) as w:
                src_rate, src_frames = w.getframerate(), w.getnframes()
        except Exception:  # tolerated: unreadable WAV: check_audio_file reports it
            continue
        if src_rate == target:
            continue
        dst = out_dir / f"{src.stem}.wav"
        try:
            n = resample_wav(src, dst, target)
        except Exception as e:
            if emit:
                emit("diagnostic", build_warning(f"\"{sfx.name}\" not resampled: {e}", "sfx"))
            continue
        if n is None:
            continue
        encoded[sfx.name] = dst
        if emit:
            emit("log_line",
                 f"[sfx] \"{sfx.name}\" {src_rate} → {target} Hz  ({src_frames} → {n} bytes in ROM)")
    return encoded
