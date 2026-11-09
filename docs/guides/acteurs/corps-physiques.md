# Corps physiques

Ce guide décrit les quatre modes de **Physics body**, ce que chacun fait, comment la gravité de la scène
les atteint, et comment construire plateformes mobiles, caisses et sols à sens unique.

**Ce qu'il vous faut :** un acteur avec une boîte **Collision** et un composant **Physics body**. La boîte est décrite dans [Collisions](collisions.md). Le guide [Gravité et saut](gravite-saut.md) précède celui-ci : il écrit la gravité à la main, ici le moteur la fournit.

## 1. Choisir un mode

Le champ **Mode** du composant dit qui déplace l'acteur et comment il rencontre les autres.

| Mode | Qui le déplace | Ce qu'il fait |
| --- | --- | --- |
| `StaticBody` | personne | décor solide : sol, mur, bloc. Écrire `self.position` le téléporte avec sa forme. |
| `CharacterBody` | le script, par `body.velocity` puis `body:apply_velocity()` | personnage : arrêté par la carte et par les boîtes **Block**, donne `grounded` et `floor`. Suit la gravité de la scène (option **Use scene gravity**). |
| `KinematicBody` | lui-même : sa `velocity` s'applique à chaque frame | plateforme mobile. Elle porte ce qui repose dessus. Suit aussi la gravité de la scène, à décocher pour une plateforme qui flotte. |
| `RigidBody` | le moteur | caisse : tombe, rebondit, s'empile, s'endort au repos. |

Une boîte de collision a une **réponse** : **Block** arrête les autres acteurs, **Sensor** ne bloque rien et
signale seulement les contacts au script. Le mode **Solid** de la boîte ne concerne que la carte de collision.

Le champ **Physics collider** choisit la boîte qui sert de forme physique. Laissé sur « Automatic », le corps
utilise les boîtes solides déjà présentes.

## 2. La gravité de la scène

Deux réglages, tous deux en pixels par frame au carré :

- **Game > Project Settings > Physics & Collisions** donne la gravité par défaut du projet, ainsi que les
  passes du solveur, la vitesse de chute maximale, l'amortissement linéaire et le sommeil des Rigid.
- La carte **Physics** de l'inspecteur d'une scène hérite de tout cela (case **Use project physics settings**)
  ou le remplace par un jeu local complet.

Un `RigidBody` reçoit toujours cette gravité (multipliée par son champ **Gravity scale**). Un `CharacterBody` et
un `KinematicBody` la reçoivent aussi tant que leur case **Use scene gravity** est cochée, ce qui est le cas par
défaut : le moteur ajoute la gravité à leur vitesse à chaque frame, multipliée par **Gravity scale** et bornée par
la vitesse maximale de chute. Le script d'un personnage n'a donc qu'à conserver la vitesse verticale :

```lua
function on_update()
    local body = self:physics_body()

    body.velocity = vec2(input:get_axis("horizontal") * 2 * 256, body.velocity.y)
    body:apply_velocity()
end
```

Le saut du guide [Gravité et saut](gravite-saut.md) se simplifie de la même façon : la ligne qui ajoutait
`scene.gravity` disparaît, le moteur la fournit, et il reste la vitesse horizontale et l'impulsion :

```lua
function on_update()
    local body = self:physics_body()
    local vitesse_y = body.velocity.y

    if body.grounded and input:pressed("a") then
        vitesse_y = -900
    end

    body.velocity = vec2(input:get_axis("horizontal") * 2 * 256, vitesse_y)
    body:apply_velocity()
end
```

Décochez **Use scene gravity** pour un corps qui ne doit pas tomber (une plateforme mobile, un personnage vu de
dessus) ou dont le script gère lui-même la chute, comme dans [Gravité et saut](gravite-saut.md). Dans ce cas,
`scene.gravity` reste lisible (Q8 : 256 vaut 1 pixel par frame au carré) et le script l'ajoute à sa vitesse. Ne
l'ajoutez pas quand la case est cochée : la gravité serait comptée deux fois.

Une gravité de `0,25` px/frame² vaut `64` en Q8. Un script peut aussi écrire `scene.gravity = vec2(0, 64)` :
les Rigid suivent, et les notions de sol (`grounded`, `floor`, transport par une plateforme) suivent l'axe
dominant de la nouvelle gravité.

