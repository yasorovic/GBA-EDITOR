# Collisions

Ce guide explique comment un acteur rencontre le décor : peindre une carte de collision, donner une
boîte de collision à l'acteur, puis le déplacer sans qu'il traverse les murs.

**Ce qu'il vous faut :** un projet avec un acteur dans une scène (un sprite et un script suffisent)
et une image de décor au format PNG.

## 1. Ajouter un décor

Importez le PNG depuis l'écran **Backgrounds**, puis affectez-le à un calque de la scène
(**BG0** à **BG3**, dans l'inspecteur de la scène). Le décor est purement visuel : il ne dit rien
sur ce qu'un acteur peut traverser.

## 2. Peindre la carte de collision

La **carte de collision** de la scène dit où le jeu arrête les acteurs. Dans la barre d'outils
flottante du canvas :

1. choisissez l'outil **Collision** (`C`) ;
2. choisissez le pinceau **8 × 8 px** ;
3. peignez une ligne de sol sous l'acteur et un petit mur à côté de lui.

La surimpression ne modifie pas l'image du décor : elle dessine seulement les tuiles pleines que
le jeu utilisera.

## 3. Donner une boîte de collision à l'acteur

Sélectionnez l'acteur, ajoutez le composant **Collision** et laissez le mode **Solid** activé.
Ajustez la largeur et la hauteur pour couvrir à peu près le sprite. Cette boîte est la partie de
l'acteur qui heurte les murs : sans elle, la carte existe mais rien ne la rencontre.

Deux modes de boîte :

- **Solid** : arrêtée par la carte de collision.
- **Trigger** : ne bloque rien, mais signale les contacts au script (voir
  [Interaction](../faire-vivre/interaction.md) et [Santé et dégâts](../faire-vivre/sante-degats.md)).

## 4. Déplacer l'acteur en respectant les murs

Écrire directement dans `self.position` **téléporte** l'acteur : la carte n'est pas consultée. Pour
un déplacement qui respecte les murs, passez par la vitesse :

```lua
local vitesse = 2

function on_update()
    self.velocity = input:get_axis("horizontal", "vertical") * vitesse * 256
    self:apply_velocity()
end
```

`self.velocity` utilise une unité plus fine que le pixel : `256` vaut 1 pixel par frame. Le moteur
conserve ainsi les fractions de déplacement et arrête l'acteur proprement contre une tuile.
`self:apply_velocity()` fait la résolution : appelez-le à chaque frame, même sans touche appuyée.

Lancez **Run** : l'acteur doit s'arrêter contre le sol et le mur peints.

## Lire et régler la boîte depuis un script

Chaque boîte porte un **Tag** (`body`, `hitbox`...). Un script demande la boîte à l'acteur par ce
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

Deux actions complètent la boîte :

```lua
if frappe:overlaps(ennemi) then ... end        -- touche-t-elle N'IMPORTE QUELLE boîte active de cet acteur ?
if frappe:overlaps(ennemi:collision_box("body")) then ... end   -- ... ou celle-là seulement ?

local sol = corps:get_collision_tile(corps.bounds.x, corps.bounds.y + corps.bounds.h)
```

`boite:get_collision_tile(x, y)` interroge la carte à une position du monde, en pixels (absolue, elle
ne dépend pas de la boîte) et rend le type de la tuile (0 = vide). Une boîte inactive ne touche
personne. Un tag que le projet ne connaît pas est refusé au Build. Une boîte que l'acteur n'a pas
donne `nil` : testez-la avec `if boite then`. `self.box_count` donne le nombre de boîtes de l'acteur.

## Si l'acteur traverse encore le décor

- la carte de collision contient-elle des tuiles peintes à l'endroit du mur ou du sol ?
- l'acteur possède-t-il un composant **Collision** en mode **Solid** ?
- le script utilise-t-il `self.velocity` puis `self:apply_velocity()`, et non une affectation à
  `self.position` ?

Pour ajouter gravité et saut, voir [Gravité et saut](gravite-saut.md).
