"""Les écrans de l'éditeur : le contrat qu'ils remplissent, et le registre où
un plugin en ajoute un.

Un écran n'était pas une donnée. Il fallait l'épeler à CINQ endroits de
`window.py` — le tableau `SCREENS`, l'ordre des `addWidget` dans `_setup_ui`,
un attribut `self._x`, une ligne dans `_refresh_ui`, les abonnements du
dispatcher — dont deux listes parallèles dont l'accord n'était tenu que par un
commentaire (« l'ordre doit rester synchronisé »). Un écran inséré au milieu
décalait silencieusement l'autre liste.

Ici il n'y a qu'une liste, construite par `MainWindow._screen_catalogue()`, et
tout en dérive : les libellés de la barre de navigation, l'ordre du
`QStackedWidget`, et la propagation du projet ouvert.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from PyQt6.QtWidgets import QWidget


@runtime_checkable
class ProjectScreen(Protocol):
    """Ce qu'un écran doit savoir faire : recevoir le projet ouvert.

    Le contrat existait déjà, sans nom : six écrans l'écrivaient
    `load_project`, un septième `set_project`, et rien ne disait lequel était
    le bon. C'est `load_project` — la majorité, et le verbe juste (un écran
    charge un projet, il ne le configure pas).

    `Protocol` et non classe de base : un écran est un `QWidget` d'abord, et
    l'héritage multiple avec Qt coûte plus qu'il ne rapporte ici. Le contrôle
    se fait à la construction (`MainWindow._build_screens`), ce qui couvre
    aussi les écrans venus d'un plugin — qu'aucun contrôle statique ne peut
    voir.

    `load_project` est le SEUL membre obligatoire — c'est lui que vérifie
    `isinstance` à la construction. Le crochet de revisite `refresh` ne fait
    volontairement PAS partie de ce Protocol : l'y déclarer ferait échouer le
    contrôle `isinstance` pour tout écran ne l'implémentant pas, alors qu'il est
    optionnel. Il est donc documenté et appelé à part, via `refresh_screen`
    ci-dessous.
    """

    def load_project(self, project) -> None: ...


def refresh_screen(widget) -> None:
    """Re-dérive les catalogues d'un écran à une visite SUIVANTE — s'il sait le
    faire, sinon ne fait rien.

    Le pendant OPTIONNEL de `load_project` : `load_project` remplit un écran à sa
    PREMIÈRE visite, `refresh` le remet à jour quand on y REVIENT après une
    modification faite dans un autre écran (chantier « L'écran resynchronisé à sa
    revisite »). Un écran qui n'affiche aucun catalogue partagé n'a rien à faire
    ici et n'a pas de `refresh` — d'où le « no-op si absent », centralisé ICI pour
    que le point d'appel (`MainWindow._show_screen`) n'ait pas à savoir quels
    écrans l'implémentent.

    Contrat d'un `refresh`, quand un écran en a un : idempotent et bon marché —
    re-dériver depuis la MÉMOIRE (relire des listes/noms déjà chargés), JAMAIS
    toucher au disque, re-décoder un asset ni reconstruire un raster ; conserver
    la sélection et l'état d'édition en cours.

    Ce helper ne fait QUE l'appel s'il existe ; c'est le point d'appel
    (`MainWindow._show_screen`) qui entoure le cas d'un écran de PLUGIN, là où le
    statut plugin est connu — exactement comme `_load_screen_for_project` le fait
    déjà pour `load_project`.
    """
    hook = getattr(widget, "refresh", None)
    if callable(hook):
        hook()


@dataclass(frozen=True)
class EditorScreen:
    """Une entrée du catalogue d'écrans.

    `build` rend le widget ; il n'est appelé qu'une fois, à la PREMIÈRE VISITE
    de l'écran (le Scene Manager et les écrans de plugin, eux, sont construits
    au démarrage — cf. `MainWindow._build_screens` et le chantier technique
    « L'écran construit à sa première visite »). C'est un appelable et non une
    classe parce qu'un écran ne se construit pas forcément par simple appel de
    constructeur — le Scene Manager est assemblé par la fenêtre à partir de
    trois colonnes qu'elle possède déjà.

    Un écran qui accueille le panneau de build expose `body`, son
    `ThreeColumnBody` (cf. `ui/common/three_column_body.py`) ; sans `body`
    — un écran de plugin le plus souvent —, il n'a pas de panneau de build.
    """

    name: str
    build: Callable[[], QWidget]
    # Un écran de plugin est du code tiers : la fenêtre entoure ses appels
    # plutôt que de laisser une exception traverser un slot Qt (cf.
    # `MainWindow._refresh_ui`). Les écrans natifs, eux, doivent échouer fort.
    plugin: bool = False
    # Le panneau de build (console, diagnostics, disque) s'ouvre-t-il avec cet
    # écran ? Une valeur de DÉPART : l'auteur l'ouvre ou le ferme ensuite, et
    # l'écran se souvient de son dernier état pour la session.
    build_panel_open: bool = False


# ── Registre des plugins ──────────────────────────────────────────────
# La seconde surface d'extension, à côté de `COMPONENT_REGISTRY` (un éditeur de
# composant) et de `@register_validator` (une règle de build) : un écran entier.
# Les plugins sont chargés par `main.py` AVANT la fenêtre, donc ce module ne
# doit rien importer d'elle — d'où le registre ici et pas dans `window.py`.

_PLUGIN_SCREENS: list[EditorScreen] = []


def register_screen(name: str, build: Callable[[], QWidget]) -> None:
    """Ajoute un écran à la barre de navigation. À appeler depuis le
    `editor.py` d'un plugin, au chargement du module.

        from ui.screens import register_screen
        register_screen("Mon écran", MonEcran)

    Le widget rendu par `build` doit satisfaire `ProjectScreen` ; sinon il est
    monté quand même, mais ne recevra jamais le projet et la fenêtre le
    signale au démarrage (même canal que les erreurs de chargement de plugin).

    Un nom déjà pris est refusé : il sert de clé de navigation
    (`MainWindow._switch_screen`).
    """
    if any(s.name == name for s in _PLUGIN_SCREENS):
        raise ValueError(f"écran « {name} » déjà enregistré")
    _PLUGIN_SCREENS.append(EditorScreen(name, build, plugin=True))


def plugin_screens() -> list[EditorScreen]:
    """Les écrans enregistrés par les plugins, dans l'ordre de chargement.

    Ils sont ajoutés APRÈS les écrans natifs : les index de ces derniers ne
    bougent pas quand un plugin est installé ou retiré, et l'ordre de la barre
    de navigation enregistré par l'utilisateur survit (cf.
    `ReorderableButtonBar._load_order`, qui repart de zéro si le compte change).
    """
    return list(_PLUGIN_SCREENS)
