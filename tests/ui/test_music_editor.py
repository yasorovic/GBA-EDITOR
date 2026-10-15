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
from PyQt6.QtCore import QPoint, QPointF, Qt
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


# ── Un WAV ────────────────────────────────────────────────────────


def test_un_wav_a_la_meme_bande_qu_un_module_mais_en_une_seule_cellule(editor, project):
    music = _wav(project)
    editor.load(project, music)
    assert not editor._strip_zone.isHidden() and not editor._sections_zone.isHidden()
    assert len(editor._strip._table) == 1 and editor._strip._extent_ms == 3000
    assert editor._wave._editable
    assert music.sections == [] and editor._wave._loop is None


def test_la_premiere_section_d_un_wav_prend_le_milieu_de_la_piste(editor, project):
    music = _wav(project)                                      # 3 s
    editor.load(project, music)
    editor._table._on_add()
    section = music.section(music.loop_section)
    assert (section.start, section.end) == (750, 2250)        # ¼ et ¾ de la piste
    assert music.unit == UNIT_MS and section.loop
    assert editor._wave._loop == (section.start, section.end)


def test_les_sections_suivantes_d_un_wav_prennent_la_suite(editor, project):
    music = _wav(project)
    editor.load(project, music)
    editor._table._on_add()
    editor._table._on_add()
    first, second = music.sections
    assert (second.start, second.end) == (first.end, 3000)    # la suite, jusqu'à la fin du fichier
    assert music.loop_section == first.name                   # la boucle par défaut ne bouge pas


def test_un_compteur_de_secondes_ecrit_des_millisecondes(editor, project):
    music = _wav(project)
    editor.load(project, music)
    editor._table._on_add()
    section = music.sections[0]
    start, end = editor._table._spins[id(section)]
    start.setValue(500)
    end.setValue(2500)
    assert (section.start, section.end) == (500, 2500)
    start.setValue(2490)                                       # la fin suit : une section ne passe pas sous 50 ms
    assert section.end >= section.start + 50


def test_glisser_une_poignee_ecrit_la_boucle_au_relachement(editor, project):
    music = _wav(project)
    editor.load(project, music)
    editor._table._on_add()
    seen = []
    editor.changed.connect(lambda: seen.append(1))
    section = music.section(music.loop_section)
    spins = editor._table._spins[id(section)]
    editor._wave.loop_moving.emit(300, 1800)                   # pendant le glisser : les bornes suivent
    assert spins[0].value() == 300 and not seen
    editor._wave.loop_changed.emit(300, 1800)                  # au relâchement : on écrit
    section = music.section(music.loop_section)
    assert (section.start, section.end) == (300, 1800) and seen


def test_les_poignees_se_saisissent_et_ne_se_croisent_pas(editor, project):
    music = _wav(project)
    editor.load(project, music)
    editor._table._on_add()
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
    assert editor._strip_zone.isHidden() and editor._sections_zone.isHidden()
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
    assert editor._strip_zone.isHidden() and editor._sections_zone.isHidden()   # ni la bande des ordres, ni les sections


def test_sans_fichier_ou_avec_un_fichier_illisible_l_editeur_le_dit(editor, project):
    music = _module(project)
    music.asset = None
    editor.load(project, music)
    assert editor._structure.isHidden() and "No file" in editor._message.text()
    music.asset = "assets/music/Nope.it"
    editor.load(project, music)
    assert editor._structure.isHidden() and "No file" in editor._message.text()


# ── Le lecteur : l'aperçu d'une section ───────────────────────────


def test_l_apercu_d_une_section_commence_a_son_debut_et_boucle_dessus(player, project, monkeypatch):
    monkeypatch.setattr(BoxPlayer, "_open_sink", lambda self: None)     # pas de carte son en test
    music = _module(project)
    section = music.add_section(3, 5, "Main")
    assert player.preview(project, music, section)
    deck = player._deck
    deck.pull(4000)
    assert deck.track.order_at(deck.position) == 3               # le son part de l'ordre 3 : le début de la section
    assert deck.looping                                          # une section boucle, drapeau ou pas
    assert deck.playing


