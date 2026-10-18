/* Le vrai pilote SRAM, avec une mémoire locale et les tables émises par le build. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

static volatile unsigned char memory[32768 + 16];
#define SRAM_MEM memory
#ifdef PROBE_NO_MEMORY
static void *no_memory(size_t count, size_t size) { (void)count; (void)size; return NULL; }
#define calloc no_memory
#endif
#include "gba_engine.h"
#include "save_tables.h"

vu16 gba_shim_registers[16];
OBJATTR gba_shim_oam[128];
const unsigned short g_palettes[1][16] = {{0}};
const int g_palette_count = 0;
void CpuFastSet(const void *source, void *dest, u32 mode) {
    (void)source; (void)dest; (void)mode;
}

static int values[8][64];
int global_read(int i) { return values[i][0]; }
void global_write(int i, int value) { values[i][0] = value; }
int global_read_at(int i, int k) { assert(i >= 0 && i < 8 && k >= 0 && k < 64); return values[i][k]; }
void global_write_at(int i, int k, int value) {
    assert(i >= 0 && i < 8 && k >= 0 && k < 64);
    for (int j = 0; j < g_save_count; j++) if (g_save_idx[j] == i) {
        int bits = g_save_bits[j] & 0x7F;
        if (bits == 1) value = value != 0;
        else if (bits < 32) {
            unsigned int raw = (unsigned int)value & ((1u << bits) - 1u);
            value = g_save_bits[j] & 0x80 ? save_signed(raw, bits) : (int)raw;
        }
        break;
    }
    values[i][k] = value;
}

int main(int argc, char **argv) {
    assert(argc == 3);
    FILE *input = fopen(argv[1], "rb");
    assert(input);
    for (int i = 0; i < 32768; i++) {
        int byte = fgetc(input);
        assert(byte != EOF);
        memory[i] = (unsigned char)byte;
    }
    fclose(input);
    for (int i = 32768; i < 32784; i++) memory[i] = 0xCD;
    char op;
    int slot, index, value;
    while (scanf(" %c %d", &op, &slot) == 2) {
        switch (op) {
        case 'S':
            assert(slot >= 0 && slot < 8 && scanf("%d", &value) == 1);
            values[slot][0] = value;
            continue;
        case 'A':
            assert(scanf("%d %d", &index, &value) == 2);
            global_write_at(slot, index, value);
            continue;
        case 'G':
            assert(scanf("%d", &index) == 1);
            printf("%d", global_read_at(slot, index));
            break;
        case 'W': printf("%d", save_write(slot)); break;
        case 'E': printf("%d", save_erase(slot)); break;
        case 'X': printf("%d", save_exists(slot)); break;
        case 'P':
            assert(scanf("%d", &index) == 1);
            printf("%d", save_read_var(slot, index));
            break;
        case 'R':
            printf("%d", save_read(slot));
            for (int i = 0; i < g_save_count; i++) printf(" %d", values[g_save_idx[i]][0]);
            break;
        default: assert(0);
        }
        putchar('\n');
    }
    FILE *output = fopen(argv[2], "wb");
    assert(output);
    for (int i = 0; i < 32768; i++) fputc(memory[i], output);
    assert(fclose(output) == 0);
    for (int i = 32768; i < 32784; i++) assert(memory[i] == 0xCD);
    return 0;
}
