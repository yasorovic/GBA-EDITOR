# About

```{toctree}
:hidden:
:maxdepth: 1

Pourquoi développer pour la GBA ? <gba>
L'écosystème GBA <ecosystem>
Licence <license>
```

**Backstage est un environnement de création visuel pour réaliser des jeux Game Boy Advance et les compiler en ROMs `.gba`.**

Le projet réunit dans un même espace les étapes qui relient vos images, vos sons et vos idées à un jeu jouable. Il s'adresse aux créateurs qui souhaitent travailler visuellement tout en gardant la possibilité de programmer leurs propres systèmes de jeu.

## Pourquoi Backstage ?

La GBA ne lit pas une image comme un ordinateur. Un décor devient des tuiles de 8 × 8 pixels, un personnage est découpé en sprites, les couleurs sont rangées par palettes (le plus souvent de 16 couleurs), et tout cela se partage une mémoire vidéo de 96 Ko. Sans outil, on convertit ses images à la main, on compte ses tuiles et on tient à jour la carte de la mémoire.

Backstage prend en charge ce travail. Vous importez une image ordinaire : l'éditeur la convertit, range ses couleurs dans les palettes de la console, place ses tuiles dans la mémoire vidéo, et affiche l'état des budgets (sprites, tuiles, palettes) pendant que vous composez la scène. Vous pensez en acteurs, en décors et en animations ; les numéros de palette, les emplacements mémoire et les registres restent calculés pour vous.

Ce que l'éditeur montre est ce que la ROM produit : le canvas et le Build appellent le même code, de sorte qu'une scène ne se comporte pas autrement sur la console que dans l'éditeur. Les scripts sont vérifiés avant le Build : une fonction inconnue, un nom d'acteur mal écrit ou une écriture que la console ne peut pas exécuter sont signalés avec leur ligne, plutôt que de planter la ROM.

**Backstage n'est pas un outil de dessin, un éditeur de cartes ni un tracker musical.** Il importe ce que vous créez dans vos autres outils (images, musiques, sons) et se charge de le faire entrer dans la console. Ce que vous y construisez, ce sont des acteurs, des scènes, des caméras, des textes, des sons et des données, auxquels vous donnez un comportement. Un inventaire, une quête ou un combat n'existent pas tout faits : ce sont des systèmes que vous concevez avec ces briques.

**Le travail visuel et la programmation se complètent.** L'éditeur sert à composer et à régler ; les scripts décrivent ce qui se passe pendant le jeu. Des notions de programmation sont utiles pour aller au-delà des comportements déjà disponibles.

## Comment ça marche

Un jeu Backstage se construit en quatre gestes, que vous pouvez enchaîner dans l'ordre qui vous convient :

1. **Importer** vos ressources : sprites, décors, palettes, polices, sons. Les images sont converties au format de la console à l'import.
2. **Construire** des scènes : placer les acteurs, dessiner les zones solides, régler la caméra et l'interface.
3. **Donner vie** au jeu : associer des comportements aux acteurs et écrire vos scripts.
4. **Tester** : lancer **Build & Run** pour compiler une ROM `.gba` et l'ouvrir dans mGBA.

Au Build, Backstage prépare les ressources et traduit les scripts en C. Ce code est compilé avec le moteur d'exécution de Backstage par **devkitARM**, la chaîne de compilation distribuée par devkitPro. Le résultat est un programme destiné à la GBA, jouable dans un émulateur et sur console avec une cartouche reprogrammable compatible.

Le langage de script reprend une partie de la syntaxe de Lua, avec des règles propres à Backstage. Il ne permet pas d'exécuter n'importe quel programme ou bibliothèque Lua existant. La [référence de scripting](../scripting-reference.md) décrit les possibilités et les différences avec Lua standard.

## Un projet en évolution

Backstage est en alpha. Des projets de démonstration permettent d'explorer son fonctionnement, mais des bugs subsistent et les fonctionnalités, les formats de projet ou l'API peuvent évoluer. Conservez une sauvegarde de vos projets avant de changer de version.

Les [releases](https://github.com/yasorovic/GBA-EDITOR/releases) présentent les versions publiées. La [roadmap](https://github.com/yasorovic/GBA-EDITOR/blob/main/ROADMAP.md) décrit les travaux en cours et les pistes envisagées ; elle ne constitue pas une liste de fonctions déjà disponibles.

Vous pouvez [signaler un problème ou proposer une amélioration](https://github.com/yasorovic/GBA-EDITOR/issues). Les retours sur les étapes difficiles à comprendre sont aussi utiles que les rapports de bugs.

## Pour découvrir le contexte

- [Pourquoi développer pour la Game Boy Advance ?](gba.md) : les contraintes de la console et la créativité qu'elles peuvent encourager.
- [L'écosystème GBA](ecosystem.md) : le rôle de devkitPro, de Butano et des outils de création autour de Backstage.

## Par où continuer ?

Pour un premier contact, suivez cet ordre :

1. **[Getting Started](../user-guide/index.md)** : installer les outils, créer un projet et obtenir une première scène jouable.
2. **[Écrire un script](../scripting.md)** : donner un premier comportement à un acteur.
3. **[Le projet de démo Pong Advanced](https://github.com/yasorovic/GBA-EDITOR/tree/main/Project%20Demo/PongAdvanced)** : un projet complet à ouvrir dans l'éditeur, pour voir comment les scènes, les acteurs et les scripts s'assemblent.

Ensuite, selon votre besoin :

| Vous souhaitez… | Consultez… |
| --- | --- |
| Comprendre les panneaux et les réglages de l'éditeur | [Manual](../manual/index.md), en préparation |
| Vérifier la syntaxe et les différences avec Lua standard | La [référence de scripting](../scripting-reference.md) |
| Trouver une fonction et ses arguments | Le [catalogue de la Lua API](../lua-api/api/index.md) |
| Comprendre comment un projet devient une ROM | [Architecture](../architecture/index.md), en préparation |
| Savoir ce que la console impose à vos ressources | [Pourquoi développer pour la GBA ?](gba.md) |
| Connaître les conditions d'utilisation de Backstage et de publication de vos jeux | [Licence](license.md) |
