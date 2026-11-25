"""Déclarer et manipuler une grille RAM depuis un script : `grid(cols, rows, step)`.

Une grille RAM est une VARIABLE, déclarée comme `array`, mais d'un octet par case
et munie d'un pas en pixels (puissance de deux). Elle complète les grilles peintes
de `data.grid` (en ROM, lecture seule) : celle-ci se lit ET s'écrit, par case
`g[x][y]` (colonne puis rangée, à partir de 1) et par pixel `g:value_at(px, py)` ;
`g.cols` / `g.rows` donnent la taille. L'ANALYSE de passage (coût, chemin, flux,
vue, échantillon de collision) n'est plus une méthode de grille : elle passe par
le module `navigation`, qui prend la grille en argument (renommage 2026-11-24).

Le dernier test compile ensemble les inlines du moteur et les expressions que le
traducteur vient d'émettre, avec un vrai tableau à plat : c'est le test de
comportement du C réellement émis que la règle de zone réclame.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement
from scripting.checker import BuildContext, check
from scripting.codegen import CodegenContext, generate
from scripting.parser import parse

REPO_DIR = Path(__file__).resolve().parents[2]
NATIVE_DIR = Path(__file__).resolve().parents[1] / "native"
MOTEUR_DIR = REPO_DIR / "runtime" / "include"

DECL = "local terrain = grid(4, 3, 16)\n"


def _script(corps: str, decl: str = DECL) -> str:
    return f"{decl}function on_update()\n{corps}\nend\n"


def _erreurs(corps: str, decl: str = DECL) -> list[str]:
    ctx = BuildContext(actor_name="Ball", scene_label="Arena")
    return [e.message for e in check(parse(_script(corps, decl)), ctx) if e.level == "error"]


def _emis(corps: str, decl: str = DECL) -> str:
    code, _globals, _consts = generate(parse(_script(corps, decl)), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[], music_names=[],
        global_names=set(), const_names=set(), all_actor_syms=["Ball"], scene_sym="Arena"))
    return code


def _expression(corps: str) -> str:
    """La seule expression émise par `local v = …`, sans son habillage."""
    (ligne,) = [L.strip() for L in _emis(corps).splitlines() if L.strip().startswith("int v =")]
    return ligne[len("int v ="):].strip().rstrip(";")


def _statement(corps: str, prefixe: str) -> str:
    """La seule instruction émise qui commence par `prefixe`, sans son `;`."""
    (ligne,) = [L.strip() for L in _emis(corps).splitlines() if L.strip().startswith(prefixe)]
    return ligne.rstrip(";")


# ── Ce que le vérificateur accepte ────────────────────────────────

def test_declaration_et_acces_passent():
    assert _erreurs("local v = terrain:value_at(32, 16)") == []
    assert _erreurs("local v = terrain[2][1]") == []
    assert _erreurs("local v = terrain[x][y]") == []
    assert _erreurs("terrain[1][1] = 5") == []
    assert _erreurs("local c = terrain.cols\nlocal r = terrain.rows") == []


def test_les_operations_de_remplissage_passent():
    assert _erreurs("terrain:fill(0)") == []
    assert _erreurs("terrain:fill_rect(1, 1, 2, 3, 5)") == []


FLOOD_DECL = "local portee = grid(4, 3, 16)\nlocal sol = grid(4, 3, 16)\nlocal couts = array(3)\n"


def test_spread_from_passe_avec_et_sans_carte_de_blocage():
    assert _erreurs("navigation:spread_from(portee, 1, 1, 5, sol, couts)", decl=FLOOD_DECL) == []
    assert _erreurs("navigation:spread_from(portee, 1, 1, 5, sol, couts, sol)", decl=FLOOD_DECL) == []


PATH_DECL = FLOOD_DECL + "local pas = array(8)\n"


def test_path_to_passe():
    assert _erreurs("local n = navigation:path_to(portee, 3, 2, pas)", decl=PATH_DECL) == []


def test_line_of_sight_passe():
    assert _erreurs("local v = navigation:line_of_sight(terrain, 1, 1, 3, 3)") == []


FLOW_DECL = FLOOD_DECL + "local flux = grid(4, 3, 16)\n"


def test_make_flow_passe():
    assert _erreurs("navigation:make_flow(portee, flux)", decl=FLOW_DECL) == []


REGIONS_DECL = DECL + "local zones = grid(4, 3, 16)\n"


def test_regions_passe():
    assert _erreurs("local n = terrain:regions(zones)", decl=REGIONS_DECL) == []


def test_sample_collision_passe():
    assert _erreurs("navigation:sample_collision(ai)", decl="local ai = grid(2, 2, 16)\n") == []


def test_sample_collision_prend_un_argument():
    (msg,) = _erreurs("navigation:sample_collision(ai, 1)", decl="local ai = grid(2, 2, 16)\n")
    assert "takes 1 argument(s)" in msg and ":sample_collision(out)" in msg


def test_le_pas_est_optionnel():
    assert _erreurs("local v = terrain:value_at(0, 0)", decl="local terrain = grid(4, 3)\n") == []


# ── Ce qu'il refuse ───────────────────────────────────────────────

def test_une_declaration_mal_formee_est_refusee():
    (msg,) = _erreurs("local v = 0", decl="local t = grid(4)\n")
    assert "two or three sizes expected" in msg


def test_un_pas_hors_des_puissances_de_deux_est_refuse():
    (msg,) = _erreurs("local v = 0", decl="local t = grid(4, 3, 12)\n")
    assert "cell step in pixels (8, 16, 32" in msg


def test_une_grille_citee_seule_n_est_pas_une_valeur():
    (msg,) = _erreurs("local v = terrain")
    assert "is a grid: a grid is not a value" in msg


def test_une_grille_ne_se_reaffecte_pas_nue():
    (msg,) = _erreurs("terrain = 5")
    assert "is a grid: a grid is not a value" in msg


def test_une_case_hors_bornes_est_refusee_quand_elle_est_ecrite_en_clair():
    (msg,) = _erreurs("local v = terrain[9][1]")
    assert "out of bounds on x" in msg and "from 1 to 4" in msg
    (msg,) = _erreurs("local v = terrain[1][7]")
    assert "out of bounds on y" in msg and "from 1 to 3" in msg


def test_une_seule_dimension_ne_designe_pas_une_case():
    (msg,) = _erreurs("local v = terrain[1]")
    assert "grid of two dimensions" in msg


def test_une_methode_inconnue_est_refusee():
    (msg,) = _erreurs("local v = terrain:lire(1, 2)")
    assert "a grid's methods are :value_at, :contains, :fill, :fill_rect, :copy_from, :regions" in msg


def test_value_at_prend_deux_arguments():
    (msg,) = _erreurs("local v = terrain:value_at(1)")
    assert "takes 2 argument(s)" in msg and ":value_at(x, y)" in msg


def test_fill_prend_un_argument():
    (msg,) = _erreurs("terrain:fill(1, 2)")
    assert "takes 1 argument(s)" in msg and ":fill(value)" in msg


def test_fill_rect_prend_cinq_arguments():
    (msg,) = _erreurs("terrain:fill_rect(1, 1, 2, 2)")
    assert "takes 5 argument(s)" in msg and ":fill_rect(x, y, w, h, value)" in msg


def test_spread_from_prend_quatre_six_ou_sept_arguments():
    (msg,) = _erreurs("navigation:spread_from(portee, 1, 1, 5, sol)", decl=FLOOD_DECL)
    assert "takes 4 or 6 or 7 argument(s)" in msg


def test_spread_from_sans_terrain_est_un_cout_uniforme():
    """`spread_from(out, x, y, budget)` : terrain et coûts facultatifs, rien à signaler."""
    assert _erreurs("navigation:spread_from(portee, 1, 1, 5)", decl=FLOOD_DECL) == []


def test_spread_from_refuse_un_terrain_qui_n_est_pas_une_grille():
    (msg,) = _erreurs("navigation:spread_from(portee, 1, 1, 5, couts, couts)", decl=FLOOD_DECL)
    assert "the 5th argument, the terrain," in msg


def test_spread_from_refuse_des_couts_qui_ne_sont_pas_un_array():
    (msg,) = _erreurs("navigation:spread_from(portee, 1, 1, 5, sol, sol)", decl=FLOOD_DECL)
    assert "the 6th argument is the costs, an array" in msg


def test_path_to_prend_quatre_arguments():
    (msg,) = _erreurs("navigation:path_to(portee, 3, 2)", decl=PATH_DECL)
    assert "takes 4 argument(s)" in msg and ":path_to(cost_map, x, y, out)" in msg


def test_direction_at_prend_une_position_vec2():
    """`direction_at` prend une grille et une position monde (un vec2)."""
    assert _erreurs("local d = navigation:direction_at(flux, self.position)",
                    decl="local flux = grid(4, 3, 16)\n") == []
    (msg,) = _erreurs("local d = navigation:direction_at(flux, 2, 1)",
                      decl="local flux = grid(4, 3, 16)\n")
    assert "takes 2 argument(s)" in msg


def test_direction_at_refuse_une_position_scalaire():
    (msg,) = _erreurs("local d = navigation:direction_at(flux, 3)",
                      decl="local flux = grid(4, 3, 16)\n")
    assert "a world position, a vec2" in msg


def test_direction_at_rend_un_vec2():
    """Le résultat est un vec2 : il s'affecte à une vélocité et se met à l'échelle."""
    code = _emis("self.velocity = navigation:direction_at(flux, self.position) * 220",
                 decl="local flux = grid(4, 3, 16)\n")
    assert "grid_step_at(flux, 4, 3, 4," in code
    assert "vec2_scale(" in code


def test_flow_to_sans_budget_emet_la_portee_maximale():
    """`flow_to(out, position)` : une seule grille, l'inline fait tout en interne."""
    code = _emis("navigation:flow_to(flux, self.position)", decl="local flux = grid(4, 3, 16)\n")
    assert "grid_target(flux, 4, 3, 4," in code and ", 254)" in code


