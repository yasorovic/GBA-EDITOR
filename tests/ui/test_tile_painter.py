"""Le pinceau à deux modes. Paint est un CALQUE par-dessus l'image : il ne touche ni le tileset ni la tilemap, la
gomme et le clic droit rendent la tuile initiale, la couleur 0 cache l'image. Inpaint ne surcharge que la palette."""
from __future__ import annotations

from core.blank_assets import build_background
from core.history import BackgroundTilePaintCmd
from core.models.background import BackgroundAsset
from core.models.gba_color import bgr555_to_rgb888
from core.models.tile_codec import pack_se, unpack_se
from ui.background_editor.bg_inpaint_canvas import BgInpaintController, BgInpaintView
import pytest


@pytest.fixture
def preparation_tools(monkeypatch):
    """Rouvre les outils gelés (compression, ajustements, miroir) pour les tests qui les exercent encore : le gel
    est temporaire, ces fonctions n'ont pas changé (cf. PREPARATION_TOOLS_ENABLED)."""
    from ui.background_editor import bg_inpaint_canvas
    monkeypatch.setattr(bg_inpaint_canvas, "PREPARATION_TOOLS_ENABLED", True)


def _blank():
    _store, ba = build_background(type("P", (), {"backgrounds": []})())
    ba.palettes[0][1:3] = [0x7FFF, 0x001F]
    ba.added_palettes = ["Test"]          # la peinture ne se pose que sur une palette AJOUTÉE : la banque 0 en est une
    return ba


def _with_image():
    """Un fond AVEC image : la case (1,1) montre une tuile opaque de couleur 1, le reste est transparent."""
    ba = _blank()
    ba.asset = "images/photo.png"
    ba.tileset.append("1" * 64)
    ba.tilemap[1 * ba.tiles_w + 1] = pack_se(1, 0, False, False)
    return ba


def _controller(ba, mode="paint"):
    ctrl = BgInpaintController()
    ctrl.set_context(None, ba)
    ctrl.set_mode(mode)
    return ctrl


def _alpha(ctrl, col, row):
    return ctrl._qimg.pixelColor(col * 8, row * 8).alpha()


def _stroke(ctrl, cells, erase=False, both=False):
    ctrl.begin_stroke(both=both)
    ctrl.paint_cells(cells, erase=erase)
    delta = dict(ctrl._tile_stroke or {})
    ctrl.end_stroke()
    return delta


def test_the_active_color_returns_to_one_with_a_new_background(qapp):
    ctrl = _controller(_blank())
    ctrl.set_active_color(7)

    ctrl.set_context(None, _blank())

    assert ctrl._active_color == 1                                  # la pastille affiche la 1


def test_paint_is_a_layer_that_leaves_the_image_data_untouched(qapp):
    ba = _with_image()
    tileset, tilemap = list(ba.tileset), list(ba.tilemap)
    ctrl = _controller(ba)

    _stroke(ctrl, [(1, 1), (2, 2)])

    assert (ba.tileset, ba.tilemap) == (tileset, tilemap)           # le PNG compressé n'a pas bougé
    assert ba.tile_paint == {(1, 1): (1, 0), (2, 2): (1, 0)}
    assert unpack_se(ba.effective_tilemap()[ba.tiles_w + 1])[0] == ba.effective_tileset().index("1" * 64)


def test_the_eraser_gives_back_the_original_tile(qapp):
    ba = _with_image()
    ctrl = _controller(ba)
    ctrl.set_active_color(2)
    _stroke(ctrl, [(1, 1)])
    assert ctrl._qimg.pixelColor(8, 8).getRgb()[:3] == bgr555_to_rgb888(0x001F)       # la peinture couvre l'image

    _stroke(ctrl, [(1, 1)], erase=True)

    assert ba.tile_paint == {} and ctrl._qimg.pixelColor(8, 8).getRgb()[:3] == bgr555_to_rgb888(0x7FFF)


def test_color_zero_makes_the_image_transparent_under_the_cell(qapp):
    ba = _with_image()
    ctrl = _controller(ba)
    assert _alpha(ctrl, 1, 1) == 255

    ctrl.set_active_color(0)
    _stroke(ctrl, [(1, 1)])

    assert _alpha(ctrl, 1, 1) == 0 and ba.tile_paint[(1, 1)][0] == 0
    _stroke(ctrl, [(1, 1)], erase=True)
    assert _alpha(ctrl, 1, 1) == 255                                 # l'image revient


def test_undo_and_redo_only_move_the_paint_layer(qapp):
    ba = _with_image()
    ctrl = _controller(ba)
    cmd = BackgroundTilePaintCmd(ctrl, ba, _stroke(ctrl, [(1, 1), (4, 4)]))

    cmd.undo()
    assert ba.tile_paint == {}
    cmd.execute()
    assert set(ba.tile_paint) == {(1, 1), (4, 4)}


def test_a_cell_painted_twice_in_a_stroke_undoes_to_its_first_state(qapp):
    ba = _blank()
    ctrl = _controller(ba)
    ctrl.begin_stroke()
    ctrl.paint_cells([(0, 0)])
    ctrl.set_active_color(2)
    ctrl.paint_cells([(0, 0)])
    cmd = BackgroundTilePaintCmd(ctrl, ba, dict(ctrl._tile_stroke))

    cmd.undo()

    assert ba.tile_paint == {}


def test_a_large_brush_notifies_once_and_the_pixels_are_painted(qapp):
    ba = _blank()
    ctrl = _controller(ba)
    renders = []
    ctrl.on_rendered = lambda: renders.append(1)
    view = BgInpaintView.__new__(BgInpaintView)
    view._ctrl, view._brush_size, view._tool, view._erase_gesture = ctrl, 32, "brush", False

    ctrl.begin_stroke()
    view._apply_brush(5, 5)

    assert len(renders) == 1                                        # 16 cases, un seul rafraîchissement
    assert _alpha(ctrl, 4, 4) == 255 and _alpha(ctrl, 8, 8) == 0


def test_a_right_click_gesture_erases_with_the_brush(qapp):
    ba = _blank()
    ctrl = _controller(ba)
    view = BgInpaintView.__new__(BgInpaintView)
    view._ctrl, view._brush_size, view._tool, view._erase_gesture = ctrl, 8, "brush", False
    ctrl.begin_stroke()
    view._apply_brush(3, 3)
    assert (3, 3) in ba.tile_paint

    view._erase_gesture = True
    view._apply_brush(3, 3)

    assert ba.tile_paint == {}


def test_the_inpaint_override_survives_under_the_paint_and_comes_back(qapp):
    ba = _with_image()
    ba.add_palette_ref("Green", [0, 0x03E0] + [0] * 14)
    ctrl = _controller(ba, "inpaint")
    ctrl.set_active_palette(1)
    _stroke(ctrl, [(1, 1)])
    assert ba.tile_palette_overrides == {(1, 1): 1}

    ctrl.set_mode("paint")
    ctrl.set_active_palette(0)
    _stroke(ctrl, [(1, 1)])
    _stroke(ctrl, [(1, 1)], erase=True)

    assert ba.tile_palette_overrides == {(1, 1): 1} and ba.tile_paint == {}


def test_inpaint_mode_only_overrides_the_palette(qapp):
    ba = _blank()
    ba.add_palette_ref("Green", [0, 0x03E0] + [0] * 14)
    ctrl = _controller(ba, "inpaint")
    ctrl.set_active_palette(1)

    _stroke(ctrl, [(3, 3)])

    assert ba.tile_palette_overrides == {(3, 3): 1} and ba.tile_paint == {}


def test_paint_fill_rect_and_eraser_write_the_layer(qapp):
    ba = _blank()
    ctrl = _controller(ba)
    ctrl.begin_stroke()
    ctrl.fill(0, 0)                                                  # fond vierge : tout l'écran
    assert len(ba.tile_paint) == ba.tiles_w * ba.tiles_h
    ctrl.paint_rect(2, 2, 3, 3, erase=True)                          # la gomme rend les cases à l'image
    assert (2, 2) not in ba.tile_paint and (3, 3) not in ba.tile_paint and (4, 4) in ba.tile_paint
    assert ba.tile_palette_overrides == {}


