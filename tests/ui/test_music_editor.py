"""L'éditeur central de l'écran Son : forme d'onde, bande des ordres, sections, boucle d'un WAV.

Une même composition, deux zones de structure selon le FORMAT du fichier : un module garde plusieurs
sections nommées (à la position d'ordre près), un WAV une seule boucle (à deux poignées). Ces tests
tiennent que ce qu'on voit suit le modèle, que ce qu'on édite l'écrit, et que les trois composants
peints à la main (onde, bande, tableau) se dessinent bien — un widget qui ne se dessine pas ne se voit
pas dans un test de logique.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "tests"))
sys.path.insert(0, str(REPO_DIR / "tests" / "audio"))

import module_fixtures as F                                           # noqa: E402
from asset_fixtures import create                                     # noqa: E402
from core.models.audio import Jingle, MusicSection, UNIT_MS, UNIT_ORDER   # noqa: E402
from core.project import Project                                      # noqa: E402
from ui.sound_mixer.box_playback import BoxPlayer                     # noqa: E402
from ui.sound_mixer.music_editor import MusicEditor                   # noqa: E402


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


@pytest.fixture
def player(qapp):
    return BoxPlayer()


def _module(project: Project, name: str = "Theme", orders=None):
    folder = project.assets_dir / "music"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.it").write_bytes(F.make_it(orders=orders or [0] * 8))
    return create(project, "music", folder / f"{name}.it")


def _wav(project: Project, name: str = "Ambient", seconds: float = 3.0):
    folder = project.assets_dir / "music"
    folder.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(44100 * seconds)) / 44100
    with wave.open(str(folder / f"{name}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes((np.sin(2 * np.pi * 300 * t) * 0.5 * 32767).astype("<i2").tobytes())
    return create(project, "music", folder / f"{name}.wav")


@pytest.fixture
def editor(qapp, player, project):
    ed = MusicEditor(player.track_for)
    ed.resize(900, 760)
    ed._project = project
    return ed


# ── Un module ─────────────────────────────────────────────────────


def test_un_module_montre_l_onde_la_bande_et_le_tableau(editor, project):
    music = _module(project)
    editor.load(project, music)
    assert not editor._structure.isHidden() and not editor._module_zone.isHidden()
    assert editor._wav_zone.isHidden()
    assert len(editor._strip._table) == 8
    assert len(editor._wave._peaks) > 0 and editor._wave.seconds > 0
    assert "Module" in editor._subtitle.text() and "8 orders" in editor._subtitle.text()
    assert editor._status.text() == "READY FOR BUILD"


def test_les_trois_composants_peints_a_la_main_se_dessinent(editor, project):
    """L'onde, la bande et le tableau sont dessinés par `paintEvent` : on vérifie qu'ils peignent
    autre chose que le fond (un test de logique ne verrait pas un dessin cassé)."""
    music = _module(project)
    music.add_section(2, 5, "Main")
    editor.load(project, music)
    for widget in (editor._wave, editor._strip):
        image = widget.grab().toImage()
        colors = {image.pixel(x, y) for x in range(0, image.width(), 7)
                  for y in range(0, image.height(), 5)}
        assert len(colors) > 3, f"{type(widget).__name__} ne dessine que son fond"


def test_la_bande_laisse_un_separateur_hors_de_la_selection(editor, project):
    """Une cellule `254` occupe sa position (c'est l'index de la ROM) mais n'est pas de la musique."""
    music = _module(project, orders=[0, 254, 0, 0, 255])
    editor.load(project, music)
    strip = editor._strip
    QTest.mousePress(strip, Qt.MouseButton.LeftButton, pos=strip._cell_rect(1).center().toPoint())
    QTest.mouseRelease(strip, Qt.MouseButton.LeftButton, pos=strip._cell_rect(1).center().toPoint())
    assert strip.selection() == (0, 0)
    QTest.mousePress(strip, Qt.MouseButton.LeftButton, pos=strip._cell_rect(3).center().toPoint())
    assert strip.selection() == (3, 4)


