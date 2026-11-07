"""Le C réel de la détection Interactive (`interact_helper_lines`), compilé et exécuté : le recouvrement
(hover), la visée dans le regard (facing), l'arrêt par les murs, et le plus proche qui l'emporte.

`interact_pick` parcourt les posés d'une plage puis le pool partagé, et lit pour chaque emplacement la ligne de son
TYPE (`Actor.model`) : le tag de la zone (255 : pas un consommateur) et la visée. Il rend l'emplacement retenu."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
Actor g_actors[8];
OamEntry g_oam_entries[8];
int g_spool_start = 0, g_spool_hw = 0;
u32 g_alive_bits[1];
u32 g_alive_epoch;
PoolCursor g_nth;
static int g_wall_x0 = 0, g_wall_x1 = -1;       /* un mur vertical : x dans [x0, x1], tout y */
static int tile_wall_at(int px, int py){ (void)py; return px >= g_wall_x0 && px <= g_wall_x1; }
static int sfx_calls, last_sfx, last_volume;
static void sfx_play(int id,int volume,int unused){ sfx_calls++; last_sfx=id; last_volume=volume; }
%(helpers)s

/* Un acteur actif de type 1 en (x, y), une seule boîte (bx, by, w, h) active, de tag 0. */
static void mk(int i, int x, int y, int bx, int by, int w, int h, int solid){
    Actor* a = &g_actors[i];
    *a = (Actor){0};
    a->active = 1; a->x = x << 8; a->y = y << 8; a->oam_entry = -1; a->model = 1;
    a->collision.box_count = 1;
    CollisionShape* b = &a->collision.boxes[0];
    b->x = bx; b->y = by; b->w = w; b->h = h; b->solid = solid; b->active = 1;
}

int main(void){
    /* Par type : 1 et 3 consomment (zone de tag 0), 2 non. */
    const u8 tag[] = {255, 0, 255, 0};
    const u8 hover[] = {0, 0, 0, 0}, aim[] = {0, 1, 0, 1};
    int r;
    /* 0 = le joueur (16x16 en 0,0), 1 = une zone 16x16 en x=10 (recouvre le joueur) ; les posés sont 1 et 2 */
    mk(0, 0, 0, 0, 0, 16, 16, 1); mk(1, 10, 0, 0, 0, 16, 16, 0); mk(2, 100, 100, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, hover, 4);  printf("hover_recouvre %%d\n", r);
    mk(1, 30, 0, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, hover, 4);  printf("hover_loin %%d\n", r);

    /* facing : zone collée à droite (x=16..32), le joueur regarde à droite, portée 4 */
    mk(1, 16, 0, 0, 0, 16, 16, 0);
    g_actors[0].facing_x = 1;
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("facing_colle %%d\n", r);
    mk(1, 19, 0, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("facing_a_portee %%d\n", r);
    mk(1, 20, 0, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("facing_trop_loin %%d\n", r);
    mk(1, 20, 0, 0, 0, 16, 16, 0);
    g_actors[0].facing_x = -1;
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("facing_dos_tourne %%d\n", r);
    g_actors[0].facing_x = 0;
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("facing_nul %%d\n", r);

    /* facing vers le bas */
    mk(1, 0, 18, 0, 0, 16, 16, 0);
    g_actors[0].facing_x = 0; g_actors[0].facing_y = 1;
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("facing_bas %%d\n", r);

    /* un mur entre les deux */
    mk(1, 20, 0, 0, 0, 16, 16, 0); g_actors[0].facing_x = 1; g_actors[0].facing_y = 0;
    mk(1, 19, 0, 0, 0, 16, 16, 0);
    g_wall_x0 = 17; g_wall_x1 = 18;
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("facing_mur %%d\n", r);
    mk(1, 10, 0, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, hover, 4);  printf("hover_ignore_le_mur %%d\n", r);
    /* une zone posee SUR un mur (x=19..35) : seul un mur entre les deux arrete la visee */
    mk(1, 19, 0, 0, 0, 16, 16, 0);
    g_wall_x0 = 19; g_wall_x1 = 35;
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("zone_sur_mur %%d\n", r);
    g_wall_x0 = 0; g_wall_x1 = -1;

    /* le plus proche l'emporte */
    mk(1, 19, 0, 0, 0, 16, 16, 0); mk(2, 17, 0, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("plus_proche %%d\n", r);
    mk(2, 17, 0, 0, 0, 16, 16, 0); g_actors[2].active = 0;
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("inactif_ignore %%d\n", r);
    g_actors[2].active = 1;
    /* le type 3 cherche une zone de tag 3, que l'emplacement 2 n'a pas : il est écarté */
    const u8 hors[] = {255, 0, 255, 3};
    g_actors[2].model = 3;
    r = interact_pick(&g_actors[0], 1, 2, 0, hors, aim, 4);   printf("zone_absente %%d\n", r);

    /* sans boite de collision : la boite du joueur est le cadre du sprite (16x16 par defaut) */
    mk(0, 0, 0, 0, 0, 16, 16, 1); g_actors[0].collision.box_count = 0; g_actors[0].facing_x = 1;
    mk(1, 18, 0, 0, 0, 16, 16, 0); mk(2, 100, 100, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], 1, 2, 0, tag, aim, 4);    printf("sans_boite %%d\n", r);

    /* Le pool PARTAGÉ : les emplacements 3 (type 2, pas un consommateur) et 4 (type 3, en visée). Les posés
       (type 1) consomment au recouvrement : `mix`. */
    {
        const u8 mix[] = {0, 0, 0, 1};
        mk(0, 0, 0, 0, 0, 16, 16, 1); mk(1, 100, 100, 0, 0, 16, 16, 0); mk(2, 100, 100, 0, 0, 16, 16, 0);
        mk(3, 10, 0, 0, 0, 16, 16, 0); g_actors[3].model = 2;     /* recouvre le joueur, mais n'est pas un consommateur */
        mk(4, 30, 0, 0, 0, 16, 16, 0); g_actors[4].model = 3;     /* un consommateur en visée, trop loin */
        g_spool_start = 3; g_spool_hw = 5;
        pool_bit_set(3); pool_bit_set(4);
        g_actors[0].facing_x = 1;
        r = interact_pick(&g_actors[0], 1, 2, 1, tag, mix, 4);  printf("pool_hors_portee %%d\n", r);
        mk(4, 19, 0, 0, 0, 16, 16, 0); g_actors[4].model = 3;
        r = interact_pick(&g_actors[0], 1, 2, 1, tag, mix, 4);  printf("pool_atteint %%d\n", r);
        g_actors[4].active = 0;
        r = interact_pick(&g_actors[0], 1, 2, 1, tag, mix, 4);  printf("pool_inactif %%d\n", r);
        g_actors[4].active = 1; g_spool_hw = 4;
        r = interact_pick(&g_actors[0], 1, 2, 1, tag, mix, 4);  printf("pool_hors_hw %%d\n", r);
        g_spool_hw = 5;
        r = interact_pick(&g_actors[0], 1, 2, 0, tag, mix, 4);  printf("pool_ignore %%d\n", r);
        /* le plus proche l'emporte, qu'il soit posé ou né : un posé à 1 px plus près que l'instance née */
        mk(1, 18, 0, 0, 0, 16, 16, 0);
        r = interact_pick(&g_actors[0], 1, 2, 1, tag, aim, 4);   printf("pool_contre_pose %%d\n", r);
        mk(1, 19, 0, 0, 0, 16, 16, 0); mk(4, 17, 0, 0, 0, 16, 16, 0); g_actors[4].model = 3;
        r = interact_pick(&g_actors[0], 1, 2, 1, tag, aim, 4);   printf("pool_plus_proche %%d\n", r);
    }
    return 0;
}
"""


