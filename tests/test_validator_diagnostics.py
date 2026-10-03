"""Chaque diagnostic du validateur est déclenché au moins une fois (chantier « La fiabilité du
journal de build », tranche 5).

Le relevé de couverture avait montré une centaine de sites du validateur que aucun test
n'atteignait : un message jamais produit est un message dont on ne sait pas s'il s'affiche
encore. Chaque test construit la plus petite panne possible et appelle LE contrôle concerné.
"""
from __future__ import annotations

import pytest

from core import validator
from core.models.background import BackgroundAsset, BackgroundLayer
from core.models.components import CollisionBoxComponent, ScriptComponent, SpriteComponent
from core.models.scene import (BLEND_ALPHA, BLEND_BOTTOM, BLEND_BRIGHTEN, BLEND_TOP, Actor, Scene)
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


# ── Sprites, scripts, collisions ──────────────────────────────────────────


def test_un_sprite_sans_png_avertit(project):
    project.sprites.append(SpriteAsset(name="Hero", asset=None))
    found = run(project, validator._check_sprite, Actor(name="A"), SpriteComponent(sprite_name="Hero"))
    assert says(found, "warning", "has no PNG assigned")


def test_un_sprite_dont_le_png_manque_est_une_erreur(project):
    project.sprites.append(SpriteAsset(name="Hero", asset="assets/sprites/gone.png"))
    found = run(project, validator._check_sprite, Actor(name="A"), SpriteComponent(sprite_name="Hero"))
    assert says(found, "error", "PNG file not found")


def test_un_sprite_aux_dimensions_de_frame_nulles_est_une_erreur(project):
    from PIL import Image
    folder = project.root / "assets" / "sprites"
    folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (16, 16)).save(folder / "hero.png")
    project.sprites.append(SpriteAsset(name="Hero", asset="assets/sprites/hero.png", frame_w=0, frame_h=16))
    found = run(project, validator._check_sprite, Actor(name="A"), SpriteComponent(sprite_name="Hero"))
    assert says(found, "error", "invalid frame_w/h")


def test_un_composant_script_sans_script_avertit(project):
    found = run(project, validator._check_script, Actor(name="A"), ScriptComponent(script=""))
    assert says(found, "warning", "without an assigned script")


def test_une_boite_de_collision_sans_surface_est_une_erreur(project):
    found = run(project, validator._check_collision, Actor(name="A"), CollisionBoxComponent(tag="hit", w=0, h=8))
    assert says(found, "error", "zero width or height")


def test_un_composant_inconnu_est_ignore_avec_un_avertissement(project):
    class Alien:
        pass
    found = run(project, validator._check_components, Actor(name="A"), [Alien()])
    assert says(found, "warning", "Unsupported component type ignored")


# ── Mélange de couleurs ───────────────────────────────────────────────────


def _scene_with_blend(project, mode, **kwargs) -> Scene:
    scene = Scene(name="Blendy", blend_mode=mode, **kwargs)
    project.scenes.append(scene)
    return scene


def test_un_melange_sans_premiere_cible_avertit(project):
    _scene_with_blend(project, BLEND_ALPHA)
    assert says(run(project, validator._check_blend), "warning", "no first target is designated")


def test_un_alpha_sans_seconde_cible_avertit(project):
    _scene_with_blend(project, BLEND_ALPHA, blend_obj_role=BLEND_TOP)
    assert says(run(project, validator._check_blend), "warning", "alpha without a second target")


def test_un_role_dessous_sous_un_mode_qui_ne_l_emploie_pas_avertit(project):
    scene = _scene_with_blend(project, BLEND_BRIGHTEN, blend_obj_role=BLEND_TOP)
    scene.background_layers.append(BackgroundLayer(background_name="x", bg_slot=1, blend_role=BLEND_BOTTOM))
    assert says(run(project, validator._check_blend), "warning", "this role does nothing")


# ── Fonds ─────────────────────────────────────────────────────────────────


def test_un_fond_dont_le_png_manque_est_ignore_avec_un_message(project):
    project.backgrounds.append(BackgroundAsset(name="sky", asset="assets/backgrounds/sky.png"))
    scene = project.active_scene
    scene.background_layers.append(BackgroundLayer(background_name="sky", bg_slot=0))
    assert says(run(project, validator._check_backgrounds), "warning", "PNG not found")


