"""Éditeur du CollisionShapeComponent."""
from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QWidget
from PyQt6.QtGui import QFont

from . import BaseComponentEditor, register, LABEL_WIDTH
from ui.common import icons
from ui.common.widgets import AssetPickerPopup, ScriptSlot, W
from ui.common.notice import notice
from ui.common.tooltip import tooltip
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.pickers import collision_tag_slot
from ui.common.icons import COLOR_SPRITE
from core.history import get_history, AddListItemCmd
from core.models.components import ONE_WAY_MODES, PhysicMaterialComponent


@register("collision_shape")
class CollisionEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        is_solid = getattr(comp, "solid", True)

        # ── Tag ─────────────────────────────────────────────────────
        # Distinct de l'"id" de la meta_bar : l'id distingue les boxes de
        # CET acteur (utile avec plusieurs CollisionShapeComponent, ex.
        # "head_hurtbox" / "body_hurtbox") ; le tag est le GROUPE de
        # collision, partagé entre acteurs, celui que lit la matrice de
        # Project Settings > Physics & Collisions et que le codegen émet en
        # BOXTAG_<TAG> (cf. codegen/runtime_codegen/headers.py). Les deux
        # étaient confondus avant le tag registry (2026-08-25) — plus
        # aujourd'hui, chacun peut varier indépendamment.
        proj = self.insp._project
        current = getattr(comp, "tag", "body") or "body"

        def _commit_tag(name: str):
            self.set_field(comp, "tag", name.strip() or "body")

        def _create_tag(name: str):
            # Création = déclaration au niveau projet (Project Settings >
            # Collisions) PUIS affectation : le tag existe pour toutes les boîtes.
            name = name.strip()
            if name and name not in proj.collision_tags():
                get_history().push(AddListItemCmd(
                    proj.settings.collision_tags, name,
                    label=f"Déclarer le tag {name}",
                    persist_fn=proj.save_settings))
            _commit_tag(name)

        tag_slot = collision_tag_slot(
            proj.collision_tags(), current, COLOR_SPRITE, _commit_tag, _create_tag, parent=self.insp)
        notice("collision.tag", tag_slot, layout)
        self.register_syncer("tag", lambda v, w=tag_slot: w.set_script(str(v) or "body"))
        W.row(label("comped.tag"), tag_slot, layout, LABEL_WIDTH)

        # ── Mode Solid / Trigger ──────────────────────────────────
        chk_solid = QCheckBox()
        chk_solid.setChecked(is_solid)
        notice("collision.solid", chk_solid, layout)

        mode_lbl = QWidget()
        hl = QHBoxLayout(mode_lbl); hl.setSpacing(6); hl.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label("comped.collision_solid"))
        lbl.setFont(QFont(T.UI, T.SM))
        lbl.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent; border:none;")
        hl.addWidget(chk_solid); hl.addWidget(lbl); hl.addStretch()
        W.row(label("common.mode"), mode_lbl, layout, LABEL_WIDTH)

        # ── Blocage entre acteurs ─────────────────────────────────
        # Une réponse à part de « Solid » (qui ne parle que de la carte) : Block repousse le Character
        # mobile, Sensor ne fait que signaler le contact.
        chk_blocks = QCheckBox(label("comped.collision_blocks"))
        chk_blocks.setFont(QFont(T.UI, T.SM))
        chk_blocks.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent;")
        chk_blocks.setChecked(getattr(comp, "response", "sensor") == "block")
        chk_blocks.setToolTip(tooltip(title=label("comped.collision_blocks"),
                                      body=label("comped.collision_blocks_tip")))
        W.row(label("comped.collision_blocks_row"), chk_blocks, layout, LABEL_WIDTH)
        chk_blocks.toggled.connect(lambda v: self.set_field(comp, "response", "block" if v else "sensor"))
        self.register_syncer("response", lambda v, w=chk_blocks: (
            w.blockSignals(True), w.setChecked(v == "block"), w.blockSignals(False)))

        # ── Sens unique : la face n'arrête que le corps venu du côté de sa normale ──
        one_way = QComboBox()
        for value in ONE_WAY_MODES:
            one_way.addItem(label(f"comped.one_way_{value}"), value)
        one_way.setCurrentIndex(max(0, one_way.findData(comp.one_way)))
        one_way.setToolTip(tooltip(title=label("comped.collision_one_way"),
                                   body=label("comped.collision_one_way_tip")))
        W.row(label("comped.collision_one_way"), one_way, layout, LABEL_WIDTH)
        one_way.currentIndexChanged.connect(lambda _: self.set_field(comp, "one_way", one_way.currentData()))
        self.register_syncer("one_way", lambda v, w=one_way: (
            w.blockSignals(True), w.setCurrentIndex(max(0, w.findData(v))), w.blockSignals(False)))

        # ── Matériau : un PhysicMaterialComponent du même acteur, désigné par son id ──
        owner = getattr(self.insp, "_actor", None)
        materials = [c for c in getattr(owner, "components", []) if isinstance(c, PhysicMaterialComponent)]
        material_icon = icons.get("view_collision", C.TEXT_DIM)
        material = ScriptSlot(add_label=label("comped.collision_choose_material"),
                              accent_color=C.ACCENT, show_clear=True)
        material.setToolTip(tooltip(title=label("comped.collision_material"),
                                    body=label("comped.collision_material_tip")))

        def show_material(value):
            if next((m for m in materials if m.id == value), None) is not None:
                material.set_script(value, icon=material_icon)
            elif value:
                material.set_script(label("comped.collision_material_missing", name=value))
            else:
                material.set_script(label("comped.collision_material_none"), icon=material_icon)

        def open_material_picker():
            entries = [(m.id, m.id, material_icon) for m in materials]
            popup = AssetPickerPopup(entries, C.ACCENT, parent=material, new_label=None)
            popup.picked.connect(lambda value: (
                self.set_field(comp, "material_id", value), show_material(value)))
            popup.show_below(material)

        material.set_callbacks(
            on_add=open_material_picker,
            on_open=open_material_picker,
            on_clear=lambda: (self.set_field(comp, "material_id", ""), show_material("")),
        )
        W.row(label("comped.collision_material"), material, layout, LABEL_WIDTH)
        show_material(comp.material_id)
        self.register_syncer("material_id", show_material)

        # ── AABB — champs px/tile ou référence de variable ────────
        # Les valeurs peuvent être un littéral (px/tile) ou pointer une
        # variable déclarée (global g_<nom> / constante CONST_<NOM>).
        vf_x = W.value_field(getattr(comp, "x", 0), project=proj)
        vf_y = W.value_field(getattr(comp, "y", 0), project=proj)
        vf_w = W.value_field(getattr(comp, "w", 16), project=proj, min_px=1)
        vf_h = W.value_field(getattr(comp, "h", 16), project=proj, min_px=1)

        # La clé de notice est ÉCRITE, pas construite : `f"collision.{fname}"`
        # se lit bien mais échappe au contrôle catalogue ↔ code, qui ne sait
        # pas à quoi il se résoudra.
        for vf, fname, key in ((vf_x, "x", "collision.x"),
                               (vf_y, "y", "collision.y"),
                               (vf_w, "w", "collision.w"),
                               (vf_h, "h", "collision.h")):
            vf.changed.connect(lambda raw, f=fname: self.set_field(comp, f, raw))
            self.register_syncer(fname, lambda v, w=vf: w.set_raw(v))
            notice(key, vf, layout)

        W.pair(label("comped.offset"), "X", C.AXIS_X, vf_x, "Y", C.AXIS_Y, vf_y, layout, LABEL_WIDTH)
        W.pair(label("common.size"), "W", C.AXIS_X, vf_w, "H", C.AXIS_Y, vf_h, layout, LABEL_WIDTH)

        def _on_solid(v):
            self.set_field(comp, "solid", v)

        chk_solid.toggled.connect(_on_solid)
        self.register_syncer("solid", lambda v, w=chk_solid: (
            w.blockSignals(True), w.setChecked(bool(v)), w.blockSignals(False)))

