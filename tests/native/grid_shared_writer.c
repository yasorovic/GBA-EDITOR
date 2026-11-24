/* grid_shared_writer.c - le "script de scène" : il ÉCRIT la grille partagée.
 *
 * Unité de traduction distincte du lecteur et du main. Il ne connaît le tampon
 * que par l'`extern` de grids.h (comme le ferait le .c d'un script de scène), et
 * l'expression d'écriture est celle que le traducteur émet pour
 * `data.grid.Flow:fill_rect(...)`. */
#include "grids.h"
#include "grid_inline.h"      /* grid_fill_rect */
#include "grid_shared_expr.h" /* GRID_WRITE_RECT, du codegen */

void flow_write(int x, int y, int w, int h, int v) {
    GRID_WRITE_RECT(x, y, w, h, v);
}