# ── Interface : textes, images, fonds de conteneur ────────────────────────


def _layout_in_scene(project, *elements):
    """Un layout `hud` posé sur la scène active par un nœud Interface (ancré écran)."""
    from core.models.ui_region import InterfaceNode, UILayout
    layout = UILayout(name="hud")
    layout.elements.extend(elements)
    project.ui_layouts.append(layout)
    project.active_scene.ui_layouts.append(InterfaceNode(layout_name="hud"))
    return layout


def test_un_texte_dont_la_cle_a_disparu_est_une_erreur(project):
    from core.models.ui_region import UIText
    _layout_in_scene(project, UIText(name="title", text_key="gone.key"))
    assert says(run(project, validator._check_ui_text_key), "error", "which no longer exists in the text table")


def test_une_image_sur_un_sprite_disparu_est_une_erreur(project):
    from core.models.ui_region import UIImage
    _layout_in_scene(project, UIImage(name="icon", sprite_name="Nowhere"))
    assert says(run(project, validator._check_ui_image), "error", "which no longer exists in the project")


def test_une_image_sur_un_etat_inconnu_avertit(project):
    from core.models.ui_region import UIImage
    project.sprites.append(SpriteAsset(name="Hero"))
    _layout_in_scene(project, UIImage(name="icon", sprite_name="Hero", state_name="Nope"))
    assert says(run(project, validator._check_ui_image), "warning", "missing from sprite")


def test_un_fond_sprite_sur_la_cible_bg_avertit(project):
    from core.models.ui_region import FILL_SPRITE, UIContainer
    _layout_in_scene(project, UIContainer(name="panel", fill_kind=FILL_SPRITE, fill_sprite="Hero"))
    assert says(run(project, validator._check_ui_container_fill), "warning", "does not exist on target BG")


def test_un_fond_couleur_sans_palette_active_n_est_pas_dans_la_rom(project):
    from core.models.ui_region import FILL_COLOR, UIContainer
    _layout_in_scene(project, UIContainer(name="panel", fill_kind=FILL_COLOR, fill_palette="Missing"))
    assert says(run(project, validator._check_ui_container_fill), "warning", "will NOT be in the ROM")


# ── Tables de données ─────────────────────────────────────────────────────


def _table(project, name="Items", columns=(), rows=()):
    from core.models.data_table import DataColumn, DataTable
    table = DataTable(name=name, columns=[DataColumn(name=n, type=t) for n, t in columns], rows=list(rows))
    project.data_tables.append(table)
    return table


def test_un_nom_de_table_qui_n_est_pas_un_identifiant_est_refuse(project):
    _table(project, name="1 bad name")
    assert says(run(project, validator._check_data_tables), "error", "must be an identifier")


def test_un_nom_de_colonne_qui_n_est_pas_un_identifiant_est_refuse(project):
    _table(project, columns=[("bad name", "int")])
    assert says(run(project, validator._check_data_tables), "error", "it is an identifier")


def test_deux_colonnes_du_meme_nom_sont_refusees(project):
    _table(project, columns=[("price", "int"), ("price", "int")])
    assert says(run(project, validator._check_data_tables), "error", "two columns named")


def test_un_type_de_colonne_inconnu_est_refuse(project):
    _table(project, columns=[("price", "float128")])
    assert says(run(project, validator._check_data_tables), "error", "unknown type")


def test_une_cle_de_ligne_sans_colonne_avertit(project):
    _table(project, columns=[("price", "int")], rows=[{"price": 1, "ghost": 2}])
    assert says(run(project, validator._check_data_tables), "warning", "matches no column")


def test_une_reference_qui_ne_resout_pas_est_une_erreur(project):
    _table(project, columns=[("hit", "sfx")], rows=[{"hit": "NoSuchSound"}])
    assert says(run(project, validator._check_data_tables), "error", 'no sfx named "NoSuchSound"')


def test_les_trois_listes_de_types_de_colonne_s_accordent_ou_le_disent(project, monkeypatch):
    from core import project as project_module
    from core.models import data_table

    monkeypatch.setattr(data_table, "COLUMN_REFERENCES", tuple(data_table.COLUMN_REFERENCES) + ("ghost",))
    found = run(project, validator._check_data_column_types)
    assert says(found, "error", "without a matching script domain: ghost")
    assert says(found, "error", "without a list of citable names: ghost")

    monkeypatch.undo()
    sources = dict(project_module.DATA_COLUMN_SOURCES, phantom=lambda *_: [])
    monkeypatch.setattr(project_module, "DATA_COLUMN_SOURCES", sources)
    assert says(run(project, validator._check_data_column_types), "warning", "no longer exists: phantom")


