# Créer des acteurs pendant le jeu

Ce guide crée des acteurs en cours de partie : des projectiles, des étincelles, tout ce qui
apparaît puis disparaît. L'exemple est une tourelle qui tire un projectile toutes les 1,5 seconde.

**Ce qu'il vous faut :** une scène et deux sprites (la tourelle et le projectile). Pour le principe
des prefabs, voir [Prefabs et instances](prefabs.md).

## 1. Le prefab du projectile

Créez un prefab `Projectile` avec son sprite, une boîte **Collision** en mode **Trigger** et ce
script :

```lua
exports = {
    vitesse = { type = "int", default = 2, label = "Vitesse", min = 1, max = 8 },
}

function on_update()
    self.position = self.position + vec2(vitesse, 0)
    if self.position.x > scene.size.w then
        self:destroy()
    end
end
```

Le projectile avance vers la droite et se détruit en sortant de la scène (`scene.size.w` est la
largeur de la scène).

## 2. Réserver des instances dans le pool

Les acteurs créés au vol viennent d'un **pool** réservé à l'avance. Dans l'inspecteur de la scène, réservez des instances de
`Projectile` dans le pool de prefabs. Sans cette réserve, `actor:spawn` ne peut pas créer de
projectile.

Prévoyez le nombre maximal de projectiles vivants en même temps. Quand le pool est plein, `spawn`
ne crée rien et renvoie `nil`.

## 3. Créer l'acteur depuis un script

Ajoutez un script à la tourelle :

```lua
function on_update()
    if scene.frame % 90 == 0 then
        actor:spawn("Projectile", self.position)
    end
end
```

`actor:spawn("Projectile", position)` crée une instance du prefab à la position donnée (un `vec2`
en pixels du monde). `scene.frame` est le compteur de frames de la scène : toutes les 90 frames
(1,5 seconde), la tourelle tire.

## 4. Régler l'instance au moment de sa création

Une instance créée en jeu n'a pas de fiche dans l'éditeur : ses exports se règlent **au moment du
`spawn`**, par une table en troisième argument.

```lua
local p = actor:spawn("Projectile", self.position, { vitesse = 4 })
```

Les clés absentes gardent la valeur du prefab, sinon le `default` du script. Les clés doivent être
des exports du prefab. La table s'écrit en début de ligne ou dans un `local x = actor:spawn(...)`.

## 5. Tester

Lancez **Run** : la tourelle tire à intervalle régulier et les projectiles disparaissent à la
sortie de la scène. Si rien n'apparaît, vérifiez d'abord la réserve du pool.

## À savoir

- Détruisez un projectile avec `self:destroy()` dès qu'il est inutile : un acteur détruit ne
  consomme plus de mise à jour ni d'affichage.
- Le contact avec le joueur se traite dans le script du projectile ou du joueur, avec
  `on_collision_enter` ([Santé et dégâts](sante-degats.md)).
