# Écrire un script

Vous avez posé une scène, ajouté un acteur, et vous voulez maintenant lui donner un comportement. Un script peut lancer une animation au démarrage, déplacer un acteur selon les touches, jouer un son ou changer de scène.

> Vous découvrez l'éditeur ? Commencez par le [guide utilisateur](user-guide/) pour créer un projet, vous repérer et importer vos premières ressources.

## Avant de commencer

**Vous écrivez avec la syntaxe de Lua, mais votre script est traduit en C puis compilé dans la ROM.** L'éditeur propose donc uniquement les écritures qu'il peut transformer de façon fiable. S'il rencontre une écriture non prise en charge, le Build l'indique avec la ligne concernée et, quand elle existe, une alternative.

Les calculs utilisent des entiers. Il n'y a pas de nombre à virgule dans le jeu, car une émulation flottante coûterait des centaines de cycles par opération. Lorsque vous avez besoin d'une valeur entre deux pixels, gardez une valeur mise à l'échelle :

```lua
self.velocity = vec2(384, 0) -- 384 = 1,5 pixel par frame ; 256 = 1 pixel
self:apply_velocity()
```

`self.position` est exprimée en pixels, tandis que `self.velocity` utilise cette échelle plus précise. Pour vos propres calculs, choisissez aussi une échelle, par exemple 100 pour des pourcentages, et conservez-la jusqu'au dernier calcul.

`self.position` **téléporte** l'acteur : la carte de collision n'est pas consultée, il traverse les murs et n'est pas remonté sur une pente. Pour un déplacement physique (murs, pentes, sol, `on_tile_collide`), donnez une vitesse avec `self.velocity` puis appelez `self:apply_velocity()` : la carte ne résout qu'un acteur dont la vitesse est non nulle.

## Votre premier script

### 1. Créez et attachez le script

Dans le **Scene Manager**, sélectionnez l'acteur auquel vous souhaitez donner un comportement. Dans son inspecteur, ajoutez le composant **Script**, puis créez ou choisissez un fichier Lua. Le Script Editor s'ouvre sur ce fichier. Vous pouvez également ouvrir un script existant par double-clic dans la liste **Scripts** du projet.

Un script attaché à un acteur connaît cet acteur sous le nom `self`. Les exemples peuvent donc écrire `self:play_anim(...)` ou changer `self.position` sans rechercher l'acteur par son nom.

Un script n'a pas de « type » : c'est ce à quoi il est attaché (acteur, prefab, scène ou caméra) qui décide de ce qu'il peut faire. Deux conséquences, refusées au build :

- `self` n'existe que pour un acteur ou un prefab. Dans un script de scène ou de caméra, il n'y a pas d'instance à désigner : utilisez `actor:get("Nom")`. Un behavior n'est attaché à rien non plus : il reçoit son acteur en paramètre, à nommer autrement que `self` (`function M.update(actor)`).
- Un événement n'existe que pour les propriétaires qui le reçoivent. `on_collision_enter` n'a pas de sens pour une caméra ; le Script Editor ne le propose pas, et le build le refuse s'il est écrit.

Un même fichier ne peut donc pas être attaché à des familles différentes (par exemple un acteur et une scène). Faites un script par famille, et mettez le code commun dans un **behavior**.

### 2. Écrivez un événement

L'éditeur appelle certaines fonctions à des moments précis. Les événements disponibles pour le script sélectionné sont affichés dans le panneau **Events** du Script Editor. Les deux plus courants sont :

```lua
function on_start()
    self:play_anim("idle")
end

function on_update()
    if input:held("right") then
        self.position = self.position + vec2(1, 0)
    end
end
```

Ne créez pas un nom d'événement au hasard. Une fonction qui n'est pas proposée dans **Events** ne sera pas appelée.

### 3. Testez tôt

Enregistrez avec `Ctrl+S`, puis utilisez **Build & Run** (`F5`). Le build vérifie les scripts avant de fabriquer la ROM. En cas d'erreur, le panneau de build indique le fichier et la ligne. Corrigez puis relancez le build. Il n'est pas nécessaire d'exporter ou de préparer les fichiers à la main.

