"""Les diagnostics des générateurs de texte, d'interface et d'effets sonores qu'aucun test ne déclenchait (la liste d'exemptions
de la couverture : cf. `tools/diagnostic_coverage_exemptions.json`). Chaque test construit la situation fautive et lit ce que
le générateur en dit."""
from __future__ import annotations

import wave
from types import SimpleNamespace

import pytest

from core.models.audio import Sfx
from core.models.sprite import SpriteAsset
from core.models.ui_region import (
    ANCHOR_ACTOR, InterfaceNode, UIImage, UILayout, UIList, UIText)
from core.project import Project


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


class Journal:
    """Ce que le générateur a émis : `emit` se passe en argument comme au vrai build."""

    def __init__(self):
        self.diagnostics = []

    def __call__(self, event, *args):
        if event == "diagnostic":
            self.diagnostics.append(args[0])

    def says(self, level: str, fragment: str) -> bool:
        return any(d.level == level and fragment in d.message for d in self.diagnostics)


def _layout_in_scene(project, *elements, **layout_fields) -> UILayout:
    """Un layout `hud` posé sur la scène active par un nœud Interface."""
    layout = UILayout(name="hud", **layout_fields)
    layout.elements.extend(elements)
    project.ui_layouts.append(layout)
    node_fields = {k: v for k, v in layout_fields.items() if k in ("anchor", "anchor_actor")}
    project.active_scene.ui_layouts.append(InterfaceNode(layout_name="hud", **node_fields))
    return layout


# ── Textes ────────────────────────────────────────────────────────────────


def test_une_police_qui_ne_s_encode_pas_est_une_erreur_et_n_arrete_pas_les_autres(project, monkeypatch):
    from codegen import font_emit
    from codegen.runtime_codegen import gen_text

    def refuse(*_args, **_kwargs):
        raise ValueError("no glyph sheet")

    pixel = SimpleNamespace(name="Pixel", asset="")
    monkeypatch.setattr(gen_text, "project_fonts", lambda _p: [pixel])
    monkeypatch.setattr(gen_text, "encodable_project_fonts", lambda _p: [pixel])
    monkeypatch.setattr(font_emit, "encode_font", refuse)
    journal = Journal()
    gen_text.fonts_and_texts_lines(project, journal)
    assert journal.says("error", "Pixel: encoding failed (no glyph sheet)")


def test_un_texte_dont_la_cle_a_disparu_n_ecrit_rien_et_le_dit(project):
    from codegen.runtime_codegen import gen_text
    _layout_in_scene(project, UIText(name="title", text_key="gone.key"))
    journal = Journal()
    gen_text.gen_ui_texts(project, project.active_scene, 1, journal)
    assert journal.says("warning", "text 'title': key 'gone.key' not found in the table")


def test_un_texte_sur_un_fond_sans_calque_de_texte_ne_s_affichera_pas(project):
    from codegen.runtime_codegen import gen_text
    text = project.new_text(content="Hi")
    _layout_in_scene(project, UIText(name="title", text_key=text.key))
    journal = Journal()
    gen_text.gen_ui_texts(project, project.active_scene, -1, journal)       # -1 : aucun BG ne porte le texte
    assert journal.says("warning", "text 'title': scene 'Scene_01' has no text layer (Text BG)")


def test_une_zone_de_texte_ancree_sur_un_acteur_introuvable_est_placee_a_l_origine(project):
    from codegen.font_emit import emit_ui_regions_c
    layout = UILayout(name="hud", anchor=ANCHOR_ACTOR, anchor_actor="Ghost")
    journal = Journal()
    emit_ui_regions_c([(layout, UIText(name="title"))], [], journal, actor_index={})
    assert journal.says("warning", "text 'title': anchored on actor 'Ghost', which was not found")


# ── Images et listes ──────────────────────────────────────────────────────


def test_une_image_ancree_sur_un_acteur_introuvable_est_placee_a_l_origine(project, monkeypatch):
    from codegen.runtime_codegen.gen_ui import emit_ui_images_c
    hero = SpriteAsset(name="Hero", asset="assets/sprites/hero.png", frame_w=8, frame_h=8)
    monkeypatch.setattr(project, "get_buildable_sprite", lambda _name: hero)      # le sprite est « compilable »
    project.ui_layouts.append(UILayout(name="hud", anchor=ANCHOR_ACTOR, anchor_actor="Ghost",
                                       elements=[UIImage(name="icon", sprite_name="Hero")]))
    journal = Journal()
    emit_ui_images_c(project, {}, {}, actor_index={}, emit=journal)
    assert journal.says("warning", "image 'icon': anchored on actor 'Ghost', which was not found in the scene")


def test_une_liste_sans_zone_de_texte_enfant_n_a_aucune_rangee_et_le_dit(project):
    from codegen.runtime_codegen.gen_ui import emit_ui_lists_c
    project.ui_layouts.append(UILayout(name="hud", elements=[UIList(name="menu")]))
    journal = Journal()
    emit_ui_lists_c(project, journal)
    assert journal.says("warning", "list 'menu': no child text zone, hence no row to display")


# ── Effets sonores ────────────────────────────────────────────────────────


def _wav(path, rate: int = 16000, frames: int = 160):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(rate)
        out.writeframes(b"\x80" * frames)
    return path


def test_un_effet_que_le_reechantillonnage_refuse_part_tel_quel_et_le_dit(project, monkeypatch):
    from codegen import sfx_encode

    def refuse(*_args, **_kwargs):
        raise ValueError("cannot resample")

    monkeypatch.setattr(sfx_encode, "write_sfx", refuse)
    boom = _wav(project.root / "assets" / "sfx" / "boom.wav", rate=16000)
    journal = Journal()
    encoded = sfx_encode.encode_sfx_for_build(project, [(Sfx(name="Boom", sample_rate=8000), boom)], journal)
    assert encoded == {}
    assert journal.says("warning", '"Boom" not encoded: cannot resample')
