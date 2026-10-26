#
# Backstage — Makefile
# Tourne depuis build/ — chemins relatifs à build/
#
# Structure attendue dans build/ :
#   src/        → main.c généré + scripts C des acteurs
#   grit_out/   → tileset.h/.c + actor_*.h/.c (sorties grit)
#   obj/        → fichiers .o compilés
#   rom.elf     → ELF linkée
#   rom.gba     → ROM finale
#

ifeq ($(strip $(DEVKITPRO)),)
    $(error "DEVKITPRO non defini — configure via l editeur")
endif

DEVKITARM := $(DEVKITPRO)/devkitARM
PREFIX    := $(DEVKITARM)/bin/arm-none-eabi-
CC        := $(PREFIX)gcc
OBJCOPY   := $(PREFIX)objcopy
LD        := $(PREFIX)gcc

# Dossiers sources
SRC_DIRS  := src grit_out
# globals.c est dans src/ (généré par le transpileur Lua)
BUILD     := obj

# Collecter tous les .c dans src/ et grit_out/
CFILES    := $(foreach dir,$(SRC_DIRS),$(wildcard $(dir)/*.c))
# Fichier assembleur optionnel du soundbank maxmod
SFILES    := $(wildcard src/*.s)
OFILES    := $(addprefix $(BUILD)/,$(notdir $(CFILES:.c=.o))) \
             $(addprefix $(BUILD)/,$(notdir $(SFILES:.s=.o)))

# Flags de compilation
ARCH      := -mthumb-interwork -mthumb
CFLAGS    := $(ARCH) \
             -O2 -Wall \
             -mcpu=arm7tdmi -mtune=arm7tdmi \
             -fomit-frame-pointer \
             $(addprefix -I,$(SRC_DIRS)) \
             -I$(DEVKITPRO)/libgba/include \
             -I$(DEVKITPRO)/maxmod/include \
             $(EXTRA_CFLAGS)
# Le plan IWRAM du tick (cf. codegen/iwram_plan.py) ne concerne que main.c : le passer par EXTRA_CFLAGS changerait
# `cflags.txt` et recompilerait tous les objets. Ces drapeaux-ci ne vont qu'à main.o.
IWRAM_CFLAGS ?=
$(BUILD)/main.o: CFLAGS += $(IWRAM_CFLAGS)

# EXTRA_CFLAGS vient de l'environnement (cf. rom_build.py::_make_env) — c'est
# là que passe -DGBA_DEBUG_BUILD. En son absence, `debug.*`
# n'entre jamais dans la ROM : la définition dépend d'un define, pas d'un
# drapeau lu au runtime.

# Flags de link
# gba.specs est built-in dans arm-none-eabi-gcc
LDFLAGS   := $(ARCH) -specs=gba.specs
# libtonc retirée : elle ne servait qu'à TTE (display.print), sorti du workflow.
LIBS      := -L$(DEVKITPRO)/libgba/lib \
             -L$(DEVKITPRO)/maxmod/lib -lgba -lmm

TARGET    := rom

.PHONY: all clean FORCE

all: $(TARGET).gba

# ROM finale
$(TARGET).gba: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@
	@echo "[build] ROM: $@"

# ELF — ordre crucial: .o avant LIBS
$(TARGET).elf: $(OFILES) | $(BUILD)
	$(LD) $(LDFLAGS) -o $@ $^ $(LIBS)

# Compilation depuis src/
$(BUILD)/%.o: src/%.c Makefile $(BUILD)/cflags.txt | $(BUILD)
	$(CC) $(CFLAGS) -MMD -MP -c -o $@ $<

# Compilation depuis grit_out/
$(BUILD)/%.o: grit_out/%.c Makefile $(BUILD)/cflags.txt | $(BUILD)
	$(CC) $(CFLAGS) -MMD -MP -c -o $@ $<

# Assemblage soundbank (bin2s output)
$(BUILD)/%.o: src/%.s Makefile | $(BUILD)
	$(CC) $(ARCH) -MMD -MP -x assembler-with-cpp -c -o $@ $<

# Les drapeaux de compilation, sous forme de fichier : make compare des DATES, pas des
# options, donc passer de debug à release (-DGBA_DEBUG_BUILD vient de l'environnement)
# laissait les anciens .o en place. Le fichier n'est réécrit que si les drapeaux
# changent ; chaque .o en dépend, et change de date avec lui.
$(BUILD)/cflags.txt: FORCE | $(BUILD)
	@[ "$$(cat $@ 2>/dev/null)" = '$(CFLAGS)' ] || echo '$(CFLAGS)' > $@

FORCE:

# Créer obj/ si nécessaire
$(BUILD):
	mkdir -p $(BUILD)

-include $(OFILES:.o=.d)

clean:
	rm -rf $(BUILD) $(TARGET).elf $(TARGET).gba
