"""
ui/sprite_editor/sprite_timeline.py — la timeline : les frames de la direction courante,
en vignettes (sélection, glisser pour réordonner, actions au clic droit).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton,
    QFrame, QScrollArea, QMenu, QApplication, QWidgetAction, QLineEdit,
)
from PyQt6.QtGui import (
    QFont, QColor, QPixmap, QImage, QDrag, QPainter, QPen, QKeySequence, QShortcut,
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint

from ui.common.theme import C, T, QSS
from ui.common.labels import label
from ui.common.tooltip import tooltip
from core.models.sprite import AnimFrame, AnimState, SpriteAsset, StateDirection
from core.sprite_compose import compose_frame_image
from core.keybindings import bind

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


def make_frame_pixmap(abs_path: Optional[Path], frame: AnimFrame,
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


class TimelineFrame(QFrame):
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
        self.setToolTip(tooltip(
            title=label("sprframe.frame_n", n=self._index + 1),
            body=label("sprframe.frame_tip"),
            note="\n".join(p[1] for p in parts),
        ))

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


class SpriteTimeline(QWidget):
    """
    Bande horizontale de frames avec :
    - clic → sélection ; Ctrl+clic → ajoute/retire ; Maj+clic → plage
    - drag-drop → réordonnancement
    - clic droit → copy / clone / clear / delete (sur toute la sélection)
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
        self._selected:  int                       = 0   # frame affichée au canvas
        self._sel:       set[int]                  = {0}  # multi-sélection (contient _selected)
        self._thumbs:    list[TimelineFrame]         = []
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
        hdr = QLabel(label("sprframe.timeline_title"))
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
        self._add_btn.setToolTip(tooltip(
            title=label("sprframe.add_frame"), body=label("sprframe.add_frame_tip")
        ))
        self._add_btn.clicked.connect(self._on_add)

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, 1)

        # Raccourcis : n'agissent que quand la timeline (ou un enfant) a le focus.
        dup = QShortcut(QKeySequence(), self)
        dup.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        dup.activated.connect(lambda: self._copy_frames(self._selected_indices()))
        bind("common.duplicate", dup)
        delete = QShortcut(QKeySequence(), self)
        delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        delete.activated.connect(lambda: self._delete_frames(self._selected_indices()))
        bind("common.delete", delete)

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
        self._sel        = {0}
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
                pm  = make_frame_pixmap(self._abs_path, frame, fw, fh, flip=self._flip)
                t   = TimelineFrame(i, frame, pm)
                t.set_selected(i in self._sel)
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
        self._select_many({index}, index)

    def _select_many(self, indices, primary: int):
        """Sélection multiple ; `primary` est la frame montrée au canvas."""
        if not self._sd:
            return
        count = len(self._frames())
        chosen = {i for i in indices if 0 <= i < count}
        if not chosen:
            return
        self._sel = chosen
        self._selected = primary if primary in chosen else min(chosen)
        for i, t in enumerate(self._thumbs):
            t.set_selected(i in chosen)
        self.frame_selected.emit(self._selected)

    def _selected_indices(self) -> list[int]:
        count = len(self._sd.frames) if self._sd else 0
        return sorted(i for i in self._sel if 0 <= i < count)

    def refresh_thumb(self, index: int, pixmap: QPixmap):
        """Met à jour l'image d'une vignette sans changer la sélection (après peinture)."""
        if 0 <= index < len(self._thumbs):
            self._thumbs[index].update_pixmap(pixmap)

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_thumb_clicked(self, index: int):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        mods = QApplication.keyboardModifiers()
        if mods & Qt.KeyboardModifier.ShiftModifier:
            lo, hi = sorted((self._selected, index))
            self._select_many(range(lo, hi + 1), index)
        elif mods & Qt.KeyboardModifier.ControlModifier:
            if index in self._sel:
                if len(self._sel) > 1:
                    rest = self._sel - {index}
                    self._select_many(rest, max(rest))
            else:
                self._select_many(self._sel | {index}, index)
        else:
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
        # Clic droit hors sélection : la vignette visée devient la sélection.
        if index not in self._sel:
            self._select(index)
        targets = self._selected_indices()
        multi = len(targets) > 1
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        copy_a  = menu.addAction(label("sprframe.menu_copy"))
        clone_a = menu.addAction(label("sprframe.menu_clone"))
        clear_a = menu.addAction(label("sprframe.menu_clear"))

        # Déclencheurs : propres à une frame, absents en multi-sélection.
        if not multi:
            menu.addSeparator()
            self._build_frame_trigger_menus(menu, index)

        menu.addSeparator()
        del_a   = menu.addAction(label("sprframe.menu_delete"))      # Delete en dernier, comme partout
        del_a.setEnabled(len(self._sd.frames) > len(targets))

        act = menu.exec(pos)
        if act == copy_a:
            self._copy_frames(targets)
        elif act == clone_a:
            self._clone_frames_to_end(targets)
        elif act == clear_a:
            self._clear_frames(targets)
        elif act == del_a:
            self._delete_frames(targets)

    def _build_frame_trigger_menus(self, menu: QMenu, index: int):
        frame = self._sd.frames[index]
        self._build_trigger_menu(menu, label("sprframe.play_action"), frame.action_name,
                                 self._sound_action_names(), index, "action_name")
        self._build_trigger_menu(menu, label("sprframe.play_sfx"), frame.direct_sfx_name,
                                 self._sfx_names(), index, "direct_sfx_name")
        self._build_event_call_menu(menu, frame.event_name, index)

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

    def _editable(self, indices: list[int]) -> bool:
        return bool(self._sd and not self._read_only and indices)

    def _copy_frames(self, indices: list[int]):
        """Insère les copies en bloc juste après la dernière frame copiée."""
        if not self._editable(indices):
            return
        at = indices[-1] + 1
        self._sd.frames[at:at] = [self._sd.frames[i].clone() for i in indices]
        self.frames_changed.emit()
        self._rebuild()
        self._select_many(range(at, at + len(indices)), at)

    def _clone_frames_to_end(self, indices: list[int]):
        if not self._editable(indices):
            return
        start = len(self._sd.frames)
        self._sd.frames.extend(self._sd.frames[i].clone() for i in indices)
        self.frames_changed.emit()
        self._rebuild()
        self._select_many(range(start, start + len(indices)), start)

    def _clear_frames(self, indices: list[int]):
        if not self._editable(indices):
            return
        for i in indices:
            self._sd.frames[i].tiles.clear()
        self.frames_changed.emit()
        self._rebuild()
        self._select_many(indices, indices[0])

    def _delete_frames(self, indices: list[int]):
        """Supprime les frames ; une direction garde toujours au moins une frame."""
        if not self._editable(indices) or len(indices) >= len(self._sd.frames):
            return
        for i in reversed(indices):
            self._sd.frames.pop(i)
        self.frames_changed.emit()
        self._rebuild()
        self._select(min(indices[0], len(self._sd.frames) - 1))

    # ── Drag-drop reorder ─────────────────────────────────────────────

    def _drag_enter(self, e):
        if not self._read_only and e.mimeData().hasFormat(TimelineFrame.MIME):
            e.acceptProposedAction()

    def _drag_move(self, e):
        if not e.mimeData().hasFormat(TimelineFrame.MIME):
            return
        self._drop_before = self._drop_index(e.position().toPoint().x())
        self._content.update()
        e.acceptProposedAction()

    def _drag_leave(self, e):
        self._drop_before = None
        self._content.update()

    def _drop(self, e):
        if self._read_only or not e.mimeData().hasFormat(TimelineFrame.MIME) or not self._sd:
            return
        src_idx  = int(e.mimeData().data(TimelineFrame.MIME).data())
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
