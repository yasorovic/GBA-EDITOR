# Scripting : la chaîne Lua → C

Comment un script Lua devient du C : catalogue d'API, grammaire, domaines, séquences, état des prefabs poolés. Extrait d'ARCHITECTURE.md, dont la section « La grammaire de l'API » garde l'essentiel.

## API Lua ↔ C

Le script Lua n'est jamais traduit directement en texte C : il passe par un AST Python intermédiaire, lui-même validé et traduit via un catalogue déclaratif unique.

```
texte Lua → parser.py → AST Python → checker.py (validation) → codegen.py → texte C
                                            ↑                        ↑
                                            └── scripting/api.py ──┘
                                          (RUNTIME_API : catalogue unique)
```

- **`parser.py`** — la grammaire Lua en dataclasses (`StmtIf`, `ExprInvoke` pour `self:method()`…). Spécifique à Lua : changer de
  langage de script réécrirait ce fichier et une partie du pattern-matching de `checker.py`/`codegen.py`, pas le reste.
- **`api.py`** (`RUNTIME_API`) — source de vérité unique de toute fonction Lua exposée : nom Lua, fonction C cible, types de
  paramètres, domaine de résolution des chaînes (`DOMAIN_ANIM`, `DOMAIN_SFX`, `DOMAIN_SCENE`…). Lu par `checker.py` (valider) et
  `codegen.py` (`_emit_api_call`).
- **`checker.py`** — valide l'AST contre `RUNTIME_API` (fonction connue, nombre d'arguments, variadiques comprises, nom de
  ressource existant). Seules les erreurs (`CheckError.level == "error"`) bloquent le build ; les avertissements (valeur littérale
  hors plage dans une globale typée) sont journalisés. Appliqué à tous les scripts (actor, scène, prefab) via
  `lua_compiler.py::_compile_script`. Les behaviors (`require("behaviors/x")`, résolus PAR NOM parmi les `.lua` marqués
  `-- @behavior`, `core/lua_scripts.py`, inlinés par `codegen.py::_emit_inlined_behaviors`) passent par le même checker avec
  `check_event_names=False` ; fichier manquant ou erreur de parse y remontent en avertissement.
- **`codegen.py`** — `_emit_api_call` génère l'appel C directement depuis l'entrée `RUNTIME_API`. Les fonctions qui ne se
  traduisent pas par un simple appel (`self:destroy` → deux instructions, `sfx.play` → arguments synthétisés) sont dans deux
  tables de dispatch en fin de fichier, `_INVOKE_CUSTOM` et `_CALL_CUSTOM`, et ont quand même une entrée de catalogue.
  `global.nom`/`const.nom`, `self.position` (RUNTIME_PROPS) et `data.Objets` sont des accès POINTÉS, résolus dans la branche
  `ExprIndex` de `_expr` et validés côté checker (`_check_global_scalar`, `_check_const_scalar`…), pas par le catalogue.
