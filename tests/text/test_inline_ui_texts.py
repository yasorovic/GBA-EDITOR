"""Les textes locaux arrivent dans la ROM sans remplir l'écran Texts."""
import json

import pytest

from core.project import Project
from core.models.scene import Scene
from core.models.settings import Language
from core.models.ui_region import UILayout, UIText, UITextbox
from core.project_texts import ui_text_build_key
from codegen.font_build import project_codepoints
from codegen.font_emit import emit_texts_c, layout_texts, scene_codepoints
from codegen.runtime_codegen.gen_text import gen_ui_texts, region_is_composited


@pytest.fixture
def local_texts(tmp_path):
    project = Project(tmp_path / 'game')
    project.project_dir.mkdir(parents=True)
    layout = UILayout(name='HUD')
    layout.elements = [UIText(name='Title', preview_text='Salut é'),
                       UITextbox(name='Box', preview_text='Bonjour'),
                       UITextbox(name='Empty')]
    project.ui_layouts.append(layout)
    scene = Scene(name='Main', ui_layouts=[layout.name])
    project.scenes.append(scene)
    return project, layout, scene


def test_local_texts_have_distinct_stable_ids_without_saved_entries(local_texts):
    project, layout, _ = local_texts
    first, second, _ = layout.elements
    second.preview_text = first.preview_text
    before = project.build_texts()
    assert len(before) == 2
    assert len({t.id for t in before}) == 2
    first.preview_text = 'Retouché'
    assert [t.id for t in project.build_texts()] == [t.id for t in before]
    assert project.texts == []
    project.save_texts()
    assert json.loads(project.texts_file.read_text(encoding='utf-8'))['texts'] == []
    restored = UILayout.from_dict(layout.to_dict())
    assert ui_text_build_key(restored, restored.elements[0]) == before[0].key


def test_local_texts_are_emitted_and_drawn_at_scene_start(local_texts):
    project, _, scene = local_texts
    texts = project.build_texts()
    assert [t.content for t in layout_texts(project, scene)] == ['Salut é', 'Bonjour']
    calls = gen_ui_texts(project, scene, text_bg=0)
    assert len(calls) == 2
    assert 'text_draw_in(0, 0)' in calls[0]
    assert 'text_draw_in(1, 1)' in calls[1]
    source = '\n'.join(emit_texts_c(texts, [''], project.text_content))
    import re
    match = re.search(r'g_text_0_0\[.*?\]\s*=\s*\{([^}]*)\}', source)
    assert match is not None
    assert [int(value) for value in match[1].split(',')] == list(map(ord, 'Salut é'))
    assert ord('é') in scene_codepoints(project, scene)
    assert 'é' in project_codepoints(project)


def test_creating_shared_entry_replaces_local_content(local_texts):
    project, layout, scene = local_texts
    entry = project.new_text(content='Partagé')
    layout.elements[0].text_key = entry.key
    assert [t.content for t in project.build_texts()] == ['Partagé', 'Bonjour']
    assert len(project.texts) == 1
    assert 'text_draw_in(0, 0)' in gen_ui_texts(project, scene, text_bg=0)[0]


def test_local_text_stays_in_source_language_and_keeps_markup(local_texts):
    project, layout, scene = local_texts
    project.settings.source_lang = Language(code='en', name='English')
    project.settings.languages = [Language(code='fr', name='French')]
    el = layout.elements[0]
    el.preview_text = '[font=Other]é[/font]'
    text = project.build_texts()[0]
    assert project.text_content(text, 'fr') == text.content
    assert region_is_composited(project, layout, el, '')
    assert ord('é') in scene_codepoints(project, scene, 'fr')


def test_legacy_preview_key_resolves_without_creating_another_editor_entry(local_texts):
    project, layout, _ = local_texts
    entry = project.new_text(content='Legacy content')
    el = layout.elements[0]
    el.preview_text, el.preview_is_literal = entry.key, False
    assert project.inline_ui_texts()[0].content == entry.content
    el.preview_is_literal = True
    assert project.inline_ui_texts()[0].content == entry.key
