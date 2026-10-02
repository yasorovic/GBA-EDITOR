# Documentation de Backstage

Cette documentation accompagne la création d'un jeu avec Backstage. Commencez par le guide
utilisateur, puis consultez le guide de scripting lorsque vous souhaitez donner un comportement
à votre jeu.

## Créer votre jeu

- [Guide utilisateur](user-guide/) : créer ou ouvrir un projet, importer des ressources,
  construire une scène et lancer une première ROM.
- [Première scène jouable](user-guide/first-playable-scene.md) : importer un sprite, déplacer
  un acteur et tester la ROM.
- [Décor et collisions](user-guide/decor-and-collision.md) : peindre les zones solides et
  empêcher l'acteur de traverser les murs.
- [Mouvement de plateforme](user-guide/platformer-movement.md) : ajouter gravité, saut et
  réglages par acteur.
- [Collectibles et score](user-guide/collectibles.md) : créer un prefab ramassable et afficher
  une valeur globale.
- [Ennemis et PNJ](user-guide/enemies.md) : écrire des dialogues, créer des ennemis et leurs comportements.
- [Boucle de gameplay](user-guide/gameplay-loop.md) : relier les scènes, l'interface et les
  transitions.
- [Boss](user-guide/boss.md) : construire une hiérarchie d'acteurs et une barre de vie.
- [Caméra](user-guide/camera-follow.md) : suivre un acteur et borner le défilement de la scène.
- [Guide de scripting](scripting.md) : écrire le comportement d'un acteur.
- [Référence de scripting](scripting-reference.md) : vérifier la syntaxe disponible et les
  limites du langage.

## Documentation de développement

Les notes destinées aux personnes qui modifient l'éditeur sont séparées dans
[development/](development/). Elles ne sont pas nécessaires pour créer un jeu.
