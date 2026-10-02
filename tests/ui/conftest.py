"""Harnais des tests de la couche UI (ARCHI A1) — un `QApplication` headless.

La couche UI était jusqu'ici sans test (cf. TodoTechnique, A1) : le code le plus
gros et le plus mouvant, sans filet. Ces tests-là ont besoin d'instancier de
vrais widgets Qt, donc d'un `QApplication` — mais sans écran. La plateforme
`offscreen` (livrée avec PyQt6) le permet, et c'est elle qui rend ces tests
exécutables en CI comme en local.

`sys.path` est déjà posé par `tests/conftest.py` (racine) : ce conftest-ci
n'ajoute que le `QApplication`. Il doit être choisi AVANT tout import de PyQt6,
d'où le `os.environ` en tête de module.
"""
from __future__ import annotations

import gc
import os

# Avant le premier import de PyQt6 : pas d'écran requis.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

# Référence de module : le `QApplication` doit survivre au GC final de pytest
# (`pytest_unconfigure` -> `gc_collect_harder`), sinon des widgets pris dans des
# cycles sont finalisés APRÈS sa destruction : violation d'accès intermittente.
_APP_KEPT_ALIVE: list[QApplication] = []


@pytest.fixture(scope="session")
def qapp():
    """L'unique `QApplication` de la session — un widget Qt ne peut exister sans
    lui. Réutilisé s'il existe déjà (un autre test UI a pu le créer)."""
    app = QApplication.instance() or QApplication([])
    _APP_KEPT_ALIVE.append(app)
    yield app
    # Finalise les widgets orphelins TANT QUE l'application existe : leurs
    # destructeurs C++ ont besoin d'elle (cf. `_APP_KEPT_ALIVE`).
    app.processEvents()
    gc.collect()
    app.processEvents()


@pytest.fixture(autouse=True)
def _drain_qt_events():
    """Purge les évènements Qt en attente APRÈS chaque test — en particulier un
    `QTimer.singleShot(0, ...)` qu'un test aurait programmé (l'AssetFinder en
    pose un pour différer l'activation d'un asset, cf. `asset_finder.py`) sans
    le laisser se déclencher lui-même.

    Un timer non drainé survit à la fin du test : il reste posé sur la boucle
    d'évènements de l'unique `QApplication` (partagée entre TOUS les tests de
    la session), et se déclenche au hasard d'un `processEvents()` ultérieur —
    potentiellement dans un tout autre fichier de test, sur des widgets que
    Python n'a gardés en vie QUE parce que la fermeture du timer les référence
    encore. Ça s'est vu planter (accès mémoire invalide) plusieurs dizaines de
    tests plus loin, sans rapport apparent avec la cause réelle."""
    yield
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
