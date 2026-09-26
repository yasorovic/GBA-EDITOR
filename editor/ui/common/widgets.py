"""
ui/widgets.py — Bibliothèque de widgets réutilisables pour les éditeurs de components.

Usage dans un éditeur de component (ou plugin) :
    from ui.common.widgets import W

    W.row("Frame", fw_widget, layout)
    W.pair("Offset", "X", C.AXIS_X, sp_x, "Y", C.AXIS_Y, sp_y, layout)
    W.section("Callbacks", layout)
    W.separator(layout)

    btn = W.btn_ghost("Choisir…")
    btn = W.btn_accent("Ouvrir")
    btn = W.btn_danger("×")
"""
from __future__ import annotations
from ui.common.labels import label
from typing import Callable, Any

from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QToolButton, QCheckBox, QLineEdit, QSpinBox,
    QDoubleSpinBox, QComboBox, QScrollArea, QApplication, QTreeWidget, QTreeWidgetItem,
    QTableWidget, QHBoxLayout, QVBoxLayout, QSizePolicy, QSpacerItem, QPlainTextEdit,
)
from PyQt6.QtGui import QFont, QIcon, QColor, QPainter
from PyQt6.QtCore import Qt, QPoint, QPointF, QSize, pyqtSignal

from ui.common.theme import C, T, S, QSS


# ── Constantes de style ───────────────────────────────────────────────
#  UI (police système) pour les labels/boutons, MONO réservé aux valeurs et axes.

_FONT_UI_SM    = QFont(T.UI, T.SM)
_FONT_UI_XS    = QFont(T.UI, T.XS)
_FONT_MONO_SM  = QFont(T.MONO, T.SM)
_FONT_MONO_XS  = QFont(T.MONO, T.XS)
_FONT_MONO_AX  = QFont(T.MONO, T.MD, QFont.Weight.Bold)   # axes X/Y/W/H

_LBL_STY    = f"color:{C.TEXT_DIM}; background:transparent; border:none;"
_LBL_AX_STY = "color:{c}; background:transparent; border:none;"

# Alias vers les fragments centralisés de theme.py — gardés ici pour ne pas
# casser les call sites existants (W.btn_ghost, W.btn_accent, ...).
# Hauteur commune des en-têtes de section de viewer — FinderSection et
# W.section_bar (repliable ou non, une section se lit à la même hauteur).
FINDER_HEADER_H = 26

BTN_GHOST  = QSS.button_ghost
BTN_ACCENT = QSS.button_accent_outline
BTN_DANGER = QSS.toolbutton_danger
BTN_ICON   = QSS.toolbutton_icon


class HoverIconButton(QToolButton):
    """`QToolButton` dont l'icône se recolore elle-même au survol et, si le
    bouton est cochable, à l'état coché.

    Un `QIcon` posé par `setIcon` est un pixmap déjà teinté (cf.
    `ui/common/icons.py`) : la feuille de style peut recolorer du TEXTE au
    survol (`QToolButton:hover{color:…}`), jamais un pixmap. D'où cette
    classe plutôt qu'un glyphe de police (`setText("+")`) stylé en CSS — les
    deux rendaient la même chose à l'écran, mais seul le second réagissait
    à la souris."""

    def __init__(self, icon_name: str, base: str, hover: str,
                 checked: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        from ui.common import icons
        self._icons = icons
        self._icon_name = icon_name
        self._base = base
        self._hover = hover
        self._checked_color = checked
        self._hovered = False
        if checked is not None:
            self.toggled.connect(lambda _c: self._sync_icon())
        self._sync_icon()

    def _sync_icon(self):
        if self._checked_color is not None and self.isChecked():
            color = self._checked_color
        elif self._hovered:
            color = self._hover
        else:
            color = self._base
        self.setIcon(self._icons.get(self._icon_name, color))

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hovered = True
        self._sync_icon()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hovered = False
        self._sync_icon()


class DragHandle(QWidget):
    """Poignée de déplacement d'une barre flottante — le MÊME motif partout.

    Une grille de points PEINTE au `QPainter`, pas un glyphe `⋮⋮` posé en
    `QLabel` : un caractère dépend de la police et du moteur Qt qui le rend,
    d'où les rendus qui différaient d'une barre à l'autre (Scene Manager,
    Background Editor, Sprite Editor). Même raison, même solution que la
    flèche de repli partagée de `ui/common/icons.py`.

    `orientation` = l'axe de la barre : `Vertical` pour une barre en colonne
    (poignée en haut, points sur une ligne), `Horizontal` pour une barre en
    ligne (poignée à gauche, points sur une colonne). La poignée est
    transparente à la souris : c'est le cadre de la barre qui gère le drag,
    et l'attraper « par la poignée » revient à attraper le cadre dessous.
    """

    _DOT = 2      # diamètre d'un point
    _GAP = 4      # pas entre centres
    _BAND = 12    # épaisseur de la bande (hauteur si Vertical, largeur si Horizontal)

    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Vertical,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._orientation = orientation
        if orientation == Qt.Orientation.Vertical:
            self.setFixedHeight(self._BAND)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.setFixedWidth(self._BAND)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e):
        # 3 points le long de l'axe de la barre, 2 en travers.
        if self._orientation == Qt.Orientation.Vertical:
            cols, rows = 3, 2
        else:
            cols, rows = 2, 3
        grid_w = (cols - 1) * self._GAP
        grid_h = (rows - 1) * self._GAP
        x0 = (self.width() - grid_w) / 2
        y0 = (self.height() - grid_h) / 2
        r = self._DOT / 2

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.TEXT_MUTED))
        for c in range(cols):
            for row in range(rows):
                p.drawEllipse(QPointF(x0 + c * self._GAP, y0 + row * self._GAP), r, r)
        p.end()


# ── Factory class (namespace) ─────────────────────────────────────────

