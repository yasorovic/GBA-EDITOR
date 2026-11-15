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
from ui.common.tooltip import tooltip
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QSpinBox, QSlider, QToolButton, QLabel, QMenu,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T, QSS
from ui.common.unit_spin import QuietDoubleSpin, QuietSpin
from core.models.field_value import FieldValue, TILE_SIZE, is_ref_raw


def _mode_button(width: int) -> QToolButton:
    """Le bouton de mode des champs de ce fichier : il montre le mode courant (px,
    t, ƒ, px/f…) et ouvre son menu. Un seul endroit pour son allure, les trois
    champs l'avaient recopiée."""
    btn = QToolButton()
    btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    btn.setFixedWidth(width)
    btn.setStyleSheet(
        f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
        f"border:1px solid {C.BORDER};border-radius:3px;"
        f"font-family:{T.MONO};font-size:{T.SM}px;}}"
        f"QToolButton:hover{{color:{C.TEXT_HI};border-color:{C.ACCENT};}}"
        f"QToolButton::menu-indicator{{image:none;width:0;}}"
    )
    return btn


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

        self._spin = QuietSpin()
        self._spin.setFont(QFont(T.MONO, T.MD))
        self._spin.setStyleSheet(QSS.spinbox)
        self._spin.valueChanged.connect(self._on_spin)
        lay.addWidget(self._spin, 1)

        self._chip = QLabel()
        self._chip.setFont(QFont(T.MONO, T.MD))
        self._chip.setVisible(False)
        lay.addWidget(self._chip, 1)

        self._btn = _mode_button(30)
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
            self._chip.setToolTip(tooltip(
                title=label('valfield.reference_title'),
                body=label('valfield.reference_tip', symbol=sym)))
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

    def _set_mode_ref(self, src: str, name: str, var_id: str = ""):
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


class NumberField(QWidget):
    """Champ numérique SANS unité (rotation, échelle, priorité) : un littéral
    (`int` ou `float`) ou une référence de variable.

    Même contrat que `ValueField` (`changed(raw)`, `raw()`, `set_raw()`,
    `set_variables()`), mais le bouton de mode propose « int »/« float » (le
    littéral, le champ tel qu'il était) ou une variable — jamais pixels/tiles,
    qui n'ont pas de sens ici. `kind` = "int" | "float".
    """
    changed = pyqtSignal(object)

    def __init__(self, raw=0, variables=None, kind: str = "int",
                 min_v=0, max_v=100, step=1, suffix: str = "", wrapping: bool = False,
                 parent=None):
        super().__init__(parent)
        self._kind = kind
        self._variables = [tuple(v) + ((0,) if len(v) == 2 else ())
                           for v in (variables or [])]
        self._ref = None
        self._blocking = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        if kind == "float":
            self._spin = QuietDoubleSpin()
            self._spin.setDecimals(2)
            self._spin.setSingleStep(step)
        else:
            self._spin = QuietSpin()
            self._spin.setSingleStep(int(step))
        self._spin.setRange(min_v, max_v)
        if suffix:
            self._spin.setSuffix(suffix)
        self._spin.setWrapping(wrapping)
        self._spin.setFont(QFont(T.MONO, T.MD))
        self._spin.setStyleSheet(QSS.spinbox)
        self._spin.valueChanged.connect(self._on_spin)
        lay.addWidget(self._spin, 1)

        self._chip = QLabel()
        self._chip.setFont(QFont(T.MONO, T.MD))
        self._chip.setVisible(False)
        lay.addWidget(self._chip, 1)

        self._btn = _mode_button(38)
        self._menu = QMenu(self._btn)
        self._menu.setStyleSheet(QSS.menu)
        self._menu.setFont(QFont(T.UI, T.MD))
        self._menu.aboutToShow.connect(self._rebuild_menu)
        self._btn.setMenu(self._menu)
        lay.addWidget(self._btn)

        self.set_raw(raw)

    # ── API publique ──────────────────────────────────────────────
    def raw(self):
        if self._ref is not None:
            return self._ref.to_raw()
        return self._spin.value()

    def set_raw(self, raw):
        self._blocking = True
        if is_ref_raw(raw):
            self._ref = FieldValue.parse(raw, self._names())
        else:
            self._ref = None
            try:
                self._spin.setValue(float(raw) if self._kind == "float" else int(round(raw)))
            except (TypeError, ValueError):
                self._spin.setValue(self._spin.minimum())
        self._blocking = False
        self._refresh_widgets()

    def set_variables(self, variables):
        self._variables = [tuple(v) + ((0,) if len(v) == 2 else ())
                           for v in (variables or [])]
        if self._ref is not None and self._ref.var_id:
            self._ref.var_name = self._names().get(
                (self._ref.var_src, self._ref.var_id), self._ref.var_name)
            self._refresh_widgets()

    def _names(self) -> dict:
        return {(s, i): n for s, n, i in self._variables if i}

    # ── Rendu ─────────────────────────────────────────────────────
    def _refresh_widgets(self):
        ref = self._ref
        if ref is not None:
            self._spin.setVisible(False)
            self._chip.setVisible(True)
            self._chip.setText(ref.var_name or "?")
            col = C.ACCENT if ref.var_src == "global" else C.ACCENT_COOL
            self._chip.setStyleSheet(
                f"QLabel{{color:{col};background:{C.BG_INPUT};"
                f"border:1px solid {C.BORDER};border-radius:3px;padding:1px 6px;}}"
            )
            sym = (f"CONST_{ref.var_name.upper()}" if ref.var_src == "const"
                   else f"g_{ref.var_name}")
            self._chip.setToolTip(tooltip(
                title=label('valfield.reference_title'),
                body=label('valfield.reference_tip', symbol=sym)))
            self._btn.setText(label('valfield.var_button'))
        else:
            self._chip.setVisible(False)
            self._spin.setVisible(True)
            self._btn.setText(self._kind)

    # ── Handlers ──────────────────────────────────────────────────
    def _on_spin(self, _v):
        if not self._blocking:
            self.changed.emit(self.raw())

    def _set_literal(self):
        if self._ref is None:
            return
        self._ref = None
        self._refresh_widgets()
        self.changed.emit(self.raw())

    def _set_ref(self, src: str, name: str, var_id: str = ""):
        self._ref = FieldValue.ref(name, src, var_id)
        self._refresh_widgets()
        self.changed.emit(self.raw())

    def _rebuild_menu(self):
        m = self._menu
        m.clear()
        a_lit = m.addAction(label('valfield.number_int' if self._kind == "int"
                                  else 'valfield.number_float'))
        a_lit.setCheckable(True)
        a_lit.setChecked(self._ref is None)
        a_lit.triggered.connect(self._set_literal)
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
                act.setChecked(self._ref is not None and self._ref.var_src == src
                               and (self._ref.var_id == vid if vid
                                    else self._ref.var_name == name))
                act.triggered.connect(
                    lambda _=False, s=src, n=name, i=vid: self._set_ref(s, n, i))


