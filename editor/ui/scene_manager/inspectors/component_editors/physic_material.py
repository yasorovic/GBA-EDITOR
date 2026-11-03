"""Éditeur du PhysicMaterialComponent."""
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.widgets import W
from . import BaseComponentEditor, register, LABEL_WIDTH


@register("physic_material")
class PhysicMaterialEditor(BaseComponentEditor):
    def build(self, comp, row, layout):
        restitution = W.double_spinbox(comp.restitution, 0.0, 1.0, 0.05, 2)
        restitution.setObjectName("materialRestitution")
        restitution.setToolTip(tooltip(title=label("comped.material_restitution"),
                                       body=label("comped.material_restitution_tip")))
        W.row(label("comped.material_restitution"), restitution, layout, LABEL_WIDTH)

        friction = W.double_spinbox(comp.friction, 0.0, 1.0, 0.05, 2)
        friction.setObjectName("materialFriction")
        friction.setToolTip(tooltip(title=label("comped.material_friction"),
                                    body=label("comped.material_friction_tip")))
        W.row(label("comped.material_friction"), friction, layout, LABEL_WIDTH)

        restitution.valueChanged.connect(lambda v: self.set_field(comp, "restitution", float(v)))
        friction.valueChanged.connect(lambda v: self.set_field(comp, "friction", float(v)))
        self.register_syncer("restitution", lambda v, w=restitution: w.setValue(float(v)))
        self.register_syncer("friction", lambda v, w=friction: w.setValue(float(v)))