class _W:
    """Toutes les fonctions retournent le widget principal pour chaînage."""

    # ── Boutons ───────────────────────────────────────────────────────

    def btn_ghost(self, text: str) -> QPushButton:
        """Bouton discret (actions secondaires : Choisir, Nouveau…)."""
        b = QPushButton(text); b.setStyleSheet(BTN_GHOST); return b

    def btn_accent(self, text: str) -> QPushButton:
        """Bouton contour coloré (action principale : Ouvrir, Créer…)."""
        b = QPushButton(text); b.setStyleSheet(BTN_ACCENT); return b

    def btn_danger(self, tooltip: str = "") -> QToolButton:
        """Bouton × danger (supprimer, détacher…). Visible au repos, rouge au survol."""
        b = HoverIconButton("clear", C.TEXT_NORM, C.ACCENT_RED)
        b.setStyleSheet(BTN_DANGER)
        b.setFixedSize(22, 22)
        b.setIconSize(QSize(14, 14))
        if tooltip:
            b.setToolTip(tooltip)
        return b

    def btn_add(self, tooltip: str = None, icon: str | None = None) -> QToolButton:
        """Bouton + sans bordure, survol accent — style project panel.
        `icon` : nom logique dans ui/common/icons.py (ex: "add_row") pour
        remplacer le "+" générique quand plusieurs boutons d'ajout se
        cotoient et doivent se distinguer par leur fonction."""
        if tooltip is None:
            tooltip = label('wdg.add')
        b = HoverIconButton(icon or "add", C.TEXT_DIM, C.ACCENT)
        b.setStyleSheet(BTN_ICON)
        b.setFixedSize(24, 24)
        b.setIconSize(QSize(16, 16))
        b.setToolTip(tooltip)
        return b

    def btn_search(self, tooltip: str = None) -> QToolButton:
        """Bouton loupe sans bordure, survol accent — style project panel."""
        if tooltip is None:
            tooltip = label('wdg.search')
        b = HoverIconButton("search", C.TEXT_DIM, C.ACCENT)
        b.setStyleSheet(BTN_ICON)
        b.setFixedSize(24, 24)
        b.setIconSize(QSize(16, 16))
        b.setToolTip(tooltip)
        return b

    def btn_reveal(self, tooltip: str = None) -> QToolButton:
        """Bouton dossier sans bordure — révèle le dossier RÉEL d'une famille
        de finder dans l'explorateur du système (cf. ui/common/reveal.py).
        Standardisé : le même bouton dans tous les finders, visible seulement
        pour les familles qui ont un dossier physique (`AssetKind.dir_of`)."""
        if tooltip is None:
            tooltip = label('wdg.open_in_file_manager')
        b = HoverIconButton("reveal_in_files", C.TEXT_DIM, C.ACCENT)
        b.setStyleSheet(BTN_ICON)
        b.setFixedSize(24, 24)
        b.setIconSize(QSize(16, 16))
        b.setToolTip(tooltip)
        return b

    def search_box(self, placeholder: str = None) -> QLineEdit:
        """Champ de filtre par nom — apparaît sous un header au clic sur btn_search()."""
        if placeholder is None:
            placeholder = label('wdg.filter_by_name_2')
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        e.setFixedHeight(24)
        e.setFont(_FONT_UI_SM)
        e.setStyleSheet(
            f"QLineEdit{{color:{C.TEXT_NORM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:3px;"
            f"font-family:{T.UI_STACK};font-size:{T.SM}px;padding:2px 6px;}}"
            f"QLineEdit:focus{{border-color:{C.ACCENT};}}"
        )
        return e

    def filter_tree(self, tree: QTreeWidget, query: str):
        """
        Filtre les items d'un QTreeWidget par sous-chaîne du nom (insensible
        à la casse). Un item reste visible si son propre texte correspond ou
        si un de ses descendants correspond (l'ancêtre est alors déplié pour
        garder le résultat visible). query vide → tout réafficher.
        """
        query = query.strip().lower()

        def _apply(item: QTreeWidgetItem) -> bool:
            self_match = query in item.text(0).lower()
            child_match = False
            for i in range(item.childCount()):
                if _apply(item.child(i)):
                    child_match = True
            visible = (not query) or self_match or child_match
            item.setHidden(not visible)
            if query and child_match:
                item.setExpanded(True)
            return visible

        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            _apply(root.child(i))

    def filter_table(self, table, query: str, name_col: int = 0):
        """
        Filtre les lignes d'un QTableWidget par sous-chaîne du nom (colonne
        name_col), insensible à la casse. query vide → tout réafficher.
        """
        query = query.strip().lower()
        for row in range(table.rowCount()):
            item = table.item(row, name_col)
            text = item.text() if item else ""
            table.setRowHidden(row, bool(query) and query not in text.lower())

    # ── Ligne label + widget ──────────────────────────────────────────

    def row(self, label: str, widget: QWidget, layout: QVBoxLayout,
            label_width: int = 76) -> QWidget:
        """
        Ligne horizontale : « label »  [ widget ]
        Retourne le widget pour usage ultérieur.
        """
        container = QWidget()
        container.setStyleSheet("background:transparent;")
        r = QHBoxLayout(container)
        r.setSpacing(8); r.setContentsMargins(0, 2, 0, 2)
        lbl = QLabel(label); lbl.setFont(_FONT_UI_SM)
        lbl.setStyleSheet(_LBL_STY); lbl.setFixedWidth(label_width)
        r.addWidget(lbl); r.addWidget(widget, 1)
        layout.addWidget(container)
        return widget

    # ── Paire d'inputs avec axes colorés ─────────────────────────────

    def pair(self, row_label: str,
             ax1: str, color1: str, widget1: QWidget,
             ax2: str, color2: str, widget2: QWidget,
             layout: QVBoxLayout,
             label_width: int = 76) -> tuple[QWidget, QWidget]:
        """
        Ligne :  « row_label »  AX1 [widget1]  AX2 [widget2]
        Axes colorés (ex: X rouge, Y bleu).
        Retourne (widget1, widget2).
        """
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        r = QHBoxLayout(inner); r.setSpacing(4); r.setContentsMargins(0, 0, 0, 0)
        for ax, col, w in ((ax1, color1, widget1), (ax2, color2, widget2)):
            lbl = QLabel(ax); lbl.setFont(_FONT_MONO_AX)
            lbl.setStyleSheet(_LBL_AX_STY.format(c=col))
            lbl.setFixedWidth(14)
            r.addWidget(lbl); r.addWidget(w, 1)
        self.row(row_label, inner, layout, label_width)
        return widget1, widget2

    # ── Checkbox inline ───────────────────────────────────────────────

    def checkbox_row(self, row_label: str, check_label: str,
                     layout: QVBoxLayout) -> QCheckBox:
        """
        Ligne :  « row_label »  ☑ check_label
        Retourne le QCheckBox.
        """
        chk = QCheckBox(check_label)
        chk.setFont(_FONT_UI_SM)
        chk.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent;")
        self.row(row_label, chk, layout)
        return chk

    # ── Séparateur horizontal ─────────────────────────────────────────

    def separator(self, layout: QVBoxLayout, margin_v: int = 4) -> QFrame:
        """Séparateur horizontal fin."""
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(
            f"background:{C.BORDER}; border:none; margin:{margin_v}px 0;"
        )
        layout.addWidget(sep)
        return sep

    # ── En-tête de sous-section ───────────────────────────────────────

    def section(self, text: str, layout: QVBoxLayout) -> QLabel:
        """Petit titre de sous-section (ex: 'CALLBACKS SOLID')."""
        lbl = QLabel(text); lbl.setFont(_FONT_UI_XS)
        lbl.setStyleSheet(QSS.title_panel)
        layout.addWidget(lbl)
        return lbl

    # ── Hiérarchie de titres (briques theme.py — voir QSS.title_*) ────

    def title_panel(self, text: str) -> QLabel:
        """En-tête de panneau/finder (niveau 1) — discret, uppercase conseillé."""
        lbl = QLabel(text); lbl.setFont(_FONT_UI_SM)
        lbl.setStyleSheet(QSS.title_panel)
        return lbl

    def title_group(self, text: str) -> QLabel:
        """Intertitre d'un groupe DANS une section de viewer (« ACTORS »,
        « BEHAVIORS »). Pas de bandeau : un simple label aligné sur la gouttière
        du panneau, avec de l'air au-dessus — c'est l'espace qui sépare."""
        lbl = QLabel(text)
        lbl.setFont(_FONT_UI_XS)
        lbl.setStyleSheet(
            f"{QSS.title_group} padding-left:{S.CONTENT}px;"
            f"padding-top:{S.MD}px; padding-bottom:{S.XS}px;"
        )
        return lbl

    def finder_bar(self, text: str) -> QFrame:
        """Bandeau d'identité d'un viewer (« PROJECT VIEWER », « SPRITE
        FINDER »). Sans fond ni filet : il nomme le panneau, les sections
        portent la structure. Le layout est accessible via `.layout()` pour y
        ajouter un compteur, un filtre ou des boutons."""
        bar = QFrame()
        bar.setFixedHeight(26)
        bar.setStyleSheet("background:transparent; border:none;")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(S.GUTTER, 0, S.SM, 0)
        hl.setSpacing(S.MD)
        lbl = QLabel(text)
        lbl.setFont(_FONT_UI_SM)
        lbl.setStyleSheet(QSS.title_panel)
        hl.addWidget(lbl)
        return bar

    def section_bar(self, text: str, color: str | None = None) -> QFrame:
        """En-tête de section NON repliable d'un viewer (Palette finder, Sound
        mixer). Même grammaire que FinderSection — titre aligné sur la gouttière,
        pas de bandeau coloré — pour que toutes les listes se ressemblent.
        Ajouter les boutons d'action directement dans `.layout()`."""
        f = QFrame()
        # Hauteur = en-tête + l'air au-dessus (même respiration qu'une
        # FinderSection, qui le prend en marge de layout).
        f.setFixedHeight(FINDER_HEADER_H + S.MD)
        f.setStyleSheet("background:transparent; border:none;")
        hl = QHBoxLayout(f)
        # Décalage à gauche = gouttière + la largeur du chevron d'une
        # FinderSection, pour que les titres repliables ou non s'alignent.
        hl.setContentsMargins(S.GUTTER + S.LG + S.SM, S.MD, S.SM, 0)
        hl.setSpacing(S.XS)
        lbl = QLabel(text)
        lbl.setStyleSheet(QSS.title_finder(color))
        hl.addWidget(lbl, 1)
        return f

    def title_section(self, text: str, color: str | None = None) -> QLabel:
        """Titre de section d'inspecteur (niveau 2) — périwinkle par défaut,
        `color` réservé à une lecture propre au contexte appelant."""
        lbl = QLabel(text); lbl.setFont(_FONT_UI_SM)
        lbl.setStyleSheet(QSS.title_section(color))
        return lbl

    def empty_state(self, text: str) -> QLabel:
        """Message central d'un écran/panneau vide — style unique app-wide."""
        lbl = QLabel(text)
        lbl.setFont(QFont(T.UI, T.LG))
        lbl.setStyleSheet(QSS.empty_state)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        return lbl

    # ── Barre méta (id + Active) ──────────────────────────────────────

    def meta_bar(self, comp: Any,
                 field_syncers: dict,
                 set_comp_fn: Callable,
                 layout: QVBoxLayout) -> tuple[QLineEdit, QCheckBox]:
        """
        Barre horizontale compacte :  id [ … ]  ☑ Active
        Enregistre automatiquement les syncers pour 'id' et 'active'.
        Retourne (id_edit, active_cb).
        """
        meta = QWidget()
        meta.setStyleSheet(
            f"background:{C.BG_PANEL}; border-radius:3px; border:1px solid {C.BORDER_DARK};"
        )
        ml = QHBoxLayout(meta); ml.setContentsMargins(8, 4, 8, 4); ml.setSpacing(10)

        id_lbl = QLabel("id"); id_lbl.setFont(_FONT_UI_SM)
        id_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")

        id_edit = QLineEdit(comp.id); id_edit.setFont(_FONT_MONO_SM)
        id_edit.setPlaceholderText("id…")
        id_edit.editingFinished.connect(lambda: set_comp_fn(comp, "id", id_edit.text()))
        field_syncers["id"] = lambda v, w=id_edit: (
            w.blockSignals(True), w.setText(str(v)), w.blockSignals(False))

        active_cb = QCheckBox(label('wdg.active')); active_cb.setFont(_FONT_UI_SM)
        active_cb.setChecked(comp.active)
        active_cb.toggled.connect(lambda v: set_comp_fn(comp, "active", v))
        field_syncers["active"] = lambda v, w=active_cb: (
            w.blockSignals(True), w.setChecked(bool(v)), w.blockSignals(False))

        ml.addWidget(id_lbl); ml.addWidget(id_edit, 1); ml.addWidget(active_cb)
        layout.addWidget(meta)
        return id_edit, active_cb

    # ── Spinbox standard ──────────────────────────────────────────────

    def double_spinbox(self, value: float = 0.0,
                       min_v: float = -9999.0, max_v: float = 9999.0,
                       step: float = 0.1, decimals: int = 2) -> QDoubleSpinBox:
        """QDoubleSpinBox précâblé, même style que spinbox."""
        from ui.common.theme import QSS as _QSS
        sp = QDoubleSpinBox()
        sp.setRange(min_v, max_v)
        sp.setSingleStep(step)
        sp.setDecimals(decimals)
        sp.setValue(value)
        sp.setFont(QFont(T.MONO, T.MD))
        sp.setStyleSheet(_QSS.spinbox)
        return sp

    def combobox(self, items: list[str], current: str = "") -> QComboBox:
        """QComboBox précâblé avec les items donnés."""
        from ui.common.theme import QSS as _QSS
        cb = QComboBox()
        cb.addItems(items)
        if current in items:
            cb.setCurrentIndex(items.index(current))
        cb.setFont(QFont(T.UI, T.MD))
        cb.setStyleSheet(_QSS.combobox)
        return cb

    def spinbox(self, value: int = 0,
                min_v: int = -512, max_v: int = 512,
                step: int = 1) -> QSpinBox:
        """
        QSpinBox précâblé, visuellement identique à ceux du Transform.
        Applique explicitement QSS.spinbox pour ne pas dépendre de la cascade parent.
        """
        from ui.common.theme import QSS as _QSS
        sp = QSpinBox()
        sp.setRange(min_v, max_v); sp.setSingleStep(step)
        sp.setValue(value)
        sp.setFont(QFont(T.MONO, T.MD))
        sp.setStyleSheet(_QSS.spinbox)
        return sp

    def value_field(self, raw=0, project=None, variables=None,
                    min_px: int = -32767, max_px: int = 32767,
                    allow_tile: bool = True):
        """Champ de valeur px / tile / référence de variable — voir
        ui/common/value_field.py. `project` alimente automatiquement la liste
        des variables (globals + constantes) ; sinon passer `variables`
        explicitement. Retourne un ValueField (signal `changed(raw)`)."""
        from ui.common.value_field import ValueField
        from core.models.field_value import variables_from_project
        vars_ = variables if variables is not None else variables_from_project(project)
        return ValueField(raw, vars_, min_px=min_px, max_px=max_px, allow_tile=allow_tile)