## Les briques du quotidien

### Garder une valeur

Une variable déclarée en tête de fichier conserve son contenu d'une frame à l'autre :

```lua
local vitesse = 2

function on_update()
    self.position = self.position + vec2(vitesse, 0)
end
```

Utilisez `global.score` pour une valeur partagée par plusieurs scripts. Les constantes se lisent avec `const.nom`. Un nom seul doit toujours avoir été déclaré ; le Build vous prévient sinon.

### Découper un script

Une fonction privée sert à ranger une action propre à ce script :

```lua
function tirer(degats)
    self:play_anim("tir")
    sfx:play("Laser")
    return degats + 1
end

function on_update()
    if input:pressed("a") then
        local total = tirer(3)
    end
end
```

Elle est déclarée au premier niveau du fichier. `self` est implicite : ne l'ajoutez pas dans les parenthèses. Ses paramètres et sa valeur de retour sont des entiers, les booléens en font partie. Elle peut appeler une autre fonction privée, mais ne peut pas être récursive. Pour partager du code entre plusieurs acteurs, créez un **behavior** puis importez-le avec `require`.

### Lire, modifier, appeler

Un point lit ou modifie une propriété. Deux points appellent une action :

```lua
self.position = vec2(10, 20)
self:play_anim("walk")
sfx:play("Bip")
```

Les noms entre guillemets, comme `"walk"` ou `"Arena"`, désignent le plus souvent une ressource du projet. Pour afficher un texte simple, vous pouvez l'écrire directement :

```lua
text:draw(2, 16, "Bonjour !")
```

Ce raccourci convient à un projet dans une seule langue. Pour un texte à traduire, créez une entrée dans l'écran **Text** et utilisez sa clé, par exemple `text:draw(2, 16, "village_garde_01")`.

Le panneau **API** du Script Editor donne la liste complète des fonctions et propriétés disponibles, avec leurs arguments.

### Réagir aux boutons

`input:pressed("a")` lit un bouton directement. Pour un combo tenu ensemble, déclarez une **action** dans Project Settings → Input → Inputs : des cases à cocher, comme pour un bouton (`dash = right + a`). Le script cite alors le NOM de l'action, exactement comme un bouton :

```lua
if input:pressed("dash") then self:apply_velocity() end
```

`input:held("nom", frames)` répond vrai à partir d'un appui de cette durée (tir chargé). `input:released("nom")` répond vrai au relâchement (saut à hauteur variable). `input:get_axis("horizontal", "vertical")` rend un `vec2` : la croix existe toujours, même sans axe déclaré.

Pour un quart de cercle, un demi-cercle ou un combo à plusieurs pas, déclarez une **séquence** dans Project Settings → Input → Séquences : une barre d'expression accepte `+` pour un accord tenu ensemble, `-` pour le pas suivant (`down - down+right - right`), et `(a|b)` pour l'une ou l'autre touche. Une séquence se lit avec `input:get_sequence("nom")` — jamais `held`/`pressed`/`released`/`buffered`, réservés aux accords simples :

```lua
if input:get_sequence("quarter_circle") then self:play_anim("special") end
```

`input:buffered("nom", frames)` retient un appui quelques frames (tampon de saut) — répondre vrai CONSOMME l'appui, ce qui rend l'ORDRE d'évaluation sensible :

```lua
-- Piège : buffered() s'évalue avant le `and`, donc consomme l'appui même en l'air.
if input:buffered("jump", 6) and self.grounded then saute() end

-- Correct : le court-circuit du `and` n'évalue buffered() qu'au sol.
if self.grounded and input:buffered("jump", 6) then saute() end
```

### Changer d'apparence

Un acteur affiche un seul sprite à la fois, mais il peut porter **plusieurs composants sprite**, chacun avec son `id`. Dans l'inspecteur, cocher « Active » sur l'un décoche l'autre. Depuis un script, `activate_sprite` fait la même chose :

```lua
if self.active_sprite == "normal" and touche_par_un_ennemi then
    self:activate_sprite("blesse")
end
```

