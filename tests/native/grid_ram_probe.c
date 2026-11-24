/* grid_ram_probe.c - exercise the C that the translator emits for a RAM grid.
 *
 * A RAM grid is a flat `unsigned char[rows*cols]`, written and read by cell
 * (`GRID_RAM_CELL`, a plain lvalue) and read by world pixel (`GRID_RAM_AT`,
 * the engine's `grid_value_at`). The macros come from the emitted expressions,
 * so this probe runs the very code the build would ship. */
#include <stdio.h>

#include "grid_inline.h"      /* grid_value_at */
#include "grid_ram_expr.h"    /* GRID_RAM_CELL / GRID_RAM_AT / sizes, from codegen */

unsigned char terrain[GRID_RAM_ROWS * GRID_RAM_COLS];

/* Operands of the flood scenario, named as the compiled script names them so the
 * emitted `grid_flood(...)` macro refers to them. */
unsigned char portee[GRID_RAM_ROWS * GRID_RAM_COLS];
unsigned char sol[GRID_RAM_ROWS * GRID_RAM_COLS];
int couts[3];

/* Output of path_to: one direction code (0..3) per step, sized by the caller. */
int pas[8];   /* comme un `array` de script : des entiers (cf. grid_path_to) */

/* Output of flow_map: one direction code per cell toward the source. */
unsigned char flux[GRID_RAM_ROWS * GRID_RAM_COLS];

/* Output of regions: one region id per cell. */
unsigned char zones[GRID_RAM_ROWS * GRID_RAM_COLS];

