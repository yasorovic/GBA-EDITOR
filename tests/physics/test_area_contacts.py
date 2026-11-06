"""Les contacts d'une Area : le C (sonde native) et le C émis par le générateur.

Le comportement du runtime est vérifié par la sonde `tests/native/actor_box_probe.c`, qui joue la MÊME séquence pour un acteur
posé (table de couples, `area_contact_run`) et un acteur du pool (`area_contact_step` avec sa propre mémoire) : posé = spawné.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.models.components import CollisionShapeComponent, TriggerComponent
from core.models.scene import Actor, Area, Scene
from native_toolchain import compilateur_hote, environnement

REPO_DIR = Path(__file__).resolve().parents[2]
NATIVE_DIR = Path(__file__).resolve().parents[1] / "native"
MOTEUR_DIR = REPO_DIR / "runtime" / "include"


@pytest.fixture(scope="module")
def sortie_sonde(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        message = "aucun compilateur C hôte : les contacts d'Area ne sont PAS vérifiés"
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; ils le sont en CI")
    from codegen.runtime_codegen.api_prototypes import build_enum_defines
    dossier = tmp_path_factory.mktemp("area_probe")
    (dossier / "enums.h").write_text("\n".join(build_enum_defines()) + "\n")
    binaire = dossier / "actor_box_probe"
    env = environnement(compilateur)
    r = subprocess.run(
        [compilateur, "-std=c11", "-w", "-O0", "-include", str(dossier / "enums.h"),
         "-I", str(NATIVE_DIR / "libgba_shim"), "-I", str(MOTEUR_DIR),
         str(NATIVE_DIR / "actor_box_probe.c"), "-o", str(binaire)],
        capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    return {l.split()[0]: [int(v) for v in l.split()[1:]] for l in run.stdout.splitlines()}


def test_c_la_reference_d_area_est_un_rang_plus_un(sortie_sonde):
    assert sortie_sonde["area_refs"] == [1, 1, 1, 0]       # rang+1, tag, active ; 0 = pas d'Area


def test_c_le_pose_et_le_spawne_suivent_la_meme_sequence(sortie_sonde):
    """Chaque ligne : enter, collide, exit du posé, puis les trois du spawné. Elles sont identiques à chaque frame."""
    frames = ["area_1_loin", "area_2_entre", "area_3_dure", "area_4_corps_exclu", "area_5_sort", "area_6_rentre",
              "area_7_area_inactive", "area_8_reactive", "area_9_acteur_inactif", "area_10_reactive", "area_11_detruit"]
    for nom in frames:
        pose, spawne = sortie_sonde[nom][:3], sortie_sonde[nom][3:]
        assert pose == spawne, nom
    assert [sortie_sonde[n][:3] for n in frames] == [
        [0, 0, 0],     # loin : rien
        [1, 0, 0],     # les pieds recouvrent l'Area : enter
        [1, 1, 0],     # ça dure : collide
        [1, 2, 0],     # le corps recouvre aussi mais son tag n'est pas permis : toujours UN contact
        [1, 2, 1],     # sorti : exit
        [2, 2, 1],     # rentré : enter
        [2, 2, 2],     # l'Area s'éteint : l'acteur encore en jeu apprend la sortie
        [3, 2, 2],     # elle se rallume : enter
        [3, 2, 2],     # l'acteur est désactivé : rien, et aucune sortie
        [4, 2, 2],     # réactivé : le contact renaît
        [4, 2, 2],     # détruit : terminal, aucune sortie
    ]


def test_c_le_tag_arrive_au_script_celui_de_la_boite_de_l_acteur(sortie_sonde):
    assert sortie_sonde["area_tag"] == [1, 1]


def test_c_le_masque_compte_un_bit_par_rang_de_boite_filtre_par_les_tags_permis(sortie_sonde):
    assert sortie_sonde["area_masque"] == [3, 1, 2]        # les deux boîtes ; le corps seul ; les pieds seuls
    assert sortie_sonde["area_masque_boite_inactive"] == [0]
    assert sortie_sonde["area_masque_area_inactive"] == [0]


def test_c_la_reference_nommee_est_la_constante_du_build(sortie_sonde):
    assert sortie_sonde["area_acces"] == [1, 1, 1]          # `area:get` et `area.name` rendent la référence elle-même


def test_c_position_et_bornes_suivent_la_forme(sortie_sonde):
    assert sortie_sonde["area_position"] == [100, 50]
    assert sortie_sonde["area_position_ecrite"] == [7, 9]
    assert sortie_sonde["area_bounds"] == [9, 12, 16, 12]   # position (7, 9) + décalage (2, 3), taille 16×12


def test_c_overlaps_est_geometrique_et_une_area_inactive_ne_touche_personne(sortie_sonde):
    assert sortie_sonde["area_recouvre"] == [1]
    assert sortie_sonde["area_recouvre_loin"] == [0]
    assert sortie_sonde["area_inactive"] == [0, 0]
    assert sortie_sonde["area_reactive"] == [1, 1]           # toute valeur non nulle réactive
    assert sortie_sonde["area_acteur_sans_boite_active"] == [0]


def test_c_une_area_qui_suit_un_acteur_ne_se_deplace_pas_par_script(sortie_sonde):
    assert sortie_sonde["area_parent_ecriture"] == [100, 50]      # recomposée chaque frame : l'écriture est sans effet
    assert sortie_sonde["area_parent_taille"] == [20, 20]         # sa taille, elle, s'écrit
    assert sortie_sonde["area_parent_lue"] == [1]
    assert sortie_sonde["area_parent_touche"] == [1, 2]           # touchée : les pieds de l'acteur (rang 1) recouvrent la zone
    assert sortie_sonde["area_parent_tenue"] == [0, 0]            # parent inactif : elle ne touche personne
    assert sortie_sonde["area_parent_detruit"] == [1]             # parent détruit : area.parent vaut nil
    assert sortie_sonde["area_libre"] == [5, 6, 1]                # sans parent, l'écriture passe


def test_c_une_reference_absente_se_lit_vide_et_s_ecrit_sans_effet(sortie_sonde):
    assert sortie_sonde["area_absente"] == [0, 0, 0, 0, 0, 0, 0]
    assert sortie_sonde["area_sans_forme"] == [0, 0, 0, 16]      # lire ou écrire la taille ne rallume pas une forme éteinte


def test_c_la_taille_se_lit_s_ecrit_et_reste_dans_un_u8(sortie_sonde):
    # lue (16×12), puis écrite hors bornes (300, -4) → (255, 0), puis (20, 6) que les bornes monde reflètent aussitôt.
    assert sortie_sonde["area_taille"] == [16, 12, 255, 0, 20, 20, 6]


# ── Le C émis ────────────────────────────────────────────────────────────

def _settings():
    return SimpleNamespace(collision_disabled_pairs=[], collision_tags=[])


def _actor(name: str, tag: str = "body") -> Actor:
    return Actor(name=name, components=[CollisionShapeComponent(id="body", tag=tag, w=8, h=8)])


def _area(name: str, tag: str = "area", trigger: bool = True, x: int = 40, y: int = 56) -> Area:
    area = Area(name=name, x=x, y=y)
    area.components[0].tag = tag
    if not trigger:
        area.components = [c for c in area.components if not isinstance(c, TriggerComponent)]
    return area


def test_le_masque_cuit_suit_la_matrice_des_tags():
    from codegen.runtime_codegen.physics.areas import area_mask
    settings = _settings()
    assert area_mask(_area("Door"), _actor("Hero"), settings) == 1          # corps rang 0 : se rencontrent par défaut
    settings.collision_disabled_pairs = ["area|body"]                       # la matrice coupe ce couple (cf. pair_key)
    assert area_mask(_area("Door"), _actor("Hero"), settings) == 0
    # Deux boîtes de même tag : UN seul rang (le premier), comme `collision_pair_mask`.
    twin = Actor(name="Twin", components=[CollisionShapeComponent(id="a", tag="body"),
                                          CollisionShapeComponent(id="b", tag="body")])
    settings.collision_disabled_pairs = []
    assert area_mask(_area("Door"), twin, settings) == 0b1


def test_seules_les_areas_a_declencheur_et_a_forme_entrent_dans_les_tests():
    from codegen.runtime_codegen.physics.areas import trigger_areas
    scene = Scene(name="S", areas=[_area("Door"), _area("Quiet", trigger=False), _area("Empty")])
    scene.areas[2].components = [c for c in scene.areas[2].components if isinstance(c, TriggerComponent)]
    assert [(i, a.name) for i, a in trigger_areas(scene)] == [(0, "Door")]


def test_la_table_des_couples_ne_garde_que_les_acteurs_dont_le_script_repond():
    from codegen.runtime_codegen.physics.areas import area_pair_lines, trigger_areas
    scene = Scene(name="S", areas=[_area("Door")])
    hero, rock = _actor("Hero"), _actor("Rock")
    actors = [(hero, None), (rock, None)]
    project = SimpleNamespace(settings=_settings())
    lines = area_pair_lines(project, scene, actors, 0, {0, 1},
                            lambda s, ev: s == "Hero" and ev in ("on_area_enter", "on_area_exit"),
                            lambda scene_name, actor_name: actor_name, trigger_areas(scene))
    text = "\n".join(lines)
    assert "static const AreaContact _area_pairs[1]" in text
    assert "{&g_areas[0],0,1,{Hero_on_area_enter,0,Hero_on_area_exit}}" in text
    assert "debug_physics_area_test();" in text
    # Rien à émettre sans aucun handler : pas de table, pas de test par frame.
    assert area_pair_lines(project, scene, actors, 0, {0, 1}, lambda s, ev: False,
                           lambda scene_name, actor_name: actor_name, trigger_areas(scene)) == []


def test_les_acteurs_du_pool_passent_par_le_meme_pas_avec_leur_memoire_par_emplacement():
    from codegen.runtime_codegen import shared_pool_gen
    from codegen.runtime_codegen.physics.areas import area_mask, trigger_areas
    from scripting.api import AREA_EVENTS
    scene = Scene(name="S", areas=[_area("Door"), _area("Zone", x=90)])
    model = {"sym": "S_Bullet", "prefab": _actor("Bullet"), "model_id": 3, "group": 1, "shared": True}
    lines = shared_pool_gen.area_lines(
        [model], 8, trigger_areas(scene), lambda pf, area: area_mask(area, pf, _settings()),
        lambda s, ev: ev == "on_area_enter", AREA_EVENTS)
    text = "\n".join(lines)
    assert "static u16 _parea[8][2] EWRAM_BSS;" in text            # un souvenir par emplacement ET par Area
    assert "_parea_gen[_sl]!=_a->gen" in text                      # il repart de zéro quand l'occupant change
    assert "static const AreaFn _on[3]={S_Bullet_on_area_enter,0,0};" in text
    assert "area_contact_step(&g_areas[0],_a,1,_on,&_parea[_sl][0]);" in text
    assert "area_contact_step(&g_areas[1],_a,1,_on,&_parea[_sl][1]);" in text
    assert shared_pool_gen.area_lines([model], 8, trigger_areas(scene), lambda pf, area: 1,
                                      lambda s, ev: False, AREA_EVENTS) == []


def _scene_with_follower(**boss):
    scene = Scene(name="S", actors=[Actor(name="Boss", x=100, y=50, **boss)], areas=[_area("Door", x=140, y=70)])
    scene.areas[0].parent = "Boss"
    return scene


def test_une_area_qui_suit_un_acteur_est_recomposee_apres_lui_et_tenue_si_il_s_eteint():
    from codegen.runtime_codegen.physics.areas import area_init_lines, area_parent_lines
    scene = _scene_with_follower()
    actors = [(scene.actors[0], None)]
    text = "\n".join(area_parent_lines(scene, actors, 0))
    assert "g_areas[0].x = g_actors[0].x +" in text and "g_areas[0].y = g_actors[0].y +" in text
    assert "g_areas[0].held = !(g_actors[0].active && g_actors[0].alive);" in text
    project = SimpleNamespace(settings=_settings(), globals=[], constants=[])
    assert "g_areas[0].parent=1;" in "\n".join(area_init_lines(project, scene, actors, 0))
    scene.areas[0].parent = None
    assert area_parent_lines(scene, actors, 0) == []                  # sans parent : aucune ligne, aucun coût


def _recompose(par, local, rotation, scale):
    """Ce que le C émis calcule (Q8, `gba_sincos`) pour la position d'une Area enfant, rendue en pixels."""
    import math
    ox, oy = local
    px = py = int(round(scale * 256))
    co, si = round(math.cos(math.radians(rotation)) * 256), round(math.sin(math.radians(rotation)) * 256)
    lx, ly = (ox * px) >> 8, (oy * py) >> 8
    return ((par.x << 8) + ((lx * co - ly * si) >> 8)) >> 8, ((par.y << 8) + ((lx * si + ly * co) >> 8)) >> 8