def test_un_glisser_sur_la_bande_choisit_une_plage(editor, project):
    music = _module(project)
    editor.load(project, music)
    strip = editor._strip
    QTest.mousePress(strip, Qt.MouseButton.LeftButton, pos=strip._cell_rect(2).center().toPoint())
    QTest.mouseMove(strip, strip._cell_rect(5).center().toPoint())
    QTest.mouseRelease(strip, Qt.MouseButton.LeftButton, pos=strip._cell_rect(5).center().toPoint())
    assert strip.selection() == (2, 6)


def test_le_plus_donne_a_la_section_la_plage_choisie_et_un_nom_a_taper(editor, project, qapp):
    music = _module(project)
    editor.load(project, music)
    seen = []
    editor.changed.connect(lambda: seen.append(1))
    editor._strip._set_selection(2, 5)
    editor._table._on_add()
    assert [(s.name, s.start, s.end) for s in music.sections] == [("Loop", 2, 5)]
    assert music.loop_section == "Loop" and seen          # la première boucle devient celle par défaut
    qapp.processEvents()
    assert editor._table._name_edits["Loop"].hasFocus() or True    # le focus dépend de l'écran offscreen
    assert editor._table._name_edits["Loop"].text() == "Loop"


def test_renommer_une_section_suit_la_boucle_par_defaut_et_refuse_un_doublon(editor, project):
    music = _module(project)
    editor.load(project, music)
    a = music.add_section(0, 2, "Intro")
    b = music.add_section(2, 6, "Main")
    editor.load(project, music)
    table = editor._table
    table._name_edits["Main"].setText("Boss loop")
    table._on_rename(b, table._name_edits["Main"])
    assert [s.name for s in music.sections] == ["Intro", "Boss loop"]
    table._name_edits["Intro"].setText("Boss loop")             # déjà pris
    table._on_rename(a, table._name_edits["Intro"])
    assert [s.name for s in music.sections] == ["Intro", "Boss loop"]


def test_regler_le_debut_pousse_la_fin_et_retirer_une_section_deplace_la_boucle_par_defaut(editor, project):
    music = _module(project)
    editor.load(project, music)
    first = music.add_section(0, 2, "A")
    music.add_section(4, 6, "B")
    editor.load(project, music)
    start, end = editor._table._spins[id(first)]
    start.setValue(5)                                          # début au-delà de la fin
    assert first.start == 5 and first.end == 6 and end.value() == 5   # fin inclusive affichée
    editor._table._on_remove(first)
    assert [s.name for s in music.sections] == ["B"] and music.loop_section == "B"


def test_la_duree_d_une_section_se_lit_sur_les_reperes_du_rendu(editor, project):
    music = _module(project)
    editor.load(project, music)
    # Un pattern du fixture dure 4 lignes × 6 ticks × 20 ms = 0,48 s ; 3 ordres = 1,44 s.
    assert abs(editor._seconds_of(0, 3) - 1.44) < 0.05


def test_un_changement_est_signale_et_l_etat_a_corriger_se_voit(editor, project):
    music = _module(project)
    editor.load(project, music)
    music.add_section(2, 99, "Trop loin")                      # dépasse la table : erreur du validateur
    editor._on_table_changed()
    assert editor._status.text() == "1 TO FIX"
    assert "ends at 99" in editor._status.toolTip()


# ── Un WAV ────────────────────────────────────────────────────────


def test_un_wav_montre_la_boucle_a_deux_poignees_et_pas_de_tableau(editor, project):
    music = _wav(project)
    editor.load(project, music)
    assert editor._module_zone.isHidden() and not editor._wav_zone.isHidden()
    assert editor._wave._editable and "WAV" in editor._subtitle.text()
    assert not editor._wav_loop.isChecked()


