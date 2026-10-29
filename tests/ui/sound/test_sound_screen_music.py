"""L'écran Son pour une musique : le panneau central, l'inspecteur, l'enregistrement, la lecture.

L'écran choisit ce qu'il montre par le TYPE de l'asset sélectionné : un effet n'a pas d'éditeur central,
une musique a l'éditeur complet, un jingle l'éditeur sans sections (la ROM n'applique à un jingle que
son volume). Ces tests tiennent que la bascule se fait, que ce qu'on règle arrive sur le disque, et que
l'écoute d'une section passe par le lecteur de l'écran.
"""
from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

REPO_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_DIR / "tests"))
sys.path.insert(0, str(REPO_DIR / "tests" / "audio"))

import module_fixtures as F                                    # noqa: E402
from asset_fixtures import create                              # noqa: E402
from core.models.audio import UNIT_MS                          # noqa: E402
from core.project import Project                               # noqa: E402
from ui.common.deferred_writes import get_deferred_writes      # noqa: E402
from ui.sound_mixer.box_playback import BoxPlayer              # noqa: E402
from ui.sound_mixer.sound_panel import SoundMixerScreen        # noqa: E402


@pytest.fixture
def project(tmp_path) -> Project:
    project = Project.create(tmp_path / "Game", "Game")
    music = project.user_library_dir / "music"
    music.mkdir(parents=True, exist_ok=True)
    (music / "Theme.it").write_bytes(F.make_it(orders=[0] * 8))
    t = np.arange(int(44100 * 2.0)) / 44100
    with wave.open(str(music / "Ambient.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes((np.sin(2 * np.pi * 300 * t) * 0.5 * 32767).astype("<i2").tobytes())
    jingles = project.user_library_dir / "jingles"
    jingles.mkdir(parents=True, exist_ok=True)
    (jingles / "Fanfare.it").write_bytes(F.make_it())
    sfx = project.user_library_dir / "sfx"
    sfx.mkdir(parents=True, exist_ok=True)
    with wave.open(str(sfx / "Beep.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(8000); w.writeframes(bytes([128]) * 800)
    create(project, "music", music / "Theme.it")
    create(project, "music", music / "Ambient.wav")
    create(project, "jingles", jingles / "Fanfare.it")
    create(project, "sfx", sfx / "Beep.wav")
    return project


@pytest.fixture
def screen(qapp, project, monkeypatch):
    monkeypatch.setattr(BoxPlayer, "_open_sink", lambda self: None)     # pas de carte son en test
    s = SoundMixerScreen()
    s.load_project(project)
    return s


def _reloaded(project: Project) -> Project:
    get_deferred_writes().flush()          # les réglages s'écrivent après un silence (cf. `deferred_writes`) : on relit le disque tenu à jour
    reopened = Project.open(project.root)
    reopened.load_all_resources()
    return reopened


# ── Ce que l'écran montre ─────────────────────────────────────────


def test_le_panneau_central_suit_le_type_de_l_asset(screen, project):
    assert screen._music_editor.isHidden() and not screen._center_filler.isHidden()
    screen._on_asset_selected(project.music.get("Theme"))
    assert not screen._music_editor.isHidden() and screen._center_filler.isHidden()
    assert screen._music_editor._music.name == "Theme"
    screen._on_asset_selected(project.sfx.get("Beep"))
    # Un effet a SON éditeur (la découpe), qui prend la colonne à la place de celui d'une musique : ni l'un ni le remplissage.
    assert screen._music_editor.isHidden() and not screen._sfx_editor.isHidden() and screen._center_filler.isHidden()
    # ... et sa table de mixage prend, en bas de la colonne de droite, la place de celle d'une musique : une seule se montre.
    assert not screen._sfx_editor.mix_panel.isHidden() and screen._music_editor.mix_panel.isHidden()
    screen._on_asset_selected(project.music.get("Theme"))
    assert screen._sfx_editor.mix_panel.isHidden() and not screen._music_editor.mix_panel.isHidden()


def test_un_jingle_montre_l_onde_sans_les_sections_et_sans_les_reglages_de_musique(screen, project):
    screen._on_asset_selected(project.jingles.get("Fanfare"))
    editor = screen._music_editor
    assert not editor.isHidden() and not editor._structure.isHidden()
    assert editor._strip_zone.isHidden() and editor._sections_zone.isHidden()   # ni la bande des ordres, ni les sections
    assert not hasattr(screen._jingle_insp, "_rate")           # pas de taux : la ROM l'ignore
    assert hasattr(screen._music_insp, "_rate")
    assert not any(spin.isEnabled() for spin in editor._faders._fades.values())   # ni de fondus


def test_un_wav_active_le_taux_et_un_module_non(screen, project):
    screen._on_asset_selected(project.music.get("Ambient"))
    insp = screen._music_insp
    assert insp._rate.isEnabled()
    screen._on_asset_selected(project.music.get("Theme"))
    assert not insp._rate.isEnabled()


def test_volume_tempo_et_hauteur_sont_a_la_table_de_mixage_pas_dans_l_inspecteur(screen, project):
    screen._on_asset_selected(project.music.get("Theme"))
    assert not hasattr(screen._music_insp, "_vol") and not hasattr(screen._music_insp, "_tempo")
    faders = screen._music_editor._faders
    assert all(faders.fader(f).isEnabled() for f in ("volume", "tempo", "pitch"))


def test_un_wav_grise_tempo_et_hauteur_et_un_jingle_aussi(screen, project):
    faders = screen._music_editor._faders
    for asset, expected in ((project.music.get("Ambient"), (True, False, False)),
                            (project.jingles.get("Fanfare"), (True, False, False)),
                            (project.music.get("Theme"), (True, True, True))):
        screen._on_asset_selected(asset)
        assert tuple(faders.fader(f).isEnabled() for f in ("volume", "tempo", "pitch")) == expected


# ── Ce qu'on règle arrive sur le disque ───────────────────────────


def test_les_reglages_de_l_inspecteur_sont_enregistres_et_changent_le_rendu(screen, project):
    theme = project.music.get("Theme")
    screen._on_asset_selected(theme)
    editor = screen._music_editor
    normal = len(editor._track.pcm)
    editor._faders.fader("tempo").setValue(200)
    editor._faders._fades["fade_in"].setValue(30)
    editor._faders._fades["fade_out"].setValue(60)
    screen._retune()                                           # ce que fait la minuterie quand le curseur s'arrête
    deadline = time.monotonic() + 10                           # le rendu se fait hors du fil d'interface : on l'attend
    while len(editor._track.pcm) >= 0.6 * normal and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert len(editor._track.pcm) < 0.6 * normal               # l'éditeur a relu : l'onde est celle du nouveau tempo
    editor._save_timer.timeout.emit()                          # et le disque, quand on lâche le curseur
    saved = _reloaded(project).music.get("Theme")
    assert (saved.tempo, saved.fade_in, saved.fade_out) == (200, 30, 60)


def test_le_taux_d_un_wav_est_enregistre(screen, project):
    screen._on_asset_selected(project.music.get("Ambient"))
    insp = screen._music_insp
    insp._rate.setCurrentIndex(insp._rate.findData(11025))
    assert _reloaded(project).music.get("Ambient").sample_rate == 11025


def test_une_section_ajoutee_dans_l_editeur_est_enregistree(screen, project):
    theme = project.music.get("Theme")
    screen._on_asset_selected(theme)
    screen._music_editor._strip._set_selection(2, 5)
    screen._music_editor._table._on_add()
    saved = _reloaded(project).music.get("Theme")
    assert [(s.name, s.start, s.end, s.loop) for s in saved.sections] == [("Loop", 2, 5, True)]
    assert saved.loop_section == "Loop" and saved.unit == "order"


def test_la_boucle_d_un_wav_est_enregistree_en_millisecondes(screen, project):
    ambient = project.music.get("Ambient")
    screen._on_asset_selected(ambient)
    screen._music_editor._table._on_add()
    saved = _reloaded(project).music.get("Ambient")
    assert saved.unit == UNIT_MS and len(saved.sections) == 1
    assert saved.sections[0].start == 500 and saved.sections[0].end == 1500    # ¼ et ¾ de 2 s


# ── La lecture ────────────────────────────────────────────────────


def test_ecouter_une_section_arme_le_lecteur_de_l_ecran(screen, project):
    theme = project.music.get("Theme")
    screen._on_asset_selected(theme)
    section = theme.add_section(3, 5, "Main")
    screen._music_editor.reload()
    screen._preview_section(section)
    assert screen._btn_rom.isChecked() and screen._armed_asset is theme
    deck = screen._box_player._deck
    deck.pull(4000)
    assert deck.track.order_at(deck.position) == 3
    screen._stop_rom_playback()
    assert not screen._btn_rom.isChecked()


# ── La table de mixage s'entend pendant qu'on la règle ───────────


def _playing(screen, project, name="Theme"):
    asset = project.music.get(name)
    screen._on_asset_selected(asset)
    assert screen._box_player.preview(project, asset)
    return asset


def test_un_curseur_de_volume_change_le_volume_de_l_apercu_en_cours(screen, project):
    from core.models.audio import volume_to_module
    asset = _playing(screen, project)
    screen._music_editor._faders.fader("volume").setValue(40)
    assert asset.volume == 40
    assert screen._box_player._deck._vol == volume_to_module(40)


def test_un_curseur_de_tempo_est_lu_par_le_rendu_en_direct_au_tick_suivant(screen, project):
    from core.engine_emulation.module_stream import StreamTrack
    asset = _playing(screen, project)
    deck = screen._box_player._deck
    track = deck.track
    assert isinstance(track, StreamTrack)                        # l'aperçu est joué tick par tick
    deck.pull(10000)
    screen._music_editor._faders.fader("tempo").setValue(200)    # aucun rendu à refaire, rien à attendre
    assert track._state.tempo == 2.0 and deck.track is track
    assert deck.playing


def test_un_curseur_de_hauteur_est_lu_au_tick_suivant_lui_aussi(screen, project):
    asset = _playing(screen, project)
    screen._music_editor._faders.fader("pitch").setValue(150)
    assert asset.pitch == 150 and abs(screen._box_player._deck.track._state.pitch - 1.5) < 0.01


def test_sans_apercu_en_cours_un_curseur_ne_touche_que_le_modele(screen, project):
    asset = project.music.get("Theme")
    screen._on_asset_selected(asset)
    screen._music_editor._faders.fader("volume").setValue(55)
    screen._music_editor._faders.fader("tempo").setValue(80)   # rien ne joue : rien à régler
    assert asset.volume == 55 and asset.tempo == 80 and not screen._box_player._deck.playing


def test_un_double_clic_remet_le_curseur_au_neutre(screen, project):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    screen._on_asset_selected(project.music.get("Theme"))
    fader = screen._music_editor._faders.fader("tempo")
    fader.setValue(160)
    fader.mouseDoubleClickEvent(QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(5, 5), Qt.MouseButton.LeftButton,
                                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert fader.value() == 100


def test_un_reglage_de_section_est_enregistre_sans_recharger_le_sound_library(screen, project, monkeypatch):
    theme = project.music.get("Theme")
    screen._on_asset_selected(theme)
    reloads = []
    monkeypatch.setattr(screen._library, "refresh", lambda *a, **k: reloads.append(1))
    screen._music_editor._table._on_add()                       # une section
    section = theme.sections[0]
    screen._music_editor._table._on_loop(section, False)        # sa case « Loop »
    screen._music_editor._table._on_default(section)            # son bouton « Default »
    assert not reloads
    assert _reloaded(project).music.get("Theme").sections[0].loop is False


def test_le_son_suit_chaque_cran_d_un_glisse(screen, project):
    from core.models.audio import tempo_to_module
    asset = _playing(screen, project)
    track = screen._box_player._deck.track
    fader = screen._music_editor._faders.fader("tempo")
    for value in (110, 130, 150, 170, 190):                      # un glissé : le rendu en direct lit le dernier cran
        fader.setValue(value)
        assert track._state.tempo == tempo_to_module(value) / 1024     # le facteur Q10 de maxmod, comme la ROM
    assert asset.tempo == 190


def test_le_json_s_ecrit_au_relachement_et_pas_pendant_que_le_curseur_est_tenu(screen, project, monkeypatch):
    asset = project.music.get("Theme")
    screen._on_asset_selected(asset)
    writes = []
    original = project.save_music
    monkeypatch.setattr(project, "save_music", lambda a: (writes.append(1), original(a))[1])
    fader = screen._music_editor._faders.fader("tempo")
    fader.setSliderDown(True)                                    # le curseur est saisi
    for value in range(101, 160, 7):
        fader.setValue(value)
    from PyQt6.QtTest import QTest
    QTest.qWait(500)                                             # même une pause, curseur tenu : rien n'est écrit
    assert writes == [] and asset.tempo == 157
    fader.setSliderDown(False)                                   # relâché : une seule écriture
    assert len(writes) == 1
    assert _reloaded(project).music.get("Theme").tempo == 157


def test_un_cran_de_molette_s_ecrit_apres_un_instant_de_calme(screen, project, monkeypatch):
    asset = project.music.get("Theme")
    screen._on_asset_selected(asset)
    writes = []
    original = project.save_music
    monkeypatch.setattr(project, "save_music", lambda a: (writes.append(1), original(a))[1])
    from PyQt6.QtTest import QTest
    screen._music_editor._faders.fader("pitch").setValue(120)    # ni tenu ni glissé : molette ou clavier
    assert writes == []
    QTest.qWait(450)
    assert len(writes) == 1


def test_un_reglage_en_attente_s_ecrit_sur_sa_musique_quand_on_en_ouvre_une_autre(screen, project):
    theme, ambient = project.music.get("Theme"), project.music.get("Ambient")
    screen._on_asset_selected(theme)
    screen._music_editor._faders.fader("pitch").setValue(120)    # le minuteur de 300 ms est armé
    screen._on_asset_selected(ambient)                           # ... et on change de musique avant son échéance
    assert _reloaded(project).music.get("Theme").pitch == 120


def test_renommer_un_son_vers_un_nom_pris_est_refuse_sans_planter(screen, project):
    screen._on_asset_selected(project.music.get("Theme"))
    screen._music_insp._on_renamed("Ambient")                    # déjà pris par l'autre musique
    assert project.music.get("Theme") is not None and screen._music_insp._asset.name == "Theme"


def test_le_renommage_d_un_son_s_annule(screen, project):
    from core.history import get_history
    theme = project.music.get("Theme")
    screen._on_asset_selected(theme)
    screen._music_insp._on_renamed("Hymn")
    assert theme.name == "Hymn" and project.music.get("Hymn") is theme
    get_history().undo()
    assert theme.name == "Theme" and project.music.get("Theme") is theme


# ── Les boîtes (panneau caché pour l'instant) : elles doivent se construire et se charger ──


def test_le_panneau_des_boites_cache_se_charge_pour_les_trois_familles(screen, project):
    from core.models.sound_box import ActionState, JingleBox, MusicBox, MusicState, SoundBox
    from ui.sound_mixer.sound_commands import AddBoxStateCmd, RemoveMusicStateCmd
    project.music_boxes.append(MusicBox(name="M", states=[MusicState(name="a", music="Theme"),
                                                          MusicState(name="b", music="Ambient")], start="a"))
    project.sound_boxes.append(SoundBox(name="S", actions=["hit"], states=[ActionState(name="s", mapping={"hit": "Beep"})], start="s"))
    project.jingle_boxes.append(JingleBox(name="J", actions=["win"], states=[ActionState(name="j", mapping={"win": "Fanfare"})], start="j"))
    screen.load_project(project)
    screen._machines_panel.show()
    for index, tab in enumerate(screen._box_tabs()):
        screen._tabs.setCurrentIndex(index)
        assert tab.current() is not None and not tab._editor.isHidden()
    music_box = project.music_boxes[0]
    state = music_box.states[1]
    cmd = RemoveMusicStateCmd(music_box, state)
    cmd.execute()
    assert [s.name for s in music_box.states] == ["a"]
    cmd.undo()
    assert [s.name for s in music_box.states] == ["a", "b"]
    AddBoxStateCmd(music_box, MusicState(name="c")).execute()
    assert len(music_box.states) == 3
