"""ui/sound_mixer/order_strip.py — la structure musicale d'une piste, avec ses sections.

Un module : une cellule par POSITION de la table BRUTE — celle que la ROM numérote (cf.
engine_emulation/module_model.ORDER_SKIP) — et non par pattern : une section vise une position, et
c'est ce numéro-là que l'auteur lit ici et qui sort au build. Un séparateur ou une fin (`254` / `255`)
occupe sa cellule, grisée, et ne se sélectionne pas.

Un WAV n'a pas d'ordres : sa bande n'a qu'UNE cellule, sur toute la durée, et ses sections s'y placent à la
milliseconde. Même bande, même geste, deux unités.

On y glisse (module) pour choisir une plage ; un clic sur le nom d'une section la sélectionne en entier,
son ▶ l'écoute. Chaque section porte son nom et sa durée.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from core.engine_emulation.module_model import is_pattern_order
from core.music_structure import MIN_SECTION_MS
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.tooltip import tooltip
from ui.sound_mixer.section_colors import section_color

_RULER = 16
_BAND = 20
_CELL = 28
_PLAY_W = 16          # la zone du ▶, au début du nom d'une section
_EDGE_GRAB = 6         # largeur de prise des deux poignées d'une section
_EDGE_INSET = 4        # le ▶ commence à cette distance du bord gauche : en deçà, la poignée de bord l'emporte


class OrderStrip(QWidget):
    selection_changed = pyqtSignal(int, int)     # [début, fin) ; (0, 0) = rien
    section_clicked = pyqtSignal(str)
    section_preview = pyqtSignal(object)         # la `MusicSection` dont on a cliqué le ▶
    section_range_moving = pyqtSignal(object, int, int)
    section_range_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lane_of: dict[int, int] = {}
        self._lane_count = 1
        self._update_height()
        self.setMouseTracking(True)
        self._table: list = []
        self._sections: list = []
        self._playhead = -1
        self._playhead_ms = -1.0
        self._extent_ms = 0                      # > 0 : un WAV, dont la cellule unique dure autant
        self._seconds_of = None                  # (début, fin) → secondes, pour la durée affichée
        self._selection = (0, 0)
        self._anchor: int | None = None
        self._drag_section = None
        self._drag_edge: str | None = None

    # ── Ce qu'on lui donne ────────────────────────────────────────

    def set_orders(self, table: list) -> None:
        self._table = list(table)
        self._extent_ms = 0
        self._selection = (0, 0)
        self.update()

    def set_timeline(self, duration_ms: int) -> None:
        """Un WAV : une seule cellule, sur toute sa durée."""
        self._table = [0]
        self._extent_ms = int(duration_ms)
        self._selection = (0, 0)
        self.update()

    def set_seconds_provider(self, seconds_of) -> None:
        """`seconds_of(début, fin)` : la durée d'une plage dans l'unité de la piste (None : pas de durée)."""
        self._seconds_of = seconds_of
        self.update()

    def set_sections(self, sections: list) -> None:
        self._sections = list(sections)
        self._layout_lanes()
        self.update()

    def set_playhead_order(self, order: int) -> None:
        if order != self._playhead:
            self._playhead = order
            self.update()

    def set_playhead_ms(self, ms: float) -> None:
        if ms != self._playhead_ms:
            self._playhead_ms = ms
            self.update()

    def selection(self) -> tuple:
        return self._selection

    def clear_selection(self) -> None:
        self._set_selection(0, 0)

    def _set_selection(self, start: int, end: int) -> None:
        if (start, end) != self._selection:
            self._selection = (start, end)
            self.selection_changed.emit(start, end)
            self.update()

    # ── Géométrie ─────────────────────────────────────────────────

    @property
    def _timed(self) -> bool:
        return self._extent_ms > 0

    @property
    def _extent(self) -> int:
        """L'étendue de la piste dans son unité : des ordres, ou des millisecondes."""
        return self._extent_ms or len(self._table)

    def _cell_width(self) -> float:
        return (self.width() - 2) / len(self._table) if self._table else 0.0

    def _x(self, position: float) -> float:
        """L'abscisse d'une position : un ordre, ou une milliseconde pour un WAV."""
        if self._timed:
            return 1 + position / self._extent_ms * (self.width() - 2)
        return 1 + position * self._cell_width()

    def _index_at(self, x: float) -> int:
        n = len(self._table)
        return max(0, min(n - 1, int((x - 1) / self._cell_width()))) if n else -1

    def _position_at(self, x: float) -> int:
        if self._timed:
            return int((x - 1) / max(1, self.width() - 2) * self._extent_ms)
        return self._index_at(x)

    def _cell_rect(self, i: int) -> QRectF:
        cw = self._cell_width()
        return QRectF(1 + i * cw, self._cells_top(), cw, _CELL)

    def _cells_top(self) -> int:
        return _RULER + self._lane_count * _BAND + 2

    def _bands_bottom(self) -> int:
        return _RULER + self._lane_count * _BAND

    def _update_height(self) -> None:
        self.setFixedHeight(self._cells_top() + _CELL + 6)

    def _layout_lanes(self) -> None:
        """Empile uniquement les sections qui se recouvrent.

        Les recouvrements restent valides : une section peut servir de variante
        ou de boucle alternative. Les placer sur des lignes distinctes évite
        qu'une poignée ou un libellé en masque un autre.
        """
        ends: list[int] = []
        self._lane_of.clear()
        for section in sorted(self._sections, key=lambda s: (s.start, s.end, s.name)):
            lane = next((i for i, end in enumerate(ends) if end <= section.start), len(ends))
            if lane == len(ends):
                ends.append(section.end)
            else:
                ends[lane] = section.end
            self._lane_of[id(section)] = lane
        lanes = max(1, len(ends))
        if lanes != self._lane_count:
            self._lane_count = lanes
            self._update_height()

    def _band_of(self, section) -> QRectF | None:
        start, end = max(0, section.start), min(self._extent, section.end)
        if end <= start:
            return None
        lane = self._lane_of.get(id(section), 0)
        return QRectF(self._x(start), _RULER + lane * _BAND,
                      self._x(end) - self._x(start) - 1, _BAND - 2)

    def _section_at(self, x: float, y: float):
        point = QPointF(x, y)
        return next((s for s in reversed(self._sections)
                     if (band := self._band_of(s)) is not None and band.contains(point)), None)

    def _edge_at(self, section, x: float) -> str | None:
        band = self._band_of(section)
        if band is None:
            return None
        if abs(x - band.left()) <= _EDGE_GRAB:
            return "start"
        if abs(x - band.right()) <= _EDGE_GRAB:
            return "end"
        return None

    def _play_hit(self, section, x: float) -> bool:
        band = self._band_of(section)
        return band is not None and band.width() >= 3 * _PLAY_W and band.left() + _EDGE_INSET <= x < band.left() + _PLAY_W

    def _boundary_at(self, x: float) -> int:
        """Borne la plus proche, y compris la fin de la table d'ordres."""
        if self._timed:
            return max(0, min(self._extent, self._position_at(x)))
        return max(0, min(self._extent, round((x - 1) / max(1.0, self._cell_width()))))

    # ── La souris ─────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self._table:
            return
        x = e.position().x()
        if e.position().y() < self._bands_bottom():               # la bande des noms
            hit = self._section_at(x, e.position().y())
            if hit is None:                                       # le vide : plus de sélection, la lecture est libre
                self._selection = (0, 0)
                self.selection_changed.emit(0, 0)                 # toujours dit : la section choisie peut survivre à un (0, 0) silencieux
                self.update()
                return
            if self._play_hit(hit, x):
                self.section_preview.emit(hit)
                return
            edge = self._edge_at(hit, x)
            if edge is not None:
                self._drag_section, self._drag_edge = hit, edge
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                return
            self._set_selection(hit.start, min(hit.end, self._extent))
            self.section_clicked.emit(hit.name)
            return
        if self._timed:                                           # pas d'ordres à choisir dans un WAV
            return
        i = self._index_at(x)
        if not is_pattern_order(self._table[i]):
            return
        self._anchor = i
        self._set_selection(i, i + 1)

    def mouseMoveEvent(self, e):
        if self._drag_section is not None:
            section = self._drag_section
            position = self._boundary_at(e.position().x())
            shortest = MIN_SECTION_MS if self._timed else 1          # une section d'un WAV ne peut pas être plus courte
            if self._drag_edge == "start":
                start, end = min(position, section.end - shortest), section.end
            else:
                start, end = section.start, max(position, section.start + shortest)
            self.section_range_moving.emit(section, start, end)
            return
        if self._anchor is None:
            x = e.position().x()
            hit = self._section_at(x, e.position().y()) if self._table and e.position().y() < self._bands_bottom() else None
            play = hit is not None and self._play_hit(hit, x)
            edge = self._edge_at(hit, x) if hit is not None and not play else None
            self.setCursor(Qt.CursorShape.SizeHorCursor if edge else
                           Qt.CursorShape.PointingHandCursor if play else Qt.CursorShape.ArrowCursor)
            self.setToolTip(tooltip(title=label("sndedit.preview_section"), body=label("sndedit.preview_section_tip"))
                            if play else "")
            return
        i = self._index_at(e.position().x())
        lo, hi = min(self._anchor, i), max(self._anchor, i)
        self._set_selection(lo, hi + 1)

    def mouseReleaseEvent(self, _e):
        if self._drag_section is not None:
            self._drag_section = self._drag_edge = None
            self.section_range_changed.emit()
        self._anchor = None

    # ── Le dessin ─────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.BG_BASE))
        n = len(self._table)
        if not n:
            return
        cw = self._cell_width()
        p.setFont(QFont(T.MONO, T.XS))
        every = max(1, int(26 / cw) + (1 if cw < 26 else 0))      # une étiquette tous les `every`
        for i, entry in enumerate(self._table):
            rect = self._cell_rect(i)
            if i % every == 0 and not self._timed:
                p.setPen(QPen(QColor(C.TEXT_DIM)))
                p.drawText(QPointF(rect.left() + 3, _RULER - 4), f"{i:02d}")
            self._paint_cell(p, rect, is_pattern_order(entry))
        for rank, section in enumerate(self._sections):
            self._paint_section(p, rank, section)
        self._paint_selection_and_playhead(p)

    def _paint_cell(self, p: QPainter, rect: QRectF, is_pattern: bool) -> None:
        p.fillRect(rect.adjusted(0, 0, -1, 0), QColor(C.BG_INPUT if is_pattern else C.BG_DEEP))
        p.setPen(QPen(QColor(C.BORDER_MID)))
        p.drawRect(rect.adjusted(0, 0, -1, 0))
        if not is_pattern:                                         # marqueur : hachuré
            p.drawLine(rect.bottomLeft(), rect.topRight())

    def _duration_text(self, section) -> str:
        if self._seconds_of is None:
            return ""
        seconds = self._seconds_of(section.start, section.end)
        whole = round(seconds)                                      # des secondes entières, jamais de virgule
        return f"{whole // 60}:{whole % 60:02d}"

    def _paint_section(self, p: QPainter, rank: int, section) -> None:
        band = self._band_of(section)
        if band is None:
            return
        start, end = max(0, section.start), min(self._extent, section.end)
        color = section_color(section, rank)
        fill = QColor(color); fill.setAlpha(80)
        left, right = self._x(start), self._x(end)
        p.fillRect(QRectF(left + 1, self._cells_top() + 1, right - left - 3, _CELL - 2), fill)
        solid = QColor(color); solid.setAlpha(60)
        p.fillRect(band, solid)
        p.setPen(QPen(color, 1))
        p.drawRect(band)
        p.setPen(QPen(QColor(C.TEXT_HI)))
        text_left = band.left() + 4
        if band.width() >= 3 * _PLAY_W:                           # le ▶, tant que la bande a la place de le porter
            cy, x0 = band.center().y(), band.left() + 5
            p.setBrush(QColor(C.TEXT_HI))
            p.drawPolygon(QPolygonF([QPointF(x0, cy - 4), QPointF(x0, cy + 4), QPointF(x0 + 7, cy)]))
            p.setBrush(Qt.BrushStyle.NoBrush)
            text_left = band.left() + _PLAY_W
        duration = self._duration_text(section)
        text = f"{section.name} · {duration}" if duration else section.name
        room = max(0, int(band.right() - text_left - 3))
        p.drawText(QRectF(text_left, band.top(), room, band.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, room))

    def _paint_selection_and_playhead(self, p: QPainter) -> None:
        lo, hi = self._selection
        if hi > lo and not self._timed:
            first, last = self._cell_rect(lo), self._cell_rect(hi - 1)
            p.setPen(QPen(QColor(C.ACCENT), 2, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(first.left(), first.top(), last.right() - first.left() - 1, _CELL))
        if self._timed:
            if self._playhead_ms >= 0:
                x = self._x(min(self._playhead_ms, self._extent_ms))
                p.setPen(QPen(QColor(C.ACCENT_WARM), 2))
                p.drawLine(QPointF(x, self._cells_top()), QPointF(x, self._cells_top() + _CELL))
        elif 0 <= self._playhead < len(self._table):
            r = self._cell_rect(self._playhead)
            p.setPen(QPen(QColor(C.ACCENT_WARM), 2))
            p.drawRect(r.adjusted(1, 1, -2, -1))
