from core.project import Project
from core.models.settings import Language
from ui.scene_manager.inspectors.project_settings_dialog import LanguagesPanel


def test_mode_and_run_language_follow_settings_and_refresh(qapp, tmp_path):
    project = Project(tmp_path)
    project.settings.source_lang = Language(code="en")
    project.settings.languages = [Language(code="ja")]
    panel = LanguagesPanel(project)
    assert not panel._combo_build_language.isEnabled()
    panel._combo_mode.setCurrentIndex(panel._combo_mode.findData("monolingual"))
    assert project.settings.language_mode == "monolingual"
    assert panel._combo_build_language.isEnabled()
    panel._combo_build_language.setCurrentIndex(panel._combo_build_language.findData("ja"))
    assert project.settings.build_language == "ja"
    project.settings.languages = []
    panel._refresh_build_settings()
    assert panel._combo_build_language.currentData() == "en"
    panel.close()


def test_game_menu_build_actions_use_their_language_and_do_not_accumulate(qapp, tmp_path):
    from PyQt6.QtWidgets import QMainWindow, QMenu
    from PyQt6.QtGui import QAction
    from editor.window import MainWindow

    window = QMainWindow()
    window.project = Project(tmp_path)
    window.project.settings.source_lang = Language(code="en")
    window.project.settings.languages = [Language(code="ja")]
    window.project.settings.language_mode = "monolingual"
    window.project.settings.build_language = "ja"
    from core.models.scene import Scene
    window.project.scenes.append(Scene(name="Main"))
    window._worker = None
    window._language_build_actions = []
    calls = []
    window._run_build = calls.append
    menu = QMenu(window)
    run = QAction("Run", window)
    menu.addAction(run)
    menu.addSeparator()
    for _ in range(2):
        MainWindow._fill_language_build_menu(window, menu, run)
        assert [action.text() for action in window._language_build_actions] == ["Build_en", "Build_ja"]
        assert len(menu.actions()) == 4
    window._language_build_actions[0].trigger()
    window._language_build_actions[1].trigger()
    assert calls == ["en", "ja"]
    assert "ja" in run.text()
    assert window.project.settings.build_language == "ja"
    window.project.settings.language_mode = "multilingual"
    MainWindow._fill_language_build_menu(window, menu, run)
    assert len(menu.actions()) == 2
    window.close()
