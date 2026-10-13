"""Un jingle est un module comme une musique ; c'est son DOSSIER qui lui donne le rôle.

`assets/jingles/` → `project.jingles` (famille `Jingle`), `assets/music/` → `project.music`.
Ces tests tiennent les quatre conséquences : le rôle suit le dossier au chargement, `music.play` et
`music.jingle` refusent chacun l'autre famille, le plafond de 4 canaux se vérifie à l'import, et les
deux familles partagent UNE numérotation de ROM (donc des noms distincts).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F                                  # noqa: E402
from asset_fixtures import create                           # noqa: E402
from core import validator                                   # noqa: E402
from core.models.audio import Jingle, Music                  # noqa: E402
from core.project import Project                             # noqa: E402
from core.resources import asset_reconciliation              # noqa: E402
from core.validator import ValidationContext                 # noqa: E402


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


def _drop(project: Project, folder: str, name: str) -> Path:
    path = project.assets_dir / folder / f"{name}.mod"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(F.make_mod())
    return path


# ── Le rôle suit le dossier ─────────────────────────────────────────────


def test_un_module_de_assets_jingles_devient_un_jingle(project):
    _drop(project, "music", "Theme")
    _drop(project, "jingles", "Fanfare")
    project.load()
    project.load_all_resources()
    create(project, "music", project.music_dir / "Theme.mod")
    create(project, "jingles", project.jingles_dir / "Fanfare.mod")
    assert [m.name for m in project.music] == ["Theme"]
    assert [j.name for j in project.jingles] == ["Fanfare"]
    assert isinstance(project.jingles.get("Fanfare"), Jingle)
    assert not isinstance(project.music.get("Theme"), Jingle)


def test_audio_modules_donne_les_deux_familles(project):
    _drop(project, "music", "Theme")
    _drop(project, "jingles", "Fanfare")
    project.load()
    project.load_all_resources()
    create(project, "music", project.music_dir / "Theme.mod")
    create(project, "jingles", project.jingles_dir / "Fanfare.mod")
    assert sorted(m.name for m in project.audio_modules()) == ["Fanfare", "Theme"]


def test_renommer_un_jingle_reecrit_music_jingle_et_pas_music_play(project):
    _drop(project, "jingles", "Fanfare")
    project.load()
    project.load_all_resources()
    create(project, "jingles", project.jingles_dir / "Fanfare.mod")
    project.scripts_dir.mkdir(parents=True, exist_ok=True)
    script = project.scripts_dir / "S.lua"
    script.write_text('function on_start()\n music.jingle("Fanfare")\n music.play("Fanfare")\nend\n',
                      encoding="utf-8")
    project.rename_sound(project.jingles.get("Fanfare"), "Victory")
    text = script.read_text(encoding="utf-8")
    assert 'music.jingle("Victory")' in text
    assert 'music.play("Fanfare")' in text


# ── Le checker sépare les deux familles ─────────────────────────────────


def _warnings(src: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    ctx = BuildContext(actor_name="Ball", anim_names=["idle"],
                       music_names=["Theme", "Fanfare"], jingle_names=["Fanfare"])
    return [e.message for e in check(parse(src), ctx) if e.level == "warning"]


def test_music_play_sur_un_jingle_avertit():
    found = _warnings('function on_start()\n music.play("Fanfare")\nend\n')
    assert any("is a jingle" in m for m in found)


def test_music_jingle_sur_une_musique_avertit():
    found = _warnings('function on_start()\n music.jingle("Theme")\nend\n')
    assert any("is a music" in m for m in found)


def test_un_nom_inconnu_avertit_dans_les_deux_appels():
    found = _warnings('function on_start()\n music.play("Nope")\n music.jingle("Nope")\nend\n')
    assert any("music 'Nope' not found" in m for m in found)
    assert any("jingle 'Nope' not found" in m for m in found)


def test_chaque_famille_passe_par_son_appel():
    assert _warnings('function on_start()\n music.play("Theme")\n music.jingle("Fanfare")\nend\n') == []


# ── 4 canaux, à l'import ────────────────────────────────────────────────


class _Module:
    def __init__(self, channels):
        self.num_channels = channels
        self.order = [0]
        self.samples = [SimpleNamespace(data=SimpleNamespace(size=1))]


def test_un_module_de_plus_de_quatre_canaux_est_refuse_comme_jingle(tmp_path, monkeypatch):
    src = tmp_path / "big.mod"
    src.write_bytes(F.make_mod())
    monkeypatch.setattr("core.engine_emulation.module_model.load_module",
                        lambda path: _Module(6))
    # `into` = où le fichier IRA : à l'import il n'est pas encore dans son dossier.
    assert "4" in (asset_reconciliation.check_audio_file(src, into="jingles") or "")
    assert asset_reconciliation.check_audio_file(src, into="music") is None


# ── Une seule numérotation de ROM ───────────────────────────────────────


def test_un_nom_de_musique_et_de_jingle_identiques_sont_une_erreur(project):
    project.music.append(Music(name="Same", asset="assets/music/Same.mod"))
    project.jingles.append(Jingle(name="Same", asset="assets/jingles/Same.mod"))
    ctx = ValidationContext(project)
    validator._check_sound_names_unique(ctx)
    assert [m.level for m in ctx._msgs] == ["error"]


# ── Pistes WAV : deux limites du matériel ───────────────────────────────


def test_une_piste_wav_trop_longue_pour_la_table_d_ordres_est_refusee(tmp_path):
    import wave
    from core import wav_module
    path = tmp_path / "long.wav"
    seconds = int(wav_module.MAX_SECONDS) + 3
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(8000)
        w.writeframes(bytes([128]) * (8000 * seconds))
    assert "limited" in (asset_reconciliation.check_audio_file(path, into="music") or "")
    with pytest.raises(ValueError, match="too long"):
        wav_module.wav_to_xm(path)


def test_une_coupe_vers_une_piste_wav_avertit(project):
    from core.models.sound_box import MusicBox, MusicState, MusicTransition, TRANSITION_CUT
    project.music.append(Music(name="A", asset="assets/music/A.wav"))
    project.music.append(Music(name="B", asset="assets/music/B.wav"))
    project.music_boxes.append(MusicBox(
        name="m", start="a",
        states=[MusicState(name="a", music="A"), MusicState(name="b", music="B")],
        transitions=[MusicTransition(src="a", dst="b", trigger="go", kind=TRANSITION_CUT)]))
    ctx = ValidationContext(project)
    validator._check_sound_boxes(ctx)
    assert any("WAV track" in m.message for m in ctx._msgs)


def test_une_piste_trop_longue_inutilisee_n_est_qu_un_avertissement(project):
    import wave
    from core import wav_module
    path = project.assets_dir / "music" / "long.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    seconds = int(wav_module.MAX_SECONDS) + 3
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(8000)
        w.writeframes(bytes([128]) * (8000 * seconds))
    project.music.append(Music(name="long", asset=project.asset_rel(path)))
    ctx = ValidationContext(project)
    validator._check_audio_files(ctx)
    assert [m.level for m in ctx._msgs if "limited to" in m.message] == ["warning"]
