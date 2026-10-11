"""L'écran Son pour une musique : le panneau central, l'inspecteur, l'enregistrement, la lecture.

L'écran choisit ce qu'il montre par le TYPE de l'asset sélectionné : un effet n'a pas d'éditeur central,
une musique a l'éditeur complet, un jingle l'éditeur sans sections (la ROM n'applique à un jingle que
son volume). Ces tests tiennent que la bascule se fait, que ce qu'on règle arrive sur le disque, et que
l'écoute d'une section passe par le lecteur de l'écran.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "tests"))
sys.path.insert(0, str(REPO_DIR / "tests" / "audio"))

import module_fixtures as F                                    # noqa: E402
from asset_fixtures import create                              # noqa: E402
from core.models.audio import UNIT_MS                          # noqa: E402
from core.project import Project                               # noqa: E402
from ui.sound_mixer.box_playback import BoxPlayer              # noqa: E402
from ui.sound_mixer.sound_panel import SoundMixerScreen        # noqa: E402


@pytest.fixture
def project(tmp_path) -> Project:
    project = Project.create(tmp_path / "Game", "Game")
    music = project.assets_dir / "music"
    music.mkdir(parents=True, exist_ok=True)
    (music / "Theme.it").write_bytes(F.make_it(orders=[0] * 8))
    t = np.arange(int(44100 * 2.0)) / 44100
    with wave.open(str(music / "Ambient.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes((np.sin(2 * np.pi * 300 * t) * 0.5 * 32767).astype("<i2").tobytes())
    jingles = project.assets_dir / "jingles"
    jingles.mkdir(parents=True, exist_ok=True)
    (jingles / "Fanfare.it").write_bytes(F.make_it())
    sfx = project.assets_dir / "sfx"
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
    assert screen._music_editor.isHidden() and not screen._center_filler.isHidden()


def test_un_jingle_montre_l_onde_sans_les_sections_et_sans_les_reglages_de_musique(screen, project):
    screen._on_asset_selected(project.jingles.get("Fanfare"))
    editor = screen._music_editor
    assert not editor.isHidden() and not editor._structure.isHidden()
    assert editor._module_zone.isHidden()
    assert not hasattr(screen._jingle_insp, "_tempo")          # ni tempo ni fondus : la ROM les ignore
    assert hasattr(screen._music_insp, "_tempo")


def test_un_wav_desactive_tempo_et_hauteur_et_active_le_taux(screen, project):
    screen._on_asset_selected(project.music.get("Ambient"))
    insp = screen._music_insp
    assert not insp._tempo.isEnabled() and not insp._pitch.isEnabled() and insp._rate.isEnabled()
    screen._on_asset_selected(project.music.get("Theme"))
    assert insp._tempo.isEnabled() and not insp._rate.isEnabled()


# ── Ce qu'on règle arrive sur le disque ───────────────────────────


def test_les_reglages_de_l_inspecteur_sont_enregistres_et_changent_le_rendu(screen, project):
    theme = project.music.get("Theme")
    screen._on_asset_selected(theme)
    editor = screen._music_editor
    normal = len(editor._track.pcm)
    insp = screen._music_insp
    insp._tempo.setValue(200)
    insp._fade_in.setValue(30)
    insp._fade_out.setValue(60)
    assert len(editor._track.pcm) < 0.6 * normal               # l'éditeur a relu : l'onde est celle du nouveau tempo
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
    screen._music_editor._wav_loop.setChecked(True)
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
    track = screen._box_player.track_for(project, theme)
    assert screen._box_player._deck.position == track.start_of(3)
    screen._stop_rom_playback()
    assert not screen._btn_rom.isChecked()
