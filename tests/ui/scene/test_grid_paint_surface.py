"""Le contrat commun de la surface peinte : collision et Grid y passent."""
from core.history import GridPaintCmd, get_history
from core.models.grid import Grid
from core.models.scene import Scene
from ui.scene_manager.grid_paint_surface import GridPaintSurface


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
