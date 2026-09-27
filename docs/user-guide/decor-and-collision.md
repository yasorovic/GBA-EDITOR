# Ajouter un décor et des collisions

Ce guide reprend après [Créer votre première scène jouable](first-playable-scene.md). Votre acteur
se déplace déjà avec une vitesse réglable. Nous allons maintenant lui donner un décor, un sol et
des murs qu'il ne peut pas traverser.

## 1. Ajouter un décor

Importez un décor PNG depuis l'écran **Backgrounds**, puis ajoutez-le à votre scène dans le
**Scene Manager**. Placez votre acteur devant une zone dégagée, avec un mur ou un sol visible à
proximité.

Le décor est visuel. Pour décider où l'acteur peut passer, utilisez la carte de collision de la
scène.

## 2. Peindre la carte de collision

Dans la barre d'outils flottante du canvas :

1. choisissez l'outil **Collision** (`C`) ;
2. choisissez le pinceau **8 × 8 px** ;
3. peignez une ligne sous l'acteur et un petit mur à côté de lui.

La surimpression de collision ne modifie pas l'image du décor. Elle dessine simplement les zones
pleines que le jeu utilisera pour arrêter les acteurs.

## 3. Donner une boîte de collision à l'acteur

Sélectionnez l'acteur, puis ajoutez le composant **Collision** dans son inspecteur. Laissez le
mode **Solid** activé. Ajustez sa largeur et sa hauteur pour qu'elle couvre approximativement le
sprite.

Cette boîte est la partie de l'acteur qui rencontre les murs et le sol. Sans elle, la carte de
collision existe mais l'acteur ne peut rien heurter.

Chaque boîte porte un **Tag** (`body`, `hitbox`…). Un script demande la boîte à l'acteur par ce
tag, la garde dans une variable, puis lit ou change ses champs pendant le jeu :

```lua
local corps = self:collision_box("body")       -- nil si l'acteur n'a pas de boîte de ce tag
local frappe = self:collision_box("hitbox")

frappe.offset = vec2(8, -4)                    -- décalage par rapport au pivot du sprite
frappe.size = vec2(20, 8)                      -- une zone d'attaque qui s'allonge
corps.solid = false                            -- devient un simple déclencheur : on traverse les murs
frappe:deactivate()                            -- la boîte n'existe plus pour personne
```

| Champ | Nature | Sens |
| --- | --- | --- |
| `tag` | lecture seule | le tag de la boîte (`if boite.tag == "hitbox"`) |
| `active` | lecture / écriture | la case **Active** de l'inspecteur n'en fixe que l'état de départ |
| `solid` | lecture / écriture | arrêtée par la carte de collision, ou simple déclencheur |
| `offset`, `size` | lecture / écriture | décalage et taille, en pixels (bornés à −128..127 et 0..255) |
| `is_grounded` | lecture seule | cette boîte repose-t-elle sur le sol (toujours faux pour une boîte non solide) |
| `bounds` | lecture seule | le rectangle de la boîte en coordonnées du monde |

Deux actions complètent la boîte, dont une question posée à la carte :

```lua
if frappe:overlaps(ennemi) then ... end        -- touche-t-elle N'IMPORTE QUELLE boîte active de cet acteur ?
if frappe:overlaps(ennemi:collision_box("body")) then ... end   -- ... ou celle-là seulement ?

local sol = corps:get_collision_tile(corps.bounds.x, corps.bounds.y + corps.bounds.h)
```

`boite:get_collision_tile(x, y)` interroge la carte de collision à une position du monde, en pixels
(absolue, elle ne dépend pas de la boîte) : elle rend le type de la tuile (0 = vide). Une boîte inactive ne touche personne.

Un tag que le projet ne connaît pas est refusé au Build. Une boîte que l'acteur n'a pas donne `nil` :
testez-la avec `if boite then`. `self.box_count` donne le nombre de boîtes de l'acteur.

## 4. Déplacer l'acteur en respectant les murs

L'écriture directe dans `self.position` est pratique pour débuter, mais elle contourne la
résolution des collisions. Remplacez `on_update` par cette version :

```lua
function on_update()
    self.velocity = input:get_axis("horizontal", "vertical") * vitesse * 256
    self:apply_velocity()
end
```

`self.velocity` utilise une unité plus précise : `256` représente 1 pixel par frame. Votre
réglage **Vitesse** reste donc exprimé simplement en pixels par frame, tandis que le moteur peut
conserver les fractions de déplacement et arrêter l'acteur proprement contre une tuile.

La résolution se fait après `on_update`. Gardez donc `self:apply_velocity()` dans cette fonction
à chaque frame, même lorsqu'aucune touche n'est appuyée.

### Variante : ajouter la gravité pour un jeu de plateforme

La carte de collision n'ajoute pas de gravité. Elle arrête l'acteur lorsqu'il rencontre un mur,
un sol ou un plafond, mais un acteur immobile dans les airs y reste immobile.

Pour un jeu vu de dessus, la version précédente est donc suffisante. Pour un jeu de plateforme,
conservez le déplacement horizontal et ajoutez une accélération vers le bas :

```lua
local gravite = 24

function on_update()
    self.velocity = vec2(input:get_axis("horizontal") * vitesse * 256, self.velocity.y + gravite)
    self:apply_velocity()
end
```

`gravite` est exprimée dans la même échelle que `self.velocity`. Ici, `24` ajoute une petite
vitesse vers le bas à chaque frame. Lorsque la boîte **Collision** touche le sol peint, le
moteur arrête la vitesse verticale ; l'acteur reste alors sur le sol tant que la gravité continue
de s'appliquer.

Pour ajouter le saut, passez au guide [Créer un mouvement de plateforme](platformer-movement.md).

## 5. Tester les collisions

Lancez **Build & Run**. Votre acteur doit s'arrêter contre les zones peintes dans la carte de
collision. Avec la variante de gravité, il tombe également jusqu'au sol.

S'il traverse encore le décor, vérifiez ces trois points :

- la carte de collision contient bien des tuiles peintes à l'endroit du mur ou du sol ;
- l'acteur possède un composant **Collision** dont le mode **Solid** est activé ;
- le script utilise `self.velocity` puis `self:apply_velocity()`, et non une affectation directe
  à `self.position`.

La prochaine étape naturelle est le [mouvement de plateforme](platformer-movement.md), puis la
caméra.
