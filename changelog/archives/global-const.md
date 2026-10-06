# `global.nom` / `const.nom` — l'accès pointé — **LIVRÉ**

> **Chantier technique** — il ne livre rien de visible pour qui joue au jeu produit avec
> l'éditeur, seulement une grammaire de script cohérente avec elle-même. Il n'a donc ni numéro
> `vX.Y`, ni ligne au [README](../../README.md), ni entrée au [CHANGELOG](../CHANGELOG.md) : c'est
> la convention des [chantiers techniques](../../ROADMAP.md#chantiers-techniques).

> **Livré le 2026-09-01.** `global.get("score")` / `global.set("score", v)` / `const.get("max")`
> ont quitté `RUNTIME_API` au profit de `global.score`, `global.score = 12` et `const.max`.
> Le C émis est le même qu'avant — `g_score`, `CONST_MAX` —, ce qui change est la façon dont
> l'auteur l'écrit et l'endroit où le checker le juge. 22 tests dans
> `tests/rom_build/test_global_const_access.py`.

## D'où vient la question

`RUNTIME_API` est le catalogue des **fonctions Lua exposées au runtime** : nom Lua, fonction C
cible, types de paramètres, domaine de résolution des chaînes. `global.get`/`global.set` et
`const.get` y avaient une entrée, mais aucune ne se traduisait par un appel : le codegen les
interceptait dans `_CALL_CUSTOM` pour émettre un accès direct (`g_score`, `CONST_MAX`). Trois
entrées de catalogue dont la seule raison d'être était de **ne pas être des appels**.

Le langage avait déjà tranché la question ailleurs, deux fois :

- une **propriété** s'écrit `identifier.member` et compile en getter/setter — `self.position`,
  `blend.mode` (`RUNTIME_PROPS`) ;
- une **table de données** se cite comme du code — `data.Objets[i].prix` — et compile en accès
  direct au tableau `const` émis par `data_tables.c` ;
- et depuis la [v0.20](v0.20.md), une globale **à plusieurs cases** s'écrivait déjà
  `global.coffres[i]`, en accès pointé, sans accesseur.

C'est cette dernière qui rendait la situation intenable : la MÊME variable se lisait
`global.get("score")` quand elle avait une case et `global.coffres[i]` quand elle en avait
quatre cents. Une propriété du modèle (le nombre de cases) décidait de la **forme syntaxique**
de l'accès, ce qu'aucune autre partie du langage ne fait.

## Décisions verrouillées

- **Ce sont des accès POINTÉS, pas des appels, et pas non plus des propriétés.**
  `RUNTIME_PROPS` ne convenait pas davantage que `RUNTIME_API` : une propriété est un membre de
  **langage** fixe (`position`, `visible`), là où `score` est un nom de **projet**. Une entrée
  de catalogue par variable déclarée serait un catalogue qui se régénère à chaque édition de
  l'écran Variables. D'où la troisième voie, déjà empruntée par `data.Objets` : le checker
  (`_check_global_scalar` / `_check_global_indexed` / `_check_const_scalar`) et le codegen
  (branche `ExprIndex` de `_expr`) résolvent **par nom** contre `BuildContext.global_counts` /
  `.const_names`, jamais contre un catalogue figé.

- **`DOMAIN_CONST` disparaît avec son dernier site.** Un domaine déclaré que rien ne cite est un
  orphelin, et `validator._check_api_domains` en fait une **erreur bloquante** —
  `const.get` étant le seul appel qui portait ce domaine, le retirer sans retirer le domaine
  aurait cassé le build de l'éditeur lui-même. `DOMAIN_GLOBAL`, lui, **reste** : `save.read(slot,
  "nom")` cite encore une globale en chaîne littérale.

- **`save.read` garde son nom littéral, et ce n'est pas une exception à contrecœur.** Son
  premier argument est l'emplacement, pas le récepteur — il n'y a pas de `slot.nom` à écrire —
  et ce qu'il résout n'est pas la même chose : `GLOBAL_NOM`, l'**id de sauvegarde**, pas `g_nom`,
  la variable en RAM. Deux résolutions différentes pour deux questions différentes.

- **Une constante ne s'écrit jamais.** `const.max = 4` est refusé par `_check_const_write`,
  branché sur `StmtAssign`. C'est ce qui distingue une constante d'une globale ; sans ce refus,
  la symétrie visuelle de l'accès pointé aurait laissé croire le contraire.

- **Un tableau n'existe qu'indexé, un scalaire jamais.** `global.coffres` nu et
  `global.score[1]` sont deux erreurs, dites sur la ligne Lua avec la forme correcte en
  remplacement. Le rang littéral reste borné (v0.20) ; un index calculé ne l'est pas plus ici
  qu'ailleurs dans le langage.

- **La valeur écrite se vérifie à l'ASSIGNATION.** L'avertissement de plage
  (`global.score = 70000` sur un `u16`) était accroché à l'appel `global.set` dans
  `_check_call_expr` ; il vit maintenant dans `_check_global_write_value`, appelé depuis
  `StmtAssign`. Seule la forme scalaire est bornée — une case de tableau ne l'a jamais été.

## Ce que ça touche

| Fichier | Ce qui change |
| --- | --- |
| `scripting/api.py` | les trois entrées quittent `RUNTIME_API` et rejoignent `REMOVED_API` avec la phrase qui dit quoi écrire ; `DOMAIN_CONST` supprimé |
| `scripting/checker.py` | `_check_global_scalar`, `_check_const_scalar`, `_check_const_write`, `_check_global_indexed` (ex-`_check_global_array` + `_check_global_index`), `_check_global_write_value` (ex-`_check_global_set_value`) ; `_check_const` supprimé |
| `scripting/codegen.py` | branche `ExprIndex` de `_expr` : `global.nom` → `g_nom`, `const.nom` → `CONST_NOM` ; `_emit_global_get`/`_emit_global_set`/`_emit_const_get` supprimés avec leurs entrées de `_CALL_CUSTOM` |
| `scripting/refactor.py` | `VarRef`, `iter_var_refs`, `rename_var_in_project` — un nom de variable est désormais un site de CODE, comme `data.Objets` ; `_rename_data` généralisé en `_rename_by_position` |
| `scripting/parser.py` | `LuaScript.globals_w` et `_collect_globals` supprimés — la collecte des écritures globales servait `global.set("nom", …)`, qui n'existe plus |
| `scripting/api_reference.json` | la section « Variables » disparaît : ce ne sont plus des appels, et l'écran les documente déjà par la table Globals/Constants |
| `core/project_variables.py` | `rename_variable` appelle `rename_var_in_project` EN PLUS de `rename_lua_refs(DOMAIN_GLOBAL, …)` — les citations pointées et le littéral de `save.read` sont deux chemins |
| `ui/script_editor/var_table_panel.py` | les snippets insérés au double-clic et au clic droit sont pointés |
| `codegen/runtime_codegen/lua_compiler.py` | `const_names` passé en LISTE même vide (cf. « Le piège » ci-dessous) |

## Le piège rencontré : « aucune constante » n'est pas « je ne sais pas »

`lua_compiler` remplissait `BuildContext.const_names = list(const_names) if const_names else
None`. Tant que `const.get` était un appel, cette nuance ne coûtait rien : `_check_const` se
taisait sur `None`, et `_emit_const_get` émettait `CONST_MAX` de toute façon — gcc échouait sur
un identifiant **nommé**, ce qui se diagnostique.

Avec l'accès pointé, le codegen n'émet `CONST_MAX` que si le nom est connu ; sinon il retombe
sur la composition générique `f"{obj}.{field}"` et écrit **`const.max` dans le C**. Un projet
qui n'a déclaré aucune constante mais dont un script cite `const.max` passait donc le checker
en silence et échouait au `make`, sur une erreur de syntaxe autour du mot-clé C `const` — le
pire des deux mondes, et exactement la famille de défauts que ce dépôt teste.

Corrigé à la source plutôt que dans le codegen : `const_names` est une **liste même vide**, ce
qui rend enfin atteignable le message déjà écrit dans `_check_const_scalar` (« aucune constante
déclarée dans ce projet »). `global_counts`, juste au-dessus, était déjà un dict même vide pour
la même raison — les deux se lisent maintenant pareil. `None` garde son sens, « l'appelant n'a
rien renseigné », et reste le comportement pour un appelant partiel.

## Ce que le chantier a rendu mort, et qui a été supprimé

- `parser.LuaScript.globals_w` et `_Converter._collect_globals` — la déclaration d'une globale
  depuis un `global.set("nom", …)` non déclaré n'a plus de site.
- `checker._check_const`, `_check_global_array`, `_check_global_index`, `_check_global_set_value`.
- `codegen._emit_global_get`, `_emit_global_set`, `_emit_const_get`.
- `api.DOMAIN_CONST` et les trois entrées `RUNTIME_API`.
- la section « Variables » d'`api_reference.json`.

## Ce qui reste vrai après

La référence de scripting porte la forme d'aujourd'hui, `ARCHITECTURE.md` la règle de décision (« deux
conséquences qui se paient cher »), et `REMOVED_API` la phrase qui guide un script écrit avant
le chantier. Un projet existant ne se casse pas en silence : il refuse de compiler en disant
quoi écrire à la place, ligne par ligne.
