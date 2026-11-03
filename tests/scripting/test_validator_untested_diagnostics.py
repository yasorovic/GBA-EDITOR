"""Des diagnostics du validateur qu'aucun test ne déclenchait (la liste d'exemptions de la couverture : cf.
`tools/diagnostic_coverage_exemptions.json`). Chaque test construit la situation fautive et lit ce que le contrôle en dit.

Un lot par famille ; le fichier grossit à mesure que les exemptions tombent."""
from __future__ import annotations

import sys

import pytest

from core import validator
from core.models.background import BackgroundLayer
from core.models.components import ScriptComponent, SpriteComponent
from core.models.scene import Actor
from core.models.sprite import SpriteAsset
from core.project import Project
from core.validator import ValidationContext


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


def run(project: Project, check, *args) -> list[tuple[str, str]]:
    """(niveau, message) de tout ce que ce contrôle émet sur ce projet."""
    ctx = ValidationContext(project)
    check(ctx, *args)
    return [(m.level, m.message) for m in ctx._msgs]


def says(found, level: str, fragment: str) -> bool:
    return any(lvl == level and fragment in msg for lvl, msg in found)


# ── Environnement, composants, sprites, scripts, fonds ────────────────────


def test_un_luaparser_absent_est_dit(project, monkeypatch):
    monkeypatch.setitem(sys.modules, "luaparser", None)            # `import` lève ImportError
    assert says(run(project, validator._check_lua_subset), "warning", "luaparser is missing")


def test_des_en_tetes_du_runtime_introuvables_sont_dits(project, tmp_path, monkeypatch):
    from core import app_paths
    monkeypatch.setattr(app_paths, "RUNTIME_DIR", tmp_path / "no_runtime")
    assert says(run(project, validator._check_api_prototypes), "warning", "Runtime headers not found")


def test_un_composant_inconnu_est_ignore_et_dit(project):
    found = run(project, validator._check_components, Actor(name="A"), [object()])
    assert says(found, "warning", "Unsupported component type ignored: object")


def test_un_sprite_sans_png_avertit(project):
    project.sprites.append(SpriteAsset(name="Hero", asset=""))
    found = run(project, validator._check_sprite, Actor(name="A"), SpriteComponent(sprite_name="Hero"))
    assert says(found, "warning", "Sprite 'Hero' has no PNG assigned")


def test_un_sprite_aux_cadres_nuls_est_une_erreur(project):
    from PIL import Image
    png = project.root / "assets" / "sprites" / "hero.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (16, 16)).save(png)
    project.sprites.append(SpriteAsset(name="Hero", asset="assets/sprites/hero.png", frame_w=0, frame_h=16))
    found = run(project, validator._check_sprite, Actor(name="A"), SpriteComponent(sprite_name="Hero"))
    assert says(found, "error", "Sprite 'Hero' : invalid frame_w/h (0×16)")


def test_un_composant_script_sans_script_avertit(project):
    found = run(project, validator._check_script, Actor(name="A"), ScriptComponent(script=""))
    assert says(found, "warning", "ScriptComponent without an assigned script")


def test_un_fichier_de_traduction_illisible_est_dit(project):
    project.translation_problems = {"fr": "ValueError: bad json"}
    found = run(project, validator._check_translation_files)
    assert says(found, "warning", 'is unreadable (ValueError: bad json) — language "fr" falls back')


def test_un_calque_de_fond_dont_l_image_manque_est_ignore_et_dit(project):
    project.active_scene.background_layers = [BackgroundLayer(bg_slot=1, background_name="Gone")]
    found = run(project, validator._check_backgrounds)
    assert says(found, "warning", "Background BG1: image 'Gone' not found — layer ignored")


# ── Interface : textes, images, fonds, mélange ────────────────────────────


def _layout_in_scene(project, *elements, **layout_fields):
    """Un layout `hud` posé sur la scène active par un nœud Interface (ancré écran par défaut)."""
    from core.models.ui_region import InterfaceNode, UILayout
    layout = UILayout(name="hud", **layout_fields)
    layout.elements.extend(elements)
    project.ui_layouts.append(layout)
    node_fields = {k: v for k, v in layout_fields.items() if k in ("anchor", "anchor_actor")}
    project.active_scene.ui_layouts.append(InterfaceNode(layout_name="hud", **node_fields))
    return layout


