"""
Component Editor Registry — système de plugins pour l'inspector.

Usage (éditeur interne) :
    from ui.scene_manager.inspectors.component_editors import register, get_editor

Usage (plugin externe) :
    from ui.scene_manager.inspectors.component_editors import register, BaseComponentEditor
    from core.models.components import COMPONENT_REGISTRY
    import dataclasses

    @dataclasses.dataclass
    class MyComp:
        id: str = "my_comp"
        active: bool = True
        speed: int = 60

    COMPONENT_REGISTRY["my_comp"] = MyComp

    @register("my_comp")
    class MyCompEditor(BaseComponentEditor):
        def build(self, comp, row, layout):
            sp = QSpinBox(); sp.setValue(comp.speed)
            sp.valueChanged.connect(lambda v: self.set_field(comp, "speed", v))
            row("Speed", sp)


"""
from __future__ import annotations
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QVBoxLayout

_REGISTRY: dict[str, type["BaseComponentEditor"]] = {}

# Largeur de la colonne des libellés des éditeurs physique/collision (« Collides with map »,
# « Physics collider » se coupaient à la largeur par défaut de W.row).
LABEL_WIDTH = 176


def register(comp_type: str):
    """Décorateur : @register('sprite') lie un éditeur à un type de component."""
    def decorator(cls: type["BaseComponentEditor"]):
        _REGISTRY[comp_type] = cls
        return cls
    return decorator


def get_editor(comp_type: str) -> type["BaseComponentEditor"] | None:
    return _REGISTRY.get(comp_type)


def all_editors() -> dict[str, type["BaseComponentEditor"]]:
    return dict(_REGISTRY)


class BaseComponentEditor:
    """
    Interface à implémenter pour un éditeur de component.

    L'inspector instancie la classe et appelle :
        editor.build(comp, row_fn, layout)   — construit les widgets
    """

    def __init__(self, inspector_ref):
        """
        inspector_ref : ActorInspector — accès à _project, _actor, _set_comp,
                        _save_component_change, _field_syncers, _editor_layout.
        """
        self.insp = inspector_ref

    # ── À surcharger ─────────────────────────────────────────────────

    def build(self, comp, row: Callable, layout: "QVBoxLayout") -> None:
        """Construit les widgets de l'éditeur dans layout via row(label, widget)."""
        raise NotImplementedError

    # ── Helpers partagés (délèguent à l'inspector) ───────────────────

    def set_field(self, comp, field: str, value):
        self.insp._set_comp(comp, field, value)

    def register_syncer(self, field: str, syncer):
        self.insp._field_syncers[field] = syncer
