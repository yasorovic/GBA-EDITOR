/* input_matcher_probe.c — interroge le VRAI matcheur d'input du moteur.

   Même intention que `text_layout_probe.c` : `held(nom, n)`, `released`,
   `buffered` et le matcheur de séquence (`input_seq_pressed`) vivent en C, dans
   `runtime_api_inline.h` — rien ici ne les réimplémente. La sonde rejoue une
   timeline de masques (un par frame, comme le ferait `scanKeys()`) à travers
   l'anneau et les compteurs RÉELS, et imprime ce que chaque primitive répond,
   frame par frame, pour un jeu de « watchers » déclarés une fois au départ.

   ENTRÉE (des entiers, séparés par des blancs) :
       n_frames
       mask[0] ... mask[n_frames-1]
       n_held_n         puis n_held_n lignes « mask n »
       n_released       puis n_released lignes « mask »
       n_seq            puis n_seq lignes « len m[0]..m[len-1] window »
       n_buffered       puis n_buffered lignes « action_index mask frames »

   SORTIE, pour chaque frame (après avoir poussé son masque dans l'anneau) :
       HELDN <r0> ... <r_{n_held_n-1}>
       RELEASED <r0> ...
       SEQ <r0> ...
       BUFFERED <r0> ...                                                    */

#include <stdio.h>
#include <stdlib.h>

#define GBA_ENGINE_IMPL
#include "gba_engine.h"
#include "actor_types_static.h"

/* Normalement émis dans runtime_api.h (généré, cf. scripting/api.py EASE_*) —
   le matcheur d'input n'en a pas besoin, mais runtime_api_inline.h est un seul
   fichier et `math_ease` (une AUTRE fonction du même en-tête) les référence :
   tout doit se parser, même ce que la sonde n'appelle jamais. */
#define EASE_IN     0
#define EASE_OUT    1
#define EASE_IN_OUT 2

#include "runtime_api_inline.h"

/* Symboles que `main.c` fournit d'ordinaire. Le matcheur d'input n'en lit
   aucun — ni acteur, ni OAM, ni texte — mais le moteur est compilé en entier :
   seules les primitives RÉELLEMENT appelées ci-dessous ont besoin d'une
   définition (cf. text_layout_probe.c pour la même remarque). */
vu16    gba_shim_registers[16];
OBJATTR gba_shim_oam[128];

void CpuFastSet(const void *source, void *dest, u32 mode) {
    (void)source; (void)dest; (void)mode;
}

/* Le reste de `gba_engine.h` (listes UI, texte, sauvegarde, palettes...) est
   compilé avec, même si le matcheur d'input n'en appelle rien : ce ne sont pas
   des `static inline`, l'éditeur de lien réclame donc leurs symboles. Même
   bloc que `ui_list_probe.c` / `text_layout_probe.c`. */
const unsigned short g_palettes[1][16] = {{0}};
const int            g_palette_count = 0;
const unsigned int   g_save_id[1]  = {0};
const unsigned short g_save_idx[1] = {0};
const int            g_save_def[1] = {0};
const int            g_save_count = 0;
const int            g_save_slots = 0;
const int            g_save_slot_size = 0;
const FontInfo       g_fonts[1];
const int            g_font_count = 0;
const unsigned char  g_lang_font_0[1] = {0};
const unsigned char* const g_lang_font[1] = {g_lang_font_0};
int g_lang = 0;
int g_lang_reload = 0;
const int g_lang_count = 1;
const unsigned short* const g_texts_0[1] = {0};
const unsigned short* const* const g_texts[1] = {g_texts_0};
const unsigned short g_text_len_0[1] = {0};
const unsigned short* const g_text_len[1] = {g_text_len_0};
const TextEvent* const g_text_events_0[1] = {0};
const TextEvent* const* const g_text_events[1] = {g_text_events_0};
const unsigned short g_text_ev_count_0[1] = {0};
const unsigned short* const g_text_ev_count[1] = {g_text_ev_count_0};
const unsigned short g_text_values_0[1] = {0};
const unsigned short* const g_text_values[1] = {g_text_values_0};
const unsigned short g_save_len[1]  = {0};
const unsigned char  g_save_bits[1] = {0};
const UIImageInfo    g_ui_images[1];
const int            g_ui_image_count = 0;
const UIElementInfo  g_ui_elements[1];
const int            g_ui_element_count = 0;
int cam_x, cam_y;

