"""
ui/common/deferred_writes.py — les écritures que l'éditeur diffère, dans UNE seule file.

Un champ qu'on tourne (flèches d'un spinbox, molette) change de valeur dix fois par seconde : écrire le fichier à
chaque cran fige l'écran. L'écran garde donc la valeur en mémoire et PLANIFIE l'écriture ici ; elle part seule après
un court silence, ou plus tôt quand quelque chose est sur le point de lire le disque ou de quitter l'écran
(`flush`, appelé par la fenêtre : changement d'écran, build, ouverture d'un projet, Ctrl+S, fermeture, perte du focus).

Elle n'part JAMAIS tant qu'un bouton de la souris est enfoncé : une main qui hésite en plein glisser (souris immobile
plus de 600 ms) ne réécrit pas le fichier à chaque pause ; l'écriture attend qu'elle se lève. Les vidages explicites (`flush`)
ne l'attendent pas.

Tant qu'une écriture attend, `has_pending` est vrai : c'est ce qui allume « Unsaved changes » dans la barre du haut.

Une écriture est planifiée sous une CLÉ : replanifier la même clé remplace l'écriture précédente (seul le dernier état
compte), deux clés différentes ne se marchent pas dessus.
"""
from __future__ import annotations

from typing import Callable, Hashable, Optional

from PyQt6.QtCore import QCoreApplication, QObject, Qt, QTimer
from PyQt6.QtGui import QGuiApplication

from core.command_dispatcher import get_dispatcher

SILENCE_MS = 600     # le silence qui déclenche l'écriture : assez long pour un geste continu, assez court pour ne rien perdre


class DeferredWrites(QObject):
    def __init__(self):
        super().__init__(QCoreApplication.instance())     # elle meurt AVEC l'application, pas après elle
        self._pending: dict[Hashable, Callable[[], None]] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(SILENCE_MS)
        self._timer.timeout.connect(self._on_silence)

    def schedule(self, key: Hashable, write: Callable[[], None]) -> None:
        """Planifie `write` sous `key` ; remplace celle que `key` attendait, et repart pour un silence."""
        self._pending[key] = write
        self._timer.start()

    def has_pending(self) -> bool:
        return bool(self._pending)

    def _on_silence(self) -> None:
        """Le silence est passé : on écrit, sauf si une main est encore posée sur la souris (on reprend un silence)."""
        if QGuiApplication.mouseButtons() != Qt.MouseButton.NoButton:
            self._timer.start()
            return
        self.flush()

    def flush(self) -> None:
        """Écrit tout ce qui attend, maintenant. Une écriture qui échoue n'empêche pas les autres ; la première erreur
        est relevée une fois toutes passées."""
        self._timer.stop()
        pending, self._pending = self._pending, {}
        failure: Optional[Exception] = None
        for write in pending.values():
            try:
                write()
            except Exception as exc:
                failure = failure or exc
        if failure is not None:
            raise failure


_instance: Optional[DeferredWrites] = None


def get_deferred_writes() -> DeferredWrites:
    """La file de l'application (créée au premier appel : il lui faut un `QApplication`)."""
    global _instance
    if _instance is None:
        _instance = DeferredWrites()
    return _instance


def schedule_save(store, item) -> None:
    """Planifie l'écriture de `item` dans son magasin (`ResourceStore.save`). Tous les écrans qui règlent un même asset
    passent par ici : leurs écritures se FUSIONNENT (même clé), un seul fichier part avec l'état final.

    Un asset retiré de son magasin dans l'intervalle (supprimé) n'est pas réécrit."""
    def write() -> None:
        if item in store:
            store.save(item)

    schedule_unwatched((id(store), id(item)), write)


def schedule_unwatched(key, write: Callable[[], None]) -> None:
    """Planifie `write` sous `key`, SANS réveiller le watcher : les fichiers sous assets/ sont surveillés, une écriture non
    suspendue revient comme une modification externe, l'asset est remplacé par une copie et l'écran se recharge."""
    def run() -> None:
        with get_dispatcher().suspended():
            write()

    get_deferred_writes().schedule(key, run)
