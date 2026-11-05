"""AreaInspector : une Area de la scène (position, forme de collision, note).

La forme est celle d'un acteur : le même éditeur (`CollisionEditor`) l'affiche, avec les réglages qui n'ont pas de sens
pour une Area en moins (cf. `Area.conform_shapes`). Le nom se change dans l'en-tête partagé, comme pour un acteur."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QCheckBox, QVBoxLayout, QWidget

from core.command_dispatcher import get_dispatcher
from core.history import AddListItemCmd, SetFieldCmd, get_history
from core.models.components import CollisionShapeComponent, TriggerComponent
from core.models.scene import Area, Scene
from core.project import Project
from ui.common.deferred_writes import schedule_save
from ui.common.labels import label
from ui.common.responsive import InspectorScrollArea
from ui.common.theme import C, T
from ui.common.tooltip import tooltip
from ui.common.widgets import CollapsibleCard, NotesEdit, W
from .component_editors.collision import CollisionEditor

_COORD_RANGE = 32767


class AreaInspector(QWidget):
    """Édite l'Area sélectionnée. `_actor`, `_scene`, `_project`, `_set_comp` et `_field_syncers` sont ce que
    `CollisionEditor` attend de son inspecteur (c'est le contrat de `BaseComponentEditor`)."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._scene: Optional[Scene] = None
        self._actor: Optional[Area] = None      # l'Area : nom exigé par le contrat des éditeurs de composants
        self._blocking = False
        self._field_syncers: dict = {}

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

        # La forme : reconstruite à chaque chargement (le composant change avec l'Area).
        self._shape_card = CollapsibleCard(label('areainsp.shape'))
        self._layout.addWidget(self._shape_card)
        self._shape_container: Optional[QWidget] = None
        self._layout.addStretch()

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
        finally:
            self._blocking = False
        self._build_shape(area)

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
