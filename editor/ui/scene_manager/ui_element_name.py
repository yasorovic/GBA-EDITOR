"""ui/scene_manager/ui_element_name.py : le message quand le nom choisi pour un élément d'interface est déjà pris.

Les noms d'élément d'interface sont uniques dans tout le projet (`Project.ui_element_names`) : ils deviennent des constantes C
(`REGION_*`, `IMAGE_*`) et se citent par `interface:get("Nom")`. `Project.rename_ui_element` complète en silence un nom pris
(`slot2` devient `slot2_2`) ; l'auteur doit le savoir AVANT, et pouvoir en choisir un autre. Pas d'écrasement proposé : l'homonyme
vit souvent dans une autre interface, l'écraser supprimerait un élément que des scripts citent.
"""
from __future__ import annotations

from core.models.unique_name import unique_name
from ui.common.labels import label
from ui.common.popup import MessageBox


def resolve_ui_element_name(parent, project, layout, element, new_name: str) -> str | None:
    """Le nom à appliquer : `new_name` s'il est libre, sinon celui que l'auteur accepte (le même complété d'un suffixe).
    None quand il préfère en choisir un autre : l'appelant garde l'ancien nom."""
    new_name = new_name.strip()
    owners = [lay.name for lay, other in project.all_elements() if other is not element and other.name == new_name]
    if not owners:
        return new_name
    suggested = unique_name(new_name, set(project.ui_element_names()) - {element.name})
    answer = MessageBox.question(
        parent, label("uielemname.taken_title"),
        label("uielemname.taken_msg", name=new_name, interface=owners[0], suggested=suggested),
        MessageBox.StandardButton.Yes | MessageBox.StandardButton.No, MessageBox.StandardButton.Yes)
    return suggested if answer == MessageBox.StandardButton.Yes else None