def test_the_layer_composes_the_tileset_without_duplicating_tiles(qapp):
    ba = _with_image()                                               # l'image a déjà une tuile pleine de couleur 1
    ba.tile_paint = {(0, 0): (1, 0), (5, 5): (3, 0), (6, 6): (3, 0)}

    tiles = ba.effective_tileset()

    assert tiles == ba.tileset + ["3" * 64] and ba.tileset == ["0" * 64, "1" * 64]
    assert unpack_se(ba.effective_tilemap()[0])[0] == 1             # réutilise l'existante
    assert unpack_se(ba.effective_tilemap()[5 * ba.tiles_w + 5])[0] == 2


def test_the_layer_round_trips_and_follows_palette_removal(qapp):
    ba = _blank()
    ba.add_palette_ref("Green", [0, 0x03E0] + [0] * 14)
    ba.tile_paint = {(0, 0): (2, 1), (1, 0): (2, 0)}                 # une peinture par POSITION dans added_palettes

    again = BackgroundAsset.from_dict(ba.to_dict())
    assert again.tile_paint == ba.tile_paint and again.added_palettes == ["Test", "Green"]

    ba.remove_palette(0)
    assert ba.added_palettes == ["Green"]
    assert ba.tile_paint == {(0, 0): (2, 0)}         # la peinture de la palette retirée disparaît, la suivante avance d'un cran


def test_the_layer_is_ignored_outside_tiled_4bpp_and_off_grid(qapp):
    ba = _blank()
    ba.tile_paint = {(0, 0): (1, 0), (99, 99): (1, 0)}
    assert set(ba.painted_cells()) == {(0, 0)}
    ba.bpp = 8
    assert ba.painted_cells() == {} and ba.effective_tilemap() == ba.tilemap


def test_the_first_color_dot_is_the_crossed_transparency_whatever_the_slot_value(qapp):
    from ui.background_editor.bg_inpaint_canvas import TileColorStrip
    strip = TileColorStrip()
    strip.load([0x7FFF] + [0x001F] * 15)                            # un index 0 non noir : il reste « transparent »

    assert strip._buttons[0]._index == 0 and strip._buttons[0].toolTip() != strip._buttons[1].toolTip()
    image = strip._buttons[0].grab().toImage()
    reds = sum(1 for x in range(image.width()) for y in range(image.height())
               if image.pixelColor(x, y).red() > 200 and image.pixelColor(x, y).green() < 90)
    assert reds > 5                                                  # le trait rouge est bien tracé


def test_the_color_strip_follows_the_palette_embedded_by_the_asset(qapp):
    from ui.background_editor.bg_inpaint_canvas import BgInpaintCanvas
    ba = _blank()
    ba.add_palette_ref("Green", [0x0000, 0x03E0] + [0] * 14)
    canvas = BgInpaintCanvas()
    canvas.load(None, ba)
    assert canvas._color_strip.isVisibleTo(canvas)

    canvas._paint_strip._select(1)
    canvas.set_active_palette(1)
    canvas.set_active_color(1)
    ba.palettes[1][1] = 0x7C00                                       # édition côté inspecteur
    canvas.reload()

    assert canvas._color_strip._buttons[1]._rgb.getRgb()[:3] == bgr555_to_rgb888(0x7C00)
    assert canvas._ctrl._active_pal == 1

    canvas._toolbar.set_mode("inpaint")                              # en Inpaint, seule la banque compte
    assert not canvas._color_strip.isVisibleTo(canvas)


def test_the_brush_toolbar_has_one_brush_with_a_mode_and_shapes_the_hints(qapp):
    from ui.background_editor.bg_inpaint_canvas import BgInpaintToolbar
    from ui.background_editor.bg_hints import background_hints
    bar = BgInpaintToolbar()
    seen = []
    bar.mode_changed.connect(seen.append)

    assert "tile_brush" not in bar._btns and bar.mode == "inpaint" and bar.hint_context == "brush"
    bar.set_mode("paint")
    bar.set_mode("paint")

    assert seen == ["paint"] and bar.hint_context == "brush_paint"
    assert background_hints("brush_paint")[1][0][1] == "hints.bg.paint_tiles"
    assert background_hints("eraser_paint")[1][0][1] == background_hints("eraser")[1][0][1] == "hints.bg.erase_all"


def test_a_background_without_image_opens_in_paint_mode_and_a_sourced_one_keeps_the_choice(qapp):
    from ui.background_editor.bg_inpaint_canvas import BgInpaintCanvas
    canvas = BgInpaintCanvas()
    canvas.load(None, _blank())
    assert canvas._toolbar.mode == "paint" and canvas._ctrl.mode == "paint"
    assert canvas._color_strip.isVisibleTo(canvas)

    canvas._toolbar.set_mode("inpaint")
    canvas.load(None, _with_image())
    assert canvas._toolbar.mode == "inpaint"


def test_the_eraser_purges_both_layers_in_one_undo_while_right_click_follows_the_mode(qapp):
    from core.history import MacroCmd, get_history
    ba = _with_image()
    ba.add_palette_ref("Green", [0, 0x03E0] + [0] * 14)
    ctrl = _controller(ba, "inpaint")
    ctrl.set_active_palette(1)
    _stroke(ctrl, [(1, 1)])                                          # surcharge de palette
    ctrl.set_mode("paint")
    _stroke(ctrl, [(1, 1)])                                          # + peinture
    assert ba.tile_palette_overrides and ba.tile_paint

    undo_before = len(get_history()._undo)
    _stroke(ctrl, [(1, 1)], erase=True, both=True)                   # la gomme : les deux d'un coup

    assert ba.tile_palette_overrides == {} and ba.tile_paint == {}
    assert len(get_history()._undo) == undo_before + 1 and isinstance(get_history()._undo[-1], MacroCmd)
    get_history()._undo[-1].undo()
    assert ba.tile_palette_overrides == {(1, 1): 1} and ba.tile_paint == {(1, 1): (1, 1)}

    _stroke(ctrl, [(1, 1)], erase=True)                              # clic droit en Paint : la peinture seule
    assert ba.tile_paint == {} and ba.tile_palette_overrides == {(1, 1): 1}


def test_restore_original_purges_both_layers_of_a_background_without_image(qapp, tmp_path, monkeypatch):
    from core.project import Project
    from ui.common.popup import MessageBox as QMessageBox
    from ui.background_editor.background_editor_screen import BgPropertiesPanel
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    project = Project(tmp_path)
    ba = _blank()
    ba.tile_paint, ba.tile_palette_overrides = {(1, 1): (1, 0)}, {(2, 2): 0}
    project.backgrounds.append(ba)
    panel = BgPropertiesPanel()
    panel._project, panel._ba = project, ba
    refreshed = []
    panel.changed.connect(lambda: refreshed.append(1))

    panel._on_restore()

    assert ba.tile_paint == {} and ba.tile_palette_overrides == {} and refreshed


def test_only_the_brush_opens_the_mode_menu_and_the_eraser_just_selects(qapp):
    from ui.background_editor.bg_inpaint_canvas import BgInpaintToolbar
    bar = BgInpaintToolbar()
    opened = []
    bar._show_brush_menu = lambda tool: opened.append(tool)

    bar._btns["eraser"].click()
    assert opened == [] and bar.current_tool == "eraser"
    bar._btns["fill"].click()
    assert opened == [] and bar.current_tool == "fill"


def test_the_palette_strip_keeps_its_width_when_a_palette_is_added_while_shown(qapp):
    from ui.background_editor.bg_inpaint_canvas import BgInpaintCanvas
    ba = _blank()
    canvas = BgInpaintCanvas()
    canvas.resize(900, 500)
    canvas.load(None, ba)
    canvas.show()
    qapp.processEvents()
    before = canvas._paint_strip.width()

    ba.add_palette_ref("Green", [0, 0x03E0] + [0] * 14)
    canvas.reload()
    qapp.processEvents()

    assert canvas._paint_strip.width() > before and canvas._paint_strip.height() > 30   # pas un carré de marges


def _panel():
    from ui.background_editor.background_editor_screen import BgPropertiesPanel
    return BgPropertiesPanel()


def _sourced(diagnostics):
    ba = _with_image()
    ba.diagnostics = diagnostics
    return ba


def test_the_compression_box_is_absent_for_a_background_without_image(qapp):
    panel = _panel()
    panel.load(_blank(), None)

    assert not panel._comp_card.isVisibleTo(panel) and not panel._tune_host.isVisibleTo(panel)