def test_la_frame_0_recompose_la_position_vue_dans_l_editeur():
    """Le local est tiré de la pose authorée du parent : recomposé avec cette même pose, il redonne la position du canvas."""
    from codegen.runtime_codegen.gen_pool import world_to_local_offset
    for boss in ({}, {"rotation": 90, "scale_x": 2.0, "scale_y": 2.0}, {"rotation": 37, "scale_x": 0.5, "scale_y": 0.5}):
        scene = _scene_with_follower(**boss)
        par, area = scene.actors[0], scene.areas[0]
        got = _recompose(par, world_to_local_offset(par, area.x, area.y), boss.get("rotation", 0), boss.get("scale_x", 1.0))
        assert abs(got[0] - area.x) <= 1 and abs(got[1] - area.y) <= 1, (boss, got)


def test_une_seule_conversion_monde_vers_local_pour_acteurs_parties_et_areas():
    """Les parties d'un prefab passent par la conversion des acteurs, avec la racine du prefab (sans pose) pour origine."""
    from codegen.runtime_codegen import gen_pool
    from core.models.scene import Prefab
    arm = Actor(name="Arm", x=0, y=0, rotation=90, scale_x=2.0, scale_y=2.0)
    # (30, 10) vu depuis un parent tourné de 90° et doublé : on défait la rotation, puis l'échelle (Q8).
    assert gen_pool.world_to_local_offset(arm, 30, 10) == (1280, -3840)
    assert gen_pool.world_to_local_offset(arm, 30, 10, origin=(30, 10)) == (0, 0)           # une origine explicite remplace la pose
    assert gen_pool.world_to_local_offset(Actor(name="P", x=10, y=0), 30, 10) == (20 * 256, 10 * 256)
    # La racine d'un prefab n'a pas de pose : ses parties s'expriment depuis l'origine, sans rotation ni échelle.
    pf = Prefab(name="Boss", actor=Actor(name="Boss"),
                children=[arm, Actor(name="Hand", x=30, y=10, parent="Arm"), Actor(name="Leg", x=7, y=-3)])
    model = {"prefab": pf, "shared": True, "model_id": 3, "group": 4, "member_entries": [0, 1, 2, 3], "spool": {"entries": True}}
    text = "\n".join(gen_pool.pool_compose_lines([model]))
    assert "int _lx = (1280 * _px) >> 8, _ly = (-3840 * _py) >> 8;" in text                   # Hand, dans le repère d'Arm
    assert "int _lx = (1792 * _px) >> 8, _ly = (-768 * _py) >> 8;" in text                    # Leg, depuis la racine (7, -3) × 256


