"""L'API de musique : surcharger à l'appel ce que l'asset règle (ROADMAP « L'asset .music »).

Tempo, hauteur, fondus et section de boucle se posent sur l'ASSET ; ces six appels les
surchargent pour la lecture en cours :

    music:set_tempo(150)            music:fade_in("Theme", 90)
    music:set_pitch(120)            music:fade_out(90)
    music:set_section("Phase 2")    music:leave_loop()

Le comportement du C — la section qui change en cours de route, la sortie de boucle, les
fondus explicites — a été MESURÉ sur ROM le 2026-10-11 (mêmes ROM auto-mesurées que le
reste du chantier). Ces tests tiennent le reste : ce qu'un script devient, ce que le
vérificateur refuse, et que la table des sections et les `MSEC_*` des scripts partent de
la même liste.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))

from codegen.runtime_codegen import sound_emit                         # noqa: E402
from core.models.audio import Jingle, Music, MusicSection, UNIT_MS      # noqa: E402
from core.music_structure import music_section_names, music_section_rows  # noqa: E402
from scripting.checker import BuildContext, check                        # noqa: E402
from scripting.codegen import CodegenContext, generate                   # noqa: E402
from scripting.parser import parse                                       # noqa: E402

SECTIONS = ["Boss", "Main"]          # triés : MSEC_BOSS = 0, MSEC_MAIN = 1


def _lua(src: str, sections=SECTIONS):
    script = parse(src)
    errors = check(script, BuildContext(
        actor_name="Ball", anim_names=["idle"], music_names=["Theme"],
        music_section_names=list(sections)))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=["idle"], sfx_names=[],
        music_names=["Theme"], global_names=set(), const_names=set(), all_actor_syms=["Ball"],
        music_info={"Theme": (True, 100)}, music_section_names=list(sections)))
    return errors, code


def _messages(errors, level="error"):
    return [e.message for e in errors if e.level == level]


# ── Ce que le script devient ──────────────────────────────────────


def test_le_tempo_et_la_hauteur_sont_des_facteurs_q10_replies_au_build():
    errors, code = _lua('function on_start()\n  music:set_tempo(150)\n  music:set_pitch(120)\nend\n')
    assert _messages(errors) == []
    assert "music_set_tempo(1536)" in code and "music_set_pitch(1229)" in code


def test_un_tempo_calcule_se_convertit_a_l_execution():
    """Un pourcentage peut venir d'une variable : la conversion ne peut alors pas être
    pliée au build, mais elle doit avoir lieu (même règle que `music:set_volume`)."""
    errors, code = _lua('function on_update(self)\n  music:set_tempo(niveau)\nend\n')
    assert "music_set_tempo(((niveau) * 1024 / 100))" in code


def test_un_fondu_d_entree_lit_la_boucle_et_le_volume_sur_la_ressource():
    errors, code = _lua('function on_start()\n  music:fade_in("Theme", 90)\nend\n')
    assert _messages(errors) == []
    assert "music_fade_in(MUSIC_THEME, 1, 1024, 90)" in code


def test_un_fondu_de_sortie_prend_ses_frames_de_l_appel():
    errors, code = _lua('function on_start()\n  music:fade_out(90)\nend\n')
    assert _messages(errors) == [] and "music_fade_out(90)" in code


def test_la_section_se_resout_en_constante_et_les_defines_suivent_la_liste_triee():
    errors, code = _lua('function on_start()\n  music:set_section("Main")\nend\n')
    assert _messages(errors) == []
    assert "music_set_section(MSEC_MAIN)" in code
    assert "#define MSEC_BOSS 0" in code and "#define MSEC_MAIN 1" in code


def test_la_sortie_de_boucle_n_a_pas_d_argument():
    errors, code = _lua('function on_start()\n  music:leave_loop()\nend\n')
    assert _messages(errors) == [] and "music_leave_loop()" in code


# ── Ce que le vérificateur refuse ─────────────────────────────────


def test_une_section_que_aucune_musique_ne_porte_est_une_erreur():
    errors, _ = _lua('function on_start()\n  music:set_section("Nope")\nend\n')
    found = _messages(errors)
    assert len(found) == 1 and "no music of the project has a section" in found[0]
    assert "Boss, Main" in found[0]


def test_sans_aucune_section_dans_le_projet_le_message_le_dit():
    errors, _ = _lua('function on_start()\n  music:set_section("Main")\nend\n', sections=[])
    assert "Sections: none" in _messages(errors)[0]


def test_un_fondu_d_entree_sur_une_musique_inconnue_avertit():
    errors, _ = _lua('function on_start()\n  music:fade_in("Nope", 30)\nend\n')
    assert any("not found in the project" in m for m in _messages(errors, "warning"))


# ── La table de main.c et les constantes du script partent de la même liste ──


def _tracker(name: str, sections) -> Music:
    return Music(name=name, asset=f"assets/music/{name}.it", loop_section=sections[0][0],
                 sections=[MusicSection(n, start=a, end=b, loop=True) for n, a, b in sections])


def test_les_noms_de_section_sont_tries_et_sans_doublon():
    boss = _tracker("Boss", [("Main", 4, 12), ("Phase 2", 12, 20)])
    town = _tracker("Town", [("Main", 0, 8)])
    assert music_section_names([boss, town]) == ["Main", "Phase 2"]


def test_un_jingle_et_une_plage_invalide_n_ont_pas_de_section_atteignable():
    jingle = Jingle(name="J", asset="assets/jingles/J.it", sections=[MusicSection("S", 0, 2)])
    wav = Music(name="W", asset="assets/music/W.wav", unit=UNIT_MS,
                sections=[MusicSection("L", start=500, end=2000, loop=True)])
    bad = Music(name="B", asset="assets/music/B.it",
                sections=[MusicSection("Rev", 6, 2), MusicSection("Neg", -1, 3)])
    assert music_section_names([jingle, bad]) == []
    assert music_section_names([wav]) == ["L"]          # un WAV a des sections, lues sur le fichier
    assert music_section_rows(wav) == [] and music_section_rows(bad) == []   # sans fichier, pas d'ordres


def test_la_table_de_main_porte_le_rang_du_nom_et_la_plage():
    boss = _tracker("Boss", [("Main", 4, 12), ("Phase 2", 12, 20)])
    town = _tracker("Town", [("Main", 0, 8)])
    project = SimpleNamespace(music=[boss, town])
    code = "\n".join(sound_emit.music_runtime_lines(
        project, {"music": [(boss, None), (town, None)]}))
    # Rangs : Main = 0, Phase 2 = 1 — ceux des `MSEC_*` du script (test ci-dessus).
    assert "{ MOD_BOSS, 0, 4, 12 }" in code and "{ MOD_BOSS, 1, 12, 20 }" in code
    assert "{ MOD_TOWN, 0, 0, 8 }" in code
    assert "#define MUSIC_SECTION_COUNT 3" in code


def test_les_rangs_ne_dependent_pas_de_ce_qui_est_en_rom():
    """Le rang vient de TOUTES les musiques du projet, comme dans le script : une musique
    laissée hors de la ROM ne décale pas les constantes de celles qui y sont."""
    a = _tracker("A", [("Alpha", 0, 4)])
    b = _tracker("B", [("Beta", 0, 4)])
    project = SimpleNamespace(music=[a, b])
    code = "\n".join(sound_emit.music_runtime_lines(project, {"music": [(b, None)]}))
    assert "{ MOD_B, 1, 0, 4 }" in code            # Beta est le rang 1 même sans Alpha en ROM


def test_sans_section_la_table_reste_valide():
    code = "\n".join(sound_emit.music_runtime_lines(
        SimpleNamespace(music=[]), {"music": []}))
    assert "#define MUSIC_SECTION_COUNT 0" in code and "g_music_sec[MUSIC_SECTION_COUNT + 1]" in code


def test_le_c_definit_les_six_appels_et_la_sortie_de_boucle_arrete_au_retour_arriere():
    code = "\n".join(sound_emit.music_runtime_lines(SimpleNamespace(music=[]), {"music": []}))
    for signature in ("void music_fade_in(", "void music_fade_out(", "void music_set_tempo(",
                      "void music_set_pitch(", "void music_set_section(", "void music_leave_loop("):
        assert signature in code
    # La sortie de boucle : une position qui RECULE est la fin du morceau.
    assert "if(pos < g_mloop_last){ mmStop();" in code
    # tempo et hauteur sont bornés à la plage de maxmod.
    assert "tempo < 0x200 ? 0x200 : tempo > 0x800 ? 0x800 : tempo" in code


def test_sans_soundbank_les_nouveaux_appels_existent_aussi():
    code = "\n".join(sound_emit.music_runtime_stub_lines())
    for name in ("music_fade_in", "music_fade_out", "music_set_tempo", "music_set_pitch",
                 "music_set_section", "music_leave_loop"):
        assert f"void {name}(" in code