def test_une_boite_qui_suit_une_sequence_sans_texte_est_une_erreur(project):
    from core.models.ui_region import UITextbox
    _layout_in_scene(project, UITextbox(name="dialog", sequence_prefix="intro"))
    found = run(project, validator._check_ui_text_key)
    assert says(found, "error", "Textbox 'dialog' (layout 'hud') follows the text sequence 'intro', which no longer has any text")


def test_un_texte_qui_pointe_une_cle_disparue_est_une_erreur(project):
    from core.models.ui_region import UIText
    _layout_in_scene(project, UIText(name="title", text_key="gone.key"))
    found = run(project, validator._check_ui_text_key)
    assert says(found, "error", "Text 'title' (layout 'hud') points to key 'gone.key'")


def test_un_mode_de_melange_sans_premiere_cible_avertit(project):
    from core.models.scene import BLEND_ALPHA, Scene
    project.scenes.append(Scene(name="Blendy", blend_mode=BLEND_ALPHA))
    assert says(run(project, validator._check_blend), "warning", "no first target is designated")


def test_un_role_dessous_sous_un_mode_qui_ne_l_emploie_pas_avertit(project):
    from core.models.scene import BLEND_BOTTOM, BLEND_BRIGHTEN, BLEND_TOP, Scene
    scene = Scene(name="Blendy", blend_mode=BLEND_BRIGHTEN, blend_obj_role=BLEND_TOP)
    scene.background_layers = [BackgroundLayer(bg_slot=2, background_name="Sky", blend_role=BLEND_BOTTOM)]
    project.scenes.append(scene)
    assert says(run(project, validator._check_blend), "warning", 'BG2 set to "bottom", but this mode only uses the top')


def test_une_image_dont_le_sprite_a_disparu_est_une_erreur(project):
    from core.models.ui_region import UIImage
    _layout_in_scene(project, UIImage(name="icon", sprite_name="Gone"))
    found = run(project, validator._check_ui_image)
    assert says(found, "error", "points to sprite 'Gone', which no longer exists")


def test_une_image_qui_demande_un_etat_absent_avertit(project):
    from core.models.ui_region import UIImage
    project.sprites.append(SpriteAsset(name="Hero", asset=""))
    _layout_in_scene(project, UIImage(name="icon", sprite_name="Hero", state_name="jump"))
    found = run(project, validator._check_ui_image)
    assert says(found, "warning", "asks for state 'jump', missing from sprite 'Hero'")


def test_un_fond_de_conteneur_d_un_mode_que_la_cible_n_a_pas_avertit(project):
    from core.models.scene import Scene
    from core.models.ui_region import ANCHOR_ACTOR, FILL_COLOR, UIContainer
    project.active_scene.actors.append(Actor(name="Hero"))
    _layout_in_scene(project, UIContainer(name="panel", fill_kind=FILL_COLOR),
                     anchor=ANCHOR_ACTOR, anchor_actor="Hero")
    found = run(project, validator._check_ui_container_fill)
    assert says(found, "warning", "which does not exist on target OBJ")


def test_un_acteur_ou_une_interface_dont_la_source_a_disparu_est_une_erreur(project):
    from core.models.ui_region import InterfaceNode
    scene = project.active_scene
    hero, node = Actor(name="Hero"), InterfaceNode(layout_name="hud")
    hero.source, node.source = "deadbeef0001", "deadbeef0002"      # posé à l'ouverture par `resolve_scene_sources`
    scene.actors.append(hero)
    scene.ui_layouts.append(node)
    found = run(project, validator._check_scene_sources)
    assert says(found, "error", "actor 'Hero' comes from a prefab that no longer exists (source deadbeef0001)")
    assert says(found, "error", "comes from a layout that no longer exists (source deadbeef0002)")


# ── Tables de données, caméras ────────────────────────────────────────────


def _table(project, name="Items", columns=(), rows=()):
    from core.models.data_table import DataColumn, DataTable
    table = DataTable(name=name, columns=[DataColumn(name=n, type=t) for n, t in columns], rows=list(rows))
    project.data_tables.append(table)
    return table


def test_un_nom_de_table_qui_n_est_pas_un_identifiant_est_une_erreur(project):
    _table(project, name="1 Items")
    assert says(run(project, validator._check_data_tables), "error", 'Table "1 Items": a script writes it without quotes')