W = _W()
"""Instance globale — importer W et utiliser W.row(), W.btn_ghost(), etc."""


# ── NotesEdit ─────────────────────────────────────────────────────────
#  Zone de note libre partagée par SceneInspector / ActorInspector (Actor ET
#  Prefab). Commit uniquement à la perte de focus (signal `committed`), pas
#  à chaque frappe — même convention que les QLineEdit.editingFinished de
#  l'inspecteur (cf. component_editors/script.py), et ça évite une écriture
#  disque par caractère tapé (cf. le crash de sauvegardes en rafale).

class NotesEdit(QPlainTextEdit):
    committed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._baseline = ""
        self.setPlaceholderText(label('wdg.notes'))
        self.setFont(QFont(T.UI, T.SM))
        self.setFixedHeight(60)
        # Hauteur fixe : politique verticale Fixed, sinon (Expanding par défaut
        # d'un QPlainTextEdit) le layout parent croit la carte extensible et
        # gonfle le voisin (ex: titre NOTE) de tout l'espace en trop.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"QPlainTextEdit{{color:{C.TEXT_NORM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID};border-radius:4px;padding:4px 6px;}}"
            f"QPlainTextEdit:focus{{border:1px solid {C.ACCENT};}}"
        )

    def set_text_silent(self, text: str):
        """Charge une valeur sans déclencher `committed` (rechargement inspecteur)."""
        self._baseline = text or ""
        self.blockSignals(True)
        self.setPlainText(self._baseline)
        self.blockSignals(False)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        text = self.toPlainText()
        if text != self._baseline:
            self._baseline = text
            self.committed.emit(text)


