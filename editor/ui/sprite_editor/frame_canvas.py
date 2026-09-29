"""
ui/sprite_editor/frame_canvas.py — timeline de frames + canvas de composition
peint tuile par tuile (édition de la frame courante d'une AnimState/StateDirection).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton,
    QFrame, QScrollArea, QMenu, QApplication, QWidgetAction, QLineEdit,
)
from PyQt6.QtGui import (
    QFont, QColor, QPixmap, QImage, QDrag, QPainter, QPen, QBrush,
    QKeySequence, QShortcut,
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint, QPointF, QRect, QRectF, QSize

from ui.common.theme import C, T, QSS, tint
from ui.common.labels import label
from ui.common.icons import get as _ico
from ui.common.palette_bank_strip import PaletteBankStrip
from ui.common.canvas_backdrop import draw_grid, draw_grid_halo
from core.models.sprite import (
    AnimFrame,
    AnimState,
    SpriteAsset,
    StateDirection,
    TilePlacement,
)
from core.history import get_history, PaintFrameCmd
from core.sprite_compose import compose_frame_image
from core.keybindings import bind

# ── Frame timeline ─────────────────────────────────────────────────────────────

_THUMB_IMG  = 52   # px image dans la vignette
_THUMB_W    = 64   # largeur totale vignette
_THUMB_H    = 74   # image + label index
_TIMELINE_H = 106  # hauteur fixe de la zone timeline


def _pil_to_pixmap(img, size: int) -> QPixmap:
    if img.width <= 0 or img.height <= 0:
        pm = QPixmap(size, size)
        pm.fill(QColor(C.BG_PANEL))
        return pm
    img = img.resize((size, size), __import__("PIL").Image.NEAREST)
    data = bytes(img.tobytes("raw", "RGBA"))
    qi = QImage(data, size, size, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qi)


def _make_frame_pixmap(abs_path: Optional[Path], frame: AnimFrame,
                       fw: int, fh: int, size: int = _THUMB_IMG,
                       flip: tuple[bool, bool] = (False, False)) -> QPixmap:
    img = compose_frame_image(abs_path, frame, fw, fh)
    if flip[0] or flip[1]:
        from PIL import Image as _Im
        if flip[0]:
            img = img.transpose(_Im.FLIP_LEFT_RIGHT)
        if flip[1]:
            img = img.transpose(_Im.FLIP_TOP_BOTTOM)
    return _pil_to_pixmap(img, size)


class _FrameThumb(QFrame):
    """Vignette d'un frame, draggable via QDrag."""

    MIME = "application/x-frame-index"

    clicked        = pyqtSignal(int)  # index
    context_asked  = pyqtSignal(int, object)  # index, QPoint global

    def __init__(self, index: int, frame: AnimFrame,
                 pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._index    = index
        self._frame    = frame
        self._selected = False
        self._draggable = True   # désactivé pour les miroirs (lecture seule)
        self._press_pos: Optional[QPoint] = None

        self.setFixedSize(_THUMB_W, _THUMB_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(False)

        self._pix_lbl = QLabel(self)
        self._pix_lbl.setPixmap(pixmap)
        self._pix_lbl.setGeometry((_THUMB_W - _THUMB_IMG) // 2, 4, _THUMB_IMG, _THUMB_IMG)
        self._pix_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._idx_lbl = QLabel(str(index + 1), self)
        self._idx_lbl.setFont(QFont(T.MONO, T.XS))
        self._idx_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._idx_lbl.setGeometry(0, _THUMB_IMG + 8, _THUMB_W, 14)
        self._idx_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Badge des déclencheurs posés sur la frame (SoundBox/Sfx/EventCall) —
        # initiales empilées en haut à droite, juste pour dire « il y a quelque
        # chose ici » sans ouvrir le menu contextuel.
        self._badge_lbl = QLabel("", self)
        self._badge_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.DemiBold))
        self._badge_lbl.setStyleSheet(f"color:{C.ACCENT};background:transparent;")
        self._badge_lbl.setGeometry(_THUMB_W - 18, 2, 16, 12)
        self._badge_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._badge_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.update_triggers(frame)

        self._refresh_style()

    def update_triggers(self, frame: AnimFrame):
        """Reflète action_name/direct_sfx_name/event_name : badge + tooltip."""
        parts = []
        if frame.action_name:
            parts.append(("B", label("sprframe.trig_action", name=frame.action_name)))
        if frame.direct_sfx_name:
            parts.append(("X", label("sprframe.trig_sfx", name=frame.direct_sfx_name)))
        if frame.event_name:
            parts.append(("E", label("sprframe.trig_event", name=frame.event_name)))
        self._badge_lbl.setText("".join(p[0] for p in parts))
        self.setToolTip("\n".join(p[1] for p in parts))

    def set_selected(self, sel: bool):
        if self._selected != sel:
            self._selected = sel
            self._refresh_style()

    def update_index(self, index: int):
        self._index = index
        self._idx_lbl.setText(str(index + 1))

    def update_pixmap(self, pixmap: QPixmap):
        self._pix_lbl.setPixmap(pixmap)

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet(
                f"QFrame{{background:{C.BG_SEL};border:2px solid {C.ACCENT};"
                f"border-radius:4px;}}"
            )
            self._idx_lbl.setStyleSheet(
                f"color:{C.ACCENT};background:transparent;")
        else:
            self.setStyleSheet(
                f"QFrame{{background:{C.BG_INPUT};border:1px solid {C.BORDER};"
                f"border-radius:4px;}}"
            )
            self._idx_lbl.setStyleSheet(
                f"color:{C.TEXT_DIM};background:transparent;")

    # ── Events ────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.pos()
        elif e.button() == Qt.MouseButton.RightButton:
            self.context_asked.emit(self._index, e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if not self._draggable:
            return
        if not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._press_pos is None:
            return
        if (e.pos() - self._press_pos).manhattanLength() < QApplication.startDragDistance():
            return
        # Démarrer le drag
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self.MIME, str(self._index).encode())
        drag.setMimeData(mime)
        # Ghost semi-transparent
        ghost = self.grab()
        painter = QPainter(ghost)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(ghost.rect(), QColor(0, 0, 0, 160))
        painter.end()
        drag.setPixmap(ghost)
        drag.setHotSpot(self._press_pos)
        self._press_pos = None
        drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            self.clicked.emit(self._index)
            self._press_pos = None


class _FrameTimeline(QWidget):
    """
    Bande horizontale de frames avec :
    - clic → sélection
    - drag-drop → réordonnancement
    - clic droit → copy / clone / delete
    - bouton + → ajouter une frame
    """

    frame_selected = pyqtSignal(int)    # index sélectionné
    frames_changed = pyqtSignal()       # frames modifiées (save)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_TIMELINE_H)
        self.setStyleSheet(
            f"background:{C.BG_PANEL};"
            f"border-top:1px solid {C.BORDER_DARK};"
        )
        # Focus requis pour que Ctrl+D / Suppr n'agissent que quand la
        # timeline est active (ex: pas pendant l'édition d'un nom ailleurs).
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._sprite:    Optional[SpriteAsset]    = None
        self._project    = None   # Project — pour lister les Sfx/actions SoundBox du menu contextuel
        self._state:     Optional[AnimState]       = None
        self._sd:        Optional[StateDirection]  = None
        self._abs_path:  Optional[Path]            = None
        self._selected:  int                       = 0
        self._thumbs:    list[_FrameThumb]         = []
        self._drop_before: Optional[int]           = None   # indicateur pendant drag
        # Mode lecture seule : direction miroir (mirror_of défini). Les frames
        # affichées sont celles de la direction source, retournées (flip) — le
        # miroir ne possède pas ses propres frames éditables.
        self._read_only:      bool                 = False
        self._disp_frames:    Optional[list]       = None   # frames source du miroir
        self._flip:           tuple[bool, bool]    = (False, False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Label section
        hdr = QLabel(label("sprframe.frames_header"))
        hdr.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        hdr.setFixedHeight(18)
        hdr.setStyleSheet(
            f"color:{C.TEXT_DIM};background:{C.BG_RAISED};"
            f"border-bottom:1px solid {C.BORDER_DARK};"
        )
        outer.addWidget(hdr)

        # Zone de scroll horizontale
        self._scroll = QScrollArea()
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(False)
        self._scroll.setStyleSheet(
            QSS.scroll_area
            + "QScrollBar:horizontal{height:6px;}"
        )

        self._content = QWidget()
        self._content.setAcceptDrops(True)
        self._content.dragEnterEvent  = self._drag_enter
        self._content.dragMoveEvent   = self._drag_move
        self._content.dragLeaveEvent  = self._drag_leave
        self._content.dropEvent       = self._drop
        self._content.paintEvent      = self._paint_drop_indicator

        self._layout = QHBoxLayout(self._content)
        self._layout.setContentsMargins(8, 0, 8, 0)
        self._layout.setSpacing(6)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Bouton +
        self._add_btn = QToolButton()
        self._add_btn.setText("+")
        self._add_btn.setFixedSize(36, _THUMB_H)
        self._add_btn.setStyleSheet(
            f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px dashed {C.BORDER};border-radius:4px;"
            f"font-size:{T.LG}px;}}"
            f"QToolButton:hover{{color:{C.ACCENT};border-color:{C.ACCENT};}}"
        )
        self._add_btn.setToolTip(label("sprframe.add_frame_tip"))
        self._add_btn.clicked.connect(self._on_add)

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, 1)

        # Raccourcis : n'agissent que quand la timeline (ou un enfant) a le focus.
        dup = QShortcut(QKeySequence(), self)
        dup.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        dup.activated.connect(lambda: self._copy_frame(self._selected))
        bind("sprite.duplicate_frame", dup)
        delete = QShortcut(QKeySequence(), self)
        delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        delete.activated.connect(lambda: self._delete_frame(self._selected))
        bind("sprite.delete_frame", delete)

    # ── API publique ───────────────────────────────────────────────────

    def load(self, sprite: SpriteAsset, state: AnimState,
             sd: StateDirection, abs_path: Optional[Path],
             read_only: bool = False, disp_frames: Optional[list] = None,
             flip: tuple[bool, bool] = (False, False), project=None):
        self._sprite     = sprite
        self._project    = project
        self._state      = state
        self._sd         = sd
        self._abs_path   = abs_path
        self._selected   = 0
        self._read_only  = read_only
        self._disp_frames = disp_frames
        self._flip       = flip
        self._rebuild()

    def _frames(self) -> list:
        """Frames à afficher : source retournée en lecture seule (miroir),
        sinon les frames propres de la direction."""
        if self._read_only and self._disp_frames is not None:
            return self._disp_frames
        return self._sd.frames if self._sd else []

    def clear(self):
        self._sprite = self._state = self._sd = None
        self._rebuild()

    # ── Construction ──────────────────────────────────────────────────

    def _rebuild(self):
        # Supprimer les anciens thumbs
        for t in self._thumbs:
            self._layout.removeWidget(t)
            t.deleteLater()
        self._thumbs.clear()

        # Retirer le stretch (dernier) et le bouton + pour les réinsérer
        while self._layout.count():
            item = self._layout.itemAt(self._layout.count() - 1)
            if item.widget() is self._add_btn or item.spacerItem():
                self._layout.takeAt(self._layout.count() - 1)
            else:
                break
        # hide() avant setParent(None) : même détaché puis rattaché dans la
        # foulée (voir plus bas), un bouton visible reparenté à rien devient
        # furtivement une fenêtre top-level ("micro popup" au changement de
        # sprite sélectionné).
        self._add_btn.hide()
        self._add_btn.setParent(None)

        frames = self._frames()
        if self._sd:
            fw = self._sprite.frame_w if self._sprite else 16
            fh = self._sprite.frame_h if self._sprite else 16
            for i, frame in enumerate(frames):
                pm  = _make_frame_pixmap(self._abs_path, frame, fw, fh, flip=self._flip)
                t   = _FrameThumb(i, frame, pm)
                t.set_selected(i == self._selected)
                t.clicked.connect(self._on_thumb_clicked)
                if self._read_only:
                    t._draggable = False
                else:
                    t.context_asked.connect(self._on_context_menu)
                self._layout.addWidget(t)
                self._thumbs.append(t)

        # Bouton + masqué en lecture seule (miroir non éditable).
        if not self._read_only:
            self._layout.addWidget(self._add_btn)
            self._add_btn.show()
        self._layout.addStretch()

        # Hauteur fixe = viewport, largeur = nombre de frames
        n = len(self._thumbs)
        content_w = n * (_THUMB_W + 6) + 16 + 6 + 42   # thumbs + marges + btn +
        vp_h = _TIMELINE_H - 20   # hauteur header (18) + séparateur (2)
        self._content.setFixedSize(max(content_w, self._scroll.width()), vp_h)

    def _select(self, index: int):
        if self._sd and 0 <= index < len(self._frames()):
            for i, t in enumerate(self._thumbs):
                t.set_selected(i == index)
            self._selected = index
            self.frame_selected.emit(index)

    def refresh_thumb(self, index: int, pixmap: QPixmap):
        """Met à jour l'image d'une vignette sans changer la sélection (après peinture)."""
        if 0 <= index < len(self._thumbs):
            self._thumbs[index].update_pixmap(pixmap)

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_thumb_clicked(self, index: int):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._select(index)

    def _on_add(self):
        if not self._sd or self._read_only:
            return
        # Copie de la frame sélectionnée (ou frame vide)
        if self._sd.frames:
            src = self._sd.frames[self._selected]
            self._sd.frames.append(src.clone())
        else:
            self._sd.frames.append(AnimFrame())
        self.frames_changed.emit()
        self._rebuild()
        self._select(len(self._sd.frames) - 1)

    def _on_context_menu(self, index: int, pos: QPoint):
        if not self._sd or self._read_only:
            return
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        copy_a  = menu.addAction(label("sprframe.menu_copy"))
        clone_a = menu.addAction(label("sprframe.menu_clone"))
        clear_a = menu.addAction(label("sprframe.menu_clear"))
        menu.addSeparator()
        del_a   = menu.addAction(label("sprframe.menu_delete"))
        del_a.setEnabled(len(self._sd.frames) > 1)

        menu.addSeparator()
        frame = self._sd.frames[index]
        self._build_trigger_menu(menu, label("sprframe.play_action"), frame.action_name,
                                 self._sound_action_names(), index, "action_name")
        self._build_trigger_menu(menu, label("sprframe.play_sfx"), frame.direct_sfx_name,
                                 self._sfx_names(), index, "direct_sfx_name")
        self._build_event_call_menu(menu, frame.event_name, index)

        act = menu.exec(pos)
        if act == copy_a:
            self._copy_frame(index)
        elif act == clone_a:
            self._clone_frame_to_end(index)
        elif act == clear_a:
            self._clear_frame(index)
        elif act == del_a:
            self._delete_frame(index)

    # ── Déclencheurs de frame (SoundBox action / Sfx / EventCall) ──────

    def _sound_action_names(self) -> list[str]:
        if not self._project:
            return []
        from core.models.sound_box import KIND_SOUND
        return self._project.sound_action_names(KIND_SOUND)

    def _sfx_names(self) -> list[str]:
        if not self._project:
            return []
        return [s.name for s in getattr(self._project, "sfx", [])]

    def _build_trigger_menu(self, parent: QMenu, title: str, current: str,
                            names: list[str], index: int, field: str):
        """Sous-menu inline listant les noms disponibles (SoundBox action ou
        Sfx) — pas de dialogue, on choisit dans le menu contextuel lui-même."""
        sub = parent.addMenu(
            label("sprframe.trigger_current", title=title, current=current)
            if current else title)
        none_a = sub.addAction(label("sprframe.none"))
        none_a.setCheckable(True)
        none_a.setChecked(not current)
        none_a.triggered.connect(lambda: self._set_frame_trigger(index, field, ""))
        if names:
            sub.addSeparator()
            for name in names:
                act = sub.addAction(name)
                act.setCheckable(True)
                act.setChecked(name == current)
                act.triggered.connect(lambda _c=False, n=name: self._set_frame_trigger(index, field, n))
        else:
            empty_a = sub.addAction(label("sprframe.none_in_project"))
            empty_a.setEnabled(False)

    def _build_event_call_menu(self, parent: QMenu, current: str, index: int):
        """EventCall : nom libre (fonction du script de l'actor), donc pas de
        liste à proposer — un champ texte embarqué DANS le menu contextuel
        (QWidgetAction), jamais une boîte de dialogue séparée."""
        title = (label("sprframe.event_call_current", name=current) if current
                 else label("sprframe.event_call"))
        sub = parent.addMenu(title)
        edit = QLineEdit(current)
        edit.setPlaceholderText(label("sprframe.event_placeholder"))
        edit.setStyleSheet(
            f"QLineEdit{{background:{C.BG_INPUT};color:{C.TEXT_HI};"
            f"border:1px solid {C.BORDER};border-radius:3px;padding:3px 6px;}}"
        )
        wa = QWidgetAction(sub)
        wa.setDefaultWidget(edit)
        sub.addAction(wa)
        edit.returnPressed.connect(lambda: (
            self._set_frame_trigger(index, "event_name", edit.text().strip()),
            sub.close(), parent.close(),
        ))
        if current:
            sub.addSeparator()
            clear_a = sub.addAction(label("sprframe.none"))
            clear_a.triggered.connect(lambda: self._set_frame_trigger(index, "event_name", ""))

    def _set_frame_trigger(self, index: int, field: str, value: str):
        if not self._sd or not (0 <= index < len(self._sd.frames)):
            return
        setattr(self._sd.frames[index], field, value)
        if 0 <= index < len(self._thumbs):
            self._thumbs[index].update_triggers(self._sd.frames[index])
        self.frames_changed.emit()

    # ── Actions frame (partagées menu contextuel + raccourcis clavier) ──

    def _copy_frame(self, index: int):
        if not self._sd or self._read_only or not self._sd.frames:
            return
        src = self._sd.frames[index]
        self._sd.frames.insert(index + 1, src.clone())
        self.frames_changed.emit()
        self._rebuild()
        self._select(index + 1)

    def _clone_frame_to_end(self, index: int):
        if not self._sd or self._read_only or not self._sd.frames:
            return
        src = self._sd.frames[index]
        self._sd.frames.append(src.clone())
        self.frames_changed.emit()
        self._rebuild()
        self._select(len(self._sd.frames) - 1)

    def _clear_frame(self, index: int):
        if not self._sd or self._read_only or not self._sd.frames:
            return
        self._sd.frames[index].tiles.clear()
        self.frames_changed.emit()
        self._rebuild()
        self._select(index)

    def _delete_frame(self, index: int):
        if not self._sd or self._read_only or len(self._sd.frames) <= 1:
            return
        self._sd.frames.pop(index)
        self.frames_changed.emit()
        self._rebuild()
        self._select(min(index, len(self._sd.frames) - 1))

    # ── Drag-drop reorder ─────────────────────────────────────────────

    def _drag_enter(self, e):
        if not self._read_only and e.mimeData().hasFormat(_FrameThumb.MIME):
            e.acceptProposedAction()

    def _drag_move(self, e):
        if not e.mimeData().hasFormat(_FrameThumb.MIME):
            return
        self._drop_before = self._drop_index(e.position().toPoint().x())
        self._content.update()
        e.acceptProposedAction()

    def _drag_leave(self, e):
        self._drop_before = None
        self._content.update()

    def _drop(self, e):
        if self._read_only or not e.mimeData().hasFormat(_FrameThumb.MIME) or not self._sd:
            return
        src_idx  = int(e.mimeData().data(_FrameThumb.MIME).data())
        dst_idx  = self._drop_index(e.position().toPoint().x())
        self._drop_before = None
        self._content.update()

        if src_idx == dst_idx or src_idx + 1 == dst_idx:
            return
        frame = self._sd.frames.pop(src_idx)
        insert_at = dst_idx if dst_idx <= src_idx else dst_idx - 1
        self._sd.frames.insert(insert_at, frame)
        self.frames_changed.emit()
        self._rebuild()
        self._select(insert_at)
        e.acceptProposedAction()

    def _drop_index(self, x: int) -> int:
        """Retourne l'index d'insertion (0..n) correspondant à la position x."""
        for i, t in enumerate(self._thumbs):
            mid = t.x() + t.width() // 2
            if x < mid:
                return i
        return len(self._thumbs)

    def _paint_drop_indicator(self, e):
        """Ligne verte indiquant l'emplacement de dépôt."""
        from PyQt6.QtGui import QPainter, QPen
        QWidget.paintEvent(self._content, e)
        if self._drop_before is None or not self._thumbs:
            return
        painter = QPainter(self._content)
        pen = QPen(QColor(C.ACCENT), 2)
        painter.setPen(pen)
        n = len(self._thumbs)
        if self._drop_before < n:
            t = self._thumbs[self._drop_before]
            x = t.x() - 3
        else:
            t = self._thumbs[-1]
            x = t.x() + t.width() + 3
        y1 = t.y()
        y2 = t.y() + t.height()
        painter.drawLine(x, y1, x, y2)
        painter.end()


# ── Canvas de frame (composition peinte tuile par tuile) ───────────────────────

class _FrameCanvas(QWidget):
    """
    Zone de composition — grille de tuiles 8×8.
    Clic gauche = peindre (brosse active) ou sélectionner/ramasser des
    tuiles déjà posées (aucune brosse active) ; clic droit = effacer +
    reset sélection picker. Molette = zoom, molette centrale glissée = pan.
    Shift+X / Shift+Y = flip horizontal/vertical de la brosse active.
    """

    DEFAULT_ZOOM = 10    # zoom à l'ouverture et à chaque nouveau sprite (Fit = 0)

    frame_painted      = pyqtSignal()
    selection_reset    = pyqtSignal()   # demande reset de la sélection dans le picker
    hover_changed       = pyqtSignal(object)  # (col, row) survolé, ou None
    brush_picked_up     = pyqtSignal(int)     # nb de tuiles ramassées depuis le canvas

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sprite:     Optional[SpriteAsset] = None
        self._abs_path:   Optional[Path]        = None
        self._src_pixmap: Optional[QPixmap]     = None
        self._frame:      Optional[AnimFrame]   = None
        self._tile_w = self._tile_h = 1
        self._show_grid  = True
        # Teinte de preview (aperçu uniquement — banque choisie via le
        # dropdown palette de la barre d'outils, cf SpriteCenterPanel) :
        # liste de couleurs BGR555, ou None pour les pixels sources.
        self._tint_bank: Optional[list[int]] = None
        # Compression NON-DESTRUCTIVE du sprite courant (own_palette BGR555) —
        # source de vérité du rendu dérivé. [] = pas de compression (source brut).
        self._own_palette: list = []
        # Mode de preview : True = "indexé" (own_palette -> banque de preview,
        # rendu in-game), False = "png" (couleurs compressées de own_palette).
        # Défaut = PNG (couleurs propres du sprite, sans banque de preview).
        self._preview_indexed: bool = False
        # (rel_c, rel_r, src_col, src_row, flip_h, flip_v)
        self._brush: list[tuple[int, int, int, int, bool, bool]] = []
        self._hover: Optional[tuple[int, int]]       = None
        self._persist_fn = None
        # Zoom/pan manuel
        self._zoom: int = self.DEFAULT_ZOOM   # 0 = auto-fit, >0 = manuel
        self._pan_x: int = 0
        self._pan_y: int = 0
        self._mid_drag: Optional[tuple] = None   # (start_pos, start_pan_x, start_pan_y)
        # Sélection de tuiles déjà posées (active seulement sans brosse)
        self._select_start: Optional[tuple[int, int]] = None
        self._select_end:   Optional[tuple[int, int]] = None
        self._mouse_pos: Optional[QPointF] = None   # halo de fond, coord. widget
        # Lecture seule : direction miroir. L'édition (peindre/effacer/ramasser)
        # est bloquée ; l'image composée est retournée pour l'affichage (flip).
        self._read_only:  bool = False
        self._flip_disp:  tuple[bool, bool] = (False, False)
        # Image composée mise en cache : compose_frame_image relit le PNG source
        # à chaque appel (I/O disque + recadrage par tuile) — la recalculer à
        # chaque peinture serait déjà coûteux, mais à CHAQUE mouvement de souris
        # (halo de fond) ce serait imperceptible... jusqu'à ce que ça ne le soit
        # plus. Invalidée uniquement quand le contenu affiché change réellement.
        self._composed_pixmap: Optional[QPixmap] = None
        self._checker_cache: tuple[int, QPixmap] = (0, QPixmap())
        self.setMinimumHeight(80)
        self.setMouseTracking(True)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        # Focus au clic — les raccourcis Shift+X/Y sont portés par
        # SpriteCenterPanel (WidgetWithChildrenShortcut) pour marcher aussi
        # bien après un clic dans le tile picker qu'après un clic ici.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    # ── API ──────────────────────────────────────────────────────────

    def load_frame(self, sprite: Optional[SpriteAsset], abs_path: Optional[Path],
                   frame: Optional[AnimFrame]):
        prev_sprite = self._sprite
        prev_dims   = (self._tile_w, self._tile_h)
        self._sprite   = sprite
        self._abs_path = abs_path
        self._frame    = frame
        self._tile_w   = sprite.tile_w if sprite else 1
        self._tile_h   = sprite.tile_h if sprite else 1
        self._src_pixmap = QPixmap(str(abs_path)) if abs_path and abs_path.exists() else None
        # Ne réinitialiser le zoom/pan que si le sprite change (dimensions
        # potentiellement différentes) — sinon la navigation de frames ET la
        # lecture d'animation (load_frame appelé à chaque tick) remettraient
        # un zoom manuel à "fit" à chaque frame.
        if sprite is not prev_sprite or (self._tile_w, self._tile_h) != prev_dims:
            self._zoom = self.DEFAULT_ZOOM; self._pan_x = self._pan_y = 0
        self._recompose()
        self.update()

    def set_brush(self, tiles: list[tuple[int, int]]):
        if not tiles:
            self._brush = []
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            min_c = min(c for c, r in tiles)
            min_r = min(r for c, r in tiles)
            self._brush = [(c - min_c, r - min_r, c, r, False, False) for c, r in tiles]
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def flip_brush_x(self):
        """Miroir horizontal de la brosse active — réarrange les tuiles
        ET retourne le contenu de chaque tuile (flip_h)."""
        if not self._brush:
            return
        max_c = max(rel_c for rel_c, rel_r, sc, sr, fh, fv in self._brush)
        self._brush = [(max_c - rel_c, rel_r, sc, sr, not fh, fv)
                       for rel_c, rel_r, sc, sr, fh, fv in self._brush]
        self.update()

    def flip_brush_y(self):
        """Miroir vertical de la brosse active — réarrange les tuiles
        ET retourne le contenu de chaque tuile (flip_v)."""
        if not self._brush:
            return
        max_r = max(rel_r for rel_c, rel_r, sc, sr, fh, fv in self._brush)
        self._brush = [(rel_c, max_r - rel_r, sc, sr, fh, not fv)
                       for rel_c, rel_r, sc, sr, fh, fv in self._brush]
        self.update()

    def set_persist_fn(self, fn):
        self._persist_fn = fn

    def set_read_only(self, ro: bool):
        """Direction miroir : édition bloquée. On coupe aussi la brosse et le
        curseur repasse en flèche pour signaler qu'on ne peut rien poser."""
        self._read_only = ro
        if ro:
            self._brush = []
            self._select_start = self._select_end = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def set_display_flip(self, flip_h: bool, flip_v: bool):
        """Miroir d'affichage de l'image composée (preview d'une direction
        miroir) — n'affecte pas les tuiles stockées."""
        self._flip_disp = (flip_h, flip_v)
        self._recompose()
        self.update()

    def set_grid(self, on: bool):
        self._show_grid = on
        self.update()

    def set_tint(self, bank_colors: Optional[list[int]]):
        """Banque de preview appliquée à l'image composée via la vraie
        quantification (nearest, comme au build) — pas à la brosse fantôme,
        ni aux pixels sources. None = couleurs sources telles quelles."""
        self._tint_bank = bank_colors
        self._recompose()
        self.update()

    def set_preview_indexed(self, indexed: bool):
        """True = mode 'indexed' (own_palette recoloré par la banque de preview,
        rendu in-game), False = mode 'png' (couleurs compressées de own_palette)."""
        self._preview_indexed = indexed
        self._recompose()
        self.update()

    def set_own_palette(self, own_palette: Optional[list]):
        """Compression du sprite courant (own_palette BGR555). Le rendu dérive de
        ça : mode 'png' l'affiche telle quelle, mode 'indexed' la recolore via la
        banque de preview. [] / None = source brut (pas encore compressé)."""
        self._own_palette = list(own_palette or [])
        self._recompose()
        self.update()

    def _recompose(self):
        """Recalcule l'image composée (lit le PNG source, recadre tuile par
        tuile) et la met en cache — seul point d'appel de compose_frame_image,
        pour que le halo de fond (repeint à chaque mouvement de souris) ne le
        redéclenche jamais."""
        if not self._frame or not self._sprite:
            self._composed_pixmap = None
            return
        img = compose_frame_image(self._abs_path, self._frame,
                                  self._tile_w * 8, self._tile_h * 8)
        # Rendu dérivé du source + own_palette (jamais le PNG modifié) :
        #   mode 'png'     -> couleurs compressées (own_palette telle quelle)
        #   mode 'indexed' -> index de own_palette recolorés par la banque preview
        if self._own_palette:
            from core.models.gba_color import render_indexed, recolor_indexed
            p_img = render_indexed(img, self._own_palette)
            if self._preview_indexed and self._tint_bank:
                img = recolor_indexed(p_img, self._tint_bank)
            else:
                img = p_img.convert("RGBA")
        # Miroir d'affichage (direction miroir en lecture seule).
        if self._flip_disp[0] or self._flip_disp[1]:
            from PIL import Image as _Im
            if self._flip_disp[0]:
                img = img.transpose(_Im.FLIP_LEFT_RIGHT)
            if self._flip_disp[1]:
                img = img.transpose(_Im.FLIP_TOP_BOTTOM)
        if img.width > 0 and img.height > 0:
            data = bytes(img.tobytes("raw", "RGBA"))
            qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
            self._composed_pixmap = QPixmap.fromImage(qi)
        else:
            self._composed_pixmap = None

    def _checker_pattern(self, cs: int) -> QPixmap:
        """Tuile 2×2 cases du damier de transparence, mise en cache par taille
        de case — un QBrush carrelé plutôt qu'un fillRect par case."""
        if self._checker_cache[0] != cs:
            pm = QPixmap(cs * 2, cs * 2)
            pm.fill(QColor(C.CHECKER_A))
            p = QPainter(pm)
            p.fillRect(cs, 0, cs, cs, QColor(C.CHECKER_B))
            p.fillRect(0, cs, cs, cs, QColor(C.CHECKER_B))
            p.end()
            self._checker_cache = (cs, pm)
        return self._checker_cache[1]

    # ── Géométrie ────────────────────────────────────────────────────

    def _auto_zoom(self) -> int:
        w, h = self.width(), self.height()
        pw, ph = max(self._tile_w * 8, 1), max(self._tile_h * 8, 1)
        return max(1, min(w // pw, h // ph))

    # ── Zoom (molette ou boutons du header) ─────────────────────────

    def _adjust_zoom(self, delta: int):
        cur = self._zoom if self._zoom > 0 else self._auto_zoom()
        self._zoom = max(1, min(24, cur + delta))
        if self._zoom == self._auto_zoom():
            self._zoom = 0; self._pan_x = self._pan_y = 0
        self.update()

    def zoom_in(self):
        self._adjust_zoom(1)

    def zoom_out(self):
        self._adjust_zoom(-1)

    def zoom_fit(self):
        self._zoom = 0
        self._pan_x = self._pan_y = 0
        self.update()

    def _geometry(self):
        zoom = self._zoom if self._zoom > 0 else self._auto_zoom()
        pw, ph = self._tile_w * 8, self._tile_h * 8
        dw, dh = pw * zoom, ph * zoom
        ox = (self.width()  - dw) // 2 + self._pan_x
        oy = (self.height() - dh) // 2 + self._pan_y
        return zoom, ox, oy, dw, dh

    def _cell_at(self, pos) -> Optional[tuple[int, int]]:
        zoom, ox, oy, dw, dh = self._geometry()
        x, y = pos.x() - ox, pos.y() - oy
        if x < 0 or y < 0 or x >= dw or y >= dh:
            return None
        return int(x // (8 * zoom)), int(y // (8 * zoom))

    # ── Événements souris ─────────────────────────────────────────────

    def mousePressEvent(self, e):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = (e.pos(), self._pan_x, self._pan_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if not self._frame or not self._sprite or self._read_only:
            return
        cell = self._cell_at(e.position())
        if cell is None:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            if self._brush:
                self._do_paint(*cell)
            else:
                # Pas de brosse active : démarrer une sélection rectangulaire
                # des tuiles déjà posées, pour les ramasser (cf mouseReleaseEvent).
                self._select_start = self._select_end = cell
                self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            self._do_erase(*cell)
            self.selection_reset.emit()

    def mouseMoveEvent(self, e):
        self._mouse_pos = e.position()
        self.update()   # halo de fond : suit le pointeur même sans changer de cellule
        if self._mid_drag and e.buttons() & Qt.MouseButton.MiddleButton:
            sp, spx, spy = self._mid_drag
            self._pan_x = spx + int(e.pos().x() - sp.x())
            self._pan_y = spy + int(e.pos().y() - sp.y())
            self.update(); return
        cell = self._cell_at(e.position())
        if cell != self._hover:
            self._hover = cell
            self.update()
            self.hover_changed.emit(cell)
        if self._read_only:
            return
        if e.buttons() & Qt.MouseButton.LeftButton and cell:
            if self._brush:
                self._do_paint(*cell)
            elif self._select_start is not None:
                self._select_end = cell
                self.update()
        elif e.buttons() & Qt.MouseButton.RightButton and cell:
            self._do_erase(*cell)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = None
            self.setCursor(Qt.CursorShape.CrossCursor if self._brush
                           else Qt.CursorShape.ArrowCursor)
        elif e.button() == Qt.MouseButton.LeftButton and self._select_start is not None:
            self._finish_canvas_selection()

    def leaveEvent(self, e):
        self._hover = None
        self._mouse_pos = None
        self.update()
        self.hover_changed.emit(None)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        self._adjust_zoom(1 if delta > 0 else -1)
        e.accept()

    # ── Peinture / effacement ─────────────────────────────────────────

    def _snapshot(self) -> list:
        return [TilePlacement(t.src_col, t.src_row, t.dst_col, t.dst_row, t.flip_h, t.flip_v)
                for t in self._frame.tiles]

    def _do_paint(self, col: int, row: int):
        if not self._frame or not self._brush:
            return
        old = self._snapshot()
        changed = False
        for rel_c, rel_r, sc, sr, fh, fv in self._brush:
            dc, dr = col + rel_c, row + rel_r
            if not (0 <= dc < self._tile_w and 0 <= dr < self._tile_h):
                continue
            self._frame.tiles = [t for t in self._frame.tiles
                                 if not (t.dst_col == dc and t.dst_row == dr)]
            self._frame.tiles.append(TilePlacement(sc, sr, dc, dr, fh, fv))
            changed = True
        if changed:
            self._recompose()
            self.update()
            self.frame_painted.emit()
            get_history().record(PaintFrameCmd(
                self._frame, old, self._snapshot(), self._persist_fn))

    def _do_erase(self, col: int, row: int):
        if not self._frame:
            return
        old = self._snapshot()
        self._frame.tiles = [t for t in self._frame.tiles
                             if not (t.dst_col == col and t.dst_row == row)]
        if len(self._frame.tiles) != len(old):
            self._recompose()
            self.update()
            self.frame_painted.emit()
            get_history().record(PaintFrameCmd(
                self._frame, old, self._snapshot(), self._persist_fn))

    def _finish_canvas_selection(self):
        """
        Fin de la sélection rectangulaire (aucune brosse active) : ramasse
        les tuiles déjà posées sous le rectangle — les retire du canvas et
        les charge comme brosse, prêtes à être reposées ailleurs sans
        repasser par le tile picker.
        """
        c0, r0 = self._select_start
        c1, r1 = self._select_end
        self._select_start = self._select_end = None
        if not self._frame:
            self.update()
            return
        cmin, cmax = min(c0, c1), max(c0, c1)
        rmin, rmax = min(r0, r1), max(r0, r1)
        picked = [t for t in self._frame.tiles
                  if cmin <= t.dst_col <= cmax and rmin <= t.dst_row <= rmax]
        if not picked:
            self.update()
            return
        old = self._snapshot()
        picked_pos = {(t.dst_col, t.dst_row) for t in picked}
        self._frame.tiles = [t for t in self._frame.tiles
                             if (t.dst_col, t.dst_row) not in picked_pos]
        self._recompose()
        self.frame_painted.emit()
        get_history().record(PaintFrameCmd(
            self._frame, old, self._snapshot(), self._persist_fn))

        self._brush = [(t.dst_col - cmin, t.dst_row - rmin, t.src_col, t.src_row,
                        t.flip_h, t.flip_v) for t in picked]
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.brush_picked_up.emit(len(self._brush))
        self.update()

    # ── Rendu ─────────────────────────────────────────────────────────

    def paintEvent(self, e):
        painter = QPainter(self)

        zoom, ox, oy, dw, dh = self._geometry()
        tile_px = 8 * zoom

        # Fond du canvas : même grille + halo au survol que le Font Editor,
        # au pas d'une tuile GBA (8 px, cadré sur l'origine de l'image).
        painter.fillRect(self.rect(), QColor(C.BG_DEEP))
        draw_grid(painter, QRectF(self.rect()), tile_px, QPointF(ox, oy), tiled=True)
        draw_grid_halo(painter, QRectF(self.rect()), tile_px, self._mouse_pos, QPointF(ox, oy))

        if not self._frame or not self._sprite:
            painter.setPen(QColor(C.TEXT_MUTED))
            painter.setFont(QFont(T.UI, T.MD))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             label("sprframe.select_frame"))
            painter.end()
            return

        # Damier transparence — motif carrelé via QBrush (une seule passe),
        # plutôt qu'un fillRect par case : la boucle Python redevenait le coût
        # dominant du halo de fond, repeint à chaque mouvement de souris.
        cs = max(4, zoom * 2)
        painter.save()
        painter.setBrushOrigin(ox, oy)
        painter.fillRect(QRect(ox, oy, dw, dh), QBrush(self._checker_pattern(cs)))
        painter.restore()

        # Image composée — mise en cache par _recompose(), jamais recalculée ici
        # (sinon chaque mouvement de souris relirait le PNG source pour le halo).
        if self._composed_pixmap is not None:
            painter.drawPixmap(QRect(ox, oy, dw, dh), self._composed_pixmap)

        # Grille 8×8
        if self._show_grid:
            painter.setPen(QPen(QColor(255, 255, 255, 35), 1))
            x = ox
            while x <= ox + dw:
                painter.drawLine(x, oy, x, oy + dh); x += tile_px
            y = oy
            while y <= oy + dh:
                painter.drawLine(ox, y, ox + dw, y); y += tile_px

        # Ghost preview de la brosse
        if self._hover and self._brush and self._src_pixmap:
            hc, hr = self._hover
            painter.setOpacity(0.55)
            for rel_c, rel_r, sc, sr, fh, fv in self._brush:
                dc, dr = hc + rel_c, hr + rel_r
                if not (0 <= dc < self._tile_w and 0 <= dr < self._tile_h):
                    continue
                dest = QRect(ox + dc * tile_px, oy + dr * tile_px, tile_px, tile_px)
                src = QRect(sc * 8, sr * 8, 8, 8)
                if fh or fv:
                    painter.save()
                    cx, cy = dest.center().x(), dest.center().y()
                    painter.translate(cx, cy)
                    painter.scale(-1 if fh else 1, -1 if fv else 1)
                    painter.translate(-cx, -cy)
                    painter.drawPixmap(dest, self._src_pixmap, src)
                    painter.restore()
                else:
                    painter.drawPixmap(dest, self._src_pixmap, src)
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(C.ACCENT), 2))
            painter.drawRect(QRect(ox + hc * tile_px, oy + hr * tile_px, tile_px, tile_px))
        elif self._hover:
            painter.setPen(QPen(QColor(C.TEXT_DIM), 1, Qt.PenStyle.DashLine))
            painter.drawRect(QRect(ox + self._hover[0] * tile_px,
                                   oy + self._hover[1] * tile_px, tile_px, tile_px))

        # Sélection en cours (ramassage de tuiles déjà posées, sans brosse)
        if self._select_start is not None and self._select_end is not None:
            c0, r0 = self._select_start
            c1, r1 = self._select_end
            cmin, cmax = min(c0, c1), max(c0, c1)
            rmin, rmax = min(r0, r1), max(r0, r1)
            rect = QRect(ox + cmin * tile_px, oy + rmin * tile_px,
                         (cmax - cmin + 1) * tile_px, (rmax - rmin + 1) * tile_px)
            fill_color = QColor(C.ACCENT_COOL)
            fill_color.setAlpha(64)
            painter.fillRect(rect, fill_color)
            painter.setPen(QPen(QColor(C.ACCENT_COOL), 2))
            painter.drawRect(rect)

        # Indicateur de zoom manuel
        if self._zoom > 0:
            painter.setPen(QColor(C.TEXT_DIM))
            painter.setFont(QFont(T.MONO, T.XS))
            painter.drawText(6, self.height() - 6, f"{self._zoom}×")

        painter.end()


class _CanvasFloatingToolbar(QFrame):
    """
    Barre d'outils flottante et déplaçable superposée au canvas — même
    modèle que FloatingToolbar/CanvasContainer du Scene Manager
    (core/scene_editor.py), en horizontal : playback (|◀ ▶ ▶|), grille,
    palettes de preview, flip brosse (X/Y), zoom (Fit/−/+).
    """

    def __init__(self, canvas: "_FrameCanvas", parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._dragging = False
        self._drag_offset = QPoint()

        self.setStyleSheet(
            f"_CanvasFloatingToolbar{{background:{C.BG_RAISED};border:1px solid {C.BORDER};border-radius:8px;}}"
            "QToolButton{border:none;background:transparent;border-radius:4px;}"
            f"QToolButton:hover{{background:{C.BG_HOVER};}}"
            f"QToolButton:checked{{background:{C.BG_SEL};border:1px solid {C.ACCENT};}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 6, 6)
        layout.setSpacing(4)

        from ui.common.widgets import DragHandle
        layout.addWidget(DragHandle(Qt.Orientation.Horizontal))

        def _sep():
            s = QFrame()
            s.setFrameShape(QFrame.Shape.VLine)
            s.setStyleSheet(f"color:{C.BORDER};margin:2px 6px;")
            layout.addWidget(s)

        def _icon_btn(icon_key: str, tip: str, checkable: bool = False) -> QToolButton:
            b = QToolButton()
            b.setIcon(_ico(icon_key, C.TEXT_DIM, C.ACCENT))
            b.setIconSize(QSize(22, 22))
            b.setFixedSize(36, 36)
            b.setCheckable(checkable)
            b.setToolTip(tip)
            layout.addWidget(b)
            return b

        self.btn_prev = _icon_btn("playback_prev", label("sprframe.first_frame"))
        self.btn_play = _icon_btn("playback_play", label("sprframe.play"), checkable=True)
        self.btn_next = _icon_btn("playback_next", label("sprframe.last_frame"))
        _sep()
        self.btn_grid = _icon_btn("playback_grid", label("sprframe.show_grid"), checkable=True)
        _sep()
        # Mode de preview : couleurs natives du PNG vs quantifiées sur la
        # banque (rendu WYSIWYG in-game) — paire mutuellement exclusive.
        _MODE_BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:transparent;border:none;"
            f"font-size:{T.SM}px;padding:0 8px;font-weight:bold;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
            f"QToolButton:checked{{color:{C.ACCENT};background:{C.BG_SEL};"
            f"border:1px solid {C.ACCENT};border-radius:4px;}}"
        )
        self.btn_original = QToolButton(); self.btn_original.setText("PNG")
        self.btn_original.setToolTip(label("sprframe.preview_png_tip"))
        self.btn_indexed = QToolButton(); self.btn_indexed.setText(label("sprframe.indexed"))
        self.btn_indexed.setToolTip(label("sprframe.preview_indexed_tip"))
        for b in (self.btn_original, self.btn_indexed):
            b.setStyleSheet(_MODE_BTN)
            b.setCheckable(True)
            b.setFixedHeight(36)
            layout.addWidget(b)
        self.btn_original.setChecked(True)   # défaut = PNG (couleurs propres)
        self.btn_original.clicked.connect(lambda: self._set_preview_indexed(False))
        self.btn_indexed.clicked.connect(lambda: self._set_preview_indexed(True))
        _sep()
        self.btn_flip_x = _icon_btn("mirror_h", label("sprframe.flip_x_tip"))
        self.btn_flip_y = _icon_btn("mirror_v", label("sprframe.flip_y_tip"))
        _sep()

        _TXT_BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:transparent;border:none;"
            f"font-size:{T.LG}px;padding:0 8px;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
        )
        self.btn_fit = QToolButton(); self.btn_fit.setText(label("sprframe.fit"))
        self.btn_zm  = QToolButton(); self.btn_zm.setText("−")
        self.btn_zp  = QToolButton(); self.btn_zp.setText("+")
        for b in (self.btn_fit, self.btn_zm, self.btn_zp):
            b.setStyleSheet(_TXT_BTN)
            b.setFixedHeight(36)
            b.setToolTip(label("sprframe.fit_tip") if b is self.btn_fit else "")
            layout.addWidget(b)

        # Grille + flip/zoom pilotent directement le canvas (pas d'état
        # externe à coordonner) ; play + palette restent exposés pour être
        # câblés par SpriteCenterPanel (timer d'animation, dropdown palette).
        self.btn_grid.setChecked(True)
        self.btn_grid.toggled.connect(self._canvas.set_grid)
        self.btn_flip_x.clicked.connect(self._canvas.flip_brush_x)
        self.btn_flip_y.clicked.connect(self._canvas.flip_brush_y)
        self.btn_fit.clicked.connect(self._canvas.zoom_fit)
        self.btn_zm.clicked.connect(self._canvas.zoom_out)
        self.btn_zp.clicked.connect(self._canvas.zoom_in)

        self.adjustSize()

    def _set_preview_indexed(self, indexed: bool):
        # Exclusivité mutuelle (checkable sans QButtonGroup pour rester dans
        # le même conteneur de layout que les autres boutons de la barre).
        self.btn_indexed.setChecked(indexed)
        self.btn_original.setChecked(not indexed)
        self._canvas.set_preview_indexed(indexed)

    # ── Drag (identique à FloatingToolbar, core/scene_editor.py) ───────

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


class _FrameCanvasPanel(QWidget):
    """
    Enrobe _FrameCanvas avec une barre d'outils flottante
    (_CanvasFloatingToolbar) et des textes flottants (tag CANVAS, stats
    Tiles/Unique, coordonnées survolées) superposés au canvas — même modèle
    que CanvasContainer/FloatingToolbar du Scene Manager.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.canvas = _FrameCanvas()
        self.canvas.hover_changed.connect(self._on_hover_changed)
        root.addWidget(self.canvas, 1)

        # Bandeau flottant de sélection de palette (bas-centre, même widget que
        # Scene Manager/Background Editor — cf. palette_bank_strip) : les
        # sous-palettes de la PAL_BANK du sprite (SpriteCenterPanel.load_sprite),
        # clic = palette active pour le mode « Indexé ». Masqué si aucune palette.
        self.paint_strip = PaletteBankStrip(label("common.no_palette"), self)
        self.paint_strip.setVisible(False)
        self.paint_strip.raise_()

        self.toolbar = _CanvasFloatingToolbar(self.canvas, self)
        self.toolbar.move(10, 10)
        self.toolbar.raise_()

        _FLOAT_STY = f"color:{C.TEXT_MUTED};background:transparent;"
        self._tag_lbl = QLabel(label("sprframe.canvas_tag"), self)
        self._tag_lbl.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        self._tag_lbl.setStyleSheet(_FLOAT_STY + "letter-spacing:1px;")
        self._tag_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tag_lbl.adjustSize()

        self._info_lbl = QLabel("", self)
        self._info_lbl.setFont(QFont(T.MONO, T.XS))
        self._info_lbl.setStyleSheet(_FLOAT_STY)
        self._info_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._coord_lbl = QLabel("", self)
        self._coord_lbl.setFont(QFont(T.MONO, T.XS))
        self._coord_lbl.setStyleSheet(_FLOAT_STY)
        self._coord_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Bandeau miroir / lecture seule — visible seulement pour une direction
        # miroir (mirror_of défini) : signale que le contenu n'est pas éditable.
        self._ro_lbl = QLabel("", self)
        self._ro_lbl.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        self._ro_lbl.setStyleSheet(
            f"color:{C.ACCENT_COOL};background:{tint(C.ACCENT_COOL, 0.15)};"
            f"border:1px solid {C.ACCENT_COOL};border-radius:4px;padding:3px 8px;"
        )
        self._ro_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ro_lbl.hide()

        self._reposition_overlays()

    def set_read_only_banner(self, text: Optional[str]):
        """Affiche/masque le bandeau miroir. text=None → masqué."""
        if text:
            self._ro_lbl.setText(text)
            self._ro_lbl.adjustSize()
            self._ro_lbl.show()
        else:
            self._ro_lbl.hide()
        self._reposition_overlays()

    def set_info(self, tiles: int, unique: int):
        self._info_lbl.setText(label("sprframe.info", tiles=tiles, unique=unique))
        self._info_lbl.adjustSize()
        self._reposition_overlays()

    def _on_hover_changed(self, cell):
        self._coord_lbl.setText(label("sprframe.coord", c=cell[0], r=cell[1]) if cell else "")
        self._coord_lbl.adjustSize()
        self._reposition_overlays()

    def _reposition_overlays(self):
        self._tag_lbl.move(10, self.height() - self._tag_lbl.height() - 8)
        self._coord_lbl.move(self.width() - self._coord_lbl.width() - 10,
                             self.height() - self._coord_lbl.height() - 8)
        self._info_lbl.move(self.width() - self._info_lbl.width() - 10, 8)
        self._ro_lbl.move((self.width() - self._ro_lbl.width()) // 2, 8)
        self._position_paint_strip()

    def _position_paint_strip(self):
        strip = self.paint_strip
        strip.reflow()
        x = max(0, (self.width() - strip.width()) // 2)
        y = max(0, self.height() - strip.height() - 12)
        strip.move(x, y)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        tb = self.toolbar
        x = max(0, min(tb.x(), self.width() - tb.width()))
        y = max(0, min(tb.y(), self.height() - tb.height()))
        tb.move(x, y)
        tb.raise_()
        self._reposition_overlays()
        if self.paint_strip.isVisible():
            self.paint_strip.raise_()

