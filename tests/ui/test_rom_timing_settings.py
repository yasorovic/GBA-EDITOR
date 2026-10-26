"""Le réglage des temps d'accès de la ROM dans les paramètres du projet : deux préréglages et un mode avancé."""
from core.project import Project
from ui.scene_manager.inspectors.project_settings_dialog import BuildPanel


def _triplet(project):
    s = project.settings
    return s.rom_wait_first, s.rom_wait_second, s.rom_prefetch


def test_les_prereglages_posent_les_trois_champs_et_cachent_l_avance(qapp, tmp_path):
    project = Project(tmp_path)
    panel = BuildPanel(project)
    assert panel._combo_timing.currentData() == "fast"
    assert panel._timing_advanced.isHidden()
    panel._combo_timing.setCurrentIndex(panel._combo_timing.findData("compatible"))
    panel._pick_timing(0)
    assert _triplet(project) == (4, 2, False)
    assert panel._combo_timing.currentData() == "compatible"
    panel.close()


def test_le_mode_avance_montre_les_champs_et_filtre_les_accès_suivants(qapp, tmp_path):
    project = Project(tmp_path)
    panel = BuildPanel(project)
    panel._combo_timing.setCurrentIndex(panel._combo_timing.findData("custom"))
    panel._pick_timing(0)
    assert not panel._timing_advanced.isHidden()
    panel._combo_wait_first.setCurrentIndex(panel._combo_wait_first.findData(2))
    panel._pick_wait_first(0)
    assert _triplet(project) == (2, 1, True)
    assert [panel._combo_wait_second.itemData(i) for i in range(panel._combo_wait_second.count())] == [1]
    panel.close()


def test_un_reglage_hors_prereglage_ouvre_le_mode_avance(qapp, tmp_path):
    project = Project(tmp_path)
    project.settings.rom_prefetch = False
    panel = BuildPanel(project)
    assert panel._combo_timing.currentData() == "custom"
    assert not panel._timing_advanced.isHidden()
    panel.close()
