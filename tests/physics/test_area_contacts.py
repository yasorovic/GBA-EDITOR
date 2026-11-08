"""Les contacts d'une Area : le C (sonde native) et le C émis par le générateur.

Le comportement du runtime est vérifié par la sonde `tests/native/actor_box_probe.c`, qui joue la MÊME séquence pour un acteur
posé et un acteur né (`area_contact_step` avec leur propre mémoire, un seul parcours des emplacements) : posé = spawné.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
import re
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
    from codegen.runtime_codegen.physics.contacts import contact_helper_lines
    dossier = tmp_path_factory.mktemp("area_probe")
    (dossier / "enums.h").write_text("\n".join(build_enum_defines()) + "\n")
    (dossier / "contacts_gen.h").write_text("\n".join(contact_helper_lines()) + "\n", encoding="utf-8")
    binaire = dossier / "actor_box_probe"
    env = environnement(compilateur)
    r = subprocess.run(
        [compilateur, "-std=c11", "-w", "-O0", "-include", str(dossier / "enums.h"),
         "-I", str(NATIVE_DIR / "libgba_shim"), "-I", str(MOTEUR_DIR), "-I", str(dossier),
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
        pose, spawne = sortie_sonde[nom][:3], sortie_sonde[nom][3:6]
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
    assert sortie_sonde["area_tag"] == [1, 1, 1, 1]      # l'acteur posé, le né, puis le script de l'Area pour chacun


def test_c_le_script_de_l_area_recoit_les_memes_contacts_que_l_acteur(sortie_sonde):
    """Un seul test de recouvrement prévient les deux côtés : à chaque frame, le script de l'Area a compté pour l'acteur posé et
    pour l'acteur né exactement ce que leurs propres crochets ont compté (posé = spawné, côté Area aussi)."""
    frames = ["area_1_loin", "area_2_entre", "area_3_dure", "area_4_corps_exclu", "area_5_sort", "area_6_rentre",
              "area_7_area_inactive", "area_8_reactive", "area_9_acteur_inactif", "area_10_reactive", "area_11_detruit"]
    for nom in frames:
        ligne = sortie_sonde[nom]
        assert ligne[6:9] == ligne[:3], nom          # script de l'Area pour le posé = crochets du posé
        assert ligne[9:12] == ligne[3:6], nom        # script de l'Area pour le né = crochets du né
    assert sortie_sonde["area_11_detruit"][6:9] == [4, 2, 2]


def test_c_sans_script_d_area_seul_l_acteur_est_prevenu(sortie_sonde):
    assert sortie_sonde["area_sans_script"] == [0]


def test_c_le_script_de_l_area_ne_recoit_pas_un_acteur_que_son_crochet_a_detruit(sortie_sonde):
    assert sortie_sonde["area_acteur_detruit_par_son_crochet"] == [0, 0]


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


def _projet(tmp_path, scene):
    from core.project import Project
    p = Project(tmp_path)
    p.scenes.items = [scene]
    return p


def test_la_passe_ne_garde_que_les_types_dont_le_script_repond(tmp_path):
    from codegen.runtime_codegen.physics.areas import area_contact_lines
    scene = Scene(name="S", areas=[_area("Door")])
    hero, rock = _actor("Hero"), _actor("Rock")
    scene.actors = [hero, rock]
    p = _projet(tmp_path, scene)
    actors = [(hero, None), (rock, None)]
    code = "\n".join(area_contact_lines(p, scene, actors, [], ["Hero", "Rock"],
                                        lambda s, ev: s == "Hero" and ev in ("on_area_enter", "on_area_exit")))
    assert "_ar_type[3]={255,0,255};" in code                        # le type 1 (Hero) seul a une ligne
    assert "static const AreaFn _ar_on[1][3]={{Hero_on_area_enter,0,Hero_on_area_exit}};" in code
    assert "static const u16 _ar_allowed[1][1]={{1}};" in code
    assert "SLOT_EACH(_k)" in code and "debug_physics_area_test();" in code
    assert "area_contact_step(&g_areas[0],_a,_ar_allowed[_i][0],_ar_on[_i],0,&g_area_prev[_k][0]);" in code
    assert "_ar_own" not in code                                     # aucune Area n'a de script : aucune table de plus
    assert "g_area_gen[_k]!=_a->gen" in code                         # la mémoire repart de zéro quand l'occupant change
    # Rien à émettre sans aucun crochet : pas de table, pas de test par frame.
    assert area_contact_lines(p, scene, actors, [], ["Hero", "Rock"], lambda s, ev: False) == []


