"""AreaInspector : une Area de la scène (position, forme de collision, note).

La forme est celle d'un acteur : le même éditeur (`CollisionEditor`) l'affiche, avec les réglages qui n'ont pas de sens
pour une Area en moins (cf. `Area.conform_shapes`). Le nom se change dans l'en-tête partagé, comme pour un acteur."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QCheckBox, QVBoxLayout, QWidget

from core.command_dispatcher import get_dispatcher
from core.history import SetFieldCmd, get_history
from core.models.components import CollisionShapeComponent
from core.models.scene import Area, Scene
from core.project import Project
from ui.common.deferred_writes import schedule_save
from ui.common.labels import label
from ui.common.responsive import InspectorScrollArea
from ui.common.theme import C, T
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

        # Position et état de départ.
        area_card = CollapsibleCard(label('common.area'))
        self._chk_active = QCheckBox(label('actorinsp.active'))
        self._chk_active.setFont(QFont(T.UI, T.SM))
        self._chk_active.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent;")
        self._chk_active.toggled.connect(lambda v: self._set_area("active", bool(v)))
        area_card.body_layout.addWidget(self._chk_active)
        self._spin_x = W.spinbox(0, -_COORD_RANGE, _COORD_RANGE)
        self._spin_y = W.spinbox(0, -_COORD_RANGE, _COORD_RANGE)
        self._spin_x.valueChanged.connect(lambda v: self._set_area("x", int(v)))
        self._spin_y.valueChanged.connect(lambda v: self._set_area("y", int(v)))
        W.pair(label('common.position'), "X", C.AXIS_X, self._spin_x, "Y", C.AXIS_Y, self._spin_y,
               area_card.body_layout)
        self._layout.addWidget(area_card)

        # La forme : reconstruite à chaque chargement (le composant change avec l'Area).
        self._shape_card = CollapsibleCard(label('areainsp.shape'))
        self._layout.addWidget(self._shape_card)
        self._shape_container: Optional[QWidget] = None

        notes_card = CollapsibleCard(label('common.note'))
        self._notes_edit = NotesEdit()
        self._notes_edit.committed.connect(lambda text: self._set_area("notes", text))
        notes_card.body_layout.addWidget(self._notes_edit)
        self._layout.addWidget(notes_card)
        self._layout.addStretch()

    # ── Chargement ────────────────────────────────────────────────

    def load(self, area: Area, project: Project, scene: Optional[Scene]) -> None:
        self._project, self._scene, self._actor = project, scene, area
        self._blocking = True
        try:
            self._chk_active.setChecked(area.active)
            self._spin_x.setValue(area.x)
            self._spin_y.setValue(area.y)
            self._notes_edit.set_text_silent(area.notes)
        finally:
            self._blocking = False
        self._build_shape(area)

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
            self._spin_x.setValue(area.x)
            self._spin_y.setValue(area.y)
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
        self.changed.emit()

    def _set_area(self, field_name: str, value) -> None:
        area = self._actor
        if self._blocking or area is None or getattr(area, field_name) == value:
            return
        get_history().push(SetFieldCmd(
            area, field_name, getattr(area, field_name), value,
            label=f"{area.name}.{field_name}", persist_fn=self._persist))

    def _set_comp(self, comp, field_name: str, value) -> None:
        """Appelé par `CollisionEditor.set_field`. Les formes d'une Area restent des capteurs (`conform_shapes`)."""
        area = self._actor
        if self._blocking or area is None or getattr(comp, field_name, None) == value:
            return
        get_history().push(SetFieldCmd(
            comp, field_name, getattr(comp, field_name), value,
            label=f"{area.name}.{getattr(comp, 'id', '?')}.{field_name}", persist_fn=self._persist))