def test_une_colonne_mal_nommee_en_double_ou_de_type_inconnu_est_une_erreur(project):
    _table(project, columns=[("bad name", "int"), ("price", "int"), ("price", "int"), ("mood", "nonsense")])
    found = run(project, validator._check_data_tables)
    assert says(found, "error", 'column "bad name": same rule as the table name')
    assert says(found, "error", 'two columns named "price"')
    assert says(found, "error", "column \"mood\": unknown type 'nonsense'")


def test_une_ligne_qui_cite_une_colonne_absente_avertit(project):
    _table(project, columns=[("price", "int")], rows=[{"price": 1, "ghost": 2}])
    assert says(run(project, validator._check_data_tables), "warning", 'row 1: key "ghost" matches no column')


def _scene_with_camera(project, scene_name, camera_name, **fields):
    from core.models.camera import Camera
    from core.models.scene import Scene
    scene = Scene(name=scene_name)
    scene.cameras = [Camera(name=camera_name, **fields)]
    project.scenes.append(scene)
    return scene


def test_une_camera_en_suivi_sans_cible_avertit(project):
    _scene_with_camera(project, "Level", "Cam", mode="follow", follow_target="")
    assert says(run(project, validator._check_cameras), "warning", "follow mode without a target actor")


def test_une_camera_qui_suit_un_acteur_d_une_autre_scene_avertit(project):
    _scene_with_camera(project, "Level", "Cam", mode="follow", follow_target="Ghost")
    assert says(run(project, validator._check_cameras), "warning", 'follows "Ghost", which is not an actor of this scene')


def test_deux_cameras_de_meme_nom_dans_deux_scenes_avertissent(project):
    _scene_with_camera(project, "One", "Cam")
    _scene_with_camera(project, "Two", "Cam")
    assert says(run(project, validator._check_cameras), "warning", 'Two cameras named "Cam" (scenes \'One\' and \'Two\')')


# ── Scripts, budget d'OAM, fenêtres, symboles C ───────────────────────────


