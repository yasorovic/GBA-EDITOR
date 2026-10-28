# Premiers pas

Cette page part d'un jeu qui existe déjà, le projet de démonstration **Platformer** : lancez-le, changez la vitesse du personnage, puis faites-en un second ennemi réglé autrement. Les notions de scène, d'acteur et de ressource viennent ensuite.

**Ce qu'il vous faut :** Backstage installé, ainsi que devkitPro et mGBA, configurés dans
**File → Settings**.

## 1. Ouvrir le projet de démonstration

::::{div} backstage-side-figure
Sur l'écran d'accueil, ouvrez l'onglet **Templates** et cliquez sur **Download** à côté de
**Platformer**. Le projet est copié dans votre dossier de projets : vous pouvez le modifier sans
risque. Le bouton devient **✓ Downloaded** ; double-cliquez sur l'entrée pour ouvrir le projet, qui
s'affiche sur l'écran **Scenes**.

```{figure} img/first-steps-templates.png
:alt: L'onglet Templates de l'écran d'accueil, avec le projet Platformer et son bouton Download.
:class: backstage-screenshot

L'onglet **Templates** de l'écran d'accueil.
```
::::

```{figure} img/first-steps-scene.png
:alt: L'écran Scenes du projet Platformer, avec le personnage sélectionné.
:class: backstage-screenshot

Le projet Platformer ouvert. Le personnage vert, sélectionné, est l'acteur `Player`.
```

## 2. Lancer le jeu

Cliquez sur le bouton **Run** (`F5`). 

Backstage construit la ROM et l'ouvre dans mGBA. Déplacez le personnage
avec les flèches, sautez avec la touche **A** de la console (réglable dans
**Project Settings → Input**), ramassez les pièces : le score s'affiche en haut de l'écran.
.

## 3. Faire le tour des écrans

La barre du haut ouvre les écrans du projet.

- **Scenes** : la scène `Scene_01`. À gauche, la liste de ses acteurs (le joueur, les pièces, la porte,
  le garde). Au centre, le niveau. À droite, l'inspecteur de l'élément sélectionné.
- **Animations** : les sprites du jeu (`Player`, `Demon`, `Collectible`), découpés en images et
  regroupés en animations.
- **Scripts** : les comportements écrits en Lua (`Player.lua`, `Guard_Patrol.lua`...).

```{figure} img/first-steps-animations.png
:alt: L'écran Animations sur le sprite Collectible : quatre images de pièce dans la timeline.
:class: backstage-screenshot

L'écran **Animations** : la pièce est une suite de quatre images.
```

Dans **Animations**, sélectionnez `Collectible` et augmentez la valeur de **Speed** dans la section
**Animation** : la pièce tourne plus vite. Relancez **Run** pour la voir dans le jeu.

## 4. Changer la vitesse du personnage

Revenez sur **Scenes** et cliquez sur le personnage (ou sur `Player` dans la liste de gauche). Dans
l'inspecteur, ouvrez la section **Components**, puis cliquez sur le composant **Script [script]**.
La zone **Exposed variables** propose trois réglages : **Speed**, **Gravity** et **Jump Force**.

```{figure} img/first-steps-exports.png
:alt: L'inspecteur du joueur : le composant script et ses trois variables exposées Speed, Gravity et Jump Force.
:class: backstage-screenshot

Les variables exposées du script `Player.lua`, réglables sans toucher au code.
```

Passez **Speed** de `2` à `4`, enregistrez avec `Ctrl+S`, puis lancez **Run**. Le personnage court deux
fois plus vite. Essayez aussi **Jump Force** pour changer la hauteur du saut.

Ces réglages s'appellent des **exports**. Le script les déclare en tête de fichier, et l'inspecteur les
affiche automatiquement. Quiconque règle le jeu n'a pas besoin d'ouvrir le code.

## 5. Un second garde, en version fantôme

Le garde patrouille d'un mur à l'autre. Son script `Guard_Patrol.lua` expose deux
variables : **Vitesse** et **Sens** (`1` vers la droite, `-1` vers la gauche).

Pour en faire un modèle réutilisable, sélectionnez `Guard` et cliquez sur **Expose to prefab** dans
l'inspecteur, puis nommez le prefab `Guard`. L'acteur de la scène devient une **instance** de ce
prefab. Le prefab est aussi un fichier : il apparaît dans l'onglet **Disk**, au bas de la fenêtre.

```{figure} img/first-steps-disk.png
:alt: L'onglet Disk du panneau du bas : le dossier assets, ses sous-dossiers et les prefabs Collectible, Guard et Player.
:class: backstage-screenshot

L'onglet **Disk** montre le contenu du dossier `assets`, prefabs compris.
```

Glissez `Guard.prefab` depuis l'onglet **Disk** vers la scène pour poser une seconde instance, et
placez-la ailleurs dans le niveau. Les deux gardes partagent le même sprite et le même script, mais
chacun peut avoir ses propres réglages : réglez **Vitesse** à `2` et **Sens** à `-1` sur la nouvelle
instance.

Pour en faire une version fantôme, changez aussi ses couleurs. Sélectionnez la nouvelle instance,
ouvrez la section **Components** de l'inspecteur et cliquez sur **Sprite [sprite]** : le champ
**Palette** liste les palettes du projet. Choisissez-en une autre que `DMG (GB Default)`, `_PICO-8`
par exemple : seul ce garde change de couleurs, l'autre garde la sienne.

```{figure} img/first-steps-guard-palette.png
:alt: L'inspecteur de la seconde instance du garde, avec le composant Sprite et son champ Palette.
:class: backstage-screenshot

Le composant **Sprite** de l'instance : le champ **Palette** change les couleurs du garde.
```

C'est tout l'intérêt d'un prefab : écrire le comportement une fois, puis varier les copies par leurs
réglages. Modifier ensuite le prefab (par exemple son sprite) change tous les gardes d'un coup. Le
guide [Prefabs et instances](../guides/organiser/prefabs.md) détaille ce geste.

## 6. Lire un script

Ouvrez l'écran **Scripts** et cliquez sur `Player.lua` dans la bibliothèque à droite. Sans rien
modifier, repérez trois choses.

```{figure} img/first-steps-script.png
:alt: Le script Player.lua dans l'écran Scripts : le bloc exports en tête, puis les fonctions on_start et on_update.
:class: backstage-screenshot

`Player.lua` : les exports en tête, puis ce qui se passe au démarrage et à chaque image.
```

- Le bloc **`exports`** en haut : c'est lui qui crée **Speed**, **Gravity** et **Jump Force** dans
  l'inspecteur, avec leur valeur par défaut, leur nom affiché et leurs bornes.
- **`on_start`** s'exécute une fois, au début de la scène : ici, le personnage lance son animation de repos.
- **`on_update`** s'exécute à chaque image : il lit les touches, calcule la vitesse, applique la gravité
  et le saut, puis déplace le personnage.

Le guide de scripting, plus loin, explique chacune de ces lignes.

## Et ensuite

- Pour comprendre les zones de la fenêtre et les gestes de base : [Se repérer dans l'éditeur](overview/editor-tour.md).
- Pour construire votre propre scène : [Tutoriel : première scène jouable](first-playable-scene.md).
- Pour approfondir un sujet vu ici : [Déplacer un acteur](../guides/acteurs/deplacer-acteur.md), [Prefabs et instances](../guides/organiser/prefabs.md).
