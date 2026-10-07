"""Éditeur du CollisionBoxComponent."""
from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget
from PyQt6.QtGui import QFont

from . import BaseComponentEditor, register
from ui.common.widgets import W
from ui.common.notice import notice
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.pickers import collision_tag_slot
from ui.common.icons import COLOR_SPRITE
from core.history import get_history, AddListItemCmd


@register("collision_box")
class CollisionEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        is_solid = getattr(comp, "solid", True)

        # ── Tag ─────────────────────────────────────────────────────
        # Distinct de l'"id" de la meta_bar : l'id distingue les boxes de
        # CET acteur (utile avec plusieurs CollisionBoxComponent, ex.
        # "head_hurtbox" / "body_hurtbox") ; le tag est le GROUPE de
        # collision, partagé entre acteurs, celui que lit la matrice de
        # Project Settings > Collisions et que le codegen émet en
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
        W.row(label("comped.tag"), tag_slot, layout)

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
        W.row(label("common.mode"), mode_lbl, layout)

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

        W.pair(label("comped.offset"), "X", C.AXIS_X, vf_x, "Y", C.AXIS_Y, vf_y, layout)
        W.pair(label("common.size"), "W", C.AXIS_X, vf_w, "H", C.AXIS_Y, vf_h, layout)

        def _on_solid(v):
            self.set_field(comp, "solid", v)

        chk_solid.toggled.connect(_on_solid)
        self.register_syncer("solid", lambda v, w=chk_solid: (
            w.blockSignals(True), w.setChecked(bool(v)), w.blockSignals(False)))