def test_the_compression_box_is_always_open_on_load_even_when_the_image_fits_and_folds_on_click(qapp, preparation_tools):
    panel = _panel()
    panel.load(_sourced({"multiple_of_8": True, "max_tile_colors": 4}), None)

    assert panel._comp_card.isVisibleTo(panel) and panel._tune_host.isVisibleTo(panel) and panel._comp_host.isVisibleTo(panel)
    panel._comp_card.set_expanded(not panel._comp_card.is_expanded())
    assert not panel._tune_host.isVisibleTo(panel)
    panel._comp_card.set_expanded(not panel._comp_card.is_expanded())
    assert panel._tune_host.isVisibleTo(panel) and panel._comp_host.isVisibleTo(panel)


def test_the_compression_box_opens_by_itself_when_the_image_does_not_fit(qapp):
    panel = _panel()
    panel.load(_sourced({"multiple_of_8": True, "max_tile_colors": 20, "tiles_reduced": 3}), None)

    assert panel._tune_host.isVisibleTo(panel) and panel._comp_card.is_expanded()


def test_the_compression_box_opens_when_settings_leave_the_default(qapp):
    ba = _sourced({"multiple_of_8": True, "max_tile_colors": 4})
    ba.compression.palettes_max = 4
    panel = _panel()
    panel.load(ba, None)

    assert panel._tune_host.isVisibleTo(panel)


def test_reloading_the_same_background_keeps_the_users_fold_and_another_one_opens_the_box(qapp, preparation_tools):
    ba = _sourced({"multiple_of_8": True, "max_tile_colors": 20, "tiles_reduced": 3})
    panel = _panel()
    panel.load(ba, None)
    assert panel._tune_host.isVisibleTo(panel)
    panel._comp_card.set_expanded(not panel._comp_card.is_expanded())                                              # l'auteur replie la boîte
    ba.diagnostics = {"multiple_of_8": True, "max_tile_colors": 4}      # la recompression a réglé le problème

    panel.load(ba, None)

    assert not panel._tune_host.isVisibleTo(panel)                       # le même fond ne rouvre ni ne referme rien sous lui
    panel.load(_sourced({"multiple_of_8": True, "max_tile_colors": 4}), None)   # un AUTRE fond : la boîte est toujours ouverte
    assert panel._tune_host.isVisibleTo(panel)


def _panel_with_project(tmp_path):
    from core.project import Project
    project = Project(tmp_path)
    ba = _blank()
    ba.add_palette_ref("Second", [0, 0x7C00, 0x03E0] + [0] * 13)
    ba.tile_paint = {(0, 0): (1, 0), (1, 0): (2, 1), (2, 0): (0, 0)}
    ba.tile_palette_overrides = {(3, 3): 1}
    project.backgrounds.append(ba)
    panel = _panel()
    panel.load(ba, project)
    return project, ba, panel


def test_save_as_png_bakes_every_layer_into_a_new_source_without_changing_the_picture(qapp, tmp_path, monkeypatch):
    from ui.common.popup import MessageBox as QMessageBox
    from core.bg_bake import render_rgba
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    project, ba, panel = _panel_with_project(tmp_path)
    before = render_rgba(ba)
    palettes_before = [list(p) for p in ba.palettes]

    panel._on_save_png()

    assert ba.asset and project.background_image_path(ba).is_file()
    assert ba.tile_paint == {} and ba.tile_palette_overrides == {}      # tout est cuit dans l'image
    assert render_rgba(ba).tobytes() == before.tobytes()                # le rendu n'a pas bougé d'un pixel
    assert [p[1:4] for p in ba.palettes] == [p[1:4] for p in palettes_before]   # ni les banques


def test_save_as_png_never_overwrites_an_existing_source(qapp, tmp_path, monkeypatch):
    from ui.common.popup import MessageBox as QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    project, ba, panel = _panel_with_project(tmp_path)
    taken = project.background_images_dir / f"{ba.name}.png"
    taken.parent.mkdir(parents=True, exist_ok=True)
    taken.write_bytes(b"not an image of ours")

    panel._on_save_png()

    assert taken.read_bytes() == b"not an image of ours" and ba.asset.endswith(f"{ba.name}_2.png")


def test_save_as_png_changes_nothing_when_declined_or_when_the_background_cannot_be_baked(qapp, tmp_path, monkeypatch):
    from ui.common.popup import MessageBox as QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    project, ba, panel = _panel_with_project(tmp_path)

    panel._on_save_png()

    assert ba.asset == "" and ba.tile_paint

    ba.bpp = 8
    panel._refresh_png_buttons()
    assert not panel._btn_save_png.isEnabled() and panel._btn_export_png.isEnabled()


def test_export_to_png_writes_the_displayed_image_wherever_asked_and_changes_nothing(qapp, tmp_path, monkeypatch):
    from PIL import Image
    from PyQt6.QtWidgets import QFileDialog
    _project, ba, panel = _panel_with_project(tmp_path)
    target = tmp_path / "elsewhere" / "shot"
    target.parent.mkdir()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))

    panel._on_export_png()

    out = Image.open(str(target) + ".png")
    assert out.mode == "P" and out.size == (240, 160) and ba.asset == "" and ba.tile_paint   # indexé par banques


def _screen_in(tmp_path, folder):
    from core.project import Project
    from ui.background_editor.background_editor_screen import BackgroundEditorScreen
    project = Project(tmp_path)
    screen = BackgroundEditorScreen()
    screen.load_project(project)
    screen.folder_provider = lambda: str(folder)
    return project, screen


def test_create_empty_makes_a_transparent_png_and_its_background_in_the_shown_folder(qapp, tmp_path):
    from PIL import Image
    project = None
    folder = tmp_path / "assets" / "levels" / "one"
    folder.mkdir(parents=True)
    project, screen = _screen_in(tmp_path, folder)
    started = []
    screen._compress_async = lambda ba, dst, token, *a, **k: started.append((ba, dst, token))

    screen._create_blank_background()

    ba, dst, token = started[0]
    assert dst.parent == folder and dst.suffix == ".png" and token == "tiled4"
    image = Image.open(dst)
    assert image.mode == "P" and image.size == (240, 160) and image.info.get("transparency") == 0
    assert ba.asset and project.background_image_path(ba) == dst


def test_import_copies_the_png_into_the_shown_folder_and_outside_assets_falls_back(qapp, tmp_path):
    folder = tmp_path / "assets" / "levels"
    folder.mkdir(parents=True)
    project, screen = _screen_in(tmp_path, folder)
    assert screen._target_folder() == folder
    screen.folder_provider = lambda: str(tmp_path / "elsewhere")
    assert screen._target_folder() == project.assets_dir / "backgrounds"


def test_the_transparent_area_is_a_neutral_checker_under_the_image(qapp):
    from ui.background_editor.bg_inpaint_canvas import _checker_tile
    tile = _checker_tile().toImage()
    assert tile.pixelColor(0, 0) != tile.pixelColor(8, 0) and tile.pixelColor(0, 0) == tile.pixelColor(8, 8)


def test_choosing_a_mode_only_stages_it_until_compress_is_pressed(qapp, tmp_path):
    from PIL import Image
    project, ba, panel = _panel_with_project(tmp_path)
    png = project.background_images_dir / "src.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("P", (16, 16), 0).save(png)
    ba.asset = project.asset_rel(png)
    panel.load(ba, project)
    asked = []
    panel.preview_requested.connect(asked.append)

    panel._d8.click()
    assert asked == [] and panel._is_pending() and panel._d8.isChecked()      # choisir ne demande rien tout de suite

    panel._d4.click()                                                # revenir au mode courant : plus rien à valider
    assert not panel._is_pending()

    panel._d8.click()
    panel._emit_request()                                   # après la pause, le service reçoit le mode choisi
    assert len(asked) == 1 and asked[0]["token"] == "tiled8" and panel.settings()["token"] == "tiled8"
    panel._d4.click()
    panel._emit_request()
    assert asked[-1] is None                                         # revenu au fond courant : la demande tombe


def test_the_inspector_scrolls_instead_of_squashing_its_widgets_when_the_compression_box_opens(qapp):
    from PyQt6.QtWidgets import QScrollArea
    ba = _sourced({"multiple_of_8": True, "max_tile_colors": 20, "tiles_reduced": 3})   # s'ouvre d'office
    panel = _panel()
    panel.resize(300, 400)
    panel.load(ba, None)
    panel.show()
    qapp.processEvents()

    scroll = panel.findChild(QScrollArea)
    body = scroll.widget()

    assert body.height() >= body.minimumSizeHint().height() and body.height() > scroll.viewport().height()
    assert panel._sl_palettes._row.height() >= 20


