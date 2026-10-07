# Ennemis et PNJ

Ce guide reprend après [Ajouter des collectibles et un score](collectibles.md). Il commence avec un personnage non-joueur (PNJ) et ses dialogues, puis fait évoluer le même niveau vers des ennemis mobiles, des projectiles et des contacts plus expressifs.

## 1. Créer un PNJ et sa zone de dialogue

Ajoutez un acteur avec le sprite du PNJ, puis une boîte **Collision** en mode **Trigger**. Nommez l'acteur `Villageois`. Ajoutez aussi une **Interface** à la scène avec un élément **Texte** nommé `Dialogue`. Cette zone est l'endroit où les répliques seront affichées. Sa position, sa taille, sa police et son habillage sont réglés visuellement dans l'éditeur, pas dans le script.

## 2. Écrire et organiser les dialogues

Ouvrez l'écran **Text** et créez les entrées suivantes. La clé sert au script ; le contenu est ce que le joueur lit.

| Clé | Texte français |
| --- | --- |
| `villageois_bonjour` | Bonjour, voyageur ! [pause=20] La forêt est dangereuse. |
| `villageois_apres_bonjour` | Tu es déjà prêt à partir ? |

Le marqueur `[pause=20]` crée une courte pause pendant l'affichage. Vous pouvez aussi utiliser `[speed=4]` en tête d'un texte pour le faire apparaître comme une machine à écrire. Préfixer les clés par `villageois_` les garde regroupées quand le projet contient beaucoup de dialogues.

## 3. Écrire le premier script d'état

Un **état** est une variable qui décrit où en est un acteur. Ici, `rencontre` vaut `0` avant la première discussion, puis `1` après. Le script choisit ainsi une réplique sans dupliquer les conditions :

```lua
local rencontre = 0

function on_collision_enter(other, my_box, other_box)
    if other.name ~= "Joueur" then
        return
    end

    if rencontre == 0 then
        interface:get("Dialogue"):draw("villageois_bonjour")
        rencontre = 1
    else
        interface:get("Dialogue"):draw("villageois_apres_bonjour")
    end
end
```

Pour ajouter une troisième étape, créez une clé telle que `villageois_quete`, ajoutez `elseif rencontre == 1 then`, puis passez `rencontre` à `2`. Gardez les noms de clés et les conditions dans le même ordre : c'est la forme la plus simple d'un arbre de dialogue.

Cette variable est remise à zéro quand la scène est rechargée. Si le PNJ doit se souvenir de la rencontre après un changement de scène, créez une globale, par exemple `global.villageois_rencontre`, et remplacez `rencontre` par cette globale. Cochez **Persist** uniquement pour conserver cet état après avoir éteint la console.

## 4. Introduire la traduction

Dans les réglages du projet, ajoutez une langue, par exemple l'anglais. L'écran **Text** affiche alors une colonne par langue : conservez les clés `villageois_bonjour` et `villageois_apres_bonjour`, puis écrivez leur traduction dans la colonne correspondante.

Le script ne change pas : il demande toujours `"villageois_bonjour"`. C'est l'éditeur qui choisit la version de la langue active. Les clés décrivent donc l'intention (`villageois_bonjour`), jamais le texte français lui-même.

## 5. Transformer un acteur en ennemi

Ajoutez un nouvel acteur avec un sprite et une boîte **Collision** en mode **Solid**, puis utilisez **Expose to Prefab** pour le nommer `Ennemi`. Les réglages exposés permettent à chaque instance de patrouiller à sa propre vitesse :

```lua
exports = {
    vitesse = { type = "int", default = 1, label = "Vitesse", min = 0, max = 4 },
    sens = { type = "int", default = 1, label = "Sens", min = -1, max = 1 },
}

function on_update()
    self.velocity = vec2(sens * vitesse * 256, 0)
    self:apply_velocity()
end

function on_tile_collide(normal_x, normal_y)
    if normal_x ~= 0 then
        sens = -sens
    end
end
```

