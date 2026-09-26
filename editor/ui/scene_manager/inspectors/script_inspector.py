"""ScriptInspector — inspecteur d'un script Lua (asset, pas un component
d'actor) : note libre + liste des variables exposées (ajout/retrait). Le nom
de l'asset (fichier .lua) est renommé via l'en-tête partagé (AssetHeaderBar),
géré par DynamicInspector — cf. dynamic_inspector._on_header_rename."""
from __future__ import annotations
from ui.common.labels import label
import re
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QLineEdit, QMessageBox, QSlider, QPlainTextEdit, QPushButton, QButtonGroup,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal, QTimer, Qt

from ui.common.theme import C, T, QSS
from ui.common.responsive import InspectorScrollArea
from ui.common.widgets import W, NotesEdit, CollapsibleCard
from ui.common import icons
from scripting.exports_parser import (
    parse_exports, add_export, remove_export, rename_export,
    update_export, default_value,
)
from scripting.script_notes import read_note, write_note

# Ordre d'affichage dans le sélecteur de type — du plus courant au plus
# spécialisé (même liste que la convention documentée dans exports_parser.py).
_TYPE_ORDER = ["int", "float", "string", "bool", "vec2", "vec3", "rect", "enum",
               "actor_ref", "scene_ref", "sfx_ref"]

_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


class _StringEdit(QPlainTextEdit):
    """Zone de texte multi-ligne qui committe à la perte de focus (comme les
    QLineEdit.editingFinished ailleurs) — évite une écriture disque par frappe."""
    committed = pyqtSignal()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.committed.emit()


