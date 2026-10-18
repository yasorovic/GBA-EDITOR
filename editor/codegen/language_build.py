"""Build-only language view; authoring data and translation files stay intact."""
from copy import copy, deepcopy


def language_build_project(project, language_code=None):
    if getattr(getattr(project, "settings", None), "language_mode", "multilingual") != "monolingual":
        return project
    settings = deepcopy(project.settings)
    if language_code is not None:
        settings.build_language = language_code
    selected = settings.selected_build_language()
    # Keep script constants for unavailable languages compilable. Index zero
    # is the bundled language; the runtime ignores all other indices.
    settings._script_languages = ([selected] if selected.code else []) + [
        lang for lang in settings.all_languages() if lang.code != selected.code]
    view = copy(project)
    view.settings = settings
    settings._build_languages = [selected] if selected.code else []
    settings.languages = ([selected] if selected.code != settings.source_lang.code else [])
    view.texts = []
    for text in project.texts:
        translated = copy(text)
        translated.content = project.text_content(text, selected.code)
        view.texts.append(translated)
    view.translations = {selected.code: dict(project.translations.get(selected.code, {}))}
    view.translation_problems = {
        code: problem for code, problem in project.translation_problems.items()
        if code == selected.code
    }
    view._font_build_cache = None
    return view