Le déplacement passe par `self.velocity` (en 256ᵉ de pixel, d'où le `* 256`) puis `apply_velocity()`, comme le joueur. C'est la vitesse que la carte de collision lit pour détecter un mur : écrire `self.position` téléporte l'acteur et la carte ne voit aucun mouvement, l'ennemi traverse donc les murs. Cette même vitesse pilote l'**auto-direction** : l'ennemi se tourne seul vers son sens de marche, à condition que le sprite dessine les deux sens (par exemple une direction est et une direction ouest en miroir). Ne retournez donc pas le sprite à la main avec `self.flip_h` : le retournement s'ajouterait à celui de la direction ouest et l'ennemi regarderait du mauvais côté. Un sprite qui ne dessine qu'un sens reste la seule exception, et peut être retourné avec `self.flip_h = sens < 0` dans `on_tile_collide`.

Ajoutez plusieurs instances du prefab dans des couloirs fermés. Elles patrouillent indépendamment, tandis que le sprite et la logique restent partagés par le prefab.

## 6. Faire tirer un projectile

Créez un prefab `Projectile` avec un sprite, une boîte **Collision** en mode **Trigger** et ce script :

```lua
function on_update()
    self.position = self.position + vec2(2, 0)
    if self.position.x > scene.size.w then
        self:destroy()
    end
end
```

Dans l'inspecteur de `Niveau1`, réservez des instances de `Projectile` dans le pool de prefabs. Sans ce pool, `actor.spawn` ne peut pas créer de projectile pendant le jeu. L'ennemi peut alors en lancer un régulièrement :

```lua
function on_update()
    self.velocity = vec2(sens * vitesse * 256, 0)
    self:apply_velocity()

    if scene.frame % 90 == 0 then
        actor:spawn("Projectile", self.position)
    end
end
```

Cette première version tire vers la droite. Un projectile qui doit suivre le sens de chaque ennemi est une bonne évolution : ajoutez-lui un réglage de direction ou créez deux prefabs, un par sens.

## 7. Recevoir un dégât avec du ressenti

Le joueur n'a pas encore besoin d'une barre de vie. Commencez par rendre le contact lisible : créez une courte invincibilité, faites clignoter le sprite et empêchez le déclenchement de plusieurs dégâts d'affilée.

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

    -- Gardez ici le mouvement et la gravité du guide précédent.
end

function on_collision_enter(other, my_box, other_box)
    if other.name == "Ennemi" and invincible == 0 then
        invincible = 30
    end
end
```

Le clignotement et la secousse sont une première dose de *juiciness* : même sans compteur de vie, le joueur comprend immédiatement qu'il a subi un choc. Vous pourrez ensuite ajouter un recul, un son et des points de vie sans changer la détection.

## 8. Éliminer un ennemi en lui sautant dessus

Donnez au joueur une petite boîte Trigger sous ses pieds, avec le tag `pieds`. Donnez à l'ennemi une petite boîte Trigger sur sa tête, avec le tag `tete`. Dans un script, `my_box` et `other_box` sont les deux boîtes en contact, et leur `.tag` se compare par le nom du tag.

Chaque couple de tags en contact est un événement à part : si les pieds du joueur touchent l'ennemi avant son corps, `on_collision_enter` est appelé une première fois pour `pieds`/`tete`, puis une seconde fois quand le corps entre à son tour. Deux boîtes de même tag chez un acteur ne comptent que pour un seul contact.

Dans le script de l'ennemi, distinguez ce contact du contact avec son corps :

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

Conservez la boîte solide principale pour empêcher le joueur de traverser l'ennemi. Les petites boîtes Trigger servent à reconnaître l'action précise : pieds contre tête, plutôt qu'un simple contact.

## Continuer

Vous pouvez maintenant relier ce niveau à un écran de victoire ou de défaite dans [Construire une boucle de gameplay](gameplay-loop.md).
