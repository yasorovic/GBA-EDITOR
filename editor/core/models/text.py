"""Textes du jeu — table de chaînes destinées au joueur.

Trois identifiants, un seul résolvable :

  `id`    — opaque, tiré une fois à la création, jamais affiché ni retapé.
            C'est lui que stockent les fichiers de données et que suit le
            graphe de dépendances. Il ne change JAMAIS, y compris si le
            contenu et la clé changent.
  `key`   — la poignée lisible, ce qu'un script Lua écrit. Unique, résolue au
            build vers un index de table C (comme SFX_* ou SCENE_IDX_*) : elle
            ne vit pas au runtime. Renommable — c'est alors à l'éditeur de
            réécrire les références.
  `path`  — PROPRIÉTÉ, jamais stockée : les segments de `key` (`SCR_Arena_Page01`
            ↔ `SCR › Arena › Page01`). Ranger un texte, c'est donc renommer sa clé.

**La clé porte la structure.** Chaque `_` ouvre un niveau. Un libellé stocké à
côté la dupliquait et se désynchronisait au premier renommage qui ne le recalait
pas : il a été retiré (ROADMAP, « Le chemin est dérivé de la clé »).

Le chemin ne suffit pas à identifier : deux répliques rangées au même endroit
produisent la même clé, d'où un rang numéroté (`village_garde_02`).

Le texte est destiné au JOUEUR, donc traduisible (cf. ROADMAP.md v0.8) : c'est
ce qui le distingue d'un `string` technique, qui reste un littéral dans le
script.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field, asdict

from core.models.unique_name import unique_name


# L'id opaque et son tirage vivent dans `models/ids.py` : les variables du
# projet et les dossiers suivent la même règle, et deux tirages séparés auraient
# fini par diverger sur la largeur ou sur la garde d'unicité.

# Longueur max d'un segment de clé — au-delà on tronque (une clé sert à situer,
# pas à raconter).
_SEGMENT_MAX = 16

# Profondeur proposée par l'éditeur. Le chargement ne tronque jamais une clé :
# chaque `_` doit rester visible, même au-delà de ce confort d'édition.
MAX_DEPTH = 10

# Séparateur d'AFFICHAGE seulement. Le stockage est une liste : un libellé
# libre a le droit de contenir « / » ou « > » sans qu'on ait à inventer une
# règle d'échappement.
SEP = " › "


@dataclass
class Text:
    """Une entrée de la table de textes du projet."""
    id:      str = ""   # opaque, stable à vie — voir en-tête du module
    key:     str = ""    # poignée unique et lisible, référencée depuis Lua
    content: str = ""    # le texte lui-même, tel qu'affiché au joueur
    note:    str = ""    # contexte pour le traducteur (v0.8)
    scene:   str = ""    # scène d'origine — filtre d'affichage uniquement

    @property
    def path(self) -> list[str]:
        """Les niveaux de la clé, dans l'ordre. Dérivé : jamais écrit."""
        return [part for part in str(self.key).split("_") if part]

    def path_str(self) -> str:
        return SEP.join(self.path)

    def to_dict(self) -> dict:
        # Dérivé des champs : ajouter un champ à Text le persiste sans risquer
        # d'oublier cette méthode. `from_dict` reste explicite.
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Text":
        key = d.get("key", "")
        if not key:
            # Anciens fichiers sans clé : elle se dérive de leur ancien chemin (ou du `label`
            # de la table plate). Les doublons sont renumérotés au chargement (`_repair_texts`).
            legacy = d.get("path")
            if legacy is None:
                legacy = [d["label"]] if d.get("label") else []
            key = key_from_path(legacy) if legacy else ""
        return cls(
            id       = str(d.get("id") or ""),
            key      = key,
            content  = d.get("content", ""),
            note     = d.get("note", ""),
            scene    = d.get("scene", ""),
        )


# ── Génération d'identifiants ─────────────────────────────────────

