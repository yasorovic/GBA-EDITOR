"""Éditeur du mode de corps physique."""
from PyQt6.QtWidgets import QCheckBox, QComboBox

from core.models.components import (
    PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_MODES,
    PHYSICS_BODY_RIGID, PHYSICS_BODY_STATIC, CollisionShapeComponent,
)
from ui.common import icons
from ui.common.field_binder import FieldBinder
from ui.common.labels import label
from ui.common.notice import note
from ui.common.theme import C
from ui.common.tooltip import tooltip
from ui.common.widgets import PickerEntry, PickerSlot, W
from . import BaseComponentEditor, register, LABEL_WIDTH


@register("physics_body")
class PhysicsBodyEditor(BaseComponentEditor):
    def meta_inline(self, comp):
        """Le Mode (nature du corps) prend la place de l'id — un physics body est
        unique par acteur, donc sans id. Construit avant la barre meta, son
        `FieldBinder` est réutilisé par `build`."""
        self.comp = comp
        self._fields = FieldBinder(lambda field, value: self.set_field(self.comp, field, value))
        mode = QComboBox()
        labels = {
            PHYSICS_BODY_STATIC: label("comped.physics_static"),
            PHYSICS_BODY_CHARACTER: label("comped.physics_character"),
            PHYSICS_BODY_KINEMATIC: label("comped.physics_kinematic"),
            PHYSICS_BODY_RIGID: label("comped.physics_rigid"),
        }
        for value in PHYSICS_BODY_MODES:
            mode.addItem(labels[value], value)
        self._fields.bind("mode", mode, values=list(PHYSICS_BODY_MODES))
        mode.setToolTip(tooltip(title=label("comped.physics_mode"), body=label("comped.physics_mode_tip")))
        self._mode = mode
        # La réaction d'affichage (show_mode) est branchée par `build`, qui la
        # définit avec les lignes qu'elle montre ou cache.
        return label("comped.physics_mode"), mode

    def build(self, comp, row, layout):
        # Normalement le Mode est déjà posé dans la barre meta (meta_inline, appelé
        # par l'inspecteur). Sans elle (construction directe), on le remet en ligne
        # pour que l'éditeur reste complet à lui seul.
        if not getattr(self, "_mode", None):
            inline_label, mode = self.meta_inline(comp)
            W.row(inline_label, mode, layout, LABEL_WIDTH)

        def colliders():
            owner = getattr(self.insp, "_actor", None)
            return [c for c in getattr(owner, "components", [])
                    if isinstance(c, CollisionShapeComponent)]

        collider_icon = icons.get("view_collision", C.TEXT_DIM)
        def describe_collider(value):
            found = next((box for box in colliders() if box.id == value), None)
            if found is not None:
                text = f"{found.id} [{found.tag}]" if found.tag else found.id
                return PickerEntry(text, value, collider_icon)
            if value:
                return PickerEntry(label("comped.physics_collider_missing", name=value), value, missing=True)
            return PickerEntry(label("comped.physics_collider_legacy"), "", collider_icon)

        collider = PickerSlot(
            label("comped.physics_choose_collider"), C.ACCENT,
            lambda: [describe_collider(box.id) for box in colliders()], describe_collider,
            lambda value: self.set_field(self.comp, "collider_id", value),
            on_cleared=lambda: self.set_field(self.comp, "collider_id", ""), cleared_value="")
        self._collider = collider
        collider.setToolTip(tooltip(title=label("comped.physics_collider"),
                                    body=label("comped.physics_collider_tip")))
        W.row(label("comped.physics_collider"), collider, layout, LABEL_WIDTH)
        static_note = note(layout, "physics.static_body")
        character_note = note(layout, "physics.character_body")
        kinematic_note = note(layout, "physics.kinematic_body")

        mass = self._fields.bind("mass", W.double_spinbox(comp.mass, 0.1, 100.0, 0.1, 2))
        mass.setObjectName("physicsMass")
        mass.setToolTip(tooltip(title=label("comped.physics_mass"),
                                body=label("comped.physics_mass_tip")))
        W.row(label("comped.physics_mass"), mass, layout, LABEL_WIDTH)
        mass_row = layout.itemAt(layout.count() - 1).widget()

        use_gravity = self._fields.bind("use_scene_gravity", QCheckBox())
        use_gravity.setObjectName("physicsUseSceneGravity")
        use_gravity.setToolTip(tooltip(title=label("comped.physics_use_scene_gravity"),
                                       body=label("comped.physics_use_scene_gravity_tip")))
        W.row(label("comped.physics_use_scene_gravity"), use_gravity, layout, LABEL_WIDTH)
        use_gravity_row = layout.itemAt(layout.count() - 1).widget()

        gravity_scale = self._fields.bind("gravity_scale", W.double_spinbox(comp.gravity_scale, -8.0, 8.0, 0.1, 2))
        gravity_scale.setObjectName("physicsGravityScale")
        gravity_scale.setToolTip(tooltip(title=label("comped.physics_gravity_scale"),
                                         body=label("comped.physics_gravity_scale_tip")))
        W.row(label("comped.physics_gravity_scale"), gravity_scale, layout, LABEL_WIDTH)
        gravity_row = layout.itemAt(layout.count() - 1).widget()

        can_sleep = self._fields.bind("can_sleep", QCheckBox())
        can_sleep.setObjectName("physicsCanSleep")
        can_sleep.setToolTip(tooltip(title=label("comped.physics_can_sleep"),
                                     body=label("comped.physics_can_sleep_tip")))
        W.row(label("comped.physics_can_sleep"), can_sleep, layout, LABEL_WIDTH)
        sleep_row = layout.itemAt(layout.count() - 1).widget()

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

        # Le combo Mode vit dans la barre meta (meta_inline) ; sa réaction d'affichage
        # et celle de la gravité de scène sont branchées ici, où show_mode est défini.
        self._mode.currentIndexChanged.connect(lambda _: show_mode(self._mode.currentData()))
        use_gravity.toggled.connect(lambda _: show_mode(self._mode.currentData()))
        self._show_mode = show_mode
        self.reload(comp)

    def reload(self, comp) -> bool:
        self.comp = comp
        self._fields.load(comp)
        self._collider.set_value(comp.collider_id)
        self._show_mode(comp.mode)
        return True
