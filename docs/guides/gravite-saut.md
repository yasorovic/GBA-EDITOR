# Gravité et saut

Ce guide donne à un acteur le comportement d'un personnage de jeu de plateforme : il tombe, marche
sur le sol et saute.

**Ce qu'il vous faut :** une scène avec un sol peint dans la carte de collision, et un acteur avec
une boîte **Collision** en mode **Solid** et un script. Ces deux éléments se préparent dans
[Décors et collisions](decors-collisions.md).

## 1. Ajouter la gravité

La carte de collision arrête l'acteur contre un mur, un sol ou un plafond, mais elle n'ajoute pas
de gravité : un acteur immobile dans les airs y reste. Pour la gravité, ajoutez une accélération
vers le bas à chaque frame :

```lua
local gravite = 24

function on_update()
    self.velocity = vec2(input:get_axis("horizontal") * 2 * 256, self.velocity.y + gravite)
    self:apply_velocity()
end
```

`gravite` s'exprime dans la même échelle que `self.velocity` (`256` vaut 1 pixel par frame). Ici,
`24` ajoute une petite vitesse vers le bas à chaque frame. Quand la boîte touche le sol peint, le
moteur annule la vitesse verticale et l'acteur reste posé.

Pour un jeu vu de dessus, vous n'avez pas besoin de gravité : un simple `self.velocity` suffit.

## 2. Savoir si l'acteur est au sol

Après la résolution des collisions, le moteur met à jour `self.grounded` : `true` quand la boîte
solide repose sur le sol, `false` dans les airs. Cette propriété empêche de sauter à chaque frame :
le joueur ne saute que depuis le sol.

## 3. Ajouter l'impulsion de saut

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

La touche `A` donne une vitesse négative sur l'axe vertical, donc vers le haut. La gravité
l'augmente ensuite chaque frame jusqu'au prochain contact avec le sol.

## 4. Comprendre les valeurs

`256` vaut 1 pixel par frame : une force de saut de `900` correspond à une impulsion d'environ
3,5 pixels par frame vers le haut. **Vitesse** et **Force du saut** sont exposées dans l'inspecteur
parce qu'elles changent souvent d'un personnage à l'autre. `gravite` reste une variable `local` :
c'est une règle commune. Exposez-la si certains acteurs doivent tomber différemment.

## 5. Tester

Lancez **Run**, déplacez l'acteur avec gauche et droite, puis appuyez sur `A` :

- il saute depuis le sol ;
- il ne peut pas sauter de nouveau en l'air ;
- il retombe et s'arrête sur le sol peint ;
- les murs peints l'arrêtent.

Si le saut ne fonctionne pas, vérifiez que la boîte est en mode **Solid** et que le sol est bien
peint. `self.grounded` décrit la fin de la frame précédente : juste après avoir quitté une
plateforme, il peut rester vrai une frame.
