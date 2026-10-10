"""ThreeColumnBody : l'emplacement du panneau de build sous la colonne centrale."""

import pytest
from PyQt6.QtWidgets import QApplication, QWidget

from ui.common.three_column_body import ThreeColumnBody


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _body():
    left, center, right = QWidget(), QWidget(), QWidget()
    body = ThreeColumnBody(left, center, right)
    body.resize(900, 600)
    body.show()
    QApplication.processEvents()
    return body, center


def test_panneau_ferme_par_defaut(app):
    body, _ = _body()
    assert not body.dock_is_open()


def test_ouvrir_puis_fermer(app):
    body, _ = _body()
    panel = QWidget()
    body.attach_dock(panel)
    assert body.holds_dock(panel)
    body.set_dock_open(True)
    QApplication.processEvents()
    assert body.dock_is_open() and panel.height() > 0
    body.set_dock_open(False)
    QApplication.processEvents()
    assert not body.dock_is_open() and panel.height() == 0


def test_panneau_reaccroche_ailleurs(app):
    first, _ = _body()
    second, _ = _body()
    panel = QWidget()
    first.attach_dock(panel)
    second.attach_dock(panel)
    assert second.holds_dock(panel) and not first.holds_dock(panel)


def test_ferme_garde_sa_poignee_et_se_rouvre_a_la_souris(app):
    body, _ = _body()
    body.attach_dock(QWidget())
    body.set_dock_open(False)
    QApplication.processEvents()
    assert body.center_split.handle(1).isVisible()     # la poignée existe, panneau fermé
    total = sum(body.center_split.sizes())
    body.center_split.setSizes([total - 200, 200])      # ce que fait un glissé de la poignée
    assert body.dock_is_open()