def _shown_canvas(qapp):
    from ui.background_editor.bg_inpaint_canvas import BgInpaintCanvas
    canvas = BgInpaintCanvas()
    canvas.resize(900, 600)
    canvas.load(None, _blank())
    canvas.show()
    qapp.processEvents()
    return canvas, canvas._view


def test_the_middle_button_pans_freely_even_when_the_image_is_smaller_than_the_view(qapp):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    _canvas, view = _shown_canvas(qapp)
    view.zoom_step(-3)                                              # l'image tient largement dans la vue
    qapp.processEvents()
    before = view.mapFromScene(0, 0)

    QTest.mousePress(view.viewport(), Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 300))
    QTest.mouseMove(view.viewport(), QPoint(380, 340))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier, QPoint(380, 340))

    after = view.mapFromScene(0, 0)
    assert (after.x() - before.x(), after.y() - before.y()) == (80, 40)   # l'image suit la main, au pixel près


def test_the_wheel_zooms_around_the_pointer(qapp):
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent
    _canvas, view = _shown_canvas(qapp)
    anchor = QPoint(200, 150)
    under = view.mapToScene(anchor)

    event = QWheelEvent(QPointF(anchor), QPointF(view.viewport().mapToGlobal(anchor)), QPoint(), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    view.wheelEvent(event)

    moved = view.mapFromScene(under) - anchor
    assert abs(moved.x()) <= 1 and abs(moved.y()) <= 1 and view._zoom > 2.0


def test_the_view_caches_its_background_and_the_hover_halo_is_drawn_in_the_foreground(qapp):
    from PyQt6.QtWidgets import QGraphicsView
    _canvas, view = _shown_canvas(qapp)
    assert view.cacheMode() & QGraphicsView.CacheModeFlag.CacheBackground
    assert type(view).drawForeground is not QGraphicsView.drawForeground


def test_edit_png_is_a_text_button_over_the_canvas_enabled_only_with_a_source(qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QPushButton
    canvas, _view = _shown_canvas(qapp)

    assert isinstance(canvas._btn_edit, QPushButton) and canvas._btn_edit.text() == "Edit .png"
    assert not canvas._btn_edit.isEnabled()                          # fond sans image
    assert abs(canvas._btn_edit.geometry().center().x() - canvas.width() // 2) <= 2
    canvas.load(None, _with_image())
    assert canvas._btn_edit.isEnabled()                              # un fond avec image
    assert canvas._btn_edit.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu   # le clic droit propose un autre éditeur


def test_compression_box_is_in_resolution_order_with_global_colors_and_dithering_first(qapp):
    ba = _sourced({"multiple_of_8": True, "max_tile_colors": 20, "tiles_reduced": 3})
    panel = _panel()
    panel.load(ba, None)
    panel.show()
    qapp.processEvents()
    comp = panel._comp_host.layout()

    assert comp.itemAt(2).widget() is panel._sl_global._row              # sous le titre : la réduction globale d'abord
    assert not panel._btn_analyze.isVisibleTo(panel)                     # la mesure reste, masquée
    ys = lambda w: w.mapTo(panel, w.rect().topLeft()).y()
    # L'ordre où l'encodeur résout : global, dithering, méthode, couleurs par palette, palettes, tuiles.
    assert (ys(panel._sl_global._row) < ys(panel._chk_dither) < ys(panel._cmb_method) < ys(panel._sl_colors._row)
            < ys(panel._sl_palettes._row) < ys(panel._sl_tiles._row))


def test_the_adjust_sliders_sit_above_the_compression_box_and_feed_one_request(qapp):
    from core.models.background import BackgroundAdjust
    ba = _sourced({"multiple_of_8": True, "max_tile_colors": 20, "tiles_reduced": 3})
    ba.adjust = BackgroundAdjust(hue=40, brightness=-20)
    panel = _panel()
    panel.load(ba, None)
    panel.show()
    qapp.processEvents()
    ys = lambda w: w.mapTo(panel, w.rect().topLeft()).y()

    assert panel._current_adjust() == ba.adjust                                    # les curseurs montrent le fond
    assert ys(panel._sl_hue) < ys(panel._sl_global._row) < ys(panel._chk_dither)   # avant la compression
    asked = []
    panel._sl_con.setValue(30)
    assert asked == [] and panel._is_pending()               # un curseur ne compresse pas
    assert panel._current_adjust().contrast == 30

    panel._on_adjust_reset()
    assert panel._current_adjust() == BackgroundAdjust()


def test_the_dither_type_waits_for_compress_like_the_checkbox_and_lands_in_the_compression(qapp, tmp_path):
    from PIL import Image
    project, ba, panel = _panel_with_project(tmp_path)
    png = project.background_images_dir / "d.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("P", (16, 16), 0).save(png)
    ba.asset = project.asset_rel(png)
    panel.load(ba, project)
    asked = []

    panel._cmb_dither.setCurrentIndex(panel._cmb_dither.findData("bayer4"))
    assert asked == [] and panel._is_pending()

    assert panel._current_compression().dither_kind == "bayer4" and panel.settings()["compression"].dither_kind == "bayer4"


def test_no_slider_compresses_by_itself_and_every_reset_only_stages(qapp):
    from core.models.background import BackgroundAdjust, BackgroundCompression
    ba = _sourced({"multiple_of_8": True, "max_tile_colors": 20, "tiles_reduced": 3})
    panel = _panel()
    panel.load(ba, None)
    asked = []
    panel.recompress_requested.connect(lambda *a: asked.append(a))
    assert not panel._is_pending()                            # rien à valider à l'ouverture

    panel._sl_palettes.setValue(4)
    panel._sl_hue.setValue(25)
    assert asked == [] and panel._is_pending()
    panel._sl_palettes.setValue(16)
    panel._sl_hue.setValue(0)
    assert not panel._is_pending()                            # revenu au fond courant : plus rien

    ba.compression = BackgroundCompression(palettes_max=4)
    ba.adjust = BackgroundAdjust(hue=40)
    panel.load(ba, None)
    assert not panel._is_pending()
    panel._on_comp_reset()
    panel._on_adjust_reset()
    assert asked == [] and panel._is_pending()                # les remises au neutre attendent « Compress »
    assert panel._current_compression().is_default() and panel._current_adjust().is_default()


def _bright_png(project):
    from PIL import Image
    png = project.background_images_dir / "bright.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), (200, 40, 40)).save(png)
    return png


def test_the_adjustments_and_the_compression_are_two_detached_cards_and_compress_ends_the_second(qapp, tmp_path):
    from PyQt6.QtWidgets import QFrame
    project, ba, panel = _panel_with_project(tmp_path)
    ba.asset = project.asset_rel(_bright_png(project))
    panel.load(ba, project)
    panel.show()
    qapp.processEvents()
    ys = lambda w: w.mapTo(panel, w.rect().topLeft()).y()

    assert panel._adj_card is not panel._comp_card and isinstance(panel._adj_card, QFrame)
    assert panel._adj_card.isAncestorOf(panel._sl_hue) and not panel._comp_card.isAncestorOf(panel._sl_hue)
    panel._sl_hue.setValue(30)                                       # un réglage en attente ouvre la carte de compression…
    assert panel._comp_card.isVisibleTo(panel) and panel._tune_host.isVisibleTo(panel)
    assert panel._is_pending() and ys(panel._adj_card) < ys(panel._comp_card)


def test_moving_an_adjustment_previews_the_adjusted_image_live_and_never_compresses(qapp, tmp_path):
    project, ba, panel = _panel_with_project(tmp_path)
    ba.asset = project.asset_rel(_bright_png(project))
    panel.load(ba, project)
    previews, applied = [], []
    panel.adjust_preview_requested.connect(previews.append)

    panel._sl_bri.setValue(40)
    panel._emit_adjust_preview()
    assert applied == [] and previews[-1] is not None and previews[-1].brightness == 40

    panel._on_adjust_reset()                                         # revenu au fond courant : le rendu compressé
    assert previews[-1] is None


def test_the_screen_shows_the_adjusted_image_in_place_of_the_compressed_render_then_gives_it_back(qapp, tmp_path):
    from core.models.background import BackgroundAdjust
    project, ba, _panel = _panel_with_project(tmp_path)
    ba.asset = project.asset_rel(_bright_png(project))
    screen = _screen_in(tmp_path, tmp_path)[1]
    screen._project = project
    screen._props._ba = ba
    canvas = screen._canvas
    canvas.load(project, ba)

    screen._on_adjust_preview(BackgroundAdjust(hue=120))

    view = canvas._view
    assert view._adjust_item.isVisible() and not view._pix_item.isVisible()
    shown = view._adjust_item.pixmap().toImage().pixelColor(2, 2)
    assert shown.green() > shown.red()                               # le rouge est devenu vert

    screen._on_adjust_preview(None)
    assert not view._adjust_item.isVisible() and view._pix_item.isVisible()


def test_the_dithering_checkbox_and_its_type_unlock_together_when_global_colors_is_raised(qapp, preparation_tools):
    ba = _sourced({"multiple_of_8": True, "max_tile_colors": 20, "tiles_reduced": 3})
    panel = _panel()
    panel.load(ba, None)

    assert not panel._chk_dither.isEnabled() and not panel._cmb_dither.isEnabled()       # Global colors : Off
    panel._sl_global.setValue(32)
    assert panel._chk_dither.isEnabled() and panel._cmb_dither.isEnabled()
    panel._chk_dither.setChecked(True)
    panel._cmb_dither.setCurrentIndex(panel._cmb_dither.findData("bayer4"))
    assert panel._chk_dither.isChecked() and panel._is_pending()

    panel._on_comp_reset()                                                               # retour à Off : les deux se regrisent
    assert not panel._chk_dither.isEnabled() and not panel._cmb_dither.isEnabled()


def _photo_png(project, name="photo.png"):
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(5)
    png = project.background_images_dir / name
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rng.integers(0, 256, (32, 32, 3), dtype=np.uint8), "RGB").save(png)
    return png


def _wait(qapp, condition, seconds=15):
    import time
    end = time.time() + seconds
    while time.time() < end and not condition():
        qapp.processEvents()
        time.sleep(0.01)
    return condition()


def _screen_on_photo(tmp_path, qapp):
    project, ba, _panel = _panel_with_project(tmp_path)
    ba.asset = project.asset_rel(_photo_png(project))
    ba.palettes = [list(ba.palettes[0])]
    ba.added_palettes = []                      # le fixture repart d'une seule palette, sans référence ajoutée
    screen = _screen_in(tmp_path, tmp_path)[1]
    screen._project = project
    screen._props._ba = ba
    screen._props._project = project
    screen._canvas.load(project, ba)
    screen._props.load(ba, project)
    return project, ba, screen


def _idle(screen) -> bool:
    """Plus aucun calcul en cours dans le service d'encodage de l'écran."""
    return screen._encoding._running is None


def label_of(key):
    from ui.common.labels import label
    return label(key)


def test_a_pending_setting_is_encoded_in_the_background_and_commits_by_itself_when_it_is_cheap(qapp, tmp_path):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    assert ba.compression.palettes_max != 3

    screen._props._sl_palettes.setValue(3)
    screen._on_encoding_wanted(screen._props.settings())

    assert screen._canvas._enc_box.isVisibleTo(screen._canvas)                         # l'attente se voit, dans la ligne d'état
    assert not screen._canvas._btn_run_encoding.isEnabled()                            # le calcul est parti tout seul : le bouton attend
    assert _wait(qapp, lambda: ba.compression.palettes_max == 3 and _idle(screen))     # le calcul part tout seul et se valide
    assert ba.encoding_is_current() and len(ba.palettes) <= 3
    assert screen._canvas._enc_box.isVisibleTo(screen._canvas) and screen._canvas._btn_run_encoding.isEnabled()   # la ligne reste : « Encoded »


def test_an_expensive_background_waits_for_recompute_then_commits(qapp, tmp_path):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    screen._encoding._auto_seconds = 4.0                                              # le seuil de coût, quand il est posé
    screen._encoding._seconds[screen._encoding._id(ba)] = 9.0                         # son dernier encodage a été cher
    screen._props._sl_palettes.setValue(3)

    screen._on_encoding_wanted(screen._props.settings())

    assert _idle(screen) and ba.compression.palettes_max != 3                          # rien ne part tout seul
    assert screen._encoding.state(ba) == "pending"
    box, button = screen._canvas._enc_box, screen._canvas._btn_run_encoding
    assert box.isVisibleTo(screen._canvas) and button.isVisibleTo(screen._canvas)      # la ligne d'état propose le bouton
    assert screen._canvas._preview_badge.isVisibleTo(screen._canvas)                   # et l'image préparée, pas le rendu GBA
    button.click()                                                                     # « Run encoding »
    assert _wait(qapp, lambda: ba.compression.palettes_max == 3 and _idle(screen))
    assert box.isVisibleTo(screen._canvas) and not screen._canvas._preview_badge.isVisibleTo(screen._canvas)


def test_run_encoding_applies_the_chosen_mode_even_when_the_current_mode_is_cached(qapp, tmp_path):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    current = screen._props._cur_mode_token()
    other = "bitmap" if current != "bitmap" else "tiled4"
    layout, depth = ("bitmap", 8) if other == "bitmap" else ("tiled", 4)
    screen._props._apply_axes(layout, depth)                      # le choix est en attente
    assert screen._props._staged is not None
    assert screen._props.settings()["token"] == other

    screen._on_run_encoding()                                     # « Run encoding » : le mode choisi doit survivre

    assert _wait(qapp, lambda: screen._props._cur_mode_token() == other and _idle(screen))
    assert screen._props._staged is None
    assert screen._canvas._enc_box.isVisibleTo(screen._canvas)


def test_a_failed_encoding_says_so_in_the_status_line_and_keeps_the_pending_choice(qapp, tmp_path, monkeypatch):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    before = screen._props._cur_mode_token()
    layout, depth = ("bitmap", 8) if before != "bitmap" else ("tiled", 4)
    screen._props._apply_axes(layout, depth)

    def boom(*_a, **_k):
        raise RuntimeError("boom")
    monkeypatch.setattr("core.bg_import.encode_by_mode", boom)

    screen._on_run_encoding()

    assert _wait(qapp, lambda: screen._encoding.state(ba) == "failed" and _idle(screen))
    canvas = screen._canvas
    assert canvas._enc_box.isVisibleTo(canvas) and "boom" in canvas._enc_label.text()   # l'échec se lit en ligne, sans fenêtre
    assert canvas._btn_run_encoding.isVisibleTo(canvas)                                 # et « Run encoding » se rejoue
    assert screen._props._staged == (layout, depth)                     # rien n'a abouti : le choix reste
    assert screen._props._cur_mode_token() == before


def test_the_toolbar_and_strips_follow_a_mode_change_applied_by_recompute(qapp, tmp_path):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    canvas = screen._canvas
    screen._props._apply_axes("bitmap", 8)
    screen._on_run_encoding()
    assert _wait(qapp, lambda: ba.mode == "bitmap" and _idle(screen))
    assert not canvas._paint_strip.isVisibleTo(canvas) and not canvas._toolbar._btns["brush"].isVisibleTo(canvas._toolbar)

    screen._props._apply_axes("tiled", 4)
    screen._on_run_encoding()
    assert _wait(qapp, lambda: ba.mode == "tiled" and _idle(screen))
    assert canvas._paint_strip.isVisibleTo(canvas) and canvas._toolbar._btns["brush"].isVisibleTo(canvas._toolbar)


def test_the_status_line_names_the_chosen_layout_and_follows_each_change_of_mode(qapp, tmp_path):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    screen._encoding._auto_seconds = 4.0
    screen._encoding._seconds[screen._encoding._id(ba)] = 9.0                         # cher : l'encodage attend le bouton
    canvas = screen._canvas

    screen._props._apply_axes("bitmap", 8)
    screen._on_encoding_wanted(screen._props.settings())
    assert "Bitmap 8bpp" in canvas._enc_label.text() and canvas._btn_run_encoding.isVisibleTo(canvas)

    screen._props._apply_axes("tiled", 8)                                              # le choix change : la ligne aussi
    screen._on_encoding_wanted(screen._props.settings())
    assert "Tiled 8bpp" in canvas._enc_label.text()

    screen._props._apply_axes(*screen._props._cur_axes())                              # revenu au mode courant : plus rien
    screen._on_encoding_wanted(None)
    assert screen._encoding.state(ba) == "up_to_date" and "Pending" not in canvas._enc_label.text()


def test_a_setting_already_seen_comes_back_from_the_cache_without_computing_again(qapp, tmp_path):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    runs = []
    real = screen._encoding._executor.run
    screen._encoding._executor.run = lambda *a, **k: (runs.append(1), real(*a, **k))
    for palettes in (3, 4):
        screen._props._sl_palettes.setValue(palettes)
        screen._on_encoding_wanted(screen._props.settings())
        assert _wait(qapp, lambda: ba.compression.palettes_max == palettes and _idle(screen))
    assert len(runs) == 2

    screen._props._sl_palettes.setValue(3)                                              # le premier réglage, déjà vu
    screen._on_encoding_wanted(screen._props.settings())

    assert ba.compression.palettes_max == 3 and len(runs) == 2                          # validé sur-le-champ, sans calcul


def test_only_one_encoding_computes_at_a_time_and_the_last_request_wins(qapp, tmp_path):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    committed = []
    screen._encoding.committed.connect(lambda _ba, job: committed.append(job.compression.palettes_max))
    for palettes in (2, 3, 4):
        screen._props._sl_palettes.setValue(palettes)
        screen._on_encoding_wanted(screen._props.settings())
    assert screen._encoding._running is not None                                        # un seul calcul à la fois

    assert _wait(qapp, lambda: ba.compression.palettes_max == 4 and _idle(screen))
    assert committed == [4]                                                             # ni le premier (périmé) ni celui du milieu


def test_nothing_pending_asks_for_nothing(qapp, tmp_path):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)

    screen._on_encoding_wanted(None)

    assert _idle(screen) and not screen._encoding._wanted
    assert not screen._canvas._preview_badge.isVisibleTo(screen._canvas)


def test_the_mirror_button_adds_a_bar_at_mid_image_and_the_background_is_recompressed_mirrored(qapp, tmp_path, preparation_tools):
    """Coché : une barre à mi-image, le fond recompressé en miroir ; décoché : le miroir disparaît ; « Restaurer
    l'image source » l'annule aussi."""
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    canvas = screen._canvas
    width, height = canvas._prepared_size()

    canvas._tb_mirror_x.click()
    assert _wait(qapp, lambda: ba.mirror_x is not None and _idle(screen))
    assert ba.mirror_x == width // 2 and ba.mirror_y is None
    assert canvas._view.mirror.isVisible() and canvas._tb_mirror_x.isChecked() and not canvas._tb_mirror_y.isChecked()

    canvas._view.mirror.begin(("x", "move"))                                         # tirer la barre, puis lâcher
    canvas._view.mirror.drag(16, 0, snap=True)
    canvas._view.mirror.end()
    canvas._view.mirror_released.emit(*canvas._view.mirror.axes(), *canvas._view.mirror.flips())
    assert _wait(qapp, lambda: ba.mirror_x == 16 and _idle(screen))

    canvas._view.mirror.begin(("x", "side"))                                         # tirer la flèche de l'autre côté
    canvas._view.mirror.drag(30, 0, snap=False)
    canvas._view.mirror.end()
    canvas._view.mirror_released.emit(*canvas._view.mirror.axes(), *canvas._view.mirror.flips())
    assert _wait(qapp, lambda: ba.mirror_flip_x and _idle(screen))

    canvas._tb_mirror_y.click()
    assert _wait(qapp, lambda: ba.mirror_y == height // 2 and _idle(screen))

    canvas._btn_prep_reset.click()
    assert _wait(qapp, lambda: ba.mirror_x is None and ba.mirror_y is None and _idle(screen))
    assert not ba.mirror_flip_x
    assert not canvas._view.mirror.isVisible() and not canvas._tb_mirror_x.isChecked()


def test_the_compression_findings_read_measures_so_a_background_says_what_it_would_after_compression(qapp):
    from ui.background_editor.background_editor_screen import BgPropertiesPanel
    from ui.common.theme import C
    lines = BgPropertiesPanel._compression_lines_from
    assert lines("tiled", 4, {"max_tile_colors": 8}, tiles=100, palettes=2) == []
    over = lines("tiled", 4, {}, tiles=600, palettes=2)
    assert len(over) == 1 and "600" in over[0][0] and over[0][1] == C.ACCENT_RED
    assert lines("tiled", 8, {}, tiles=300, palettes=1)[0][0] and not lines("tiled", 8, {}, tiles=256, palettes=1)


def test_a_bitmap_background_says_its_canvas_in_the_overlay(qapp, tmp_path):
    from PIL import Image
    from core.bg_import import encode_by_mode, prepare_source
    from core.resources.asset_reconciliation import apply_bg_encoding
    project, ba, _panel = _panel_with_project(tmp_path)
    png = project.background_images_dir / "big.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (240, 134), (30, 90, 200)).save(png)
    ba.asset = project.asset_rel(png)
    ba.choose_layout("bitmap")
    apply_bg_encoding(ba, encode_by_mode(prepare_source(png), "bitmap"))
    screen = _screen_in(tmp_path, tmp_path)[1]
    screen._project = project
    screen._props._ba = ba
    screen._canvas.load(project, ba)

    screen._props._emit_overlays()

    text = screen._canvas._info_ov.text() + screen._canvas._warn_ov.text()
    assert "240×160 px" in text                               # le canvas d'un bitmap, pas la taille du fond d'avant


# ── Le mode Canvas : le fichier posé dans le canvas ───────────────────────────

def _canvas_on_photo(tmp_path, qapp):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    canvas = screen._canvas
    canvas._src_size = canvas._read_source_size()         # 32×32
    canvas._refresh_prepare_ui()
    return project, ba, screen, canvas


def test_the_canvas_card_shows_the_canvas_and_the_image_posed_in_it(qapp, tmp_path):
    _project, _ba, screen, _canvas = _canvas_on_photo(tmp_path, qapp)

    spins = screen._props._canvas_spins
    assert not screen._props._canvas_card.isHidden()
    assert (spins["canvas_w"].value(), spins["canvas_h"].value()) == (32, 32)
    assert (spins["pos_x"].value(), spins["pos_y"].value(), spins["size_w"].value(), spins["size_h"].value()) == (0, 0, 32, 32)


def test_editing_the_canvas_size_in_the_inspector_opens_the_canvas_mode_and_the_central_view_follows(qapp, tmp_path):
    _project, _ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)

    screen._props._canvas_spins["canvas_w"].setValue(48)

    assert canvas._view.canvas_mode_active() and canvas._toolbar.current_tool == "select"
    assert canvas._view.canvas_place.canvas() == (48, 32)
    assert canvas._view.canvas_place.rect() == (0, 0, 32, 32)                 # l'image n'a pas bougé


def test_dragging_the_image_updates_the_inspector_fields_live(qapp, tmp_path):
    _project, _ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)
    canvas._toolbar.choose_select()
    place = canvas._view.canvas_place

    assert place.begin(10, 10)                                                 # le corps de l'image
    place.drag(18, 14, False, False)
    canvas._view.canvas_rect_live.emit(place.rect())
    place.end()

    spins = screen._props._canvas_spins
    assert (spins["pos_x"].value(), spins["pos_y"].value()) == (8, 4)


