/* Sonde : la grille de valeurs REELLEMENT emise par le build.
 *
 * Compile le `grids.h` / `grids.c` qu'un vrai projet vient de produire, et rend
 * ce que la ROM contiendrait : la geometrie annoncee par les macros, une valeur
 * nommee de la legende, puis chaque case lue a travers la formule d'acces par
 * pixel (un decalage de bits, le pas etant une puissance de deux).
 *
 * Les symboles sont ceux de la scene « Arena » et de sa grille « Terrain » :
 * c'est le fixture du test qui les nomme ainsi.
 */
#include <stdio.h>

#include "grids.h"

/* La forme que prendra l'acces par pixel : `at(px, py)`. Le pas etant une
 * puissance de deux, passer d'un pixel a une case est un decalage. */
static int shift_of(int step) {
    int n = 0;
    while ((1 << n) < step) n++;
    return n;
}

static int at(int px, int py) {
    const int shift = shift_of(GRID_STEP_ARENA_TERRAIN);
    const int tx = px >> shift, ty = py >> shift;
    if (tx < 0 || ty < 0 || tx >= GRID_W_ARENA_TERRAIN || ty >= GRID_H_ARENA_TERRAIN)
        return 0;
    return (int)g_grid_Arena_Terrain[ty * GRID_W_ARENA_TERRAIN + tx];
}

int main(void) {
    printf("W %d\n", GRID_W_ARENA_TERRAIN);
    printf("H %d\n", GRID_H_ARENA_TERRAIN);
    printf("STEP %d\n", GRID_STEP_ARENA_TERRAIN);
    printf("EAU %d\n", GRID_VALUE_ARENA_TERRAIN_EAU);

    /* Chaque case, par son centre en pixels : la formule d'acces et la mise a
     * plat doivent donner ce que l'editeur a peint. */
    const int step = GRID_STEP_ARENA_TERRAIN;
    printf("CELLS");
    for (int ty = 0; ty < GRID_H_ARENA_TERRAIN; ty++)
        for (int tx = 0; tx < GRID_W_ARENA_TERRAIN; tx++)
            printf(" %d", at(tx * step + step / 2, ty * step + step / 2));
    printf("\n");

    /* Hors de la grille vaut 0, comme hors de la carte de collision. */
    printf("OUT %d %d\n", at(-1, 0), at(GRID_W_ARENA_TERRAIN * step, 0));
    return 0;
}
