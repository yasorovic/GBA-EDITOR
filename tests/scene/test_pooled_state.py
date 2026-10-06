"""L'état par instance d'un prefab poolé — ce qui ne se verrait pas au `make`.

Un script de prefab poolé est une fonction C partagée par toutes ses instances.
Chaque défaut couvert ici produit du C qui **compile parfaitement** et se trompe
à l'exécution, ou un chiffre de build qui ment :

- une variable écrite par le script émise au scope fichier → les vingt copies
  partagent un compteur, sans un mot ;
- une constante émise par instance → de la mémoire payée seize fois, et une
  mesure qui annonce la longueur de l'en-tête du fichier au lieu de l'état ;
- un tableau de l'état que `pool_init` ne remet pas à zéro → une instance
  respawnée hérite de la précédente ;
- un tableau d'état dimensionné par un littéral au lieu de
  `POOL_<SYM>_INSTANCES` → débordement si les deux divergent.

Cf. ROADMAP v0.7.6.
"""
from __future__ import annotations

import pytest


def _pooled(src: str, pool_size: int = 16):
    """Parse + check + génère le C d'un prefab poolé nommé Ball."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = [e.message for e in check(script, BuildContext(actor_name="Ball"))
              if e.level == "error"]
    code, _warnings, state_bytes = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Ball"], is_pooled=True, pool_size=pool_size))
    return errors, code, state_bytes


# ── Le partage de l'état : ce qui change est à l'instance ─────────


def test_une_variable_ecrite_vit_dans_le_slot_de_l_instance():
    """Le défaut visé : `compteur` émis en `static int compteur` compilerait,
    et les seize balles partageraient le même compteur."""
    _errs, code, _n = _pooled(
        "local compteur = 0\n"
        "function on_update()\n"
        "    compteur = compteur + 1\n"
        "end\n")
    assert "static int compteur" not in code
    assert "_st->compteur = (_st->compteur + 1);" in code
    assert "BallState* _st = &g_state_Ball[Ball_pool_slot(self)];" in code


def _champs(code: str) -> list[str]:
    """Les champs de la structure d'état, dans l'ordre d'émission."""
    if "typedef struct {" not in code:
        return []
    corps = code.split("typedef struct {", 1)[1].split("}", 1)[0]
    return [l.strip() for l in corps.strip().splitlines()]


def test_une_constante_reste_partagee():
    """`FX_POP` n'est assigné nulle part : le recopier dans chaque slot ferait
    payer seize fois une valeur qui ne bouge jamais."""
    _errs, code, state_bytes = _pooled(
        "local FX_POP = 1\n"
        "local fx = 0\n"
        "function on_update()\n"
        "    fx = FX_POP\n"
        "end\n")
    assert "static int FX_POP = 1;" in code
    # L'état, c'est `fx` seul — un entier.
    assert _champs(code) == ["int fx;"]
    assert state_bytes == 4


def test_un_champ_ecrit_par_indexation_est_bien_de_l_etat():
    """`trajet[i] = …` écrit `trajet`, et `vitesse.x = …` écrit `vitesse` :
    c'est le nom à la BASE de la cible qui compte, pas le nœud d'affectation."""
    _errs, code, _n = _pooled(
        "local trajet = array(4)\n"
        "local vitesse = vec2(0, 0)\n"
        "function on_update()\n"
        "    trajet[1] = 3\n"
        "    vitesse.x = 1\n"
        "end\n")
    assert "static int trajet[4]" not in code
    assert "static Vec2 vitesse" not in code
    assert "_st->trajet[0] = 3;" in code


# ── Les trois refus levés (v0.7.1, v0.7.3, et la string) ──────────


