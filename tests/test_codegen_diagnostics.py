"""Les diagnostics des étapes de build qu'aucun vrai build ne déclenche (chantier « La fiabilité du
journal de build », tranche 5).

Les étapes qui lancent grit, mmutil, make ou mGBA ne tournent pas dans ces tests : on leur donne un
outil factice qui échoue de la manière voulue, et on regarde ce que le journal en dit.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from codegen import grit_conversion
from core.models.background import BackgroundAsset, BackgroundLayer
from core.models.scene import Actor
from core.models.sprite import SpriteAsset
from core.project import Project


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


class Journal:
    """Ce que l'étape a émis : `emit` se passe en argument comme au vrai build."""

    def __init__(self):
        self.events: list[tuple[str, tuple]] = []

    def __call__(self, event, *args):
        self.events.append((event, args))

    def diagnostics(self) -> list:
        return [args[0] for event, args in self.events if event == "diagnostic"]

    def says(self, level: str, fragment: str) -> bool:
        return any(d.level == level and fragment in d.message for d in self.diagnostics())


def _png(path: Path, mode: str = "RGB", size=(16, 16)) -> Path:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size).save(path)
    return path


def _failing_run_cmd(*_args, **_kwargs) -> bool:
    return False


# ── Fonctions de conversion de feuilles de sprites ────────────────────────


def test_une_sortie_grit_inattendue_est_refusee(tmp_path):
    journal = Journal()
    c_file = tmp_path / "sprite.c"
    c_file.write_text("// nothing that looks like grit output\n", encoding="utf-8")
    assert grit_conversion.remap_tiles_to_bank(c_file, [0] * 16, journal) is False
    assert journal.says("error", "unexpected grit format")


# ── grit : fonds ──────────────────────────────────────────────────────────


def _background(project, png: bool = True):
    asset = BackgroundAsset(name="sky", asset="sky.png")
    layer = BackgroundLayer(background_name="sky", bg_slot=0)
    if png:
        _png(project.background_images_dir / "sky.png")
    return asset, layer


def test_grit_introuvable_arrete_la_conversion_des_fonds(project):
    journal = Journal()
    asset, layer = _background(project)
    conversion = grit_conversion.GritBackground(None, journal, _failing_run_cmd)
    assert conversion.run(project, [(asset, layer, None, None)]) is False
    assert journal.says("error", "not found")


# ── grit : sprites ────────────────────────────────────────────────────────


# ── mmutil ────────────────────────────────────────────────────────────────


def _sounds(*names: str) -> dict:
    return {"sfx": [(SimpleNamespace(name=n), Path(f"{n}.wav")) for n in names], "music": [], "skipped": []}


def test_un_soundbank_aux_numeros_decales_est_une_erreur(tmp_path):
    journal = Journal()
    header = tmp_path / "soundbank.h"
    header.write_text("#define SFX_BOOM 3\n", encoding="utf-8")
    audio = grit_conversion.MmutilAudio("mmutil", "bin2s", journal, _failing_run_cmd)
    assert audio._check_ids(header, _sounds("Boom", "Missing")) is False
    assert journal.says("error", "SFX_BOOM is 3, expected 0")
    assert journal.says("error", "SFX_MISSING absent de soundbank.h")
    assert journal.says("error", "build interrupted")




# ── rom_build : les étapes de l'orchestrateur ─────────────────────────────


class FakeToolchain:
    """Une chaîne d'outils où l'on choisit ce qui existe."""

    def __init__(self, make=None, mgba=None):
        self._make, self._mgba = make, mgba
        self.devkitpro_path = None

    def resolve_make(self):
        return self._make

    def resolve_mgba(self):
        return self._mgba


def _worker(project, toolchain=None):
    from codegen import BuildWorker
    from core.toolchain import Toolchain
    worker = BuildWorker(project, toolchain or Toolchain())
    journal = Journal()
    worker.on("diagnostic", lambda d: journal("diagnostic", d))
    worker.on("log_line", lambda line: journal("log_line", line))
    return worker, journal


def test_un_projet_sans_scene_est_refuse_avant_tout_travail(project, monkeypatch):
    monkeypatch.setattr(project, "scenes", [])
    worker, journal = _worker(project)
    worker.run()
    assert journal.says("error", "no scene in the project")