@pytest.fixture(scope="module")
def resultats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la détection est vérifiée en CI")
    from codegen.runtime_codegen.interact_gen import interact_helper_lines
    dossier = tmp_path_factory.mktemp("interact")
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(interact_helper_lines())},
                                     encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True,
                            env=environnement(compilateur)).stdout.split()
    return {nom: int(valeur) for nom, valeur in zip(sortie[::2], sortie[1::2])}


def test_hover_recouvre_la_zone(resultats):
    assert resultats["hover_recouvre"] == 1          # l'emplacement 1
    assert resultats["hover_loin"] == -1


def test_facing_atteint_la_zone_dans_le_regard_a_portee(resultats):
    assert resultats["facing_colle"] == 1            # collée : sans marge sur la zone
    assert resultats["facing_a_portee"] == 1         # 3 px d'écart : la bande de 4 px la touche
    assert resultats["facing_trop_loin"] == -1       # 4 px d'écart : les bords ne se recouvrent pas
    assert resultats["facing_bas"] == 1


def test_facing_n_atteint_rien_dans_le_dos_ou_sans_regard(resultats):
    assert resultats["facing_dos_tourne"] == -1
    assert resultats["facing_nul"] == -1


def test_un_mur_arrete_la_visee_mais_pas_le_recouvrement(resultats):
    assert resultats["facing_mur"] == -1
    assert resultats["hover_ignore_le_mur"] == 1