Comme `play_anim`, c'est un geste : l'animation repart de son premier état. Les noms d'animation cités ensuite (`self:play_anim("walk")`) s'entendent pour le sprite qui est affiché à cet instant ; un état absent de ce sprite ne fait rien. Toutes les apparences restent chargées en VRAM : chaque sprite supplémentaire occupe ses tuiles.

### Décider et répéter

```lua
if x > 0 then … elseif x < 0 then … else … end
while x > 0 do … end
for i = 1, 10 do … end
for i = 10, 1, -1 do … end
break
return
```

Les tableaux ont une taille fixe, contiennent des entiers et commencent à l'index 1 :

```lua
local degats = {1, 2, 4, 8}
for i = 1, #degats do
    debug:log(degats[i])
end
```

### Gérer plusieurs états à la fois

Un personnage de plateforme peut courir, attaquer et être invincible en même temps. Un seul `enum` ne peut pas le représenter : il ne vaut qu'une étiquette à la fois. Séparez donc l'état en deux familles.

- **Ce qui s'exclut** (au sol, en saut, en chute) s'écrit avec un `enum` exposé, qu'on compare et qu'on affecte par son étiquette.
- **Ce qui se cumule** (attaque, dégâts, invincibilité) s'écrit avec un bit par état dans un seul entier. `|` active un bit, `& ~` l'éteint, `&` le teste.

```lua
exports = {
    locomotion = { type = "enum", default = "IDLE", values = {"IDLE", "RUN", "JUMP", "FALL"} },
}

local FLAG_ATTACKING  = 1    -- bit 0
local FLAG_HURT       = 2    -- bit 1
local FLAG_INVINCIBLE = 4    -- bit 2
local flags = 0

local attack_timer = 0

function has_flag(flag)
    return flags & flag ~= 0
end

function on_update()
    local move_dir = input:get_axis("horizontal")

    -- Exclusif : déduit de la physique à chaque frame.
    if not self.grounded then
        if self.velocity.y < 0 then locomotion = "JUMP" else locomotion = "FALL" end
    elseif move_dir ~= 0 then
        locomotion = "RUN"
    else
        locomotion = "IDLE"
    end

    -- Cumulable : on attaque en courant comme en sautant.
    if not has_flag(FLAG_ATTACKING) and input:pressed("b") then
        flags = flags | FLAG_ATTACKING
        attack_timer = 20
    end
    if attack_timer > 0 then
        attack_timer = attack_timer - 1
        if attack_timer == 0 then flags = flags & ~FLAG_ATTACKING end
    end

    -- L'action prime sur la locomotion pour choisir l'animation.
    if has_flag(FLAG_ATTACKING) then self:play_anim("attack")
    elseif locomotion == "RUN" then self:play_anim("moving")
    elseif locomotion == "IDLE" then self:play_anim("idle")
    else self:play_anim("jumping") end
end

function on_collision_enter(other, my_box, other_box)
    if not has_flag(FLAG_INVINCIBLE) then
        flags = flags | FLAG_HURT | FLAG_INVINCIBLE   -- deux drapeaux d'un coup
    end
end
```

Quelques points à retenir :

- **Un compteur par drapeau temporaire.** Le drapeau tombe quand son compteur atteint `0`. Ici seul `attack_timer` est écrit en entier ; `FLAG_HURT` et `FLAG_INVINCIBLE` suivraient le même schéma avec leurs propres compteurs.
- **Les drapeaux sont des entiers de 32 bits** : un seul entier en porte jusqu'à 32. Une globale `u8` n'en garde que 8, une `u16` que 16.
- **L'`enum` se compare par son étiquette** (`locomotion == "RUN"`) ; le build refuse une étiquette absente de `values`.
- **Il n'y a pas de `switch`.** Pour choisir entre plusieurs valeurs, écrivez `if … elseif … else`. Le `else` joue le rôle d'un cas par défaut.

