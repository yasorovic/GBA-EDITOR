"""ui/sound_mixer/order_strip.py — la structure musicale d'une piste, avec ses sections.

Un module : une cellule par POSITION de la table BRUTE — celle que la ROM numérote (cf.
engine_emulation/module_model.ORDER_SKIP) — et non par pattern : une section vise une position, et
c'est ce numéro-là que l'auteur lit ici et qui sort au build. Un séparateur ou une fin (`254` / `255`)
occupe sa cellule, grisée, et ne se sélectionne pas.

Un WAV n'a pas d'ordres : sa bande n'a qu'UNE cellule, sur toute la durée, et ses sections s'y placent à la
milliseconde. Même bande, même geste, deux unités.

On y glisse (module) pour choisir une plage ; un clic sur le nom d'une section la sélectionne en entier,
son ▶ l'écoute. Chaque section porte son nom et sa durée.

Au-dessus des sections, une voie porte les REPÈRES de la musique : un drapeau par son à déclencher, planté à la
position où la lecture le joue. On le saisit pour le déplacer ; le clic droit (sur un drapeau, ou dans le vide pour
en poser un) ne construit rien ici : la bande dit seulement OÙ, et l'éditeur — qui connaît le projet — dit QUOI.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from core.engine_emulation.module_model import is_pattern_order
from core.models.audio import CUE_JINGLE, CUE_JINGLE_ACTION, CUE_SFX, CUE_SOUND_ACTION
from core.music_structure import MIN_SECTION_MS
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.tooltip import tooltip
from ui.sound_mixer.section_colors import section_color

_RULER = 16
_CUE_LANE = 18        # la voie des repères, entre la règle et les sections
_BAND = 20
_CELL = 28
_LEAD_W = 14           # la largeur d'une case d'amorce : réduite, et barrée
_PLAY_W = 16          # la zone du ▶, au début du nom d'une section
_EDGE_GRAB = 6         # largeur de prise des deux poignées d'une section
_EDGE_INSET = 4        # le ▶ commence à cette distance du bord gauche : en deçà, la poignée de bord l'emporte

# Le drapeau d'un repère se lit sans légende : l'ICÔNE dit la famille (haut-parleur = un effet, note = un jingle), la couleur la
# redit, et une pastille en coin dit que le son passe par une BOÎTE (une action : l'état de la boîte choisit lequel).
_CUE_FLAG_W = 22
_CUE_IS_JINGLE = (CUE_JINGLE, CUE_JINGLE_ACTION)
_CUE_VIA_BOX = (CUE_SOUND_ACTION, CUE_JINGLE_ACTION)


class OrderStrip(QWidget):
    selection_changed = pyqtSignal(int, int)     # [début, fin) ; (0, 0) = rien
    section_clicked = pyqtSignal(str)
    section_preview = pyqtSignal(object)         # la `MusicSection` dont on a cliqué le ▶
    section_range_moving = pyqtSignal(object, int, int)
    section_range_changed = pyqtSignal()
    cue_context_requested = pyqtSignal(object, int, object)   # (le repère visé ou None, la position, où ouvrir le menu)
    cue_moving = pyqtSignal(object, int)                      # (le repère, sa nouvelle position) pendant le glisser
    cue_moved = pyqtSignal()                                  # le drapeau est lâché

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lane_of: dict[int, int] = {}
        self._lane_count = 1
        self._update_height()
        self.setMouseTracking(True)
        self._table: list = []
        self._lead_in = 0                        # les ordres de tête qui ne sont qu'une amorce
        self._sections: list = []
        self._playhead = -1
        self._playhead_fraction = 0.0
        self._playhead_ms = -1.0
        self._extent_ms = 0                      # > 0 : un WAV, dont la cellule unique dure autant
        self._seconds_of = None                  # (début, fin) → secondes, pour la durée affichée
        self._selection = (0, 0)
        self._anchor: int | None = None
        self._drag_section = None
        self._drag_edge: str | None = None
        self._cues: list = []
        self._drag_cue = None

    # ── Ce qu'on lui donne ────────────────────────────────────────

    def set_orders(self, table: list, lead_in: int = 0) -> None:
        """`lead_in` : combien d'ordres de tête ne sont qu'une amorce (cf. `lead_in_orders`) — cases réduites et barrées."""
        self._table = list(table)
        self._lead_in = lead_in
        self._extent_ms = 0
        self._selection = (0, 0)
        self.update()

    def set_timeline(self, duration_ms: int) -> None:
        """Un WAV : une seule cellule, sur toute sa durée."""
        self._table = [0]
        self._lead_in = 0
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

    def set_cues(self, cues: list) -> None:
        self._cues = list(cues)
        self.update()

    def set_playhead_order(self, order: int, fraction: float = 0.0) -> None:
        """La tête de lecture : l'ordre joué, et où l'on en est DANS sa case (0..1) — la ligne avance en continu."""
        if order < 0:
            fraction = 0.0
        if order != self._playhead or fraction != self._playhead_fraction:
            self._playhead, self._playhead_fraction = order, fraction
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
        """La largeur d'une case ordinaire : ce qui reste après les cases d'amorce, partagé entre les autres."""
        n = len(self._table) - self._lead_in
        return (self.width() - 2 - self._lead_in * _LEAD_W) / n if n > 0 else 0.0

    def _x(self, position: float) -> float:
        """L'abscisse d'une position : un ordre, ou une milliseconde pour un WAV."""
        if self._timed:
            return 1 + position / self._extent_ms * (self.width() - 2)
        lead = min(position, self._lead_in)
        return 1 + lead * _LEAD_W + (position - lead) * self._cell_width()

    def _position_f(self, x: float) -> float:
        """Où tombe `x` dans la table d'ordres, à la fraction près (l'inverse de `_x`)."""
        offset = x - 1
        if offset < self._lead_in * _LEAD_W:
            return offset / _LEAD_W
        return self._lead_in + (offset - self._lead_in * _LEAD_W) / max(1.0, self._cell_width())

    def _index_at(self, x: float) -> int:
        n = len(self._table)
        return max(0, min(n - 1, int(self._position_f(x)))) if n else -1

    def _position_at(self, x: float) -> int:
        if self._timed:
            return int((x - 1) / max(1, self.width() - 2) * self._extent_ms)
        return self._index_at(x)

    def _cell_rect(self, i: int) -> QRectF:
        return QRectF(self._x(i), self._cells_top(), self._x(i + 1) - self._x(i), _CELL)

    def _bands_top(self) -> int:
        return _RULER + _CUE_LANE

    def _cells_top(self) -> int:
        return self._bands_top() + self._lane_count * _BAND + 2

    def _bands_bottom(self) -> int:
        return self._bands_top() + self._lane_count * _BAND

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
        return QRectF(self._x(start), self._bands_top() + lane * _BAND,
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

    def _flag_rect(self, cue) -> QRectF:
        """Le drapeau d'un repère : sa hampe est à la position, la bannière flotte à droite."""
        return QRectF(self._x(cue.position), _RULER + 1, _CUE_FLAG_W, _CUE_LANE - 3)

    def _cue_at(self, x: float, y: float):
        point = QPointF(x, y)
        return next((c for c in reversed(self._cues)
                     if self._flag_rect(c).adjusted(-3, 0, 0, 2).contains(point)), None)

    def _boundary_at(self, x: float) -> int:
        """Borne la plus proche, y compris la fin de la table d'ordres."""
        if self._timed:
            return max(0, min(self._extent, self._position_at(x)))
        return max(0, min(self._extent, round(self._position_f(x))))

    # ── La souris ─────────────────────────────────────────────────

    def _cue_position_at(self, x: float) -> int | None:
        """La position où un repère se pose sous `x` : un ordre qui porte un pattern (module), ou une milliseconde (WAV)."""
        if self._timed:
            return max(0, min(self._extent_ms - 1, self._position_at(x)))
        i = self._index_at(x)
        return i if i >= self._lead_in and is_pattern_order(self._table[i]) else None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton and self._table:
            x, y = e.position().x(), e.position().y()
            cue = self._cue_at(x, y) if y < self._bands_top() else None
            position = cue.position if cue is not None else self._cue_position_at(x)
            if position is not None:
                self.cue_context_requested.emit(cue, position, e.globalPosition().toPoint())
            return
        if e.button() != Qt.MouseButton.LeftButton or not self._table:
            return
        x = e.position().x()
        if e.position().y() < self._bands_top():                  # la voie des repères : un drapeau se saisit, le vide ne fait rien
            cue = self._cue_at(x, e.position().y())
            if cue is not None:
                self._drag_cue = cue
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            return
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
        if i < self._lead_in or not is_pattern_order(self._table[i]):      # l'amorce n'est pas un ordre qu'on choisit
            return
        self._anchor = i
        self._set_selection(i, i + 1)

    def mouseMoveEvent(self, e):
        if self._drag_cue is not None:
            position = self._cue_position_at(e.position().x())
            if position is not None and position != self._drag_cue.position:
                self.cue_moving.emit(self._drag_cue, position)
            return
        if self._drag_section is not None:
            section = self._drag_section
            position = self._boundary_at(e.position().x())
            shortest = MIN_SECTION_MS if self._timed else 1          # une section d'un WAV ne peut pas être plus courte
            if self._drag_edge == "start":
                start, end = min(max(position, self._lead_in), section.end - shortest), section.end
            else:
                start, end = section.start, max(position, section.start + shortest)
            self.section_range_moving.emit(section, start, end)
            return
        if self._anchor is None:
            x = e.position().x()
            cue = self._cue_at(x, e.position().y()) if self._table and e.position().y() < self._bands_top() else None
            if cue is not None:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                self.setToolTip(self.cue_tip(cue))
                return
            hit = self._section_at(x, e.position().y()) if self._table and e.position().y() < self._bands_bottom() else None
            play = hit is not None and self._play_hit(hit, x)
            edge = self._edge_at(hit, x) if hit is not None and not play else None
            self.setCursor(Qt.CursorShape.SizeHorCursor if edge else
                           Qt.CursorShape.PointingHandCursor if play else Qt.CursorShape.ArrowCursor)
            on_lead_in = (self._lead_in and not self._timed and e.position().y() >= self._cells_top()
                          and self._index_at(x) < self._lead_in)
            self.setToolTip(tooltip(title=label("sndedit.preview_section"), body=label("sndedit.preview_section_tip"))
                            if play else
                            tooltip(title=label("sndedit.lead_in"), body=label("sndedit.lead_in_tip"))
                            if on_lead_in else "")
            return
        i = self._index_at(e.position().x())
        lo, hi = max(self._lead_in, min(self._anchor, i)), max(self._anchor, i)
        self._set_selection(lo, hi + 1)

    def mouseReleaseEvent(self, _e):
        if self._drag_cue is not None:
            self._drag_cue = None
            self.cue_moved.emit()
            self.unsetCursor()
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
            if i % every == 0 and not self._timed and i >= self._lead_in:
                p.setPen(QPen(QColor(C.TEXT_DIM)))
                p.drawText(QPointF(rect.left() + 3, _RULER - 4), f"{i:02d}")
            if i < self._lead_in:
                self._paint_lead_in(p, rect)
            else:
                self._paint_cell(p, rect, is_pattern_order(entry))
        for rank, section in enumerate(self._sections):
            self._paint_section(p, rank, section)
        for cue in self._cues:
            self._paint_cue(p, cue)
        self._paint_selection_and_playhead(p)

    def _paint_cell(self, p: QPainter, rect: QRectF, is_pattern: bool) -> None:
        p.fillRect(rect.adjusted(0, 0, -1, 0), QColor(C.BG_INPUT if is_pattern else C.BG_DEEP))
        p.setPen(QPen(QColor(C.BORDER_MID)))
        p.drawRect(rect.adjusted(0, 0, -1, 0))
        if not is_pattern:                                         # marqueur : hachuré
            p.drawLine(rect.bottomLeft(), rect.topRight())

    def _paint_lead_in(self, p: QPainter, rect: QRectF) -> None:
        """L'amorce : une case étroite, creuse, BARRÉE d'une diagonale franche — on la lit comme « pas une vraie case »."""
        box = rect.adjusted(0, 0, -1, 0)
        p.fillRect(box, QColor(C.BG_DEEP))
        p.setPen(QPen(QColor(C.BORDER_MID), 1, Qt.PenStyle.DashLine))
        p.drawRect(box)
        p.setPen(QPen(QColor(C.TEXT_DIM), 2))
        p.drawLine(box.bottomLeft() + QPointF(2, -2), box.topRight() + QPointF(-2, 2))

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

    def cue_tip(self, cue) -> str:
        """L'infobulle d'un drapeau : sa nature, sa cible, et où il tombe."""
        where = (f"{cue.position / 1000:.2f} s" if self._timed else f"{cue.position:02d}")
        return tooltip(title=label(f"sndedit.cue_kind_{cue.kind}"),
                       body=label("sndedit.cue_tip", target=cue.target or "—", where=where))

    def _paint_cue(self, p: QPainter, cue) -> None:
        """La hampe descend jusqu'aux cases (là où la lecture entre) ; la bannière porte l'icône de la famille."""
        flag = self._flag_rect(cue)
        if flag.left() > self.width():
            return
        color = QColor(C.ACCENT_WARM if cue.kind in _CUE_IS_JINGLE else C.ACCENT_COOL)
        faint = QColor(color)
        faint.setAlpha(110)
        p.setPen(QPen(faint, 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(flag.left(), flag.bottom()), QPointF(flag.left(), self._cells_top()))
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fill = QColor(color)
        fill.setAlpha(60)
        p.setPen(QPen(color, 1.4))
        p.setBrush(fill)
        p.drawRect(flag)                                           # la bannière
        p.setPen(QPen(color, 2))
        p.drawLine(QPointF(flag.left(), flag.top() - 1), QPointF(flag.left(), flag.bottom() + 1))   # la hampe
        icon = QRectF(flag.left() + 5, flag.top() + 2, flag.width() - 8, flag.height() - 4)
        p.setPen(QPen(QColor(C.TEXT_HI), 1.3))
        p.setBrush(QColor(C.TEXT_HI))
        if cue.kind in _CUE_IS_JINGLE:
            self._paint_note(p, icon)
        else:
            self._paint_speaker(p, icon)
        if cue.kind in _CUE_VIA_BOX:
            p.setPen(QPen(QColor(C.BG_BASE), 1))
            p.setBrush(color)
            p.drawEllipse(QPointF(flag.right() - 1, flag.bottom() - 1), 3.2, 3.2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    @staticmethod
    def _paint_speaker(p: QPainter, r: QRectF) -> None:
        """Un haut-parleur : le boîtier, le cône, et une onde."""
        cx, cy = r.left(), r.center().y()
        p.drawPolygon(QPolygonF([QPointF(cx, cy - 2), QPointF(cx + 3, cy - 2), QPointF(cx + 6.5, cy - 4.5),
                                 QPointF(cx + 6.5, cy + 4.5), QPointF(cx + 3, cy + 2), QPointF(cx, cy + 2)]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        wave = QPainterPath()
        wave.arcMoveTo(QRectF(cx + 3.5, cy - 3.5, 7, 7), 40)
        wave.arcTo(QRectF(cx + 3.5, cy - 3.5, 7, 7), 40, -80)
        p.drawPath(wave)

    @staticmethod
    def _paint_note(p: QPainter, r: QRectF) -> None:
        """Une croche : la tête, la hampe, le crochet."""
        x, y = r.left() + 3, r.bottom() - 2
        p.drawEllipse(QPointF(x, y), 2.4, 1.9)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(x + 2.3, y), QPointF(x + 2.3, r.top() + 1))
        p.drawLine(QPointF(x + 2.3, r.top() + 1), QPointF(x + 6, r.top() + 3.5))

    def _paint_selection_and_playhead(self, p: QPainter) -> None:
        lo, hi = self._selection
        if hi > lo and not self._timed:
            first, last = self._cell_rect(lo), self._cell_rect(hi - 1)
            p.setPen(QPen(QColor(C.ACCENT), 2, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(first.left(), first.top(), last.right() - first.left() - 1, _CELL))
        if self._timed:
            x = self._x(min(self._playhead_ms, self._extent_ms)) if self._playhead_ms >= 0 else None
        elif 0 <= self._playhead < len(self._table):
            r = self._cell_rect(self._playhead)
            p.setPen(QPen(QColor(C.ACCENT_WARM), 2))
            p.drawRect(r.adjusted(1, 1, -2, -1))
            x = r.left() + r.width() * max(0.0, min(1.0, self._playhead_fraction))
        else:
            x = None
        if x is not None:                       # la ligne traverse TOUTE la structure : voie des repères, sections, cases
            warm = QColor(C.ACCENT_WARM)
            p.setPen(QPen(warm, 2))
            p.drawLine(QPointF(x, _RULER), QPointF(x, self._cells_top() + _CELL))
            p.setBrush(warm)
            p.drawPolygon(QPolygonF([QPointF(x - 4, _RULER - 6), QPointF(x + 4, _RULER - 6), QPointF(x, _RULER)]))
            p.setBrush(Qt.BrushStyle.NoBrush)