# ── ScriptSlot ────────────────────────────────────────────────────────
# Widget réutilisable : bouton "+" pointillé quand vide,
# ligne (nom · Éditer · ×) quand un script est assigné.

class ScriptSlot(QWidget):
    """
    Slot d'assignation de script réutilisable.

    États :
      - vide  → bouton "＋ <add_label>" dashed, cliquable
      - actif → bouton nommé (nom de l'asset assigné) + btn "×"
                le nom EST le bouton d'édition — pas de "Change" séparé.

    Signaux émis via callbacks :
      on_add()    → l'utilisateur clique "＋"
      on_open()   → l'utilisateur clique sur le nom
      on_clear()  → l'utilisateur clique "×"

    Appeler set_script(name) / clear_script() pour changer l'état.
    """

    def __init__(self, add_label: str, accent_color: str,
                 hint: str = "", show_clear: bool = True, parent=None):
        super().__init__(parent)
        self._color = accent_color

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # ── Bouton "+" ────────────────────────────────────────────
        self._btn_add = QPushButton(f"＋  {add_label}")
        self._btn_add.setFont(QFont(T.UI, T.MD))
        self._btn_add.setFixedHeight(36)
        self._btn_add.setStyleSheet(
            f"QPushButton{{background:{C.BG_DEEP};color:{C.TEXT_DIM};"
            f"border:1px dashed {C.BORDER};border-radius:4px;}}"
            f"QPushButton:hover{{color:{accent_color};border-color:{accent_color};}}"
        )
        root.addWidget(self._btn_add)

        # ── Ligne active ──────────────────────────────────────────
        self._active_w = QWidget()
        hl = QHBoxLayout(self._active_w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)

        # Le nom assigné EST le bouton d'édition : cliquer dessus rouvre le
        # picker, comme le "＋" de l'état vide. L'icône de l'asset, quand il y
        # en a une, vit DANS le bouton.
        self._lbl = QPushButton("")
        self._lbl.setIconSize(QSize(16, 16))
        self._lbl.setFont(QFont(T.MONO, T.SM))
        self._lbl.setFixedHeight(22)
        self._lbl.setStyleSheet(
            f"QPushButton{{color:{accent_color};background:{C.BG_DEEP};"
            f"border:1px solid {accent_color};border-radius:4px;padding:0 8px;"
            f"text-align:left;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER};}}"
        )

        self._btn_clear = QToolButton()
        self._btn_clear.setText("×")
        self._btn_clear.setFont(QFont(T.MONO, T.XL))
        self._btn_clear.setStyleSheet(BTN_DANGER)

        hl.addWidget(self._lbl, 1)
        hl.addWidget(self._btn_clear)
        root.addWidget(self._active_w)
        # setVisible() APRÈS avoir été ajouté au layout (donc parenté) :
        # appelé avant, sur un QToolButton encore sans parent, Qt le montre
        # brièvement comme une vraie fenêtre top-level ("micro popup" observé
        # à l'ouverture d'un projet / à la sélection d'un sprite).
        self._btn_clear.setVisible(show_clear)
        self._active_w.setVisible(False)

        # ── Hint ──────────────────────────────────────────────────
        if hint:
            lbl_hint = QLabel(hint)
            lbl_hint.setFont(_FONT_UI_XS)
            lbl_hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
            root.addWidget(lbl_hint)

        # ── Connexions internes ───────────────────────────────────
        self._on_add   = None
        self._on_open  = None
        self._on_clear = None
        self._btn_add.clicked.connect(self._click_add)
        self._lbl.clicked.connect(self._click_open)
        self._btn_clear.clicked.connect(self._click_clear)

    def set_callbacks(self, on_add=None, on_open=None, on_clear=None):
        self._on_add   = on_add
        self._on_open  = on_open
        self._on_clear = on_clear

    def set_script(self, name: str, icon: QIcon | None = None):
        self._lbl.setText(name)
        self._lbl.setIcon(icon if icon is not None else QIcon())
        self._btn_add.setVisible(False)
        self._active_w.setVisible(True)

    def clear_script(self):
        self._lbl.setText("")
        self._lbl.setIcon(QIcon())
        self._btn_add.setVisible(True)
        self._active_w.setVisible(False)

    def _click_add(self):
        if self._on_add: self._on_add()

    def _click_open(self):
        if self._on_open: self._on_open()

    def _click_clear(self):
        if self._on_clear: self._on_clear()


# ── ScriptPickerPopup ─────────────────────────────────────────────────────────

