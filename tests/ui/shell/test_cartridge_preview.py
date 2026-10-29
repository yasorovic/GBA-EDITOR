import pytest
from PyQt6.QtCore import Qt

from core.history import get_history
from core.project import Project
from ui.common.labels import label
from ui.scene_manager.inspectors.project_settings_dialog import BuildPanel


@pytest.mark.parametrize('frozen', [False, True])
@pytest.mark.parametrize('category', ['Build', 'Visual'])
def test_project_settings_never_show_temporary_top_level_widgets(
        qapp, tmp_path, monkeypatch, frozen, category):
    from PyQt6.QtCore import QObject, QEvent
    from PyQt6.QtWidgets import QWidget
    from core import app_paths
    from ui.scene_manager.inspectors.project_settings_dialog import ProjectSettingsDialog

    monkeypatch.setattr(app_paths, 'IS_FROZEN', frozen)

    class WindowShows(QObject):
        def __init__(self):
            super().__init__()
            self.shown = []

        def eventFilter(self, watched, event):
            if (event.type() == QEvent.Type.Show and isinstance(watched, QWidget)
                    and watched.isWindow()):
                self.shown.append(watched.metaObject().className())
            return False

    observer = WindowShows()
    qapp.installEventFilter(observer)
    dialog = None
    try:
        dialog = ProjectSettingsDialog(Project(tmp_path), initial_category=category)
        assert observer.shown == []
        dialog.show()
        qapp.processEvents()
        assert observer.shown == ['ProjectSettingsDialog']
    finally:
        qapp.removeEventFilter(observer)
        if dialog is not None:
            dialog.close()


def test_rom_target_updates_documented_board_and_undo(qapp, tmp_path):
    history = get_history()
    history.clear()
    panel = BuildPanel(Project(tmp_path))
    preview = panel._cartridge_preview
    assert not preview._photo.pixmap.isNull()
    assert preview._rom.text() == label('cartpreview.rom', mib=4)
    assert preview._battery.text() == label('cartpreview.battery_removed')
    panel._combo_cart.setCurrentIndex(panel._combo_cart.findData(8))
    assert panel._project.settings.cartridge_mib == 8
    assert not preview._photo.pixmap.isNull()
    assert preview._rom.text() == label('cartpreview.rom', mib=8)
    assert preview._battery.text() == label('cartpreview.battery_mounted')
    history.undo()
    assert panel._project.settings.cartridge_mib == 4
    assert preview._rom.text() == label('cartpreview.rom', mib=4)
    assert preview._battery.text() == label('cartpreview.battery_removed')
    history.clear()
    panel.close()


def test_larger_targets_do_not_claim_an_exact_hardware_match(qapp, tmp_path):
    project = Project(tmp_path)
    panel = BuildPanel(project)
    preview = panel._cartridge_preview
    for mib in (16, 32):
        project.settings.cartridge_mib = mib
        panel._refresh_fields()
        assert preview._target.text() == label('cartpreview.target', mib=mib)
        assert preview._rom.text() == label('cartpreview.rom', mib=8)
        assert preview._note.text() == label('cartpreview.example')
        assert not preview._photo.pixmap.isNull()
    panel.close()