def test_une_zone_posee_sur_un_mur_reste_atteignable(resultats):
    assert resultats["zone_sur_mur"] == 1


def test_le_plus_proche_l_emporte_et_l_inactif_est_ignore(resultats):
    assert resultats["plus_proche"] == 2             # l'acteur 2 (x=17) bat l'acteur 1 (x=19)
    assert resultats["inactif_ignore"] == 1
    assert resultats["zone_absente"] == 1            # le type de l'emplacement 2 cherche un tag absent : écarté


def test_sans_boite_de_collision_la_visee_part_du_cadre(resultats):
    assert resultats["sans_boite"] == 1


def test_une_instance_du_pool_est_un_consommateur_par_son_type(resultats):
    assert resultats["pool_hors_portee"] == -1
    assert resultats["pool_atteint"] == 4            # l'emplacement né
    assert resultats["pool_inactif"] == -1
    assert resultats["pool_hors_hw"] == -1           # au-delà du plus haut emplacement utilisé : ignoré
    assert resultats["pool_ignore"] == -1            # `pool` nul : le pool n'est pas parcouru


def test_le_plus_proche_l_emporte_entre_pose_et_ne(resultats):
    assert resultats["pool_contre_pose"] == 1        # le posé (à 18 px) est plus proche que l'instance née (19 px)
    assert resultats["pool_plus_proche"] == 4        # l'instance née (17 px) l'emporte


def _scene_coffre(dossier: Path, pooled: bool, handler: bool):
    """Le héros (Player, sans sprite) est posé ; le coffre est posé, ou né du prefab `Chest` par le script de scène.
    Rend les lignes émises (table du descripteur, puis bloc d'interaction), les types du héros et du coffre, et le
    numéro du tag de la zone."""
    import copy
    from types import SimpleNamespace
    from codegen.oam_alloc import scene_oam_layout
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import shown
    from codegen.runtime_codegen.interact_gen import interact_tick_lines
    from codegen.runtime_codegen.model_desc import model_desc_lines
    from core.models.audio import Sfx
    from core.models.components import CollisionShapeComponent, InteractiveComponent, SoundFxComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    project = Project(dossier)
    project.sfx.append(Sfx(name="Open", volume=70))
    chest = Prefab(name="Chest")
    chest.actor.components += [CollisionShapeComponent(tag="zone", w=16, h=16), InteractiveComponent(box_tag="zone"),
                               SoundFxComponent(sfx_name="Open", trigger="on_interact")]
    hero = Actor(name="Hero", is_player=True)
    posed = [hero] if pooled else [hero, Actor(name="ChestPose", prefab_name="Chest",
                                               components=copy.deepcopy(chest.actor.components))]
    scene = Scene(name="S", actors=posed)
    project.scenes.items = [scene]
    project.prefabs.items = [chest]
    if pooled:
        faire_naitre(dossier, scene, "Chest")
    pi = scene_pi(project, scene)
    actors = [(a, None) for a in scene.actors]
    # Le code du coffre : celui du modèle (`S_Chest`), qu'il soit posé ou né.
    scripts = [None] + ([] if pooled else ["S_Chest" if handler else None])
    has = lambda sym, event: handler and event == "on_interact"
    layout = SimpleNamespace(masks={"interact": "1"})
    lines = (model_desc_lines(project, scene, actors, pi, scripts, has, layout)
             + interact_tick_lines(project, scene, actors, 0, pi, scripts, has, layout, shown))
    lay = scene_oam_layout(project, scene)
    chest_type = next(m["model_id"] for m in pi if m["shared"]) if pooled else lay.placed_model[1]
    return lines, lay.placed_model[0], chest_type, project.collision_tags().index("zone")


