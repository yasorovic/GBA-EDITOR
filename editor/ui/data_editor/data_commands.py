"""ui/data_editor/data_commands.py : les écritures annulables de la grille.

Ce qui n'est PAS ici, et pourquoi : ajouter ou supprimer une TABLE
(`AddResourceCmd` / `DeleteResourceCmd` de `core.history` le font déjà pour
n'importe quel `ResourceStore`), supprimer une LIGNE (`RemoveListItemCmd`, qui
retient déjà son rang). On n'écrit ici que ce que ces commandes génériques ne
savent pas faire — une ligne étant un `dict` et non un objet à champs, et une
colonne vivant dans deux endroits à la fois (le schéma et chaque ligne).

Le RENOMMAGE n'y est pas non plus, et c'est délibéré : renommer une table ou
une colonne réécrit les scripts qui la citent, et l'historique de l'éditeur ne
sait pas défaire une écriture sur disque hors du projet. Il passe donc par
`Project.rename_data_*`, comme le renommage d'une variable — même règle, même
raison.
"""
from __future__ import annotations

from typing import Any

from core.history import Command
from core.models.data_table import DataColumn


class SetCellCmd(Command):
    """Écriture d'une cellule — `table.rows[r][colonne]`.

    Une ligne est un dict keyé par nom de colonne, pas un objet à attributs :
    `SetFieldCmd` (qui fait un `setattr`) ne s'y applique pas. Le reste est
    identique, fusion comprise — maintenir une flèche sur un spinbox ne doit
    pas remplir l'historique."""

    def __init__(self, table, row: dict, column: str,
                 old_val: Any, new_val: Any, persist_fn=None):
        self._table  = table
        self._row    = row
        self._column = column
        self._old    = old_val
        self._new    = new_val
        self.label   = f"{table.name}.{column}"
        self._persist = persist_fn

    def _write(self, value):
        self._row[self._column] = value
        if self._persist:
            self._persist()

    def execute(self):
        self._write(self._new)

    def undo(self):
        self._write(self._old)

    def merge(self, newer: "Command") -> bool:
        if not isinstance(newer, SetCellCmd):
            return False
        if self._row is newer._row and self._column == newer._column:
            self._new = newer._new
            self._persist = newer._persist
            return True
        return False


class InsertRowCmd(Command):
    """Insertion d'une ligne à un RANG précis.

    `AddListItemCmd` ajoute en fin de liste ; ici le rang compte, parce qu'il
    EST ce qu'un script indexe (`data.Objets[3]`). Insérer au milieu décale
    tout ce qui suit — c'est le comportement voulu, la grille numérote les
    lignes pour que ça se voie."""

    def __init__(self, table, index: int, row: dict, persist_fn=None):
        self._table = table
        self._index = index
        self._row   = row
        self.label  = f"Ligne {index + 1} de {table.name}"
        self._persist = persist_fn

    def execute(self):
        self._table.rows.insert(min(self._index, len(self._table.rows)), self._row)
        if self._persist:
            self._persist()

    def undo(self):
        if self._row in self._table.rows:
            self._table.rows.remove(self._row)
        if self._persist:
            self._persist()


class AddColumnCmd(Command):
    """Ajout d'une colonne. Les lignes existantes ne la mentionnent pas : elles
    prennent son défaut à la lecture (cf. `DataTable.value`), donc il n'y a rien
    à écrire dedans."""

    def __init__(self, table, column: DataColumn, persist_fn=None):
        self._table  = table
        self._column = column
        self.label   = f"Colonne {column.name}"
        self._persist = persist_fn

    def execute(self):
        if self._column not in self._table.columns:
            self._table.columns.append(self._column)
        if self._persist:
            self._persist()

    def undo(self):
        if self._column in self._table.columns:
            self._table.columns.remove(self._column)
        if self._persist:
            self._persist()


class RemoveColumnCmd(Command):
    """Suppression d'une colonne, VALEURS COMPRISES.

    Retirer la colonne du schéma sans vider les lignes laisserait des clés
    orphelines dans le JSON ; les vider sans les retenir ferait d'un Ctrl+Z une
    colonne vide. On retient donc les deux — le rang de la colonne et ce que
    chaque ligne y portait."""

    def __init__(self, table, column: DataColumn, persist_fn=None):
        self._table  = table
        self._column = column
        self._index  = table.columns.index(column)
        self._values = {id(r): r[column.name] for r in table.rows
                        if column.name in r}
        self.label   = f"Colonne {column.name}"
        self._persist = persist_fn

    def execute(self):
        if self._column in self._table.columns:
            self._table.columns.remove(self._column)
        for r in self._table.rows:
            r.pop(self._column.name, None)
        if self._persist:
            self._persist()

    def undo(self):
        if self._column not in self._table.columns:
            self._table.columns.insert(min(self._index, len(self._table.columns)),
                                       self._column)
        for r in self._table.rows:
            if id(r) in self._values:
                r[self._column.name] = self._values[id(r)]
        if self._persist:
            self._persist()


class SetColumnTypeCmd(Command):
    """Changement de type d'une colonne.

    Les valeurs déjà saisies ne survivent pas au changement — un nom de sfx ne
    veut rien dire dans une colonne d'entiers — donc la colonne est VIDÉE, et
    l'annulation les rend. Vider est le seul comportement honnête : convertir
    inventerait des valeurs, et garder afficherait dans une colonne `int` des
    chaînes que le build refuserait."""

    def __init__(self, table, column: DataColumn, new_type: str, persist_fn=None):
        self._table  = table
        self._column = column
        self._old    = column.type
        self._new    = new_type
        self._values = {id(r): r[column.name] for r in table.rows
                        if column.name in r}
        self.label   = f"{column.name} : {new_type}"
        self._persist = persist_fn

    def execute(self):
        self._column.type = self._new
        for r in self._table.rows:
            r.pop(self._column.name, None)
        if self._persist:
            self._persist()

    def undo(self):
        self._column.type = self._old
        for r in self._table.rows:
            if id(r) in self._values:
                r[self._column.name] = self._values[id(r)]
        if self._persist:
            self._persist()
