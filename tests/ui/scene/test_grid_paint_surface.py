"""Le contrat commun de la surface peinte : collision et Grid y passent."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QGraphicsView, QStyleOptionGraphicsItem

from core.history import GridPaintCmd, get_history
from core.models.grid import Grid, GridValue
from core.models.scene import Scene
from ui.scene_manager.canvas_tools import GridPaintTool
from ui.scene_manager.canvas.canvas_items import GridOverlay
from ui.scene_manager.grid_paint_surface import GridPaintSurface, SceneInpaintingSurface
from ui.scene_manager.scene_canvas import CanvasContainer, SceneEditor


class _Event:
    def __init__(self, button=Qt.MouseButton.LeftButton, held=Qt.MouseButton.LeftButton):
        self._button = button
        self._held = held

    def button(self):
        return self._button

    def buttons(self):
        return self._held


def test_une_grille_et_la_collision_exposent_le_meme_acces_par_case(qapp):
    scene = Scene(name="Arena", collision_map=[[0, 1], [2, 0]],
                  grids=[Grid(name="Terrain", step=16, cells=[[3, 4], [5, 6]])])
    collision = GridPaintSurface("Collision", 8, scene.collision_map)
    terrain = GridPaintSurface(scene.grid("Terrain").name, scene.grid("Terrain").step,
                               scene.grid("Terrain").cells)

    assert collision.scene_to_cell(15, 8) == (1, 1)
    assert terrain.scene_to_cell(31, 16) == (1, 1)
    assert collision.value_at(1, 0) == 1 and terrain.value_at(1, 0) == 4


def test_la_commande_commune_defait_et_refait_une_grille(qapp):
    cells = [[0, 0], [0, 0]]
    surface = GridPaintSurface("Terrain", 16, cells)
    history = get_history()
    history.clear()

    surface.set_value(1, 0, 7)
    history.push_executed(GridPaintCmd(surface, {(1, 0): (0, 7)}))

    assert cells == [[0, 7], [0, 0]]
    assert history.undo() and cells == [[0, 0], [0, 0]]
    assert history.redo() and cells == [[0, 7], [0, 0]]
    history.clear()


def test_la_commande_commune_peut_delaisser_le_stockage_particulier_d_un_calque(qapp):
    calls = []

    class Surface:
        def apply_delta(self, delta, forward):
            calls.append((delta, forward))

    history = get_history()
    history.clear()
    delta = {(2, 3): (None, 4)}
    history.push_executed(GridPaintCmd(Surface(), delta))

    assert history.undo() and calls == [(delta, False)]
    assert history.redo() and calls == [(delta, False), (delta, True)]
    history.clear()


def test_le_pinceau_commun_relie_deux_evenements_et_persiste(qapp):
    cells = [[0] * 6]
    saves = []
    get_history().clear()
    tool = GridPaintTool(None, GridPaintSurface("Terrain", 16, cells), "brush", 7,
                         lambda: saves.append(True))

    tool.on_press(QPointF(1, 1), _Event())
    tool.on_move(QPointF(5 * 16 + 1, 1), _Event())
    tool.on_release(QPointF(5 * 16 + 1, 1), _Event())

    assert cells == [[7] * 6]
    assert saves == [True]
    get_history().clear()


def test_le_remplissage_commun_reste_dans_la_zone_contigue(qapp):
    cells = [[1, 1, 0], [1, 0, 1], [0, 1, 1]]
    get_history().clear()
    tool = GridPaintTool(None, GridPaintSurface("Terrain", 16, cells), "fill", 4, None)

    tool.on_press(QPointF(1, 1), _Event())
    tool.on_release(QPointF(1, 1), _Event())

    assert cells == [[4, 4, 0], [4, 0, 1], [0, 1, 1]]
    get_history().clear()


def test_un_calque_de_fond_expose_le_meme_contrat_de_case(qapp):
    class Controller:
        def tiles_size(self):
            return 3, 2

        def set_override(self, col, row, value, *, refresh=True):
            old = layer.tile_palette_overrides.get((col, row))
            if old == value:
                return False
            if value is None:
                layer.tile_palette_overrides.pop((col, row), None)
            else:
                layer.tile_palette_overrides[(col, row)] = value
            return True

        def refresh(self):
            pass

        def apply_override_delta(self, *_args):
            pass

    layer = type("Layer", (), {"tile_palette_overrides": {}})()
    surface = SceneInpaintingSurface(Controller(), layer, 2)

    assert surface.scene_to_cell(23, 9) == (2, 1)
    assert surface.set_value(2, 1, 5)
    assert surface.value_at(2, 1) == 5
    assert surface.set_value(2, 1, None)
    assert surface.value_at(2, 1) is None


def test_le_bandeau_de_collision_se_place_en_bas_avec_ses_icones(qapp):
    container = CanvasContainer(QGraphicsView())
    container.resize(800, 600)
    container.refresh_paint_surfaces(Scene(name="Arena"))

    container.set_inpaint_strip_visible(True)

    strip = container._paint_strip
    assert strip.x() == (container.width() - strip.width()) // 2
    assert strip.y() == container.height() - strip.height() - 12
    assert len(container._inpaint_bank_strip._btns) == 8
    assert all(not button.icon().isNull()
               for button in container._inpaint_bank_strip._btns.values())
    assert all(mode[0] != "paint_slope" for mode in container._toolbar._PAINT_MODES)
    brush = next(mode for mode in container._toolbar._PAINT_MODES
                 if mode[0] == "paint_brush")
    assert brush[1] == "tool_tile_brush"


def test_le_picker_de_surface_propose_la_creation_d_une_grille(qapp):
    container = CanvasContainer(QGraphicsView())
    requested = []
    container.grid_creation_requested.connect(requested.append)
    container.refresh_paint_surfaces(Scene(name="Arena"))

    container._paint_surface._created("Terrain")

    assert requested == ["Terrain"]
    assert container._paint_surface._create_named


def test_une_grille_affiche_les_octets_reels_plutot_que_des_couleurs(qapp):
    container = CanvasContainer(QGraphicsView())
    container.refresh_paint_surfaces(Scene(
        name="Arena", grids=[Grid(name="basegrid")]))

    container.select_paint_surface("grid:basegrid")

    buttons = container._inpaint_bank_strip._btns
    assert "0x0A" in buttons[10].toolTip()
    assert "0x0F" in buttons[15].toolTip()
    assert "palette" not in buttons[10].toolTip().lower()
    assert all(not button.icon().isNull() for button in buttons.values())


def test_la_surcouche_de_grille_isole_la_zone_et_encadre_les_valeurs(qapp):
    overlay = GridOverlay()
    overlay.load(Grid(name="Terrain", step=16, cells=[[0, 10]]))
    image = QImage(32, 16, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    overlay.paint(painter, QStyleOptionGraphicsItem())
    painter.end()

    empty_cell = image.pixelColor(8, 8)
    inside_value = [image.pixelColor(x, y) for y in range(2, 14) for x in range(18, 30)]
    value_border = [image.pixelColor(x, y) for y in range(3, 13) for x in (16, 17)]
    assert (empty_cell.red(), empty_cell.green(), empty_cell.blue(), empty_cell.alpha()) == (0, 0, 0, 102)
    assert any(color.alpha() for color in inside_value)
    assert any(color.red() > 50 for color in value_border)
    assert not any(color.alpha() and color.blue() > color.red() + 20
                   for color in inside_value)


def test_la_valeur_de_grille_reste_selectionnee_si_les_couleurs_se_repetent(qapp):
    container = CanvasContainer(QGraphicsView())
    container.refresh_paint_surfaces(Scene(name="Arena", grids=[Grid(
        name="Terrain",
        values=[GridValue(value=10, name="Eau"), GridValue(value=11, name="Lave")],
    )]))
    container.select_paint_surface("grid:Terrain")

    container._inpaint_bank_strip._select(11)
    container.refresh_paint_values()

    assert container._inpaint_bank_strip.active() == 11


def test_creer_une_grille_la_dimensionne_la_selectionne_et_l_annule(qapp, monkeypatch):
    class Dispatcher:
        def __init__(self):
            self.saves = 0

        def save_scene(self):
            self.saves += 1

        def status(self, _message):
            pass

    dispatcher = Dispatcher()
    monkeypatch.setattr("ui.scene_manager.scene_canvas.get_dispatcher", lambda: dispatcher)
    history = get_history()
    history.clear()
    editor = SceneEditor()
    scene = Scene(name="Arena")
    editor._project = type("Project", (), {"active_scene": scene})()
    editor._canvas_w, editor._canvas_h = 320, 192
    editor.scene_changed.connect(dispatcher.save_scene)

    editor._on_grid_creation_requested("Terrain")

    grid = scene.grid("Terrain")
    assert grid is not None
    assert (grid.cols, grid.rows) == (20, 12)
    assert editor._canvas_container._paint_surface.value() == "grid:Terrain"
    assert dispatcher.saves == 1

    assert history.undo()
    assert scene.grid("Terrain") is None
    assert editor._canvas_container._paint_surface.value() == "collision"
    history.clear()


def test_la_case_ram_bascule_la_grille_et_s_annule(qapp):
    """La case « Partagée (RAM) » n'apparaît que pour une grille, bascule son
    drapeau `ram` de façon annulable, et reflète l'état du modèle."""
    history = get_history()
    history.clear()
    editor = SceneEditor()
    grid = Grid(name="Flow", step=16, cells=[[0, 0], [0, 0]])
    scene = Scene(name="Arena", grids=[grid])
    editor._project = type("Project", (), {"active_scene": scene})()
    editor._canvas_w = editor._canvas_h = 32
    saves = []
    editor.scene_changed.connect(lambda: saves.append(True))
    editor._canvas_container.refresh_paint_surfaces(scene)
    editor._canvas_container.select_paint_surface("grid:Flow")

    chk = editor._canvas_container._grid_ram
    # Montrée pour une grille, décochée tant que la grille est en ROM.
    assert not chk.isHidden() and chk.isChecked() is False

    editor._on_grid_ram_changed(True)
    assert grid.ram is True and saves == [True]

    assert history.undo() and grid.ram is False
    assert chk.isChecked() is False           # resynchronisée par l'annulation
    assert history.redo() and grid.ram is True
    history.clear()

    # Sur la collision, la case disparaît : le drapeau RAM est propre aux grilles.
    editor._canvas_container.select_paint_surface("collision")
    assert editor._canvas_container._grid_ram.isHidden()