_DEFAULT_NEW_LABEL = object()


class ScriptPickerPopup(QFrame):
    """
    Dropdown flottant pour choisir ou créer un script.

    Signaux :
        picked(rel_path: str)  — l'utilisateur a sélectionné un script existant
        new_requested()        — l'utilisateur clique "Nouveau script"
    """

    picked        = pyqtSignal(str)   # chemin relatif au projet
    new_requested = pyqtSignal()

    def __init__(self, scripts: list[tuple], accent: str, parent=None,
                 new_label: str | None | object = _DEFAULT_NEW_LABEL):
        """
        scripts   : liste de (nom_affichage, valeur) ou (nom_affichage, valeur, QIcon)
                    — le 3e élément (icône par ligne) est optionnel, pour les
                    pickers qui ont une identité visuelle (palettes, sprites...).
        accent    : couleur d'accentuation (hex)
        new_label : texte du bouton de création en bas du popup ; None pour
                    l'omettre (ex: picker qui ne propose que des éléments déjà
                    existants, sans création à la volée).
        """
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        # Normalise en (display, valeur, icone|None) — accepte les anciens
        # appels à 2-tuples sans modification.
        if new_label is _DEFAULT_NEW_LABEL:
            new_label = label('wdg.new_script')
        self._scripts = [(e[0], e[1], e[2] if len(e) > 2 else None) for e in scripts]
        self._accent  = accent

        self.setFixedWidth(260)
        self.setStyleSheet(
            f"QFrame{{background:{C.BG_PANEL};border:1px solid {accent};"
            f"border-radius:6px;}}"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Barre de recherche ─────────────────────────────────────
        self._search = QLineEdit()
        self._search.setPlaceholderText(label('wdg.filter'))
        self._search.setFont(QFont(T.UI, T.SM))
        self._search.setStyleSheet(
            f"QLineEdit{{background:{C.BG_DEEP};color:{C.TEXT_NORM};border:1px solid {C.BORDER};"
            f"border-radius:3px;padding:3px 6px;}}"
            f"QLineEdit:focus{{border-color:{accent};}}"
        )
        root.addWidget(self._search)

        # ── Zone scrollable des scripts ────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(180)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(QSS.scroll_area)

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background:transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        scroll.setWidget(self._list_widget)
        root.addWidget(scroll)

        # ── Séparateur + bouton de création (optionnels) ────────────
        if new_label is not None:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color:{C.BORDER};")
            root.addWidget(sep)

            btn_new = QPushButton(new_label)
            btn_new.setFont(QFont(T.UI, T.SM))
            btn_new.setFixedHeight(28)
            btn_new.setStyleSheet(
                f"QPushButton{{background:{C.BG_DEEP};color:{accent};"
                f"border:1px solid {accent};border-radius:3px;}}"
                f"QPushButton:hover{{background:{accent};color:{C.BG_DEEP};}}"
            )
            btn_new.clicked.connect(self._on_new)
            root.addWidget(btn_new)

        self._search.textChanged.connect(self._filter)
        self._filter("")
        self._search.setFocus()

    # ── Internals ─────────────────────────────────────────────────

    def _filter(self, text: str):
        query = text.lower().strip()
        # Vider la liste
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        matches = [(d, r, i) for d, r, i in self._scripts if query in d.lower()]

        if not matches:
            lbl = QLabel(label('wdg.no_results'))
            lbl.setFont(QFont(T.UI, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_MUTED};padding:4px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_layout.addWidget(lbl)
        else:
            for display, rel, icon in matches:
                btn = QPushButton(display)
                btn.setFont(QFont(T.MONO, T.SM))
                btn.setFixedHeight(26)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                if icon is not None:
                    btn.setIcon(icon)
                    btn.setIconSize(QSize(16, 16))
                btn.setStyleSheet(
                    f"QPushButton{{background:transparent;color:{C.TEXT_NORM};"
                    f"border:none;border-radius:3px;text-align:left;padding:0 6px;}}"
                    f"QPushButton:hover{{background:{C.BG_DEEP};color:{self._accent};}}"
                )
                btn.clicked.connect(lambda checked, r=rel: self._on_pick(r))
                self._list_layout.addWidget(btn)

        self._list_layout.addStretch()

    def _on_pick(self, rel: str):
        self.picked.emit(rel)
        self.close()

    def _on_new(self):
        self.new_requested.emit()
        self.close()

    # ── Positionnement ────────────────────────────────────────────

    def show_below(self, anchor: QWidget):
        """Affiche le popup sous le widget anchor."""
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 2))
        # Éviter de sortir à droite de l'écran — celui de l'ancre (pas
        # forcément l'écran primaire : la fenêtre peut être sur un 2e moniteur).
        screen = anchor.screen() or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        if pos.x() + self.width() > geo.right():
            pos.setX(geo.right() - self.width() - 4)
        self.move(pos)
        self.show()


# ──────────────────────────────────────────────────────────────────
#  FinderSection — en-tête de section collapsible commun aux 4 finders
#  (Assets finder / Sprite finder / Script finder / Sound finder)
# ──────────────────────────────────────────────────────────────────

