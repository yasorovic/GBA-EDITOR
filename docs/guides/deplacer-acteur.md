# Déplacer un acteur

Ce guide présente les trois façons de lire les touches dans un script et de transformer une
direction en déplacement, puis comment rendre la vitesse réglable depuis l'inspecteur.

**Ce qu'il vous faut :** un acteur avec un sprite et un script (composant **Script**, fichier Lua
vide). Aucun décor n'est nécessaire : ce guide déplace l'acteur librement, en ignorant les murs.
Pour des déplacements qui les respectent, voir [Décors et collisions](decors-collisions.md).

## 1. Une condition par touche

`input:held("nom")` est vrai tant que la touche est maintenue. Les noms de touches de la croix
sont `left`, `right`, `up` et `down`.

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

`vec2(x, y)` est un **vecteur** : une paire de coordonnées, `x` pour la gauche et la droite, `y`
pour le haut et le bas (vers le bas, `y` augmente). Avec cette écriture, deux touches appuyées
déplacent l'acteur sur les deux axes à la fois : les diagonales vont plus vite.

Pour une action qui n'a lieu qu'à l'appui, et non tant que la touche est tenue, utilisez
`input:pressed("a")`. `input:released("a")` détecte le relâchement.

## 2. Un vecteur de direction

`input:get_axis("horizontal", "vertical")` lit la croix d'un seul coup et renvoie un `vec2` dont
chaque coordonnée vaut `-1`, `0` ou `1`. Tout le contenu de `on_update` se réduit à :

```lua
function on_update()
    self.position = self.position + input:get_axis("horizontal", "vertical")
end
```

Le résultat est le même que les quatre conditions. La première forme convient quand chaque
direction déclenche une action différente. `get_axis` convient quand les directions représentent
simplement un déplacement.

## 3. Une vitesse variable

Multipliez le vecteur par un nombre pour changer la vitesse :

```lua
local vitesse = 2

function on_update()
    self.position = self.position + input:get_axis("horizontal", "vertical") * vitesse
end
```

## 4. Régler la vitesse dans l'inspecteur

Pour ajuster la vitesse sans toucher au code, déclarez-la dans une table `exports` au début du
script :

```lua
exports = {
    vitesse = { type = "int", default = 2, label = "Vitesse", min = 0, max = 8 },
}

function on_update()
    self.position = self.position + input:get_axis("horizontal", "vertical") * vitesse
end
```

Après enregistrement, sélectionnez l'acteur : son composant **Script** affiche le réglage
**Vitesse**. La valeur `default` sert aux nouveaux acteurs ; la valeur choisie dans l'inspecteur
appartient à cet acteur.

Exposez une valeur quand vous voulez la régler d'un acteur à l'autre (vitesse, points de vie, portée
d'une attaque). Gardez une variable `local` pour un état interne que personne n'a besoin de
modifier depuis l'éditeur.

## À savoir

- Écrire dans `self.position` **téléporte** l'acteur : pratique pour débuter, mais la carte de
  collision n'est pas consultée. Pour un déplacement physique, utilisez `self.velocity` et
  `self:apply_velocity()` ([Décors et collisions](decors-collisions.md)).
- Les touches se nomment et se reconfigurent dans **Project Settings → Input**.