def test_leaving_the_canvas_mode_applies_the_placement_with_one_recompression(qapp, tmp_path):
    _project, ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)
    asked = []
    canvas.prepare_requested.connect(asked.append)
    screen._props._canvas_spins["canvas_w"].setValue(16)
    screen._props._canvas_spins["pos_x"].setValue(-8)
    assert asked == []                                                         # rien ne se compresse pendant qu'on règle

    canvas._toolbar.leave_select()

    assert len(asked) == 1 and asked[0]["canvas"] == (16, 32) and asked[0]["pos"] == (-8, 0)
    assert _wait(qapp, lambda: ba.canvas_size == (16, 32) and ba.image_pos == (-8, 0))
    assert (ba.tiles_w, ba.tiles_h) == (2, 4)                                  # le canvas fait 16×32, l'image déborde


def test_escape_leaves_the_canvas_mode_without_applying(qapp, tmp_path):
    _project, ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)
    asked = []
    canvas.prepare_requested.connect(asked.append)
    screen._props._canvas_spins["canvas_w"].setValue(16)

    canvas._view.canvas_finished.emit(False)

    assert not canvas._view.canvas_mode_active() and asked == [] and ba.canvas_size is None


def test_a_bitmap_has_a_fixed_canvas_the_card_cannot_change(qapp, tmp_path):
    _project, ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)
    ba.mode = "bitmap"
    screen._props.load(ba, screen._project)                                    # l'inspecteur dit le layout montré
    canvas._refresh_prepare_ui()

    props = screen._props
    assert props._canvas_size_host.isHidden() and not props._canvas_fixed.isHidden()    # pas des champs grisés : une ligne qui dit « fixe »
    assert "240" in props._canvas_fixed.text() and "160" in props._canvas_fixed.text()
    assert props._canvas_spins["size_w"].isEnabled()                           # l'image, elle, se règle


