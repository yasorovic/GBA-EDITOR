/* Sonde des PORTES D'INSPECTEUR d'un acteur — boîtes de collision et drapeaux
   fixés au build, exécutés par les VRAIES fonctions de `runtime_api_inline.h`.

   Ce que le catalogue Python ne peut pas vérifier, c'est le comportement C :
   la borne d'un s8/u8 qui déborderait sur la boîte voisine, la boîte absente
   qui doit se lire vide et s'écrire sans effet, le tag qui choisit la BONNE
   boîte. Un test d'en-tête (« la fonction existe ») ne voit aucun des trois.

   Les `#define` d'énumération (EASE_*, DIR_*…) sont GÉNÉRÉS dans runtime_api.h
   et absents de l'en-tête à la main : le test les fournit en préambule, par
   `-include`, depuis la même source que le build (`build_enum_defines`).

   SORTIE — une ligne par vérification, « nom valeur… », lue par le test. */

#include <stdio.h>
#include "gba_engine.h"
#include "actor_types_static.h"
#include "runtime_api_inline.h"

/* Symboles que main.c fournit d'ordinaire — aucun n'est appelé ici, mais le
   moteur est compilé en entier. */
vu16    gba_shim_registers[16];
OBJATTR gba_shim_oam[128];
void CpuFastSet(const void *source, void *dest, u32 mode) {
    (void)source; (void)dest; (void)mode;
}
const unsigned int   g_save_id[1]  = {0};
const unsigned short g_save_idx[1] = {0};
const int            g_save_def[1] = {0};
const int            g_save_count = 0;
const int            g_save_slots = 0;
const int            g_save_slot_size = 0;
const unsigned short g_palettes[1][16] = {{0}};
const int            g_palette_count = 0;
const unsigned short g_save_len[1]  = {0};
const unsigned char  g_save_bits[1] = {0};
int  global_read (int i)        { (void)i; return 0; }
void global_write(int i, int v) { (void)i; (void)v; }
int  global_read_at (int i, int k)        { (void)i; (void)k; return 0; }
void global_write_at(int i, int k, int v) { (void)i; (void)k; (void)v; }

Actor g_actors[2];
u32 g_obj_state[16];
int g_spool_start = 0, g_spool_end = 0, g_spool_hw = 0, g_spool_entry = -1;
const AppearanceInit* g_appearance_init;
OamEntry g_oam_entries[2];   /* l'affichage des acteurs : Actor.oam_entry en est l'indice */

/* La carte de collision vit dans main.c ; la sonde la remplace par un stub dont
   la réponse dit quelles coordonnées lui sont arrivées. */
int collision_map_tile(int px, int py) { return px * 10 + py; }

/* État de la caméra active — main.c le définit d'ordinaire. */
int g_cam_active = 0;
int g_cam_margin_x = 0, g_cam_margin_y = 0;
int g_cam_frame_w = 240, g_cam_frame_h = 160;
int cam_x = 0, cam_y = 0;
int g_bounds_x = 0, g_bounds_y = 0, g_bounds_w = 0, g_bounds_h = 0;

/* Le moteur (gba_engine.h) n'est pas compilé ici : substituts minimaux. La vitesse d'un fond
   est un vrai tableau (c'est elle que la conversion pourcent ↔ Q8 doit round-tripper) ; les
   windows ne sont pas observées. */
static int s_bg_speed[4];
int  layer_get_speed(int bg) { return s_bg_speed[bg & 3]; }
void layer_set_speed(int bg, int q8) { s_bg_speed[bg & 3] = q8; }
void window_set(int n, int x, int y, int w, int h) { (void)n; (void)x; (void)y; (void)w; (void)h; }
void window_show(int n, int on) { (void)n; (void)on; }

#define TAG_BODY 0
#define TAG_HIT  1
#define TAG_NONE 7

static void rect(const char *nom, Rect r) {
    printf("%s %d %d %d %d\n", nom, r.x, r.y, r.w, r.h);
}
static void vec(const char *nom, Vec2 v) {
    printf("%s %d %d\n", nom, v.x, v.y);
}