# ── Fenêtres, noms d'acteurs, polices de scène, banques de palettes ───────


def test_plus_de_deux_fenetres_rectangulaires_par_scene_est_une_erreur(project):
    from core.models.scene import WindowSlot
    project.active_scene.windows = [WindowSlot(name=n) for n in ("a", "b", "c")]
    assert says(run(project, validator._check_window_regions), "error", "do(es) not fit")


def test_une_fenetre_sans_nom_est_une_erreur(project):
    from core.models.scene import WindowSlot
    project.active_scene.windows = [WindowSlot(name="")]
    assert says(run(project, validator._check_window_regions), "error", "has no name")


def test_deux_fenetres_de_meme_nom_dans_deux_scenes_avertissent(project):
    from core.models.scene import WindowSlot
    project.scenes.append(Scene(name="Other"))
    for scene in project.scenes:
        scene.windows = [WindowSlot(name="dialog")]
    assert says(run(project, validator._check_window_regions), "warning", 'Two windows named "dialog"')


def test_deux_acteurs_de_meme_symbole_c_avertissent(project):
    scene = project.active_scene
    scene.actors = [Actor(name="Player 1"), Actor(name="Player-1"), Actor(name="Twin"), Actor(name="Twin")]
    found = run(project, validator._check_actor_name_collisions)
    assert says(found, "warning", 'Actors "Player 1" and "Player-1"')
    assert says(found, "warning", 'Two actors named "Twin"')


def test_une_police_par_defaut_inconnue_avertit_au_niveau_du_projet_et_de_la_langue(project):
    from core.models.settings import Language
    project.settings.default_font = "Ghost"
    project.settings.languages = [Language(code="de", name="Deutsch", default_font="Phantom")]
    found = run(project, validator._check_scene_font)
    assert says(found, "warning", 'Default Font "Ghost" is missing or unusable')
    assert says(found, "warning", 'Language "de": the Default Font "Phantom"')


def test_une_police_de_scene_inconnue_ou_sans_planche_avertit(project):
    from core.models.font import Font
    project.fonts.append(Font(name="Sheetless", asset="assets/fonts/missing.png", source_format="png"))
    project.active_scene.font_name = "Sheetless"
    assert says(run(project, validator._check_scene_font), "warning", "has no usable sheet")
    project.active_scene.font_name = "Nowhere"
    assert says(run(project, validator._check_scene_font), "warning", "does not exist in the project")


def test_un_acteur_d_ecran_avec_collision_camera_ou_interface_avertit(project):
    from core.models.camera import Camera
    from core.models.ui_region import ANCHOR_ACTOR, InterfaceNode, UILayout
    scene = project.active_scene
    hud = Actor(name="Hud", screen_space=True)
    hud.components = [CollisionBoxComponent(tag="hit", w=8, h=8)]
    scene.actors = [hud]
    scene.cameras = [Camera(name="Cam", mode="follow", follow_target="Hud")]
    scene.camera = "Cam"
    project.ui_layouts.append(UILayout(name="bubble", anchor=ANCHOR_ACTOR, anchor_actor="Hud"))
    scene.ui_layouts.append(InterfaceNode(layout_name="bubble", anchor=ANCHOR_ACTOR, anchor_actor="Hud"))
    found = run(project, validator._check_screen_space)
    assert says(found, "warning", "carries a CollisionBox")
    assert says(found, "warning", "will stay still")
    assert says(found, "warning", "subtract the scroll a second time")