def test_choosing_tiled_makes_the_canvas_size_editable_before_the_layout_is_even_compressed(qapp, tmp_path):
    """Le canvas se règle pour le layout CHOISI : un bitmap qu'on vient de passer en tuilé (en attente) ouvre les champs."""
    _project, ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)
    ba.mode = "bitmap"
    screen._props.load(ba, screen._project)
    props = screen._props
    assert not props._canvas_fixed.isHidden()

    props._set_layout("tiled")                                                 # en attente : rien n'est compressé

    assert ba.mode == "bitmap"
    assert not props._canvas_size_host.isHidden() and props._canvas_fixed.isHidden()
    props._canvas_spins["canvas_w"].setValue(48)
    assert canvas._view.canvas_place.canvas() == (48, 32)                      # la vue suit, au lieu de forcer 240×160


def test_the_fit_buttons_place_the_image_in_the_canvas(qapp, tmp_path):
    _project, _ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)
    screen._props._canvas_spins["canvas_w"].setValue(64)

    screen._props.canvas_fit_requested.emit("fill")

    assert canvas._view.canvas_place.rect() == (0, -16, 64, 64)               # 32×32 couvre 64×32 : à 200 %, rogné en haut et en bas


def test_the_canvas_mode_paints_the_whole_file_and_dims_what_falls_outside_the_canvas(qapp, tmp_path):
    _project, _ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)
    view = canvas._view
    view.resize(400, 300)
    screen._props._canvas_spins["canvas_w"].setValue(16)                      # le canvas ne couvre que la moitié gauche
    view._zoom = 8.0
    view._apply_zoom()
    view.centerOn(16, 16)

    image = view.viewport().grab().toImage()

    def brightness(scene_x):
        p = view.mapFromScene(scene_x, 16)
        block = [image.pixelColor(p.x() + dx, p.y() + dy) for dx in range(-3, 4) for dy in range(-3, 4)]
        return sum(c.red() + c.green() + c.blue() for c in block) / len(block)

    assert brightness(24) < 0.7 * brightness(8)                              # hors du cadre : même image, grisée


