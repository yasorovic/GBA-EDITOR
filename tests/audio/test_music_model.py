"""L'asset `.music` : ses réglages, leur relecture, et leur accord avec le fichier.

Le sidecar surcharge, le fichier propose (ROADMAP « L'asset .music ») : sections,
boucle, tempo, hauteur, fondus et taux sont posés PAR-DESSUS un morceau sans
jamais le toucher. Ces tests tiennent ce que ça exige — un sidecar d'avant ces
champs se relit comme avant, un sidecar qui décrit un morceau disparu est signalé
avant le build, et les échelles du matériel sont celles de `maxmod.h`.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F                                  # noqa: E402
from core import validator, wav_module                       # noqa: E402
from core.models import audio                                # noqa: E402
from core.models.audio import Jingle, Music, MusicSection    # noqa: E402
from core.project import Project                             # noqa: E402
from core.resources import asset_reconciliation              # noqa: E402
from core.validator import ValidationContext                 # noqa: E402


# ── 1. Relecture ──────────────────────────────────────────────────


def test_les_sections_font_l_aller_retour():
    m = Music(name="Boss", unit=audio.UNIT_ORDER, loop_section="Main",
              sections=[MusicSection("Intro", "#2e7d32", 0, 4),
                        MusicSection("Main", "#1976d2", 4, 12, loop=True)],
              tempo=110, pitch=95, fade_in=30, fade_out=60, sample_rate=13379)
    back = Music.from_dict(m.to_dict())
    assert back == m
    assert all(isinstance(s, MusicSection) for s in back.sections)


def test_un_sidecar_d_avant_ces_champs_se_relit_comme_avant():
    """Aucun réglage n'est inventé pour un asset existant : les défauts sont
    exactement l'ancien comportement (tempo/hauteur neutres, pas de fondu, boucle
    sur tout le morceau, taux par défaut)."""
    m = Music.from_dict({"name": "Old", "asset": "assets/music/Old.xm", "loop": False, "volume": 80})
    assert (m.loop, m.volume) == (False, 80)
    assert m.sections == [] and m.loop_section == ""
    assert (m.tempo, m.pitch, m.fade_in, m.fade_out, m.sample_rate) == (100, 100, 0, 0, 0)


def test_la_migration_du_volume_survit_aux_nouveaux_champs():
    """Au-dessus de 100, l'ancienne échelle 0–255 : toujours convertie."""
    assert Music.from_dict({"name": "x", "volume": 255}).volume == 100


def test_une_section_illisible_est_ignoree_et_un_champ_inconnu_aussi():
    m = Music.from_dict({"name": "x", "sections": ["n'importe quoi", {"name": "A", "end": 3}],
                         "champ_futur": 1})
    assert [s.name for s in m.sections] == ["A"]


def test_un_jingle_porte_les_memes_reglages():
    j = Jingle.from_dict({"name": "j", "tempo": 120, "sections": [{"name": "A", "end": 2}]})
    assert j.tempo == 120 and j.sections[0].name == "A"


def test_renommer_une_section_suit_la_boucle_qui_la_cite():
    m = Music(sections=[MusicSection("Main", start=4, end=12, loop=True)], loop_section="Main")
    m.rename_section("Main", "Boss loop")
    assert m.loop_section == "Boss loop" and m.section("Boss loop") is not None
    assert m.section("Main") is None


# ── 2. Les échelles du matériel ───────────────────────────────────


@pytest.mark.parametrize("percent, q10", [(100, 1024), (50, 512), (200, 2048),
                                          (10, 512), (400, 2048)])
def test_tempo_et_hauteur_sont_des_facteurs_q10_bornes(percent, q10):
    """`mmSetModuleTempo` / `mmSetModulePitch` : 0x200 à 0x800 (maxmod.h)."""
    assert audio.tempo_to_module(percent) == q10
    assert audio.pitch_to_module(percent) == q10


# ── 3. Le taux de build, la durée qui tient ───────────────────────


def test_la_duree_qui_tient_est_celle_de_la_table_d_ordres():
    assert wav_module.max_seconds() == wav_module.MAX_SECONDS
    assert wav_module.MAX_SECONDS > 600            # le titre de 1:18 des maquettes passe largement
    assert wav_module.effective_rate(0) == wav_module.WAV_MUSIC_RATE
    assert wav_module.effective_rate(11025) == 11025