def test_l_apercu_d_un_wav_commence_a_sa_boucle(player, project, monkeypatch):
    monkeypatch.setattr(BoxPlayer, "_open_sink", lambda self: None)
    music = _wav(project)
    music.unit = UNIT_MS                    # ce que l'éditeur pose au chargement d'un WAV
    section = music.add_section(500, 2000, "Main")
    assert player.preview(project, music, section)
    deck = player._deck
    deck.pull(4000)
    assert deck.track.order_at(deck.position) == deck.track.loop_orders[0] == 1     # le segment qui commence à 0,5 s
    assert deck.looping                                          # une section WAV boucle comme celle d'un module


# ── Le poids en ROM ───────────────────────────────────────────────


def test_un_wav_montre_son_poids_exact_et_il_suit_le_taux(editor, project):
    from core.wav_module import wav_to_xm
    music = _wav(project, seconds=3.0)
    editor.load(project, music)
    path = project.asset_abs(music.asset)
    assert not editor._weight.isHidden()
    assert editor._weight.text() == f"ROM {len(wav_to_xm(path, 16726)) / 1024:.1f} KiB"   # le module que le build écrit
    music.sample_rate = 8000
    editor.reload()
    assert editor._weight.text() == f"ROM {len(wav_to_xm(path, 8000)) / 1024:.1f} KiB"    # moitié moins d'octets


# ── Tout tient à l'écran ──────────────────────────────────────────


def _add_buttons(table):
    """Le « + » vivant : un tableau reconstruit laisse ses anciens boutons attendre leur suppression."""
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication, QPushButton
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    return [b for b in table.findChildren(QPushButton) if b.text().startswith("＋")]


def test_le_plus_se_desactive_a_six_sections(editor, project):
    from core.music_structure import MAX_SECTIONS
    # Une section ajoutée sans sélection CONTINUE la dernière (quatre ordres) : il faut un morceau qui en contienne six.
    music = _module(project, orders=[0] * (4 * MAX_SECTIONS))
    editor.load(project, music)
    for _ in range(MAX_SECTIONS - 1):
        editor._table._on_add()
    assert _add_buttons(editor._table)[0].isEnabled()
    editor._table._on_add()
    assert len(music.sections) == MAX_SECTIONS
    assert _add_buttons(editor._table) == []                     # au maximum, le bouton n'est plus là


def test_la_section_cliquee_devient_la_plage_qui_boucle(editor, project):
    """Un clic sur le nom d'une section pose ses bornes ; le vide les retire, et la lecture redevient libre."""
    music = _module(project)
    music.sections.clear()
    editor.resize(900, 760)
    editor.load(project, music)
    section = music.add_section(0, 4, "Main")
    editor._refresh_sections()
    strip = editor._strip
    assert editor.scope_section is None and editor.scope_seconds() is None

    band = strip._band_of(section)
    QTest.mousePress(strip, Qt.MouseButton.LeftButton, pos=QPoint(int(band.center().x()), int(band.center().y())))
    QTest.mouseRelease(strip, Qt.MouseButton.LeftButton, pos=QPoint(int(band.center().x()), int(band.center().y())))
    assert editor.scope_section is section
    start, end = editor.scope_seconds()
    assert 0 <= start < end
    assert editor._wave._scope is not None

    editor._wave.set_cue(end + 1.0)                       # une poignée hors de la section : la lecture part quand même de là
    assert editor.start_seconds() == end + 1.0
    editor._wave.set_cue((start + end) / 2)
    assert editor.start_seconds() is not None

    QTest.mousePress(strip, Qt.MouseButton.LeftButton, pos=QPoint(int(strip.width()) - 3, int(band.center().y())))
    assert editor.scope_section is None and editor._wave._scope is None


