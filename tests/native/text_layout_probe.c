/* text_layout_probe.c — interroge le VRAI `text_layout` du moteur.

   `core/engine_emulation/text_layout.py` rejoue en Python ce que
   `runtime/include/gba_engine.h` fait en C : c'est l'aperçu de l'éditeur qui
   promet à l'auteur où ses glyphes atterriront. ARCHITECTURE.md le dit sans
   détour — « DEUX implémentations à tenir d'accord ». Rien, jusqu'ici, ne
   vérifiait qu'elles le restaient, et une divergence ne se voit qu'après le
   build, sur la console, comme un décalage que rien n'explique.

   Cette sonde donne à la suite de tests une porte d'entrée sur le C d'origine :
   elle lit une police et un texte sur son entrée standard, appelle le moteur, et
   imprime où chaque glyphe est tombé. Aucune ligne du moteur n'est recopiée ici
   — c'est tout l'intérêt : le jour où quelqu'un touche à la coupe au mot d'un
   côté seulement, le test tombe.

   COMMENT ON LIT LES POSITIONS SANS DESSINER. Le moteur écrit normalement en
   VRAM, à des adresses que cette machine n'a pas. On emprunte donc son propre
   mécanisme de CAPTURE (`g_cap_max > 0`, cf. gba_engine.h) : sous une portée
   animée, la mise en page NOTE le glyphe au lieu de le poser. En couvrant tout
   le texte d'un `[wave]`, chaque glyphe est capturé, rien n'est dessiné, et le
   chemin parcouru reste celui du rendu — pas celui de la mesure.

   ENTRÉE (des entiers, séparés par des blancs) :
       line_h cell_w composited n_glyphs
       cp[n] adv[n] gw[n] gh[n] seq_off[n] seq_len[n]
       n_seq seq[n_seq]
       clip_w clip_h wrap_tiles align
       slen s[slen]

   SORTIE :
       CAP <n>            puis n lignes « <x> <y> <index de glyphe> »
       SIZE <w> <h>       l'étendue rendue, en tuiles (passe de mesure)  */

#include <stdio.h>

/* Le corps du moteur vit derrière ce drapeau — `main.c` le pose de la même
   façon (cf. runtime_codegen/main_gen.py). Sans lui, `gba_engine.h` ne livre que
   ses types, et la mise en page reste hors de portée. */
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
   codegen (ROADMAP v0.9 phase 3) : la sonde ne rend aucun texte de la table,
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
const UIImageInfo    g_ui_images[1];
const int            g_ui_image_count = 0;
const UIElementInfo  g_ui_elements[1];
const int            g_ui_element_count = 0;
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

/* ── Tampons d'entrée ─────────────────────────────────────────── */

#define PROBE_MAX_GLYPHS 128
#define PROBE_MAX_SEQ    256
#define PROBE_MAX_TEXT   TEXT_ANIM_MAX   /* cf. la garde plus bas */

static unsigned short probe_cp[PROBE_MAX_GLYPHS];
static unsigned short probe_slot[PROBE_MAX_GLYPHS];
static unsigned char  probe_adv[PROBE_MAX_GLYPHS];
static unsigned char  probe_gw[PROBE_MAX_GLYPHS];
static unsigned char  probe_gh[PROBE_MAX_GLYPHS];
static unsigned short probe_seq[PROBE_MAX_SEQ];
static unsigned short probe_seq_off[PROBE_MAX_GLYPHS];
static unsigned char  probe_seq_len[PROBE_MAX_GLYPHS];
static unsigned short probe_text[PROBE_MAX_TEXT];

static int lire(int *out) { return scanf("%d", out) == 1; }

static int lire_serie(int n, int limite, void *dest, int taille_element) {
    for (int i = 0; i < n; i++) {
        int v;
        if (i >= limite || !lire(&v)) return 0;
        if (taille_element == 1) ((unsigned char  *)dest)[i] = (unsigned char)v;
        else                     ((unsigned short *)dest)[i] = (unsigned short)v;
    }
    return 1;
}

