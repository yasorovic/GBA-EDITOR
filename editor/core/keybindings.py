"""
core/keybindings.py — registre central des raccourcis REMAPPABLES.

Avant ce fichier, un raccourci était une chaîne codée en dur au point où il
s'active — 22 sites, répartis sur 7 fichiers, sans nom ni mémoire commune.
Changer une touche voulait dire éditer le code ; l'écran Réglages (catégorie
« Shortcuts ») ne peut lister et remapper que ce qui a un NOM et une valeur
par défaut ici — le reste continue de s'activer directement.

Chaque site d'origine résout sa touche via `resolve(id)` au lieu d'une chaîne
en dur ; ce module ne branche rien lui-même, il ne fait que dire quelle touche
va avec quel id.

Règle de partage : une touche est remappable quand elle déclenche une ACTION
NOMMÉE d'un canvas ou d'un écran (outil, copier, supprimer, ajuster, zoom). Elle
ne l'est pas quand elle NAVIGUE dans un widget, ferme ou annule, édite du texte,
ou suit une convention du système. Les familles ci-dessous sont donc
VOLONTAIREMENT absentes de ce registre, remappables nulle part :

  - **Navigation dans un widget** — flèches, Entrée, Tab, Espace, Home/End dans
    les grilles (palettes, glyphes), le graphe des scènes, la complétion Lua,
    l'éditeur Lua et l'aperçu de police ; Suppr/Entrée du graphe des scènes
    et validation/annulation du recadrage de fond.
  - **Fermer / annuler** — Échap pour quitter un renommage, une sélection de
    glyphe ou le recadrage de fond.
  - **Édition de texte et complétion Lua** — Ctrl+Espace compris : c'est la
    convention des éditeurs de code.

  - **Undo/Redo** (window.py) — `QKeySequence.StandardKey`, la convention du
    système d'exploitation, pas un choix de ce projet ; Redo est en plus
    doublement lié (Ctrl+Y ET la touche standard) pour couvrir les deux
    habitudes à la fois. Remapper l'un des deux casserait l'autre en silence.
    Listés quand même dans l'écran Réglages via `DISPLAY_ONLY` ci-dessous —
    pour la découvrabilité, pas pour le remappage : lecture seule, aucune
    entrée dans `BINDINGS`/`_BY_ID`.
  - **Renommer (F2)** (scene_tree_panel.py, asset_finder.py) — le `F2` qui
    apparaît dans ces menus est un LIBELLÉ, pas un branchement : Qt déclenche
    déjà l'édition en place via son trigger natif `EditKeyPressed` sur
    QTreeWidget/QListWidget. Le remapper ici changerait le texte affiché sans
    changer la touche qui agit réellement — pire que ne rien afficher.
  - **Nudge de sélection** (scene_canvas.py, flèches ± Shift) — les 8
    variantes sont POSITIONNELLES (haut/bas/gauche/droite), pas des actions
    nommées ; leur binder une à une n'offrirait rien qu'un vrai remappage de
    clavier de jeu n'offre pas déjà, pour 8 lignes de registre.
  - **Backspace en second alias de Suppr** (scene_canvas.py) — un simple
    confort clavier, jamais montré nulle part : remapper « Suppr » ne doit
    pas le priver de son alias.

Persistance : un fichier JSON à côté de `toolchain.json` (même dossier de
config, cf. `core/toolchain.config_dir`), qui ne porte QUE les
SUBSTITUTIONS à la valeur par défaut — un raccourci jamais changé n'y figure
pas, donc une valeur par défaut modifiée dans une prochaine version profite
à qui n'a rien personnalisé.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from PyQt6.QtCore import QKeyCombination, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut, QAction

from core.toolchain import config_dir

CONFIG_FILE = config_dir() / "keybindings.json"


@dataclass(frozen=True)
class Binding:
    id: str            # stable — c'est la clé de persistance, jamais affichée
    context_id: str     # regroupement stable, résolu en libellé par l'UI
    default: str         # QKeySequence, ex. "Ctrl+D", "Shift+X", "F"


# ── Le registre — un binding par ligne, dans l'ordre d'affichage ──────────
BINDINGS: list[Binding] = [
    # Commun — actif dans tout le logiciel. Le contexte « global » est la
    # première section de l'écran Réglages ; une touche d'écran qui entrerait
    # en collision avec l'une d'elles est signalée comme un conflit.
    Binding("file.new",   "global", "Ctrl+N"),
    Binding("file.open",  "global", "Ctrl+O"),
    Binding("file.save",  "global", "Ctrl+S"),
    Binding("file.quit",  "global", "Ctrl+Q"),
    Binding("game.build", "global", "F5"),
    Binding("common.copy",       "global", "Ctrl+C"),
    Binding("common.paste",      "global", "Ctrl+V"),
    Binding("common.duplicate",  "global", "Ctrl+D"),
    Binding("common.delete",     "global", "Del"),
    Binding("common.cancel",     "global", "Escape"),
    Binding("common.fit",        "global", "F"),
    Binding("common.zoom_in",    "global", "+"),
    Binding("common.zoom_out",   "global", "-"),
    Binding("common.zoom_reset", "global", "1"),

    # Scene canvas (ui/scene_manager/scene_canvas.py)
    Binding("canvas.tool_select",    "scene_canvas", "S"),
    Binding("canvas.tool_add",       "scene_canvas", "A"),
    Binding("canvas.tool_erase",     "scene_canvas", "E"),
    Binding("canvas.tool_collision", "scene_canvas", "C"),
    Binding("canvas.tool_inpaint",   "scene_canvas", "B"),
    Binding("canvas.tool_ui",        "scene_canvas", "T"),

    # Sprite editor (ui/sprite_editor/*)
    Binding("sprite.flip_h", "sprite_editor", "Shift+X"),
    Binding("sprite.flip_v", "sprite_editor", "Shift+Y"),

    # Sound mixer (ui/sound_mixer/sound_panel.py)
    Binding("sound.play_pause", "sound_mixer", "Space"),

    # Scene Manager — project viewer & Graphe des scènes
    Binding("scene.group", "scene_manager", "Ctrl+G"),
    Binding("scene.graph_toggle_minimap", "scene_manager", "H"),
    Binding("scene.graph_search", "scene_manager", "Ctrl+F"),
]

_BY_ID: dict[str, Binding] = {b.id: b for b in BINDINGS}


# ── Affichage seul — pas dans BINDINGS, jamais remappable ──────────────────
# Rangées de la section « global » de l'écran Réglages, après ses raccourcis
# remappables. La molette et le clic-milieu sont des gestes de souris : la
# troisième colonne est vide, l'écran y met le nom du geste traduit.
DISPLAY_ONLY: list[tuple[str, str, str]] = [
    # (context_id, display_id, touche affichée)
    ("global", "undo", "Ctrl+Z"),
    ("global", "redo", "Ctrl+Y"),
    ("global", "wheel_zoom", ""),
    ("global", "middle_pan", ""),
]


class Keybindings(QObject):
    """Charge/sauvegarde les substitutions, résout un id vers sa touche
    effective. `QObject` pour UNE raison : `changed` permet à un raccourci
    déjà construit (QShortcut/QAction) de se remettre à jour SANS relancer
    l'éditeur quand l'écran Réglages le change — cf. `bind()` plus bas, seul
    consommateur du signal."""

    changed = pyqtSignal(str)   # binding_id qui vient de changer

    def __init__(self):
        super().__init__()
        self._overrides: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self._overrides, indent=2), encoding="utf-8")

    def resolve(self, binding_id: str) -> str:
        """La touche EFFECTIVE d'un id — la substitution si elle existe,
        sinon la valeur par défaut du registre. Un id inconnu du registre
        (faute de frappe au site d'appel) rend une chaîne vide plutôt que de
        lever : un raccourci manquant se voit à l'usage, il ne doit pas
        empêcher l'écran de s'ouvrir."""
        b = _BY_ID.get(binding_id)
        if b is None:
            return ""
        return self._overrides.get(binding_id, b.default)

    def set(self, binding_id: str, sequence: str):
        b = _BY_ID.get(binding_id)
        if b is None:
            return
        sequence = sequence.strip()
        if sequence == b.default:
            self._overrides.pop(binding_id, None)   # revenu au défaut = plus une substitution
        else:
            self._overrides[binding_id] = sequence
        self.save()
        self.changed.emit(binding_id)

    def reset(self, binding_id: str):
        if binding_id in self._overrides:
            del self._overrides[binding_id]
            self.save()
            self.changed.emit(binding_id)

    def reset_all(self):
        ids = list(self._overrides)
        self._overrides.clear()
        self.save()
        for binding_id in ids:
            self.changed.emit(binding_id)

    def is_customized(self, binding_id: str) -> bool:
        return binding_id in self._overrides


# ── Singleton — même règle que get_history()/get_bus()/get_dispatcher() :
# un registre, partagé par tous les sites qui en ont besoin sans avoir à se
# le passer de widget en widget.
_instance: Keybindings | None = None


def get_keybindings() -> Keybindings:
    global _instance
    if _instance is None:
        _instance = Keybindings()
    return _instance


def matches(binding_id: str, event) -> bool:
    """Vrai si `event` (un QKeyEvent) est la touche EFFECTIVE de `binding_id`.

    Pour les widgets qui lisent déjà le clavier eux-mêmes (`keyPressEvent`,
    filtre d'événements) : là, un `QShortcut` volerait la touche aux champs
    de saisie voisins (Suppr, Ctrl+C dans un champ HEX). Un id inconnu ou une
    touche vidée ne correspond à rien.

    Maj est ignoré pour « + » : sur un clavier AZERTY il s'obtient avec Maj,
    et Qt le rapporte avec ce modificateur."""
    wanted = QKeySequence(get_keybindings().resolve(binding_id))
    if wanted.isEmpty():
        return False
    mods = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
    key = Qt.Key(event.key())
    if QKeySequence(QKeyCombination(mods, key)) == wanted:
        return True
    if key == Qt.Key.Key_Plus and mods & Qt.KeyboardModifier.ShiftModifier:
        return QKeySequence(QKeyCombination(
            mods & ~Qt.KeyboardModifier.ShiftModifier, key)) == wanted
    return False


def bind(binding_id: str, target: QShortcut | QAction) -> None:
    """Pose la touche EFFECTIVE de `binding_id` sur `target`, et le tient à
    jour si l'écran Réglages la change EN COURS DE SESSION — un seul appel
    remplace à la fois la construction d'une `QKeySequence` en dur et
    l'abonnement à son changement. Remplace, à chaque site d'origine :

        a = QAction("New project", self); a.setShortcut("Ctrl+N")
    par
        a = QAction("New project", self); bind("file.new", a)

    Un id absent du registre (faute de frappe) laisse `target` sans touche —
    silencieux à dessein, cf. `Keybindings.resolve`."""
    kb = get_keybindings()

    def _apply():
        seq = QKeySequence(kb.resolve(binding_id))
        if isinstance(target, QShortcut):
            target.setKey(seq)
        else:
            target.setShortcut(seq)

    _apply()
    kb.changed.connect(lambda changed_id: _apply() if changed_id == binding_id else None)
