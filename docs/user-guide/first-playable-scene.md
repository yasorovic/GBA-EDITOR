# Tutoriel : votre première scène jouable

Ce tutoriel crée un résultat simple, mais complet : un acteur visible qui se déplace quand vous
appuyez sur une touche, puis une ROM que vous lancez dans mGBA. Suivez-le dans l'ordre.

Avant de commencer, installez devkitPro et mGBA, puis créez ou ouvrez un projet (voir la
[vue d'ensemble](index.md)).

## 1. Importer un sprite

Ouvrez l'écran **Animations**, cliquez sur **+** dans la liste des sprites et choisissez une image
PNG. Pour ce premier essai, une image simple suffit : un personnage, un objet ou un carré coloré.

Dans l'inspecteur, définissez la taille d'une frame, puis créez une animation nommée `idle` qui
contient au moins une image. Enregistrez avec `Ctrl+S`.

```{note}
Si votre image n'est pas découpée comme prévu, vérifiez d'abord la taille des frames. Pour ce
premier essai, une animation d'une seule frame suffit.
```

## 2. Créer une scène et un acteur

Ouvrez l'écran **Scenes**. Dans la section **Scenes** de la **Scene library**, cliquez sur **+** et
donnez un nom à la scène, par exemple `PremiereScene`.

Ajoutez ensuite un acteur avec l'outil d'ajout, puis sélectionnez-le. Dans son inspecteur :

1. choisissez votre sprite ;
2. placez l'acteur à un endroit visible du canvas ;
3. sélectionnez l'animation `idle`.

Lancez déjà **Run** (`F5`) pour vérifier que l'acteur apparaît. C'est un bon réflexe : vérifiez une
étape avant d'ajouter la suivante.

## 3. Attacher un script

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

## 4. Les quatre directions

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

## Ce que vous avez fait

Un sprite importé, une scène, un acteur, un script, une ROM : c'est la boucle de base de
Backstage. Pour aller plus loin, ouvrez le guide dont vous avez besoin :

- [Déplacer un acteur](../guides/deplacer-acteur.md) : un vecteur de direction, une vitesse
  réglable dans l'inspecteur.
- [Décors et collisions](../guides/decors-collisions.md) : un décor, un sol et des murs.
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
