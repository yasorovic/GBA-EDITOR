"""Les diagnostics du validateur que la suite ne déclenchait jamais : boîte de collision dégénérée ou à sens unique sur un
capteur, relations physiques cassées entre composants d'un même acteur, zone de texte qui déborde de son cadre, et mGBA absent.

Chaque test construit la situation fautive et lit ce que le contrôle en dit (cf. `test_validator_diagnostics.py`)."""
from __future__ import annotations

import pytest

from codegen.runtime_codegen import gen_text
from codegen.rom_build import BuildWorker
from core import validator
from core.models.components import (
    COLLISION_RESPONSE_BLOCK, COLLISION_RESPONSE_SENSOR, CollisionShapeComponent, PhysicMaterialComponent,
    PhysicsBodyComponent)
from core.models.scene import Actor
from core.models.ui_region import FILL_NINE, InterfaceNode, UIContainer, UILayout, UIText
from core.project import Project
from core.toolchain import Toolchain
from core.validator import ValidationContext


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


def _found(project: Project, check, *args) -> list[tuple[str, str]]:
    ctx = ValidationContext(project)
    check(ctx, *args)
    return [(m.level, m.message) for m in ctx._msgs]


def _says(found, level: str, fragment: str) -> bool:
    return any(lvl == level and fragment in msg for lvl, msg in found)


def test_une_boite_de_collision_sans_largeur_ou_hauteur_est_une_erreur(project):
    actor = Actor(name="Hero")
    box = CollisionShapeComponent(tag="body", w=0, h=8)
    assert _says(_found(project, validator._check_collision, actor, box), "error", "zero width or height")


def test_une_face_a_sens_unique_sur_un_capteur_avertit(project):
    actor = Actor(name="Hero")
    sensor = CollisionShapeComponent(tag="floor", w=8, h=8, response=COLLISION_RESPONSE_SENSOR, one_way="up")
    block = CollisionShapeComponent(tag="floor", w=8, h=8, response=COLLISION_RESPONSE_BLOCK, one_way="up")
    assert _says(_found(project, validator._check_collision, actor, sensor), "warning", "One-way is set")
    assert _found(project, validator._check_collision, actor, block) == []


def test_un_corps_qui_cite_une_boite_absente_ou_en_double_est_une_erreur(project):
    actor = Actor(name="Hero")
    body = PhysicsBodyComponent(collider_id="hit")
    check = lambda: _found(project, validator._check_physics_body, actor, body)   # noqa: E731

    actor.components = [body]
    assert _says(check(), "error", "contains 0 matching boxes")
    actor.components = [body, CollisionShapeComponent(id="hit", tag="a", w=8, h=8)]
    assert check() == []
    actor.components.append(CollisionShapeComponent(id="hit", tag="b", w=8, h=8))
    assert _says(check(), "error", "contains 2 matching boxes")


def test_une_boite_qui_cite_un_materiau_absent_ou_en_double_est_une_erreur(project):
    actor = Actor(name="Hero")
    box = CollisionShapeComponent(id="box", tag="body", w=8, h=8, material_id="ice")
    check = lambda: _found(project, validator._check_collision_material, actor, box)   # noqa: E731

    actor.components = [box]
    assert _says(check(), "error", "contains 0 matching materials")
    actor.components = [box, PhysicMaterialComponent(id="ice")]
    assert check() == []
    actor.components.append(PhysicMaterialComponent(id="ice"))
    assert _says(check(), "error", "contains 2 matching materials")


def test_une_zone_de_texte_qui_deborde_de_son_cadre_avertit(project, monkeypatch):
    """Le fond IMAGE du conteneur est simulé : ce que le contrôle juge, c'est la zone liée ou non à ce fond."""
    layout = UILayout(name="hud")
    layout.elements.extend([
        UIContainer(name="panel", w=32, h=16, fill_kind=FILL_NINE),
        UIText(name="title", parent="panel", w=64, h=8),
    ])
    project.ui_layouts.append(layout)
    project.active_scene.ui_layouts.append(InterfaceNode(layout_name="hud"))
    monkeypatch.setattr(gen_text, "scene_image_fills", lambda _p, _scene: ([{"name": "panel"}], []))

    monkeypatch.setattr(gen_text, "scene_region_backdrops", lambda _p, _scene, _fills: [])
    found = _found(project, validator._check_text_zone_in_container)
    assert _says(found, "warning", "text zone 'title' (64x8 px) does not fit inside its container 'panel'")

    monkeypatch.setattr(gen_text, "scene_region_backdrops", lambda _p, _scene, _fills: [{"name": "title"}])
    assert _found(project, validator._check_text_zone_in_container) == []


def test_mgba_absent_est_dit_au_journal(project, monkeypatch):
    class _NoMgba(Toolchain):
        def resolve_mgba(self):
            return None

    events = []
    worker = BuildWorker(project, _NoMgba())
    worker._emit = lambda event, *args: events.append((event, args))
    project.rom_path.parent.mkdir(parents=True, exist_ok=True)
    project.rom_path.write_bytes(b"\0")

    assert worker._step_launch_mgba(project) is False
    diagnostics = [args[0] for event, args in events if event == "diagnostic"]
    assert any(d.level == "error" and "not found" in d.message for d in diagnostics)


def test_des_touches_mgba_non_ecrites_sont_un_avertissement_et_mgba_se_lance(project, monkeypatch, tmp_path):
    from codegen import rom_build

    class _WithMgba(Toolchain):
        mgba_keys = {"A": 65}

        def resolve_mgba(self):
            return tmp_path / "mgba.exe"

    def refuse(_file, _keys):
        raise OSError("disk full")

    launched = []
    monkeypatch.setattr(rom_build, "mgba_config_file", lambda _mgba: tmp_path / "config.ini")
    monkeypatch.setattr(rom_build, "write_keys", refuse)
    monkeypatch.setattr(rom_build.subprocess, "Popen", lambda cmd, **_kw: launched.append(cmd))
    monkeypatch.setattr(BuildWorker, "_mgba_proc", None)
    events = []
    worker = BuildWorker(project, _WithMgba())
    worker._emit = lambda event, *args: events.append((event, args))
    project.rom_path.parent.mkdir(parents=True, exist_ok=True)
    project.rom_path.write_bytes(b"\0")

    assert worker._step_launch_mgba(project) is True
    diagnostics = [args[0] for event, args in events if event == "diagnostic"]
    assert any(d.level == "warning" and "key bindings not written: disk full" in d.message for d in diagnostics)
    assert launched                                         # l'échec d'écriture n'empêche pas de jouer
