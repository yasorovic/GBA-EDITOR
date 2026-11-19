"""ui/scene_manager/canvas/canvas_toolbar.py : la palette d'outils flottante.

Extrait de `scene_canvas` (A3) : `FloatingToolbar`, le `QFrame` déplaçable
superposé au canvas — les boutons d'outils (sélection, collision, inpaint,
interface), leurs menus déroulants et les raccourcis. N'émet que des signaux
(`tool_changed`…) ; elle ne connaît ni la vue ni la scène.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from core.keybindings import get_keybindings
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
        add       — Ajouter un actor ou une Area au clic (A, dropdown)
        erase     — Supprimer un actor au clic         (E)
        inpaint   — Peinture de la surface choisie (B, C pour Collision)
    """

    tool_changed = pyqtSignal(str)  # ex. "select", "paint_brush", "paint_fill"…

    # Outils principaux — (id, icon_key, titre, description) — le raccourci est `canvas.<icon_key>`
    _MAIN_TOOLS = [
        ("select", "tool_select", 'cvtool.select', 'cvtool.select_tip'),
        ("add", "tool_add", 'cvtool.add', 'cvtool.add_tip'),
        ("erase", "tool_erase", 'cvtool.eraser', 'cvtool.eraser_tip'),
    ]

    # Sous-outils d'ajout — (id, icon_key, label, tooltip). Le bouton (+) garde son icône ; ce qu'un clic pose se
    # choisit au dropdown, comme collision et interface, et A reprend le dernier choix.
    _ADD_MODES = [
        ("add", "tool_add", 'cvtool.add_actor', 'cvtool.add_actor_tip'),
        ("add_area", "area", 'cvtool.add_area', 'cvtool.add_area_tip'),
    ]

    # Sous-outils inpainting de scène — (id, icon_key, label, tooltip)
    _PAINT_MODES = [
        ("paint_brush", "tool_tile_brush", 'cvtool.brush',
         'cvtool.paint_brush_tip'),
        ("paint_rect", "tool_inpaint_rect", 'cvtool.rectangle',
         'cvtool.paint_rect_tip'),
        ("paint_fill", "tool_fill", 'bginp.fill', 'cvtool.paint_fill_tip'),
    ]
    _PAINT_ICON_KEYS = {
        "paint_brush": "tool_tile_brush",
        "paint_rect": "tool_inpaint_rect",
        "paint_fill": "tool_fill",
    }

    # Sous-outils UI — (id, icon_key, label, tooltip). Un seul bouton, le type
    # se choisit au dropdown (comme collision/inpaint) ; le geste rectangle est
    # le même pour les trois. Icônes = formes de la famille Interface.
    _UI_MODES = [
        ("ui_text", "ui_text", 'common.text',
         'cvtool.text_tip'),
        ("ui_container", "ui_container", 'common.container',
         'cvtool.container_tip'),
        ("ui_image", "ui_image", 'common.image',
         'cvtool.image_tip'),
        ("ui_textbox", "ui_textbox", 'common.textbox',
         'cvtool.textbox_tip'),
    ]
    _UI_ICON_KEYS = {
        "ui_text": "ui_text",
        "ui_textbox": "ui_textbox",
        "ui_container": "ui_container",
        "ui_image": "ui_image",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._dragging = False
        self._drag_offset = QPoint()
        self._current_tool = "select"
        self._current_add = "add"
        self._current_paint = "paint_brush"
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
        for tool_id, icon_key, title_key, body_key in self._MAIN_TOOLS:
            btn = QToolButton()
            btn.setIcon(_ico(icon_key, COLOR_DEFAULT, COLOR_ACTIVE))
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setToolTip(tooltip(
                title=label(title_key), shortcut=get_keybindings().resolve(f"canvas.{icon_key}"), body=label(body_key)
            ))
            btn.setCheckable(True)
            btn.setChecked(tool_id == "select")
            btn.setFixedSize(36, 36)
            if tool_id == "add":
                btn.clicked.connect(self._on_add_click)    # un dropdown : acteur ou Area
            else:
                btn.clicked.connect(lambda _, t=tool_id: self._set_tool(t))  # re-coché par _sync_buttons
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._btns[tool_id] = btn

        # ── Bouton de peinture de surface avec dropdown ───────────
        self._btn_paint = QToolButton()
        self._btn_paint.setIcon(
            _ico(self._PAINT_ICON_KEYS[self._current_paint],
                 COLOR_DEFAULT, COLOR_ACTIVE)
        )
        self._btn_paint.setIconSize(QSize(24, 24))
        self._btn_paint.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_paint.setToolTip(tooltip(
            title=label('cvtool.surface_painting'), shortcut=get_keybindings().resolve("canvas.tool_inpaint"),
            body=label('cvtool.surface_painting_tip'),
        ))
        self._btn_paint.setCheckable(True)
        self._btn_paint.setFixedSize(36, 36)
        self._btn_paint.clicked.connect(self._on_paint_click)
        layout.addWidget(self._btn_paint, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["paint_btn"] = self._btn_paint

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
            title=label('cvtool.interface_widget'), shortcut=get_keybindings().resolve("canvas.tool_ui"),
            body=label('cvtool.interface_widget_tip'),
        ))
        self._btn_ui.setCheckable(True)
        self._btn_ui.setFixedSize(34, 34)
        self._btn_ui.clicked.connect(self._on_ui_click)
        layout.addWidget(self._btn_ui, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["ui_btn"] = self._btn_ui

        layout.addStretch()
        self.adjustSize()

    # ── Ajout dropdown ────────────────────────────────────────────

    def _on_add_click(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(f"""
            QMenu {{ background:{C.BG_RAISED}; color:{C.TEXT_NORM}; border:1px solid {C.SPLITTER};
                    border-radius:4px; padding:4px; }}
            QMenu::item {{ padding:5px 14px 5px 8px; border-radius:3px; icon-size:20px; }}
            QMenu::item:selected {{ background:{C.BG_SEL}; color:{C.ACCENT}; }}
            QMenu::item:checked  {{ color:{C.ACCENT}; }}
        """)
        from ui.common.icons import COLOR_DEFAULT
        from ui.common.icons import get as _ico

        for mode_id, icon_key, lbl_key, tip in self._ADD_MODES:
            act = QAction(label(lbl_key), self)
            act.setIcon(_ico(icon_key, COLOR_DEFAULT))
            act.setToolTip(tooltip(title=label(lbl_key), body=label(tip)))
            act.setCheckable(True)
            act.setChecked(self._current_add == mode_id)
            act.triggered.connect(lambda _, m=mode_id: self._select_add_mode(m))
            menu.addAction(act)

        btn = self._btns["add"]
        self._exec_menu(menu, btn.mapToGlobal(QPoint(btn.width() + 4, 0)), btn)

    def _select_add_mode(self, mode: str):
        # Le bouton garde son (+) ; le mode choisi est indiqué par la coche du menu.
        self._current_add = mode
        self._set_tool(mode)

    # ── Peinture de surface dropdown ──────────────────────────────
    # ── Peinture palette BG dropdown ──────────────────────────────

    def _on_paint_click(self):
        self._show_paint_menu()

    def _show_paint_menu(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(f"""
            QMenu {{ background:{C.BG_RAISED}; color:{C.TEXT_NORM}; border:1px solid {C.SPLITTER};
                    border-radius:4px; padding:4px; }}
            QMenu::item {{ padding:5px 14px 5px 8px; border-radius:3px; icon-size:20px; }}
            QMenu::item:selected {{ background:{C.BG_SEL}; color:{C.ACCENT}; }}
            QMenu::item:checked  {{ color:{C.ACCENT}; }}
        """)
        from ui.common.icons import COLOR_DEFAULT
        from ui.common.icons import get as _ico

        for mode_id, icon_key, lbl_key, tip in self._PAINT_MODES:
            act = QAction(label(lbl_key), self)
            act.setIcon(_ico(icon_key, COLOR_DEFAULT))
            act.setToolTip(tooltip(title=label(lbl_key), body=label(tip)))
            act.setCheckable(True)
            act.setChecked(self._current_paint == mode_id)
            act.triggered.connect(lambda _, m=mode_id: self._select_paint_mode(m))
            menu.addAction(act)

        btn_pos = self._btn_paint.mapToGlobal(
            QPoint(self._btn_paint.width() + 4, 0)
        )
        self._exec_menu(menu, btn_pos, self._btn_paint)

    def _select_paint_mode(self, mode: str):
        self._current_paint = mode
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._btn_paint.setIcon(
            _ico(self._PAINT_ICON_KEYS[mode], COLOR_DEFAULT, COLOR_ACTIVE)
        )
        self._set_tool(mode)

    def activate_paint_gesture(self, mode: str):
        if mode in self._PAINT_ICON_KEYS:
            self._select_paint_mode(mode)

    # ── Widgets d'interface dropdown ──────────────────────────────

    def _on_ui_click(self):
        self._show_ui_menu()

    def _show_ui_menu(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(f"""
            QMenu {{ background:{C.BG_RAISED}; color:{C.TEXT_NORM}; border:1px solid {C.SPLITTER};
                    border-radius:4px; padding:4px; }}
            QMenu::item {{ padding:5px 14px 5px 8px; border-radius:3px; icon-size:20px; }}
            QMenu::item:selected {{ background:{C.BG_SEL}; color:{C.ACCENT}; }}
            QMenu::item:checked  {{ color:{C.ACCENT}; }}
        """)
        from ui.common.icons import COLOR_UI
        from ui.common.icons import get as _ico

        from core.models.ui_region import KINDS_ASSEMBLY
        for mode_id, icon_key, lbl_key, tip in self._UI_MODES:
            # Deux familles dans le même menu : les briques d'abord, puis ce
            # qui s'assemble. L'ordre de `_UI_MODES` les range déjà ainsi.
            if mode_id[3:] == KINDS_ASSEMBLY[0]:
                menu.addSection(label('common.assemblies'))
            elif mode_id == self._UI_MODES[0][0]:
                menu.addSection(label('common.bricks'))
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
                or (tid == "add" and tool == "add_area")
                or (tid == "paint_btn" and tool.startswith("paint_"))
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
        """Active un outil depuis un raccourci clavier. Pour la peinture,
        reprend le dernier geste utilisé (comme un clic ré-active
        le mode courant). Passe par _set_tool → boutons + signal synchronisés."""
        if group == "add":
            self._set_tool(self._current_add)
        elif group == "collision":
            self._set_tool(self._current_paint)
        elif group == "paint":
            self._set_tool(self._current_paint)
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
