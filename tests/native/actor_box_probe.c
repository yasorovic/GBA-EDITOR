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
#include "contacts_gen.h"   /* les aides des contacts, émises par le générateur (cf. physics/contacts.py) */

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

Actor g_actors[64];
u16 *g_actor_floor = 0;
u8 *g_drop_through = 0;
u8 g_support_normal = 1;
int g_gravity_x = 0, g_gravity_y = 0;
int g_rigid_rest[64][2];
u32 g_obj_state[16];
int g_spool_start = 0, g_spool_end = 0, g_actor_slot_end = 0, g_spool_entry = -1, g_spool_free = 0;
u32 g_alive_bits[16];
int g_scene_placed = 0;
SlotLink g_slot_link[64]; int g_slot_depth = 0;
u32 g_alive_epoch;
PoolCursor g_nth;
const u8 *g_spool_part = 0;
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

/* Les contacts d'une paire d'acteurs : enter, collide, exit, et un côté B qui ne répond qu'à enter. */
static int s_ev_a[3], s_ev_b[3];
static u8 s_tag_a, s_tag_b;
static void a_enter(Actor *s, Actor *o, u8 m, u8 t)   { (void)s; (void)o; s_ev_a[0]++; s_tag_a = m; s_tag_b = t; }
static void a_collide(Actor *s, Actor *o, u8 m, u8 t) { (void)s; (void)o; (void)m; (void)t; s_ev_a[1]++; }
static void a_exit(Actor *s, Actor *o, u8 m, u8 t)    { (void)s; (void)o; (void)m; (void)t; s_ev_a[2]++; }
static void b_enter(Actor *s, Actor *o, u8 m, u8 t)   { (void)s; (void)o; (void)m; (void)t; s_ev_b[0]++; }
static void b_exit(Actor *s, Actor *o, u8 m, u8 t)    { (void)s; (void)o; (void)m; (void)t; s_ev_b[2]++; }
static void a_replace_other(Actor *s, Actor *o, u8 m, u8 t) {
    (void)s; (void)m; (void)t;
    if (o->slot_index != 1) return;
    Actor replacement = *o;
    actor_destroy_internal(o);
    actor_init_slot(1, -1, &replacement, 0);
}
/* Le type 1 (emplacement 0) répond aux trois crochets, le type 2 (emplacement 1) à enter et exit. */
static ModelDesc s_desc[3];
static const u8 s_ki[3] = {255, 0, 1};
static const u16 s_allowed[2][2] = {{0, 0xFFFF}, {0xFFFF, 0}};
static ContactBody s_list[2];
static Contact s_prev[1], s_cur[1];
static int s_prev_n;
static void contact_frame(const char *nom) {
    contacts_run(s_desc, s_ki, &s_allowed[0][0], 2, s_list, s_prev, &s_prev_n, s_cur, 1);
    printf("%s %d %d %d %d %d\n", nom, s_ev_a[0], s_ev_a[1], s_ev_a[2], s_ev_b[0], s_ev_b[2]);
}

/* Les Areas : `g_areas` est défini par main.c d'ordinaire ; le runtime en déclare l'extern. Les deux côtés du scénario de
   parité (deux emplacements passés par `area_contact_step`, chacun avec sa mémoire) écrivent chacun
   dans leur ligne de `s_area_ev` : enter, collide, exit. */
Area g_areas[4];
static int s_area_ev[2][3];
static u8 s_area_tag[2];
static void ap_enter(Actor *s, Area *a, u8 t)   { (void)s; (void)a; s_area_ev[0][0]++; s_area_tag[0] = t; }
static void ap_collide(Actor *s, Area *a, u8 t) { (void)s; (void)a; (void)t; s_area_ev[0][1]++; }
static void ap_exit(Actor *s, Area *a, u8 t)    { (void)s; (void)a; (void)t; s_area_ev[0][2]++; }
static void as_enter(Actor *s, Area *a, u8 t)   { (void)s; (void)a; s_area_ev[1][0]++; s_area_tag[1] = t; }
static void as_collide(Actor *s, Area *a, u8 t) { (void)s; (void)a; (void)t; s_area_ev[1][1]++; }
static void as_exit(Actor *s, Area *a, u8 t)    { (void)s; (void)a; (void)t; s_area_ev[1][2]++; }
/* Le script de l'Area (`on_actor_*`) : il reçoit l'acteur et le tag de sa boîte. Ligne 0 pour le posé, 1 pour le né. */
static int s_own_ev[2][3];
static u8 s_own_tag[2];
static int own_row(Actor *o) { return o == &g_actors[4] ? 0 : 1; }
static void own_enter(Actor *o, u8 t)   { s_own_ev[own_row(o)][0]++; s_own_tag[own_row(o)] = t; }
static void own_collide(Actor *o, u8 t) { (void)t; s_own_ev[own_row(o)][1]++; }
static void own_exit(Actor *o, u8 t)    { (void)t; s_own_ev[own_row(o)][2]++; }
/* Un crochet d'acteur qui détruit l'acteur : le script de l'Area ne doit pas recevoir un acteur mort. */
static void ap_enter_destroy(Actor *s, Area *a, u8 t) { (void)a; (void)t; s->alive = 0; s->active = 0; }