int main(void) {
    int line_h, cell_w, composited, n_glyphs;
    if (!lire(&line_h) || !lire(&cell_w) || !lire(&composited) || !lire(&n_glyphs)) {
        fprintf(stderr, "entree tronquee : en-tete de police\n");
        return 2;
    }
    if (n_glyphs > PROBE_MAX_GLYPHS) {
        fprintf(stderr, "police trop grande : %d glyphes\n", n_glyphs);
        return 2;
    }
    if (!lire_serie(n_glyphs, PROBE_MAX_GLYPHS, probe_cp, 2)
     || !lire_serie(n_glyphs, PROBE_MAX_GLYPHS, probe_adv, 1)
     || !lire_serie(n_glyphs, PROBE_MAX_GLYPHS, probe_gw, 1)
     || !lire_serie(n_glyphs, PROBE_MAX_GLYPHS, probe_gh, 1)
     || !lire_serie(n_glyphs, PROBE_MAX_GLYPHS, probe_seq_off, 2)
     || !lire_serie(n_glyphs, PROBE_MAX_GLYPHS, probe_seq_len, 1)) {
        fprintf(stderr, "entree tronquee : tables de glyphes\n");
        return 2;
    }

    int n_seq;
    if (!lire(&n_seq) || n_seq > PROBE_MAX_SEQ
     || !lire_serie(n_seq, PROBE_MAX_SEQ, probe_seq, 2)) {
        fprintf(stderr, "entree tronquee : sequences\n");
        return 2;
    }

    int clip_w, clip_h, wrap, align;
    if (!lire(&clip_w) || !lire(&clip_h) || !lire(&wrap) || !lire(&align)) {
        fprintf(stderr, "entree tronquee : cadre\n");
        return 2;
    }

    int slen;
    if (!lire(&slen)) {
        fprintf(stderr, "entree tronquee : longueur du texte\n");
        return 2;
    }
    /* Garde INDISPENSABLE, pas défensive : au-delà du budget de capture le
       moteur se remet à DESSINER, donc à écrire en VRAM — à une adresse que ce
       processus n'a pas. Un codepoint donnant au plus un glyphe, borner le texte
       borne la capture. */
    if (slen > PROBE_MAX_TEXT) {
        fprintf(stderr, "texte trop long : %d codepoints, %d au plus "
                        "(budget de capture)\n", slen, PROBE_MAX_TEXT);
        return 2;
    }
    if (!lire_serie(slen, PROBE_MAX_TEXT, probe_text, 2)) {
        fprintf(stderr, "entree tronquee : texte\n");
        return 2;
    }

    FontInfo fi;
    fi.tiles   = 0;
    fi.n_tiles = 0;
    fi.pal     = 0;
    fi.cp      = probe_cp;
    fi.slot    = probe_slot;      /* jamais lu : rien n'est dessiné */
    fi.seq     = probe_seq;
    fi.seq_off = probe_seq_off;
    fi.seq_len = probe_seq_len;
    fi.gw      = probe_gw;
    fi.gh      = probe_gh;
    fi.n_glyphs  = n_glyphs;
    fi.tiles_x   = 1;
    fi.tiles_y   = 1;
    fi.adv       = probe_adv;
    fi.cell_w    = cell_w;
    fi.line_h    = line_h;
    fi.composited = composited;

    /* `g_font` est posé À LA MAIN : `text_set_font` chargerait les glyphes en
       VRAM, ce qui n'a de sens que sur la console. */
    g_font     = &fi;
    g_font_sub = 0;
    text_clip_set(0, 0, clip_w, clip_h);

    TextEvent tout_anime;
    tout_anime.at    = 0;
    tout_anime.end   = (unsigned short)slen;
    tout_anime.value = 0;
    tout_anime.kind  = TEXT_EV_WAVE;
    tout_anime.limit = 0;
    g_ev  = &tout_anime;
    g_nev = 1;

    g_cap_max = TEXT_ANIM_MAX;
    g_cap_n   = 0;
    text_layout(probe_text, slen, 0, 0, wrap, -1, 0, align, 0, 0, 0);

    printf("CAP %d\n", g_cap_n);
    for (int k = 0; k < g_cap_n; k++)
        printf("%d %d %d\n", g_cap_x[k], g_cap_y[k], g_cap_gi[k]);

    int w = 0, h = 0;
    g_cap_max = 0;             /* la mesure ne capture pas : elle ne dessine pas */
    text_layout(probe_text, slen, 0, 0, wrap, -1, 1, align, 0, &w, &h);
    printf("SIZE %d %d\n", w, h);
    return 0;
}
