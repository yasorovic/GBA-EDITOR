"""Éditeur du ScriptComponent."""
from __future__ import annotations

from copy import deepcopy

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QSlider, QVBoxLayout, QWidget
from PyQt6.QtGui import QFont

from . import BaseComponentEditor, register
from ui.common.widgets import W
from ui.common import icons
from ui.common.pickers import attached_script_slot, name_picker_slot
from ui.common.labels import label
from ui.common.theme import C, T, QSS


def reveal_export_row(insp, scroll, export: str) -> None:
    """Fait défiler `scroll` jusqu'à la ligne de l'export `export` que `ScriptEditor` a construite pour `insp`, et donne
    le focus à son champ. Appelé au clic d'un diagnostic d'export, jamais au chargement."""
    row = getattr(insp, "_export_rows", {}).get(export)
    if row is None:
        return

    def go():
        scroll.ensureWidgetVisible(row)
        field = next((w for w in row.findChildren(QWidget) if w.focusPolicy() != Qt.FocusPolicy.NoFocus), None)
        (field or row).setFocus(Qt.FocusReason.OtherFocusReason)
    QTimer.singleShot(0, go)


@register("script")
class ScriptEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        self.comp = comp
        self._layout = layout
        self._exports_container = None
        self._variables = None
        self._exports_project = None
        self._loading = False
        slot = attached_script_slot(
            project     = lambda: self.insp._project,
            on_assigned = lambda rel: self._assign_script(self.comp, rel),
            on_cleared  = lambda: self._clear_script(self.comp),
            open_file   = self._open_file,
            template    = "actor",
            add_label   = label("comped.script_add"),
            new_title   = label("comped.new_script_title"),
            hint        = label("comped.script_hint"),
            parent      = self.insp,
        )
        self._slot = slot
        layout.addWidget(slot)
        self.reload(comp)

    def reload(self, comp) -> bool:
        from scripting.exports_parser import parse_exports

        same_comp = self.comp is comp
        self.comp = comp
        proj = self.insp._project
        path = proj.asset_abs(comp.script) if proj and comp.script else None
        variables = parse_exports(path) if path else []
        self._slot.set_value(comp.script)
        self._loading = True
        try:
            if variables != self._variables or proj is not self._exports_project:
                if self._exports_container is not None:
                    self._layout.removeWidget(self._exports_container)
                    self._exports_container.deleteLater()
                self._variables = variables
                self._exports_project = proj
                self._export_loaders = []
                self.insp._export_rows = {}
                self._exports_container = QWidget()
                layout = QVBoxLayout(self._exports_container)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(self._layout.spacing())
                self._build_exports_panel(comp, variables, layout)
                self._layout.addWidget(self._exports_container)
                self._exports_container.setVisible(bool(variables))
            elif not same_comp or comp.exports_values != self._loaded_values:
                for var, load in self._export_loaders:
                    load(comp.exports_values.get(var["name"], var["default"]))
            self._loaded_values = deepcopy(comp.exports_values)
        finally:
            self._loading = False
        return True

    # ── Panneau variables exposées ────────────────────────────────────

    def _build_exports_panel(self, comp, variables, layout):
        if not variables:
            return

        W.separator(layout)
        W.section(label("comped.exposed_vars"), layout)

        for var in variables:
            first = layout.count()
            self._build_var_row(comp, var, layout)
            item = layout.itemAt(first)
            if item is not None and item.widget() is not None:
                self.insp._export_rows[var["name"]] = item.widget()

    _FLOAT_SLIDER_STEPS = 1000

    @staticmethod
    def _row_with_slider(text, spin, value, lo, hi, kind, layout):
        """Ligne « libellé | slider | spinbox » pour une variable bornée. Le
        spinbox reste la source de la valeur (c'est lui qui émet le save) ; le
        slider ne fait que le piloter. Flottant : le slider parcourt
        _FLOAT_SLIDER_STEPS pas entre min et max."""
        steps = 0 if kind is int else ScriptEditor._FLOAT_SLIDER_STEPS
        if kind is int:
            to_slider, from_slider = int, int
            s_lo, s_hi = int(lo), int(hi)
        else:
            span = (hi - lo) or 1.0
            to_slider = lambda v: round((v - lo) / span * steps)
            from_slider = lambda s: lo + s / steps * span
            s_lo, s_hi = 0, steps
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(s_lo, s_hi)
        slider.setValue(to_slider(value))

        def on_slider(s):
            spin.setValue(from_slider(s))      # émet valueChanged → save

        def on_spin(v):
            slider.blockSignals(True)
            slider.setValue(to_slider(v))
            slider.blockSignals(False)

        slider.valueChanged.connect(on_slider)
        spin.valueChanged.connect(on_spin)
        box = QWidget()
        hb = QHBoxLayout(box)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(6)
        hb.addWidget(slider, 1)
        hb.addWidget(spin)
        W.row(text, box, layout)

    def _build_var_row(self, comp, var: dict, layout):
        name    = var["name"]
        typ     = var["type"]
        title   = var.get("label", name)
        current = comp.exports_values.get(name, var["default"])

        def save(value, _name=name):
            if self._loading:
                return
            self.comp.exports_values[_name] = value
            self._loaded_values = deepcopy(self.comp.exports_values)
            self.insp._save_component_change(None)

        # ── bool ──────────────────────────────────────────────────
        if typ == "bool":
            chk = W.checkbox_row(title, "", layout)
            chk.setChecked(bool(current))
            chk.toggled.connect(save)
            load = lambda v: chk.setChecked(bool(v))

        # ── int ───────────────────────────────────────────────────
        elif typ == "int":
            mn = int(var["min"]) if var["min"] is not None else -9999
            mx = int(var["max"]) if var["max"] is not None else  9999
            sp = W.spinbox(int(current) if current != "" else 0, mn, mx)
            if var["min"] is not None and var["max"] is not None:
                self._row_with_slider(title, sp, sp.value(), mn, mx, int, layout)
            else:
                W.row(title, sp, layout)
            sp.valueChanged.connect(save)
            load = lambda v: sp.setValue(int(v) if v != "" else 0)

        # ── float ─────────────────────────────────────────────────
        elif typ == "float":
            mn = float(var["min"]) if var["min"] is not None else -9999.0
            mx = float(var["max"]) if var["max"] is not None else  9999.0
            def as_float(value):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0
            val = as_float(current)
            sp = W.double_spinbox(val, mn, mx)
            if var["min"] is not None and var["max"] is not None:
                self._row_with_slider(title, sp, sp.value(), mn, mx, float, layout)
            else:
                W.row(title, sp, layout)
            sp.valueChanged.connect(save)
            load = lambda v: sp.setValue(as_float(v))

        # ── string ────────────────────────────────────────────────
        elif typ == "string":
            le = QLineEdit(str(current))
            le.setFont(QFont(T.UI, T.MD))
            le.setStyleSheet(QSS.lineedit)
            W.row(title, le, layout)
            le.editingFinished.connect(lambda w=le: save(w.text()))
            load = lambda v: le.setText(str(v))

        # ── vec2 ──────────────────────────────────────────────────
        elif typ == "vec2":
            vals = current if isinstance(current, (list, tuple)) and len(current) >= 2 else [0, 0]
            sp_x = W.spinbox(int(vals[0]), -9999, 9999)
            sp_y = W.spinbox(int(vals[1]), -9999, 9999)
            W.pair(title, "X", C.AXIS_X, sp_x, "Y", C.AXIS_Y, sp_y, layout)
            sp_x.valueChanged.connect(lambda _, sx=sp_x, sy=sp_y: save([sx.value(), sy.value()]))
            sp_y.valueChanged.connect(lambda _, sx=sp_x, sy=sp_y: save([sx.value(), sy.value()]))
            def load(value):
                vals = value if isinstance(value, (list, tuple)) and len(value) >= 2 else [0, 0]
                sp_x.setValue(int(vals[0]))
                sp_y.setValue(int(vals[1]))

        # ── rect ──────────────────────────────────────────────────
        elif typ == "rect":
            vals = current if isinstance(current, (list, tuple)) and len(current) >= 4 else [0, 0, 16, 16]
            sp_x = W.spinbox(int(vals[0]), -9999, 9999)
            sp_y = W.spinbox(int(vals[1]), -9999, 9999)
            sp_w = W.spinbox(int(vals[2]),     0, 9999)
            sp_h = W.spinbox(int(vals[3]),     0, 9999)
            W.pair(title, "X", C.AXIS_X, sp_x, "Y", C.AXIS_Y, sp_y, layout)
            W.pair("",    "W", C.TEXT_DIM, sp_w, "H", C.TEXT_DIM, sp_h, layout)

            def _save_rect(_, sx=sp_x, sy=sp_y, sw=sp_w, sh=sp_h):
                save([sx.value(), sy.value(), sw.value(), sh.value()])
            for sp in (sp_x, sp_y, sp_w, sp_h):
                sp.valueChanged.connect(_save_rect)
            def load(value):
                vals = value if isinstance(value, (list, tuple)) and len(value) >= 4 else [0, 0, 16, 16]
                for widget, val in zip((sp_x, sp_y, sp_w, sp_h), vals):
                    widget.setValue(int(val))

        # ── enum ──────────────────────────────────────────────────
        elif typ == "enum":
            values = var.get("values") or []
            cb = W.combobox(values, str(current))
            W.row(title, cb, layout)
            cb.currentTextChanged.connect(save)
            load = lambda v: cb.setCurrentIndex(max(0, cb.findText(str(v))))

        # ── scene_ref / sfx_ref / actor_ref : un nom parmi ceux du projet ──
        elif typ in ("scene_ref", "sfx_ref", "actor_ref"):
            def names():
                project = self.insp._project
                if typ == "scene_ref":
                    return [s.name for s in project.scenes] if project else []
                if typ == "sfx_ref":
                    if project:
                        project.load_audio()   # catalogue différé
                    return [s.name for s in project.sfx] if project else []
                scene = getattr(self.insp, "_scene", None) or (project.active_scene if project else None)
                return [a.name for a in scene.actors if a is not self.insp._actor] if scene else []
            kind = typ[:-4]
            slot = name_picker_slot(
                names, str(current or ""), icons.COLOR_SCRIPT, on_picked=save,
                add_label=title, icon=icons.get(kind, C.TEXT_DIM) if kind != "actor" else None,
                none_label=label("common.none_dash"))
            W.row(title, slot, layout)
            load = lambda v: slot.set_value(str(v or ""))
        else:
            return

        self._export_loaders.append((var, load))

    # ── Actions ───────────────────────────────────────────────────────

    def _open_file(self, path: str):
        fn = getattr(self.insp, "_script_open_fn", None)
        if fn:
            fn(path)

    def _assign_script(self, comp, rel: str):
        comp.script = rel
        comp.exports_values = {}   # les valeurs de l'ancien script ne valent pas pour le nouveau
        self.reload(comp)
        self.insp._save_component_change(None)

    def _clear_script(self, comp):
        comp.script = None
        comp.exports_values = {}
        self.reload(comp)
        self.insp._save_component_change(None)
