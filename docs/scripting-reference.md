# Référence de scripting

Cette référence complète le [guide de scripting](scripting.md). Utilisez-la lorsque vous voulez vérifier une écriture, plutôt que de la lire avant votre premier script.

## Ce que le langage accepte

Un script contient des variables, des événements proposés dans le panneau **Events**, des séquences `on_sequence_<nom>` et des fonctions privées déclarées au premier niveau.

| Valeur | Écriture | Notes |
| --- | --- | --- |
| Entier | `12`, `-3` | Seul type numérique. `7 / 2` vaut `3`. |
| Booléen | `true`, `false` | Utilisable comme 1 ou 0. |
| `nil` | `nil` | Vaut 0. |
| Vecteur | `vec2(x, y)`, `vec3(x, y, z)` | `+`, `-`, multiplication par un entier. |
| Rectangle | `rect(x, y, w, h)` | Pour les bornes et zones. |
| Tableau | `{1, 2, 4}` ou `array(20, 12)` | Taille fixe, entiers, indexation à partir de 1. |
| Chaîne | `"walk"`, `"Arena"` | Nom d'une ressource. Un littéral est aussi accepté par `text.draw`. |

```lua
+  -  *  /  %              -- arithmétique entière
== ~= < <= > >=           -- comparaison
and or not                -- logique
#t                         -- taille d'un tableau, connue au build
```

Les boucles disponibles sont `while` et `for`. Un `for` accepte un début, une fin et un pas écrit en clair. `break` et `return` sont disponibles.

## Fonctions et appels

Une fonction privée prend et rend des entiers. `self` est fourni automatiquement dans un script d'acteur. Elle ne peut pas être récursive, directement ou indirectement, ni être placée dans une variable.

```lua
function degats_critiques(degats)
    return degats * 2
end
```

Une propriété s'écrit avec un point, une méthode avec deux points :

```lua
self.position = vec2(8, 8)
self:destroy()
sfx:play("Bip")
```

Certains appels renvoient une référence à un élément matériel. Une référence vaut `0` si aucun slot n'est libre ; une référence devenue périmée ne fait rien.

```lua
local pas = sfx:play("Pas")
if pas:playing() then pas:stop() end
```

`actor:get("nom")` rend un acteur de la scène par son nom. **Un acteur appartient à sa scène** : le nom est local à la scène, donc « Cursor » peut exister dans autant de scènes qu'on veut, et `actor:get("Cursor")` vise toujours le Cursor de la scène en cours. La référence **peut valoir `nil`** — l'acteur a été détruit (`self:destroy()`), ou il n'existe pas dans cette scène — donc on la teste avant d'en appeler une méthode :

```lua
local cible = actor:get("Boss")
if cible ~= nil then
    cible:move_to(vec2(120, 80), 2)
end
```

On peut aussi adresser un acteur **par son index**, à partir de 1 (comme `data.Table[1]`), dans l'ordre où il est posé dans la scène. `actor:count()` donne le nombre d'acteurs posés — la borne de la boucle :

```lua
for i = 1, actor:count() do
    local a = actor:get(i)
    if a ~= nil then a:play_anim("idle") end
end
```

C'est ce qui remplace une cascade `if sel == 1 then actor:get("Unit1") elseif …` : `actor:get(sel)` suffit.

Le catalogue **Gameplay**, **Scripting** et **Hardware** du panneau **API** est la référence des fonctions du moteur. Il est tenu à jour par l'éditeur.

## Variables exposées (`exports`)

Une table `exports` déclarée au premier niveau expose des variables **réglables par instance** depuis l'inspecteur. Chaque acteur posé du même script garde sa propre valeur — un seul `Patrol.lua` sur trois gardes, chacun sa vitesse, au lieu de trois scripts jumeaux.

```lua
exports = {
    speed = { type = "int",  default = 5 },
    angry = { type = "bool", default = false },
    team  = { type = "enum", default = "RED", values = {"RED", "BLUE"} },
}

function on_update()
    self.position = self.position + vec2(speed, 0)   -- on la LIT comme une variable
    if angry then speed = speed + 1 end              -- et on peut la RÉÉCRIRE
end
```

