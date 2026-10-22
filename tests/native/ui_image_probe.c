/* ui_image_probe.c : fait poser puis masquer une image BG par le VRAI `ui_image_update`.

   Le moteur écrit en VRAM, à des adresses que cette machine n'a pas : la sonde substitue à `MAP_RAM` un
   tableau (le moteur laisse cette porte ouverte, `#ifndef MAP_RAM`). Une tilemap de 32x32 entrées porte un
   « cadre » de fond (entrée 0x2005, banque 2) ; une image de 16x16 px (2x2 cases) est posée dessus. On imprime
   ce que contiennent ses cases quand elle est posée, masquée, reposée, puis déplacée.

   SORTIE : « <étape> <col> <ligne> <entrée en hexadécimal> » pour chaque case de la zone 0..4 x 0..3.  */

#include <stdio.h>

static unsigned short fake_vram[0x8000];
#define MAP_RAM(sbb) ((vu16 *)(fake_vram + (sbb) * 0x400))

#define GBA_ENGINE_IMPL
#include "gba_engine.h"

/* Symboles que le code GÉNÉRÉ fournit d'ordinaire (main.c). La mise en page n'en
   lit aucun — la table de textes, les zones d'UI et la caméra vivent au-dessus
   d'elle —, mais le moteur les déclare, donc l'éditeur de liens les réclame. */
vu16    gba_shim_registers[16];
OBJATTR gba_shim_oam[128];

void CpuFastSet(const void *source, void *dest, u32 mode) {
    (void)source; (void)dest; (void)mode;
}

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
/* Une langue (la source), aucun texte — mêmes types imbriqués que le vrai
   codegen : la sonde ne rend aucun texte de la table,
   elle n'a donc besoin que des symboles pour satisfaire l'éditeur de liens. */
int g_lang = 0;
int g_lang_reload = 0;
/* Compte des langues ÉMISES (`font_emit`), sur lequel `lang_set` se borne. La
   sonde ne change pas de langue, mais `lang_set` n'est pas statique : elle est
   compilée, et l'éditeur de liens réclame le symbole. */
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
const UIRegionInfo   g_ui_regions[1];
const int            g_ui_region_count = 0;
const UIListInfo     g_ui_lists[1];
const short          g_ui_list_rows[1] = {0};
const int            g_ui_list_count = 0;
/* État vivant des listes : défini par main.c dans un vrai build, donc à
   fournir ici. La sonde n'en fait rien — elle interroge `text_layout`, pas la
   navigation — mais `ui_list_tick` est compilé avec le reste du moteur. */
int g_ui_list_index[1], g_ui_list_first[1], g_ui_list_total[1], g_ui_list_timer[1];
/* `active` et `shown` sont du même bois : l'état vivant d'une liste, posé par
   main.c depuis la valeur authorée. `row_text` retient ce qu'une rangée
   affiche, pour la redessiner au changement de style. */
int g_ui_list_active[1], g_ui_list_shown[1];
short g_ui_list_row_text[1] = {-1};
u32 _g_keys_held = 0;
int cam_x, cam_y;

int  global_read (int i)        { (void)i; return 0; }
void global_write(int i, int v) { (void)i; (void)v; }
int  global_read_at (int i, int k)        { (void)i; (void)k; return 0; }
void global_write_at(int i, int k, int v) { (void)i; (void)k; (void)v; }


static const unsigned char dirs0[2][3] = {{0, 0, 1}, {255, 0, 0}};
static const unsigned char st_start[1] = {0}, st_speed[1] = {0}, st_loop[1] = {0};
const UIImageInfo g_ui_images[1] = {{
    .x = 8, .y = 8, .w = 16, .h = 16, .target = 0, .anchor = 0, .actor = -1,
    .dirs = dirs0, .state_start = st_start, .state_speed = st_speed, .state_loop = st_loop,
    .n_states = 1, .state0 = 0, .playing = 0, .tile_base = 0, .tiles_per_frame = 4,
    .oam_rel = 0, .priority = 0, .cols = 1, .rows = 1, .speed = 0, .elem = 1 }};
const int g_ui_image_count = 1;
const UIElementInfo g_ui_elements[2] = {{-1, 1}, {0, 1}};   /* 0 = conteneur, 1 = l'image (enfant) */
const int g_ui_element_count = 2;

#define FOND 0x2005

static void imprimer(const char *etape) {
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 5; c++)
            printf("%s %d %d %04x\n", etape, c, r, (unsigned)*bg_se_addr(0, c, r));
}

int main(void) {
    g_text_layer = 0;
    g_bgcnt_sh[0] = (unsigned short)(4 << 8);              /* écran de tuiles n° 4 : fake_vram + 4 * 0x400 */
    for (int r = 0; r < 32; r++)
        for (int c = 0; c < 32; c++) *bg_se_addr(0, c, r) = FOND;   /* le fond du conteneur */
    ui_elements_reset();
    ui_images_reset();
    ui_image_set_bg_base(0, 100);

    ui_image_update();      imprimer("pose");
    ui_element_show(1, 0);
    ui_image_update();      imprimer("masque");
    ui_element_show(1, 1);
    ui_image_update();      imprimer("repose");
    ui_image_move(0, 8, 0);
    ui_image_update();      imprimer("deplace");
    return 0;
}