def _script(project, text, name):
    (project.user_library_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (project.user_library_dir / "scripts" / name).write_text(text, encoding="utf-8")
    return f"assets/scripts/{name}"


def test_une_instruction_hors_fonction_dans_un_brouillon_avertit(project):
    _script(project, "x = 1\nfunction on_start()\nend\n", "Draft.lua")
    ctx = ValidationContext(project)
    validator._check_scripts_parse(ctx)
    assert any("outside any function" in m.message and "(attached to nothing)" in m.message
               and m.level == "warning" and m.file == "Draft.lua" for m in ctx._msgs)


def test_un_script_attache_sans_aucune_fonction_avertit(project):
    project.active_scene.script = _script(project, "-- rien\n", "Empty.lua")
    ctx = ValidationContext(project)
    validator._check_scripts_parse(ctx)
    assert any(m.level == "warning" and "defines no function" in m.message and m.file == "Empty.lua"
               for m in ctx._msgs)


def _oam_layout(monkeypatch, **fields):
    from types import SimpleNamespace
    from codegen import oam_alloc
    layout = SimpleNamespace(over_budget=False, over_capacity=False, ui=0, placed=0, capacity=256, pools=[], **fields)
    monkeypatch.setattr(oam_alloc, "scene_oam_layout", lambda _p, _scene: layout)


def test_une_interface_qui_depasse_a_elle_seule_l_oam_est_une_erreur(project, monkeypatch):
    from types import SimpleNamespace
    from codegen import oam_alloc
    layout = SimpleNamespace(over_budget=True, over_capacity=False, ui=140, placed=0, capacity=256, pools=[])
    monkeypatch.setattr(oam_alloc, "scene_oam_layout", lambda _p, _scene: layout)
    found = run(project, validator._check_actor_budget)
    assert says(found, "error", "the interface alone needs 140 OAM entries")


def test_un_prefab_spawne_qui_ne_peut_pas_naitre_est_une_erreur(project, monkeypatch):
    from scripting import refactor
    _oam_layout(monkeypatch)
    monkeypatch.setattr(refactor, "scene_spawned_prefabs", lambda _p, _scene: {"Bullet"})
    found = run(project, validator._check_actor_budget)
    assert says(found, "error", "prefab 'Bullet' is spawned but cannot be born")


def test_une_fenetre_rectangulaire_sans_nom_est_une_erreur(project):
    from core.models.scene import WindowSlot
    project.active_scene.windows = [WindowSlot(name="")]
    assert says(run(project, validator._check_window_regions), "error", "a rectangle window has no name")


def test_deux_fenetres_de_meme_nom_dans_deux_scenes_avertissent(project):
    from core.models.scene import Scene, WindowSlot
    second = Scene(name="Second")
    project.scenes.append(second)
    project.scenes[0].windows = [WindowSlot(name="hud")]
    second.windows = [WindowSlot(name="hud")]
    found = run(project, validator._check_window_regions)
    assert says(found, "warning", 'Two windows named "hud"')


def test_deux_assets_de_meme_symbole_c_sont_une_erreur(project):
    project.sprites.append(SpriteAsset(name="My Hero", asset=""))
    project.sprites.append(SpriteAsset(name="My_Hero", asset=""))
    found = run(project, validator._check_asset_symbol_collisions)
    assert says(found, "error", 'The sprites "My Hero" and "My_Hero" give the same C symbol')


# ── Entrées réservées, audio, boîtes sonores ──────────────────────────────


def test_une_entree_au_nom_reserve_est_une_erreur_pour_chaque_famille(project):
    from core.models.settings import INTERACT_INPUT_NAME, InputAxis, InputBinding, InputSequence
    settings = project.settings
    settings.inputs = [InputBinding(name=INTERACT_INPUT_NAME)]
    settings.axes = [InputAxis(name=INTERACT_INPUT_NAME)]
    settings.sequences = [InputSequence(name=INTERACT_INPUT_NAME)]
    found = run(project, validator._check_reserved_input_names)
    for kind in ("input", "axis", "sequence"):
        assert says(found, "error", f'The {kind} "{INTERACT_INPUT_NAME}" uses a reserved name')


def _audio_file(project, relative: str):
    path = project.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF")
    return relative


def test_un_son_sans_fichier_associe_avertit(project):
    from core.models.audio import Sfx
    project.sfx.append(Sfx(name="Coin", asset=""))
    assert says(run(project, validator._check_audio_files), "warning", 'SFX "Coin": no associated file')


def test_un_fichier_audio_refuse_est_une_erreur(project, monkeypatch):
    from core.models.audio import Sfx
    from core.resources import asset_reconciliation
    project.sfx.append(Sfx(name="Coin", asset=_audio_file(project, "assets/sfx/coin.wav")))
    monkeypatch.setattr(asset_reconciliation, "check_audio_file", lambda *_a, **_k: "24-bit WAV is not supported")
    assert says(run(project, validator._check_audio_files), "error", 'SFX "Coin" (coin.wav): 24-bit WAV is not supported')


def test_un_effet_dont_le_decoupage_est_faux_avertit(project, monkeypatch):
    from core.models.audio import Sfx
    from core.resources import asset_reconciliation
    project.sfx.append(Sfx(name="Coin", asset=_audio_file(project, "assets/sfx/coin.wav")))
    monkeypatch.setattr(asset_reconciliation, "check_audio_file", lambda *_a, **_k: None)
    monkeypatch.setattr(validator, "_sfx_trim_problem", lambda _sfx, _path: "The trim is past the end.")
    found = run(project, validator._check_audio_files)
    assert says(found, "warning", 'SFX "Coin": The trim is past the end. The whole effect goes into the ROM.')


def test_une_scene_dont_la_musique_n_existe_pas_avertit(project):
    project.active_scene.music = "Nope"
    assert says(run(project, validator._check_audio_files), "warning", 'music "Nope" does not exist')


def test_une_musique_au_nom_du_silence_est_une_erreur(project):
    from core.models.audio import Music
    from core.models.scene import MUSIC_NONE
    project.music.append(Music(name=MUSIC_NONE, asset=""))
    assert says(run(project, validator._check_audio_files), "error", "is the reserved word for silence")


def test_un_module_de_plus_de_voies_que_de_canaux_avertit(project, monkeypatch):
    from types import SimpleNamespace
    from core.models.audio import Music
    project.music.append(Music(name="Theme", asset=_audio_file(project, "assets/music/theme.it")))
    project.settings.sound_channels = 8
    monkeypatch.setattr(ValidationContext, "module", lambda self, _path: SimpleNamespace(num_channels=16))
    found = run(project, validator._check_module_channels)
    assert says(found, "warning", '"Theme" uses 16 voices, the project only has 8 channels')


def test_une_boite_en_trop_un_etat_double_et_une_musique_absente_sont_dits(project):
    from core.models.sound_box import MusicBox, MusicState
    first = MusicBox(name="a", states=[MusicState(name="calm", music="Gone"), MusicState(name="calm", music="")])
    project.music_boxes.append(first)
    project.music_boxes.append(MusicBox(name="b"))
    found = run(project, validator._check_sound_boxes)
    assert says(found, "warning", 'MusicBox "b": the game only loads one, "a"')
    assert says(found, "error", 'MusicBox "a": two states are named "calm"')
    assert says(found, "warning", 'MusicBox "a", state "calm": music "Gone" does not exist')


def test_une_action_de_boite_qui_cite_un_son_absent_avertit(project):
    from core.models.sound_box import ActionState, SoundBox
    project.sound_boxes.append(SoundBox(name="fx", states=[ActionState(name="idle", mapping={"jump": "NoSuchSfx"})]))
    found = run(project, validator._check_sound_boxes)
    assert says(found, "warning", 'SoundBox "fx", state "idle": action "jump" points to sound effect "NoSuchSfx"')


# ── Polices, palettes de fond ─────────────────────────────────────────────


def test_un_texte_qui_cite_un_caractere_absent_de_sa_police_avertit(project, monkeypatch):
    """La police est factice (un seul glyphe, « a ») : ce que le contrôle juge, c'est le caractère que le texte cite en plus."""
    from types import SimpleNamespace
    from codegen import font_emit
    from core.models.font import Font
    from core.models.ui_region import UIText
    from scripting import api, refactor
    project.fonts.append(Font(name="Pixel"))
    pixel = SimpleNamespace(name="Pixel", glyphs=[SimpleNamespace(char="a")])
    monkeypatch.setattr(font_emit, "encodable_project_fonts", lambda _p: [pixel])
    text = project.new_text("a☃")
    _layout_in_scene(project, UIText(name="title"))
    site = SimpleNamespace(values={api.DOMAIN_UI_ELEMENT: "title", api.DOMAIN_TEXT: text.key})
    monkeypatch.setattr(refactor, "find_call_sites_in_project", lambda _p, *_domains: [site])
    found = run(project, validator._check_font_coverage)
    assert says(found, "warning", f"Text '{text.key}' cites a character missing from the active font (the zone 'title'): Pixel : ☃")


def test_une_police_par_defaut_du_projet_ou_d_une_langue_inutilisable_avertit(project):
    from core.models.settings import Language
    project.settings.default_font = "NoSuchFont"
    project.settings.languages = [Language(code="fr", name="Français", default_font="AlsoGone")]
    found = run(project, validator._check_scene_font)
    assert says(found, "warning", 'Project: the Default Font "NoSuchFont" is missing or unusable')
    assert says(found, "warning", 'Language "fr": the Default Font "AlsoGone" is missing or unusable')


def test_une_police_de_scene_sans_planche_ou_inexistante_avertit(project):
    from core.models.font import Font
    from core.models.scene import Scene
    project.fonts.append(Font(name="Sheetless"))              # existe, mais rien à compiler
    for name, font in (("NoSheet", "Sheetless"), ("NoFont", "Ghost")):
        project.scenes.append(Scene(name=name, font_name=font))
    found = run(project, validator._check_scene_font)
    assert says(found, "warning", "Scene 'NoSheet': the default font \"Sheetless\" has no usable sheet")
    assert says(found, "warning", "Scene 'NoFont': the default font \"Ghost\" does not exist in the project")


def test_un_override_de_palette_leve_par_un_nouvel_encodage_est_dit(project):
    from core.models.background import BackgroundAsset
    ba = BackgroundAsset(name="Sky")
    ba.diagnostics = {"palette_overrides_dropped": [2, 3]}
    project.backgrounds.append(ba)
    found = run(project, validator._check_background_palette_refs)
    assert says(found, "warning", "Background 'Sky': the palette override(s) on derived palette(s) 2, 3 were lifted")
