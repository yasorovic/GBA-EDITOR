"""Sfx / Music — assets audio, stockés dans project/{sfx,music}/{name}.json.

La police a quitté ce module pour `core/models/font.py` quand elle a cessé
d'être un stub (glyphes, grille, charset dérivé).

Les formats acceptés (ROADMAP v0.8.1, élargie en v0.8.8) : les quatre modules
que maxmod sait jouer — `.mod`, `.s3m`, `.xm`, `.it` — et `.wav` PCM 8/16 bits
pour les effets, ainsi que pour une musique (encapsulé en module au build). Tout le reste est refusé à l'import par `check_audio_file`.

La hauteur, le volume et le panning se surchargent À L'APPEL depuis la v0.8.6 :
`sfx.play` rend une référence, et les conversions vers les trois graduations du
matériel vivent plus bas dans ce fichier."""

from dataclasses import dataclass, field
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
PAN_CENTER  = 128      # mmEffectPanning : 0 = gauche, 255 = droite
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


# ── Tempo et hauteur d'un MODULE ──────────────────────────────────────
#
# `mmSetModuleTempo` et `mmSetModulePitch` prennent un facteur Q10 de 0x200 à
# 0x800 : 0,5× à 2,0× (maxmod.h). Ce n'est pas un BPM — le BPM du fichier reste
# de l'information, jamais un réglage. En pourcentage, comme tout le reste du
# fichier : 100 = le fichier tel qu'il est.

TEMPO_MIN = 50          # % — 0x200
TEMPO_MAX = 200         # % — 0x800
PITCH_MIN = 50
PITCH_MAX = 200

# Les fondus sont en FRAMES, comme les transitions de la MusicBox : une durée ne
# s'écrit pas de deux façons selon l'écran. Dix secondes bornent un réglage
# raisonnable ; au-delà, c'est une transition, pas un fondu.
FADE_MAX_FRAMES = 600

_MODULE_FACTOR_NORMAL = 1024    # Q10 : 1,0×
_MODULE_FACTOR_MIN = 0x200
_MODULE_FACTOR_MAX = 0x800


def tempo_to_module(percent: int) -> int:
    """% → l'argument de `mmSetModuleTempo` (Q10, 0x200–0x800)."""
    return max(_MODULE_FACTOR_MIN,
               min(_MODULE_FACTOR_MAX, round(percent * _MODULE_FACTOR_NORMAL / VOLUME_MAX)))


def pitch_to_module(percent: int) -> int:
    """% → l'argument de `mmSetModulePitch` (Q10, 0x200–0x800)."""
    return max(_MODULE_FACTOR_MIN,
               min(_MODULE_FACTOR_MAX, round(percent * _MODULE_FACTOR_NORMAL / VOLUME_MAX)))


def tempo_to_module_expr(c_expr: str) -> str:
    """La même conversion, pour un tempo qui n'existe qu'À L'EXÉCUTION (cf. `volume_to_module_expr`).
    Le C ne borne pas ici : `music_set_tempo` le fait, dans la plage de maxmod."""
    return f"(({c_expr}) * {_MODULE_FACTOR_NORMAL} / {VOLUME_MAX})"


def pitch_to_module_expr(c_expr: str) -> str:
    """Idem pour la hauteur de module."""
    return f"(({c_expr}) * {_MODULE_FACTOR_NORMAL} / {VOLUME_MAX})"


def pitch_to_rate(percent: int) -> int:
    """% → facteur de hauteur (1024 = hauteur normale)."""
    return max(1, min(4 * _RATE_NORMAL, round(percent * _RATE_NORMAL / VOLUME_MAX)))


