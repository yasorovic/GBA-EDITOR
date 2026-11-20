# Premiers pas

Avant de modifier un jeu, il est utile de savoir ce que Backstage produit. Cette page explique les quelques mots
nécessaires, puis propose trois gestes courts dans le projet de démonstration **Platformer**.

## Ce que vous allez produire

Une **ROM** est le fichier qui contient un jeu destiné à une console. Pour la Game Boy Advance, ce fichier porte
l'extension `.gba`. Il rassemble le programme, les images, les sons et les données du projet. On peut le lancer
dans un émulateur ou le copier plus tard sur une cartouche flash compatible.

Un **émulateur** est un programme qui reproduit le fonctionnement de la console sur votre ordinateur. Backstage
utilise [mGBA](https://mgba.io/) pour ouvrir et tester la ROM sans matériel particulier.

Quand vous lancez **Run**, Backstage prépare la ROM puis demande à mGBA de l'ouvrir. Vous pouvez donc essayer
chaque modification sans quitter l'éditeur.

## Pourquoi les scripts s'écrivent en Lua

Les consoles Game Boy Advance exécutent du code machine. Les outils habituels de la communauté, réunis dans
devkitPro, passent par le langage C. Backstage vous laisse écrire le comportement du jeu avec une syntaxe Lua plus
directe : un script décrit par exemple ce qui se passe au démarrage, à chaque image ou quand un acteur touche un
autre élément.

Au Build, Backstage lit ce script, le traduit en C, puis devkitPro compile ce C avec le reste du jeu. Il n'y a pas
de programme Lua embarqué dans la ROM. Ce choix garde une ROM adaptée aux contraintes de la console, tout en
évitant d'avoir à écrire l'initialisation de la GBA, sa boucle principale et les appels techniques du moteur.

La syntaxe Lua de Backstage est volontairement limitée à ce qui peut être traduit de façon fiable. L'éditeur signale
une écriture non prise en charge avant la compilation. Vous n'avez pas besoin de lire le C généré pour commencer.
La section [Lua API](../lua-api/index.md) explique ce langage lorsque vous voudrez écrire vos propres scripts.

## 1. Ouvrir le projet de démonstration

Sur l'écran d'accueil, ouvrez l'onglet **Templates** et cliquez sur **Download** à côté de **Platformer**. Le projet
est copié dans votre dossier de projets : vous pouvez le modifier sans risque. Le bouton devient **✓ Downloaded**.
Double-cliquez ensuite sur l'entrée pour l'ouvrir.

Vous arrivez sur **Scenes**. Une **scène** est une partie jouable du jeu. Ici, elle contient le niveau, le joueur,
les pièces, un garde et une porte. Ces éléments sont des **acteurs** : des objets du jeu que l'on peut placer et
configurer.

```{figure} img/first-steps-scene.png
:alt: L'écran Scenes du projet Platformer, avec le personnage sélectionné.
:class: backstage-screenshot

Le projet Platformer ouvert. Le personnage vert, sélectionné, est l'acteur `Player`.
```

## 2. Lancer la démo avant de la modifier

Cliquez sur **Run** (`F5`). Backstage construit la ROM et l'ouvre dans mGBA. Déplacez le personnage, sautez,
ramassez quelques pièces et rejoignez la porte. Vous savez ainsi ce que vous allez modifier dans les étapes
suivantes.

Si la ROM ne démarre pas, vérifiez que devkitPro et mGBA sont renseignés dans **File → Settings**. La page
[Configuration requise](../about/requirements.md) indique le rôle de chacun.

## 3. Modifier la vitesse du joueur

Revenez sur **Scenes** et cliquez sur le personnage, ou sur `Player` dans la liste de gauche. Dans l'inspecteur,
ouvrez **Components**, puis cliquez sur **Script [script]**. La zone **Exposed variables** propose les réglages que
le script rend accessibles sans modifier son code.

```{figure} img/first-steps-exports.png
:alt: L'inspecteur du joueur : le composant script et ses variables exposées.
:class: backstage-screenshot

Les réglages exposés par `Player.lua` sont modifiables depuis l'inspecteur.
```

Passez **Speed** de `2` à `4`, enregistrez avec `Ctrl+S`, puis lancez à nouveau **Run**. Le joueur court deux fois
plus vite. Essayez ensuite **Jump Force** pour modifier la hauteur du saut.

Ces réglages sont des **exports**. Le script les déclare une fois et l'inspecteur les affiche automatiquement. Le
code reste partagé, tandis que chaque acteur peut recevoir ses propres valeurs.

## 4. Changer un détail visuel

Ouvrez l'écran **Animations**, sélectionnez `Collectible`, puis augmentez **Speed** dans la section **Animation**.
Cette ressource est la pièce que vous avez ramassée dans la démo. Relancez **Run** : elle tourne maintenant plus
vite, partout où elle apparaît.

```{figure} img/first-steps-animations.png
:alt: L'écran Animations sur le sprite Collectible : quatre images de pièce dans la timeline.
:class: backstage-screenshot

La pièce est une animation composée de quatre images.
```

## 5. Relier un réglage à son script

Ouvrez l'écran **Scripts** et choisissez `Player.lua`. Repérez le bloc `exports` au début : c'est lui qui crée les
réglages **Speed** et **Jump Force** que vous venez de modifier. Plus bas, `on_start` décrit ce qui se produit au
début de la scène et `on_update` ce qui se produit à chaque image, comme la lecture des touches et le déplacement
du joueur.

```{figure} img/first-steps-script.png
:alt: Le script Player.lua dans l'écran Scripts : le bloc exports en tête, puis les fonctions on_start et on_update.
:class: backstage-screenshot

`Player.lua` relie les réglages de l'inspecteur au comportement du joueur.
```

Ne modifiez rien dans ce script pour l'instant. Vous avez vu le lien entre un réglage, le comportement écrit et le
résultat dans la ROM.

## Et ensuite

- Pour vous repérer dans les zones de la fenêtre : [Se repérer dans l'éditeur](overview/editor-tour.md).
- Pour construire votre propre scène : [Tutoriel : première scène jouable](first-playable-scene.md).
- Pour écrire ou modifier un comportement : [Guide de scripting](../scripting.md).