def _scripted(tmp_path, scene, area_name: str, source: str = "function on_actor_enter(other)\nend\n"):
    """Donne un script Lua à l'Area `area_name`, écrit dans le projet de la scène."""
    from core.models.components import ScriptComponent
    p = _projet(tmp_path, scene)
    path = tmp_path / "assets" / f"{area_name}.lua"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    area = next(a for a in scene.areas if a.name == area_name)
    area.components.append(ScriptComponent(script=p.asset_rel(path)))
    return p


def test_le_script_d_une_area_est_prevenu_meme_si_aucun_acteur_n_ecoute(tmp_path):
    """Un type sans crochet d'Area entre dans la passe dès qu'une Area scriptée l'écoute ; seule cette Area est testée pour lui."""
    from codegen.runtime_codegen.physics.areas import area_contact_lines
    scene = Scene(name="S", areas=[_area("Door"), _area("Quiet", x=90)])
    hero = _actor("Hero")
    scene.actors = [hero]
    p = _scripted(tmp_path, scene, "Door")
    code = "\n".join(area_contact_lines(p, scene, [(hero, None)], [], ["Hero"],
                                        lambda s, ev: s == "S_Door_area" and ev == "on_actor_enter"))
    assert "static const AreaFn _ar_on[1][3]={{0,0,0}};" in code      # l'acteur n'écoute rien
    assert "static const AreaActorFn _ar_own[2][3]={{S_Door_area_on_actor_enter,0,0},{0,0,0}};" in code
    assert "_ar_allowed[1][2]={{1,0}}" in code                       # Quiet : personne n'écoute, jamais testée
    assert "_ar_on[_i],_ar_own[0],&g_area_prev[_k][0]" in code


def test_les_points_d_entree_d_un_script_d_area(tmp_path):
    """`on_start` à l'entrée de la scène, `on_update` chaque frame si l'Area est active et non tenue, et les `extern` de tous
    ses points d'entrée (le codegen pose un corps vide pour ceux que le script n'écrit pas)."""
    from codegen.runtime_codegen.physics.areas import area_extern_lines, area_start_lines, area_update_lines
    scene = Scene(name="S", areas=[_area("Quiet"), _area("Door")])
    p = _scripted(tmp_path, scene, "Door", "function on_update()\nend\n")
    defined = {"S_Door_area": {"on_update"}}
    has = lambda s, ev: ev in defined.get(s, ())
    assert area_update_lines(p, scene, has) == [
        "    if(g_areas[1].active && !g_areas[1].held) S_Door_area_on_update();"]
    assert area_start_lines(p, scene, has) == []                     # pas d'on_start écrit : pas d'appel
    externs = area_extern_lines(p, scene)
    assert "extern void S_Door_area_on_update(void);" in externs
    assert any(e.startswith("extern void S_Door_area_on_actor_exit(Actor* other") for e in externs)
    assert not any("Quiet" in e for e in externs)                    # une Area sans script n'a rien à déclarer


