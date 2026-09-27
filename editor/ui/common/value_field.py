"""
editor/ui/common/value_field.py — champ de valeur « intelligent » pour les
coordonnées/tailles de composant (Offset X/Y, Taille W/H…).

COMPOSANT DE RÉFÉRENCE réutilisable : à privilégier partout où un champ
numérique spatial doit pouvoir valoir un littéral OU pointer une variable.

Une valeur peut être :
  • un littéral en PIXELS  → spinbox, bouton affiche « px »
  • un littéral en TILES   → spinbox (en tiles), bouton affiche « t »
  • une RÉFÉRENCE variable → puce avec le nom, bouton affiche « ƒ »
    (variables globales `g_<nom>` ou constantes `CONST_<NOM>` du projet)

Le bouton de mode ouvre un menu : Pixels / Tiles / puis la liste des globals
et constantes déclarées. Le widget émet `changed(raw)` où `raw` est la forme
sérialisable (`int` px, ou dict tile/ref) — voir core/models/field_value.py.

──────────────────────────────────────────────────────────────────────────
API
    ValueField(raw=0, variables=None, min_px=-32767, max_px=32767, allow_tile=True)
        variables : list[(src, name)] avec src ∈ {"global","const"}.
                    En pratique : core.models.field_value.variables_from_project.
    .changed(raw)          signal — nouvelle forme sérialisable (int|dict)
    .raw() -> int|dict     forme courante (à stocker dans le modèle)
    .set_raw(raw)          MAJ silencieuse (syncer inspecteur ; n'émet pas)
    .set_variables(vars)   remplace la liste des variables proposées

USAGE (éditeur de composant) — passer par la factory W.value_field :
    vf = W.value_field(getattr(comp, "x", 0), project=proj)   # min_px=1 pour W/H
    vf.changed.connect(lambda raw: self.set_field(comp, "x", raw))
    self.register_syncer("x", lambda v, w=vf: w.set_raw(v))
    W.pair("Offset", "X", C.AXIS_X, vf, "Y", C.AXIS_Y, vf_y, layout)

RÉSOLUTION à l'affichage (canvas) — une ref n'a pas de pixel connu :
    from core.models.field_value import FieldValue, make_resolver
    resolve = make_resolver(project)
    px = FieldValue.parse(comp.x).px(resolve)   # ref → défaut de la variable

CODEGEN :
    FieldValue.parse(comp.x).c_expr()   # "16" | "g_score" | "CONST_MAX"
──────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from ui.common.labels import label
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QSpinBox, QToolButton, QLabel, QMenu,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T, QSS
from core.models.field_value import FieldValue, TILE_SIZE


class _QuietSpin(QSpinBox):
    """N'attrape la molette que s'il a déjà le focus (sinon vole le scroll du
    panneau d'inspecteur)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class ValueField(QWidget):
    changed = pyqtSignal(object)   # émet la forme sérialisable (int | dict)

    def __init__(self, raw=0, variables=None, min_px: int = -32767, max_px: int = 32767,
                 allow_tile: bool = True, parent=None):
        super().__init__(parent)
        # [(src, nom, id)] — les paires d'avant l'identité opaque restent
        # acceptées, elles décrivent alors une variable sans id connu.
        self._variables = [tuple(v) + ((0,) if len(v) == 2 else ())
                           for v in (variables or [])]
        self._min_px = min_px
        self._max_px = max_px
        self._allow_tile = allow_tile
        self._fv = FieldValue.parse(raw, self._names())
        self._blocking = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self._spin = _QuietSpin()
        self._spin.setFont(QFont(T.MONO, T.MD))
        self._spin.setStyleSheet(QSS.spinbox)
        self._spin.valueChanged.connect(self._on_spin)
        lay.addWidget(self._spin, 1)

        self._chip = QLabel()
        self._chip.setFont(QFont(T.MONO, T.MD))
        self._chip.setVisible(False)
        lay.addWidget(self._chip, 1)

        self._btn = QToolButton()
        self._btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn.setFixedWidth(30)
        self._btn.setStyleSheet(
            f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:3px;"
            f"font-family:{T.MONO};font-size:{T.SM}px;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};border-color:{C.ACCENT};}}"
            f"QToolButton::menu-indicator{{image:none;width:0;}}"
        )
        self._menu = QMenu(self._btn)
        self._menu.setStyleSheet(QSS.menu)
        self._menu.setFont(QFont(T.UI, T.MD))
        self._menu.aboutToShow.connect(self._rebuild_menu)
        self._btn.setMenu(self._menu)
        lay.addWidget(self._btn)

        self._refresh_widgets(emit=False)

    # ── API publique ──────────────────────────────────────────────
    def raw(self):
        return self._fv.to_raw()

    def set_raw(self, raw):
        self._fv = FieldValue.parse(raw, self._names())
        self._refresh_widgets(emit=False)

    def set_variables(self, variables):
        self._variables = [tuple(v) + ((0,) if len(v) == 2 else ())
                           for v in (variables or [])]
        # La référence courante peut désigner une variable RENOMMÉE depuis :
        # relire son nom, sinon la puce garderait l'ancien.
        if self._fv.is_ref and self._fv.var_id:
            self._fv.var_name = self._names().get(
                (self._fv.var_src, self._fv.var_id), self._fv.var_name)

    def _names(self) -> dict:
        """`{(src, id): nom}` — la résolution d'une référence stockée."""
        return {(s, i): n for s, n, i in self._variables if i}

    # ── Plages ────────────────────────────────────────────────────
    def _tile_range(self) -> tuple[int, int]:
        lo = self._min_px // TILE_SIZE
        hi = self._max_px // TILE_SIZE
        if self._min_px > 0 and lo < 1:
            lo = 1
        return lo, hi

    # ── Rendu selon le mode courant ───────────────────────────────
    def _refresh_widgets(self, emit: bool):
        self._blocking = True
        fv = self._fv
        if fv.is_ref:
            self._spin.setVisible(False)
            self._chip.setVisible(True)
            self._chip.setText(fv.var_name or "?")
            col = C.ACCENT if fv.var_src == "global" else C.ACCENT_COOL
            self._chip.setStyleSheet(
                f"QLabel{{color:{col};background:{C.BG_INPUT};"
                f"border:1px solid {C.BORDER};border-radius:3px;padding:1px 6px;}}"
            )
            sym = (f"CONST_{fv.var_name.upper()}" if fv.var_src == "const"
                   else f"g_{fv.var_name}")
            self._chip.setToolTip(f"→ {sym}")
            self._btn.setText("ƒ")
        else:
            self._chip.setVisible(False)
            self._spin.setVisible(True)
            if fv.is_tile:
                lo, hi = self._tile_range()
                self._btn.setText("t")
            else:
                lo, hi = self._min_px, self._max_px
                self._btn.setText("px")
            self._spin.setRange(lo, hi)
            self._spin.setValue(int(fv.n))
            fv.n = self._spin.value()   # refléter un éventuel clamp du spin
        self._blocking = False
        if emit:
            self.changed.emit(self.raw())

    # ── Handlers ──────────────────────────────────────────────────
    def _on_spin(self, v: int):
        if self._blocking:
            return
        self._fv.n = v
        self.changed.emit(self.raw())

    def _set_mode_px(self):
        self._fv = FieldValue.pixels(self._fv.px())      # tile/ref → px courant
        self._refresh_widgets(emit=True)

    def _set_mode_tile(self):
        self._fv = FieldValue.tiles(round(self._fv.px() / TILE_SIZE))
        self._refresh_widgets(emit=True)

    def _set_mode_ref(self, src: str, name: str, var_id: int = 0):
        # Le nom sert à l'affichage, l'id part dans la donnée : c'est lui qui
        # tiendra si la variable est renommée demain.
        self._fv = FieldValue.ref(name, src, var_id)
        self._refresh_widgets(emit=True)

    # ── Menu ──────────────────────────────────────────────────────
    def _rebuild_menu(self):
        m = self._menu
        m.clear()
        a_px = m.addAction(label('valfield.pixels'))
        a_px.setCheckable(True)
        a_px.setChecked(self._fv.mode == "px")
        a_px.triggered.connect(self._set_mode_px)
        if self._allow_tile:
            a_t = m.addAction(label('valfield.tiles'))
            a_t.setCheckable(True)
            a_t.setChecked(self._fv.is_tile)
            a_t.triggered.connect(self._set_mode_tile)

        globs = [(n, i) for s, n, i in self._variables if s == "global"]
        consts = [(n, i) for s, n, i in self._variables if s == "const"]
        if globs or consts:
            m.addSeparator()
        for title, src, names in ((label('valfield.globals'), "global", globs),
                                  (label('valfield.constants'), "const", consts)):
            if not names:
                continue
            hdr = m.addAction(title)
            hdr.setEnabled(False)
            for name, vid in names:
                act = m.addAction(f"   {name}")
                act.setCheckable(True)
                act.setChecked(self._fv.is_ref and self._fv.var_src == src
                               and (self._fv.var_id == vid if vid
                                    else self._fv.var_name == name))
                act.triggered.connect(
                    lambda _=False, s=src, n=name, i=vid: self._set_mode_ref(s, n, i))