- **Important pour toute nouvelle fonction Lua** : si elle se traduit par un simple appel C avec conversion d'arguments, une entrée dans `RUNTIME_API` suffit *côté traduction*. Ce n'est que si elle a besoin de logique de traduction (nom C dynamique, arguments non présents côté Lua, émission multi-instructions) qu'elle doit aussi rejoindre `_INVOKE_CUSTOM`/`_CALL_CUSTOM`.
- **Une fonction du moteur exposée a son prototype GÉNÉRÉ** (« Prototypes et énumérations » ci-dessous) ; seules les énumérations redéfinies à la main côté moteur et l'ordre des arguments sont comparés au build.
- **`lua_subset.py`** — la LISTE de ce que le langage accepte, et de ce qu'il refuse en le disant. Chaque nœud de luaparser est
  `ACCEPTED` (il se traduit), `REFUSED` (avec la phrase qui dit quoi écrire) ou `STRUCTURAL` (jamais dispatché) ; la bibliothèque
  standard de Lua reçoit le même traitement, par nom. Trois consommateurs : `checker.py` (refuser en nommant l'issue),
  `docs/scripting-reference.md` (un test échoue si un refus n'y est pas documenté) et `validator._check_lua_subset` (**erreur
  bloquante** si un nœud n'est classé nulle part). Les nœuds non traduits sont PORTÉS (`StmtUnsupported`, `ExprUnsupported`, avec
  leur ligne) : le parser décrit, le checker juge. Une faute de SYNTAXE est le seul refus que le parser prononce (`LuaParseError`
  porte `line` et une phrase, cf. `_syntax_message`).
- **`expr_types.py`** — les deux exceptions au sous-ensemble Lua scalaire. `vec2(x, y)`/`vec3(x, y, z)` sont des constructeurs de
  langage, pas des entrées `RUNTIME_API` ; `+ - * /` s'y traduisent en `vec2_add`/`vec2_sub`/`vec2_scale`/`vec2_div`
  (`runtime_api_inline.h`), un entier mêlé à un vecteur vaut ce vecteur dont toutes les composantes sont cet entier (`v + 2` =
  `v + vec2(2, 2)`), la division est entière, et `dot(a, b)` (`VEC_FUNCTIONS`) rend un entier. La seconde exception sont les
  **références** (`local pas = sfx:play("Pas")`) : une valeur composée se copie, une référence DÉSIGNE un slot de pool. Checker et
  codegen partagent ce module pour répondre à « quel type porte ce nom ? » (`self._vec_types`, remplie au fil d'un parcours à plat).

### La grammaire cible de l'API — trois formes, une par nature

**Grammaire visée (ROADMAP v0.16, non verrouillée).** Le catalogue livré emploie encore `module.action(…)` ; la forme n'est pas
un choix stylistique : elle dit au parseur quoi produire (`Invoke` pour `:`, `Index` pour `.`), donc qui décide de la résolution.

| Syntaxe | Nature | Compile en |
|---|---|---|
| `identifier:member(...)` | **méthode** — opération sur une instance, qui peut produire un effet | `actor_member(récepteur, ...)`, ou `sfx_member(...)` sur une référence |
| `identifier.member` | **propriété** — donnée que l'API expose comme un état, lue et écrite | `actor_get_member(...)` / `actor_set_member(...)` |
| `module.member` | **propriété de singleton** — état d'un système moteur | `module_get_member()` / `module_set_member()` |
| `module:member(...)` | **méthode de singleton** — opération au niveau du système | `module_member(...)` |

`identifier` dans la forme méthode est une **instance** : un acteur (`self`, `other`, une variable d'actor) ou une **référence**
rendue par un appel (`local pas = sfx:play("Pas")` → `pas:set_volume(80)`). Le catalogue range les méthodes d'acteur sous la clé
`self:` et celles d'une référence sous le TYPE qu'elle porte (`sfx:`), relevé sur le `local` par `expr_types.infer_ref_type` ; une
référence porte aussi des **propriétés** (`hb.solid = false`, déclarées dans `RUNTIME_PROPS` sous `collision_box.champ`, le
checker refusant l'écriture d'un champ en lecture seule). Un module du moteur est un **singleton**, donc un récepteur comme une
instance : états en propriétés (`camera.position`, `music.volume`), opérations en méthodes (`camera:follow(...)`). Une
bibliothèque sans état, telle que `math`, reste une exception nommée (`math.abs(x)`).

La règle de décision pour TOUTE API future, dérivée des définitions ci-dessus :

- **état intrinsèque** → propriété (`self.position`, `blend.mode`) — jamais un
  appel `get_*`/`set_*`.
- **requête pure sans argument** (`input.axis`, `scene.frame`) → c'est
  de l'état déguisé en fonction → propriété en lecture seule.
- **requête INDEXÉE** (`hb:get_collision_tile(x, y)`, `save:read(slot, "nom")`, `layer.get_*(n)`) →
  reste une fonction : une propriété ne prend pas d'argument.
- **action qui produit un effet** → méthode sur son récepteur, qu'il soit une instance
  (`self:move(...)`) ou un singleton moteur (`scene:switch(...)`, `sfx:play(...)`).
- **cycle de vie** (décision du 2026-09-25, non encore migrée dans le catalogue) → **cinq verbes
  communs**, `:show()`, `:hide()`, `:activate()`, `:deactivate()`, `:destroy()`, seule porte
  d'ÉCRITURE ; l'état se lit par `visible` / `active` en **lecture seule**. C'est la seule
  exception à « réglage runtime → lecture ET écriture » : `x.visible = false` n'existe pas, sinon
  deux portes diraient la même chose. Voir « Cycle de vie » plus bas.
- **réglage d'inspecteur** → il a TOUJOURS une porte, dont la nature dit ce que le runtime sait
  faire : modifiable au runtime → lecture ET écriture ; fixé au build (le C émis en dépend, ou il
  réserve du matériel) → lecture seule (`self.screen_space`, `self.affine`, `self.box_count`).
  Un champ édité à l'éditeur mais invisible du script est un oubli, pas un choix. Un élément
  adressé par un NOM du projet (une boîte par son tag) s'obtient par un CONSTRUCTEUR de référence
  (`local hb = self:collision_box("hitbox")`) ; ses champs sont alors des propriétés
  (`hb.solid`, `hb.size`) et ses actions des méthodes (`hb:overlaps(other)`).

Deux cas hors des trois formes : la **fonction libre** `array` (une déclaration) et les **constructeurs** (`vec2(x, y)`).
`global.nom` / `const.nom` sont de la forme PROPRIÉTÉ, sans getter/setter : `nom` est un nom de PROJET (pas d'entrée
`RUNTIME_PROPS` possible, ce serait un catalogue régénéré à chaque édition de l'écran Variables). Ils compilent en accès direct
(`g_nom` / `CONST_NOM`), validés par `BuildContext.global_counts` / `.const_names`, comme `data.Objets`.

Deux conséquences qui se paient cher si on les oublie :

- **Méthode et propriété s'écrivent sur N'IMPORTE QUEL acteur nommé**, pas seulement `self` (`other.velocity`,
  `other:move(...)`) : le catalogue les range sous la clé `self:`/`self.` — une clé, pas une restriction — et `checker.py` valide
  tous les récepteurs. Seule exception, bloquée explicitement : un argument OU une comparaison de propriété dont le nom appartient
  au sprite du RÉCEPTEUR (`other:play_anim("walk")`, `other.anim == "walk"`), que le contexte de build ne peut ni vérifier ni
  résoudre (`checker._RECEIVER_DOMAINS`, jugé dans `_check_args` ET `_check_prop_domain_value`).
- **Une propriété peut porter un domaine** (`ApiProp.domain`) et s'écrire ou se comparer par un NOM : `self.obj_mode = "window"`,
  `blend.mode == "alpha"`, `other.name == "Ball"`. C'est le même `DOMAIN_*` que sur un paramètre, jugé par les mêmes tables
  (`checker._DOMAIN_CHECKS`, `codegen._DOMAIN_CONSTANT`) ; le C ne change pas (`OBJ_MODE_WINDOW` vaut un entier). Quand la forme
  nommée n'atteint pas l'état par la même fonction C que la forme ordinaire (`self.direction` : vec2 côté calcul, boussole côté
  nom), `c_getter_named`/`c_setter_named` portent la seconde porte.

### Module, type, instance — d'où vient le récepteur (ROADMAP v0.16, non verrouillée)

Les trois formes disent **comment ça s'écrit** ; il manque **de quel TYPE est le récepteur, et où le catalogue le range**.

| Mot | Ce que c'est | Exemple |
|---|---|---|
| **module** | un namespace : un système unique (singleton), ou une **fabrique** d'instances | `camera`, `scene`, `actor` (`get`/`spawn`/`count`) |
| **type** | une sorte de chose qui a des instances ; **son nom est la clé du catalogue** | `sfx`, `collision_box`, `ui_element`, `actor` |
| **instance** | une chose précise ; `self` et `other` en sont, une variable qui tient une référence aussi | `self`, `local hb = …` |
| **référence** | la valeur qui désigne une instance quand elle ne se déduit pas du contexte | rendue par une acquisition (`actor.get`, `interface.get`) ou une action (`sfx.play`) |

**Le module gère, crée ou acquiert ; le type expose l'état et les opérations d'une instance.** Un module n'opère jamais sur UNE
instance désignée par un nom du projet : c'est soit un système sans instance (`scene`, `camera`), soit une fabrique (`actor`). Tout
ce qui porte sur une instance nommée s'écrit en méthode ou en propriété **sur la référence** :

```lua
local menu = interface:get("Menu")     -- fabrique : une chose nommée du projet
menu.index = 0                         -- propriété
menu:show()                            -- méthode
```

Le numéro de matériel reste la porte des choses numérotées par le matériel, mais c'est aussi une acquisition (`layer:get(n)`) : le
fond `n` est une référence de type `background_layer`. Les fonds qu'une scène a dépendent de son mode vidéo
(`api.LAYERS_BY_MODE` × `Scene.render_mode`, passé au checker par `lua_compiler`) ; seul le mode 0 est offert à l'auteur, et rien
de ce qu'il lit ne parle de mode (un test le garde).

**Ce qui reste à migrer** : `window.*` (7 fonctions qui reçoivent encore le nom d'une instance) et
`layer.*` (numéroté par le matériel). Le type acteur est rangé sous `actor:` ; `sfx`, `collision_box` et
`ui_element` sont des lignes de `api.REF_TYPE_TABLE`. Dans le C émis, « absent » est UNE chose : `nil` vaut 0
(`if p ~= nil` → `(p != 0)`, `tests/scripting/test_ref_type_table.py`) ; une référence d'élément d'interface est un
index connu au build, jamais absente.

**Ce que ça ne coûte pas.** Une référence à une chose STATIQUE du projet (`interface:get("Menu")`,
`window:get("Panel")`) se résout au build en constante, comme `TEXT_<clé>` : aucun slot, aucun
test à l'exécution. Seules les références de POOL (`actor.get`, `sfx.play`, `actor.spawn`) portent
une valeur qui peut être périmée ou absente.

**Déclarer un type de référence — trois gestes, aucun cas spécial** (livré, v0.16 étape b).

1. UNE ligne dans `api.REF_TYPE_TABLE` : `RefType(c_type=…, prefix=…, hint=…)`. Le type C du
   `local` qui tient la référence, la variable des snippets, la phrase ajoutée à l'erreur
   « méthode/champ inconnu ».
2. Ses entrées de catalogue : la fabrique (`ApiFunc(ret="<type>")`), les méthodes sous
   `"<type>:<méthode>"`, les propriétés sous `"<type>.<champ>"`.
3. Les fonctions C, déclarées DEUX fois (section suivante).

Tout le reste s'en dérive : le `local` typé (`codegen`), le refus d'un membre inconnu
(`checker._unknown_ref_method` / `_unknown_ref_field`), les snippets (`api_snippets`), le
renommage (`refactor`). `tests/scripting/test_ref_type_table.py` déclare un type factice `gizmo` par ces trois
gestes seulement et vérifie qu'il se vérifie et se traduit — chaîné ou non — sans toucher
`checker.py` ni `codegen.py`. Seule une traduction C réellement atypique reste un cas de
`_INVOKE_CUSTOM` (`ui_element:show` → `ui_element_show(h, 1)`).

**Le garde-fou.** Comme `_check_api_domains` et `test_inspector_api_parity`, un test échoue si une
entrée de `RUNTIME_API` de la forme `module.fonction` prend en premier paramètre un domaine d'INSTANCE
(`ui_list`, `image`, `region`, `win_region`…) : la règle ne tient pas sur la discipline, elle tient
sur le catalogue.

### Cycle de vie — cinq verbes, communs à tous les types (décision du 2026-09-25)

Montrer, cacher, activer, désactiver et détruire s'écrivent pareil sur toute instance :

```lua
interface:get("menu"):hide()
interface:get("menu"):deactivate()
window:get("Panel"):hide()
actor:get("Boss"):destroy()
if menu.visible then ... end      -- lecture seule
```

| Verbe | Effet | Propriété de lecture |
|---|---|---|
| `show()` / `hide()` | rendre visible / invisible | `visible` |
| `activate()` / `deactivate()` | participer / ne plus participer (collision, entrée, navigation) | `active` |
| `destroy()` | libérer l'instance ; la référence devient périmée (`nil`) | — |

Règles :

- **Une porte d'écriture, une de lecture.** Pas de `x.visible = …` en écriture, pas de
  `layer.show(n, on)` ni de `list.set_active(nom, on)` — ces portes n'existent plus. Une valeur
  calculée s'écrit avec un `if`.
- **Chaque type déclare les verbes qu'il supporte** (dans sa ligne du catalogue) ; le checker refuse
  les autres. Une `collision_box` n'a pas `show`, un `sfx` n'a aucun des quatre premiers.
- **`destroy` ne vaut que pour les instances de pool** (acteur, `sfx`). Un élément d'interface ou
  une fenêtre est statique, connu au build : `destroy` y est une erreur du checker.
- **Le type de base `ui_element` porte `show`/`hide`/`activate`/`deactivate`** ; les types concrets
  (`list`, `image`, `button`…) ajoutent leurs propres états et actions.
- **Migré** : acteur, boîte, `ui_element` et ses natures, fonds (`background_layer`) et régions de
  window (`window_region`) — ROADMAP v0.16, étape (c) et (d). Reste `self:` → `actor:` (étape e).
  Les types `background_layer` et `window_region` ne portent pas le nom de leur module : un type
  `layer` aurait donné à `layer.priority` deux lectures (propriété du type, ou fonction du module).

### Prototypes et énumérations : générés depuis le moteur

`gba_engine.h` porte l'implémentation du moteur ; les scripts d'actor et de scène sont compilés en unités de
traduction séparées qui ne l'incluent pas. Leurs prototypes sont **générés** dans `runtime_api.h`
(`codegen/runtime_codegen/api_prototypes.py`) pour le seul sous-ensemble exposé par le catalogue : une fonction
exposée ne peut plus manquer de déclaration. `runtime_api_inline.h` porte, à la main, l'API en `static inline`.

`validator._check_api_prototypes` garde ce que la génération ne couvre pas, en **erreur bloquante** :

- l'ACCORD de VALEUR des énumérations entre `api.py` (leur source, d'où sont générés les `#define`) et les
  quelques-unes que `gba_engine.h` redéfinit à la main (`BLD_MODE_*`, `BLD_SIDE_*`) : sinon `main.c` et les scripts
  verraient deux valeurs, sans erreur ;
- l'ORDRE des arguments entre `api.py` et `gba_engine.h` : une permutation compile proprement (tout est `int`) et
  range chaque valeur dans le mauvais paramètre.

### Ce que l'éditeur INSÈRE dérive du catalogue

`scripting/api_snippets.py` fabrique le Lua que la sidebar du Script Editor propose au clic, depuis `RUNTIME_API` : écrits en dur,
ces snippets pourrissaient (le checker laisse passer un appel inconnu, qui peut être un helper de l'utilisateur, donc l'erreur
n'arrivait qu'à la compilation C). `call(name, **by_domain)` remplit les arguments **par domaine** et non par position : un
réordonnancement de paramètres dans `api.py` n'invalide aucun appelant. Même logique pour `api_reference.json`, qui ne décrit que
la *présentation* (groupes, ordre, descriptions) : `api_reference.get_categories()` le filtre par le catalogue puis le complète
avec lui, si bien qu'une fonction retirée disparaît de l'écran et qu'une ajoutée y apparaît sans toucher au JSON.

### Un domaine a TROIS consommateurs, et deux ne le disaient pas

Le `domain` d'un `Param` sert à `refactor` (suivre les renommages), au `checker` (le nom existe-t-il ?) et au `codegen` (quelle
constante C émettre ?). Le premier **dérive** sa table du catalogue (`_reference_sites()`). Les deux autres sont des **tables**,
comparées à `api.ALL_DOMAINS` (dérivé des constantes `DOMAIN_*`) par `validator._check_api_domains`, en **erreur bloquante** : un
domaine absent n'y produirait aucun signal (le checker ne validerait rien, le codegen émettrait la chaîne telle quelle, donc du
texte C là où le C attend un entier, avec une panne au `make` loin de la cause). Placer un nouveau domaine dans une case fait
partie de son ajout :

| Côté | Cases |
|---|---|
| `checker` | validé par domaine (`_DOMAIN_CHECKS`) ou non validé **avec sa raison** (`_DOMAINS_UNCHECKED` — seul `tag` y est) |
| `codegen` | constante générique (`_DOMAIN_CONSTANT`) ou émetteur dédié (`_DOMAIN_EMITTED_ELSEWHERE`) |

Chacun n'expose qu'un `covered_domains()` — le contrôle demande « ce domaine
t'est-il connu ? », pas la mécanique interne.

### Un nom se vérifie par son DOMAINE, pas par le nom de l'appel

Le contrôle d'un nom s'accroche au `domain` du `Param`, jamais à la clé de l'appel : une seconde fonction prenant
`DOMAIN_SCENE` est validée sans rien ajouter. `DOMAIN_PREFAB` est une **erreur** de checker (sinon `spawn_<Scene>_<Nom>`
n'échoue qu'au `make`, sur un « implicit declaration »), contre la liste PROJET des prefabs
(`BuildContext.prefab_names`, remplie par `lua_compiler`) — le raffiner en « poolé DANS CETTE scène » est possible
depuis le spawn per-scène (ROADMAP v0.17). Ce qui reste accroché à un appel dans `_check_call_expr` : le numéro
d'emplacement d'un `save.*`. La **valeur** d'un `global.nom = v` (plage du type déclaré) se vérifie à l'ASSIGNATION
(`_check_global_write_value`, sur `StmtAssign`).

**Une collision a deux côtés, et chacun l'apprend dans son propre script.** Le tick de scène teste scène↔scène et
pool↔scène, et appelle `on_collision_enter` des DEUX acteurs dans les deux cas, avec les boxes échangées (la
`my_box` de l'un est l'`other_box` de l'autre), sur le même test de recouvrement et le même souvenir de frame
(`_pcol_`).

### Tableaux — la forme est reconnue une fois, employée deux fois

Un tableau se déclare de deux façons, et c'est `parser.array_dims()` qui les
reconnaît — un seul endroit, appelé par le checker (valider) et par le codegen
(émettre). Il rend les dimensions, ou `None` quand ce n'en est pas une :

| Écrit en Lua | Dimensions | C émis |
|---|---|---|
| `local couts = {1, 2, 4, 8}` | `(4,)` | `static int couts[4] = {1, 2, 4, 8};` |
| `local grille = array(20, 12)` | `(20, 12)` | `static int grille[20][12] = {{0}};` |

**L'ordre des arguments d'`array` est l'ordre des index** : `array(20, 12)` se
lit `grille[1..20][1..12]`. Aucun vocabulaire de largeur ni de hauteur n'entre
dans la règle — il obligerait à se rappeler lequel des deux vient en premier,
alors que la déclaration le montre.

Trois pièges, et où ils sont tenus :

- **Lua indexe à partir de 1**, et c'est `CodeGen._index()` qui traduit, à un
  seul endroit : `t[i]` devient `t[(i) - 1]`, replié tout de suite quand l'index
  est littéral (`t[1]` → `t[0]`). Le reste de l'API expose bien des index à
  partir de 0, mais ce sont des **numéros matériels**, pas des positions dans un
  conteneur du langage.
- **`#t` est une constante de compilation** (`CodeGen._array_length`) : la taille
  fait partie du type, elle n'est rangée nulle part à l'exécution.
- **Un tableau d'état est permis partout, y compris dans un prefab poolé** (cf. « L'état d'un prefab poolé »).

`Checker._check_expr` parcourt l'expression entière (opérandes, arguments, cible d'affectation) : une erreur de
bornes dans `t[9] + 1` doit se voir.

`ExprIndex` (notation pointée, un NOM connu à l'écriture) et `ExprIndexAt`
(crochets, une EXPRESSION calculée) sont deux noeuds distincts : les confondre rendrait `t[i]` indiscernable de
`t.i`, et le C lirait un champ de structure là où le script veut un élément.

### Tables de données — `data.Objets[i].prix`

`data` est l'espace de noms RÉSERVÉ des tables authorées du projet
(`parser.DATA_NS`). Un nom réservé plutôt qu'un global par table : sans lui, une
table nommée `score` masquerait un `local score`, et rien ne dirait lequel des
deux est lu.

**La traduction se compose toute seule**, parce qu'elle suit la forme de l'AST :

| Lua | AST | C |
|---|---|---|
| `data.Objets` | `ExprIndex(ExprName("data"), "Objets")` | `g_data_Objets` |
| `data.Objets[i]` | `ExprIndexAt(…, i)` | `g_data_Objets[(i) - 1]` |
| `data.Objets[i].prix` | `ExprIndex(…, "prix")` | `g_data_Objets[(i) - 1].prix` |
| `#data.Objets` | `ExprUnop("#", …)` | le nombre de lignes, en littéral |

Les trois lignes du milieu ne sont qu'une branche chacune : la première pose le
tableau, et le reste (l'indexation à partir de 1, puis l'accès au champ) est le
chemin générique déjà écrit. Le C se relit avec les mots du Lua.

**Où vit quoi**, et pourquoi ce n'est pas un `DOMAIN_*` :

- une table n'apparaît **jamais comme argument littéral d'un appel**, donc la
  mécanique de domaine — dérivée de `RUNTIME_API.params` — ne s'y applique pas.
  Lui inventer un domaine obligerait à le déclarer « traité ailleurs » des deux
  côtés de `validator._check_api_domains` pour un `Param` qui n'existe pas ;
- le CHECKER reçoit `BuildContext.data_tables` = `{nom: (colonnes, lignes)}` et
  refuse une table inconnue, une colonne inconnue, un rang hors bornes écrit en
  clair, et **toute écriture** (une table est `const` en ROM) ;
- le CODEGEN reçoit la même table, dont il ne lit que le nombre de lignes — pour
  `#data.X`, constante de compilation comme `#t` ;
- les COLONNES de référence, elles, portent bien le nom d'un domaine (`text`,
  `sfx`…), mais côté DONNÉE et non côté argument : c'est
  `codegen/runtime_codegen/data_tables.py` qui les résout en index, et
  `validator._check_data_column_types` qui tient les trois listes d'accord
  (`COLUMN_REFERENCES`, `api.ALL_DOMAINS`, `project.DATA_COLUMN_SOURCES`).

**L'émission n'emploie pas les `#define`** `TEXT_*` / `SFX_*` : ils sont écrits
par `codegen` dans CHAQUE unité de traduction d'acteur, et `data_tables.c` n'en
est pas une. L'entier est donc écrit en clair, suivi d'un commentaire qui nomme
l'élément. `data_tables.h`, lui, est **toujours** généré et **toujours** inclus —
un include conditionnel serait un second chemin pour un cas vide — alors que le
`.c` n'existe que s'il y a une table (une unité de traduction vide n'est pas du
C standard, et le Makefile ramasse `src/*.c` au glob).

## Les séquences — une ligne droite devient un `switch`

`function on_sequence_intro()` est un handler que le build **découpe à chaque
attente** et réémet en machine à états. C'est la seule transformation du
transpileur qui change la FORME du code, et non seulement son vocabulaire.

La forme est reconnue dans `parser.py` (`sequence_name`, `wait_call`), comme
celle du tableau et du `require` : ses trois consommateurs l'appellent — le
checker, le codegen, et `rom_build` (cf. plus bas).

`CodeGen._plan_sequences` produit, par séquence, la liste de ses tranches et
l'état qu'elle demande ; `_emit_sequence` écrit le `switch`. Les deux temps sont
séparés parce que l'état doit être **déclaré avant** d'être écrit, et à un
endroit qui dépend du propriétaire.

```c
static void Hero_sequence_intro(Actor* self) {
    switch (Hero_seq_intro_step) {
    case 1: {
        Hero_seq_intro_depart = actor_get_position(self).x;
        actor_move_to(self, (Vec2){120, 80}, 60);
        Hero_seq_intro_step = 2;
    } break;
    case 2: {   /* wait_until */
        if (!((actor_get_position(self).x >= 120))) break;
        Hero_seq_intro_step = 3;
    } break;
    case 3: {   /* wait(30) */
        if (++Hero_seq_intro_timer < 30) break;
        Hero_seq_intro_timer = 0;
        Hero_seq_intro_step = 0;   /* dernière tranche : la séquence s'arrête */
    } break;
    }
}
```

(Propriétaire unique ci-dessus, donc des statiques de fichier. Dans un prefab
poolé, la même séquence ouvre sur `BallState* _st = &g_state_Ball[…];` et lit
`_st->seq_intro_step` — cf. `_state_ref` plus haut.)

Cinq points s'y tiennent :

- **Un entier suffit** : 0 = arrêtée, 1..N = l'étape en cours. `sequence.start`
  écrit 1, `stop` écrit 0, `running` teste ≠ 0 — aucune fonction C derrière les
  trois, d'où un `c_func` vide dans `RUNTIME_API`.
- **Pas de boucle autour du `switch`.** Chaque `case` rend la main : une tranche
  par frame. C'est ce qui rend impossible, par construction, qu'une séquence
  tourne en rond dans une frame — et c'est pourquoi une attente ne peut
  s'écrire qu'au PREMIER NIVEAU d'une séquence (le checker refuse ailleurs :
  dans un `if`, le `switch` ne saurait pas où reprendre).
- **Chaque `case` est accolé.** Un `local` non hissé y est déclaré, et sauter
  par-dessus une déclaration dans un `switch` nu ne serait pas correct.
- **Ce qui traverse une attente est HISSÉ dans l'état.** `referenced_names()`
  répond à « ce `local` est-il encore lu dans une tranche suivante ? » ; si oui
  il devient un champ, et son `local x = …` n'est plus qu'une affectation. Sinon
  il reste un local C, et ne coûte rien.
- **L'état vit là où vit celui du script** (`_state_ref`) : statique de fichier pour un propriétaire unique, champ de
  `g_state_<sym>[]` pour un prefab poolé.

**Le pompage vit à la fin de `on_update`** (`_emit_sequence_pump`), dans l'ordre
de déclaration. Rien n'est ajouté à la boucle de frame de `main.c`, qui appelle
déjà `on_update` pour chaque propriétaire. Un script qui n'écrit pas
d'`on_update` en reçoit un : le stub existant le porte. Le seul fil à tirer
ailleurs est dans `rom_build._collect_events`, qui ajoute `on_update` aux events
d'un script à séquences — sans ça, `main.c` ne l'appellerait pas et la séquence
démarrerait pour ne jamais avancer.

`DOMAIN_SEQUENCE` est le seul domaine dont **l'espace de noms est le script** et
non le projet : checker et codegen reçoivent l'AST et collectent les noms
eux-mêmes. Conséquence : `refactor` le dérive du catalogue comme les autres,
mais aucun renommage d'asset ne le déclenche — une séquence n'est pas un asset.

## L'état d'un prefab poolé

Un script de prefab poolé est **une fonction C partagée** par toutes ses instances : ses variables de tête ne peuvent donc
pas être de simples `static` de fichier, qui seraient communes aux vingt copies.

À la place, `CodeGen._emit_pool_state` émet un état dimensionné par le pool :

```c
typedef struct { int fx; int fx_t; } BallState;
static BallState g_state_Ball[POOL_BALL_INSTANCES];
static inline int Ball_pool_slot(Actor* self) { return ((int)(self - g_actors) - POOL_BALL_START) / POOL_BALL_GROUP; }

void Ball_on_update(Actor* self) {
    BallState* _st = &g_state_Ball[Ball_pool_slot(self)];
    _st->fx_t = _st->fx_t + 1;
}
```

Quatre points s'y tiennent :

- **Le pool est une plage contiguë de `g_actors[]`**, dont les bornes sont des
  constantes de build. `POOL_<SYM>_START`, `_SIZE`, `_GROUP` et `_INSTANCES` sont
  émises par `headers.py`, à l'endroit même où l'offset est calculé — le script
  transpilé est compilé une fois pour le PROJET et ne peut pas les connaître
  autrement. Le C émis se dimensionne sur le `#define`, jamais sur un littéral
  recalculé : un écart avec la boucle de pool de `main.c` serait un débordement
  silencieux.

  Les quatre ne disent pas la même chose : une instance de prefab **segmenté** occupe un GROUPE d'entrées de `g_actors` (la
  racine, puis ses parties) mais n'exécute qu'**un** script, celui de la racine. `_SIZE` compte les entrées réservées (ce qui
  est payé), `_INSTANCES` les scripts : c'est lui qui dimensionne l'état, et `_GROUP` ramène `self` à son rang d'instance
  (1 pour un prefab plat).