def test_un_modele_ne_passe_par_le_meme_parcours_que_les_poses(tmp_path):
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.physics.areas import area_contact_lines
    from core.models.scene import Prefab
    from oam_fixtures import faire_naitre
    cible = _actor("Cible")
    prefab = Prefab(name="Bullet", actor=_actor("Bullet"))
    scene = Scene(name="S", areas=[_area("Door"), _area("Zone", x=90)], actors=[cible])
    p = _projet(tmp_path, scene)
    p.prefabs.items = [prefab]
    faire_naitre(tmp_path, scene, prefab.name)
    code = "\n".join(area_contact_lines(p, scene, [(cible, None)], scene_pi(p, scene), [None],
                                        lambda s, ev: ev == "on_area_enter"))
    assert code.count("SLOT_EACH(") == 1                              # un seul parcours, posés et nés ensemble
    assert re.search(r"_ar_on\[1\]\[3\]=\{\{\w*Bullet_on_area_enter,0,0\}\};", code)
    assert "_ar_allowed[1][2]={{1,1}}" in code                       # une colonne par Area à déclencheur
    assert "&g_area_prev[_k][0]" in code and "&g_area_prev[_k][1]" in code


def _scene_with_follower():
    scene = Scene(name="S", actors=[Actor(name="Boss", x=100, y=50)], areas=[_area("Door", x=140, y=70)])
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


def test_la_frame_0_recompose_la_position_vue_dans_l_editeur():
    """Le local est tiré de la pose authorée du parent : ajouté à cette même pose (translation, comme le C émis), il
    redonne la position du canvas."""
    from codegen.runtime_codegen.gen_actor_hierarchy import local_transform
    scene = _scene_with_follower()
    par, area = scene.actors[0], scene.areas[0]
    ox, oy = local_transform(area, par.x, par.y)
    assert (((par.x << 8) + ox) >> 8, ((par.y << 8) + oy) >> 8) == (area.x, area.y)


def test_une_seule_conversion_monde_vers_local_pour_acteurs_parties_et_areas():
    """Les parties d'un prefab passent par la conversion des acteurs, avec la racine du prefab (sans pose) pour origine."""
    from codegen.runtime_codegen.gen_actor_hierarchy import local_transform, part_link_lines
    from core.models.scene import Prefab
    arm = Actor(name="Arm", x=20, y=-5)
    assert local_transform(Actor(name="C", x=30, y=10), 0, 0) == (30 * 256, 10 * 256)
    assert local_transform(Actor(name="C", x=30, y=10), 30, 10) == (0, 0)           # l'origine donnée remplace la pose
    # La racine d'un prefab n'a pas de pose : ses parties s'expriment depuis l'origine.
    pf = Prefab(name="Boss", actor=Actor(name="Boss"),
                children=[arm, Actor(name="Hand", x=30, y=10, parent="Arm"), Actor(name="Leg", x=7, y=-3)])
    text = "\n".join(part_link_lines(pf, "_b", ""))
    assert "group_slot(_b, 2), group_slot(_b, 1), 2, 1, 2560, 3840);" in text          # Hand, depuis Arm (10, 15) × 256
    assert "group_slot(_b, 3), _b, 1, 1, 1792, -768);" in text                         # Leg, depuis la racine (7, -3) × 256


def test_l_entree_de_scene_pose_les_areas_et_remet_les_contacts_a_zero():
    from codegen.runtime_codegen.physics.areas import area_init_lines
    scene = Scene(name="S", areas=[_area("Door", tag="door", x=40, y=56)])
    scene.areas[0].components[0].w = 48
    project = SimpleNamespace(settings=_settings(), globals=[], constants=[])
    text = "\n".join(area_init_lines(project, scene, [], 0))
    assert "g_areas[0].x=(40)<<8; g_areas[0].y=(56)<<8; g_areas[0].active=1;" in text
    assert "g_areas[0].box.w=(u8)48;" in text and "g_areas[0].box.tag=BOXTAG_DOOR;" in text
    assert "((u16*)g_area_prev)[_i]=0" in text                     # la mémoire des couples ne survit pas à la scène
    assert area_init_lines(project, Scene(name="Empty"), [], 0) == []     # une scène sans Area n'émet rien


def test_c_les_effets_de_zone(sortie_sonde):
    """`area_effects_apply` : le pas commun du posé et du né (un seul code, une seule forme)."""
    assert sortie_sonde["fx_gravite"] == [0, 64]                    # la gravité de zone remplace celle de la scène
    assert sortie_sonde["fx_gravite_echelle"] == [0, 64]            # l'échelle du corps est appliquée ensuite, par `body_motion_step`
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
