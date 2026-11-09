# Zones de jeu (Area)

Ce guide pose une **Area** : une zone de jeu sans sprite, qui prévient le script d'un acteur quand
celui-ci y entre, y reste ou en sort, et peut porter son propre script. Elle sert à une porte, un piège, une sortie de niveau ou un
déclencheur de cinématique.

Une Area est un volume léger : pas de sprite, pas d'OAM, et aucune place dans le pool d'acteurs. Elle
porte une **forme** de collision (un rectangle) et, si elle doit prévenir des scripts, un
**déclencheur**. Les **acteurs** qui la touchent reçoivent les événements ; un **script d'Area**, s'il
existe, les reçoit aussi (voir la section 4).

**Ce qu'il vous faut :** une scène avec un acteur qui se déplace et qui porte une boîte **Collision**
et un script (voir [Déplacer un acteur](../acteurs/deplacer-acteur.md)).

## 1. Poser une Area

Dans le canvas, ouvrez le menu du bouton **+** de la barre d'outils flottante et choisissez
**Add area**, puis cliquez dans la scène : une zone de 32×32 pixels, centrée sur le clic, est créée.
Le bouton **+** de l'arbre de scène propose aussi **Area**.

Sélectionnez l'Area pour régler dans l'inspecteur :

- **Active on start** indique si l'Area est active au chargement de la scène.
- **Trigger** active les événements de contact envoyés aux scripts des acteurs. Cette case est cochée
  pour une Area neuve.
- **Position**, puis la carte **Shape** : le **Tag** de la forme, son décalage (**Offset**) et sa
  taille (**Size**). La taille se règle aussi à la souris, avec les poignées d'une Area sélectionnée.

Le nom se change dans l'en-tête de l'inspecteur, comme pour un acteur. Il est **local à la scène** :
deux scènes peuvent chacune avoir une Area `Porte`.

### Déplacer ou dupliquer une sélection

Dans le canvas, ajoutez des acteurs ou des Areas à la sélection avec `Shift+clic`. Glissez l'un
des éléments sélectionnés pour déplacer le groupe. Un seul `Ctrl+Z` annule le déplacement des
acteurs et des Areas.

Maintenez `Alt` pendant le glisser pour poser des copies au point de chute, ou utilisez `Ctrl+D`
pour les dupliquer avec un décalage fixe. Si la sélection contient une Area et son parent,
la copie de l'Area suit la copie de l'acteur. Un seul `Ctrl+Z` retire les copies des acteurs et des Areas.

### Faire suivre un acteur à une Area

Le sélecteur **Parent** de l'inspecteur (ou le glisser-déposer de l'Area **sur** un acteur dans
l'arbre de scène) attache l'Area à un acteur **posé** de la scène : elle le suit, comme un acteur
enfant. Quelques règles :

- La position se pose en coordonnées **monde** dans l'éditeur : attacher une Area ne la déplace pas.
  C'est le build qui en tire sa position par rapport au parent, et la recompose à chaque frame
  (elle suit la position du parent). L'éditeur montre donc exactement ce
  qu'affiche la première frame du jeu.
- Déplacer le parent au canvas, à la souris ou aux flèches, **entraîne ses Areas** ; une Area n'a pas
  d'enfant, et un acteur ne peut pas avoir une Area pour parent.
- Tant que le parent est **désactivé ou détruit**, l'Area ne touche personne (les acteurs qui la
  touchaient reçoivent `on_area_exit`). Quand il revient, elle reprend.
- Un script ne peut pas déplacer une Area qui a un parent : `area.position = …` est sans effet, sa
  place est recomposée depuis son parent à chaque frame. `area.parent` rend l'acteur suivi, ou `nil`.
- **Supprimer le parent** dans l'éditeur supprime aussi ses Areas, et ses acteurs enfants avec
  les Areas qui les suivent : un seul `Ctrl+Z` rend tout le sous-arbre. Supprimer l'Area seule ne
  touche pas le parent.
