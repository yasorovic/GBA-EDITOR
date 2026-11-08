"""Cartes repliables réordonnées par leur poignée, ordre retenu par panneau."""
from __future__ import annotations

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.common import card_order
from ui.common.widgets import CollapsibleCard


class _Panel(QWidget):
    def __init__(self, titles):
        super().__init__()
        layout = QVBoxLayout(self)
        self.note = QLabel("note")
        layout.addWidget(self.note)
        self.cards = [CollapsibleCard(t) for t in titles]
        for card in self.cards:
            layout.addWidget(card)
        layout.addStretch()

    def titles(self):
        layout = self.layout()
        widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
        return [w._title_lbl.text() for w in widgets if isinstance(w, CollapsibleCard)]


def _memory(monkeypatch):
    store = {}
    monkeypatch.setattr(card_order, "load", lambda panel: list(store.get(panel, [])))
    monkeypatch.setattr(card_order, "save", lambda panel, titles: store.__setitem__(panel, titles))
    return store


def test_dropping_a_card_below_another_moves_it_and_remembers_the_order(qapp, monkeypatch):
    store = _memory(monkeypatch)
    panel = _Panel(["A", "B", "C"])
    panel.resize(300, 600)
    panel.show()
    qapp.processEvents()
    last = panel.cards[2]
    below_last = last.mapToGlobal(QPoint(0, last.height())).y()
    panel.cards[0]._drop_at(below_last)
    assert panel.titles() == ["B", "C", "A"]
    assert panel.layout().indexOf(panel.note) == 0          # le reste du layout ne bouge pas
    assert list(store.values()) == [["B", "C", "A"]]


def test_a_new_panel_of_the_same_class_restores_the_order_and_keeps_unknown_cards_in_place(qapp, monkeypatch):
    store = _memory(monkeypatch)
    store[f"{_Panel.__module__}.{_Panel.__qualname__}"] = ["C", "A"]
    panel = _Panel(["A", "New", "C"])
    panel.show()
    qapp.processEvents()
    assert panel.titles() == ["C", "New", "A"]


def test_a_lone_card_shows_no_grip(qapp, monkeypatch):
    _memory(monkeypatch)
    panel = _Panel(["Only"])
    panel.show()
    qapp.processEvents()
    assert not panel.cards[0]._grip.isVisible()
