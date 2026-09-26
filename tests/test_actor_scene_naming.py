"""L'acteur appartient à sa scène (ROADMAP « L'acteur appartient à sa scène »).

Son NOM est local à la scène — deux scènes peuvent chacune poser un « Cursor » —
tandis que son SYMBOLE C est qualifié par la scène (`<Scène>_<Acteur>`), comme un
prefab poolé l'est déjà. Deux conséquences vérifiées ici :

  ① le validateur n'exige l'unicité que DANS une scène (décision B) — réutiliser
    un nom d'une scène à l'autre ne produit plus d'avertissement, un doublon dans
    la MÊME scène en produit un ;
  ② le symbole émis (`scene_actor_sym`) est bien qualifié, donc deux « Cursor »
    ne partagent plus `TAG_CURSOR` ni `actor_Cursor.c`.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "editor"))

from core.models.scene import Scene, Actor
from core.validator import _check_actor_name_collisions
from codegen.c_names import scene_actor_sym, sym as c_sym


class _Ctx:
    def __init__(self, scenes):
        self.project = type("P", (), {"scenes": scenes})()
        self.msgs: list[str] = []

    def warn(self, _actor, message, target=None):
        self.msgs.append(message)


def test_nom_reutilise_entre_scenes_ne_collisionne_plus():
    a = Scene(name="A"); a.actors = [Actor(name="Cursor")]
    b = Scene(name="B"); b.actors = [Actor(name="Cursor")]
    ctx = _Ctx([a, b])
    _check_actor_name_collisions(ctx)
    assert ctx.msgs == [], ctx.msgs


def test_doublon_dans_une_meme_scene_avertit():
    s = Scene(name="S")
    s.actors = [Actor(name="Cursor"), Actor(name="Cursor")]
    ctx = _Ctx([s])
    _check_actor_name_collisions(ctx)
    assert len(ctx.msgs) == 1
    assert "même scène" in ctx.msgs[0] or "scène 'S'" in ctx.msgs[0]


def _gen(body: str, **ctx_kw):
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = f"function on_update()\n{body}\nend\n"
    base = dict(actor_name="Cam", actor_sym="Cam", anim_names=[], sfx_names=[],
                music_names=[], global_names=set(), const_names=set(),
                all_actor_syms=["Foe"])
    base.update(ctx_kw)
    code, _, _ = generate(parse(src), CodegenContext(**base))
    return code


def test_get_actor_dans_un_script_de_scene_resout_a_la_compilation():
    """Une scène connue → TAG qualifié + filtre `actor_live` (nil si détruit,
    décision C')."""
    code = _gen('    local u = actor:get("Foe")', scene_sym="Arena")
    assert "actor_live(&g_actors[TAG_ARENA_FOE])" in code
    assert "runtime_get_actor" not in code


def test_get_actor_dans_un_script_partage_resout_au_runtime():
    """Pas de scène (script de caméra partagé) → lookup runtime nullable par
    ACTORNAME (décision C)."""
    code = _gen('    local u = actor:get("Foe")', scene_sym="")
    assert "runtime_get_actor(ACTORNAME_FOE)" in code
    assert "TAG_" not in code


def test_get_actor_par_index_dynamique():
    """actor:get(i) — adressage dynamique 1-based → slot 0-based borné
    (`actor_at`), même repli 1→0 que data.Table[i]."""
    code = _gen('    local u = actor:get(i)', scene_sym="Arena")
    assert "actor_at((i) - 1)" in code
    assert "Actor* u" in code           # typé Actor*, pas int


def test_get_actor_index_litteral_est_replie():
    """Un index littéral est replié tout de suite : actor:get(2) → actor_at(1)."""
    code = _gen('    local u = actor:get(2)', scene_sym="Arena")
    assert "actor_at(1)" in code


def test_actor_count_rend_le_compte_de_la_scene_active():
    code = _gen('    local n = actor:count()', scene_sym="Arena")
    assert "g_scene_placed" in code


def test_symbole_dacteur_pose_est_qualifie_par_la_scene():
    # Le symbole d'un acteur posé porte sa scène — jamais le nom nu.
    assert scene_actor_sym("Battlefield", "Cursor") == "Battlefield_Cursor"
    # Deux scènes, même nom d'acteur → deux symboles distincts.
    assert (scene_actor_sym("A", "Cursor")
            != scene_actor_sym("B", "Cursor"))
    # Un nom d'auteur non-C reste assaini par `sym` de part et d'autre.
    assert scene_actor_sym("Zone 1", "Foe-2") == f"{c_sym('Zone 1')}_{c_sym('Foe-2')}"
