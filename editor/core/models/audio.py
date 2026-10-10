"""Sfx / Music — assets audio, stockés dans project/{sfx,music}/{name}.json.

La police a quitté ce module pour `core/models/font.py` quand elle a cessé
d'être un stub (glyphes, grille, charset dérivé).

Les formats acceptés (ROADMAP v0.8.1, élargie en v0.8.8) : les quatre modules
que maxmod sait jouer — `.mod`, `.s3m`, `.xm`, `.it` — et `.wav` PCM 8/16 bits
pour les effets, ainsi que pour une musique (encapsulé en module au build). Tout le reste est refusé à l'import par `check_audio_file`.

La hauteur, le volume et le panning se surchargent À L'APPEL depuis la v0.8.6 :
`sfx.play` rend une référence, et les conversions vers les trois graduations du
matériel vivent plus bas dans ce fichier."""

from dataclasses import dataclass
from typing import Optional

from core.models.resource import Resource
from core.models import asset_extensions


# ── Les niveaux sont des POURCENTAGES ─────────────────────────────────
#
# maxmod a DEUX échelles de volume, et les confondre est le défaut que ce
# passage corrige (ROADMAP v0.8.5) :
#
#   mm_sound_effect.volume   0–255   (mm_byte, par effet)
#   mmSetModuleVolume        0–1024
#   mmSetEffectsVolume       0–1024
#
# Le modèle passait 0–255 aux trois. `Music.volume = 255` — le défaut « à
# fond » — réglait donc le module au QUART de son niveau, et la musique était
# quatre fois trop basse que les effets depuis la première version.
#
# Un pourcentage n'appartient à aucun registre : il ne peut donc pas être
# confondu avec l'un d'eux, et c'est chaque émission qui convertit vers
# l'échelle de sa cible. Multiplier par quatre au moment d'émettre aurait
# corrigé le symptôme en laissant le piège dans le modèle.

VOLUME_MAX = 100

# Les deux plages matérielles, nommées une fois pour toutes.
_EFFECT_FULL = 255      # mm_byte, volume d'un effet
_MODULE_FULL = 1024     # scaler de module et scaler d'effets


def volume_to_effect(percent: int) -> int:
    """% → l'échelle de `mm_sound_effect.volume` (0–255)."""
    return max(0, min(_EFFECT_FULL, round(percent * _EFFECT_FULL / VOLUME_MAX)))


def volume_to_module(percent: int) -> int:
    """% → l'échelle de `mmSetModuleVolume` / `mmSetEffectsVolume` (0–1024)."""
    return max(0, min(_MODULE_FULL, round(percent * _MODULE_FULL / VOLUME_MAX)))


# ── Les deux autres graduations du matériel ───────────────────────────
#
# La hauteur est un FACTEUR 6.10 (`mm_sound_effect.rate`) : 1024 = la hauteur
# d'origine de l'échantillon. Le panning est un OFFSET : 0 à gauche, 128 au
# centre, 255 à droite — d'où une conversion qui n'est pas une mise à
# l'échelle, mais un décalage autour du centre (ROADMAP v0.8.6).

_RATE_NORMAL = 1024     # mm_sound_effect.rate — facteur 6.10, 1024 = normale
_PAN_CENTER  = 128      # mmEffectPanning : 0 = gauche, 255 = droite
_PAN_SIDE    = 127      # ce qu'un côté vaut, depuis le centre

PANNING_MAX = 100       # l'API Lua écrit −100..+100, centrée sur 0


# ── Les canaux logiciels, et ce qu'ils coûtent ────────────────────────
#
# Mesuré au désassemblage de `mmInitDefault` (ROADMAP v0.8.8) : elle alloue
# `92 × n + 1056` octets, soit 40 o de voie de module, 28 o de voie active et
# 24 o de voie de mixage par canal, plus le tampon de mixage du mode 16 kHz.
# Les trois tailles sont aussi dans `maxmod.h` (MM_SIZEOF_MODCH/ACTCH/MIXCH) —
# on les nomme ici pour que le chiffre affiché à l'auteur vienne d'un endroit,
# pas d'une constante recopiée dans un tooltip.

SOUND_CHANNELS_MIN = 4      # sous 4, un module ordinaire ne tient pas
SOUND_CHANNELS_MAX = 32     # le masque de canaux de maxmod est un mot 32 bits
SOUND_HANDLE_SLOTS = 16     # la table de RÉFÉRENCES, indépendante du nombre de canaux

