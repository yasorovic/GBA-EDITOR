"""Éditeur du mode de corps physique."""
from PyQt6.QtWidgets import QCheckBox, QComboBox

from core.models.components import (
    PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_MODES,
    PHYSICS_BODY_RIGID, PHYSICS_BODY_STATIC, CollisionShapeComponent,
)
from ui.common import icons
from ui.common.labels import label
from ui.common.notice import note
from ui.common.theme import C
from ui.common.tooltip import tooltip
from ui.common.widgets import AssetPickerPopup, ScriptSlot, W
from . import BaseComponentEditor, register


@register("physics_body")
class PhysicsBodyEditor(BaseComponentEditor):
    def build(self, comp, row, layout):
        mode = QComboBox()
        labels = {
            PHYSICS_BODY_STATIC: label("comped.physics_static"),
            PHYSICS_BODY_CHARACTER: label("comped.physics_character"),
            PHYSICS_BODY_KINEMATIC: label("comped.physics_kinematic"),
            PHYSICS_BODY_RIGID: label("comped.physics_rigid"),
        }
        for value in PHYSICS_BODY_MODES:
            mode.addItem(labels[value], value)
        mode.setCurrentIndex(max(0, mode.findData(comp.mode)))
        row(label("comped.physics_mode"), mode)

        owner = getattr(self.insp, "_actor", None)
        colliders = [c for c in getattr(owner, "components", [])
                     if isinstance(c, CollisionShapeComponent)]
        collider_icon = icons.get("view_collision", C.TEXT_DIM)
        collider = ScriptSlot(add_label=label("comped.physics_choose_collider"),
                              accent_color=C.ACCENT, show_clear=True)
        collider.setToolTip(tooltip(title=label("comped.physics_collider"),
                                    body=label("comped.physics_collider_tip")))

        def collider_text(box):
            return f"{box.id} [{box.tag}]" if box.tag else box.id

        def show_collider(value):
            found = next((box for box in colliders if box.id == value), None)
            if found is not None:
                collider.set_script(collider_text(found), icon=collider_icon)
            elif value:
                collider.set_script(label("comped.physics_collider_missing", name=value))
            else:
                collider.set_script(label("comped.physics_collider_legacy"), icon=collider_icon)

        def open_collider_picker():
            entries = [(collider_text(box), box.id, collider_icon) for box in colliders]
            popup = AssetPickerPopup(entries, C.ACCENT, parent=collider, new_label=None)
            popup.picked.connect(lambda value: (
                self.set_field(comp, "collider_id", value), show_collider(value)))
            popup.show_below(collider)

        collider.set_callbacks(
            on_add=open_collider_picker,
            on_open=open_collider_picker,
            on_clear=lambda: (self.set_field(comp, "collider_id", ""), show_collider("")),
        )
        row(label("comped.physics_collider"), collider)
        static_note = note(layout, "physics.static_body")
        character_note = note(layout, "physics.character_body")
        kinematic_note = note(layout, "physics.kinematic_body")

        mass = W.double_spinbox(comp.mass, 0.1, 100.0, 0.1, 2)
        mass.setObjectName("physicsMass")
        mass.setToolTip(tooltip(title=label("comped.physics_mass"),
                                body=label("comped.physics_mass_tip")))
        row(label("comped.physics_mass"), mass)
        mass_row = layout.itemAt(layout.count() - 1).widget()

        gravity_scale = W.double_spinbox(comp.gravity_scale, -8.0, 8.0, 0.1, 2)
        gravity_scale.setObjectName("physicsGravityScale")
        gravity_scale.setToolTip(tooltip(title=label("comped.physics_gravity_scale"),
                                         body=label("comped.physics_gravity_scale_tip")))
        row(label("comped.physics_gravity_scale"), gravity_scale)
        gravity_row = layout.itemAt(layout.count() - 1).widget()

        can_sleep = QCheckBox()
        can_sleep.setObjectName("physicsCanSleep")
        can_sleep.setChecked(comp.can_sleep)
        can_sleep.setToolTip(tooltip(title=label("comped.physics_can_sleep"),
                                     body=label("comped.physics_can_sleep_tip")))
        row(label("comped.physics_can_sleep"), can_sleep)
        sleep_row = layout.itemAt(layout.count() - 1).widget()

        def sync_number(widget, value):
            widget.blockSignals(True)
            widget.setValue(float(value))
            widget.blockSignals(False)

        def sync_check(widget, value):
            widget.blockSignals(True)
            widget.setChecked(bool(value))
            widget.blockSignals(False)

        def show_mode(value):
            is_rigid = value == PHYSICS_BODY_RIGID
            static_note.show_text() if value == PHYSICS_BODY_STATIC else static_note.clear()
            character_note.show_text() if value == PHYSICS_BODY_CHARACTER else character_note.clear()
            kinematic_note.show_text() if value == PHYSICS_BODY_KINEMATIC else kinematic_note.clear()
            for widget in (mass_row, gravity_row, sleep_row):
                widget.setVisible(is_rigid)

        def show_value(value):
            mode.blockSignals(True)
            mode.setCurrentIndex(max(0, mode.findData(value)))
            mode.blockSignals(False)
            show_mode(value)

        def changed():
            value = mode.currentData()
            self.set_field(comp, "mode", value)
            show_mode(value)

        mode.currentIndexChanged.connect(changed)
        mass.valueChanged.connect(lambda value: self.set_field(comp, "mass", float(value)))
        gravity_scale.valueChanged.connect(
            lambda value: self.set_field(comp, "gravity_scale", float(value)))
        can_sleep.toggled.connect(lambda value: self.set_field(comp, "can_sleep", bool(value)))
        self.register_syncer("mode", show_value)
        self.register_syncer("collider_id", show_collider)
        self.register_syncer("mass", lambda value: sync_number(mass, value))
        self.register_syncer("gravity_scale", lambda value: sync_number(gravity_scale, value))
        self.register_syncer("can_sleep", lambda value: sync_check(can_sleep, value))
        show_collider(comp.collider_id)
        show_value(comp.mode)