def test_l_entree_de_scene_pose_les_areas_et_remet_les_contacts_a_zero():
    from codegen.runtime_codegen.physics.areas import area_init_lines
    scene = Scene(name="S", areas=[_area("Door", tag="door", x=40, y=56)])
    scene.areas[0].components[0].w = 48
    project = SimpleNamespace(settings=_settings(), globals=[], constants=[])
    text = "\n".join(area_init_lines(project, scene, [], 0))
    assert "g_areas[0].x=(40)<<8; g_areas[0].y=(56)<<8; g_areas[0].active=1;" in text
    assert "g_areas[0].box.w=(u8)48;" in text and "g_areas[0].box.tag=BOXTAG_DOOR;" in text
    assert "g_area_prev[_i]=0" in text                              # la mémoire des couples ne survit pas à la scène
    assert area_init_lines(project, Scene(name="Empty"), [], 0) == []     # une scène sans Area n'émet rien


def test_c_les_effets_de_zone(sortie_sonde):
    """`area_effects_apply` : le pas commun du posé et du pool (un seul code, une seule forme)."""
    assert sortie_sonde["fx_gravite"] == [0, 64]                    # la gravité de zone remplace celle de la scène
    assert sortie_sonde["fx_gravite_echelle"] == [0, 128]           # multipliée par le gravity_scale du corps
    assert sortie_sonde["fx_gravite_ignoree"] == [5, 100]           # un corps qui ne suit pas la gravité n'en reçoit pas
    assert sortie_sonde["fx_force"] == [2560, -1280]
    assert sortie_sonde["fx_trainee"] == [128, -128]                # la moitié de la vitesse est retenue
    assert sortie_sonde["fx_flottaison"] == [0, 0]                  # centre dans la zone : flottaison neutre
    assert sortie_sonde["fx_flottaison_bord"] == [40, 100]          # il recouvre la zone mais son centre est dehors
    assert sortie_sonde["fx_turbulence"] == [1, 1, 1]               # déterministe (générateur remis à 1), bornée
    assert sortie_sonde["fx_personnage_ok"] == [1000]
    assert sortie_sonde["fx_personnage_exclu"] == [0]               # CharacterBody : seulement sur option de la zone
    assert sortie_sonde["fx_zone_inactive"] == [0]
    assert sortie_sonde["fx_hors_zone"] == [0]