- **Seul ce que le script ÉCRIT est de l'état.** `assigned_names()` (codegen)
  parcourt les handlers ; un local de tête qu'aucune ligne n'assigne est une
  constante et reste un `static` de fichier. Sur `Ball.lua`, quatre des six
  locals sont dans ce cas. La règle rend aussi la mesure honnête : le build
  annonce l'état, pas la longueur de l'en-tête du fichier.
- **`pool_init` est une seule affectation de structure**, pas un champ à la
  fois : c'est ce qui réinitialise un tableau ou un vec2 sans code spécial.
  L'état de départ est un `static const` (donc en ROM), et il est recopié dans
  le slot au spawn.
- **Le slot est résolu une fois par fonction**, dans un `_st` posé en tête par
  `_close_state_scope()` — et seulement si le corps y a touché, sinon c'est un
  `-Wunused-variable`. `_state_ref()` rend donc `_st->champ`, jamais le chemin
  complet : `sizeof(Actor)` ne vaut pas une puissance de deux, la soustraction
  de pointeurs coûte une division, et surtout le chemin complet répété à chaque
  site noyait le nom écrit par l'auteur. Tous les émetteurs de corps passent par
  cette paire — handlers, stubs, `pool_init`, séquences, behaviors inlinés — de
  sorte qu'il n'existe qu'UNE forme d'accès à cet état dans le fichier émis.
- **Le build dit ce que ça coûte, il ne le plafonne pas** — `[ewram] prefab X :
  état de script N octets × M instances`. Cf. ROADMAP v0.7.6 pour pourquoi il
  n'y a pas de garde-fou bloquant ici, là où la mémoire vidéo en a un.

Ce n'est pas en contradiction avec « le stockage affine est PAR-ACTOR et non par
slot » ci-dessus, dont les deux raisons ne s'appliquent pas : l'index est ici
celui de l'instance dans `g_actors[]` (unique par instance, pas un slot de
matrice partagé), et `g_state_*` est `static` dans **un seul** `.c`, celui du
prefab — pas dans un header multi-inclus.