def test_the_toolbar_stays_for_a_bitmap_with_the_select_tool_alone(qapp, tmp_path):
    _project, ba, _screen, canvas = _canvas_on_photo(tmp_path, qapp)
    ba.mode = "bitmap"
    canvas.load(canvas._project, ba)

    toolbar = canvas._toolbar
    assert not toolbar.isHidden()
    assert not toolbar._btns["select"].isHidden() and toolbar._btns["select"].isEnabled()
    assert all(toolbar._btns[t].isHidden() for t in ("brush", "fill", "rect", "eraser"))      # rien à peindre
    assert toolbar.current_tool == "" and not canvas._view.canvas_mode_active()               # aucun outil choisi d'office


def test_select_comes_first_in_the_toolbar_and_a_paintable_background_keeps_its_brush(qapp, tmp_path):
    _project, _ba, _screen, canvas = _canvas_on_photo(tmp_path, qapp)

    toolbar = canvas._toolbar
    assert list(toolbar._btns)[0] == "select"
    assert toolbar.current_tool == "brush" and not canvas._view.canvas_mode_active()
    toolbar.choose_select()
    assert canvas._view.canvas_mode_active()
    toolbar.choose_select()                                                # re-cliquer « select » ne le quitte pas…
    assert canvas._view.canvas_mode_active()
    toolbar._btns["select"].click()                                        # …mais son bouton, si
    assert toolbar.current_tool == "brush" and not canvas._view.canvas_mode_active()


def test_what_falls_outside_the_canvas_stays_visible_dimmed_outside_the_mode_too(qapp, tmp_path):
    """Le passe-partout : sans mode Canvas, le fichier déborde et on le voit, grisé, autour du canvas."""
    _project, ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)
    ba.canvas_size = (16, 32)                                              # un canvas plus étroit que l'image (32×32)
    canvas._refresh_prepare_ui()
    view = canvas._view
    view.resize(400, 300)
    view._zoom = 8.0
    view._apply_zoom()
    view.centerOn(16, 16)

    assert not view.canvas_mode_active() and view.canvas_place.isVisible() and not view.canvas_place.active
    image = view.viewport().grab().toImage()
    def brightness(scene_x):
        p = view.mapFromScene(scene_x, 16)
        block = [image.pixelColor(p.x() + dx, p.y() + dy) for dx in range(-3, 4) for dy in range(-3, 4)]
        return sum(c.red() + c.green() + c.blue() for c in block) / len(block)

    assert brightness(24) > 60                                             # l'image y est, pas un fond noir
    assert not view.canvas_place.hit(24, 16)                               # et le passe-partout ne se manipule pas


# ── La boîte de compression suit le layout CHOISI ; les ajustements se replient ───────────────────────────────

def test_the_compression_box_follows_the_chosen_depth_before_anything_is_compressed(qapp, tmp_path):
    _project, ba, screen = _screen_on_photo(tmp_path, qapp)
    props = screen._props
    props._refresh_compression_ui()
    assert ba.bpp == 4 and all(r.isVisibleTo(props) is not None for r in props._rows_4bpp)
    assert props._comp_title.text() == label_of("bgedit.comp_title")

    props._set_depth(8)                                                    # en attente : rien n'est compressé

    assert ba.bpp == 4
    assert props._comp_title.text() == label_of("bgedit.comp_title8")
    assert all(r.isHidden() for r in props._rows_4bpp) and not any(r.isHidden() for r in props._rows_8bpp)
    assert [props._cmb_method.itemData(i) for i in range(props._cmb_method.count())] == list(
        __import__("core.bg_import", fromlist=["QUANTIZERS_8BPP"]).QUANTIZERS_8BPP)

    props._set_depth(4)                                                    # le retour réaffiche les options du 4bpp

    assert props._comp_title.text() == label_of("bgedit.comp_title")
    assert not any(r.isHidden() for r in props._rows_4bpp) and all(r.isHidden() for r in props._rows_8bpp)


def test_a_pending_slider_survives_a_change_of_depth(qapp, tmp_path):
    _project, _ba, screen = _screen_on_photo(tmp_path, qapp)
    props = screen._props
    props._sl_palettes.setValue(5)

    props._set_depth(8)
    props._set_depth(4)

    assert props._sl_palettes.value() == 5                                 # un curseur déjà tiré reste où il est


def test_the_bitmap_choice_hides_the_tile_target_before_it_is_compressed(qapp, tmp_path):
    _project, _ba, screen = _screen_on_photo(tmp_path, qapp)
    props = screen._props

    props._set_layout("bitmap")

    assert props._sl_tiles._row.isHidden()                                 # un bitmap n'a pas de tuiles


def test_the_adjustments_card_folds_and_opens_by_itself_when_one_is_set(qapp, tmp_path, preparation_tools):
    from core.models.background import BackgroundAdjust
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    props = screen._props
    assert not props._adj_host.isVisibleTo(props) or props._adj_host.isHidden() is False
    props._adj_open = False
    props._refresh_tune_visibility()
    assert not props._adj_host.isVisibleTo(props) and not props._adj_card.is_expanded()

    props._adj_card.set_expanded(True)
    assert props._adj_host.isVisibleTo(props) and props._adj_card.is_expanded()

    ba.adjust = BackgroundAdjust(hue=20)
    other = _with_image()
    props.load(other, project)                                             # un autre fond, sans ajustement : replié
    assert not props._adj_host.isVisibleTo(props)
    props.load(ba, project)                                                # un fond déjà réglé : ouvert d'office
    assert props._adj_host.isVisibleTo(props)


