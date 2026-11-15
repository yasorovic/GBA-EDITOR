"""Message quand un nom est déjà pris dans le même layout d'interface."""
from __future__ import annotations

from core.models.unique_name import unique_name
from ui.common.labels import label
from ui.common.popup import MessageBox


def resolve_ui_element_name(parent, project, layout, element, new_name: str) -> str | None:
    """Le nom à appliquer : `new_name` s'il est libre, sinon celui que l'auteur accepte (le même complété d'un suffixe).
    None quand il préfère en choisir un autre : l'appelant garde l'ancien nom."""
    new_name = new_name.strip()
    owners = [layout.name for other in layout.elements
              if other is not element and other.name == new_name]
    if not owners:
        return new_name
    suggested = unique_name(new_name, set(layout.element_names()) - {element.name})
    answer = MessageBox.question(
        parent, label("uielemname.taken_title"),
        label("uielemname.taken_msg", name=new_name, interface=owners[0], suggested=suggested),
        MessageBox.StandardButton.Yes | MessageBox.StandardButton.No, MessageBox.StandardButton.Yes)
    return suggested if answer == MessageBox.StandardButton.Yes else None
