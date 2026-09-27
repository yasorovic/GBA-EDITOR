# Correctifs trouvés en marchant, hors chantier — **CLOS**

Des défauts réels, trouvés en marchant — la plupart en construisant et en jouant les projets
démo pendant le chantier v0.9, quelques-uns depuis — sans rapport avec un jalon en particulier,
consignés ici pour ne pas être restés invisibles faute d'un jalon à qui les rattacher. Tous
corrigés, tous couverts par un test.

- **`g_actors[]` débordait l'IWRAM sur un projet multi-scène dense**
  (`codegen/runtime_codegen/main_gen.py`), révélé par le fixture `BuildBenchmark` : 120
  acteurs répartis sur quatre scènes n'emploient jamais plus de 30 entrées OAM simultanément,
  mais leurs tranches restent réunies dans une table runtime unique. Ses ~20 Kio, ajoutés au
  moteur, dépassaient les 32 Kio d'IWRAM et faisaient échouer l'édition de liens. Cette table
  est désormais émise en **EWRAM** (`EWRAM_DATA`, 256 Kio) ; les `TAG_*` et la sémantique des
  transitions ne changent pas. Le dimensionnement par scène, gain plus large déjà identifié
  pour v0.17, a été traité par ce chantier-là (livré).

- **`project.save()` réécrivait tout à chaque `Ctrl+S`** (`core/resources/resource_store.py`), trouvé le
  2026-09-07 en traitant une lenteur de sauvegarde signalée sur le Script Editor. Enregistrer le
  projet sérialise et réécrit les quatorze collections ; or éditer un script ne change AUCUN
  asset, et `atomic_write` écrivait quand même chaque fichier (temporaire + rename, ré-armant le
  QFileSystemWatcher à chaque fois). Il **saute** désormais l'écriture quand le disque contient
  déjà le même texte — le patron de `build_output.write` côté build, porté au chemin de
  sauvegarde. Sur 200 assets intacts : ~950 ms → ~100 ms. Bénéfice au passage : un fichier non
  réécrit garde son mtime, donc pas de faux rebuild incrémental.

- **`_hw_layer_z` — l'ordre de composition du canvas** (`ui/scene_manager/scene_canvas.py`).
  Un acteur (OBJ) portait un zValue fixe (10) et une zone d'interface un zValue fixe (120) :
  l'acteur passait donc TOUJOURS sous l'interface dans le canvas, quelle que soit la priorité
  réelle — le contraire de ce que montre la ROM dès que `text_bg` n'est pas 0 (priorité GBA =
  `bg_slot` directement, et à priorité égale l'OBJ passe devant le BG). Le canvas reproduit
  désormais l'ordre matériel plutôt qu'un empilement choisi pour le confort de l'édition.
  Tests : `test_canvas_draw_order.py`.

