/* grid_shared_main.c - l'entrée de scène et le pilote de la sonde.
 *
 * Il germe le tampon RAM partagé depuis le germe ROM, comme `gen_scene_init` le
 * fait à l'entrée de scène (la même boucle), puis fait écrire le "script de
 * scène" et lire le "script d'acteur" : trois unités de traduction, un seul
 * tampon `g_grid_Arena_Flow` (défini dans grids.c). C'est la preuve du partage
 * inter-scripts au niveau du C réellement émis. */
#include <stdio.h>

#include "grids.h"

void flow_write(int x, int y, int w, int h, int v);
int flow_at(int px, int py);
int flow_cell(int x, int y);

int main(void) {
    /* Germination : la copie que `gen_scene_init` émet pour une grille RAM. */
    for (int i = 0; i < GRID_W_ARENA_FLOW * GRID_H_ARENA_FLOW; i++)
        g_grid_Arena_Flow[i] = g_grid_Arena_Flow_seed[i];

    /* Après germination : le lecteur voit le germe peint (cellules intactes). */
    printf("SEED %d %d\n", flow_cell(1, 1), flow_cell(4, 3));

    /* Le "script de scène" écrit un rectangle ; le "script d'acteur" le relit
     * dans le MÊME tampon. */
    flow_write(2, 1, 2, 2, 9);
    printf("WRITTEN %d %d\n", flow_cell(2, 1), flow_cell(3, 2));

    /* Une cellule hors du rectangle garde son germe ; une lecture par pixel
     * (centre de la case 2,1) retombe sur la valeur écrite. */
    printf("KEPT %d\n", flow_cell(1, 1));
    printf("AT %d\n", flow_at(1 * 16 + 8, 0 * 16 + 8));
    return 0;
}
