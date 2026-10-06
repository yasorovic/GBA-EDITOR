# L'acteur appartient à sa scène — noms locaux, `get_actor` nullable — **LIVRÉ**

### D'où vient la question (2026-09-20)

En construisant la démo tactique (le deuxième jeu de démo de la v1.0), puis en la passant à
l'échelle (40 scènes / 200 sprites), deux frictions jumelles sont sorties — cf. « Frictions
relevées en construisant la démo tactique », points **#1** et **#2**. Le test d'échelle a levé
**229 avertissements de collision** : deux scènes qui posent chacune un acteur « Cursor » (ou
« Enemy », « Boss ») partagent un seul symbole C. Cause exacte : les acteurs **posés** sont la
seule chose que la compilation par scène (v0.17) **ne qualifie pas** — `TAG_<Acteur>` nu et
`actor_<Acteur>.c` ([headers.py:67](editor/codegen/runtime_codegen/headers.py:67)), là où un
prefab est déjà `TAG_<Scène>_<Prefab>` et un script `<Scène>_scene`. Le réflexe d'auteur —
nommer « curseur » dans chaque scène — est légitime et doit marcher : **personne ne doit écrire
« curseur01 ».**

### Le principe

Un acteur appartient à sa scène. Son **nom** est local à la scène (l'auteur écrit « curseur »
partout) ; son **symbole C** est qualifié par la scène, comme tout le reste sous v0.17 ; et le
qualificatif est **dérivé** au build, **jamais un second champ stocké** (source de vérité
unique — pas de « curseur01 » rangé quelque part).

### Décisions verrouillées (2026-09-20)

- **A — un acteur appartient toujours à la scène courante.** Une seule scène est vivante à la
  fois ; un acteur d'une autre scène n'existe pas dans `g_actors`. Aucune référence
  inter-scènes, donc aucune syntaxe pour en viser une.
- **B — unicité DANS la scène.** Deux acteurs de même nom dans la MÊME scène = l'erreur (le vrai
  doublon). D'une scène à l'autre, le nom se réutilise librement. Le contrôle du validateur
  passe de « unique au projet » à « unique dans la scène ».
- **C — `get_actor` rend un `Actor*` ou `nil` : un seul contrat, deux réalisations selon le
  contexte d'écriture (dérivé, pas une nouvelle syntaxe).**
  - Script de **scène / acteur / prefab** (une scène est connue au build) : résolu à la
    **compilation** en `&g_actors[TAG_<Scène>_<Nom>]`. L'acteur est authoré → présent. `~= nil`
    permis mais toujours vrai, **zéro overhead, rétrocompatible**.
  - Script **partagé** (caméra, `scene_sym` vide) : **lookup runtime** dans la scène active →
    l'`Actor*` ou `nil`. C'est le seul endroit où le nil « absent de la scène » apparaît. Ceci
    **remplace** l'idée initiale de *refuser* `get_actor` dans une caméra : au lieu de refuser,
    on résout à l'exécution (une caméra partagée par trois scènes peut dire « s'il y a un
    'player' ici, suis-le »).
- **C' — un acteur DÉTRUIT au runtime (`self:destroy()`) rend aussi `nil`.** C'est une
  information de gameplay (« ma cible est-elle encore là ? »), pas seulement « absent de la
  scène ». `get_actor` teste donc l'état ACTIF du slot, pas seulement sa présence.

### Ce que ça touche

- `codegen/runtime_codegen/headers.py` — `TAG_<Nom>` → `TAG_<Scène>_<Nom>` pour les acteurs
  posés (aligné sur les pools juste en dessous) ; les `#define` d'un bloc de scène cessent de
  collisionner.
- `scripting/codegen.py` — `_emit_get_actor` préfixe par `ctx.scene_sym` quand elle existe
  (constante compile-time) ; sinon émet l'appel `runtime_get_actor(ACTORNAME_<Nom>)`. Le fichier
  `actor_<Nom>.c` devient `actor_<Scène>_<Nom>.c`.