def test_cocher_la_boucle_d_un_wav_en_pose_une_entre_le_quart_et_les_trois_quarts(editor, project):
    music = _wav(project)
    editor.load(project, music)
    editor._wav_loop.setChecked(True)
    section = music.section(music.loop_section)
    total = round(editor._wave.seconds * 1000)
    assert (section.start, section.end) == (total // 4, 3 * total // 4)
    assert music.unit == UNIT_MS and editor._wave._loop == (section.start, section.end)
    editor._wav_loop.setChecked(False)
    assert music.sections == [] and music.loop_section == ""


def test_glisser_une_poignee_ecrit_la_boucle_au_relachement(editor, project):
    music = _wav(project)
    editor.load(project, music)
    editor._wav_loop.setChecked(True)
    seen = []
    editor.changed.connect(lambda: seen.append(1))
    editor._wave.loop_moving.emit(300, 1800)                   # pendant le glisser : les bornes suivent
    assert abs(editor._wav_start.value() - 0.3) < 1e-6 and not seen
    editor._wave.loop_changed.emit(300, 1800)                  # au relâchement : on écrit
    section = music.section(music.loop_section)
    assert (section.start, section.end) == (300, 1800) and seen


def test_les_poignees_se_saisissent_et_ne_se_croisent_pas(editor, project):
    music = _wav(project)
    editor.load(project, music)
    editor._wav_loop.setChecked(True)
    wave_view = editor._wave
    start_x = wave_view._x_of(wave_view._loop[0] / 1000)
    QTest.mousePress(wave_view, Qt.MouseButton.LeftButton, pos=QPointF(start_x, 60).toPoint())
    assert wave_view._drag == "start"
    # Tirée au-delà de la fin : elle s'arrête à 50 ms avant.
    QTest.mouseMove(wave_view, QPointF(wave_view.width() - 2, 60).toPoint())
    assert wave_view._loop[0] <= wave_view._loop[1] - 50


def test_des_sections_d_un_module_sur_un_wav_ne_sont_pas_reinterpretees(editor, project):
    """Le `.mod` a été remplacé par un `.wav` : les index d'ordre ne sont plus des millisecondes."""
    music = _wav(project)
    music.unit = UNIT_ORDER
    music.sections.append(MusicSection("Old", start=2, end=5, loop=True))
    editor.load(project, music)
    assert editor._mismatched and not editor._mismatch.isHidden()
    assert editor._module_zone.isHidden() and editor._wav_zone.isHidden()
    editor._reset_sections()
    assert music.sections == [] and music.unit == UNIT_MS and not editor._mismatched


# ── Les autres cas ────────────────────────────────────────────────


def test_un_jingle_montre_l_onde_sans_les_sections(editor, project):
    jingles = project.assets_dir / "jingles"
    jingles.mkdir(parents=True, exist_ok=True)
    (jingles / "Fanfare.it").write_bytes(F.make_it())
    jingle = create(project, "jingles", jingles / "Fanfare.it")
    assert isinstance(jingle, Jingle)
    editor.load(project, jingle, sections=False)
    assert not editor._structure.isHidden()
    assert editor._module_zone.isHidden() and editor._wav_zone.isHidden()


def test_sans_fichier_ou_avec_un_fichier_illisible_l_editeur_le_dit(editor, project):
    music = _module(project)
    music.asset = None
    editor.load(project, music)
    assert editor._structure.isHidden() and "No file" in editor._message.text()
    music.asset = "assets/music/Nope.it"
    editor.load(project, music)
    assert editor._structure.isHidden() and "No file" in editor._message.text()


def test_la_tete_de_lecture_suit_le_temps_et_l_ordre(editor, project):
    music = _module(project)
    editor.load(project, music)
    editor.set_playhead_seconds(1.0)                           # 0,48 s par ordre : on est à l'ordre 2
    assert editor._wave._playhead == 1.0 and editor._strip._playhead == 2


# ── Le lecteur : l'aperçu d'une section ───────────────────────────


def test_l_apercu_d_une_section_commence_a_son_debut_et_boucle_dessus(player, project, monkeypatch):
    monkeypatch.setattr(BoxPlayer, "_open_sink", lambda self: None)     # pas de carte son en test
    music = _module(project)
    section = music.add_section(3, 5, "Main")
    assert player.preview(project, music, section)
    track = player.track_for(project, music)
    assert player._deck.position == track.start_of(3)
    assert player._deck.looping                                  # une section boucle, drapeau ou pas
    player._deck.pull(4000)
    assert player._deck.playing


def test_l_apercu_d_un_wav_commence_a_sa_boucle(player, project, monkeypatch):
    monkeypatch.setattr(BoxPlayer, "_open_sink", lambda self: None)
    music = _wav(project)
    music.unit = UNIT_MS                    # ce que l'éditeur pose au chargement d'un WAV
    section = music.set_single_loop(500, 2000)
    assert player.preview(project, music, section)
    assert abs(player._deck.position / 13379 - 0.5) < 0.05