def _wav(path: Path, seconds: int) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(2000)
        w.writeframes(bytes([128]) * (2000 * seconds))
    return path


def test_la_limite_de_duree_ne_depend_plus_du_taux(tmp_path):
    assert asset_reconciliation.wav_too_long(_wav(tmp_path / "ok.wav", 70)) is None
    long = _wav(tmp_path / "long.wav", 800)
    assert "limited" in (asset_reconciliation.wav_too_long(long) or "")


# ── 4. Les réglages face au fichier ───────────────────────────────


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


def _problems(project: Project, music: Music) -> list[tuple[str, str]]:
    project.music.append(music)
    ctx = ValidationContext(project)
    validator._check_music_structure(ctx)
    # Plusieurs musiques s'accumulent dans un même test : on ne lit que celle-ci.
    prefix = f'Music "{music.name}": '
    return [(m.level, m.message.removeprefix(prefix)) for m in ctx._msgs
            if m.message.startswith(prefix)]


def _drop(project: Project, filename: str, data: bytes) -> str:
    path = project.assets_dir / "music" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return f"assets/music/{filename}"


def _drop_wav(project: Project, filename: str, seconds: int) -> None:
    (project.assets_dir / "music").mkdir(parents=True, exist_ok=True)
    _wav(project.assets_dir / "music" / filename, seconds)


def _levels(problems) -> list[str]:
    return [level for level, _ in problems]


def test_des_sections_saines_ne_disent_rien(project):
    rel = _drop(project, "ok.xm", F.make_xm(orders=[0, 0, 0, 0]))
    m = Music(name="Ok", asset=rel, loop_section="Main",
              sections=[MusicSection("Intro", start=0, end=1),
                        MusicSection("Main", start=1, end=4, loop=True)])
    assert _problems(project, m) == []


def test_une_section_qui_depasse_le_fichier_est_une_erreur(project):
    rel = _drop(project, "court.xm", F.make_xm(orders=[0, 0]))
    problems = _problems(project, Music(name="C", asset=rel,
                                        sections=[MusicSection("Fin", start=1, end=9)]))
    assert _levels(problems) == ["error"]
    assert "only 2 order positions" in problems[0][1]


def test_une_plage_vide_ou_inversee_est_une_erreur(project):
    rel = _drop(project, "x.xm", F.make_xm(orders=[0, 0, 0]))
    problems = _problems(project, Music(name="X", asset=rel, sections=[
        MusicSection("Vide", start=2, end=2), MusicSection("Inversee", start=2, end=1)]))
    assert _levels(problems) == ["error", "error"]


def test_une_section_ne_peut_pas_commencer_sur_un_marqueur(project):
    """L'index brut 1 est le séparateur : un saut là ne tomberait pas sur de la musique."""
    rel = _drop(project, "sep.it", F.make_it(orders=[0, 254, 0, 255]))
    ok = _problems(project, Music(name="A", asset=rel, sections=[MusicSection("S", start=2, end=3)]))
    assert ok == []
    bad = _problems(project, Music(name="B", asset=rel, sections=[MusicSection("S", start=1, end=3)]))
    assert _levels(bad) == ["error"] and "marker" in bad[0][1]


def test_des_sections_d_une_autre_famille_de_fichier_sont_signalees(project):
    """Le `.mod` est remplacé par un `.wav` : les index d'ordre ne sont plus des
    millisecondes. Jamais réinterprétés en silence."""
    _drop_wav(project, "p.wav", 3)
    problems = _problems(project, Music(name="P", asset="assets/music/p.wav", unit=audio.UNIT_ORDER,
                                        sections=[MusicSection("S", start=0, end=2)]))
    assert _levels(problems) == ["error"] and "reset" in problems[0][1]


def test_un_wav_peut_avoir_plusieurs_sections_qui_bouclent(project):
    """Un WAV est un module : chaque section est une plage d'ordres, et plusieurs peuvent boucler."""
    _drop_wav(project, "w.wav", 4)
    m = Music(name="W", asset="assets/music/w.wav", unit=audio.UNIT_MS, loop_section="A",
              sections=[MusicSection("A", start=0, end=1000, loop=True),
                        MusicSection("B", start=1000, end=3000, loop=True)])
    assert _problems(project, m) == []