def test_flow_to_accepte_un_budget():
    code = _emis("navigation:flow_to(flux, self.position, 6)", decl="local flux = grid(4, 3, 16)\n")
    assert "grid_target(flux, 4, 3, 4," in code and ", 6)" in code


def test_flow_to_refuse_une_position_scalaire():
    (msg,) = _erreurs("navigation:flow_to(flux, 3)", decl="local flux = grid(4, 3, 16)\n")
    assert "a world position, a vec2" in msg


def test_flow_to_refuse_une_grille_trop_grande():
    """Le scratch interne borne la taille (GRID_TARGET_MAX = 1024 cases)."""
    (msg,) = _erreurs("navigation:flow_to(flux, self.position)", decl="local flux = grid(40, 30, 8)\n")
    assert "too large" in msg and "1024 cells" in msg


def test_path_to_refuse_une_sortie_qui_n_est_pas_un_array():
    (msg,) = _erreurs("local n = navigation:path_to(portee, 3, 2, sol)", decl=PATH_DECL)
    assert "the 4th argument is the output, an array" in msg


def test_line_of_sight_prend_cinq_arguments():
    (msg,) = _erreurs("local v = navigation:line_of_sight(terrain, 1, 1, 3)")
    assert "takes 5 argument(s)" in msg and ":line_of_sight(blockers, x0, y0, x1, y1)" in msg