def test_une_banque_de_palette_inexistante_avertit_pour_acteur_prefab_et_fond(project):
    from core.models.scene import Prefab
    project.sprites.append(SpriteAsset(name="Hero", asset="assets/sprites/hero.png"))
    scene = project.active_scene
    actor = Actor(name="A", pal_bank=5)
    actor.components = [SpriteComponent(sprite_name="Hero")]
    scene.actors = [actor]
    prefab = Prefab(name="Bullet")
    prefab.actor.pal_bank = 3
    prefab.actor.components = [SpriteComponent(sprite_name="Hero")]
    project.prefabs.append(prefab)
    scene.prefab_pools = {"Bullet": 1}
    scene.background_layers.append(BackgroundLayer(background_name="sky", bg_slot=0, pal_bank=4))
    found = run(project, validator._check_pal_bank_reference)
    assert says(found, "warning", "Actor 'A' points to OBJ bank 5")
    assert says(found, "warning", "Prefab 'Bullet' points to OBJ bank 3")
    assert says(found, "warning", "Background 'sky' BG0")


def test_un_depassement_de_seize_banques_avertit(project, monkeypatch):
    from codegen import palette_alloc

    class Full:
        def overflow(self):
            return True

    monkeypatch.setattr(palette_alloc, "scene_bank_layout", lambda *_args: Full())
    assert says(run(project, validator._check_palette_bank_overflow), "warning", "more than 16")


# ── Audio ─────────────────────────────────────────────────────────────────


class _FakeModule:
    def __init__(self, patterns: int, channels: int):
        self.order = [0] * patterns
        self.num_channels = channels


def _music_files(project, monkeypatch, **modules):
    """Des morceaux dont l'analyse est simulée : {nom: (nombre de patterns, nombre de voies)}."""
    from core.models.audio import Music
    folder = project.root / "assets" / "music"
    folder.mkdir(parents=True, exist_ok=True)
    for name in modules:
        (folder / f"{name}.mod").write_bytes(b"stub")
        project.music.append(Music(name=name, asset=f"assets/music/{name}.mod"))
    monkeypatch.setattr(ValidationContext, "module",
                        lambda self, path: _FakeModule(*modules[path.stem]))


def _script(project, text, name="Song.lua"):
    project.scripts_dir.mkdir(parents=True, exist_ok=True)
    (project.scripts_dir / name).write_text(text, encoding="utf-8")


def test_deux_morceaux_de_structure_differente_ne_se_relaient_pas(project, monkeypatch):
    _music_files(project, monkeypatch, A=(4, 4), B=(8, 4))
    _script(project, 'function on_start()\n music.play("B")\n music.cut_to("A")\nend\n')
    assert says(run(project, validator._check_music_cut_compat), "warning", "does not have the same structure")


def test_un_jingle_de_plus_de_quatre_canaux_avertit(project, monkeypatch):
    _music_files(project, monkeypatch, Fanfare=(1, 6))
    _script(project, 'function on_start()\n music.jingle("Fanfare")\nend\n')
    assert says(run(project, validator._check_jingle_channels), "warning", "only gives 4 to a jingle")


def test_un_module_de_plus_de_voies_que_le_projet_avertit(project, monkeypatch):
    _music_files(project, monkeypatch, Big=(1, 16))
    project.settings.sound_channels = 8
    assert says(run(project, validator._check_module_channels), "warning", "uses 16 voices")


def test_les_boites_sonores_disent_doublons_extras_et_references_mortes(project):
    from core.models.sound_box import ActionState, JingleBox, MusicBox, MusicState, SoundBox
    project.music_boxes.append(MusicBox(name="a", states=[MusicState(name="s", music="Nope")]))
    project.music_boxes.append(MusicBox(name="b"))
    project.sound_boxes.append(SoundBox(name="floor", states=[
        ActionState(name="sand", mapping={"step": "NoSuchSfx"}), ActionState(name="sand")]))
    project.jingle_boxes.append(JingleBox(name="j", states=[ActionState(name="win", mapping={"fanfare": "NoSuchSong"})]))
    found = run(project, validator._check_sound_boxes)
    assert says(found, "warning", "the game only loads one")
    assert says(found, "error", 'two states are named "sand"')
    assert says(found, "warning", 'music "Nope" does not exist')
    assert says(found, "warning", 'points to sound effect "NoSuchSfx"')
    assert says(found, "warning", 'points to music "NoSuchSong"')


def test_une_frame_qui_cite_une_action_ou_un_sfx_inconnus_avertit(project):
    from core.models.sprite import AnimFrame, AnimState, StateDirection
    frame = AnimFrame(action_name="step", direct_sfx_name="NoSuchSfx")
    state = AnimState(name="Walk", directions=[StateDirection(dir=0, frames=[frame])])
    project.sprites.append(SpriteAsset(name="Hero", states=[state]))
    found = run(project, validator._check_sound_boxes)
    assert says(found, "warning", "which no SoundBox declares")
    assert says(found, "warning", "cites Sfx")