@pytest.mark.parametrize("handler", [False, True])
def test_son_interaction_parite_pose_spawne(tmp_path, handler):
    """Le tick généré joue le son du seul objet retenu, avec ou sans script, posé ou né au tick 0."""
    from codegen.runtime_codegen.interact_gen import interact_helper_lines
    from core.models.audio import volume_to_effect

    cc = compilateur_hote()
    if cc is None:
        pytest.skip("aucun compilateur C hôte")
    blocs, types = [], []
    for pooled in (False, True):
        lines, hero_type, chest_type, zone = _scene_coffre(tmp_path / ("pool" if pooled else "pose"), pooled, handler)
        assert any("interact_pick(" in line for line in lines)
        # Les deux tables portent le même nom : chaque chemin a la sienne, dans sa propre fonction.
        blocs.append("static void tick_%s(void){\n%s\n}" % ("pool" if pooled else "placed", "\n".join(lines)))
        types.append((hero_type, chest_type))
    source = SONDE.split("int main(void){")[0] % {"helpers": "\n".join(interact_helper_lines())}
    source += """
#define SFX_OPEN 7
static int pressed, callbacks;
static int input_pressed(int mask){ return pressed; }
void S_Chest_on_interact(Actor* target,Actor* who){ callbacks++; target->active=0; }
""" + "\n".join(blocs) + r"""
static const int hero_type[2] = {%d, %d}, chest_type[2] = {%d, %d};
int main(void){
    for(int pooled=0;pooled<2;pooled++){
        int target=pooled?3:1;
        for(int frame=0;frame<6;frame++){
            for(int k=0;k<8;k++) g_actors[k]=(Actor){0};
            g_alive_bits[0]=0;
            mk(0,0,0,0,0,16,16,1); g_actors[0].model=hero_type[pooled];
            mk(target,frame==2?100:10,0,0,0,16,16,0);
            g_actors[target].model=chest_type[pooled];
            g_actors[target].collision.boxes[0].tag=@ZONE@;
            g_spool_start=pooled?1:2; g_spool_hw=pooled?4:2;
            if(pooled) pool_bit_set(target);
            if(frame==3) g_actors[target].active=0;
            if(frame==4) g_actors[target].collision.boxes[0].active=0;
            pressed=(frame!=0);
            sfx_calls=callbacks=0; last_sfx=last_volume=-1;
            if(pooled) tick_pool(); else tick_placed();
            printf("%%d %%d %%d %%d\n",sfx_calls,last_sfx,last_volume,callbacks);
        }
    }
    return 0;
}
""" % (types[0][0], types[1][0], types[0][1], types[1][1])
    source = source.replace("@ZONE@", str(zone))
    path = tmp_path / "sfx_interact.c"
    path.write_text(source, encoding="utf-8")
    binary = tmp_path / "sfx_interact.exe"
    result = subprocess.run([cc, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                             "-o", str(binary), str(path)], capture_output=True, text=True, env=environnement(cc))
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True, env=environnement(cc))
    assert result.returncode == 0, result.stderr
    rows = [tuple(map(int, line.split())) for line in result.stdout.splitlines()]
    silence = (0, -1, -1, 0)
    played = (1, 7, volume_to_effect(70), int(handler))
    expected = [silence, played, silence, silence, silence, played]
    assert rows[:6] == rows[6:] == expected