def test_make_flow_prend_deux_arguments():
    (msg,) = _erreurs("navigation:make_flow(portee)", decl=FLOW_DECL)
    assert "takes 2 argument(s)" in msg and ":make_flow(cost_map, out)" in msg


def test_make_flow_refuse_une_sortie_qui_n_est_pas_une_grille():
    (msg,) = _erreurs("navigation:make_flow(portee, couts)", decl=FLOW_DECL)
    assert "the second argument is the output, a writable grid" in msg


def test_regions_prend_un_argument():
    (msg,) = _erreurs("terrain:regions()", decl=REGIONS_DECL)
    assert "takes 1 argument(s)" in msg and ":regions(out)" in msg


def test_regions_refuse_une_sortie_qui_n_est_pas_une_grille():
    (msg,) = _erreurs("local n = terrain:regions(sac)",
                      decl=REGIONS_DECL + "local sac = array(4)\n")
    assert "the argument is the output, a writable grid" in msg


def test_une_grille_peinte_reste_en_lecture_seule():
    """`fill` sur une grille peinte est refusé : elle est en ROM, pas de `self._grids`
    pour elle. Juge dans le contexte d'une scène, via le chemin `data.grid`."""
    from codegen.runtime_codegen.grids import scene_grid_access
    from core.models.grid import Grid, GridValue
    from core.models.scene import Scene
    scene = Scene(name="Arena", grids=[Grid(name="Terrain", step=16,
                  values=[GridValue(value=1, name="HERBE")], cells=[[0, 1], [1, 0]])])
    ctx = BuildContext(actor_name="Ball", scene_label="Arena",
                       scene_grids=scene_grid_access(scene))
    msgs = [e.message for e in check(parse(_script("data.grid.Terrain:fill(0)", decl="")), ctx)
            if e.level == "error"]
    assert any("read-only" in m for m in msgs)


def test_un_champ_inconnu_est_refuse():
    (msg,) = _erreurs("local v = terrain.width")
    assert "a grid exposes only .cols and .rows" in msg


