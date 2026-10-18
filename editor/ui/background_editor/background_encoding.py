"""ui/background_editor/background_encoding.py — le service d'encodage unique d'un fond.

Un seul chemin pour tout ce qui encode : un geste du canvas, un curseur de compression, le bouton « Run encoding »,
l'import. Il ne connaît ni l'inspecteur ni le canvas : on lui donne un `EncodingJob` (ce qu'on veut encoder), il calcule en
arrière-plan, et il VALIDE le résultat sur le fond quand il correspond encore à ce qui est voulu.

Règles
  · le dernier réglage voulu gagne : un seul calcul à la fois, tous fonds confondus ; un résultat devenu périmé va au cache
    et n'est jamais validé ;
  · `request` part tout seul, toujours (le dernier réglage gagne, donc rien ne s'empile). Un seuil de coût existe
    (`auto_seconds` : au-delà, l'état reste « en attente » jusqu'à `run_now`) mais il est éteint par défaut — il servira si
    l'encodage de très grandes images gêne l'interface avant le processus séparé ;
  · les rappels `then` s'accumulent et s'exécutent à la validation FINALE : un réglage remplacé ne les perd pas ;
  · un résultat déjà vu (cache de `CACHE_SIZE` entrées) se valide sans calcul.

Le calcul passe par un exécuteur interchangeable (`ThreadExecutor` : un thread Qt). Le jour où une grande image demandera
un processus séparé, c'est lui qu'on remplace.
"""
from __future__ import annotations

import dataclasses
import time
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class EncodingState:
    UP_TO_DATE = "up_to_date"
    PENDING = "pending"
    COMPUTING = "computing"
    FAILED = "failed"


@dataclass(frozen=True)
class EncodingJob:
    """Ce qu'on veut encoder : le fond, son PNG, le layout (`token` : tiled4 | tiled8 | bitmap), la méthode, le dithering,
    la préparation de la source (canvas, pose, taille, miroir, ajustements) et la compression."""
    ba: object
    path: Path
    token: str
    method: str
    dither: bool
    prep: dict
    compression: object

    def key(self) -> tuple:
        """Tout ce qui fait un résultat : l'image (chemin, date, taille) et tous les réglages. Deux travaux de même clé donnent le
        même encodage — c'est ce qui permet le cache."""
        try:
            stat = Path(self.path).stat()
            # shortcut: edits preserving both mtime and size are invisible; hash contents if this must be supported.
            stamp = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = 0
        p = self.prep
        adjust = p.get("adjust")
        return (str(self.path), stamp, self.token, self.method, bool(self.dither),
                p.get("canvas"), p.get("pos"), p.get("size"), tuple(p.get("mirror") or ()),
                dataclasses.astuple(adjust) if adjust is not None else (),
                dataclasses.astuple(self.compression))


# ── Les exécuteurs ───────────────────────────────────────────────────────────

class _Signals(QObject):
    done = pyqtSignal(object, float)      # résultat, durée en secondes
    failed = pyqtSignal(str)


class _Task(QRunnable):
    def __init__(self, work: Callable[[], dict]):
        super().__init__()
        self._work = work
        self.signals = _Signals()

    def run(self):
        started = time.perf_counter()
        try:
            result = self._work()
        except Exception as error:  # noqa: BLE001 — remonté à l'interface, pas avalé
            self.signals.failed.emit(str(error))
            return
        self.signals.done.emit(result, time.perf_counter() - started)


class ThreadExecutor:
    """Un thread du `QThreadPool` global. `run(work, on_done, on_failed)` : `work()` rend le résultat ; les rappels sont
    appelés sur le thread de l'interface (signaux en file)."""

    def __init__(self):
        self._tasks: set = set()

    def run(self, work: Callable[[], dict], on_done, on_failed) -> None:
        task = _Task(work)
        self._tasks.add(task)

        def done(result, seconds):
            self._tasks.discard(task)
            on_done(result, seconds)

        def failed(message):
            self._tasks.discard(task)
            on_failed(message)

        task.signals.done.connect(done)
        task.signals.failed.connect(failed)
        QThreadPool.globalInstance().start(task)


# ── Le service ───────────────────────────────────────────────────────────────

