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
from ui.common.widgets import PickerEntry, PickerSlot, W
from . import BaseComponentEditor, register, LABEL_WIDTH


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
        mode.setToolTip(tooltip(title=label("comped.physics_mode"),
                                body=label("comped.physics_mode_tip")))
        W.row(label("comped.physics_mode"), mode, layout, LABEL_WIDTH)

        owner = getattr(self.insp, "_actor", None)
        colliders = [c for c in getattr(owner, "components", [])
                     if isinstance(c, CollisionShapeComponent)]
        collider_icon = icons.get("view_collision", C.TEXT_DIM)
        def describe_collider(value):
            found = next((box for box in colliders if box.id == value), None)
            if found is not None:
                text = f"{found.id} [{found.tag}]" if found.tag else found.id
                return PickerEntry(text, value, collider_icon)
            if value:
                return PickerEntry(label("comped.physics_collider_missing", name=value), value, missing=True)
            return PickerEntry(label("comped.physics_collider_legacy"), "", collider_icon)

        collider = PickerSlot(
            label("comped.physics_choose_collider"), C.ACCENT,
            lambda: [describe_collider(box.id) for box in colliders], describe_collider,
            lambda value: self.set_field(comp, "collider_id", value),
            on_cleared=lambda: self.set_field(comp, "collider_id", ""), cleared_value="")
        collider.setToolTip(tooltip(title=label("comped.physics_collider"),
                                    body=label("comped.physics_collider_tip")))
        W.row(label("comped.physics_collider"), collider, layout, LABEL_WIDTH)
        static_note = note(layout, "physics.static_body")
        character_note = note(layout, "physics.character_body")
        kinematic_note = note(layout, "physics.kinematic_body")

        mass = W.double_spinbox(comp.mass, 0.1, 100.0, 0.1, 2)
        mass.setObjectName("physicsMass")
        mass.setToolTip(tooltip(title=label("comped.physics_mass"),
                                body=label("comped.physics_mass_tip")))
        W.row(label("comped.physics_mass"), mass, layout, LABEL_WIDTH)
        mass_row = layout.itemAt(layout.count() - 1).widget()

        use_gravity = QCheckBox()
        use_gravity.setObjectName("physicsUseSceneGravity")
        use_gravity.setChecked(comp.use_scene_gravity)
        use_gravity.setToolTip(tooltip(title=label("comped.physics_use_scene_gravity"),
                                       body=label("comped.physics_use_scene_gravity_tip")))
        W.row(label("comped.physics_use_scene_gravity"), use_gravity, layout, LABEL_WIDTH)
        use_gravity_row = layout.itemAt(layout.count() - 1).widget()

        gravity_scale = W.double_spinbox(comp.gravity_scale, -8.0, 8.0, 0.1, 2)
        gravity_scale.setObjectName("physicsGravityScale")
        gravity_scale.setToolTip(tooltip(title=label("comped.physics_gravity_scale"),
                                         body=label("comped.physics_gravity_scale_tip")))
        W.row(label("comped.physics_gravity_scale"), gravity_scale, layout, LABEL_WIDTH)
        gravity_row = layout.itemAt(layout.count() - 1).widget()

        can_sleep = QCheckBox()
        can_sleep.setObjectName("physicsCanSleep")
        can_sleep.setChecked(comp.can_sleep)
        can_sleep.setToolTip(tooltip(title=label("comped.physics_can_sleep"),
                                     body=label("comped.physics_can_sleep_tip")))
        W.row(label("comped.physics_can_sleep"), can_sleep, layout, LABEL_WIDTH)
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
            has_gravity_option = value in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC)
            use_gravity_row.setVisible(has_gravity_option)
            gravity_row.setVisible(is_rigid or (has_gravity_option and use_gravity.isChecked()))
            for widget in (mass_row, sleep_row):
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
        use_gravity.toggled.connect(lambda value: (
            self.set_field(comp, "use_scene_gravity", bool(value)), show_mode(mode.currentData())))
        self.register_syncer("mode", show_value)
        self.register_syncer("collider_id", collider.set_value)
        self.register_syncer("mass", lambda value: sync_number(mass, value))
        self.register_syncer("gravity_scale", lambda value: sync_number(gravity_scale, value))
        self.register_syncer("can_sleep", lambda value: sync_check(can_sleep, value))
        self.register_syncer("use_scene_gravity", lambda value: (
            sync_check(use_gravity, value), show_mode(mode.currentData())))
        collider.set_value(comp.collider_id)
        show_value(comp.mode)