def test_un_outil_introuvable_ou_qui_ne_demarre_pas_est_un_diagnostic(project, monkeypatch):
    from codegen import rom_build
    worker, journal = _worker(project)
    assert worker._run_cmd(["definitely-not-a-tool.exe"], "[tool]") is False
    assert journal.says("error", "not found")

    def refuse(*_args, **_kwargs):
        raise PermissionError("working directory refused")

    monkeypatch.setattr(rom_build.subprocess, "run", refuse)
    assert worker._run_cmd(["anything"], "[tool]") is False
    assert journal.says("error", "could not start the tool")


def test_make_introuvable_ou_makefile_manquant_arretent_l_etape(project, monkeypatch, tmp_path):
    from codegen import rom_build
    worker, journal = _worker(project, FakeToolchain(make=None))
    assert worker._step_make(project) is False
    assert journal.says("error", "not found")

    worker, journal = _worker(project, FakeToolchain(make=Path("make.exe")))
    monkeypatch.setattr(rom_build, "RUNTIME_DIR", tmp_path / "no-runtime")
    assert worker._step_make(project) is False
    assert journal.says("error", "Makefile missing")


def test_un_fond_dont_l_en_tete_grit_manque_ou_deborde_bloque_le_build(project):
    worker, journal = _worker(project)
    asset = BackgroundAsset(name="sky", asset="sky.png")
    layer = BackgroundLayer(background_name="sky", bg_slot=0)
    _png(project.background_images_dir / "sky.png", size=(64, 64))
    project.active_scene.background_layers.append(layer)
    layers = [(asset, layer)]

    assert worker._check_bg_tile_budget(project, layers) is False
    assert journal.says("error", "not found/unreadable")

    project.grit_out_dir.mkdir(parents=True, exist_ok=True)
    (project.grit_out_dir / f"{grit_conversion.bg_layer_sym('sky', 0)}.h").write_text(
        f"extern const unsigned int {grit_conversion.bg_layer_sym('sky', 0)}TilesLen 999999;\n", encoding="utf-8")
    assert worker._check_bg_tile_budget(project, layers) is False
    assert journal.says("error", "tiles generated")


def test_un_fond_compresse_qui_depasse_son_budget_bloque_le_build(project, monkeypatch):
    from codegen import bg_anim
    worker, journal = _worker(project)
    project.backgrounds.append(BackgroundAsset(name="sky", asset="sky.png", tileset=["0" * 64] * 4))
    project.active_scene.background_layers.append(BackgroundLayer(background_name="sky", bg_slot=0))
    monkeypatch.setattr(bg_anim, "layer_tile_count", lambda *_args: 40)
    monkeypatch.setattr(worker, "_scene_tile_budgets", lambda _p: {("sky", 0): 10})
    assert worker._check_encoded_tile_budget(project) is False
    assert journal.says("error", "36 for the animated backgrounds placed on it")


# ── lua_compiler : un avertissement du générateur nomme son script ────────


@pytest.mark.slow
def test_un_avertissement_du_generateur_nomme_le_script_de_chaque_famille(tmp_path, monkeypatch):
    """Acteur, prefab, scène, caméra : quatre boucles émettent les avertissements du générateur,
    chacune doit citer SON fichier."""
    from codegen import BuildWorker
    from codegen.runtime_codegen import lua_compiler
    from core.models.camera import Camera
    from core.models.components import ScriptComponent
    from core.models.scene import Actor, Prefab
    from core.toolchain import Toolchain

    real = lua_compiler.lua_generate

    def with_warning(*args, **kwargs):
        code, warnings, size = real(*args, **kwargs)
        return code, [*warnings, "generator says hello"], size

    monkeypatch.setattr(lua_compiler, "lua_generate", with_warning)

    project = Project.create(tmp_path / "Game", "Game")
    project.scripts_dir.mkdir(parents=True, exist_ok=True)
    body = "function on_update()\nend\n"
    for name in ("Hit", "Bullet", "Level", "Cam"):
        (project.scripts_dir / f"{name}.lua").write_text(body, encoding="utf-8")
    scene = project.scenes[0]
    actor = Actor(name="A")
    actor.components = [ScriptComponent(script="assets/scripts/Hit.lua")]
    scene.actors.append(actor)
    prefab = Prefab(name="Bullet")
    prefab.actor.components = [ScriptComponent(script="assets/scripts/Bullet.lua")]
    project.prefabs.append(prefab)
    scene.prefab_pools = {"Bullet": 1}
    scene.script = "assets/scripts/Level.lua"
    scene.cameras.append(Camera(name="Cam", script="assets/scripts/Cam.lua"))
    project.save()

    worker = BuildWorker(Project.open(project.root), Toolchain())
    worker._step_make = lambda _p: True
    worker._step_launch_mgba = lambda _p: True
    lines = []
    worker.on("diagnostic", lambda d: lines.append(d.console_line()))
    worker.run()

    said = [line for line in lines if "generator says hello" in line]
    for script in ("Hit.lua", "Bullet.lua", "Level.lua", "Cam.lua"):
        assert any(script in line for line in said), (script, said)


