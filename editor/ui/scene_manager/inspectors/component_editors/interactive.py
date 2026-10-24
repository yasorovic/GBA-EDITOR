"""Éditeur de l'InteractiveComponent : deux sélecteurs (saisie, interaction), puis la zone."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QSpinBox

from core.models.components import (
    INTERACT_AREA_MODES, INTERACT_INPUT_MODES, CollisionBoxComponent, InteractiveComponent,
    displayed_sprite_component, interactive_box_size,
)
from core.models.settings import INTERACTIVE_COLLISION_TAG
from . import BaseComponentEditor, register
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.theme import C
from ui.common.unit_spin import UnitSpin
from ui.common.widgets import W


def _input_labels() -> dict:
    """Appels LITTÉRAUX : `check_ui_text.py` lit les clés du catalogue statiquement."""
    return {"pressed": label("comped.interact_pressed"),
            "hold": label("comped.interact_hold"),
            "released": label("comped.interact_released")}


def _area_labels() -> dict:
    return {"hover": label("comped.interact_hover"),
            "facing": label("comped.interact_facing")}


def _owner_box_tags(owner) -> list[str]:
    """Les tags des boîtes que l'acteur porte déjà, sans doublon, dans l'ordre."""
    tags: list[str] = []
    for c in getattr(owner, "components", []):
        if isinstance(c, CollisionBoxComponent):
            tag = c.tag or "body"
            if tag not in tags:
                tags.append(tag)
    return tags


@register("interactive")
class InteractiveEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        # ── Saisie : le geste sur l'entrée interne `interact` ─────────
        inputs = _input_labels()
        mode = QComboBox()
        for v in INTERACT_INPUT_MODES:
            mode.addItem(inputs[v], v)
        mode.setCurrentIndex(max(0, mode.findData(comp.input_mode)))
        mode.setToolTip(tooltip(title=label("comped.interact_input"),
                                body=label("comped.interact_input_tip")))
        row(label("comped.interact_input"), mode)

        hold = UnitSpin()
        hold.setRange(1, 600)
        hold.setSuffix(" f")
        hold.setValue(comp.hold_frames)
        hold.setToolTip(tooltip(title=label("comped.interact_hold_frames"),
                                body=label("comped.interact_hold_frames_tip")))
        row(label("comped.interact_hold_frames"), hold)
        hold_row = layout.itemAt(layout.count() - 1).widget()     # la ligne entière, pour la masquer

        # ── Interaction : comment l'interacteur atteint la zone ───────
        areas = _area_labels()
        area = QComboBox()
        for v in INTERACT_AREA_MODES:
            area.addItem(areas[v], v)
        area.setCurrentIndex(max(0, area.findData(comp.interaction)))
        area.setToolTip(tooltip(title=label("comped.interact_area"),
                                body=label("comped.interact_area_tip")))
        row(label("comped.interact_area"), area)

        # ── Zone : la boîte du composant, ou une boîte déjà posée ─────
        owner = getattr(self.insp, "_actor", None)
        existing = _owner_box_tags(owner)
        box = QComboBox()
        box.addItem(label("comped.interact_own_box", tag=INTERACTIVE_COLLISION_TAG), "")
        for tag in existing:
            box.addItem(tag, tag)
        idx = box.findData(comp.box_tag)
        box.setCurrentIndex(idx if idx >= 0 else 0)
        box.setToolTip(tooltip(title=label("comped.interact_box"),
                               body=label("comped.interact_box_tip")))
        row(label("comped.interact_box"), box)

        # « Auto » dit ce qu'il vaut : le cadre du sprite affiché, sinon 16 — la MÊME fonction que le
        # canvas et le build.
        proj = self.insp._project
        shown = displayed_sprite_component(owner) if owner is not None else None
        sprite = proj.get_sprite(shown.sprite_name) if (proj and shown) else None
        auto_w, auto_h = interactive_box_size(
            InteractiveComponent(), sprite.frame_w if sprite else 0, sprite.frame_h if sprite else 0)
        size_w, size_h = QSpinBox(), QSpinBox()
        for sp, value, auto in ((size_w, comp.box_w, auto_w), (size_h, comp.box_h, auto_h)):
            sp.setRange(0, 64)
            sp.setSpecialValueText(label("comped.interact_auto", n=auto))
            sp.setValue(value)
            sp.setToolTip(tooltip(title=label("common.size"),
                                  body=label("comped.interact_size_tip")))
        W.pair(label("common.size"), "W", C.AXIS_X, size_w, "H", C.AXIS_Y, size_h, layout)
        size_row = layout.itemAt(layout.count() - 1).widget()

        def _sync_visibility():
            hold_row.setVisible(comp.input_mode == "hold")
            size_row.setVisible(comp.box_tag == "")        # la boîte d'un autre composant a sa taille

        mode.currentIndexChanged.connect(lambda i: (
            self.set_field(comp, "input_mode", mode.itemData(i)), _sync_visibility()))
        hold.valueChanged.connect(lambda v: self.set_field(comp, "hold_frames", int(v)))
        area.currentIndexChanged.connect(
            lambda i: self.set_field(comp, "interaction", area.itemData(i)))
        box.currentIndexChanged.connect(lambda i: (
            self.set_field(comp, "box_tag", box.itemData(i) or ""), _sync_visibility()))
        size_w.valueChanged.connect(lambda v: self.set_field(comp, "box_w", int(v)))
        size_h.valueChanged.connect(lambda v: self.set_field(comp, "box_h", int(v)))
        _sync_visibility()