_CHANNEL_BYTES = 40 + 28 + 24    # MM_SIZEOF_MODCH + _ACTCH + _MIXCH
_MIX_BUFFER_BYTES = 1056         # MM_MIXLEN_16KHZ — le mode que mmInitDefault choisit


def sound_channels_bytes(channels: int) -> int:
    """Ce que `mmInitDefault` alloue sur le tas pour ce nombre de canaux."""
    return _CHANNEL_BYTES * int(channels) + _MIX_BUFFER_BYTES


def pitch_to_rate(percent: int) -> int:
    """% → facteur de hauteur (1024 = hauteur normale)."""
    return max(1, min(4 * _RATE_NORMAL, round(percent * _RATE_NORMAL / VOLUME_MAX)))


def panning_to_hardware(panning: int) -> int:
    """−100..+100 → l'échelle de `mmEffectPanning` (0–255, centrée sur 128)."""
    p = max(-PANNING_MAX, min(PANNING_MAX, panning))
    return _PAN_CENTER + round(p * _PAN_SIDE / PANNING_MAX)


# ── Les mêmes conversions, pour une valeur qui n'existe qu'À L'EXÉCUTION ──
#
# Un pourcentage écrit dans un script peut être un littéral — converti ici, au
# build, comme les niveaux lus sur une ressource — ou une expression
# (`global.Musique`), qui n'a de valeur que sur la console. Les deux
# formes vivent CÔTE À CÔTE pour qu'aucune ne dérive de l'autre : même
# constante, même graduation, seul le moment change. Le C tronque là où Python
# arrondit — un demi-cran sur 255, inaudible, et le dire vaut mieux que de
# recopier un arrondi en C pour le plaisir de la symétrie.

def volume_to_effect_expr(c_expr: str) -> str:
    return f"(({c_expr}) * {_EFFECT_FULL} / {VOLUME_MAX})"


def volume_to_module_expr(c_expr: str) -> str:
    return f"(({c_expr}) * {_MODULE_FULL} / {VOLUME_MAX})"


def pitch_to_rate_expr(c_expr: str) -> str:
    return f"(({c_expr}) * {_RATE_NORMAL} / {VOLUME_MAX})"


def panning_to_hardware_expr(c_expr: str) -> str:
    return f"({_PAN_CENTER} + ({c_expr}) * {_PAN_SIDE} / {PANNING_MAX})"


class _MigrateVolumeMixin:
    """Relit un `volume` écrit sur l'ancienne échelle 0–255.

    Au-dessus de 100, la valeur ne peut PAS être un pourcentage : elle vient
    forcément de l'ancien format et se convertit exactement. En dessous, elle
    est ambiguë — mais les 110 ressources audio du projet de démo étaient
    toutes au défaut 255, donc aucun réglage réel n'existe dans cette zone.
    """

    @classmethod
    def from_dict(cls, d: dict):
        obj = super().from_dict(d)
        if obj.volume > VOLUME_MAX:
            obj.volume = round(obj.volume * VOLUME_MAX / _EFFECT_FULL)
        return obj


@dataclass
class Sfx(_MigrateVolumeMixin, Resource):
    sidecar_extension = asset_extensions.SFX
    name: str = "sfx"
    asset: Optional[str] = None
    volume: int = 100          # POURCENTAGE — cf. _MigrateVolumeMixin
    # Taux d'échantillonnage cible, en Hz. 0 = suit le défaut du projet
    # (`ProjectSettings.sfx_sample_rate`), lui-même à 0 = on garde le taux du
    # fichier. Par effet et non seulement par projet : un bip de menu et une
    # nappe d'ambiance n'ont ni la même durée ni le même contenu spectral.
    #
    # Le ré-échantillonnage a lieu au BUILD, vers le dossier de build ; le
    # fichier de `assets/` n'est jamais réécrit. On peut donc remonter le taux
    # après coup sans avoir rien perdu (ROADMAP v0.8.1).
    sample_rate: int = 0