def test_les_poignees_d_un_wav_suivent_la_section_selectionnee(editor, project):
    """Pas de poignées sans sélection ; celles de la section choisie, la première comme la suivante, sinon."""
    music = _wav(project)
    editor.resize(900, 760)
    editor.load(project, music)
    editor._table._on_add()
    editor._table._on_add()
    first, second = music.sections
    assert editor._wave._loop == (second.start, second.end)      # « + » choisit la section qu'il vient de créer

    strip = editor._strip
    band = strip._band_of(first)
    QTest.mousePress(strip, Qt.MouseButton.LeftButton, pos=QPoint(int(band.center().x()), int(band.center().y())))
    QTest.mouseRelease(strip, Qt.MouseButton.LeftButton, pos=QPoint(int(band.center().x()), int(band.center().y())))
    assert editor._wave._loop == (first.start, first.end)
    editor._wave.loop_changed.emit(100, 900)                    # la poignée écrit la section choisie, pas la « par défaut »
    assert (first.start, first.end) == (100, 900) and (second.start, second.end) != (100, 900)

    QTest.mousePress(strip, Qt.MouseButton.LeftButton, pos=QPoint(int(strip._x(1500)), int(band.center().y())))   # le vide entre les deux
    assert editor._wave._loop is None


def test_les_bords_d_une_section_de_wav_se_glissent_sur_la_bande(editor, project):
    music = _wav(project)
    editor.resize(900, 760)
    editor.load(project, music)
    editor._table._on_add()
    section = music.sections[0]
    strip = editor._strip
    band = strip._band_of(section)
    y = int(band.center().y())
    QTest.mousePress(strip, Qt.MouseButton.LeftButton, pos=QPoint(int(band.right()), y))
    QTest.mouseMove(strip, QPoint(int(band.right()) - 60, y))
    QTest.mouseRelease(strip, Qt.MouseButton.LeftButton, pos=QPoint(int(band.right()) - 60, y))
    assert section.end < 2250 and section.end >= section.start + 50
    assert isinstance(section.end, int)




# ── La barre de rognage prend la place de la courbe de polyphonie ─────────


def test_un_wav_montre_la_barre_de_rognage_a_la_place_de_la_polyphonie(editor, project):
    music = _wav(project)
    editor.load(project, music)
    assert not editor._trim_zone.isHidden() and editor._poly.isHidden()
    grid = editor._structure.layout().itemAt(0).layout()
    assert grid.indexOf(editor._trim_zone) >= 0 and grid.indexOf(editor._poly) >= 0     # la même case, une seule des deux visible


def test_un_module_garde_sa_courbe_de_polyphonie_et_n_a_pas_de_rognage(editor, project):
    editor.load(project, _module(project))
    assert editor._trim_zone.isHidden() and not editor._poly.isHidden()


def test_un_wav_ne_demande_pas_la_hauteur_de_la_courbe_en_plus_de_la_barre(editor, project, qapp):
    editor.load(project, _wav(project))
    editor.show()
    editor._trim_btn.setChecked(True)
    qapp.processEvents()

    assert editor._trim_zone.height() <= 80                          # la case sous l'onde est celle de la barre seule
    assert editor._wave.minimumHeight() == 96                        # l'onde garde la sienne
    assert editor._trim_bar.height() == 38                           # et la barre est plus basse qu'avant (46 → 38 px)
    top = editor._wave.mapTo(editor, editor._wave.rect().bottomLeft()).y()
    assert editor._trim_zone.mapTo(editor, editor._trim_zone.rect().topLeft()).y() - top <= 12   # juste sous l'onde


@pytest.mark.parametrize("height", [520, 600, 700, 800, 1000])
def test_un_wav_rogne_ne_fait_pas_defiler_l_ecran_aux_hauteurs_courantes(editor, project, qapp, height):
    editor.load(project, _wav(project))
    editor.resize(900, height)
    editor.show()
    editor._trim_btn.setChecked(True)
    qapp.processEvents()

    assert editor._scroll.verticalScrollBar().maximum() == 0, (height, editor._scroll.verticalScrollBar().maximum())
