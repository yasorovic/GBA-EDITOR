/* Sonde : la lecture d'une grille de valeurs, telle que le build l'emet VRAIMENT.
 *
 * Elle compile trois choses reelles ensemble, et rien d'ecrit a la main :
 *   - `grids.h` / `grids.c`, ecrits par `runtime_codegen/grids.py` ;
 *   - `grid_value_at`, EXTRAIT de `runtime/include/runtime_api_inline.h` par le test
 *     et depose dans `grid_inline.h`. La fonction ne depend de rien (un pointeur et
 *     des entiers), alors que l'en-tete entier reclamerait tout l'etat du moteur :
 *     l'extraction garde le code reel sans son contexte ;
 *   - les EXPRESSIONS que le traducteur Lua vers C a produites, deposees dans
 *     `grid_expr.h` sous forme de macros qui prennent leurs coordonnees en
 *     parametres.
 *
 * Si le codegen ou l'inline changent de forme, cette sonde compile la nouvelle.
 */
#include <stdio.h>

#include "grid_inline.h"
#include "grids.h"
#include "grid_expr.h"

int main(void) {
    /* Par pixel : le centre de chaque case, puis deux points hors de la grille. */
    printf("AT");
    for (int ty = 0; ty < GRID_H_ARENA_TERRAIN; ty++)
        for (int tx = 0; tx < GRID_W_ARENA_TERRAIN; tx++) {
            const int px = tx * GRID_STEP_ARENA_TERRAIN + GRID_STEP_ARENA_TERRAIN / 2;
            const int py = ty * GRID_STEP_ARENA_TERRAIN + GRID_STEP_ARENA_TERRAIN / 2;
            printf(" %d", GRID_EXPR_AT(px, py));
        }
    printf("\n");
    printf("OUT %d %d\n", GRID_EXPR_AT(-1, 0),
           GRID_EXPR_AT(GRID_W_ARENA_TERRAIN * GRID_STEP_ARENA_TERRAIN, 0));

    /* Par case : les index partent de 1, la colonne puis la rangee. */
    printf("CELL");
    for (int y = 1; y <= GRID_H_ARENA_TERRAIN; y++)
        for (int x = 1; x <= GRID_W_ARENA_TERRAIN; x++)
            printf(" %d", GRID_EXPR_CELL(x, y));
    printf("\n");

    /* Une valeur nommee de la legende est une constante du build. */
    printf("EAU %d\n", GRID_VALUE_ARENA_TERRAIN_EAU);
    return 0;
}