# Extensions reconnues dans assets/sfx/ et assets/music/ (fichiers bruts
# sans sidecar) — utilisées à la fois par la resynchronisation au chargement
# du projet (Project.load) et par le ProjectWatcher pour le live-reload.
#
# La règle qui produit ces deux listes (ROADMAP v0.8.1) : on n'accepte que ce
# que la chaîne sait CONSTRUIRE et que l'éditeur sait FAIRE ÉCOUTER.
#   - musique : les QUATRE formats de maxmod, depuis la v0.8.8. La liste ne
#     s'est pas allongée par exception : c'est l'aperçu qui a rattrapé le
#     matériel (engine_emulation/ lit maintenant XM, S3M et IT), donc la règle
#     rend quatre entrées au lieu d'une. Le refus d'hier était une limite de
#     l'éditeur, pas de la console — et c'était le seul point du jalon qui
#     contraignait le métier de quelqu'un d'autre.
#   - effets  : mmutil ne convertit que le wav. Ni .ogg ni .mp3 sans embarquer
#     un décodeur, pour une source qui finit de toute façon en 8 bits.
#
# Elles sont la SEULE source : les filtres des dialogues d'import en dérivent
# (file_dialog_filter) au lieu d'être réécrits à la main.
SFX_FILE_EXTS   = {".wav"}
MUSIC_FILE_EXTS = {".mod", ".xm", ".s3m", ".it", ".wav"}
# `.wav` y est un cas à part : maxmod ne joue pas de WAV en musique, c'est le
# build qui l'encapsule en module (`core/wav_module.py`). Il se reconnaît donc
# à son extension ET à son dossier — dans assets/sfx/, c'est un effet.
WAV_MUSIC_EXT = ".wav"

# `check_audio_file` vit dans `core/resources/asset_reconciliation.py` : elle doit LIRE
# un module pour le valider, donc importer `core.engine_emulation` — et une
# donnée de projet (`core.models`) n'a pas le droit d'importer la couche
# au-dessus d'elle. Les deux listes, elles, restent ici : ce sont bien des
# faits sur le format, pas un service.

# Profondeurs que mmutil sait convertir. Au-delà il écrit « Unsupported
# bit-depth. », sort quand même avec le code 0, ET émet le #define : la ROM se
# construit et l'effet est muet. C'est un FAIT sur le format, donc il vit ici ;
# c'est `asset_reconciliation.check_audio_file` qui s'en sert pour dire non.
WAV_BITS_OK = (8, 16)


def file_dialog_filter(label: str, exts) -> str:
    """Filtre QFileDialog dérivé d'une des deux listes ci-dessus.

    Pas d'entrée « Tous (*) » : elle rouvrirait exactement la porte que la
    liste ferme.
    """
    return f"{label} ({' '.join(sorted('*' + e for e in exts))})"


def sfx_rom_bytes(path) -> Optional[int]:
    """Ce que l'effet pèsera dans la ROM, ou None s'il est illisible.

    mmutil convertit en 8 bits mono mais CONSERVE le taux d'échantillonnage :
    c'est donc exactement un octet par frame, quel que soit le format d'entrée.
    Vérifié sur WALLBOUNCE.wav — 13 558 frames, 13 558 octets de données dans
    le soundbank.

    De là vient le seul chiffre qui compte pour l'auteur : les cinq effets de
    Pong, en 44,1 kHz, occupent 222,6 Kio d'une ROM de 810 Kio.
    """
    from pathlib import Path
    import wave
    try:
        with wave.open(str(Path(path))) as w:
            return w.getnframes()
    except Exception:
        return None


@dataclass
class Music(_MigrateVolumeMixin, Resource):
    sidecar_extension = asset_extensions.MUSIC
    name: str = "music"
    asset: Optional[str] = None
    loop: bool = True
    volume: int = 100          # POURCENTAGE — cf. _MigrateVolumeMixin


# maxmod ne donne que 4 canaux à la couche jingle (doc `mmJingle`) : un module
# qui en demande plus serait joué tronqué, et un morceau tronqué ne s'entend pas
# comme une erreur, il s'entend comme un morceau raté.
JINGLE_MAX_CHANNELS = 4


@dataclass
class Jingle(Music):
    """Un module joué PAR-DESSUS la musique (`music.jingle`, JingleBox).

    Même fichier, mêmes champs qu'une `Music` : ce qui les distingue n'est écrit
    nulle part dans le module, c'est le DOSSIER où il vit — `assets/jingles/`
    contre `assets/music/`. Une classe à part plutôt qu'un drapeau : le rôle ne
    peut pas diverger de l'emplacement du fichier, et chaque écran, chaque
    contrôle demande l'une ou l'autre famille par son nom."""
    sidecar_extension = asset_extensions.JINGLE
    name: str = "jingle"
