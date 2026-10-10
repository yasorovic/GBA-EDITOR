"""
core/models/ids.py — identifiants opaques, partagés par les modèles.

**Un id opaque dans les fichiers de DONNÉES, un nom lisible dans le code écrit à
la main.** C'est la règle dégagée par la table de textes (cf. models/text.py),
étendue ici aux variables du projet puis aux dossiers : ce qu'un fichier JSON
référence doit survivre à un renommage, alors qu'un id dans du Lua versionné en
git serait illisible et indébuggable hors éditeur.

Un id est une chaîne de 12 chiffres hexadécimaux (48 bits), tirée au sort — et
non un compteur monotone : ça survit à la fusion de deux branches ou de deux
projets, là où deux compteurs auraient produit les mêmes valeurs pour des objets
différents. À 48 bits le risque de collision entre deux projets fusionnés est de
l'ordre de 2·10⁻⁷ pour 10 000 ids ; dans un même projet, `taken` l'écarte
tout à fait.

Un id n'entre jamais dans la ROM : le build le remplace par des noms et des
index C. Seule la sauvegarde en garde une trace (cf. `gen_save.save_id32`).
"""
from __future__ import annotations

import re
import secrets

ID_HEX_LENGTH = 12

_ID_PATTERN = re.compile(rf"[0-9a-f]{{{ID_HEX_LENGTH}}}")


def new_id(taken) -> str:
    """Id opaque non encore utilisé. `taken` est un ensemble d'ids pris."""
    while True:
        candidate = secrets.token_hex(ID_HEX_LENGTH // 2)
        if candidate not in taken:
            return candidate


def is_id(value) -> bool:
    """`value` a-t-il la forme d'un id ? Ce qui distingue un id d'un NOM dans
    les endroits qui acceptent les deux (`{"var": <id|nom>}`), d'où l'interdit
    de nommer une variable avec 12 chiffres hexadécimaux."""
    return isinstance(value, str) and _ID_PATTERN.fullmatch(value) is not None
