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
const AppearanceInit* g_appearance_init;
OamEntry g_oam_entries[2];   /* l'affichage des acteurs : Actor.oam_entry en est l'indice */

/* La carte de collision vit dans main.c ; la sonde la remplace par un stub dont
   la réponse dit quelles coordonnées lui sont arrivées. */
int collision_map_tile(int px, int py) { return px * 10 + py; }

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
           actor_get_frame_h(a), actor_get_pal(a), actor_get_auto_dir(a), o->timer);
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
    return 0;
}
