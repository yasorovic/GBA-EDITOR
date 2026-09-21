
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
| v0.16 | L'API : règle de construction et rangement | Non commencée |
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
  donc `.y`, `.foo` et `:bouge()` passaient tous. Reconnue par sa FORME (`ui.get(...)`) et non
  en l'inscrivant dans `REF_TYPES` — l'y mettre ferait chercher les méthodes sous
  `ui_element:show` alors qu'elles vivent sous `self:show`, et casserait le `ui.get(x):show()`
  qui marche. (3) **Les arguments d'un appel utilisé comme RÉCEPTEUR** :
  `ui.get("Cusor"):show()` ne validait rien, alors que la même expression posée seule était
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

1. ~~**Aucun moyen d'adresser un acteur dynamique.**~~ **Corrigé (2026-09-20).** `get_actor`
   accepte désormais un **index dynamique 1-based** en plus d'un nom littéral :
   `get_actor(i)` → `actor_at((i) - 1)` (repli 1→0 comme `data.Table[i]`), borné à la scène
   active et filtré par `actor_live` (nil hors bornes ou détruit). `actor_count()` rend le
   nombre d'acteurs posés — la borne de boucle. La cascade `if sel==1 then get_actor("Soldier1")…`
   devient `get_actor(sel)`, vérifié de bout en bout sur la démo. Décisions verrouillées :
   **1-based** (cohérent avec le langage) ; porte les acteurs **posés** de la scène active dans
   l'ordre d'authoring (l'ordre C correspond exactement) ; l'indexation des **pools spawnés**
   (`pool_at`) reste un chantier distinct différé. `runtime_api_inline.h` (`actor_at`,
   `g_scene_placed`), `main_gen` (pose `g_scene_placed` au scene_init), `scripting/codegen.py`,
   `scripting/api.py` (`actor_count`). Tests : `test_actor_scene_naming.py`. Piste encore ouverte :
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
   `text.draw(tx, ty, "clé")` après avoir posé le global. Pour un genre qui affiche *beaucoup*
   de chiffres (PV, dégâts, portées, or, niveaux), l'indirection est lourde et se répète à
   chaque valeur (`editor/scripting/api.py`, entrée retirée `text.draw_num`).

5. **Contention d'input entre le curseur et une liste active.** Une liste `active` consomme la
   croix directionnelle **automatiquement** chaque frame, pendant que le script du curseur la
   lit aussi : sans notion de « focus », les deux bougent au même appui. Il a fallu geler le
   curseur à la main (garde d'état). Tout jeu à plusieurs couches d'UI (menu + sous-menu +
   curseur de carte) rejouera ce conflit (runtime `ui_list_tick`, v0.22).

6. **Deux idiomes non évidents du transpileur, et une doc qui mentait.**
   ~~`get_actor(...):méthode()` en chaîne directe ne transpile pas (« invoke sur expression
   complexe ignoré »)~~ **Corrigé (2026-09-20)** : `_invoke` accepte désormais un receveur qui
   est une expression de type connu — un actor (`get_actor(...)`, `actor.spawn(...)`,
   `self.<enfant>`) ou une référence —, donc `get_actor("Foe"):move_to(p, 2)` marche sans local
   intermédiaire ; une expression sans type reste refusée. La docstring de `get_actor`, qui
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
| Les exports de script, câblés au jeu | 2026-09-20 | **Ouvert — posé + poolé livrés (2026-09-21)** : int/float/bool/enum ; valeur d'instance au build (posé, pli read-only vérifié en ROM) et au spawn via table facultative (poolé, `actor.spawn("X", pos, {k=v})`). Reste les autres types (string/refs/vec) + prolongement locals. Voir [ci-dessous](#les-exports-de-script-câblés-au-jeu--paramétrer-une-instance) |
| Le cache de scène | 2026-09-16 | À ouvrir — voir [ci-dessous](#le-cache-de-scène-rouvrir-une-scène-déjà-visitée-sans-tout-redécoder) |
| L'écran resynchronisé à sa revisite | 2026-09-18 | **Livré (2026-09-20)** — [archive](changelog-archive/screen-resync-revisit.md) |
| Undo/redo des sidecars d'éditeur | — | À ouvrir — envisagé pour **V2**, voir [ci-dessous](#undoredo-des-sidecars-déditeur-annuler-la-création-dun-groupe-un-déplacement-de-nœud) |

---

## Les exports de script, câblés au jeu — paramétrer une instance

### D'où vient la question (2026-09-20)

Relevé en réglant l'adressage dynamique (friction #1) : c'est le pendant « données » de
`get_actor(i)`. Un script d'acteur peut déjà déclarer une table `exports` en tête
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
`team`, au lieu de trois scripts jumeaux — l'identité propre d'une instance, quand `get_actor(i)`
donne l'instance.

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

- **`actor.spawn` accepte une table d'exports FACULTATIVE** : `actor.spawn("Bullet", pos, { speed = 8 })`.
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
   déclaré en tête du spawner) : forme `local b = actor.spawn(...)` ou spawn nu (temporaire). L'accès
   passe par setter, jamais par `g_state` d'un autre `.c`. Enum/bool résolus en entier.
3. **Stockage.** ✅ **Fait.** Uniformisation décidée avec Victor : sur un prefab poolé, TOUT export de
   type réglable est un champ de `g_state` (même lu seulement), plus de constante partagée fondue — pas
   de scan inter-script. `_emit_locals` force ces exports en état.
4. **Checker.** ✅ **Fait.** `_check_spawn_table` : table à clés nommées, clés = exports réglables du
   prefab visé (via `spawn_exports`), valeurs littérales, et **position statement** seulement (début de
   ligne ou `local x =`, là où le codegen sait écrire).
5. **Validation build/ROM + doc.** ✅ **Fait.** Build ROM headless (TacticsDemo : `Range` poolé avec
   export `tint`, `actor.spawn("Range", pos, {tint=3})` dans `cursor.lua`) : le `.c` de Range porte le
   champ d'état, le setter et l'init template ; celui de Cursor l'extern + l'appelle après le spawn ;
   **compile + link vert**. Chaque instance écrit son propre slot (`g_state[pool_slot(inst)]`), donc
   deux spawns = deux valeurs. Doc : `scripting-reference.md` (« Régler un prefab au spawn »).

### Prolongement conditionnel

- **Si les tests exports passent → généraliser le pli read-only aux LOCALS de script.** Périmètre
  confirmé avec Victor : **locals seulement, globals EXCLUS** (un global est partagé et persistable
  en SRAM — cf. v0.5/v0.20 — le baker casserait le partage et la sauvegarde). En pratique gcc -O2
  fait déjà ce pli pour un `local` littéral non réassigné ; le vrai apport propre au chantier reste
  l'export (valeur injectée au build). À ouvrir comme tranche distincte une fois les exports verts,
  **pas d'office**.

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
| `module.spawn(…)` / `sfx.play(…)` | un **slot pris dans un pool dimensionné au build** ; rend une référence, ou rien si le pool est plein | une boucle sur une plage contiguë |
| `module.verbe(n, …)` | le **matériel, numéroté par le matériel** : 4 calques, 2 fenêtres, 16 banques | un registre |

Plus une quatrième, qui n'obtient rien et ne vise rien de numéroté : `text.draw(tx, ty, id)`
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

- **Quatre renommages, complets.** `get_actor` → `actor.get` (le verbe passe derrière, comme
  `ui.get` — `global.get`/`const.get`, cités ici à l'origine, ont depuis quitté l'API
  au profit de l'accès pointé, cf. [Chantiers techniques](#chantiers-techniques)) ; `ui` → `interface` (une abréviation, que la grammaire
  de la maison refuse) ; les quatre `text.*_in` → `interface.draw_text` / `clear_text` /
  `reading` / `skip` (elles visent une **zone nommée d'une mise en page**, pas des coordonnées
  libres — c'est ce mélange qui rendait « Texte » illisible) ; les trois boîtes sonores
  (v0.8.6).

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

### Ouvert

- **`#data.Objets`** — le nombre de lignes d'une table de données. Évident, absent. À ouvrir,
  ou à refuser par écrit dans la référence de scripting.
- **La référence de scripting adopte-t-elle les mêmes huit sections ?** Deux plans différents pour la même
  API rouvriraient exactement le problème qu'on ferme ici.
- **v0.13 hérite de ce rangement** : les palettes de blocs de l'édition mixte seront ces huit
  sections. À vérifier quand le chantier démarre, pas maintenant.
- **`ARCHITECTURE.md` porte déjà les anciens noms** (`get_actor`, `ui.get`, `text.draw_in`
  — huit endroits au moins). Ils y sont **justes tant que le renommage n'est pas fait** : ce
  fichier décrit le code tel qu'il est. Il devient donc la liste de contrôle du renommage,
  pas une dette à corriger d'avance.

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

**Décision de conception (2026-09-10) : on ne scinde PAS `Actor` en deux structs.** L'idée d'un
`Actor` (logique) référençant un `Sprite` (affichage) par pointeur a été pesée puis écartée : sur un
ARM7TDMI sans cache, l'indirection frappe le cas 1:1 majoritaire dans les boucles les plus chaudes
(tick d'anim, compose OAM), et rouvre un second allocateur à durée de vie coordonnée — exactement ce
que le merge de la v0.25 (`actor_types_static.h`, « Une seule entité runtime ») refuse. « Actor sans
sprite » existe DÉJÀ (le marqueur : point de tir, ancre). Le seul cas neuf, « sprite sans actor »,
est couvert soit par l'acteur poolé (projectile), soit par une primitive d'affichage légère posée
sur un slot OAM (particule, UI) — jamais par un `Actor` amaigri.

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

**Ce que ça ne fait pas** : ça ne touche pas la struct `Actor` (cf. décision ci-dessus) et ça ne
crée pas de runtime commun. C'est la couche asset qui s'unifie, pas la couche entité.

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
`text.draw_in(list.row(...), ...)` par un contrat de rendu lié aux rangées authorées, sans faire de
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
