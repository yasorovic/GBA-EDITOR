"""`FieldBinder` — le pont champ↔widget des inspecteurs (cf. ui/common/field_binder).

Ce que ces tests tiennent, c'est le contrat du binder, indépendamment de tout
inspecteur :
  - `load` repeuple les widgets SANS déclencher de mutation ;
  - une édition utilisateur passe la valeur par `set_field(name, valeur)` ;
  - un `QComboBox` traduit index ↔ valeur de modèle via sa table `values` ;
  - un widget non couvert LÈVE à la liaison (un inspecteur natif échoue fort).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLabel, QSpinBox

from ui.common.field_binder import FieldBinder


def _binder():
    """Un binder et la liste des (name, value) qu'il pousse — la trace des
    mutations, à la place du `_set` réel d'un inspecteur."""
    calls: list[tuple[str, object]] = []
    return FieldBinder(lambda name, val: calls.append((name, val))), calls


def test_load_peuple_sans_emettre(qapp):
    b, calls = _binder()
    check = b.bind("visible", QCheckBox())
    spin = b.bind("priority", QSpinBox()); spin.setRange(0, 3)
    dbl = b.bind("scale", QDoubleSpinBox()); dbl.setRange(0.0, 4.0); dbl.setSingleStep(0.1)

    b.load(SimpleNamespace(visible=True, priority=2, scale=1.5))

    assert check.isChecked() is True
    assert spin.value() == 2
    assert dbl.value() == pytest.approx(1.5)
    assert calls == []          # repeupler n'est pas muter


def test_edition_utilisateur_passe_par_set_field(qapp):
    b, calls = _binder()
    check = b.bind("visible", QCheckBox())
    spin = b.bind("priority", QSpinBox()); spin.setRange(0, 3)

    check.setChecked(True)
    spin.setValue(3)

    assert ("visible", True) in calls
    assert ("priority", 3) in calls


def test_combobox_traduit_index_et_valeur(qapp):
    b, calls = _binder()
    combo = QComboBox(); combo.addItems(["Normal", "Masque"])
    b.bind("obj_mode", combo, values=[0, 2])

    # valeur de modèle → index
    b.load(SimpleNamespace(obj_mode=2))
    assert combo.currentIndex() == 1

    # index → valeur de modèle
    combo.setCurrentIndex(0)
    assert ("obj_mode", 0) in calls


def test_combobox_sans_values_leve(qapp):
    b, _ = _binder()
    with pytest.raises(TypeError):
        b.bind("obj_mode", QComboBox())


def test_widget_non_couvert_leve(qapp):
    b, _ = _binder()
    with pytest.raises(TypeError):
        b.bind("x", QLabel())