def test_un_evenement_de_frame_sans_fonction_dans_le_script_avertit(project):
    from core.models.sprite import AnimFrame, AnimState, StateDirection
    _script(project, "function on_start()\nend\n", name="Hero.lua")
    state = AnimState(name="Hit", directions=[StateDirection(dir=0, frames=[AnimFrame(event_name="on_hit_frame")])])
    project.sprites.append(SpriteAsset(name="Hero", states=[state]))
    scene = project.active_scene
    actor = Actor(name="A")
    actor.components = [SpriteComponent(sprite_name="Hero"), ScriptComponent(script="assets/scripts/Hero.lua")]
    scene.actors = [actor]
    ctx = ValidationContext(project)
    validator._check_frame_events(ctx)
    assert says([(m.level, m.message) for m in ctx._msgs], "warning", 'declares no function "on_hit_frame"')


# ── Planches de polices, scripts, accord des listes internes ──────────────


def test_une_planche_de_police_absente_est_une_erreur(project):
    from core.models.font import Font
    project.fonts.append(Font(name="Gone", asset="assets/fonts/gone.png", source_format="png"))
    assert says(run(project, validator._check_font_sheets), "error", "sheet gone.png not found")


def test_un_script_attache_a_deux_familles_est_refuse(project):
    _script(project, "function on_start()\nend\n", name="Shared.lua")
    attached = "assets/scripts/Shared.lua"
    project.active_scene.script = attached
    actor = Actor(name="A")
    actor.components = [ScriptComponent(script=attached)]
    project.active_scene.actors = [actor]
    assert says(run(project, validator._check_script_owner_families), "error", "several families of owners")


def test_un_script_illisible_est_dit_avec_son_fichier(project, monkeypatch):
    _script(project, "function on_start()\nend\n", name="Locked.lua")
    real = type(project.scripts_dir / "x").read_text

    def refuse(self, *args, **kwargs):
        if self.name == "Locked.lua":
            raise PermissionError("denied")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(type(project.scripts_dir / "x"), "read_text", refuse)
    ctx = ValidationContext(project)
    validator._check_scripts_parse(ctx)
    assert any("cannot be read" in m.message and m.file == "Locked.lua" for m in ctx._msgs)


def test_une_scene_absente_est_une_erreur_de_build(project):
    ctx = ValidationContext(project)
    ctx.scene = None
    validator._check_scene(ctx)
    assert any("No active scene" in m.message for m in ctx._msgs)