int main(void) {
    /* Write a distinct value in every cell, through the indexed write path. */
    for (int y = 1; y <= GRID_RAM_ROWS; y++)
        for (int x = 1; x <= GRID_RAM_COLS; x++)
            GRID_RAM_CELL(x, y) = (unsigned char)(y * GRID_RAM_COLS + x);

    /* Read back by cell, row by row. */
    printf("CELL");
    for (int y = 1; y <= GRID_RAM_ROWS; y++)
        for (int x = 1; x <= GRID_RAM_COLS; x++)
            printf(" %d", GRID_RAM_CELL(x, y));
    printf("\n");

    /* Read back by pixel, at the centre of each cell: same order, same values. */
    printf("AT");
    for (int y = 1; y <= GRID_RAM_ROWS; y++)
        for (int x = 1; x <= GRID_RAM_COLS; x++)
            printf(" %d", GRID_RAM_AT((x - 1) * GRID_RAM_STEP + GRID_RAM_STEP / 2,
                                      (y - 1) * GRID_RAM_STEP + GRID_RAM_STEP / 2));
    printf("\n");

    /* Outside the grid reads 0, like a missing collision cell. */
    printf("OUT %d %d\n", GRID_RAM_AT(-1, -1),
           GRID_RAM_AT(GRID_RAM_COLS * GRID_RAM_STEP, GRID_RAM_ROWS * GRID_RAM_STEP));

    /* fill: every cell becomes the same value. */
    GRID_RAM_FILL(7);
    printf("FILL");
    for (int y = 1; y <= GRID_RAM_ROWS; y++)
        for (int x = 1; x <= GRID_RAM_COLS; x++)
            printf(" %d", GRID_RAM_CELL(x, y));
    printf("\n");

    /* fill_rect: a 2x2 block from cell (2, 1), base 1, over the filled grid. The
     * rest keeps its value, and a rect clipped at the edge never overflows. */
    GRID_RAM_FILL_RECT(2, 1, 2, 2, 9);
    GRID_RAM_FILL_RECT(4, 3, 5, 5, 1);   /* spills past the edge: clamped */
    printf("RECT");
    for (int y = 1; y <= GRID_RAM_ROWS; y++)
        for (int x = 1; x <= GRID_RAM_COLS; x++)
            printf(" %d", GRID_RAM_CELL(x, y));
    printf("\n");

    /* flood: a cost map from a start cell. sol[] is the terrain, couts[] the cost
     * to enter a cell of each terrain value (value 2 costs 0 = a wall). The result
     * is read from the `portee` grid the macro writes into. */
    for (int i = 0; i < GRID_RAM_ROWS * GRID_RAM_COLS; i++) sol[i] = 0;
    sol[1 * GRID_RAM_COLS + 1] = 2;   /* wall at (1, 1) base 0 */
    sol[1 * GRID_RAM_COLS + 2] = 2;   /* wall at (2, 1) base 0 */
    couts[0] = 1;   /* plain  */
    couts[1] = 2;   /* rough  */
    couts[2] = 0;   /* wall (cost <= 0 is impassable) */

    GRID_RAM_FLOOD(1, 1, 5);          /* start cell (1, 1) base 1, budget 5 */
    printf("FLOOD");
    for (int y = 0; y < GRID_RAM_ROWS; y++)
        for (int x = 0; x < GRID_RAM_COLS; x++)
            printf(" %d", portee[y * GRID_RAM_COLS + x]);
    printf("\n");

    GRID_RAM_FLOOD(1, 1, 3);          /* same, tighter budget: far cells drop out */
    printf("BUDGET");
    for (int y = 0; y < GRID_RAM_ROWS; y++)
        for (int x = 0; x < GRID_RAM_COLS; x++)
            printf(" %d", portee[y * GRID_RAM_COLS + x]);
    printf("\n");

    /* path_to: rebuild the path to a cell from the cost map flood wrote into
     * `portee`. Re-run the budget-5 flood so the full map is back, then descend
     * to cell (4, 3) base 1. The count comes first, then each step (0..3). */
    GRID_RAM_FLOOD(1, 1, 5);
    int n = GRID_RAM_PATH(4, 3);
    printf("PATH %d", n);
    for (int i = 0; i < n; i++) printf(" %d", pas[i]);
    printf("\n");

    /* A walled cell is unreachable (cost 255): no path, zero steps. */
    printf("NOPATH %d\n", GRID_RAM_PATH(2, 2));

    /* flow_map: from the budget-5 cost map, one direction per cell toward the
     * source (4 at the source, 255 unreachable), read into the `flux` grid. */
    GRID_RAM_FLOOD(1, 1, 5);
    GRID_RAM_FLOW;
    printf("FLOW");
    for (int y = 0; y < GRID_RAM_ROWS; y++)
        for (int x = 0; x < GRID_RAM_COLS; x++)
            printf(" %d", flux[y * GRID_RAM_COLS + x]);
    printf("\n");

    /* line_of_sight: on an obstacle map (a wall at cell (2, 2)), a non-zero cell
     * between the endpoints blocks the view; the endpoints are not tested. */
    for (int i = 0; i < GRID_RAM_ROWS * GRID_RAM_COLS; i++) terrain[i] = 0;
    GRID_RAM_CELL(2, 2) = 1;
    printf("LOS %d %d %d %d\n",
           GRID_RAM_LOS(1, 1, 3, 3),   /* diagonal through the wall -> 0 */
           GRID_RAM_LOS(1, 1, 1, 3),   /* clear column -> 1 */
           GRID_RAM_LOS(1, 1, 3, 1),   /* clear row -> 1 */
           GRID_RAM_LOS(1, 1, 2, 2));  /* the wall is the target, not tested -> 1 */

    /* regions: connected cells of EQUAL value share an id 1..N (4-connectivity).
     * Three regions: the 1s top-left, the 2s on the right, the 3s centre-bottom. */
    GRID_RAM_CELL(1, 1) = 1; GRID_RAM_CELL(2, 1) = 1; GRID_RAM_CELL(3, 1) = 2; GRID_RAM_CELL(4, 1) = 2;
    GRID_RAM_CELL(1, 2) = 1; GRID_RAM_CELL(2, 2) = 3; GRID_RAM_CELL(3, 2) = 3; GRID_RAM_CELL(4, 2) = 2;
    GRID_RAM_CELL(1, 3) = 1; GRID_RAM_CELL(2, 3) = 3; GRID_RAM_CELL(3, 3) = 3; GRID_RAM_CELL(4, 3) = 3;
    const int nreg = GRID_RAM_REGIONS;
    printf("REGIONS %d", nreg);
    for (int y = 0; y < GRID_RAM_ROWS; y++)
        for (int x = 0; x < GRID_RAM_COLS; x++)
            printf(" %d", zones[y * GRID_RAM_COLS + x]);
    printf("\n");
    return 0;
}
