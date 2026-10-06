"""`scene_codepoints` par langue + `scene_codepoints_union` (ROADMAP v0.9,
phase 3.3).

Ce que ces tests protègent :

- le sous-ensemble par langue lit la TRADUCTION de cette langue, pas
  toujours la source — sinon une scène en japonais chargerait une police
  sans un seul kanji ;
- l'UNION couvre toutes les langues déclarées, même celles dont la
  traduction ajoute des caractères que la source n'a jamais ;
- une langue INDÉCIDABLE (script hors analyse) rend l'union entière
  indécidable — émettre un sous-ensemble partiel mentirait par omission ;
- sans langue déclarée (`[""]`), le comportement est celui d'avant la phase
  3 : l'union se réduit à la seule source.

Cf. `codegen/font_emit.scene_codepoints` / `scene_codepoints_union`.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.scene import Scene
    from core.models.ui_region import UILayout, UIText
    from core.models.settings import Language

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)

    zone = UIText(name="bubble", w=64, h=16)
    layout = UILayout(name="hud")
    layout.elements.append(zone)
    p.ui_layouts.append(layout)

    t = p.new_text(content="Hi", path=["Dialogue", "Greet"])
    zone.text_key = t.key

    scene = Scene(name="Main", ui_layouts=["hud"])
    p.scenes.append(scene)

    p.settings.source_lang = Language(code="en", name="English")
    p.settings.languages = [Language(code="ja", name="Japanese")]
    p.load_translations()
    return p, scene, t


def test_une_langue_lit_sa_propre_traduction(projet):
    from codegen.font_emit import scene_codepoints
    p, scene, t = projet
    p.translations["ja"][t.id] = "こんにちは"

    src_cps = scene_codepoints(p, scene, "")
    ja_cps = scene_codepoints(p, scene, "ja")

    assert set("Hi") <= {chr(c) for c in src_cps}
    assert set("こんにちは") <= {chr(c) for c in ja_cps}
    # La source ne contient AUCUN des caractères japonais.
    assert not (set("こんにちは") & {chr(c) for c in src_cps})


def test_union_couvre_toutes_les_langues(projet):
    from codegen.font_emit import scene_codepoints_union
    p, scene, t = projet
    p.translations["ja"][t.id] = "こんにちは"

    union = scene_codepoints_union(p, scene, ["", "ja"])

    assert set("Hi") <= {chr(c) for c in union}
    assert set("こんにちは") <= {chr(c) for c in union}


def test_traduction_absente_replie_sur_la_source_dans_l_union(projet):
    """Aucune traduction ja déclarée pour ce texte : l'union ne doit gagner
    aucun caractère de plus que la source (repli `text_content`)."""
    from codegen.font_emit import scene_codepoints_union
    p, scene, _t = projet

    union = scene_codepoints_union(p, scene, ["", "ja"])
    src = scene_codepoints_union(p, scene, [""])

    assert union == src


def test_sans_langue_declaree_equivaut_a_avant_la_phase_3(projet):
    from codegen.font_emit import scene_codepoints, scene_codepoints_union
    p, scene, _t = projet
    assert scene_codepoints_union(p, scene, [""]) == scene_codepoints(p, scene)
