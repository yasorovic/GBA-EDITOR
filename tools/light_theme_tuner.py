"""Règle à la main le dégradé de blanc du thème clair, avec un aperçu en direct.

Les valeurs de départ sont lues dans `_LIGHT` de editor/ui/common/theme.py (source unique).
Chaque curseur est un gris neutre (0-255). « Tout décaler » assombrit ou éclaircit
l'ensemble d'un coup ; les curseurs fins règlent chaque surface. Le bouton « Copier »
met dans le presse-papiers les lignes à coller dans `_LIGHT` : rien n'est écrit dans le dépôt.

    python -X utf8 tools/light_theme_tuner.py
"""
import re
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

THEME_PATH = Path(__file__).resolve().parent.parent / "editor" / "ui" / "common" / "theme.py"

# (clé de _LIGHT, libellé) du plus sombre au plus clair attendu
SURFACES = [
    ("BG_DEEP", "Creux : fenêtre, canvas, listes, statut"),
    ("BG_BASE", "Corps des libraries, dialogues"),
    ("BG_PANEL", "Fond des widgets / inspecteur"),
    ("BG_RAISED", "Menus, barres d'outils"),
    ("BG_INPUT", "Champs de saisie"),
    ("BG_HOVER", "Survol"),
    ("BG_SEL", "Sélection"),
    ("BORDER", "Filet"),
    ("BORDER_MID", "Filet moyen"),
    ("BORDER_DARK", "Filet léger"),
]
TEXT_HI = "#1a1a1a"
TEXT_DIM = "#666666"
SPLITTER = "#242424"
ACCENT = "#3a3a3a"


def read_light_defaults() -> dict[str, int]:
    """Lit les gris de `_LIGHT` ; un gris neutre vaut son premier octet."""
    source = THEME_PATH.read_text(encoding="utf-8")
    block = source[source.index("_LIGHT = dict("):]
    block = block[:block.index("\n)\n")]
    values = {}
    for key, _label in SURFACES:
        match = re.search(rf'{key}="#([0-9a-fA-F]{{2}})', block)
        values[key] = int(match.group(1), 16) if match else 240
    return values


def gray(level: int) -> str:
    level = max(0, min(255, level))
    return f"#{level:02x}{level:02x}{level:02x}"


class SurfaceRow:
    def __init__(self, grid: QGridLayout, row: int, key: str, label: str, value: int, on_change):
        self.key = key
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 255)
        self.slider.setValue(value)
        self.spin = QSpinBox()
        self.spin.setRange(0, 255)
        self.spin.setValue(value)
        self.swatch = QFrame()
        self.swatch.setFixedSize(28, 18)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.slider.valueChanged.connect(on_change)
        grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(self.slider, row, 1)
        grid.addWidget(self.spin, row, 2)
        grid.addWidget(self.swatch, row, 3)

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, level: int):
        self.slider.setValue(max(0, min(255, level)))


