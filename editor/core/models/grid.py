"""Grid : une grille de valeurs peinte par l'auteur, lue par un script.

Une grille appartient à SA SCÈNE, comme la carte de collision, et porte un
contenu identique dans toutes ses cases, retrouvées par leur position. C'est ce
qui la distingue d'une `DataTable`, dont le contenu diffère d'une colonne à
l'autre. Un script la lit par `data.grid.<Nom>`, une table par
`data.table.<Nom>`.

Elle ne dessine rien. Le moteur ne la montre jamais : c'est de la donnée de
gameplay (coût d'un terrain, cases interdites, points d'apparition, visibilité
par camp), et son affichage éventuel est un geste de script qui peint un calque.

**Un octet par case.** Chiffré le 2026-11-18 : une grille au pas de 16 px coûte
544 octets sur la scène de la démo publique, soit 0,4 % de sa ROM. Les valeurs
vont donc de 0 à `GRID_VALUE_MAX`, et la grille est émise en `const` dans la
ROM, sans compression (une compression par plages grèverait l'accès, qui est la
seule raison d'être d'une grille).

**Le pas est une puissance de deux** (`GRID_STEPS`) : passer d'un pixel à une
case est alors un décalage de bits, et la GBA n'a pas d'instruction de division.
16 px par défaut, la maille des jeux visés.

**Pas d'en-tête d'identité** (`name` / `id` / `source`) : une grille n'est pas
posée dans la scène, elle n'a ni position ni parent. Elle suit le précédent de
`DataTable`, citée par son nom et par rien d'autre.

Module feuille : il n'importe rien du projet, comme `collision_tiles.py`, parce
que le modèle de scène, le canvas qui peindra la grille et le codegen qui
l'émettra en C doivent tous trois lire la même définition.
"""

from dataclasses import dataclass, field

# Pas possibles, en pixels. La carte de collision garde le 8 ; 32 sert aux
# grandes cartes de gameplay (une scène de 1 656 x 952 px tient alors dans
# 1,5 Kio au lieu de 24).
GRID_STEPS = (8, 16, 32)
GRID_STEP_DEFAULT = 16

# Une case est un octet. La carte de collision n'utilise que 26 de ces valeurs :
# le plafond ne mord pas, et il dit que l'octet est la bonne largeur.
GRID_VALUE_EMPTY = 0
GRID_VALUE_MAX = 255


