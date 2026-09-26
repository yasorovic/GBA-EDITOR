# Créer votre première scène jouable

Ce guide crée un résultat simple, mais complet : un acteur visible qui se déplace quand vous
appuyez sur une touche, puis une ROM que vous pouvez lancer dans mGBA.

Avant de commencer, installez devkitPro et mGBA, puis créez ou ouvrez un projet. Le
[guide utilisateur](index.md) explique ces premières étapes.

## 1. Importer un sprite

Ouvrez l'écran **Sprites**, puis cliquez sur **+** et choisissez une image PNG. Utilisez de
préférence une image simple pour ce premier essai : un personnage, un objet ou un carré coloré.

Dans l'inspecteur, définissez la taille d'une frame, puis créez une animation nommée `idle` qui
contient au moins une image. Enregistrez avec `Ctrl+S`.

> Si votre image n'est pas découpée comme prévu, vérifiez d'abord la taille des frames. Pour ce
> premier essai, une animation d'une seule frame suffit.

## 2. Créer une scène et un acteur

Ouvrez le **Scene Manager**. Dans la section **Scenes**, cliquez sur **+** et donnez un nom à la
scène, par exemple `PremiereScene`. Son canvas représente l'écran de la GBA.

Ajoutez ensuite un acteur avec l'outil d'ajout, puis sélectionnez-le. Dans son inspecteur :

1. choisissez votre sprite ;
2. placez l'acteur à un endroit visible du canvas ;
3. sélectionnez l'animation `idle`.

Vous pouvez déjà lancer **Build & Run** (`F5`) pour vérifier que l'acteur apparaît. C'est un bon
réflexe : vérifiez une étape avant d'ajouter la suivante.

## 3. Attacher un script

Avec l'acteur toujours sélectionné, ajoutez le composant **Script** dans son inspecteur, puis
créez un fichier Lua. Le Script Editor s'ouvre.

Remplacez son contenu par ceci :

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

Enregistrez le script, puis lancez **Build & Run**. Maintenez la touche droite dans mGBA : votre
acteur doit avancer d'un pixel à chaque image.

## 4. Faire bouger l'acteur dans les quatre directions

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
l'acteur sur les deux axes. Nous améliorerons ce comportement lorsque nous aborderons le
mouvement et les collisions.

### Variante : déplacer avec un vecteur de direction

La croix directionnelle peut aussi être lue d'un seul coup avec `input.axis`. Cette propriété
renvoie un **vecteur** `vec2` : une paire de coordonnées, `x` pour la gauche et la droite, `y`
pour le haut et le bas. Chaque coordonnée vaut `-1`, `0` ou `1`.

Vous pouvez donc remplacer tout le contenu de `on_update` par :

```lua
function on_update()
    local direction = input.axis
    self.position = self.position + direction
end
```

Le résultat est le même que les quatre conditions précédentes, mais cette écriture devient plus
pratique lorsque la vitesse devient une variable :

```lua
local vitesse = 2

function on_update()
    self.position = self.position + input.axis * vitesse
end
```

La première forme, avec une condition par touche, est préférable quand chaque direction doit
faire une action différente. La forme avec `input.axis` convient quand les quatre directions
représentent simplement un déplacement.


### Variante : régler la vitesse dans l'inspecteur

La ligne `local vitesse = 2` fixe la vitesse dans le fichier Lua. Pour pouvoir l'ajuster depuis
l'inspecteur de l'acteur, déclarez-la dans la table `exports` au début du script :

```lua
exports = {
    vitesse = { type = "int", default = 2, label = "Vitesse", min = 0, max = 8 },
}

function on_update()
    self.position = self.position + input.axis * vitesse
end
```

Après avoir enregistré, sélectionnez l'acteur dans le **Scene Manager**. Son composant
**Script** affiche le réglage **Vitesse**. Vous pouvez maintenant tester plusieurs valeurs sans
modifier le code. La valeur `default` sert aux nouveaux acteurs ; la valeur choisie dans
l'inspecteur appartient à cet acteur.

Exposez une valeur lorsque vous pensez vouloir la régler d'un acteur à l'autre, par exemple la
vitesse, les points de vie ou la portée d'une attaque. Gardez une variable `local` pour un état
interne que personne n'a besoin de modifier depuis l'éditeur.


## Continuer

Votre acteur bouge maintenant et sa vitesse se règle dans l'inspecteur. Pour lui donner un décor,
des murs et un sol, passez au guide [Ajouter un décor et des collisions](decor-and-collision.md).

## Si le Build s'arrête

Lisez la première erreur dans le panneau de build. Les causes les plus fréquentes sont :

- le nom de l'animation ne correspond pas à `"idle"` ; corrigez le nom dans le script ou dans
  l'éditeur de sprites ;
- le script n'est pas attaché au bon acteur ; sélectionnez l'acteur et vérifiez son composant
  **Script** ;
- une parenthèse, une guillemet ou un `end` manque ; le panneau indique la ligne concernée.

Le [guide de scripting](../scripting.md) explique ensuite les événements, les variables et les
fonctions privées.