class Preview(QFrame):
    """Maquette sommaire de l'éditeur : barre, arbre, canvas, inspecteur, statut."""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.toolbar = QFrame()
        bar = QHBoxLayout(self.toolbar)
        for text in ("Run", "Undo", "Redo", "Scenes", "Backgrounds", "Palettes"):
            button = QPushButton(text)
            button.setObjectName("tab_active" if text == "Scenes" else "tab")
            bar.addWidget(button)
        bar.addStretch()
        self.search = QLineEdit("PongAdvanced")
        bar.addWidget(self.search)
        outer.addWidget(self.toolbar)

        body = QHBoxLayout()
        body.setSpacing(0)
        self.tree = QFrame()
        tree_layout = QVBoxLayout(self.tree)
        tree_layout.addWidget(QLabel("SCR_Arena"))
        self.selected = QLabel("  Player")
        self.hovered = QLabel("  BALL")
        for row in (QLabel("  Player_copy"), self.selected, self.hovered, QLabel("  Interface")):
            tree_layout.addWidget(row)
        tree_layout.addStretch()
        self.canvas = QFrame()
        canvas_layout = QVBoxLayout(self.canvas)
        canvas_layout.addStretch()
        canvas_layout.addWidget(QLabel("canvas 240x160"), alignment=Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addStretch()
        self.inspector = QFrame()
        inspector_layout = QVBoxLayout(self.inspector)
        inspector_layout.addWidget(QLabel("Scene mode"))
        self.field = QLineEdit("SCR_Arena.lua")
        inspector_layout.addWidget(self.field)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Notes...")
        inspector_layout.addWidget(self.notes)
        inspector_layout.addStretch()
        body.addWidget(self.tree, 2)
        body.addWidget(self.canvas, 4)
        body.addWidget(self.inspector, 3)
        outer.addLayout(body, 1)

        self.status = QLabel("OAM 3/128   AFFINE 3/32   OBJ VRAM 5/1024")
        outer.addWidget(self.status)

    def apply(self, c: dict[str, str]):
        self.setStyleSheet(f"""
            Preview {{ background: {c['BG_DEEP']}; }}
            QLabel {{ color: {TEXT_HI}; background: transparent; padding: 2px 6px; }}
            QPushButton {{ color: {TEXT_HI}; background: {c['BG_RAISED']};
                           border: 1px solid {c['BORDER']}; padding: 5px 12px; }}
            QPushButton:hover {{ background: {c['BG_HOVER']}; }}
            QPushButton#tab {{ border: none; background: transparent; }}
            QPushButton#tab_active {{ border: none; background: {c['BG_SEL']}; }}
            QLineEdit, QPlainTextEdit {{ color: {TEXT_HI}; background: {c['BG_INPUT']};
                           border: 1px solid {c['BORDER_MID']}; padding: 3px; }}
        """)
        self.toolbar.setStyleSheet(
            f"QFrame {{ background: {c['BG_RAISED']}; border-bottom: 2px solid {SPLITTER}; }}")
        self.tree.setStyleSheet(
            f"QFrame {{ background: {c['BG_BASE']}; border-right: 2px solid {SPLITTER}; }}")
        self.canvas.setStyleSheet(f"QFrame {{ background: {c['BG_DEEP']}; }}")
        self.inspector.setStyleSheet(
            f"QFrame {{ background: {c['BG_PANEL']}; border-left: 2px solid {SPLITTER}; }}")
        self.selected.setStyleSheet(
            f"background: {c['BG_SEL']}; border-left: 2px solid {ACCENT}; color: {TEXT_HI};")
        self.hovered.setStyleSheet(f"background: {c['BG_HOVER']}; color: {TEXT_HI};")
        self.status.setStyleSheet(
            f"background: {c['BG_DEEP']}; color: {TEXT_DIM}; border-top: 2px solid {SPLITTER};"
            "padding: 4px 8px;")


class Tuner(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Thème clair : réglage du blanc")
        self.resize(1100, 640)
        defaults = read_light_defaults()
        self.defaults = dict(defaults)
        self._shifting = False

        root = QHBoxLayout(self)
        controls = QVBoxLayout()
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self.rows: list[SurfaceRow] = []
        for index, (key, label) in enumerate(SURFACES):
            self.rows.append(SurfaceRow(grid, index, key, label, defaults[key], self.refresh))
        controls.addLayout(grid)

        self.shift = QSlider(Qt.Orientation.Horizontal)
        self.shift.setRange(-60, 30)
        self.shift.setValue(0)
        self.shift.valueChanged.connect(self.shift_all)
        self.shift_label = QLabel("Tout décaler : 0")
        controls.addWidget(self.shift_label)
        controls.addWidget(self.shift)

        self.keep_order = QCheckBox("Garder l'ordre profond < base < widgets < menus")
        self.keep_order.setChecked(True)
        self.keep_order.toggled.connect(self.refresh)
        controls.addWidget(self.keep_order)

        reset = QPushButton("Revenir aux valeurs du thème")
        reset.clicked.connect(self.reset)
        controls.addWidget(reset)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(130)
        controls.addWidget(self.output)
        copy = QPushButton("Copier pour theme.py")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.output.toPlainText()))
        controls.addWidget(copy)
        controls.addStretch()

        self.preview = Preview()
        root.addLayout(controls, 2)
        root.addWidget(self.preview, 3)
        self.refresh()

    def shift_all(self, amount: int):
        self.shift_label.setText(f"Tout décaler : {amount:+d}")
        self._shifting = True
        for row in self.rows:
            row.set_value(self.defaults[row.key] + amount)
        self._shifting = False
        self.refresh()

    def reset(self):
        self.shift.setValue(0)
        for row in self.rows:
            row.set_value(self.defaults[row.key])

    def colors(self) -> dict[str, str]:
        return {row.key: gray(row.value()) for row in self.rows}

    def refresh(self, *_):
        if self._shifting:
            return
        colors = self.colors()
        for row in self.rows:
            row.swatch.setStyleSheet(
                f"background: {colors[row.key]}; border: 1px solid #888;")
        self.preview.apply(colors)
        lines = [f'    {key}="{value}",' for key, value in colors.items()]
        self.output.setPlainText("\n".join(lines))
        if self.keep_order.isChecked():
            by_key = {row.key: row.value() for row in self.rows}
            ramp = [by_key[k] for k in ("BG_DEEP", "BG_BASE", "BG_PANEL", "BG_RAISED")]
            ok = ramp == sorted(ramp)
            self.output.setStyleSheet("" if ok else "color: #c62828;")
            if not ok:
                self.output.setPlainText("# ordre inversé (profond < base < widgets < menus)\n"
                                         + self.output.toPlainText())


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Tuner()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