- **On l'utilise par son nom nu**, comme n'importe quelle variable : la lire, la réassigner. Sa seule particularité est que sa valeur de départ vient de l'inspecteur, pas du script.
- **La valeur réglée sur l'instance** l'emporte sur le `default` ; sans réglage, c'est le `default`.
- **Tous les types sont réglables par instance**, avec la valeur portée jusqu'au jeu :
  - `int`, `float`, `bool`, `enum` — entiers au runtime (`float` est tronqué, un `enum` vaut l'index de son étiquette).
  - `string` — le texte devient une **entrée de la table de textes** (comme un littéral passé à `text.draw`) : traduisible, et un simple index au runtime. On l'utilise donc là où un texte est attendu (`text:draw(label)`).
  - `actor_ref`, `scene_ref`, `sfx_ref` — une **référence** par son nom. Un `actor_ref` désigne un acteur **de la scène** de l'instance ; vide = aucune référence.
  - `vec2`, `vec3`, `rect` — des **valeurs composées** (`{x, y}`, `{x, y, w, h}`), lisibles champ par champ (`home.x`).
- **Le nom d'un export ne peut pas être** celui d'un champ d'acteur (`position`, `velocity`…), d'une variable globale, ni d'un mot de l'API (`input`, `wait`…) — le build le refuse.
- **Une variable seulement LUE ne coûte rien** (acteur posé) : le build la fond dans le code. Seule une variable réécrite occupe de la mémoire. Régler `speed` sur dix gardes qui ne font que la lire n'ajoute aucun octet.

### Régler un prefab au spawn

Une instance créée au runtime avec `actor.spawn` n'a pas de fiche éditeur : ses exports se règlent **au moment du spawn**, par une table facultative en 3ᵉ argument.

```lua
local b = actor:spawn("Bullet", vec2(116, 76), { speed = 8, team = "RED" })
```

- **Les clés absentes gardent la valeur réglée sur le prefab** (dans l'éditeur), sinon le `default` du script.
- La table s'écrit **en début de ligne** ou dans un `local x = actor:spawn(...)` — pas au milieu d'une expression.
- Ses clés doivent être des exports du prefab. Les valeurs suivent le type : un littéral pour un scalaire (`speed = 8`), un nom entre guillemets pour une référence ou une string (`boom = "Pop"`, `tgt = "Enemy"`), un constructeur pour un composite (`vel = vec2(1, 2)`). Sur un prefab poolé, chaque instance garde sa propre valeur.

## Séquences

Une séquence est une fonction `on_sequence_<nom>`. Elle attend avec `wait(frames)` ou `wait_until(condition)`, et avance dans l'ordre de ses lignes.

- Elle s'arrête seule à la dernière ligne.
- Ses variables locales survivent à une attente.
- `wait_until` réévalue son expression à chaque frame.
- Une attente est seule sur sa ligne, au premier niveau de la séquence ou dans un `for` borné.
- Une condition qui ne peut jamais devenir vraie est refusée au Build.

Chaque attente ajoute une frame au déroulement de la séquence.

## Texte, listes et langue

`text.draw` accepte un littéral pour afficher rapidement un texte dans un projet monolingue :

```lua
text:draw(2, 2, "Bonjour !")
```

Au Build, ce littéral devient une entrée interne de la table de textes. Il n'est pas visible dans l'écran **Text** et ne peut donc pas être traduit. Dès qu'une langue est déclarée dans le projet, le Build le signale par un avertissement.

Pour un texte traduisible ou qui contient une valeur, créez une entrée dans l'écran **Text**. Une clé, telle que `"dialogue_garde_01"`, est passée à `text.draw` ou à `draw` sur une zone de texte (`interface:get("bulle"):draw("dialogue_garde_01")`). Pour afficher une valeur, utilisez un marqueur de valeur dans l'entrée de texte, plutôt qu'une concaténation :

```text
Score : $score_joueur
```

```lua
global.score_joueur = 12
text:draw(2, 2, "score")
```

### Balisage dans l'écran Text

Les textes créés dans l'écran **Text** peuvent contenir des balises. Elles ne
s'affichent pas telles quelles : elles règlent le rendu du fragment concerné.
Par exemple, une police de titre peut être utilisée au milieu d'une phrase :

```text
Vous recevez [font=Titre]Niveau suivant[/font] !
```

`Titre` doit être le nom d'une police du projet. La balise est toujours
fermée : elle ne change pas la police du texte qui suit. La police de la zone
reste responsable de l'interligne ; `[font=…]` change les glyphes et leur
largeur, pas l'espacement vertical. La barre de balisage de l'écran **Text**
propose les polices connues et entoure la sélection.

Les mêmes textes acceptent aussi `[speed=n]`, `[pause=n]`, `[wave]…[/wave]`,
`[shake]…[/shake]`, `[color=n]…[/color]`, `[icon=nom]` et `$valeur`.

Une liste se pilote par ses propriétés : `menu.index`, `menu.first`, `menu.count`, et sa méthode `menu:row(n)` qui rend la zone de texte d'une rangée (`local menu = interface:get("Menu")`). Une liste fixe gère sa navigation sans script supplémentaire. `menu.count` s'écrit pour les listes défilantes. `menu:activate()` et `menu:deactivate()` lui donnent ou lui retirent la croix directionnelle.

`interface:get("Nom")` rend une référence du **type réel** de l'élément — liste, image, zone de texte, ou conteneur. Le cycle de vie (`:show()`, `:hide()`, `.visible`) est commun ; le reste appartient au type : `heart.state = "vide"` et `cursor.offset = vec2(0, 16)` pour une image, `box:draw("clé")` et `box.reading` pour une zone de texte.

`lang:get()` rend la langue active. `lang:set(code)` la modifie et recharge la scène courante. Pour mémoriser ce choix, conservez la valeur dans une globale persistante puis utilisez `save.write`.

## Écritures refusées

Le Build refuse les éléments suivants :

| Vous écrivez | À la place |
| --- | --- |
| `for k, v in pairs(t) do … end` | `for i = 1, #t do … end` |
| `repeat … until c` | `while true do … if c then break end end` |
| `goto etiquette` ou `::etiquette::` | `break`, `return` ou un `if` |
| `do … end` | Écrivez son contenu directement. |
| `local function f()` | `function f()` au premier niveau |
| Une fonction dans un handler | Déclarez-la au premier niveau. |
| `local f = function() … end` | Une fonction n'est pas une valeur. |
| `...` | Les arguments variables n'existent pas. |
| `a .. b` | Une entrée de texte et ses marqueurs de valeur. |
| `a ^ b` | Multipliez explicitement, par exemple `x * x`. |
| `a // b` | `/` effectue déjà une division entière. |
| `a & b`, `a | b`, `a << b` | Utilisez l'API matérielle ou des multiplications et divisions. |

`~=` signifie bien « différent de ». Seul `~`, utilisé pour une opération binaire ou unaire, n'est pas disponible.

## Bibliothèque standard Lua

La bibliothèque standard de Lua n'est pas embarquée dans la ROM. Les cas usuels ont les équivalents suivants :

| Vous cherchez à faire | Utilisez |
| --- | --- |
| Formater ou assembler du texte | L'écran **Text** et les marqueurs de valeur. |
| Ajouter à une collection dynamique | Un tableau de taille fixe et un compteur. |
| Parcourir un tableau | `for i = 1, #t do`. |
| Lire l'heure | `scene.frame` pour compter les frames. |
| Ouvrir un fichier | `save.write` et `save.read` pour la SRAM. |
| Afficher une trace | `debug:log(...)`, visible dans mGBA et retiré des builds release. |
| Gérer une erreur ou une exception | Un `if` qui contrôle et corrige la valeur. |
| Charger un behavior | `require("behaviors/nom")`, résolu au build. |

Il n'y a pas de `string`, `table`, `os`, `io`, `coroutine`, `utf8`, métatable, fonction de réflexion ni chargement de code à l'exécution.

Pour rechercher une forme Lua précise dans une erreur, voici les appels refusés les plus courants :

| Catégorie | Écritures concernées |
| --- | --- |
| Console et erreurs | `print(x)`, `assert(c)`, `error(msg)`, `pcall(f)`, `xpcall(f, h)` |
| Collections Lua | `pairs(t)`, `ipairs(t)`, `next(t)`, `table.insert(t, v)`, `unpack(t)`, `select(n, ...)` |
| Chaînes et types | `string.format(…)`, `tostring(x)`, `tonumber(s)`, `type(x)`, `utf8.char(…)` |
| Métatables | `setmetatable(t, mt)`, `getmetatable(t)`, `rawget(t, k)`, `rawset(t, k, v)`, `rawequal(a, b)`, `rawlen(t)` |
| Fichiers et code | `os.time()`, `io.open(…)`, `package.path`, `dofile(chemin)`, `load(src)`, `loadfile(chemin)`, `loadstring(src)`, `collectgarbage()` |
| Coroutines | `coroutine.create(f)` |

Une fonction écrite `function f() … end, dans un corps` ou `function objet:methode() … end` est également refusée. Déclarez une fonction privée au premier niveau. `local function f() … end` n'est pas une forme disponible.

## Le module `math`

`math` est le module du moteur, en entiers. Il expose exactement :

```text
abs   atan2   clamp   cos   ease   lerp   max   min   rand   sign   sin   sqrt
```

- `math.sin` et `math.cos` reçoivent des degrés, pas des radians.
- Le hasard s'écrit `math.rand(min, max)`.
- Il n'y a pas d'arrondi. Les valeurs sont déjà entières.

| Vous écrivez | À la place |
| --- | --- |
| `math.floor(x)` | Rien : `/` tronque déjà. |
| `math.ceil(a / b)` | `(a + b - 1) / b` pour une division positive arrondie au-dessus. |
| `math.random(a, b)` | `math.rand(a, b)` |
| `math.pi` | Des angles en degrés. |
| `math.pow(x, n)` | Une multiplication explicite, par exemple `x * x`. |
| `math.fmod(a, b)` | `a % b` |

Les autres noms de Lua qui ne sont pas proposés sont `math.ceil(x)`, `math.huge`, `math.modf(x)` et `math.randomseed(n)`.

Les décalages et opérations binaires `a >> b`, `a ~ b` et `~a` ne sont pas disponibles non plus.

## Comprendre les erreurs

Une erreur arrête le Build : le code produit ne serait pas valable. Un avertissement laisse le Build continuer, mais indique une situation probablement involontaire. Les diagnostics indiquent le fichier et la ligne lorsqu'ils sont disponibles.
