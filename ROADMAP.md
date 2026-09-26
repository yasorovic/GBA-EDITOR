
# Roadmap

Ce document explique **le pourquoi** derrière les jalons qui restent à ouvrir : le scope,
les décisions déjà verrouillées avant même de commencer, et les questions volontairement
laissées ouvertes.

Une fois un jalon **livré**, son détail quitte ce fichier : la discussion complète (décisions
verrouillées, pièges rencontrés, mesures) part dans [changelog-archive/](changelog-archive/), un
fichier par version — ou par chantier, pour un [chantier technique](#chantiers-techniques). Un
jalon **produit** gagne en plus une ligne au [CHANGELOG](CHANGELOG.md) ; un chantier technique
n'y va jamais, il ne concerne que le code. Rien n'est perdu, ça change juste d'endroit — pour
rouvrir une décision passée, c'est là qu'elle est.

Six documents, six rôles :

| Fichier | Pour qui | Contenu |
| --- | --- | --- |
| [README](README.md) | un visiteur | une ligne par version |
| [CHANGELOG](CHANGELOG.md) | qui veut savoir ce qui a changé | une entrée courte par version livrée |
| [changelog-archive/](changelog-archive/) | qui rouvre une décision passée | le détail complet d'une version livrée |
| **ce fichier** | qui décide de la suite | scope, décisions, ouvert — jalons **non livrés** seulement |
| [ARCHITECTURE](ARCHITECTURE.md) | qui modifie le code | comment c'est construit |
| [Référence de scripting](docs/scripting-reference.md) | qui écrit un script | le Lua accepté, et ce qui ne l'est pas |

Convention : **Décisions verrouillées** = tranché, à implémenter tel quel — on ne rouvre
pas sans raison neuve. **Ouvert** = identifié mais volontairement non tranché : à rouvrir
quand le chantier démarre réellement, le contexte du moment valant mieux que des
suppositions faites à l'avance.

Un **jalon produit** porte un numéro (`vX.Y`) : il figure dans le tableau qui suit, et une fois
livré, une ligne rejoint le [README](README.md) — c'est ce qu'un visiteur vient chercher. Un
**chantier technique** n'en porte pas : né en cours de route (une question posée à
l'architecture, une dette relevée en marchant), il ne change rien pour qui joue au jeu produit
avec l'éditeur, seulement pour qui modifie le code. Il vit dans sa propre section,
[Chantiers techniques](#chantiers-techniques), à l'écart du tableau et du README — jamais
numéroté, jamais mélangé aux jalons produit.

---

## Où on en est

| Version | Sujet | État |
| --- | --- | --- |
| v0.2 | Palettes de couleurs | **Livrée**, quelques finitions — [archive](changelog-archive/v0.2.md) |
| v0.3 | Background vivant, texte et interface | **Livrée** — [archive](changelog-archive/v0.3.md) ; le balisage `[font=nom]` livré à part — [archive](changelog-archive/font-markup-reopened.md) |
| v0.4 | Animation de décor | **Livrée** — [archive](changelog-archive/v0.4.md) |
| v0.5 | Sauvegarde | **Livrée** — [archive](changelog-archive/v0.5.md) |
| v0.6 | Polish de la boucle de jeu | **Livrée**, rouverte pour le game feel — [archive](changelog-archive/v0.6.md) |
| v0.7 | Structures de données, et le langage | **Livrée**, les deux chantiers rouverts avec — [archive](changelog-archive/v0.7.md) |
| v0.8 | Son : la musique par scène, les transitions, le mixage | **Livrée** — [archive](changelog-archive/v0.8.md) |
| v0.14 | Diagnostic (trace de débogage, budget) | **Livrée**, réduite au frame+OAM (canaux/DMA non mesurables) — [archive](changelog-archive/v0.14.md) |
| v0.19 | Le sous-pixel | **Livrée** — [archive](changelog-archive/v0.19.md) |
| v0.24 | Le projet à l'échelle d'une équipe | **Livrée** — formats, build et chargement (paresseux + réconciliation incrémentale) — [archive](changelog-archive/v0.24.md) |
| v0.20 | L'état du monde : les collections persistantes | **Livrée** — [archive](changelog-archive/v0.20.md) |
| v0.23 | Ce qu'un boss demande | **Livrée** — [archive](changelog-archive/v0.23.md) |
| v0.21 | Le texte adressable : le dialogue piloté par la donnée | **Livrée** — [archive](changelog-archive/v0.21.md) |
| v0.22 | Menus, listes et curseur | **Livrée** — [archive](changelog-archive/v0.22.md) |
| v0.9 | Traduction des jeux | **Livrée** — [archive](changelog-archive/v0.9.md) |
| v0.10 | Distribution Linux | **Livrée** — format `.gba-project` et associations OS livrés — [archive](changelog-archive/v0.10.md) |
| v0.11 | Traduction de l'éditeur | **Livrée (infra)** — extraction UI, contrôles et choix de langue livrés ; la traduction FR elle-même est reportée au chantier « traduction fr » (v2.0) — [archive](changelog-archive/v0.11.md) |
| v0.12 | Vue d'ensemble (graphe des scènes) | **Livrée** — carte, groupes, notes, mini-carte, recherche, inspecteur d'arête, retargetage et création de scène ; création de transition ex nihilo, cibles calculées (`?`), routage anti-croisement et tracé libre reportés à v2.0 — [archive](changelog-archive/v0.12.md) |
| v0.13 | Édition mixte (appels d'API en blocs) | Non commencée |
| v0.15 | Visibilité des éléments d'interface | **Livrée**, sous une autre forme que prévu — [archive](changelog-archive/v0.15.md) |
| v0.16 | L'API : règle de construction et rangement | En cours — cinq renommages faits (`actor.get`/`actor.count`, `ui`→`interface`, `text.*_in`→`interface.*`) + `REMOVED_API` vidé + **rangement en 8 sections livré** (sidebar : navigation unique par nom, sous-titres, couche moteur repliée sous « Aller plus loin ») ; restent les items « Ouvert » (doc) ; **amendement du 2026-09-24** (proposé, non verrouillé) : module fabrique / type opère, clé `actor:` au lieu de `self:`, 25 fonctions à ranger (`list`, `interface.image_*`, `window`) |
| v0.17 | Le pool par scène | **Livrée le 2026-09-19** — pool déclaré sur la scène, budget OAM dérivé (`128 − posés − UI`) et compilation par scène, en sept tranches vérifiées au build ROM ; culling existence/OBJ reporté — [archive](changelog-archive/v0.17.md) |
| v0.18 | La valeur affichée : d'où elle vient | **Livrée** — première tranche (`$locale` dans les littéraux `text.draw`/`text.draw_in`, limite `!1`…`!9`), validée au build ROM ; extensions à d'autres sources reportées — [archive](changelog-archive/v0.18.md) |
| v0.25 | L'interface possède son chemin matériel | **Livrée** — [archive](changelog-archive/v0.25.md) |
| v0.26 | Les polices : sources, assets et aperçu | **Livrée** — [archive](changelog-archive/v0.26.md) |
| v0.27 | L'éditeur souffle le mot juste (autocomplétion) | **Livrée** — [archive](changelog-archive/v0.27.md) |

Les sept lignes qui suivent la v0.8 — de la v0.14 à la v0.22 — sont rangées dans leur **ordre
de traitement recommandé**, issu de la revue « projet de production » du 2026-08-19 et détaillé
dans sa section, juste après ce tableau : **v0.14 → v0.19 → v0.24 → v0.20 → v0.23 → v0.21 →
v0.22**. Les sept sont désormais livrées et archivées, v0.24 comprise. Les seuls jalons produit
encore ouverts sont **v0.13** et **v0.16** (v0.18 est livrée depuis le 2026-09-20, sa première
tranche) : sans priorité tranchée entre eux, ils restent dans leur ordre numérique, à la suite du
bloc priorisé.

Le chantier technique *La grammaire de la struct `Actor`* (voir
[Chantiers techniques](#chantiers-techniques)) ne vient pas de cette revue : il est né d'une
question posée à l'architecture le 2026-08-23 (« l'API C tient-elle les trois concepts de
l'éditeur ? »). Il se traite tôt malgré tout : il touche la struct que tous les jalons produit
manipulent, donc chaque jalon ouvert après lui est un jalon à ne pas migrer avant qu'il se
referme.

Un numéro de version reste une **identité**, pas un rang : il n'est pas renuméroté quand
l'ordre de traitement change. Seul l'ordre de LECTURE de ce document — et l'ordre dans lequel
les chantiers seront ouverts — suit désormais l'ordre de traitement.

---

## Correctifs (trouvés en marchant, hors chantier)

Des défauts réels, trouvés en marchant — la plupart en construisant et en jouant les projets
démo pendant le chantier v0.9, quelques-uns depuis — sans rapport avec un jalon en particulier,
consignés ici pour ne pas rester invisibles faute d'un jalon à qui les rattacher.

- **`g_actors[]` débordait l'IWRAM sur un projet multi-scène dense**
  (`codegen/runtime_codegen/main_gen.py`), révélé par le fixture `BuildBenchmark` : 120
  acteurs répartis sur quatre scènes n'emploient jamais plus de 30 entrées OAM simultanément,
  mais leurs tranches restent réunies dans une table runtime unique. Ses ~20 Kio, ajoutés au
  moteur, dépassaient les 32 Kio d'IWRAM et faisaient échouer l'édition de liens. Cette table
  est désormais émise en **EWRAM** (`EWRAM_DATA`, 256 Kio) ; les `TAG_*` et la sémantique des
  transitions ne changent pas. Le dimensionnement par scène, gain plus large déjà identifié
  pour v0.17, reste un chantier distinct.

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

---

## Frictions relevées en construisant la démo tactique (2026-09-20)

La démo tactique (type Advance Wars) est le **deuxième jeu de démo** exigé par la v1.0 — un
jeu de validation, dont le rôle est précisément de faire remonter ce sur quoi un projet non
trivial bute. La boucle complète a été construite et compile (grille + curseur, sélection,
stats pilotées par `data.Units`, portée surlignée par pool spawné, déplacement d'unité, menu
d'action, tour sauvegardé), assets 100 % auto-générés passés par le vrai pipeline d'import.
Voici les points de friction rencontrés en chemin, **par ordre d'importance** — ce ne sont pas
des bugs de la démo mais des manques de l'outil qu'elle a révélés. Les cinq premiers
toucheront TOUT projet non trivial, pas seulement ce genre. Les points 1 et 2 ont été
relevés en construisant la boucle ; le 2 a été confirmé par le **test d'échelle** (40 scènes /
200 sprites, cf. la note en fin de section).

1. ~~**Aucun moyen d'adresser un acteur dynamique.**~~ **Corrigé (2026-09-20).** `actor.get`
   accepte désormais un **index dynamique 1-based** en plus d'un nom littéral :
   `actor:get(i)` → `actor_at((i) - 1)` (repli 1→0 comme `data.Table[i]`), borné à la scène
   active et filtré par `actor_live` (nil hors bornes ou détruit). `actor:count()` rend le
   nombre d'acteurs posés — la borne de boucle. La cascade `if sel==1 then actor:get("Soldier1")…`
   devient `actor:get(sel)`, vérifié de bout en bout sur la démo. Décisions verrouillées :
   **1-based** (cohérent avec le langage) ; porte les acteurs **posés** de la scène active dans
   l'ordre d'authoring (l'ordre C correspond exactement) ; l'indexation des **pools spawnés**
   (`pool_at`) reste un chantier distinct différé. `runtime_api_inline.h` (`actor_at`,
   `g_scene_placed`), `main_gen` (pose `g_scene_placed` au scene_init), `scripting/codegen.py`,
   `scripting/api.py` (`actor.get`/`actor.count`). Tests : `test_actor_scene_naming.py`. Piste encore ouverte :
   les `exports_values` par instance (script exports) ne sont pas câblés au codegen — paramétrer
   une instance pour qu'elle se gère elle-même reste à faire.

2. **Les acteurs posés ne sont pas namespacés par scène.** Deux scènes qui posent chacune un
   acteur nommé « Cursor » (ou « Enemy », « Boss »…) collisionnent sur un seul symbole C :
   `actor_Cursor.c` de la seconde écrase celui de la première, et `TAG_CURSOR` est défini deux
   fois avec des valeurs différentes. Les prefabs et les scripts de scène, eux, SONT qualifiés
   (`<Scène>_<Prefab>`, `<Scène>_scene`) ; les acteurs posés font exception. Le validateur
   l'attrape et nomme le doublon (bien) — mais dans un jeu à 40 scènes, réutiliser un nom
   d'acteur par scène est le réflexe naturel, et l'auteur se retrouve à préfixer ses noms à la
   main. Relevé au **test d'échelle** : 40 scènes réutilisant « Cursor »/« U0 »… ont produit
   229 avertissements de collision, tous levés en préfixant par la scène. La qualification par
   scène (comme les prefabs) réglerait le réflexe (`codegen/runtime_codegen/headers.py`,
   `core/validator.py`).

3. **Un pool ne se vide ni ne s'itère.** Les marqueurs de portée spawnés n'ont ni `pool.clear()`
   ni parcours : chaque instance doit **sonder un global et s'auto-détruire**
   (`if global.range_on == 0 then self:destroy()`). Ce détour a façonné toute la machine à
   états du curseur (interdit de re-spawner tant que l'ancien lot vit). Attendu pour tout ce
   qui affiche puis efface un ensemble dynamique : portée de déplacement, cases d'attaque,
   curseurs multiples, projectiles à purger en fin de phase (`codegen/actor_budget.py`,
   runtime du pool par scène, ROADMAP v0.17).

4. **`text.draw_num` retiré : afficher un nombre coûte trois artefacts.** Un PV à l'écran
   impose de créer un global, une entrée de table de texte contenant `$global`, puis
   `text:draw(tx, ty, "clé")` après avoir posé le global. Pour un genre qui affiche *beaucoup*
   de chiffres (PV, dégâts, portées, or, niveaux), l'indirection est lourde et se répète à
   chaque valeur (`editor/scripting/api.py`, entrée retirée `text.draw_num`).

5. **Contention d'input entre le curseur et une liste active.** Une liste `active` consomme la
   croix directionnelle **automatiquement** chaque frame, pendant que le script du curseur la
   lit aussi : sans notion de « focus », les deux bougent au même appui. Il a fallu geler le
   curseur à la main (garde d'état). Tout jeu à plusieurs couches d'UI (menu + sous-menu +
   curseur de carte) rejouera ce conflit (runtime `ui_list_tick`, v0.22).

6. **Deux idiomes non évidents du transpileur, et une doc qui mentait.**
   ~~`actor:get(...):méthode()` en chaîne directe ne transpile pas (« invoke sur expression
   complexe ignoré »)~~ **Corrigé (2026-09-20)** : `_invoke` accepte désormais un receveur qui
   est une expression de type connu — un actor (`actor:get(...)`, `actor:spawn(...)`,
   `self.<enfant>`) ou une référence —, donc `actor:get("Foe"):move_to(p, 2)` marche sans local
   intermédiaire ; une expression sans type reste refusée. La docstring de `actor.get`, qui
   montrait la forme fautive, est corrigée. Tests : `test_lua_subset.py`
   (`test_get_actor_chaine_directe_une_methode`, …). **Reste** : un `vec2` ne se stocke toujours
   pas dans un local (`local c = …:get_position()` devient `int c = /* ignoré */`) — lire
   `self.position.x` **inline** ; et `get_position()` n'existe pas comme méthode (seulement la
   propriété `self.position`) (`editor/scripting/codegen.py` `_invoke`, `editor/scripting/api.py`).

7. **Pas de pose instantanée d'un acteur tiers.** Seul `self.position = …` est sûr ; l'écriture
   de propriété sur un handle (`u.position = …`) n'est ni documentée ni fiable. Un déplacement
   instantané d'une autre unité s'obtient par le détour `u:move_to(cible, 999)` (vitesse énorme
   pour ne pas étaler sur plusieurs frames), ce qui n'est pas son intention (`editor/scripting/api.py`
   `self:move_to`).

8. **Aucune API headless « builder le projet ».** Le codegen n'est pas exposé comme une simple
   fonction : il a fallu instancier `BuildWorker` (un `threading.Thread`/`EventEmitter`) et
   appeler `run()` en câblant les callbacks. Pire, `run()` **couple build et lancement mGBA** —
   en headless il a fallu sous-classer pour neutraliser `_step_launch_mgba`, sinon le worker
   rapporte `finished(False)` alors que la ROM est bel et bien produite. Il manque un point
   d'entrée « build seul, sans run », utile à la CI et à toute génération automatisée
   (`editor/codegen/rom_build.py`).

9. **Création programmatique d'un projet : pas de raccourcis, et un piège.** Ajouter un sprite
   depuis un PNG impose d'enchaîner soi-même `encode_sprite_asset` + `file_stamp` + `append` +
   `save` (les sidecars portent des champs calculés — `source_stamp`, palettes quantifiées,
   mapping de tuiles — donc rien à écrire à la main) ; rien n'expose ça comme une opération
   unique. Et `Project.create` écrit une `Scene_01` de starter **sur le disque** : remplacer la
   liste de scènes en mémoire ne l'efface pas, et le build recompile alors une scène fantôme —
   il faut `project.scenes.delete()` explicitement. Aucun chemin évident « remplace la scène par
   défaut » (`editor/core/project.py`, `editor/core/resources/asset_reconciliation.py`).

**Le test d'échelle (Temps 2) — le point « vérification à l'échelle » de la v1.0 est validé.**
Un projet généré de **40 scènes / 200 sprites** (assets auto-générés, scène de tension à 120
acteurs posés) passe de bout en bout. Mesures (VM de dev, `.venv-build312`) : `Project.open`
paresseux **≈190 ms** (**≈125 ms** à froid ensuite), `load_all_resources` **≈690 ms**,
`validate_project` **≈1,7 s**, build ROM complet **≈96 s**, ROM finale **388 Kio** (9,5 % d'une
cartouche 4 Mio). Le chargement paresseux (v0.24) tient l'échelle, le budget OAM dérivé
encaisse 120 acteurs sans fausse alerte, et rien ne s'effondre. La seule friction levée par ce
test est le point 2 ci-dessus (collision de noms d'acteurs entre scènes).

---

## Ce que la revue « projet de production » a relevé (2026-08-19)

Les six versions qui suivent viennent d'une seule séance : la relecture du logiciel du point
de vue d'un **projet cible** — un metroidvania à composante RPG (dialogues denses, arbre de
compétences, physique fine) et à combats de boss scénarisés (phases, projectiles, effets,
ambiance), mené par une **équipe de trois** : un programmeur, un sound designer, un pixel
artiste, avec une cartouche réelle au bout.

Ce ne sont pas des idées de fonctionnalités. Chacune est un point où ce projet-là **s'arrête**,
ou paie un prix qui ne se rattrape plus en fin de production. Elles passent avant la v1.0
parce que la v1.0 affirme « le logiciel absorbe un projet 2D de production », et qu'elle
déclare le platformer et le metroidvania « atteignables aujourd'hui » : la revue dit où c'est
faux.

**L'ordre recommandé n'est pas l'ordre des numéros** — un numéro est une identité, pas un
rang :

| Rang | Version | Pourquoi là |
| --- | --- | --- |
| 1 | **v0.14** — Diagnostic | Un combat de boss est l'endroit exact où le budget de frame se perd. Sans mesure, tout le reste se règle à l'aveugle. |
| 2 | **v0.19** — Le sous-pixel | Décide si le genre est faisable. Touche la structure `Actor` : plus il arrive tard, plus il casse de projets. |
| 3 | **v0.24** — Le projet à l'échelle d'une équipe | Les formats non fusionnables plafonnent l'outil au travail solitaire **dès la première semaine**, pas à la v1.0. |
| 4 | **v0.20** — Collections persistantes | Sans elle, l'état d'un monde metroidvania s'écrit à la main, une variable par coffre. |
| 5 | **v0.23** — Ce qu'un boss demande | Trois manques déjà connus, réunis par un seul cas d'usage. |
| 6 | **v0.21** — Le texte adressable | Débloque le dialogue dense ; la v0.9 (traduction) en dépend. |
| 7 | **v0.22** — Menus, listes et curseur | Le plus gros chantier, et le seul dont la forme reste ouverte. |

---

## Chantiers techniques

Un chantier technique ne livre rien de visible pour qui joue au jeu produit avec l'éditeur —
seulement une réécriture, une clarification ou une garantie côté code. Il n'apparaît ni dans le
[README](README.md) ni dans le [CHANGELOG](CHANGELOG.md), et ne porte pas de numéro `vX.Y` : une
fois refermé, son détail rejoint [changelog-archive/](changelog-archive/) comme n'importe quel
jalon, mais référencé par son nom plutôt que par un numéro.

| Chantier | Ouvert le | État |
| --- | --- | --- |
| La grammaire de la struct `Actor` | 2026-08-23 | **Livré** — [archive](changelog-archive/actor-struct-grammar.md) |
| Les trois couleurs de l'interface | 2026-08-24 | **Livré** — [archive](changelog-archive/three-colors.md) |
| `global.nom` / `const.nom` — l'accès pointé | 2026-09-01 | **Livré** — [archive](changelog-archive/global-const.md) |
| L'identité d'un asset et son fichier | 2026-09-02 | **Livré** — [archive](changelog-archive/asset-identity.md) |
| Les formats acceptés à l'import | 2026-09-03 | **Livré** — [archive](changelog-archive/import-formats.md) |
| La police, une palette d'asset comme les autres | 2026-09-03 | **Livré** — [archive](changelog-archive/font-palette.md) |
| L'écran construit à sa première visite | 2026-09-13 | **Livré** — [archive](changelog-archive/lazy-screen-build.md) |
| L'ouverture d'un projet, et l'écran blanc | 2026-09-13 | **Livré** — [archive](changelog-archive/open-white-screen.md) |
| Les palettes, rangées avec les assets | 2026-09-18 | **Livré** — [archive](changelog-archive/palettes-in-assets.md) |
| L'acteur appartient à sa scène | 2026-09-20 | **Livré** — [archive](changelog-archive/actor-scene-local.md) |
| Les exports de script, câblés au jeu | 2026-09-20 | **Livré (2026-09-21)** — les 10 types (int/float/bool/enum, string→TEXT_*, `*_ref`→index, vec2/vec3/rect) portent leur valeur d'instance au build (posé) et au spawn via table facultative (poolé) ; build/ROM headless vert, pli read-only vérifié au `nm`. Prolongement aux locals écarté (gcc -O2 le fait déjà). Voir [ci-dessous](#les-exports-de-script-câblés-au-jeu--paramétrer-une-instance) |
| L'API dit tout ce que l'inspecteur règle | 2026-09-23 | **En cours** — tranche 1 (acteur, sprite, collision) livrée le 2026-09-23, sauf `parent` et `sprite_name` — **la collision est rouverte le 2026-09-24** (boîte = référence typée, `collision_box.get_tile`) ; tranches 2 (caméra, scène, calque) et 3 (interface) à suivre. Voir [ci-dessous](#lapi-dit-tout-ce-que-linspecteur-règle) |
| Un seul type de script — le propriétaire donne le contexte | 2026-09-26 | **Livré (2026-09-26)** — refus au build (`self`, événements, fichier multi-familles, `self` en behavior), complétion contextuelle, `is_scene`/`hook_kind` remplacés par `owner_kind`/`has_self`. Voir [ci-dessous](#un-seul-type-de-script--le-propriétaire-donne-le-contexte) |
| Le cache de scène | 2026-09-16 | À ouvrir — voir [ci-dessous](#le-cache-de-scène-rouvrir-une-scène-déjà-visitée-sans-tout-redécoder) |
| L'écran resynchronisé à sa revisite | 2026-09-18 | **Livré (2026-09-20)** — [archive](changelog-archive/screen-resync-revisit.md) |
| Undo/redo des sidecars d'éditeur | — | À ouvrir — envisagé pour **V2**, voir [ci-dessous](#undoredo-des-sidecars-déditeur-annuler-la-création-dun-groupe-un-déplacement-de-nœud) |
| La struct `Actor` allégée — l'OAM au composant sprite | 2026-09-21 | À ouvrir — **décidé : à faire quoi qu'il arrive**, voir [ci-dessous](#la-struct-actor-allégée--lacteur-entité-légère-le-sprite-et-loam-deviennent-un-composant) |
| Préparer une image riche à l'import — recadrer, redimensionner | 2026-09-26 | **Livré (2026-09-26)**, validation à la souris dans l'éditeur à faire — voir [ci-dessous](#préparer-une-image-riche-à-limport--recadrer-redimensionner-sans-toucher-au-png) |
| Les inputs personnalisés — mini-langage d'actions et API d'historique | 2026-09-27 | **Conception posée, à valider** — voir [ci-dessous](#les-inputs-personnalisés--un-mini-langage-dactions-et-une-api-qui-lit-lhistorique) |

---

## Les inputs personnalisés — un mini-langage d'actions, et une API qui lit l'historique

### D'où vient la question (2026-09-27)

Une action d'input n'est aujourd'hui qu'un ET de boutons (`InputBinding.buttons`), saisi par dix cases
à cocher qui débordent déjà de la ligne. L'API ne sait dire que `held` et `pressed`. Ce qu'un
plateformer réclame en premier (relâcher = sauter moins haut, tampon de saut, appui long) et ce
qu'un jeu de combat réclame (séquences : quart de cercle + A) n'a aucune expression.

Décision de Victor : garder `held` / `pressed` **sans renommage**, ajouter `released`, `buffered`, la durée
de maintien en **argument optionnel de `held`**, les axes nommés, et remplacer les cases par **une barre
éditable** où l'action s'écrit dans un mini-langage (`+`, `-`, mouvements nommés).

### Le principe

Deux choses, une seule source de vérité chacune :

- **L'expression est le texte.** `InputBinding.expression: str` remplace `buttons`. Un parseur pur
  (`core/models/input_expression.py`) la transforme en `InputExpression` (liste de pas, un pas = un masque
  de boutons). L'éditeur (barre + aperçu), le checker et le codegen appellent CE parseur — il n'existe
  pas de seconde grammaire.
- **Le runtime ne garde que ce qu'il faut, sans état par action.** Deux structures globales, alimentées une
  fois par frame là où `_g_keys_held` est mis à jour :
  - **dix compteurs `u8`, un par bouton physique** : le nombre de frames consécutifs où il est tenu, saturé
    à 255. `held(nom, n)` en dérive EXACTEMENT : un accord est tenu depuis `n` frames si chacun de ses
    boutons l'est. 10 octets, pas d'historique pour l'appui long ;
  - **un anneau de masques `u16`** des derniers frames, pour `buffered` et les séquences (qui doivent
    remonter le temps). Sa profondeur est **calculée au build** à partir du projet — le plus grand entre les
    littéraux de `buffered` et l'étendue de chaque séquence (pas × fenêtre) — jamais plus de 255 : un jeu
    sans séquence ni tampon n'en paie pas.
  `released` ne lit que le masque du frame précédent. Aucune action déclarée ne coûte de RAM ; aucune ne
  coûte de CPU tant qu'un script ne l'interroge pas.

### Le mini-langage

```
expression := pas ( "-" pas )*          -- "-" : puis (séquence)
pas        := atome ( "+" atome )*      -- "+" : en même temps (accord)
atome      := bouton | direction | mouvement
```

| Famille | Jetons |
| --- | --- |
| Boutons | `a` `b` `l` `r` `start` `select` |
| Directions | `up` `down` `left` `right` |
| Mouvements (abrègent une séquence) | `quarter_circle_right` = `down - down + right - right` · `half_circle_right` = `left - down + left - down - down + right - right` · `dragon_punch_right` = `right - down - down + right` · et leurs trois versions `_left` (miroir) |

- Noms complets, minuscules, espaces libres, aucune abréviation (règle de nommage du projet, valeurs
  comprises). `right - right` dit « double appui », `down + a` dit « bas et A ensemble » : pas de jeton
  dédié.
- Un mouvement se lit comme une séquence de pas ; `+ bouton` derrière lui s'ajoute à son DERNIER pas
  (`quarter_circle_right + a`). Le mouvement s'écrit donc en premier : `a + quarter_circle_right` est refusé
  avec un message qui le dit.
- Un pas est satisfait quand TOUS ses boutons sont tenus (contient, pas exact) : `down + right` reste vrai
  si A est aussi tenu.
- Les atomes sont matériels seulement : une action ne référence pas une autre action (composition écartée —
  elle rendrait le parseur dépendant du projet et les cycles possibles).
- **Fenêtre entre deux pas** : 15 frames par défaut, réglable par action (champ « Fenêtre »,
  visible seulement quand l'expression est une séquence). Un réglage d'action, pas de la grammaire.

### L'API

Toutes les fonctions prennent le NOM d'une action ou d'un bouton (`DOMAIN_KEY`, inchangé). Toutes les durées
sont en frames et tiennent dans un `u8` (≤ 255) — le checker refuse un littéral au-delà.

| Appel | Vrai quand |
| --- | --- |
| `input:held(nom)` | l'accord est tenu ce frame (inchangé) |
| `input:held(nom, frames)` | l'accord est tenu depuis au moins `frames` frames consécutifs (appui long, tir chargé). `frames` omis = 1 |
| `input:pressed(nom)` | l'accord vient de devenir complet (inchangé). Pour une séquence : son DERNIER pas vient d'être pressé et les précédents se trouvent en amont, dans l'ordre, chacun dans la fenêtre |
| `input:released(nom)` | l'accord était complet au frame précédent et ne l'est plus (saut à hauteur variable) |
| `input:buffered(nom, frames)` | `pressed(nom)` a été vrai dans les `frames` derniers frames, celui-ci compris (tampon de saut), **et cet appui n'a pas déjà été consommé**. Répondre vrai CONSOMME l'appui : les appels suivants répondent faux jusqu'au prochain appui |
| `input:get_axis(x)` | rend −1, 0 ou 1 : la position de l'axe `x` (cf. ci-dessous) |
| `input:get_axis(x, y)` | rend un `Vec2` des deux axes (`get_axis("horizontal", "vertical")`) — la forme 2D de l'ancien `input.axis`. Le type du retour suit le NOMBRE d'arguments : le catalogue et le checker le portent, le codegen émet `input_get_axis` ou `input_get_vector` |

- **Une séquence ne se « tient » pas** : `held` et `released` sur une action-séquence sont refusés au
  build (« `held` n'a pas de sens sur une séquence — utiliser `pressed` »). Le matériel façonne le langage.
- **`input.axis` disparaît, absorbé par `get_axis`** (décision de Victor, 2026-09-27) : la croix devient
  deux axes PAR DÉFAUT, `"horizontal"` et `"vertical"`, fournis par l'application — non modifiables, non
  supprimables, présents dans tout projet (même vide). Un seul vocabulaire pour la croix et pour les axes
  du projet.
- **Signe** : `horizontal` > 0 vers la droite, `vertical` > 0 vers le BAS — la convention écran de tout le
  reste de l'éditeur (`self.y + get_axis("vertical")` descend), pas celle de Unity. Documenté.
- **Axe déclaré** : `InputAxis {name, negative, positive}`, chaque côté = nom d'action ou de bouton. Un axe est
  scalaire ; il permet de remapper la croix, ou de piloter un axe avec d'autres boutons, sans toucher au
  script. Un nom d'axe ne peut pas être `horizontal`/`vertical` (réservés) ; un nom d'axe et un nom
  d'action peuvent coexister (ce ne sont pas les mêmes appels).
- **Migration de l'API** : `input.axis` est retiré (pas d'alias), et ses usages du guide (`first-playable-scene`,
  `platformer-movement`, `decor-and-collision`) passent à `get_axis`.

### L'écran

- Une ligne = **nom** · **barre d'expression** (étirable) · retrait. Plus de cases.
- La barre : complétion des jetons (`QCompleter` — mêmes tables que le parseur), et sous elle un **aperçu**
  lisible (`↓ ↘ → ➜ Ⓐ`, `+` entre les boutons d'un accord, flèche entre les pas) qui prouve à l'auteur
  ce que le parseur a compris.
- Une expression invalide reste dans le champ, en rouge, avec le message et la colonne fautive ; elle est
  **conservée** dans le projet et **refusée au build** en nommant l'action (même contrat que « Un seul
  type de script » : on ne perd pas la saisie, on ne livre pas une ROM fausse).
- Un avertissement (non bloquant) quand deux actions ont la même expression.
- Le champ « Fenêtre » n'apparaît que pour une séquence.

### Décisions verrouillées (2026-09-27, Victor)

- `held` et `pressed` gardent leur nom ; `released` s'ajoute.
- La durée de maintien est l'argument optionnel de `held`, pas une fonction `held_frames`.
- `buffered(nom, frames)` et les axes nommés sont dans le chantier.
- L'expression est saisie dans une barre éditable à mini-langage (`+` accord, `-` séquence, mouvements nommés).
- `get_axis` unifie tout : `input.axis` disparaît au profit des axes par défaut `"horizontal"` et `"vertical"`.
  `get_axis(x)` rend un scalaire, `get_axis(x, y)` un `Vec2` — le second argument est optionnel. Pas de
  `get_vector`.
- **Fenêtre d'une séquence : un réglage de l'action** (champ dans sa ligne), pas un argument d'appel — la
  fenêtre est une propriété du mouvement, pas du site d'appel. 15 frames par défaut.
- **Toutes les durées tiennent dans un `u8`** (1 à 255 frames ≈ 4 s) ; au-delà, le build refuse.

### Proposé, à valider avant le code

- Le jeu de mouvements : six (quarts de cercle, demi-cercles, dragon punch), chacun dans ses deux sens. Ajouter
  un mouvement, c'est une ligne dans la table.
- **`buffered` consomme quand il répond vrai** (idée de Victor, 2026-09-27). Sans cela, un appui reste vrai
  N frames et peut faire re-sauter le personnage qui retouche le sol (plafond bas, rebond). Le runtime ne sait
  pas si le script a « agi », mais il sait qu'il a répondu vrai — cela suffit. État : **un `u8` par action
  interrogée par `buffered`** (âge depuis la dernière consommation, saturé à 255, incrémenté à chaque frame),
  alloué par le codegen qui connaît statiquement ces actions ; les autres n'en paient pas. Un appui n'est
  éligible que s'il est plus récent que la dernière consommation.
  **Le piège devient l'ordre d'évaluation** : `if input:buffered("jump", 6) and au_sol` consomme l'appui
  même en l'air, et le tampon est perdu ; il faut écrire `if au_sol and input:buffered("jump", 6)` (le
  `and` court-circuite, `buffered` n'est évalué qu'au sol). Documenté dans `scripting.md` avec cet exemple ;
  le checker ne peut pas le détecter de façon fiable. Deux scripts qui interrogent la même action se
  partagent l'appui : le premier à répondre vrai le prend.

### Ce que ça ne fait pas

- Pas de composition d'actions, pas de parenthèses, pas d'alternatives (`a | b`) : les deux se
  contournent par deux actions.
- Pas de remappage des boutons par le joueur au runtime (le GBA n'a que 10 boutons).
- Pas de remplacement des dix `on_button_*` avant la tranche finale (cf. plus bas) : ils dépendent du
  runtime livré.

### Ce que ça touche

- `core/models/settings.py` : `InputBinding.expression` (+ `window`), `InputAxis` ; `from_dict` tolérant
  (`buttons: [a, b]` → `"a + b"`), pour ne casser aucun projet existant.
- `core/models/input_expression.py` (nouveau) : parseur, tables de jetons et de mouvements.
- `scripting/api.py` : `input.released`, `input.buffered`, `input.get_axis`, `held` à 2e paramètre optionnel ;
  `scripting/checker.py` (`_check_key`, bornes des frames, refus `held`/`released` sur séquence) ;
  `scripting/codegen.py` (`input_masks` → masque OU index de séquence).
- `runtime/include/runtime_api_inline.h` + point de mise à jour de `_g_keys_held` : l'anneau et les lecteurs ;
  sonde C (comme `text_layout`) pour prouver l'équivalence Python ↔ C du parseur/matcheur.
- `ui/scene_manager/inspectors/inputs_card.py` (refonte), nouvelle carte d'axes, `project_settings_dialog.py`,
  `labels.json` + `labels_fr.json` ; `docs/scripting.md`, `api_reference.json` régénéré.

### Ordre d'implémentation

1. Parseur pur + tests (grammaire, mouvements, erreurs, migration `buttons`).
2. Runtime : anneau, `released`, `held(n)`, `buffered`, séquences ; sonde C.
3. Catalogue + checker + codegen ; build ROM headless d'un projet de test.
4. Écran : barre, aperçu, fenêtre, carte d'axes.
5. Docs, puis suppression de `buttons` (l'ancien sort avant de dire « terminé »).
6. Tranche finale : les événements `on_button_*` (ci-dessous).

### Tranche finale — les dix `on_button_*` disparaissent, le déclencheur SoundFx vise les actions

À faire APRÈS le runtime, car le déclencheur SoundFx réutilise `pressed(nom)`.

**Constat (2026-09-27).** Les dix noms `on_button_*` servent deux mécanismes : des événements de script
(`function on_button_a()`, front montant, appelés sur les acteurs de la scène et la racine des prefabs
poolés, cf. `_BTN_MAP` de `main_gen.py`) et la liste des déclencheurs du SoundFxComponent
(`SFX_AUTO_TRIGGERS`).

**Décision (recommandée, à confirmer par Victor avant de coder) :**

- **Les événements de script sont supprimés.** Ils dupliquent `if input:pressed("a")` dans `on_update`,
  ne voient que les dix boutons physiques (ni action, ni séquence, ni `released`), encombrent le panneau
  Events (10 entrées sur ~20), et ne valent que pour les acteurs et racines de prefab. Aucun `.lua`, doc ou
  démo du dépôt ne les utilise. Un script qui en définit encore un est **refusé au build**, avec un message
  qui renvoie à `input:pressed(nom)` dans `on_update`.
- **Le déclencheur SoundFx est gardé, mais vise les actions.** C'est le seul vrai gain (un item de menu qui
  joue un son sans une ligne de Lua). Son champ `trigger` devient « manuel » ou un NOM d'action ou de bouton — la
  même liste que `input:pressed(nom)` — et se déclenche quand `pressed(nom)` devient vrai : un combo ou une
  séquence marche donc aussi. Migration : `on_button_a` → `"a"`, `on_button_up` → `"up"`, etc., à la
  lecture du projet.
- **Disparaissent** : les dix entrées de `EVENT_REGISTRY` (`scripting/api.py`), `_BTN_MAP` et ses boucles
  (`main_gen.py`), `SFX_AUTO_TRIGGERS` (`core/models/components.py`), les dix libellés `comped.trig_*` du
  `component_editors/sfx.py` (remplacés par un choix dans la liste des actions).

---

## Préparer une image riche à l'import — recadrer, redimensionner sans toucher au PNG

### D'où vient la question (2026-09-26)

Une photo de 474×314 importée en tuilé 8bpp donne 2194 tuiles uniques pour un budget de 256 : le
Background Editor le **dit** (avertissement rouge « Exceeds VRAM ») mais ne laisse rien faire —
l'auteur n'a que le mode (tuilé/bitmap, profondeur) et un logiciel externe. Et le tuilé tronque
l'index de tuile à 10 bits (`pack_se`), donc au-delà de 1024 la carte se brouille en silence.

### Le principe

Deux gestes sur la **préparation de la source**, avant l'encodage, portés par le sidecar :

- **Recadrer** (`import_crop`, en pixels de la source) puis **redimensionner** (`import_size`, en
  pixels de l'image préparée), dans cet ordre ;
- le PNG n'est **jamais** modifié : `prepare_source` produit une image PIL en mémoire, que
  reçoit `encode_by_mode` — l'unique endroit qui choisit l'encodeur. Tous les chemins qui
  encodent (recompression de l'inspecteur, import, resynchronisation d'un PNG retouché,
  réconciliation au chargement) lisent la MÊME préparation, sinon la ROM et l'éditeur
  divergeraient ;
- revenir en arrière = effacer la préparation (bouton « Original »), le PNG étant intact.

### Décisions verrouillées (2026-09-26)

- **Barre du canvas** : deux bascules exclusives (Recadrer / Redimensionner) et une action
  (Original), dans la même `CanvasTopBar` que les autres canvas.
- **Redimensionner** : libre au pixel ; **Maj** = proportionnel ; **Ctrl** = accroche 8×8.
- **Recadrer** : libre au pixel ; **Maj** = garde les proportions de l'image d'origine ; **Ctrl**
  = accroche 8×8.
- **Rééchantillonnage automatique** : plus proche voisin si le PNG source est indexé (palette
  préservée), Lanczos sinon — aucun réglage exposé.
- **Fonds de scène seulement** : un cadre d'UI ou une planche d'animation ont une géométrie qui
  dépend des pixels d'origine (marges, grille de frames).
- La taille affichée par le Scene Manager suit la taille **préparée** (`pixel_size()`), plus celle
  du PNG.

### Mesurer le 4bpp avant d'y passer (2026-09-26)

Bouton « Analyser pour le 4bpp » dans l'inspecteur, sur l'image **préparée**, hors-thread :
couleurs par tuile (min / moyenne / max et répartition), tuiles qui tiennent en 15 couleurs,
jeux de couleurs distincts et tuiles qui en partagent un, palettes nécessaires, verdict « sans
perte » ou non. `bg_import.analyze_tile_colors` réutilise l'extraction et le packing de la
compression : le chiffre annoncé est celui que la compression trouvera. Les palettes comptées
sont celles des tuiles qui tiennent, sans la réduction — un minimum, pas une promesse.

### Jouer avec la compression — l'inspecteur contextuel (2026-09-26)

L'auteur règle la compression avec des curseurs et voit le rendu au canvas ; un réglage relance
l'encodage hors-thread après 250 ms. **L'inspecteur est contextuel** : chaque mode (tuilé
4bpp / 8bpp, bitmap 8 / 16bpp) a sa boîte de réglages, absente des autres. Aucun refus d'office :
une image hors budget s'encode quand même, et les mesures disent ce que ça coûte.

**Tranche 1 — tuilé 4bpp (livrée).** Réglages portés par le sidecar (`BackgroundAsset.compression`,
seuls les écarts au défaut sont écrits) :

- **Palettes** (1–16) et **couleurs par palette** (2–15). Sans perte quand l'image le permet (pixel art :
  packing exact) ; sinon `core/bg_palette_cluster.py` regroupe les tuiles qui se ressemblent, taille une
  palette par groupe depuis ses pixels réels et affine — l'ancienne méthode (garder les 16 palettes les
  plus employées, renvoyer le reste au plus proche) laissait l'océan d'une photo sans ses bleus, même
  au réglage par défaut ;
- **Couleurs globales** : réduire toute l'image avant le découpage en tuiles — c'est ce qui rend
  les tuiles voisines compatibles, donc ce qui fait rentrer une photo (le 4bpp par défaut y perd
  la moitié de l'image) ;
- **Tuiles** : cible de tuiles uniques ; `core/bg_tile_merge.py` regroupe par **plus faible perte**
  (agglomération de Ward, coût pondéré par les cases couvertes, distance qui pèse la luminance),
  garde la tuile la plus centrale de chaque groupe et renvoie les autres cases vers la variante
  gardée la plus proche. Le premier essai — garder « les plus employées » — écrasait le bas de
  l'image : sur une photo toutes les tuiles sont employées une fois, et l'égalité tombait sur
  l'ordre de balayage. Reste à explorer : réutiliser une tuile sous une autre banque de palette ;
- **Méthode** de réduction dans une tuile, et le **dithering** (agit sur la réduction globale).

**Tranche 2 — tuilé 8bpp (livrée).** Même boîte, contextuelle : **Couleurs** de l'unique palette
(2–255, `palette_colors`), **Tuiles** (la même fusion par plus faible perte, budget 256 par charblock),
**méthode** de quantification (median-cut, octree, couverture max — quantifieurs de PIL) et
**dithering**. Le dithering des modes 8bpp et bitmap était sans effet : `Image.quantize(dither=…)`
ignore l'option tant qu'on ne lui donne pas de palette. Corrigé pour les deux (`_quantize_rgb`),
test à l'appui. Reste la tranche bitmap : son propre panneau.

### Ce que ça ne fait pas

Pas d'annulation pas-à-pas (Ctrl+Z) : la recompression est asynchrone et « Original » suffit à
revenir. Pas de réglage de couleurs (le mode et la profondeur existent déjà dans l'inspecteur).

---

## Les exports de script, câblés au jeu — paramétrer une instance

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
- Tests : `tests/test_script_owner.py`. Les quatre projets de démo ne produisent aucun nouveau refus.

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
   Tests : `tests/test_export_values_codegen.py`.
2. **Résolution du nom.** ✅ **Déjà couvert** par l'émission existante : un export est un local
   top-level nommé (émis `static int <nom> = …` pour un posé), donc une référence nue `<nom>` dans le
   corps du script résout vers cette variable sans travail supplémentaire. Reste la SÛRETÉ du nom
   (collision) — c'est l'étape 3 (checker).
3. **Checker.** ✅ **Fait.** `_check_export_names` **refuse** (erreur) un nom d'export qui masque un
   champ fixe d'`Actor`, un global, ou un namespace/fonction d'API — la contrepartie du nom nu. Un
   type dont la valeur d'instance n'est pas encore câblée (string/refs/composites ; int/float/bool/enum
   le sont) donne un **avertissement non bloquant** (le défaut du script s'applique), pas un refus —
   pour ne pas casser un projet existant. Tests dans `tests/test_export_values_codegen.py`.
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
spawns runtime. **Décidé avec Victor (D2) :**

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
3. **Stockage.** ✅ **Fait.** Uniformisation décidée avec Victor : sur un prefab poolé, TOUT export de
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

**Décisions verrouillées avec Victor (2026-09-21) :**

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
(collecte des littéraux d'export string). Tests : `tests/test_export_values_codegen.py` (résolveur
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

---

## L'API dit tout ce que l'inspecteur règle

### D'où vient la question (2026-09-23)

Vérification faite : plusieurs champs édités dans un inspecteur n'avaient aucune porte côté Lua
(`screen_space`, les boîtes de collision, le mode de caméra, le défilement de scène, tout l'habillage
des éléments d'interface…). Un auteur qui règle une chose à l'éditeur ne peut ni la lire ni, quand le
matériel le permet, la changer en jeu.

### La règle

Tout champ d'inspecteur a une porte dans l'API, et la porte dépend de ce que le runtime sait faire :

- **modifiable au runtime** → propriété (ou fonction, si elle est INDEXÉE) en lecture ET en écriture ;
- **fixé au build** (l'écrire n'aurait aucun effet, ou changerait l'allocation du matériel) →
  **lecture seule**, pour qu'un script puisse s'y adapter sans dupliquer la valeur.

La forme suit la grammaire existante (état → propriété ; requête indexée → fonction ; cf.
ARCHITECTURE.md « La grammaire de l'API »). Aucun mécanisme nouveau.

### Décisions verrouillées (2026-09-23)

- **Trois tranches**, chacune livrée, testée et documentée avant la suivante : (1) acteur + sprite +
  collision ; (2) caméra + scène + calque de fond ; (3) éléments d'interface.
- **Boîtes de collision** : ~~adressées par leur tag, en requêtes indexées~~ — **rouvert le
  2026-09-24**, voir [l'amendement ci-dessous](#amendement-2026-09-24--la-boîte-de-collision-devient-une-référence-typée).
  La forme initiale (`self:box_rect("hitbox")`, `self:set_box_solid(...)`) avait écarté l'idée
  `self:box("tag").w` parce qu'une propriété sur une boîte exige un TYPE de référence dans le
  checker et le codegen. Ce coût est maintenant accepté : la boîte est un composant à part entière
  (id, tag, active, solid, offset, size), elle mérite son propre objet et son propre module.
- **Interface** : décision remplacée par l'amendement v0.16 du 2026-09-25 : le singleton
  `interface` acquiert un élément typé (`interface:get("Nom")`) ; l'élément porte ses
  propriétés et méthodes. Les fonctions qui recevaient un nom d'élément en premier argument
  migrent avec la surface décrite dans « Interface — singleton et éléments typés ».

### Amendement (2026-09-24) — la boîte de collision devient une référence typée

Le type `collision_box` rejoint `REF_TYPES` (à côté de `sfx`). Un script obtient une boîte par son
tag ; le tag reste la CLÉ de la boîte, donc lecture seule.

```lua
local hb = self:collision_box("hitbox")   -- nil si l'acteur n'a pas de boîte de ce tag
hb.active = false                         -- bool
hb.solid  = false                         -- bool : arrêtée par la carte de collision, ou déclencheur
hb.offset = vec2(8, -4)                   -- décalage relatif au pivot du sprite (valeur immuable)
hb.size   = vec2(12, 8)                   -- largeur, hauteur
local r = hb.bounds                       -- rect MONDE (position + offset + taille), lecture seule
if hb:overlaps(other) then ... end        -- `other` : un acteur OU une autre boîte
hb.is_grounded                            -- bool, lecture seule : cette boîte repose-t-elle sur le sol ?
local t = hb:get_collision_tile(x, y)     -- type de tile de collision au point monde (x, y)
```

| Porte | Nature | Remplace |
| --- | --- | --- |
| `self:collision_box(tag)` | constructeur de référence, `nil` possible | — |
| `hb.tag` | lecture seule | la clé des anciens appels |
| `hb.active` | modifiable — **champ à créer au runtime** : la résolution contre la carte et le test de chevauchement doivent l'ignorer quand il est faux | (aucune porte) |
| `hb.solid` | modifiable | `self:box_solid` / `self:set_box_solid` |
| `hb.offset`, `hb.size` | modifiables, bornés (offset −128..127, taille 0..255) | `self:box_rect` / `self:set_box_rect` |
| `hb.bounds` | lecture seule, rect monde | le calcul que chaque script refaisait |
| `hb:overlaps(other)` | méthode, bool | — |
| `hb.is_grounded` | lecture seule, bool | (aucune porte par boîte) — `self.grounded` reste, et en est le OU |
| `hb:get_collision_tile(x, y)` | méthode, requête indexée (point monde ABSOLU) | `tile.get` (la carte lue est la carte de collision ; le verbe `get` est juste ici : le tile n'est pas un champ de la boîte) |
| `self.box_count` | lecture seule, inchangée | — |

`overlaps(other)` prend un acteur (« ma hitbox touche-t-elle N'IMPORTE QUELLE boîte de cet
acteur ? ») ou une autre boîte (« ... précisément sa hurtbox ? ») — la même distinction que
`on_collide(other, my_box, other_box)`. `touches_tile` a été écartée : `hb:get_collision_tile` sur
`hb.bounds` fait la même chose sans nouvelle action. Le point de `get_collision_tile` est absolu : la
boîte sert de porte d'entrée (une boîte absente répond 0) mais ne relativise rien.

Ce que le chantier ajoute, hors renommage : des **propriétés sur une référence** (jusqu'ici une
référence n'a que des méthodes — `sfx`, élément d'interface). Le checker doit typer la lecture et
l'écriture `ref.champ`, refuser l'écriture d'un champ lecture seule, et le codegen émettre les
`actor_get/set_box_*` existants. Les quatre fonctions `self:box_*` sont **supprimées** à la livraison
(pas d'alias), de même que `tile.get`.

**Livré (2026-09-24)** : le type `collision_box`, ses six propriétés, `hb:overlaps(x)`,
`hb:get_collision_tile(x, y)`, `hb.is_grounded` ; `self:box_rect`, `self:set_box_rect`, `self:box_solid`,
`self:set_box_solid` et `tile.get` sont **supprimées**, sans alias. Ce que le chantier a demandé en plus :

- **`active` existe désormais au runtime** (`CollisionBox.active`). La case de l'inspecteur n'en fixe que
  l'état de DÉPART : une boîte inactive au départ est émise quand même (ROM et tags), parce qu'un script
  peut l'allumer. Les filtres de build (`actor_box_tags`, `has_solid_box`, `collision_tags`) ne lisent
  plus `active`. La résolution contre la carte, `actors_overlap_boxes` (donc `on_collide`) et
  `overlaps` l'ignorent tant qu'elle vaut 0.
- **Bug trouvé en route, corrigé** : `box_overlap` recevait les positions d'acteur en Q8 (v0.19) et les
  comparait à des offsets en pixels — deux boîtes à 5 px ne se voyaient pas comme se chevauchant, donc
  `on_collide` / `on_collision_enter` ne se déclenchaient qu'à moins d'1/256 de pixel. Régression tenue
  par la sonde native (`overlap_5px`, `actors_overlap`).
- **La référence est un entier** (rang de l'acteur × `MAX_BOXES` + rang de la boîte + 1, 0 = absente),
  comme le handle d'un `sfx` : `if not hb` compile en `!hb`. Les propriétés d'une référence passent par
  `resolve_prop(expr, ref_types)`, sans jamais retomber sur les champs d'actor (`hb.tag` n'est pas
  `self.tag`). Le renommage d'un tag suit aussi `hb.tag == "hitbox"` (`refactor._iter_prop_refs`).
- **Vérifié** : sonde native (`actor_box_probe.c`), `test_inspector_api_parity.py`, et un build ROM complet
  sur une copie d'OrbitTest (deux boîtes sur la tourelle dont une inactive au départ, une sur Moon, script
  utilisant toute l'API) — `rom.gba` produite.

### Tranche 1 — acteur, sprite, collision

| Champ d'inspecteur | Porte Lua | Nature |
| --- | --- | --- |
| Actor `screen_space` | `self.screen_space` | lecture seule (le C émis diffère selon la valeur) |
| SpriteComponent `affine_transform` | `self.affine` | lecture seule (réserve un slot OAM au build) |
| CollisionBox `x, y` | `hb.offset` (`hb = self:collision_box(tag)`) | modifiable |
| CollisionBox `w, h` | `hb.size` | modifiable |
| CollisionBox `solid` | `hb.solid` | modifiable |
| CollisionBox `active` | `hb.active` | modifiable (champ runtime à créer) |
| CollisionBox `tag` | `hb.tag` ; `self.box_count` | lecture seule |

**Livré (2026-09-23)** : les sept portes du tableau, la sonde C `tests/native/actor_box_probe.c`, 
`tests/test_inspector_api_parity.py`, un build ROM complet sur une copie d'OrbitTest (boîte « hitbox » 
ajoutée à la tourelle, script utilisant les sept portes). Le renommage d'un tag de collision 
(`RenameCollisionTagCmd`) réécrit maintenant aussi les scripts.

Le re-parentage (`parent`) et le changement d'asset de sprite (`sprite_name`) sont **explicitement
laissés lecture-seule-à-venir** : ni l'un ni l'autre n'a de trace runtime aujourd'hui (la hiérarchie
est composée au build), leur porte demande un champ par acteur. À trancher avant d'être ouverts.

---

## Un seul type de script — le propriétaire donne le contexte

### D'où vient la question (2026-09-26)

Les scripts se présentent en plusieurs « types » (scène, caméra, acteur/prefab, behavior) qui ont tous
accès à la même API. Vérification faite : le type n'est jamais saisi, il est déduit de l'attache, et
`self` n'existe déjà que pour un acteur ou un prefab (`CodegenContext.has_self` côté codegen). Ce qui distingue
réellement ces « types » appartient au **propriétaire**, pas au script : le jeu d'événements admis, le
symbole C émis, le stockage par instance d'un prefab poolé. Unity et Godot n'ont, eux aussi, qu'un seul
concept de script.

### La règle

Un script est un fichier Lua. Son contexte vient de ce à quoi il est attaché.

- `self` désigne sans ambiguïté l'instance à laquelle le script est attaché, et n'est admis que pour un
  script attaché à un acteur ou à un prefab. Partout ailleurs, `self` est une **erreur**.
- Le « type » est un attribut **dérivé**, jamais choisi par l'auteur.
- Le **behavior** reste : c'est un module (`require`), sans propriétaire ni événements. `self` y est
  refusé ; l'acteur passe en paramètre.

### Décisions verrouillées (2026-09-26)

1. **Un fichier, une famille de propriétaire.** Attacher le même script à des propriétaires de familles
   différentes (par exemple un acteur et la scène) est **refusé au build**, avec une erreur nommant les
   deux attaches. On n'autorise pas ce cas au prix d'un `self` ambigu : ce serait de la complexité.
2. **Les événements sont validés par propriétaire.** `on_collision_enter` dans un script de caméra reste
   refusé au build. L'éditeur le **filtre en amont** : l'auto-complétion ne propose que les événements de
   la famille du propriétaire du script édité, et les modèles de nouveau script suivent le même critère.
3. **Le behavior est conservé** comme module distinct.

### Ce que ça touche

- `scripting/codegen.py` / `checker.py` : `is_scene` et `hook_kind` deviennent une notion de
  propriétaire ; erreur explicite sur `self` hors acteur/prefab ; refus de l'attache multi-familles.
- `scripting/completion.py` : filtrage des événements selon le propriétaire (la fonction lit déjà un
  `context` actor/scene/behavior/camera/unknown).
- `scripting/script_templates.py` : le `kind` saisi devient « ce que l'éditeur propose selon l'endroit de
  création ».
- Docs : `docs/scripting.md`, `docs/scripting-reference.md`, `ARCHITECTURE.md`.

Le comportement des projets valides ne change pas ; seuls les cas déjà ambigus deviennent des erreurs.

---

## Le cache de scène — rouvrir une scène déjà visitée sans tout redécoder

### D'où vient la question (2026-09-16)

Victor : sélectionner une scène dans le project viewer prend une demi-seconde perceptible, même
pour une scène triviale (title screen, deux zones de texte). Trois causes indépendantes trouvées
en investiguant `window._on_scene_selected` ([window.py:1128](editor/window.py:1128)) :

1. **Corrigé (2026-09-16).** `AssetsFinderPanel.refresh()` reconstruisait les 3 arbres (Scenes,
   Prefabs, Scripts) à chaque clic, alors que rien n'y change quand on change simplement de scène
   active. Remplacé par un simple surlignage de la scène active, sans repeuplement —
   `highlight_active_scene` ([assets_finder_panel.py](editor/ui/scene_manager/assets_finder_panel.py)),
   posé sur `AssetFinder.highlight_selection` déjà existant.
2. **Pas de bug.** `_refresh_diagnostics` → `validate_project` → `project.load_all_resources()`
   ([validator.py:126](editor/core/validator.py:126)) est déjà gardé par
   `_deferred_resource_collections` ([project.py:339](editor/core/project.py:339)) : le coût réel
   (stat + hash de tout le catalogue) n'est payé qu'à la toute première scène ouverte d'une
   session ; ensuite chaque `load_*` est un test d'ensemble vide, donc quasi gratuit.
3. **Ce chantier.** `SceneEditor.load_project` ([scene_canvas.py:721](editor/ui/scene_manager/scene_canvas.py:721))
   reconstruit le canvas ENTIER à chaque sélection — y compris en revenant sur une scène déjà
   visitée dans la même session, où rien n'a changé :
   - `compose_frame_image` ([sprite_compose.py:15](editor/core/sprite_compose.py:15)) rouvre et
     redécode depuis le disque le PNG source du sprite pour CHAQUE acteur, à CHAQUE visite —
     aucun cache, même quand le fichier n'a pas bougé depuis la visite précédente.
   - `bg_pixmap` / `BgLayerRaster.render` ([canvas_raster.py:171](editor/ui/scene_manager/canvas/canvas_raster.py:171))
     recompose le rendu tuile par tuile du fond à chaque visite. Le tileset lui-même est déjà en
     mémoire (`BackgroundAsset`, pas de disque ici), mais le raster complet est refait à zéro.
   - `_reload_ui_regions` / `set_ui_regions` ([canvas_scene.py:440](editor/ui/scene_manager/canvas/canvas_scene.py:440))
     détruit et recrée tous les items d'interface et recalcule les couleurs de banque
     (`_compute_bank_colors`, documenté à ~15 ms/région) à chaque visite.

### Ce qu'il faudrait trancher avant d'ouvrir

- **Quoi cacher, précisément.** Deux formes envisagées avec Victor, pas encore choisies :
  - un cache des **décodages disque** purs (PNG source des sprites/fonds), invalidé par mtime —
    la composition par frame/scène (flips, palette, overrides live) continue de tourner à chaque
    visite. Scope net, risque faible : rien ne peut devenir périmé, seul le pixel brut du fichier
    est mémorisé, jamais un résultat qui dépend de l'état vivant du projet.
  - un cache du **canvas complet par scène** (QGraphicsScene/items déjà construits), pour rouvrir
    une scène visitée sans rien recalculer, même pas le raster de palette/bank colors. Gain plus
    net, mais très invasif (`SceneEditor.load_project` en profondeur) et risque de
    désynchronisation si un asset ou une palette change pendant que la scène est en cache
    (édition d'un sprite ou d'une palette depuis un autre écran) — demanderait une invalidation
    explicite, pas seulement un mtime.
- **Recouvrement avec CanvasRework.** Le chantier de refonte du canvas est en cours (`scene_graph`,
  `scene_graph_state`, non encore committés à l'ouverture de cette entrée) : ouvrir un cache de
  scène avant que cette refonte se stabilise risque de dupliquer le travail ou de mettre en cache
  un état que CanvasRework va remplacer. À revérifier au moment d'ouvrir.
- **Mesurer avant de trancher.** Aucune mesure chiffrée prise pour l'instant, seulement une lecture
  de code — profiler `load_project` sur un projet réel donnerait la vraie proportion entre
  décodage sprite, raster de fond et reconstruction des régions UI, plutôt que de deviner laquelle
  des trois mérite le cache en premier.

---

## Undo/redo des sidecars d'éditeur — annuler la création d'un groupe, un déplacement de nœud

### D'où vient la question (2026-09-16)

En revue du chantier « groupes du Graphe de scènes » (créer/supprimer/renommer un groupe, y ranger
des scènes, déplacer et redimensionner les boîtes, déplacer les nœuds), Victor a demandé de
vérifier que **toutes** les opérations introduites étaient reliées à undo/redo. Constat :

- **Reliée.** La *suppression de scène* (clic-droit du Graphe) pousse `DeleteResourceCmd` dans
  l'historique — exactement la commande du project viewer. C'est une vraie mutation de `Resource`.
- **Non reliées, et à dessein.** Tout le reste — créer / supprimer / renommer / colorer un groupe,
  ranger une scène (`move_member`), déplacer une carte, déplacer ou redimensionner un cadre —
  écrit dans **deux sidecars d'éditeur** : `AssetFolderStore` (les groupes, partagés viewer ↔
  Graphe) et `SceneGraphState` (positions des nœuds, géométrie des cadres). Aucun ne passe par
  `get_history()`. Les opérations de dossiers du project viewer n'y sont **jamais** passées non
  plus, avant ce chantier — ce n'est pas une régression.

### Pourquoi ce n'est pas un simple oubli

Deux obstacles durs empêchent de brancher naïvement ces gestes sur l'historique existant :

1. **L'historique est PAR SCÈNE et vidé à chaque changement de scène ou d'écran**
   ([window.py:878](editor/window.py:878), [window.py:1135](editor/window.py:1135)). Créer ou
   déplacer un groupe est une action *projet*, pas *scène* : on créerait un groupe, on cliquerait
   une autre scène dans le viewer → `_history.clear()` → l'entrée « annuler le groupe » aurait déjà
   disparu. Un undo qui ne survit pas au prochain clic de scène est pire que pas d'undo.
2. **Ces sidecars ne changent ni le jeu, ni le build, ni le JSON de gameplay** (cf. en-tête de
   [asset_folder_store.py](editor/core/asset_folder_store.py)) : un dossier ne fait que choisir le
   parent visuel d'un asset, une position n'existe que pour l'œil. L'historique actuel sert les
   mutations du modèle, pas la présentation.

### Ce qu'il faudrait trancher avant d'ouvrir

- **Un stack undo DÉDIÉ, projet-wide.** Distinct de `get_history()`, non vidé au changement de
  scène ni d'écran, tant que le projet reste ouvert. C'est le cœur du chantier : sans lui, aucune de
  ces opérations n'est annulable de façon fiable.
- **Le conflit de Ctrl+Z.** Deux piles undo (modèle per-scène vs organisation projet) réclament la
  même touche dans le Scene Manager. Décider laquelle répond — selon le focus (Graphe/viewer vs
  canvas), selon le dernier geste, ou une pile unifiée — sans que Ctrl+Z devienne imprévisible.
- **Réversibilité de la suppression de groupe.** `delete_folder` remonte membres et sous-groupes au
  parent ([asset_folder_store.py](editor/core/asset_folder_store.py)) : l'undo doit restaurer
  l'appartenance *exacte* d'avant, donc capturer l'état (id, `parent_id`, `members`) avant de
  supprimer, pas seulement recréer un dossier vide.
- **Granularité et fusion.** Un `Ctrl+G` sur une sélection = plusieurs `move_member` → une seule
  entrée (comme le lot de suppression du finder via `MacroCmd`). Un glisser de nœud = une entrée,
  pas une par pixel (même besoin de fusion que `SetFieldCmd`).
- **Portée.** Trancher quelles opérations entrent : la *structure* seule (groupes + appartenance),
  ou aussi la *présentation* (positions, géométrie des cadres). La présentation change à chaque
  petit glisser ; l'y inclure gonfle la pile pour un gain douteux.

---

## La struct `Actor` allégée — l'acteur entité légère, le sprite (et l'OAM) deviennent un composant

**Décidé le 2026-09-21 : à faire quoi qu'il arrive.** Ce dossier fixe le POURQUOI et les marches ;
les décisions fines se tranchent à l'ouverture.

### D'où vient la question

Le modèle runtime est aujourd'hui **plat** : une seule struct `Actor`
([runtime/include/actor_types_static.h](runtime/include/actor_types_static.h)), un tableau
`g_actors[]`, le `tag` distingue le type. Deux coûts assumés en découlent :

1. **La struct grasse.** Chaque `Actor` porte l'union de tous les champs possibles — dont le
   sous-struct `sprite` complet. Un acteur-logique (contrôleur, spawner, directeur d'IA, déclencheur)
   qui ne veut que x/y paie tout. Ce n'est pas théorique : `g_actors[]` a dû **migrer en EWRAM** faute
   de tenir en IWRAM (cf. Correctifs).
2. **Le budget OAM ment par prudence.** `oam_alloc` compte `128 − acteurs actifs − UI`, alors que son
   propre commentaire reconnaît qu'« un acteur sans sprite ne consomme aucune entrée OAM ; le budget
   les compte quand même ». Un acteur-logique grignote donc un plafond matériel qu'il n'utilise pas.

### Le principe

Faire de `Actor` une **entité légère**, et déplacer la logique d'affichage sur un **composant sprite** :
la règle « **1 acteur = 1 slot OAM** » devient « **un sprite component affiché = 1 slot OAM** ».
Conséquences visées :

- **Un acteur sans sprite est gratuit** (0 slot OAM, pas de sous-struct sprite) — les acteurs-logique
  cessent de peser sur les 128 et sur l'IWRAM.
- **Le budget OAM devient honnête** : `128 − sprites affichés − UI`, la vérité du matériel (OAM =
  objets affichés, pas entités). Cohérent avec « le matériel façonne le langage ».
- **Swap d'apparence** : un acteur peut porter **plusieurs** sprite components dont **un seul affiché**
  — changer de planche sans second acteur ni second slot.

### Le rôle de l'Actor — racine de composition, pas fourre-tout

L'Actor est le **type stable et simple** que manipule le gameplay. Il porte ce qui existe pour
toute entité : identité, durée de vie, transform (`position`, orientation), mouvement courant
(`velocity`) et script. Les composants lui ajoutent une capacité optionnelle ; ils ne changent
ni son identité ni le fait qu'un script peut tenir une référence d'Actor.

| Porteur | Responsabilité publique | Coût matériel |
| --- | --- | --- |
| `Actor` | identité, `active`, `destroy`, position, vélocité, helpers de gameplay | aucun OAM par lui-même |
| `Sprite` | dessin, animation, palette, priorité et taille de frame | une entrée OAM seulement s'il est affiché |
| `Collision` | formes, contacts, résolution contre le monde | aucun OAM |
| `CollisionBox` | une forme précise, ses réglages et ses requêtes avancées | aucun OAM |
| `SoundFx` / script | émission sonore et logique de l'entité | aucun OAM |

Cette composition est une **forme d'API et d'authoring**, pas l'obligation d'un ECS par pointeurs
au runtime. La GBA peut garder une représentation compacte — champs à plat pour le chaud,
side-array pour le Sprite optionnel — tant que le contrat public reste le même. Les composants
ne sont donc pas un prétexte pour déplacer toute propriété derrière une indirection.

L'Actor conserve des **helpers de gameplay agrégés**, parce qu'ils répondent à l'intention la
plus fréquente sans obliger à connaître la forme qui la réalise. La forme cible est une
propriété, jamais `is_grounded()` :

```lua
if self.grounded then                 -- au moins une collision porte l'Actor
  self:add_velocity(vec2(0, -900))
end

local collision = self.collision      -- nil si l'Actor n'a pas cette capacité
local feet = collision:get_box("feet")
```

`self.grounded` vaut `false` sans composant Collision. Il agrège les contacts porteurs de la
capacité Collision, pas une box particulière : le helper survit donc à plusieurs boîtes, et
plus tard à une autre représentation de collision. Les détails — tag, géométrie, activation,
requêtes par boîte — restent sur `Collision` et `CollisionBox`.

### Ce qui existe déjà à ne pas confondre

- Les **AnimStates** : une entité, plusieurs visuels d'une MÊME planche, un slot. (déjà là)
- Les **prefabs segmentés** (v0.23) : une entité, PLUSIEURS parties = plusieurs slots (enfants). (déjà là)
- Le neuf ici : (a) l'acteur **zéro sprite** gratuit, (b) N planches **distinctes** swappables, 1 affichée.

### Ce qu'il faudrait trancher avant d'ouvrir

- **Quelle découpe compacte porte le Sprite optionnel** : index nullable vers un side-array de
  sprite-components, ou bloc hot/cold absent des acteurs sans Sprite. Dans les deux cas, aucun
  Actor logique ne garde le sous-struct sprite complet ; le choix doit éviter la fragmentation
  d'identité vue à la tranche poolé des exports.
- **La VRAM, pas l'OAM, est le vrai plafond du multi-apparence.** « 1 affiché » économise un slot OAM,
  mais les tuiles + palette de CHAQUE apparence doivent être résidentes (ou streamées). À trancher :
  tout résident vs streaming.
- **Le budget reste au build mais devient un pire-cas.** Avec un affichage dynamique, le build borne le
  **max concurrent de sprites affichés** par scène. Reste de l'allocation au build — **pas « un autre
  moteur »**, contrairement au spawn dynamique.
- **Ne PAS construire un ECS général.** Position, durée de vie et mouvement restent le socle
  chaud de l'Actor. Collision devient une capacité publique parce qu'elle est déjà optionnelle
  et porte ses propres formes ; cela ne justifie pas de mettre chaque champ dans une table de
  composants. La séparation physique vise d'abord Sprite/OAM, là où la douleur matérielle est
  concentrée.

### Le verrou réel : un seul indice pour trois choses (constaté le 2026-09-25)

Dans le C émis, `idx` est **à la fois** l'entrée `g_actors[idx]`, le slot `shadow_oam[idx]` et
le numéro d'acteur que connaissent le tick d'animation, le writer OAM et le spawn. Le writer est
**entièrement déroulé**, un bloc par acteur, avec les constantes du sprite écrites en dur
(`sh`, `sz`, `bt`, `tiles_per_frame`) : `main_gen.py` (boucles « OAM actors scène » et « OAM
prefab pool »), `gen_sprite.anim_tick_lines`, `gen_affine`. Deux conséquences :

- **`g_actors` a la taille de l'empreinte OAM, pas du nombre d'acteurs.** Sa dimension est
  `max(placed + ui + pool_slots)` sur les scènes (`Actor g_actors[n_actors]`, `main_gen.py`) : les
  slots d'interface OBJ (`ui`), qui n'ont **aucun acteur**, réservent chacun une struct entière.
  Le gaspillage existe déjà, indépendamment de ce chantier.
- **Compter seulement les porteurs de sprite dans le budget ne libère rien** tant que l'indice
  d'acteur EST le slot OAM : un acteur-logique garde son entrée `g_actors` et son numéro OAM.

**Le side-array a un coût d'exécution nul dans le C généré, mais pas dans les accesseurs.**
Le writer OAM et le tick d'animation étant déroulés par porteur, le build connaît l'emplacement
de chaque entrée : `g_oam_entries[k].frame` est un accès à adresse fixe, comme
`g_actors[idx].sprite.frame` aujourd'hui. En revanche, les accesseurs de script prennent un
`Actor*` (`actor_get_frame(const Actor* s)`) : il leur faut `g_oam_entries[s->oam_entry]`, donc
**un déréférencement** — celui que redoute le commentaire de `actor_types_static.h` (décision
v0.25) — plus un cas « pas de sprite » (`oam_entry < 0` : lecture = 0, écriture = sans effet).
Ce coût ne pèse que sur les lectures/écritures de script, pas sur le rendu ; il reste à peser
contre le gain de RAM. Le commentaire de la struct sera à réécrire avec la marche 2.

### Ce que le transpileur pèse (mesuré le 2026-09-25)

Le transpileur est **découplé du layout C** : `editor/scripting/api.py` déclare chaque propriété
`self.*` en `ApiProp(c_getter=…, c_setter=…)`, et `codegen.py` n'émet que l'appel à l'accesseur
(`actor_get_frame(self)`). Aucun accès de champ n'est écrit par le transpileur. Le layout
vit donc dans un seul fichier, `runtime/include/runtime_api_inline.h` (60 accesseurs, dont 26
touchent `sprite.*`).

- Sur les 29 propriétés `self.*` de `RUNTIME_PROPS`, une vingtaine sont du domaine Sprite :
  `rotation`, `scale`, `sprite_rotation/scale/offset`, `visible`, `anim`, `anim_speed/length/
  loop/finished`, `frame`, `frame_w/h`, `flip_h/v`, `pal`, `obj_mode`, `priority`, `auto_dir`,
  `screen_space`, `affine`. Restent à l'Actor : `position`, `velocity`, `active`, `tag`,
  `direction` ; à la Collision : `grounded`, `box_count`.
- **Déplacer le layout (marche 2) ne change aucun script utilisateur** : seuls les accesseurs de
  `runtime_api_inline.h` et le writer/tick/spawn changent. C'est ce qui rend la marche 2
  invisible pour l'auteur.
- **Compartimenter l'API** (`self.sprite.frame` au lieu de `self.frame`) est en revanche un
  changement de surface : les noms passent par `RUNTIME_PROPS`, `api_reference.py` (catégories),
  `api_reference.json`, le checker (`checker.py`, liste des propriétés de transform), la
  complétion, le refactor, `SCRIPTING.md` / `docs/scripting-reference.md` et les tests
  (`test_scripting_api.py`). Elle est indépendante de la marche 2 et peut la précéder.
- Piège : `actor:get(i)` → `actor_at(i0)` (index 1-based côté Lua) expose l'indice `g_actors`.
  Tant que l'indice d'acteur est le slot OAM, il n'y a pas de sujet ; **la marche 0 doit
  garder cet indice stable et documenté** (un acteur-logique a un indice mais pas de slot).
  De même, `UIImageInfo.actor` et la bande de texte OBJ référencent `g_actors` par indice
  (`gba_engine.h`) : à réviser quand `ui` sort de `g_actors`.

### Le modèle figé : `g_oam_entries[]` réserve l'OAM, `g_actors[]` ne porte que des acteurs

**Proposé par Victor le 2026-09-25.** Le tableau qui réservait les slots OAM change de propriétaire :

| Tableau | Un indice = | Taille (max sur les scènes) | Porte |
| --- | --- | --- | --- |
| `g_oam_entries[]` | **une entrée OAM** | `used` = sprites d'acteurs + OBJ d'interface/texte + sprites de pools (≤ 128) | l'état d'affichage |
| `g_actors[]` | **un acteur** | acteurs posés + instances de pools × parties | identité, position, vélocité, tag, collision, lien `oam_entry` |

- **L'invariant migre de l'acteur au sprite** : `shadow_oam[k]` ↔ `g_oam_entries[k]`, même `k`. Le writer
  reste déroulé et à adresse fixe ; seule la clé change. `used` devient LE nombre honnête : un slot
  par consommateur réel.
- **Les consommateurs OAM réels** (inventaire du 2026-09-25 — quatre écrivains de `shadow_oam[]`) :
  (1) sprites d'acteurs posés, (2) sprites des pools de prefabs (`main_gen`) ; (3) bandes de texte
  OBJ et (4) images d'UI OBJ (`gba_engine.h`, via `g_obj_oam_base + oam_rel`). Chacun occupe une
  bande contiguë de `g_oam_entries[]`, connue au build ; `oam_rel` des zones de texte/UI devient un
  décalage dans cette table, plus dans un « slot fantôme » de `g_actors`.
- **`Actor` → `OamEntry` par un lien nullable** : `Actor.oam_entry` = indice dans `g_oam_entries[]`, ou -1. Un
  acteur-logique, un marqueur de prefab (point de tir, ancre de hitbox) n'ont **ni slot ni état
  d'affichage**. Aujourd'hui un marqueur réserve quand même un slot (`attr0=0x0200`).
- **Ce que porte une entrée `OamEntry`** : `frame`, `anim_state/speed/length/loop/finished`, `timer`
  d'animation (le tick d'animation écrit `timer`, aujourd'hui sur l'Actor), `frame_w/h`, `auto_dir`,
  les registres OAM (`visible`, `flip_h/v`, `pal_bank`, `obj_mode`, `priority`), le transform
  **local** (`rotation`, `scale`, `offset`), `affine_slot`, `screen_space`. Le transform **monde**
  (`rotation`, `scale_x/y`) reste sur l'Actor : c'est de l'état de jeu, lisible sans sprite.
- **Table uniforme, types étroits.** Les slots d'UI/texte ont une entrée qu'ils n'utilisent pas ;
  plutôt que des unions par nature de consommateur (complexité), l'entrée est **étroite** (`u8`/`s8`/
  `s16`, ~24 o au lieu de ~100) : le rétrécissement des types n'est plus « à part », il rend la table
  uniforme bon marché. Alternative écartée : un registre de propriétaires + un second tableau d'états.
- **Accesseurs** : `actor_get_frame(const Actor*)` passe par `g_oam_entries[s->sprite]` ; `sprite < 0` →
  lecture 0, écriture sans effet (`self.visible = true` sur un acteur sans sprite ne fait rien). Le
  coût d'un déréférencement, décrit plus haut, reste borné aux accès de script.
- **La marche 3 s'y loge sans changer le modèle** : les N apparences d'un acteur sont des données ROM ;
  le slot porte l'identifiant de l'apparence courante. Un swap change l'état du slot, il n'ajoute pas
  d'entrée. VRAM : tout résident (tranché, voir « Marche 3 »).
- **Le budget** : `over_budget` porte sur `used` de `g_oam_entries[]`. Les acteurs sans sprite n'y figurent
  pas ; le plafond de 128 vaut pour `g_oam_entries[]`, celui de `g_actors[]` est la RAM.
- **Indices exposés à ne pas casser** : `actor:get(i)` → `actor_at(i0)` et `UIImageInfo.actor`
  restent des indices de `g_actors[]`, désormais vraiment « d'acteur » (plus jamais un slot OAM).

**Le nom (tranché le 2026-09-25).** Le type est `OamEntry`, le tableau `g_oam_entries[]`, le lien
`Actor.oam_entry`. Écartés : `Sprite` (déjà défini par libgba, `gba_sprites.h`), `SpriteComponent` (le
composant d'acteur de l'éditeur : un seul des consommateurs de la table), `SpriteOAM` (mêle le
sprite et la mémoire OAM entière). « Entrée de l'OAM » est le mot que le code emploie déjà
(`oam_alloc`, « OBJ »), et l'entrée est l'état logiciel derrière un `OBJATTR` de `shadow_oam`.

À trancher à l'implémentation (0b) : la forme exacte du lien pour un groupe de pool dont certains
membres n'ont pas d'entrée (table de build, pas un simple décalage).

### Les marches (staging, sans réécriture ECS)

0. **Introduire `g_oam_entries[]`.** En deux temps, pour rester vérifiable :
   - **0a — miroir. LIVRÉE (2026-09-25).** `g_oam_entries[]` créé ; le sous-struct `sprite` et les
     registres OAM de la racine (`visible`, `flip_h/v`, `pal_bank`, `obj_mode`, `priority`,
     `screen_space`, `timer`) y migrent. `Actor.oam_entry` = même indice que l'acteur, `g_actors[]`
     gardant sa taille. Le transform monde (`rotation`, `scale_x/y`) reste à l'Actor. Déplacement
     mécanique de `runtime_api_inline.h`, du writer, du tick d'animation, de `gen_affine`, du spawn
     et de `scene_init` ; `project_oam_entry_count` distingue déjà les deux tailles (égales en 0a).
     Vérifié : 4 projets démo se buildent à froid, et leur `main.c` d'avant, renommé par les mêmes
     règles, ne diffère de celui d'après que par les ajouts voulus (déclaration, remise à zéro,
     pose du lien). Le code de la ROM grossit de 100 à 170 octets : l'indirection des accesseurs.
   - **0b — géométrie. LIVRÉE (2026-09-25).** `oam_alloc.py` calcule deux espaces :
     `g_actors[]` = `[posés][pools]`, `g_oam_entries[]` = `[posés à sprite][interface][pools à
     sprite]`. `has_oam_entry` est LE prédicat (writer et budget le partagent) ; `Actor.oam_entry`
     vaut -1 pour un acteur sans sprite ou un marqueur de prefab ; les accesseurs de script y sont
     neutres (entrée nulle) ; les bandes texte/UI s'ancrent à `OamLayout.ui_start` ; le budget
     (`actor_budget`, validateur) compte des entrées, plus des acteurs. Le spawn avance dans les
     deux espaces (`_i += groupe`, `_e += entrées par instance`). MyGame : `g_actors[4]` → `[1]`.
     Vérifié : 4 démos à froid, et une démo synthétique (contrôleur sans sprite en tête, marqueur
     enfant de prefab, UI forcée à 2) qui compile et émet le C attendu. Non vérifié sur émulateur.
     *Décision prise en route :* un budget qui compte les entrées fait que les tests d'allocation
     doivent dire quels acteurs affichent (`tests/oam_fixtures.py`). Intention d'origine : on brise l'identité : `g_actors[]` se compacte (sans `ui`, sans marqueurs),
     les bandes UI/texte s'ancrent dans `g_oam_entries[]`, `scene_oam_layout` calcule les deux tailles
     (`test_0a_les_deux_tables_ont_la_meme_taille` marque cette frontière et devra changer).
     C'est là que les prefabs poolés (groupes contigus) demandent une table de build.
1. **Le budget compte les slots de `g_oam_entries[]`.** Conséquence de 0b, plus « `oam_alloc` seul ».
2. **L'entrée OAM devient optionnelle** → LIVRÉE avec la 0b : `Actor.oam_entry` nullable (-1),
   `g_actors[]` dimensionné sur les seuls acteurs. L'acteur ne porte plus aucun champ d'affichage.
   Sans coût d'exécution (voir ci-dessus).
3. **N sprite components, 1 actif** → swap d'apparence. **OUVERTE (2026-09-25), conception figée
   ci-dessous, code non commencé.** La plus grosse marche.

#### Marche 3 — le modèle (décisions de Victor, 2026-09-25)

- **VRAM : tout résident.** Toutes les apparences déclarées restent en VRAM, comme tous les sprites le
  sont déjà : `sprite_offsets_for` donne à chaque sprite une base fixe, calculée sur le PROJET (pas par
  scène), et chaque `scene_init` recopie ceux de sa scène plus les sprites de prefab. N apparences =
  N sprites de plus sous le même plafond de 1024 tuiles OBJ, vérifié au build par le contrôle
  existant. Pas de streaming : ce serait un mécanisme nouveau (copie à la demande, allocation
  dynamique, partage entre acteurs), sans besoin démontré.
- **Un acteur affiche UN seul sprite (une entrée OAM) ; ses SpriteComponent sont actifs ou non, et
  en activer un désactive le précédent.** `SpriteComponent.active` existe déjà : il devient le
  SÉLECTEUR. Un acteur peut donc porter plusieurs `SpriteComponent` (le modèle le permet déjà : les
  `id` de composants sont uniques au sein de l'acteur), avec l'invariant « au plus un actif ». Ce n'est
  pas une liste d'apparences dans un composant.
- **L'entrée OAM est réservée dès qu'au moins un composant a un sprite** (`has_oam_entry` ne teste
  plus le seul composant actif : elle teste l'existence d'un sprite). Aucun actif au départ = entrée
  réservée mais cachée.
- **Swap = changer l'apparence de l'entrée, pas l'entrée.** `OamEntry` gagne un `u8 appearance`. Les
  constantes aujourd'hui écrites en dur dans le C émis (base de tuiles `bt`, forme, taille,
  `tiles_per_frame`, tailles de frame, tables d'animation `sprite_X_anim_dirs`…) passent dans une table
  ROM par apparence ; le writer OAM et le tick d'animation lisent `appearance_table[entry.appearance]`.
  C'est le SEUL coût d'exécution de la marche 3 sur le chemin chaud ; un acteur à une seule apparence
  garde le C émis actuel (constantes), sans table. *Révisé à la 3a : pas de table ROM.* Le writer et le
  tick étant déjà déroulés par entrée avec des constantes, on les déroule aussi PAR APPARENCE — un
  `switch` sur `OamEntry.appearance`, chaque cas gardant ses constantes et ses tables d'animation
  nommées. Pas de pointeurs, pas de test de NULL sur les tables optionnelles (sfx, événements de
  frame) ; le coût est du code (proportionnel aux apparences), et un `switch` par entrée et par
  frame — seulement pour les acteurs multi-apparence.
- **À l'activation d'un composant** : l'état d'animation repart à l'`initial_state` de ce composant,
  frame 0, timer 0 ; la palette OBJ est celle du composant ; `frame_w/h` sont réécrits.
- **Affine** : le slot de matrice appartient à l'ENTRÉE (réservé au build). Si un composant de l'acteur
  est affine, l'entrée l'est ; les autres apparences sont rendues avec la matrice de l'entrée (à
  documenter à l'ouverture de 3b, ne pas laisser deviner).

#### Marche 3 — l'API de script (à trancher avant 3c)

**Tranché à l'ouverture de la 3c (2026-09-25) — à valider par Victor.** Forme proposée par Victor :
`self.sprite = self.sprite.myID`, mais `self.sprite` y désignerait deux choses (le composant actif et le
conteneur des composants), et un id valant un nom de propriété serait ambigu. Le code donne un précédent
plus net : le commentaire de `self.anim` dit que changer d'état est un GESTE (il remet frame et timer à
zéro), pas une propriété qu'on assigne — `self:play_anim(nom)`. Activer une apparence remet aussi
l'animation, les tailles et la palette : c'est le même cas. Retenu, donc, sans type de référence :

- `self:activate_sprite("id")` — le geste ; « activate » reprend le mot de la case « Active » de
  l'inspecteur, et « activer l'une désactive l'autre ».
- `self.active_sprite` — lecture seule, comparable par son nom (`self.active_sprite == "blesse"`).
- `id` = celui du composant sprite ; résolu à la compile en `SPRITE_<ACTEUR>_<ID>` (domaine
  `DOMAIN_SPRITE_ID`, comme `ANIM_*`). Un id inconnu est une ERREUR du checker ; l'appel sur un autre
  acteur (`other:activate_sprite`) est refusé (l'id appartient à l'acteur qui exécute).
- Les noms de `self.sprite` / `self.sprites` restent LIBRES pour la compartimentation de l'API
  (`self.sprite.frame`) : aucun nom n'est réservé ici. Changer l'orthographe est un changement de
  table dans `api.py` (`self:activate_sprite`, `self.active_sprite`).

#### Marche 3 — les sous-étapes

- **3a — l'apparence devient une donnée (sans changement visible). LIVRÉE (2026-09-25).**
  `Appearance` (sprite, base de tuiles, origine) dans `gen_sprite.py` ; `oam_write_lines` et
  `anim_tick_variants` émettent une apparence par cas, `OamEntry.appearance` (`u8`, +1 octet : 34
  au total) choisit. Les deux writers de `main_gen` (acteurs posés, pools) et le tick passent par
  ces helpers avec UNE apparence. Vérifié : le `main.c` des 4 démos est IDENTIQUE octet pour octet
  avant/après ; un build OrbitTest où chaque acteur reçoit une 2e apparence factice (58 `switch`)
  compile ; tests unitaires dans `tests/test_oam_appearances.py`. Reste pour 3b : construire la
  liste d'apparences depuis les composants (aujourd'hui elle n'en a qu'une, le premier), et poser
  `frame_w/h`, palette, `anim_state` initial et VRAM par apparence (init, spawn, pools).
- **3b — le modèle éditeur. LIVRÉE (2026-09-25), sauf le swap à l'exécution (3c).**
  - *Modèle* : trois fonctions dans `core/models/components.py` sont la SEULE façon de lire « le »
    sprite d'un porteur — `sprite_components`, `displayed_sprite_component` (l'actif),
    `affine_sprite_component` (l'affine appartient à l'entrée) — plus `competing_sprite_components`.
    `get_sprite_comp` a disparu ; les 22 sites ont été repris.
  - *Build* : `oam_alloc.owner_appearances/initial_appearance` (source unique) ; `has_oam_entry` =
    « au moins une apparence » (une entrée cachée est réservée si aucune n'est active) ; `rom_build`
    charge les sprites de TOUTES les apparences (`extra_sprites`, prefabs et parties compris) ;
    l'init pose `appearance = n` et cache l'entrée si aucune n'est active ; writer et tick émis par
    apparence (une apparence fixe, sans états, donne un `case` vide) ; palettes propres de chaque
    apparence réservées (`palette_alloc._owner_sprites`).
  - *Validation* : `_check_sprite_appearances` (deux actives = erreur) ; événements de frame vérifiés
    pour chaque apparence.
  - *Éditeur* : activer une apparence désactive l'autre en UNE entrée d'historique ; une apparence
    ajoutée naît inactive si une autre est affichée ; aperçu, canvas et barre de statut suivent
    l'apparence affichée (le canvas ne dessine plus un sprite que la ROM n'afficherait pas).
  - *Vérifié* : `main.c` des 4 démos identique ; builds synthétiques (acteur et prefab poolé à 2
    apparences : seconde inactive, seconde active, aucune active) compilent ; 13 tests de modèle et 5
    tests d'inspecteur. *Correction (2026-09-25)* : la jauge « sprites / tuiles / cycles » de la barre
    d'état (`GbaStatusBar.update_scene`) comptait tout acteur portant un composant sprite — même vide
    ou sans sprite résolu — et plantait sur un sprite introuvable ; elle lit maintenant le prédicat du
    build (`has_oam_entry`), compte les tuiles de toutes les apparences et le coût par scanline de la
    seule apparence affichée (`tests/ui/test_gba_status_bar.py`). Le build et le budget de l'inspecteur
    étaient déjà justes : un composant vide n'y réservait rien. *Changement de comportement* : un acteur dont le SEUL composant sprite est
    inactif réserve désormais une entrée (cachée) au lieu de n'en avoir aucune.
  - *Reste pour 3c* : les constantes propres à une apparence (`frame_w/h`, palette, `anim_state`
    initial) ne sont posées que pour l'apparence de départ ; l'ACTIVATION à l'exécution doit les
    reposer, et n'a pas encore d'API de script.
- **3c — l'activation à l'exécution et l'API de script. LIVRÉE (2026-09-25).**
  - *Primitif C* : `actor_set_appearance(Actor*, n)` repose `frame_w/h`, `pal_bank`, `auto_dir` depuis
    `g_appearance_init` (table ROM PAR SCÈNE, `AppearanceInit`, une ligne par apparence des porteurs
    multi-apparence — `gen_appearance.py`), remet frame/timer/état à 0 ; `OamEntry.appearance_base` =
    1re ligne + 1 (0 = rien à activer : un acteur mono-apparence ne lit jamais la ligne d'un autre) ;
    sans entrée OAM, sans effet. `OamEntry` = 36 octets.
  - *Noms d'animation* : pour un acteur multi-apparence, `anim_names` est l'UNION des états de ses sprites
    et `ANIM_*` une expression qui lit l'apparence de `self` (`<sym>_anim_map[apparence][k]`, 255 = état
    absent, ignoré par `actor_play_anim`). Un acteur mono-apparence garde des constantes littérales.
  - *Script* : `self:activate_sprite`, `self.active_sprite`, domaine `DOMAIN_SPRITE_ID`, checker,
    transpileur, `sprite_ids` dans les deux contextes.
  - *Vérifié* : sonde C native (constantes reposées, sans-entrée, mono-apparence, état absent) ; 10 tests
    de script ; build TacticsDemo avec un script Lua réel (deux apparences, `Move` absent du soldat) ;
    ids inconnus et appel sur `other` refusés. Démos : seule la ligne `g_appearance_init` est ajoutée.
  - *Limites connues* : la constante `ANIM_*` d'un acteur multi-apparence utilise `self` — un helper
    de script sans `self` qui cite une animation ne compilera pas ; les scripts de PREFAB poolé ne
    reçoivent pas d'`anim_names` (héritage : `pf_anim` reste vide), donc `play_anim` y est déjà hors
    contrat.
  - *Suivi de renommage de l'`id` (livré, 2026-09-25)* : renommer l'`id` d'un composant sprite dans
    l'inspecteur réécrit `self:activate_sprite("id")` et `self.active_sprite == "id"` dans le script
    de SON propriétaire seulement (`Project.rename_sprite_id_refs`, `refactor.rename_in_files`) — deux
    acteurs peuvent avoir chacun un « blesse ». La commande `RenameSpriteIdCmd` défait l'`id` ET le
    script d'un seul Ctrl+Z. Un id vide ou déjà pris est refusé ; deux ids qui donnent la même
    constante C (`c_ident`) sont une erreur du validateur. Le suivi couvre désormais aussi
    `self.<propriété> == "nom"` (`self.anim`, `self.active_sprite`) : un renommage d'animation
    réécrit `self.anim == "walk"`, ce qu'il oubliait. *Limite* : un behavior PARTAGÉ qui cite l'id
    n'est pas réécrit — le checker signale l'id devenu inconnu au build.

**Types étroits — LIVRÉ (2026-09-25).** `OamEntry` 92 → 32 octets, `Actor` 96 → 68, mesurés par
le compilateur hôte (`test_les_tailles_des_structs_ne_regressent_pas` fige les plafonds). Champs 16
bits d'abord, puis 8 bits : aucun remplissage. `s16` : `frame`, `timer`, `anim_speed`,
`anim_length`, transform (rotation, scale Q8, offset), `tag`, `oam_entry`, `last_x`, `slope_acc` ;
`u8` : drapeaux et registres OAM, `anim_state`, `frame_w/h`, `active`, `grounded`, `box_count` ;
`s8` : `dir_*`, `affine_slot`. Position et vélocité restent en `int` (Q8, 32 bits requis). ROM
plus petite d'environ 4 Ko sur OrbitTest et TacticsDemo (moins d'octets par instruction d'accès).
*Limite assumée :* un script qui écrit une rotation locale hors de ±32767° ou une échelle hors de
×127 voit la valeur tronquée à 16 bits ; les registres à valeurs bornées sont masqués par leurs
accesseurs. Ancienne remarque, pour mémoire : les drapeaux étaient tous des `int` de 4 octets
pour des valeurs qui tiennent sur 1. Les rétrécir gagne de la place sans toucher au layout logique — à peser à part.

### Piste Collision — un `Contact` d'événement, pas une « dernière collision »

Une boîte peut toucher plusieurs tuiles ou plusieurs acteurs dans une même frame. Lui demander
`my_box:get_collision()` ou `get_collision_vector()` imposerait de choisir arbitrairement une
« dernière » collision — information instable, perdue dès que deux contacts coexistent. La
collision doit au contraire livrer un **Contact immuable** au moment où elle est observée.

```lua
function on_collision_enter(contact)
  local other = contact.other
  local mine = contact.self_box
  local theirs = contact.other_box
end

function on_tile_collision(contact)
  local point = contact.position       -- point monde, en pixels
  local normal = contact.normal        -- vec2 : direction de la réponse, ex. vec2(0, -1)
  local cell = contact.tile_position   -- coordonnée de tuile, distincte du point monde
  local box = contact.self_box
end
```

`Contact` est une valeur d'événement, pas une référence durable au moteur : `position`,
`normal`, la tuile et les deux boîtes décrivent l'impact précis de CET appel. Il peut donc être
étendu sans transformer `CollisionBox` en journal mutable. Un contact acteur↔acteur porte
`other` et `other_box` ; un contact tuile porte `tile_position` et éventuellement son type.
Les anciennes signatures (`on_collision_enter(other, my_box, other_box)`,
`on_tile_collide(nx, ny)`) sont à migrer ensemble quand le type `Contact` sera introduit,
après vérification que le sous-ensemble Lua sait porter cette valeur.

La boîte conserve ses opérations stables (`active`, `solid`, `bounds`, `overlaps`) ; le
`Contact` explique **ce qui vient d'arriver**. Cette frontière évite de mélanger configuration,
requête de géométrie et événement de collision.

#### Extension proposée (2026-09-25) — la normale vaut aussi pour un contact acteur↔acteur

**Non verrouillée.** Aujourd'hui la normale n'existe que pour les tuiles (`on_tile_collide(normal_x,
normal_y)`, deux entiers) ; un contact acteur↔acteur n'en porte aucune (`on_collision_enter(other,
my_box, other_box)`). Distinguer « on me marche dessus » de « on me touche » impose donc deux boîtes
Trigger dédiées (`tete`, `pieds`) et la comparaison de deux constantes `BOXTAG_*` (cf.
`docs/user-guide/enemies.md`). Le `Contact` ci-dessus ne le règle que si la normale s'y trouve aussi :

```lua
function on_collision_enter(contact)
  if contact.other.tag ~= "Joueur" then return end
  if contact.normal.y < 0 then          -- poussé vers le haut : on me marche dessus
    self:destroy()
  else
    global.hp = global.hp - 1
    contact.self_box:deactivate()       -- cycle de vie (v0.16, critère 3)
  end
end
```

Un seul type d'événement, une seule forme de normale : `on_tile_collision(contact)` et
`on_collision_enter(contact)` lisent `contact.normal` de la même façon. Sur l'ennemi du guide, le script
passe de 21 à 17 lignes et perd ses deux boîtes de piétinement.

- **Convention à fixer.** La normale est la direction de la **réponse de celui qui reçoit** l'événement :
  la direction dans laquelle il serait repoussé. « On me marche dessus » donne `y < 0` (l'axe Y du GBA
  descend). Pour le joueur qui piétine, le même contact lu de son côté donne `y > 0`. Chaque acteur
  reçoit son propre `Contact` avec sa propre normale ; le contrat ne dépend pas de l'ordre des appels.
- **Point ouvert — le calcul.** Le runtime ne dérive aujourd'hui aucune normale entre deux boîtes. Pour
  deux AABB, la normale est l'axe de plus petit recouvrement, de signe donné par les centres. À
  vérifier : coût par paire (le budget de détection est un budget de scanline), comportement en
  diagonale (recouvrements égaux : choisir une règle et l'écrire), boîte contenue dans l'autre, et
  vitesse relative très élevée (traversée en une frame). La normale d'un contact tuile, elle, est déjà
  connue.
- **Point ouvert — la valeur.** Comme pour le `Contact` de tuile, l'introduction attend la vérification
  que le sous-ensemble Lua (`lua_subset.py`) sait porter une valeur structurée (`contact.normal.y`,
  `contact.other.tag`) et qu'un paramètre de handler peut en être une.
- **Migration.** Les trois signatures (`on_collision_enter(other, my_box, other_box)`,
  `on_collision_exit`, `on_tile_collide(nx, ny)`) migrent ENSEMBLE vers un `Contact`, avec le renommage
  `on_tile_collide` → `on_tile_collision`. Retrait sec, comme le reste. Le guide utilisateur
  (`enemies.md`, `collectibles.md`, `gameplay-loop.md`, `boss.md`) et les démos sont à migrer avec la
  tranche ; les boîtes `tete`/`pieds` du guide disparaissent au profit d'une seule boîte et de la normale.
- **Ce que ça ne change pas.** `hb:overlaps(other)` reste la requête booléenne pour un test ponctuel
  hors événement ; le `Contact` n'est délivré qu'aux handlers.

### Ce que ça touche (au premier regard)

`runtime/include/actor_types_static.h` (struct `Actor`), `editor/codegen/oam_alloc.py` (budget),
le writer OAM et `scene_init`/spawn dans `main_gen.py`, le modèle éditeur (un acteur porte 0..N
sprite components), et la validation (un budget par sprites affichés). À préciser à l'ouverture.

---

## L'atelier Texte réuni — écrire et voir dans un même écran — **EN COURS**

L'atelier actuel coupe le geste en deux : la source balisée vit dans un `QTextEdit` à gauche,
le rendu GBA dans `FontScreenPreview` à droite. Cette séparation a servi à poser le pipeline des
polices, mais elle oblige désormais à lire deux fois le même texte pour savoir ce que produisent
`[font]`, `[color]`, les icônes et les valeurs. Le chantier les réunit dans **une seule surface de
travail** : le texte se modifie là où son rendu est visible.

Il ne s'agit pas de confier le texte à la mise en forme de Qt : ses polices système, son retour à
la ligne et sa sélection ne sont pas ceux de la ROM. `FontScreenPreview` reste donc le moteur de
rendu fidèle (glyphes rasterisés et `layout_marked_text`) ; l'éditeur devient la couche d'entrée
et de sélection posée sur cette même surface.

### Le contrat utilisateur

- **Un seul écran de contenu.** La clé, le rangement, les langues et la barre de balisage restent
  autour ; la division « source | preview » disparaît. Le texte affiché utilise les vrais glyphes,
  ses polices portées et sa coupe GBA.
- **Bouton “Afficher le balisage”.** Il ne bascule pas vers une vue source : la surface reste
  fidèle à l'écran final. Lorsqu'il est actif, les balises reconnues (`[font=…]`, `[wave]`,
  `[/font]`, etc.) apparaissent directement entre les mots, dessinées avec la police technique du
  moteur. Le contenu conserve toujours la police réellement utilisée par la preview. Lorsqu'il est
  masqué, seuls ces fragments techniques disparaissent ; le texte visible ne change ni de police
  ni de mise en page.
- **Clic droit sur une sélection → “Retirer le balisage”.** L'action enlève les bornes des balises
  reconnues qui enveloppent exactement la sélection, sans effacer le contenu. Les balises imbriquées
  sont retirées ensemble dans une seule annulation ; une sélection partielle ne modifie rien plutôt
  que de produire une portée ambiguë.
- **La source reste la vérité.** `texts.json` et les traductions conservent le BBCode actuel. Ni la
  ROM, ni la table Text, ni le système de traduction ne changent de format.

### Le morceau difficile : correspondre source et rendu

Aujourd'hui `parse()` sait retirer les balises et produire les marqueurs, mais un `Marker` ne porte
que la position de son ouverture. Pour masquer le balisage sans casser le curseur, il faut une
projection explicite : source → caractères affichés, et retour affichage → plage source. Elle doit
produire des segments fidèles pour le contenu et des segments en police moteur pour les balises
visibles ; les balises masquées ont une longueur visuelle nulle. Elle doit connaître les balises
ouvrantes/fermantes, les échappements `[[`/`$$`, les icônes, et une valeur `$nom` qui occupe une
place source mais plusieurs caractères à l'aperçu.

Cette projection servira trois lecteurs plutôt que trois approximations : le rendu unifié, la
sélection/caret et l'action « Retirer le balisage ». Les locales de littéraux restent hors de cet
aperçu, comme aujourd'hui : aucune portée Lua n'existe dans l'écran Text.

### Analyse technique d'implémentation

Le socle est déjà en place et doit être conservé :

- `core.text_markup.parse()` est la seule grammaire. Il fournit le texte réellement lu (`display`),
  les portées (`Marker`) et les fragments de source reconnus (`Token`).
- `FontScreenPreview` matérialise déjà les Font Assets et dessine les vrais glyphes selon
  `layout_marked_text()`. Il sait donc afficher une suite de polices bitmap et vectorielles sans
  déléguer le rendu à Qt.
- `TextWorkbench` possède déjà la source active, le commit différé et l'historique en amont ;
  `MarkupToolbar` sait déjà poser ou retirer une portée dans un bloc d'édition unique.

Le manque précis est une **projection d'édition** : aujourd'hui, `ParsedText` fait correspondre la
source au texte final, mais pas à une surface qui mélange du contenu final et des balises visibles.
Il faut ajouter dans `core.text_markup` un objet pur, par exemple `MarkupProjection`, construit à
partir de `source`, de `ParsedText` et de l'option `show_markup`.

Chaque `ProjectionSpan` portera :

- sa plage dans la source (`source_start`, `source_end`) ;
- son texte à dessiner ;
- son rôle (`content`, `markup`, `value`, `escape`, `literal`) ;
- la police à demander (`preview` pour le contenu, `engine` pour une balise visible) ;
- le comportement de sélection : une balise est atomique, tandis qu'un contenu est sélectionnable
  caractère par caractère.

La projection doit aussi exposer deux conversions sans ambiguïté : `source_to_visible(position)`
et `visible_to_source(position, bias)`. Le `bias` départage les deux bornes d'une balise masquée :
aller à gauche doit placer le caret avant la balise, aller à droite après elle. Cela évite les
oscillations du curseur et rend Backspace/Suppr déterministes.

Les valeurs `$nom` forment le seul cas non isométrique : une plage source peut être dessinée sous
la forme de plusieurs chiffres de la valeur initiale. Elles doivent rester un span atomique dans la
projection, avec une position de caret avant ou après, jamais entre les chiffres calculés. Ainsi,
l'édition ne transforme pas accidentellement `$score` en texte statique. Les échappements `[[` et
`$$`, eux, restent du contenu normal : ils dessinent respectivement `[` et `$` mais gardent leur
plage source pour le remplacement.

`layout_marked_text()` ne doit pas être modifié pour le rendu joueur : il doit continuer à refléter
strictement la ROM. Le nouvel atelier utilisera un petit adaptateur de mise en page voisin, qui
réemploie les règles d'avance, de ligature, de coupe et d'interligne existantes, mais accepte les
`ProjectionSpan` et retourne des glyphes enrichis de leur plage source. C'est cette information qui
permet le hit-testing, la sélection, le caret et le menu contextuel. La police moteur des balises
sera une recette dédiée et stable de l'éditeur ; elle n'entre pas dans les assets ni dans le build.

`FontScreenPreview` évolue alors en surface interactive :

1. il construit la projection à chaque changement de source, valeurs, police ou option de balisage ;
2. il dessine les glyphes à partir du placement enrichi ;
3. il convertit clic, glisser, flèches et raccourcis en plages source ;
4. il émet un remplacement source et une demande de commit, mais ne modifie pas directement le
   modèle Projet.

`TextWorkbench` reste propriétaire de la langue active, de la valeur de départ et du commit. Il
remplace son `QTextEdit` par cette surface, mais **réutilise la barre de balisage existante**
(`MarkupToolbar`) : ses boutons, ses choix d'assets, ses règles de pose/retrait et ses infobulles
ne sont pas recréés. Son unique adaptation est de viser une petite interface d'édition abstraite
(`source()`, `selection_source()`, `replace_source()`) plutôt qu'un `QTextEdit` concret ; un
adaptateur temporaire gardera cette même interface pour l'éditeur actuel. `MarkupHighlighter`
devient alors inutile. Cette interface conserve les insertions existantes, leur sélection et leur
regroupement dans l'annulation.

Le clic droit « Retirer le balisage » doit être une opération pure du modèle de projection : à partir de
la sélection source, repérer les paires de `Marker` dont les deux bornes enveloppent exactement la
portée, retourner les deux suppressions en ordre décroissant, puis les appliquer dans un seul bloc
d'édition. Les portées croisées ou incomplètes restent désactivées : l'éditeur ne doit jamais
réparer silencieusement une structure ambiguë.

Les tests à ajouter se répartissent naturellement :

- **unitaires** dans `tests/test_font_markup.py` : projection avec et sans balisage, imbrications,
  échappements, `$valeur!n`, limites et retrait de portée ;
- **mise en page** dans `tests/test_text_layout.py` : alternance contenu/police moteur, changement
  bitmap/vectoriel et correspondance clic → plage source ;
- **interface** : frappe, collage, sélection au clavier, Ctrl+Z/Ctrl+Y, menu contextuel, langue de
  traduction et absence de changement dans le contenu envoyé au build.

Risque principal : la police moteur ajoutée au balisage modifie nécessairement la largeur visible
et peut provoquer un retour à la ligne qui n'existe pas dans le jeu. C'est acceptable en **vue
balisage**, à condition que la bascule reste purement éditoriale et que la vue masquée retrouve
exactement le placement ROM. La position du caret doit donc suivre la projection courante, pas une
coordonnée pixel mise en cache entre les deux modes.

### Ordre d'implémentation

1. **Extraire le modèle de projection** dans `core.text_markup` : spans source/affichés, bornes de
   chaque portée, conversion d'une sélection et opération pure de retrait. Tests des imbrications,
   échappements, icônes, valeurs, traductions et annulation textuelle.
2. **Faire de `FontScreenPreview` une surface éditable**, sans changer son algorithme de rendu :
   exposition des positions de glyphes, hit-testing, caret et sélection. La projection compose une
   seule surface de segments fidèles pour le contenu et de segments en police moteur pour les
   balises visibles ; aucun `QTextEdit` source séparé n'est nécessaire.
3. **Remplacer le splitter** de `TextWorkbench` par cette surface unique. Le bouton de balisage ne
   fait varier que les segments techniques de la projection, en maintenant les états existants
   (aucune sélection, multi-sélection, langue source, traduction avec référence en lecture seule).
4. **Ajouter le menu contextuel sûr** : option visible seulement sur une portée entièrement
   sélectionnée, édition regroupée en une commande d'historique, puis retour du curseur sur le
   contenu conservé.
5. **Vérifier de bout en bout** : bitmap/vectoriel, plusieurs `[font]` imbriqués, longueur et
   coupe GBA, collage texte brut, Ctrl+Z/Ctrl+Y, changement de langue et build ROM inchangé.

### Décision verrouillée (2026-09-19)

La vue balisage n'est jamais une vue source typographique Qt : les balises sont affichées en police
du moteur, dans la même composition, tandis que tout le contenu reste rendu de façon fidèle avec
les polices de preview.

### À trancher au démarrage

- Le bouton doit-il mémoriser sa préférence par projet ou rester une bascule de session ?
- Une valeur `$score` affiche-t-elle sa valeur initiale dans la vue nette (comportement actuel de
  l'aperçu) ou le jeton `$score` pour rappeler qu'elle est dynamique ?

---

## v0.13 — Édition mixte — les appels d'API en blocs

Un appel d'API d'un script apparaît comme un bloc éditable, et modifier le bloc réécrit
l'appel là où il est. Du code ET du no-code, sans que ce soient deux chemins : **le script
reste la source, le bloc en est une projection.**

Référence assumée : GB Studio, dont l'ergonomie est le bon modèle. Son **architecture** ne
l'est pas, et pour une raison précise — GB Studio n'a pas de texte du tout, ce qui rend son
approche cohérente chez lui et inapplicable ici. Copier son modèle imposerait soit d'abandonner
le Lua, soit d'accepter deux chemins d'authoring pour la même logique.

La v0.12 (graphe des scènes) est la première instance de ce principe, appliquée à
`scene.switch` seul. Cette version le généralise à tout le catalogue. Les deux reposent sur ce
qui existe déjà : `iter_call_sites` pour trouver les appels, `RUNTIME_API` pour les décrire,
la réécriture par offsets de `refactor.py` pour les modifier.

### Décisions verrouillées

- **Les appels seulement, jamais le flux de contrôle.** `if`, `while`, `for` restent du texte.
  La raison est l'aller-retour : un appel dont les arguments sont des littéraux se relit et se
  réécrit à l'identique, octet pour octet. Le flux de contrôle, lui, pose immédiatement la
  question des commentaires, des lignes vides et de la mise en forme — et la première chose
  qu'un éditeur structuré perd, c'est ce que l'auteur avait écrit autour de son code.
- **La vue ne possède rien.** Chaque édition visuelle est une édition de texte à des offsets
  connus (le mécanisme de `rename_in_text`). Aucun modèle parallèle, aucune sérialisation de
  blocs, donc rien à tenir d'accord et rien à migrer.
- **Les blocs DÉRIVENT de `RUNTIME_API`**, jamais écrits à la main. Même règle et même raison
  mesurée que pour les snippets de la sidebar (cf. ARCHITECTURE, « Ce que l'éditeur INSÈRE
  dérive du catalogue ») : écrits en dur, ils ont proposé pendant des mois `scene_goto("X")`
  et `instantiate("X", x, y)`, deux noms qui n'ont jamais existé. Une fonction ajoutée à
  `api.py` obtient son bloc gratuitement ; une fonction retirée perd le sien.
- **Un argument s'édite selon son DOMAINE**, pas selon son rang. Un paramètre `DOMAIN_SCENE`
  ouvre un sélecteur de scènes, `DOMAIN_SFX` un sélecteur d'effets, un entier un champ
  numérique — tout vient de `Param.ptype` et `Param.domain`. Aucune interface par fonction à
  écrire, et un réordonnancement de paramètres n'invalide rien.
- **Ce qui n'est pas représentable s'affiche EN TEXTE, jamais masqué.** Un argument qui est une
  expression (`self:move(dx * 2, 0)`), un appel hors catalogue, un helper de l'auteur :
  fragment de code opaque dans la surface, éditable dans le Script Editor. **La surface ne
  ment jamais par omission** — c'est la règle qui rend l'hybride honnête, et c'est exactement
  celle dont GB Studio n'a pas besoin.

### Ouvert

- Où vit la surface : un panneau à côté du texte, une bascule qui le remplace, ou dans
  l'inspecteur du composant Script qui porte le fichier ?
- **Insérer un appel depuis la surface.** Contrairement à l'arête du graphe, une position par
  défaut est ici défendable (fin de la fonction courante). À rouvrir sur un cas réel — c'est
  la frontière entre « lire et ajuster » et « écrire », et elle mérite d'être franchie
  sciemment.
- Un argument qui référence une variable plutôt qu'un littéral. `FieldValue` traite déjà
  exactement cette question pour les champs de composant (px / tuile / variable) ; c'est la
  même, et sa réponse devrait être la même.

---

## v0.16 — L'API : la règle de construction, et le rangement

Le constat, posé le 2026-08-19 : **l'API est inégale, et il lui manque une règle de
construction.** Relevé sur le catalogue réel — `api_reference.get_categories()` réconcilié
rend **22 sections, 124 entrées, aucune périmée, aucune permutée**. La mécanique est saine :
`api.py` reste la source de vérité, le JSON ne décide que de la mise en rayon, et le loader
filtre puis complète tout seul. C'est le **rangement** qui ne va pas, pas la machinerie.

### Deux couches

L'API se conçoit à deux niveaux, et toute porte ouverte doit dire auquel elle appartient.

- **La couche d'itération** est celle de la majorité des scripts : simple à découvrir, rapide
  à utiliser, proche du Lua ordinaire, suffisante pour le gameplay courant, sans exposer
  l'intérieur du moteur. Faire une chose courante tient en quelques lignes.
- **La couche moteur** expose les outils spécialisés, et leur **nom** dit qu'ils en sont :
  `Interface`, `TextTable`, `DataTable`, `SoundBox`, `MusicBox`, `JingleBox`.

L'itération répond au **besoin immédiat**, le moteur au **besoin spécialisé**. On ne déplace
pas le simple vers le spécialisé par anticipation — afficher un texte ponctuel ne doit pas
exiger `TextTable` ; à l'inverse, un RPG de centaines de dialogues ira volontairement le
chercher. **Et l'itération ne cherche pas à égaler le moteur** : les deux ont volontairement
des objectifs différents. Le moteur peut être complexe ; l'API de base ne doit pas l'être.

### La règle de construction : on ne construit rien

**Une règle existe déjà, et elle n'est pas celle-ci.** `ARCHITECTURE.md` tranche la **forme**
d'un appel : état intrinsèque → propriété, requête sans argument → propriété en lecture seule,
requête indexée → fonction, action → méthode ou fonction de module. Elle répond à « *comment
ça s'écrit* ». Elle ne dit rien de « *d'où vient la chose sur laquelle j'écris* » — et c'est ce
deuxième axe qui manque. Les deux se composent ; aucune ne remplace l'autre.

Signe que le manque était déjà visible : `ARCHITECTURE.md` range `get_actor(name)` parmi les
« cas hors des trois formes », sans pouvoir dire pourquoi il détonne. La réponse est ici — il
ne suit aucune des trois provenances.

Trois provenances, et trois seulement :

| Provenance | Ce que c'est | Coût runtime |
| --- | --- | --- |
| `module.get("Nom")` | une chose **nommée du projet**, qui existe avant que le jeu démarre | un `#define` |
| `module.spawn(…)` / `sfx:play(…)` | un **slot pris dans un pool dimensionné au build** ; rend une référence, ou rien si le pool est plein | une boucle sur une plage contiguë |
| `module.verbe(n, …)` | le **matériel, numéroté par le matériel** : 4 calques, 2 fenêtres, 16 banques | un registre |

Plus une quatrième, qui n'obtient rien et ne vise rien de numéroté : `text:draw(tx, ty, id)`
dessine à des **coordonnées libres**. Elle est légitime — elle doit être nommée comme telle au
lieu d'être subie.

**Aucun constructeur ne rend une référence.** Le seul `new` envisagé —
`new_sound_effect()` — a été retiré le jour même : les huit canaux de maxmod sont un pool, et
`sfx.play` rend son slot comme `actor.spawn` rend le sien (v0.8.6). `vec2` / `vec3` / `rect`
sont bien des constructeurs, comme `ARCHITECTURE.md` les nomme — mais ils construisent une
**valeur**, comme `12` : rien qui vive dans le moteur, rien dont on tienne une référence. La
règle se dit donc précisément : *aucune référence ne s'obtient autrement que par les trois
provenances ci-dessus.*

Ce qui est inégal, c'est exactement ce qui ne suit aucune des trois : `get_actor("x")`, seule
fonction du catalogue à porter son verbe devant — et le seul « cas hors formes » de
`ARCHITECTURE.md` que ce chantier fait rentrer dans le rang.

### Ce que le rangement actuel enseigne de faux

Cinq intentions ordinaires, passées sur les 22 sections. **Quatre échouent.**

| « Je veux… » | Ce que l'auteur trouve |
| --- | --- |
| cacher quelque chose | cinq réponses dans cinq sections — `self.visible` (Animation), `self:hide()` (Interface), `self.active` (Actor), `layer.show` (Layer), `window.show` (Window). Choisir suppose de savoir ce qu'est sa chose **pour le moteur** — précisément ce que l'itération promet de ne pas exiger. Et `self.visible` rangé dans « Animation » ne s'invente pas. |
| faire sauter mon perso | **Movement** ne contient rien à ce sujet ; la réponse est dans **Physics** (`add_velocity`, `velocity`, `grounded`). Deux sections, un sujet, une frontière indevinable — et on s'arrête raisonnablement à la première. |
| afficher mon score | **Texte** montre huit fonctions, aucune ne dit que la valeur vient d'une globale écrite au script (`global.score = 12`) plus un marqueur `$`. La recette traverse deux sections et un écran de l'éditeur. |
| changer mon fond | cinq sections, trente entrées, toutes nommées d'après des **registres**. Et **Tile** (1 entrée) parle de collision, pas de décor : posé à côté de Tilemap, il se lit comme son petit frère. |
| débuter | **Actor** est la corbeille de repli du réconciliateur (`_ACTOR_FALLBACK`) : la section la plus consultée par un débutant est celle dont le contenu est le moins prévisible. |

Seule **Sauvegarde** passe proprement : quatre fonctions, un sujet, un nom.

Et la liste des intitulés **inverse la réalité deux fois** :

| Ce que la liste montre | Ce qui est vrai |
| --- | --- |
| Transform, Movement, Physics, Animation, Actor — **5 sections** | **un seul objet**, `self` |
| Layer, Tilemap, Palette, Window, Blend — **5 sections** | **une seule chose**, le décor |
| Tableaux (1), Tile (1), Scène (3) | des feuilles isolées, au même rang qu'Audio (11) |

Les sections sont nommées d'après le **grain de l'implémentation** — une famille de verbes, un
registre matériel — jamais d'après la **chose que l'auteur a en tête**. Qui lit la barre
latérale en déduit un moteur à 22 sous-systèmes de poids comparable. Il en a huit.

### Décisions verrouillées

- **Huit sections, une par chose qu'on tient.**

  | Section | Ce qu'elle absorbe | Entrées |
  | --- | --- | --- |
  | **L'acteur** | Transform + Movement + Physics + Animation + Actor | 17 fn + 18 propriétés |
  | **Le décor** | Layer + Tilemap + Window + Blend + Palette | 29 fn + 1 |
  | **Le son** | Audio + les trois boîtes | 22 |
  | **Le texte et l'interface** | Texte + Interface | 14 |
  | **Les données** | Variables + Sauvegarde + `data` + `array` | 8 + l'indexation |
  | **Le script** | Maths + Séquences + `vec2`/`rect` + `wait` + les handlers | 21 + les handlers |
  | **La scène** | Scène + Caméra + `tile.get` | 5 fn + 4 |
  | **Le joueur** | Input | 2 fn + 1 |

- **Les 22 noms actuels deviennent des sous-titres**, ils ne disparaissent pas. `blend` reste
  `blend` pour qui le connaît déjà ; il cesse d'être une **porte d'entrée** pour qui ne le
  connaît pas.

- **La couche est une MARQUE sur l'entrée, pas la navigation.** Couper le panneau en deux au
  premier niveau (« Itération » / « Moteur ») obligerait qui cherche à faire défiler son fond
  à savoir d'abord que le défilement est « moteur » — encore de la connaissance du moteur pour
  trouver la porte. Donc : **une seule navigation, par nom** ; dans chaque section,
  l'itération d'abord, le moteur replié sous un « Aller plus loin ». C'est la réponse à la
  question « où la frontière se voit-elle », sans laquelle la frontière ne survivrait pas
  trois versions.

- **Cinq renommages, complets.** `get_actor` → `actor.get` (le verbe passe derrière, comme
  `interface.get` — `global.get`/`const.get`, cités ici à l'origine, ont depuis quitté l'API
  au profit de l'accès pointé, cf. [Chantiers techniques](#chantiers-techniques)) ; `actor_count`
  → `actor.count` (acté en cours de chantier — même provenance module que `actor.get`/`actor.spawn`,
  la dernière fonction du catalogue à porter un `_` de séparateur) ; `ui` → `interface` (une
  abréviation, que la grammaire de la maison refuse) ; les quatre `text.*_in` →
  `interface.draw_text` / `clear_text` / `reading` / `skip` (elles visent une **zone nommée
  d'une mise en page**, pas des coordonnées libres — c'est ce mélange qui rendait « Texte »
  illisible) ; les trois boîtes sonores (v0.8.6).

- **Retrait sec, `REMOVED_API` vidé.** Un ancien nom (`get_actor`, `ui.get`…) devient
  « inconnu », sans guide de migration — le blocage tient au checker (un `:` ou un module
  hors catalogue est refusé), pas à `REMOVED_API`. Le dictionnaire, gonflé du churn pré-1.0,
  est vidé ; le guidage de migration redevient un engagement quand la 1.0 fige l'API. Le
  contrat « une suppression = une entrée » revient à ce moment-là, sur une surface promise stable.

- **Rangement livré — le mécanisme.** Le JSON n'a PAS bougé (sa prose rédigée reste) : le
  rangement vit dans le loader (`api_reference.py`). `SECTIONS` bucketise les 24 catégories en 8
  (une catégorie hors table rend sa propre section, rien ne se perd) ; `_PROP_HOME` était déjà
  bon (les propriétés tombent dans leurs catégories, qui tombent dans les sections). La couche
  moteur est un **drapeau `engine` par ENTRÉE** (`_ENGINE_KEYS`), plus fin que la catégorie —
  `sfx.play` reste itération quand `sound_box.set_state` est moteur, tous deux dans « Le son » ;
  le calque garde une face simple (`show`/`scroll`) et replie l'avancé (`set_map`). Curé à la
  main comme `_PROP_HOME` : aucune règle ne le dérive. La sidebar rend 8 sections (la seule
  navigation), sous-titres statiques par ancienne catégorie, un fold « Aller plus loin » par
  section. Le découpage à 3 groupes (`get_categories_by_group`) est retiré ; les libellés des
  sections passent par le catalogue de traduction (base anglaise + FR d'office).

- **`TextTable` n'a pas de module.** Sa surface Lua **est** `text.draw` plus les marqueurs
  `$variable` de l'entrée ; clés, balisage et traductions sont résolus au build. Pas de module
  vide inventé par symétrie avec les autres assets nommés.

- **`text.draw` accepte DÉJÀ un littéral écrit sur place** (`api.py`, entrée anonyme
  `_lit_<hash>` dérivée du contenu). « Un texte ponctuel ne doit pas exiger `TextTable` » est
  donc tenu depuis le début, et n'était écrit nulle part. **À documenter, pas à construire.**

- **C'est du rangement, pas une réécriture.** `api_reference.json` décide déjà de la mise en
  rayon, et le loader complète depuis `api.py` : il faut réécrire ses catégories et
  `_PROP_HOME`. Le catalogue, lui, ne bouge que par les quatre renommages.

Bilan : **112 fonctions de catalogue** (100 + 12 par v0.8.6), **24 propriétés** rangées avec
leur objet, **6 mots du langage** enfin listés (`vec2`, `vec3`, `rect`, `wait`, `wait_until`,
`require`), **8 sections** au lieu de 22.

### Amendement (2026-09-24) — le type du récepteur : module fabrique, type opère

**D'où ça vient.** Un relevé du catalogue réel (`RUNTIME_API` : 23 modules, 129 fonctions) montre
que la règle de provenance ci-dessus est posée mais **appliquée à moitié**. Une chose nommée du
projet s'adresse aujourd'hui de quatre façons : par constructeur de référence (`actor.get`,
`interface.get`, `self:collision_box`), par fonction de module qui reçoit son NOM en argument
(`list.index("Menu")`, `interface.image_set("Icone", "on")`, `window.show("Panel", on)`), par numéro
(`layer.*`, `tilemap.*` — légitime, provenance 3) ou par singleton (`music`, `camera` — sain). La
deuxième est exactement ce que la provenance 1 interdit : « une chose nommée du projet → `module.get("Nom")` ».
Ce n'est pas une règle nouvelle, c'est celle-ci **finie**. Le rappel vit dans `ARCHITECTURE.md`,
« Module, type, instance ».

**Ce qui manque à la règle : l'axe du TYPE.** Elle dit d'où vient la chose, pas dans quelle case du
catalogue vivent ses méthodes. Résultat : le type acteur s'appelle `self:` (une clé qui sert de
fourre-tout — `show`/`hide` d'un élément d'interface, `collision_box` constructeur), le type
`interface` n'existe que par un cas spécial du checker, et « quelle valeur désigne quelque chose » a
trois mécanismes.

**Proposition — à relire, rien n'est verrouillé** (chaque point est une décision à prendre, cf. « Ouvert ») :

- **Module fabrique, type opère.** Un module est un système ou une fabrique ; toute action ou donnée
  sur UNE instance nommée est une méthode ou une propriété du type, sur la référence.
- **La clé du catalogue est le nom du type** : `self:` → `actor:` (`self` reste l'instance implicite).
- **Un seul mécanisme de référence** (type déclaré + représentation C), à la place des trois.
- **Migration, par ordre de dette** : `interface` + `list` (18 fonctions : `list.*` 8, `image_*` 6,
  `draw_text`/`clear_text`/`reading`/`skip` 4), puis `window` (7), puis le rangement des clés `self:`.
  `layer.*` et `tilemap.*` ne bougent pas (numéros de matériel). `actor` et `sfx` ne changent presque rien.
- **Coût nul pour le statique** : `interface:get("Menu")` / `window:get("Panel")` se résolvent au build
  en constante ; seules les références de pool portent une valeur.
- **Le catalogue se garde lui-même** : un test refuse une fonction `module.fonction` dont le premier
  paramètre est un domaine d'instance. Sans lui, la règle retombe en trois versions.
- **Retrait sec** (comme les cinq renommages) : pas de `REMOVED_API` avant la 1.0.
- **Ce que ça touche** : `api.py` (clés, `REF_TYPES`), `expr_types.infer_ref_type`, `checker.py`
  (le cas spécial `interface.get`, `_RECEIVER_DOMAINS`), `codegen.py` (`_INVOKE_CUSTOM`), les
  prototypes C (`runtime_api.h`), `api_reference.json` + `_ENGINE_KEYS`, la doc de scripting, les
  scripts des démos.

**Prérequis vérifié (2026-09-24) — le chaînage n'est pas prêt, et c'est un blocage.** Passé dans le
vrai parseur, checker et codegen (`interface:get("X").index` en une expression est la condition
de « ne pas alourdir le cas simple ») :

| Forme | Checker | C émis |
| --- | --- | --- |
| `actor:get("Foe"):move_to(...)` | OK | correct (sans test de `nil` : `runtime_get_actor` peut rendre `NULL`) |
| `sfx:play("Bip"):set_volume(50)` | OK | correct |
| `self:collision_box("hb"):overlaps(...)` | OK | correct |
| `interface:get("Cursor"):show()` | OK | **rien** : `/* invoke sur expression complexe ignoré */` |
| `actor:get("Foe").position` / `.velocity = …` | OK | **`runtime_get_actor(…).position`** : champ brut sur un pointeur, ne compile pas (`gcc`) |
| `self:collision_box("hb").solid = false` | OK | **`actor_get_box(…).solid = 0`** : champ brut sur un `int`, ne compile pas |
| même chose via un `local` (`local a = actor:get(…) ; a.position`) | OK | correct : `actor_get_position(a)` |

**Étape (a) faite le 2026-09-24** — les deux défauts ci-dessous sont réparés, avec
`tests/test_chained_receivers.py` (24 tests : parité chaîné/`local` au niveau du C, refus du
checker ; chaque correction a été retirée à tour de rôle pour vérifier que les tests échouent).
`resolve_prop` accepte un récepteur chaîné (`expr_types._resolve_chained_prop`), le codegen en
tire le C de l'expression (`_prop_receiver_c`), `_invoke` accepte `interface:get(…)`, et le
checker refuse un récepteur chaîné sans type (`math.abs(1):foo()`) ou une méthode/un champ
inconnu sur un acteur ou une référence chaînés. `interface:get("X").y` et
`interface:get("X"):bouge()` sont passés de l'avertissement à l'**erreur** (2026-09-25) : le C
qu'ils émettaient ne compilait pas. Reste ouvert : le chaînage n'est pas testé sur
`self.<enfant>` au-delà de la méthode.

Deux défauts DÉJÀ présents, qui préexistent à l'amendement et que le checker laissait passer :

1. **Un récepteur `interface:get(…)` chaîné est ignoré sans un mot.** `_invoke` n'accepte une
   chaîne que si l'expression rend une référence de `REF_TYPES` ou un acteur ; `interface.get`
   n'en est pas une (c'est le cas spécial du checker). `checker._is_ui_element` affirme pourtant
   que `interface:get("x"):show()` « marche aujourd'hui » : faux côté C. Aucun test ne couvre le
   codegen de cette forme (`test_checker_holes` ne juge que le checker).
2. **Une propriété chaînée saute les getters/setters.** La lecture/écriture d'une propriété passe
   par `_prop_read` quand le récepteur est un nom (`a.position` → `actor_get_position(a)`), pas quand
   c'est un appel : le C émis est un accès de champ brut, accepté par le checker, refusé par `gcc`
   sur une ligne que l'auteur n'a pas écrite. C'est la même famille de faute que
   `test_checker_holes` a déjà fermée pour `interface:get(…).y`.

**Conséquence : la forme `interface:get("Menu").index` n'existe pas.** L'amendement est viable
seulement si le chaînage devient un citoyen de première classe : propriété ET méthode, sur tout
type de référence, un seul chemin de traduction (`_prop_read` / `_invoke` partagés). Sinon la
migration impose `local menu = …` pour chaque usage et contredit le principe d'itération de cette
section (« faire une chose courante tient en quelques lignes »).

**Critères d'acceptation** — l'amendement n'est pas livré tant qu'ils ne tiennent pas tous :

1. **Le chaînage est complet et testé au niveau du C.** Chaque forme du tableau ci-dessus donne le
   même C chaînée ou via un `local` ; un test compare les deux. Aucune forme ne passe le checker
   pour être ignorée (ou refusée par `gcc`) plus loin.
2. **Un type se déclare dans UNE table.** Nom, représentation C, fabrique, peut-il être absent,
   méthodes, propriétés : ajouter un type touche cette table et les fonctions C, rien d'autre
   (ni `REF_TYPES`, ni `C_REF_TYPES`, ni un cas dans le checker, ni `_INVOKE_CUSTOM`). Un test
   déclare un type factice et vérifie qu'il n'a besoin de rien d'autre. Sans ce critère, on aura
   remplacé trois mécanismes par un seul, écrit à la main aux mêmes cinq endroits.
3. **Le cycle de vie s'écrit en cinq verbes, communs à tous les types (décision du 2026-09-25).**
   `:show()`, `:hide()`, `:activate()`, `:deactivate()`, `:destroy()` — une seule porte d'ÉCRITURE
   pour « visible », « actif » et « détruit », sur l'acteur, l'élément d'interface, la fenêtre, la
   boîte de collision. L'ÉTAT se lit par deux propriétés **en lecture seule** (`visible`, `active`) :
   `if menu.visible then`. Jamais `x.visible = false` ni `layer.show(n, on)` : deux portes pour un
   même état, c'est ce que la grammaire refuse, et c'est ce que la v0.16 relevait déjà (cinq façons
   de cacher une chose). Le cas courant tient sans variable : `interface:get("menu"):hide()`.

   - **Chaque type déclare les verbes qu'il supporte**, le vocabulaire est commun mais pas obligatoire.
     Une `collision_box` a `activate`/`deactivate` sans `show`/`hide` ; un `sfx` n'en a aucun. Le
     checker refuse un verbe que le type ne déclare pas.
   - **`destroy` ne s'applique qu'aux instances de POOL** (acteur, `sfx`). Un élément d'interface ou
     une fenêtre est statique, défini au build : `destroy` y est refusé par le checker. Après
     `destroy()`, la référence est périmée et se teste `nil`, comme toute référence de pool.
   - **Le prix est assumé** : une valeur calculée s'écrit
     `if flag then panel:show() else panel:hide() end` là où `window.show("Panel", flag)` tenait en
     une ligne. On ne garde pas `visible = flag` en écriture pour l'éviter — ce serait la seconde porte.
   - **Migration** : retire les écritures `self.visible = …` / `self.active = …` (les propriétés
     restent, en lecture seule), `window.show`, `layer.show`, `list.set_active`. Retrait sec, comme
     le reste. Les démos qui écrivent ces propriétés sont à migrer avec la tranche.
4. **« Absent » a une règle par type, écrite et vérifiable.** Une référence statique n'est jamais
   absente et n'appelle pas de test de `nil` ; une référence de pool peut l'être. Le checker refuse
   ou signale le test inutile, plutôt que de laisser un débutant tester par précaution.
5. **Chaque tranche se juge sur des scripts réels** (démo tactique) : on compte les appels migrés et
   on compare la longueur avant/après. Une tranche qui allonge le cas courant est revue avant la suivante.

**Ordre revu.** (a) ~~Réparer les deux défauts ci-dessus, avec leurs tests~~ — **fait** ;
(b) ~~la table de types unique, appliquée d'abord à `sfx`/`collision_box`/`interface`~~ — **fait le
2026-09-25**, cf. ci-dessous ; (c) ~~migrer `interface` + `list`~~ — **fait le 2026-09-26** (tranche 1 :
les cinq verbes ; tranche 2 : les types d'élément) ; (d) ~~`window`~~ — **fait le 2026-09-26**, avec les fonds ; (e) ~~les clés `self:` → `actor:`~~ — **fait le 2026-09-26**.

**Étape (b) faite (2026-09-25) — critère 2 tenu pour les types de référence.** `api.REF_TYPE_TABLE`
déclare `sfx`, `collision_box` et `ui_element` (`RefType(c_type, variable, hint)`). Ce qui était écrit
à la main aux mêmes endroits s'en dérive : `REF_TYPES` (vue vivante de la table), `C_REF_TYPES`
(retiré), `_REF_VARIABLE` des snippets (retiré), et le cas spécial d'`interface.get` du checker
(`_is_ui_element`, `_UI_ELEMENT_METHODS`, `_check_ui_element_field`, retirés) et du codegen
(`is_ui_element_call`, retiré). `self:show` / `self:hide` ont rejoint `ui_element:` : la clé `self:`
n'est plus un fourre-tout d'interface (17 méthodes, toutes d'acteur). Le checker juge un membre inconnu
de n'importe quel type par deux aides génériques, l'`hint` du type s'ajoutant à l'erreur (celui
d'`ui_element` reprend le guidage vers `interface.image_move` / `image_set`).
`tests/test_ref_type_table.py` (12 tests) déclare un type factice `gizmo` par trois gestes (une ligne de
table, ses entrées de catalogue, ses fonctions C) et vérifie qu'il se vérifie et se traduit — chaîné ou
non — sans toucher `checker.py` ni `codegen.py`, ni aucune autre liste ; il fige aussi l'accord table ↔
catalogue (pas de type sans fabrique, pas de clé `<type>:` inconnue).

**Étape (c), tranche 1 faite (2026-09-25) — les cinq verbes sur les types existants.** `self:` gagne
`show`/`hide`/`activate`/`deactivate` (`destroy` y était déjà), `collision_box:` gagne
`activate`/`deactivate`, `ui_element:` garde `show`/`hide`. Les verbes sont de simples entrées du
catalogue : « le type déclare ses verbes, le checker refuse les autres » est déjà ce que fait le catalogue
(un `hb:show()` ou un `interface:get("X"):destroy()` est une méthode inconnue). `ApiFunc.fixed_args` porte
la valeur constante d'un verbe (`:hide()` = `ui_element_show(h, 0)`), ce qui retire les deux émetteurs
dédiés d'`ui_element` de `_INVOKE_CUSTOM`. `visible` / `active` sont en **lecture seule** sur l'acteur et la
boîte, et `ui_element.visible` naît (lecture, `ui_element_is_visible` — elle remonte la chaîne des parents).
`tests/test_lifecycle_verbs.py` fige le contrat (paires, `destroy` réservé au pool, état en lecture seule,
C émis, refus) et tient `_PENDING` : les trois portes de module qui restent — `list.set_active`,
`window.show`, `layer.show` — partiront avec leur tranche. Écritures migrées : les tests, les docs
(`ARCHITECTURE.md`, `scripting-reference.md`, guide collision) ; aucune démo n'écrivait `visible`/`active`.
Reste dans cette étape : voir la tranche 2, ci-dessous.

**Étape (c), tranche 2 faite (2026-09-26) — `interface.get` rend le type RÉEL de l'élément.** Lu dans
la mise en page au build (`scripting/project_names.ui_ref_kinds` → `BuildContext.ref_kinds`, même
dictionnaire pour le checker et le codegen), le type d'`interface:get("X")` est `list`, `image`,
`text_region`, ou `ui_element` pour un conteneur (aucune capacité propre : il EST le type de base).
Les trois premiers HÉRITENT de `ui_element` (`RefType.base`) : `menu:hide()` et `menu.visible` sont
ses membres, cherchés par `api.ref_member` sur le type puis ses ancêtres. Comme une liste est un
index de `g_ui_lists` et que le cycle de vie veut l'index d'ÉLÉMENT, chaque type déclare sa conversion
(`RefType.to_base` → `ui_list_element`/`ui_image_element`/`ui_region_element`, dans `gba_engine.h`) que
le codegen applique au récepteur d'un membre hérité : `ui_element_show(ui_list_element(menu), 0)`.
`UIListInfo` gagne `elem` (en dernier, pour les initialiseurs positionnels).

Migré, retrait sec : `list.count/set_count/index/set_index/first/row/active/set_active`
→ `menu.count`, `.index`, `.first`, `.active` (lecture seule), `menu:row(n)` (rend une `text_region`,
donc `menu:row(1):draw("…")`), `menu:activate()`/`:deactivate()` ; `interface.image_set/state/play/
move/dx/dy` → `heart.state = "vide"` (par NOM, dans le sprite de l'image que le récepteur désigne —
`element_of` : le littéral d'`interface.get`, ou un `local` affecté une seule fois), `heart:play()`/
`:pause()`, `cursor.offset` (un `vec2`, construit dans la façade sur les trois entiers du moteur) ;
`interface.draw_text/clear_text/reading/skip` → `box:draw(…)`, `box:clear()`, `box.reading`,
`box:skip()`. Aucune fonction de module ne prend plus un nom d'élément en premier argument. Trois
domaines disparaissent (`region`, `image`, `ui_list`) ; le nom d'un élément se cite par un seul,
`ui_element`, y compris pour renommer un conteneur — qu'aucun domaine ne couvrait. `infer_ref_type`
suit `interface:get("Menu"):row(1)` et `menu:row(1)`, donc un type qui rend un autre type.
Les paires (zone, texte) que le build mesure (`validator`, débordement et glyphes absents) se lisent
sur `box:draw("clé")` par `refactor.iter_call_sites` (`DOMAIN_UI_ELEMENT`), chaîné ou via un `local`.

Vérifié sur du VRAI : les trois démos (TacticsDemo — menu de liste —, MyGame et OrbitTest — dialogue,
curseur d'image) sont migrées et se construisent en ROM complète, sur des copies ; le C émis compile.
`tests/test_ui_typed_elements.py`, `tests/test_ref_type_table.py` (héritage) et `test_lifecycle_verbs.py`
(`_PENDING` ne garde plus que `window.show` et `layer.show`) tiennent le contrat.

Ce qui reste, dit franchement :

- ~~**Les colonnes `region` / `image` d'une table de données** n'ont plus de consommateur~~ **Réglé le
  2026-09-26.** La cellule d'une telle colonne est typée d'après sa colonne : `data.Dialogue[i].boite`
  est une `text_region`, `data.Dialogue[i].icone` une `image` (`RefType.column`, `project_names.
  data_column_kinds`, clé `data.Table.colonne` dans `ref_kinds` — un seul dictionnaire pour « ce que rend
  une chose nommée », sans paramètre de plus). `data.Dialogue[i].boite:draw("…")`, `.reading`,
  `icone.offset = …`, `icone:pause()` se jugent et se traduisent comme après `interface:get(…)`, le C lisant
  l'entier de la cellule — que le build a rangé comme l'index de la zone : vérifié sur une copie
  d'OrbitTest, ROM complète. Le handle se lit ; la CELLULE reste constante en ROM (l'écrire est refusé),
  seule une propriété de l'élément désigné s'écrit. Limite : l'état d'une image par NOM (`icone.state =
  "vide"`) reste refusé sur une cellule, le build ne sachant pas dans quel sprite chercher.
- **Pas de `button` ni de `container` typé** : l'éditeur n'a pas ces natures. Un nouveau widget se
  déclare dans la table (une ligne, ses membres, ses fonctions C), rien d'autre.
- **L'état d'une image ne s'écrit que par un nom connu au build** : un `local` réaffecté à deux
  images, ou un paramètre, est refusé (il faudrait deviner dans quel sprite chercher).
**Étape (d) faite (2026-09-26) — les fonds et les régions de window.** `layer:get(n)` rend un
`background_layer`, `window:get("Nom")` un `window_region` (types à part, sans le nom du module : un
type `layer` donnerait à `layer.priority` deux lectures). Verbes `show`/`hide`, état `visible` en
lecture seule ; `priority`, `scroll` (un `vec2`, converti dans la façade sur les deux entiers du
moteur) et `map` sont des propriétés ; `scroll_by` et les tuiles de la carte (`set_tile`, `get_tile`,
`set_tile_palette`, `set_tile_flip`, `fill`) des méthodes — le module `tilemap` disparaît, il
adressait le même fond par son numéro. `window_region` garde `set`, `set_layer`, `get_layer`,
`set_obj`, `set_blend`. Retrait sec ; `_PENDING` de `test_lifecycle_verbs.py` est vide. **Le numéro
est borné par les fonds de la scène** (`api.LAYERS_BY_MODE` × `Scene.render_mode`, passé au checker par
`lua_compiler` : `BuildContext.layer_numbers`) : un numéro écrit en clair qu'elle n'a pas est refusé, un
numéro calculé n'est pas jugé. **Anticipé mais invisible** (décision de Victor, 2026-09-26) : les modes
affine et bitmap ne sont pas offerts à l'utilisateur, donc rien de ce qu'il lit — doc, indice du type,
messages du checker — ne parle de mode ; `tests/test_layer_window_refs.py` le garde. Aujourd'hui seul le
mode 0 est offert, les quatre fonds existent toujours. Les fonds affines et bitmap auront leur propre type
avec leur rendu. Vérifié sur une copie d'OrbitTest
dont un script emploie toute la famille : ROM complète, C émis conforme. Aucune démo n'utilisait ces
appels. Une limite : `layer:get(n)` s'est écrit `.` un temps comme `interface.get` — le passage de tous
les modules à `:` est fait depuis (voir plus haut).

- **`ui_list_row` rend -1 hors bornes**
 : `menu:row(9):draw(…)` écrit dans la région -1, ignorée par le
  moteur. Une valeur de garde et non un `nil`, comme pour `sfx` et les boîtes.


Ce qui reste, dit franchement :

- ~~**`actor` n'est pas dans la table.**~~ **Fait le 2026-09-26 (étape e).** `actor` est un type de
  `REF_TYPE_TABLE` (`Actor*`, variable `self`) : ses méthodes sont `actor:<m>`, ses propriétés `actor.<champ>`
  (52 entrées renommées, dont `api.REF_ACTOR`). **`self` n'est pas le type, c'est un récepteur** : tout nom
  qui ne tient pas une référence typée est un acteur (`self`, `other`, un acteur de la scène), et une variable
  qui tient `actor:get(…)` / `actor:spawn(…)` est désormais une référence du type `actor` — mêmes membres,
  par le chemin générique. L'écriture ne change pas : `self:move_to(…)`, `other.velocity = …`. Deux
  conséquences réglées : (1) le type et le MODULE partagent leur nom (`actor.position` vs `actor:get`),
  donc les propriétés d'un type ne se lisent que sur une référence de ce type (`resolve_prop`,
  `module_members`, la complétion), et `actor.position` — comme `camera.nawak`, silencieux avant — est une
  erreur du checker qui nomme les membres du module ; (2) la référence affiche `self` dans les snippets
  et les libellés (`api.module_call_form` / `canonical_key` traduisent dans les deux sens). Vérifié : les
  quatre démos se construisent en ROM de MÊME taille qu'avant (C émis équivalent). Restent des chemins
  propres à l'acteur, légitimes : les enfants de prefab (`self.bras`), la lecture `self.<enfant>` et
  `_is_actor_expr` — un acteur n'est jamais « absent » de la même façon qu'un `sfx`.
- **« Absent » n'a pas eu besoin d'un champ.** Dans le C émis, `nil` vaut 0 et une référence absente
  vaut 0 : `if p ~= nil` marche pour un acteur, un effet et une boîte (test dédié). Les « trois façons »
  n'en étaient qu'une. Reste le critère 4 : refuser le test de `nil` inutile sur une référence statique
  (`ui_element`), et l'écrire par type.
- **`ui_element` reste UN type** aux capacités déclarées (`show`, `hide`), comme l'accepte la relecture.
  Le scinder en `ui_list` / `image` / `text_region` ajoute des lignes de table, pas du code — c'est
  l'étape (c), et elle demande que le checker connaisse la nature de l'élément au build.
- **La traduction C atypique reste un cas de `_INVOKE_CUSTOM`** (`ui_element:show` → `ui_element_show(h, 1)`,
  `sfx:set_volume`, l'overload `collision_box:overlaps`) : ce qui s'émet change, pas ce que le type est.
- **La suite `tests/ui` plante sur un accès mémoire Qt** (déjà avant ce changement) : aucun échec relevé
  avant le plantage, mais je n'ai pas de verdict sur ses derniers tests.

### Ouvert

- **Le récepteur direct `Boss:move_to()`.** Plus court, mais collision possible avec un local ou un
  module (un acteur nommé « input »), et l'acteur peut être détruit. Recommandation : garder `get()`,
  honnête sur le `nil`. À trancher.
- ~~**Le type d'une référence d'interface.**~~ **Tranché le 2026-09-25 :**
  `interface:get("X")` rend le type réel de l'élément (image, liste, bouton, région…), connu
  du projet au build ; le checker le déduit et n'emploie pas un `ui_element` permissif.
- **Dire « absent » d'une seule façon.** `nil` (acteur), `0` (`sfx`, boîte de collision), rien
  (interface). À unifier, ou à écrire par type.
- **Les calques par nom.** `layer:get("Fond")` en plus du numéro ? Recommandation : attendre un besoin.
- ~~**Les calques et les cinq verbes.**~~ **Tranché le 2026-09-26 :** une seule porte, la référence
  numérotée — `layer:get(0):hide()`. Un raccourci `layer:hide(0)` recréerait le doublon que la grammaire
  refuse, et devrait reproduire le contrôle du numéro (borné par le mode de la scène) que la référence porte une fois.
- **`self:collision_box("hitbox")`** : garder ce constructeur déguisé en méthode, ou le ranger sous
  un module (`self.boxes.get`) ? Tant qu'aucun module n'y prétend, il reste — la règle doit le nommer
  comme exception, pas le subir.

- **`#data.Objets`** — le nombre de lignes d'une table de données. Évident, absent. À ouvrir,
  ou à refuser par écrit dans la référence de scripting.
- **La référence de scripting adopte-t-elle les mêmes huit sections ?** Deux plans différents pour la même
  API rouvriraient exactement le problème qu'on ferme ici.
- **v0.13 hérite de ce rangement** : les palettes de blocs de l'édition mixte seront ces huit
  sections. À vérifier quand le chantier démarre, pas maintenant.
- **`ARCHITECTURE.md` a été renommé avec le catalogue** — il portait les anciens noms
  (`get_actor`, `ui.get`, `text.draw_in`, une douzaine d'endroits) et a servi de liste de
  contrôle du renommage, comme prévu. Fait ; `docs/scripting-reference.md`, le guide
  utilisateur et `SCRIPTING.md` ont suivi.

### Relecture de conception (2026-09-24) — conditions de verrouillage

L'amendement donne une direction cohérente : la provenance rend l'acquisition d'une chose
lisible, et « module fabrique, type opère » remet les opérations d'instance sur leur
récepteur. Cela améliore déjà les trois objectifs : compréhension, usage courant et
extensibilité. **Ce n'est toutefois pas encore suffisant pour verrouiller la règle** : les
cas ouverts ci-dessous doivent devenir un contrat, sinon chaque nouveau type recréera un cas
spécial.

- **Le module ne « fabrique » pas toujours.** `actor.spawn` crée, `sfx.play` agit puis rend une
  référence, `actor.get` et `interface.get` l'acquièrent. La phrase de règle devient donc :
  **« le module gère, crée ou acquiert ; le type expose l'état et les opérations d'une
  instance »**. Elle décrit les quatre provenances sans appeler constructeur une recherche
  statique.

- **Chaque type déclare un contrat de référence.** Pour toute référence, le catalogue doit
  connaître son type, sa représentation C, sa durée de vie, son identité et sa valeur
  d'absence. La recommandation est `nil` pour toute acquisition qui peut échouer ; si un type
  conserve une autre forme, elle doit être écrite ici avec sa raison. Cela ferme l'actuel
  triplet `nil` (acteur), `0` (SFX/boîte) et rien (interface).

- **Interface — singleton et éléments typés (décision du 2026-09-25).** `interface` est le
  singleton de la mise en page active de la scène. Il acquiert un élément par son nom ; le nom
  et la nature de cet élément sont connus au build, donc cette acquisition ne fait ni recherche
  ni allocation runtime. L'élément obtenu est une instance de son type réel — `list`, `image`,
  `button`, `text_region`, `container`, ou un type futur — et porte lui-même état et actions.
  Les éléments ne sont pas des modules qui reçoivent un nom en premier argument : ce sont les
  objets typés que l'Interface contient et rend accessibles.

  ```lua
  local menu = interface:get("Menu")      -- type `list`, connu au build
  menu.index = 2
  menu:activate()
  menu:show()
  if menu.visible then ... end            -- lecture seule : l'écriture passe par les verbes

  interface:get("Menu"):hide()            -- cas courant : un geste, sans variable

  local heart = interface:get("Heart")    -- type `image`
  heart.state = "empty"
  heart:play()

  local start = interface:get("Start")    -- type `button`
  if start.pressed then ... end
  ```

  Le cycle de vie (`show`, `hide`, `activate`, `deactivate`, et les propriétés de lecture
  `visible` / `active`) vit sur le type de base `ui_element` (critère 3 ci-dessus ; `destroy`
  y est refusé, un élément est statique) ; les propriétés et actions spécialisées vivent sur leur
  type concret. Ainsi `menu.index` est valable, `heart.state` est valable, mais
  `heart.index` et `menu.state` sont refusés par le checker. Ajouter un widget revient à
  déclarer un type et ses capacités dans la table unique des références, jamais à ajouter un
  cas spécial à `checker.py` ou `codegen.py`.

  Les portes actuelles qui prennent un nom d'élément migrent sans doublon : `list.*`,
  `interface.image_*`, `interface.draw_text` / `clear_text` / `reading` / `skip` deviennent
  les propriétés ou méthodes de `list`, `image` et `text_region`. Le déplacement de
  `self:show` / `self:hide` est également achevé : l'acteur ne porte plus les gestes d'un
  élément d'interface. La navigation montre d'abord les opérations ordinaires du type ; ses
  capacités spécialisées restent sous « Aller plus loin ».

- **Une acquisition dérivée est une forme nommée, pas une exception muette.**
  `self:collision_box("hitbox")` reste légitime si elle est déclarée comme acquisition d'un
  sous-objet de l'instance ; un futur capteur, inventaire ou équipement suivra alors la même
  forme, au lieu d'inventer son propre constructeur déguisé.

- **Le garde-fou doit porter sur toute opération d'instance.** Le test proposé refuse déjà
  `module.fonction("nom_d_instance", …)`. Il doit aussi refuser une fonction de module qui
  reçoit une référence d'instance (`interface.move(element, …)`) ou tout autre mécanisme qui
  contourne méthode/propriété. La règle tient ainsi contre les futurs ajouts, pas seulement
  contre les formes déjà présentes.

- **Un module du moteur est un récepteur singleton.** Il ne se comporte pas grammaticalement
  autrement qu'une instance : son état s'écrit `module.propriété`, son opération
  `module:action(…)`. Ainsi `music.volume = 60` / `music:play("Combat")`,
  `scene.frame` / `scene:switch("Village")`, `sfx:play("Clap")` et
  `actor:spawn("Bullet", pos)` suivent exactement le même axe que
  `clap.volume = 70` / `clap:stop()`. Le module et le type ne se distinguent que par leur
  durée de vie et leur rôle (singleton système, fabrique ou type d'instance), jamais par une
  ponctuation à mémoriser. **Exception nommée :** une bibliothèque sans état ni identité
  runtime garde l'appel pointé (`math.abs(x)`), car `math` n'est pas un récepteur du moteur.
  **Livrée le 2026-09-26** (décision de Victor : y compris `input`, `save` et `text`, sans autre
  exception que `math`). Le catalogue garde ses clés `module.fonction` — `RUNTIME_API`, le checker,
  le codegen et le renommage n'ont qu'une forme à traduire —, et seule l'ÉCRITURE change : le parseur
  ramène `module:f(…)` à `ExprCall(module.f)` (`api.MODULE_CALLS` : les modules qui portent des
  fonctions, moins `api.STATELESS_MODULES = {math}`), et retient le point écrit à l'ancienne
  (`ExprCall.dotted`) que le checker refuse en disant quoi écrire. Retrait sec, comme le reste. Les
  diagnostics et la référence parlent la forme écrite (`api.modernize_message`,
  `api.module_call_form` / `canonical_key`) ; la complétion propose les ACTIONS derrière « : » et
  l'ÉTAT derrière « . » (`camera.bound`, `scene.frame`, `input.axis` restent des propriétés). Ce qui a
  suivi : le repérage structurel du renommage (`refactor._call_key`), la réservation de surface de
  texte (`font_emit._FREE_WRITE_RE` lit `text:draw`), les tooltips de l'arbre de scène, les
  démos (les six projets), les docs et 55 fichiers de tests. Les six démos se construisent en ROM. Le
  tout est tenu par `tests/test_module_colon.py`, dont un test paramétré sur TOUTE fonction de module
  du catalogue (le point est refusé pour chacune, sans en nommer aucune).


#### Proposition — le singleton `mixer` : jouer simplement, diriger finement

Le son possède déjà trois **bus de sortie** matériels : les effets, le module musical qui
boucle et le jingle qui se superpose. Ils existent aujourd'hui, mais sont cachés derrière des
noms de boîtes qui ont une autre responsabilité (`sound_box.set_volume`,
`jingle_box.set_volume`, `music.set_volume`). Une `SoundBox` / `MusicBox` / `JingleBox` est
un automate de **sélection** ; elle n'est pas un bus de **mixage**.

**Décision proposée : `mixer` devient le singleton sonore d'itération.** Il porte les actions
ordinaires et les trois niveaux de sortie, tous lisibles et modifiables. Un auteur qui veut
entendre quelque chose n'a pas à connaître les boîtes :

```lua
mixer.music_volume   = 60
mixer.effects_volume = 80

local clap = mixer:play_sfx("Clap")
clap.volume = 70

local village = mixer:play_music("Village")
local victoire = mixer:play_jingle("Victoire")
```

| Porte cible | Nature | Remplace |
| --- | --- | --- |
| `mixer.effects_volume` | propriété lecture/écriture : bus de tous les effets | `sound_box.set_volume` |
| `mixer.music_volume` | propriété lecture/écriture : bus du module musical | `music.set_volume` |
| `mixer.jingle_volume` | propriété lecture/écriture : bus du jingle | `jingle_box.set_volume` |
| `mixer:play_sfx(name)` | action, rend une référence `sfx` | `sfx.play` |
| `mixer:play_music(name)` | action, rend la référence `music` de l'unique lecture musicale | `music.play` |
| `mixer:play_jingle(name)` | action, rend la référence `jingle` de l'unique jingle superposé | `music.jingle` |
| `mixer.music` / `mixer.jingle` | propriétés lecture seule : lecture active, ou `nil` | — |

**Les trois sorties passent directement par leur référence.** `mixer` acquiert ou remplace une
lecture ; ensuite, le type opère. Il n'existe donc pas de raccourci parallèle
`mixer:stop_music()` qui doublerait `music:stop()` :

```lua
local clap = mixer:play_sfx("Clap")
if clap.playing then clap:stop() end

local village = mixer:play_music("Village")
village:pause()
village:resume()
village:fade_to("Combat", 30)

local victoire = mixer:play_jingle("Victoire")
if victoire.playing then victoire:stop() end
```

`sfx` porte l'état de CET effet (`playing`, `volume`, `pitch`, `panning`) et ses actions
(`stop()`). `music` et `jingle` portent au minimum `playing` et leurs actions de transport ;
leurs niveaux restent les propriétés de bus du `mixer`, car le matériel ne possède qu'un scaler
pour chaque sortie. Une nouvelle musique ou un nouveau jingle remplace la lecture unique : la
référence précédente devient périmée et toute opération dessus est sans effet. Le contrat
unifie ainsi les trois types sans mentir sur leur cardinalité (`sfx` 0..N ; `music` et `jingle`
0..1).

Le module `sfx` cesse ainsi d'être à la fois fabrique et type : `sfx`, `music` et `jingle` sont
les types de lecture ; `mixer` est le système qui les lance.

**Avancé — les boîtes ne disparaissent pas, elles changent de niveau.** Elles restent des
singletons spécialisés, repliés sous « Aller plus loin », et n'exposent plus les volumes :

```lua
sound_box:set_state("Caverne")   -- choisit les effets des actions animées
music_box:trigger("combat")      -- laisse l'automate choisir morceau et transition
jingle_box:set_state("Boss")     -- choisit vers quel jingle pointe une action
```

Cette séparation donne deux portes sans doublon : `mixer` règle **ce qui sort**, les boîtes
décident **ce qui est choisi**. Elle rend aussi l'état du mixage interrogeable pour un jeu
musical, sans exposer les canaux Maxmod : un canal matériel est volatile et peut être repris ;
l'API doit dire quel bus, quelle lecture et quel état l'auteur a demandés. Une horloge musicale
(mesure / temps / battement) est un besoin distinct à ouvrir sur les informations réellement
accessibles au lecteur de modules ; elle ne doit pas être simulée avec `scene.frame`.

Le `master_volume` n'est pas ajouté par symétrie : il demande un besoin réel et une vérification
de la porte matérielle disponible. Les anciens noms seront retirés sans alias avec la migration
v0.16, conformément à la règle pré-1.0.

**Critère de verrouillage :** ajouter un type ne demande que sa déclaration (représentation,
acquisition, absence, propriétés, méthodes) et aucun cas spécial dans le checker ou le
codegen, hors traduction C réellement atypique. À cette condition, l'API est à la fois
facile à comprendre, facile à employer et extensible sans dette de grammaire.

---

## v1.0 — Le pipeline 2D complet

### L'objectif concret — cinq genres

La v1.0 était écrite comme un jalon de *validation* (« un deuxième jeu de démo, plus
stabilisation »). Elle porte en réalité une **affirmation de capacité** : à la v1.0, le
logiciel absorbe un projet 2D de production, de bout en bout.

Une affirmation pareille n'est décidable que si on dit *quoi*. Voici le critère, sur le modèle
de « V-Rally 3 » pour la v3.1 — une cible se compare, une capacité s'étend indéfiniment :

| Genre | Ce qu'il exerce en propre |
| --- | --- |
| **Platformer** | gravité scriptée, pentes, collision de tuiles, caméra en suivi |
| **Metroidvania** | état persistant entre scènes, retour arrière, déverrouillages |
| **RPG** | tables de données (objets, sorts), menus, dialogues, sauvegarde longue |
| **Tactique** (Advance Wars, FFT en vue de dessus) | grille, liste d'unités, recherche de chemin, curseur |
| **Gestion** (Zoo Tycoon) | N entités à état propre, économie, budget OAM sous tension |

Les trois derniers attendaient la v0.7, qui est livrée. Quant aux deux premiers, ils étaient
écrits ici comme **atteignables aujourd'hui** : la revue du 2026-08-19 (juste au-dessus) dit
que c'est faux, et où. Un platformer sans sous-pixel (v0.19) n'a ni accélération ni saut à
hauteur variable ; un metroidvania sans collection persistante (v0.20) écrit une variable par
coffre. Les deux genres réputés acquis sont donc, en réalité, les deux qui ouvrent la liste.

### Le deuxième jeu de démo se choisit dans cette liste

Et **pas parmi les deux premiers**. Un platformer ne validerait presque rien de neuf : il
n'exerce ni les tables, ni les menus, ni la sauvegarde longue. Un proto-tactique ou un
proto-gestion, à l'inverse, échoue immédiatement si la v0.7 a manqué sa cible — ce qui est
exactement ce qu'on attend d'un jeu de validation.

Le reste de la version est ce qu'il était : stabilisation du runtime et de l'éditeur,
documentation utilisateur.

### Ce qu'une « première version stable » exige, et qui n'est pas une fonctionnalité

Quatre points sans lesquels le mot « 1.0 » ne tient pas. Aucun n'ajoute de capacité au moteur ;
tous conditionnent le fait que quelqu'un puisse réellement bâtir dessus. **Le premier est
réglé** ; il reste trois.

- ~~**Une licence.**~~ **FAIT.** Le point était plus aigu ici qu'ailleurs : l'éditeur **copie
  son propre C dans la ROM de l'utilisateur** (`gba_engine.h` et les sources générées), donc
  sous une licence unique tout jeu construit avec l'outil serait devenu un travail dérivé sous
  GPL. D'où **deux licences, et c'est la découpe qui compte** : `LICENSE` (GPL-3.0-only) couvre
  l'ÉDITEUR, `runtime/LICENSE` (zlib) couvre le moteur recopié dans la ROM — le jeu et sa ROM
  appartiennent entièrement à leur auteur, sans rien à publier ni à demander.
  `THIRD-PARTY-NOTICES.md` recense les composants redistribués, obligation déjà active
  puisqu'ils sont dans l'installateur. Reste hors de ce point, et à trancher ailleurs : le nom
  et la marque, où « GBA » porte un risque Nintendo.
- **Des formats que git sait relire** — devenu la **v0.24**, où il est traité avec le build et le chargement, parce que la revue du 2026-08-19 a montré qu'il ne se comporte pas comme une finition de v1.0 mais comme un préalable. Aujourd'hui un fond fait 688 lignes et la carte de
  collision d'une scène environ 600, à raison d'**un entier par ligne** ; les couleurs sont
  des entiers BGR555 décimaux. Ce n'est pas qu'un défaut de lisibilité : chaque modification
  de scène produit un diff illisible, l'historique devient inexploitable, et deux personnes ne
  peuvent pas toucher la même scène sans un conflit qu'aucun humain ne résout à la main. **Ça
  plafonne le logiciel au travail solitaire**, ce qui est incompatible avec « projet de
  production ».

  La correction est connue et petite : une ligne de texte par rangée de grille — c'est
  exactement ce que `tileset` fait déjà, une chaîne hexadécimale par tuile, et c'est de loin
  la partie la plus lisible du sidecar. Et les couleurs en hexadécimal (`#39A8FF`), les deux
  formes acceptées en lecture.
- **Des modèles de départ.** Un seul projet de démo existe (Pong). Un modèle « platformer »
  enseigne l'API sans qu'on lise une ligne de documentation, et c'est ce qui décide qu'on
  reste après la première heure. Même famille que le deuxième jeu de démo : du contenu qui
  enseigne, pas une fonctionnalité.
- **La vérification que ça tient à l'échelle** (le chargement paresseux lui-même est en v0.24 ; ce qui reste ici, c'est la vérification sur un vrai projet). `Project.load()` charge tout, tout de suite —
  chaque sidecar de chaque collection. Pong et ses 118 fichiers vont très bien ; quarante
  scènes et deux cents sprites, personne n'en sait rien. L'affirmation « absorbe un projet de
  production » se vérifie ou s'écroule exactement là, et c'est le deuxième jeu de démo qui
  tranchera.

### Ouvert

- Lequel des trois genres bloqués sert de démo. À trancher quand la v0.7 est livrée, sur ce
  qu'elle rend réellement confortable.
- ~~Les menus et listes (curseur, défilement, sélection)~~ **Tranché le 2026-08-19 : le moteur
  en prend une part, et c'est la v0.22.** La question posée ici — « si les trois genres à menus
  le rendent pénible, c'est ici que ça se verra » — a reçu sa réponse d'un projet cible à arbre
  de compétences, inventaire et équipement : ce n'est pas un confort qu'on juge après coup,
  c'est un tiers du contenu, entièrement à la charge de l'auteur.

---

## Au-delà de la v1.0

### Chantier transverse — l'allocateur de ressources matérielles

Ne porte pas de numéro de version : il **se déclenche par un événement**, pas par une date —
le jour où une ressource matérielle a son deuxième consommateur. Le viewport de caméra
(`Camera.frame_w/h`, réglé le 2026-08-24) a d'abord semblé ne PAS en être un — une seule
caméra active à la fois, allocation fixe WIN0=caméra/WIN1=scène. **Corrigé le 2026-08-25** :
c'en était bien un. Le second consommateur n'a pas besoin d'être simultané À L'EXÉCUTION pour
poser le problème — il suffit que deux INTENTIONS différentes (le cadre d'une caméra, un
panneau UI) veuillent la même ressource dans la MÊME scène, même si une seule caméra tourne à
la fois. `codegen/window_alloc.py` est livré : c'est la première instance réelle de ce
chantier, cf. ARCHITECTURE.md, « Windows — le pochoir ». Le candidat qui reste vraiment ouvert
est l'**écran partagé** de la v2.0 (plusieurs caméras actives SIMULTANÉMENT — un arbitrage
différent, à l'exécution).

#### Le problème

Les ressources du matériel ne correspondent pas aux concepts du game design. Une window GBA
n'est pas une fonctionnalité : c'est une ressource. Or une caméra veut une région de rendu,
l'UI un rectangle de découpe, un acteur un masque de visibilité, un effet un pochoir — quatre
intentions distinctes qui réclament le même stock de trois slots.

Écrire `camera.window = WIN0`, `ui.window = WIN1` fabrique le bug le plus classique de
l'ingénierie logicielle : chaque fonctionnalité marche parfaitement, jusqu'au jour où deux
d'entre elles servent en même temps. Et les windows ne sont que le premier exemple — sprites,
palettes, VRAM, OAM, DMA, canaux sonores, matrices affines posent le même problème.

Le principe et ses trois niveaux (intention / ressource logique / ressource matérielle) sont
décrits dans [ARCHITECTURE](ARCHITECTURE.md), « Ressources matérielles — l'auteur ne les nomme
jamais ». Ce jalon est son implémentation.

#### Décisions verrouillées

- **Deux allocateurs, pas un.** Ce qui se résout au BUILD (palettes, VRAM, tuiles) et ce qui
  se résout à la FRAME (OAM, DMA, windows disputées) ne partagent qu'un vocabulaire. Le
  premier peut être coûteux et **doit** parler à l'auteur ; le second tourne 60 fois par
  seconde et n'a personne à qui parler. `palette_alloc.py` et `vram_alloc.py` sont déjà des
  instances correctes du premier — ce chantier ne les refait pas, il leur donne une famille.
- **Le rang fait partie de la ressource.** `WINR_0` > `WINR_1` > `WINR_OBJ` > `WINR_OUT` est
  une priorité câblée : traiter deux slots comme équivalents produit une allocation valide et
  une image fausse. C'est le mode de panne à empêcher par construction, parce que rien ne le
  signalera au runtime.
- **Déterminisme avant optimalité.** Pas d'ordonnancement par priorités déclarées
  (`critical`/`high`/`medium`) : une allocation qui change parce que l'auteur a posé un sprite
  sans rapport casse son UI sans qu'il puisse faire le lien. Un ordre de résolution stable,
  documenté et ennuyeux vaut mieux qu'un ordre optimal — il est prévisible, et il est
  testable.
- **Les solutions de repli proposées doivent exister matériellement.** Fusionner deux masques
  identiques, reprogrammer par scanline en HBlank (donne réellement plus de régions, au prix
  de cycles), renoncer au masquage, assigner à la main. Pas de « clipping logiciel » pour un
  calque tuilé en mode 0 : il faudrait réécrire la tilemap. Une liste courte et vraie, sinon
  l'éditeur promet ce que la machine ne fait pas.
  - **Précisé le 2026-08-25, pour les windows** : « renoncer au masquage » silencieusement est
    justement le pire cas ici — une région qui ne cache rien à la place d'une région découpée
    est un bug visuel sans signal. `window_alloc.py` choisit donc l'échec de build NOMMÉ
    plutôt que ce repli-là : pas de fusion possible (rangs différents, `WINR_0`/`WINR_1` ne
    sont pas interchangeables), pas de HBlank par scanline (hors périmètre v1), pas
    d'assignation à la main proposée (ce serait renommer la ressource matérielle). Un futur
    consommateur d'un AUTRE type de ressource peut légitimement choisir un vrai repli parmi la
    liste — ce n'est pas une règle générale, c'est ce que « exister matériellement » a donné
    pour CE cas.
- **L'assignation matérielle reste visible, dans un panneau avancé.** Le principe « l'auteur
  peut descendre jusqu'au matériel » n'est pas suspendu : il ne nomme plus la ressource pour
  obtenir un masque, mais il peut voir laquelle lui a été donnée, et la forcer.

#### Ce qui est fait (2026-08-25) — les windows

1. **Le principe est écrit** (cf. ARCHITECTURE), pour que rien de neuf ne lie un concept de
   haut niveau à un slot matériel.
2. **`WindowSlot.region` n'est plus un index matériel côté auteur** — renommé `.name`, résolu
   par `codegen/window_alloc.py`.
3. **La rupture assumée sur l'API Lua est faite pour les windows** :
   `window.set`/`window.show`/`window.is_visible` adressent maintenant par nom
   (`DOMAIN_WIN_REGION`), comme `window.set_layer` le faisait déjà — un seul schéma, plus de
   numéro matériel brut atteignable depuis un script.

#### Ouvert

- Jusqu'où va l'allocateur de frame (OAM, DMA, matrices affines). Un arbitrage par frame est
  un vrai coût CPU ; il se décide sur un cas mesuré, pas à l'avance — les windows n'en avaient
  pas besoin (résolubles au build, cf. ARCHITECTURE.md « Deux allocateurs, pas un »).
- L'assignation matérielle « visible dans un panneau avancé, et forçable » (décision
  verrouillée ci-dessus) n'est pas construite pour les windows — l'auteur voit le budget
  (N/2) mais pas quelle intention a reçu quel rang. À rouvrir si un projet réel en a besoin
  pour déboguer un recouvrement.

#### Le cas mesuré de l'allocateur de frame — l'OAM dynamique (2026-09-10)

La décision « l'allocateur de frame se décide sur un cas mesuré » (« Ouvert » ci-dessus) a son cas.
Trois familles de consommateurs OAM apparaissent ou disparaissent **en cours de partie**, et aucune
n'a de place dans le partitionnement build de la scène :

- **Les projectiles** — un acteur poolé les sert déjà (v0.17) : ils ont position, vélocité,
  collision, un brin de logique. Ce ne sont PAS un cas pour une primitive à part, seulement pour une
  bonne API de spawn/despawn. Ils prennent leurs slots dans le pool de leur scène.
- **Les particules** — le vrai cas hors-budget : des centaines, éphémères, sans collision ni script.
  Un `Actor` plein par particule est absurde, et 128 OAM sature instantanément. Elles veulent
  probablement un modèle À PART (cap fixe, ou effet BG) — peut-être pas de l'OAM du tout.
- **L'UI en sprites** — déjà des consommateurs OAM légers (texte, images), placés au build et
  repositionnés par frame. À laisser tels quels côté runtime ; ce qui change pour eux est la
  **source visuelle** (chantier séparé ci-dessous).

**Clarification de conception (2026-09-25).** On ne construit PAS deux hiérarchies générales
`Actor`/`Sprite`, ni un ECS où chaque accès passe par un pointeur : ce coût reste injustifié dans les
boucles chaudes ARM7TDMI. En revanche, le `Sprite` devient bien une **capacité optionnelle** : un
Actor logique n'embarque ni sous-struct sprite imposée ni réservation OAM. La marche retenue est
celle du chantier « Actor allégé » : side-array ou découpe hot/cold seulement pour les porteurs de
Sprite, et OAM compté par Sprite affiché. L'API conserve un Actor unique, enrichi de composants ;
seule sa représentation mémoire cesse de lui imposer un sprite.

« Actor sans sprite » n'est donc plus seulement le marqueur déjà toléré : c'est une entité légère
promise. « Sprite sans Actor » reste un cas distinct, couvert soit par une primitive d'affichage
légère (particule, UI), soit par un Actor si elle a besoin de logique, collision ou script.

**Ce qui reste ouvert** : la forme exacte de l'allocateur OAM de frame (une free-list de slots pour
ce qui apparaît en jeu), et si les particules relèvent de l'OAM ou d'un effet BG. À trancher sur un
projet réel qui en a besoin, pas avant — fidèle à la règle du chantier.

### Chantier transverse — le Sprite, source visuelle unique

Ne porte pas de numéro : c'est un remaniement de **données**, déclenché par le constat qu'un même
dessin animé a aujourd'hui **plusieurs pipelines de définition** selon qui l'affiche. Un acteur
pointe un `SpriteAsset` (ses tables d'anim émises en ROM) ; une image d'UI pointe une autre voie ;
un futur projectile ou une particule ne pointent rien. Le dessin, ses frames, ses états et ses
directions sont pourtant la même chose — celle qu'on édite dans **l'écran d'animation**.

**La direction (2026-09-10)** : tout ce qui s'affiche — acteur, image d'UI, projectile, particule —
**référence un seul `Sprite`**, l'asset de l'écran d'animation. C'est « source de vérité unique »
appliquée au visuel. Distinct des deux questions OAM ci-dessus : celles-ci partagent le STOCK
matériel (les 128 slots) ; celle-ci partage la DÉFINITION (l'asset). Un consommateur peut être léger
côté runtime (une particule ne porte pas de logique) tout en pointant le même Sprite qu'un acteur
lourd.

**Ce que ça ne décide pas** : cela ne choisit pas la représentation mémoire de l'Actor — la
découpe Sprite optionnel relève du chantier « Actor allégé » ci-dessus — et ne crée pas de runtime
commun. C'est la couche asset qui s'unifie, pas la couche entité.

**Ouvert** : l'inventaire des pipelines actuels (SpriteAsset côté acteur, la voie image de l'UI) et
lequel absorbe l'autre ; et si le décor animé (v0.4) relève de ce même `Sprite` ou reste une voie BG
à part.

### Chantier transverse — la Liste d'interface est un contrôleur, pas une collection

La liste actuelle (v0.22) a résolu le morceau qui devait l'être dans le moteur : navigation à la
croix, sélection, bornes, répétition, défilement et curseur. Elle expose encore une partie de la
mécanique de données et de rendu (`list.set_count`, `list.first`, `list.row`) : l'auteur doit dire à
la primitive combien d'items sa collection contient, puis la consulter pour repeupler les rangées.
Cela fabrique un second vocabulaire de collection alors qu'une liste n'a pas vocation à posséder les
données qu'elle affiche.

Le projet a déjà TROIS formes de tableau accessibles à l'auteur, qui ne se recouvrent pas :

| Forme | Rôle | Lua |
| --- | --- | --- |
| Tableau local | mémoire de travail privée d'un script | `local grille = array(20, 12)` |
| État global | valeurs mutables du jeu, partageables et éventuellement sauvegardées | `global.inventaire[i]` |
| Catalogue Data | fiches structurées, constantes, éditées dans le projet et émises en ROM | `data.Objets[i].prix` |

Le tableau local reste une construction du langage, hors inspecteur. Les deux autres sont les deux
formes de **donnée de projet** : elles vivront dans le même écran *Data*, rangées en **État** et
**Catalogues**, sans les faire passer pour la même chose. Un global peut devenir un vecteur ou une
grille 2D homogène ; une Data Table reste une suite de fiches à colonnes nommées et typées. La
seconde ne doit pas être réduite à un « global 2D » : elle est en lecture seule, vit en ROM et ses
colonnes portent des références validées au build.

Le but est de conserver le helper là où il évite du code répétitif, tout en rétablissant une seule
source de vérité. Dans l'inspecteur, une Liste choisira une source déclarée — un vecteur d'état ou
un catalogue Data — ; le script lira et modifiera l'état directement avec `global.*`, et lira les
fiches avec `data.*`. La Liste ne sera qu'une vue navigable sur cette source. Un auteur qui veut un
comportement hors modèle pourra laisser la Liste de côté et écrire son propre contrôleur sans migrer
ni recopier sa donnée.

#### Décisions verrouillées

- **La donnée appartient à l'état ou au catalogue, jamais à `UIList`.** L'inspecteur conserve une
  référence vers la source, pas une copie de ses items ni une structure propre au widget. Un même
  tableau global ou catalogue Data peut donc alimenter une Liste standard, une vue entièrement
  scriptée, ou les deux selon la scène.
- **`list.*` ne modifie jamais les items.** Il n'existera pas de `list.add_item`,
  `list.delete_item`, `list.sort`, ni de méthode équivalente. Ajouter, retirer, transformer ou
  chercher une valeur relève de l'état et du Lua, pas de l'interface.
- **La primitive ne porte que son état d'interaction.** Son API vise la position sélectionnée
  (`list.cursor_pos`, et son éventuel setter), la prise de focus (`active`) et les paramètres de
  navigation. Elle observe la taille de la source liée, borne elle-même le curseur après une
  mutation et recale seule le défilement et l'image curseur. Exemple : `list.cursor_pos("Inventaire")`
  donne le rang avec lequel le script lit `global.inventaire[rang]`, puis éventuellement
  `data.Objets[id]`.
- **La longueur logique appartient à la source, pas à l'API Liste.** Un vecteur d'état à capacité
  fixe peut déclarer dans l'inspecteur la variable globale qui porte son nombre d'items utiles
  (`global.inventaire_count`) ; la Liste l'observe. Le script déplace les valeurs et met ce compteur
  à jour sans jamais appeler `list.set_count`.
- **Le défilement n'est pas une donnée publique.** La première case visible est une conséquence de
  la sélection, de la géométrie et de la taille de la source ; elle ne doit pas devenir une
  seconde position à tenir par le script. Le contrat de rendu devra permettre de repeupler les
  rangées visibles sans imposer à l'auteur de manipuler `first`/`row`.
- **Une Liste reste un helper optionnel, pas une dépendance des données.** Remplacer son rendu ou
  sa navigation ne demande pas de convertir la donnée : `global.*` et `data.*` restent directement
  accessibles en Lua dans tous les cas.

#### Ce que le chantier implique

Le chantier dépasse un renommage de fonctions. Il relie l'inspecteur de Liste, l'écran Data (État +
Catalogues), le modèle de globals, le checker Lua, le codegen, le runtime de navigation et le rendu
de texte. Il faudra aussi remplacer le chemin actuel où le script pose explicitement le texte dans
`interface.draw_text(list.row(...), ...)` par un contrat de rendu lié aux rangées authorées, sans faire de
l'item un nouvel objet d'interface.

Les tableaux Lua actuels sont **de taille fixe au build** et `table.insert`/`table.remove` ne font
pas partie du sous-ensemble accepté. Les globals ne portent aujourd'hui qu'une dimension ; les
grilles 2D font partie de leur extension, pas de la responsabilité de `UIList`. Une collection
réellement redimensionnable n'est donc pas à faire entrer subrepticement dans la Liste : si les cas
d'usage demandent plus qu'une capacité fixe et une longueur logique, ce sera un chantier de modèle
de données explicite, avec sa mémoire, sa sauvegarde et ses opérations propres. La Liste suivra
cette donnée ; elle ne l'implémentera pas.

#### Ouvert

- Le contrat exact entre une collection liée et le rendu des rangées : callback de rendu, boucle
  dédiée, liaison déclarative, ou autre forme qui laisse le défilement interne sans masquer la
  donnée Lua.
- La forme exacte de l'extension 2D des globals : syntaxe, inspection, bornes, valeur par défaut,
  sérialisation et sauvegarde. Elle doit conserver la règle des tableaux locaux : les dimensions
  sont de la forme du type, non des propriétés manipulées par le runtime.
- La forme du modèle de collections dynamiques, si un projet réel en demande : capacité fixe avec
  longueur logique, collection compacte redimensionnable, identifiants stables, persistance et
  coût RAM. Cette décision précède toute promesse de suppression physique d'un item.
- La migration des listes v0.22 et de leurs appels `set_count`/`first`/`row` : compatibilité
  temporaire ou rupture guidée. Elle se décide avec un inventaire des projets existants, pas en
  supposant qu'aucun script ne les emploie.
- Le comportement après mutation : le curseur conserve-t-il son index, se rabat-il sur le dernier
  item valide, ou peut-il suivre un identifiant stable ? Le bon choix dépend du modèle de données
  finalement retenu.

### v2.0 — Cible cartouche : le matériel embarqué façonne le langage — **JALON OUVERT**

> La famille v2.0 n'est pas rangée. Ce jalon est **posé, pas ordonnancé** : quand on y sera,
> on fera le point de tout ce qui s'y accumule et on décidera de la découpe. Ce qui suit fixe
> l'**intention** et les décisions déjà prises (2026-09-10), pas un périmètre daté.

Un **profil de cartouche** décrit ce que la cartouche embarque **physiquement** — capteurs,
rumble, RTC, type et taille de sauvegarde. Il reste **100% GBA** : les limites mémoire (IWRAM,
EWRAM, VRAM, OAM, palettes) sont fixes pour toute la gamme et **ne bougent pas**. Cibler un
matériel aux limites différentes (NDS…) serait un second backend d'émission, un autre modèle
mémoire — **hors de ce jalon**, écarté explicitement le 2026-09-10.

Le profil n'énumère que des **faits matériels** ; il ne porte aucune logique. Il est la **source
de vérité unique** de « ce que porte la cartouche », d'où tout dérive :

| Capacité | Ce qu'elle débloque | Réel |
| --- | --- | --- |
| `tilt` | API `tilt.*` (angle brut X/Y) | WarioWare Twisted, Yoshi Topsy-Turvy |
| `solar` | `solar.level` | Boktai |
| `rumble` | `rumble.*` | Drill Dozer |
| `rtc` | `rtc.*` | Pokémon Ruby/Sapphire |
| `save` | type + taille (SRAM/Flash/EEPROM) | déjà modélisé partiellement (v0.5) |

**Trois conséquences en cascade** (une source, tout en dérive) :

1. **API script.** Chaque capacité présente ajoute son module au langage ; absente, le module
   **n'existe pas** — pas grisé. Ce sont des modules **moteur spécialisés et nommés**, jamais de
   l'itération par défaut (cf. la règle des deux couches).
2. **Éditeur.** Les nœuds et champs qui dépendent d'une capacité absente ne s'affichent pas. Le
   *pourquoi* d'une absence ne sort qu'en notice niveau 3, désactivable — l'éditeur ne commente
   pas le matériel.
3. **Émission ROM.** Le codegen n'inclut le driver (lecture capteur, IRQ RTC, registre rumble)
   que si la capacité est déclarée. Pas de code mort dans une ROM qui n'a pas le hardware.

#### Décision verrouillée (2026-09-10) — le profil ABSORBE la sauvegarde

La config SRAM de la v0.5 est déjà un morceau de « ce que porte la cartouche » qui vit à côté.
Le profil **l'absorbe** : une seule source de vérité, pas deux partielles. C'est un **vrai
chantier de migration** — migration du modèle de save existant et relecture du codegen de
sauvegarde, l'ancien supprimé avant de dire terminé — pas un bonus glissé dans autre chose.

#### Deux pièges matériels à encoder

- **Capteurs analogiques mutuellement exclusifs.** Une cartouche GBA porte *un* capteur
  analogique (tilt **ou** solaire), pas les deux — même ligne d'acquisition. Le profil doit
  interdire la combinaison, sinon on laisse décrire une cartouche qui n'existe pas.
- **Le tilt n'est pas un axe de pad.** Il rend un angle bruité à calibrer/filtrer. L'exposer
  comme un axe propre mentirait sur le matériel : valeur brute, et au plus un helper de
  calibration nommé.

#### Le catalogue « cartouche conseillée » — trois tiers (2026-09-10)

Le catalogue s'inscrit dans une démarche homebrew/retrodev : on ne propose que des cartouches
qu'un utilisateur peut **réellement obtenir ou fabriquer**. Décisions de cadrage :
**marques écartées** (pas de nom de flashcart commercial dans l'UI, cf. le risque « GBA » de
`project_licensing_model`), **flashcarts reprogrammables dépriorisées** au profit des vraies
cartouches, et **priorité aux créateurs indépendants**.

**Tier 1 — Profils de base : cartouches réelles historiques reproductibles.** Les configs que
la logithèque GBA a réellement portées, reproductibles avec des puces standard et un gabarit
`kicad-gamepaks` (djedditt — contours aux dimensions des coques officielles). La vraie variable
est la puce de save + le périphérique embarqué :

| Profil de base | Matériel embarqué | Équivalent historique |
| --- | --- | --- |
| Save — SRAM | SRAM sur pile | gros de la logithèque |
| Save — Flash | Flash 64/128K | jeux à grosse sauvegarde |
| Save — EEPROM | EEPROM 4/64K | petits jeux |
| RTC | horloge + Flash | RPG jour/nuit (Pokémon G3) |
| Solaire + RTC | photodiode + RTC | Boktai |
| Rumble | moteur + driver | Drill Dozer, Pinball R/S |

**Tier 2 — Options « cool » : créateurs indépendants.** Cartouches à matériel embarqué,
buildables. Référence mature : **insideGadgets** (RTC+Rumble, Solar+RTC, FRAM sans pile, kits
*build-it-yourself*). Écosystème : **GBMake** (fabrication indé de cartouches sur mesure),
`kicad-gamepaks` (la brique de conception open source qui rend le Tier 1 fabricable).

**Frontière — documentée, pas livrée comme profil.** De la R&D, pas des cibles stables :
`jojolebarjos/gba-cartridge` (cartouche **FPGA**, TinyFPGA BX — mappers/périphériques custom) et
`konsumer/dkart` (framework open hardware avec **ESP32 + SD** soudés — « cartouche
intelligente »). Notés comme horizon, hors catalogue conseillé.

#### Convention de nommage — capacité d'abord, board number en note

Les cartouches historiques portent une nomenclature Nintendo, mais deux schémas coexistent :
`AGB-002/013/019…` désigne la **coque/famille physique** (inutile ici) ; `AGB-Exx-nn` est le
**PCB du jeu** qui encode save + périphérique (p. ex. `AGB-E05-01` = RTC + Flash, la carte
Pokémon Gen 3 — le seul rock-solid). Le fil nesdev le confirme : pour un jeu GBA, les seules
variables sont **taille de ROM, type de save, taille de save, présence d'un RTC** — donc notre
modèle de capacités *est* déjà la bonne granularité.

**On ne nomme PAS les profils par `AGB-Exx`** : c'est une désignation interne Nintendo (marque,
écartée), le catalogue de référence est mort (Pocket Heaven — reconstituer une table exhaustive
serait deviner), et le numéro n'encode rien qu'un nom de capacité ne dise mieux. Les profils
sont nommés **par capacité** ; le board number n'apparaît qu'en **note historique** pour les cas
sûrs (« profil RTC — équivalent historique `AGB-E05` »), jamais comme identifiant.

#### Références externes à surveiller

- [`kicad-gamepaks`](https://github.com/djedditt/kicad-gamepaks) — gabarits KiCad aux dimensions
  des cartouches officielles (la brique de fabrication du Tier 1).
- [insideGadgets](https://shop.insidegadgets.com/) — cartouches à RTC / Solar / Rumble / FRAM
  (référence Tier 2, kits *build-it-yourself*).
- [GBMake](https://gbmake.com/us) — fabrication indé de cartouches GB/GBA sur mesure.
- [`jojolebarjos/gba-cartridge`](https://github.com/jojolebarjos/gba-cartridge) — cartouche
  FPGA (TinyFPGA BX, KiCad) — frontière.
- [`konsumer/dkart`](https://github.com/konsumer/dkart) — framework cartouche open hardware
  ESP32 + SD — frontière.

#### Ouvert

- La découpe : ce jalon face aux autres candidats v2.0 (Backgrounds affines ci-dessous, etc.),
  et s'il se scinde par capacité.
- La forme exacte du profil dans le projet, et où il vit par rapport au reste de la config projet.
- L'ordre de livraison des capacités (RTC, rumble et les saves sont sûrs et fabricables ;
  l'ordre des capteurs analogiques dépend de la demande réelle). **Le tilt/gyro reste hors
  catalogue** : historique et réel, mais non reproductible (soudé dans la cartouche OEM, aucune
  flashcart ni repro ne l'embarque) — documenté « OEM-only », jamais proposé comme cible.

### v2.0 — Backgrounds affines (« Mode 7 »)

Un calque affine ajoute rotation et zoom, au prix de perdre des calques réguliers ailleurs —
et il adresse sa carte différemment, donc c'est un **second chemin de génération de code**,
pas « un calque de plus ».

Volontairement décrit à haut niveau : la portée exacte dépendra de ce qui aura été appris en
construisant les fondations précédentes.

#### Ce que la v2.0 n'est PAS — l'objectif V-Rally 3 n'est pas ici

Cet objectif a été rangé dans cette version pendant une journée, sur une lecture de captures
d'écran qui concluait au Mode 7 : sol texturé fuyant vers l'horizon, décor en sprites mis à
l'échelle, HUD en calque normal. **Cette lecture était fausse**, et la mesure l'a montrée
(2026-08-13, visualiseur de cartes mGBA sur la ROM) :

| Relevé | Lecture |
| --- | --- |
| Fond de tuile : *s.o.* | aucune base de tuiles — le fond n'est pas tuilé |
| Taille : 240×160 | un écran, pas une carte |
| Fond de carte : `0x0600A000` | VRAM + 0xA000 = **frame 1 du mode 4** |

Le mode 3 n'a pas de second tampon et le mode 5 afficherait 160×128 : c'est donc le **mode 4**,
240×160 en 8bpp double-tamponné. Un framebuffer rempli par le processeur. Confirmé par des
maillages qui tournent dans les menus.

La leçon vaut d'être gardée : **un rasteriseur logiciel et un sol affine produisent la même
image.** Une capture ne distingue pas les deux — seul le mode vidéo le fait. Aucune décision
de rendu ne se verrouille sur une image, ici ou ailleurs.

L'objectif part donc en **v3.1**, derrière le framebuffer dont il dépend. La v2.0 redevient
ce qu'elle était : une capacité, sans cible de jeu.

#### Piste posée — l'abstraction « caméra » sera remise en cause ici

La caméra est en train de devenir une entité, en absorbant les fenêtres de la v0.3.2 — auquel
cas ce n'est plus « où on regarde » mais **une configuration d'écran nommée qu'on active** :
cadrage, suivi, et régions qui découpent l'affichage. Comme les caméras sont mutuellement
exclusives, deux fenêtres par caméra n'impliquent jamais plus de deux rectangles à l'écran :
la contrainte matérielle tient.

Nom de travail : **Caméra2D** (convention Godot, immédiatement lisible). Réserve à garder en
tête, il promet une Caméra3D qui n'existera jamais sur GBA — le Mode 7 n'est pas de la 3D mais
une transformation affine en 2D. Le vrai axe est donc *régulière* contre *affine*, pas 2D
contre 3D.

Une chose à traiter à ce moment-là, pas avant : l'**écran partagé**, qui rouvrira la question
« une région appartient-elle à une caméra, ou l'inverse ? ». Tant que les caméras sont
exclusives (une seule active par scène à la fois), la question ne se pose pas.

*Mise à jour 2026-08-24* : « unifier les mécanismes de caméra concurrents » (l'autre point que
cette piste listait) est réglé — c'est fait depuis la v0.6.1, et l'objet nommé porteur d'un
état existe déjà. Ce qui a bougé depuis n'est pas cet axe-là mais la PROPRIÉTÉ de la caméra :
elle appartient désormais à sa scène plutôt qu'au projet (cf. `changelog-archive/v0.6.md`,
« Révisé le 2026-08-24 »). Ça ne contredit pas Caméra2D — une caméra reste exclusive, une
seule active à la fois — et ça ne change rien à ce qui reste ouvert ici.

*Mise à jour 2026-08-24 (suite)* : la question « une région appartient-elle à une caméra, ou
l'inverse ? » posée ci-dessus est **réglée pour le cas à une seule caméra active** — la
caméra possède désormais un viewport (`Camera.frame_w/h`, cf. `ARCHITECTURE.md`, « Windows —
le pochoir ») : WIN0 lui appartient, WIN1 reste à la scène. Une allocation FIXE, décidée une
fois, pas un arbitrage à l'exécution — donc pas l'allocateur de ressources générique que ce
chantier réserve. Ce qui reste ouvert ici, sans changement, c'est l'**écran partagé** :
plusieurs caméras actives SIMULTANÉMENT (split-screen), qui redemanderait de vrais
arbitrages entre plusieurs propriétaires possibles des mêmes deux rectangles.

### v2.1 — Physique et collision

Le moteur n'a aujourd'hui aucune physique à lui : un script décide du mouvement, la
résolution de la v0.6.3 ne fait que le corriger. Cette version est **le renversement de cette
règle** — pas son extension. C'est pour ça qu'elle est ici et pas en v0.6.4 : tant que les
fondations 2D ne sont pas finies, un moteur qui décide du mouvement à la place du script
coûterait plus qu'il ne rendrait.

#### Périmètre

- **Collision par normale.** Le contact rend une direction, pas seulement un booléen — c'est
  ce qui distingue « je touche » de « je glisse le long de », et c'est la condition de tout
  le reste.
- **Gravité**, et deux milieux qui la modulent : **air** (traînée) et **viscosité**
  (résistance d'un fluide). Trois réglages qui vivent quelque part entre la scène et
  l'acteur — l'endroit reste ouvert.
- **Nouvelles primitives** : cercle de collision et maillage de collision. Ce sont des
  primitives **2D** ; le mot « mesh » ne promet pas de volume. La distinction devient
  critique une fois la v3.1 au programme : deux choses différentes porteront le même mot si
  personne n'y veille.
- **Nouveaux types de collision**, en remplacement du booléen `solid` actuel :

  | Type | Sens |
  | --- | --- |
  | `rigidbody` | réactif — le moteur calcule sa réponse au contact |
  | `actor` | simplifié — se déplace, se bloque, ne réagit pas |
  | `solid` | immobile — ne bouge jamais, sert de décor de collision |

- **Import de carte de collision** — un nouvel asset, pour des collisions fidèles à l'image.

#### Décisions verrouillées

- **Jamais avant la v2.0.** Décidé explicitement (2026-08-12) : les fondations 2D passent
  d'abord. La section « Ouvert » de la v0.6.3 reste donc vraie jusque-là, elle n'est pas
  contredite — elle est datée.
- **Les trois types ne sont pas un confort, ils sont le budget.** Une réponse par normale sur
  N acteurs se paie en cycles, sans FPU et en virgule fixe. `actor` et `solid` existent pour
  que `rigidbody` reste payable : le coût élevé se réserve à ce qui en a besoin. Une
  taxonomie à deux niveaux (« physique ou trigger », l'actuelle) ne permet pas cet arbitrage.
- **La carte de collision s'IMPORTE, elle ne se peint pas.** Même règle que partout ailleurs :
  l'image source n'est jamais modifiée, un sidecar porte le résultat, et l'éditeur n'ajoute
  pas d'outil de dessin (cf. la même décision pour les fonds et les sprites). C'est un
  troisième client du pipeline d'import existant, pas un nouveau pipeline.
- **« Pixel perfect » veut dire par tuile, pas par pixel.** Tester chaque pixel d'une scène
  240×160 à chaque frame n'est pas tenable ; la forme réalisable est un masque de bits par
  tuile, consulté après un rejet grossier par boîte. Le nom du champ doit dire ça, sinon il
  promet une précision que le runtime ne tient pas.

#### Ouvert

- **`CollisionBoxComponent.solid` est un booléen aujourd'hui.** Les trois types le
  remplacent : c'est un changement de format de composant, à traiter comme tel (la maison ne
  migre pas les formats — cf. `core/project.py`).
- Où vivent gravité, air et viscosité : propriétés de scène, de zone, ou d'acteur ? Les trois
  se défendent et le choix dépend du premier jeu qui s'en sert.
- Le maillage de collision est-il authoré, dérivé de l'image importée, ou les deux ? Dérivé
  est cohérent avec le refus de l'outil de dessin ; authoré est ce que réclame une forme qui
  n'existe dans aucune image.
- Rien n'est dit du coût réel. Il se mesure sur un cas, pas avant — c'est la règle qui a
  servi pour les animés de décor (v0.4.1, « L'ordre de grandeur, mesuré »).

### v2.2 — Distorsion d'image

Déformer un fond pour l'eau, la chaleur, la vitesse. Rangé ici parce que c'est **la même
plomberie que le sol affine de la v2.0** : dans les deux cas on réécrit des registres de
rendu à chaque scanline, seuls les registres visés et la table de valeurs changent. Construire
l'un donne l'autre presque gratuitement — c'est la raison de leur voisinage, et l'ordre entre
les deux n'a pas d'importance.

#### Décisions verrouillées

- **Sur un fond tuilé, la distorsion est PAR LIGNE, jamais par pixel.** On réécrit les
  registres de décalage du calque à chaque scanline (HDMA) — c'est l'effet eau/chaleur
  classique, réel et bon marché sur ce matériel. Une flow map par pixel suppose un
  framebuffer : elle appartient donc à la v3.0, et n'a pas de sens avant.
- **Les sprites n'en font pas partie.** Un OBJ ne connaît que la transformation affine
  (rotation, échelle) ; il n'y a pas de distorsion libre à lui appliquer. Le proposer
  promettrait un rendu que le matériel ne produit pas — même règle que les modes de mélange
  *multiply* et *overlay*, absents pour cette raison.

#### Ouvert

- La forme d'authoring : une courbe par calque, une table d'amplitudes, ou un script qui
  écrit la table lui-même ? Le troisième cas existe de toute façon, la question est ce que
  le déclaratif couvre.

### v2.3 — Rendu isométrique

**Ce n'est pas un mode de rendu**, et c'est le piège du sujet : l'isométrique reste du 2D
tuilé ordinaire, sur le même matériel, avec les mêmes calques. Ce qui change est la
**convention de projection** et, surtout, l'**ordre de dessin**. Aucune ligne du moteur 2D
n'est remplacée ; il s'en ajoute.

#### Périmètre

- **Le tri en profondeur des sprites.** C'est le cœur, et c'est du runtime. En vue de dessus,
  l'ordre OAM suffit tel quel ; en isométrique, un acteur passe *devant* ou *derrière* un
  autre selon sa position dans le monde, et l'ordre doit être recalculé quand ils bougent.
  Le matériel dessine les OBJ dans l'ordre de la table : c'est donc la table qu'on trie.
- **La projection.** Une position monde (x, y) devient une position écran en losange. Une
  seule formule, mais elle doit vivre **au même endroit pour l'éditeur et pour le moteur** —
  sinon le canvas ment sur l'emplacement des choses (c'est déjà le rôle de
  `core/engine_emulation/`).
- **La collision en espace isométrique.** Une boîte alignée à l'écran n'est pas une boîte
  alignée dans le monde. À raccorder à la v2.1, qui aura introduit les normales et les
  nouvelles primitives — les deux versions se touchent ici.
- **L'authoring.** Poser un acteur au canvas doit se faire dans la grille du monde, pas dans
  les pixels du losange.

#### Ouvert

- Le coût du tri par frame, et son plafond. Trier N acteurs à chaque frame sur un ARM7TDMI a
  un prix ; le nombre d'entités simultanées s'en déduira, il ne se décrète pas.
- Vraie isométrique (2:1) ou projection libre ? La première se tuile proprement, la seconde
  ouvre des cas qui ne se rangent pas dans une grille.
- La hauteur. Un décor isométrique sans élévation est une grille inclinée ; avec élévation,
  le tri cesse d'être un tri sur Y. À décider avant, parce que ça change la donnée de carte.

### v2.4 — Sucre syntaxique Lua (+=, ++, ?:)

Demandé le 2026-08-14 : `x += 1` / `x -= 1` / `x *= 2` / `x /= 2`, `x++` / `x--`, et
`cond ? a : b`. **Aucun des trois n'est du Lua** — Lua n'a jamais eu d'affectation composée ni
d'opérateur ternaire, choix délibéré du langage — et `luaparser` (un vrai parseur ANTLR) les
refuse net :

```
x += 1          → no viable alternative at input 'x +'
x++             → no viable alternative at input 'x+'
a ? b : c       → token recognition error at: '?'
```

Donc ce n'est pas « étendre l'AST » : `parser.py` reçoit le texte source tel quel et le passe
à `luaparser.ast.parse()` sans passe intermédiaire (`scripting/parser.py::parse()`). Accepter
cette syntaxe demande une **réécriture du texte AVANT `luaparser`** — un dialecte Lua-like, pas
du Lua strict.

**Le ternaire a déjà un équivalent qui ne coûte rien** : `cond and a or b` est du Lua valide
aujourd'hui et couvre tout ce que ce sous-ensemble manipule (entiers, vec2/vec3, chaînes) —
sauf le cas où `a` vaut `false`, où Lua bascule sur `b` alors qu'un vrai `? :` ne le ferait
pas. À vérifier si ce cas se présente en pratique avant d'écrire quoi que ce soit.

#### Ce que le fork coûterait, si tranché « oui »

- **La coloration syntaxique du Script Editor** (`lua_editor.py`) devrait apprendre ces tokens
  en plus, sinon ils s'afficheraient comme une erreur alors qu'ils compileraient.
- **Un vrai script Lua copié ailleurs** (interpréteur externe, autre colorateur) ne le
  reconnaîtrait plus comme du Lua valide.
- **Les numéros de ligne/colonne d'une vraie erreur de syntaxe** se décaleraient : `luaparser`
  rapporterait la position dans le texte RÉÉCRIT, pas dans ce que l'auteur a tapé — une faute
  ailleurs sur la ligne verrait son message mentir sur l'endroit fautif.
- `? :` est le plus dur à réécrire sûrement en texte (imbrication, `?`/`:` à l'intérieur d'une
  chaîne…) — une regex naïve est fragile ; il faudrait un petit tokenizer dédié, pas un
  remplacement de texte.
- `+=`/`++`/`--` sont plus simples : réécriture au niveau de l'instruction complète
  (`NOM (+=|-=|*=|/=) EXPR` ou `NOM (\+\+|--)`), sans ambiguïté de priorité d'opérateurs.

### v3.0 — Le second moteur de rendu

**Décidé (2026-08-13) : l'éditeur porte DEUX moteurs de rendu.** Un moteur 2D — tout ce qui
existe jusqu'à la v2.2 incluse, calques tuilés et OBJ — et un moteur 3D, qui est le sujet de
cette version.

L'ancienne v3.0 « modes bitmap » disparaît en tant que jalon et **devient le substrat de
celle-ci**. Elle n'avait jamais été un jalon pour l'auteur de jeu : personne ne veut « le
support du mode 4 », on veut ce qu'il permet. Elle reste décrite ci-dessous parce que ses
contraintes ne changent pas, mais elle ne se livre plus seule.

Ce n'est pas un mode de plus dans le moteur existant. C'est **un second moteur**, et cette
version consiste autant à réoutiller l'éditeur qu'à écrire un rasteriseur.

#### Le substrat — les modes bitmap

Famille complètement différente des modes tuilés : un seul calque, pas de tuiles ni de cartes,
un framebuffer direct. Le budget des sprites y est par ailleurs divisé par deux.

| Mode | Résolution | Couleur | Tampons |
| --- | --- | --- | --- |
| 3 | 240×160 | 16 bits directs | 1 seul |
| 4 | 240×160 | 8 bits indexés | 2 (double tampon) |
| 5 | 160×128 | 16 bits directs | 2, résolution réduite |

**Priorité au mode 4** : 256 couleurs, double tampon, pleine résolution — il évite le
déchirement d'image du mode 3 et la résolution réduite du mode 5. C'est aussi celui que le
jeu de référence emploie (relevé du 2026-08-13).

**Exclu délibérément des fondations v0.3** : les modes bitmap cassent tout le pipeline actuel
(tilesets réutilisables, palettes par banque) au profit d'un framebuffer brut — et c'est aussi
pourquoi de vrais jeux commerciaux les emploient rarement.

Une brique est déjà là : `BackgroundAsset.mode == "bitmap"` existe côté éditeur (image plein
écran, détectée à l'import) et n'attend que son émission ROM. C'est le plus petit usage du
framebuffer, sans géométrie — un bon premier pas dans cette version.

**Ce que le framebuffer débloque, et rien d'autre ne débloquera** : la vraie *flow map* — une
distorsion décidée par pixel, et non par ligne comme en v2.2 — et le rendu de géométrie
ci-dessous. C'est le seul mode où l'adresse de chaque pixel de destination est écrite par le
programme.

#### Ce qui reste PARTAGÉ entre les deux moteurs

C'est la liste la plus importante de cette version : ce qui n'y figure pas se dédouble, et
tout ce qui se dédouble est une occasion de diverger. Elle se tient courte volontairement.

Palettes, audio, table de textes, variables et sauvegarde, scripting (le langage, le parseur,
le checker, le renommage), le pipeline de build et la construction de la ROM, la découverte
d'assets et les sidecars. **Rien de tout cela ne connaît le mode de rendu**, et rien ne doit
l'apprendre.

Les sprites (OBJ) sont partagés aussi, et c'est contre-intuitif : ils survivent au changement
de moteur puisque le matériel OBJ est le même — mieux, c'est en 3D qu'ils portent le CIEL
(cf. « rôles inversés » ci-dessous).

#### Ce qui se DÉDOUBLE, et à quel niveau

- **La scène.** `Scene.render_mode` existe déjà en ébauche : c'est le bon endroit, et
  l'arbitrage est **par scène, pas par projet** — un jeu veut ses menus en 2D et sa course en
  3D. Conséquence : la moitié des champs de `Scene` n'a de sens que dans un moteur
  (`background_layers`, `collision_map`, `windows`, `text_bg` d'un côté ; la géométrie et la
  caméra à projection de l'autre). À trancher : deux types de scène, ou un type dont les
  champs se taisent selon le mode.
- **Le canvas.** Cf. « Le point dur » ci-dessous.
- **Les assets de géométrie.** Maillages et textures n'ont aucun équivalent 2D. Ils entrent
  dans le pipeline d'import existant (fichier déposé → sidecar), pas dans un pipeline neuf.
- **Le codegen.** Second chemin d'émission, comme prévu de longue date pour l'affine.
- **L'API Lua.** `layer.*`, `tilemap.*`, `window.*` ne veulent rien dire en 3D, et la
  géométrie n'a pas d'équivalent en 2D. `RUNTIME_API` doit donc porter la disponibilité par
  moteur, et le checker refuser un appel 2D dans une scène 3D — sinon la faute n'apparaît
  qu'au `make`, sur une ligne générée, jamais sur la cause. C'est le même défaut que les deux
  listes de prototypes du moteur, et il se règle au même endroit : dans le catalogue.
- **Les écrans de l'éditeur.** Le Background Editor n'a pas d'objet en 3D ; le Palette Editor
  et le Sprite Editor gardent le leur ; le Scene Manager change de nature. Un écran doit
  pouvoir déclarer les moteurs où il s'applique, faute de quoi l'utilisateur voit des outils
  qui ne peuvent rien produire pour la scène ouverte.

#### L'aperçu fidèle — une source, deux compilations

`core/engine_emulation/` existe parce que **l'éditeur refait en Python ce que la console fait
en C**, pour montrer le vrai résultat plutôt qu'une approximation : le layout de texte, les
formules de mélange, le mixeur. Promesse tenue jusqu'ici, à un coût connu — deux
implémentations à tenir d'accord.

Un moteur 3D aurait mis cette promesse en défaut : porter un rasteriseur en Python fait de la
double implémentation un vrai risque, et ses divergences sont **invisibles** — un arrondi en
virgule fixe qui diffère ne plante pas, il donne une autre image. L'autre issue était d'admettre
un aperçu approximatif, c'est-à-dire de mentir pour la première fois.

**Décision (2026-08-13) : ni l'un ni l'autre. Le rasteriseur s'écrit UNE fois, en C portable,
et se compile DEUX fois** — pour la GBA (ARM, en IWRAM), et pour l'hôte en bibliothèque
partagée que l'éditeur appelle et dont il affiche le tampon rendu. Même source, mêmes types en
virgule fixe : l'image de l'aperçu est identique au pixel près **par construction**, et non par
discipline. C'est ce qu'Unity obtient en embarquant son runtime dans son éditeur ; on l'obtient
en compilant le même fichier deux fois.

Ce que ça implique, et qui n'est pas négociable :

- **Le cœur du rasteriseur ne touche JAMAIS le matériel.** Il reçoit un pointeur de destination
  et une palette de son appelant ; c'est la couche GBA qui lui passe la VRAM. Si la version
  console écrit dans la VRAM en ligne, la compilation hôte devient impossible. **C'est le seul
  point de cette version dont l'ordre est irréversible** : la contrainte ne coûte rien
  aujourd'hui et ne se rattrape pas après coup.
- **Ce que l'aperçu ne donnera pas : le temps.** Sur PC il tournera vite quoi qu'il arrive et ne
  dira jamais si la frame tient dans le budget. mGBA reste l'outil de la cadence — appelé, pas
  incorporé, et le lancement de ROM est déjà outillé.
- **Un compilateur C hôte devient une dépendance de build**, pour ce composant seulement.
  Relevé sur la machine de développement (2026-08-13) : aucun compilateur hôte, et le msys2
  livré avec devkitPro n'expose que les dépôts `msys`, `dkp-libs`, `dkp-windows` — pas de
  mingw-w64. C'est donc une installation à part, et elle ne concerne que qui touche au
  rasteriseur : l'éditeur se distribue avec la bibliothèque déjà compilée, et le reste du
  travail Python n'en a pas besoin.
- **TCC pour développer, gcc pour publier.** TCC (Tiny C Compiler) tient en quelques
  mégaoctets et un seul dossier, et sort la bibliothèque directement (`tcc -shared`) : c'est
  le coût d'entrée le plus bas pour itérer sur le rasteriseur. Il convient d'autant mieux que
  la source doit de toute façon rester du C conservateur et sans dépendances — elle compile
  pour un ARM7TDMI avec devkitARM, ce qui interdit déjà tout ce que TCC ne saurait pas
  digérer. Les builds de **release** passent par gcc (w64devkit, ou la CI qui en fournit un
  gratuitement), pour du code optimisé et un compilateur éprouvé.

  Le risque de TCC est réel mais borné : moins éprouvé que gcc, et une compilation fausse
  donnerait une **image fausse** plutôt qu'un plantage. Deux garde-fous tombent tout seuls :
  la même source tourne sur le vrai matériel (mGBA), et la présence des deux chaînes fait du
  build de release un **test différentiel gratuit** — si l'image TCC et l'image gcc diffèrent,
  l'un des deux compilateurs a tort et on le sait avant l'utilisateur.

  **Ce choix n'engage rien.** Le compilateur hôte est un détail de build, pas une décision
  d'architecture : la source étant du C portable dans les deux cas, remplacer TCC par autre
  chose ne déplace aucune ligne, aucun format, aucune structure. À rouvrir librement, sans
  que ce soit une reprise de décision.

#### Ouvert

- Le nom des deux moteurs, dans le code comme dans l'interface. Il sera lu partout et pour
  longtemps.
- Une scène peut-elle mélanger les deux ? Le matériel dit non pour les calques, mais les OBJ
  traversent — donc « pas de mélange » est faux tel quel, et « mélange libre » est faux
  aussi.
- Ce que devient un projet dont l'auteur bascule une scène d'un moteur à l'autre. Rien ne se
  convertit ; la question est ce que l'éditeur en dit.

### v3.1 — Le rasteriseur

Le moteur 3D proprement dit, une fois le substrat et le réoutillage de la v3.0 en place.

#### L'objectif concret — V-Rally 3

**Un jeu du niveau de V-Rally 3 sur GBA doit être constructible avec l'éditeur.** Premier
objectif de la roadmap énoncé comme un résultat visible plutôt que comme une capacité — c'est
ce qui rend sa portée décidable : une capacité s'étend indéfiniment, une cible se compare.

#### Décisions verrouillées

- **C'est un rasteriseur logiciel, mesuré, pas supposé.** Relevé mGBA du 2026-08-13 : mode 4,
  framebuffer 240×160 8bpp double-tamponné (`0x0600A000` = frame 1), aucune base de tuiles, et
  des maillages qui tournent dans les menus. **Confirmé en course**, où toute la scène passe
  par ce même framebuffer — le doute « les menus seulement » est levé, il n'y a pas de chemin
  hybride. Le détail du relevé et l'erreur qu'il corrige sont conservés en v2.0, « Ce que la
  v2.0 n'est PAS ».
- **Le framebuffer d'abord, sans alternative.** Le rendu écrit chaque pixel : il lui faut le
  substrat bitmap de la v3.0, et il n'y a aucun chemin par les calques tuilés. Ce n'est pas
  une préférence d'ordonnancement, c'est une dépendance — d'où la découpe v3.0 / v3.1.
- **La GBA n'a ni FPU ni matériel 3D.** Tout est en virgule fixe et coûte des cycles
  proportionnels au nombre de triangles — c'est le seul renderer de la roadmap dont le coût
  dépend du contenu de la scène et non de sa configuration. Le budget est donc un sujet de
  conception, pas une optimisation de fin de chantier.
- **Le vocabulaire ne change pas de règle pour autant.** « 3D » décrit ici ce que le
  PROGRAMME calcule, jamais une capacité du matériel : pas de calque 3D, pas de mode vidéo
  3D. La réserve de la v2.0 sur « Caméra3D » tombe en revanche — une caméra à projection
  perspective a un sens dans cette version, parce que quelque chose la calcule enfin.
- **Les rôles fond/sprite sont INVERSÉS par rapport à tout le reste de l'éditeur.** Relevé en
  course (2026-08-13) : le monde entier — sol, route, panneaux publicitaires, bâtiments,
  public — est rasterisé dans l'unique fond disponible, et **c'est le ciel qui est fait de
  sprites**.

  Mesuré : un seul fond porte toute la scène, aucun élément de décor n'est un OBJ, l'arrière-
  plan lointain en est un. Déduit : en mode bitmap il ne reste qu'un fond (BG2 = le
  framebuffer), donc aucun calque pour le ciel ; et remplir le ciel dans le framebuffer
  coûterait du CPU à chaque pixel de chaque frame, quand le matériel OBJ le peint pour rien.
  Le rasteriseur ne dessine que sous l'horizon.

  Trois conséquences, toutes structurantes :

  - **Le vocabulaire actuel de l'éditeur ne tient pas ici.** Ce que l'auteur appelle « le
    fond » (le ciel) est de l'OBJ ; ce que le matériel appelle le fond est la cible de rendu,
    que personne n'authore. Les deux sens du mot se croisent — à trancher avant d'écrire le
    moindre écran, sous peine d'un inspecteur qui ment sur ce qu'il configure.
  - **Le budget OBJ devient un sujet.** Les modes bitmap divisent déjà la VRAM des sprites
    par deux (cf. v3.0) — et le ciel vient maintenant en réclamer une part. Un ciel en bandes
    répétées, avare en tuiles uniques, n'est pas une optimisation tardive : c'est la
    condition pour qu'il reste des sprites au jeu.
  - **Aucune contrainte affine ne s'applique.** Les 32 jeux de paramètres OBJ, invoqués tant
    que la lecture était « décor en sprites mis à l'échelle », ne concernent rien ici.

#### Ouvert

- Tout le reste. Format des maillages, texturage ou faces plates, élimination des faces
  cachées, tri en profondeur, découpage, budget par scène, et ce que l'éditeur montre d'un
  maillage sans devenir un modeleur — le refus de l'outil de dessin s'applique ici aussi, et
  il est bien plus dur à tenir face à de la géométrie que face à des tuiles.
- **Le ciel est-il authoré comme un fond, ou comme des sprites ?** Les deux réponses coûtent
  quelque chose. « Comme un fond » garde le modèle mental de l'auteur — il dessine un ciel,
  le build le découpe en OBJ — mais c'est l'éditeur qui commente le matériel au lieu de le
  rendre, ce que la maison refuse partout ailleurs. « Comme des sprites » est honnête et
  demande à l'auteur de comprendre pourquoi son ciel n'est pas un fond. La tension est réelle
  et ne se tranche pas à l'avance.
- Le lien avec la v2.1 : une course a besoin de physique, mais la physique de la v2.1 est
  **2D**. Ce qu'il faut ici pour un véhicule sur un relief n'est pas décidé, et ce n'est pas
  la même chose.
- La cadence visée. 60 fps n'est pas donné ; le jeu de référence tourne dans un budget qu'il
  faudra mesurer plutôt que supposer.

---

## Hors périmètre (pour l'instant)

- **Multijoueur par câble Link** — envisagé après la v1.0, pas avant. Très spécifique et
  coûteux à implémenter proprement.
