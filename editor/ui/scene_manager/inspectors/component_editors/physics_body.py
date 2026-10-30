"""Éditeur du mode de corps physique."""
from PyQt6.QtWidgets import QComboBox

from core.models.components import PHYSICS_BODY_MODES
from ui.common.labels import label
from . import BaseComponentEditor, register


@register("physics_body")
class PhysicsBodyEditor(BaseComponentEditor):
    def build(self, comp, row, layout):
        mode = QComboBox()
        labels = {
            "character": label("comped.physics_character"),
            "static": label("comped.physics_static"),
        }
        for value in PHYSICS_BODY_MODES:
            mode.addItem(labels[value], value)
        mode.setCurrentIndex(max(0, mode.findData(comp.mode)))
        row(label("comped.physics_mode"), mode)
        mode.currentIndexChanged.connect(
            lambda _: self.set_field(comp, "mode", mode.currentData()))
        self.register_syncer("mode", lambda value, w=mode: w.setCurrentIndex(max(0, w.findData(value))))