def panning_to_hardware(panning: int) -> int:
    """−100..+100 → l'échelle de `mmEffectPanning` (0–255, centrée sur 128)."""
    p = max(-PANNING_MAX, min(PANNING_MAX, panning))
    return PAN_CENTER + round(p * _PAN_SIDE / PANNING_MAX)


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
    return f"({PAN_CENTER} + ({c_expr}) * {_PAN_SIDE} / {PANNING_MAX})"


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
    # La plage GARDÉE du fichier, en ms depuis son début. Le fichier n'est jamais touché : le build ne rend que cette
    # plage (cf. `core/sfx_render.py`), et le poids ROM suit. `trim_end` à 0 = jusqu'à la fin du fichier ; les deux à
    # 0 = l'effet entier, ce que lisent aussi les sidecars d'avant ces champs.
    trim_start: int = 0
    trim_end: int = 0
    # Hauteur et panoramique PAR DÉFAUT : celles avec lesquelles l'effet démarre. La règle du volume — la ressource
    # propose, l'API surcharge : `sfx:set_pitch` / `sfx:set_panning` posent une valeur ABSOLUE sur une lecture, quelle que
    # soit celle de la ressource. Pourcentage de la hauteur d'origine (100 = le fichier tel quel, 200 = une octave plus
    # haut) et −100 (gauche) .. +100 (droite). Rien ne s'écrit dans la ROM : la console les lit dans deux tables, au
    # lancement de l'effet (cf. `sfx_play`).
    pitch: int = 100
    panning: int = 0
    # Variation aléatoire de la hauteur : à chaque lecture l'effet démarre à `pitch` ± ce pourcentage, tiré au hasard
    # (0 = toujours la même). Ce qui rend naturels les sons qui se répètent — pas, coups, pièces. Le tirage a son propre
    # générateur, côté console : un effet qui varie ne consomme jamais le `math.rand` du jeu.
    pitch_variation: int = 0
    # Fondu de sortie, en FRAMES (1/60 s) comme tous les fondus de l'éditeur : l'effet descend linéairement à zéro sur ses
    # dernières frames. Cuit dans l'échantillon par le build (cf. `core/sfx_render.py`) — rien ne se calcule sur la console ;
    # c'est ce qui évite le clic d'une découpe qui tombe en plein signal.
    fade_out: int = 0
    # Fondu d'entrée, même règle et même unité : l'effet monte linéairement depuis zéro sur ses premières frames, cuit dans
    # l'échantillon par le build. Le pendant du fondu de sortie pour une découpe qui commence en plein signal.
    fade_in: int = 0
    # Effet PROTÉGÉ : maxmod ne peut jamais lui voler son canal quand les canaux du projet sont tous pris. Sans cette case, un
    # effet lancé sans référence (`sfx.play("Bip")` posé seul) reste volable — le plus faible cède — ; avec elle, il tient son
    # canal jusqu'à la fin de son échantillon, quoi que fasse l'appelant. Le build le range dans une table (`sfx_play`).
    protected: bool = False


# La plage du réglage de hauteur d'un effet : deux octaves de chaque côté du fichier. `mm_sound_effect.rate` est un
# facteur 6.10 que `pitch_to_rate` borne à 1–4096 ; en dessous d'un quart, un effet n'est plus qu'un grondement.
SFX_PITCH_MIN = 25
SFX_PITCH_MAX = 400
# La variation aléatoire s'écrit ± en % de la hauteur de départ ; à 50 %, l'effet va d'une demi à une fois et demie sa hauteur.
SFX_PITCH_VARIATION_MAX = 50


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

# Profondeurs qu'un WAV peut avoir à l'import, effet, musique ou jingle : l'éditeur décode lui-même le 24 et le 32 bits
# (`core/sfx_render.read_wav`) et ne passe à mmutil qu'un 16 bits écrit dans le dossier de build (effet), ou un module
# (musique, jingle) — jamais le fichier d'origine. `WAV_BITS_OK` reste ce que mmutil lit tel quel.
WAV_BITS_DECODED = WAV_BITS_OK + (24, 32)


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


# ── Les sections d'une musique ────────────────────────────────────────
#
# Une section est une plage NOMMÉE du morceau, que l'auteur pose par-dessus le
# fichier sans jamais le toucher (ROADMAP « L'asset .music »). L'unité dépend de
# la source, et le sidecar l'écrit lui-même (`Music.unit`) :
#
#   "order"  un module tracker — un INDEX BRUT de la table d'ordres, celui que
#            `mmGetPosition()` rend (cf. engine_emulation/module_model.ORDER_SKIP) ;
#   "ms"     un WAV — des millisecondes depuis le début de la piste.
#
# Les deux sont DEMI-OUVERTES : [start, end). La boucle saute dès que la
# position atteint `end`, et deux sections voisines (4–12 puis 12–16) se
# touchent sans se recouvrir. L'écran écrit « ordres 04–11 » pour [4, 12) : c'est
# à lui de traduire, le modèle n'a qu'une convention.

UNIT_ORDER = "order"
UNIT_MS    = "ms"
MUSIC_UNITS = (UNIT_ORDER, UNIT_MS)


@dataclass
class MusicSection:
    name: str = "section"
    color: str = ""            # "#RRGGBB" ; vide = l'écran en choisit une selon le rang
    start: int = 0
    end: int = 0               # exclu
    loop: bool = False         # cette section PEUT être jouée en boucle

    @classmethod
    def from_dict(cls, d: dict) -> "MusicSection":
        return cls(name=str(d.get("name", "section")), color=str(d.get("color", "")),
                   start=int(d.get("start", 0)), end=int(d.get("end", 0)),
                   loop=bool(d.get("loop", False)))


