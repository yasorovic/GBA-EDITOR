# Zones de jeu (Area)

Ce guide pose une **Area** : une zone de jeu sans sprite, qui prévient le script d'un acteur quand
celui-ci y entre, y reste ou en sort. Elle sert à une porte, un piège, une sortie de niveau ou un
déclencheur de cinématique.

Une Area est un volume pur : pas de sprite, pas d'OAM, pas de script à elle, et aucune place dans le
pool d'acteurs. Elle porte une **forme** de collision (un rectangle) et, si elle doit prévenir des
scripts, un **déclencheur**. Ce sont les **acteurs** qui reçoivent les événements : l'Area, elle, ne
réagit à rien.

**Ce qu'il vous faut :** une scène avec un acteur qui se déplace et qui porte une boîte **Collision**
et un script (voir [Déplacer un acteur](../acteurs/deplacer-acteur.md)).

## 1. Poser une Area

Dans le canvas, ouvrez le menu du bouton **+** de la barre d'outils flottante et choisissez
**Add area**, puis cliquez dans la scène : une zone de 32×32 pixels, centrée sur le clic, est créée.
Le bouton **+** de l'arbre de scène propose aussi **Area**.

Sélectionnez l'Area pour régler dans l'inspecteur :

- **Active on start** : l'Area touche-t-elle quelqu'un dès l'entrée dans la scène ?
- **Trigger** : l'Area prévient-elle les scripts ? Une Area neuve est un déclencheur. Sans cette case,
  elle ne teste aucun contact.
- **Position**, puis la carte **Shape** : le **Tag** de la forme, son décalage (**Offset**) et sa
  taille (**Size**). La taille se règle aussi à la souris, avec les poignées d'une Area sélectionnée.

Le nom se change dans l'en-tête de l'inspecteur, comme pour un acteur. Il est **local à la scène** :
deux scènes peuvent chacune avoir une Area `Porte`.

### Faire suivre un acteur à une Area

Le sélecteur **Parent** de l'inspecteur (ou le glisser-déposer de l'Area **sur** un acteur dans
l'arbre de scène) attache l'Area à un acteur **posé** de la scène : elle le suit, comme un acteur
enfant. Quelques règles :

- La position se pose en coordonnées **monde** dans l'éditeur : attacher une Area ne la déplace pas.
  C'est le build qui en tire sa position par rapport au parent, et la recompose à chaque frame
  (position, rotation et échelle du parent comprises). L'éditeur montre donc exactement ce
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

Les contacts sont calculés **au build** : un acteur dont aucun tag ne rencontre celui de l'Area, ou
dont le script ne répond à aucun événement d'Area, n'est jamais testé.

## 3. Réagir dans le script de l'acteur

Le script de l'acteur qui entre dans la zone reçoit trois événements :

```lua
function on_area_enter(area, my_box)
    if area.name == "Porte" and my_box.tag == "body" then
        scene:switch("Interieur")
    end
end

function on_area_collide(area, my_box)
    -- appelé à chaque frame passée dans la zone
end

function on_area_exit(area, my_box)
    -- première frame hors de la zone
end
```

- `area` est une **référence** vers l'Area touchée ; `area.name` se compare à son nom
  (`area.name == "Porte"`), `area.tag` au tag de sa forme.
- `my_box` est la boîte de l'acteur qui est en contact, comme pour `on_collision_enter`.
- Les événements ne sont envoyés qu'à l'acteur qui touche l'Area. Un acteur **détruit** dans la zone
  n'apprend aucune sortie ; une Area **désactivée** envoie `on_area_exit` aux acteurs encore en jeu.

Un acteur né pendant la partie (`actor:spawn`) reçoit les mêmes événements qu'un acteur posé dans
l'éditeur : il n'y a qu'un seul chemin pour les deux.

## 4. Retrouver une Area depuis n'importe où

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

## 5. Faire agir la zone sur la physique

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

## 6. Faire sonner la zone

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
- Seuls les **effets** sonores sont possibles : la musique n'a qu'une couche et reste pilotée par `music`.

## Choisir entre une Area et un acteur sensor

Un **acteur** dont la boîte est vide fait déjà office de déclencheur : il reste le bon choix s'il
**bouge**, s'il a un sprite, ou s'il porte son propre script. Une **Area** est plus légère (aucune
place dans le pool, aucun sprite, aucun script) : elle convient à tout ce qui est **fixe** et qui
ne sert qu'à prévenir les acteurs qui la touchent.

Une Area suit la scène : elle ne naît pas pendant la partie et ne se détruit pas. Elle ne bouge que
si un script écrit `area.position` (sans parent), ou si son parent bouge.
