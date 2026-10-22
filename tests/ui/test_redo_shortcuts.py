"""Les raccourcis globaux Annuler/Refaire de la fenêtre ne se gênent pas (Ctrl+Y doublé était ambigu sous Windows : rien ne se déclenchait)."""
from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtGui import QKeySequence

WINDOW = Path(__file__).resolve().parents[2] / "editor" / "window.py"


def test_les_raccourcis_globaux_d_historique_ont_des_touches_distinctes(qapp):
    text = WINDOW.read_text(encoding="utf-8")
    block = text[text.index("# Raccourcis clavier globaux"):text.index("self._restore_layout()")]
    keys = []
    for expression in re.findall(r"QShortcut\((.+?),\s*self\)", block):
        if expression.startswith("QKeySequence.StandardKey."):
            keys.append(QKeySequence(getattr(QKeySequence.StandardKey, expression.rsplit(".", 1)[1])).toString())
        else:
            keys.append(QKeySequence(re.search(r'"([^"]+)"', expression).group(1)).toString())
    assert {"Ctrl+Z", "Ctrl+Y", "Ctrl+Shift+Z"} <= set(keys), keys
    assert len(keys) == len(set(keys)), keys
