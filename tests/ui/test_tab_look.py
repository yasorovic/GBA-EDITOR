"""Un seul look d'onglets : la feuille globale le porte, et les écrans qui avaient leurs
propres boutons (arbre de scène, langues) gardent leur comportement sur une vraie QTabBar."""
from types import SimpleNamespace as NS

from PyQt6.QtWidgets import QTabBar

from ui.common.theme import GLOBAL_QSS, QSS
from ui.scene_manager.scene_tree_panel import SceneTreePanel
from ui.text_editor.text_workbench import _LangTabs


def test_the_global_stylesheet_carries_the_tab_look():
    assert QSS.tab and QSS.tab in GLOBAL_QSS


def test_scene_tree_contexts_are_tabs_and_a_refresh_is_not_a_click(qapp):
    panel = SceneTreePanel()
    bar = panel._context_tabs
    assert isinstance(bar, QTabBar) and bar.count() == 2

    bar.setCurrentIndex(1)                              # un clic de l'auteur
    assert panel._context == "priority"

    panel._context = "content"
    panel._update_context_tabs()                        # un rafraîchissement : montre, ne décide pas
    assert bar.currentIndex() == 0 and panel._context == "content"


def _project(codes: list[str], gaps: dict[str, list] | None = None):
    langs = [NS(code=code, name=code.upper()) for code in codes]
    return NS(settings=NS(all_languages=lambda: langs, source_lang=langs[0]),
              translation_gaps=lambda code: (gaps or {}).get(code, []))


def test_language_tabs_hide_with_one_language_and_report_only_real_picks(qapp):
    tabs = _LangTabs()
    picked: list[str] = []
    tabs.picked.connect(picked.append)

    assert tabs.populate(_project(["en"]), "") == "" and tabs.isHidden()      # rien à choisir : caché
    assert tabs.populate(_project(["en", "fr"], {"fr": [1, 2]}), "fr") == "fr"
    assert not tabs.isHidden()
    assert picked == []                                  # peupler n'est pas un clic
    assert tabs._bar.tabText(1) == "FR (2)"              # le compte de trous suit la traduction

    tabs._bar.setCurrentIndex(0)                         # l'auteur choisit la source
    assert picked == ["en"]
    tabs._bar.setCurrentIndex(0)
    assert picked == ["en"]                              # rien de neuf : pas de second signal

    assert tabs.populate(_project(["en", "fr"]), "de") == "en"     # code disparu : on retombe sur la source


