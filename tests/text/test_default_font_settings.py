"""Le choix de Default Font : persistance et pont depuis l'ancien repli."""
from __future__ import annotations

import json


def test_un_manifest_ancien_migre_le_repli_en_default_font(tmp_path):
    from core.project import Project

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True)
    p.project_file.write_text(json.dumps({
        "name": "jeu", "fallback_font": "dialog",
        "languages": [{"code": "ja", "name": "Japanese",
                       "fonts": {"dialog": "dialog_ja", "title": "title_ja"}}],
    }), encoding="utf-8")

    p.load_settings()

    assert p.settings.default_font == "dialog"
    # Seul le remplacement de l'ancien défaut est conservé : `title` doit
    # désormais porter ses sources de couverture dans sa FontAsset.
    assert p.settings.languages[0].default_font == "dialog_ja"

    p.save_settings()
    saved = json.loads(p.project_file.read_text(encoding="utf-8"))
    assert saved["default_font"] == "dialog"
    assert "fallback_font" not in saved
    assert saved["languages"][0]["default_font"] == "dialog_ja"
    assert "fonts" not in saved["languages"][0]


def test_une_langue_ne_remplace_pas_une_police_explicitement_choisie():
    from types import SimpleNamespace
    from codegen.font_emit import emit_lang_fonts_c

    ja = SimpleNamespace(code="ja", default_font="dialog_ja")
    src = "\n".join(emit_lang_fonts_c(
        ["dialog", "dialog_ja", "title"], [ja], "dialog"))

    assert "g_lang_font_0[3] = {1,1,2}" in src
