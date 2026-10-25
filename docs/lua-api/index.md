# Lua API

Les scripts de Backstage s'écrivent dans une syntaxe Lua simplifiée, traduite en C au Build. Cette section contient deux guides rédigés et le catalogue des fonctions.

```{toctree}
:hidden:
:maxdepth: 1

Guide de scripting <../scripting>
Référence de scripting <../scripting-reference>
api/index
```

- [Guide de scripting](../scripting.md) : écrire le comportement d'un acteur.
- [Référence de scripting](../scripting-reference.md) : la syntaxe disponible et les limites du langage.
- [Catalogue de l'API](api/index.md) : toutes les fonctions, générées depuis l'éditeur.

## Pourquoi du Lua ?

Une cartouche Game Boy Advance exécute du code machine, et les outils de référence de la communauté (devkitPro) se programment en C. Voici le même programme, afficher « Hello World! » à l'écran, écrit des deux façons.

::::{tab-set}
:sync-group: language

:::{tab-item} Backstage (Lua)
:sync: lua

```lua
function on_start()
    text:draw(10, 10, "Hello World!")
end
```
:::

:::{tab-item} devkitPro (C)
:sync: c

```c
#include <gba_console.h>
#include <gba_video.h>
#include <gba_interrupt.h>
#include <gba_systemcalls.h>
#include <stdio.h>

int main(void) {
    irqInit();
    irqEnable(IRQ_VBLANK);

    consoleDemoInit();
    iprintf("\x1b[10;10HHello World!\n");

    while (1) {
        VBlankIntrWait();
    }
}
```
:::
::::

Le C ci-dessus est adapté du modèle fourni avec devkitPro. Les deux programmes affichent le même message, mais pas de la même manière.

### Ce que le Lua vous épargne

- **L'initialisation de la console.** Le C doit activer l'interruption de l'écran (`irqInit`, `irqEnable`) et préparer l'affichage du texte (`consoleDemoInit`) avant d'écrire quoi que ce soit.
- **La boucle principale.** Un programme GBA ne se termine jamais : le C boucle sans fin et attend l'écran à chaque tour (`while (1)`, `VBlankIntrWait`). Dans Backstage, cette boucle existe déjà et appelle vos événements.
- **L'écriture du texte.** Le C positionne le message avec une séquence d'échappement (`\x1b[10;10H`). Le Lua donne deux nombres, la colonne et la ligne, en tuiles de 8 pixels.
- **La chaîne de compilation.** Le C demande un `Makefile`, les bibliothèques et leurs chemins. Backstage appelle devkitPro pour vous quand vous lancez **Build & Run**.

### Ce que vous gardez

Votre script dit **quoi** faire et **quand** : `on_start` s'exécute au début de la scène, `text:draw` affiche un texte. Le reste, la machinerie de la console, est écrit par Backstage.

Le Lua n'est donc pas une couche qui remplace le C : au Build, vos scripts sont traduits en C, puis compilés avec le reste du jeu par les mêmes outils.

- Pour écrire votre premier script, suivez le [guide de scripting](../scripting.md).
- Pour en savoir plus sur la syntaxe Lua dans Backstage, vérifiez une écriture depuis la [référence de scripting](../scripting-reference.md).
- Pour en savoir plus sur le parsing du Lua, la façon dont Backstage lit puis traduit vos scripts, rendez-vous dans la section [Architecture](../architecture/index.md) (à venir).