int  global_read (int i)        { (void)i; return 0; }
void global_write(int i, int v) { (void)i; (void)v; }
int  global_read_at (int i, int k)        { (void)i; (void)k; return 0; }
void global_write_at(int i, int k, int v) { (void)i; (void)k; (void)v; }

#define PROBE_ROWS_MAX 1
const UIListInfo   g_ui_lists[1] = {{1, 1, 0, 0, 0, 0, 0, -1, 0, 1, 0, 0}};
const short        g_ui_list_rows[PROBE_ROWS_MAX] = {0};
const int          g_ui_list_count = 1;
const UIRegionInfo g_ui_regions[PROBE_ROWS_MAX];
const int          g_ui_region_count = PROBE_ROWS_MAX;
short g_ui_list_row_text[PROBE_ROWS_MAX];
int   g_ui_list_index[1], g_ui_list_first[1], g_ui_list_total[1];
int   g_ui_list_timer[1], g_ui_list_active[1], g_ui_list_shown[1];

#define RING_DEPTH 32
#define MAX_QUERIES 16
#define MAX_SEQ_LEN 8

u32 _g_keys_held    = 0;
u32 _g_keys_pressed = 0;
u16       _g_input_ring[RING_DEPTH];
int       _g_input_ring_pos = 0;
const int g_input_ring_depth = RING_DEPTH;
u8 _g_key_hold_frames[10];
u8 _g_input_buffered_consumed[1] = {0};

int main(void) {
    int n_frames;
    if (scanf("%d", &n_frames) != 1) return 1;
    int *frame_masks = (int*)malloc(sizeof(int) * (size_t)n_frames);
    for (int i = 0; i < n_frames; i++)
        if (scanf("%d", &frame_masks[i]) != 1) return 1;

    int n_heldn;
    scanf("%d", &n_heldn);
    int heldn_mask[MAX_QUERIES], heldn_n[MAX_QUERIES];
    for (int i = 0; i < n_heldn; i++)
        scanf("%d %d", &heldn_mask[i], &heldn_n[i]);

    int n_released;
    scanf("%d", &n_released);
    int released_mask[MAX_QUERIES];
    for (int i = 0; i < n_released; i++)
        scanf("%d", &released_mask[i]);

    int n_seq;
    scanf("%d", &n_seq);
    int seq_len[MAX_QUERIES], seq_window[MAX_QUERIES];
    u16 seq_masks[MAX_QUERIES][MAX_SEQ_LEN];
    for (int i = 0; i < n_seq; i++) {
        scanf("%d", &seq_len[i]);
        for (int j = 0; j < seq_len[i]; j++) {
            int m; scanf("%d", &m); seq_masks[i][j] = (u16)m;
        }
        scanf("%d", &seq_window[i]);
    }

    int n_buffered;
    scanf("%d", &n_buffered);
    int buf_action[MAX_QUERIES], buf_mask[MAX_QUERIES], buf_frames[MAX_QUERIES];
    for (int i = 0; i < n_buffered; i++)
        scanf("%d %d %d", &buf_action[i], &buf_mask[i], &buf_frames[i]);

    for (int f = 0; f < n_frames; f++) {
        _g_keys_held = (u32)frame_masks[f];
        _input_ring_push(_g_keys_held);
        _input_update_hold_frames(_g_keys_held);

        printf("HELDN");
        for (int i = 0; i < n_heldn; i++)
            printf(" %d", input_held_n(heldn_mask[i], heldn_n[i]));
        printf("\n");

        printf("RELEASED");
        for (int i = 0; i < n_released; i++)
            printf(" %d", input_released(released_mask[i]));
        printf("\n");

        printf("SEQ");
        for (int i = 0; i < n_seq; i++)
            printf(" %d", input_seq_pressed(seq_masks[i], seq_len[i], seq_window[i]));
        printf("\n");

        printf("BUFFERED");
        for (int i = 0; i < n_buffered; i++)
            printf(" %d", input_buffered(buf_action[i], buf_mask[i], buf_frames[i]));
        printf("\n");
    }
    return 0;
}
