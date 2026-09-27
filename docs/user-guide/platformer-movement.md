# Créer un mouvement de plateforme

Ce guide reprend après [Ajouter un décor et des collisions](decor-and-collision.md). Votre acteur
possède une boîte **Collision**, la scène contient un sol peint et la gravité le fait tomber.
Nous allons lui permettre de marcher et de sauter.

## 1. Savoir si l'acteur est au sol

Après la résolution des collisions, le moteur met à jour `self.grounded`. Cette propriété vaut
`true` lorsque la boîte solide de l'acteur repose sur le sol, et `false` lorsqu'il est dans les
airs.

Elle sert à empêcher un saut à chaque frame : le joueur ne pourra sauter que depuis le sol.

## 2. Ajouter une impulsion de saut

Remplacez le script de déplacement par cette version complète :

```lua
exports = {
    vitesse    = { type = "int", default = 2,   label = "Vitesse",       min = 0, max = 8 },
    force_saut = { type = "int", default = 900, label = "Force du saut", min = 0, max = 2048 },
}

local gravite = 24

function on_update()
    local vitesse_x = input:get_axis("horizontal") * vitesse * 256
    local vitesse_y = self.velocity.y + gravite

    if self.grounded and input:pressed("a") then
        vitesse_y = -force_saut
    end

    self.velocity = vec2(vitesse_x, vitesse_y)
    self:apply_velocity()
end
```

La touche `A` donne une vitesse négative sur l'axe vertical, donc une impulsion vers le haut. La
gravité augmente ensuite cette vitesse vers le bas jusqu'au prochain contact avec le sol.

## 3. Comprendre les valeurs

`self.velocity` est exprimée en sous-pixels : `256` vaut 1 pixel par frame. C'est pourquoi
`vitesse` est multipliée par `256`, et pourquoi une force de saut comme `900` correspond à une
impulsion d'environ 3,5 pixels par frame vers le haut.

Dans l'inspecteur de l'acteur, essayez de modifier **Vitesse** et **Force du saut**, puis relancez
**Build & Run**. Ces deux réglages sont exposés parce qu'ils changent souvent d'un personnage à
l'autre.

`gravite` reste une variable `local` : pour l'instant, elle fait partie de la règle commune du
jeu. Vous pourrez l'exposer plus tard si certains acteurs doivent tomber différemment.

## 4. Tester le saut

Lancez la ROM, déplacez l'acteur avec gauche et droite, puis appuyez sur `A` :

- il doit sauter depuis le sol ;
- il ne doit pas pouvoir sauter de nouveau pendant qu'il est en l'air ;
- il doit retomber et s'arrêter sur le sol peint ;
- il doit être arrêté par les murs peints dans la carte de collision.

Si le saut ne fonctionne pas, vérifiez que la boîte **Collision** est en mode **Solid** et que le
sol est bien peint dans la carte de collision. `self.grounded` décrit la fin de la frame
précédente : juste après avoir quitté une plateforme, il peut rester vrai une frame.

## Continuer

Votre plateforme est jouable. Vous pouvez maintenant y ajouter des objectifs avec
[Ajouter des collectibles et un score](collectibles.md), ou faire suivre le joueur dans une
grande scène avec [Faire suivre l'acteur par une caméra](camera-follow.md).