def test_une_dimension_ne_s_ecrit_pas():
    (msg,) = _erreurs("terrain.cols = 5")
    assert "read-only" in msg and "a grid's size is fixed at build" in msg


# ── Ce que le traducteur émet ─────────────────────────────────────

def test_la_declaration_emet_un_tableau_d_octets_a_plat():
    assert "static unsigned char terrain[12] = {0};" in _emis("local v = terrain[1][1]")


def test_l_acces_par_case_indexe_le_tableau_a_plat():
    assert _expression("local v = terrain[2][1]") == "terrain[(0) * 4 + (1)]"
    assert _expression("local v = terrain[x][y]") == "terrain[((y) - 1) * 4 + ((x) - 1)]"


def test_l_acces_par_pixel_passe_par_l_inline_du_moteur():
    assert _expression("local v = terrain:value_at(32, 16)") == (
        "grid_value_at(terrain, 4, 3, 4, 32, 16)")


def test_les_dimensions_sont_des_litteraux():
    assert _expression("local v = terrain.cols") == "4"
    assert _expression("local v = terrain.rows") == "3"


def test_l_ecriture_d_une_case_cible_le_tableau_a_plat():
    ligne = next(L.strip() for L in _emis("terrain[3][2] = 7").splitlines()
                 if L.strip().startswith("terrain["))
    assert ligne == "terrain[(1) * 4 + (2)] = 7;"


def test_fill_remplit_toutes_les_cases():
    assert _statement("terrain:fill(5)", "grid_fill(") == "grid_fill(terrain, 12, 5)"


def test_fill_rect_ramene_l_origine_en_base_zero():
    assert _statement("terrain:fill_rect(2, 1, 3, 2, 9)", "grid_fill_rect(") == (
        "grid_fill_rect(terrain, 4, 3, 1, 0, 3, 2, 9)")
    assert _statement("terrain:fill_rect(a, b, w, h, v)", "grid_fill_rect(") == (
        "grid_fill_rect(terrain, 4, 3, (a) - 1, (b) - 1, w, h, v)")


def _emis_flood(corps: str) -> str:
    code, _g, _c = generate(parse(f"{FLOOD_DECL}function on_update()\n{corps}\nend\n"), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[], music_names=[],
        global_names=set(), const_names=set(), all_actor_syms=["Ball"], scene_sym="Arena"))
    return code


def test_spread_from_emet_un_appel_avec_les_pointeurs_et_l_origine_en_base_zero():
    ligne = next(L.strip() for L in
                 _emis_flood("navigation:spread_from(portee, sx, sy, b, sol, couts)").splitlines()
                 if L.strip().startswith("grid_flood(")).rstrip(";")
    assert ligne == "grid_flood(portee, sol, 0, 4, 3, (sx) - 1, (sy) - 1, b, couts, 3)"


def test_spread_from_passe_la_carte_de_blocage_quand_elle_est_donnee():
    ligne = next(L.strip() for L in
                 _emis_flood("navigation:spread_from(portee, 1, 1, 5, sol, couts, sol)").splitlines()
                 if L.strip().startswith("grid_flood(")).rstrip(";")
    assert ligne == "grid_flood(portee, sol, sol, 4, 3, 0, 0, 5, couts, 3)"


def _emis_path(corps: str) -> str:
    code, _g, _c = generate(parse(f"{PATH_DECL}function on_update()\n{corps}\nend\n"), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[], music_names=[],
        global_names=set(), const_names=set(), all_actor_syms=["Ball"], scene_sym="Arena"))
    return code


def test_path_to_emet_un_appel_avec_la_sortie_et_sa_longueur():
    ligne = next(L.strip() for L in
                 _emis_path("local n = navigation:path_to(portee, tx, ty, pas)").splitlines()
                 if "grid_path_to(" in L).rstrip(";")
    assert ligne == "int n = grid_path_to(portee, 4, 3, (tx) - 1, (ty) - 1, pas, 8)"


def test_line_of_sight_emet_un_appel_base_zero():
    ligne = next(L.strip() for L in
                 _emis("local v = navigation:line_of_sight(terrain, a, b, c, d)").splitlines()
                 if "grid_line_of_sight(" in L).rstrip(";")
    assert ligne == ("int v = grid_line_of_sight(terrain, 4, 3, "
                     "(a) - 1, (b) - 1, (c) - 1, (d) - 1)")


def _emis_flow(corps: str) -> str:
    code, _g, _c = generate(parse(f"{FLOW_DECL}function on_update()\n{corps}\nend\n"), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[], music_names=[],
        global_names=set(), const_names=set(), all_actor_syms=["Ball"], scene_sym="Arena"))
    return code