- `codegen/runtime_codegen/main_gen.py` — pose de `g_actors` et des `TAG_` au `scene_init` avec
  le nom qualifié ; émission d'une table `{ACTORNAME_id → slot}` par scène.
- Runtime (`runtime/…`) — `runtime_get_actor(id)` : lit la table de la scène active, rend
  `&g_actors[slot]` si présent **et actif**, `NULL` sinon (couvre C'). Un enum global
  `ACTORNAME_*` sert de **clé de lookup**, distincte des symboles C qualifiés par scène (donc
  pas de régression sur la collision qu'on corrige).
- `scripting/checker.py` — unicité DANS la scène (B) ; `get_actor` d'un littéral absent de la
  scène → avertissement au build (comme un nom de prefab inconnu), **sauf** script partagé où
  l'absence est légitime et se résout à `nil`.
- `core/validator.py` — retirer l'avertissement « deux acteurs de même nom entre scènes » (le
  cas devient légitime).
- `docs/scripting-reference.md` — `get_actor` peut rendre `nil` ; le patron
  `if get_actor("x") ~= nil then …`.

### Ce qui reste HORS de ce chantier

L'adressage **dynamique** (friction #1) — indexer les acteurs par une valeur calculée,
`get_actor(i)`, tenir un tableau d'acteurs, remplacer la cascade `if sel==1 then…`. C'est un
chantier distinct et plus gros ; celui-ci ne le traite pas, mais en est le **préalable propre** :
une fois les noms locaux et le contrat nullable posés, l'adressage dynamique se construit dessus.

### Ordre d'implémentation

1. ~~**Qualification des symboles d'acteurs posés** (`TAG_`, `actor_<…>.c`, `g_actors`/
   `scene_init`).~~ **Fait (2026-09-20).** Helper unique `codegen.c_names.scene_actor_sym`
   appliqué aux huit sites de `main_gen`, à `lua_compiler` (fichier + `child_refs` + clé
   d'events dans `rom_build`) et à `headers` (`TAG_`). Vérifié : un projet de 40 scènes
   réutilisant « Cursor »/« U0 »… **build et link proprement** (ROM 388 Kio), là où il levait
   229 avertissements de collision.
2. ~~**`get_actor` compile-time préfixé par scène** (constante).~~ **Fait (2026-09-20).**
   `_emit_get_actor` émet `&g_actors[TAG_<Scène>_<Nom>]` quand une scène est connue ; les scripts
   existants (noms locaux) ne changent pas.
3. ~~**Enum `ACTORNAME_*` + table par scène + `runtime_get_actor` + nil sur détruit** ; `get_actor`
   runtime dans les scripts partagés.~~ **Fait (2026-09-20).** `actor_live()`
   (`runtime_api_inline.h`) filtre le chemin compile-time → `nil` si l'acteur a été détruit
   (**C'**). Pour un script partagé (caméra, sans scène), `_emit_get_actor` émet
   `runtime_get_actor(ACTORNAME_<Nom>)` ; `headers.actorname_ids` pose l'enum de lookup global,
   et `main_gen` émet le résolveur `runtime_get_actor` (switch `g_current_scene` → `ACTORNAME_*`
   → `actor_live(&g_actors[TAG_<Scène>_<Nom>])`, le TAG per-scène valant le slot). Réalise **C**
   (nullable au runtime) et **C'**. Tests : `test_actor_scene_naming.py`.
4. ~~**Checker/validateur** (unicité dans la scène) + **doc**.~~ **Fait (2026-09-20).**
   `_check_actor_name_collisions` vérifie l'unicité DANS une scène ; réutiliser un nom d'une
   scène à l'autre ne produit plus rien. `docs/scripting-reference.md` documente le contrat
   nullable de `get_actor`. Tests : `test_actor_scene_naming.py`.

**Chantier CLOS (2026-09-20).** Vérifié de bout en bout : un projet de 40 scènes réutilisant
« Cursor »/« U0 »… **build et link proprement** (ROM 403 Kio), 0 avertissement de collision,
suite non-UI verte. Il ne reste rien d'ouvert.