class ScriptInspector(QWidget):
    """Note libre + variables exposées d'un script Lua sélectionné dans le
    Project Viewer."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: Optional[Path] = None
        self._focus_var: Optional[str] = None   # nom de la ligne à focus après refresh
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        scroll = InspectorScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        self._empty = QLabel(label('scrinsp.empty'))
        self._empty.setFont(QFont(T.UI, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        layout.addWidget(self._empty)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        # ── Carte Note ────────────────────────────────────────────
        notes_card = CollapsibleCard(label('common.note'))
        self._notes_edit = NotesEdit()
        self._notes_edit.committed.connect(self._on_note_committed)
        notes_card.body_layout.addWidget(self._notes_edit)
        cl.addWidget(notes_card)

        # ── Carte Variables exposées ──────────────────────────────
        vars_card = CollapsibleCard(label('scrinsp.exposed_variables'))
        self._btn_add_var = W.btn_add(label('scrinsp.add_an_exposed_variable'))
        self._btn_add_var.clicked.connect(self._on_add_var)
        vars_card.add_header_widget(self._btn_add_var)

        self._vars_list = QVBoxLayout()
        self._vars_list.setContentsMargins(0, 2, 0, 0)
        self._vars_list.setSpacing(3)
        vars_card.body_layout.addLayout(self._vars_list)

        self._vars_empty_hint = QLabel(label('scrinsp.no_exposed_variable'))
        self._vars_empty_hint.setFont(QFont(T.UI, T.XS))
        self._vars_empty_hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        vars_card.body_layout.addWidget(self._vars_empty_hint)

        cl.addWidget(vars_card)
        cl.addStretch()
        layout.addWidget(self._content)
        self._content.setVisible(False)

    # ── Chargement ──────────────────────────────────────────────────

    def load(self, path: Optional[Path]):
        self._path = path
        if not path:
            self._content.setVisible(False); self._empty.setVisible(True)
            return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._notes_edit.set_text_silent(read_note(path))
        self._refresh_vars()

    def _refresh_vars(self):
        while self._vars_list.count():
            item = self._vars_list.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        variables = parse_exports(self._path) if self._path else []
        self._vars_empty_hint.setVisible(not variables)
        for var in variables:
            self._vars_list.addWidget(self._build_var_row(var))

    def _build_var_row(self, var: dict) -> QWidget:
        name = var["name"]
        card = QFrame()
        card.setStyleSheet(f"background:{C.BG_INPUT}; border-radius:4px;")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(8, 5, 6, 7)
        cv.setSpacing(5)

        # ── En-tête : nom éditable · type · supprimer ──────────────
        hdr = QHBoxLayout(); hdr.setContentsMargins(0, 0, 0, 0); hdr.setSpacing(6)
        name_edit = QLineEdit(name)
        name_edit.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        name_edit.setFrame(False)
        name_edit.setStyleSheet(
            f"QLineEdit{{color:{C.TEXT_HI};background:transparent;border:none;padding:0;}}"
            f"QLineEdit:focus{{border-bottom:1px solid {icons.COLOR_SCRIPT};}}"
        )
        name_edit.editingFinished.connect(
            lambda e=name_edit, old=name: self._commit_name(old, e))
        hdr.addWidget(name_edit, 1)

        type_cb = W.combobox(_TYPE_ORDER, var["type"])
        type_cb.setFixedWidth(92)
        type_cb.currentTextChanged.connect(
            lambda t, n=name: self._commit_type(n, t))
        hdr.addWidget(type_cb)

        btn_del = W.btn_danger(label('scrinsp.remove_name', name=name))
        btn_del.clicked.connect(lambda _c=False, n=name: self._on_remove_var(n))
        hdr.addWidget(btn_del)
        cv.addLayout(hdr)

        # ── Éditeur de valeur adapté au type ───────────────────────
        self._build_value_editor(var, cv)

        # Ligne fraîchement créée via « + » : focus + sélection du nom
        if name == self._focus_var:
            self._focus_var = None
            QTimer.singleShot(0, lambda e=name_edit: (e.setFocus(), e.selectAll()))
        return card

    # ── Éditeurs de valeur par type ───────────────────────────────

    def _save_var(self, var: dict):
        if self._path:
            update_export(self._path, var["name"], var)
            self.changed.emit()

    @staticmethod
    def _as_nums(val, n: int, fallback=None) -> list:
        if isinstance(val, (list, tuple)) and len(val) >= n:
            return [float(x) for x in val[:n]]
        return [float(x) for x in (fallback or [0] * n)]

    def _build_value_editor(self, var: dict, vbox: QVBoxLayout):
        typ = var["type"]

        def save():
            self._save_var(var)

        if typ == "bool":
            cur = bool(var.get("default"))
            seg = QWidget(); hb = QHBoxLayout(seg)
            hb.setContentsMargins(0, 0, 0, 0); hb.setSpacing(0)
            grp = QButtonGroup(seg); grp.setExclusive(True)
            for disp, val, rounded in (("true", True, "left"), ("false", False, "right")):
                b = QPushButton(disp); b.setCheckable(True)
                b.setFont(QFont(T.MONO, T.SM))
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setChecked(cur == val)
                radius = ("border-top-left-radius:3px;border-bottom-left-radius:3px;"
                          if rounded == "left" else
                          "border-top-right-radius:3px;border-bottom-right-radius:3px;")
                b.setStyleSheet(
                    f"QPushButton{{background:{C.BG_INPUT};color:{C.TEXT_DIM};"
                    f"border:1px solid {C.BORDER};padding:3px 16px;font-family:{T.MONO};{radius}}}"
                    f"QPushButton:checked{{background:{C.ACCENT};color:{C.BG_DEEP};"
                    f"border-color:{C.ACCENT};font-weight:bold;}}"
                )
                grp.addButton(b)
                hb.addWidget(b)
            hb.addStretch()
            # Groupe exclusif à 2 boutons : true coché ⟺ false décoché.
            grp.buttons()[0].toggled.connect(
                lambda checked: (var.__setitem__("default", bool(checked)), save()))
            vbox.addWidget(seg)

        elif typ in ("int", "float"):
            self._build_numeric_editor(var, vbox, is_float=(typ == "float"))

        elif typ == "string":
            from ui.common.screen_text_preview import ScreenTextPreview, MAX_CELLS
            edit = _StringEdit()
            edit.setPlainText(str(var.get("default") or ""))
            edit.setFont(QFont(T.MONO, T.MD))
            edit.setFixedHeight(52)
            edit.setStyleSheet(
                f"QPlainTextEdit{{color:{C.TEXT_NORM};background:{C.BG_INPUT};"
                f"border:1px solid {C.BORDER_MID};border-radius:4px;padding:3px 5px;}}"
                f"QPlainTextEdit:focus{{border:1px solid {C.ACCENT};}}"
            )
            preview = ScreenTextPreview()
            cap = QLabel()
            cap.setFont(QFont(T.UI, T.XS))

            # Jauge, pas aperçu : une chaîne exposée n'est liée à aucune police
            # (et n'est pas forcément du texte à afficher). Le libellé annonce
            # donc la grille de mesure — 8 px/caractère — et non un rendu.
            def sync_preview(_=None):
                preview.set_text(edit.toPlainText())
                if preview.truncated:
                    cap.setText(label('scrinsp.overflow', MAX_CELLS=MAX_CELLS))
                    cap.setStyleSheet(f"color:{C.ACCENT_RED}; background:transparent;")
                else:
                    cap.setText(label('scrinsp.gauge_240px_screen_8px_char'))
                    cap.setStyleSheet(f"color:{C.TEXT_MUTED}; background:transparent;")
            edit.textChanged.connect(sync_preview)
            edit.committed.connect(
                lambda: (var.__setitem__("default", edit.toPlainText()), save()))
            sync_preview()
            vbox.addWidget(edit)
            vbox.addWidget(cap)
            vbox.addWidget(preview)

        elif typ in ("vec2", "vec3"):
            n = 2 if typ == "vec2" else 3
            vals = self._as_nums(var.get("default"), n)
            axes = ["X", "Y", "Z"][:n]
            colors = [C.AXIS_X, C.AXIS_Y, C.AXIS_Z][:n]
            roww = QWidget(); hb = QHBoxLayout(roww)
            hb.setContentsMargins(0, 0, 0, 0); hb.setSpacing(6)
            spins = []
            for ax, col, val in zip(axes, colors, vals):
                lbl = QLabel(ax); lbl.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
                lbl.setStyleSheet(f"color:{col}; background:transparent;")
                sp = W.spinbox(int(val), -9999, 9999)
                spins.append(sp)
                hb.addWidget(lbl); hb.addWidget(sp, 1)

            def save_vec(_v=None):
                var["default"] = [s.value() for s in spins]; save()
            for sp in spins:
                sp.valueChanged.connect(save_vec)
            vbox.addWidget(roww)

        elif typ == "rect":
            vals = self._as_nums(var.get("default"), 4, [0, 0, 16, 16])
            sp_x = W.spinbox(int(vals[0]), -9999, 9999)
            sp_y = W.spinbox(int(vals[1]), -9999, 9999)
            sp_w = W.spinbox(int(vals[2]), 0, 9999)
            sp_h = W.spinbox(int(vals[3]), 0, 9999)
            W.pair(label('scrinsp.offset'), "X", C.AXIS_X, sp_x, "Y", C.AXIS_Y, sp_y, vbox)
            W.pair(label('common.size'), "W", C.TEXT_DIM, sp_w, "H", C.TEXT_DIM, sp_h, vbox)

            def save_rect(_v=None):
                var["default"] = [sp_x.value(), sp_y.value(), sp_w.value(), sp_h.value()]; save()
            for sp in (sp_x, sp_y, sp_w, sp_h):
                sp.valueChanged.connect(save_rect)

        elif typ == "enum":
            values = list(var.get("values") or [])
            vals_edit = QLineEdit(", ".join(values))
            vals_edit.setFont(QFont(T.MONO, T.MD)); vals_edit.setStyleSheet(QSS.lineedit)
            vals_edit.setPlaceholderText(label('scrinsp.values_comma_separated'))

            def commit_values():
                new_vals = [s.strip() for s in vals_edit.text().split(",") if s.strip()]
                var["values"] = new_vals
                if var.get("default") not in new_vals:
                    var["default"] = new_vals[0] if new_vals else ""
                save(); self._refresh_vars()
            vals_edit.editingFinished.connect(commit_values)
            W.row(label('scrinsp.values'), vals_edit, vbox)
            if values:
                cb = W.combobox(values, str(var.get("default") or values[0]))
                cb.currentTextChanged.connect(
                    lambda t: (var.__setitem__("default", t), save()))
                W.row(label('scrinsp.default'), cb, vbox)

        else:  # actor_ref / scene_ref / sfx_ref — pas de contexte projet ici
            le = QLineEdit(str(var.get("default") or ""))
            le.setFont(QFont(T.MONO, T.MD)); le.setStyleSheet(QSS.lineedit)
            le.setPlaceholderText(label('scrinsp.name_typ', typ=typ))
            le.editingFinished.connect(lambda: (var.__setitem__("default", le.text()), save()))
            W.row(label('scrinsp.ref'), le, vbox)

    def _labeled_field(self, label: str, widget: QWidget) -> QWidget:
        """Colonne : label (mot complet) au-dessus de son champ."""
        col = QWidget(); v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(1)
        lbl = QLabel(label); lbl.setFont(QFont(T.UI, T.XS))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
        v.addWidget(lbl); v.addWidget(widget)
        return col

    def _build_numeric_editor(self, var: dict, vbox: QVBoxLayout, is_float: bool):
        default = var.get("default") or 0

        def save():
            self._save_var(var)

        # Bornes toujours affichées, défaut 0/0. (min, max) == (0, 0) = variable
        # classique : valeur libre (spinbox), et min/max non écrits dans le .lua.
        mn, mx = var.get("min"), var.get("max")
        lo = mn if mn is not None else 0
        hi = mx if mx is not None else 0
        clamped = not (lo == 0 and hi == 0)

        # ── Valeur ─────────────────────────────────────────────────
        if clamped and not is_float:
            lo_i, hi_i = int(lo), int(hi)
            cur = max(lo_i, min(hi_i, int(default)))
            roww = QWidget(); hb = QHBoxLayout(roww)
            hb.setContentsMargins(0, 0, 0, 0); hb.setSpacing(6)
            slider = QSlider(Qt.Orientation.Horizontal); slider.setRange(lo_i, hi_i); slider.setValue(cur)
            spin = W.spinbox(cur, lo_i, hi_i)

            def on_val(v):
                var["default"] = int(v); save()
            slider.valueChanged.connect(lambda v: (
                spin.blockSignals(True), spin.setValue(v), spin.blockSignals(False), on_val(v)))
            spin.valueChanged.connect(lambda v: (
                slider.blockSignals(True), slider.setValue(v), slider.blockSignals(False), on_val(v)))
            hb.addWidget(slider, 1); hb.addWidget(spin)
            vbox.addWidget(roww)
        elif is_float:
            r_lo = float(lo) if clamped else -9999.0
            r_hi = float(hi) if clamped else 9999.0
            sp = W.double_spinbox(float(default), r_lo, r_hi)
            sp.valueChanged.connect(lambda v: (var.__setitem__("default", float(v)), save()))
            vbox.addWidget(sp)
        else:  # int non borné → spinbox libre (comportement classique)
            sp = W.spinbox(int(default), -32768, 32767)
            sp.valueChanged.connect(lambda v: (var.__setitem__("default", int(v)), save()))
            vbox.addWidget(sp)

        # ── Min / Max — mot complet, label au-dessus, toujours visibles ──
        mk = (lambda v: W.double_spinbox(float(v), -9999, 9999)) if is_float \
            else (lambda v: W.spinbox(int(v), -32768, 32767))
        mn_w = mk(lo); mx_w = mk(hi)

        def on_bounds():
            lo2, hi2 = mn_w.value(), mx_w.value()
            if lo2 == 0 and hi2 == 0:
                var["min"] = var["max"] = None   # (0,0) → classique, non persisté
            else:
                if hi2 < lo2:
                    hi2 = lo2
                var["min"], var["max"] = lo2, hi2
            save(); self._refresh_vars()
        mn_w.editingFinished.connect(on_bounds)
        mx_w.editingFinished.connect(on_bounds)

        bounds = QWidget(); bh = QHBoxLayout(bounds)
        bh.setContentsMargins(0, 0, 0, 0); bh.setSpacing(10)
        bh.addWidget(self._labeled_field(label('scrinsp.min'), mn_w), 1)
        bh.addWidget(self._labeled_field(label('scrinsp.max'), mx_w), 1)
        vbox.addWidget(bounds)

    # ── Actions ───────────────────────────────────────────────────

    def _on_note_committed(self, text: str):
        if self._path:
            write_note(self._path, text)
            self.changed.emit()

    def _on_add_var(self):
        """Crée directement une variable exposée préremplie (nom unique + type
        int par défaut), sans dialogue, et met le focus sur son nom pour
        renommage immédiat."""
        if not self._path:
            return
        existing = {v["name"] for v in parse_exports(self._path)}
        base = "nouvelle_var"
        name, i = base, 1
        while name in existing:
            i += 1
            name = f"{base}_{i}"
        add_export(self._path, name, "int", name)
        self._focus_var = name
        self._refresh_vars()
        self.changed.emit()

    def _commit_name(self, old_name: str, edit: QLineEdit):
        new_name = edit.text().strip()
        if new_name == old_name or not self._path:
            return
        existing = {v["name"] for v in parse_exports(self._path)}
        if not _NAME_RE.match(new_name) or new_name in existing:
            edit.setText(old_name)   # invalide ou doublon → revert silencieux
            return
        rename_export(self._path, old_name, new_name)
        self._refresh_vars()
        self.changed.emit()

    def _commit_type(self, name: str, new_type: str):
        if not self._path:
            return
        var = next((v for v in parse_exports(self._path) if v["name"] == name), None)
        if var is None or var["type"] == new_type:
            return
        # Reset : la valeur par défaut d'un type ne convient pas à un autre
        # (int 5 → vec2), on repart du défaut neutre et on nettoie les extras.
        var["type"] = new_type
        var["default"] = default_value(new_type)
        var["min"] = var["max"] = None
        if new_type != "enum":
            var["values"] = []
        update_export(self._path, name, var)
        self._refresh_vars()
        self.changed.emit()

    def _on_remove_var(self, name: str):
        if not self._path:
            return
        if QMessageBox.question(
            self, label('scrinsp.remove_variable'),
            label('scrinsp.remove_var_confirm', name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        remove_export(self._path, name)
        self._refresh_vars()
        self.changed.emit()