def test_make_flow_emet_un_appel_avec_les_deux_grilles():
    ligne = next(L.strip() for L in _emis_flow("navigation:make_flow(portee, flux)").splitlines()
                 if "grid_flow_map(" in L).rstrip(";")
    assert ligne == "grid_flow_map(portee, flux, 4, 3)"


def test_regions_emet_un_appel_avec_les_deux_grilles():
    ligne = next(L.strip() for L in _emis("local n = terrain:regions(zones)",
                                           decl=REGIONS_DECL).splitlines()
                 if "grid_regions(" in L).rstrip(";")
    assert ligne == "int n = grid_regions(terrain, zones, 4, 3)"


def test_sample_collision_emet_l_appel_avec_le_pas():
    ligne = next(L.strip() for L in _emis("navigation:sample_collision(ai)",
                                          decl="local ai = grid(2, 2, 16)\n").splitlines()
                 if "collision_sample(" in L).rstrip(";")
    assert ligne == "collision_sample(ai, 2, 2, 16)"


# ── Tranche 2 : contains, copy_from, reachable, cost_at, arrived ───

COPY_DECL = DECL + "local src = grid(4, 3, 16)\n"
NAV2_DECL = "local field = grid(4, 3, 16)\n"


def test_contains_passe():
    assert _erreurs("local b = terrain:contains(32, 16)") == []


def test_contains_prend_deux_arguments():
    (msg,) = _erreurs("local b = terrain:contains(1)")
    assert "takes 2 argument(s)" in msg and ":contains(x, y)" in msg


def test_contains_emet_la_geometrie_sans_pointeur():
    """`contains` ne lit aucune case : juste la géométrie, pas de pointeur de grille."""
    assert _expression("local v = terrain:contains(32, 16)") == "grid_contains(4, 3, 4, 32, 16)"


def test_copy_from_passe():
    assert _erreurs("terrain:copy_from(src)", decl=COPY_DECL) == []


def test_copy_from_refuse_une_source_qui_n_est_pas_une_grille():
    (msg,) = _erreurs("terrain:copy_from(5)", decl=COPY_DECL)
    assert "the argument is the source, a grid" in msg


def test_copy_from_refuse_une_geometrie_differente():
    (msg,) = _erreurs("terrain:copy_from(small)", decl=DECL + "local small = grid(2, 2, 16)\n")
    assert "same geometry" in msg


def test_copy_from_emet_une_copie_de_n_cases():
    ligne = next(L.strip() for L in _emis("terrain:copy_from(src)", decl=COPY_DECL).splitlines()
                 if L.strip().startswith("grid_copy_from(")).rstrip(";")
    assert ligne == "grid_copy_from(terrain, src, 12)"


def test_reachable_cost_at_arrived_passent():
    assert _erreurs("local b = navigation:reachable(field, self.position)", decl=NAV2_DECL) == []
    assert _erreurs("local c = navigation:cost_at(field, self.position)", decl=NAV2_DECL) == []
    assert _erreurs("local b = navigation:arrived(field, self.position)", decl=NAV2_DECL) == []


def test_reachable_refuse_une_position_scalaire():
    (msg,) = _erreurs("local b = navigation:reachable(field, 3)", decl=NAV2_DECL)
    assert "a world position, a vec2" in msg


def test_cost_at_refuse_un_premier_argument_non_grille():
    (msg,) = _erreurs("local c = navigation:cost_at(sac, self.position)", decl="local sac = array(4)\n")
    assert "the first argument, the cost map," in msg


def test_reachable_cost_at_arrived_emettent_leur_inline():
    assert "grid_reachable(field, 4, 3, 4," in _emis(
        "local b = navigation:reachable(field, self.position)", decl=NAV2_DECL)
    assert "grid_cost_at(field, 4, 3, 4," in _emis(
        "local c = navigation:cost_at(field, self.position)", decl=NAV2_DECL)
    assert "grid_arrived(field, 4, 3, 4," in _emis(
        "local b = navigation:arrived(field, self.position)", decl=NAV2_DECL)


# ── Navigation sans grille : arrive, keep_distance ────────────────

def test_arrive_et_keep_distance_passent():
    assert _erreurs("local d = navigation:arrive(self.position, self.position, 8, 48, 2)") == []
    assert _erreurs("local d = navigation:keep_distance(self.position, self.position, 16, 64, 2)") == []


def test_arrive_prend_cinq_arguments():
    (msg,) = _erreurs("local d = navigation:arrive(self.position, self.position, 8, 48)")
    assert ("takes 5 argument(s)" in msg
            and ":arrive(position, target, stop_radius, slow_radius, max_speed)" in msg)


