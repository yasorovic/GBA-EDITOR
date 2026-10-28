# Machines d'état

Un **état** est une variable qui décrit ce que fait un acteur en ce moment : attendre, marcher,
fuir. Ce guide organise un script autour d'états plutôt que d'une pile de conditions, ce qui rend
le comportement lisible et facile à étendre.

**Ce qu'il vous faut :** une scène avec un sol peint, et un acteur avec une boîte **Collision** en
mode **Solid** et un script (voir [Collisions](../acteurs/collisions.md)). L'exemple est un
gardien qui attend, marche jusqu'à un mur, puis repart dans l'autre sens.

## 1. Nommer les états

Choisissez un nombre par état et notez-le en commentaire en tête de script :

```lua
-- Etats : 0 = attend, 1 = marche
local etat = 0
local minuteur = 0
local sens = 1
```

`minuteur` compte les frames passées dans l'état courant, `sens` vaut `1` (vers la droite) ou
`-1` (vers la gauche).

## 2. Un bloc par état

`on_update` choisit le bloc à exécuter selon `etat` :

```lua
function on_start()
    etat = 0
    minuteur = 60
end

function on_update()
    if etat == 0 then
        self.velocity = vec2(0, 0)
        minuteur = minuteur - 1
        if minuteur <= 0 then
            etat = 1
        end
    elseif etat == 1 then
        self.velocity = vec2(sens * 256, 0)
    end
    self:apply_velocity()
end
```

Dans l'état `0`, le gardien s'arrête et compte 60 frames (une seconde). Dans l'état `1`, il avance
d'un pixel par frame. La transition d'un état à l'autre est la seule ligne qui change `etat`.

## 3. Changer d'état sur un événement

Les événements du moteur déclenchent aussi des transitions. `on_tile_collide` est appelé quand
l'acteur heurte une tuile de la carte de collision, avec la normale du choc :

```lua
function on_tile_collide(normal_x, normal_y)
    if normal_x ~= 0 and etat == 1 then
        sens = -sens
        etat = 0
        minuteur = 60
    end
end
```

Un choc horizontal pendant la marche retourne le gardien et le renvoie à l'attente. Le mouvement
passe par `self.velocity` puis `apply_velocity()` : c'est cette vitesse que la carte lit pour
détecter un mur. Écrire `self.position` téléporterait l'acteur, et la carte ne verrait aucun
mouvement.

## 4. Ajouter un état

Pour un troisième état, par exemple `2 = fuite`, ajoutez son bloc dans `on_update` avec un
`elseif etat == 2 then`, et la ligne de commentaire en tête. Chaque état reste indépendant des
autres : c'est son bloc, et seulement lui, qui décide de la suite.

## À savoir

- Un état est une donnée de l'acteur. Pour qu'il survive à un changement de scène, utilisez une
  globale ([Variables et affichage](../organiser/variables-affichage.md)).
- L'auto-direction fait tourner le sprite vers son sens de marche si le sprite dessine les deux
  sens (par exemple une direction est et une direction ouest). Dans ce cas, ne retournez pas le
  sprite à la main avec `self.flip_h` : les deux retournements s'ajouteraient.
- Pour une suite d'actions qui s'enchaînent dans le temps (attendre, jouer une animation,
  recommencer), une **séquence** (`on_sequence_<nom>` avec `wait`) peut être plus simple qu'un état
  explicite. Un exemple figure dans [Santé et dégâts](sante-degats.md).
