# Les exports de script, câblés au jeu — paramétrer une instance — **LIVRÉ**

### D'où vient la question (2026-09-20)

Relevé en réglant l'adressage dynamique (friction #1) : c'est le pendant « données » de
`actor:get(i)`. Un script d'acteur peut déjà déclarer une table `exports` en tête
(`editor/scripting/exports_parser.py`) — des variables réglables PAR INSTANCE depuis
l'éditeur :

```lua
exports = {
    speed = { type = "int",  default = 5, label = "Speed", min = 0, max = 20 },
    team  = { type = "enum", default = "RED", values = {"RED","BLUE"} },
}
```

L'inspecteur du composant Script lit cette table et affiche un champ par variable
(`editor/ui/scene_manager/inspectors/component_editors/script.py`) ; les valeurs choisies pour
CET acteur sont rangées dans `ScriptComponent.exports_values` (dict `nom → valeur`, override du
défaut) et sérialisées dans le sidecar de scène.

**Le trou** : `exports_values` est authoré, stocké et édité, mais **le codegen ne le lit nulle
part** — `exports_values` n'apparaît que dans le modèle (`components.py`) et l'UI, jamais dans
`editor/scripting` ni `editor/codegen`. Au runtime, le script n'a donc aucun moyen de LIRE sa
valeur d'export : la fonctionnalité est à moitié construite (on remplit des champs sans effet en
jeu). Le cas d'usage : un seul `Patrol.lua` posé sur trois gardes, chacun sa `speed` et sa
`team`, au lieu de trois scripts jumeaux — l'identité propre d'une instance, quand `actor:get(i)`
donne l'instance.

### Livré le 2026-09-26

- `BuildContext.owner_kind` (`actor`/`prefab`/`scene`/`camera`) posé aux quatre sites de `lua_compiler.py` ;
  le checker refuse `self` hors acteur/prefab et un événement d'une autre famille
  (`api.KNOWN_EVENTS_BY_KIND` = source unique des événements par famille).
- `core/script_owners.py` : la lecture « à quoi ce fichier est-il attaché ? », partagée par le
  validateur (refus multi-familles) et l'éditeur de script (le contexte vient de l'attache, plus du dossier).
