# Santé et dégâts

Ce guide donne des points de vie à un acteur, rend les coups lisibles, affiche une barre de vie et
distingue un coup précis (frapper la tête) d'un simple contact.

**Ce qu'il vous faut :** une scène avec un acteur `Cible` (sprite, boîte **Collision**, script). Les
dégâts sont déclenchés ici par un appui sur `B` pour tester ; remplacez-le ensuite par le contact
d'une attaque.

## 1. Des points de vie

Exposez la vie maximale, gardez la vie courante en variable locale, et préparez une fonction de
dégâts :

```lua
exports = {
    vie_max = { type = "int", default = 20, label = "Vie maximale", min = 1, max = 999 },
}

local vie

function on_start()
    vie = vie_max
end

function subir_degats(degats)
    vie = math.max(0, vie - degats)
    if vie == 0 then
        self:destroy()
    end
end

function on_update()
    if input:pressed("b") then
        subir_degats(1)
    end
end
```

`vie_max` se règle pour chaque acteur dans l'inspecteur ; `vie` est un état temporaire. Quand vous
ajouterez une vraie attaque, appelez `subir_degats(1)` au moment de son impact.

## 2. Un coup que l'on sent

Rendre le contact lisible demande peu : une courte invincibilité, un clignotement et une secousse.
Ces effets évitent aussi que plusieurs dégâts s'enchaînent d'une seule collision.

```lua
local invincible = 0
local temps_degats = 0

function on_update()
    if invincible > 0 then
        invincible = invincible - 1
        temps_degats = temps_degats + 1
        self:blink(temps_degats, 30, 3)
        self:shake(temps_degats, 8, 3)
    else
        temps_degats = 0
    end
end

function on_collision_enter(other, my_box, other_box)
    if other.name == "Ennemi" and invincible == 0 then
        invincible = 30
        subir_degats(1)
    end
end
```

`blink` et `shake` prennent un temps écoulé `t`, une durée et un paramètre propre à l'effet. Même
sans compteur de vie visible, le joueur comprend qu'il a subi un choc. Vous pourrez ajouter un recul
et un son sans changer la détection.

## 3. Une barre de vie

Ajoutez une **Interface** à la scène, puis une **Image** nommée `Remplissage` placée en haut de
l'écran. Préparez cinq états dans l'image, de `vie_0` (vide) à `vie_4` (pleine), puis choisissez
l'état selon la vie restante :

```lua
function on_update()
    local remplissage = interface:get("Remplissage")
    local etat = vie * 4 / vie_max
    if etat == 0 then
        remplissage.state = "vie_0"
    elseif etat == 1 then
        remplissage.state = "vie_1"
    elseif etat == 2 then
        remplissage.state = "vie_2"
    elseif etat == 3 then
        remplissage.state = "vie_3"
    else
        remplissage.state = "vie_4"
    end
end
```

Le calcul utilise des entiers : `vie * 4 / vie_max` donne cinq paliers lisibles sans coût inutile.
Les paliers se lisent dans le même `on_update` que le reste du script : fusionnez-les avec
l'entrée `B` et le clignotement des sections précédentes.

## 4. Frapper un point précis

Pour distinguer « le joueur saute sur la tête » d'un contact ordinaire, donnez à chaque acteur une
petite boîte **Trigger** : `pieds` sous les pieds du joueur et `tete` sur la tête de l'ennemi.
Les tags doivent exister dans **Project Settings → Collisions**. Dans `on_collision_enter`,
`my_box` et `other_box` sont les deux boîtes en contact, et leur `.tag` se compare par nom.

Chaque couple de tags en contact est un événement à part : si les pieds touchent la tête avant que
les corps se touchent, `on_collision_enter` est appelé d'abord pour `pieds`/`tete`, puis une seconde
fois quand les corps entrent à leur tour. Deux boîtes de même tag chez un acteur ne comptent que
pour un seul contact.

Dans le script de l'ennemi :

```lua
function on_collision_enter(other, my_box, other_box)
    if other.name == "Joueur" and my_box.tag == "tete" and other_box.tag == "pieds" then
        sequence:start("mort")
    end
end

function on_sequence_mort()
    for t = 0, 7 do
        self:squash(t, 8, 30)
        wait(1)
    end
    self:destroy()
end
```

Une **séquence** (`on_sequence_<nom>`) avance ligne par ligne et attend avec `wait(frames)` : ici,
l'ennemi s'écrase pendant huit frames puis disparaît. Gardez la boîte solide principale pour empêcher
le joueur de traverser l'ennemi : les petites boîtes Trigger servent seulement à reconnaître
l'action précise.