class FinderSection(QFrame):
    """
    Section collapsible standard : chevron ▾/▸ + titre en capitales espacées,
    boutons "+" et "recherche" à droite, champ de filtre masqué par défaut.
    Le filtre s'applique automatiquement à tout QTreeWidget posé via
    set_widget() (recherche par nom sur les colonnes de l'arbre).

    Utilisée par les 4 finders pour une apparence et un comportement
    identiques — voir assets_finder_panel.py pour l'exemple de référence.

    Parti pris visuel : l'en-tête n'est PAS un bandeau — empilées, des sections
    à fond plein donnent un panneau rayé. La séparation vient de l'espace et de
    la casse, le fond ne s'allume qu'au survol pour dire « ça se clique ».
    """

    add_clicked = pyqtSignal()
    reveal_clicked = pyqtSignal()

    # Air au-dessus du titre et sous le corps. Le bas ne compte que déplié :
    # replié, doubler la marge ferait flotter des sections vides.
    _PAD_TOP    = S.MD
    _PAD_BOTTOM = S.MD

    def __init__(self, title: str, color: str = C.TEXT_NORM, parent=None):
        # `color` par défaut neutre : les finders n'utilisent plus de code
        # couleur par type d'asset (distinction par forme d'icône + libellé).
        # Le paramètre reste pour un usage ponctuel hors finder si besoin.
        super().__init__(parent)
        self._expanded = True
        # Le contenu sait-il occuper plus que sa hauteur naturelle ? Renseigné
        # par set_widget ; pilote la politique de taille de la section.
        self._content_grows = False
        self.setStyleSheet(f"background:{C.BG_BASE};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, self._PAD_TOP, 0, self._PAD_BOTTOM)
        root.setSpacing(0)

        # Header — le clic sur la zone texte/chevron toggle, les boutons sont
        # indépendants. Transparent : c'est le fond du panneau qui passe.
        hdr = QFrame()
        hdr.setFixedHeight(FINDER_HEADER_H)
        hdr.setStyleSheet("background:transparent; border:none;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, S.SM, 0)
        hl.setSpacing(0)

        # Zone cliquable pour toggle (chevron + titre) ; le survol l'éclaire.
        toggle_area = QWidget()
        toggle_area.setObjectName("finderToggle")
        toggle_area.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toggle_area.setStyleSheet(
            f"QWidget#finderToggle {{ background:transparent; border:none; }}"
            f"QWidget#finderToggle:hover {{ background:{C.BG_PANEL}; }}"
        )
        ta_layout = QHBoxLayout(toggle_area)
        ta_layout.setContentsMargins(S.GUTTER, 0, 0, 0)
        ta_layout.setSpacing(S.SM)

        # Triangle vectoriel partagé (icons.arrow_icon) — pas un glyphe ▾/▸ de
        # police : c'est le MÊME dessin que la flèche de QTreeWidget::branch
        # (cf. theme.py::_tree_arrow_rule), à la même taille (T.MD).
        self._arrow_lbl = QLabel()
        self._arrow_lbl.setFixedWidth(S.LG)
        self._arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow_lbl.setStyleSheet("background:transparent;")
        self._set_arrow("down")

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(QSS.title_finder(color))

        # Sans ça, survoler le titre enverrait un Leave à la zone cliquable :
        # survol clignotant, et clic inopérant sur le texte lui-même.
        for lbl in (self._arrow_lbl, title_lbl):
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        ta_layout.addWidget(self._arrow_lbl)
        ta_layout.addWidget(title_lbl, 1)

        toggle_area.mousePressEvent = lambda e: self._toggle()
        self._color = color
        self._title = title

        self._btn_add = W.btn_add(label('wdg.add_item'))
        self._btn_add.clicked.connect(self.add_clicked)

        self._btn_search = W.btn_search(label('wdg.filter_by_name'))
        self._btn_search.setCheckable(True)
        self._btn_search.toggled.connect(self._on_search_toggled)

        # Masqué par défaut : seules les familles avec un dossier physique
        # (`AssetKind.dir_of`) l'affichent — cf. AssetFinder._reveal.
        self._btn_reveal = W.btn_reveal(label('wdg.open_in_file_manager'))
        self._btn_reveal.setVisible(False)
        self._btn_reveal.clicked.connect(self.reveal_clicked)

        hl.addWidget(toggle_area, 1)
        hl.addWidget(self._btn_reveal)
        hl.addWidget(self._btn_add)
        hl.addWidget(self._btn_search)
        root.addWidget(hdr)

        # Champ de filtre — masqué par défaut, révélé par btn_search
        self._search_box = W.search_box(label('wdg.filter_value', value=title.lower()))
        self._search_box.textChanged.connect(self._apply_filter)
        _orig_keypress = self._search_box.keyPressEvent
        def _search_key_press(e, _orig=_orig_keypress):
            if e.key() == Qt.Key.Key_Escape:
                self._btn_search.setChecked(False)
            else:
                _orig(e)
        self._search_box.keyPressEvent = _search_key_press
        search_row = QWidget()
        search_row.setStyleSheet(f"background:{C.BG_BASE};")
        sr_layout = QHBoxLayout(search_row)
        sr_layout.setContentsMargins(S.GUTTER, S.SM, S.MD, S.SM)
        sr_layout.addWidget(self._search_box)
        self._search_row = search_row
        self._search_row.setVisible(False)
        root.addWidget(self._search_row)

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{C.BG_BASE};")
        # Le corps porte le stretch : sinon, pour une section dont le contenu ne
        # peut pas grandir, QBoxLayout répartit la place à parts égales et
        # l'en-tête descend vers le centre.
        self._body_index = root.count()
        root.addWidget(self._body, 1)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, S.XS, 0, 0)
        self._body_layout.setSpacing(0)

        # Cale de queue de la section : repliée, la section n'a que son en-tête
        # et rien n'absorbe la hauteur donnée par le parent — la cale la prend,
        # donc le titre reste ferré en haut. Dépliée elle est inerte
        # (Minimum) : une cale expansible rendrait la section elle-même
        # expansible, elle réclamerait de la hauteur au ressort de queue du
        # panneau et se retrouverait avec du vide à meubler.
        self._tail_index = root.count()
        self._tail = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum,
                                 QSizePolicy.Policy.Minimum)
        root.addSpacerItem(self._tail)

    def set_add_tooltip(self, tooltip: str):
        self._btn_add.setToolTip(tooltip)

    def set_add_visible(self, visible: bool):
        self._btn_add.setVisible(visible)

    def set_search_visible(self, visible: bool):
        self._btn_search.setVisible(visible)

    def set_reveal_visible(self, visible: bool):
        self._btn_reveal.setVisible(visible)

    def _set_arrow(self, direction: str):
        """direction: "down" (dépliée) ou "right" (repliée)."""
        from ui.common import icons
        icon = icons.arrow_icon(direction, C.TEXT_DIM)
        self._arrow_lbl.setPixmap(icon.pixmap(QSize(T.MD, T.MD)))

    def _toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool):
        """Fixe l'état initial ou répond à un repli demandé par un finder."""
        self._expanded = bool(expanded)
        self._body.setVisible(self._expanded)
        self._set_arrow("down" if self._expanded else "right")
        lay = self.layout()
        m = lay.contentsMargins()
        lay.setContentsMargins(
            m.left(), m.top(), m.right(), self._PAD_BOTTOM if self._expanded else 0)
        # Dépliée, l'espace va au contenu ; repliée, à la cale de queue —
        # qui ne devient expansible qu'à ce moment-là (cf. __init__).
        lay.setStretch(self._body_index, 1 if self._expanded else 0)
        lay.setStretch(self._tail_index, 0 if self._expanded else 1)
        self._tail.changeSize(
            0, 0, QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Minimum if self._expanded else QSizePolicy.Policy.Expanding)
        lay.invalidate()
        self._apply_size_policy()

    def _apply_size_policy(self):
        """Repliée, la section ne vaut que son en-tête ; dépliée sur un contenu
        à hauteur fixe, elle ne vaut que ce contenu. Dans les deux cas politique
        Fixed : sinon le facteur d'étirement du parent (3/2 dans le Sprite
        Finder) ou le rab d'un panneau plus haut que ses sections reste
        appliqué, et la hauteur reste en blanc sous le titre."""
        grow = self._expanded and self._content_grows
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred if grow else QSizePolicy.Policy.Fixed,
        )

    def _on_search_toggled(self, checked: bool):
        self._search_row.setVisible(checked)
        if checked:
            self._search_box.setFocus()
        else:
            self._search_box.clear()  # déclenche _apply_filter("") via textChanged

    def _apply_filter(self, query: str):
        for tree in self._body.findChildren(QTreeWidget):
            W.filter_tree(tree, query)
        for table in self._body.findChildren(QTableWidget):
            W.filter_table(table, query)

    def set_widget(self, w: QWidget):
        """Remplace le contenu de la section par w."""
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            old = item.widget()
            if old:
                # hide() avant setParent(None) : un widget visible détaché de
                # son parent redevient une fenêtre top-level à part entière.
                old.hide()
                old.setParent(None)
                old.deleteLater()
        # Un contenu qui sait grandir (Expanding : listes des finders sprite /
        # fond / police) remplit la section. Un contenu à hauteur fixe (arbres
        # du finder projet, tables de variables) est ferré en haut, et la
        # section se cale sur lui (_apply_size_policy) : sans ça, QBoxLayout
        # répartit le rab autour du contenu et la liste flotte au milieu de la
        # section au lieu de commencer sous son titre.
        self._content_grows = bool(
            w.sizePolicy().expandingDirections() & Qt.Orientation.Vertical)
        if self._content_grows:
            self._body_layout.addWidget(w, 1)
        else:
            self._body_layout.addWidget(w, 1, Qt.AlignmentFlag.AlignTop)
        self._apply_size_policy()
        if self._search_box.text():
            self._apply_filter(self._search_box.text())