def test_un_validateur_plugin_qui_plante_devient_un_avertissement(project, monkeypatch):
    def broken(_ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(validator, "_VALIDATORS", [broken])
    warns, _errors = validator.validate_project(project)
    assert any("Validator 'broken' crashed: boom" in w.message for w in warns)


# ── L'accord api.py ↔ en-têtes du runtime et lua_subset ↔ luaparser ───────


def _fake_runtime(tmp_path, monkeypatch, engine_header: str):
    from core import app_paths
    include = tmp_path / "runtime" / "include"
    include.mkdir(parents=True)
    (include / "gba_engine.h").write_text(engine_header, encoding="utf-8")
    (include / "runtime_api_inline.h").write_text("", encoding="utf-8")
    monkeypatch.setattr(app_paths, "RUNTIME_DIR", tmp_path / "runtime")


def test_des_en_tetes_introuvables_avertissent(project, tmp_path, monkeypatch):
    from core import app_paths
    monkeypatch.setattr(app_paths, "RUNTIME_DIR", tmp_path / "nowhere")
    assert says(run(project, validator._check_api_prototypes), "warning", "Runtime headers not found")


def test_une_valeur_d_enum_qui_diverge_est_une_erreur(project, tmp_path, monkeypatch):
    from scripting import api
    _fake_runtime(tmp_path, monkeypatch, "#define FAKE_MODE 5\n")
    monkeypatch.setattr(api, "hardware_enum_defines", lambda: [("FAKE_MODE", 7)])
    assert says(run(project, validator._check_api_prototypes), "error", "FAKE_MODE (api.py=7, gba_engine.h=5)")


def test_deux_arguments_permutes_entre_lua_et_c_sont_une_erreur(project, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripting import api
    _fake_runtime(tmp_path, monkeypatch, "void fake_call(int b, int a);\n")
    fake = SimpleNamespace(c_func="fake_call", params=[SimpleNamespace(name="a"), SimpleNamespace(name="b")])
    monkeypatch.setattr(api, "RUNTIME_API", {"fake.call": fake})
    monkeypatch.setattr(api, "hardware_enum_defines", lambda: [])
    assert says(run(project, validator._check_api_prototypes), "error", "Inconsistent argument order")


def test_un_luaparser_absent_avertit(project, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "luaparser", None)
    assert says(run(project, validator._check_lua_subset), "warning", "luaparser is missing")


def test_un_noeud_lua_non_classe_ou_fantome_est_dit(project, monkeypatch):
    from scripting import lua_subset
    real = lua_subset.covered_nodes()
    monkeypatch.setattr(lua_subset, "covered_nodes", lambda: frozenset(list(real)[1:]))
    assert says(run(project, validator._check_lua_subset), "error", "not classified in scripting/lua_subset.py")
    monkeypatch.setattr(lua_subset, "covered_nodes", lambda: frozenset(real | {"PhantomNode"}))
    assert says(run(project, validator._check_lua_subset), "warning", "PhantomNode")


# ── Caméras, audio, behaviors, domaines d'argument ────────────────────────


def test_les_pannes_muettes_des_cameras_avertissent(project):
    from core.models.camera import Camera
    first = project.active_scene
    second = Scene(name="Second")
    project.scenes.append(second)
    first.cameras = [Camera(name="Loose", mode="follow", follow_target=""),
                     Camera(name="Lost", mode="follow", follow_target="Ghost"),
                     Camera(name="Same")]
    second.cameras = [Camera(name="Same")]
    first.camera = "Gone"
    found = run(project, validator._check_cameras)
    assert says(found, "warning", "follow mode without a target actor")
    assert says(found, "warning", "which is not an actor of this scene")
    assert says(found, "warning", 'Two cameras named "Same"')
    assert says(found, "warning", 'camera "Gone" no longer exists')


def test_les_fichiers_audio_absents_ou_mauvais_sont_dits(project):
    from core.models.audio import Music, Sfx
    from core.models.scene import MUSIC_NONE
    folder = project.root / "assets" / "sfx"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bad.wav").write_bytes(b"not a wave file")
    project.sfx.append(Sfx(name="Silent", asset=None))
    project.sfx.append(Sfx(name="Gone", asset="assets/sfx/gone.wav"))
    project.sfx.append(Sfx(name="Bad", asset="assets/sfx/bad.wav"))
    project.music.append(Music(name=MUSIC_NONE, asset=None))
    project.active_scene.music = "NoSuchSong"
    found = run(project, validator._check_audio_files)
    assert says(found, "warning", 'SFX "Silent": no associated file')
    assert says(found, "error", 'SFX "Gone": file not found')
    assert says(found, "error", 'SFX "Bad" (bad.wav)')
    assert says(found, "warning", 'music "NoSuchSong" does not exist')
    assert says(found, "error", "reserved word for silence")


def test_un_behavior_qui_emploie_self_est_une_erreur(project):
    project.scripts_behaviors_dir.mkdir(parents=True, exist_ok=True)
    (project.scripts_behaviors_dir / "Bad.lua").write_text(
        "local M = {}\nfunction M.update(actor)\n self.x = 1\nend\nreturn M\n", encoding="utf-8")
    assert says(run(project, validator._check_behaviors_without_self), "error", '`self` is reserved')


def test_un_domaine_d_argument_oublie_par_le_checker_ou_le_codegen_est_une_erreur(project, monkeypatch):
    from scripting import checker, codegen
    monkeypatch.setattr(checker, "covered_domains", lambda: frozenset({"phantom_domain"}))
    monkeypatch.setattr(codegen, "covered_domains", lambda: frozenset({"phantom_domain"}))
    found = run(project, validator._check_api_domains)
    assert says(found, "error", "Unknown argument domain(s) for checker")
    assert says(found, "error", "Unknown argument domain(s) for codegen")
    assert says(found, "warning", "domain(s) declared but missing from api.py: phantom_domain")