def slug(s: str) -> str:
    """Segment de clé : ASCII minuscule, séparateurs en `_`, tronqué.

    Les accents sont dépliés (« Forêt » → « foret ») plutôt que supprimés :
    une clé reste lisible pour un francophone."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    out = "".join(c.lower() if c.isalnum() else "_" for c in s)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")[:_SEGMENT_MAX]


def norm_path(path) -> list[str]:
    """Libellés propres : un niveau par segment, segments rognés, trous supprimés.

    Règle unique : un `_` ouvre un niveau, comme dans une clé. `SCR_Arena` vaut
    donc `SCR`, `Arena` — pour un nom de scène, de TextBox ou un libellé tapé.
    Les trous sont compactés (`["", "Garde"]` → `["Garde"]`) : un niveau vide
    au milieu d'un chemin ne veut rien dire, et le laisser passer produirait
    deux nœuds distincts d'apparence identique dans l'arbre."""
    if isinstance(path, str):
        path = [path]
    parts = (part.strip() for label in (path or []) for part in str(label).split("_"))
    return [part for part in parts if part]


def key_segment(label: str) -> str:
    """Identifiant d'un niveau, sans `_` puisque celui-ci sépare les niveaux."""
    value = unicodedata.normalize("NFKD", str(label or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    words = []
    word = ""
    for char in value:
        if char.isalnum():
            word += char
        elif word:
            words.append(word)
            word = ""
    if word:
        words.append(word)
    return "".join(words[:1] + [part[:1].upper() + part[1:] for part in words[1:]])[:_SEGMENT_MAX]


# ── Rangement ─────────────────────────────────────────────────────
def moved_text_paths(texts, source, destination):
    """Déplace un nœud sous un dossier, en conservant son nom et ses enfants.

    Une liste vide signale une destination invalide ou un déplacement nul.
    La vue et la commande utilisent la même validation, sans modifier le modèle.
    """
    source, destination = tuple(source), tuple(destination)
    if (not source or destination[:len(source)] == source or
            destination == source[:-1]):
        return []
    targets = [t for t in texts if tuple(t.path[:len(destination)]) == destination]
    if destination and not (len(targets) > 1 or
                            any(len(t.path) > len(destination) for t in targets)):
        return []
    entries = []
    for text in texts:
        if tuple(text.path[:len(source)]) != source:
            continue
        new = list(destination) + list(text.path[len(source) - 1:])
        if len(new) > MAX_DEPTH:
            return []
        entries.append((text, list(text.path), new))
    return entries


# Toujours DÉRIVÉ de la liste plate : `texts.json` reste une liste dont chaque
# entrée porte son chemin. `tree_paths` (les nœuds d'un arbre à reconstruire)
# a disparu avec `text_tree_panel.py` — la table qui l'a remplacé (ROADMAP
# v0.9) groupe par catégorie sans en avoir besoin.

def texts_under(texts, path) -> list:
    """Textes rangés dans `path` ou dans un de ses sous-nœuds."""
    path = tuple(path)
    return [t for t in texts if tuple(t.path[:len(path)]) == path]


def repath_segment(texts, path, new_seg: str) -> list[tuple]:
    """Renommage d'un nœud : [(texte, ancien chemin, nouveau chemin)].

    Renommer un rangement le renomme pour TOUT ce qu'il contient — c'est le
    même geste que déplacer une entrée, à l'échelle près. Ne modifie rien : le
    déplacement passe par une commande annulable."""
    depth = len(path) - 1
    return [
        (t, list(t.path),
         list(t.path[:depth]) + [new_seg] + list(t.path[depth + 1:]))
        for t in texts_under(texts, path)
    ]


def key_from_path(path, *, taken: set[str] | None = None, like: str = "") -> str:
    """Clé positionnelle unique dérivée du chemin : `village_garde`.

    Le rang `_2`, `_3`… n'apparaît qu'en cas de collision — plusieurs répliques
    rangées au même endroit (cf. `unique_name`). La clé reste ainsi lisible dans
    le cas courant (un texte par nœud), qui est aussi celui qu'on copie dans un
    script.

    `like` : une clé existante dont les segments gardent leur casse. Les libellés par défaut
    (`scr` → `Scr`) n'en portent pas : sans elle, déplacer un dossier recaserait des clés que
    personne n'a renommées, et réécrirait les scripts qui les citent.

    Chemin vide : la base est `texte`."""
    cased = {part.casefold(): part for part in like.split("_") if part}
    segs = [s for s in (key_segment(p) for p in norm_path(path)) if s]
    segs = [cased.get(s.casefold(), s) for s in segs]
    return unique_name("_".join(segs) or "texte", taken or set())
