"""
ui/common/field_binder.py — le pont champ de modèle ↔ widget d'un inspecteur.

Un inspecteur répète le même geste pour chaque champ : connecter le signal du
widget à une mutation, et repeupler le widget quand l'objet édité change. Écrit
à la main, ce geste vit à DEUX endroits par champ — la connexion à la
construction, la ligne de peuplement dans `load()` — qui doivent rester d'accord.
Un champ ajouté d'un côté et oublié de l'autre se désynchronise en silence.

`FieldBinder` tient les deux bouts d'un seul enregistrement :

    self._fields = FieldBinder(self._set)          # _set(name, value) : la mutation
    self._priority = self._fields.bind("priority", W.spinbox(0, 0, 3))
    ...
    self._fields.load(actor)                        # repeuple TOUS les champs liés

Ce qu'il fait, et RIEN d'autre :
  - il connecte le signal « valeur changée » du widget à `set_field(name, v)` ;
  - il repeuple chaque widget depuis `getattr(obj, name)` au `load`, sans émettre
    (il coupe les signaux du widget le temps de l'écriture — donc aucun aller-
    retour, et sans dépendre du drapeau `_blocking` de l'inspecteur).

Ce qu'il NE fait PAS, par choix (cf. TodoTechnique, U1 — « glue seule ») :
  - il ne CRÉE pas les widgets ni ne les pose dans un layout — `W`
    (ui/common/widgets) reste la source unique du style, et le layout reste
    explicite au site d'appel ;
  - il ne connaît ni l'historique ni le dispatcher — la mutation passe par le
    `set_field` que l'inspecteur lui donne (typiquement son `_set`, qui garde
    déjà l'undo, le no-op et le contexte de persistance). La dépendance ne va
    que dans un sens ;
  - il ne modélise pas les champs IRRÉGULIERS (un widget qui écrit deux champs,
    un combo dont les choix sont dynamiques) : ceux-là gardent leur handler
    explicite, plus lisible qu'une abstraction qui plierait pour eux.

Types de widget couverts (les cas 1:1 des inspecteurs) : QCheckBox, QSpinBox,
QDoubleSpinBox, ValueField, et QComboBox avec une table `values` donnant la
valeur de modèle par index. Un widget d'un autre type LÈVE à la liaison — un
inspecteur natif doit échouer fort, pas lier un champ à moitié.
"""
from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox

from ui.common.value_field import NumberField, ValueField


def _resolve(widget, values):
    """(signal, read, write) pour ce widget — la seule table qui sait relier un
    type de widget à sa valeur. `read(w)` rend la valeur de modèle, `write(w, v)`
    la pose dans le widget. QDoubleSpinBox n'hérite PAS de QSpinBox (tous deux
    sous QAbstractSpinBox) : les deux sont donc cités."""
    if isinstance(widget, QCheckBox):
        return widget.toggled, (lambda w: w.isChecked()), (lambda w, v: w.setChecked(bool(v)))
    if isinstance(widget, QComboBox):
        if values is None:
            raise TypeError(
                "bind(QComboBox) exige values=[...] — la valeur de modèle par "
                "index. Un combo dont les choix sont dynamiques est un champ "
                "irrégulier : il garde son handler explicite.")
        return (
            widget.currentIndexChanged,
            (lambda w: values[w.currentIndex()]),
            (lambda w, v: w.setCurrentIndex(values.index(v) if v in values else 0)),
        )
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        return widget.valueChanged, (lambda w: w.value()), (lambda w, v: w.setValue(v))
    if isinstance(widget, (ValueField, NumberField)):
        # `.changed` émet déjà la forme sérialisable ; `set_raw` ne réémet pas.
        return widget.changed, (lambda w: w.raw()), (lambda w, v: w.set_raw(v))
    raise TypeError(f"FieldBinder ne sait pas lier un {type(widget).__name__}")


class FieldBinder:
    def __init__(self, set_field: Callable[[str, Any], None]):
        # set_field(name, value) : l'entrée de mutation de l'inspecteur (son
        # `_set`). Le binder ne fait que l'appeler — il n'écrit jamais le modèle
        # directement, pour que l'undo et la persistance restent d'un seul côté.
        self._set_field = set_field
        self._binds: list[tuple[str, Any, Callable]] = []   # (name, widget, write)

    def bind(self, name: str, widget, *, values: list | None = None):
        """Lie `name` (attribut de l'objet édité) à `widget`. Connecte le signal
        de changement à `set_field(name, …)` et enregistre le widget pour
        `load`. Rend le widget, pour l'enchaîner avec `W.row`/`W.pair` et les
        réglages restants (`setSuffix`…) au site d'appel."""
        signal, read, write = _resolve(widget, values)
        signal.connect(lambda *_: self._set_field(name, read(widget)))
        self._binds.append((name, widget, write))
        return widget

    def load(self, obj) -> None:
        """Repeuple tous les widgets liés depuis `obj`, signaux coupés le temps
        de l'écriture (aucune mutation déclenchée)."""
        for name, widget, write in self._binds:
            widget.blockSignals(True)
            try:
                write(widget, getattr(obj, name))
            finally:
                widget.blockSignals(False)
