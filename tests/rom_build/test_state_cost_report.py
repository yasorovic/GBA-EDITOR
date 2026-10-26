"""Ce que l'état de script coûte VRAIMENT : le bloc de chaque emplacement a la taille du plus gros état du projet, et tous
les emplacements le paient (`g_obj_state`). Le journal par prefab (`… bytes per instance`) sous-estimait donc le total d'un
facteur égal au nombre d'emplacements ; la ligne `state_cost_line` dit le total et le prefab qui fixe la taille."""
from __future__ import annotations

from types import SimpleNamespace

from codegen.runtime_codegen.lua_compiler import read_state_stride, state_cost_line, write_state_sizes


def _projet(tmp_path, par_scene: dict):
    """Un projet réduit à ce que lisent ces fonctions (`src_dir`), avec les tailles d'état déjà rangées scène par scène."""
    p = SimpleNamespace(src_dir=tmp_path)
    for scene, tailles in par_scene.items():
        write_state_sizes(p, SimpleNamespace(name=scene), tailles)
    return p


def test_sans_aucun_etat_pas_de_ligne(tmp_path):
    assert state_cost_line(_projet(tmp_path, {}), 256) is None
    assert state_cost_line(_projet(tmp_path, {"Tests": {}}), 256) is None


def test_la_ligne_dit_le_total_et_le_prefab_qui_fixe_la_taille(tmp_path):
    p = _projet(tmp_path, {"Tests": {"Tests_Boss": 260, "Tests_Bullet": 4}})
    assert state_cost_line(p, 256) == (
        "[ewram] script state: 260 bytes x 256 slots = 65.0 KiB, set by prefab Boss (scene Tests); "
        "the other prefabs need at most 4 bytes")


def test_le_total_utilise_la_taille_du_bloc_arrondie_au_mot(tmp_path):
    p = _projet(tmp_path, {"S": {"S_Tourelle": 10}})
    assert read_state_stride(p) == 12
    assert "12 bytes x 100 slots = 1.2 KiB" in state_cost_line(p, 100)


def test_le_plus_gros_etat_est_cherche_dans_toutes_les_scenes(tmp_path):
    p = _projet(tmp_path, {"Intro": {"Intro_Garde": 8}, "Niveau": {"Niveau_Chef": 40, "Niveau_Balle": 4}})
    ligne = state_cost_line(p, 10)
    assert "40 bytes x 10 slots" in ligne and "prefab Chef (scene Niveau)" in ligne
    assert "the other prefabs need at most 8 bytes" in ligne          # le second plus gros vient d'une AUTRE scène


def test_un_prefab_seul_n_a_pas_d_autres(tmp_path):
    p = _projet(tmp_path, {"Tests": {"Tests_Boss": 4}})
    assert state_cost_line(p, 256).endswith("the other prefabs need at most 0 bytes")


def test_un_nom_de_scene_a_espaces_garde_le_nom_du_prefab(tmp_path):
    """Le symbole C d'une scène remplace les espaces : le préfixe retiré doit être celui du SYMBOLE, pas du nom."""
    p = _projet(tmp_path, {"Scene 01": {"Scene_01_Boss": 16}})
    assert "prefab Boss (scene Scene 01)" in state_cost_line(p, 5)


def test_un_cache_corrompu_se_lit_comme_aucun_etat(tmp_path):
    (tmp_path / "obj_state_sizes.json").write_text("{pas du json", encoding="utf-8")
    p = SimpleNamespace(src_dir=tmp_path)
    assert state_cost_line(p, 256) is None and read_state_stride(p) == 4


def test_le_build_emet_la_ligne_quand_il_ecrit_le_stride():
    """`main_gen` appelle `state_cost_line` juste après avoir écrit `obj_state.h` : sans cet appel la ligne n'apparaît jamais."""
    import inspect
    from codegen.runtime_codegen import main_gen
    source = inspect.getsource(main_gen)
    assert source.index("OBJ_STATE_STRIDE {read_state_stride(p)}") < source.index("state_cost_line(p, n_actors)")
    assert 'emit("log_line", _state_cost)' in source
