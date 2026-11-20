# About

Backstage est un logiciel libre de création de jeux pour Game Boy Advance. Un projet réunit des scènes, des acteurs,
des ressources et des scripts dans des fichiers que l'on peut lire, ranger et partager.

L'éditeur sert à assembler ces éléments : placer une scène, relier un sprite à un acteur, régler une collision ou
écrire un comportement. Les scripts utilisent une syntaxe Lua simplifiée ; le projet est ensuite compilé avec les
outils de la Game Boy Advance.

## Pour qui ?

- Vous souhaitez travailler sur les scènes, les acteurs et les ressources d'un jeu GBA dans le même projet.
- Vous voulez écrire le comportement de vos acteurs sans organiser vous-même toute la chaîne C de la console.
- Vous programmez déjà, ou souhaitez avancer des guides vers le catalogue Lua.

Backstage reste volontairement spécialisé. Il importe vos images et vos sons, mais n'est ni un outil de dessin, ni un
éditeur de cartes graphiques, ni un tracker musical.

## Choisir son point de départ

- Suivez [Getting Started](../user-guide/index.md) pour installer Backstage, ouvrir la démo et produire une première
  ROM.
- Téléchargez l'application depuis [Télécharger Backstage](download.md).
- Consultez les [fonctionnalités](features.md) pour voir ce que le logiciel couvre aujourd'hui.
- Vérifiez la [configuration requise](requirements.md) avant l'installation.
- Ouvrez la [Lua API](../lua-api/index.md) si vous voulez écrire le comportement de votre jeu.

```{toctree}
:hidden:
:maxdepth: 1

Fonctionnalités <features>
Configuration requise <requirements>
Télécharger Backstage <download>
```

<!-- TODO documentation : ajouter une page « Flasher votre ROM sur une cartouche GBA » et faire pointer vers elle
la section « Tester sur console » de la configuration requise. La page présentera les différentes cartouches flash
GBA et leur utilisation. -->
