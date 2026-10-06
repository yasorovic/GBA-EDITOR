"""Un TextBox référence une police logique et une face native."""

from core.models.ui_region import UIText


def test_textbox_persists_font_asset_and_native_weight():
    text = UIText(name="title", font_name="Comic Neue", font_weight=300, font_italic=True)

    restored = UIText.from_dict(text.to_dict())

    assert restored.font_name == "Comic Neue"
    assert restored.font_weight == 300
    assert restored.font_italic is True


def test_old_textbox_without_weight_keeps_regular_as_default():
    restored = UIText.from_dict({"kind": "text", "name": "title", "font_name": "ascii"})

    assert restored.font_name == "ascii"
    assert restored.font_weight == 400
    assert restored.font_italic is False
