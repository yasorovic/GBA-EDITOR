"""
ui/text_editor/text_table.py — colonne centre (contexte Texte), partie HAUTE :
la table des textes.

`texts.json` reste une liste plate, mais son rangement est montré comme un
arbre : un chemin de six niveaux ne doit ni disparaître, ni devenir six
colonnes de plus. Chaque nœud emploie la même pastille et se replie comme un
dossier ; son renommage propage le nouveau segment à tous ses descendants.

Aucune colonne ne s'appelle « Key » pour un niveau de chemin : dans le modèle,
`key` désigne une chose et une seule — la poignée que le Lua écrit et que le
build résout. Un niveau de rangement n'est jamais résolu ni référencé. Deux
mots pour deux choses.

Cette vue ne MODIFIE rien : elle dit ce qui a été édité et laisse le panneau en
tirer une commande annulable. Le modèle est plat et l'ordre des lignes est un
tri d'affichage — laisser Qt écrire dans la table la ferait mentir hors
historique.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QToolButton, QApplication,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView,
    QStyledItemDelegate, QStyle,
)
from PyQt6.QtGui import QFont, QFontMetrics, QColor, QBrush, QPen, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF, QPointF, QEvent

from core.text_markup import parse, resolve
from core.models.text import SEP
from ui.common.theme import C, T, S
from ui.common.widgets import W
from ui.common import icons
from ui.common.labels import label
from ui.text_editor.colors import TEXT_COLOR


# Une colonne = un rôle, nommé une fois ici : la construction des lignes, le
# routage du double-clic et le tri s'y réfèrent tous les trois.
COL_KEY, COL_CONTENT, COL_STATUS, COL_USED, COL_PATH = range(5)
# Clés de libellé des en-têtes, dans l'ordre des colonnes — résolues à l'usage.
_HEADER_KEYS = ("txttbl.h_key", "txttbl.h_content", "txttbl.h_status",
                "txttbl.h_used", "txttbl.h_path")

_ROLE_TEXT = Qt.ItemDataRole.UserRole        # Text, sur une ligne
_ROLE_GROUP = Qt.ItemDataRole.UserRole + 1   # tuple[str, ...], nœud de rangement
_ROLE_SORT = Qt.ItemDataRole.UserRole + 2    # clé de tri, quand ≠ de l'affichage

# Ce que la ligne raconte d'elle-même, indépendamment du filtre.
FLAG_EMPTY = "empty"      # référencée peut-être, mais rien à afficher
FLAG_UNUSED = "unused"    # écrite, mais personne ne la demande
# N'existe que pendant qu'on TRADUIT une langue — cf. `_apply_filter`. Distinct
# de FLAG_EMPTY : une entrée non traduite affiche la SOURCE (donc rarement
# vide), et une entrée traduite peut très bien être vide. Deux axes, deux
# flags, comme le veut la ROADMAP v0.9.
FLAG_MISSING = "missing"

class _PathDelegate(QStyledItemDelegate):
    """Peint chaque nœud de rangement avec la même pastille."""

    def paint(self, painter: QPainter, option, index):
        disp = index.data(Qt.ItemDataRole.DisplayRole) or ""
        # Le fond de sélection est peint par la vue pour les autres colonnes :
        # sans ce rappel, la ligne sélectionnée aurait un trou ici.
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(C.BG_SEL))
        if not disp:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        w = min(painter.fontMetrics().horizontalAdvance(disp) + 12,
                max(option.rect.width() - 8, 16))
        r = QRectF(option.rect.left() + 6, option.rect.center().y() - 7.0, w, 15.0)
        painter.setPen(QPen(QColor(C.BORDER_MID)))
        painter.setBrush(QBrush(QColor(C.BG_RAISED)))
        painter.drawRoundedRect(r, 3, 3)
        painter.setPen(QPen(QColor(C.TEXT_DIM)))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, disp)
        painter.restore()


class _KeyDelegate(QStyledItemDelegate):
    """Isole la poignée Lua du contenu et des données de lecture.

    La clé est volontairement à droite : on la consulte pour relier un script,
    pas pour lire la table. Le filet garde cette frontière visible, même sur
    une ligne sélectionnée ou très longue.
    """

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        painter.save()
        # L'icône fait partie du rendu de la cellule, plutôt qu'un widget
        # ajouté par-dessus : une seule clé, aucune découpe ni doublon.
        icon = icons.get("copy", C.TEXT_DIM)
        size = 15
        x = option.rect.right() - size - 8
        y = option.rect.center().y() - size // 2
        icon.paint(painter, x, y, size, size)
        painter.restore()


class _Row(QTreeWidgetItem):
    """Une ligne qui se trie par ce qu'elle VAUT, pas par ce qu'elle affiche.

    « 12 scripts » se range avant « 2 scripts » dans l'ordre alphabétique, et
    une colonne d'usage qui trie faux est pire qu'une colonne qui ne trie
    pas."""

    def __lt__(self, other):
        tree = self.treeWidget()
        col = tree.sortColumn() if tree is not None else 0
        a, b = self.data(col, _ROLE_SORT), other.data(col, _ROLE_SORT)
        if a is not None and b is not None:
            return a < b
        return self.text(col).casefold() < other.text(col).casefold()


class TextTable(QWidget):
    """La table des textes, ses filtres et son groupement.

    Vue seulement : elle signale ce qui a été édité, le panneau décide."""

    selection_changed = pyqtSignal(list)               # [Text] (vide = plus rien)
    key_edited = pyqtSignal(object, str)               # (Text, clé saisie)
    group_renamed = pyqtSignal(object, str)            # (chemin du nœud, nouveau nom)
    add_asked = pyqtSignal()
    delete_asked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._project = None
        self._usages = None            # TextUsageIndex, None = à reconstruire
        self._blocking = False
        self._values: dict = {}
        # "" = source. Reçue de l'extérieur — cf. `set_active_lang` — la table
        # ne CHOISIT plus la langue depuis la v0.9.2 : les onglets de l'atelier
        # s'en chargent, elle en tire juste ce que Content/Status/le chip
        # « Missing » doivent montrer.
        self._active_lang = ""
        self._folder_filter: tuple[str, ...] = ()
        # Nœuds explicitement REPLIÉS : un nouveau nœud reste visible sans
        # demander d'aller le chercher dans un arbre fermé.
        self._collapsed: set[tuple[str, ...]] = set()
        self._flags: dict[int, set[str]] = {}    # {id du texte: {FLAG_*}}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_bar())
        self._crumb_bar = QFrame()
        self._crumb_bar.setFixedHeight(30)
        self._crumb_bar.setStyleSheet(
            f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER_DARK};")
        crumb_layout = QHBoxLayout(self._crumb_bar)
        crumb_layout.setContentsMargins(10, 0, 10, 0)
        self._crumb = QLabel()
        self._crumb.setFont(QFont(T.UI, T.SM))
        self._crumb.setStyleSheet(f"color:{C.TEXT_DIM};")
        crumb_layout.addWidget(self._crumb)
        crumb_layout.addStretch()
        self._crumb_count = QLabel()
        self._crumb_count.setFont(QFont(T.MONO, T.XS))
        self._crumb_count.setStyleSheet(f"color:{C.TEXT_MUTED};")
        crumb_layout.addWidget(self._crumb_count)
        self._crumb_bar.setVisible(False)
        root.addWidget(self._crumb_bar)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_HEADER_KEYS))
        self._tree.setHeaderLabels([label(k) for k in _HEADER_KEYS])
        # La table centrale est plate : le classement se fait dans le Finder.
        # Garder la décoration d'arbre ici réservait inutilement une indentation
        # sur chaque clé et rognait sa fin derrière l'icône de copie.
        self._tree.setRootIsDecorated(False)
        # Un double-clic appartient déjà au pliage natif. Le renommage passe
        # par un clic sur le badge d'un nœud ouvert et sélectionné — voir le
        # filtre d'événements plus bas.
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setAllColumnsShowFocus(True)
        # Multi-sélection : ranger vingt entrées d'un coup est le geste que le
        # glisser-déposer d'un arbre ne savait pas faire.
        self._tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        # Aucun déclencheur automatique : le double-clic est routé à la main
        # vers les colonnes ÉDITABLES — jamais vers le contenu, qui est un
        # rendu (balises résolues) et non la source.
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setItemDelegateForColumn(COL_PATH, _PathDelegate(self))
        self._tree.setItemDelegateForColumn(COL_KEY, _KeyDelegate(self))
        self._tree.setStyleSheet(
            f"QTreeWidget{{background:{C.BG_BASE}; color:{C.TEXT_NORM}; border:none;"
            f"font-family:{T.UI_STACK}; font-size:{T.MD}px; outline:none;}}"
            f"QTreeWidget::item{{padding:6px 10px; height:{S.ROW + 10}px; border:none;}}"
            f"QTreeWidget::item:selected{{background:{C.BG_SEL}; color:{TEXT_COLOR};}}"
            f"QTreeWidget::item:hover:!selected{{background:{C.BG_PANEL};}}"
            f"QHeaderView::section{{background:transparent; color:{C.TEXT_MUTED};"
            f"border:none; border-bottom:1px solid {C.BORDER_DARK}; padding:4px 6px;"
            f"font-family:{T.UI_STACK}; font-size:{T.XS}px; font-weight:700;"
            f"letter-spacing:1px;}}"
            f"QHeaderView::section:hover{{color:{C.TEXT_DIM};}}"
        )
        th = self._tree.header()
        for col in (COL_PATH, COL_KEY):
            th.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        th.setSectionResizeMode(COL_CONTENT, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(COL_USED, QHeaderView.ResizeMode.ResizeToContents)
        for col, width in ((COL_PATH, 260), (COL_KEY, 190)):
            self._tree.setColumnWidth(col, width)
        # Colonne muette tant qu'on n'édite pas une traduction : un projet
        # monolingue — le cas de tous ceux d'avant la v0.9 — ne voit rien de
        # nouveau. `refresh_languages()` la révèle en même temps que la barre.
        self._tree.setColumnHidden(COL_STATUS, True)
        # Le rangement appartient exclusivement au Finder : le centre liste
        # toujours des entrées, y compris à la racine du projet.
        self._tree.setColumnHidden(COL_PATH, True)
        # L'ordre est celui du chemin : trier une colonne transverse casserait
        # visuellement la relation parent → enfant.
        self._tree.setSortingEnabled(False)
        self._tree.itemSelectionChanged.connect(self._on_sel)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.itemExpanded.connect(lambda it: self._on_fold(it, False))
        self._tree.itemCollapsed.connect(lambda it: self._on_fold(it, True))
        self._tree.viewport().installEventFilter(self)
        root.addWidget(self._tree, 1)
        root.addWidget(self._build_footer())

    # ── Barres ────────────────────────────────────────────────────

    def _build_bar(self) -> QFrame:
        hdr = W.finder_bar(label("common.texts"))
        hl = hdr.layout()
        self._count = QLabel("")
        self._count.setFont(QFont(T.MONO, T.XS))
        self._count.setStyleSheet(f"color:{C.TEXT_MUTED};")
        hl.addWidget(self._count)
        hl.addStretch()

        # Deux axes, deux filtres cumulables — pas une pastille unique. Une
        # entrée peut être écrite ET orpheline, ou référencée ET vide : les
        # fondre ferait disparaître celui des deux qui n'a pas la priorité.
        self._chips: dict[str, QToolButton] = {}
        for flag, lbl_key, tip_key in (
            (FLAG_EMPTY, "txttbl.empty", "txttbl.empty_tip"),
            (FLAG_UNUSED, "txttbl.unused", "txttbl.unused_tip"),
            # Ajouté ici pour vivre dans le même style, mais caché tant qu'on
            # n'édite pas une traduction — `refresh_languages()` le révèle.
            (FLAG_MISSING, "txttbl.missing", "txttbl.missing_tip"),
        ):
            b = QToolButton()
            b.setText(label(lbl_key))
            b.setCheckable(True)
            b.setFont(QFont(T.UI, T.XS))
            b.setToolTip(label(tip_key))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QToolButton{{background:transparent; color:{C.TEXT_DIM};"
                f"border:1px solid {C.BORDER}; border-radius:9px; padding:1px 8px;}}"
                f"QToolButton:hover{{color:{C.TEXT_NORM}; border-color:{C.BORDER_MID};}}"
                f"QToolButton:checked{{background:{C.BG_SEL}; color:{TEXT_COLOR};"
                f"border-color:{TEXT_COLOR};}}"
            )
            b.toggled.connect(lambda _c: self._apply_filter())
            hl.addWidget(b)
            self._chips[flag] = b
        self._chips[FLAG_MISSING].setVisible(False)

        self._search = W.search_box(label("txttbl.search"))
        self._search.setFixedWidth(200)
        self._search.textChanged.connect(lambda _q: self._apply_filter())
        hl.addWidget(self._search)

        self._btn_add = W.btn_add(label("txttbl.add_tip"))
        self._btn_add.clicked.connect(self.add_asked.emit)
        hl.addWidget(self._btn_add)
        self._btn_del = W.btn_danger(label("txttbl.delete_tip"))
        self._btn_del.clicked.connect(self.delete_asked.emit)
        self._btn_del.setEnabled(False)
        hl.addWidget(self._btn_del)
        return hdr

    def _build_footer(self) -> QFrame:
        """Ce que la sélection couvre et ce que le filtre cache : deux nombres
        qu'on ne peut pas deviner en regardant des lignes."""
        bar = QFrame()
        bar.setFixedHeight(20)
        bar.setStyleSheet(
            f"background:{C.BG_PANEL}; border-top:1px solid {C.BORDER_DARK};")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 8, 0)
        self._sel_lbl = QLabel("")
        self._sel_lbl.setFont(QFont(T.UI, T.XS))
        self._sel_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        bl.addWidget(self._sel_lbl)
        bl.addStretch()
        self._total_lbl = QLabel("")
        self._total_lbl.setFont(QFont(T.UI, T.XS))
        self._total_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        bl.addWidget(self._total_lbl)
        return bar

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project):
        self._project = project
        self._values = project.text_values() if project else {}
        self._usages = None
        self._active_lang = ""
        self.refresh()

    def invalidate_usages(self):
        """Les scripts ont bougé : l'index est périmé.

        Reconstruit paresseusement, au prochain `refresh` — luaparser est trop
        lent pour être relancé sur un écran qui n'est peut-être pas affiché."""
        self._usages = None

    def _usage_index(self):
        if self._usages is None and self._project is not None:
            self._usages = self._project.text_usage_index()
        return self._usages

    # ── Langue en cours d'édition ────────────────────────────────
    # Choisie par les ONGLETS de l'atelier (`TextWorkbench`), jamais ici : la
    # table en tire seulement ce que Content/Status/le chip « Missing »
    # doivent montrer. `TextPanel` est le relais entre les deux.

    def active_lang(self) -> str:
        return self._active_lang

    def is_translating(self) -> bool:
        """Vrai quand la langue active est une TRADUCTION — pas la source, pas
        « aucune langue déclarée ». C'est ce qui décide si Status et le chip
        « Missing » ont un sens."""
        p = self._project
        return bool(self._active_lang and p
                    and self._active_lang != p.settings.source_lang.code)

    def set_active_lang(self, code: str):
        """La langue éditée change — appelé par le panneau, lui-même averti
        par les onglets de l'atelier."""
        if code == self._active_lang:
            return
        self._active_lang = code
        translating = self.is_translating()
        self._tree.setColumnHidden(COL_STATUS, not translating)
        self._chips[FLAG_MISSING].setVisible(translating)
        if not translating:
            self._chips[FLAG_MISSING].setChecked(False)
        self.refresh()

    def set_folder_filter(self, path) -> None:
        """Limite la liste au dossier choisi dans le Finder des textes."""
        path = tuple(path or ())
        if path != self._folder_filter:
            self._folder_filter = path
            self._update_breadcrumb()
            self.refresh()

    def _update_breadcrumb(self) -> None:
        """Le chemin est dans le Finder ; le centre le rappelle sans arbre."""
        path = self._folder_filter
        self._crumb_bar.setVisible(bool(path))
        if path:
            self._crumb.setText(f"{label('txttbl.h_path')}  {SEP.join(path)}")
            self._crumb_count.setText("")

    def refresh(self, select_ids: Optional[list[int]] = None):
        """Reconstruit la table depuis le projet, sélection conservée."""
        if select_ids is None:
            select_ids = [t.id for t in self.selected_texts()]
        self._blocking = True
        self._tree.clear()
        texts = sorted(self._project.texts, key=lambda t: (tuple(x.casefold() for x in t.path),
                                                            t.key.casefold())) if self._project else []
        usages = self._usage_index()
        self._flags = {}

        groups: dict[tuple[str, ...], QTreeWidgetItem] = {}
        for t in texts:
            row = _Row()
            self._fill_row(row, t, usages)
            # Le Finder porte toute l'arborescence. La zone centrale ne montre
            # jamais de nœuds techniques : elle reste une liste d'entrées.
            self._tree.addTopLevelItem(row)

        for path, item in groups.items():
            item.setExpanded(path not in self._collapsed)

        self._count.setText(f"  {len(texts)}")
        self._apply_filter()
        if self._folder_filter:
            shown = sum(1 for text in texts
                        if tuple(text.path[:len(self._folder_filter)]) == self._folder_filter)
            self._crumb_count.setText(label("txttbl.text_count", n=shown))
        self._blocking = False

        if select_ids:
            self.select_by_ids(select_ids)
        self._on_sel()

    def _path_item(self, path: list[str], groups: dict) -> QTreeWidgetItem:
        """Retourne le nœud du chemin, en créant chacun de ses ancêtres."""
        parent = None
        for depth, segment in enumerate(path):
            node_path = tuple(path[:depth + 1])
            item = groups.get(node_path)
            if item is None:
                item = _Row()
                item.setText(COL_PATH, segment)
                item.setData(COL_PATH, _ROLE_GROUP, node_path)
                item.setIcon(COL_PATH, icons.folder_icon(True, icons.COLOR_FOLDER))
                item.setToolTip(COL_PATH, label("txttbl.group_rename_tip"))
                if parent is None:
                    self._tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
                groups[node_path] = item
            parent = item
        return parent

    def retitle_group(self, old: tuple[str, ...], new: str):
        """Reporte le pliage de tout le sous-arbre après son renommage."""
        old, new_path = tuple(old), tuple(old[:-1]) + (new,)
        self._collapsed = {
            new_path + path[len(old):] if path[:len(old)] == old else path
            for path in self._collapsed
        }

    def _fill_row(self, row: QTreeWidgetItem, t, usages):
        """Une ligne : où c'est rangé, comment ça s'appelle, ce que ça dit, et
        qui s'en sert."""
        row.setData(0, _ROLE_TEXT, t)

        row.setText(COL_KEY, t.key)
        row.setFont(COL_KEY, QFont(T.CODE, T.SM))
        # Clé dérivée = jetable, en retrait ; clé nommée à la main = un contrat
        # posé par quelqu'un, elle mérite l'accent.
        row.setForeground(COL_KEY,
                          QColor(C.TEXT_MUTED if t.auto_key else TEXT_COLOR))
        row.setToolTip(COL_KEY,
                       (label("txttbl.key_auto") if t.auto_key
                        else label("txttbl.key_hand"))
                       + label("txttbl.key_dblclick"))

        flags = set()
        # Le texte tel qu'on le LIT dans la langue ACTIVE : balises retirées,
        # valeurs substituées, et — hors source — repli sur la source tant que
        # rien n'est traduit (`Project.text_content`, point unique de la
        # règle : "" comme langue inconnue rendent tous les deux la source).
        # Le balisage, lui, s'édite dans l'atelier.
        content = (self._project.text_content(t, self._active_lang)
                  if self._project else t.content)
        display = resolve(parse(content), self._values).replace("\n", " ⏎ ")
        row.setText(COL_CONTENT, display or label('txttbl.empty_cell'))
        row.setForeground(COL_CONTENT,
                          QColor(C.TEXT_HI if display else C.ACCENT_YLW))
        if not display:
            flags.add(FLAG_EMPTY)

        if self.is_translating():
            translated = bool(self._project.translations
                              .get(self._active_lang, {}).get(t.id, ""))
            row.setText(COL_STATUS, label("txttbl.status_translated") if translated
                        else label("txttbl.missing"))
            row.setForeground(COL_STATUS,
                              QColor(C.TEXT_DIM if translated else C.ACCENT_YLW))
            row.setData(COL_STATUS, _ROLE_SORT, 1 if translated else 0)
            if not translated:
                flags.add(FLAG_MISSING)

        use = usages.get(t.key) if usages is not None else None
        if usages is not None and not usages.scripts_scanned:
            # Sans luaparser, l'index ne sait pas : il le DIT. Afficher zéro
            # ferait passer tout le projet pour orphelin, et un orphelin, ça
            # se supprime.
            row.setText(COL_USED, "?")
            row.setForeground(COL_USED, QColor(C.TEXT_MUTED))
            row.setToolTip(COL_USED, label("txttbl.used_unknown_tip"))
            row.setData(COL_USED, _ROLE_SORT, -1)
        elif use is not None and use.count:
            row.setText(COL_USED, use.summary())
            row.setForeground(COL_USED, QColor(C.TEXT_DIM))
            row.setToolTip(COL_USED, use.detail())
            row.setData(COL_USED, _ROLE_SORT, use.count)
        else:
            row.setText(COL_USED, label("txttbl.unused_cell"))
            row.setForeground(COL_USED, QColor(C.TEXT_MUTED))
            row.setToolTip(COL_USED, label("txttbl.unused_cell_tip"))
            row.setData(COL_USED, _ROLE_SORT, 0)
            flags.add(FLAG_UNUSED)
        self._flags[t.id] = flags

    def update_content(self, t, display: str):
        """Recale la cellule de contenu pendant la frappe, sans reconstruire.

        L'atelier édite la SOURCE ; la table montre le RENDU. Elle doit suivre
        la frappe, mais reconstruire la table à chaque caractère perdrait la
        sélection et le tri."""
        row = self._row_of(t)
        if row is None:
            return
        self._blocking = True
        row.setText(COL_CONTENT, display or label('txttbl.empty_cell'))
        row.setForeground(COL_CONTENT,
                          QColor(C.TEXT_HI if display else C.ACCENT_YLW))
        self._blocking = False

    # ── Sélection ─────────────────────────────────────────────────

    def selected_texts(self) -> list:
        """Les `Text` sélectionnés, dans l'ordre de la table. Les lignes de
        groupe et les lignes masquées par le filtre n'en sont pas."""
        return [t for it in self._tree.selectedItems()
                if not it.isHidden()
                and (t := it.data(0, _ROLE_TEXT)) is not None]

    def selected_path(self) -> list[str]:
        """Rangement courant — sert au « + » : la nouvelle entrée naît là où on
        regarde."""
        items = self._tree.selectedItems()
        if not items:
            return []
        t = items[0].data(0, _ROLE_TEXT)
        if t is not None:
            return list(t.path)
        path = items[0].data(COL_PATH, _ROLE_GROUP)
        return list(path) if path else []

    def select_by_ids(self, ids: list[int]):
        self._blocking = True
        self._tree.clearSelection()
        wanted, first = set(ids), None
        for item in self._iter_rows():
            t = item.data(0, _ROLE_TEXT)
            if t is not None and t.id in wanted:
                if first is None:
                    # La ligne courante D'ABORD : `setCurrentItem` remplace la
                    # sélection, l'appeler après aurait réduit un lot de vingt
                    # entrées à une seule.
                    first = item
                    self._tree.setCurrentItem(item)
                item.setSelected(True)
        if first is not None:
            self._tree.scrollToItem(first)
        self._blocking = False

    def clear_selection(self):
        """Vide la sélection sans rien émettre — l'écran bascule de contexte,
        ce n'est pas l'utilisateur qui a désélectionné."""
        self._blocking = True
        self._tree.clearSelection()
        self._tree.setCurrentItem(None)
        self._blocking = False
        self._update_footer()

    def _row_of(self, t) -> Optional[QTreeWidgetItem]:
        for item in self._iter_rows():
            if item.data(0, _ROLE_TEXT) is t:
                return item
        return None

    def _iter_rows(self, parent: Optional[QTreeWidgetItem] = None):
        node = parent if parent is not None else self._tree.invisibleRootItem()
        for i in range(node.childCount()):
            child = node.child(i)
            yield child
            yield from self._iter_rows(child)

    def _on_sel(self):
        if self._blocking:
            return
        texts = self.selected_texts()
        self._btn_del.setEnabled(bool(texts))
        self._update_footer()
        self.selection_changed.emit(texts)

    def _update_footer(self):
        n = len(self.selected_texts())
        self._sel_lbl.setText(label("txttbl.n_selected", n=n) if n else "")
        total = len(self._project.texts) if self._project else 0
        shown = sum(1 for it in self._iter_rows()
                    if it.data(0, _ROLE_TEXT) is not None and not it.isHidden())
        self._total_lbl.setText(
            label("txttbl.text_count", n=total) if shown == total
            else label("txttbl.shown_of", shown=shown, total=total))

    # ── Filtre et groupement ──────────────────────────────────────

    def _apply_filter(self):
        """Masque ce qui ne correspond pas ; une ligne d'en-tête survit tant
        qu'un de ses textes survit."""
        q = self._search.text().strip().casefold()
        wanted = {f for f, b in self._chips.items() if b.isChecked()}
        was_blocking, self._blocking = self._blocking, True

        def visit(item: QTreeWidgetItem) -> bool:
            t = item.data(0, _ROLE_TEXT)
            hits = [visit(item.child(i)) for i in range(item.childCount())]
            if t is None:
                item.setHidden(not any(hits))
                return any(hits)
            hay = " ".join((*t.path, t.key, item.text(COL_CONTENT))).casefold()
            # Les deux chips se CUMULENT : « Empty » + « Unused » demande les
            # entrées qui sont les deux, pas leur réunion.
            in_folder = (not self._folder_filter or
                         tuple(t.path[:len(self._folder_filter)]) == self._folder_filter)
            visible = in_folder and ((not q) or (q in hay)) and \
                      wanted <= self._flags.get(t.id, set())
            item.setHidden(not visible)
            return visible

        for i in range(self._tree.invisibleRootItem().childCount()):
            visit(self._tree.invisibleRootItem().child(i))
        self._blocking = was_blocking
        self._update_footer()

    def _on_fold(self, item: QTreeWidgetItem, collapsed: bool):
        path = item.data(COL_PATH, _ROLE_GROUP)
        if self._blocking or path is None:
            return
        path = tuple(path)
        self._collapsed.add(path) if collapsed else self._collapsed.discard(path)

    # ── Édition en place ──────────────────────────────────────────

    def _badge_at(self, pos):
        """(nœud, colonne) si `pos` vise son badge de rangement.

        La zone de flèche est laissée à Qt : c'est elle qui replie et déplie.
        Le badge, lui, est une cible étroite et prévisible, identique au dessin
        de `_PathDelegate` ; il ne vole donc jamais un clic de navigation.
        """
        item = self._tree.itemAt(pos)
        if item is None or item.data(COL_PATH, _ROLE_GROUP) is None:
            return None
        index = self._tree.indexFromItem(item, COL_PATH)
        rect = self._tree.visualRect(index)
        font = QFont(T.MONO, T.XS, QFont.Weight.Bold)
        # Même largeur que le délégué : texte + 12 px, bornée à la cellule.
        badge_w = min(QFontMetrics(font).horizontalAdvance(item.text(COL_PATH)) + 12,
                      max(rect.width() - 8, 16))
        badge = QRectF(rect.left() + 6, rect.center().y() - 7.0, badge_w, 15.0)
        return (item, COL_PATH) if badge.contains(QPointF(pos)) else None

    def eventFilter(self, watched, event):
        if watched is self._tree.viewport():
            if (event.type() == QEvent.Type.MouseButtonPress
                    and event.button() == Qt.MouseButton.LeftButton):
                pos = event.position().toPoint()
                item = self._tree.itemAt(pos)
                index = self._tree.indexAt(pos)
                text = item.data(0, _ROLE_TEXT) if item else None
                if text is not None and index.column() == COL_KEY:
                    rect = self._tree.visualRect(index)
                    if pos.x() >= rect.right() - 28:
                        QApplication.clipboard().setText(text.key)
                        return True
            hit = self._badge_at(event.position().toPoint()) if hasattr(event, "position") else None
            editable = bool(hit and hit[0].isSelected() and hit[0].isExpanded())
            if event.type() == QEvent.Type.MouseMove:
                self._tree.viewport().setCursor(
                    Qt.CursorShape.IBeamCursor if editable else Qt.CursorShape.ArrowCursor)
            elif (event.type() == QEvent.Type.MouseButtonPress
                  and event.button() == Qt.MouseButton.LeftButton and editable):
                item, col = hit
                # Qt finit d'abord de traiter le clic (sélection/focus). Lui
                # demander un éditeur PENDANT ce traitement est ignoré selon
                # le style de plateforme ; le tour suivant est stable.
                QTimer.singleShot(0, lambda i=item, c=col: self._start_edit(i, c))
                return True
        return super().eventFilter(watched, event)

    def _start_edit(self, item: QTreeWidgetItem, col: int):
        """Ouvre l'éditeur natif sans réintroduire le double-clic ambigu."""
        # `setFlags` émet itemChanged : ne pas laisser son handler retirer le
        # flag avant que Qt ait créé le QLineEdit.
        self._blocking = True
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._blocking = False
        self._tree.setCurrentItem(item, col)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._tree.editItem(item, col)
        QTimer.singleShot(0, lambda: self._tree.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers))

    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        """Fin d'édition — la table SIGNALE, elle n'écrit pas.

        `setFlags` ré-émet `itemChanged` comme `setText` : sans le garde, le
        handler se rappelle indéfiniment. Et le panneau reconstruit la table en
        réponse, ce qui DÉTRUIT l'item dont on traite le signal — d'où le
        report d'un tour de boucle, sans quoi Qt revient dans un objet libéré.
        """
        if self._blocking:
            return
        self._blocking = True
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._blocking = False
        typed = item.text(col).strip()

        path = item.data(COL_PATH, _ROLE_GROUP)
        if path is not None:
            old = path[-1]
            if not typed or typed == old:
                self._reset_cell(item, col, old)
                return
            QTimer.singleShot(0, lambda: self.group_renamed.emit(tuple(path), typed))
            return

        t = item.data(0, _ROLE_TEXT)
        if t is None:
            return
        if col == COL_KEY:
            if not typed or typed == t.key:
                self._reset_cell(item, col, t.key)
                return
            QTimer.singleShot(0, lambda: self.key_edited.emit(t, typed))
            return

    def _reset_cell(self, item: QTreeWidgetItem, col: int, value: str):
        """Repose la valeur d'origine après une saisie vide ou inchangée."""
        self._blocking = True
        item.setText(col, value)
        self._blocking = False
