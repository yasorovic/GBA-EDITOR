"""ui/common/import_collision.py — la question unique posée quand un import rencontre un fichier du même nom."""
from __future__ import annotations

from ui.common.labels import label
from ui.common.popup import MessageBox


def ask_overwrite(parent, names, citing=()) -> bool | None:
    """True : écraser. False : garder les deux (la copie prend un nom libre). None : annuler.
    `citing` : les assets dont la source serait changée par l'écrasement."""
    text = label("collision.text", names="\n".join(f"  {name}" for name in names))
    if citing:
        text += "\n\n" + label("collision.cited", assets="\n".join(f"  {entry}" for entry in citing))
    box = MessageBox(MessageBox.Icon.Question, label("collision.title"), text, MessageBox.StandardButton.NoButton, parent)
    overwrite = box.addButton(label("collision.overwrite"), MessageBox.ButtonRole.DestructiveRole)
    keep = box.addButton(label("collision.keep_both"), MessageBox.ButtonRole.AcceptRole)
    box.addButton(label("common.cancel"), MessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(keep)
    box.exec()
    clicked = box.clickedButton()
    return True if clicked is overwrite else False if clicked is keep else None
