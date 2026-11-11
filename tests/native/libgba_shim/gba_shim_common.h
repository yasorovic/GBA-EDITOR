/* gba_shim_common.h — de quoi compiler `runtime/include/gba_engine.h` sur une
   machine de développement, pour l'y INTERROGER.

   Le moteur inclut six en-têtes de libgba. Aucun n'existe hors devkitPro, et
   même là ils décrivent une cible ARM qu'on ne peut pas exécuter ici. Ce fichier
   fournit le strict nécessaire — treize symboles, relevés dans le moteur — pour
   que `gba_engine.h` compile en natif.

   DEUX RÈGLES, à tenir si ce shim grossit :

   1. **Il ne réimplémente rien.** Les registres deviennent des variables
      ordinaires, les appels système des fonctions vides. Le seul code qui
      s'exécute pendant un test est celui du moteur ; tout ce qui est ici doit
      être inerte, sous peine de tester le shim.
   2. **Les adresses matérielles restent celles du moteur.** `TILE_RAM` et
      consorts sont définis dans `gba_engine.h` et pointent sur la VRAM réelle
      (0x06000000) : les déréférencer ici planterait. Un test ne doit donc
      emprunter que des chemins qui n'écrivent pas — pour la mise en page,
      c'est ce que garantit la CAPTURE (`g_cap_max > 0`, cf.
      text_layout_probe.c), qui note les glyphes au lieu de les dessiner. */
#ifndef GBA_SHIM_COMMON_H
#define GBA_SHIM_COMMON_H

typedef unsigned char      u8;
typedef unsigned short     u16;
typedef unsigned int       u32;
typedef signed char        s8;
typedef signed short       s16;
typedef signed int         s32;

typedef volatile unsigned char  vu8;
typedef volatile unsigned short vu16;
typedef volatile unsigned int   vu32;

/* Registres matériels — de la mémoire ordinaire. Le moteur y écrit (mélange de
   couleurs, fenêtres) sans jamais relire ce que la console en fait ; leur
   donner une case suffit à ce que ce code compile et s'exécute sans effet.

   `REG_WAITCNT` n'est pas ici : le moteur le définit lui-même (gba_engine.h),
   le redéfinir ne ferait qu'un avertissement de plus à chaque compilation. */
extern vu16 gba_shim_registers[16];

#define REG_DISPCNT   (gba_shim_registers[0])
#define REG_BLDCNT    (gba_shim_registers[2])
#define REG_BLDALPHA  (gba_shim_registers[3])
#define REG_BLDY      (gba_shim_registers[4])
#define REG_WIN0H     (gba_shim_registers[5])
#define REG_WIN0V     (gba_shim_registers[6])
#define REG_WIN1H     (gba_shim_registers[7])
#define REG_WIN1V     (gba_shim_registers[8])
#define REG_WININ     (gba_shim_registers[9])
#define REG_WINOUT    (gba_shim_registers[10])

/* Attributs d'un sprite, tels que la console les range en OAM. Le 4e champ porte, par groupes de quatre entrées, une
   matrice affine ; il s'appelle `dummy` comme dans libgba (`gba_sprites.h`), que `oam_write_affine` lit. */
typedef struct {
    u16 attr0, attr1, attr2;
    u16 dummy;
} OBJATTR;

extern OBJATTR gba_shim_oam[128];
#define OAM (gba_shim_oam)

/* Appel système de copie rapide — une copie ordinaire suffit : le moteur ne
   demande à `CpuFastSet` que de déplacer des mots, jamais de le faire vite. */
#define COPY32 0
#define FILL   (1 << 24)

void CpuFastSet(const void *source, void *dest, u32 mode);

/* Bits du registre de touches, aux valeurs de libgba. Le moteur les lit depuis
   que la navigation de liste existe (`ui_lists_tick`) : sans eux la sonde ne
   compile plus, et l'équivalence Python/C n'est plus vérifiée du tout. */
#define KEY_A       0x0001
#define KEY_B       0x0002
#define KEY_SELECT  0x0004
#define KEY_START   0x0008
#define KEY_RIGHT   0x0010
#define KEY_LEFT    0x0020
#define KEY_UP      0x0040
#define KEY_DOWN    0x0080
#define KEY_R       0x0100
#define KEY_L       0x0200

/* Section EWRAM de libgba (gba_base.h) : hors GBA, de la mémoire ordinaire. Gardé
   par #ifndef : des sondes la définissent déjà elles-mêmes avant d'inclure le moteur. */
#ifndef EWRAM_BSS
#define EWRAM_BSS
#endif

#endif /* GBA_SHIM_COMMON_H */
