"""Les repères d'une musique sur la bande des ordres : les poser, les déplacer, les supprimer, et ce que le projet en fait.

La bande dit OÙ (une position, un drapeau qu'on saisit), l'éditeur dit QUOI (un menu par nature de repère). Ces tests tiennent
que le geste écrit le modèle, que le disque n'est écrit qu'au lâcher, qu'un drapeau se dessine, et que ce qu'un repère cite
est gardé en ROM et signalé par le validateur quand il pointe dans le vide.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMenu

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "tests"))
sys.path.insert(0, str(REPO_DIR / "tests" / "audio"))

import module_fixtures as F                                                       # noqa: E402
from asset_fixtures import create                                                 # noqa: E402
from codegen.grit_conversion import referenced_sound_names                        # noqa: E402
from core.models.audio import CUE_JINGLE, CUE_SFX, CUE_SOUND_ACTION, UNIT_MS, UNIT_ORDER   # noqa: E402
from core.engine_emulation.module_render import GBA_MIX_RATE                      # noqa: E402
from core.project import Project                                                  # noqa: E402
from core.validator import validate_project                                       # noqa: E402
from ui.sound_mixer.box_playback import BoxPlayer                                 # noqa: E402
from ui.sound_mixer.music_editor import MusicEditor                               # noqa: E402


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


@pytest.fixture
def editor(qapp, project, monkeypatch):
    monkeypatch.setattr(QMenu, "exec", lambda self, *args: None)       # un menu modal bloquerait le test
    ed = MusicEditor(BoxPlayer().track_for)
    ed.resize(900, 760)
    ed._project = project
    return ed


def _module(project: Project, name: str = "Theme", orders=None):
    folder = project.user_library_dir / "music"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.it").write_bytes(F.make_it(orders=orders or [0] * 8))
    return create(project, "music", folder / f"{name}.it")


def _wav_file(folder: Path, name: str, seconds: float = 3.0) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(44100 * seconds)) / 44100
    with wave.open(str(folder / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes((np.sin(2 * np.pi * 300 * t) * 0.5 * 32767).astype("<i2").tobytes())
    return folder / f"{name}.wav"


def _flag_point(strip, cue) -> QPoint:
    return strip._flag_rect(cue).center().toPoint()


# ── La bande ──────────────────────────────────────────────────────


def test_un_repere_du_modele_a_son_drapeau_dans_la_voie_au_dessus_des_sections(editor, project):
    music = _module(project)
    music.add_cue(3, CUE_SFX, "Bip")
    editor.load(project, music)
    strip = editor._strip
    flag = strip._flag_rect(music.cues[0])
    assert flag.bottom() <= strip._bands_top() and flag.left() == pytest.approx(strip._x(3))
    assert not strip.grab().isNull()                                    # un widget peint à la main doit se dessiner


def test_un_clic_droit_dans_le_vide_propose_la_position_de_la_case(editor, project):
    music = _module(project)
    editor.load(project, music)
    strip, seen = editor._strip, []
    strip.cue_context_requested.connect(lambda cue, position, _where: seen.append((cue, position)))
    QTest.mouseClick(strip, Qt.MouseButton.RightButton, pos=QPoint(int(strip._cell_rect(5).center().x()), 9))
    assert seen == [(None, 5)]


def test_un_clic_droit_sur_un_separateur_ne_propose_rien(editor, project):
    music = _module(project, orders=[0, 0, 254, 0, 255])
    editor.load(project, music)
    strip, seen = editor._strip, []
    strip.cue_context_requested.connect(lambda *args: seen.append(args))
    QTest.mouseClick(strip, Qt.MouseButton.RightButton, pos=QPoint(int(strip._cell_rect(2).center().x()), 9))
    assert seen == []


def test_un_clic_droit_sur_un_drapeau_le_designe(editor, project):
    music = _module(project)
    cue = music.add_cue(4, CUE_SFX, "Bip")
    editor.load(project, music)
    strip, seen = editor._strip, []
    strip.cue_context_requested.connect(lambda c, position, _where: seen.append((c, position)))
    QTest.mouseClick(strip, Qt.MouseButton.RightButton, pos=_flag_point(strip, cue))
    assert seen == [(cue, 4)]


def test_glisser_un_drapeau_le_deplace_et_le_disque_n_ecrit_qu_au_lacher(editor, project):
    music = _module(project)
    cue = music.add_cue(2, CUE_SFX, "Bip")
    editor.load(project, music)
    strip, saved = editor._strip, []
    editor.changed.connect(lambda: saved.append(1))
    start = _flag_point(strip, cue)
    QTest.mousePress(strip, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(strip, QPoint(int(strip._cell_rect(6).center().x()), start.y()))
    assert cue.position == 6 and not saved                              # le modèle suit, le disque attend
    QTest.mouseRelease(strip, Qt.MouseButton.LeftButton, pos=QPoint(int(strip._cell_rect(6).center().x()), start.y()))
    assert saved == [1]


def test_un_drapeau_ne_se_pose_pas_sur_un_separateur(editor, project):
    music = _module(project, orders=[0, 0, 254, 0, 255])
    cue = music.add_cue(1, CUE_SFX, "Bip")
    editor.load(project, music)
    strip = editor._strip
    start = _flag_point(strip, cue)
    QTest.mousePress(strip, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(strip, QPoint(int(strip._cell_rect(2).center().x()), start.y()))
    QTest.mouseRelease(strip, Qt.MouseButton.LeftButton)
    assert cue.position == 1


def test_choisir_une_cible_pose_ou_change_un_repere_et_le_supprimer_l_efface(editor, project):
    music = _module(project)
    editor.load(project, music)
    saved = []
    editor.changed.connect(lambda: saved.append(1))
    editor._set_cue(None, 3, CUE_SOUND_ACTION, "pas")
    cue = music.cues[0]
    assert (cue.position, cue.kind, cue.target) == (3, CUE_SOUND_ACTION, "pas")
    editor._set_cue(cue, 3, CUE_JINGLE, "Fanfare")
    assert (cue.kind, cue.target) == (CUE_JINGLE, "Fanfare") and len(music.cues) == 1
    editor._delete_cue(cue)
    assert music.cues == [] and len(saved) == 3
    assert editor._strip._cues == []


def test_les_reperes_d_un_wav_se_posent_a_la_milliseconde(editor, project):
    path = _wav_file(project.user_library_dir / "music", "Ambient")
    music = create(project, "music", path)
    editor.load(project, music)
    strip = editor._strip
    x = int(strip._x(1500))
    seen = []
    strip.cue_context_requested.connect(lambda cue, position, _where: seen.append((cue, position)))
    QTest.mouseClick(strip, Qt.MouseButton.RightButton, pos=QPoint(x, 9))
    assert seen[0][0] is None and abs(seen[0][1] - 1500) < 40
    editor._set_cue(None, seen[0][1], CUE_SFX, "Bip")
    assert music.unit == UNIT_MS and music.cues[0].position == seen[0][1]


def test_des_reperes_ecrits_pour_un_autre_type_de_fichier_ne_se_reinterpretent_pas(editor, project):
    music = _module(project)
    music.unit = UNIT_MS
    music.add_cue(1000, CUE_SFX, "Bip")
    editor.load(project, music)
    assert editor._mismatched
    editor._reset_sections()
    assert music.cues == [] and music.unit == UNIT_ORDER


# ── Ce que le projet en fait ──────────────────────────────────────


def test_un_effet_cite_par_un_repere_est_garde_en_rom(project):
    sfx = create(project, "sfx", _wav_file(project.user_library_dir / "sfx", "Bip", 0.3))
    unused = create(project, "sfx", _wav_file(project.user_library_dir / "sfx", "Muet", 0.3))
    music = _module(project)
    music.add_cue(0, CUE_SFX, sfx.name)
    sfx_names, _music_names = referenced_sound_names(project)
    assert sfx.name in sfx_names and unused.name not in sfx_names


def test_un_repere_vers_un_nom_qui_n_existe_pas_est_un_avertissement(project):
    music = _module(project)
    music.add_cue(0, CUE_SFX, "Fantome")
    music.add_cue(2, CUE_SOUND_ACTION, "inconnue")
    warnings, errors = validate_project(project)
    said = [str(m) for m in warnings]
    assert any("Fantome" in m and "cue at 0" in m for m in said)
    assert any("inconnue" in m and "cue at 2" in m for m in said)
    assert not any("cue" in str(m) for m in errors)


def test_un_jingle_module_n_a_ni_voie_des_reperes_ni_sections(editor, project):
    """Un jingle ne montre plus la voie des repères (elle ne servait pas) : seulement l'onde et, dessous, sa barre de découpe."""
    folder = project.user_library_dir / "jingles"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Fanfare.it").write_bytes(F.make_it(orders=[0]))
    jingle = create(project, "jingles", folder / "Fanfare.it")
    editor.load(project, jingle, sections=False)
    assert editor._strip_zone.isHidden() and editor.sections_panel.isHidden()
    assert not editor._trim_zone.isHidden()


def test_la_tete_de_lecture_traverse_la_structure_et_avance_dans_sa_case(editor, project):
    music = _module(project)
    editor.load(project, music)
    track = editor._track
    seconds = (track.marks[3] + (track.marks[4] - track.marks[3]) // 2) / GBA_MIX_RATE if 4 in track.marks else None
    if seconds is None:
        pytest.skip("le rendu n'a pas de repère d'ordre 4")
    order, fraction = editor._playhead_in_order(seconds)
    assert order == 3 and fraction == pytest.approx(0.5, abs=0.02)
    editor.set_playhead_seconds(seconds)
    strip = editor._strip
    assert strip._playhead == 3 and strip._playhead_fraction == pytest.approx(fraction)
    assert not strip.grab().isNull()
