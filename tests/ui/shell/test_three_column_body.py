"""ThreeColumnBody : l'emplacement du panneau de build sous la colonne centrale."""

import pytest
from PyQt6.QtWidgets import QApplication, QWidget

from ui.common.three_column_body import ThreeColumnBody


@pytest.fixture(scope="module")
def app(qapp):
    return qapp              # l'application de la session (cf. `tests/ui/conftest.py`), jamais une qu'on détruirait avec ce module


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


def test_disk_reste_sous_la_bibliotheque_et_conserve_son_arbre(app):
    from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
    first, _ = _body()
    second, _ = _body()
    disk = QTreeWidget()
    folder = QTreeWidgetItem(disk, ["Sources"])
    QTreeWidgetItem(folder, ["hero.png"])
    folder.setExpanded(True)
    disk.setCurrentItem(folder)
    first.attach_disk(disk)
    QApplication.processEvents()
    first.left_split.setSizes([180, 410])
    sizes = first.left_split.sizes()
    second.attach_disk(disk)
    assert second.left_split.widget(0) is not disk
    assert second._disk_layout.itemAt(0).widget() is disk
    assert disk.currentItem() is folder and folder.isExpanded()
    first.attach_disk(disk)
    QApplication.processEvents()
    assert first._disk_layout.itemAt(0).widget() is disk
    assert first.left_split.sizes() == sizes


def test_tous_les_ecrans_natifs_affichent_le_meme_disk_sous_leur_library(qapp, tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QTreeWidgetItem
    import window
    monkeypatch.setattr(window, "QSettings", lambda *args: QSettings(
        str(tmp_path / "layout.ini"), QSettings.Format.IniFormat))
    win = window.MainWindow()
    win.show()
    disk_tabs = win._left_tab_widget
    disk = win.disk_tree_view
    from ui.common.disk_tree_view import _PATH_ROLE
    folder = QTreeWidgetItem(disk._tree, ["Sources"])
    folder.setData(0, _PATH_ROLE, str(tmp_path))
    QTreeWidgetItem(folder, ["hero.png"])
    folder.setExpanded(True)
    disk._tree.setCurrentItem(folder)
    try:
        for index, spec in enumerate(win._screens):
            if spec.plugin:
                continue
            win._show_screen(index)
            qapp.processEvents()
            body = win._body_of(index)
            assert body._disk_layout.itemAt(0).widget() is disk_tabs, spec.name
            assert body.left_split.widget(1) is disk_tabs.parentWidget(), spec.name
            assert disk.isVisible(), spec.name
            assert disk._tree.currentItem() is folder and folder.isExpanded(), spec.name
        assert disk_tabs.count() == 1 and disk_tabs.widget(0) is disk
        assert win.scene_tree_panel._context_tabs.count() == 3
    finally:
        win.hide()
