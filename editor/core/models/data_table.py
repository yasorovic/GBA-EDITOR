"""DataTable — une table de données du projet : des colonnes typées, des lignes.

Rangée avec les données PROPRES au projet (`assets/data/`) et non dans
`assets/` : elle ne dérive d'aucun fichier importé, comme une caméra ou une
palette.

**Le JSON reste lisible et modifiable à la main**, même si l'écran Data Editor
l'édite : une ligne est un OBJET keyé par nom de colonne, jamais un tableau
positionnel. Réordonner les colonnes ne déplace alors aucune valeur, une clé
absente reprend le défaut de sa colonne, et on relit un fichier de deux cents
lignes sans compter les virgules — ce qu'un diff git rend aussi beaucoup plus
utile.

```json
{
  "name": "Objets",
  "columns": [
    {"name": "prix", "type": "int"},
    {"name": "nom",  "type": "text"},
    {"name": "rare", "type": "bool"}
  ],
  "rows": [
    {"prix": 10, "nom": "potion_nom", "rare": false},
    {"prix": 50, "nom": "epee_nom",   "rare": true}
  ]
}
```

Un script la lit par indexation — `data.Objets[i].prix` — et le build l'émet en
`const` dans la ROM. Elle ne peut donc pas être écrite : le checker le refuse en
nommant la table et la colonne.

Renommer une table ou une colonne depuis l'écran réécrit les scripts qui la
citent (`Project.rename_data_table` / `rename_data_column`). C'est un SECOND
type de site pour `scripting/refactor.py`, qui ne savait jusque-là repérer une
référence que dans un argument littéral d'appel : une table se cite comme du
code, pas comme une chaîne.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Any

from core.models.resource import Resource
from core.models import asset_extensions

# Le nom d'une table et celui de ses colonnes sont des IDENTIFIANTS, pas des
# libellés : un script les écrit comme du CODE (`data.Objets[i].prix`), sans
# guillemets. « Objets rares » ne s'écrirait donc pas.
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Ce qu'une colonne peut valoir.
#
# Les colonnes de RÉFÉRENCE portent exactement le nom de leur domaine de
# script (`scripting/api.DOMAIN_*`) : une colonne « text » cite une clé de la
# table de textes, et le checker la valide par le chemin qui valide déjà
# `text:draw("…")`. La coïncidence des deux listes est vérifiée au build
# (`validator._check_data_column_types`), pas supposée — ce module ne peut pas
# importer `scripting` (cf. les couches, ARCHITECTURE.md).
#
# Les références d'assets graphiques désignent leur rang dans le catalogue du
# projet ; elles ne sont ni un composant sprite d'acteur ni une couche BG.
# L'ancien type `image` désigne un élément d'interface : on continue à le lire,
# mais on ne le propose plus pour une nouvelle colonne.
COLUMN_SCALARS = ("int", "bool")
COLUMN_ASSET_REFERENCES = ("sprite", "background")
LEGACY_COLUMN_REFERENCES = ("image",)
COLUMN_REFERENCES = ("text", "sfx", "music", "scene", "camera", "font",
                     "palette", "region") + COLUMN_ASSET_REFERENCES + LEGACY_COLUMN_REFERENCES
COLUMN_TYPES = COLUMN_SCALARS + COLUMN_REFERENCES
COLUMN_CHOICES = tuple(t for t in COLUMN_TYPES if t not in LEGACY_COLUMN_REFERENCES)


@dataclass
class DataColumn:
    name: str = "colonne"
    type: str = "int"
    color: str = ""  # Repère d'éditeur uniquement, sans effet sur les valeurs ROM.

    def default(self) -> Any:
        """Ce que vaut la colonne quand une ligne ne la mentionne pas."""
        if self.type == "bool":
            return False
        if self.type in COLUMN_REFERENCES:
            return ""        # aucune référence — le build émet 0
        return 0


# Ancienne métadonnée d'éditeur d'une ligne (export de TextBox, retiré) : ignorée à la lecture.
_LEGACY_ROW_META = "$editor"


@dataclass
class DataTable(Resource):
    sidecar_extension = asset_extensions.TABLE
    name:    str = "Table"
    columns: list[DataColumn] = field(default_factory=list)
    rows:    list[dict]       = field(default_factory=list)
    # Lien avec une séquence de textes : {"prefix", "column"}, vide si la table est libre.
    text_link: dict = field(default_factory=dict)

    def column(self, name: str):
        return next((c for c in self.columns if c.name == name), None)

    def value(self, row: dict, col: DataColumn) -> Any:
        """La valeur d'une ligne pour cette colonne, défaut compris."""
        v = row.get(col.name)
        return col.default() if v is None else v

    def to_dict(self) -> dict:
        return {
            "name":    self.name,
            "columns": [asdict(c) for c in self.columns],   # dérivé des champs de DataColumn
            "rows":    list(self.rows),
            **({"text_link": self.text_link} if self.text_link else {}),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DataTable":
        return cls(
            name    = d.get("name", "Table"),
            columns = [DataColumn(name=c.get("name", "colonne"),
                                  type=c.get("type", "int"),
                                  color=c.get("color", ""))
                       for c in d.get("columns", [])],
            rows    = [{k: v for k, v in r.items() if k != _LEGACY_ROW_META}
                       for r in d.get("rows", []) if isinstance(r, dict)],
            text_link = dict(d.get("text_link", {})),
        )