Plus la chute est longue, plus la vitesse croît : sans plafond côté script, un Character peut dépasser les 8 pixels
par frame. Le moteur en tient compte pour le sol, mais borner `vitesse_y` dans le script reste le plus sûr.

## 3. Plateformes mobiles (KinematicBody)

Donnez une `velocity` au `KinematicBody` ; il avance seul. Décochez **Use scene gravity** pour qu'une plateforme
ne tombe pas. Les Character et les Rigid posés sur sa face qui regarde la
gravité sont **portés** : ils suivent le déplacement réel de la plateforme, une seule fois par frame, même si un mur
a raccourci son trajet.

- La plateforme **pousse** un Character qu'elle rencontre, même immobile. Un mur ou le
  sol derrière lui l'arrête : il n'est jamais enfoncé dans la carte.
- Un Character porté puis coincé contre un StaticBody ou la carte reçoit, à chaque frame de blocage, l'événement
  `on_crushed(obstacle)` (l'obstacle est `nil` pour la carte). Le moteur ne choisit aucune conséquence : dégâts,
  arrêt de la plateforme ou rien, c'est le script du jeu.

```lua
function on_crushed(obstacle)
    sfx:play("sfx_hurt")
end
```

`body.floor` rend l'acteur qui porte le Character, ce qui permet de reconnaître une plateforme précise.

## 4. Caisses et piles (RigidBody)

Un Rigid se règle dans l'inspecteur :

- **Mass** (0,1 à 100) répartit les corrections entre deux Rigid ; elle ne change rien contre un StaticBody ;
- **Gravity scale** (-8 à 8) multiplie la gravité de la scène ;
- **Can sleep** autorise le sommeil : un Rigid qui ne bouge plus pendant le délai du projet (30 frames par défaut)
  ne coûte plus rien, et un choc le réveille.

Le rebond et le frottement viennent du matériau de la boîte (voir [Gravité et saut](gravite-saut.md)). Plus les
passes du solveur sont nombreuses (1 à 8, 4 par défaut), plus une pile est stable et plus la scène coûte. Des caisses
posées sans se recouvrir s'endorment vite ; des caisses qui naissent en se recouvrant se repoussent sans cesse et
gardent un coût élevé tant que le recouvrement dure.

## 5. Faces à sens unique et descente

Une face à sens unique n'arrête que ce qui vient du côté vers lequel elle regarde. Deux endroits la déclarent :

- une **tuile** de la carte (index 22 à 25, voir [Types de tuile de collision](types-de-tuile-collision.md)) ;
- une **boîte** d'acteur, par son champ **Sens unique** : `Against gravity` (la plateforme classique), `Up`,
  `Down`, `Left` ou `Right`.

`Down` se traverse par le dessus et bute par le dessous ; `Up` fait l'inverse. Pour descendre à travers une face
qui porte le personnage :

```lua
if body.grounded and input:pressed("b") then
    body:drop_through(10)       -- ignore les faces à sens unique pendant 10 frames
end
```

L'appel retire le contact au sol : le personnage tombe dès la frame suivante, y compris debout et immobile, et un
sol plein sous lui le reprend aussitôt.

## 6. Acteurs posés et acteurs créés par le script

Un acteur créé par `actor:spawn` se comporte comme le même acteur posé dans la scène : même blocage, mêmes
impulsions Rigid, même transport par une plateforme, même sol, même événement `on_crushed`.

## Si le comportement surprend

- un Character reste dans les airs : sa gravité est peut-être nulle, ou **Use scene gravity** est décochée. Lisez
  `scene.gravity` et vérifiez le réglage du projet et de la scène ;
- une plateforme `KinematicBody` tombe : décochez **Use scene gravity** ;
- un Rigid ne tombe pas : même cause, ou **Gravity scale** à `0` ;
- un personnage ne descend pas d'une plateforme : appelez `body:drop_through(frames)`, et vérifiez qu'elle est à sens
  unique (une face pleine le porte toujours) ;
- une boîte ne bloque rien : sa réponse est **Sensor**, ou la matrice de tags de **Physics & Collisions** refuse le
  couple.
