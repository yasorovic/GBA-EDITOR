/* runtime/include/gba_debug.h — canal de diagnostic (ROADMAP v0.14)
 *
 * Le C émis par le codegen pour `debug:log(...)` et pour la mesure de
 * budget est LE MÊME en build debug et release (cf. codegen.py,
 * `_emit_debug_log` et main_gen.py) : ce header décide, en fournissant soit
 * les vraies fonctions (`-DGBA_DEBUG_BUILD`, posé par rom_build.py quand
 * ProjectSettings.debug_build est coché — cf. runtime/Makefile
 * EXTRA_CFLAGS), soit des stubs `inline` VIDES sinon. À -O2, un appel à un
 * stub vide disparaît par inlining : retiré à la compilation, sans qu'un
 * drapeau soit testé au runtime — la décision verrouillée de la ROADMAP.
 *
 * ── Le canal de log ─────────────────────────────────────────────
 * mGBA expose un port de debug (protocole documenté par le projet mGBA
 * lui-même, repris par la plupart des moteurs homebrew) : écrire une
 * chaîne à 0x4FFF600 puis un niveau à 0x4FFF700 la fait apparaître dans la
 * console de log de l'émulateur. Hors mGBA (matériel réel, autre
 * émulateur), ces adresses ne répondent à rien : l'écriture se perd
 * silencieusement, sans geler ni corrompre quoi que ce soit — testé, ce
 * n'est pas une hypothèse.
 *
 * `debug:log(...)` (script) ne formate rien : chaque argument est déjà une
 * chaîne littérale ou un entier, et le codegen émet une SÉQUENCE d'appels
 * à `debug_write_str`/`debug_write_int`, terminée par `debug_flush()` — pas
 * un `printf`, que le moteur évite partout ailleurs (ROADMAP v0.14,
 * décisions verrouillées, 2026-08-20).
 */
#ifndef GBA_DEBUG_H
#define GBA_DEBUG_H

#ifdef GBA_DEBUG_BUILD

#include <gba_types.h>
#include <gba_timers.h>

/* ── Port de log mGBA ─────────────────────────────────────────── */
#define MGBA_DEBUG_ENABLE   (*(vu16*)0x4FFF780)
#define MGBA_DEBUG_STRING   ((char*)0x4FFF600)
#define MGBA_DEBUG_FLAGS    (*(vu16*)0x4FFF700)
#define MGBA_DEBUG_SEND     0x0100
#define MGBA_DEBUG_LEVEL_INFO 3

static char _debug_buf[256];
static int  _debug_len = 0;

static inline void debug_init(void) {
    MGBA_DEBUG_ENABLE = 0xC0DE;
}

/* Concatène une chaîne dans le tampon de la ligne en cours — ne flush pas. */
static inline void debug_write_str(const char* s) {
    while (*s && _debug_len < 255) _debug_buf[_debug_len++] = *s++;
}

/* Concatène un entier signé, en base 10, sans passer par un printf. */
static inline void debug_write_int(int v) {
    char tmp[12];
    int n = 0;
    unsigned u;
    if (v < 0) { debug_write_str("-"); u = (unsigned)(-v); }
    else u = (unsigned)v;
    if (u == 0) tmp[n++] = '0';
    while (u) { tmp[n++] = (char)('0' + (u % 10)); u /= 10; }
    while (n > 0 && _debug_len < 255) _debug_buf[_debug_len++] = tmp[--n];
}

/* Envoie la ligne accumulée à mGBA et vide le tampon pour la suivante. */
static inline void debug_flush(void) {
    _debug_buf[_debug_len] = 0;
    for (int i = 0; i <= _debug_len; i++) MGBA_DEBUG_STRING[i] = _debug_buf[i];
    MGBA_DEBUG_FLAGS = MGBA_DEBUG_LEVEL_INFO | MGBA_DEBUG_SEND;
    _debug_len = 0;
}

/* ── Budget par frame ─────────────────────────────────────────────
 * Timer 3 : le seul des quatre timers matériels que Maxmod NE réserve PAS
 * (le mixage logiciel prend les timers 0/1 — cf. runtime/Makefile, -lmm).
 * Prescaler /64 → 262144 Hz, ~3.815 µs/tick ; une frame à 60 Hz (~16.7 ms)
 * tient en ~4370 ticks, largement sous les 65535 d'un compteur 16 bits :
 * pas besoin de timer en cascade pour mesurer UNE frame.
 *
 * OAM et canaux sonores/DMA : voir ROADMAP v0.14, section « Ouvert » —
 * seul le temps de frame et l'OAM sont de VRAIES mesures avec le SDK
 * installé ; les deux autres axes envisagés n'ont pas de source fiable et
 * ont été écartés plutôt que fabriqués.
 */
#define DEBUG_TIMER_PRESCALER_64  1   /* bits 0-1 de TMxCNT_H : 00=/1 01=/64 10=/256 11=/1024 */

static inline void debug_budget_start(void) {
    REG_TM3CNT_H = 0;                 /* arrêt avant remise à zéro */
    REG_TM3CNT_L = 0;
    REG_TM3CNT_H = TIMER_START | DEBUG_TIMER_PRESCALER_64;
}

/* `n_oam_visible` : nombre de slots shadow_oam non cachés cette frame,
 * compté par l'appelant (cf. main_gen.py, boucle principale) — c'est lui
 * qui possède le tableau, pas ce header. */
static inline void debug_budget_report(int n_oam_visible) {
    u16 ticks = REG_TM3CNT_L;
    REG_TM3CNT_H = 0;   /* mesure d'UNE frame, pas cumulative : on arrête */
    /* µs ≈ ticks * 3.8147 ≈ ticks * 61 / 16 (erreur < 0.3 %, entier only) */
    int us = (ticks * 61) >> 4;
    debug_write_str("frame us=");
    debug_write_int(us);
    debug_write_str(" oam=");
    debug_write_int(n_oam_visible);
    debug_flush();
}

#else /* !GBA_DEBUG_BUILD — stubs vides, éliminés à l'inlining (-O2) */

static inline void debug_init(void) {}
static inline void debug_write_str(const char* s) { (void)s; }
static inline void debug_write_int(int v) { (void)v; }
static inline void debug_flush(void) {}
static inline void debug_budget_start(void) {}
static inline void debug_budget_report(int n_oam_visible) { (void)n_oam_visible; }

#endif /* GBA_DEBUG_BUILD */

#endif /* GBA_DEBUG_H */
