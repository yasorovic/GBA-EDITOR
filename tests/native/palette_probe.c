/* palette_probe.c : fait écrire des palettes par le VRAI moteur, puis les fait recopier au VBlank.

   Le moteur écrit dans la mémoire de palettes, à une adresse que cette machine n'a pas : la sonde lui substitue un
   tableau (le moteur laisse la porte ouverte, `#ifndef PAL_BG_RAM`). Le tableau part rempli de 0x7777, une valeur
   qu'aucune étape n'écrit : une case qui la garde n'a pas été recopiée.

   SORTIE : « <étape> <pool> <index> <couleur en hexadécimal> » pour les index 47 à 64 de chaque pool, puis
   « lu <index> <couleur> » pour ce que `get_color` rend.

   Les tables de début de scène (`g_pal_bg_<scène>` dans un vrai build) sont posées par `palette_scene_start` : le
   pool BG part de couleurs 0x05nn, le pool OBJ n'en a pas (NULL, comme une scène sans palette OBJ). */

#include <stdio.h>

static unsigned short fake_pal[512];
#define PAL_BG_RAM  ((vu16 *)fake_pal)
#define PAL_OBJ_RAM ((vu16 *)(fake_pal + 256))

#define GBA_ENGINE_IMPL
#include "gba_engine.h"

/* Symboles que le code GÉNÉRÉ fournit d'ordinaire (main.c), comme dans ui_fill_probe.c : la sonde n'en lit aucun
   d'autre que `g_palettes`, mais le moteur les déclare, donc l'éditeur de liens les réclame. */
vu16    gba_shim_registers[16];
OBJATTR gba_shim_oam[128];

void CpuFastSet(const void *source, void *dest, u32 mode) {
    (void)source; (void)dest; (void)mode;
}

const unsigned short g_palettes[2][16] = {
    {0x0000, 0x0101, 0x0102, 0x0103, 0x0104, 0x0105, 0x0106, 0x0107,
     0x0108, 0x0109, 0x010A, 0x010B, 0x010C, 0x010D, 0x010E, 0x010F},
    {0x0000, 0x0201, 0x0202, 0x0203, 0x0204, 0x0205, 0x0206, 0x0207,
     0x0208, 0x0209, 0x020A, 0x020B, 0x020C, 0x020D, 0x020E, 0x020F},
};
const int            g_palette_count = 2;
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
const UIRegionInfo   g_ui_regions[1];
const int            g_ui_region_count = 0;
const UIListInfo     g_ui_lists[1];
const short          g_ui_list_rows[1] = {0};
const int            g_ui_list_count = 0;
int g_ui_list_index[1], g_ui_list_first[1], g_ui_list_total[1], g_ui_list_timer[1];
int g_ui_list_active[1], g_ui_list_shown[1];
short g_ui_list_row_text[1] = {-1};
u32 _g_keys_held = 0;
int cam_x, cam_y;

int  global_read (int i)        { (void)i; return 0; }
void global_write(int i, int v) { (void)i; (void)v; }
int  global_read_at (int i, int k)        { (void)i; (void)k; return 0; }
void global_write_at(int i, int k, int v) { (void)i; (void)k; (void)v; }

const UIImageInfo   g_ui_images[1];
const int           g_ui_image_count = 0;
const UIElementInfo g_ui_elements[1];
const int           g_ui_element_count = 0;

static void imprimer(const char *etape) {
    for (int pool = 0; pool < 2; pool++)
        for (int i = 47; i <= 64; i++)
            printf("%s %d %d %04x\n", etape, pool, i, (unsigned)fake_pal[pool * 256 + i]);
}

static unsigned short scene_bg[256];

int main(void) {
    for (int i = 0; i < 512; i++) fake_pal[i] = 0x7777;
    for (int i = 0; i < 256; i++) scene_bg[i] = (unsigned short)(0x0500 + i);
    palette_scene_start(scene_bg, 0);

    palette_set_bg(3, 1);       imprimer("ecrite");     /* la copie change, pas la mémoire de palettes */
    palette_commit();           imprimer("recopiee");   /* la banque 3 du pool BG arrive, rien d'autre */

    fake_pal[48] = 0x1111;      /* la console n'y touche pas : si commit recopie sans raison, la case est écrasée */
    palette_commit();           imprimer("rien_a_recopier");

    palette_set_obj(3, 0);      palette_commit();       imprimer("obj");

    /* Une banque tenue par un script : couleur par couleur, puis rendue à son début de scène. */
    int banque = palette_bg_bank(3);
    palette_bank_set_color(banque, 5, palette_rgb(31, 0, 0));
    palette_bank_set_color(banque, 0, 0x1234);              /* l'index 0 n'est pas écrit */
    palette_bank_set_color(palette_bg_bank(16), 5, 0x1234); /* banque hors bornes : rien */
    printf("lu 5 %04x\n", (unsigned)palette_bank_get_color(banque, 5));
    palette_commit();           imprimer("couleur");
    palette_bank_reset(banque); palette_commit();       imprimer("reset");
    palette_bank_reset(palette_obj_bank(3)); palette_commit(); imprimer("reset_obj_sans_table");
    printf("lu rgb %04x\n", (unsigned)palette_rgb(40, 16, -2));

    /* Les effets de palette. Banque 3 du BG : couleur 5 = noir, 6 = rouge pur, le reste vient du début de scène
       (0x05nn, après le reset ci-dessus). */
    palette_bank_set_color(banque, 5, palette_rgb(0, 0, 0));
    palette_bank_set_color(banque, 6, palette_rgb(31, 0, 0));
    palette_bank_fade(banque, palette_rgb(31, 31, 31), 8);    palette_commit(); imprimer("fondu_moitie");
    printf("lu fondu %04x\n", (unsigned)palette_bank_get_color(banque, 5));   /* l'origine, pas le fondu */
    palette_bank_fade(banque, 0, 0);
    palette_bank_grayscale(banque, 16);                       palette_commit(); imprimer("gris");
    palette_bank_grayscale(banque, 0);
    palette_bank_invert(banque, 99);                          palette_commit(); imprimer("inverse");  /* borné à 16 */
    palette_bank_invert(banque, 0);                           palette_commit(); imprimer("sans_effet");
    palette_bank_fade(32, palette_rgb(31, 31, 31), 16);       /* pas une banque : le pool BG n'est pas touché */
    palette_pool_fade(7, palette_rgb(31, 31, 31), 16);        /* pas un pool */
    palette_commit();                                         imprimer("hors_bornes");

    /* L'effet de la banque passe avant celui du pool ; le pool atteint aussi l'index 0 des banques. */
    palette_bank_fade(banque, palette_rgb(0, 0, 0), 16);
    palette_pool_fade(palette_bg_pool(), palette_rgb(31, 31, 31), 8); palette_commit(); imprimer("pool_blanc");
    palette_pool_fade(palette_bg_pool(), 0, 0);               palette_commit(); imprimer("pool_retire");

    /* Une nouvelle scène part sans effet : la banque blanchie revient à ses couleurs d'origine. */
    palette_pool_invert(palette_obj_pool(), 16);              palette_commit();
    palette_scene_start(scene_bg, 0);                         palette_commit(); imprimer("nouvelle_scene");
    return 0;
}
