"""
ui/common/catalog.py — un catalogue de textes d'ÉDITEUR : un maître (la source)
et un side par langue, joints par CLÉ. C'est le cœur partagé par les notices
(ui/common/notice.py) et les libellés (ui/common/labels.py) : même règle de
repli, même pluriel, même `format`, et UN SEUL `set_language` qui les bascule
tous d'un coup.

    <name>.json          le MAÎTRE — clé → { "text": … } ou { "singular"/"plural": … }
    <name>_fr.json       un SIDE   — la traduction seule, jointe par clé

**Une entrée absente vaut la SOURCE, jamais une chaîne vide** ; une clé absente
du maître vaut la clé elle-même — visible à l'écran, retrouvable dans le code.
Le pluriel se déclare (`one`/`other`, choisi par l'argument `n`) plutôt que de
s'écrire `"s" if n > 1`, intraduisible. Le Python passe des VALEURS, jamais des
morceaux de phrase : c'est la concaténation qui rend un texte intraduisible.

Distinct de core/project_langs.py (les textes du JEU) : celui-là joint par id
opaque et vit dans la couche modèle ; celui-ci joint par une clé écrite dans le
Python versionné et vit dans l'interface. Deux couches, deux jointures — d'où
deux mécaniques, et non une seule à cheval sur la frontière.

`tools/check_architecture.py` vérifie chaque catalogue dans les deux sens :
toute clé citée existe, toute entrée est citée.
"""
from __future__ import annotations

import json
from pathlib import Path


# Tous les catalogues construits, pour que `set_language` les atteigne sans que
# l'appelant ait à les connaître. Ils naissent à l'import (singletons de
# module), donc le registre est complet avant tout changement de langue.
_REGISTRY: list["Catalog"] = []
_lang: str = ""

# Les noms sont une donnée de l'éditeur, pas des noms de langue du JEU : les
# langues de jeu appartiennent à ProjectSettings. Un code sans nom connu reste
# tout de même sélectionnable, ce qui permet d'ajouter un side sans changer le
# Python.
_LANGUAGE_NAMES = {
    "fr": "Français",
}


def _template(entry, args: dict) -> str:
    """La forme brute d'une entrée : `text`, ou `one`/`other` selon `n`."""
    if not isinstance(entry, dict):
        return str(entry)
    if "text" in entry:
        return str(entry["text"])
    form = "singular" if int(args.get("n", 0) or 0) == 1 else "plural"
    return str(entry.get(form, entry.get("plural", "")))


class Catalog:
    """Un maître + un side courant, chargés paresseusement depuis `directory`.
    `name` est à la fois le nom de fichier (`<name>.json`) et la clé de premier
    niveau à l'intérieur (`{ "<name>": { … } }`)."""

    def __init__(self, name: str, directory: Path):
        self.name = name
        self.dir = directory
        self._master: dict = {}
        self._side: dict = {}
        _REGISTRY.append(self)
        if _lang:
            self._load_side(_lang)

    def _read(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8")).get(self.name, {})
        except (OSError, ValueError):
            # Un catalogue illisible ne doit pas empêcher l'éditeur de démarrer :
            # chaque texte retombe alors sur sa clé, ce qui se voit à l'écran et
            # se retrouve dans le code — contrairement à un écran vide.
            return {}

    def _catalog(self) -> dict:
        if not self._master:
            self._master = self._read(self.dir / f"{self.name}.json")
        return self._master

    def _load_side(self, code: str):
        self._side = self._read(self.dir / f"{self.name}_{code}.json") if code else {}

    def raw(self, key: str) -> dict:
        """L'entrée BRUTE du maître (pour lire un ton, un `code`…). `{}` si
        absente. Toujours la source : ces métadonnées ne se traduisent pas."""
        entry = self._catalog().get(key)
        return entry if isinstance(entry, dict) else {}

    def text(self, key: str, **args) -> str:
        """Le texte résolu — traduction, pluriel et valeurs."""
        source = self._catalog().get(key)
        if source is None:
            return key      # visible à l'écran, retrouvable dans le code
        raw = _template(self._side.get(key) or source, args)
        try:
            return raw.format(**args)
        except (KeyError, IndexError, ValueError):
            # Une traduction dont les {valeurs} ne correspondent plus au maître
            # ne doit pas casser l'écran : on retombe sur la source, juste par
            # construction. Le contrôle d'architecture le dira au build.
            try:
                return _template(source, args).format(**args)
            except (KeyError, IndexError, ValueError):
                return key


def set_language(code: str):
    """Bascule TOUS les catalogues sur une langue (`""` = la source seule).

    C'est le seul geste que l'écran de réglages de langue (ROADMAP v0.11)
    appelle : la règle de repli appartient au catalogue, pas à l'écran."""
    global _lang
    _lang = code or ""
    for cat in _REGISTRY:
        cat._load_side(_lang)


def available_languages() -> list[tuple[str, str]]:
    """Langues d'interface réellement livrées, maître inclus.

    Une langue apparaît dès qu'un catalogue fournit son side. Les clés absentes
    de ce side retombent sur le maître : on peut donc traduire l'interface par
    étapes sans masquer ni casser aucun libellé.
    """
    codes = {""}
    for cat in _REGISTRY:
        prefix = f"{cat.name}_"
        for path in cat.dir.glob(f"{cat.name}_*.json"):
            code = path.stem.removeprefix(prefix)
            if code:
                codes.add(code)
    return [(code, "English (source)" if not code
             else _LANGUAGE_NAMES.get(code, code))
            for code in sorted(codes)]