class BackgroundEncodingService(QObject):
    state_changed = pyqtSignal(object)            # ba
    committed = pyqtSignal(object, object)        # (ba, job) : le résultat est validé sur le fond
    failed = pyqtSignal(object, str)              # (ba, message)

    CACHE_SIZE = 8

    def __init__(self, commit: Callable[[EncodingJob, dict], None], work_cache=None, executor=None,
                 auto_seconds: Optional[float] = None, parent=None):
        super().__init__(parent)
        self._commit = commit
        self._work_cache = work_cache
        self._executor = executor or ThreadExecutor()
        self._auto_seconds = auto_seconds
        self._wanted: dict = {}        # clé du fond -> (EncodingJob, [then…]) : ce qui est voulu, le dernier remplace
        self._go: set = set()          # clés de fonds autorisés à calculer (bon marché, geste, ou « Run encoding »)
        self._owners: dict = {}        # id d'objet -> référence faible du fond : détecte une adresse réutilisée
        self._gesture: set = set()     # fonds dont la demande vient d'un geste (import, canvas) : l'inspecteur ne la retire pas
        self._order: list = []         # l'ordre dans lequel les fonds ont demandé
        self._states: dict = {}
        self._seconds: dict = {}       # clé du fond -> durée du dernier encodage
        self._cache: OrderedDict = OrderedDict()
        self._running: Optional[EncodingJob] = None

    # ── Questions ────────────────────────────────────────────────
    def _id(self, ba):
        # L'identité de l'objet, pas `ba.id` : l'id hex n'est posé qu'à la sauvegarde, donc au milieu d'un encodage — la clé
        # changerait entre la demande et la validation, et la durée mesurée ne serait jamais retrouvée.
        key = id(ba)
        owner = self._owners.get(key)
        if owner is None or owner() is not ba:
            # Une adresse reprise par un autre fond (le premier est supprimé) n'hérite ni de son état ni de sa durée.
            if owner is not None:
                self._states.pop(key, None)
                self._seconds.pop(key, None)
                self._gesture.discard(key)
            self._owners[key] = weakref.ref(ba)
        return key

    def state(self, ba) -> str:
        known = self._states.get(self._id(ba))
        if known is not None and known != EncodingState.UP_TO_DATE:
            return known
        # À jour (ou jamais demandé) : le modèle seul le dit — un réglage changé depuis, sans demande, le rend périmé.
        return EncodingState.UP_TO_DATE if ba.encoding_is_current() else EncodingState.PENDING

    def last_seconds(self, ba) -> Optional[float]:
        return self._seconds.get(self._id(ba))

    def wanted(self, ba) -> Optional[EncodingJob]:
        entry = self._wanted.get(self._id(ba))
        return entry[0] if entry else None

    # ── Demandes ─────────────────────────────────────────────────
    def request(self, job: EncodingJob, *, immediate: bool = False, force: bool = False,
                then: Optional[Callable] = None, then_key=None) -> None:
        """« Voilà ce qui est voulu maintenant » pour `job.ba` : remplace la demande précédente de ce fond. `force` (le
        bouton « Recompute ») ignore le cache de résultats : on recalcule même un réglage déjà vu. `then_key` : un rappel
        de même clé déjà en attente n'est pas ajouté une seconde fois (un curseur tiré refait la demande à chaque pause)."""
        ba_id = self._id(job.ba)
        thens = list(self._wanted.get(ba_id, (None, []))[1])
        if then is not None and (then_key is None or all(key != then_key for key, _ in thens)):
            thens.append((then_key, then))
        self._wanted[ba_id] = (job, thens)
        if immediate:
            self._gesture.add(ba_id)
        if ba_id not in self._order:
            self._order.append(ba_id)
        key = job.key()
        hit = None if force else self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            self._finish(ba_id, job, hit)
            return
        # Autorisé à calculer : un geste, ou un fond dont le dernier encodage a été bon marché (ou jamais mesuré).
        if immediate or self._cheap(ba_id):
            self._go.add(ba_id)
        else:
            self._go.discard(ba_id)
        self._set_state(job.ba, EncodingState.PENDING)
        self._pump()

    def run_now(self, ba) -> None:
        """Le bouton « Run encoding » : calcule ce qui est voulu pour ce fond, même si c'est cher."""
        ba_id = self._id(ba)
        if ba_id not in self._wanted:
            return
        self._go.add(ba_id)
        self._pump()

    def withdraw(self, ba) -> None:
        """L'inspecteur ne tient plus aucun réglage en attente. Il ne retire que ses propres demandes : celle d'un geste
        (l'import, le canvas) a des rappels à honorer et l'auteur l'a voulue, un réglage revenu au défaut ne l'annule pas."""
        if self._id(ba) not in self._gesture:
            self.cancel(ba)

    def cancel(self, ba) -> None:
        """Plus rien n'est voulu pour ce fond (l'auteur est revenu à ses réglages validés) : la demande tombe ; un calcul en
        cours finit au cache sans rien valider."""
        ba_id = self._id(ba)
        self._wanted.pop(ba_id, None)
        self._go.discard(ba_id)
        self._gesture.discard(ba_id)
        if ba_id in self._order:
            self._order.remove(ba_id)
        if self._running is None or self._id(self._running.ba) != ba_id:
            self._set_state(ba, EncodingState.UP_TO_DATE)

    def cancel_all(self) -> None:
        """Annule les demandes et leurs rappels ; le calcul en cours finit sans rien valider."""
        for job, _thens in list(self._wanted.values()):
            self.cancel(job.ba)
        # Les états et durées sont indexés par `id(ba)` : un fond d'un autre projet pourrait reprendre l'adresse d'un fond
        # disparu et en hériter. On repart de zéro (le calcul en cours, s'il y en a un, se réinscrit à sa fin).
        self._states.clear()
        self._seconds.clear()

    def _cheap(self, ba_id) -> bool:
        seconds = self._seconds.get(ba_id)
        return self._auto_seconds is None or seconds is None or seconds <= self._auto_seconds

    # ── Le calcul ────────────────────────────────────────────────
    def _pump(self) -> None:
        if self._running is not None:
            return
        for ba_id in list(self._order):
            entry = self._wanted.get(ba_id)
            if entry is None or ba_id not in self._go:
                continue
            self._start(ba_id, entry[0])
            return

    def _start(self, ba_id, job: EncodingJob) -> None:
        key = job.key()  # La source peut changer pendant le calcul : garder l'identité du lancement.
        self._running = job
        self._set_state(job.ba, EncodingState.COMPUTING)
        work_cache = self._work_cache

        def work():
            from core.bg_import import encode_by_mode
            return encode_by_mode(str(job.path), job.token, job.method, job.dither, job.prep, job.compression,
                                  work_cache)

        self._executor.run(work, lambda result, seconds: self._on_done(ba_id, job, key, result, seconds),
                           lambda message: self._on_failed(ba_id, job, key, message))

    def _on_done(self, ba_id, job: EncodingJob, key: tuple, result: dict, seconds: float) -> None:
        self._running = None
        try:
            self._seconds[ba_id] = seconds
            unchanged = job.key() == key
            if unchanged:
                self._remember(key, result)
            current = self._wanted.get(ba_id)
            if unchanged and current is not None and current[0].key() == key:
                self._finish(ba_id, job, result)
            else:
                # Périmé : source ou réglage changé — le voulu garde ses rappels et repart (ou attend).
                # Plus rien de voulu (annulé) : le fond n'attend rien, il est à jour.
                if current is None:
                    self._set_state(job.ba, EncodingState.UP_TO_DATE)
                else:
                    if self._cheap(ba_id):
                        self._go.add(ba_id)
                    else:
                        self._go.discard(ba_id)
                        self._set_state(current[0].ba, EncodingState.PENDING)
        finally:
            self._pump()      # même si un rappel lève : sinon la file des autres fonds reste bloquée

    def _on_failed(self, ba_id, job: EncodingJob, key: tuple, message: str) -> None:
        self._running = None
        try:
            current = self._wanted.get(ba_id)
            if current is None:
                self._set_state(job.ba, EncodingState.UP_TO_DATE)
            elif current[0].key() == key:
                self._go.discard(ba_id)            # on ne boucle pas : le réglage reste voulu, « Run encoding » le rejoue
                self._set_state(job.ba, EncodingState.FAILED)
                self.failed.emit(job.ba, message)
        finally:
            self._pump()

    def _finish(self, ba_id, job: EncodingJob, result: dict) -> None:
        """Valide `result` sur le fond, puis appelle les rappels accumulés."""
        _job, thens = self._wanted.pop(ba_id, (job, []))
        self._go.discard(ba_id)
        self._gesture.discard(ba_id)
        if ba_id in self._order:
            self._order.remove(ba_id)
        try:
            self._commit(job, result)
        except Exception as error:  # noqa: BLE001 — l'écriture a échoué : signalé comme un échec d'encodage, pas avalé
            self._set_state(job.ba, EncodingState.FAILED)
            self.failed.emit(job.ba, str(error))
            return
        self._set_state(job.ba, EncodingState.UP_TO_DATE)
        self.committed.emit(job.ba, job)
        for _key, callback in thens:
            callback()

    def _remember(self, key, result: dict) -> None:
        self._cache[key] = result
        self._cache.move_to_end(key)
        while len(self._cache) > self.CACHE_SIZE:
            self._cache.popitem(last=False)

    def _set_state(self, ba, state: str) -> None:
        ba_id = self._id(ba)
        if self._states.get(ba_id) != state:
            self._states[ba_id] = state
            self.state_changed.emit(ba)
