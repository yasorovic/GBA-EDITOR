"""Les TROIS boîtes sonores : MusicBox, JingleBox, SoundBox.

Trois assets distincts, et non trois machines dans un même fichier — décision
du 2026-08-18, après avoir constaté que le fichier unique laissait croire à une
coordination qui n'existe pas. Le matériel n'en offre aucune :

    MusicBox   la couche MODULE — une seule piste, qui boucle. Elle seule est
                continue, donc elle seule a des TRANSITIONS.
    JingleBox  la couche JINGLE — un module joué PAR-DESSUS la musique, sans
                l'arrêter, sans boucler. Il ne remplace jamais la musique : il
                n'y a donc aucune transition entre les deux, seulement une
                superposition.
    SoundBox   les canaux d'EFFETS — ponctuels. Le prochain déclenchement
                prend le nouvel échantillon, il n'y a rien à faire transiter.

Une ACTION est le nom qu'une frame d'animation cite à la place d'un son
concret : « ici, il y a un pas ». L'état courant de la boîte dit lequel. Le mot
n'est pas « emplacement » ni « slot » — `slot` désigne déjà un rang de palette,
de VRAM et de sauvegarde dans ce dépôt, et l'auteur nomme spontanément ces
choses d'après le geste qu'elles sonnent (`PlayerWalk`, `PlayerRun`).

Chaque boîte porte sa propre configuration et son propre espace de noms, et
l'appel Lua nomme la boîte à qui il parle (`music_box.trigger`,
`sound_box.set_state`, `jingle_box.set_state`) : l'auteur sait ce qu'il appelle
sans avoir à se rappeler quelle machine porte quel état.

Rangées avec les données propres au projet, pas avec les ressources importées :
une boîte ne dépend d'aucun fichier extérieur. Même statut que la caméra (v0.6.1).
"""

from dataclasses import dataclass, field, asdict

from core.models.resource import Resource
from core.models import asset_extensions

# Les deux transitions que le matériel tient (cf. v0.8.3). Il n'y en a pas de
# troisième : maxmod n'a qu'une couche de module qui boucle.
TRANSITION_FADE = "fade"       # fondu traversant — creux assumé
TRANSITION_CUT  = "cut"        # coupe à la position — sans creux, en mesure
TRANSITION_KINDS = (TRANSITION_FADE, TRANSITION_CUT)

# Les trois molettes continues du matériel, et elles seules. Tout le reste
# (DRUMLESS <-> complet) est un choix de variante, donc un autre état.
INTENSITY_TARGETS = ("volume", "tempo", "pitch")

# Les trois familles, telles que les nomment les dossiers, l'API Lua et le C.
KIND_MUSIC  = "music_box"
KIND_JINGLE = "jingle_box"
KIND_SOUND  = "sound_box"


# ══════════════════════════════════════════════════════════════════
#  MusicBox — la couche module, la seule qui a des arêtes
# ══════════════════════════════════════════════════════════════════

@dataclass
class MusicState:
    """Un état de la couche musique : ce qui joue, et à quel niveau."""
    name: str = "state"
    music: str = ""            # nom d'une Music ; "" = silence
    loop: bool = True
    level: int = 100           # POURCENTAGE (cf. models/audio.py)
    # « Intensité » porte SA CIBLE, explicitement : un curseur sans cible
    # nommée promettrait un mixeur de couches qui n'existe pas sur cette
    # console.
    intensity_target: str = "volume"
    intensity: int = 100       # % — 100 = valeur neutre de la cible
    # Position du nœud dans le graphe, en pixels de scène. De la donnée
    # d'AUTHORING, pas de l'état d'interface : le build l'ignore, mais deux
    # personnes sur le même projet voient le même dessin, et une disposition
    # recalculée à l'ouverture effacerait le travail de l'auteur à chaque fois.
    x: int = 0
    y: int = 0


@dataclass
class MusicTransition:
    """Une arête du graphe musical.

    `src` vide = « depuis n'importe quel état » : c'est le cas courant d'un
    événement global (« le joueur meurt »), et l'écrire une fois vaut mieux
    qu'une arête par état de départ.
    """
    src: str = ""
    dst: str = ""
    trigger: str = ""
    kind: str = TRANSITION_FADE
    # En FRAMES, pas en millisecondes : c'est l'unité du runtime et celle des
    # transitions de scène (v0.6.2). Une même durée ne doit pas s'écrire de
    # deux façons selon l'écran. Ignorée par une coupe, qui attend la mesure.
    frames: int = 30