def test_preview_profiles_never_change_settings_history_or_emitted_save_driver(qapp, tmp_path):
    from dataclasses import asdict
    from core.models.settings import GlobalVar
    from codegen.runtime_codegen.gen_save import save_lines
    from ui.common.cartridge_preview import save_preview_profiles

    project = Project(tmp_path)
    project.globals = [GlobalVar(name="score", id="123456abcdef", persist=True)]
    before = asdict(project.settings)
    emitted = save_lines(project)
    assert any("SRAM_V113" in line for line in emitted)
    history = get_history()
    history.clear()
    panel = BuildPanel(project)
    assert panel._combo_save_preview.count() == 6
    for profile in save_preview_profiles():
        panel._combo_save_preview.setCurrentIndex(panel._combo_save_preview.findData(profile.key))
        for capacity in profile.capacities:
            panel._combo_save_capacity.setCurrentIndex(panel._combo_save_capacity.findData(capacity))
            preview = panel._cartridge_preview
            assert preview.profile_id == profile.key
            assert preview.capacity == capacity
            assert not preview._photo.isHidden()
            assert preview._diagram.isHidden()
            assert not preview._photo.pixmap.isNull()
            if profile.key != "sram":
                assert label('cartpreview.photo_preview_only') in preview._note.text()
            for side in (0, 1):
                preview._side.setCurrentIndex(side)
                assert not preview._photo.pixmap.isNull()
                assert bool(preview._photo.points) == (side == 0)
            assert asdict(project.settings) == before
            assert save_lines(project) == emitted
            assert not history.can_undo
    panel.close()


def test_rom_refresh_and_undo_preserve_experimental_preview(qapp, tmp_path):
    history = get_history()
    history.clear()
    panel = BuildPanel(Project(tmp_path))
    panel._combo_save_preview.setCurrentIndex(panel._combo_save_preview.findData("flash"))
    panel._combo_save_capacity.setCurrentIndex(panel._combo_save_capacity.findData(131072))
    panel._combo_cart.setCurrentIndex(panel._combo_cart.findData(32))
    preview = panel._cartridge_preview
    preview._side.setCurrentIndex(1)
    assert preview._target.text() == label('cartpreview.preview_target', mib=32,
                                           profile=label('cartpreview.profile_flash'))
    history.undo()
    assert preview._target.text() == label('cartpreview.preview_target', mib=4,
                                           profile=label('cartpreview.profile_flash'))
    assert preview._side.currentData() == "back"
    assert preview.profile_id == "flash"
    assert preview.capacity == 131072
    assert panel._combo_save_capacity.currentData() == 131072
    history.clear()
    panel.close()


def test_the_selector_lists_every_save_type_and_greys_out_the_ones_the_engine_cannot_write(qapp, tmp_path):
    from ui.common.cartridge_preview import save_preview_profiles

    profiles = save_preview_profiles()
    assert {p.key for p in profiles if p.functional} == {"sram"}
    panel = BuildPanel(Project(tmp_path))
    combo = panel._combo_save_preview
    assert combo.count() == len(profiles)
    for row, profile in enumerate(profiles):
        assert combo.model().item(row).isEnabled() == profile.functional
        assert bool(combo.itemData(row, Qt.ItemDataRole.ToolTipRole)) == (not profile.functional)
    assert combo.currentData() == "sram"
    assert not combo.parentWidget().isHidden()
    panel.close()


def test_photo_catalog_contains_only_traceable_licensed_assets(qapp):
    import hashlib
    from ui.common.cartridge_preview import _CATALOG, _IMAGES

    assert len(_CATALOG) == 9
    for specimen in _CATALOG.values():
        assert set(specimen['photos']) == {'front', 'back'}
        for photo in specimen['photos'].values():
            path = _IMAGES / photo['file']
            assert path.is_file()
            assert hashlib.sha1(path.read_bytes()).hexdigest() == photo['sha1']
            assert photo['license_documented']
            assert photo['license'] == 'CC BY-SA 4.0'
            assert photo['source_page'].startswith('https://gbhwdb.gekkio.fi/cartridges/')


def test_a_profile_without_a_matching_bare_scan_stays_on_the_assembled_photo(qapp, tmp_path):
    panel = BuildPanel(Project(tmp_path))
    preview = panel._cartridge_preview
    # No matching bare scan for E06-10: do not silently show another revision.
    preview.set_profile('sram')
    preview.set_target(8)
    assert preview._view_mode.currentData() == 'assembled'
    assert not preview._view_mode.model().item(1).isEnabled()
    assert 'AGB-E06-10' in preview._reference.text()
    assert not preview._rom.isHidden()
    panel.close()


