from codegen.language_build import language_build_project
from codegen.font_build import project_codepoints
from codegen.font_emit import emit_lang_fonts_c, emit_texts_c
from core.models.settings import Language
from core.models.text import Text
from core.project import Project


def project_with_languages(tmp_path):
    project = Project(tmp_path)
    project.settings.source_lang = Language(code="en", name="English")
    project.settings.languages = [Language(code="ja", default_font="Japanese"),
                                  Language(code="fr", default_font="French")]
    project.settings.default_font = "Latin"
    project.texts = [Text(id="greeting", key="greeting", content="Hello"),
                     Text(id="missing", key="missing", content="Fallback")]
    project.translations = {"ja": {"greeting": "日本語"},
                            "fr": {"greeting": "Bonjour"}}
    return project


def test_monolingual_emits_one_language_and_its_font_without_mutating_project(tmp_path):
    project = project_with_languages(tmp_path)
    project.settings.language_mode = "monolingual"
    project.settings.build_language = "ja"
    view = language_build_project(project)
    assert [lang.code for lang in view.settings.all_languages()] == ["ja"]
    assert [lang.code for lang in view.settings._script_languages] == ["ja", "en", "fr"]
    assert [t.content for t in view.texts] == ["日本語", "Fallback"]
    assert "H" not in project_codepoints(view)
    assert "日" in project_codepoints(view)
    lines = "\n".join(emit_texts_c(view.build_texts(), ["ja"], view.text_content, [], []))
    assert "g_texts[1]" in lines
    assert "g_texts_1" not in lines
    remap = "\n".join(emit_lang_fonts_c(
        ["Latin", "Japanese"], view.settings.all_languages(), "Latin"))
    assert "g_lang_font_0[2] = {1,1}" in remap
    assert "g_lang_font_1" not in remap
    assert project.texts[0].content == "Hello"
    assert len(project.settings.languages) == 2
    assert project.translations["fr"]["greeting"] == "Bonjour"


def test_source_override_and_missing_preset_fall_back_to_source(tmp_path):
    project = project_with_languages(tmp_path)
    project.settings.language_mode = "monolingual"
    project.settings.build_language = "ja"
    source = language_build_project(project, "en")
    assert source.texts[0].content == "Hello"
    assert source.settings.languages == []
    assert project.settings.build_language == "ja"
    project.settings.build_language = "removed"
    assert language_build_project(project).settings.all_languages()[0].code == "en"


def test_multilingual_preserves_all_languages(tmp_path):
    project = project_with_languages(tmp_path)
    assert language_build_project(project) is project
    assert [lang.code for lang in project.settings.all_languages()] == ["en", "ja", "fr"]


def test_only_the_selected_replacement_font_is_bundled(tmp_path, monkeypatch):
    from codegen.font_emit import project_fonts
    from core.models.font import Font
    from core.models.scene import Scene
    project = project_with_languages(tmp_path)
    project.settings.language_mode = "monolingual"
    project.settings.build_language = "ja"
    project.scenes.append(Scene(name="Main"))
    fonts = [Font(name=name) for name in ("Latin", "Japanese", "French")]
    monkeypatch.setattr("codegen.font_emit.encodable_project_fonts", lambda p: fonts)
    assert [font.name for font in project_fonts(language_build_project(project))] == ["Latin", "Japanese"]


def test_mode_and_preset_round_trip(tmp_path):
    project = project_with_languages(tmp_path)
    project.settings.language_mode = "monolingual"
    project.settings.build_language = "ja"
    project.save_settings()
    loaded = Project(tmp_path)
    loaded.load_settings()
    assert loaded.settings.language_mode == "monolingual"
    assert loaded.settings.build_language == "ja"