# ── Les repères d'une musique ─────────────────────────────────────────
#
# Un repère déclenche un SON quand la lecture atteint une position du morceau (ROADMAP « Des déclencheurs sur la
# musique »). Quatre natures, les quatre façons dont l'éditeur de sprites pose déjà un son sur une frame, moins
# l'appel d'événement (qui n'a pas encore de destinataire : une musique n'a pas d'acteur) :
#
#   "sound_action"   une ACTION de SoundBox : l'état courant de la boîte dit vers quel effet elle pointe ;
#   "jingle_action"  une ACTION de JingleBox, même principe, vers un jingle ;
#   "sfx"            un effet nommé, direct ;
#   "jingle"         un jingle nommé, direct.
#
# La position est dans l'UNITÉ de la musique, comme une section (`Music.unit`) : un index d'ordre pour un module,
# des millisecondes pour un WAV. Elle est atteinte à CHAQUE passage — chaque tour d'une boucle la rejoue.

CUE_SOUND_ACTION  = "sound_action"
CUE_JINGLE_ACTION = "jingle_action"
CUE_SFX           = "sfx"
CUE_JINGLE        = "jingle"
CUE_KINDS = (CUE_SOUND_ACTION, CUE_JINGLE_ACTION, CUE_SFX, CUE_JINGLE)
# L'ORDRE est le code C de `music_cue_fire` (cf. runtime_codegen/sound_emit).


@dataclass
class MusicCue:
    position: int = 0
    kind: str = CUE_SFX
    target: str = ""           # un nom d'action (SoundBox / JingleBox), d'effet ou de jingle selon `kind`

    @classmethod
    def from_dict(cls, d: dict) -> "MusicCue":
        kind = str(d.get("kind", CUE_SFX))
        return cls(position=int(d.get("position", 0)),
                   kind=kind if kind in CUE_KINDS else CUE_SFX,
                   target=str(d.get("target", "")))


@dataclass
class Music(_MigrateVolumeMixin, Resource):
    sidecar_extension = asset_extensions.MUSIC
    name: str = "music"
    asset: Optional[str] = None
    loop: bool = True
    volume: int = 100          # POURCENTAGE — cf. _MigrateVolumeMixin
    # Le sidecar surcharge, le fichier propose : ce qui suit ne modifie JAMAIS
    # le fichier source, le build l'applique. Un sidecar d'avant ces champs relit
    # les défauts ci-dessous, qui sont exactement l'ancien comportement.
    unit: str = UNIT_ORDER
    sections: list = field(default_factory=list)       # list[MusicSection]
    loop_section: str = ""     # nom de la section bouclée ; vide = tout le morceau
    # Valeurs PAR DÉFAUT, que l'API surcharge à l'appel — la règle du volume
    # depuis la v0.8.6. Pourcentages : 100 = le fichier tel qu'il est.
    tempo: int = 100
    pitch: int = 100
    fade_in: int = 0           # frames
    fade_out: int = 0          # frames
    # WAV seulement : le taux auquel la piste devient un module. 0 = le défaut
    # (`wav_module.WAV_MUSIC_RATE`). Un taux plus bas allège la ROM, au prix des aigus.
    sample_rate: int = 0
    # WAV seulement : la plage GARDÉE du fichier, en ms depuis son début (même convention qu'un effet, cf. `core/wav_edit.py` :
    # fin à 0 = jusqu'au bout, les deux à 0 = le fichier entier). Le fichier n'est jamais réécrit : le build et l'aperçu ne
    # rendent que cette plage. Les SECTIONS d'une musique WAV sont dans le temps de la plage gardée — celui de l'onde qu'on voit
    # et qu'on entend — et suivent le son quand la plage bouge (cf. `music_structure.retrim`). Un module tracker ne se rogne
    # pas : ses plages sont des sections en positions d'ordre.
    trim_start: int = 0
    trim_end: int = 0
    # Les sons que la lecture déclenche en atteignant une position (cf. `MusicCue`). Dans l'unité de `unit`, comme les
    # sections : ils suivent le son quand la plage d'un WAV bouge (`music_structure.retrim`).
    cues: list = field(default_factory=list)           # list[MusicCue]

    @classmethod
    def from_dict(cls, d: dict):
        obj = super().from_dict(d)
        obj.sections = [MusicSection.from_dict(sec) for sec in obj.sections
                        if isinstance(sec, dict)]
        obj.cues = [MusicCue.from_dict(cue) for cue in obj.cues if isinstance(cue, dict)]
        return obj

    def add_cue(self, position: int, kind: str, target: str) -> "MusicCue":
        """Pose un repère et le rend ; la liste reste triée par position (l'ordre où l'on les lit, et où le build les émet)."""
        cue = MusicCue(max(0, int(position)), kind, target)
        self.cues.append(cue)
        self.cues.sort(key=lambda c: c.position)
        return cue

    def remove_cue(self, cue: "MusicCue") -> None:
        self.cues = [c for c in self.cues if c is not cue]

    def section(self, name: str):
        return next((s for s in self.sections if s.name == name), None)

    def unique_section_name(self, base: str = "Loop") -> str:
        """`base`, puis `base 2`, `base 3`… : la première forme libre dans CETTE musique."""
        taken = {s.name for s in self.sections}
        if base not in taken:
            return base
        n = 2
        while f"{base} {n}" in taken:
            n += 1
        return f"{base} {n}"

    def add_section(self, start: int, end: int, name: str = "", color: str = "",
                    loop: bool = True) -> "MusicSection":
        """Ajoute une section et la rend. Son nom est unique ; la première section qui boucle
        devient la boucle par défaut — une musique qui n'a qu'une boucle n'a pas à la désigner."""
        section = MusicSection(self.unique_section_name(name or "Loop"), color, start, end, loop)
        self.sections.append(section)
        if loop and not self.loop_section:
            self.loop_section = section.name
        return section

    def remove_section(self, name: str) -> None:
        """Retire une section ET ce qui la cite : la boucle par défaut ne doit pas pendre dans le
        vide. Si d'autres sections bouclent, la première reprend ce rôle."""
        self.sections = [s for s in self.sections if s.name != name]
        if self.loop_section == name:
            self.loop_section = next((s.name for s in self.sections if s.loop), "")

    def rename_section(self, old: str, new: str) -> None:
        """Renomme une section ET ce qui la cite : `loop_section` ne doit pas
        pendre dans le vide quand l'auteur la renomme."""
        sec = self.section(old)
        if sec is None:
            return
        sec.name = new
        if self.loop_section == old:
            self.loop_section = new


