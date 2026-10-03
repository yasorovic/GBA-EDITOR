"""Le validateur contrôle TOUTES les scènes (chantier « La fiabilité du journal de build », tranche 3).

Une matrice de pannes injectées dans la démo a montré le défaut : les contrôles par scène ne
regardaient que la scène ACTIVE, alors que le build les compile toutes. Un script supprimé, un
sprite illisible ou un fond cassé dans une autre scène passait en silence, ou sortait plus tard en
« internal error ». Le message nomme désormais sa scène.
"""
from __future__ import annotations

from codegen import BuildWorker
from core.models.components import ScriptComponent, SpriteComponent
from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from core.toolchain import Toolchain
from core.validator import ValidationMessage, validate_project


def _deux_scenes(tmp_path) -> Project:
    """Deux scènes ; la première (active) est saine, la seconde porte les fautes."""
    project = Project.create(tmp_path / "Game", "Game")
    project.scenes.append(Scene(name="Level2"))
    project.scripts_dir.mkdir(parents=True, exist_ok=True)
    return project


def _verdict(project):
    project.save()
    warns, errors = validate_project(Project.open(project.root))
    return warns, errors


def test_un_script_manquant_dans_une_autre_scene_est_une_erreur_nommee(tmp_path):
    project = _deux_scenes(tmp_path)
    actor = Actor(name="Hero")
    actor.components = [ScriptComponent(script="assets/scripts/Gone.lua")]
    project.scenes[1].actors.append(actor)

    _warns, errors = _verdict(project)

    [err] = [e for e in errors if "Gone.lua" in e.message]
    assert (err.scene, err.actor) == ("Level2", "Hero")
    assert err.console_line().startswith("[error] [Level2/Hero] ")


def test_un_sprite_inconnu_dans_une_autre_scene_est_vu(tmp_path):
    project = _deux_scenes(tmp_path)
    actor = Actor(name="Hero")
    actor.components = [SpriteComponent(sprite_name="Nowhere")]
    project.scenes[1].actors.append(actor)

    warns, errors = _verdict(project)

    assert any("Nowhere" in m.message and m.scene == "Level2" for m in warns + errors)


def test_le_sprite_d_un_prefab_est_controle(tmp_path):
    project = _deux_scenes(tmp_path)
    prefab = Prefab(name="Bullet")
    prefab.actor.components = [SpriteComponent(sprite_name="Nowhere")]
    project.prefabs.append(prefab)

    warns, errors = _verdict(project)

    assert any("Nowhere" in m.message and m.actor == "Bullet" for m in warns + errors)


def test_une_scene_d_interface_sans_acteur_n_avertit_pas(tmp_path):
    """Un écran titre n'a souvent aucun acteur : un script suffit à le justifier. Une scène
    sans acteur, sans script et sans interface, elle, ne fait rien — et le dit."""
    project = _deux_scenes(tmp_path)
    (project.scripts_dir / "Title.lua").write_text("function on_start()\nend\n", encoding="utf-8")
    project.scenes[0].script = "assets/scripts/Title.lua"

    warns, _errors = _verdict(project)

    messages = [(m.scene, m.message) for m in warns if "do nothing" in m.message]
    assert messages == [("Level2", "The scene has no actor, script or interface: it will do nothing.")]


def test_une_scene_de_depart_inconnue_avertit(tmp_path):
    project = _deux_scenes(tmp_path)
    project.settings.start_scene = "Nope"

    warns, _errors = _verdict(project)

    assert any("start scene \"Nope\"" in m.message for m in warns)


# ── Trois « internal error » deviennent des diagnostics ───────────


def test_un_script_latin_1_est_dit_sans_planter_le_validateur(tmp_path):
    project = _deux_scenes(tmp_path)
    (project.scripts_dir / "Old.lua").write_bytes("-- café\nfunction on_update()\nend\n".encode("latin-1"))
    actor = Actor(name="Hero")
    actor.components = [ScriptComponent(script="assets/scripts/Old.lua")]
    project.scenes[0].actors.append(actor)

    _warns, errors = _verdict(project)

    [err] = errors
    assert err.file == "Old.lua" and "not valid UTF-8" in err.message


def test_un_dossier_build_qui_est_un_fichier_est_une_erreur_de_systeme_de_fichiers(tmp_path):
    project = _deux_scenes(tmp_path)
    project.save()
    (project.root / "build").write_text("not a directory", encoding="utf-8")

    worker = BuildWorker(Project.open(project.root), Toolchain())
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()

    assert verdict == [False]
    assert any(d.message.startswith("file system error:") for d in diagnostics)
    assert not any("internal error" in d.message for d in diagnostics)


# ── Le rendu du propriétaire ──────────────────────────────────────


def test_le_proprietaire_se_lit_scene_puis_acteur():
    assert ValidationMessage("error", "Hero", "x", scene="Level2").console_line() == \
        "[error] [Level2/Hero] x"
    assert ValidationMessage("error", "", "x", scene="Level2").console_line() == "[error] [Level2] x"
    assert ValidationMessage("error", "Hero", "x").console_line() == "[error] [Hero] x"


def test_une_police_vectorielle_n_est_pas_controlee_comme_une_image(tmp_path):
    """Une police `.ttf` / `.otf` n'a pas de planche PNG : la lire comme une image faisait refuser
    tout projet qui en portait une (régression vue sur la démo PongAdvanced)."""
    from core.models.font import Font

    project = Project.create(tmp_path / "Game", "Game")
    fonts = project.root / "assets" / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    (fonts / "vector.ttf").write_bytes(b"not an image")
    project.fonts.append(Font(name="vector", asset="assets/fonts/vector.ttf", source_format="ttf"))

    _warns, errors = _verdict(project)

    assert not [e for e in errors if "unreadable" in e.message and "vector" in e.message]


def test_une_planche_png_illisible_reste_une_erreur(tmp_path):
    from core.models.font import Font

    project = Project.create(tmp_path / "Game", "Game")
    fonts = project.root / "assets" / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    (fonts / "sheet.png").write_bytes(b"not an image")
    project.fonts.append(Font(name="sheet", asset="assets/fonts/sheet.png", source_format="png"))

    _warns, errors = _verdict(project)

    assert any("sheet.png" in e.message and "unreadable" in e.message for e in errors)
