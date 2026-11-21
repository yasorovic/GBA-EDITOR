"""
ui/common/labels.py — les LIBELLÉS de l'interface de l'éditeur : boutons,
titres, entêtes, infobulles, entrées de menu. Un catalogue FRÈRE des notices,
sur le même cœur (ui/common/catalog.py) : maître `labels.json` + side
`labels_<code>.json` joints par clé, repli sur la source, pluriel, `format`.

    from ui.common.labels import label
    btn.setText(label("settings.close"))
    reset.setToolTip(label("settings.shortcuts.reset_to", default=b.default))

**Un libellé n'a NI ton NI niveau** — c'est ce qui le sépare d'une notice
(ui/common/notice.py), qui porte une gravité et un degré d'insistance. Deux
natures de texte, deux catalogues ; la machinerie, elle, est la même.

Convention de clés : `<écran>.<slug>`, en snake_case (`settings.close`,
`settings.shortcuts.reset_all`). La clé est écrite dans du Python versionné,
donc lisible et renommable dans le même commit que le side qui la suit.
"""
from __future__ import annotations

from pathlib import Path

from ui.common.catalog import Catalog

LABELS_DIR = Path(__file__).parent / "labels"
_CAT = Catalog("labels", LABELS_DIR)


def label(key: str, **args) -> str:
    """Le libellé résolu. Une clé absente rend la clé elle-même — visible à
    l'écran, retrouvable dans le code (jamais un blanc silencieux)."""
    return _CAT.text(key, **args)


def history_text(action) -> str:
    """Rend une action d'historique au dernier moment.

    Les commandes viennent du cœur et ne doivent pas dépendre du catalogue de
    l'interface. Une chaîne reste acceptée provisoirement pour les commandes
    externes qui ne sont pas encore migrées.
    """
    from core.history import HistoryLabel

    if isinstance(action, HistoryLabel):
        return label(action.key, **action.values)
    return str(action)
