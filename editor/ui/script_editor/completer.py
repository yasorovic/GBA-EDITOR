"""ui/script_editor/completer.py — le popup d'autocomplétion, branché sur `LuaEditor`.

Couche mince : il ne SAIT rien de l'API. Il demande à `scripting.completion` les
candidats pour le texte à gauche du curseur, les affiche, et insère le choix. La
connaissance vit dans le catalogue ; ce fichier n'en est que la fenêtre (cf.
ROADMAP v0.27).
"""
from __future__ import annotations

import re

from PyQt6.QtCore import Qt, QObject, QEvent, QModelIndex
from PyQt6.QtGui import QStandardItem, QStandardItemModel, QColor, QTextCursor, QPixmap, QIcon
from PyQt6.QtWidgets import QCompleter

from scripting.completion import (
    candidates_at, Candidate,
    KIND_FUNCTION, KIND_PROPERTY, KIND_MODULE, KIND_KEYWORD,
    KIND_EVENT, KIND_CONSTRUCTOR, KIND_ENUM, KIND_LOCAL, KIND_REF,
)
from ui.common.theme import C
from ui.common.icons import COLOR_SCRIPT, COLOR_SFX
from .colors import _C_API, _C_REF

# Une pastille de couleur par nature — la même famille que le reste de l'écran
# (logique = magenta du script, valeur = froid des références). L'UI distingue,
# le modèle ne fait que nommer.
_KIND_COLOR = {
    KIND_FUNCTION:    _C_API,
    KIND_PROPERTY:    _C_REF,
    KIND_MODULE:      COLOR_SCRIPT,
    KIND_KEYWORD:     C.TEXT_MUTED,
    KIND_EVENT:       COLOR_SCRIPT,
    KIND_CONSTRUCTOR: _C_API,
    KIND_ENUM:        COLOR_SFX,
    KIND_LOCAL:       C.TEXT_HI,
    KIND_REF:         _C_REF,
}

# Le texte réellement INSÉRÉ (le membre seul) vit dans un rôle à lui. Le rôle
# d'édition ne conviendrait pas : le constructeur de `QStandardItem` le pré-remplit
# avec le libellé, et le modèle de complétion le rabat alors sur l'affichage — la
# complétion insérerait « play_anim(name) » au lieu de « play_anim ». Un rôle
# dédié évite la collision, et le filtre par préfixe travaille sur le membre nu.
_INSERT_ROLE = Qt.ItemDataRole.UserRole

# Le mot déjà tapé (que la sélection remplace) : la traîne de caractères de mot.
# Un nom d'énumération en porte aussi (`north_east`), d'où `\w*`.
_TRAILING = re.compile(r"\w*$")

# Les caractères qui ouvrent d'eux-mêmes le popup, curseur juste après : l'accès
# à un membre (`.`/`:`) et l'ouverture d'une chaîne (`"`/`'`), sans qu'il ait
# fallu taper une lettre.
_OPENERS = ".:\"'"


