# L'écosystème GBA

La communauté homebrew développe des outils, des moteurs et de la documentation qui rendent la création sur GBA possible. Backstage hérite de ce travail collectif. Voici quelques points d'entrée pour découvrir cet écosystème et les différents outils qui le composent.

## gbadev : la communauté et les ressources

[gbadev](https://gbadev.net/) rassemble des ressources pour apprendre à développer sur Game Boy Advance : guides de démarrage, documentation technique et liens vers les outils de la communauté. C'est un bon point de départ pour explorer les différentes approches du développement sur la console.

La communauté propose aussi des espaces d'entraide et organise des game jams, où des créateurs réalisent et partagent de nouveaux jeux GBA.

## devkitPro : les outils de compilation

[devkitPro](https://devkitpro.org/) distribue des chaînes de compilation, des bibliothèques et des outils pour le développement homebrew sur plusieurs consoles.

Pour la GBA, **devkitARM** permet notamment de compiler du C, du C++ et de l'assembleur en code exécutable par la console. Les outils associés servent à préparer les ressources et à produire les ROMs. Cette chaîne de compilation est celle qu'utilise Backstage lors du Build.

## mGBA : l'émulation et les tests

[mGBA](https://mgba.io/) est un émulateur libre qui permet d'exécuter des jeux Game Boy Advance sur ordinateur. Pendant le développement, il permet de tester une ROM après chaque compilation, sans devoir la transférer sur une cartouche à chaque modification.

Il propose aussi des fonctions utiles pour analyser un problème ou montrer son travail : débogueur, sauvegardes de l'état de l'émulation, captures d'écran et enregistrement vidéo. Son [dépôt](https://github.com/mgba-emu/mgba) présente les fonctionnalités et les plateformes prises en charge.

C'est l'émulateur lancé par **Build & Run** dans Backstage. Des essais sur une véritable console restent utiles pour vérifier le résultat sur le matériel auquel le jeu est destiné.

## Butano : une autre approche pour créer votre jeu

[Butano](https://gvaliente.github.io/butano/) est un moteur de haut niveau en C++ pour la Game Boy Advance. Il fournit des abstractions pour gérer notamment les sprites, les décors, les palettes, les animations, les caméras et l'audio, sans devoir gérer soi-même chaque détail matériel.

Le jeu se construit par le code, en s'appuyant sur les fonctions et les classes du moteur. Sa documentation accompagne la prise en main, l'import des ressources et l'utilisation des différents modules. Ses nombreux [exemples](https://gvaliente.github.io/butano/examples.html) permettent d'explorer les fonctionnalités du moteur et les possibilités graphiques et sonores de la console.

Si vous préférez construire votre jeu directement en C++, Butano constitue une alternative à Backstage. Vous organisez votre projet et programmez ses systèmes à partir des outils du moteur. Cette approche convient aux créateurs qui souhaitent travailler principalement dans le code ; Backstage propose pour sa part un environnement visuel pour composer les scènes et les relier aux comportements scriptés.
