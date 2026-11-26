"""Les sections de la sidebar Script gardent leur état après une recherche."""
from ui.common.theme import C
from ui.script_editor.sidebar_widgets import _Section, _BTN_API, _EntryButton


def test_le_filtre_restitue_les_sections_repliees(qapp):
    section = _Section("API", C.ACCENT, expanded=False)
    sub = section.sub_section("Actor")
    sub._do_toggle()                 # sous-section initialement repliée
    sub.add_widget(_EntryButton("  actor:get", _BTN_API, ""))

    section.apply_filter("actor")
    assert section._expanded
    assert sub._expanded

    section.apply_filter("")
    assert not section._expanded
    assert not sub._expanded
