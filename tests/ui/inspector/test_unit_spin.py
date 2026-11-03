"""`UnitSpin` : un champ entier dont l'unité est DEHORS, et la charte qui en découle.

Un `QSpinBox` + `setSuffix` met l'unité dans le texte édité (le curseur s'y promène, la sélection l'emporte). Le texte du champ
ne doit être que le nombre ; l'unité se lit à côté, comme le « px » d'un `ValueField`."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_DIR / "editor"))

from ui.common.unit_spin import UnitDoubleSpin, UnitSpin      # noqa: E402


def test_the_edited_text_is_only_the_number(qapp):
    spin = UnitSpin()
    spin.setRange(0, 100)
    spin.setSuffix(" %")
    spin.setValue(50)
    assert spin.field.text() == "50"
    assert spin._unit.text() == "%" and not spin._unit.isHidden()


def test_a_prefix_becomes_a_caption_before_the_field(qapp):
    spin = UnitSpin()
    spin.setPrefix("Window ")
    spin.setValue(3)
    assert spin.field.text() == "3" and spin._lead.text() == "Window" and not spin._lead.isHidden()


def test_the_unit_hides_next_to_a_word_and_comes_back(qapp):
    spin = UnitSpin()
    spin.setRange(0, 255)
    spin.setSuffix(" ticks")
    spin.setSpecialValueText("From animation")
    assert spin.value() == 0 and spin._unit.isHidden()
    spin.setValue(4)
    assert not spin._unit.isHidden()


def test_it_speaks_like_a_spinbox(qapp):
    spin = UnitSpin()
    spin.setRange(2, 255)
    seen = []
    spin.valueChanged.connect(seen.append)
    spin.setValue(30)
    assert (spin.value(), seen, spin.minimum(), spin.maximum()) == (30, [30], 2, 255)
    spin.blockSignals(True)
    spin.setValue(40)
    spin.blockSignals(False)
    assert spin.value() == 40 and seen == [30]                 # un écran qui pose une valeur sans l'émettre n'est pas surpris


def test_a_decimal_spin_keeps_the_unit_outside_the_text(qapp):
    spin = UnitDoubleSpin()
    spin.setRange(-8.0, 8.0)
    spin.setDecimals(2)
    spin.setSuffix(" px/f²")
    spin.setValue(0.25)
    assert spin.field.text() == "0.25" or spin.field.text() == "0,25"
    assert spin._unit.text() == "px/f²" and not spin._unit.isHidden()
    seen = []
    spin.valueChanged.connect(seen.append)
    spin.setValue(0.5)
    assert seen == [0.5]


def test_no_physics_field_carries_its_unit_in_the_text(qapp, tmp_path):
    """Le même garde-fou que ci-dessous, mais sur les écrans construits : il voit ce que le texte du source cache (champ créé dans
    une expression conditionnelle, réglé dans une boucle)."""
    from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox
    from core.models.scene import Scene
    from core.project import Project
    from ui.scene_manager.inspectors.project_settings_dialog import PhysicsCollisionsPanel
    from ui.scene_manager.inspectors.scene_inspector import SceneInspector

    project = Project(tmp_path)
    scene = Scene(name="Platform")
    project.scenes.append(scene)
    inspector = SceneInspector()
    inspector.load(scene, project)
    panel = PhysicsCollisionsPanel(project)
    offenders = [f"{type(screen).__name__}: {spin.prefix()!r} {spin.suffix()!r}"
                 for screen in (inspector, panel)
                 for spin in screen.findChildren((QSpinBox, QDoubleSpinBox))
                 if spin.prefix() or spin.suffix()]
    assert offenders == []


_RAW_SPIN = r"(?:QSpinBox|QDoubleSpinBox|W\.spinbox|W\.double_spinbox)\("


def _unit_offenders(text: str) -> list[str]:
    """Les `setSuffix` / `setPrefix` posés sur un QSpinBox brut dans ce source, sous la forme `nom.appel`.

    Un champ brut est un nom affecté d'un constructeur de spinbox où que ce soit dans l'instruction (`x = QSpinBox()`, mais aussi
    `x = (W.spinbox(...) if ... else W.double_spinbox(...))`). Le réglage d'une série de champs se fait souvent dans une boucle
    `for x, ... in (champs...)` : sa variable ne vaut que dans le bloc de la boucle (le même nom resservira ailleurs)."""
    import re
    raw = set(re.findall(rf"([\w.]+)\s*=[^\n=]*\b{_RAW_SPIN}", text))
    found = {f"{name}.{call}" for name in raw for call in ("setSuffix", "setPrefix") if f"{name}.{call}(" in text}
    lines = text.splitlines()
    for number, line in enumerate(lines):
        loop = re.match(r"(\s*)for\s+([\w, ]+?)\s+in\b", line)
        if not loop or not any(name in " ".join(lines[number:number + 6]) for name in raw):
            continue
        body = []
        for later in lines[number + 1:]:
            if later.strip() and len(later) - len(later.lstrip()) <= len(loop.group(1)) and not later.lstrip().startswith(")"):
                break
            body.append(later)
        for var in (name.strip() for name in loop.group(2).split(",")):
            found.update(f"{var}.{call}" for call in ("setSuffix", "setPrefix") if any(f"{var}.{call}(" in l for l in body))
    return sorted(found)


def test_the_unit_scan_sees_the_forms_that_used_to_slip_through():
    conditional = ("spin = (W.spinbox(lo, lo, hi, step) if kind == 'int'\n"
                   "        else W.double_spinbox(lo, lo, hi, step, 2))\n"
                   "spin.setSuffix(' px')\n")
    in_a_loop = ("self._x = QDoubleSpinBox()\nself._y = QDoubleSpinBox()\n"
                 "for spin, axis in (\n    (self._x, 'X'),\n    (self._y, 'Y'),\n):\n    spin.setSuffix(' px/f')\n")
    assert _unit_offenders(conditional) == ["spin.setSuffix"]
    assert _unit_offenders(in_a_loop) == ["spin.setSuffix"]
    assert _unit_offenders("spin = UnitSpin()\nspin.setSuffix(' px')\n") == []


def test_no_screen_puts_a_unit_inside_an_editable_spinbox():
    """La charte : une unité s'écrit avec `UnitSpin`, jamais avec `QSpinBox.setSuffix` / `setPrefix`. Seuls l'unité elle-même et le
    champ numérique à mode (`NumberField`, dont le bouton de droite est déjà pris) la posent encore dans un QSpinBox."""
    allowed = {"ui/common/unit_spin.py", "ui/common/value_field.py"}
    offenders = []
    for path in (REPO_DIR / "editor" / "ui").rglob("*.py"):
        rel = path.relative_to(REPO_DIR / "editor").as_posix()
        if rel not in allowed:
            offenders += [f"{rel}: {found}" for found in _unit_offenders(path.read_text(encoding="utf-8"))]
    assert offenders == []
