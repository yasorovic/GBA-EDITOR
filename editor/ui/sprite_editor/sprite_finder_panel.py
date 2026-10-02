"""ui/sprite_editor/sprite_finder_panel.py — panneau gauche : liste des sprites + arbre d'animations."""
from __future__ import annotations
from ui.common.labels import label
from ui.common.tooltip import tooltip
from typing import Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QSizePolicy,
    QMenu, QMessageBox, QAbstractItemView,
    QTreeWidget, QTreeWidgetItem,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from ui.common.widgets import W, FinderSection
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import SPRITES
from ui.common.theme import C, T, QSS
from ui.common.icons import get as _ico, COLOR_DEFAULT
from core.models.sprite import AnimState, SpriteAsset, StateDirection
from core.project import Project
from core.history import get_history, DeleteResourceCmd, RemoveListItemCmd
from core.command_dispatcher import get_dispatcher

# ── Helpers styles ─────────────────────────────────────────────────────────────

_PANEL_BG   = f"background:{C.BG_BASE};"

_DIR_LABELS = {
    0: 'sprfind.all_directions',
    1: 'sprfind.north',      2: 'sprfind.north_east', 3: 'sprfind.east',      4: 'sprfind.south_east',
    5: 'sprfind.south',      6: 'sprfind.south_west', 7: 'sprfind.west',      8: 'sprfind.north_west',
}

_DIR_ICON_KEYS = {
    0: "dir_omni",
    1: "dir_n",  2: "dir_ne", 3: "dir_e",  4: "dir_se",
    5: "dir_s",  6: "dir_sw", 7: "dir_w",  8: "dir_nw",
}


# Sentinelle : "conserver la sélection courante si elle existe encore après
# rebuild de l'arbre" — distincte de None qui signifie "ne rien sélectionner".
_KEEP_SELECTION = object()


def dir_label(sd: StateDirection) -> str:
    base = label(_DIR_LABELS[sd.dir]) if sd.dir in _DIR_LABELS else str(sd.dir)
    if sd.mirror_of is not None:
        src = label(_DIR_LABELS[sd.mirror_of]) if sd.mirror_of in _DIR_LABELS else str(sd.mirror_of)
        flips = ("H" if sd.flip_h else "") + ("V" if sd.flip_v else "")
        return f"{base}  ↔{src}{'['+flips+']' if flips else ''}"
    return base


# ── Panneau gauche ─────────────────────────────────────────────────────────────


