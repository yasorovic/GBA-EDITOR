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

## 2. Rien à réserver

Les acteurs créés au vol naissent dans un **pool partagé par toute la scène** : 512 emplacements en tout,
acteurs posés compris, et n'importe quel prefab y prend la première place libre. Il n'y a donc rien à régler
par prefab. Un projectile détruit rend sa place aux suivants.

Quand la scène est pleine, `spawn` ne crée rien et renvoie `nil`. Un prefab qui demande encore des
emplacements fixes (un interacteur, un prefab à parties ou à rotation, un prefab qui bloque d'autres
acteurs) garde une réserve de 8 instances.

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
sortie de la scène. Si rien n'apparaît, vérifiez d'abord le nom du prefab dans `actor:spawn`.

## À savoir

- Détruisez un projectile avec `self:destroy()` dès qu'il est inutile : un acteur détruit ne
  consomme plus de mise à jour ni d'affichage.
- Le contact avec le joueur se traite dans le script du projectile ou du joueur, avec
  `on_collision_enter` ([Santé et dégâts](sante-degats.md)).