def test_arrive_refuse_une_cible_non_vec2():
    (msg,) = _erreurs("local d = navigation:arrive(self.position, 3, 8, 48, 2)")
    assert "the second argument, the target," in msg


def test_keep_distance_refuse_une_position_non_vec2():
    (msg,) = _erreurs("local d = navigation:keep_distance(3, self.position, 16, 64, 2)")
    assert "the first argument, the position," in msg


def test_arrive_et_keep_distance_emettent_leur_inline():
    assert "nav_arrive(actor_get_position(self), actor_get_position(self), 8, 48, 2)" in _emis(
        "local d = navigation:arrive(self.position, self.position, 8, 48, 2)")
    assert "nav_keep_distance(actor_get_position(self), actor_get_position(self), 16, 64, 2)" in _emis(
        "local d = navigation:keep_distance(self.position, self.position, 16, 64, 2)")


# ── Le C réellement émis, compilé et exécuté ──────────────────────

def _inline_du_moteur() -> str:
    """Les inlines de grille du moteur, extraits sans l'en-tête entier (qui réclame
    tout l'état du runtime). Renommées ou déplacées, l'extraction échoue."""
    source = (MOTEUR_DIR / "runtime_api_inline.h").read_text(encoding="utf-8")
    morceaux = []
    for signature in (r"static inline int grid_value_at\(.*?\n\}\n",
                      r"static inline void grid_fill\(.*?\n\}\n",
                      r"static inline void grid_fill_rect\(.*?\n\}\n",
                      r"static inline void grid_flood\(.*?\n\}\n",
                      r"static inline int grid_path_to\(.*?\n\}\n",
                      r"static inline int grid_line_of_sight\(.*?\n\}\n",
                      r"static inline void grid_flow_map\(.*?\n\}\n",
                      r"static inline int grid_regions\(.*?\n\}\n",
                      r"static inline int grid_contains\(.*?\n\}\n",
                      r"static inline void grid_copy_from\(.*?\n\}\n",
                      r"static inline int grid_reachable\(.*?\n\}\n",
                      r"static inline int grid_cost_at\(.*?\n\}\n",
                      r"static inline int grid_arrived\(.*?\n\}\n",
                      r"static inline int isqrt\(.*?\n\}\n",
                      r"static inline Vec2 nav_arrive\(.*?\n\}\n",
                      r"static inline Vec2 nav_keep_distance\(.*?\n\}\n"):
        trouve = re.search(signature, source, re.S)
        assert trouve, f"inline introuvable dans runtime_api_inline.h : {signature}"
        morceaux.append(trouve.group(0))
    return "\n".join(morceaux)