Les opérateurs bit à bit sont détaillés dans la [référence](scripting-reference.md#le-langage).

## Construire une action dans le temps

### Le temps se compte en frames

Le moteur appelle vos handlers **une fois par frame**, environ 60 fois par seconde, et il n'y a pas de `dt` : une vitesse s'exprime par frame (`256` sous-pixels valent 1 pixel par frame) et une durée en nombre de frames (`wait(30)` attend une demi-seconde). `scene.frame` compte ces frames depuis le début de la scène.

Si le travail d'une frame dure plus de 16,7 ms, le jeu **ralentit par paliers** au lieu de sauter ou de rattraper : un tour qui dure entre 1 et 2 images fait avancer le jeu à 30 frames par seconde, entre 2 et 3 images à 20 par seconde. `scene.frame`, `wait(n)` et tous vos compteurs ralentissent avec lui ; l'affichage continue de se rafraîchir. Cela a été mesuré dans mGBA, dont le BIOS est émulé (`tools/frame_overrun_probe`). Pour vérifier le budget de votre jeu, cochez le build debug : chaque frame écrit `frame us=N` dans le journal de mGBA, et `N` doit rester sous **16 743**.

Un handler rend la main à chaque frame. Une **séquence** permet d'écrire une action qui attend, en restant lisible :

```lua
function on_sequence_intro()
    self:move_to(vec2(120, 80), 60)
    wait_until(self.position.x >= 120)
    wait(30)
    interface:get("bulle"):draw("garde_01")
    scene:switch("Arena")
end

function on_start()
    sequence:start("intro")
end
```

Une séquence se nomme `on_sequence_<nom>` et se pilote avec `sequence.start`, `sequence.stop` et `sequence.running`. Elle se termine seule à sa dernière ligne.

Écrivez `wait` ou `wait_until` seuls sur leur ligne, au premier niveau de la séquence ou dans une boucle `for` bornée. `wait_until` relit sa condition à chaque frame. Évitez de le placer dans un `if` ou un `while`.

## Texte, menus et langue

`text:draw(2, 16, "Bonjour !")` affiche un texte écrit directement dans le script. Au Build, ce littéral devient une entrée interne. C'est pratique pour un projet dans une seule langue.

Pour un texte à traduire, ou qui contient une valeur, créez une entrée dans l'écran **Text**, puis affichez-la par sa clé. Utilisez un marqueur dans l'entrée, comme `Score : $score`, puis écrivez `global.score = 12` dans le script.

Une **Liste** de l'interface gère déjà sa navigation. Le script lit l'élément choisi avec `interface:get("Menu").index`. Écrivez `menu.count` seulement lorsqu'une liste défilante contient plus d'éléments que de rangées visibles.

`lang:set(code)` change la langue active et recharge la scène courante. Conservez le choix dans une variable globale persistante si vous souhaitez le retrouver après l'extinction.

## Quand le Build signale un problème

Le panneau de build affiche chaque erreur avec le fichier et la ligne quand elle est connue :

```text
[error] Ball.lua, ligne 12 : `repeat … until` n'existe pas. Utilisez `while`.
```

Une **erreur** arrête le build. Un **avertissement** le laisse continuer, mais signale un résultat probablement inattendu, par exemple un son inexistant ou une valeur hors de sa plage. La [référence de scripting](scripting-reference.md) détaille les écritures disponibles et leurs équivalents.

## Pourquoi ces limites, plutôt qu'un « vrai » Lua ?

Embarquer un interpréteur coûterait la mémoire et le temps processeur qui font la différence entre un jeu fluide et un jeu qui rame sur du matériel de 2001 : 16,8 MHz, 32 Ko de mémoire rapide et aucune unité de calcul flottant.

| La limite | Ce qu'elle apporte |
| --- | --- |
| Pas de table, de closure ou de coroutine | Aucune allocation à l'exécution. La mémoire est décidée au build, donc mesurable. |
| Que des entiers | Aucune émulation flottante. |
| Taille des tableaux connue au build | Pas de vérification de bornes à l'exécution. |
| Noms résolus au build | `sfx:play("Bip")` devient un index, pas une recherche par chaîne. |

Les possibilités du langage évoluent à partir de besoins concrets. Si une écriture utile vous manque, signalez-la : elle pourra être étudiée sans vous laisser deviner si elle est prévue ou non.
