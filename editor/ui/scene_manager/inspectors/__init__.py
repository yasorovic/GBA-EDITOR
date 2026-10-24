"""
ui.scene_manager.inspectors — package principal.

Import de compat :
    from ui.scene_manager.inspectors import DynamicInspector, ActorInspector

Un fichier par classe (actor_inspector.py, scene_inspector.py,
camera_inspector.py, uses_inspectors.py, dynamic_inspector.py).
"""

# Charger les éditeurs built-in dans le registre
from ui.scene_manager.inspectors.component_editors import sprite    # noqa: F401
from ui.scene_manager.inspectors.component_editors import collision  # noqa: F401
from ui.scene_manager.inspectors.component_editors import sfx        # noqa: F401
from ui.scene_manager.inspectors.component_editors import interactive  # noqa: F401
from ui.scene_manager.inspectors.component_editors import script     # noqa: F401

from ui.scene_manager.inspectors.actor_inspector import ActorInspector, ComponentListWidget
from ui.scene_manager.inspectors.scene_inspector import SceneInspector
from ui.scene_manager.inspectors.camera_inspector import CameraInspector
from ui.scene_manager.inspectors.uses_inspectors import PrefabUsesInspector
from ui.scene_manager.inspectors.dynamic_inspector import DynamicInspector

__all__ = [
    "DynamicInspector",
    "ActorInspector",
    "SceneInspector",
    "CameraInspector",
    "PrefabUsesInspector",
    "ComponentListWidget",
]
