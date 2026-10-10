"""Un acteur qu'on tire hors du canvas reprend sa place et devient un glisser vers l'onglet Disk."""
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QDrag, QMouseEvent, QPixmap

from core.history import get_history
from core.models.resource import MIME_CANVAS_ACTOR
from core.models.scene import Actor
from ui.scene_manager.canvas.canvas_view import GBAView
from ui.scene_manager.canvas.canvas_scene import GBAScene


def test_dragging_an_actor_out_of_the_view_starts_a_drag_and_restores_it(qapp, monkeypatch):
    get_history().clear()
    scene = GBAScene()
    view = GBAView(scene)
    view.resize(400, 300)
    view.show()
    actor = Actor(name="Hero", x=40, y=40)
    item = scene.add_sprite(QPixmap(16, 16), actor)
    item.setPos(40, 40)
    started = []
    monkeypatch.setattr(QDrag, "exec", lambda self, *a: started.append(bytes(self.mimeData().data(MIME_CANVAS_ACTOR))))
    viewport = view.viewport()
    start = view.mapFromScene(item.sceneBoundingRect().center())

    def event(kind, point, button, buttons):
        return QMouseEvent(kind, QPointF(point), QPointF(viewport.mapToGlobal(point)), button, buttons, Qt.KeyboardModifier.NoModifier)

    left = Qt.MouseButton.LeftButton
    view.mousePressEvent(event(QEvent.Type.MouseButtonPress, start, left, left))
    view.mouseMoveEvent(event(QEvent.Type.MouseMove, start + QPoint(30, 0), Qt.MouseButton.NoButton, left))
    assert actor.x != 40                                                   # dans la vue : un déplacement ordinaire
    view.mouseMoveEvent(event(QEvent.Type.MouseMove, QPoint(viewport.width() + 50, start.y()), Qt.MouseButton.NoButton, left))

    assert started == [b"Hero"]
    assert (actor.x, actor.y) == (40, 40)                                  # l'acteur n'a pas bougé
    assert scene.mouseGrabberItem() is None
    assert len(get_history()._undo) == 0                                   # et le déplacement n'a laissé aucune entrée
