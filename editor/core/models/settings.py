"""Settings globaux du projet + variables déclarées explicitement (globals/constants)."""

import unicodedata
from dataclasses import dataclass, field


# ── Langues (ROADMAP v0.9) ────────────────────────────────────────
# Une langue DÉCLARÉE, jamais devinée. C'est la déclaration qui lie une langue
# à son fichier de traduction et à ses polices — pas un suffixe de nom de
# fichier : `font_de.fnt` est une praticité au moment d'importer, pas une règle
# de résolution. Une règle tirée d'un nom casse au premier renommage et ne se
# vérifie nulle part, ce que la convention `<asset>_name` du graphe de
# dépendances interdit déjà partout ailleurs.

def lang_code(s: str) -> str:
    """Code de langue utilisable comme nom de fichier : `pt-BR` → `pt_br`.

    Le code n'est pas qu'un libellé : c'est lui qui NOMME le fichier side
    (`texts_pt_br.json`). Un espace ou un accent y produirait un fichier
    impossible à retrouver sur un autre système."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    out = "".join(c.lower() if c.isalnum() else "_" for c in s)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")[:12]


@dataclass
class Language:
    """Une langue du jeu et, si nécessaire, sa police par défaut."""
    code: str = ""      # `de` — identité, et le nom du fichier side
    name: str = ""      # `Deutsch` — libellé lisible
    # Remplace ProjectSettings.default_font dans cette langue. Les autres
    # FontAsset ne sont jamais remappées par la langue : leur propre chaîne de
    # sources porte leur couverture et conserve donc leur intention graphique.
    default_font: str = ""

    def to_dict(self) -> dict:
        d = {"code": self.code, "name": self.name}
        if self.default_font:
            d["default_font"] = self.default_font
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Language":
        return cls(
            code=lang_code(d.get("code", "")),
            name=str(d.get("name", "")),
            default_font=str(d.get("default_font", "") or ""),
        )


# ── Inputs ─────────────────────────────────────────────────────────
# Les 10 boutons physiques du GBA, dans l'ordre du boîtier. SOURCE UNIQUE : ce
# fichier est dans `core.models` (le socle), la seule couche que tout le monde a
# le droit d'importer. `scripting/checker.py` (`VALID_KEYS`) et l'UI
# (`inputs_card.py`) l'importent d'ici — le socle, lui, ne peut pas remonter vers
# eux (cf. check_architecture, INTERDITS), d'où le sens des imports.
BUTTON_NAMES: tuple = ("up", "down", "left", "right", "a", "b", "l", "r", "start", "select")


@dataclass
class InputBinding:
    """Une action de jeu nommée, liée à un ou plusieurs boutons pressés
    ENSEMBLE — un combo à un seul bouton est le cas courant, à plusieurs il
    en fait un vrai combo (ex: {up, a} pour un dash).

    Le nom devient une clé utilisable dans les scripts, par exemple
    `input:pressed("jump")`. Les directions de la croix sont des boutons au
    même titre que A/B : `jump = up` et `dash = right + a` ne demandent donc
    aucun cas spécial au runtime.

    Décision de l'auteur (2026-09-27, après coup) : un ACCORD simple reste des
    cases à cocher (l'écran d'avant ce chantier, jugé plus clair) — le
    mini-langage complet (`+`/`-`/`(a|b)`/mouvements) ne sert plus qu'aux
    SÉQUENCES, cf. `InputSequence`. `input:held/pressed/released/buffered` ne
    lisent donc que des accords, jamais une séquence — les deux ne partagent
    plus le même espace de noms côté modèle (même s'ils restent tous deux des
    clés `input:...(nom)` valides côté script)."""
    name: str = ""
    buttons: list = field(default_factory=list)   # sous-ensemble de BUTTON_NAMES

    def to_dict(self) -> dict:
        d = {"name": self.name}
        if self.buttons:
            d["buttons"] = list(self.buttons)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "InputBinding":
        return cls(
            name=str(d.get("name", "")),
            buttons=[b for b in (d.get("buttons") or []) if b in BUTTON_NAMES],
        )


@dataclass
class InputSequence:
    """Une séquence de boutons nommée — un mouvement (quart de cercle, demi-
    cercle, dragon punch, ou une composition personnalisée) reconnu par
    `input:get_sequence("nom")`. Expression dans le mini-langage complet
    (ROADMAP « Les inputs personnalisés » : `+` accord, `-` pas suivant,
    `(a|b)` alternative, mouvements). Rôle distinct d'`InputBinding` : un
    accord se lit avec held/pressed/released/buffered, une séquence avec
    get_sequence — jamais l'inverse, décision de l'auteur (2026-09-27)."""
    name: str = ""
    expression: str = ""
    window: int = 15   # fenêtre entre deux pas

    def to_dict(self) -> dict:
        d = {"name": self.name, "expression": self.expression}
        if self.window != 15:
            d["window"] = self.window
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "InputSequence":
        return cls(
            name=str(d.get("name", "")),
            expression=str(d.get("expression", "") or ""),
            window=int(d.get("window", 15) or 15),
        )


@dataclass
class InputAxis:
    """Un axe scalaire déclaré (ROADMAP « Les inputs personnalisés ») :
    remappe la croix, ou pilote un axe avec d'autres boutons/actions, sans
    toucher au script. `negative`/`positive` sont un nom de bouton ou
    d'action — jamais `horizontal`/`vertical` (réservés à la croix par
    défaut, toujours présente, même dans un projet qui ne déclare aucun axe)."""
    name: str = ""
    negative: str = ""
    positive: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "negative": self.negative, "positive": self.positive}

    @classmethod
    def from_dict(cls, d: dict) -> "InputAxis":
        return cls(
            name=str(d.get("name", "")),
            negative=str(d.get("negative", "")),
            positive=str(d.get("positive", "")),
        )


@dataclass
class InputMovement:
    """Un mouvement personnalisé (ROADMAP « Les inputs personnalisés ») : une
    suite de pas dans le même mini-langage que les actions, mais qui ne
    référence AUCUN mouvement (built-in ou personnalisé) — pas de cycle
    possible par construction. S'utilise comme un mouvement built-in, en tête
    d'une expression d'action (cf. `core/models/input_expression.py`)."""
    name: str = ""
    steps: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "steps": self.steps}

    @classmethod
    def from_dict(cls, d: dict) -> "InputMovement":
        return cls(name=str(d.get("name", "")), steps=str(d.get("steps", "")))


@dataclass
class ProjectSettings:
    name: str = "mon_jeu"
    start_scene: str = ""   # scène sur laquelle démarre le JEU (choisie par l'auteur)
    # Dernière scène ouverte dans l'ÉDITEUR — état d'interface, pas réglage de
    # jeu : restauré à l'ouverture du projet. Séparé de start_scene, sinon
    # éditer une autre scène écraserait silencieusement le point de départ.
    last_scene: str = ""
    author: str = ""
    version: str = "0.1"
    # Couleur de backdrop par défaut (BGR555) — PAL_BG_RAM[0], affichée quand
    # rien d'opaque n'est dessiné nulle part. Éditée dans le ProjectInspector ;
    # Scene.backdrop_color peut la surcharger par scène.
    # Gris 50 % (16, 16, 16 en 5 bits) pour un projet NEUF ; le chargement
    # (`Project.load`) garde 0 pour un project.json qui n'a pas la clé.
    backdrop_color: int = 0x4210
    # Nombre d'emplacements de sauvegarde en SRAM. Un réglage et non une valeur
    # libre laissée au script : c'est lui qui BORNE la place occupée, donc ce
    # qui rend la capacité vérifiable au build plutôt qu'à l'exécution.
    save_slots: int = 1
    # Transition jouée à chaque changement de scène — le DÉFAUT du projet, qu'une
    # scène peut surcharger (cf. Scene.transition_kind). Répondre ici une fois
    # évite de reposer la question sur chaque scène ; la surcharge évite
    # d'imposer un fondu à un menu qui doit apparaître net.
    # Valeurs : les mêmes chaînes que les effets de mélange (models/scene.py),
    # un fondu au noir devant s'appeler pareil partout.
    transition_kind: str = "none"    # none | fade_black | fade_white
    transition_frames: int = 16      # durée d'UNE moitié (fermeture ou ouverture)
    # Capacité de la cartouche visée, en Mio — 4, 8, 16 ou 32, les tailles
    # réellement produites en cartouche masquée sur GBA (l'espace d'adressage
    # de la console s'arrête à 32 Mio). Sert de plafond au rapport de poids
    # affiché en fin de build (cf. codegen/rom_report.py).
    cartridge_mib: int = 4
    # Taux d'échantillonnage cible des effets, en Hz — le DÉFAUT du projet,
    # qu'un Sfx peut surcharger (cf. Sfx.sample_rate). 0 = on garde le taux du
    # fichier source. C'est bien le défaut : ré-échantillonner d'office
    # dégraderait un projet existant sans que personne ne l'ait demandé.
    sfx_sample_rate: int = 0
    # Canaux logiciels de maxmod, partagés par la musique et les effets.
    # `mmInitDefault(bank, n)` alloue exactement 92 × n + 1056 octets sur le
    # tas (40 o de voie de module + 28 o de voie active + 24 o de voie de
    # mixage par canal, plus le tampon de mixage 16 kHz) — mesuré au
    # désassemblage, cf. ROADMAP v0.8.8. Défaut 8 : la valeur qui était en dur,
    # pour qu'un projet existant ne change pas de son parce qu'un réglage est
    # apparu. Le pool de RÉFÉRENCES d'effets, lui, vaut 16 quoi qu'on mette ici.
    sound_channels: int = 8
    # Build DEBUG (`debug.log`, mesure de budget par frame — cf. ROADMAP v0.14)
    # vs RELEASE (les deux disparaissent de la ROM, à la compilation, pas au
    # runtime). Vrai par défaut : c'est le comportement qu'avait le logiciel
    # avant que ce réglage existe, un projet existant ne doit rien voir changer.
    debug_build: bool = True
    # Les couples de TAGS de boxes qui ne se rencontrent PAS (ROADMAP v0.23).
    # Chaque entrée est une clé `pair_key(a, b)`, donc un couple non ordonné :
    # « les projectiles du joueur ignorent ceux du boss » se dit une fois.
    #
    # On stocke ce qui est INTERDIT, pas ce qui est permis : un projet existant
    # a une liste vide et tout continue de se heurter, comme avant. C'est aussi
    # ce qui garde le fichier court — on déclare les exceptions, pas la règle.
    #
    # Le build s'en sert pour NE PAS ÉMETTRE la paire : le gain est en ROM
    # autant qu'en cycles, ce qu'un filtre au runtime n'aurait pas donné.
    collision_disabled_pairs: list = field(default_factory=list)
    # Tags DÉCLARÉS explicitement, même sans aucun composant qui les porte —
    # ce qui permet de réserver un nom et de régler ses paires avant de
    # l'assigner au premier acteur. Les tags simplement TROUVÉS sur des
    # composants n'ont pas besoin d'y figurer : la matrice les découvre déjà
    # en parcourant les scènes (cf. CollisionsPanel._all_tags). Union des deux
    # ensembles à l'affichage, jamais l'un à la place de l'autre.
    collision_tags: list = field(default_factory=list)
    # Cadence de répétition des listes de menu, en frames (ROADMAP v0.22) —
    # le DÉFAUT du projet, qu'une liste peut surcharger (UIContainer.list_repeat_*).
    # Répondre ici une fois évite trois listes à trois cadences dans le même
    # jeu, ce qu'un joueur sent ; la surcharge laisse un cas particulier
    # possible. Même politique d'héritage que la transition de scène (v0.6.2).
    list_repeat_delay: int = 10   # avant le premier renvoi
    list_repeat_rate: int = 4     # entre les renvois suivants
    # ── Langues (ROADMAP v0.9) ────────────────────────────────────
    # La langue SOURCE est celle qu'on écrit dans `texts.json` : c'est le
    # fichier maître qui la porte, elle n'a donc jamais de fichier side. La
    # déclarer sert à la nommer — dans l'éditeur, et plus tard dans le menu de
    # choix du jeu, où elle est une langue comme les autres.
    source_lang: Language = field(default_factory=Language)
    # Les TRADUCTIONS, une par fichier `texts_<code>.json`. La source n'y est
    # pas : elle y serait une seconde copie de l'anglais, donc une seconde
    # vérité à tenir d'accord. Liste vide = projet monolingue, exactement ce
    # qu'était tout projet avant la v0.9.
    languages: list = field(default_factory=list)
    # Police choisie quand une zone ou `text.draw` n'en nomme pas. Les projets
    # multilingues peuvent la remplacer dans chaque Language ; la couverture
    # d'une FontAsset explicite reste configurée dans cette FontAsset elle-même.
    default_font: str = ""
    # ── Inputs ──────────────────────────────────────────────────────
    # Actions nommées du joueur, chacune liée à un accord de boutons (cases
    # à cocher — held/pressed/released/buffered).
    inputs: list = field(default_factory=list)
    # Séquences nommées (mini-langage complet — get_sequence).
    sequences: list = field(default_factory=list)
    # Axes déclarés, en plus des deux par défaut ("horizontal"/"vertical", la
    # croix — toujours présents, jamais stockés ici : cf. `get_axis`).
    axes: list = field(default_factory=list)
    # Mouvements personnalisés, en plus des six built-in du parseur.
    movements: list = field(default_factory=list)

    def all_languages(self) -> list:
        """Source d'abord, puis les traductions — l'ordre du menu de choix.

        Ne rend rien tant que rien n'est déclaré : un projet monolingue n'a pas
        « une langue », il n'a pas de langues du tout, et c'est ce qui lui
        permet de ne pas changer de comportement."""
        if not self.languages and not self.source_lang.code:
            return []
        return [self.source_lang] + list(self.languages)


# ── Variables du projet ───────────────────────────────────────────
# DEUX identifiants, comme pour les textes (cf. models/text.py) :
#
#   `id`   — opaque, tiré une fois, jamais affiché. C'est lui que citent les
#            fichiers de DONNÉES (une référence de champ, `{"var": <id>}`).
#            Renommer la variable ne le touche pas : le lien tient.
#   `name` — la poignée lisible, seule chose qu'écrit le Lua et seule chose que
#            cite un `$nom` dans un texte. Renommable — c'est alors à l'éditeur
#            de réécrire ces citations-là, qui sont du texte écrit à la main.
#
# Un id opaque dans un `.lua` versionné en git serait illisible et indébuggable
# hors éditeur ; un nom dans un fichier de données casse au premier renommage.
# D'où les deux, chacun là où il est bon.

@dataclass
class GlobalVar:
    """Variable globale déclarée explicitement dans le projet."""
    name:    str  = "var"
    type:    str  = "int"   # int|bool|u8|u16|s8|s16 — un type par variable en C
    default: int  = 0
    desc:    str  = ""      # description optionnelle
    id:      int  = 0       # opaque, stable à vie — voir en-tête de section
    # Cette variable survit-elle à l'extinction de la console ? Un drapeau par
    # variable, et non « tout persister » : un compteur de travail n'a rien à
    # faire en SRAM, et surtout ce qui entre dans la sauvegarde décide de sa
    # compatibilité (cf. ROADMAP.md v0.5). C'est l'`id` ci-dessus qui l'identifie
    # dans le fichier de sauvegarde — jamais son rang, jamais son nom.
    persist: bool = False
    # Combien de CASES cette variable tient (ROADMAP v0.20). 1 = un scalaire,
    # exactement ce qu'était toute variable avant cette version — un projet
    # existant ne voit donc rien changer. Au-delà, c'est un tableau, écrit
    # `global.coffres[i]` dans un script et indexé À PARTIR DE 1 comme tout
    # tableau du langage (v0.7.1).
    #
    # Un tableau plutôt qu'un système de drapeaux : `flag.set(id)` serait un
    # domaine de plus pour un seul usage, là où un tableau sert aussi bien les
    # 200 à 400 booléens de monde d'un metroidvania (coffres, portes, boss
    # vaincus) que l'inventaire, les niveaux de compétence et le journal.
    #
    # `default` reste UNE valeur, pour toutes les cases : c'est ce que demande
    # le cas qui a ouvert le chantier (tout à faux au départ). Un inventaire
    # de départ se remplit dans `on_start`.
    count:   int  = 1


@dataclass
class Constant:
    """Constante déclarée explicitement dans le projet (lecture seule)."""
    name:  str = "const"
    type:  str = "int"   # même jeu de types que GlobalVar : int|bool|u8|u16|s8|s16
    value: int = 0
    desc:  str = ""      # description optionnelle
    id:    int = 0       # opaque, stable à vie


# ── La matrice de collision (ROADMAP v0.23) ──────────────────────────
# Une matrice par PAIRES et non un masque par tag. Le masque s'écrit plus vite
# mais se relit mal : c'est le modèle « layer / mask » de Godot, où il faut
# tenir deux champs asymétriques dans sa tête pour répondre à « est-ce que A
# touche B ? ». La paire répond à cette question-là directement, et c'est la
# question qu'on se pose. Une grille triangulaire de n tags fait n(n+1)/2
# cases : dix tags, cinquante-cinq cases — ça se lit d'un coup d'œil.

# Les tags qu'un projet NEUF déclare d'office : « Player » pour ce que le joueur
# pilote, « body » pour tout le reste (le tag par défaut d'une boîte). Posés à
# la création (`Project.create`) et non à la lecture : un projet existant, dont
# `collision_tags` est absent, garde exactement les siens.
DEFAULT_COLLISION_TAGS = ("Player", "body")


def pair_key(tag_a: str, tag_b: str) -> str:
    """La clé d'un couple de tags, indépendante de l'ordre — « A contre B » et
    « B contre A » sont la même question."""
    a, b = sorted((tag_a or "body", tag_b or "body"))
    return f"{a}|{b}"


def tags_collide(settings, tag_a: str, tag_b: str) -> bool:
    """Ces deux tags se rencontrent-ils ? Vrai par défaut : la matrice ne
    contient que les exceptions."""
    disabled = getattr(settings, "collision_disabled_pairs", None) or []
    return pair_key(tag_a, tag_b) not in disabled