# ──────────────────────────────────────────────────────────────────
#  CollapsibleCard — norme des sections d'inspecteur
# ──────────────────────────────────────────────────────────────────
#  Chaque groupe de champs d'un inspecteur (Note, Transform, Affine,
#  Components…) est une carte QSS.card() avec un en-tête chevron ▾/▸ +
#  titre (même style que W.title_section), cliquable pour replier. Avant
#  ce widget, ActorInspector dupliquait cette mécanique à la main
#  (_toggle_section) pour Components/Children/Editor seulement, et laissait
#  Note/Transform/Affine non repliables — d'où l'incohérence visuelle.
# ──────────────────────────────────────────────────────────────────

class CollapsibleCard(QFrame):
    """
    Carte d'inspecteur repliable. Usage :

        card = CollapsibleCard("Transform")
        W.row("Priority", spin, card.body_layout)
        layout.addWidget(card)

    `color` teinte le titre (périwinkle par défaut, via title_section) —
    réservé aux cartes dont le contexte donne une signification à cette
    couleur. `add_header_widget()` ajoute
    un bouton (+, −...) à droite du titre, en dehors de la zone cliquable
    de bascule.
    """

    toggled = pyqtSignal(bool)   # état déplié après le clic

    _counter = 0   # object names uniques sans que l'appelant en fournisse un

    def __init__(self, title: str, color: str | None = None,
                 expanded: bool = True, parent=None):
        super().__init__(parent)
        CollapsibleCard._counter += 1
        object_name = f"card_{CollapsibleCard._counter}"
        self.setObjectName(object_name)
        self.setStyleSheet(QSS.card(object_name))
        self._expanded = expanded
        self._color = color
        # Par défaut la carte ne vaut que sa hauteur naturelle (Fixed) :
        # sans ça, un parent qui lui laisse plus de place que nécessaire
        # (QScrollArea widgetResizable, un addStretch() à facteur 0) la fait
        # grandir au lieu de laisser le stretch absorber l'espace en trop —
        # une carte repliée reste alors haute et son en-tête flotte au milieu
        # plutôt que de rester ferré en haut. `set_expanding(True)` lève cette
        # contrainte pour une carte dont le corps doit remplir l'espace
        # restant (ex: une liste défilante, cf. uses_inspectors.py).
        self._content_grows = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── En-tête : zone cliquable (chevron + titre) + boutons à part ──
        hdr = QWidget()
        hdr.setStyleSheet("background:transparent;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 6, 6, 6)
        hl.setSpacing(4)

        toggle_area = QWidget()
        toggle_area.setObjectName("cardToggle")
        toggle_area.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toggle_area.setStyleSheet(
            "QWidget#cardToggle { background:transparent; border:none; }"
            f"QWidget#cardToggle:hover {{ background:{C.BG_HOVER}; }}"
        )
        ta_layout = QHBoxLayout(toggle_area)
        ta_layout.setContentsMargins(0, 0, 0, 0)
        ta_layout.setSpacing(6)

        self._arrow = QLabel("▾" if expanded else "▸")
        self._arrow.setFixedWidth(12)
        self._arrow.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
        self._title_lbl = QLabel(title)
        self._title_lbl.setFont(_FONT_UI_SM)
        self._title_lbl.setStyleSheet(QSS.title_section(color))
        # Sans ça, survoler chevron/titre enverrait un Leave à toggle_area.
        for w in (self._arrow, self._title_lbl):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        ta_layout.addWidget(self._arrow)
        ta_layout.addWidget(self._title_lbl, 1)
        toggle_area.mousePressEvent = lambda e: self.set_expanded(not self._expanded)

        hl.addWidget(toggle_area, 1)
        self._header_row = hl   # add_header_widget y ajoute après toggle_area
        root.addWidget(hdr)

        self._sep = QFrame(); self._sep.setFrameShape(QFrame.Shape.HLine)
        self._sep.setStyleSheet(f"color:{C.BORDER}; margin:0;")
        root.addWidget(self._sep)

        self._body = QWidget()
        self._body.setStyleSheet("background:transparent;")
        self.body_layout = QVBoxLayout(self._body)
        self.body_layout.setContentsMargins(8, 6, 8, 8)
        self.body_layout.setSpacing(6)
        # Stretch=1 : un contenu qui grandit (ex: QScrollArea d'une liste)
        # reçoit l'espace en trop du parent ; un contenu à hauteur naturelle
        # (des lignes de champs) n'en réclame pas et n'en reçoit pas — la
        # carte ne s'étire que si son corps sait quoi faire de la place.
        root.addWidget(self._body, 1)

        self._body.setVisible(expanded)
        self._sep.setVisible(expanded)
        self._apply_size_policy()

    def sizeHint(self) -> QSize:
        # Hauteur POUR la largeur actuelle. Avec la politique verticale Fixed,
        # Qt plafonne la carte à son sizeHint ; celui-ci, calculé sans largeur,
        # ignore qu'une note repliée sur deux lignes (inspecteur étroit) a
        # besoin de plus de place — la note passait alors sous le champ voisin.
        hint = super().sizeHint()
        layout = self.layout()
        if layout is not None and layout.hasHeightForWidth() and self.width() > 0:
            hint.setHeight(max(hint.height(), layout.heightForWidth(self.width())))
        return hint

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self.updateGeometry()

    def add_header_widget(self, w: QWidget):
        """Bouton (+ / −...) à droite du titre, hors zone de bascule."""
        self._header_row.addWidget(w)

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self._body.setVisible(expanded)
        self._sep.setVisible(expanded)
        self._arrow.setText("▾" if expanded else "▸")
        self._apply_size_policy()
        # Sans ça, la carte garde parfois sa hauteur d'avant le temps d'un
        # cycle d'affichage : masquer _body invalide le layout de la carte
        # (son sizeHint se met à jour aussitôt), mais rien ne dit toujours au
        # layout du PARENT de recalculer tout de suite — updateGeometry()
        # force cette remontée.
        self.updateGeometry()
        self.toggled.emit(expanded)

    def set_expanding(self, grows: bool):
        """Une carte dont le corps doit remplir l'espace vertical restant
        (ex: une liste défilante, cf. uses_inspectors.py) plutôt que de ne
        prendre que sa hauteur naturelle. Par défaut False — voir la note
        dans __init__."""
        self._content_grows = grows
        self._apply_size_policy()

    def _apply_size_policy(self):
        grow = self._expanded and self._content_grows
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding if grow else QSizePolicy.Policy.Fixed,
        )

    def is_expanded(self) -> bool:
        return self._expanded

    def set_title(self, text: str):
        self._title_lbl.setText(text)

    def set_color(self, color: str | None):
        self._color = color
        self._title_lbl.setStyleSheet(QSS.title_section(color))