- **`BOXTAG_*` absent pour une box portée par un prefab** (`codegen/runtime_codegen/headers.py`).
  `spawn_<Prefab>()` écrit `boxes[].tag = BOXTAG_<TAG>` pour la box d'un prefab poolé et de ses
  parties (v0.23, « Ce qu'un boss demande »), mais la génération des `#define` ne parcourait
  que les acteurs de SCÈNE — un tag porté seulement par un prefab n'avait donc pas de
  constante, et le C émis ne compilait pas (`'BOXTAG_BODY' undeclared`).
  `Project.collision_tags()` était déjà la source unique (scènes, prefabs, parties de prefabs)
  pour le sélecteur de tag et la matrice de Project Settings ; le codegen en était la troisième
  lecture, et la seule qui mentait. Tests : `test_collision_tags.py`.

- **Glyphes animés d'une zone : dérivés, plus déclarés** (`core/project.py`,
  `core/models/ui_region.py`). Le nombre de caractères qu'une zone sort de la bande pour les
  animer était un champ rempli à la main dans l'inspecteur ; il se déduit désormais du texte
  affiché (`Project.region_animated_glyphs`), au maximum sur TOUTES les langues déclarées (une
  réservation trop basse fait retomber l'effet en statique sans un mot) et plafonné aux slots
  OAM disponibles (zéro quand rien n'est animé). Le modèle ne résout pas la table de textes —
  le compte lui est fourni, comme les frames d'un sprite. Tests : `test_animated_glyphs.py`.

- **Renommer une clé de texte désynchronisait les zones d'interface**
  (`core/project_renames.py`). `region.text_key` est une COPIE de chaîne, pas l'id stable du
  texte. Le script Lua qui cite une clé était déjà réécrit par `rename_lua_refs` ; les zones
  d'interface (`UIText.text_key`), l'autre des deux seuls référents d'une clé (cf.
  `TextUsage`), ne l'étaient pas — un rangement qui recale une clé automatiquement
  désynchronisait silencieusement l'écran de scène. Bug réel rencontré sur le projet démo
  Fonts&Texts (2026-08-27). Tests : `test_text_key_ui_sync.py`.

- **Surface de composition texte partagée entre zones qui ne devraient pas se disputer les
  tuiles** (`gba_engine.h`, `codegen/font_emit.py`). La surface partagée est adressée modulo
  et ne couvre que 8 rangées sur les 20 de l'écran : deux zones dont les rangées coïncidaient
  modulo 8 se disputaient les mêmes tuiles et s'écrasaient en VRAM — un titre en haut et une
  boîte de dialogue en bas, une mise en page banale, tombait dans ce cas, et aucun garde-fou ne
  pouvait le rendre acceptable : c'était la mise en page qu'il fallait interdire. Corrigé en
  allouant un bloc PAR ZONE (`RegionSurf`), à la taille du rectangle ABSOLU (une zone enfant
  d'un panneau n'occupe pas les tuiles écran de son offset local) ; la surface partagée n'est
  plus réservée que si un script écrit LIBREMENT (`text.draw`/`text.clear`, qui n'ont pas de
  rectangle à qui donner un bloc). Tests : `test_text_surface_alloc.py`.

- **Un remplacement de police par langue n'était pas compté comme une composition**
  (`codegen/runtime_codegen/gen_text.py`, 2026-09-12). Une zone déclarée en Font8x8 Latin
  pouvait devenir Misaki Gothic 8 au runtime japonais : le moteur choisissait alors bien le
  chemin pixel, mais le build n'avait réservé aucun `RegionSurf` car il n'avait examiné que la
  police latine. `region_is_composited()` tient désormais compte de chaque remplacement de la
  police par défaut ; la réservation émet `text_set_region_surf` pour la zone. La palette de la
  police suit la même source persistante (`Scene.font_pal_banks`) dans l'inspecteur, le canvas,
  l'allocateur et le runtime. Tests : `test_text_surface_alloc.py`,
  `test_font_palette_tracking.py`, `test_scene_canvas_smoke.py`.

- **Trois trous du checker, fermés en avertissement** (`scripting/checker.py`, 2026-09-02).
  Trois défauts de la même famille, trouvés en écrivant un écran de sélection de langue : le
  script traverse le checker sans un mot, le codegen émet du C, et gcc parle d'un fichier que
  l'auteur n'a jamais écrit — le piège que l'ARCHITECTURE nomme le plus coûteux de cette
  chaîne. (1) **Un nom NU non déclaré** : `curpos = curpos + 1` émettait
  `curpos = (curpos + 1);`, un identifiant qui n'existe pas. `_check_expr` n'avait
  simplement AUCUNE branche `ExprName`. Le contrôle s'appuie sur un quatrième parcours à plat
  (`_collect_local_names`, même forme et même approximation que ses trois jumeaux) et sur la
  liste des espaces de noms, parce que la fin de la branche `ExprIndex` visite `e.obj` — le
  `global` de `global.score` passe par là. (2) **Les membres d'une référence d'élément
  d'interface** : `ui_element` est déclaré comme type de retour mais absent de `REF_TYPES`,
  donc `.y`, `.foo` et `:bouge()` passaient tous. Reconnue par sa FORME (`interface:get(...)`) et non
  en l'inscrivant dans `REF_TYPES` — l'y mettre ferait chercher les méthodes sous
  `ui_element:show` alors qu'elles vivent sous `self:show`, et casserait le `interface:get(x):show()`
  qui marche [*levé le 2026-09-25 : `show`/`hide` vivent sous `ui_element:` et le type est dans
  `REF_TYPE_TABLE` — cf. v0.16, étape (b)*]. (3) **Les arguments d'un appel utilisé comme RÉCEPTEUR** :
  `interface:get("Cusor"):show()` ne validait rien, alors que la même expression posée seule était
  refusée — `_check_call_expr` s'arrête à un récepteur `ExprName`. Corrigé en faisant descendre
  un appel posé seul par `_check_expr` comme n'importe quelle expression.

  **Avertissement pour (1) et (2)**, à durcir une fois éprouvés : ils s'appliquent à tous les
  scripts de tous les projets, et un cas légitime oublié bloquerait un build qui marche. **(3)
  garde la sévérité des contrôles existants** — il ne fait que les laisser passer, et un nom
  d'élément inconnu ne produit aucun `#define` : ce build-là échouait déjà au `make`.
  Tests : `test_checker_holes.py`, dont la moitié tient ce que les contrôles ne doivent PAS
  refuser.

- **Une faute de syntaxe disait « None »** (`scripting/parser.py`). Le parse est le PREMIER
  filtre de la chaîne, et c'était le seul message qui ne disait pas où regarder :
  `[error] Titre.lua — parse: syntax errors: None`, quelle que soit la faute. Le contraire de
  ce que la v0.7.5 a établi partout ailleurs — le checker nomme sa ligne, `lua_subset` nomme
  le nœud refusé ET la phrase à écrire à la place. Rien n'était perdu, c'était jeté au
  FORMATAGE : luaparser lève sa `SyntaxException` depuis un `except`, donc Python garde la
  `ParseCancellationException` d'antlr dans `__context__`, laquelle porte l'exception réelle
  avec son jeton fautif et ses jetons attendus. Deux décisions : le jeton **trouvé** n'est
  jamais rapporté — antlr le désigne là où il a renoncé, pas là où l'auteur s'est trompé (sur
  `if x(...) :`, il nomme la parenthèse de l'appel) —, et un « end » manquant se dit comme
  tel plutôt que d'envoyer l'auteur regarder la dernière ligne du fichier, qui est presque
  toujours correcte. S'y ajoute une table de **faux amis** (`+=` et les affectations
  composées, `++`, `:` au lieu de `then`, `!=`, `&&`, `||`, `elif`, `#` en commentaire…) balayée SEULEMENT après un échec, donc jamais sur
  un script valide, et hors chaînes et commentaires — un `!=` dans une réplique de dialogue
  n'est pas une faute de syntaxe. Elle n'est pas dans `lua_subset.REFUSED` : celui-là range
  des nœuds d'AST, et ces fautes-là empêchent l'AST d'exister. `LuaParseError` porte
  désormais sa `line`, que le build cite comme le reste (`Titre.lua:2 : …`).
  Tests : `test_parse_errors.py`.

- **`g_ui_list_total` démarrait à 0** (`codegen/runtime_codegen/main_gen.py`). Un panneau
  « Liste » restait figé tant que le script n'appelait pas `list.set_count`, même avec des
  rangées visibles posées dans le canvas — contraire au propre texte de l'inspecteur de scène
  (« place text zones INSIDE this panel — ceux-là sont ce que la liste parcourt »). Le total
  démarre désormais au compte de rangées AUTHORÉES ; `list.set_count` garde son rôle pour dire
  un total plus grand que les rangées visibles (un inventaire qui défile), auquel cas il écrase
  le défaut. Tests : `test_ui_list_default_count.py`.
