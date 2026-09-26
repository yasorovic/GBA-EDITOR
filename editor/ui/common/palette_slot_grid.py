"""editor/ui/common/palette_slot_grid.py — grille de banques de palettes partagée.

`PaletteSlotGridAsset` matérialise l'allocation de palettes d'un pool (jusqu'à 16
banques) sous forme de grille compacte de swatches, sur le **modèle du Scene
Inspector** :

  [ palettes éditables (catalogue) ][ bouton + ][ palettes propres (grisées / override) ]

Les cellules passent à la ligne selon la largeur disponible, sur 4 lignes au
plus (16 banques → jamais moins de 4 colonnes). Seules les banques OCCUPÉES sont
dessinées : le widget se resserre au lieu de montrer des cases noires vides.

Consommateurs (une même vue duck-typée, cf. `codegen.palette_alloc.ScenePaletteView`
ou toute vue équivalente au tier asset) :
- Scene Inspector (palettes actives OBJ/BG d'une scène) ;
- (à venir) Background Editor / Sprite Editor au tier asset (PAL_BANK de l'objet).

La vue fournie expose : `scene_entries`, `asset_entries`, `can_add()`. Les entrées
sont duck-typées (cf. `ScenePaletteEntry` / `AssetPaletteEntry`). Le widget est
purement une vue : il émet des signaux, le consommateur mute son modèle et
recharge.
"""
from __future__ import annotations

from ui.common.labels import label
from PyQt6.QtWidgets import QWidget, QPushButton, QLayout
from PyQt6.QtCore import Qt, QSize, QRect, QPoint, pyqtSignal

from ui.common.theme import C
from ui.common.widgets import ScriptPickerPopup
from ui.common.palette_swatch import (
    bank_icon as _bank_icon, swatch_icon as _swatch_icon, plus_icon as _plus_icon,
)