def test_une_section_plus_courte_qu_une_ligne_est_une_erreur(project):
    _drop_wav(project, "w.wav", 4)
    m = Music(name="W", asset="assets/music/w.wav", unit=audio.UNIT_MS,
              sections=[MusicSection("Blip", start=1000, end=1004)])
    problems = _problems(project, m)
    assert _levels(problems) == ["error"] and "shorter than one line" in problems[0][1]


def test_la_boucle_nommee_doit_exister_et_boucler(project):
    rel = _drop(project, "l.xm", F.make_xm(orders=[0, 0, 0]))
    absent = _problems(project, Music(name="A", asset=rel, loop_section="Nope",
                                      sections=[MusicSection("S", start=0, end=2, loop=True)]))
    assert _levels(absent) == ["error"]
    muet = _problems(project, Music(name="B", asset=rel, loop_section="S",
                                    sections=[MusicSection("S", start=0, end=2, loop=False)]))
    assert _levels(muet) == ["warning"]


def test_deux_sections_de_meme_nom_sont_une_erreur(project):
    rel = _drop(project, "d.xm", F.make_xm(orders=[0, 0, 0]))
    problems = _problems(project, Music(name="D", asset=rel, sections=[
        MusicSection("S", start=0, end=1), MusicSection("S", start=1, end=2)]))
    assert _levels(problems) == ["error"] and "ambiguous" in problems[0][1]


def test_tempo_hauteur_et_fondus_hors_bornes_avertissent(project):
    rel = _drop(project, "t.xm", F.make_xm())
    problems = _problems(project, Music(name="T", asset=rel, tempo=300, pitch=10,
                                        fade_in=-1, fade_out=9999))
    assert _levels(problems) == ["warning"] * 4


def test_un_taux_sur_un_module_avertit_et_un_taux_absurde_sur_un_wav_est_une_erreur(project):
    rel = _drop(project, "r.xm", F.make_xm())
    assert _levels(_problems(project, Music(name="R", asset=rel, sample_rate=11025))) == ["warning"]
    _drop_wav(project, "r.wav", 2)
    assert _levels(_problems(project, Music(name="W", asset="assets/music/r.wav",
                                            unit=audio.UNIT_MS, sample_rate=100))) == ["error"]


def test_une_musique_sans_fichier_ne_fait_pas_planter_le_controle(project):
    assert _problems(project, Music(name="Vide", sections=[MusicSection("S", 0, 1)])) == []


# ── 5. Ce que le build n'applique pas ─────────────────────────────


def test_un_wav_ignore_tempo_et_hauteur_et_le_dit(project):
    _drop_wav(project, "t.wav", 2)
    problems = _problems(project, Music(name="W", asset="assets/music/t.wav", unit=audio.UNIT_MS,
                                        tempo=150, pitch=120))
    assert _levels(problems) == ["warning"] and "do not apply to a WAV" in problems[0][1]


def test_une_section_de_boucle_boucle_meme_sans_le_drapeau(project):
    rel = _drop(project, "nl.xm", F.make_xm(orders=[0, 0, 0]))
    problems = _problems(project, Music(name="NL", asset=rel, loop=False, loop_section="S",
                                        sections=[MusicSection("S", start=0, end=2, loop=True)]))
    assert _levels(problems) == ["warning"] and "loops anyway" in problems[0][1]


def test_un_jingle_avertit_des_reglages_que_le_build_n_applique_pas(project):
    from core.models.audio import Jingle
    project.jingles.append(Jingle(name="J", asset="assets/jingles/J.xm", tempo=140, fade_in=10,
                                  sections=[MusicSection("S", 0, 1)]))
    ctx = ValidationContext(project)
    validator._check_music_structure(ctx)
    found = [m.message for m in ctx._msgs if m.message.startswith('Jingle "J"')]
    assert len(found) == 1 and "sections, tempo, fades" in found[0]


def test_plus_de_six_sections_avertissent(project):
    rel = _drop(project, "six.xm", F.make_xm(orders=[0] * 10))
    music = Music(name="Six", asset=rel, sections=[MusicSection(f"S{i}", start=i, end=i + 1) for i in range(7)])
    problems = _problems(project, music)
    assert [lvl for lvl, msg in problems if "6 at most" in msg] == ["warning"]