- Complétion : plus de `self.`/`self:` en scène ou caméra ; événements filtrés par famille.
- Interface : plus de badge de type ni de boutons « + Acteur / + Scène » dans le Script Editor ; un seul « + Script », créé à plat dans `assets/scripts/` (seul `behaviors/` reste un dossier, car c'est un module importé par son chemin). `Project.scripts_actors_dir/scenes_dir/cameras_dir` supprimés au profit de `scripts_dir` et `script_files()` ; les sélecteurs de script de scène et de caméra listent tous les scripts attachables. Les projets existants gardent leurs fichiers où ils sont : rien n'est déplacé, le contexte venant de l'attache.
- Tests : `tests/scene/test_script_owner.py`. Les quatre projets de démo ne produisent aucun nouveau refus.

**Décision 3 précisée (2026-09-26)** : un behavior reçoit son acteur en PREMIER PARAMÈTRE, que la
convention nommait `actor` ou `self`. Pour que `self` désigne TOUJOURS l'instance attachée, le mot est
interdit dans un behavior, en corps comme en paramètre : `function M.update(actor)`. Le refus bloque le
build (`validator._check_behaviors_without_self` — les erreurs du checker sur un behavior ne sont que
des avertissements) et le checker le dit aussi à l'inline (`owner_kind="behavior"`).

### Ce que ça touche

- Émission des valeurs par instance et un chemin de lecture — `editor/codegen/runtime_codegen/`
  (main_gen / lua_compiler) et `editor/scripting/codegen.py`.
- `editor/scripting/api.py` / `checker.py` : la syntaxe de lecture doit être connue et validée.
- `docs/scripting-reference.md` : documenter la déclaration `exports` et sa lecture.

### Décisions verrouillées (2026-09-20)

- **Un export EST une variable à valeur initiale posée par instance** (tranche D3). L'auteur
  l'écrit par son **nom nu** (`speed`), et s'en sert comme de n'importe quelle variable — lecture
  ET réassignation. Sa seule différence avec un `local` : sa valeur de départ vient de l'éditeur
  (bakée au build), pas du source. Rien de spécial à apprendre côté auteur.

  ```lua
  exports = { speed = { default = 5 } }   -- déclaré en tête
  actor.x = actor.x + speed   -- lecture
  speed = speed + 1           -- réassignation permise
  ```

- **Le stockage est décidé par l'USAGE, pas par le type d'acteur** (D1 reprécisé). Chaque export est
  émis comme variable C **initialisée** (`int speed = 5;`) ; l'optimiseur `arm-none-eabi-gcc -O2`
  fond un export jamais réassigné en immédiat (**zéro RAM/ROM**), et ne garde une case que s'il est
  muté. On ne code donc PAS nous-mêmes l'analyse d'assignation — le compilateur C la fait. À vérifier
  au build ROM (comme v0.18) que le pli a bien lieu.

- **Premier jet : acteur POSÉ seulement** (D2 écarté pour l'instant). Un posé a son propre
  `actor_<Scène>_<Nom>.c`, sa valeur y est triviale à émettre. Le cas POOLÉ (passage de paramètres
  à `actor.spawn`, stockage par instance `g_state_<sym>[]`) est une tranche suivante — **D2 se
  rouvre à ce moment-là**, pas maintenant.

- **Collision de noms interdite** (achève D3). Un nom d'export ne peut masquer ni un champ FIXE de la
  struct `Actor` (`position`, `velocity`…), ni un global, ni un mot du langage. La règle vit dans le
  `checker` — pas de namespace `export.` imposé à l'auteur, la validation suffit.

- **Types du premier jet : `int` / `bool` / `enum`** (D4), qui tombent tous sur un entier au runtime.
  `float` (→ Q8), `string` (→ clé de table de texte), `vec2`/`rect`, et les `*_ref`
  (`actor_ref`/`scene_ref`/`sfx_ref`) sont **reportés** à une tranche suivante, sur cas réel — un
  `actor_ref` devra alors se résoudre DANS la scène de l'instance (cohérent avec « L'acteur
  appartient à sa scène »).

### Ordre d'implémentation

1. **Émission des valeurs.** ✅ **Fait.** `lua_compiler._export_inits(actor, script)` résout, par
   export entier (int/float/bool/enum), l'override d'instance (`ScriptComponent.exports_values`) sinon
   le `default` → un littéral C (bool→0/1, enum→index). Il lit le **même arbre** (`script.locals`) que
   le codegen — pas un second parseur du fichier : le parser capte désormais les `values` d'enum sur
   le `LuaLocal` (`export_values`). Passé au codegen via `CodegenContext.export_inits` ; `_local_decl`
   l'utilise comme initialiseur prioritaire. Corrige au passage l'enum, qui émettait `0`.
   Tests : `tests/rom_build/test_export_values_codegen.py`.
2. **Résolution du nom.** ✅ **Déjà couvert** par l'émission existante : un export est un local
   top-level nommé (émis `static int <nom> = …` pour un posé), donc une référence nue `<nom>` dans le
   corps du script résout vers cette variable sans travail supplémentaire. Reste la SÛRETÉ du nom
   (collision) — c'est l'étape 3 (checker).
3. **Checker.** ✅ **Fait.** `_check_export_names` **refuse** (erreur) un nom d'export qui masque un
   champ fixe d'`Actor`, un global, ou un namespace/fonction d'API — la contrepartie du nom nu. Un
   type dont la valeur d'instance n'est pas encore câblée (string/refs/composites ; int/float/bool/enum
   le sont) donne un **avertissement non bloquant** (le défaut du script s'applique), pas un refus —
   pour ne pas casser un projet existant. Tests dans `tests/rom_build/test_export_values_codegen.py`.
4. **Validation build/ROM.** ✅ **Fait (2026-09-21).** Projet test (acteur posé « Flying Note » de
   MyGame, exports int/int/bool/enum, valeurs d'instance réglées) **compilé et lié en ROM** headless.
   Le `.c` porte les valeurs d'instance (`speed=7`, `boost=5`, `spin=1`, `dir=1` — enum résolu, plus
   de « non résolue »). Dans `rom.elf` (`nm`) : `boost` **muté** = vraie variable en IWRAM
   (`03001228 d boost`) ; `speed`/`spin`/`dir` **lus seulement** = **absents**, fondus en immédiats
   par gcc -O2, **zéro RAM**. Le pli read-only tient — la préoccupation « une constante prend de la
   place » est levée en pratique.
5. **Doc.** ✅ **Fait.** Section « Variables exposées (`exports`) » dans `docs/scripting-reference.md`
   (déclaration, usage par nom nu, types réglables par instance, règle de nom, coût nul en lecture
   seule). `api.py` : rien à faire — `exports` est une construction du parser, pas une fonction du
   catalogue moteur.

### Tranche suivante : le cas poolé (D2, ouverte le 2026-09-21)

Le premier jet ne couvre que l'acteur POSÉ. Un **prefab poolé** partage un `.c` et ses instances
naissent au runtime par `actor.spawn` — elles n'ont pas de fiche éditeur où régler une valeur. Fait
clarifiant : une instance de prefab **posée dans une scène est un acteur posé** (`prefab_name` est
purement informatif, `core/models/scene.py`) — donc déjà couverte. Le cas poolé ne concerne que les
spawns runtime. **Décidé avec l'auteur (D2) :**

- **`actor.spawn` accepte une table d'exports FACULTATIVE** : `actor:spawn("Bullet", pos, { speed = 8 })`.
  C'est l'analogue au spawn du réglage éditeur du posé — une balle rapide vs lente se règle au moment
  du spawn.
- **Repli à trois niveaux, par clé.** Pour chaque export d'une instance spawnée : (1) la valeur donnée
  dans la table de spawn si présente → sinon (2) la valeur d'export du **template prefab**
  (`Prefab.exports_values`, réglée en éditant le prefab — un `Prefab` EST son acteur racine, il porte
  donc un `ScriptComponent`) → sinon (3) le `default` du script. Les niveaux (2) et (3) sont connus au
  **build** et forment l'init du pool ; seul (1) s'écrit au site d'appel du spawn.
- **Stockage.** Un export réglable au spawn varie d'une instance à l'autre : il doit vivre en **état
  par instance** (`g_state_<sym>[]`), même s'il n'est que lu — comme un export muté aujourd'hui. Un
  export d'un prefab poolé jamais réglé au spawn ET jamais muté reste une constante partagée (le
  défaut template/script, fondu).

**Ordre d'implémentation (poolé) :**

1. **Init du pool depuis le template.** ✅ **Fait (2026-09-21).** Le ctx poolé reçoit
   `export_inits = _export_inits(pf, pf_ast)` — le même helper, mais sur le `Prefab` (qui porte
   `exports_values` en tant qu'acteur racine) : l'init résout la valeur du template sinon le `default`,
   pour un export muté (champ `g_state`) comme lu-seul (constante partagée). Vérifié : unit test
   `test_poole_init_depuis_le_template` + build ROM headless de TacticsDemo (prefabs poolés) vert.
2. **`actor.spawn` étendu.** ✅ **Fait (2026-09-21).** 3ᵉ argument facultatif = table `{ clé = valeur }`
   (le parser retient les clés, nouveau champ `ExprTable.keys` ; `actor.spawn` devient `variadic`). Le
   codegen émet, après le spawn, un **setter par clé** (`<Scène>_<Prefab>_set_<clé>`, extern, forward-
   déclaré en tête du spawner) : forme `local b = actor:spawn(...)` ou spawn nu (temporaire). L'accès
   passe par setter, jamais par `g_state` d'un autre `.c`. Enum/bool résolus en entier.
3. **Stockage.** ✅ **Fait.** Uniformisation décidée avec l'auteur : sur un prefab poolé, TOUT export de
   type réglable est un champ de `g_state` (même lu seulement), plus de constante partagée fondue — pas
   de scan inter-script. `_emit_locals` force ces exports en état.
4. **Checker.** ✅ **Fait.** `_check_spawn_table` : table à clés nommées, clés = exports réglables du
   prefab visé (via `spawn_exports`), valeurs littérales, et **position statement** seulement (début de
   ligne ou `local x =`, là où le codegen sait écrire).
5. **Validation build/ROM + doc.** ✅ **Fait.** Build ROM headless (TacticsDemo : `Range` poolé avec
   export `tint`, `actor:spawn("Range", pos, {tint=3})` dans `cursor.lua`) : le `.c` de Range porte le
   champ d'état, le setter et l'init template ; celui de Cursor l'extern + l'appelle après le spawn ;
   **compile + link vert**. Chaque instance écrit son propre slot (`g_state[pool_slot(inst)]`), donc
   deux spawns = deux valeurs. Doc : `scripting-reference.md` (« Régler un prefab au spawn »).

### Tranche : les types non-entiers (ouverte et livrée le 2026-09-21)

Le premier jet ne câblait que les types entiers (int/float/bool/enum). Les **six autres**
types déclarables (`string`, `actor_ref`, `scene_ref`, `sfx_ref`, `vec2`/`vec3`, `rect`)
étaient authorables et édités, mais retombaient sur leur défaut de source au build. Ils sont
maintenant câblés jusqu'au C, réglables par instance (éditeur posé + template poolé) ET par la
table de spawn.

**Décisions verrouillées avec l'auteur (2026-09-21) :**

- **`string` → entrée de texte ANONYME → index `TEXT_*`** (décision A). Le moteur est entièrement
  entier et `text.draw` prend un index, pas un `const char *` : une string brute ne pourrait rien
  alimenter. Le texte libre saisi (défaut OU valeur d'instance) devient une entrée anonyme de la
  table de textes — le MÊME chemin qu'un littéral de `text:draw("…")` — et se résout en index. Donc
  traduisible par le pipeline existant, et un `int` au runtime (le pli read-only s'y applique).
  `core/project_texts.collect_literal_texts` collecte désormais aussi ces littéraux (défauts de
  tous les scripts + overrides de chaque owner).

- **`*_ref` → constante symbolique de la scène de compilation.** `sfx_ref`→`SFX_*`,
  `scene_ref`→`SCENE_IDX_*`, `actor_ref`→`TAG_*` **qualifié par la scène** qui compile (cohérent
  avec « L'acteur appartient à sa scène » — un nom d'acteur n'a de sens que dans sa scène). Une réf
  vide tombe sur `0`. Toutes ces macros sont en portée dans le `.c` généré (l'en-tête les `#define`).

- **`vec2`/`vec3`/`rect` → type composé du moteur** (`Vec2`/`Vec3`/`Rect`, cf. `expr_types.C_TYPES`),
  déclaré `Vec2 home = { x, y };`. La valeur d'instance (liste `[x, y]`) ou le défaut de source
  (table `{x, y}`) résolvent le littéral composé. Poids par instance : 8/12/16 octets (`_STATE_BYTES`).

- **Réglables aussi à la table de spawn** (décision B). `actor:spawn("X", pos, { vel = vec2(1,2),
  boom = "Pop", tgt = "Enemy" })` : le setter émis est **typé** (`int` pour un scalaire/handle,
  `Vec2`/`Rect` pour un composite), défini dans le `.c` du prefab et forward-déclaré `extern` dans le
  spawner. Les valeurs se résolvent au site du spawn, dans la scène du spawner.

**Ce que ça a touché :** `codegen.py` (`_EXPORT_SETTABLE`/`_EXPORT_C_TYPE`, `_local_decl`,
`_emit_pool_state`, `_emit_shared_local`, setters typés `_export_setter_c_type`,
`_spawn_export_value`/`_ref_or_text_literal`) ; `lua_compiler.py` (`_make_export_resolver`
scène-scopé, `_export_inits` reçoit le résolveur, `_spawn_exports_meta` élargi) ;
`checker.py` (`_EXPORT_WIRED_TYPES` = tous, `_check_spawn_value`/`_check_spawn_ref_name`, **semage
des types composites** pour valider `home + vec2(1,0)` / `box.x`) ; `core/project_texts.py`
(collecte des littéraux d'export string). Tests : `tests/rom_build/test_export_values_codegen.py` (résolveur
par type, émission posé, table de spawn, setters composites typés, checker, régression composite).

**Validation build/ROM ✅ (2026-09-21).** MyGame, acteur posé « Flying Note » réglé sur les six
types (label string, boom sfx_ref vide, dest scene_ref, target actor_ref, home vec2 muté, box rect).
Le `.c` porte les valeurs résolues : `label = TEXT__LIT_…` (littéral d'instant « Buzz buzz » →
entrée anonyme), `boom = 0`, `dest = SCENE_IDX_TITLESCREEN`, `target = TAG_DIALOGUE_FLYING_NOTE`,
`home = { 10, 20 }` (Vec2), `box = { 2, 3, 8, 9 }` (Rect) ; **compile + link vert**. Dans `rom.elf`
(`nm`) : `home` **muté** = vraie variable IWRAM (`03001228 d home`) ; `box`/`dest`/`target`/`label`/
`boom` **lus seuls** = **absents**, fondus en immédiats par gcc -O2 — le pli read-only tient aussi
pour les index de texte, les refs et le rect. **Reste : rien** (le prolongement locals ci-dessous
est une tranche à part).

### Prolongement aux locals — écarté (2026-09-21)

Envisagé un temps : généraliser le pli read-only aux `local` de script. **Écarté**, car il
n'apporterait rien. `arm-none-eabi-gcc -O2` **fond déjà** un `local` littéral non réassigné en
immédiat (c'est ce que le `nm` montre pour les exports lus seuls) — aucun code à écrire. Et
contrairement à un export, un `local` n'a pas de valeur d'éditeur à injecter au build : le seul
apport propre du chantier était justement l'export, livré. Les globals resteraient de toute façon
exclus (partagés + persistables en SRAM, cf. v0.5/v0.20 : les baker casserait partage et
sauvegarde). Chantier **clos**.

**Chantier CLOS (2026-09-26).** Toutes les tranches (int/bool/enum, poolé, types non-entiers,
un seul type de script) sont livrées. Il ne reste rien d'ouvert.
