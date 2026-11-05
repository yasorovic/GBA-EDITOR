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


def test_c_une_reference_absente_se_lit_vide_et_s_ecrit_sans_effet(sortie_sonde):
    assert sortie_sonde["area_absente"] == [0, 0, 0, 0, 0, 0, 0]
    assert sortie_sonde["area_sans_forme"] == [0, 0]


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


def test_l_entree_de_scene_pose_les_areas_et_remet_les_contacts_a_zero():
    from codegen.runtime_codegen.physics.areas import area_init_lines
    scene = Scene(name="S", areas=[_area("Door", tag="door", x=40, y=56)])
    scene.areas[0].components[0].w = 48
    project = SimpleNamespace(settings=_settings(), globals=[], constants=[])
    text = "\n".join(area_init_lines(project, scene))
    assert "g_areas[0].x=(40)<<8; g_areas[0].y=(56)<<8; g_areas[0].active=1;" in text
    assert "g_areas[0].box.w=(u8)48;" in text and "g_areas[0].box.tag=BOXTAG_DOOR;" in text
    assert "g_area_prev[_i]=0" in text                              # la mémoire des couples ne survit pas à la scène
    assert area_init_lines(project, Scene(name="Empty")) == []     # une scène sans Area n'émet rien