# maxmod ne donne que 4 canaux à la couche jingle (doc `mmJingle`) : un module
# qui en demande plus serait joué tronqué, et un morceau tronqué ne s'entend pas
# comme une erreur, il s'entend comme un morceau raté.
JINGLE_MAX_CHANNELS = 4

# La politique d'un jingle envers la musique. L'ORDRE est le code C de `music_jingle` (0 = mix, 1 = duck, 2 = pause).
JINGLE_MIX, JINGLE_DUCK, JINGLE_PAUSE = "mix", "duck", "pause"
JINGLE_POLICIES = (JINGLE_MIX, JINGLE_DUCK, JINGLE_PAUSE)
JINGLE_DUCK_LEVEL_DEFAULT = 30       # % : assez bas pour qu'une fanfare passe devant, assez haut pour que la musique reste là
JINGLE_DUCK_RELEASE_DEFAULT = 30     # frames : une demi-seconde


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
    # Ce que devient la MUSIQUE pendant que ce jingle sonne (le jingle a sa propre couche : elle ne s'arrête pas d'elle-même).
    # `music_policy` : « mix » (elle continue, le défaut — l'ancien comportement), « duck » (elle descend à `duck_level` %
    # de son volume, puis remonte en `duck_release` frames à la fin du jingle) ou « pause » (elle est suspendue, puis
    # reprend là où elle s'était arrêtée). La console en tient un seul réglage par jingle : un seul jingle sonne à la fois.
    music_policy: str = JINGLE_MIX
    duck_level: int = JINGLE_DUCK_LEVEL_DEFAULT      # pourcentage du volume de la musique, tant que le jingle sonne
    duck_release: int = JINGLE_DUCK_RELEASE_DEFAULT  # frames, pour que la musique remonte
    # Un jingle en MODULE se coupe aux positions d'ordre, pas en ms (cf. `core/module_trim.py`) : l'entrée de la table brute
    # où il commence, et celle où il finit (exclue ; 0 = jusqu'au bout). Le fichier n'est jamais réécrit : le build et
    # l'aperçu lisent le module coupé. Sans effet sur un WAV, qui a sa propre plage (`trim_start` / `trim_end`).
    order_start: int = 0
    order_end: int = 0

    @classmethod
    def from_dict(cls, d: dict):
        obj = super().from_dict(d)
        if obj.music_policy not in JINGLE_POLICIES:           # un sidecar écrit à la main : le défaut, pas un plantage
            obj.music_policy = JINGLE_MIX
        obj.duck_level = max(0, min(100, int(obj.duck_level)))
        obj.duck_release = max(0, min(FADE_MAX_FRAMES, int(obj.duck_release)))
        obj.order_start, obj.order_end = max(0, int(obj.order_start)), max(0, int(obj.order_end))
        return obj

    def runtime_policy(self) -> tuple[int, int, int]:
        """(code, niveau, remontée) tels que `music_jingle` les lit : le niveau sur l'échelle 0–1024 du module, la remontée en
        frames. Le niveau et la remontée ne valent que pour « duck » : les autres politiques les émettent à leur neutre."""
        code = JINGLE_POLICIES.index(self.music_policy)
        if self.music_policy != JINGLE_DUCK:
            return code, volume_to_module(100), 0
        return code, volume_to_module(self.duck_level), max(0, min(FADE_MAX_FRAMES, int(self.duck_release)))