def test_changer_le_pas_reinstalle_l_outil_et_s_annule(qapp, monkeypatch):
    class Dispatcher:
        def __init__(self):
            self.saves = 0

        def save_scene(self):
            self.saves += 1

        def status(self, _message):
            pass

    dispatcher = Dispatcher()
    monkeypatch.setattr("ui.scene_manager.scene_canvas.get_dispatcher", lambda: dispatcher)
    history = get_history()
    history.clear()
    editor = SceneEditor()
    grid = Grid(name="Terrain", step=16, cells=[[1, 2], [3, 4]])
    scene = Scene(name="Arena", grids=[grid])
    editor._project = type("Project", (), {"active_scene": scene})()
    editor._canvas_w = editor._canvas_h = 32
    editor.scene_changed.connect(dispatcher.save_scene)
    editor.show()
    qapp.processEvents()
    editor._canvas_container.refresh_paint_surfaces(scene)
    editor._canvas_container.select_paint_surface("grid:Terrain")
    editor._canvas_container.activate_paint_gesture("paint_brush")

    assert editor._canvas_container._grid_step.currentData() == 16
    assert not editor._canvas_container._grid_step.isHidden()
    assert editor._gba_view._active_tool._surface.cell_size == 16

    editor._on_grid_step_changed(8)

    assert grid.step == 8
    assert (grid.cols, grid.rows) == (4, 4)
    assert editor._gba_view._active_tool._surface.cell_size == 8
    assert dispatcher.saves == 1

    assert history.undo()
    assert grid.step == 16
    assert grid.cells == [[1, 2], [3, 4]]
    assert editor._gba_view._active_tool._surface.cell_size == 16
    history.clear()