# ──────────────────────────────────────────────────────────────────
#  AssetHeaderBar — en-tête unifié "type + nom" pour l'objet sélectionné
# ──────────────────────────────────────────────────────────────────

def kind_colors(accent: str) -> tuple[str, str, str]:
    """Dérive (fond sombre, couleur du label TYPE, couleur du nom) depuis une
    seule couleur d'accent canonique (voir ui/icons.py), pour que toute la
    palette dérive d'une unique source par type d'objet."""
    from PyQt6.QtGui import QColor
    c = QColor(accent)
    h, s, _v, _a = c.getHsv()
    bg  = QColor.fromHsv(h, max(0, int(s * 0.55)), C.HEADER_BG_VALUE).name()
    mid = QColor.fromHsv(h, s, 150).name()
    return bg, mid, accent


class AssetHeaderBar(QWidget):
    """
    En-tête réutilisable affichant le type et le nom (renommable) de l'objet
    actuellement sélectionné — même template/couleurs/renommage partout
    (Scene Manager, Sprite Editor, Sound Mixer, Script Editor).

    Couleurs pilotées par `kind`, dérivées des couleurs canoniques de
    ui/icons.py (mêmes couleurs que les icônes du project panel).

    Usage :
        header = AssetHeaderBar()
        header.renamed.connect(lambda new_name: ...)
        header.set_header("actor", "Actor", actor.name, editable=True)
    """

    renamed = pyqtSignal(str)   # nouveau nom, émis quand l'utilisateur valide

    _PALETTE: dict[str, tuple[str, str, str]] = {}  # rempli au premier accès (import tardif)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kind = "empty"
        self._editable = False

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 0, 12, 0)
        root.setSpacing(0)
        self.setFixedHeight(44)

        self._type_lbl = QLabel("")
        self._type_lbl.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))

        self._name_edit = QLineEdit("")
        self._name_edit.setFont(QFont(T.UI, T.XXL, QFont.Weight.DemiBold))
        self._name_edit.setFrame(False)
        self._name_edit.setReadOnly(True)
        self._name_edit.editingFinished.connect(self._on_editing_finished)

        col = QVBoxLayout(); col.setSpacing(1)
        col.addWidget(self._type_lbl)
        col.addWidget(self._name_edit)
        root.addLayout(col, 1)

        self.set_header("empty", "", "")

    @classmethod
    def _palette(cls) -> dict[str, tuple[str, str, str]]:
        if not cls._PALETTE:
            from ui.common import icons
            cls._PALETTE = {
                "actor":  kind_colors(icons.COLOR_ACTOR),
                "prefab": kind_colors(icons.COLOR_PREFAB),
                "scene":  kind_colors(icons.COLOR_SCENE),
                "camera": kind_colors(icons.COLOR_SCENE),
                "script": kind_colors(icons.COLOR_SCRIPT),
                "script_asset": kind_colors(icons.COLOR_SCRIPT),
                "sprite": kind_colors(icons.COLOR_SPRITE),
                "background": kind_colors(icons.COLOR_BACKGROUND),
                "sfx":    kind_colors(icons.COLOR_SFX),
                "music":  kind_colors(icons.COLOR_MUSIC),
                "uses":   kind_colors(icons.COLOR_PREFAB),
                "project": kind_colors(C.ACCENT),
                # Arête du Graphe des scènes : une transition ENTRE scènes, même
                # famille que la scène.
                  "edge":   kind_colors(icons.COLOR_SCENE),
                  "group":  kind_colors(icons.COLOR_SCENE),
                # Interface — un kind par type d'élément (même famille bleue) ;
                # "ui_element" reste en repli pour les appels génériques.
                "ui_container":   kind_colors(icons.COLOR_UI),
                "ui_list":    kind_colors(icons.COLOR_UI),
                "ui_text":    kind_colors(icons.COLOR_UI),
                "ui_image":   kind_colors(icons.COLOR_UI),
                "ui_element": kind_colors(icons.COLOR_UI),
                "ui_layout":  kind_colors(icons.COLOR_UI),
                "empty":  (C.BG_BASE, C.BORDER_MID, C.TEXT_MUTED),
            }
        return cls._PALETTE

    def set_header(self, kind: str, type_text: str, name_text: str, editable: bool = True):
        """kind : clé de palette (voir _palette()). editable=False → lecture seule
        (ex: caméra, ou un contexte où le renommage se fait ailleurs)."""
        bg, tc, nc = self._palette().get(kind, self._palette()["empty"])
        editable = editable and kind != "empty"
        self.setStyleSheet(f"background:{bg};")
        self._type_lbl.setStyleSheet(f"color:{tc}; font-size:8pt; font-weight:bold;")
        self._name_edit.setStyleSheet(
            f"background:transparent; color:{nc}; font-size:13pt; font-weight:bold;"
            f"border:none; border-bottom:1px solid {C.BORDER_MID if editable else 'transparent'};"
            f"padding:0;"
        )
        self._name_edit.setReadOnly(not editable)
        self._name_edit.setCursor(
            Qt.CursorShape.IBeamCursor if editable else Qt.CursorShape.ArrowCursor
        )
        self._type_lbl.setText(type_text)
        self._name_edit.setText(name_text)
        self._kind = kind
        self._editable = editable

    def set_name(self, name_text: str):
        """Met à jour uniquement le nom affiché (ex: après renommage externe)."""
        self._name_edit.setText(name_text)

    def _on_editing_finished(self):
        if not self._editable:
            return
        new_name = self._name_edit.text().strip()
        if new_name:
            self.renamed.emit(new_name)