def test_capacity_variants_select_different_real_photos(qapp, tmp_path):
    panel = BuildPanel(Project(tmp_path))
    preview = panel._cartridge_preview
    for profile, capacities in [('eeprom', (512, 8192)), ('flash', (65536, 131072))]:
        preview.set_profile(profile, capacities[0])
        first = preview._photo.pixmap.toImage()
        preview.set_profile(profile, capacities[1])
        assert first != preview._photo.pixmap.toImage()
    panel.close()


def test_missing_assembled_photo_falls_back_to_identified_diagram(qapp, tmp_path, monkeypatch):
    from ui.common.cartridge_preview import _CATALOG

    panel = BuildPanel(Project(tmp_path))
    preview = panel._cartridge_preview
    monkeypatch.setitem(_CATALOG['fram']['photos']['front'], 'file', 'missing.jpg')
    preview.set_profile('fram')
    assert preview._photo.isHidden()
    assert not preview._diagram.isHidden()
    assert preview._reference.text() == label('cartpreview.schematic')
    assert preview._note.text() == label('cartpreview.unavailable')
    panel.close()


def test_numbered_markers_have_distinct_complementary_help_at_every_photo_size(qapp, tmp_path):
    from PyQt6.QtCore import QPoint
    from ui.common.cartridge_preview import save_preview_profiles
    from ui.common.tooltip_controller import resolve_tooltip

    panel = BuildPanel(Project(tmp_path))
    preview = panel._cartridge_preview
    for profile in save_preview_profiles():
        for capacity in profile.capacities:
            preview.set_profile(profile.key, capacity)
            photo = preview._photo
            assert photo.toolTip() == ''
            for width, height in ((320, 200), (500, 280), (260, 360)):
                photo.resize(width, height)
                contents = []
                for number, x, y in photo.points:
                    position = photo._marker_rect(x, y).center().toPoint()
                    content = resolve_tooltip(photo, position)
                    assert content.rect.contains(position)
                    assert content.text
                    assert f'{number} · ' in content.text
                    assert content.text not in contents
                    contents.append(content.text)
                assert resolve_tooltip(photo, QPoint(1, 1)).text == ''
            if profile.key == 'eeprom':
                assert label('cartpreview.help_eeprom') in photo.marker_tooltips[2]
            if profile.key == 'flash_rtc':
                assert label('cartpreview.help_battery_rtc') in photo.marker_tooltips[3]
                assert label('cartpreview.help_rtc') in photo.marker_tooltips[4]
            if profile.key == 'sram':
                assert label('cartpreview.help_battery_save') in photo.marker_tooltips[3]
    panel.close()


def test_reverse_and_bare_photos_do_not_reuse_front_marker_help(qapp, tmp_path, monkeypatch):
    from ui.common import cartridge_preview
    from ui.common.tooltip_controller import resolve_tooltip

    # Les scans « nus » vivent dans internal/ (hors git) : sans ce dossier, la vue « bare » n'est
    # pas proposée et le test ne vérifierait rien. Un dossier quelconque suffit à l'activer.
    monkeypatch.setattr(cartridge_preview, '_BARE_SCANS', tmp_path)
    panel = BuildPanel(Project(tmp_path))
    preview = panel._cartridge_preview
    preview.set_profile('sram')
    photo = preview._photo
    _, x, y = photo.points[0]
    position = photo._marker_rect(x, y).center().toPoint()
    panel.setToolTip('Parent help must not leak onto an unmarked photo')
    assert resolve_tooltip(photo, position).text
    preview._side.setCurrentIndex(1)
    assert resolve_tooltip(photo, position).text == ''
    preview._side.setCurrentIndex(0)
    preview._view_mode.setCurrentIndex(1)
    assert resolve_tooltip(photo, position).text == ''
    panel.close()

