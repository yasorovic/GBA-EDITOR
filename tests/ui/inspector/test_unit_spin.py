"""`UnitSpin` : un champ entier dont l'unité est DEHORS, et la charte qui en découle.

Un `QSpinBox` + `setSuffix` met l'unité dans le texte édité (le curseur s'y promène, la sélection l'emporte). Le texte du champ
ne doit être que le nombre ; l'unité se lit à côté, comme le « px » d'un `ValueField`."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_DIR / "editor"))

from ui.common.unit_spin import UnitSpin                      # noqa: E402


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


def test_no_screen_puts_a_unit_inside_an_editable_spinbox():
    """La charte : une unité s'écrit avec `UnitSpin`, jamais avec `QSpinBox.setSuffix` / `setPrefix`. Seuls l'unité elle-même et le
    champ numérique à mode (`NumberField`, dont le bouton de droite est déjà pris) la posent encore dans un QSpinBox."""
    import re
    allowed = {"ui/common/unit_spin.py", "ui/common/value_field.py"}
    made = re.compile(r"([\w.]+)\s*=\s*(?:QSpinBox|QDoubleSpinBox|W\.spinbox|W\.double_spinbox)\(")
    offenders = []
    for path in (REPO_DIR / "editor" / "ui").rglob("*.py"):
        rel = path.relative_to(REPO_DIR / "editor").as_posix()
        if rel in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for name in set(made.findall(text)):
            for call in ("setSuffix", "setPrefix"):
                if f"{name}.{call}(" in text:
                    offenders.append(f"{rel}: {name}.{call}")
    assert offenders == []