class UnitModeField(QWidget):
    """Champ ENTIER dont le bouton de mode choisit l'UNITÉ DE SAISIE : celle que le
    script a déclarée sur son export (`unit = "px/f"`), ou l'unité du matériel qui
    est derrière (Q8). La valeur ne change pas de nature en changeant de mode : elle
    reste un entier, et l'autre lecture s'affiche à côté du champ.

    Trois champs voisins, trois rôles : `ValueField` tient une valeur SPATIALE de
    composant (pixels, tiles, variable), `UnitSpin` (ui/common/unit_spin.py) tient
    un entier dont l'unité est fixe et seulement affichée, et celui-ci tient un
    entier que deux unités expriment, parce que le matériel compte autrement que
    l'auteur.

    API
        UnitModeField(raw, unit, min_v, max_v)
            raw   : int (unité de base) ou {"unit": u, "n": n} (unité déclarée)
            unit  : une clé de scripting.exports_parser.EXPORT_UNITS
        .changed(raw)       signal : la forme sérialisable (int | dict)
        .raw() -> int|dict  forme courante
        .set_raw(raw)       MAJ silencieuse (n'émet pas)
    """
    changed = pyqtSignal(object)

    def __init__(self, raw=0, unit: str = "", min_v: int = -9999, max_v: int = 9999,
                 slider: bool = False, parent=None):
        super().__init__(parent)
        from scripting.exports_parser import normalize_unit, unit_base, unit_factor
        self._unit = normalize_unit(unit)
        self._factor = unit_factor(self._unit)
        self._base = unit_base(self._unit)
        self._min, self._max = int(min_v), int(max_v)
        self._mode = "unit"
        self._blocking = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        # Le slider d'une valeur bornée, comme pour un entier sans unité. Il vit ICI
        # et non dans la ligne de l'inspecteur : sa plage suit le mode (0 à 8 px/f,
        # ou 0 à 2048 en Q8), et le champ est seul à savoir quand elle change.
        self._slider = QSlider(Qt.Orientation.Horizontal) if slider else None
        if self._slider is not None:
            self._slider.valueChanged.connect(self._on_slider)
            lay.addWidget(self._slider, 1)

        self._spin = QuietSpin()
        self._spin.setFont(QFont(T.MONO, T.MD))
        self._spin.setStyleSheet(QSS.spinbox)
        self._spin.valueChanged.connect(self._on_spin)
        lay.addWidget(self._spin, 1)

        # La seconde lecture : ce que la même valeur vaut dans l'autre unité. C'est
        # elle qui rend le Q8 lisible sans le remplacer.
        self._reading = QLabel()
        self._reading.setFont(QFont(T.MONO, T.SM))
        self._reading.setStyleSheet(f"QLabel{{color:{C.TEXT_DIM};}}")
        lay.addWidget(self._reading)

        self._btn = _mode_button(44)
        self._menu = QMenu(self._btn)
        self._menu.setStyleSheet(QSS.menu)
        self._menu.setFont(QFont(T.UI, T.MD))
        self._menu.aboutToShow.connect(self._rebuild_menu)
        self._btn.setMenu(self._menu)
        self._btn.setToolTip(tooltip(
            title=label('valfield.unit_title'),
            body=label('valfield.unit_tip', unit=self._unit or "?",
                       base=self._base or "?", factor=self._factor)))
        # Une unité de facteur 1 (px) ne nomme qu'elle-même : rien à choisir, le
        # bouton ne ferait qu'ouvrir un menu d'une seule ligne.
        self._btn.setEnabled(self._factor != 1)
        lay.addWidget(self._btn)

        self.set_raw(raw)

    # ── API publique ──────────────────────────────────────────────
    def raw(self):
        n = self._spin.value()
        return {"unit": self._unit, "n": n} if self._mode == "unit" else int(n)

    def set_raw(self, raw):
        self._mode = "unit" if isinstance(raw, dict) else "base"
        if isinstance(raw, dict):
            n = int(raw.get("n", 0))
        else:
            try:
                n = int(raw)
            except (TypeError, ValueError):
                n = 0
        self._refresh(n)

    # ── Rendu ─────────────────────────────────────────────────────
    def _refresh(self, n: int):
        self._blocking = True
        if self._mode == "unit":
            lo, hi = self._min, self._max
            self._btn.setText(self._unit or "?")
        else:
            lo, hi = self._min * self._factor, self._max * self._factor
            self._btn.setText(self._base or "?")
        self._spin.setRange(lo, hi)
        self._spin.setValue(n)
        if self._slider is not None:
            self._slider.setRange(lo, hi)
            self._slider.setValue(self._spin.value())
        self._blocking = False
        self._update_reading()

    def _update_reading(self):
        if self._factor == 1:
            self._reading.setVisible(False)
            return
        n = self._spin.value()
        if self._mode == "unit":
            text = f"= {n * self._factor} {self._base}"
        else:
            text = f"= {_trim(n / self._factor)} {self._unit}"
        self._reading.setVisible(True)
        self._reading.setText(text)

    # ── Handlers ──────────────────────────────────────────────────
    def _on_spin(self, v):
        if self._blocking:
            return
        if self._slider is not None and self._slider.value() != v:
            self._blocking = True
            self._slider.setValue(v)
            self._blocking = False
        self._update_reading()
        self.changed.emit(self.raw())

    def _on_slider(self, v):
        # Le spinbox reste la source de la valeur : le slider le pilote, et c'est
        # lui qui notifie (même partage que `_row_with_slider` côté inspecteur).
        if not self._blocking:
            self._spin.setValue(v)

    def _set_mode(self, mode: str):
        if mode == self._mode:
            return
        n = self._spin.value()
        self._mode = mode
        # La valeur SUIT le changement de mode : c'est la même quantité, dite
        # autrement. Le passage vers l'unité déclarée arrondit, puisqu'elle est
        # plus grosse que celle du matériel.
        self._refresh(n * self._factor if mode == "base" else round(n / self._factor))
        self.changed.emit(self.raw())

    def _rebuild_menu(self):
        m = self._menu
        m.clear()
        for mode, name in (("unit", self._unit), ("base", self._base)):
            act = m.addAction(name or "?")
            act.setCheckable(True)
            act.setChecked(self._mode == mode)
            act.triggered.connect(lambda _=False, md=mode: self._set_mode(md))


def _trim(value: float) -> str:
    """La lecture d'une valeur fractionnaire : deux décimales, sans les zéros de
    fin. Un AFFICHAGE, jamais une valeur stockée : l'éditeur ne manipule que des
    entiers."""
    return f"{value:.2f}".rstrip("0").rstrip(".")
