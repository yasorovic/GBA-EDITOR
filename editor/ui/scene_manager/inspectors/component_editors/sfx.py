"""Éditeur du SoundFxComponent."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from core.models.components import SFX_AUTO_TRIGGERS
from core.models.settings import BUTTON_NAMES
from . import BaseComponentEditor, register
from ui.common.labels import label
from ui.common.tooltip import tooltip

# CLÉS de libellé pour les trois triggers fixes — résolues par `label()` à
# l'affichage.
_FIXED_LABELS: dict[str, str] = {
    "manual":     "comped.trig_manual",
    "on_spawn":   "comped.trig_on_spawn",
    "on_destroy": "comped.trig_on_destroy",
}


def _button_labels() -> dict:
    """Appels LITTÉRAUX (pas de f-string) : `check_ui_text.py` extrait les
    clés du catalogue par une lecture statique — les mêmes clés que les
    tooltips d'InputsCard (`inputs_card._button_tooltips`), un bouton se
    nomme pareil partout dans l'éditeur."""
    return {
        "up": label('inputs.button_up'), "down": label('inputs.button_down'),
        "left": label('inputs.button_left'), "right": label('inputs.button_right'),
        "a": label('inputs.button_a'), "b": label('inputs.button_b'),
        "l": label('inputs.button_l'), "r": label('inputs.button_r'),
        "start": label('inputs.button_start'), "select": label('inputs.button_select'),
    }


@register("sound_fx")
class SfxEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        proj  = self.insp._project
        if proj:
            proj.load_audio()   # catalogue différé — sur sélection d'acteur, pas à l'ouverture
        names = [s.name for s in proj.sfx.items] if proj else []

        sfx = QComboBox()
        if names:
            sfx.addItems(names)
            if comp.sfx_name in names:
                sfx.setCurrentText(comp.sfx_name)
        else:
            sfx.addItem(label("comped.sfx_none"))
            sfx.setEnabled(False)
        sfx.setToolTip(tooltip(
            title=label("comped.sfx"), note=label("comped.sfx_note")))
        sfx.currentTextChanged.connect(
            lambda v: self.set_field(comp, "sfx_name", v if v in names else None)
        )
        row(label("comped.sfx"), sfx)

        # Le trigger vise un bouton ou une action déclarée (Project Settings →
        # Input → Inputs, jamais une séquence) — la même liste que
        # `input:pressed(nom)` (ROADMAP « Les inputs personnalisés », tranche
        # finale, 2026-09-27, qui a remplacé les dix `on_button_*` fixes).
        button_labels = _button_labels()
        input_names = ([b.name for b in proj.settings.inputs if b.name]
                       if proj else [])
        valid = {"manual", *SFX_AUTO_TRIGGERS, *BUTTON_NAMES, *input_names}

        trigger = QComboBox()
        for v in ("manual", *SFX_AUTO_TRIGGERS):
            trigger.addItem(label(_FIXED_LABELS[v]), v)
        trigger.insertSeparator(trigger.count())
        for v in BUTTON_NAMES:
            trigger.addItem(button_labels[v], v)
        if input_names:
            trigger.insertSeparator(trigger.count())
            for v in input_names:
                trigger.addItem(v, v)
        current = comp.trigger if comp.trigger in valid else "manual"
        idx = trigger.findData(current)
        trigger.setCurrentIndex(idx if idx >= 0 else 0)
        trigger.setToolTip(tooltip(
            title=label("comped.trigger"), body=label("comped.trigger_tip"),
            note=label("comped.trigger_note")))
        trigger.currentIndexChanged.connect(
            lambda i: self.set_field(comp, "trigger", trigger.itemData(i))
        )
        row(label("comped.trigger"), trigger)