int main(void) {
    for (int i = 0; i < 64; i++) g_slot_link[i].parent = -1;   /* chaque emplacement est une racine */
    Actor *a = &g_actors[0];
    Actor *b = &g_actors[1];
    a->oam_entry = 0;
    b->oam_entry = 1;
    a->collision.box_count = 2;
    a->collision.boxes[0] = (CollisionShape){ 0,  0, 16, 16, 1, 1, TAG_BODY };
    a->collision.boxes[1] = (CollisionShape){ 2, -3,  8,  8, 0, 1, TAG_HIT  };
    b->collision.box_count = 1;
    b->collision.boxes[0] = (CollisionShape){ 0,  0, 16, 16, 1, 1, TAG_BODY };

    /* Le tag choisit la bonne boîte : la référence est un rang, 0 = absente. */
    int body = actor_get_box(a, TAG_BODY);
    int hit  = actor_get_box(a, TAG_HIT);
    int none = actor_get_box(a, TAG_NONE);
    int bbox = actor_get_box(b, TAG_BODY);
    printf("refs %d %d %d %d\n", body, hit, none, bbox);
    printf("tags %d %d\n", collision_shape_get_tag(body), collision_shape_get_tag(hit));

    /* Décalage et taille, lus séparément. */
    vec("offset_body", collision_shape_get_offset(body));
    vec("offset_hit",  collision_shape_get_offset(hit));
    vec("size_hit",    collision_shape_get_size(hit));

    /* Une écriture hors bornes est SERRÉE, elle ne déborde pas. */
    collision_shape_set_offset(hit, (Vec2){ 500, -500 });
    collision_shape_set_size(hit,   (Vec2){ 300, -4 });
    vec("offset_borne", collision_shape_get_offset(hit));
    vec("size_borne",   collision_shape_get_size(hit));
    vec("voisine_offset", collision_shape_get_offset(body));
    vec("voisine_size",   collision_shape_get_size(body));
    collision_shape_set_offset(hit, (Vec2){ 4, 5 });
    collision_shape_set_size(hit,   (Vec2){ 6, 7 });
    vec("offset_normal", collision_shape_get_offset(hit));
    vec("size_normal",   collision_shape_get_size(hit));

    /* solid et active : lecture, écriture, et l'autre boîte n'est pas touchée. */
    printf("solid_avant %d %d\n", collision_shape_get_solid(body), collision_shape_get_solid(hit));
    collision_shape_set_solid(hit, 5);          /* toute valeur non nulle = vrai */
    collision_shape_set_solid(body, 0);
    printf("solid_apres %d %d\n", collision_shape_get_solid(body), collision_shape_get_solid(hit));
    printf("active_avant %d %d\n", collision_shape_get_active(body), collision_shape_get_active(hit));
    collision_shape_set_active(hit, 0);
    printf("active_apres %d %d\n", collision_shape_get_active(body), collision_shape_get_active(hit));
    collision_shape_set_active(hit, 1);

    /* Une boîte absente : lecture vide, écriture sans effet. */
    vec("absente_offset", collision_shape_get_offset(none));
    rect("absente_bounds", collision_shape_get_bounds(none));
    collision_shape_set_offset(none, (Vec2){ 1, 1 });
    collision_shape_set_solid(none, 1);
    collision_shape_set_active(none, 1);
    printf("absente_solid %d\n", collision_shape_get_solid(none));
    printf("box_count %d\n", actor_get_box_count(a));

    /* Le rectangle MONDE : position en Q8 (>>8), plus décalage, plus taille. */
    collision_shape_set_offset(hit, (Vec2){ 2, -3 });
    collision_shape_set_size(hit,   (Vec2){ 8, 8 });
    a->x = 100 << 8;  a->y = 50 << 8;
    rect("bounds_body", collision_shape_get_bounds(body));
    rect("bounds_hit",  collision_shape_get_bounds(hit));

    /* Chevauchement : des PIXELS, pas du Q8. Deux 16x16 distants de 5 px se
       touchent, de 20 px non — y compris avec un reste sous-pixel. */
    b->x = (105 << 8) + 77;  b->y = 50 << 8;
    printf("overlap_5px  %d %d\n", collision_shape_overlaps_box(body, bbox),
                                    collision_shape_overlaps_actor(body, b));
    b->x = 120 << 8;
    printf("overlap_20px %d %d\n", collision_shape_overlaps_box(body, bbox),
                                    collision_shape_overlaps_actor(body, b));
    b->x = 105 << 8;
    printf("actors_overlap %d\n", actors_overlap(a, b));

    /* Une boîte inactive ne touche personne, des deux côtés. */
    collision_shape_set_active(bbox, 0);
    printf("overlap_inactive_autre %d %d %d\n", collision_shape_overlaps_box(body, bbox),
                                                 collision_shape_overlaps_actor(body, b),
                                                 actors_overlap(a, b));
    collision_shape_set_active(bbox, 1);
    collision_shape_set_active(body, 0);
    printf("overlap_inactive_moi %d\n", collision_shape_overlaps_box(body, bbox));
    collision_shape_set_active(body, 1);
    printf("overlap_absente %d\n", collision_shape_overlaps_box(none, bbox));

    /* Contacts par couple de TAGS : un bit par couple, pour que le premier contact
       ne masque pas les suivants. `joueur` = un corps (haut) + des pieds (bas) ;
       `piece` = un seul corps. Tombée sur la pièce, c'est d'abord les pieds. */
    Actor *joueur = &g_actors[2];
    Actor *piece  = &g_actors[3];
    joueur->collision.box_count = 2;
    joueur->collision.boxes[0] = (CollisionShape){ 0,  0, 16, 16, 0, 1, TAG_BODY };
    joueur->collision.boxes[1] = (CollisionShape){ 0, 16, 16,  4, 1, 1, TAG_HIT  };
    piece->collision.box_count = 1;
    piece->collision.boxes[0] = (CollisionShape){ 0, 0, 8, 8, 0, 1, TAG_BODY };
    joueur->x = 0;  joueur->y = 0;
    piece->x = 4 << 8;
    piece->y = 18 << 8;                       /* ne touche que les pieds */
    printf("mask_pieds %d\n", actors_overlap_mask(joueur, piece, 0xFFFF));
    piece->y = 10 << 8;                       /* touche le corps ET les pieds */
    printf("mask_les_deux %d\n", actors_overlap_mask(joueur, piece, 0xFFFF));
    piece->y = 40 << 8;
    printf("mask_loin %d\n", actors_overlap_mask(joueur, piece, 0xFFFF));
    /* Deux boîtes de même tag chez le même acteur : UN seul contact. */
    joueur->collision.boxes[1].tag = TAG_BODY;
    piece->y = 10 << 8;
    printf("mask_meme_tag %d\n", actors_overlap_mask(joueur, piece, 0xFFFF));
    /* Une boîte inactive ne fait pas de contact. */
    joueur->collision.boxes[1].tag = TAG_HIT;
    joueur->collision.boxes[1].active = 0;
    printf("mask_inactive %d\n", actors_overlap_mask(joueur, piece, 0xFFFF));

    /* Au sol : par boîte, et une boîte absente est fausse. */
    a->collision.boxes[0].grounded = 1;
    a->collision.boxes[1].grounded = 0;
    printf("grounded %d %d %d\n", collision_shape_get_grounded(body),
                                  collision_shape_get_grounded(hit),
                                  collision_shape_get_grounded(none));

    /* La carte de collision, interrogée par la boîte. */
    printf("collision_tile %d %d\n", collision_shape_get_collision_tile(body, 3, 7),
                                     collision_shape_get_collision_tile(none, 3, 7));

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
        printf("ref_indice %d\n", (actor_ref_make(&g_actors[1]) & 0xFFFF) == 2);   /* indice + 1 : 0 reste « aucun » */
        /* Génération sur 16 bits : le bit de signe du handle est pris sans gêner, et une référence périmée le reste
           bien au-delà des 256 générations d'un octet. */
        x->gen = 0x8000;
        int hs = actor_ref_make(x);
        printf("ref_signe %d %d\n", hs < 0, actor_ref_get(hs) == x);
        x->gen = 0;
        int hv = actor_ref_make(x);
        for (int g = 0; g < 300; g++) x->gen++;
        printf("ref_300 %d\n", actor_ref_get(hv) == 0);
        x->gen = 0xFFFF;
        int hw = actor_ref_make(x);
        x->gen++;                                                    /* 0xFFFF -> 0 : le compteur boucle, la référence meurt */
        printf("ref_boucle %d %d\n", actor_ref_get(hw) == 0, hw != 0);
        g_actors[0].gen = 0;
        int h0 = actor_ref_make(&g_actors[0]);                       /* génération 0 sur l'emplacement 0 : jamais confondue avec nil */
        printf("ref_zero %d %d\n", h0 != 0, actor_ref_get(h0) == &g_actors[0]);
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
        /* Le pool PARTAGÉ : les instances d'un modèle se retrouvent à `Actor.type_id`, pas par la table. */
        g_spool_start = 0; g_spool_end = 2; g_actor_slot_end = 2;
        x->alive = 1; x->type_id = 3; y->alive = 1; y->type_id = 4;
        alive_bit_set(0); alive_bit_set(1);
        printf("pool_modele %d %d %d\n", actor_model_count(0, 0, 3), actor_model_count(0, 0, 4), actor_model_count(0, 0, 9));
        printf("pool_nth %d %d\n", actor_model_nth(0, 0, 4, 0) == y, actor_model_nth(0, 0, 3, 1) == 0);
        /* Une table de posés ET le pool partagé : les posés d'abord. */
        const ModelSlot posee[1] = { {1, 0} };
        printf("pool_mixte %d %d %d\n", actor_model_count(posee, 1, 3), actor_model_nth(posee, 1, 3, 0) == y,
               actor_model_nth(posee, 1, 3, 1) == x);
        /* Hors du pool utilisé (au-delà de `g_actor_slot_end`), rien n'est compté. */
        g_actor_slot_end = 1; g_alive_epoch++;       /* la borne a changé hors naissance/mort : le compte en cache est périmé */
        printf("pool_hw %d\n", actor_model_count(0, 0, 4));
        /* Le bloc d'état d'un emplacement : un bloc de OBJ_STATE_STRIDE octets par `inst`. */
        x->slot_index = 0; y->slot_index = 1;
        printf("pool_etat %d\n", (int)((char*)(g_obj_state + (int)y->slot_index * (OBJ_STATE_STRIDE / 4)) - (char*)g_obj_state) == OBJ_STATE_STRIDE);
        /* Un modèle à PARTIES : la racine (type 2) a un groupe de 3 aux emplacements 2..4, ses parties les types 3 et 4. */
        {
            static const u8 part[5] = {0, 0, 0, 1, 2};
            g_spool_part = part;
            g_spool_start = 2; g_spool_end = 8; g_actor_slot_end = 5; g_spool_free = 5;
            for (int i = 0; i < 8; i++) { g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; }
            g_alive_bits[0] = 0;
            for (int i = 2; i < 5; i++) { g_actors[i].alive = 1; g_actors[i].active = 1; g_actors[i].type_id = i; alive_bit_set(i); }
            /* la partie 1 (emplacement 3) a pour parent la racine, la partie 2 (emplacement 4) la partie 1 */
            actor_link_slot(3, 2, 1, 1, 0, 0); actor_link_slot(4, 3, 2, 1, 0, 0); g_slot_depth = 2;
            printf("grp_occupe %d %d %d %d\n", spool_slot_free(2), spool_slot_free(3), spool_slot_free(4), spool_slot_free(5));
            /* Les accès de groupe : la racine d'une partie, d'une racine et d'un modèle plat ; la partie k d'une racine. */
            printf("grp_acces %d %d %d %d %d %d\n", group_root_slot(3), group_root_slot(4), group_root_slot(2), group_root_slot(5),
                   group_part(&g_actors[2], 2) == &g_actors[4], group_slot(2, 1) == 3 && group_entry(10, 2) == 12);
            /* a.root et a.parent : la racine d'une partie, d'une racine, de nil ; le parent d'une partie, d'une partie
               de partie, d'une racine, de nil. */
            printf("grp_racine_de %d %d %d %d\n", actor_root(&g_actors[3]) == &g_actors[2], actor_root(&g_actors[4]) == &g_actors[2],
                   actor_root(&g_actors[2]) == &g_actors[2], actor_root(0) == 0);
            printf("grp_parent_de %d %d %d %d\n", actor_parent(&g_actors[3]) == &g_actors[2], actor_parent(&g_actors[4]) == &g_actors[3],
                   actor_parent(&g_actors[2]) == 0, actor_parent(0) == 0);
            actor_destroy_internal(&g_actors[3]);        /* une partie détruite : le groupe la garde, avec sa descendance */
            printf("grp_partie %d %d %d\n", g_actors[3].alive, spool_slot_free(3), g_spool_free);
            /* La partie 1 détruite emporte la partie 2 ; toutes deux gardent leur place, la racine vit. */
            printf("grp_apres_perte %d %d %d %d\n", g_actors[4].alive, spool_slot_free(4), actor_root(&g_actors[3]) == 0,
                   g_actors[2].alive);
            printf("grp_bits_partie %u\n", g_alive_bits[0]);     /* les parties détruites n'ont plus leur bit, la racine le garde */
            actor_destroy_internal(&g_actors[2]);        /* la racine : tout le groupe est rendu */
            printf("grp_racine %d %d %d %d %d\n", spool_slot_free(2), spool_slot_free(3), spool_slot_free(4),
                   g_actors[4].alive, g_actors[4].type_id);
            printf("grp_curseur %d\n", g_spool_free);
            printf("grp_bits_racine %u\n", g_alive_bits[0]);     /* le groupe entier est rendu : plus aucun bit */
            g_spool_part = 0; g_slot_depth = 0;
            for (int i = 2; i < 5; i++) g_slot_link[i].parent = -1;
            printf("grp_sans_table %d\n", group_root_slot(3));      /* sans table de parties, chaque emplacement est sa propre racine */
        }
    }

    /* Le curseur de `actor:get(modèle, i)` et le compte en cache : le même résultat qu'un parcours complet, quoi qu'il
       arrive entre deux appels (naissance, mort, boucle qui détruit au milieu). Suite pseudo-aléatoire, déterministe. */
    {
        enum { SLOTS = 64 };
        g_spool_part = 0;
        g_spool_start = 0; g_spool_end = SLOTS; g_actor_slot_end = SLOTS; g_spool_free = 0;
        for (int i = 0; i < SLOTS; i++) { g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; }
        g_alive_bits[0] = 0; g_alive_bits[1] = 0;
        unsigned seed = 12345u;
        #define RND() (seed = seed * 1103515245u + 12345u, (seed >> 16) & 0x7fff)
        int checks = 0, bad = 0, hits = 0;
        for (int step = 0; step < 6000; step++) {
            int op = RND() % 6;
            if (op == 0 || op == 1) {                                  /* naissance dans un emplacement libre */
                int k = RND() % SLOTS;
                if (!g_actors[k].alive) {
                    g_actors[k].alive = 1; g_actors[k].active = 1; g_actors[k].type_id = 1 + RND() % 3; g_actors[k].slot_index = k;
                    alive_bit_set(k);
                }
            } else if (op == 2) {                                      /* mort d'un vivant */
                int k = RND() % SLOTS;
                if (g_actors[k].alive) actor_destroy_internal(&g_actors[k]);
            } else if (op == 3) {                                      /* un rang quelconque */
                int m = 1 + RND() % 3, i = RND() % 12, want = -1, r = i;
                for (int k = 0; k < SLOTS; k++) if (g_actors[k].alive && g_actors[k].type_id == m && r-- == 0) { want = k; break; }
                Actor* got = actor_model_nth(0, 0, m, i);
                checks++; bad += (want < 0) ? (got != 0) : (got != &g_actors[want]);
            } else if (op == 4) {                                      /* une boucle de 0 au compte, un modèle */
                int m = 1 + RND() % 3, cnt = 0;
                for (int k = 0; k < SLOTS; k++) cnt += g_actors[k].alive && g_actors[k].type_id == m;
                checks++; bad += (actor_model_count(0, 0, m) != cnt);
                for (int i = 0; i < cnt; i++) {
                    int want = -1, r = i;
                    for (int k = 0; k < SLOTS; k++) if (g_actors[k].alive && g_actors[k].type_id == m && r-- == 0) { want = k; break; }
                    long before = g_nth.rank;
                    Actor* got = actor_model_nth(0, 0, m, i);
                    checks++; bad += (got != &g_actors[want]);
                    hits += (i > 0 && before == i - 1 && g_nth.rank == i);       /* avancer de 1 : le curseur a suivi */
                }
            } else {                                                   /* une boucle qui détruit l'élément qu'elle vient de lire */
                int m = 1 + RND() % 3, cnt = 0;
                for (int k = 0; k < SLOTS; k++) cnt += g_actors[k].alive && g_actors[k].type_id == m;
                for (int i = 0; i < cnt && i < actor_model_count(0, 0, m); i++) {
                    int want = -1, r = i;
                    for (int k = 0; k < SLOTS; k++) if (g_actors[k].alive && g_actors[k].type_id == m && r-- == 0) { want = k; break; }
                    Actor* got = actor_model_nth(0, 0, m, i);
                    checks++; bad += (want < 0) ? (got != 0) : (got != &g_actors[want]);
                    if (got && (RND() & 1)) actor_destroy_internal(got);
                }
            }
        }
        printf("nth_fuzz %d %d\n", bad, checks > 1000);
        printf("nth_curseur %d\n", hits > 100);
        #undef RND
    }

    /* La hiérarchie des acteurs POSÉS : 0 est le sommet, 1 son enfant, 2 l'enfant de 1 ; 3 est un autre sommet, 4 son enfant. */
    {
        g_spool_part = 0; g_scene_placed = 5; g_spool_start = g_spool_end = g_spool_free = 0; g_actor_slot_end = 5;
        for (int i = 0; i < 5; i++) { g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; g_actors[i].alive = 1; g_actors[i].active = 1; }
        actor_link_slot(1, 0, 1, 1, 0, 0); actor_link_slot(2, 1, 2, 1, 0, 0);
        actor_link_slot(4, 3, 1, 1, 0, 0); g_slot_depth = 2;
        printf("pose_parent %d %d %d %d %d\n", actor_parent(&g_actors[1]) == &g_actors[0], actor_parent(&g_actors[2]) == &g_actors[1],
               actor_parent(&g_actors[0]) == 0, actor_parent(&g_actors[4]) == &g_actors[3], actor_parent(0) == 0);
        printf("pose_racine %d %d %d %d %d\n", actor_root(&g_actors[2]) == &g_actors[0], actor_root(&g_actors[1]) == &g_actors[0],
               actor_root(&g_actors[0]) == &g_actors[0], actor_root(&g_actors[4]) == &g_actors[3], actor_root(0) == 0);
        /* le « Bras » de « Chef » : l'enfant posé se lit par la référence au parent, nil si elle est nil ou si l'enfant est mort */
        printf("pose_enfant %d %d\n", actor_placed_child(&g_actors[0], &g_actors[1]) == &g_actors[1],
               actor_placed_child(0, &g_actors[1]) == 0);
        actor_destroy_internal(&g_actors[1]);                  /* le maillon du milieu : détruire un parent détruit ses enfants */
        printf("pose_milieu_mort %d %d %d %d\n", g_actors[2].alive, actor_root(&g_actors[2]) == 0, g_actors[0].alive,
               actor_placed_child(&g_actors[0], &g_actors[1]) == 0);
        actor_destroy_internal(&g_actors[3]);                  /* l'autre sommet : son enfant part avec lui */
        printf("pose_sommet_mort %d %d\n", g_actors[4].alive, g_actors[0].alive);
        for (int i = 0; i < 5; i++) g_slot_link[i].parent = -1;
        g_slot_depth = 0;
        printf("pose_sans_lien %d %d\n", actor_parent(&g_actors[0]) == 0, actor_root(&g_actors[0]) == &g_actors[0]);
        g_scene_placed = 0;
    }

    /* Les tables par emplacement hors d'Actor (floor, drop_through, ancre Rigid) : la destruction les rend à zéro, celles
       des autres emplacements ne bougent pas. */
    {
        static u16 sol[64]; static u8 chute[64];
        g_actor_floor = sol; g_drop_through = chute;
        for (int i = 0; i < 3; i++) {
            g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; g_actors[i].alive = 1; g_actors[i].active = 1;
            sol[i] = 7; chute[i] = 9; g_rigid_rest[i][0] = 100 + i; g_rigid_rest[i][1] = 200 + i;
        }
        actor_destroy_internal(&g_actors[1]);
        printf("tables_detruit %d %d %d %d\n", sol[1], chute[1], g_rigid_rest[1][0], g_rigid_rest[1][1]);
        printf("tables_voisins %d %d %d %d\n", sol[0], chute[2], g_rigid_rest[0][0], g_rigid_rest[2][1]);
        g_actor_floor = 0; g_drop_through = 0;                   /* projet sans floor ni sens unique : pas d'écriture */
        actor_destroy_internal(&g_actors[2]);
        printf("tables_sans_floor %d\n", g_rigid_rest[2][0]);
    }

    /* Une paire en contact : enter à la naissance, collide tant qu'elle dure, exit quand elle se défait, rien quand elle est
       éloignée ou qu'un côté est inactif. Les tags arrivent du bon côté (my_box d'abord). */
    {
        for (int i = 0; i < 2; i++) {
            g_actors[i] = (Actor){0}; g_actors[i].active = 1; g_actors[i].alive = 1; g_actors[i].type_id = i + 1;
            g_actors[i].collision.box_count = 1;
        }
        g_actors[0].collision.boxes[0] = (CollisionShape){ 0, 0, 16, 16, 1, 1, TAG_HIT };
        g_actors[1].collision.boxes[0] = (CollisionShape){ 0, 0, 16, 16, 1, 1, TAG_BODY };
        s_desc[1].on_contact[0] = a_enter; s_desc[1].on_contact[1] = a_collide; s_desc[1].on_contact[2] = a_exit;
        s_desc[2].on_contact[0] = b_enter; s_desc[2].on_contact[2] = b_exit;
        /* La scène du cas : deux posés (0 et 1), pas de pool ; les cas précédents ne doivent pas être parcourus. */
        for (int w = 0; w < 16; w++) g_alive_bits[w] = 0;
        g_spool_start = 0; g_actor_slot_end = 2; g_scene_placed = 2; alive_bit_set(0); alive_bit_set(1);
        s_prev_n = 0;
        contact_frame("contact_1");            /* superposés : enter */
        contact_frame("contact_2");            /* ça dure : collide */
        printf("contact_tags %d %d\n", s_tag_a, s_tag_b);
        g_actors[1].x = 100 << 8;
        contact_frame("contact_3");            /* éloignés : exit des deux côtés */
        contact_frame("contact_4");            /* rien de plus */
        g_actors[1].x = 0; g_actors[1].active = 0;
        contact_frame("contact_5");            /* un côté inactif : pas de contact */
        g_actors[1].active = 1;
        contact_frame("contact_6");            /* de nouveau : enter */
        g_actors[1].active = 0;
        contact_frame("contact_7");            /* désactivé : seul le partenaire actif (A) apprend exit */
        g_actors[1].active = 1;
        contact_frame("contact_8");            /* enter */
        g_actors[1].alive = 0; g_actors[1].active = 0;
        contact_frame("contact_9");            /* détruit : personne n'apprend exit */
        g_actors[1].alive = 1; g_actors[1].active = 1;
        contact_frame("contact_10");           /* enter */
        g_actors[1].gen++;
        contact_frame("contact_11");           /* emplacement réoccupé : un nouveau contact, sans exit de l'ancien */
    }
    {   /* Un callback réoccupe B : A-C reste valide, A-B et B-C ne doivent plus prévenir l'ancien B. */
        Actor initial = {.active = 1, .type_id = 2};
        initial.collision.box_count = 1;
        initial.collision.boxes[0] = (CollisionShape){ 0, 0, 16, 16, 1, 1, TAG_BODY };
        for (int i = 0; i < 3; i++) actor_init_slot(i, -1, &initial, 0);
        g_actors[0].type_id = 1;
        g_actor_slot_end = 3;
        s_desc[1].on_contact[0] = a_replace_other;
        s_ev_b[0] = 0;
        const u16 allowed[2][2] = {{0, 1}, {1, 1}};
        ContactBody list[3];
        Contact prev[3], cur[3];
        int prev_n = 0;
        contacts_run(s_desc, s_ki, &allowed[0][0], 2, list, prev, &prev_n, cur, 3);
        printf("contact_reoccupation_callback %d\n", s_ev_b[0]);

        /* B-C existe avant que A n'entre. A-C attend une place ; A-B peut entrer tout de suite. */
        s_desc[1].on_contact[0] = a_enter;
        s_ev_b[2] = 0;
        prev_n = 0;
        g_actors[0].x = 100 << 8;
        contacts_run(s_desc, s_ki, &allowed[0][0], 2, list, prev, &prev_n, cur, 2);
        g_actors[0].x = 0;
        contacts_run(s_desc, s_ki, &allowed[0][0], 2, list, prev, &prev_n, cur, 2);
        printf("contact_saturation %d %d %d %d\n", prev_n, prev[1].a, prev[1].b, s_ev_b[2]);
        contacts_run(s_desc, s_ki, &allowed[0][0], 2, list, prev, &prev_n, cur, 2);
        printf("contact_saturation_dure %d %d %d %d\n", prev_n, prev[1].a, prev[1].b, s_ev_b[2]);
        g_actors[2].x = 100 << 8;
        contacts_run(s_desc, s_ki, &allowed[0][0], 2, list, prev, &prev_n, cur, 2);
        printf("contact_saturation_liberee %d %d %d %d\n", prev_n, prev[0].a, prev[0].b, s_ev_b[2]);
    }
    {   /* scene.gravity : le côté d'appui suit l'axe dominant (le bas sans gravité ou à égalité), et un Rigid endormi
           reprend sa chute seulement si la gravité change. */
        g_scene_placed = 2;
        g_actors[0].physics_sleep = 30; g_actors[1].physics_sleep = 30;
        scene_set_gravity((Vec2){ 0, 64 });
        printf("gravite_reveil %d %d\n", g_actors[0].physics_sleep, g_actors[1].physics_sleep);
        g_actors[0].physics_sleep = 30;
        scene_set_gravity((Vec2){ 0, 64 });
        printf("gravite_inchangee %d\n", g_actors[0].physics_sleep);
        int n[7];
        scene_set_gravity((Vec2){ 0, -64 });   n[0] = g_support_normal;
        scene_set_gravity((Vec2){ 64, 0 });    n[1] = g_support_normal;
        scene_set_gravity((Vec2){ -64, 0 });   n[2] = g_support_normal;
        scene_set_gravity((Vec2){ 0, 64 });    n[3] = g_support_normal;
        scene_set_gravity((Vec2){ 50, 50 });   n[4] = g_support_normal;
        scene_set_gravity((Vec2){ -30, -50 }); n[5] = g_support_normal;
        scene_set_gravity((Vec2){ 0, 0 });     n[6] = g_support_normal;
        printf("gravite_normales %d %d %d %d %d %d %d\n", n[0], n[1], n[2], n[3], n[4], n[5], n[6]);
        scene_set_gravity((Vec2){ -12, 34 });
        Vec2 lue = scene_get_gravity();
        printf("gravite_lue %d %d\n", lue.x, lue.y);
        g_scene_placed = 0;
    }
    /* Areas : la même séquence pour deux emplacements, l'un posé et l'autre né. Ils passent par `area_contact_step`, chacun
       avec sa mémoire de la frame précédente : leurs compteurs doivent rester égaux. */
    {
        for (int i = 4; i < 6; i++) {
            g_actors[i] = (Actor){0};
            g_actors[i].active = 1; g_actors[i].alive = 1; g_actors[i].collision.box_count = 2;
            g_actors[i].collision.boxes[0] = (CollisionShape){ 0,  0, 16, 16, 0, 1, TAG_BODY };   /* le corps (rang 0) */
            g_actors[i].collision.boxes[1] = (CollisionShape){ 0, 16, 16,  4, 0, 1, TAG_HIT  };   /* les pieds (rang 1) */
        }
        g_areas[0] = (Area){ 100 << 8, 50 << 8, (CollisionShape){ 0, 0, 16, 16, 0, 1, TAG_HIT }, 1 };
        /* Seul le rang 1 (les pieds) rencontre le tag de l'Area : le masque cuit au build vaut 0b10. */
        static const AreaFn sur_posee[3] = { ap_enter, ap_collide, ap_exit };
        static const AreaFn sur_pool[3] = { as_enter, as_collide, as_exit };
        static const AreaActorFn script_area[3] = { own_enter, own_collide, own_exit };
        u16 prev_posee = 0, prev_pool = 0;
        /* Chaque ligne : les crochets de l'acteur (posé puis né), puis ceux du script de l'Area pour chacun d'eux. */
        #define AREA_FRAME(nom, px, py) do {                                                            \
            g_actors[4].x = g_actors[5].x = (px) << 8; g_actors[4].y = g_actors[5].y = (py) << 8;       \
            area_contact_step(&g_areas[0], &g_actors[4], 2, sur_posee, script_area, &prev_posee);       \
            area_contact_step(&g_areas[0], &g_actors[5], 2, sur_pool, script_area, &prev_pool);         \
            printf("%s %d %d %d %d %d %d %d %d %d %d %d %d\n", nom,                                      \
                   s_area_ev[0][0], s_area_ev[0][1], s_area_ev[0][2],                                   \
                   s_area_ev[1][0], s_area_ev[1][1], s_area_ev[1][2],                                   \
                   s_own_ev[0][0], s_own_ev[0][1], s_own_ev[0][2],                                      \
                   s_own_ev[1][0], s_own_ev[1][1], s_own_ev[1][2]);                                     \
        } while (0)
        printf("area_refs %d %d %d %d\n", area_ref(&g_areas[0]), area_get_tag(1), area_get_active(1), area_get_tag(0));
        AREA_FRAME("area_1_loin", 0, 0);
        AREA_FRAME("area_2_entre", 100, 34);       /* les pieds (y 50..54) recouvrent l'Area ; le corps la touche à peine : rien */
        printf("area_tag %d %d %d %d\n", s_area_tag[0], s_area_tag[1], s_own_tag[0], s_own_tag[1]);
        AREA_FRAME("area_3_dure", 100, 34);
        AREA_FRAME("area_4_corps_exclu", 100, 45);  /* le corps recouvre aussi, mais son tag n'est pas permis : un seul contact */
        AREA_FRAME("area_5_sort", 200, 34);
        AREA_FRAME("area_6_rentre", 100, 34);
        g_areas[0].active = 0;
        AREA_FRAME("area_7_area_inactive", 100, 34);   /* l'Area s'éteint : l'acteur apprend la sortie */
        g_areas[0].active = 1;
        AREA_FRAME("area_8_reactive", 100, 34);
        g_actors[4].active = g_actors[5].active = 0;
        AREA_FRAME("area_9_acteur_inactif", 100, 34);  /* un acteur inactif ne touche rien, et n'apprend aucune sortie */
        g_actors[4].active = g_actors[5].active = 1;
        AREA_FRAME("area_10_reactive", 100, 34);
        g_actors[4].active = g_actors[5].active = 0; g_actors[4].alive = g_actors[5].alive = 0;
        AREA_FRAME("area_11_detruit", 100, 34);        /* détruire est terminal : aucune sortie */
        #undef AREA_FRAME
        {   /* Sans script d'Area (`own` NULL) : seul l'acteur apprend le contact. Puis un crochet d'acteur qui le détruit :
               le script de l'Area ne reçoit pas cet acteur mort. */
            Actor sauve = g_actors[4];
            g_actors[4].active = 1; g_actors[4].alive = 1;
            g_actors[4].x = 100 << 8; g_actors[4].y = 34 << 8;
            for (int k = 0; k < 3; k++) s_own_ev[0][k] = 0;
            u16 prev = 0;
            area_contact_step(&g_areas[0], &g_actors[4], 2, sur_posee, 0, &prev);
            printf("area_sans_script %d\n", s_own_ev[0][0]);
            static const AreaFn detruit[3] = { ap_enter_destroy, 0, 0 };
            prev = 0;
            area_contact_step(&g_areas[0], &g_actors[4], 2, detruit, script_area, &prev);
            printf("area_acteur_detruit_par_son_crochet %d %d\n", g_actors[4].alive, s_own_ev[0][0]);
            g_actors[4] = sauve;
        }
        /* Le masque : un bit par RANG de boîte de l'acteur, filtré par `allowed` ; une Area ou une boîte inactive ne touche rien. */
        g_actors[4].alive = 1; g_actors[4].active = 1; g_actors[4].x = 100 << 8; g_actors[4].y = 45 << 8;
        printf("area_masque %d %d %d\n", area_overlap_mask(&g_areas[0], &g_actors[4], 0xFFFF),
               area_overlap_mask(&g_areas[0], &g_actors[4], 1), area_overlap_mask(&g_areas[0], &g_actors[4], 2));
        g_areas[0].box.active = 0;
        printf("area_masque_boite_inactive %d\n", area_overlap_mask(&g_areas[0], &g_actors[4], 0xFFFF));
        g_areas[0].box.active = 1; g_areas[0].active = 0;
        printf("area_masque_area_inactive %d\n", area_overlap_mask(&g_areas[0], &g_actors[4], 0xFFFF));
    }
    /* Areas : les accès d'un script. Une forme décalée de (2, 3) et grande de 16×12 ; la référence EST la constante du build. */
    {
        g_actors[4].alive = 1; g_actors[4].active = 1; g_actors[4].collision.box_count = 2;
        g_actors[4].x = 100 << 8; g_actors[4].y = 34 << 8;
        g_areas[0] = (Area){ 100 << 8, 50 << 8, (CollisionShape){ 2, 3, 16, 12, 0, 1, TAG_HIT }, 1 };
        int h = area_by_name(1);
        printf("area_acces %d %d %d\n", h, area_get_name(h), area_get_name(h) == 1);
        Vec2 pos = area_get_position(h);
        printf("area_position %d %d\n", pos.x, pos.y);
        area_set_position(h, (Vec2){ 7, 9 });
        printf("area_position_ecrite %d %d\n", g_areas[0].x >> 8, g_areas[0].y >> 8);
        Rect r = area_get_bounds(h);
        printf("area_bounds %d %d %d %d\n", r.x, r.y, r.w, r.h);       /* position, plus le décalage de la forme, plus sa taille */
        Vec2 taille = area_get_size(h);
        area_set_size(h, (Vec2){ 300, -4 });                                         /* hors bornes : serré, jamais de débordement */
        Vec2 serree = area_get_size(h);
        area_set_size(h, (Vec2){ 20, 6 });
        Rect apres = area_get_bounds(h);
        printf("area_taille %d %d %d %d %d %d %d\n", taille.x, taille.y, serree.x, serree.y, area_get_size(h).x, apres.w, apres.h);
        area_set_size(h, (Vec2){ 16, 12 });
        area_set_position(h, (Vec2){ 100, 50 });
        printf("area_recouvre %d\n", area_overlaps_actor(h, &g_actors[4]));          /* les pieds (y 50..54) touchent la forme (y 53..65) */
        g_actors[4].x = 300 << 8;
        printf("area_recouvre_loin %d\n", area_overlaps_actor(h, &g_actors[4]));
        g_actors[4].x = 100 << 8;
        area_set_active(h, 0);
        printf("area_inactive %d %d\n", area_get_active(h), area_overlaps_actor(h, &g_actors[4]));
        area_set_active(h, 7);                                                       /* toute valeur non nulle = vrai */
        printf("area_reactive %d %d\n", area_get_active(h), area_overlaps_actor(h, &g_actors[4]));
        g_actors[4].collision.boxes[0].active = 0; g_actors[4].collision.boxes[1].active = 0;
        printf("area_acteur_sans_boite_active %d\n", area_overlaps_actor(h, &g_actors[4]));
        /* Une référence absente (0) : lecture vide, écriture sans effet. */
        area_set_position(0, (Vec2){ 5, 5 });  area_set_active(0, 1);
        Vec2 vide = area_get_position(0);  Rect rv = area_get_bounds(0);
        printf("area_absente %d %d %d %d %d %d %d\n", vide.x, vide.y, rv.x, rv.y, rv.w, rv.h, area_overlaps_actor(0, &g_actors[4]));
        g_areas[0].box.active = 0;
        Rect sans = area_get_bounds(h);
        area_set_size(h, (Vec2){ 50, 50 });                                         /* sans forme : l'écriture ne la rallume pas */
        printf("area_sans_forme %d %d %d %d\n", sans.w, sans.h, area_get_size(h).x, g_areas[0].box.w);
    }
    /* Areas : une Area qui suit un acteur posé (l'emplacement 6, d'où `parent` = 7). Sa position est recomposée chaque frame par le
       build : un script ne la déplace pas. Tant que le parent est inactif ou détruit (`held`), elle ne touche personne. */
    {
        g_actors[6] = (Actor){0};
        g_actors[6].alive = 1; g_actors[6].active = 1;
        g_actors[4].alive = 1; g_actors[4].active = 1; g_actors[4].x = 100 << 8; g_actors[4].y = 34 << 8;
        g_actors[4].collision.boxes[0].active = 1; g_actors[4].collision.boxes[1].active = 1;
        g_areas[0] = (Area){ 100 << 8, 50 << 8, (CollisionShape){ 0, 0, 16, 16, 0, 1, TAG_HIT }, 1, 0, 7 };
        int h = 1;
        area_set_position(h, (Vec2){ 5, 5 });
        printf("area_parent_ecriture %d %d\n", g_areas[0].x >> 8, g_areas[0].y >> 8);          /* sans effet : elle ne bouge pas */
        area_set_size(h, (Vec2){ 20, 20 });
        printf("area_parent_taille %d %d\n", g_areas[0].box.w, g_areas[0].box.h);              /* la taille, elle, s'écrit */
        printf("area_parent_lue %d\n", area_get_parent(h) == &g_actors[6]);
        printf("area_parent_touche %d %d\n", area_overlaps_actor(h, &g_actors[4]), area_overlap_mask(&g_areas[0], &g_actors[4], 0xFFFF));
        g_areas[0].held = 1;                                                                    /* le parent s'est éteint */
        printf("area_parent_tenue %d %d\n", area_overlaps_actor(h, &g_actors[4]), area_overlap_mask(&g_areas[0], &g_actors[4], 0xFFFF));
        g_areas[0].held = 0;
        g_actors[6].alive = 0;                                                                  /* le parent est détruit */
        printf("area_parent_detruit %d\n", area_get_parent(h) == 0);
        g_areas[0].parent = 0;                                                                  /* sans parent : l'écriture passe */
        area_set_position(h, (Vec2){ 5, 6 });
        printf("area_libre %d %d %d\n", g_areas[0].x >> 8, g_areas[0].y >> 8, area_get_parent(h) == 0);
    }

    /* Les effets de zone : `area_effects_apply` est le pas commun du posé et du né, il n'a qu'une forme. Le corps est
       l'acteur 4 (boîte 0 de 8x8, centre à (104, 54)) ; la zone couvre (100,50)..(116,66). */
    {
        static const AreaEffect gravite = { &g_areas[0], 0, 64, 0, 0, 0, 0, 256, AREAFX_GRAVITY };
        static const AreaEffect force   = { &g_areas[0], 0, 0, 2560, -1280, 0, 0, 256, 0 };
        static const AreaEffect trainee = { &g_areas[0], 0, 0, 0, 0, 0, 0, 128, 0 };
        static const AreaEffect flotte  = { &g_areas[0], 0, 0, 0, 0, 256, 0, 256, 0 };
        static const AreaEffect secoue  = { &g_areas[0], 0, 0, 0, 0, 0, 100, 256, 0 };
        static const AreaEffect persos  = { &g_areas[0], 0, 0, 1000, 0, 0, 0, 256, AREAFX_CHARACTER };
        Actor *c = &g_actors[4];
        int gx, gy;
        /* Le descripteur du corps : `gravity_scale` nul = il ignore la gravité de scène ; l'échelle elle-même est
           appliquée ensuite par `body_motion_step`, pas ici. */
        static const ModelDesc suit   = { .body_mode = BODY_MODE_RIGID, .gravity_scale = 256 };
        static const ModelDesc suit2  = { .body_mode = BODY_MODE_RIGID, .gravity_scale = 512 };
        static const ModelDesc ignore = { .body_mode = BODY_MODE_KINEMATIC };
        static const ModelDesc perso  = { .body_mode = BODY_MODE_CHARACTER };
        g_actors[4] = (Actor){0};
        c->alive = 1; c->active = 1; c->x = 100 << 8; c->y = 50 << 8;
        c->collision.box_count = 1;
        c->collision.boxes[0] = (CollisionShape){ 0, 0, 8, 8, 0, 1, TAG_HIT };
        g_areas[0] = (Area){ 100 << 8, 50 << 8, (CollisionShape){ 0, 0, 16, 16, 0, 1, TAG_HIT }, 1 };

        gx = 5; gy = 100; area_effects_apply(&gravite, 1, c, 0, &suit, &gx, &gy);
        printf("fx_gravite %d %d\n", gx, gy);                                   /* remplacée par celle de la zone */
        gx = 5; gy = 100; area_effects_apply(&gravite, 1, c, 0, &suit2, &gx, &gy);
        printf("fx_gravite_echelle %d %d\n", gx, gy);                           /* multipliée par le gravity_scale du corps */
        gx = 5; gy = 100; area_effects_apply(&gravite, 1, c, 0, &ignore, &gx, &gy);
        printf("fx_gravite_ignoree %d %d\n", gx, gy);                           /* un corps qui ne suit pas la gravité */
        c->vx = 0; c->vy = 0; gx = 0; gy = 0;
        area_effects_apply(&force, 1, c, 0, &suit, &gx, &gy);
        printf("fx_force %d %d\n", c->vx, c->vy);
        c->vx = 256; c->vy = -256;
        area_effects_apply(&trainee, 1, c, 0, &suit, &gx, &gy);
        printf("fx_trainee %d %d\n", c->vx, c->vy);
        gx = 40; gy = 100;
        area_effects_apply(&flotte, 1, c, 0, &suit, &gx, &gy);
        printf("fx_flottaison %d %d\n", gx, gy);                                /* le centre est dans la zone : neutre */
        c->x = 112 << 8;                                                        /* centre à (116, 54) : hors de la zone */
        gx = 40; gy = 100;
        area_effects_apply(&flotte, 1, c, 0, &suit, &gx, &gy);
        printf("fx_flottaison_bord %d %d\n", gx, gy);                           /* il recouvre la zone mais flotte pas */
        c->x = 100 << 8;
        c->vx = 0; c->vy = 0; g_fx_rng = 1;
        area_effects_apply(&secoue, 1, c, 0, &suit, &gx, &gy);
        int t1x = c->vx, t1y = c->vy;
        c->vx = 0; c->vy = 0; g_fx_rng = 1;
        area_effects_apply(&secoue, 1, c, 0, &suit, &gx, &gy);
        printf("fx_turbulence %d %d %d\n", t1x == c->vx && t1y == c->vy, (c->vx >= -100 && c->vx <= 100),
               (c->vy >= -100 && c->vy <= 100));                                /* déterministe, bornée */
        c->vx = 0; c->vy = 0;
        area_effects_apply(&persos, 1, c, 0, &perso, &gx, &gy);
        printf("fx_personnage_ok %d\n", c->vx);                                 /* la zone le demande : il subit */
        c->vx = 0;
        area_effects_apply(&force, 1, c, 0, &perso, &gx, &gy);
        printf("fx_personnage_exclu %d\n", c->vx);                              /* la zone ne le demande pas : rien */
        c->vx = 0;
        g_areas[0].active = 0;
        area_effects_apply(&force, 1, c, 0, &suit, &gx, &gy);
        printf("fx_zone_inactive %d\n", c->vx);
        g_areas[0].active = 1; c->x = 200 << 8;
        area_effects_apply(&force, 1, c, 0, &suit, &gx, &gy);
        printf("fx_hors_zone %d\n", c->vx);
    }
    return 0;
}
