"""Les diagnostics des outils de build sont déclenchés au moins une fois (chantier « La fiabilité du
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


def test_une_feuille_non_indexee_est_refusee_au_remplissage(tmp_path):
    journal = Journal()
    src = _png(tmp_path / "rgb.png", "RGB")
    assert grit_conversion.pad_sprite_png_indexed(src, 16, 16, tmp_path, journal) is None
    assert journal.says("error", "not an indexed PNG")


def test_un_remplissage_qui_plante_est_un_diagnostic_pas_une_trace(tmp_path):
    journal = Journal()
    assert grit_conversion.pad_sprite_png_indexed(tmp_path / "absent.png", 16, 16, tmp_path, journal) is None
    assert journal.says("error", "indexed padding error")


def test_une_feuille_de_sprite_non_indexee_est_refusee(tmp_path):
    journal = Journal()
    src = _png(tmp_path / "rgb.png", "RGB")
    assert grit_conversion.build_sprite_sheet_indexed(src, SpriteAsset(name="Hero"), tmp_path, journal) is None
    assert journal.says("error", "not an indexed PNG")


def test_une_reconstruction_de_feuille_qui_plante_est_un_diagnostic(tmp_path):
    journal = Journal()
    assert grit_conversion.build_sprite_sheet_indexed(tmp_path / "absent.png", SpriteAsset(name="Hero"),
                                                      tmp_path, journal) is None
    assert journal.says("error", "indexed reconstruction error")


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


def test_une_image_de_fond_manquante_arrete_la_conversion(project):
    journal = Journal()
    asset, layer = _background(project, png=False)
    conversion = grit_conversion.GritBackground(Path("grit.exe"), journal, _failing_run_cmd)
    assert conversion.run(project, [(asset, layer, None, None)]) is False
    assert journal.says("error", "image missing: sky")


def test_une_quantification_de_fond_impossible_est_un_diagnostic(project, monkeypatch):
    def refuse(*_args):
        raise ValueError("palette too small")

    monkeypatch.setattr(grit_conversion, "quantize_asset", refuse)
    journal = Journal()
    asset, layer = _background(project)
    conversion = grit_conversion.GritBackground(Path("grit.exe"), journal, _failing_run_cmd)
    assert conversion.run(project, [(asset, layer, [0x7FFF] * 16, 1)]) is False
    assert journal.says("error", "palette too small")


# ── grit : sprites ────────────────────────────────────────────────────────


def test_grit_introuvable_arrete_la_conversion_des_sprites(project):
    journal = Journal()
    conversion = grit_conversion.GritSprites(None, journal, _failing_run_cmd)
    assert conversion.run(project, [(None, SpriteAsset(name="Hero", asset="hero.png"), None)]) is False
    assert journal.says("error", "not found")


def test_un_sprite_dont_le_fichier_manque_arrete_la_conversion(project):
    journal = Journal()
    conversion = grit_conversion.GritSprites(Path("grit.exe"), journal, _failing_run_cmd)
    sprite = SpriteAsset(name="Hero", asset="assets/sprites/gone.png")
    assert conversion.run(project, [(None, sprite, None)]) is False
    assert journal.says("error", "asset missing")


def test_une_quantification_de_sprite_impossible_est_un_diagnostic(project, monkeypatch):
    from core.models import gba_color

    def refuse(*_args):
        raise ValueError("palette too small")

    monkeypatch.setattr(grit_conversion, "quantize_asset", refuse)
    monkeypatch.setattr(gba_color, "render_indexed",
                        lambda *_args: __import__("PIL.Image", fromlist=["new"]).new("P", (16, 16)))
    monkeypatch.setattr(grit_conversion, "build_sprite_sheet_indexed",
                        lambda src, *_args: src)
    journal = Journal()
    _png(project.root / "assets" / "sprites" / "hero.png")
    sprite = SpriteAsset(name="Hero", asset="assets/sprites/hero.png")
    conversion = grit_conversion.GritSprites(Path("grit.exe"), journal, _failing_run_cmd)
    assert conversion.run(project, [(None, sprite, [0x7FFF] * 16)]) is False
    assert journal.says("error", "palette too small")


# ── mmutil ────────────────────────────────────────────────────────────────


def _sounds(*names: str) -> dict:
    return {"sfx": [(SimpleNamespace(name=n), Path(f"{n}.wav")) for n in names], "music": [], "skipped": []}


def test_un_soundbank_illisible_arrete_le_controle_des_numeros(tmp_path):
    journal = Journal()
    audio = grit_conversion.MmutilAudio("mmutil", "bin2s", journal, _failing_run_cmd)
    assert audio._check_ids(tmp_path / "absent.h", _sounds("Boom")) is False
    assert journal.says("error", "soundbank.h unreadable")


def test_un_soundbank_aux_numeros_decales_est_une_erreur(tmp_path):
    journal = Journal()
    header = tmp_path / "soundbank.h"
    header.write_text("#define SFX_BOOM 3\n", encoding="utf-8")
    audio = grit_conversion.MmutilAudio("mmutil", "bin2s", journal, _failing_run_cmd)
    assert audio._check_ids(header, _sounds("Boom", "Missing")) is False
    assert journal.says("error", "SFX_BOOM is 3, expected 0")
    assert journal.says("error", "SFX_MISSING absent de soundbank.h")
    assert journal.says("error", "build interrupted")


def test_mmutil_introuvable_saute_l_audio_avec_un_avertissement(project):
    journal = Journal()
    audio = grit_conversion.MmutilAudio(None, None, journal, _failing_run_cmd)
    assert audio.run(project, _sounds("Boom")) is True
    assert journal.says("warning", "audio skipped")


def test_un_reechantillonnage_qui_plante_est_ignore_avec_un_avertissement(project, monkeypatch):
    from codegen import sfx_encode

    def refuse(*_args):
        raise RuntimeError("no encoder")

    monkeypatch.setattr(sfx_encode, "encode_sfx_for_build", refuse)
    journal = Journal()
    audio = grit_conversion.MmutilAudio(Path("mmutil.exe"), None, journal, _failing_run_cmd)
    audio.run(project, {"sfx": [], "music": [], "skipped": []})
    assert journal.says("warning", "resampling ignored: no encoder")


def _mmutil_succeeds(project, journal, bin2s):
    """Un mmutil factice qui « réussit » en déposant soundbank.bin / .h dans build/."""
    project.build_dir.mkdir(parents=True, exist_ok=True)

    def run_cmd(*_args, **_kwargs) -> bool:
        (project.build_dir / "soundbank.bin").write_bytes(b"\0")
        (project.build_dir / "soundbank.h").write_text("#define SFX_BOOM 0\n", encoding="utf-8")
        return True

    wave = project.root / "boom.wav"
    wave.write_bytes(b"x")
    sounds = {"sfx": [(SimpleNamespace(name="Boom", to_dict=lambda: {}), wave)], "music": [], "skipped": []}
    return grit_conversion.MmutilAudio(Path("mmutil.exe"), bin2s, journal, run_cmd), sounds


def test_bin2s_introuvable_est_un_avertissement(project, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise FileNotFoundError("bin2s.exe")

    monkeypatch.setattr(grit_conversion.subprocess, "run", refuse)
    journal = Journal()
    audio, sounds = _mmutil_succeeds(project, journal, Path("bin2s.exe"))
    audio.run(project, sounds)
    assert journal.says("warning", "not found: bin2s.exe")


def test_sans_bin2s_la_soundbank_n_est_pas_liee(project):
    journal = Journal()
    audio, sounds = _mmutil_succeeds(project, journal, None)
    audio.run(project, sounds)
    assert journal.says("warning", "soundbank not linked")


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


def test_un_chemin_trop_long_est_refuse_avant_la_validation(project, monkeypatch):
    from codegen import rom_build
    monkeypatch.setattr(rom_build, "path_too_long_message", lambda _p: "path is too long")
    worker, journal = _worker(project)
    worker.run()
    assert journal.says("error", "path is too long"), [(e, str(a)[:200]) for e, a in journal.events]


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


def test_un_rapport_de_poids_qui_plante_ou_deborde_avertit(project, monkeypatch):
    from codegen import rom_report
    worker, journal = _worker(project)

    def refuse(*_args, **_kwargs):
        raise RuntimeError("nm is missing")

    monkeypatch.setattr(rom_report, "measure", refuse)
    worker._step_rom_report(project, None)
    assert journal.says("warning", "report unavailable: nm is missing")

    monkeypatch.setattr(rom_report, "measure", lambda *_a, **_k: SimpleNamespace(over_capacity=True))
    monkeypatch.setattr(rom_report, "format_report", lambda _report: [])
    worker._step_rom_report(project, None)
    assert journal.says("warning", "exceeds the declared cartridge capacity")


def test_mgba_ne_se_lance_pas_sans_rom_ni_emulateur(project):
    worker, journal = _worker(project, FakeToolchain(mgba=None))
    assert worker._step_launch_mgba(project) is False
    assert journal.says("error", "ROM missing")

    project.rom_path.parent.mkdir(parents=True, exist_ok=True)
    project.rom_path.write_bytes(b"rom")
    assert worker._step_launch_mgba(project) is False
    assert journal.says("error", "not found")


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


def test_un_texte_d_interface_dont_la_cle_manque_n_ecrit_rien(project):
    from codegen.runtime_codegen import gen_text
    from core.models.ui_region import UIText
    _ui_scene(project, None, "", UIText(name="title", text_key="ghost"))
    journal = Journal()
    gen_text.gen_ui_texts(project, project.active_scene, 1, journal)
    assert _warned(journal, "not found in the table")


def test_un_texte_sans_calque_de_texte_ne_s_affichera_pas(project):
    from codegen.runtime_codegen import gen_text
    from core.models.ui_region import UIText
    text = project.new_text(content="Hi")
    _ui_scene(project, None, "", UIText(name="title", text_key=text.key))
    journal = Journal()
    gen_text.gen_ui_texts(project, project.active_scene, -1, journal)
    assert _warned(journal, "has no text layer")


def test_un_texte_ancre_sur_un_acteur_ne_le_suivra_pas(project):
    from codegen.runtime_codegen import gen_text
    from core.models.ui_region import ANCHOR_ACTOR, UIText
    text = project.new_text(content="Hi")
    _ui_scene(project, ANCHOR_ACTOR, "Hero", UIText(name="title", text_key=text.key))
    journal = Journal()
    gen_text.gen_ui_texts(project, project.active_scene, 1, journal)
    assert _warned(journal, "will not follow the actor")


def test_une_police_qui_ne_s_encode_pas_est_une_erreur_nommee(project, monkeypatch):
    from codegen import font_emit
    from codegen.runtime_codegen import gen_text
    from core.models.font import Font

    def refuse(*_args):
        raise RuntimeError("bad glyph table")

    monkeypatch.setattr(gen_text, "project_fonts", lambda _p: [Font(name="Broken")])
    monkeypatch.setattr(font_emit, "encode_font", refuse)
    journal = Journal()
    try:
        gen_text.fonts_and_texts_lines(project, journal)
    except Exception:       # tolerated: only the diagnostic emitted before is under test
        pass
    assert journal.says("error", "Broken: encoding failed (bad glyph table)")


def test_une_image_ancree_sur_un_acteur_introuvable_se_pose_a_l_origine(project):
    from codegen.runtime_codegen import gen_ui
    from core.models.ui_region import ANCHOR_ACTOR, UIImage
    project.sprites.append(SpriteAsset(name="Hero", asset="hero.png"))
    _ui_scene(project, ANCHOR_ACTOR, "Ghost", UIImage(name="icon", sprite_name="Hero"))
    journal = Journal()
    gen_ui.emit_ui_images_c(project, {}, {}, {}, {}, journal)
    assert _warned(journal, "placed at the screen origin")


def test_une_liste_sans_zone_de_texte_enfant_avertit(project):
    from codegen.runtime_codegen import gen_ui
    from core.models.ui_region import UIList
    _ui_scene(project, None, "", UIList(name="menu"))
    journal = Journal()
    gen_ui.emit_ui_lists_c(project, journal)
    assert _warned(journal, "no child text zone")


def test_une_zone_de_texte_ancree_sur_un_acteur_introuvable_se_pose_a_l_origine(project):
    from codegen import font_emit
    from core.models.ui_region import ANCHOR_ACTOR, UIText
    layout = _ui_scene(project, ANCHOR_ACTOR, "Ghost", UIText(name="bubble"))
    journal = Journal()
    font_emit.emit_ui_regions_c([(layout, layout.elements[0])], [], journal, {}, {}, {})
    assert _warned(journal, "placed at the screen origin")


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


def test_un_reechantillonnage_qui_echoue_est_un_avertissement_nomme(project, monkeypatch):
    import wave
    from codegen import sfx_encode
    from core.models.audio import Sfx

    folder = project.root / "assets" / "sfx"
    folder.mkdir(parents=True, exist_ok=True)
    with wave.open(str(folder / "boom.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 160)
    project.settings.sfx_sample_rate = 8000

    def refuse(*_args):
        raise RuntimeError("disk full")

    monkeypatch.setattr(sfx_encode, "resample_wav", refuse)
    journal = Journal()
    sfx = Sfx(name="Boom", asset="assets/sfx/boom.wav")
    sfx_encode.encode_sfx_for_build(project, [(sfx, folder / "boom.wav")], journal)
    assert journal.says("warning", '"Boom" not resampled: disk full')


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
