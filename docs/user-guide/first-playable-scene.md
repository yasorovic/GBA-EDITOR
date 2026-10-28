# Tutoriel : votre première scène jouable

Ce tutoriel va d'un nouveau projet à une ROM jouable : un acteur visible qui se déplace quand vous
appuyez sur une touche, lancé dans mGBA. Suivez-le dans l'ordre.

Avant de commencer, installez devkitPro et mGBA, puis créez ou ouvrez un projet (voir la
[vue d'ensemble](index.md)).

## 1. Importer un sprite

Le tutoriel utilise une petite planche de fantôme : {download}`ghost.png <downloads/ghost.png>`.
Elle contient quatre images de 16 x 16 pixels.

```{image} downloads/ghost.png
:alt: La planche ghost.png : quatre fantômes blancs côte à côte.
:width: 256px
:class: backstage-screenshot backstage-pixel
```

Ouvrez l'écran **Animations**, cliquez sur **+** dans la liste des sprites et choisissez
`ghost.png`. Vous pouvez aussi prendre votre propre image : un personnage, un objet ou un carré
coloré. [Importer votre première ressource](overview/first-import.md) détaille les autres chemins.

Dans l'inspecteur, réglez la taille d'une frame sur 16 x 16, puis créez une animation nommée `idle`
qui contient au moins une image. Enregistrez avec `Ctrl+S`.

```{note}
Si votre image n'est pas découpée comme prévu, vérifiez d'abord la taille des frames. Pour ce
premier essai, une animation d'une seule frame suffit.
```

## 2. Le point de départ

Ouvrez l'écran **Scenes**. Un nouveau projet contient déjà une scène, `Scene_01`, avec deux
éléments : un acteur, `Player`, et une `Camera`. Au centre du canvas, l'acteur apparaît sous la forme
d'une petite icône de fantôme : il n'a pas encore de sprite.

```{figure} overview/img/new-project.png
:alt: Un nouveau projet dans l'éditeur : la scène Scene_01 avec Player et Camera, et l'acteur au centre du canvas.
:class: backstage-screenshot

Un nouveau projet : une scène, un acteur et une caméra.
```

Le canvas montre la scène à l'échelle de la console, dont l'écran fait 240 x 160 pixels. Cliquez sur
`Scene_01` dans la liste de gauche : l'inspecteur règle alors la scène elle-même (son mode, ses
calques de décor, sa musique, sa transition).

## 3. Donner un sprite à l'acteur

Cliquez sur `Player` dans la liste de gauche, ou sur l'acteur dans le canvas : l'inspecteur affiche
ses réglages. Dans la section **Components**, cliquez sur le **+** et choisissez **Sprite**.

```{figure} overview/img/add-component.png
:alt: L'inspecteur de l'acteur Player, avec le menu d'ajout de composant : Sprite, Collision, SoundFX, Interactive, Script.
:class: backstage-screenshot

Le **+** de la section **Components** propose Sprite, Collision, SoundFX, Interactive et Script.
```

Dans le composant, choisissez votre sprite, puis l'animation `idle`. Déplacez l'acteur avec l'outil
de sélection (la flèche de la barre d'outils du canvas) pour le placer à un endroit visible.

Lancez déjà **Run** (`F5`) pour vérifier que l'acteur apparaît. C'est un bon réflexe : vérifiez une
étape avant d'ajouter la suivante. La barre du bas de la fenêtre suit au passage les limites de la
console pour cette scène (sprites, tuiles, palettes, mémoire). Une valeur passe au jaune puis au
rouge à l'approche d'une limite ; elle ne bloque rien.

## 4. Attacher un script

Avec l'acteur sélectionné, ajoutez le composant **Script** dans son inspecteur, puis créez un
fichier Lua. Le Script Editor s'ouvre. Remplacez son contenu par :

```lua
function on_start()
    self:play_anim("idle")
end

function on_update()
    if input:held("right") then
        self.position = self.position + vec2(1, 0)
    end
end
```

Enregistrez, puis lancez **Run**. Maintenez la touche droite dans mGBA : l'acteur avance d'un pixel
à chaque image.

## 5. Les quatre directions

Ajoutez les autres touches dans `on_update` :

```lua
function on_update()
    if input:held("left") then
        self.position = self.position + vec2(-1, 0)
    end
    if input:held("right") then
        self.position = self.position + vec2(1, 0)
    end
    if input:held("up") then
        self.position = self.position + vec2(0, -1)
    end
    if input:held("down") then
        self.position = self.position + vec2(0, 1)
    end
end
```

Les diagonales sont normales avec cette première version : deux directions appuyées déplacent
l'acteur sur les deux axes.

## 6. Aller plus loin dans la scène

- **Un deuxième acteur :** choisissez l'outil d'ajout (le **+** dans un cercle) dans la barre
  d'outils du canvas, puis cliquez dans la scène.
- **Une deuxième scène :** dans l'onglet **Scene library** de la colonne de gauche, cliquez sur le
  **+** de la section **Scenes** et choisissez **New scene**. **Create group** range les scènes par
  dossier.
- **Un décor :** les calques **BG0** à **BG3** de l'inspecteur de la scène reçoivent chacun un
  background importé depuis l'écran **Backgrounds**. Le guide
  [Collisions](../guides/acteurs/collisions.md) détaille ce geste.

```{figure} overview/img/new-scene-menu.png
:alt: La Scene library avec le menu du + de la section Scenes : New scene et Create group.
:class: backstage-screenshot

Le **+** de la section **Scenes** : **New scene** ou **Create group**.
```

## Ce que vous avez fait

Un sprite importé, une scène, un acteur, un script, une ROM : c'est la boucle de base de
Backstage. Pour aller plus loin, ouvrez le guide dont vous avez besoin :

- [Déplacer un acteur](../guides/acteurs/deplacer-acteur.md) : un vecteur de direction, une vitesse
  réglable dans l'inspecteur.
- [Collisions](../guides/acteurs/collisions.md) : un décor, un sol et des murs.
- Tous les [guides](../guides/index.md), ou l'enchaînement complet de
  [Un mini-jeu de plateforme](mini-game.md).

## Si le Build s'arrête

Lisez la première erreur dans l'onglet **Diagnostics**. Les causes les plus fréquentes :

- le nom de l'animation ne correspond pas à `"idle"` : corrigez-le dans le script ou dans
  l'écran **Animations** ;
- le script n'est pas attaché au bon acteur : sélectionnez l'acteur et vérifiez son composant
  **Script** ;
- une parenthèse, un guillemet ou un `end` manque : le panneau indique la ligne concernée.

Le [guide de scripting](../scripting.md) explique ensuite les événements, les variables et les
fonctions privées.
