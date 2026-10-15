"""
core/sfx_render.py — ce qu'un effet sonore devient avant mmutil : découpé, puis ré-échantillonné.

C'est de l'ENCODAGE, pas de la conversion de format : le même geste que découper un PNG en tuiles et lui allouer une
palette avant de l'envoyer en ROM. Le fichier de `assets/` n'est **jamais** réécrit — l'asset garde ses réglages
(`Sfx.trim_start`, `Sfx.trim_end`, `Sfx.sample_rate`), le build écrit le résultat dans son dossier, et c'est lui que
mmutil reçoit. Remonter le taux ou rouvrir la découpe après coup ne perd donc rien.

Un seul module pour le build ET pour l'écran Son : ce qu'on voit sur l'onde et ce qu'on entend à l'aperçu est
EXACTEMENT ce que la ROM portera (cf. `ui/sound_mixer/box_playback.py`).

Pourquoi ça vaut le détour, mesuré sur la démo : mmutil convertit en 8 bits mono mais **conserve le taux
d'échantillonnage** — un octet par frame. Cinq bruitages en 44,1 kHz pèsent 222,7 Kio ; à 16 kHz — au-dessus de ce
que le mixeur Maxmod restitue — ils tombent à ~83 Kio. Couper la queue de silence d'un effet se lit de même dans le
poids ROM.
"""
from __future__ import annotations

import hashlib
import random
import tempfile
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from core.models.audio import WAV_BITS_OK
from core.wav_edit import apply_fades, fade_in_of, fade_out_of, is_trimmed, kept_range, trim_of

