"""Lien entre une DataTable et une séquence de textes (cf. `core/text_sequences`).

Le lien est un état de la table (`DataTable.text_link` : préfixe et colonne
clé) : elle seule sait qu'elle est reliée, personne d'autre ne la réécrit. Le
groupe est ce que la règle des clés désigne, rien d'autre. Une ligne est
identifiée par sa clé : les clés se renumérotent d'elles-mêmes et
`rename_text_key` réécrit les cellules, donc retirer une page ne décale jamais
les autres colonnes. Relier ne change que le nombre de lignes ; une ligne dont
la page a disparu est perdue.
"""
import re

from core.history import Command
from core.text_sequences import group_keys


def key_column(table):
    column = table.column(table.text_link.get("column", ""))
    return column if column is not None and column.type == "text" else None


def _cell(table, row, column) -> str:
    return str(table.value(row, column) or "").strip()


def link_state(project, table):
    """None si la table n'est pas reliée, sinon 'current' | 'different' | 'missing_column'."""
    if not table.text_link:
        return None
    column = key_column(table)
    if column is None:
        return "missing_column"
    keys = group_keys(project, table.text_link.get("prefix", ""))
    return "current" if [_cell(table, r, column) for r in table.rows] == keys else "different"


def row_changes(project, table, prefix, column) -> tuple[int, int]:
    """(lignes ajoutées, lignes perdues) si on synchronise maintenant."""
    keys = group_keys(project, prefix)
    have = [_cell(table, r, column) for r in table.rows]
    return len(set(keys) - set(have)), sum(cell not in keys for cell in have)


def _follow(project, table, column, prefix):
    """Les lignes suivent les clés du groupe ; une ligne qui existe garde son objet
    (l'historique de cellules la cible)."""
    existing = {}
    for row in table.rows:
        existing.setdefault(_cell(table, row, column), row)
    table.rows[:] = [existing.get(key) or {column.name: key}
                     for key in group_keys(project, prefix)]


def text_signature(project) -> tuple:
    return tuple(t.key for t in project.texts)


class TableSync:
    """Réaligne les tables liées quand les clés de texte ont changé depuis la dernière fois.

    On compare au dernier état VU, pas à celui d'avant la commande : certains gestes de l'écran
    Texte modifient les textes avant de pousser leur commande. Une commande sans rapport (un
    déplacement d'acteur, un trait de sprite) ne change pas les clés : elle ne touche à aucune ligne."""

    def __init__(self, project):
        self.project, self.seen = project, text_signature(project)

    def __call__(self):
        """Renvoie de quoi défaire (`.changed` : des lignes ont bougé), ou None si rien à faire."""
        now = text_signature(self.project)
        if now == self.seen:
            return None
        self.seen = now
        restore = sync_linked_tables(self.project)

        def undo():
            if restore:
                restore()
            self.seen = text_signature(self.project)     # l'annulation a aussi changé les textes
        undo.changed = restore is not None
        return undo


def sync_linked_tables(project):
    """Aligne chaque table liée sur sa séquence ; renvoie de quoi défaire, ou None."""
    before = []
    for table in project.data_tables:
        column = key_column(table) if table.text_link else None
        if column is not None and link_state(project, table) == "different":
            before.append((table, list(table.rows)))
            _follow(project, table, column, table.text_link["prefix"])
            project.data_tables.save(table)
    if not before:
        return None

    def restore():
        for table, rows in before:
            table.rows[:] = rows
            project.data_tables.save(table)
    return restore


def free_tables(project) -> list:
    """Les tables qu'on peut relier : libres, avec une colonne `text`."""
    return [t for t in project.data_tables
            if not t.text_link and any(c.type == "text" for c in t.columns)]


def link_free_table(project, table, prefix, applied=None):
    column = next(c for c in table.columns if c.type == "text")
    return LinkTableCmd(project, table, prefix, column.name, applied)


def create_linked_table(project, prefix, applied=None):
    """Une table neuve d'une colonne `text`, déjà reliée : un seul pas d'historique."""
    from core.history import AddResourceCmd, MacroCmd
    from core.models.data_table import DataTable, DataColumn, IDENTIFIER
    from core.models.unique_name import unique_name
    base = re.sub(r"\W", "_", prefix)
    base = base if IDENTIFIER.match(base) else "T_" + base
    table = DataTable(name=unique_name(base, {t.name for t in project.data_tables}),
                      columns=[DataColumn("line", "text")])
    return MacroCmd([AddResourceCmd(project.data_tables, table, applied),
                     LinkTableCmd(project, table, prefix, "line", applied)],
                    "Create table from text sequence")


class LinkTableCmd(Command):
    """Relier (ou resynchroniser) : les lignes suivent les pages du groupe."""
    label = "Link table to text group"

    def __init__(self, project, table, prefix, column_name, applied=None):
        column = table.column(column_name)
        if column is None or column.type != "text":
            raise ValueError("Key column must be a text column")
        self.project, self.table, self.applied = project, table, applied
        self.link = {"prefix": prefix, "column": column_name}
        self._before = (dict(table.text_link), list(table.rows))

    def _persist(self):
        self.project.data_tables.save(self.table)
        if self.applied:
            self.applied()

    def execute(self):
        column = self.table.column(self.link["column"])
        _follow(self.project, self.table, column, self.link["prefix"])
        self.table.text_link = dict(self.link)
        self._persist()

    def undo(self):
        self.table.text_link, rows = dict(self._before[0]), self._before[1]
        self.table.rows[:] = rows
        self._persist()


class UnlinkTableCmd(Command):
    """Délier : les lignes restent telles quelles."""
    label = "Unlink table from text group"

    def __init__(self, project, table, applied=None):
        self.project, self.table, self.applied = project, table, applied
        self._before = dict(table.text_link)

    def _set(self, link):
        self.table.text_link = link
        self.project.data_tables.save(self.table)
        if self.applied:
            self.applied()

    def execute(self):
        self._set({})

    def undo(self):
        self._set(dict(self._before))