class _WrapLayout(QLayout):
    """Cellules de taille fixe, rangées de gauche à droite et renvoyées à la
    ligne selon la largeur offerte — jamais plus de `max_rows` lignes : le
    nombre de colonnes ne descend pas sous ceil(n / max_rows)."""

    def __init__(self, parent, cell: int, spacing: int, max_rows: int):
        super().__init__(parent)
        self._items = []
        self._cell = cell
        self._gap = spacing
        self._max_rows = max_rows
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def _columns(self, width: int) -> int:
        count = len(self._items)
        fit = max(1, (width + self._gap) // (self._cell + self._gap))
        return max(1, min(count, max(fit, -(-count // self._max_rows))))

    def _extent(self, columns: int, rows: int) -> tuple[int, int]:
        return (columns * self._cell + (columns - 1) * self._gap,
                rows * self._cell + (rows - 1) * self._gap)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        count = len(self._items)
        if not count:
            return 0
        return self._extent(1, -(-count // self._columns(width)))[1]

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        columns = self._columns(rect.width())
        for index, item in enumerate(self._items):
            row, col = divmod(index, columns)
            item.setGeometry(QRect(
                QPoint(rect.x() + col * (self._cell + self._gap),
                       rect.y() + row * (self._cell + self._gap)),
                QSize(self._cell, self._cell)))

    def sizeHint(self):
        count = len(self._items)
        if not count:
            return QSize(0, 0)
        columns = min(count, 8)
        return QSize(*self._extent(columns, -(-count // columns)))

    def minimumSize(self):
        count = len(self._items)
        if not count:
            return QSize(0, 0)
        return QSize(*self._extent(-(-count // self._max_rows), 1))


# ──────────────────────────────────────────────────────────────────
#  PaletteSlotGridAsset — vue live des 16 banques d'un pool (cf. palette_alloc)
# ──────────────────────────────────────────────────────────────────
class PaletteSlotGridAsset(QWidget):
    """
    Grille compacte à retour à la ligne (4 lignes au plus) qui matérialise
    l'allocation d'une scène (ScenePaletteView), dans l'ordre :

      [ palettes de scène (éditables) ][ bouton + ][ palettes d'asset (grisées / override) ]

    - palette de scène : clic = remplacer (catalogue), clic droit = retirer ;
    - palette d'asset « own » (grisée) : clic = override par une palette du
      CATALOGUE de l'éditeur (comme une couleur normale) ; « override »
      (marqueur d'angle) : clic droit = revenir à la palette d'origine de
      l'asset ;
    - « + » : ajoute une palette de scène (masqué quand les 16 banques sont
      pleines).
    """

    scene_replace  = pyqtSignal(int, str)        # slot hardware, nouveau nom
    scene_add      = pyqtSignal(str)             # nouveau nom de palette de scène
    scene_remove   = pyqtSignal(int)             # slot hardware à retirer
    # AssetPaletteEntry, nom de banque catalogue (str) — le consommateur
    # résout/réutilise le slot actif (tier scène) ou l'override direct
    # (tier asset, cf. SubPaletteAssetMixin.palette_overrides).
    asset_override = pyqtSignal(object, object)
    asset_restore  = pyqtSignal(object)          # AssetPaletteEntry

    _ICON_SIZE = 28
    _MAX_ROWS = 4

    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self._accent = accent
        self._layout = _WrapLayout(self, self._ICON_SIZE + 10, 4, self._MAX_ROWS)
        self._buttons: list[QPushButton] = []
        self._catalog: list = []

    # ── Styles de cellule ─────────────────────────────────────────
    def _style(self, *, bg: str, border: str, dashed: bool = False, width: int = 1) -> str:
        b = "dashed" if dashed else "solid"
        return (f"QPushButton{{background:{bg};border:{width}px {b} {border};border-radius:4px;}}"
                f"QPushButton:hover{{border-color:{self._accent};}}")

    def load(self, view, catalog: list):
        """view : ScenePaletteView ; catalog : list[PaletteBank] (choix +/replace)."""
        for b in self._buttons:
            self._layout.removeWidget(b)
            b.deleteLater()
        self._buttons.clear()
        self._catalog = catalog

        # Ordre : palettes de scène → bouton « + » (séparateur) → palettes
        # d'asset (grisées). Le « + » sépare l'éditable du
        # grisé ; ajouter une palette de scène le décale (ainsi que les assets)
        # vers la droite. Le « + » n'occupe pas de banque : il disparaît quand
        # les 16 sont pleines, et scène/assets redeviennent contigus.
        cells: list[tuple[str, object]] = []
        for e in view.scene_entries:
            cells.append(("scene", e))
        if view.can_add():
            cells.append(("plus", None))
        for e in view.asset_entries:
            # Un fond compressé occupe un BLOC de N banques → N cellules
            # (même swatch), pour que la grille reflète les banques consommées.
            for _ in range(max(1, getattr(e, "bank_span", 1))):
                cells.append(("asset", e))

        for kind, entry in cells[:16]:
            btn = self._make_cell(kind, entry, view)
            self._layout.addWidget(btn)
            self._buttons.append(btn)
        self.updateGeometry()

    def _make_cell(self, kind: str, entry, view) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(self._ICON_SIZE + 10, self._ICON_SIZE + 10)
        btn.setIconSize(QSize(self._ICON_SIZE, self._ICON_SIZE))
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        if kind == "scene":
            btn.setIcon(_swatch_icon(entry.colors, self._ICON_SIZE))
            btn.setToolTip(label('palslot.slot_tip', slot=entry.slot, name=entry.name))
            btn.setStyleSheet(self._style(bg=C.BG_INPUT, border=C.BORDER_MID))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, e=entry, b=btn: self._pick_scene(b, e.slot))
            btn.customContextMenuRequested.connect(
                lambda _p, e=entry: self.scene_remove.emit(e.slot))

        elif kind == "asset":
            names = ", ".join(i.label for i in entry.instances)
            if entry.state == "override":
                # Tier asset : l'entrée porte directement ses couleurs/nom de
                # cible (ref_colors/ref_name) — pas besoin d'un scene_entry cible.
                # Tier scène : on résout la cible par slot dans scene_entries.
                target = next((s for s in view.scene_entries
                               if s.slot == entry.ref_slot), None)
                cols = (getattr(entry, "ref_colors", None)
                        or (target.colors if target else entry.own_colors))
                btn.setIcon(_swatch_icon(cols, self._ICON_SIZE,
                                         override=True, marker_color=self._accent))
                tgt = (getattr(entry, "ref_name", None)
                       or (target.name if target else "?"))
                btn.setToolTip(label('palslot.override_tip', names=names, tgt=tgt))
                btn.setStyleSheet(self._style(bg=C.BG_INPUT, border=self._accent))
                btn.customContextMenuRequested.connect(
                    lambda _p, e=entry: self.asset_restore.emit(e))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _c, e=entry, b=btn: self._pick_override(b, e))
            elif not getattr(entry, "overridable", True):
                # Bloc compressé : palette d'asset fixe, non remappable.
                btn.setIcon(_swatch_icon(entry.own_colors, self._ICON_SIZE, greyed=True))
                span = getattr(entry, "bank_span", 1)
                span_txt = label('palslot.bank_span', count=span) if span > 1 else ""
                btn.setToolTip(label('palslot.compressed_tip', names=names, span_txt=span_txt))
                btn.setStyleSheet(
                    f"QPushButton{{background:{C.BG_BASE};"
                    f"border:1px solid {C.BORDER_DARK};border-radius:4px;}}")
            else:  # own — palette propre grisée (overridable)
                btn.setIcon(_swatch_icon(entry.own_colors, self._ICON_SIZE, greyed=True))
                btn.setToolTip(label('palslot.own_palette_tip', names=names))
                btn.setStyleSheet(self._style(bg=C.BG_BASE, border=C.BORDER_MID, dashed=True))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _c, e=entry, b=btn: self._pick_override(b, e))

        elif kind == "plus":
            btn.setIcon(_plus_icon(self._ICON_SIZE, self._accent))
            btn.setToolTip(label('palslot.add_a_scene_palette'))
            btn.setStyleSheet(
                f"QPushButton{{background:{C.BG_INPUT};"
                f"border:1px dashed {self._accent};border-radius:4px;}}"
                f"QPushButton:hover{{background:{C.SEL_BG};}}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, b=btn: self._pick_add(b))

        else:
            raise ValueError(f"cellule de palette inconnue : {kind}")

        return btn

    # ── Pickers ───────────────────────────────────────────────────
    def _catalog_entries(self) -> list:
        return [(b.name, b.name, _bank_icon(b)) for b in self._catalog]

    def _pick_scene(self, anchor: QPushButton, slot: int):
        popup = ScriptPickerPopup(self._catalog_entries(), self._accent,
                                  parent=self, new_label=None)
        popup.picked.connect(lambda name, s=slot: self.scene_replace.emit(s, name))
        popup.show_below(anchor)

    def _pick_add(self, anchor: QPushButton):
        popup = ScriptPickerPopup(self._catalog_entries(), self._accent,
                                  parent=self, new_label=None)
        popup.picked.connect(lambda name: self.scene_add.emit(name))
        popup.show_below(anchor)

    def _pick_override(self, anchor: QPushButton, entry):
        """Popup de choix de la cible d'override : tout le CATALOGUE de
        l'éditeur (comme une couleur normale), aux deux tiers — emit (entry,
        nom_catalogue:str). Au tier scène, le consommateur (SceneInspector)
        réutilise un slot actif existant portant ce nom, ou l'ajoute au
        premier slot libre : jamais deux slots pour la même palette."""
        if not self._catalog:
            return
        popup = ScriptPickerPopup(self._catalog_entries(), self._accent,
                                  parent=self, new_label=None)
        popup.picked.connect(lambda name, e=entry: self.asset_override.emit(e, name))
        popup.show_below(anchor)
