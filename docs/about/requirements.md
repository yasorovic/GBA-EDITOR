# Configuration requise

## Système

Backstage fonctionne sous **Windows** et **Linux**. Un ordinateur capable d'exécuter l'éditeur et mGBA suffit. Une
console Game Boy Advance n'est pas nécessaire pour tester une ROM pendant son développement.

Les formats disponibles et leurs liens sont sur la page [Télécharger Backstage](download.md).

## Outils nécessaires au Build

| Outil | Rôle |
| --- | --- |
| [devkitPro](https://devkitpro.org/wiki/Getting_Started) | Compile le projet en ROM `.gba`. |
| [mGBA](https://mgba.io/downloads.html) | Lance et teste les ROMs `.gba`. |

L'installateur Windows de Backstage propose devkitPro. La version portable demande une installation séparée. Sous
Linux, les étapes d'installation de devkitPro sont détaillées dans [Télécharger Backstage](download.md).

## Tester sur console

La ROM `.gba` se teste d'abord dans mGBA. La copier sur une cartouche flash compatible est une étape distincte, qui
dépend du matériel choisi.