# ── Générateurs de tables et de code d'interface ──────────────────────────


def _warned(journal: Journal, fragment: str) -> bool:
    return journal.says("warning", fragment)


def _ui_scene(project, anchor=None, anchor_actor="", *elements):
    """Un layout `hud` posé sur la scène active ; `anchor` ancre le layout (écran par défaut)."""
    from core.models.ui_region import InterfaceNode, UILayout
    kwargs = {"anchor": anchor} if anchor else {}
    layout = UILayout(name="hud", anchor_actor=anchor_actor, **kwargs)
    layout.elements.extend(elements)
    project.ui_layouts.append(layout)
    node = InterfaceNode(layout_name="hud", anchor=anchor or "screen", anchor_actor=anchor_actor)
    project.active_scene.ui_layouts.append(node)
    return layout


def test_un_texte_ancre_sur_un_acteur_ne_le_suivra_pas(project):
    from codegen.runtime_codegen import gen_text
    from core.models.ui_region import ANCHOR_ACTOR, UIText
    text = project.new_text(content="Hi")
    _ui_scene(project, ANCHOR_ACTOR, "Hero", UIText(name="title", text_key=text.key))
    journal = Journal()
    gen_text.gen_ui_texts(project, project.active_scene, 1, journal)
    assert _warned(journal, "will not follow the actor")


def test_une_image_sans_banque_libre_avertit_et_retombe_sur_la_banque_zero(project, monkeypatch):
    from codegen import palette_alloc
    from codegen.runtime_codegen import main_gen
    from core.models.ui_region import UIImage

    class NoBank:
        def bank_index(self, *_args):
            return None

    monkeypatch.setattr(palette_alloc, "scene_bank_layout", lambda *_args: NoBank())
    scene = project.active_scene
    scene._ui_images = [{"index": 0, "sprite": SpriteAsset(name="Hero", asset="hero.png"),
                         "bg": False, "el": UIImage(name="icon", sprite_name="Hero")}]
    journal = Journal()
    main_gen._gen_ui_images(project, scene, 0, {}, journal)
    assert _warned(journal, "no free bank for the palette")


def test_un_script_qui_ne_se_parse_pas_est_une_erreur_nommee(tmp_path):
    from codegen.runtime_codegen import lua_compiler
    script = tmp_path / "Broken.lua"
    script.write_text("function on_update(\n", encoding="utf-8")
    journal = Journal()
    ast, ok = lua_compiler._compile_script(script, None, journal, owner="prefab Ball")
    assert ast is None and ok is False
    assert any(d.file == "Broken.lua" and d.actor == "prefab Ball" for d in journal.diagnostics())


# ── main_gen : la parenté et l'affine ─────────────────────────────────────


def _scene_data(project, *actors):
    scene = project.active_scene
    scene.actors = list(actors)
    return [{"scene": scene, "bg_pairs": [], "scene_actors": [(a, None) for a in actors], "extra_sprites": [], "prefab_sprites": []}]


def test_un_parent_inconnu_bloque_la_generation_du_main(project):
    from codegen.runtime_codegen import main_gen
    child = Actor(name="Child", parent="Ghost")
    journal = Journal()
    assert main_gen.generate_main(project, _scene_data(project, child), None, [], [], journal) is False
    assert journal.says("error", "Ghost")


def test_un_enfant_sans_slot_affine_sous_un_parent_qui_tourne_avertit(project):
    from codegen.runtime_codegen import main_gen
    from core.models.components import SpriteComponent
    parent = Actor(name="Parent")
    parent.components = [SpriteComponent(sprite_name="Hero", affine_transform=True)]
    child = Actor(name="Child", parent="Parent", rotation=45)
    child.components = [SpriteComponent(sprite_name="Hero")]
    journal = Journal()
    main_gen.generate_main(project, _scene_data(project, parent, child), None, [], [], journal)
    assert journal.says("warning", "has no affine slot")
