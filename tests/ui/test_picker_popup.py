"""Le popup de choix (une liste construite une fois, filtrée sans reconstruction, qui rend la valeur telle quelle)
et le slot qui tient la valeur (montrée avant d'être notifiée, gardée dans la liste même absente)."""
from ui.common.widgets import PickerEntry, PickerPopup


def _popup(entries, **kwargs):
    return PickerPopup(entries, "#ffffff", **kwargs)


def test_filter_hides_rows_without_rebuilding_them(qapp):
    popup = _popup([PickerEntry("Hero", "hero"), PickerEntry("Enemy", "enemy"), PickerEntry("Hermit", "hermit")])
    rows = [popup._list.item(i) for i in range(popup._list.count())]
    popup._search.setText("he")
    assert [e.value for e in popup.visible_entries()] == ["hero", "hermit"]
    assert [popup._list.item(i) for i in range(popup._list.count())] == rows    # les mêmes lignes, masquées
    popup._search.setText("zzz")
    assert popup.visible_entries() == [] and not popup._no_results.isHidden()
    popup._search.setText("")
    assert len(popup.visible_entries()) == 3 and popup._no_results.isHidden()


def test_picked_carries_the_value_untouched(qapp):
    picked = []
    popup = _popup([PickerEntry("Auto", -1), PickerEntry("3", 3)])
    popup.picked.connect(picked.append)
    popup._list.itemClicked.emit(popup._list.item(1))
    popup._list.itemActivated.emit(popup._list.item(0))   # le popup est déjà fermé : un seul choix
    assert picked == [3]


def test_a_missing_entry_stays_listed_and_is_marked(qapp):
    from ui.common.theme import C
    popup = _popup([PickerEntry("Ok", "ok"), PickerEntry("Gone (missing)", "gone", missing=True)])
    item = popup._list.item(1)
    assert item.foreground().color().name().lower() == C.ACCENT_YLW.lower()
    assert not item.icon().isNull()


def test_no_creation_button_unless_asked(qapp):
    assert _popup([])._btn_new is None
    assert _popup([], new_label="New")._btn_new is not None


def test_create_named_only_for_a_free_name(qapp):
    created = []
    popup = _popup([PickerEntry("solid", "solid")], new_label="Create {name}", create_named=True)
    popup.created.connect(created.append)
    popup._search.setText("SOLID")
    assert not popup._btn_new.isEnabled()
    popup._search.setText("ladder")
    popup._on_enter()
    assert created == ["ladder"]


# ── PickerSlot : le bouton qui tient la valeur ────────────────────

def _slot(values, picked, **kwargs):
    from ui.common.widgets import PickerSlot

    def describe(value):
        if not value:
            return None
        return PickerEntry(value.title(), value, missing=value not in values)
    return PickerSlot("Add", "#ffffff", lambda: [PickerEntry(v.title(), v) for v in values], describe,
                      picked.append, **kwargs)


def test_slot_shows_the_value_before_notifying_and_ignores_the_same_choice(qapp):
    seen = []
    slot = None

    def picked(value):
        seen.append((value, slot._lbl.text()))
    from ui.common.widgets import PickerSlot
    slot = PickerSlot("Add", "#ffffff", lambda: [], lambda v: PickerEntry(v.title(), v) if v else None, picked)
    assert not slot._btn_add.isHidden() and slot._active_w.isHidden()
    slot.pick("hero")
    slot.pick("hero")
    assert seen == [("hero", "Hero")] and slot.value() == "hero"


def test_slot_lists_a_posed_value_absent_from_the_entries_as_missing(qapp):
    slot = _slot(["hero"], [])
    slot.set_value("ghost")
    entries = slot.popup_entries()
    assert [e.value for e in entries] == ["hero", "ghost"] and entries[-1].missing
    slot.set_value("hero")
    assert [e.value for e in slot.popup_entries()] == ["hero"]


def test_slot_clear_restores_the_cleared_value_then_notifies(qapp):
    cleared = []
    slot = _slot(["hero"], [], on_cleared=lambda: cleared.append(True))
    slot.set_value("hero")
    assert not slot._btn_clear.isHidden()
    slot._click_clear()
    assert cleared == [True] and slot.value() is None and not slot._btn_add.isHidden()
    assert _slot(["hero"], [])._btn_clear.isHidden()      # sans on_cleared, pas de ×


def test_slot_create_named_posts_the_name_then_calls_on_new(qapp):
    created = []
    slot = _slot(["solid"], [], new_label="Create {name}", create_named=True,
                 on_new=lambda name: created.append((name, slot.value())))
    slot._created("ladder")
    assert created == [("ladder", "ladder")]


def test_font_slot_lists_the_missing_font_of_the_current_value_not_the_first_one(qapp):
    from types import SimpleNamespace
    from ui.common.pickers import font_picker_slot
    fonts = [SimpleNamespace(name="Main")]
    slot = font_picker_slot(fonts, {"Main"}, "Gone", "#ffffff", on_picked=lambda _n: None)
    assert [e.value for e in slot.popup_entries()] == ["", "Main", "Gone"]
    slot.pick("Main")
    assert [e.value for e in slot.popup_entries()] == ["", "Main"]   # « Gone » n'est plus la valeur posée
