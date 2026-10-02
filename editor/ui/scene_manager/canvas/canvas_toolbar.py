"""ui/scene_manager/canvas/canvas_toolbar.py — la palette d'outils flottante.

Extrait de `scene_canvas` (A3) : `FloatingToolbar`, le `QFrame` déplaçable
superposé au canvas — les boutons d'outils (sélection, collision, inpaint,
interface), leurs menus déroulants et les raccourcis. N'émet que des signaux
(`tool_changed`…) ; elle ne connaît ni la vue ni la scène.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from PyQt6.QtCore import Qt, QPoint, QSize, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QToolButton, QVBoxLayout
from ui.common.theme import T, C


# ──────────────────────────────────────────────────────────────────
#  Toolbar flottante
# ──────────────────────────────────────────────────────────────────
class FloatingToolbar(QFrame):
    """
    Palette d'outils flottante et déplaçable superposée au canvas.

    Outils :
        select    — Sélection / déplacement d'actors   (S)
        add       — Ajouter un actor au clic           (A)
        erase     — Supprimer un actor au clic         (E)
        collision — Édition de collisions (dropdown)   (C)
        palette   — Éditeur de palette couleurs        (P)

    Le bouton collision ouvre un dropdown avec 3 modes :
        collision_8    — Pinceau  8×8 px
        collision_16   — Pinceau 16×16 px
        collision_slope— Slope (triangle)
    """

    tool_changed = pyqtSignal(str)  # ex. "select", "collision_8", "collision_slope"…

    # Outils principaux — (id, icon_key, titre, raccourci, description)
    _MAIN_TOOLS = [
        ("select", "tool_select", 'cvtool.select', 'cvtool.shortcut_select', 'cvtool.select_tip'),
        ("add", "tool_add", 'cvtool.add_actor', 'cvtool.shortcut_add', 'cvtool.add_actor_tip'),
        ("erase", "tool_erase", 'cvtool.eraser', 'cvtool.shortcut_erase', 'cvtool.eraser_tip'),
    ]

    # Sous-outils collision — (id, icon_key, label, tooltip)
    _COLLISION_MODES = [
        (
            "collision_8",
            "tool_collision_8",
            'cvtool.8_8_px_brush',
            'cvtool.collision_brush_8_8_px',
        ),
        (
            "collision_16",
            "tool_collision_16",
            'cvtool.16_16_px_brush',
            'cvtool.collision_brush_16_16_px',
        ),
        (
            "collision_slope",
            "tool_collision_slope",
            'cvtool.floor_slope',
            'cvtool.floor_slope_triangle_bresenham',
        ),
        (
            "collision_slope_inv",
            "tool_collision_slope_inv",
            'cvtool.ceiling_slope',
            'cvtool.ceiling_slope_tip',
        ),
    ]

    # Sous-outils inpainting de scène — (id, icon_key, label, tooltip)
    _INPAINT_MODES = [
        ("inpaint_brush", "tool_inpaint_brush", 'cvtool.brush',
         'cvtool.inpaint_brush_tip'),
        ("inpaint_rect", "tool_inpaint_rect", 'cvtool.rectangle',
         'cvtool.inpaint_rect_tip'),
    ]
    _INPAINT_ICON_KEYS = {
        "inpaint_brush": "tool_inpaint_brush",
        "inpaint_rect": "tool_inpaint_rect",
    }

    # Sous-outils UI — (id, icon_key, label, tooltip). Un seul bouton, le type
    # se choisit au dropdown (comme collision/inpaint) ; le geste rectangle est
    # le même pour les trois. Icônes = formes de la famille Interface.
    _UI_MODES = [
        ("ui_text", "ui_text", 'common.text',
         'cvtool.text_tip'),
        ("ui_container", "ui_container", 'common.container',
         'cvtool.container_tip'),
        ("ui_list", "ui_list", 'common.list',
         'cvtool.list_tip'),
        ("ui_image", "ui_image", 'common.image',
         'cvtool.image_tip'),
    ]
    _UI_ICON_KEYS = {
        "ui_text": "ui_text",
        "ui_container": "ui_container",
        "ui_list": "ui_list",
        "ui_image": "ui_image",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._dragging = False
        self._drag_offset = QPoint()
        self._current_tool = "select"
        self._current_collision = "collision_8"
        self._current_inpaint = "inpaint_brush"
        self._current_ui = "ui_text"

        self.setFixedWidth(46)
        self.setStyleSheet(f"""
            FloatingToolbar {{
                background: {C.BG_RAISED};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
            }}
            QToolButton {{
                border: none;
                background: transparent;
                border-radius: 5px;
            }}
            QToolButton:hover   {{ background: {C.BG_HOVER}; }}
            QToolButton:checked {{
                background: {C.BG_SEL};
                border: 1px solid {C.ACCENT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(2)

        from ui.common.widgets import DragHandle
        drag_handle = DragHandle(Qt.Orientation.Vertical)
        drag_handle.setToolTip(tooltip(title=label("cvtool.move_toolbar")))
        layout.addWidget(drag_handle)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C.BORDER}; margin:2px 0;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        self._btns: dict[str, QToolButton] = {}

        # ── Outils principaux ─────────────────────────────────────
        for tool_id, icon_key, title_key, shortcut_key, body_key in self._MAIN_TOOLS:
            btn = QToolButton()
            btn.setIcon(_ico(icon_key, COLOR_DEFAULT, COLOR_ACTIVE))
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setToolTip(tooltip(
                title=label(title_key), shortcut=label(shortcut_key), body=label(body_key)
            ))
            btn.setCheckable(True)
            btn.setChecked(tool_id == "select")
            btn.setFixedSize(36, 36)
            btn.clicked.connect(lambda _, t=tool_id: self._set_tool(t))  # re-coché par _sync_buttons
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._btns[tool_id] = btn

        # ── Bouton collision avec dropdown ────────────────────────
        self._btn_collision = QToolButton()
        # Icône « mur » partagée avec le toggle « Collisions scène » de la
        # toolbar haute : une seule identité visuelle pour la collision. Le
        # sous-mode actif (8/16/slope) se choisit dans le menu déroulant.
        self._btn_collision.setIcon(_ico("view_collision", COLOR_DEFAULT, COLOR_ACTIVE))
        self._btn_collision.setIconSize(QSize(24, 24))
        self._btn_collision.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_collision.setToolTip(tooltip(
            title=label('cvtool.collision_editing'), shortcut="C",
            body=label('cvtool.collision_editing_tip'),
        ))
        self._btn_collision.setCheckable(True)
        self._btn_collision.setFixedSize(36, 36)
        self._btn_collision.clicked.connect(self._on_collision_click)
        layout.addWidget(self._btn_collision, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["collision"] = self._btn_collision

        # ── Bouton peinture palette BG avec dropdown ──────────────
        self._btn_inpaint = QToolButton()
        self._btn_inpaint.setIcon(
            _ico(self._INPAINT_ICON_KEYS[self._current_inpaint],
                 COLOR_DEFAULT, COLOR_ACTIVE)
        )
        self._btn_inpaint.setIconSize(QSize(24, 24))
        self._btn_inpaint.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_inpaint.setToolTip(tooltip(
            title=label('cvtool.scene_inpainting'), shortcut="B",
            body=label('cvtool.scene_inpainting_tip'),
        ))
        self._btn_inpaint.setCheckable(True)
        self._btn_inpaint.setFixedSize(36, 36)
        self._btn_inpaint.clicked.connect(self._on_inpaint_click)
        layout.addWidget(self._btn_inpaint, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["inpaint_btn"] = self._btn_inpaint

        # ── Séparateur + outil palette ────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{C.BORDER}; margin:3px 0;")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        # Widgets d'interface. Un bouton, trois types au dropdown (zone,
        # conteneur, texte) — l'icône du bouton reflète le type courant, T
        # reprend le dernier utilisé, comme collision (C) et inpainting (B).
        self._btn_ui = QToolButton()
        self._btn_ui.setIcon(
            _ico(self._UI_ICON_KEYS[self._current_ui], COLOR_DEFAULT, COLOR_ACTIVE))
        self._btn_ui.setIconSize(QSize(20, 20))
        self._btn_ui.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_ui.setToolTip(tooltip(
            title=label('cvtool.interface_widget'), shortcut="T",
            body=label('cvtool.interface_widget_tip'),
        ))
        self._btn_ui.setCheckable(True)
        self._btn_ui.setFixedSize(34, 34)
        self._btn_ui.clicked.connect(self._on_ui_click)
        layout.addWidget(self._btn_ui, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["ui_btn"] = self._btn_ui

        layout.addStretch()
        self.adjustSize()

    # ── Collision dropdown ────────────────────────────────────────

    def _on_collision_click(self):
        self._show_collision_menu()

    def _show_collision_menu(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(f"""
            QMenu {{
                background: {C.BG_RAISED};
                color: {C.TEXT_NORM};
                border: 1px solid {C.BORDER_MID};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{ padding: 5px 14px 5px 8px; border-radius: 3px; icon-size: 20px; }}
            QMenu::item:selected {{ background: {C.BG_SEL}; color: {C.ACCENT}; }}
            QMenu::item:checked  {{ color: {C.ACCENT}; }}
        """)

        from ui.common.icons import COLOR_DEFAULT
        from ui.common.icons import get as _ico

        for mode_id, icon_key, lbl_key, tip in self._COLLISION_MODES:
            act = QAction(label(lbl_key), self)
            act.setIcon(_ico(icon_key, COLOR_DEFAULT))
            act.setToolTip(tooltip(title=label(lbl_key), body=label(tip)))
            act.setCheckable(True)
            act.setChecked(self._current_collision == mode_id)
            act.triggered.connect(lambda _, m=mode_id: self._select_collision_mode(m))
            menu.addAction(act)

        # Positionner le menu à droite du bouton
        btn_pos = self._btn_collision.mapToGlobal(
            QPoint(self._btn_collision.width() + 4, 0)
        )
        self._exec_menu(menu, btn_pos, self._btn_collision)

    def _select_collision_mode(self, mode: str):
        # Le bouton garde l'icône « mur » (identité collision partagée) ; le
        # sous-mode choisi est indiqué par la coche du menu déroulant.
        self._current_collision = mode
        self._set_tool(mode)

    # ── Peinture palette BG dropdown ──────────────────────────────

    def _on_inpaint_click(self):
        self._show_inpaint_menu()

    def _show_inpaint_menu(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(f"""
            QMenu {{ background:{C.BG_RAISED}; color:{C.TEXT_NORM}; border:1px solid {C.BORDER_MID};
                    border-radius:4px; padding:4px; }}
            QMenu::item {{ padding:5px 14px 5px 8px; border-radius:3px; icon-size:20px; }}
            QMenu::item:selected {{ background:{C.BG_SEL}; color:{C.ACCENT}; }}
            QMenu::item:checked  {{ color:{C.ACCENT}; }}
        """)
        from ui.common.icons import COLOR_DEFAULT
        from ui.common.icons import get as _ico

        for mode_id, icon_key, lbl_key, tip in self._INPAINT_MODES:
            act = QAction(label(lbl_key), self)
            act.setIcon(_ico(icon_key, COLOR_DEFAULT))
            act.setToolTip(tooltip(title=label(lbl_key), body=label(tip)))
            act.setCheckable(True)
            act.setChecked(self._current_inpaint == mode_id)
            act.triggered.connect(lambda _, m=mode_id: self._select_inpaint_mode(m))
            menu.addAction(act)

        btn_pos = self._btn_inpaint.mapToGlobal(
            QPoint(self._btn_inpaint.width() + 4, 0)
        )
        self._exec_menu(menu, btn_pos, self._btn_inpaint)

    def _select_inpaint_mode(self, mode: str):
        self._current_inpaint = mode
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._btn_inpaint.setIcon(
            _ico(self._INPAINT_ICON_KEYS[mode], COLOR_DEFAULT, COLOR_ACTIVE)
        )
        self._set_tool(mode)

    # ── Widgets d'interface dropdown ──────────────────────────────

    def _on_ui_click(self):
        self._show_ui_menu()

    def _show_ui_menu(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(f"""
            QMenu {{ background:{C.BG_RAISED}; color:{C.TEXT_NORM}; border:1px solid {C.BORDER_MID};
                    border-radius:4px; padding:4px; }}
            QMenu::item {{ padding:5px 14px 5px 8px; border-radius:3px; icon-size:20px; }}
            QMenu::item:selected {{ background:{C.BG_SEL}; color:{C.ACCENT}; }}
            QMenu::item:checked  {{ color:{C.ACCENT}; }}
        """)
        from ui.common.icons import COLOR_UI
        from ui.common.icons import get as _ico

        for mode_id, icon_key, lbl_key, tip in self._UI_MODES:
            act = QAction(label(lbl_key), self)
            act.setIcon(_ico(icon_key, COLOR_UI))
            act.setToolTip(tooltip(title=label(lbl_key), body=label(tip)))
            act.setCheckable(True)
            act.setChecked(self._current_ui == mode_id)
            act.triggered.connect(lambda _, m=mode_id: self._select_ui_mode(m))
            menu.addAction(act)

        btn_pos = self._btn_ui.mapToGlobal(QPoint(self._btn_ui.width() + 4, 0))
        self._exec_menu(menu, btn_pos, self._btn_ui)

    def _select_ui_mode(self, mode: str):
        self._current_ui = mode
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._btn_ui.setIcon(
            _ico(self._UI_ICON_KEYS[mode], COLOR_DEFAULT, COLOR_ACTIVE)
        )
        self._set_tool(mode)

    # ── Outil actif ───────────────────────────────────────────────

    def _set_tool(self, tool: str):
        self._current_tool = tool
        self._sync_buttons()
        self.tool_changed.emit(tool)

    def _sync_buttons(self):
        """Coche EXACTEMENT le bouton de l'outil courant. Seule source de l'état
        visuel : le toggle automatique de QToolButton (clic sur un bouton déjà
        coché, ou sur un bouton à menu) ne doit jamais décider seul."""
        tool = self._current_tool
        for tid, btn in self._btns.items():
            btn.setChecked(
                tid == tool
                or (tid == "collision" and tool.startswith("collision"))
                or (tid == "inpaint_btn" and tool.startswith("inpaint"))
                or (tid == "ui_btn" and tool.startswith("ui_"))
            )

    def _exec_menu(self, menu, pos, owner):
        """Ouvre un dropdown d'outil. Pendant qu'il est ouvert, SEUL son bouton
        est coché (l'utilisateur est en train de choisir un autre outil) ; s'il
        est refermé sans choix, l'outil précédent est restauré."""
        for btn in self._btns.values():
            btn.setChecked(btn is owner)
        menu.exec(pos)
        self._sync_buttons()

    @property
    def current_tool(self) -> str:
        return self._current_tool

    def activate_shortcut(self, group: str):
        """Active un outil depuis un raccourci clavier. Pour 'collision' /
        'inpaint', reprend le dernier sous-mode utilisé (comme un clic ré-active
        le mode courant). Passe par _set_tool → boutons + signal synchronisés."""
        if group == "collision":
            self._set_tool(self._current_collision)
        elif group == "inpaint":
            self._set_tool(self._current_inpaint)
        elif group == "ui":
            self._set_tool(self._current_ui)
        else:
            self._set_tool(group)

    # ── Drag ──────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = e.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging and self.parent():
            new_pos = self.mapToParent(e.pos()) - self._drag_offset
            p = self.parent()
            x = max(0, min(new_pos.x(), p.width() - self.width()))
            y = max(0, min(new_pos.y(), p.height() - self.height()))
            self.move(x, y)

    def mouseReleaseEvent(self, e):
        self._dragging = False
        super().mouseReleaseEvent(e)
