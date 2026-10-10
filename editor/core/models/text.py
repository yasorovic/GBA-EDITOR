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
  `path`  — le rangement : 1 à 6 niveaux de libellés libres, avec accents,
            espaces et doublons autorisés. Jamais résolu, jamais référencé.

**La clé situe, elle ne résume pas.** Elle est dérivée de la PLACE du texte
(son chemin de rangement), jamais du contenu : le contenu d'un texte est
réécrit vingt fois pendant l'écriture, sa place dans le jeu bouge rarement. Une
clé tirée du contenu (`garde_je_suis`) devient un mensonge dès que le garde
devient un mendiant — et personne ne va la corriger. Une clé positionnelle
reste au pire imprécise.

**Le chemin PROPOSE la clé, il ne la POSSÈDE pas.** Tant que `auto_key` est
vrai, ranger le texte ailleurs recale sa clé (et réécrit les scripts qui la
citent : c'est sans danger, une clé automatique est par définition jetable).
Dès que l'utilisateur la nomme à la main, `auto_key` tombe à faux et la clé se
détache définitivement — réorganiser l'arbre ne la touchera plus jamais.

Sans ce détachement, ranger reviendrait à refactorer : renommer un nœud
« Village » en « Village Nord » réécrirait N clés dans M fichiers `.lua`
versionnés en git, pour un geste purement cosmétique.

Le chemin ne suffit pas non plus à identifier : deux répliques rangées au même
endroit produisent la même clé, d'où un rang numéroté (`village_garde_02`). Si
la clé était strictement dérivée, il faudrait imposer un dernier niveau unique
— et le libellé ne serait plus libre, juste une clé déguisée.

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

# Profondeur max du chemin de rangement. Plafond de départ, choisi pour que la
# clé dérivée reste lisible (6 × 16 caractères reste exploitable) — pas une
# limite structurelle : le chemin est une liste, la relever ne coûtera rien.
MAX_DEPTH = 6

# Séparateur d'AFFICHAGE seulement. Le stockage est une liste : un libellé
# libre a le droit de contenir « / » ou « > » sans qu'on ait à inventer une
# règle d'échappement.
SEP = " › "


@dataclass
class Text:
    """Une entrée de la table de textes du projet."""
    id:      str = ""   # opaque, stable à vie — voir en-tête du module
    key:     str = ""    # poignée unique et lisible, référencée depuis Lua
    path:    list[str] = field(default_factory=list)  # rangement libre, 1..6 niveaux
    content: str = ""    # le texte lui-même, tel qu'affiché au joueur
    note:    str = ""    # contexte pour le traducteur (v0.8)
    scene:   str = ""    # scène d'origine — filtre d'affichage uniquement
    auto_key: bool = True  # clé jamais renommée à la main → badge « auto »

    def path_str(self) -> str:
        return SEP.join(self.path)

    def to_dict(self) -> dict:
        # Dérivé des champs : ajouter un champ à Text le persiste sans risquer
        # d'oublier cette méthode. `from_dict` reste explicite — il porte la
        # migration de l'ancienne table plate (`label` → `path`).
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Text":
        raw = d.get("path")
        if raw is None:
            # Migration depuis la table plate : le `label` unique devient le
            # premier — et pour l'instant seul — niveau du chemin.
            raw = [d["label"]] if d.get("label") else []
        return cls(
            id       = str(d.get("id") or ""),
            key      = d.get("key", ""),
            path     = norm_path(raw),
            content  = d.get("content", ""),
            note     = d.get("note", ""),
            scene    = d.get("scene", ""),
            auto_key = bool(d.get("auto_key", True)),
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
    """Chemin propre : segments rognés, trous supprimés, profondeur plafonnée.

    Les trous sont compactés (`["", "Garde"]` → `["Garde"]`) : un niveau vide
    au milieu d'un chemin ne veut rien dire, et le laisser passer produirait
    deux nœuds distincts d'apparence identique dans l'arbre."""
    if isinstance(path, str):
        path = [path]
    return [s for s in (str(p).strip() for p in (path or [])) if s][:MAX_DEPTH]


# ── Rangement ─────────────────────────────────────────────────────
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


def key_from_path(path, *, taken: set[str] | None = None) -> str:
    """Clé positionnelle unique dérivée du chemin : `village_garde`.

    Le rang `_2`, `_3`… n'apparaît qu'en cas de collision — plusieurs répliques
    rangées au même endroit (cf. `unique_name`). La clé reste ainsi lisible dans
    le cas courant (un texte par nœud), qui est aussi celui qu'on copie dans un
    script.

    Chemin vide : la base est `texte`."""
    segs = [s for s in (slug(p) for p in norm_path(path)) if s]
    return unique_name("_".join(segs) or "texte", taken or set())