- Renommer le parent suit : les Areas qui le suivaient le suivent sous son nouveau nom. Le parent doit
  être dans la même scène ; sinon le build le refuse.
- Collée dans une scène qui n'a pas ce parent, une Area devient libre.

Pour **réutiliser** une Area dans une autre scène, copiez-la (`Ctrl+C`) puis collez-la (`Ctrl+V`)
dans l'autre scène : la copie garde sa position, sa forme et son tag, et reçoit un nom unique dans
la scène d'arrivée.

## 2. Choisir qui la touche

Une Area ne touche que les acteurs dont une boîte porte un tag qui **rencontre** celui de sa forme.
C'est la même matrice que celle des acteurs, dans **Project Settings → Collisions** : le tag d'une
Area (`area` par défaut) y apparaît comme n'importe quel autre. Si le couple est coupé dans la
matrice, l'Area n'appelle jamais ce tag.

Le build détermine quelles boîtes peuvent déclencher un événement, d'après la matrice des tags et
les événements définis dans le script de l'acteur. Le jeu teste ensuite leur recouvrement à chaque
frame.

## 3. Réagir dans le script de l'acteur

Le script de l'acteur qui entre dans la zone reçoit trois événements :

```lua
function on_area_enter(area, my_box)
    if area.name == "Porte" and my_box.tag == "body" then
        scene:switch("Interieur")
    end
end

function on_area_collide(area, my_box)
    -- appelé à partir de la deuxième frame de contact
end

function on_area_exit(area, my_box)
    -- première frame hors de la zone
end
```

- `area` désigne l'Area touchée. `area.name` se compare à un nom local à la scène, par exemple
  `area.name == "Porte"`. Pour un script partagé entre plusieurs scènes, un tag de forme commun
  au projet permet de retrouver le même usage dans chaque scène avec `area.tag`.
- `my_box` désigne la boîte de l'acteur qui touche la zone. Chaque boîte autorisée reçoit ses propres
  événements. Filtrez sur `my_box.tag` si une seule boîte doit déclencher l'action.
- Les événements sont envoyés à l'acteur qui touche l'Area, et au script de l'Area s'il en a un. Un
  acteur **détruit** dans la zone n'apprend aucune sortie ; une Area **désactivée** envoie `on_area_exit`
  aux acteurs encore en jeu.

Un acteur né pendant la partie (`actor:spawn`) reçoit les mêmes événements qu'un acteur posé dans
l'éditeur : il n'y a qu'un seul chemin pour les deux.

## 4. Donner un script à l'Area

La carte **Script** de l'inspecteur attache un script à l'Area, comme pour un acteur. Dans ce script,
`self` désigne **l'Area elle-même** : ses propriétés et ses actions sont celles du tableau de la
section suivante (`self.name`, `self.position`, `self:deactivate()`…). `self` n'est jamais un acteur.

```lua
local passages = 0

function on_start()
    self.size = vec2(32, 16)
end

function on_update()
    if passages >= 3 then
        self:deactivate()                     -- le piège ne sert que trois fois
    end
end

function on_actor_enter(other, other_box)
    if other_box.tag == "body" then
        passages = passages + 1
        other:hide()
    end
end

function on_actor_exit(other, other_box)
    other:show()
end
```

| Événement | Quand |
|---|---|
| `on_start()` | à l'entrée de la scène, même si l'Area est inactive |
| `on_update()` | à chaque frame, après les acteurs, tant que l'Area est active et que son parent est en jeu |
| `on_actor_enter(other, other_box)` | première frame de contact d'un acteur |
| `on_actor_collide(other, other_box)` | chaque frame suivante du contact |
| `on_actor_exit(other, other_box)` | première frame sans contact |

- `other` est l'acteur qui touche l'Area, `other_box` sa boîte en contact (`other_box.tag`).
- Les contacts demandent la case **Trigger**, et suivent la même matrice de tags que ceux des acteurs.
- L'acteur et l'Area sont prévenus par le **même** test : l'acteur d'abord (`on_area_*`), puis l'Area
  (`on_actor_*`). Un acteur que son propre `on_area_enter` détruit n'arrive pas jusqu'au script de
  l'Area.