class SpriteFinderPanel(QWidget):
    """
    Panneau gauche : liste des sprites (arbre fichiers) + arbre d'animations.
    Sélectionner un sprite charge ses animations dans l'arbre du dessous.
    Sélectionner une animation (StateDirection) notifie l'éditeur centre.
    """

    sprite_selected   = pyqtSignal(object)   # SpriteAsset
    direction_selected = pyqtSignal(object, object)  # AnimState, StateDirection

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(420)
        self.setStyleSheet(_PANEL_BG)
        self._project: Optional[Project] = None
        self._current_sprite: Optional[SpriteAsset] = None
        self._blocking = False
        self._build()

    # ── Construction ──────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sprites : le composant partagé (il porte aussi le bandeau
        #    d'identité du panneau) ──────────────────────────────────
        self._sprites = AssetFinder(label('sprfind.sprite_finder'), [SPRITES],
                                    min_width=180, max_width=420)
        self._sprites.selected.connect(lambda _kind, sp: self._on_sprite_chosen(sp))
        self._sprites.add_requested.connect(lambda _label: self._import_sprite())
        self._sprites.emptied.connect(lambda _label: self._on_sprite_chosen(None))
        root.addWidget(self._sprites, 1)

        # ── Animations ────────────────────────────────────────────
        # PAS un asset finder : l'arbre montre la structure INTERNE du sprite
        # choisi (états × directions), pas des assets du projet.
        sec_anim = FinderSection(label('sprfind.animation_states'))
        sec_anim._btn_add.setToolTip(tooltip(
            title=label('sprfind.add_state'), body=label('sprfind.add_state_tip')
        ))
        sec_anim.add_clicked.connect(self._on_add_state)
        self._sprites.add_section(sec_anim)

        self._anim_tree = QTreeWidget()
        self._anim_tree.setHeaderHidden(True)
        self._anim_tree.setStyleSheet(QSS.tree_widget)
        self._anim_tree.setIndentation(14)
        self._anim_tree.setIconSize(QSize(14, 14))
        self._anim_tree.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._anim_tree.currentItemChanged.connect(self._on_anim_item_changed)
        self._anim_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._anim_tree.customContextMenuRequested.connect(self._on_anim_context_menu)
        self._anim_tree.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._anim_tree.setToolTip(tooltip(
            title=label('sprfind.animation_states'), body=label('sprfind.animation_tree_tip')
        ))
        self._anim_tree.itemChanged.connect(self._on_anim_item_text_changed)
        sec_anim.set_widget(self._anim_tree)



    # ── API publique ──────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._sprites.load_project(project)

    def refresh_anim_tree(self):
        """Recharge l'arbre d'animations depuis le sprite courant (conserve la sélection)."""
        self._refresh_anim_tree(self._current_sprite)

    def select_sprite(self, name: str):
        """Sélectionne le sprite `name` — point d'entrée d'une navigation venue
        d'un autre écran, ex. la carte « Utilisations » du Palette Editor."""
        sprite = self._project.sprites.get(name) if self._project else None
        if sprite is not None:
            self._sprites.select(SPRITES.label, sprite)

    def select_direction(self, state: AnimState, sd: StateDirection):
        """Sélectionne explicitement (state, sd) dans l'arbre — ex: après ajout
        d'une direction depuis le panneau droit, pour que le canvas central
        bascule immédiatement dessus au lieu de rester sur l'ancienne sélection."""
        self._refresh_anim_tree(self._current_sprite, select=(state, sd))

    # ── Peuplement anim tree ──────────────────────────────────────

    def _refresh_anim_tree(self, sprite: Optional[SpriteAsset], select: Any = _KEEP_SELECTION):
        if select is _KEEP_SELECTION:
            current = self._anim_tree.currentItem()
            data = current.data(0, Qt.ItemDataRole.UserRole) if current else None
            target = data if isinstance(data, tuple) else None
        else:
            target = select

        self._blocking = True
        self._anim_tree.blockSignals(True)
        self._anim_tree.clear()

        if not sprite:
            self._blocking = False
            self._anim_tree.blockSignals(False)
            return

        for state in sprite.states:
            state_item = QTreeWidgetItem([state.name])
            state_item.setFont(0, QFont(T.UI, T.SM, QFont.Weight.Bold))
            state_item.setForeground(0, QColor(C.TEXT_HI))
            state_item.setIcon(0, _ico("anim_state", COLOR_DEFAULT))
            state_item.setData(0, Qt.ItemDataRole.UserRole, (state, None))
            state_item.setFlags(state_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._anim_tree.addTopLevelItem(state_item)
            state_item.setExpanded(True)

            for sd in state.directions:
                lbl = dir_label(sd)
                sd_item = QTreeWidgetItem([f"    {lbl}"])
                sd_item.setFont(0, QFont(T.UI, T.SM))
                mirrored = sd.mirror_of is not None
                fg = C.TEXT_DIM if mirrored else C.TEXT_NORM
                sd_item.setForeground(0, QColor(fg))
                # Mirror signalé par le texte grisé (fg) ; icône neutre.
                sd_item.setIcon(0, _ico(_DIR_ICON_KEYS.get(sd.dir, "dir_omni"), COLOR_DEFAULT))
                sd_item.setData(0, Qt.ItemDataRole.UserRole, (state, sd))
                state_item.addChild(sd_item)

        self._blocking = False
        self._anim_tree.blockSignals(False)

        # Sélectionner la cible demandée si elle existe encore, sinon la
        # première direction du premier état.
        target_item = None
        if target:
            t_state, t_sd = target
            for i in range(self._anim_tree.topLevelItemCount()):
                state_item = self._anim_tree.topLevelItem(i)
                data = state_item.data(0, Qt.ItemDataRole.UserRole)
                if not data or data[0] is not t_state:
                    continue
                if t_sd is None:
                    target_item = state_item.child(0) if state_item.childCount() else state_item
                else:
                    for j in range(state_item.childCount()):
                        child = state_item.child(j)
                        cdata = child.data(0, Qt.ItemDataRole.UserRole)
                        if cdata and cdata[1] is t_sd:
                            target_item = child
                            break
                break
        if target_item is None:
            first = self._anim_tree.topLevelItem(0)
            if first and first.childCount():
                target_item = first.child(0)
        if target_item is not None:
            self._anim_tree.setCurrentItem(target_item)

    # ── Slots ─────────────────────────────────────────────────────

    def _on_sprite_chosen(self, sp):
        """Sprite choisi dans le finder partagé."""
        self._current_sprite = sp
        # Le sprite actif doit être propagé AVANT que l'arbre d'animations ne
        # sélectionne sa première direction, sinon le panneau central résout
        # encore l'ancien sprite/PNG.
        self.sprite_selected.emit(sp)
        self._refresh_anim_tree(sp)


    def _on_anim_item_changed(self, current, _prev):
        if self._blocking or not current:
            return
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple):
            return
        state, sd = data
        if sd is None:
            sd = state.directions[0] if state.directions else None
        if sd is not None:
            self.direction_selected.emit(state, sd)

    def _on_add_state(self):
        if not self._current_sprite:
            return
        name = f"State{len(self._current_sprite.states) + 1}"
        new_state = AnimState(name=name)
        self._current_sprite.states.append(new_state)
        if self._project:
            get_dispatcher().save_sprite(self._current_sprite)
        self._refresh_anim_tree(self._current_sprite, select=(new_state, None))

    # ── Sprites : import (le reste est porté par AssetFinder/SPRITES) ──

    def _import_sprite(self):
        """Le « + » du finder délègue ici : le dialogue d'import a besoin d'un
        widget parent, que le composant partagé n'a pas à connaître."""
        from .import_png_dialog import import_new_sprite
        dst = import_new_sprite(self._project, self)
        if not dst:
            return
        self._sprites.refresh()
        sprite = self._project.sprites.get(dst.stem)
        if sprite is not None:
            self._sprites.select(SPRITES.label, sprite)


    # ── Animations : renommage / suppression d'un état ──────────────

    def _on_anim_context_menu(self, pos):
        item = self._anim_tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple):
            return
        state, sd = data
        if sd is not None:
            return  # pas de menu sur une direction (gérée via le panneau DIRECTIONS)
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        delete_a = menu.addAction(label('sprfind.delete_state'))
        can_delete = bool(self._current_sprite) and len(self._current_sprite.states) > 1
        delete_a.setEnabled(can_delete)
        act = menu.exec(self._anim_tree.viewport().mapToGlobal(pos))
        if act == delete_a:
            self._delete_state(state)

    def _on_anim_item_text_changed(self, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple) or data[1] is not None:
            return  # seuls les états (pas les directions) sont renommables
        state: AnimState = data[0]
        new_name = item.text(0).strip()
        if not new_name or new_name == state.name:
            self._anim_tree.blockSignals(True)
            item.setText(0, state.name)
            self._anim_tree.blockSignals(False)
            return
        old_name = state.name
        if self._project:
            # self:play_anim("…") dans les scripts suit le renommage.
            from scripting.api import DOMAIN_ANIM
            refs = self._project.rename_lua_refs(DOMAIN_ANIM, old_name, new_name)
            state.name = new_name
            if self._current_sprite:
                get_dispatcher().save_sprite(self._current_sprite)
            self._project._notify_renamed("Animation", old_name, new_name, refs)
        else:
            state.name = new_name
        self._anim_tree.blockSignals(True)
        item.setText(0, state.name)
        self._anim_tree.blockSignals(False)

    def _delete_state(self, state: AnimState):
        if not self._current_sprite or len(self._current_sprite.states) <= 1:
            return
        if QMessageBox.question(
            self, label('common.delete'),
            label('sprfind.delete_confirm', name=state.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        sprite = self._current_sprite
        project = self._project
        get_history().push(RemoveListItemCmd(
            sprite.states, state,
            persist_fn=(lambda: get_dispatcher().save_sprite(sprite)) if project else None,
            label=f"Delete state {state.name}",
        ))
        self._refresh_anim_tree(self._current_sprite)
