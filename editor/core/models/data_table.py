"""DataTable — une table de données du projet : des colonnes typées, des lignes.

Rangée avec les données PROPRES au projet (`project/data/`) et non dans
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
# N'y figurent que les domaines que le runtime sait INDEXER : chacun est déjà un
# `#define NOM i` désignant une entrée d'une table en ROM, donc une colonne de ce
# type EST cet entier. `sprite` et `prefab` en sont absents pour deux raisons
# différentes, dites dans la ROADMAP (v0.7.2).
COLUMN_SCALARS = ("int", "bool")
COLUMN_REFERENCES = ("text", "sfx", "music", "scene", "camera", "font",
                     "palette", "region", "image")
COLUMN_TYPES = COLUMN_SCALARS + COLUMN_REFERENCES


@dataclass
class DataColumn:
    name: str = "colonne"
    type: str = "int"

    def default(self) -> Any:
        """Ce que vaut la colonne quand une ligne ne la mentionne pas."""
        if self.type == "bool":
            return False
        if self.type in COLUMN_REFERENCES:
            return ""        # aucune référence — le build émet 0
        return 0


@dataclass
class DataTable(Resource):
    name:    str = "Table"
    columns: list[DataColumn] = field(default_factory=list)
    rows:    list[dict]       = field(default_factory=list)

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
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DataTable":
        return cls(
            name    = d.get("name", "Table"),
            columns = [DataColumn(name=c.get("name", "colonne"),
                                  type=c.get("type", "int"))
                       for c in d.get("columns", [])],
            rows    = [r for r in d.get("rows", []) if isinstance(r, dict)],
        )
