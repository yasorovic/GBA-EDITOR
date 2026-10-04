"""Les contrôles du validateur dont une panne serait silencieuse (chantier « La fiabilité du journal
de build », tranche 5).

On garde ceux qui portent une vraie logique : l'accord de listes internes (api.py ↔ en-têtes du
runtime, lua_subset ↔ luaparser, domaines, colonnes), les budgets (palettes, fenêtres, structure de
musique), les promesses que l'éditeur fait sans que le build les tienne, et les pannes de lecture.
Chaque test construit la plus petite panne possible et appelle LE contrôle concerné.
"""
from __future__ import annotations

import pytest

from core import validator
from core.models.background import BackgroundLayer
from core.models.components import CollisionBoxComponent, ScriptComponent, SpriteComponent
from core.models.scene import BLEND_ALPHA, BLEND_TOP, Actor, Scene
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


def test_un_sprite_dont_le_png_manque_est_un_avertissement(project):
    project.sprites.append(SpriteAsset(name="Hero", asset="assets/sprites/gone.png"))
    found = run(project, validator._check_sprite, Actor(name="A"), SpriteComponent(sprite_name="Hero"))
    assert says(found, "warning", "PNG file not found")


# ── Mélange de couleurs ───────────────────────────────────────────────────


def _scene_with_blend(project, mode, **kwargs) -> Scene:
    scene = Scene(name="Blendy", blend_mode=mode, **kwargs)
    project.scenes.append(scene)
    return scene


def test_un_alpha_sans_seconde_cible_avertit(project):
    _scene_with_blend(project, BLEND_ALPHA, blend_obj_role=BLEND_TOP)
    assert says(run(project, validator._check_blend), "warning", "alpha without a second target")


# ── Fonds ─────────────────────────────────────────────────────────────────


# ── Interface : textes, images, fonds de conteneur ────────────────────────


def _layout_in_scene(project, *elements):
    """Un layout `hud` posé sur la scène active par un nœud Interface (ancré écran)."""
    from core.models.ui_region import InterfaceNode, UILayout
    layout = UILayout(name="hud")
    layout.elements.extend(elements)
    project.ui_layouts.append(layout)
    project.active_scene.ui_layouts.append(InterfaceNode(layout_name="hud"))
    return layout


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


def test_deux_acteurs_de_meme_symbole_c_avertissent(project):
    scene = project.active_scene
    scene.actors = [Actor(name="Player 1"), Actor(name="Player-1"), Actor(name="Twin"), Actor(name="Twin")]
    found = run(project, validator._check_actor_name_collisions)
    assert says(found, "warning", 'Actors "Player 1" and "Player-1"')
    assert says(found, "warning", 'Two actors named "Twin"')


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


def test_un_noeud_lua_non_classe_ou_fantome_est_dit(project, monkeypatch):
    from scripting import lua_subset
    real = lua_subset.covered_nodes()
    monkeypatch.setattr(lua_subset, "covered_nodes", lambda: frozenset(list(real)[1:]))
    assert says(run(project, validator._check_lua_subset), "error", "not classified in scripting/lua_subset.py")
    monkeypatch.setattr(lua_subset, "covered_nodes", lambda: frozenset(real | {"PhantomNode"}))
    assert says(run(project, validator._check_lua_subset), "warning", "PhantomNode")


# ── Caméras, audio, behaviors, domaines d'argument ────────────────────────


def test_un_domaine_d_argument_oublie_par_le_checker_ou_le_codegen_est_une_erreur(project, monkeypatch):
    from scripting import checker, codegen
    monkeypatch.setattr(checker, "covered_domains", lambda: frozenset({"phantom_domain"}))
    monkeypatch.setattr(codegen, "covered_domains", lambda: frozenset({"phantom_domain"}))
    found = run(project, validator._check_api_domains)
    assert says(found, "error", "Unknown argument domain(s) for checker")
    assert says(found, "error", "Unknown argument domain(s) for codegen")
    assert says(found, "warning", "domain(s) declared but missing from api.py: phantom_domain")
