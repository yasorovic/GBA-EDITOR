"""Surface de valeurs peignable sur le canvas de scène.

Collision et ``Grid`` stockent toutes deux une liste de rangées d'entiers. Ce
module donne à l'outil commun le contrat minimal dont il a besoin, sans faire
croire que leurs valeurs ont la même signification.
"""
from __future__ import annotations


class GridPaintSurface:
    """Une surface rectangulaire de valeurs, repérée par des cellules.

    ``cells`` reste la source de vérité. Le canvas de collision continue donc
    d'afficher la même carte que la physique, et une ``Grid`` conserve son
    format JSON inchangé.
    """

    def __init__(self, name: str, cell_size: int, cells: list[list[int]] | None = None,
                 empty_value=0, changed=None, read=None, write=None, bounds=None):
        if cells is None and (read is None or write is None):
            raise ValueError("A painted surface needs cells or read/write accessors")
        self.name = name
        self.cell_size = cell_size
        self.cells = cells
        self.empty_value = empty_value
        self._changed = changed
        self._read = read
        self._write = write
        self._bounds = bounds

    @property
    def rows(self) -> int:
        return len(self.cells) if self.cells is not None else 0

    @property
    def cols(self) -> int:
        return max((len(row) for row in self.cells), default=0) if self.cells is not None else 0

    def contains(self, col: int, row: int) -> bool:
        if self.cells is not None:
            return 0 <= row < self.rows and 0 <= col < len(self.cells[row])
        if self._bounds is None:
            return True
        cols, rows = self._bounds()
        return 0 <= col < cols and 0 <= row < rows

    def scene_to_cell(self, x: float, y: float) -> tuple[int, int]:
        return int(x // self.cell_size), int(y // self.cell_size)

    def value_at(self, col: int, row: int) -> int:
        if not self.contains(col, row):
            return self.empty_value
        return self._read(col, row) if self._read else self.cells[row][col]

    def set_value(self, col: int, row: int, value, *, notify: bool = True) -> bool:
        """Écrit une cellule existante et indique si elle a réellement changé."""
        if not self.contains(col, row) or self.value_at(col, row) == value:
            return False
        if self._write:
            self._write(col, row, value)
        else:
            self.cells[row][col] = value
        if notify and self._changed:
            self._changed()
        return True

    def apply_delta(self, delta: dict, forward: bool):
        """Réapplique un trait d'historique sans connaître sa valeur métier."""
        for (col, row), pair in delta.items():
            self.set_value(col, row, pair[1 if forward else 0], notify=False)
        self.notify_changed()

    def notify_changed(self):
        if self._changed:
            self._changed()


class SceneInpaintingSurface:
    """Surface d'un calque BG, dont la valeur est une banque ou son absence.

    Une banque absente se représente par ``None`` : ce n'est pas la valeur 0
    d'une grille. La surface garde cette différence de stockage hors de la
    commande d'historique commune.
    """

    def __init__(self, controller, layer, bg_slot: int):
        self.name = f"BG{bg_slot}"
        self.cell_size = 8
        self.empty_value = None
        self._controller = controller
        self._layer = layer
        self._bg_slot = bg_slot

    def contains(self, col: int, row: int) -> bool:
        cols, rows = self._controller.tiles_size()
        return 0 <= col < cols and 0 <= row < rows

    def scene_to_cell(self, x: float, y: float) -> tuple[int, int]:
        return int(x // self.cell_size), int(y // self.cell_size)

    def value_at(self, col: int, row: int):
        if not self.contains(col, row):
            return self.empty_value
        return self._layer.tile_palette_overrides.get((col, row))

    def set_value(self, col: int, row: int, value, *, notify: bool = True) -> bool:
        return self._controller.set_override(col, row, value, refresh=notify)

    def notify_changed(self):
        self._controller.refresh()

    def apply_delta(self, delta: dict, forward: bool):
        self._controller.apply_override_delta(self._layer, self._bg_slot, delta, forward)