int main(void) {
    Actor *a = &g_actors[0];
    Actor *b = &g_actors[1];
    a->oam_entry = 0;
    b->oam_entry = 1;
    a->collision.box_count = 2;
    a->collision.boxes[0] = (CollisionBox){ 0,  0, 16, 16, 1, 1, TAG_BODY };
    a->collision.boxes[1] = (CollisionBox){ 2, -3,  8,  8, 0, 1, TAG_HIT  };
    b->collision.box_count = 1;
    b->collision.boxes[0] = (CollisionBox){ 0,  0, 16, 16, 1, 1, TAG_BODY };

    /* Le tag choisit la bonne boîte : la référence est un rang, 0 = absente. */
    int body = actor_get_box(a, TAG_BODY);
    int hit  = actor_get_box(a, TAG_HIT);
    int none = actor_get_box(a, TAG_NONE);
    int bbox = actor_get_box(b, TAG_BODY);
    printf("refs %d %d %d %d\n", body, hit, none, bbox);
    printf("tags %d %d\n", collision_box_get_tag(body), collision_box_get_tag(hit));

    /* Décalage et taille, lus séparément. */
    vec("offset_body", collision_box_get_offset(body));
    vec("offset_hit",  collision_box_get_offset(hit));
    vec("size_hit",    collision_box_get_size(hit));

    /* Une écriture hors bornes est SERRÉE, elle ne déborde pas. */
    collision_box_set_offset(hit, (Vec2){ 500, -500 });
    collision_box_set_size(hit,   (Vec2){ 300, -4 });
    vec("offset_borne", collision_box_get_offset(hit));
    vec("size_borne",   collision_box_get_size(hit));
    vec("voisine_offset", collision_box_get_offset(body));
    vec("voisine_size",   collision_box_get_size(body));
    collision_box_set_offset(hit, (Vec2){ 4, 5 });
    collision_box_set_size(hit,   (Vec2){ 6, 7 });
    vec("offset_normal", collision_box_get_offset(hit));
    vec("size_normal",   collision_box_get_size(hit));

    /* solid et active : lecture, écriture, et l'autre boîte n'est pas touchée. */
    printf("solid_avant %d %d\n", collision_box_get_solid(body), collision_box_get_solid(hit));
    collision_box_set_solid(hit, 5);          /* toute valeur non nulle = vrai */
    collision_box_set_solid(body, 0);
    printf("solid_apres %d %d\n", collision_box_get_solid(body), collision_box_get_solid(hit));
    printf("active_avant %d %d\n", collision_box_get_active(body), collision_box_get_active(hit));
    collision_box_set_active(hit, 0);
    printf("active_apres %d %d\n", collision_box_get_active(body), collision_box_get_active(hit));
    collision_box_set_active(hit, 1);

    /* Une boîte absente : lecture vide, écriture sans effet. */
    vec("absente_offset", collision_box_get_offset(none));
    rect("absente_bounds", collision_box_get_bounds(none));
    collision_box_set_offset(none, (Vec2){ 1, 1 });
    collision_box_set_solid(none, 1);
    collision_box_set_active(none, 1);
    printf("absente_solid %d\n", collision_box_get_solid(none));
    printf("box_count %d\n", actor_get_box_count(a));

    /* Le rectangle MONDE : position en Q8 (>>8), plus décalage, plus taille. */
    collision_box_set_offset(hit, (Vec2){ 2, -3 });
    collision_box_set_size(hit,   (Vec2){ 8, 8 });
    a->x = 100 << 8;  a->y = 50 << 8;
    rect("bounds_body", collision_box_get_bounds(body));
    rect("bounds_hit",  collision_box_get_bounds(hit));

    /* Chevauchement : des PIXELS, pas du Q8. Deux 16x16 distants de 5 px se
       touchent, de 20 px non — y compris avec un reste sous-pixel. */
    b->x = (105 << 8) + 77;  b->y = 50 << 8;
    printf("overlap_5px  %d %d\n", collision_box_overlaps_box(body, bbox),
                                    collision_box_overlaps_actor(body, b));
    b->x = 120 << 8;
    printf("overlap_20px %d %d\n", collision_box_overlaps_box(body, bbox),
                                    collision_box_overlaps_actor(body, b));
    b->x = 105 << 8;
    printf("actors_overlap %d\n", actors_overlap(a, b));

    /* Une boîte inactive ne touche personne, des deux côtés. */
    collision_box_set_active(bbox, 0);
    printf("overlap_inactive_autre %d %d %d\n", collision_box_overlaps_box(body, bbox),
                                                 collision_box_overlaps_actor(body, b),
                                                 actors_overlap(a, b));
    collision_box_set_active(bbox, 1);
    collision_box_set_active(body, 0);
    printf("overlap_inactive_moi %d\n", collision_box_overlaps_box(body, bbox));
    collision_box_set_active(body, 1);
    printf("overlap_absente %d\n", collision_box_overlaps_box(none, bbox));

    /* Contacts par couple de TAGS : un bit par couple, pour que le premier contact
       ne masque pas les suivants. `joueur` = un corps (haut) + des pieds (bas) ;
       `piece` = un seul corps. Tombée sur la pièce, c'est d'abord les pieds. */
    Actor *joueur = &g_actors[2];
    Actor *piece  = &g_actors[3];
    joueur->collision.box_count = 2;
    joueur->collision.boxes[0] = (CollisionBox){ 0,  0, 16, 16, 0, 1, TAG_BODY };
    joueur->collision.boxes[1] = (CollisionBox){ 0, 16, 16,  4, 1, 1, TAG_HIT  };
    piece->collision.box_count = 1;
    piece->collision.boxes[0] = (CollisionBox){ 0, 0, 8, 8, 0, 1, TAG_BODY };
    joueur->x = 0;  joueur->y = 0;
    piece->x = 4 << 8;
    piece->y = 18 << 8;                       /* ne touche que les pieds */
    printf("mask_pieds %d\n", actors_overlap_mask(joueur, piece));
    piece->y = 10 << 8;                       /* touche le corps ET les pieds */
    printf("mask_les_deux %d\n", actors_overlap_mask(joueur, piece));
    piece->y = 40 << 8;
    printf("mask_loin %d\n", actors_overlap_mask(joueur, piece));
    /* Deux boîtes de même tag chez le même acteur : UN seul contact. */
    joueur->collision.boxes[1].tag = TAG_BODY;
    piece->y = 10 << 8;
    printf("mask_meme_tag %d\n", actors_overlap_mask(joueur, piece));
    /* Une boîte inactive ne fait pas de contact. */
    joueur->collision.boxes[1].tag = TAG_HIT;
    joueur->collision.boxes[1].active = 0;
    printf("mask_inactive %d\n", actors_overlap_mask(joueur, piece));

    /* Au sol : par boîte, et une boîte absente est fausse. */
    a->collision.boxes[0].grounded = 1;
    a->collision.boxes[1].grounded = 0;
    printf("grounded %d %d %d\n", collision_box_get_grounded(body),
                                  collision_box_get_grounded(hit),
                                  collision_box_get_grounded(none));

    /* La carte de collision, interrogée par la boîte. */
    printf("collision_tile %d %d\n", collision_box_get_collision_tile(body, 3, 7),
                                     collision_box_get_collision_tile(none, 3, 7));

    /* Drapeaux fixés au build. */
    g_oam_entries[a->oam_entry].affine_slot = -1;
    printf("affine_sans_slot %d\n", actor_get_affine(a));
    g_oam_entries[a->oam_entry].affine_slot = 0;               /* le slot 0 EST un slot */
    printf("affine_slot_zero %d\n", actor_get_affine(a));
    g_oam_entries[a->oam_entry].screen_space = 1;
    printf("screen_space %d\n", actor_get_screen_space(a));

    /* Apparences : activer l'une repose les constantes du sprite d'arrivée et remet
       l'animation à zéro ; un acteur SANS entrée reste muet. */
    static const AppearanceInit lignes[3] = { {16,16,3,1}, {32,24,7,0}, {8,8,2,1} };
    g_appearance_init = &lignes[1];                 /* la base n'est pas 0 : elle compte */
    OamEntry *o = &g_oam_entries[a->oam_entry];
    o->appearance_base = 1;                          /* « ligne 0 », plus un */
    o->anim_state = 4; o->frame = 9; o->timer = 5; o->frame_w = 99;
    actor_set_appearance(a, 1);                      /* ligne base+1 = lignes[2] */
    printf("appearance_set %d %d %d %d %d %d %d %d\n", actor_get_appearance(a),
           actor_get_anim(a), actor_get_frame(a), actor_get_frame_w(a),
           actor_get_frame_h(a), actor_get_pal(a), actor_get_facing_auto(a), o->timer);
    b->oam_entry = -1;
    actor_set_appearance(b, 1);
    printf("appearance_sans_entree %d\n", actor_get_appearance(b));
    /* Une seule apparence (base 0) : jamais la ligne d'un autre porteur. */
    o->appearance_base = 0; o->frame_w = 55;
    actor_set_appearance(a, 0);
    printf("appearance_mono %d\n", actor_get_frame_w(a));
    /* Un état absent (255) ne change rien ; un état réel repart de la frame 0. */
    o->anim_state = 2; o->frame = 6;
    actor_play_anim(a, 255);
    printf("anim_absente %d %d\n", actor_get_anim(a), actor_get_frame(a));
    actor_play_anim(a, 1);
    printf("anim_reelle %d %d\n", actor_get_anim(a), actor_get_frame(a));

    /* Tranche 2 — la caméra : l'index de table EST la constante CAM_<NOM>. */
    g_cam_active = 3;
    printf("cam_active %d\n", camera_get_active());
    camera_set_margin((Vec2){ 60, -5 });                 /* négatif → serré à 0 */
    vec("cam_margin", camera_get_margin());
    camera_set_frame((Vec2){ 500, 0 });                  /* hors bornes → 240×1 */
    vec("cam_frame_borne", camera_get_frame());
    camera_set_frame((Vec2){ 240, 100 });
    vec("cam_frame_reduit", camera_get_frame());
    camera_set_frame((Vec2){ 240, 160 });                /* plein écran : WIN0 s'éteint */
    vec("cam_frame_plein", camera_get_frame());

    /* Tranche 2 — la vitesse de parallax d'un fond : pourcent pour l'auteur, Q8 dedans.
       `+ 1` doit avancer à CHAQUE pas (l'arrondi dans les deux sens le garantit). */
    layer_set_scroll_speed(1, 50);
    printf("speed_50 %d %d\n", layer_get_scroll_speed(1), layer_get_speed(1));
    int p = 50, avance = 1;
    for (int i = 0; i < 60; i++) {
        layer_set_scroll_speed(1, p + 1);
        if (layer_get_scroll_speed(1) != p + 1) avance = 0;
        p = layer_get_scroll_speed(1);
    }
    printf("speed_incrementale %d %d\n", avance, p);
    layer_set_scroll_speed(2, -20);
    printf("speed_negative %d\n", layer_get_scroll_speed(2));
    printf("speed_voisin %d\n", layer_get_speed(3));   /* jamais écrit : la vitesse d'un autre n'a pas bougé */

    /* Bornes de caméra : monde large (bornage normal), puis monde plus étroit que
       l'écran (la caméra reste collée au bord, jamais en dehors). */
    g_bounds_x = 10; g_bounds_y = 20; g_bounds_w = 400; g_bounds_h = 300;
    cam_x = 999; cam_y = -5;
    camera_apply_bounds();
    printf("cam_large %d %d\n", cam_x, cam_y);
    g_bounds_w = 100; g_bounds_h = 50;
    cam_x = 500; cam_y = 500;
    camera_apply_bounds();
    printf("cam_etroit_haut %d %d\n", cam_x, cam_y);
    cam_x = -500; cam_y = -500;
    camera_apply_bounds();
    printf("cam_etroit_bas %d %d\n", cam_x, cam_y);
    /* Divisions par zéro : une composante nulle donne 0, jamais une trappe. */
    vec("div2", vec2_div((Vec2){ 10, 7 }, (Vec2){ 0, 2 }));
    Vec3 d3 = vec3_div((Vec3){ 9, 8, 7 }, (Vec3){ 3, 0, 0 });
    printf("div3 %d %d %d\n", d3.x, d3.y, d3.z);
    /* actor_move_to : vitesse négative sur la cible (dist == 0), puis loin de la cible. */
    Actor m; m.x = 5 << 8; m.y = 5 << 8;
    actor_move_to(&m, (Vec2){ 5, 5 }, -3);
    printf("move_sur_cible %d %d\n", m.x >> 8, m.y >> 8);
    actor_move_to(&m, (Vec2){ 50, 5 }, -3);
    printf("move_vitesse_negative %d %d\n", m.x >> 8, m.y >> 8);
    /* atan2 : arrondi au degré le plus proche (et non vers le haut), quadrants conservés. */
    printf("atan2 %d %d %d %d %d %d\n", math_atan2(1, 1000), math_atan2(100, 100),
           math_atan2(100, 0), math_atan2(0, -5), math_atan2(-100, -100), math_atan2(-100, 1));
    /* Courbes : bornes (num hors [0, den], den nul) puis milieu de chaque courbe. */
    printf("ease_bornes %d %d %d %d\n", math_ease(10, 90, -3, 10, EASE_IN), math_ease(10, 90, 12, 10, EASE_IN),
           math_ease(10, 90, 5, 0, EASE_IN), math_lerp(7, 99, 3, 0));
    printf("ease_milieu %d %d %d\n", math_ease(0, 100, 5, 10, EASE_IN), math_ease(0, 100, 5, 10, EASE_OUT),
           math_ease(0, 100, 5, 10, EASE_IN_OUT));
    /* Sinus : table 0..90° repliée sur les quatre quadrants, angles négatifs compris. */
    printf("sin %d %d %d %d %d %d %d %d\n", math_sin(0), math_sin(30), math_sin(90), math_sin(150),
           math_sin(210), math_sin(270), math_sin(359), math_sin(-30));
    printf("cos %d %d %d\n", math_cos(0), math_cos(180), math_cos(-90));
    /* Wobble : départ à -amount (350°), retombe à 0 en fin de durée, durée nulle sans division. */
    actor_wobble(a, 0, 30, 10);   int w0 = actor_get_sprite_rotation(a);
    actor_wobble(a, 30, 30, 10);  int w1 = actor_get_sprite_rotation(a);
    actor_wobble(a, 0, 0, 10);    int w2 = actor_get_sprite_rotation(a);
    printf("wobble %d %d %d\n", w0, w1, w2);
    /* Marge de suivi : bornée à la demi-largeur / demi-hauteur, jamais négative. */
    camera_set_margin((Vec2){ 500, -3 });
    printf("marge %d %d\n", g_cam_margin_x, g_cam_margin_y);
    camera_set_margin((Vec2){ 7, 500 });
    printf("marge_y %d %d\n", g_cam_margin_x, g_cam_margin_y);

    /* Références d'acteur : l'emplacement change de main, la référence cesse de résoudre. */
    {
        Actor *x = &g_actors[0];
        x->gen = 0; x->active = 1;
        int h = actor_ref_make(x);
        printf("ref_make %d %d\n", h != 0, actor_ref_make(0));
        printf("ref_get %d %d\n", actor_ref_get(h) == x, actor_ref_get(0) == 0);
        actor_set_active(x, 0);
        printf("ref_inactif %d\n", actor_ref_get(h) == x);        /* désactivé : adressable */
        actor_set_active(x, 1);
        actor_destroy_internal(x);
        printf("ref_detruit %d\n", actor_ref_get(h) == 0);        /* détruit : plus rien */
        x->active = 1; x->gen++;                                   /* un spawn y naît */
        printf("ref_reoccupe %d\n", actor_ref_get(h) == 0);       /* l'ancienne reste périmée */
        int h2 = actor_ref_make(x);
        printf("ref_neuve %d %d\n", h2 != h, actor_ref_get(h2) == x);
        printf("ref_indice %d\n", (actor_ref_make(&g_actors[1]) & 0xFFFF) == 1);
    }

    /* Cycle de vie d'un emplacement : détruit = libre, désactivé = occupé et adressable. */
    {
        Actor *x = &g_actors[0], *y = &g_actors[1];
        const ModelSlot deux[2] = { {0, 0}, {1, 0} };           /* un modèle de deux instances */
        const ModelSlot racine[1] = { {0, 0} };                  /* une seule instance */
        x->alive = 1; x->active = 1; y->alive = 1; y->active = 1;
        printf("vie_occupes %d %d\n", actor_model_count(deux, 2, 0), actor_live(x) == x);
        actor_set_active(x, 0);
        printf("vie_desactive %d %d\n", actor_live(x) == x, actor_model_count(deux, 2, 0));
        actor_set_active(x, 1);
        actor_destroy_internal(x);
        printf("vie_detruit %d %d %d\n", actor_live(x) == 0, x->alive, actor_model_count(deux, 2, 0));
        printf("vie_nth %d %d %d %d\n", actor_model_nth(deux, 2, 0, 0) == y, actor_model_nth(deux, 2, 0, 1) == 0,
               actor_model_nth(deux, 2, 0, -1) == 0, actor_model_nth(deux, 2, 0, 5) == 0);
        x->alive = 1; x->active = 1;                                /* un spawn reprend l'emplacement */
        printf("vie_nth_ordre %d %d\n", actor_model_nth(deux, 2, 0, 0) == x, actor_model_nth(deux, 2, 0, 1) == y);
        /* La table dit où sont les instances : ici une seule, dont la racine est l'emplacement 0. */
        printf("vie_groupe %d\n", actor_model_count(racine, 1, 0));
        /* Et elles n'ont pas à être contiguës ni dans l'ordre des emplacements. */
        const ModelSlot eclate[2] = { {1, 0}, {0, 0} };
        printf("vie_eclate %d %d\n", actor_model_nth(eclate, 2, 0, 0) == y, actor_model_nth(eclate, 2, 0, 1) == x);
        /* Le pool PARTAGÉ : les instances d'un modèle se retrouvent à `Actor.model`, pas par la table. */
        g_spool_start = 0; g_spool_end = 2; g_spool_hw = 2;
        x->alive = 1; x->model = 3; y->alive = 1; y->model = 4;
        printf("pool_modele %d %d %d\n", actor_model_count(0, 0, 3), actor_model_count(0, 0, 4), actor_model_count(0, 0, 9));
        printf("pool_nth %d %d\n", actor_model_nth(0, 0, 4, 0) == y, actor_model_nth(0, 0, 3, 1) == 0);
        /* Une table de posés ET le pool partagé : les posés d'abord. */
        const ModelSlot posee[1] = { {1, 0} };
        printf("pool_mixte %d %d %d\n", actor_model_count(posee, 1, 3), actor_model_nth(posee, 1, 3, 0) == y,
               actor_model_nth(posee, 1, 3, 1) == x);
        /* Hors du pool utilisé (au-delà de `g_spool_hw`), rien n'est compté. */
        g_spool_hw = 1;
        printf("pool_hw %d\n", actor_model_count(0, 0, 4));
        /* Le bloc d'état d'un emplacement : un bloc de OBJ_STATE_STRIDE octets par `inst`. */
        x->inst = 0; y->inst = 1;
        printf("pool_etat %d\n", (int)((char*)(g_obj_state + (int)y->inst * (OBJ_STATE_STRIDE / 4)) - (char*)g_obj_state) == OBJ_STATE_STRIDE);
    }
    return 0;
}