# Largeurs d'échantillon (en octets) que mmutil lit tel quel ; toute autre est décodée ici puis réécrite en 16 bits.
WAV_BITS_OK_BYTES = tuple(bits // 8 for bits in WAV_BITS_OK)


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


def is_edited(sfx) -> bool:
    """L'effet demande un rendu — une découpe ou un fondu : sans l'un ni l'autre, son fichier part tel quel."""
    return is_trimmed(sfx) or fade_out_of(sfx) > 0 or fade_in_of(sfx) > 0


# ── La découpe : cf. `core/wav_edit.py` ────────────────────────────────

def planned_frames(sfx, frames: int, rate: int, target_rate: int) -> int:
    """Les frames — donc les octets de ROM — que l'effet portera : la plage gardée, au taux visé. 0 si la découpe est vide."""
    kept = kept_range(sfx, frames, rate)
    if kept is None:
        return 0
    count = kept[1] - kept[0]
    if target_rate > 0 and target_rate != rate:
        return max(1, round(count * target_rate / rate))
    return count


# ── Le rendu ──────────────────────────────────────────────────────────

def read_wav(path: Path) -> Optional[tuple[np.ndarray, int, int]]:
    """(échantillons float32 entrelacés, taux, nb de canaux), ou None pour une profondeur que ni l'éditeur ni mmutil ne lisent."""
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
    elif width == 3:
        # 24 bits : trois octets little-endian par échantillon, qu'on place en tête d'un entier 32 bits signé.
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        packed = np.zeros((b.shape[0], 4), dtype=np.uint8)
        packed[:, 1:] = b
        data = packed.view("<i4").ravel().astype(np.float32) / 2147483648.0
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        return None
    return data, rate, ch


def render_sfx(src: Path, sfx, target_rate: int) -> Optional[tuple[np.ndarray, int]]:
    """`(échantillons mono float32, taux)` de `src` tel que la ROM le portera : mixé en mono, découpé selon `sfx`, puis
    ré-échantillonné à `target_rate` (0 : le taux du fichier). None si le fichier n'est pas convertible, ou si la
    découpe ne laisse rien. Les fondus (`Sfx.fade_in`, `Sfx.fade_out`) sont cuits dans les premières et les dernières frames du résultat."""
    got = read_wav(src)
    if got is None:
        return None
    data, rate, ch = got
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    kept = kept_range(sfx, int(data.size), rate)
    if kept is None:
        return None
    data = data[kept[0]:kept[1]]

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
    data = apply_fades(data, rate, fade_in_of(sfx), fade_out_of(sfx))
    return data, rate


def varied_pitch(sfx, rng=random) -> float:
    """La hauteur de départ d'UNE lecture de `sfx` : `pitch` ± `pitch_variation` %, uniforme, au dixième de pour cent —
    ce que tire `sfx_play` sur la console (cf. `headers.py`). L'aperçu de l'éditeur s'en sert à chaque ▶."""
    spread = int(getattr(sfx, "pitch_variation", 0) or 0)
    tenths = rng.randint(-10 * spread, 10 * spread)
    return int(getattr(sfx, "pitch", 100) or 100) * (1000 + tenths) / 1000


def preview_file(src: Path, sfx, settings) -> Path:
    """Le fichier que l'aperçu doit jouer pour que l'oreille entende ce que la ROM portera : `src` lui-même quand l'effet
    n'est ni découpé ni ré-échantillonné ni changé de hauteur, sinon son rendu (cf. `write_sfx`), rangé dans le dossier
    temporaire du système sous un nom qui est l'empreinte du fichier ET des réglages — un réglage qui change donne un
    autre fichier, un réglage qui revient retrouve le sien. En cas d'échec (fichier illisible, découpe vide) : `src`,
    l'aperçu joue l'effet entier.

    La hauteur par défaut (`Sfx.pitch`) s'entend en déclarant le rendu à un taux plus haut ou plus bas : mêmes
    échantillons, joués plus vite ou plus lentement — ce que fait la console avec `mm_sound_effect.rate`, sans rien
    changer à la ROM. Le panoramique, lui, ne passe pas par le fichier (toujours mono) : l'aperçu le pose sur l'échantillon
    du module (cf. `wav_to_xm`, `pan`)."""
    try:
        with wave.open(str(src)) as w:
            rate, width = w.getframerate(), w.getsampwidth()
        target = effective_rate(sfx, settings)
        pitch = float(getattr(sfx, "pitch", 100) or 100)      # fractionnaire quand l'aperçu tire une variation
        if width in WAV_BITS_OK_BYTES and not is_edited(sfx) and pitch == 100 and (target <= 0 or target == rate):
            return src
        stamp = f"{src.resolve()}|{src.stat().st_mtime_ns}|{trim_of(sfx)}|{fade_in_of(sfx)}|{fade_out_of(sfx)}|{target}|{pitch}"
        directory = Path(tempfile.gettempdir()) / "backstage_sfx_preview"
        out = directory / f"{hashlib.sha1(stamp.encode('utf-8')).hexdigest()[:16]}.wav"
        if not out.is_file() and write_sfx(src, out, sfx, target, pitch / 100) is None:
            return src
        return out
    except Exception:
        return src


def write_sfx(src: Path, dst: Path, sfx, target_rate: int, rate_factor: float = 1.0) -> Optional[int]:
    """Écrit dans `dst` l'effet `sfx` rendu depuis `src` (cf. `render_sfx`). Rend le nombre de frames écrites, ou None
    si rien n'est écrit.

    Sortie en **16 bits mono** : mmutil descendra lui-même en 8 bits, et lui laisser cette étape évite de quantifier
    deux fois. Le mono est acquis de toute façon — mmutil ne mixe que des échantillons mono.

    `rate_factor` : le taux DÉCLARÉ dans l'en-tête est celui du rendu multiplié par ce facteur. Le build n'en donne jamais
    (la hauteur par défaut se joue à l'exécution) ; l'aperçu s'en sert pour l'entendre (cf. `preview_file`).
    """
    rendered = render_sfx(src, sfx, target_rate)
    if rendered is None:
        return None
    data, rate = rendered
    pcm = np.clip(data * 32767.0, -32768, 32767).astype("<i2")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(max(1, int(round(rate * rate_factor))))
        w.writeframes(pcm.tobytes())
    return int(pcm.size)