@pytest.mark.parametrize("decl,champ,octets", [
    ("local trajet = array(8)\n    trajet[1] = 1", "int trajet[8];", 32),
    ("local vitesse = vec2(1, 2)\n    vitesse.x = 0", "Vec2 vitesse;", 8),
    ("local etat = \"neuf\"\n    etat = \"vieux\"", "const char * etat;", 4),
])
def test_les_types_autrefois_refuses_sont_des_champs(decl, champ, octets):
    """Un tableau, un vec2 et une string d'état étaient refusés parce que
    `Actor.data[8]` ne portait que des entiers. La struct n'a pas cette
    contrainte, donc les refus n'ont plus de raison d'être."""
    head, ligne = decl.split("\n")
    errs, code, state_bytes = _pooled(
        f"{head}\nfunction on_update()\n{ligne}\nend\n")
    assert errs == []
    assert champ in code
    assert state_bytes == octets


# ── La forme du C émis ────────────────────────────────────────────


def test_la_taille_du_tableau_vient_du_define_pas_d_un_litteral():
    """`main.c` boucle sur la plage du pool avec ses propres bornes. Si le
    tableau d'état était dimensionné par un littéral recalculé ici, un écart
    entre les deux serait un débordement muet.

    La constante est `POOL_<SYM>_INSTANCES` et non `_SIZE` : depuis la v0.23 une
    instance de prefab segmenté occupe un GROUPE d'entrées de `g_actors` (la
    racine puis ses parties) mais n'exécute qu'UN script. `_SIZE` compte les
    entrées réservées, `_INSTANCES` compte les scripts — c'est le second qui
    dimensionne l'état, et `_GROUP` qui ramène `self` à son rang d'instance."""
    _errs, code, _n = _pooled(
        "local n = 0\nfunction on_update()\n    n = 1\nend\n", pool_size=16)
    assert "g_state_Ball[POOL_BALL_INSTANCES]" in code
    assert "g_state_Ball[16]" not in code
    assert "(self - g_actors) - POOL_BALL_START" in code
    assert "/ POOL_BALL_GROUP" in code


def test_pool_init_repose_l_etat_de_depart_en_un_bloc():
    """Champ par champ, un tableau de l'état ne serait pas réinitialisable en
    C : une instance respawnée hériterait du trajet de la précédente."""
    _errs, code, _n = _pooled(
        "local trajet = array(4)\n"
        "local fx = 2\n"
        "function on_update()\n"
        "    trajet[1] = 1\n"
        "    fx = 0\n"
        "end\n")
    assert "*_st = (BallState){ .trajet = {0}, .fx = 2 };" in code


def test_l_etat_de_depart_peut_citer_une_constante_du_script():
    """Le défaut que le build a attrapé : `.fx = FX_POP` dans un `static const`
    de fichier ne compile pas — en C, l'initialiseur d'un objet statique doit
    être une constante, et `FX_POP` est une variable. Le littéral composé de
    `pool_init` est en portée bloc, il n'a pas cette contrainte."""
    _errs, code, _n = _pooled(
        "local FX_POP = 1\n"
        "local fx = FX_POP\n"
        "function on_update()\n"
        "    fx = 0\n"
        "end\n")
    assert "static const BallState" not in code
    assert "(BallState){ .fx = FX_POP };" in code


def test_sans_etat_rien_n_est_emis():
    """Un prefab dont le script n'écrit aucune variable de tête ne doit
    produire ni structure, ni tableau, ni fonction de slot — `pool_slot` sans
    appelant, c'est un -Wunused-function à chaque build."""
    _errs, code, state_bytes = _pooled(
        "local SEUIL = 10\nfunction on_update()\n    self:move(1, 0)\nend\n")
    assert "BallState" not in code
    assert "Ball_pool_slot" not in code
    assert state_bytes == 0
    assert "void Ball_pool_init(Actor* self) {" in code


# ── Un acteur de scène n'a qu'une instance ────────────────────────


def test_un_acteur_de_scene_garde_ses_statiques_de_fichier():
    """La séparation écrit/constant ne concerne que les pools : un acteur de
    scène est unique, tout y reste au scope fichier."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    script = parse("local compteur = 0\n"
                   "function on_update()\n    compteur = compteur + 1\nend\n")
    code, _w, state_bytes = generate(script, CodegenContext(
        actor_name="Hero", actor_sym="Hero", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Hero"]))
    assert "static int compteur = 0;" in code
    assert "g_state_Hero" not in code
    assert state_bytes == 0