def test_the_compression_settings_follow_the_order_the_encoder_resolves_them(qapp, tmp_path):
    """De haut en bas : un réglage ne refait que ce qui le suit. 4bpp : global, dithering, méthode, couleurs, palettes,
    tuiles ; 8bpp : méthode, couleurs, dithering, tuiles. « Reset » reste en dernier."""
    _project, _ba, screen = _screen_on_photo(tmp_path, qapp)
    props = screen._props
    lay = props._comp_host.layout()

    def order(*widgets):
        indexes = [lay.indexOf(w) for w in widgets]
        return indexes == sorted(indexes) and -1 not in indexes

    props._refresh_compression_ui()
    assert order(props._sl_global._row, props._dither_host, props._cmb_method, props._sl_colors._row,
                 props._sl_palettes._row, props._sl_tiles._row, props._btn_comp_reset)

    props._set_depth(8)
    assert order(props._cmb_method, props._sl_pal8._row, props._dither_host, props._sl_tiles._row, props._btn_comp_reset)

    props._set_depth(4)                                                    # le retour remet l'ordre du 4bpp
    assert order(props._sl_global._row, props._dither_host, props._cmb_method, props._sl_colors._row,
                 props._sl_palettes._row, props._sl_tiles._row, props._btn_comp_reset)
    assert props._chk_dither.parent() is props._dither_host                # le dithering vit dans la boîte


def test_choosing_bitmap_makes_the_canvas_card_and_the_window_follow_with_the_canvas_mode_open_or_not(qapp, tmp_path):
    from PIL import Image
    _project, ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)
    props = screen._props
    props._canvas_spins["canvas_w"].setValue(48)                          # un canvas tuilé réglé, mode Canvas ouvert
    assert canvas._view.canvas_mode_active() and canvas._view.canvas_place.canvas() == (48, 32)

    props._set_layout("bitmap")                                           # en attente : rien n'est compressé

    assert canvas._view.canvas_place.canvas() == (240, 160)               # la fenêtre suit
    assert "240" in props._canvas_fixed.text() and "160" in props._canvas_fixed.text()
    assert canvas._view.canvas_place.rect() == (0, 0, 32, 32)             # l'image n'a pas bougé

    props._set_layout("tiled")                                            # le retour rend le canvas réglé avant

    assert canvas._view.canvas_place.canvas() == (48, 32) and not props._canvas_size_host.isHidden()


def test_choosing_bitmap_outside_the_canvas_mode_moves_the_passe_partout_frame(qapp, tmp_path):
    _project, ba, screen, canvas = _canvas_on_photo(tmp_path, qapp)
    assert not canvas._view.canvas_mode_active()
    assert canvas._view.canvas_place.canvas() == (32, 32)

    screen._props._set_layout("bitmap")

    assert canvas._view.canvas_place.canvas() == (240, 160)               # le cadre du passe-partout suit
    assert "240" in screen._props._canvas_fixed.text()


def test_inpainting_only_targets_an_added_palette_and_stores_its_position(qapp):
    ba = _with_image()
    ba.source_palettes = [list(ba.palettes[0])]                       # une palette DÉRIVÉE du PNG, en banque 0
    ba.palettes = [list(ba.palettes[0])]
    ba.added_palettes = []
    bank = ba.add_palette_ref("Green", [0, 0x03E0] + [0] * 14)        # banque 1 = position 0
    ctrl = _controller(ba, "inpaint")

    ctrl.set_active_palette(0)                                         # la palette dérivée : refusée
    _stroke(ctrl, [(2, 2)])
    assert ba.tile_palette_overrides == {}

    ctrl.set_active_palette(bank)
    _stroke(ctrl, [(2, 2)])
    assert ba.tile_palette_overrides == {(2, 2): 0}                    # la POSITION, pas le numéro de banque
    assert unpack_se(ba.effective_tilemap()[2 * ba.tiles_w + 2])[1] == bank


def test_the_palette_strip_lists_added_palettes_only_in_both_modes(qapp):
    from ui.background_editor.bg_inpaint_canvas import BgInpaintCanvas
    ba = _with_image()
    ba.source_palettes = [list(ba.palettes[0])]
    ba.palettes = [list(ba.palettes[0])]
    ba.added_palettes = []
    ba.add_palette_ref("Green", [0, 0x03E0] + [0] * 14)
    canvas = BgInpaintCanvas()
    canvas.load(None, ba)

    for mode in ("inpaint", "paint"):
        canvas._toolbar.set_mode(mode)
        assert list(canvas._paint_strip._colors) == [1], mode          # la banque 0 est dérivée : pas une cible


def test_the_passe_partout_slider_sets_how_much_the_outside_is_dimmed(qapp):
    from ui.background_editor.bg_inpaint_canvas import BgInpaintCanvas
    canvas = BgInpaintCanvas()
    place = canvas._view.canvas_place

    canvas._sl_passe_partout.setValue(100)
    assert place._dim == 255
    canvas._sl_passe_partout.setValue(0)
    assert place._dim == 0
    assert canvas._bar.layout().indexOf(canvas._sl_passe_partout) < canvas._bar.layout().indexOf(canvas._bar._size_label)


def test_a_compression_from_the_screen_leaves_the_result_current_for_the_settings_it_used(qapp, tmp_path):
    from core.models.background import BackgroundCompression
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    assert not ba.encoded_for                                          # la fixture n'a rien encodé par l'écran

    screen._compress_async(ba, project.background_image_path(ba), "tiled4", ba.quantize_method, ba.dither,
                           compression=BackgroundCompression(palettes_max=2))

    assert _wait(qapp, lambda: screen._encoding._running is None and ba.encoded_for)
    assert ba.compression.palettes_max == 2 and ba.encoding_is_current()    # les réglages posés AVANT l'encodage
    ba.compression = BackgroundCompression(palettes_max=5)
    assert not ba.encoding_is_current()                                # un réglage de plus : périmé



def test_the_status_line_stays_visible_when_up_to_date_and_recompute_redoes_the_encoding(qapp, tmp_path):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    canvas = screen._canvas
    screen._on_selected(ba)
    assert canvas._enc_box.isVisibleTo(canvas) and canvas._btn_run_encoding.isEnabled()   # à jour : l'état se lit, le bouton est là

    runs = []
    import core.bg_import as bg_import
    real = bg_import.encode_by_mode
    bg_import.encode_by_mode = lambda *a, **k: (runs.append(1), real(*a, **k))[1]
    try:
        canvas._btn_run_encoding.click()
        assert _wait(qapp, lambda: runs and _idle(screen))
    finally:
        bg_import.encode_by_mode = real
    assert ba.encoding_is_current() and "last run" in canvas._enc_label.text()


def test_the_brush_size_lives_in_the_top_bar_and_drives_the_view(qapp, tmp_path):
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    canvas = screen._canvas
    assert not hasattr(canvas._toolbar, "size_changed")                 # plus dans le menu du pinceau
    assert canvas._brush_size_buttons[8].isChecked()
    canvas._brush_size_buttons[32].click()
    assert canvas._view._brush_size == 32 and canvas._brush_size_buttons[32].isChecked()
    assert not canvas._brush_size_buttons[8].isChecked()


def test_an_encoding_finishing_in_canvas_mode_leaves_the_source_on_screen_until_the_mode_ends(qapp, tmp_path, preparation_tools):
    """Le mode Canvas montre le FICHIER source : une fin d'encodage (ou un aperçu) ne doit pas remettre l'image encodée, la
    grille ou l'aperçu par-dessus ; ils reviennent, à jour, à la sortie du mode."""
    project, ba, screen = _screen_on_photo(tmp_path, qapp)
    canvas, view = screen._canvas, screen._canvas._view
    canvas._toolbar.choose_select()
    assert view.canvas_mode_active()

    screen._props._d8.click()
    screen._on_run_encoding()
    assert _wait(qapp, lambda: ba.bpp == 8 and _idle(screen))

    assert view.canvas_mode_active() and not view._pix_item.isVisible() and not view._adjust_item.isVisible()
    assert not view._grid.isVisible()
    canvas._toolbar.leave_select()
    qapp.processEvents()
    assert not view.canvas_mode_active() and view._pix_item.isVisible() and not view._adjust_item.isVisible()
