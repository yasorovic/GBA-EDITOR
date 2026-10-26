"""`actor:clear("Bullet")` : détruit toutes les instances vivantes d'un prefab que la scène fait naître ou déclare, et rend leur
nombre. Il se juge comme `actor:count("Bullet")` : un nom de prefab écrit en toutes lettres, un prefab de cette scène."""
from __future__ import annotations

from scripting.api import RUNTIME_API
from scripting.checker import BuildContext, check
from scripting.codegen import CodegenContext, generate
from scripting.parser import parse


def _c(body: str) -> str:
    ctx = CodegenContext(actor_name="Ctrl", actor_sym="Ctrl", anim_names=["idle"], sfx_names=[], music_names=[],
                         global_names=set(), const_names=set(), all_actor_syms=["Ctrl"], scene_sym="Sc")
    return generate(parse(f"function on_update()\n{body}\nend\n"), ctx)[0]


def _errors(body: str, owner_kind: str = "actor") -> list[str]:
    ctx = BuildContext(actor_name="Ctrl", anim_names=["idle"], sprite_ids=["a"], actor_names=[], prefab_names=["Bullet", "Coin"],
                       pooled_prefab_names=["Bullet"], owner_kind=owner_kind)
    return [e.message for e in check(parse(f"function on_update()\n{body}\nend\n"), ctx) if e.level == "error"]


def test_clear_est_un_appel_c_sur_la_table_du_modele():
    code = _c('actor:clear("Bullet")')
    assert "actor_model_clear(g_model_Sc_Bullet, MODEL_SC_BULLET_COUNT, MODELID_SC_BULLET);" in code


def test_clear_rend_le_nombre_d_instances_detruites():
    code = _c('local n = actor:clear("Bullet")')
    assert "int n = actor_model_clear(g_model_Sc_Bullet, MODEL_SC_BULLET_COUNT, MODELID_SC_BULLET);" in code


def test_un_script_qui_ne_fait_que_clear_ne_fait_pas_naitre_le_prefab():
    """Sans paramètre de domaine prefab, `clear` n'est pas pris pour un `spawn` : la scène ne réserve pas de pool pour lui."""
    assert RUNTIME_API["actor.clear"].params == []
    assert not any(p.domain == "prefab" for p in RUNTIME_API["actor.clear"].params)


def test_un_prefab_que_la_scene_n_a_pas_est_refuse_avec_la_liste():
    erreurs = _errors('actor:clear("Coin")')
    assert len(erreurs) == 1 and "'Coin'" in erreurs[0] and "Bullet" in erreurs[0]


def test_un_prefab_de_la_scene_est_accepte():
    assert _errors('actor:clear("Bullet")') == []


def test_le_nom_du_prefab_est_obligatoire_et_litteral():
    assert any("missing" in e for e in _errors("actor:clear()"))
    assert any("string" in e for e in _errors("local nom = 1\nactor:clear(nom)"))


def test_un_seul_argument():
    assert any("arguments given" in e for e in _errors('actor:clear("Bullet", 2)'))


def test_un_script_de_camera_n_a_pas_d_instances():
    assert any("camera" in e for e in _errors('actor:clear("Bullet")', owner_kind="camera"))
