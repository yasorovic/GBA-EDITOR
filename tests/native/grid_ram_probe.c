/* grid_ram_probe.c - exercise the C that the translator emits for a RAM grid.
 *
 * A RAM grid is a flat `unsigned char[rows*cols]`, written and read by cell
 * (`GRID_RAM_CELL`, a plain lvalue) and read by world pixel (`GRID_RAM_AT`,
 * the engine's `grid_value_at`). The macros come from the emitted expressions,
 * so this probe runs the very code the build would ship. */
#include <stdio.h>

/* Minimal Vec2 for the navigation macros that pass a world position (vec2(px, py)
 * emits a `(Vec2){x, y}` compound literal). The engine's Vec2 is richer; here only
 * .x / .y are read by the emitted expressions. */
typedef struct { int x, y; } Vec2;

#include "grid_inline.h"      /* grid_value_at, grid_contains, grid_copy_from, grid_reachable, grid_cost_at, grid_arrived */
#include "grid_ram_expr.h"    /* GRID_RAM_CELL / GRID_RAM_AT / sizes, from codegen */

unsigned char terrain[GRID_RAM_ROWS * GRID_RAM_COLS];

/* Operands of the flood scenario, named as the compiled script names them so the
 * emitted `grid_flood(...)` macro refers to them. */
unsigned char portee[GRID_RAM_ROWS * GRID_RAM_COLS];
unsigned char sol[GRID_RAM_ROWS * GRID_RAM_COLS];
int couts[3];

/* Source of the copy_from scenario. */
unsigned char src[GRID_RAM_ROWS * GRID_RAM_COLS];

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

    /* --- Tranche 2 : contains, copy_from, reachable, cost_at, arrived --- */
    const int half = GRID_RAM_STEP / 2;

    /* contains: a point inside the grid vs outside. A cell holding 0 still counts
     * as inside, which value_at alone cannot tell from out-of-grid. */
    printf("CONTAINS %d %d\n",
           GRID_RAM_CONTAINS(GRID_RAM_STEP + half, GRID_RAM_STEP + half),   /* inside */
           GRID_RAM_CONTAINS(-1, -1));                                      /* outside */

    /* copy_from: a source grid of the same geometry is copied cell for cell. */
    for (int i = 0; i < GRID_RAM_ROWS * GRID_RAM_COLS; i++) src[i] = (unsigned char)(100 + i);
    GRID_RAM_COPY;
    printf("COPY");
    for (int y = 1; y <= GRID_RAM_ROWS; y++)
        for (int x = 1; x <= GRID_RAM_COLS; x++)
            printf(" %d", GRID_RAM_CELL(x, y));
    printf("\n");

    /* reachable / cost_at: on the budget-5 cost map, cell (4, 3) holds cost 5 and
     * the walled cell (2, 2) is out of range (255 -> not reachable, cost -1). */
    GRID_RAM_FLOOD(1, 1, 5);
    printf("REACH %d %d\n",
           GRID_RAM_REACH(3 * GRID_RAM_STEP + half, 2 * GRID_RAM_STEP + half),   /* cell (4,3) -> 1 */
           GRID_RAM_REACH(1 * GRID_RAM_STEP + half, 1 * GRID_RAM_STEP + half));  /* cell (2,2) -> 0 */
    printf("COST %d %d\n",
           GRID_RAM_COST(3 * GRID_RAM_STEP + half, 2 * GRID_RAM_STEP + half),    /* 5 */
           GRID_RAM_COST(1 * GRID_RAM_STEP + half, 1 * GRID_RAM_STEP + half));   /* -1 */

    /* arrived: on the flow map, the source cell (1, 1) holds 4 (arrived); any
     * other reachable cell holds a direction, not 4. */
    GRID_RAM_FLOOD(1, 1, 5);
    GRID_RAM_FLOW;
    printf("ARRIVED %d %d\n",
           GRID_RAM_ARRIVED(half, half),                                        /* cell (1,1) -> 1 */
           GRID_RAM_ARRIVED(3 * GRID_RAM_STEP + half, 2 * GRID_RAM_STEP + half)); /* cell (4,3) -> 0 */

    /* --- Navigation sans grille : arrive, keep_distance (vec2 -> vec2) --- */
    /* arrive from (0,0) to (30,40), dist 50 : ramp (stop 10, slow 100 -> speed 4
     * -> (2,3)), full speed (slow 40 -> speed 10 -> (6,8)), inside stop -> (0,0). */
    Vec2 ar = GRID_RAM_ARRIVE(0, 0, 30, 40, 10, 100, 10);
    Vec2 af = GRID_RAM_ARRIVE(0, 0, 30, 40, 10, 40, 10);
    Vec2 az = GRID_RAM_ARRIVE(0, 0, 3, 4, 10, 100, 10);
    printf("ARRIVE %d %d %d %d %d %d\n", ar.x, ar.y, af.x, af.y, az.x, az.y);

    /* keep_distance : (0,0) in the band, close in past max (dist 50 > 40 -> (3,4)),
     * back away below min (dist 5 < 20 -> (-3,-4)). */
    Vec2 kb = GRID_RAM_KEEP(0, 0, 30, 40, 20, 60, 5);
    Vec2 kc = GRID_RAM_KEEP(0, 0, 30, 40, 20, 40, 5);
    Vec2 kf = GRID_RAM_KEEP(0, 0, 3, 4, 20, 60, 5);
    printf("KEEP %d %d %d %d %d %d\n", kb.x, kb.y, kc.x, kc.y, kf.x, kf.y);
    return 0;
}
