"""AreaInspector : une Area de la scène (position, forme de collision, effets, script, note).

La forme est celle d'un acteur : le même éditeur (`CollisionEditor`) l'affiche, avec les réglages qui n'ont pas de sens
pour une Area en moins (cf. `Area.conform_shapes`). Le script aussi : l'éditeur du `ScriptComponent` des acteurs
(`ScriptEditor`). Le nom se change dans l'en-tête partagé, comme pour un acteur."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QCheckBox, QSpinBox, QVBoxLayout, QWidget

from core.command_dispatcher import get_dispatcher
from core.history import AddListItemCmd, SetFieldCmd, get_history
from core.models.components import (
    AudioEmitterComponent, CollisionShapeComponent, ForceFieldComponent, GravityOverrideComponent, ScriptComponent,
    TriggerComponent,
)
from core.models.scene import Area, Scene
from core.project import Project
from ui.common.deferred_writes import schedule_save
from ui.common.labels import label
from ui.common.responsive import InspectorScrollArea
from ui.common.theme import C, T
from ui.common.tooltip import tooltip
from ui.common import icons
from ui.common.pickers import name_picker_slot
from ui.common.widgets import CollapsibleCard, NotesEdit, PickerSlot, W
from .component_editors.collision import CollisionEditor
from .component_editors.script import ScriptEditor

_COORD_RANGE = 32767

# Les effets physiques d'une Area : (composant, clé de libellé, [(champ, min, max, pas, décimales)]). Mêmes bornes que le modèle.
_EFFECTS = (
    (GravityOverrideComponent, "gravity", [("gravity_x", -8.0, 8.0, 0.05, 3), ("gravity_y", -8.0, 8.0, 0.05, 3)]),
    (ForceFieldComponent, "force", [("force_x", -8.0, 8.0, 0.05, 3), ("force_y", -8.0, 8.0, 0.05, 3),
                                    ("turbulence", 0.0, 8.0, 0.05, 3), ("buoyancy", 0.0, 4.0, 0.05, 2),
                                    ("drag", 0.0, 1.0, 0.05, 2)]),
    (AudioEmitterComponent, "emitter", []),    # ses réglages ont des widgets propres (cf. `_build_emitter_rows`)
)
_FIELD_TIPS = {"gravity_x": "areainsp.fx.gravity_tip", "gravity_y": "areainsp.fx.gravity_tip",
               "force_x": "areainsp.fx.force_xy_tip", "force_y": "areainsp.fx.force_xy_tip"}
_EFFECT_NAMES = {GravityOverrideComponent: "gravity_override", ForceFieldComponent: "force_field",
                 AudioEmitterComponent: "audio_emitter"}


class AreaInspector(QWidget):
    """Édite l'Area sélectionnée. `_actor`, `_scene`, `_project`, `_set_comp`, `_field_syncers`, `_save_component_change`
    et `_script_open_fn` sont ce que `CollisionEditor` et `ScriptEditor` attendent de leur inspecteur (c'est le contrat de
    `BaseComponentEditor`)."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._scene: Optional[Scene] = None
        self._actor: Optional[Area] = None      # l'Area : nom exigé par le contrat des éditeurs de composants
        self._blocking = False
        self._field_syncers: dict = {}
        self._script_open_fn = None      # injecté par l'inspecteur dynamique (ouvre un script dans l'éditeur)
        self._script_comp: Optional[ScriptComponent] = None

        scroll = InspectorScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(10)
        scroll.setWidget(inner)

        # La note, en tête comme dans l'inspecteur d'un acteur.
        notes_card = CollapsibleCard(label('common.note'))
        self._notes_edit = NotesEdit()
        self._notes_edit.committed.connect(lambda text: self._set_area("notes", text))
        notes_card.body_layout.addWidget(self._notes_edit)
        self._layout.addWidget(notes_card)

        # Position et état de départ.
        area_card = CollapsibleCard(label('common.area'))
        self._chk_active = QCheckBox(label('actorinsp.active'))
        self._chk_active.setFont(QFont(T.UI, T.SM))
        self._chk_active.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent;")
        self._chk_active.toggled.connect(lambda v: self._set_area("active", bool(v)))
        area_card.body_layout.addWidget(self._chk_active)
        # Le déclencheur : sans lui, l'Area ne prévient aucun script (cf. TriggerComponent).
        self._chk_trigger = QCheckBox(label('areainsp.trigger'))
        self._chk_trigger.setFont(QFont(T.UI, T.SM))
        self._chk_trigger.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent;")
        self._chk_trigger.setToolTip(tooltip(title=label('areainsp.trigger'), body=label('areainsp.trigger_tip')))
        self._chk_trigger.toggled.connect(self._set_trigger)
        area_card.body_layout.addWidget(self._chk_trigger)
        self._spin_x = W.spinbox(0, -_COORD_RANGE, _COORD_RANGE)
        self._spin_y = W.spinbox(0, -_COORD_RANGE, _COORD_RANGE)
        self._spin_x.valueChanged.connect(lambda v: self._set_area("x", int(v)))
        self._spin_y.valueChanged.connect(lambda v: self._set_area("y", int(v)))
        W.pair(label('common.position'), "X", C.AXIS_X, self._spin_x, "Y", C.AXIS_Y, self._spin_y,
               area_card.body_layout)
        # Le parent : un acteur posé de la scène que l'Area suit (cf. Area.parent).
        self._cmb_parent = W.combobox([])
        self._cmb_parent.setToolTip(tooltip(title=label('actorinsp.tr.parent'), body=label('areainsp.parent_tip')))
        self._cmb_parent.currentIndexChanged.connect(self._on_parent_changed)
        W.row(label('actorinsp.tr.parent'), self._cmb_parent, area_card.body_layout)
        self._layout.addWidget(area_card)

        # La forme, les effets et le script partent repliés : la note et l'Area suffisent à l'ouverture.
        # La forme : reconstruite à chaque chargement (le composant change avec l'Area).
        self._shape_card = CollapsibleCard(label('areainsp.shape'), expanded=False)
        self._layout.addWidget(self._shape_card)
        self._shape_container: Optional[QWidget] = None
        self._build_effects_card()
        # Le script : reconstruit à chaque chargement, comme la forme.
        self._script_card = CollapsibleCard(label('areainsp.script'), expanded=False)
        self._layout.addWidget(self._script_card)
        self._script_container: Optional[QWidget] = None
        self._layout.addStretch()

    # ── Effets physiques ──────────────────────────────────────────

    def _build_effects_card(self) -> None:
        """Une case par effet (ajoute ou réactive le composant, comme le déclencheur) et ses réglages, grisés tant que la case est
        décochée. Les widgets sont construits une fois et resynchronisés par `_sync_effects`."""
        card = CollapsibleCard(label('areainsp.fx.card'), expanded=False)
        self._fx_checks: dict = {}
        self._fx_inputs: dict = {}
        for kind, key, fields in _EFFECTS:
            check = QCheckBox(label(f'areainsp.fx.{key}'))
            check.setFont(QFont(T.UI, T.SM))
            check.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent;")
            check.setToolTip(tooltip(title=label(f'areainsp.fx.{key}'), body=label(f'areainsp.fx.{key}_tip')))
            check.toggled.connect(lambda on, k=kind: self._set_effect(k, on))
            card.body_layout.addWidget(check)
            self._fx_checks[kind] = check
            for field_name, low, high, step, decimals in fields:
                spin = W.double_spinbox(0.0, low, high, step, decimals)
                spin.valueChanged.connect(lambda v, k=kind, f=field_name: self._set_effect_field(k, f, float(v)))
                spin.setToolTip(tooltip(title=label(f'areainsp.fx.{field_name}'),
                                        body=label(_FIELD_TIPS.get(field_name, f'areainsp.fx.{field_name}_tip'))))
                W.row(label(f'areainsp.fx.{field_name}'), spin, card.body_layout)
                self._fx_inputs[(kind, field_name)] = spin
            if kind is AudioEmitterComponent:
                self._build_emitter_rows(card)
        characters = QCheckBox(label('areainsp.fx.characters'))
        characters.setFont(QFont(T.UI, T.SM))
        characters.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent;")
        characters.setToolTip(tooltip(title=label('areainsp.fx.characters'), body=label('areainsp.fx.characters_tip')))
        characters.toggled.connect(lambda on: self._set_effect_field(ForceFieldComponent, "affects_characters", bool(on)))
        card.body_layout.addWidget(characters)
        self._fx_inputs[(ForceFieldComponent, "affects_characters")] = characters
        self._layout.addWidget(card)

    def _build_emitter_rows(self, card) -> None:
        """Les réglages de l'émetteur sonore : l'effet, son volume, la marge d'atténuation et le panoramique."""
        kind = AudioEmitterComponent
        sfx = name_picker_slot(
            self._sfx_names, None, icons.COLOR_SFX,
            on_picked=lambda v: self._set_effect_field(kind, "sfx_name", v or None),
            add_label=label('comped.sfx_choose'), icon=icons.get("sfx", icons.COLOR_SFX),
            none_label=label('common.none_dash'))
        sfx.setToolTip(tooltip(title=label('areainsp.fx.sfx'), body=label('areainsp.fx.sfx_tip')))
        W.row(label('areainsp.fx.sfx'), sfx, card.body_layout)
        self._fx_inputs[(kind, "sfx_name")] = sfx
        for field_name, high in (("volume", 100), ("falloff", 255)):
            spin = W.spinbox(0, 0, high)
            spin.setToolTip(tooltip(title=label(f'areainsp.fx.{field_name}'), body=label(f'areainsp.fx.{field_name}_tip')))
            spin.valueChanged.connect(lambda v, f=field_name: self._set_effect_field(kind, f, int(v)))
            W.row(label(f'areainsp.fx.{field_name}'), spin, card.body_layout)
            self._fx_inputs[(kind, field_name)] = spin
        panning = QCheckBox(label('areainsp.fx.panning'))
        panning.setFont(QFont(T.UI, T.SM))
        panning.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent;")
        panning.setToolTip(tooltip(title=label('areainsp.fx.panning'), body=label('areainsp.fx.panning_tip')))
        panning.toggled.connect(lambda on: self._set_effect_field(kind, "panning", bool(on)))
        card.body_layout.addWidget(panning)
        self._fx_inputs[(kind, "panning")] = panning

    def _sfx_names(self) -> list[str]:
        """Les effets du projet ; l'effet cité s'il a disparu reste montré par le slot."""
        if self._project:
            self._project.load_audio()      # catalogue différé
        return [s.name for s in self._project.sfx.items] if self._project else []

    def _effect(self, kind):
        return next((c for c in self._actor.components if isinstance(c, kind)), None) if self._actor else None

    def _sync_effects(self) -> None:
        """Remet cases et réglages à la valeur du modèle (sous `_blocking`) ; sans composant, les valeurs par défaut."""
        for kind, _key, _fields in _EFFECTS:
            comp = self._effect(kind)
            on = comp is not None and comp.active
            self._fx_checks[kind].setChecked(on)
            source = comp if comp is not None else kind()
            for (k, field_name), widget in self._fx_inputs.items():
                if k is not kind:
                    continue
                value = getattr(source, field_name)
                if isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, PickerSlot):
                    widget.set_value(value)
                elif isinstance(widget, QSpinBox):
                    widget.setValue(int(value))
                else:
                    widget.setValue(float(value))
                widget.setEnabled(on)

    def _set_effect(self, kind, on: bool) -> None:
        area = self._actor
        existing = self._effect(kind)
        if self._blocking or area is None or (existing is not None and existing.active == on) or (existing is None and not on):
            return
        name = _EFFECT_NAMES[kind]
        if existing is None:
            get_history().push(AddListItemCmd(area.components, kind(), persist_fn=self._after_effect,
                                              label=f"{area.name}.{name}"))
        else:
            get_history().push(SetFieldCmd(existing, "active", not on, on, label=f"{area.name}.{name}.active",
                                           persist_fn=self._after_effect))

    def _set_effect_field(self, kind, field_name: str, value) -> None:
        comp = self._effect(kind)
        if self._blocking or comp is None or getattr(comp, field_name) == value:
            return
        get_history().push(SetFieldCmd(comp, field_name, getattr(comp, field_name), value,
                                       label=f"{self._actor.name}.{_EFFECT_NAMES[kind]}.{field_name}",
                                       persist_fn=self._persist))

    def _after_effect(self) -> None:
        """Ajouter ou (dés)activer un effet change aussi l'état grisé des réglages."""
        self._blocking = True
        try:
            self._sync_effects()
        finally:
            self._blocking = False
        self._persist()

    # ── Chargement ────────────────────────────────────────────────

    def load(self, area: Area, project: Project, scene: Optional[Scene]) -> None:
        self._project, self._scene, self._actor = project, scene, area
        self._blocking = True
        try:
            self._chk_active.setChecked(area.active)
            self._chk_trigger.setChecked(area.is_trigger())
            self._spin_x.setValue(area.x)
            self._spin_y.setValue(area.y)
            self._refresh_parent_choices()
            self._notes_edit.set_text_silent(area.notes)
            self._sync_effects()
        finally:
            self._blocking = False
        self._build_shape(area)
        self._build_script(area)

    def _refresh_parent_choices(self) -> None:
        """Les acteurs posés de la scène, et « (none) ». Un parent disparu reste visible plutôt que réécrit en silence : le build
        le refuse déjà, l'inspecteur dit la même chose que lui."""
        area = self._actor
        self._cmb_parent.blockSignals(True)
        self._cmb_parent.clear()
        self._cmb_parent.addItem(label('common.none_dash'), None)
        for actor in (self._scene.actors if self._scene else []):
            self._cmb_parent.addItem(actor.name, actor.name)
        index = self._cmb_parent.findData(area.parent) if area is not None else 0
        if area is not None and area.parent and index < 0:
            self._cmb_parent.addItem(label('actorinsp.parent_missing', name=area.parent), area.parent)
            index = self._cmb_parent.findData(area.parent)
        self._cmb_parent.setCurrentIndex(max(0, index))
        self._cmb_parent.blockSignals(False)

    def _on_parent_changed(self, _index: int) -> None:
        self._set_area("parent", self._cmb_parent.currentData())

    def _build_shape(self, area: Area) -> None:
        if self._shape_container is not None:
            self._shape_card.body_layout.removeWidget(self._shape_container)
            self._shape_container.deleteLater()
        self._field_syncers = {}
        container = QWidget()
        container.setStyleSheet(f"background:{C.BG_BASE};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        shape = self._shape()
        if shape is not None:
            CollisionEditor(self).build(shape, None, layout)
        self._shape_card.body_layout.addWidget(container)
        self._shape_container = container

    def _build_script(self, area: Area) -> None:
        """Le `ScriptComponent` de l'Area, ou un composant neuf, pas encore rangé : il n'entre dans l'Area qu'au premier
        script choisi (cf. `_save_component_change`), pour qu'une Area sans script ne gagne pas de composant vide."""
        if self._script_container is not None:
            self._script_card.body_layout.removeWidget(self._script_container)
            self._script_container.deleteLater()
        self._script_comp = area.get_component("script") or ScriptComponent()
        container = QWidget()
        container.setStyleSheet(f"background:{C.BG_BASE};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        ScriptEditor(self).build(self._script_comp, None, layout)
        self._script_card.body_layout.addWidget(container)
        self._script_container = container

    def _save_component_change(self, _comp=None) -> None:
        """Appelé par `ScriptEditor` après qu'il a écrit `script` sur le composant. Le premier script choisi range le
        composant dans l'Area (une entrée d'historique) ; ensuite, il suffit d'enregistrer."""
        area, comp = self._actor, self._script_comp
        if area is None or comp is None:
            return
        if comp not in area.components and comp.script:
            get_history().push(AddListItemCmd(area.components, comp, persist_fn=self._persist,
                                              label=f"{area.name}.script"))
            return
        self._persist()

    def set_script_open_fn(self, fn) -> None:
        self._script_open_fn = fn

    def _shape(self) -> Optional[CollisionShapeComponent]:
        """La forme que l'inspecteur édite : la première de l'Area."""
        if self._actor is None:
            return None
        return next((c for c in self._actor.components if isinstance(c, CollisionShapeComponent)), None)

    def refresh(self) -> None:
        """Remet les champs à la valeur du modèle SANS reconstruire (après annuler/rétablir ou un glisser dans le
        canvas) : reconstruire détruirait le champ en cours de saisie."""
        area = self._actor
        if area is None:
            return
        self._blocking = True
        try:
            self._chk_active.setChecked(area.active)
            self._chk_trigger.setChecked(area.is_trigger())
            self._spin_x.setValue(area.x)
            self._spin_y.setValue(area.y)
            self._refresh_parent_choices()
            self._sync_effects()
            shape = self._shape()
            if shape is not None:
                for field_name, sync in self._field_syncers.items():
                    sync(getattr(shape, field_name))
        finally:
            self._blocking = False

    # ── Écriture ──────────────────────────────────────────────────

    def _persist(self) -> None:
        if self._project is None or self._actor is None:
            return
        scene = self._scene or self._project.active_scene
        if scene is not None:
            schedule_save(self._project.scenes, scene)
        get_dispatcher()._emit("scene_sprites_changed")   # le canvas redessine l'Area
        get_dispatcher()._emit("actors_list_changed")     # l'arbre range l'Area sous son parent
        self.changed.emit()

    def _set_area(self, field_name: str, value) -> None:
        area = self._actor
        if self._blocking or area is None or getattr(area, field_name) == value:
            return
        get_history().push(SetFieldCmd(
            area, field_name, getattr(area, field_name), value,
            label=f"{area.name}.{field_name}", persist_fn=self._persist))

    def _set_trigger(self, on: bool) -> None:
        """Coche = l'Area a un déclencheur actif : le composant est ajouté, ou réactivé s'il existe déjà. Décoche = il est
        désactivé, jamais retiré (un seul déclencheur par Area, et la réactivation garde son identifiant)."""
        area = self._actor
        if self._blocking or area is None or area.is_trigger() == on:
            return
        existing = next((c for c in area.components if isinstance(c, TriggerComponent)), None)
        if existing is None:
            get_history().push(AddListItemCmd(area.components, TriggerComponent(), persist_fn=self._persist,
                                              label=f"{area.name}.trigger"))
        else:
            get_history().push(SetFieldCmd(existing, "active", not on, on, label=f"{area.name}.trigger.active",
                                           persist_fn=self._persist))

    def _set_comp(self, comp, field_name: str, value) -> None:
        """Appelé par `CollisionEditor.set_field`. Les formes d'une Area restent des capteurs (`conform_shapes`)."""
        area = self._actor
        if self._blocking or area is None or getattr(comp, field_name, None) == value:
            return
        get_history().push(SetFieldCmd(
            comp, field_name, getattr(comp, field_name), value,
            label=f"{area.name}.{getattr(comp, 'id', '?')}.{field_name}", persist_fn=self._persist))
