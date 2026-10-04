"""Éditeur du SpriteComponent."""
from __future__ import annotations


from . import BaseComponentEditor, register
from ui.common.widgets import W, ScriptSlot, ScriptPickerPopup
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.pickers import sprite_picker_slot, palette_picker_slot
from ui.common.theme import C
from ui.common.icons import COLOR_SPRITE
from core.command_dispatcher import get_dispatcher
from core.models.components import center_on_frame


@register("sprite")
class SpriteEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        proj   = self.insp._project
        # Le picker liste TOUS les sprites : matérialise le catalogue différé
        # (v0.24). On est ici sur sélection d'un acteur — une action délibérée,
        # jamais à l'ouverture du projet — donc le charger maintenant est sans
        # effet sur la fluidité d'ouverture.
        proj.load_sprites()
        sprite = proj.get_sprite(comp.sprite_name) if comp.sprite_name else None

        # ── Sprite : bouton qui se déploie en liste filtrable, comme le
        #    slot "Ajouter un script" — plus de sélection de PNG direct.
        def _on_sprite_picked(name: str):
            if self.insp._blocking or not self.insp._actor or name == comp.sprite_name:
                return
            comp.sprite_name = name
            self.insp._save_component_change(None)
            self.insp._refresh_sprite_preview()
            self.insp._build_editor(comp)   # re-affiche État/Anim pour le sprite choisi

        def _on_sprite_cleared():
            if self.insp._blocking or not self.insp._actor:
                return
            comp.sprite_name = None
            self.insp._save_component_change(None)
            self.insp._refresh_sprite_preview()
            self.insp._build_editor(comp)

        slot = sprite_picker_slot(
            [s.name for s in proj.sprites], sprite.name if sprite else None,
            COLOR_SPRITE, on_picked=_on_sprite_picked, on_cleared=_on_sprite_cleared,
            add_label=label("comped.choose_sprite"), parent=self.insp,
        )
        W.row(label("common.sprite"), slot, layout)

        # ── Palette OBJ (pal_bank est un champ Actor/Prefab) ─────────────
        # Un Prefab n'est qu'un modèle : à l'instanciation, il arrive dans une
        # scène et se comporte comme un actor normal — même picker de palette
        # ACTIVE nommée (+ « Sans palette ») aux deux niveaux. Si le slot
        # assigné n'a pas de palette active dans la scène où il finit instancié,
        # il retombe sur le slot 0, comme n'importe quel actor (pas un cas
        # spécial des prefabs).
        from core.models.palette import OWN_PAL_BANK
        from ui.common.pickers import PALETTE_NONE
        actor = self.insp._actor
        scene = self.insp._scene

        active_names = scene.active_obj_palettes if scene else []
        active_banks = [b for n in active_names if (b := proj.get_palette(n))]
        current_pal_name = (
            active_names[actor.pal_bank]
            if actor and 0 <= actor.pal_bank < len(active_names) else None
        )

        def _on_pal_picked(name: str):
            if name == PALETTE_NONE:
                self.insp._set("pal_bank", OWN_PAL_BANK)
                return
            try:
                idx = active_names.index(name)
            except ValueError:
                return
            self.insp._set("pal_bank", idx)

        pal_slot = palette_picker_slot(
            active_banks, current_pal_name,
            COLOR_SPRITE, on_picked=_on_pal_picked,
            add_label=label("common.choose_palette"), parent=self.insp,
        )
        pal_slot.setToolTip(tooltip(
            title=label("comped.palette"), body=label("comped.palette_tip"),
            note=label("comped.palette_note")))
        W.row(label("comped.palette"), pal_slot, layout)

        # ── État initial : même bouton+popup filtrable que "Sprite" ──
        state_slot = ScriptSlot(
            add_label=label("comped.choose_state"),
            accent_color=COLOR_SPRITE,
            show_clear=False,   # un state initial est toujours requis, rien à "vider"
        )
        state_slot.set_script(comp.initial_state or "Idle")
        state_slot.setEnabled(sprite is not None)

        def _open_state_picker():
            if not sprite:
                return
            names = [s.name for s in sprite.states] or [comp.initial_state or "Idle"]
            popup = ScriptPickerPopup(
                [(n, n) for n in names], COLOR_SPRITE, parent=self.insp, new_label=None,
            )
            popup.picked.connect(lambda name: _on_state_picked(name))
            popup.show_below(state_slot)

        def _on_state_picked(name: str):
            if self.insp._blocking or not self.insp._actor or name == comp.initial_state:
                return
            comp.initial_state = name
            self.insp._save_component_change(None)
            self.insp._refresh_sprite_preview()
            state_slot.set_script(name)
            new_state = next((s for s in sprite.states if s.name == name), None) if sprite else None
            if new_state:
                speed.blockSignals(True)
                speed.setValue(new_state.speed)
                speed.blockSignals(False)

        state_slot.set_callbacks(on_add=_open_state_picker, on_open=_open_state_picker)
        W.row(label("comped.state_init"), state_slot, layout)

        # ── Anim speed (du state initial uniquement — pas des autres states) ──
        _init_state = (
            next((s for s in sprite.states if s.name == comp.initial_state), None)
            if sprite else None
        ) or (sprite.states[0] if sprite and sprite.states else None)
        speed = W.spinbox(_init_state.speed if _init_state else 8, min_v=1, max_v=120)
        speed.setEnabled(sprite is not None)
        speed.setToolTip(tooltip(
            title=label("comped.anim_speed_title"),
            body=label("comped.anim_speed_tip", state=comp.initial_state),
            note=label("comped.anim_speed_note")))
        speed.valueChanged.connect(lambda v: self._set_anim_speed(comp, v))
        W.row(label("comped.anim_speed"), speed, layout)

        # ── Affine transform ──────────────────────────────────────
        # La case vit ICI et pas sur l'Actor : réserver un des 32 slots de
        # matrice affine OAM est une capacité de RENDU (cf. ARCHITECTURE.md
        # « Le modèle affine »). C'est aussi ce qui la rend décidable sur une
        # racine de prefab, dont cette carte est la seule affichée.
        #
        # Elle commande les trois réglages qui suivent (affichés seulement si cochée) — et, à l'écran
        # seulement, le rotation/scale MONDE de l'actor (carte Transform) :
        # ceux-là gardent leur valeur, ils ne s'affichent simplement pas.
        aff = W.checkbox_row("", label("comped.affine"), layout)
        aff.setChecked(bool(getattr(comp, "affine_transform", False)))
        aff.setToolTip(tooltip(
            title=label("comped.affine"), body=label("comped.affine_tip"),
            note=label("comped.affine_note")))
        aff.toggled.connect(lambda on, c=comp: self._set_affine(c, on))

        # ── Réglages locaux ───────────────────────────────────────
        # Transform LOCAL : ne vaut QUE si la case ci-dessus est cochée
        # (rotation/scale/offset sont relatifs à l'actor et se composent par-
        # dessus son transform monde). Sinon aucun slot de matrice affine, et
        # ces réglages seraient ignorés : on ne les montre pas. Leurs valeurs
        # restent dans le component ; `_set_affine` reconstruit l'éditeur.
        if not getattr(comp, "affine_transform", False):
            return

        # Offset relatif à l'actor, dans SON repère local (il tourne/scale avec
        # lui) : le sprite n'a PAS de position monde.
        # px / tile / variable : un script change l'offset (self.sprite_offset),
        # la variable est donc légitime ici (assignation à l'init).
        offx = W.value_field(getattr(comp, "offset_x", 0), project=proj,
                             min_px=-32768, max_px=32767)
        offy = W.value_field(getattr(comp, "offset_y", 0), project=proj,
                             min_px=-32768, max_px=32767)
        offx.setToolTip(tooltip(
            title=label("comped.offset_x_title"), body=label("comped.offset_x_tip")))
        offy.setToolTip(tooltip(
            title=label("comped.offset_y_title"), body=label("comped.offset_y_tip")))
        offx.changed.connect(lambda raw: self._set_comp_field(comp, "offset_x", raw))
        offy.changed.connect(lambda raw: self._set_comp_field(comp, "offset_y", raw))
        W.pair(label("comped.offset"), "X", C.AXIS_X, offx, "Y", C.AXIS_Y, offy, layout)

        rot = W.number_field(getattr(comp, "rotation", 0), project=proj, kind="int",
                             min_v=0, max_v=359, suffix="°", wrapping=True)
        rot.setToolTip(tooltip(
            title=label("comped.rotation_title"), body=label("comped.rotation_tip")))
        rot.changed.connect(lambda raw: self._set_comp_field(comp, "rotation", raw))
        W.row(label("common.rotation"), rot, layout)

        # float ou variable (en POURCENT, comme `self.sprite_scale`).
        sx = W.number_field(getattr(comp, "scale_x", 1.0), project=proj, kind="float",
                            min_v=-4.0, max_v=4.0, step=0.1)
        sy = W.number_field(getattr(comp, "scale_y", 1.0), project=proj, kind="float",
                            min_v=-4.0, max_v=4.0, step=0.1)
        sx.setToolTip(tooltip(
            title=label("comped.scale_x_title"), body=label("comped.scale_x_tip")))
        sy.setToolTip(tooltip(
            title=label("comped.scale_y_title"), body=label("comped.scale_y_tip")))
        sx.changed.connect(lambda raw: self._set_comp_field(comp, "scale_x", raw))
        sy.changed.connect(lambda raw: self._set_comp_field(comp, "scale_y", raw))
        W.pair(label("common.scale"), "X", C.AXIS_X, sx, "Y", C.AXIS_Y, sy, layout)

        W.separator(layout)

        # Point de pivot, depuis le CENTRE du cadre ((0, 0) = le centre) : le
        # point autour duquel rotation, échelle et flip s'exercent. Même forme
        # que l'offset, donc un script le change aussi (self.sprite_pivot).
        pivx = W.value_field(getattr(comp, "pivot_x", 0), project=proj,
                             min_px=-32768, max_px=32767)
        pivy = W.value_field(getattr(comp, "pivot_y", 0), project=proj,
                             min_px=-32768, max_px=32767)
        pivx.setToolTip(tooltip(
            title=label("comped.pivot_x_title"), body=label("comped.pivot_x_tip")))
        pivy.setToolTip(tooltip(
            title=label("comped.pivot_y_title"), body=label("comped.pivot_y_tip")))
        pivx.changed.connect(lambda raw: self._set_comp_field(comp, "pivot_x", raw))
        pivy.changed.connect(lambda raw: self._set_comp_field(comp, "pivot_y", raw))
        W.pair(label("comped.pivot"), "X", C.AXIS_X, pivx, "Y", C.AXIS_Y, pivy, layout)

    # ── Helpers ──────────────────────────────────────────────────────

    def _set_affine(self, comp, on: bool):
        """La case ne fait pas que changer un champ : elle décide du grisage des
        trois réglages locaux ci-dessus, et de ce que le canvas dessine (le
        transform monde de l'actor n'est visible que si un slot est réservé).
        D'où la reconstruction de l'éditeur après la sauvegarde."""
        if self.insp._blocking or not self.insp._actor: return
        comp.affine_transform = bool(on)
        if on:
            # Cas courant d'entrée de jeu : l'acteur au centre du cadre (cf.
            # `center_on_frame`). Les boîtes de collision suivent le sprite.
            sprite = (self.insp._project.get_sprite(comp.sprite_name)
                      if comp.sprite_name else None)
            center_on_frame(self.insp._actor, comp, sprite)
        self.insp._save_component_change(comp)
        self.insp._build_editor(comp)

    def _set_comp_field(self, comp, field, value):
        if self.insp._blocking or not self.insp._actor: return
        setattr(comp, field, value)
        self.insp._save_component_change(comp)

    def _set_anim_speed(self, comp, value: int):
        """Ne modifie que le state initial de ce component — les autres states du
        sprite gardent leur propre vitesse (réglée dans le Sprite Editor)."""
        if self.insp._blocking or not self.insp._actor: return
        sprite = self.insp._project.get_sprite(comp.sprite_name) if comp.sprite_name else None
        if not sprite:
            return
        state = next((s for s in sprite.states if s.name == comp.initial_state), None)
        if not state and sprite.states:
            state = sprite.states[0]
        if state:
            state.speed = value
        get_dispatcher().save_sprite(sprite)
        self.insp._persist()
        self.insp.changed.emit()