def test_la_sonde_ecrit_et_relit_dans_le_c_emis(tmp_path):
    compilateur = compilateur_hote()
    if compilateur is None:
        message = ("aucun compilateur C hôte (cc/gcc/clang, ou CC=...) — "
                   "la grille RAM n'est PAS vérifiée sur le C émis")
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; elle l'est en CI")

    (tmp_path / "grid_inline.h").write_text(_inline_du_moteur(), encoding="utf-8")

    # Les expressions du traducteur, paramétrées par leurs coordonnées : le
    # littéral écrit dans le script devient le paramètre de la macro. La case est
    # une lvalue, donc elle sert à l'écriture comme à la lecture.
    at = _expression("local v = terrain:value_at(111, 222)").replace("111", "(px)").replace("222", "(py)")
    cell = _expression("local v = terrain[x][y]")
    fill = _statement("terrain:fill(v)", "grid_fill(")
    fill_rect = _statement("terrain:fill_rect(x, y, w, h, v)", "grid_fill_rect(")
    flood = next(L.strip() for L in
                 _emis_flood("navigation:spread_from(portee, sx, sy, b, sol, couts)").splitlines()
                 if L.strip().startswith("grid_flood(")).rstrip(";")
    path = next(L.strip() for L in
                _emis_path("local n = navigation:path_to(portee, tx, ty, pas)").splitlines()
                if "grid_path_to(" in L)
    path = path[path.index("grid_path_to"):].rstrip(";")
    los = next(L.strip() for L in
               _emis("local v = navigation:line_of_sight(terrain, x0, y0, x1, y1)").splitlines()
               if "grid_line_of_sight(" in L)
    los = los[los.index("grid_line_of_sight"):].rstrip(";")
    flow = next(L.strip() for L in _emis_flow("navigation:make_flow(portee, flux)").splitlines()
                if "grid_flow_map(" in L).rstrip(";")
    regions = next(L.strip() for L in _emis("local n = terrain:regions(zones)",
                                             decl=REGIONS_DECL).splitlines()
                   if "grid_regions(" in L)
    regions = regions[regions.index("grid_regions"):].rstrip(";")

    # Tranche 2 : contains (géométrie seule), copy_from (statement), et les trois
    # lecteurs de sentinelle du module navigation (position en vec2 littéral,
    # paramétrée par (px, py) comme `at`).
    contains = _expression("local v = terrain:contains(111, 222)").replace("111", "(px)").replace("222", "(py)")
    copy = next(L.strip() for L in _emis("terrain:copy_from(src)", decl=COPY_DECL).splitlines()
                if L.strip().startswith("grid_copy_from(")).rstrip(";")

    def _nav2(call: str, fn: str) -> str:
        code = _emis(f"local v = {call}",
                     decl="local portee = grid(4, 3, 16)\nlocal flux = grid(4, 3, 16)\n")
        ligne = next(L.strip() for L in code.splitlines() if fn in L)
        return ligne[ligne.index(fn):].rstrip(";").replace("111", "(px)").replace("222", "(py)")

    reach = _nav2("navigation:reachable(portee, vec2(111, 222))", "grid_reachable(")
    cost = _nav2("navigation:cost_at(portee, vec2(111, 222))", "grid_cost_at(")
    arrived = _nav2("navigation:arrived(flux, vec2(111, 222))", "grid_arrived(")

    # Navigation sans grille : deux positions vec2 + trois entiers, paramétrés par
    # des littéraux distincts (901..907) remplacés par les arguments de la macro.
    def _steer(call: str, fn: str) -> str:
        ligne = next(L.strip() for L in _emis(f"local v = {call}").splitlines() if fn in L)
        expr = ligne[ligne.index(fn):].rstrip(";")
        for lit, arg in (("901", "(px)"), ("902", "(py)"), ("903", "(tx)"),
                         ("904", "(ty)"), ("905", "(a)"), ("906", "(b)"), ("907", "(c)")):
            expr = expr.replace(lit, arg)
        return expr

    arrive = _steer("navigation:arrive(vec2(901, 902), vec2(903, 904), 905, 906, 907)", "nav_arrive(")
    keep = _steer("navigation:keep_distance(vec2(901, 902), vec2(903, 904), 905, 906, 907)",
                  "nav_keep_distance(")
    (tmp_path / "grid_ram_expr.h").write_text(
        "#define GRID_RAM_COLS 4\n"
        "#define GRID_RAM_ROWS 3\n"
        "#define GRID_RAM_STEP 16\n"
        "#define GRID_RAM_AT(px, py) " + at + "\n"
        "#define GRID_RAM_CELL(x, y) " + cell + "\n"
        "#define GRID_RAM_FILL(v) " + fill + "\n"
        "#define GRID_RAM_FILL_RECT(x, y, w, h, v) " + fill_rect + "\n"
        "#define GRID_RAM_FLOOD(sx, sy, b) " + flood + "\n"
        "#define GRID_RAM_PATH(tx, ty) " + path + "\n"
        "#define GRID_RAM_LOS(x0, y0, x1, y1) " + los + "\n"
        "#define GRID_RAM_FLOW " + flow + "\n"
        "#define GRID_RAM_REGIONS " + regions + "\n"
        "#define GRID_RAM_CONTAINS(px, py) " + contains + "\n"
        "#define GRID_RAM_COPY " + copy + "\n"
        "#define GRID_RAM_REACH(px, py) " + reach + "\n"
        "#define GRID_RAM_COST(px, py) " + cost + "\n"
        "#define GRID_RAM_ARRIVED(px, py) " + arrived + "\n"
        "#define GRID_RAM_ARRIVE(px, py, tx, ty, a, b, c) " + arrive + "\n"
        "#define GRID_RAM_KEEP(px, py, tx, ty, a, b, c) " + keep + "\n", encoding="utf-8")

    binaire = tmp_path / "grid_ram_probe"
    env = environnement(compilateur)
    compile = subprocess.run(
        [compilateur, "-std=c11", "-Wall", "-Werror", "-O0", "-I", str(tmp_path),
         str(NATIVE_DIR / "grid_ram_probe.c"), "-o", str(binaire)],
        capture_output=True, text=True, env=env)
    assert compile.returncode == 0, f"le C émis ne compile pas :\n{compile.stderr}"

    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    sortie = dict(re.match(r"(\w+) (.*)", L).groups() for L in run.stdout.strip().splitlines())

    # Chaque case reçoit `y * cols + x` par ÉCRITURE indexée, relue par case puis
    # par pixel au centre de la case : les deux chemins voient ce que la sonde a
    # écrit, et hors de la grille vaut 0.
    attendu = [str(y * 4 + x) for y in range(1, 4) for x in range(1, 5)]
    assert sortie["CELL"].split() == attendu
    assert sortie["AT"].split() == attendu
    assert sortie["OUT"] == "0 0"
    # fill met toute la grille à 7 ; fill_rect pose un bloc 2x2 de 9 depuis la
    # case (2, 1), puis un rectangle débordant écrêté à la seule case (4, 3) = 1.
    assert sortie["FILL"].split() == ["7"] * 12
    assert sortie["RECT"].split() == ["7", "9", "9", "7",
                                      "7", "9", "9", "7",
                                      "7", "7", "7", "1"]
    # spread_from depuis (1, 1), budget 5 : carte de coûts, deux murs (terrain 2,
    # coût 0) au centre que le chemin contourne, 255 dessus. Budget 3 : les cases à
    # plus de 3 retombent hors de portée.
    assert sortie["FLOOD"].split() == ["0", "1", "2", "3",
                                       "1", "255", "255", "4",
                                       "2", "3", "4", "5"]
    assert sortie["BUDGET"].split() == ["0", "1", "2", "3",
                                        "1", "255", "255", "255",
                                        "2", "3", "255", "255"]
    # path_to relit la carte de coûts (budget 5 rejoué) et redescend vers (4, 3) :
    # le chemin contourne les deux murs par la colonne de gauche puis le bas, en
    # pas source -> cible (2 bas, 3 droites : codes 2,2,0,0,0). Une case murée est
    # hors de portée, donc aucun pas.
    assert sortie["PATH"].split() == ["5", "2", "2", "0", "0", "0"]
    assert sortie["NOPATH"] == "0"
    # line_of_sight sur une carte d'obstacles (un mur en (2, 2)) : la diagonale qui
    # traverse le mur est bloquée (0), la colonne et la rangée libres sont dégagées
    # (1), et une ligne dont la cible EST le mur reste dégagée (1, extrémités non
    # testées).
    assert sortie["LOS"].split() == ["0", "1", "1", "1"]
    # make_flow dérive de la carte de coûts (budget 5) une direction vers la source
    # par case : 4 à la source, 255 sur les deux murs, sinon le pas vers le voisin
    # le moins cher (0 droite, 1 gauche, 2 bas, 3 haut).
    assert sortie["FLOW"].split() == ["4", "1", "1", "1",
                                      "3", "255", "255", "3",
                                      "3", "1", "1", "1"]
    # regions étiquette les groupes connexes de valeur égale : 3 régions (les 1 en
    # haut-gauche, les 2 à droite, les 3 au centre-bas), un id par case, le compte
    # en tête.
    assert sortie["REGIONS"].split() == ["3",
                                         "1", "1", "2", "2",
                                         "1", "3", "3", "2",
                                         "1", "3", "3", "3"]
    # contains : un point dans la grille (1), un point hors grille (0).
    assert sortie["CONTAINS"].split() == ["1", "0"]
    # copy_from : la grille source (100..111) recopiée case pour case.
    assert sortie["COPY"].split() == [str(100 + i) for i in range(12)]
    # reachable / cost_at sur la carte de coûts (budget 5) : case (4, 3) atteignable
    # à coût 5 ; case murée (2, 2) hors de portée (non atteignable, coût -1).
    assert sortie["REACH"].split() == ["1", "0"]
    assert sortie["COST"].split() == ["5", "-1"]
    # arrived sur le champ de flux : la source (1, 1) vaut 4 (arrivé), une autre case non.
    assert sortie["ARRIVED"].split() == ["1", "0"]
    # arrive : rampe à mi-approche (dist 50, stop 10, slow 100 -> speed 4 -> (2,3)),
    # plein régime (slow 40 -> speed 10 -> (6,8)), et nul dans le rayon d'arrêt.
    assert sortie["ARRIVE"].split() == ["2", "3", "6", "8", "0", "0"]
    # keep_distance : (0,0) dans la bande, se rapproche au-delà de max (dist 50 > 40
    # -> (3,4)), s'éloigne sous min (dist 5 < 20 -> (-3,-4)).
    assert sortie["KEEP"].split() == ["0", "0", "3", "4", "-3", "-4"]