class ScriptCompleter(QObject):

    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor
        self._context = "unknown"
        self._project_names: dict | None = None
        # Une sélection n'est ACTIVE qu'après une flèche : à l'ouverture rien
        # n'est surligné, et `Entrée` reste une nouvelle ligne tant que l'auteur
        # n'a pas choisi. Remis à faux à chaque réaffichage (une frappe qui
        # refiltre la liste défait le choix).
        self._nav_active = False

        self._model = QStandardItemModel(self)
        self._qc = QCompleter(self._model, editor)
        self._qc.setWidget(editor)
        self._qc.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._qc.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # Le rôle d'édition porte le texte INSÉRÉ (le membre seul) : c'est sur lui
        # que le filtre par préfixe travaille, et c'est lui que l'activation rend.
        self._qc.setCompletionRole(_INSERT_ROLE)
        # `activated[str]` rend le texte du `completionRole` (le membre seul), via
        # `pathFromIndex` sur l'index SOURCE — fiable, contrairement à la lecture
        # d'un rôle sur l'index du proxy de complétion.
        self._qc.activated[str].connect(self._insert)

        popup = self._qc.popup()
        # On prend la main sur les touches du popup — le tri de QCompleter accepte
        # sur Entrée, ce qu'on ne veut pas (Entrée = nouvelle ligne). Installé
        # APRÈS la création du popup, ce filtre passe avant celui de QCompleter.
        popup.installEventFilter(self)
        popup.setFont(self._editor.font())
        popup.setStyleSheet(
            f"QListView{{background:{C.BG_RAISED};color:{C.TEXT_HI};"
            f"border:1px solid {C.BORDER_MID};outline:none;padding:2px;}}"
            f"QListView::item{{padding:2px 6px;}}"
            f"QListView::item:selected{{background:{C.ACCENT};color:{C.ON_ACCENT};}}"
        )

    # ── Contexte (type de script) ────────────────────────────────
    def set_context(self, context: str):
        self._context = context or "unknown"

    def set_project_names(self, names: dict | None):
        """{domaine → noms du projet} — ce que proposent les arguments chaîne
        (`sfx:play("`, `scene:switch("`). Recalculé par l'écran quand le projet
        change, jamais ici : le modèle reste sans dépendance au projet."""
        self._project_names = names

    # ── État interrogé par l'éditeur ─────────────────────────────
    def popup_visible(self) -> bool:
        return self._qc.popup().isVisible()

    def hide(self):
        self._qc.popup().hide()

    # ── Clavier du popup ─────────────────────────────────────────
    def eventFilter(self, obj, event):
        """La table clavier du popup, tenue à la main :
        ↑/↓ sélectionnent (la première flèche ACTIVE le premier item) · `Tab`
        valide — la sélection active, ou à défaut le premier item (validation
        passive) · `Entrée` valide la sélection active, sinon insère une nouvelle
        ligne · `Échap` ferme."""
        if obj is self._qc.popup() and event.type() == QEvent.Type.KeyPress:
            key = event.key()

            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                # La toute première flèche ne déplace pas : elle ACTIVE le premier
                # item (celui qu'on voit en tête). Les suivantes naviguent — on
                # les laisse à la QListView.
                if not self._nav_active:
                    self._nav_active = True
                    self._qc.popup().setCurrentIndex(
                        self._qc.completionModel().index(0, 0))
                    return True
                return False

            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                # `Tab` valide TOUJOURS quand le popup est ouvert : la sélection
                # active si l'auteur a navigué, sinon le premier item. En début de
                # ligne aucun popup n'est ouvert, donc `Tab` y indente (cf.
                # `maybe_complete`).
                self._accept()
                return True

            if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                # `Entrée` ne valide QUE si l'auteur a choisi (une flèche) ; sinon
                # c'est une nouvelle ligne. L'éditeur n'a pas d'auto-indentation,
                # donc `\n` reproduit la frappe.
                if self._nav_active and self._qc.popup().currentIndex().isValid():
                    self._accept()
                else:
                    self.hide()
                    self._editor.insert_newline_keeping_indent()
                return True

            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(obj, event)

    def _accept(self, row: int | None = None):
        """Insère un candidat et ferme. `row` par défaut : la sélection active,
        ou le PREMIER item si rien n'est activé (validation passive du `Tab`)."""
        if row is None:
            idx = self._qc.popup().currentIndex()
            row = idx.row() if idx.isValid() else 0
        if row < 0 or row >= self._qc.completionCount():
            self.hide()
            return
        # `setCurrentRow` puis `currentCompletion` : le texte à insérer lu par
        # `pathFromIndex` sur l'index SOURCE, fiable (l'index du proxy ne préserve
        # pas le rôle).
        self._qc.setCurrentRow(row)
        self._insert(self._qc.currentCompletion())
        self.hide()

    # ── Calcul et affichage ──────────────────────────────────────
    def maybe_complete(self, force: bool = False):
        """Recalcule les candidats pour le curseur courant et montre (ou cache)
        le popup. `force` = déclenché à la demande (Ctrl+Espace), qui ouvre même
        sur un préfixe vide."""
        tc = self._editor.textCursor()
        if tc.hasSelection():
            self.hide()
            return
        block = tc.block()
        line_prefix = block.text()[:tc.positionInBlock()]
        # Début de ligne (rien, ou seulement de l'indentation) : pas de popup
        # automatique — `Tab` doit pouvoir indenter librement. `Ctrl+Espace`
        # l'ouvre quand même.
        if not force and not line_prefix.strip():
            self.hide()
            return
        cands = candidates_at(line_prefix, context=self._context,
                              source=self._editor.toPlainText(),
                              line=block.blockNumber(),
                              project_names=self._project_names)
        if not cands:
            self.hide()
            return

        prefix = _TRAILING.search(line_prefix).group(0)
        opener = line_prefix[-len(prefix) - 1] if len(line_prefix) > len(prefix) else ""
        # Sans forçage : on n'ouvre pas sur rien. Il faut soit un préfixe tapé,
        # soit un caractère d'ouverture juste avant (`.`/`:`/guillemet).
        if not force and not prefix and opener not in _OPENERS:
            self.hide()
            return

        self._fill(cands)
        self._qc.setCompletionPrefix(prefix)
        if self._qc.completionCount() == 0:
            self.hide()
            return
        popup = self._qc.popup()
        # Rien de surligné à l'ouverture : la sélection n'existe qu'après une
        # flèche (cf. `_nav_active`), pour qu'`Entrée` reste une nouvelle ligne
        # tant que l'auteur n'a pas choisi.
        self._nav_active = False
        popup.setCurrentIndex(QModelIndex())
        rect = self._editor.cursorRect()
        rect.setWidth(popup.sizeHintForColumn(0)
                      + popup.verticalScrollBar().sizeHint().width() + 24)
        self._qc.complete(rect)

    # ── Détails privés ───────────────────────────────────────────
    def _fill(self, cands: list[Candidate]):
        self._model.clear()
        for c in cands:
            item = QStandardItem(c.label)                      # affiché : la signature
            item.setData(c.insert, _INSERT_ROLE)               # inséré + filtré : le membre
            item.setData(c.tooltip, Qt.ItemDataRole.ToolTipRole)
            item.setIcon(_dot(_KIND_COLOR.get(c.kind, C.TEXT_NORM)))
            item.setEditable(False)
            self._model.appendRow(item)

    def _insert(self, text: str):
        if not text:
            return
        tc = self._editor.textCursor()
        prefix_len = len(self._qc.completionPrefix())
        tc.movePosition(QTextCursor.MoveOperation.Left,
                        QTextCursor.MoveMode.KeepAnchor, prefix_len)
        tc.insertText(text)
        self._editor.setTextCursor(tc)


_DOT_CACHE: dict[str, QIcon] = {}


def _dot(color: str) -> QIcon:
    """Une pastille ronde de la couleur de la nature du candidat. Mise en cache :
    il n'y a qu'une poignée de couleurs, et `_fill` s'appelle à chaque frappe —
    repeindre 60 pixmaps par touche coûtait pour rien."""
    icon = _DOT_CACHE.get(color)
    if icon is None:
        from PyQt6.QtGui import QPainter, QBrush
        pm = QPixmap(10, 10)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 8, 8)
        p.end()
        icon = _DOT_CACHE[color] = QIcon(pm)
    return icon