- Un acteur posé et un acteur créé par `actor:spawn` déclenchent les mêmes événements.
- Un script d'Area est compilé pour **son** Area : le même fichier attaché à deux Areas donne deux
  copies indépendantes, chacune avec ses variables. Un fichier ne peut pas servir à la fois à une Area
  et à un acteur, une scène ou une caméra.

Une Area peut donner une impulsion à un autre acteur de la scène quand le joueur entre dans la zone.
Dans la carte **Script** de chaque Area, choisissez l'acteur dans le champ **Rock**. L'acteur choisi
doit avoir un corps physique. La boîte du joueur doit porter le tag `player` et la matrice de tags
doit autoriser le contact avec la zone.

```lua
exports = {
    Rock = { type = "actor_ref", default = "", label = "Rock" },
}

function on_actor_enter(other, other_box)
    if other_box.tag == "player" and Rock then
        Rock:physics_body():add_velocity(vec2(512, -256))
    end
end
```

Chaque Area peut ainsi viser son propre rocher avec le même script. Si le champ **Rock** est vide ou
si le rocher a été détruit, la condition échoue. L'impulsion ajoute à sa vitesse 2 px par frame vers
la droite et 1 px par frame vers le haut.

## 5. Retrouver une Area depuis n'importe où

Un script (d'acteur ou de scène) obtient une Area par son nom, comme `actor:get` pour un acteur :

```lua
function on_update()
    local porte = area:get("Porte")

    if input:pressed("b") then
        porte:deactivate()                    -- plus personne ne la touche
    end

    if porte:overlaps(self) then              -- test géométrique : ni matrice, ni déclencheur
        self.position = self.position - vec2(1, 0)
    end

    porte.position = vec2(120, 80)            -- la déplacer : prise en compte au prochain test
    porte.size = vec2(48, 32)                 -- l'agrandir : largeur et hauteur, de 0 à 255 pixels
    local zone = porte.bounds                 -- le rectangle monde de sa forme (lecture seule)
end
```

| Pour | Écrivez | Remarque |
|---|---|---|
| obtenir une Area | `area:get("Nom")` | le nom est vérifié au build, dans la scène du script |
| connaître son nom | `area.name` | se compare à une chaîne : `area.name == "Porte"` |
| la désactiver ou la réactiver | `area:deactivate()` / `area:activate()` | `area.active` se lit, il ne s'écrit pas |
| lire ou changer sa place | `area.position` | `area.position = vec2(x, y)` ; sans effet si l'Area a un parent |
| l'acteur qu'elle suit | `area.parent` | lecture seule ; `nil` sans parent ou si le parent est détruit |
| sa taille | `area.size` | `area.size = vec2(w, h)`, bornée de 0 à 255 ; sans forme, elle reste nulle |
| son rectangle | `area.bounds` | lecture seule, vide sans forme |
| savoir si un acteur la recouvre | `area:overlaps(acteur)` | une Area inactive ne recouvre personne |
| son tag | `area.tag` | se compare à un tag du projet |

Renommer une Area dans l'éditeur réécrit aussi les `area:get("…")` et les `area.name == "…"` des
scripts, et l'annulation les remet.

## 6. Faire agir la zone sur la physique

Une Area peut aussi pousser les corps qui la traversent, sans script ni événement. Dans la carte **Physics
effects** de l'inspecteur, cochez l'effet voulu :

- **Gravity override** : dans la zone, les corps qui suivent la gravité de la scène reçoivent cette gravité à
  la place, multipliée par leur échelle de gravité (en pixels par frame au carré). Quand plusieurs zones se
  recouvrent, la dernière de la scène l'emporte.
- **Force field** : une force constante (**Force X / Y**, vent ou courant), une **Turbulence** (une poussée
  aléatoire à chaque frame, la même suite à chaque entrée dans la scène), une **Buoyancy** (la part de gravité
  annulée tant que le centre de la boîte du corps est dans la zone : 1 flotte sans monter ni descendre) et une
  **Drag** (la part de vitesse perdue à chaque frame, la viscosité : 0 est l'air libre).

Règles :

- Seuls les corps **KinematicBody** et **RigidBody** dont la boîte de physique recouvre la zone sont touchés.
  Un **CharacterBody**, conduit par son script, ne l'est que si la zone coche **Affects characters** (la
  gravité de zone, elle, atteint tout corps qui suit la gravité de la scène).
- La force s'ajoute à la vitesse avant la gravité du pas physique, donc avant toute collision : un corps poussé
  est arrêté par un mur comme n'importe quel autre. Elle réveille un RigidBody endormi.
- Un acteur posé et un acteur créé par `actor:spawn` suivent exactement la même règle.
- Une zone inactive, ou sans forme, n'agit pas. Désactivez-la avec `area:deactivate()`.
- Le coût se lit dans le journal de débogage : le compteur `fx=` donne le nombre de couples (zone, corps) testés
  par frame.

## 7. Faire sonner la zone

Une Area peut aussi jouer un son d'ambiance (une cascade, un moteur, le vent dans un couloir) sans script. Dans la carte
**Physics effects**, cochez **Sound emitter** et choisissez un **Sound effect** du projet.

- L'**écouteur** est le centre de la caméra. Le son est à **plein volume** quand il est dans la forme de l'Area, puis
  **décroît linéairement** jusqu'à zéro à la distance **Fall-off** (en pixels) autour de la forme. Au-delà, le son est
  coupé et ne tient plus de canal.
- **Volume** est un pourcentage du volume de l'effet lui-même. **Pan with position** place le son à gauche ou à droite
  selon la position de l'Area par rapport au centre de la caméra.
- Il n'y a pas de boucle d'échantillon : quand l'effet se termine et que l'écouteur est toujours à portée, il **repart à la
  frame suivante** (au plus une frame de silence). Choisissez donc un effet qui se raccorde bien à lui-même.
- Chaque émetteur à portée occupe **un canal** du projet (8 par défaut). Quand tous les canaux sont pris, l'émetteur
  retente à la frame suivante ; le validateur avertit si une scène porte plus d'émetteurs que le projet n'a de canaux.
- Une Area **inactive**, ou dont le parent est désactivé ou détruit, se tait. Elle peut suivre un acteur (son qui accompagne
  un monstre) comme n'importe quelle Area.
- L'émetteur joue des **effets sonores**. Le module Lua `music` pilote la piste musicale.

### Baisser la musique dans une zone

Donnez le tag `musique_calme` à la forme d'une Area avec **Trigger** activé. La matrice de
collision doit autoriser le contact avec le tag `body` du personnage. Dans son script, baissez le
volume quand sa boîte `body` entre dans la zone, puis rétablissez le volume habituel de la piste
à la sortie. Ici, il est de 100 %.

```lua
function on_area_enter(area, my_box)
    if area.tag == "musique_calme" and my_box.tag == "body" then
        music:set_volume(45)
    end
end

function on_area_exit(area, my_box)
    if area.tag == "musique_calme" and my_box.tag == "body" then
        music:set_volume(100)
    end
end
```

La piste continue à jouer pendant le changement de volume.

## Choisir entre une Area et un acteur sensor

Un **acteur** avec une boîte capteur convient à un déclencheur qui a besoin d'un sprite ou d'être
créé pendant le jeu. Une **Area** convient à un volume posé dans la scène qui prévient les acteurs qui
le touchent, réagit par son propre script, modifie la physique ou émet un son.

Une Area suit la scène : elle ne naît pas pendant la partie et ne se détruit pas. Elle ne bouge que
si un script écrit `area.position` (sans parent), ou si son parent bouge.
