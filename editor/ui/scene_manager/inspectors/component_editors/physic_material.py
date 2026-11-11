"""Éditeur du PhysicMaterialComponent."""
from ui.common.labels import label
from ui.common.field_binder import FieldBinder
from ui.common.tooltip import tooltip
from ui.common.widgets import W
from . import BaseComponentEditor, register, LABEL_WIDTH


@register("physic_material")
class PhysicMaterialEditor(BaseComponentEditor):
    def build(self, comp, row, layout):
        self._fields = FieldBinder(lambda field, value: self.set_field(self.comp, field, value))
        restitution = self._fields.bind("restitution", W.double_spinbox(0.0, 0.0, 1.0, 0.05, 2))
        restitution.setObjectName("materialRestitution")
        restitution.setToolTip(tooltip(title=label("comped.material_restitution"),
                                       body=label("comped.material_restitution_tip")))
        W.row(label("comped.material_restitution"), restitution, layout, LABEL_WIDTH)

        friction = self._fields.bind("friction", W.double_spinbox(0.0, 0.0, 1.0, 0.05, 2))
        friction.setObjectName("materialFriction")
        friction.setToolTip(tooltip(title=label("comped.material_friction"),
                                    body=label("comped.material_friction_tip")))
        W.row(label("comped.material_friction"), friction, layout, LABEL_WIDTH)

        self.reload(comp)

    def reload(self, comp) -> bool:
        self.comp = comp
        self._fields.load(comp)
        return True