@dataclass
class MusicBox(Resource):
    """Les états musicaux d'un projet et les transitions entre eux."""
    sidecar_extension = asset_extensions.MUSIC_BOX
    KIND = KIND_MUSIC

    name: str = "musics"
    states: list = field(default_factory=list)        # list[MusicState]
    transitions: list = field(default_factory=list)   # list[MusicTransition]
    start: str = ""

    def state(self, name: str):
        return next((s for s in self.states if s.name == name), None)

    def duplicate_state_names(self) -> list[str]:
        """Les noms portés par PLUSIEURS états de CETTE boîte.

        Ils rendraient `music_box.trigger` incapable de désigner sa cible — le
        validateur les refuse plutôt que de laisser le build choisir à la place
        de l'auteur. Un homonyme dans une AUTRE boîte, lui, est légitime : les
        trois espaces de noms sont séparés depuis qu'elles sont trois assets.
        """
        seen, dups = set(), []
        for s in self.states:
            if s.name in seen and s.name not in dups:
                dups.append(s.name)
            seen.add(s.name)
        return sorted(dups)

    def referenced_music(self) -> set:
        """Les musiques citées — pour le filtre ROM de la v0.8.1."""
        return {s.music for s in self.states if s.music}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start": self.start,
            "states":      [asdict(s) for s in self.states],        # dérivé des champs
            "transitions": [asdict(tr) for tr in self.transitions],  # de MusicState/Transition
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MusicBox":
        return cls(
            name=d.get("name", "musics"),
            start=d.get("start", ""),
            states=[
                MusicState(name=s.get("name", "state"),
                           music=s.get("music", ""),
                           loop=s.get("loop", True),
                           level=int(s.get("level", 100)),
                           intensity_target=s.get("intensity_target", "volume"),
                           intensity=int(s.get("intensity", 100)),
                           x=int(s.get("x", 0)), y=int(s.get("y", 0)))
                for s in d.get("states", [])
            ],
            transitions=[
                MusicTransition(src=tr.get("src", ""), dst=tr.get("dst", ""),
                                trigger=tr.get("trigger", ""),
                                kind=tr.get("kind", TRANSITION_FADE),
                                frames=int(tr.get("frames", 30)))
                for tr in d.get("transitions", [])
            ],
        )


# ══════════════════════════════════════════════════════════════════
#  Les deux boîtes d'ACTIONS
# ══════════════════════════════════════════════════════════════════

@dataclass
class ActionState:
    """Un état d'une boîte d'ACTIONS : vers quoi chaque action se résout.

    Une action absente de `mapping` ne joue rien dans cet état — c'est
    légitime (pas de bruit de pas en vol) et ça se lit sans réglage dédié.
    """
    name: str = "state"
    mapping: dict = field(default_factory=dict)   # {action: nom d'asset}


@dataclass
class ActionBox(Resource):
    """Une boîte d'ACTIONS : une table actions × états, sans arête.

    Base commune à SoundBox et JingleBox, qui ne diffèrent que par ce qu'une
    action RÉSOUT — un effet ou un module. Ce n'est pas une factorisation
    par ressemblance : c'est une seule structure dont l'élément varie, et deux
    classes complètes auraient dupliqué la sérialisation pour un mot.
    """
    KIND = ""

    name: str = "box"
    actions: list = field(default_factory=list)   # noms d'actions déclarées
    states: list = field(default_factory=list)    # list[ActionState]
    start: str = ""                               # état au démarrage

    def duplicate_state_names(self) -> list[str]:
        """Les noms portés par plusieurs états de CETTE boîte."""
        seen, dups = set(), []
        for s in self.states:
            if s.name in seen and s.name not in dups:
                dups.append(s.name)
            seen.add(s.name)
        return sorted(dups)

    def referenced_assets(self) -> set:
        """Ce que les mappings citent — pour le filtre ROM de la v0.8.1.

        Les actions ne citent rien par elles-mêmes : ce sont les MAPPINGS des
        états qui nomment des assets. Un effet cité seulement ici doit tout de
        même entrer en ROM, sinon sa constante n'existe pas.
        """
        return {v for st in self.states for v in st.mapping.values() if v}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "actions": list(self.actions),
            "start": self.start,
            "states": [asdict(s) for s in self.states],   # dérivé des champs d'ActionState
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ActionBox":
        return cls(
            name=d.get("name", "box"),
            # `slots` : les fichiers écrits avant le renommage du 2026-08-19.
            # Lus, jamais réécrits — la sauvegarde suivante pose « actions ».
            actions=list(d.get("actions", d.get("slots", []))),
            start=d.get("start", ""),
            states=[ActionState(name=s.get("name", "state"),
                                mapping=dict(s.get("mapping", {})))
                    for s in d.get("states", [])],
        )


@dataclass
class SoundBox(ActionBox):
    """Les actions d'EFFETS. Une action résout vers un `Sfx`."""
    sidecar_extension = asset_extensions.SOUND_BOX
    KIND = KIND_SOUND
    name: str = "sounds"


@dataclass
class JingleBox(ActionBox):
    """Les actions de JINGLES. Une action résout vers une `Music`, jouée
    par-dessus la piste en cours sans l'arrêter."""
    sidecar_extension = asset_extensions.JINGLE_BOX
    KIND = KIND_JINGLE
    name: str = "jingles"
