# Qu'est-ce qu'une tilemap ?

Une image de décor n'est pas stockée dans la console comme une grande photo, pixel après pixel. La Game Boy
Advance la décompose en **tuiles** et en **carte**. Comprendre ce découpage explique pourquoi l'éditeur parle de
palettes, de retournements et de budgets, et ouvre la porte à des effets que seul un script peut produire.

**Ce qu'il vous faut :** un décor importé (voir [Importer un décor](importer-un-decor.md)).

## 1. Des tuiles de 8 × 8 pixels

La console dessine un décor avec des **tuiles** : de petits carrés de 8 × 8 pixels. Une image de 240 × 160 pixels
(la taille de l'écran) représente donc 30 tuiles en largeur et 20 en hauteur.

## 2. Une palette par tuile

Chaque tuile n'emploie qu'une **palette** de 16 couleurs. Le décor peut en avoir jusqu'à 16, et c'est la
carte qui dit laquelle s'applique à chaque tuile. Une même tuile dessinée avec une autre palette change de
couleurs sans coûter une tuile de plus.

## 3. Le jeu de tuiles et la carte

Quand vous importez un décor, l'éditeur le sépare en deux parties :

- **le jeu de tuiles** (*tileset*) : la liste des tuiles **différentes** du décor ;
- **la carte** (*tilemap*) : une grille qui dit, pour chaque case de l'image, quelle tuile y poser.

Chaque case de la carte retient quatre informations :

| Information | Rôle |
| --- | --- |
| le numéro de la tuile | quelle tuile du jeu de tuiles dessiner |
| la banque de palette (0 à 15) | avec quelles couleurs |
| le retournement horizontal | tuile retournée de gauche à droite, ou non |
| le retournement vertical | tuile retournée de haut en bas, ou non |

## 4. Pourquoi découper ainsi

Un décor contient beaucoup de motifs répétés : de l'herbe, une brique, un morceau de ciel. L'éditeur les
reconnaît, y compris quand une tuile n'est que le miroir d'une autre, et ne **stocke qu'une seule fois** chaque
tuile différente. La carte, elle, répète simplement un numéro. C'est cette déduplication qui permet de faire
tenir un grand niveau dans la mémoire vidéo de la console.

Un décor très varié, où presque aucune tuile ne se répète, consomme donc plus de mémoire qu'un décor construit
avec peu de motifs.

## 5. Modifier la carte depuis un script

Comme la carte est une grille de numéros, un script peut la changer pendant le jeu, une case à la fois : ouvrir
une porte, casser un bloc, faire pousser une plante. Les cases se repèrent en **tuiles** (colonne, ligne), pas en
pixels, et se lisent et s'écrivent sur un calque (voir [Fond et calque](fond-et-calque.md)).

Cet exemple recopie la tuile de la case (2, 10) dans la case (5, 10) :

```lua
function on_start()
    local fond = layer:get(0)
    local herbe = fond:get_tile(2, 10)   -- le numéro de la tuile en colonne 2, ligne 10
    fond:set_tile(5, 10, herbe)          -- la même tuile, en colonne 5, ligne 10
end
```

On y lit un numéro de tuile sans avoir besoin de le connaître : il vient de la carte. Les autres fonctions
(`fill`, `set_tile_palette`, `set_tile_flip`) sont dans le [groupe Tilemap](../../lua-api/api/scene/tilemap.md)
du catalogue.

## À savoir

- Un numéro de tuile ne désigne que les tuiles qui existent dans le jeu de tuiles du décor : un script ne crée
  pas de nouvelle tuile, il réutilise celles de l'image importée.
- La carte et le jeu de tuiles appartiennent au **fond**, pas à la scène : voir
  [Fond et calque](fond-et-calque.md).