def make_cells(width_px: int, height_px: int, step: int = GRID_STEP_DEFAULT) -> list[list[int]]:
    """Une grille vide aux dimensions de la scène, en cases de `step` pixels."""
    step = step if step in GRID_STEPS else GRID_STEP_DEFAULT
    cols = max(1, (width_px + step - 1) // step)
    rows = max(1, (height_px + step - 1) // step)
    return [[GRID_VALUE_EMPTY] * cols for _ in range(rows)]


@dataclass
class GridValue:
    """Une valeur nommée de la légende.

    Le nom est ce qu'un script cite ; la couleur n'est qu'un repère d'éditeur
    pour la surcouche, sans effet sur ce qui part en ROM (même règle que
    `DataColumn.color`)."""
    value: int = GRID_VALUE_EMPTY
    name: str = ""
    color: str = ""

    def to_dict(self) -> dict:
        return {"value": self.value, "name": self.name, "color": self.color}

    @classmethod
    def from_dict(cls, d: dict) -> "GridValue":
        return cls(value=max(GRID_VALUE_EMPTY, min(GRID_VALUE_MAX, int(d.get("value", 0)))),
                   name=str(d.get("name", "")),
                   color=str(d.get("color", "")))


@dataclass
class Grid:
    """Une grille nommée d'une scène : son pas, sa légende, ses cases.

    `cells` est une liste de RANGÉES de colonnes (`cells[row][col]`), la même
    forme que `Scene.collision_map` : le JSON reste lisible à la main et
    l'émission ROM met la carte à plat de la même façon."""
    name: str = "Grid"
    step: int = GRID_STEP_DEFAULT
    values: list = field(default_factory=list)   # list[GridValue], la légende
    cells: list = field(default_factory=list)    # list[row][col], un octet par case
    # Grille modifiable au runtime : ses cases sont copiées en RAM à l'entrée de
    # scène (germe = `cells`, ou zéro si vide), partagées par tous les scripts de
    # la scène via `data.grid.<Nom>`, et inscriptibles par les méthodes de grille.
    # Fausse par défaut : une grille reste `const` en ROM, lue seule. Même patron
    # que `Scene.collision_mutable`.
    ram: bool = False

    def __post_init__(self):
        # Invariant : `values` tient toujours des `GridValue`, quel que soit le
        # chemin de construction (constructeur direct comme relecture).
        self.values = [v if isinstance(v, GridValue) else GridValue.from_dict(v)
                       for v in self.values]
        if self.step not in GRID_STEPS:
            self.step = GRID_STEP_DEFAULT

    @property
    def cols(self) -> int:
        return max((len(row) for row in self.cells), default=0)

    @property
    def rows(self) -> int:
        return len(self.cells)

    def value_named(self, name: str):
        """L'entrée de légende qui porte ce nom, ou None."""
        return next((v for v in self.values if v.name == name), None)

    def ensure_size(self, width_px: int, height_px: int) -> None:
        """Initialise les cases, ou les AGRANDIT à la taille de la scène.

        Jamais de rognage : réduire un fond ne doit pas détruire ce que l'auteur
        a déjà peint. Même contrat que `Scene.ensure_collision_map`."""
        want = make_cells(width_px, height_px, self.step)
        if not self.cells:
            self.cells = want
            return
        cols = max(len(want[0]), self.cols)
        rows = max(len(want), self.rows)
        for row in self.cells:
            row.extend([GRID_VALUE_EMPTY] * (cols - len(row)))
        while len(self.cells) < rows:
            self.cells.append([GRID_VALUE_EMPTY] * cols)

    def cells_at_step(self, width_px: int, height_px: int, step: int) -> list[list[int]]:
        """Rééchantillonne la grille dans le même espace monde.

        Chaque nouvelle case lit l'ancienne case qui contient son centre. Le
        passage vers une maille plus fine duplique donc les régions peintes ;
        vers une maille plus grosse, il choisit un échantillon prévisible. La
        commande d'interface garde les deux états pour rendre ce choix
        intégralement annulable.
        """
        step = step if step in GRID_STEPS else GRID_STEP_DEFAULT
        width_px = max(width_px, self.cols * self.step)
        height_px = max(height_px, self.rows * self.step)
        cells = make_cells(width_px, height_px, step)
        if not self.cells:
            return cells
        for row in range(len(cells)):
            old_row = min(self.rows - 1, (row * step + step // 2) // self.step)
            source = self.cells[old_row]
            if not source:
                continue
            for col in range(len(cells[row])):
                old_col = min(len(source) - 1,
                              (col * step + step // 2) // self.step)
                cells[row][col] = source[old_col]
        return cells

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "step": self.step,
            "values": [v.to_dict() for v in self.values],
            "cells": self.cells,
            # Absent du JSON quand faux, comme `Scene.collision_mutable`.
            **({"ram": True} if self.ram else {}),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Grid":
        step = int(d.get("step", GRID_STEP_DEFAULT))
        return cls(
            name=str(d.get("name", "Grid")),
            step=step if step in GRID_STEPS else GRID_STEP_DEFAULT,
            values=[GridValue.from_dict(v) for v in d.get("values", []) if isinstance(v, dict)],
            cells=[[max(GRID_VALUE_EMPTY, min(GRID_VALUE_MAX, int(c))) for c in row]
                   for row in d.get("cells", [])],
            ram=bool(d.get("ram", False)),
        )
