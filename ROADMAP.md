
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

Ce fichier ne garde que les jalons **non livrés** — c'est son rôle propre, cf. le tableau des six
documents en tête. Toute version livrée (v0.2 à v0.28 à ce jour) a son entrée dans le
[CHANGELOG](CHANGELOG.md) et son détail complet dans [changelog-archive/](changelog-archive/) ;
elle ne reste pas ici en doublon.

**Aucun jalon produit n'est actuellement ouvert.** v0.16 (« L'API : règle de construction et
rangement ») s'est fermé le 2026-09-27 — huit sections, cinq renommages, `REF_TYPE_TABLE`, cycle
de vie en cinq verbes, éléments d'interface typés, `module:fonction()` généralisé, garde-fou du
catalogue — voir le [CHANGELOG](CHANGELOG.md) et son [détail](changelog-archive/v0.16-api-construction.md).
Le singleton `mixer`, seule chose restée non tranchée, est sorti en chantier transverse (route
vers v1.0-stable, voir [ci-dessous](#au-delà-de-la-v10)) plutôt que de garder v0.16 ouvert pour
une proposition qui ne le concerne plus vraiment.

**v0.13** (« Édition mixte — les appels d'API en blocs ») a été retiré le 2026-09-27 : jamais
engagé (aucune ligne de code), et hors scope — ce logiciel n'est pas un outil de visual
scripting. Son numéro n'est pas réattribué (une version reste une identité, pas un rang) ; son
détail (désormais purement historique) reste consultable dans l'historique git de ce fichier.

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

1. ~~**Aucun moyen d'adresser un acteur dynamique.**~~ **Corrigé (2026-09-20)** — `actor.get`
   accepte un index dynamique 1-based (`actor:get(i)`), voir [test_actor_scene_naming.py](tests/test_actor_scene_naming.py).
   La piste restée ouverte à l'époque (les `exports_values` par instance non câblées au codegen)
   est depuis livrée — voir [le chantier des exports de script](changelog-archive/script-exports.md).

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
   ~~`actor:get(...):méthode()` en chaîne directe ne transpile pas~~ **Corrigé (2026-09-20)** —
   voir [test_lua_subset.py](tests/test_lua_subset.py) (`test_get_actor_chaine_directe_une_methode`).
   **Reste** : un `vec2` ne se stocke toujours pas dans un local (`local c = …:get_position()`
   devient `int c = /* ignoré */`) — lire `self.position.x` **inline** ; et `get_position()`
   n'existe pas comme méthode (seulement la propriété `self.position`) (`editor/scripting/codegen.py`
   `_invoke`, `editor/scripting/api.py`).

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

Séance du 2026-08-19 : relecture du logiciel du point de vue d'un projet cible (metroidvania à
composante RPG, équipe de trois, cartouche réelle au bout), qui a fixé un ordre de traitement
recommandé pour sept jalons alors ouverts (v0.14 → v0.19 → v0.24 → v0.20 → v0.23 → v0.21 →
v0.22). **Les sept sont désormais livrés**, dans cet ordre — voir le [CHANGELOG](CHANGELOG.md)
pour chacun. Le détail du raisonnement (pourquoi ce rang plutôt qu'un autre) reste consultable
dans l'historique git de ce fichier.

---

## Chantiers techniques

Un chantier technique ne livre rien de visible pour qui joue au jeu produit avec l'éditeur —
seulement une réécriture, une clarification ou une garantie côté code. Il n'apparaît ni dans le
[README](README.md) ni dans le [CHANGELOG](CHANGELOG.md), et ne porte pas de numéro `vX.Y` : une
fois refermé, son détail rejoint [changelog-archive/](changelog-archive/) comme n'importe quel
jalon, mais référencé par son nom plutôt que par un numéro — c'est là qu'est l'index complet des
chantiers clos ; ce tableau ne garde que ceux **non livrés**.

| Chantier | Ouvert le | État |
| --- | --- | --- |
| Préparer une image riche à l'import — recadrer, redimensionner | 2026-09-26 | Route vers v1.0-stable — non prioritaire pour l'alpha (décidé le 2026-09-29) ; tranches 4bpp/8bpp livrées, reste la tranche bitmap et la validation à la souris. Voir [ci-dessous](#chantier-transverse--préparer-une-image-riche-à-limport-recadrer-et-redimensionner-sans-toucher-au-png) |
| L'API dit tout ce que l'inspecteur règle | 2026-09-23 | **En cours** — tranche 1 (acteur, sprite, collision) livrée le 2026-09-23, sauf `parent` et `sprite_name` — **la collision est rouverte le 2026-09-24** (boîte = référence typée, `collision_box.get_tile`) ; tranches 2 (caméra, scène, calque) et 3 (interface) à suivre. Voir [ci-dessous](#lapi-dit-tout-ce-que-linspecteur-règle) |
| Piste Collision — un `Contact` d'événement | 2026-09-25 | À ouvrir — non verrouillée (normale acteur↔acteur), extraite de la struct `Actor` allégée, code non commencé — voir [ci-dessous](#piste-collision--un-contact-dévénement-pas-une-dernière-collision) |
| Le cache de scène | 2026-09-16 | À ouvrir — voir [ci-dessous](#le-cache-de-scène-rouvrir-une-scène-déjà-visitée-sans-tout-redécoder) |
| Undo/redo des sidecars d'éditeur | — | À ouvrir — envisagé pour **V2**, voir [ci-dessous](#undoredo-des-sidecars-déditeur-annuler-la-création-dun-groupe-un-déplacement-de-nœud) |
| L'atelier Texte réuni — écrire et voir dans un même écran | 2026-09-19 | Route vers v1.0-stable — non prioritaire pour l'alpha (décidé le 2026-09-29) ; conception et décision verrouillée, aucune étape commencée. Voir [ci-dessous](#chantier-transverse--latelier-texte-réuni-écrire-et-voir-dans-un-même-écran) |
| L'élément d'interface appartient à sa scène — des noms locaux | 2026-10-03 | À ouvrir — priorité non arbitrée ; conception proposée, **aucune décision verrouillée**, code non commencé. Garde-fou en place : un nom en double entre deux layouts est une erreur de build. Voir [ci-dessous](#lélément-dinterface-appartient-à-sa-scène--des-noms-locaux) |
| La fiabilité du journal de build | 2026-10-03 | **Tranche 1 livrée le 2026-10-03** (aucune erreur avalée, tout script vérifié, fautes injectées) ; **tranche 2 livrée le 2026-10-03** (diagnostic unique, `build.log`, sortie des outils classée) ; reste ouvert : les codes stables, si le besoin apparaît. Voir [ci-dessous](#la-fiabilité-du-journal-de-build) |

---

## La fiabilité du journal de build

### D'où vient la question (2026-10-03)

Un `; ADFZ` écrit en fin de ligne compilait « proprement ». Cause : `convert_chunk` « ignorait les
autres statements top-level », donc `local x = 1; ADFZ = 5` en tête de fichier était lu puis jeté, sans
une ligne de journal. Corrigé le même jour (le parseur porte désormais ces instructions, le checker les
refuse), mais le défaut n'était pas isolé : en cherchant autour, trois autres silences du même genre.

- Un behavior dont la syntaxe est fausse n'était qu'un **avertissement** : le build continuait sans ses
  fonctions.
- Un prefab sans instance dans la scène était sauté **avant** que son script soit parsé.
- Vingt-trois `except` larges (`Exception`, nu, `LuaParseError`) de la chaîne de build ne disaient rien,
  et rien n'écrivait pourquoi c'était acceptable.

Le journal est le seul témoin de ce que fait le build. Un silence y vaut une garantie fausse.

### Tranche 1 — aucun silence (livrée le 2026-10-03)

1. **Un `except` large dit pourquoi ou parle.** Dans `codegen/`, `scripting/` et `core/validator.py`, un
   handler de `Exception`, nu ou de `LuaParseError` doit lever, émettre un diagnostic, ou porter sur sa
   ligne `# tolerated: <raison>`. Un test parcourt le code et refuse le reste. Les `except:` nus de
   `exports_parser` deviennent `ValueError`.
2. **Tout script est vérifié, utilisé ou non.** Le validateur parse chaque `.lua` de `scripts/` :
   - attaché (acteur, scène, caméra, prefab, y compris un prefab à zéro instance) ou behavior : une
     faute de syntaxe ou une instruction hors fonction est une **erreur** ;
   - attaché à rien : un **avertissement** (un brouillon ne bloque pas le build, mais ne passe pas non plus
     sous silence).
3. **Des fautes connues injectées au build.** Un test construit un projet jetable contenant chacune des
   fautes trouvées (instruction hors fonction, `; ADFZ`, behavior cassé, prefab inutilisé cassé, script
   orphelin cassé) et exige qu'elle ressorte dans le journal avec son fichier et sa ligne.

Ne touche pas au format des messages, ni à l'interface.

Livré : `tests/test_silent_except.py` (la garde, 23 handlers annotés `# tolerated:` avec leur raison),
`_check_scripts_parse` dans `core/validator.py` (qui absorbe la lecture des behaviors de
`_check_behaviors_without_self`), `tests/test_build_fault_injection.py` (sept cas, dont un projet sain
comme témoin ; désactiver le contrôle en fait échouer cinq). Ajouté le même jour : un prefab qu'aucune scène ne
déclare n'était que parsé ; `lua_compiler` le fait maintenant passer par le checker (une fois, par la
première scène), donc une faute sémantique sort avant qu'une scène ne le déclare. Un script attaché à
rien reste vérifié pour sa seule syntaxe : sans propriétaire, il n'a pas de contexte (`self`, événements)
contre lequel être jugé.

### Tranche 2 — un seul diagnostic, un journal conservé (livrée le 2026-10-03)

Le problème, relevé dans le code : le validateur produit des `ValidationMessage` structurés (niveau,
cible cliquable) que l'onglet Diagnostics affiche, mais le build les aplatit en lignes
`[warn]  ⚠  [acteur] message` ; les erreurs du checker Lua, les avertissements du codegen et les
générateurs n'existent que comme texte, donc l'onglet Diagnostics ne les voit jamais. La gravité est
portée par un préfixe écrit à la main et par le canal d'émission (`log_line` gris, `error_line` rouge) ;
tout le stderr des outils est rouge, avertissements de gcc compris ; le clic « fichier:ligne » est une
regex sur du texte libre ; le verdict est un booléen ; le journal disparaît avec la fenêtre.

Décisions (2026-10-03) :

1. **Un seul objet.** `ValidationMessage` est étendu (`source`, `file`, `line`), pas doublé. Le
   `BuildWorker` l'émet par un événement `diagnostic` ; la console s'en rend, l'onglet Diagnostics se
   remplit de la même liste à la fin du build, le clic lit `file`/`line` au lieu d'une regex. Les lignes
   purement informatives (`[gen] 12 fichier(s) écrit(s)`) restent du texte. `CheckError` gagne un champ
   `line` (la ligne sort du texte du message).
2. **Le verdict se chiffre** : « N erreur(s), M avertissement(s) » à la fin de chaque build.
3. **`build.log`** dans `<projet>/build/`, **écrasé à chaque build**, écrit par le `BuildWorker` lui-même
   (donc indépendant de l'interface, et lisible d'un test) ; en-tête : version de l'éditeur, outils,
   projet, scène.
4. **La sortie des outils est classée par contenu** : `error`/`warning` de gcc deviennent des
   diagnostics ; le code de retour reste le seul juge de l'échec ; les lignes non classées d'un outil
   qui a échoué restent affichées en rouge, celles d'un outil qui a réussi passent en information.
5. **Pas de codes stables** (`E0412`) pour l'instant : à rouvrir seulement si le besoin apparaît (recherche
   dans la doc, suppression d'une classe d'avertissement). Les champs de 1 découplent déjà les tests du
   texte.

Livré : `tests/test_build_diagnostics.py` (douze cas : l'objet, le classement de la sortie des outils, le
verdict, `build.log` réécrit) et trois cas d'interface dans `tests/ui/test_diagnostics_panel.py`. Un build
réel de la démo `PongAdvanced` (17 s) donne `[build] 0 error(s), 1 warning(s)` et un `build.log` de 19 Ko.
Mécanique décrite dans ARCHITECTURE.md, « Le journal de build ».

**Suite (2026-10-03) — gcc cite le script.** Pas de table de correspondance : le générateur pose
`#line N "Script.lua"` avant chaque statement (la ligne vient du parseur, `Stmt*.line`) et rend gcc à son
`.c` en fin de corps de fonction, avec le numéro calculé sur le texte final. Une erreur de gcc sur le C
émis sort donc comme un diagnostic `Script.lua:N`, cliquable. Un behavior inliné porte ses propres
lignes. Le C d'un appelant sans nom de script (tests unitaires) reste sans directive. Vérifié par un vrai
gcc (`tests/test_gcc_cites_the_script.py`) et par la démo, dont la ROM garde sa taille.

Ce que ça ne fait pas : un réglage « avertissements = erreurs ».

### Tranche 3 — la couverture, mesurée (livrée le 2026-10-03)

Une matrice de pannes (31 cas injectés dans une copie de la démo, un vrai `BuildWorker` par cas) a mesuré
ce que le journal dit. Le bilan : les fautes de script sont toutes localisées ; trois familles de trous.

1. **Le validateur ne regardait que la scène active**, alors que le build compile toutes les scènes : un
   script supprimé, un sprite tronqué ou un fond illisible dans une autre scène passait en silence ou
   sortait en « internal error ». Les contrôles par scène (`_check_scene`, `_check_actors`,
   `_check_backgrounds`, `_check_frame_events`) tournent maintenant pour chaque scène ; le diagnostic porte
   le nom de sa scène. Les prefabs sont contrôlés comme des acteurs. « The scene contains no actor » ne
   s'affiche plus pour une scène qui a un script ou une interface (un écran titre est valide).
2. **Trois « internal error » deviennent des diagnostics clairs** : un script qui n'est pas en UTF-8, une
   erreur de système de fichiers (`build` qui est un fichier), un PNG illisible.
3. **Du français revenait par les exceptions** du cœur (palette, module de musique, polices, import) : en
   anglais, comme le reste du journal.

Résultat : avant, 6 pannes sur 31 sortaient en silence et 3 en « internal error » ; après, aucune panne
réelle ne passe sous silence. Les cas restants que la matrice range encore en « silence » ou « interne » sont
voulus : un script vide (valide), un fond dont le PNG manque (avertissement « layer ignored », le build
continue), une table de textes illisible (le projet refuse de s'ouvrir, message clair) et un générateur qui
lève (le filet de sécurité « internal error » + `crash.log`). Ajoutés au passage : un avertissement pour une
scène de départ inexistante, un `UnicodeDecodeError` de script dit comme tel (et le validateur s'arrête là, les
autres contrôles relisant le même fichier), une `OSError` du build dite « file system error ».

Reste volontairement tel quel : `actor:get("Inconnu")` est un avertissement (un script peut être partagé
entre scènes, et les noms d'acteurs sont locaux à leur scène).



### Tranche 4 — la couverture, tenue (livrée le 2026-10-03)

La matrice de la tranche 3 était un script jetable de 31 cas écrits à la main. Mesurée (274 sites qui
peuvent émettre un diagnostic, comptés dans le code puis comparés à ceux qui se déclenchent
réellement) : la matrice en atteint 28 (10 %), la suite entière 97, les deux réunis 107 (39 %). Les 167
autres ne se déclenchent jamais : audio, tables de données, caméras, budgets, vecteurs et tableaux du
checker, conversion grit.

1. **Des invariants testés en masse.** `tests/test_build_invariants.py` corrompt un à un des fichiers de
   la démo (tronqué, vidé, octets de bruit, clé JSON retirée, valeur du mauvais type, jeton de script
   supprimé) et exige, pour chaque cas : aucun « internal error » ; un build en échec porte au moins une
   erreur ; aucune erreur n'est en français ni ne recopie le chemin du projet ; un build en échec nomme le
   fichier abîmé. Une exception à l'invariant est une entrée datée dans le test, avec sa raison.
2. **Une couverture mesurée, avec un avertissement.** `tools/diagnostic_coverage.py` énumère les sites
   d'émission (AST), enregistre ceux qu'une exécution déclenche, et une fin de run complet de `pytest`
   **avertit** (sans échouer) quand un diagnostic couvert ne l'est plus ou qu'un nouveau n'est jamais
   déclenché. La référence est `tools/diagnostic_coverage_baseline.json`, mise à jour à la main.

Décidé le 2026-10-03 : le cliquet avertit, il ne bloque pas.

Livré. L'invariant a trouvé, en trois relevés complets (~105 pannes), ce que 31 cas écrits à la main
n'avaient pas vu : un projet qui refusait de s'ouvrir sans nommer son fichier (manifeste, `texts.json`,
`variables.json`) ; un code de langue du mauvais type ; `tiles_w` du mauvais type dans un fond, qui
plantait au build (`TypeError`) ; une planche de police illisible qui ne sortait que par ses
conséquences ; un fichier de traduction cassé **ignoré en silence** ; un script vide sans un mot. Tous
corrigés. Le relevé a aussi attrapé une régression de ce chantier même (un contrôle de planche appliqué
aux polices vectorielles), d'où le cas témoin « la démo saine ne produit aucune erreur ». État : 0
violation sur les ~105 pannes. `FUZZ_FULL=1` les joue toutes ; par défaut, une panne tournante par
fichier (31 builds). Les cas dont l'invariant est tenu par construction sont exclus avec leur raison
(`STILL_VALID_WHEN_CUT` : un script, une palette ou un module coupé reste un fichier valide).

La référence de couverture est relevée à 103 sites exercés sur 278. Les 175 autres sont la liste de
travail de la tranche suivante (audio, tables de données, caméras, budgets, vecteurs et tableaux du
checker, conversion grit).

### Tranche 5 — les 175 sites jamais atteints (livrée le 2026-10-03)

Trois fichiers de tests, un par famille : `tests/test_checker_diagnostics.py` (cas paramétrés du checker),
`tests/test_validator_diagnostics.py` (le plus petit projet fautif, puis l'appel du contrôle concerné) et
`tests/test_codegen_diagnostics.py` (outils factices, `BuildWorker` aux étapes court-circuitées). Les accords
internes (api.py ↔ en-têtes, lua_subset ↔ luaparser, domaines, colonnes) se testent en faussant leur source.

La référence passe de 103 à **274 sites exercés sur 278**. Restent quatre sites : un fond animé 8 bpp
(`rom_build`, avertissement de palette), l'erreur de placement d'un animé fusionné (`_err`), et une branche
défensive du checker (méthode inconnue sur un enfant, `_check_call_expr`).

Trouvé en chemin : deux messages restés en français (`frame_w/h invalides`, `l'image`, et deux libellés
d'audio), corrigés ; et l'outil de couverture comptait à tort les appels à une fonction locale `_warn` comme
des sites — un conduit, désormais ignoré.

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
hb:deactivate()                           -- les cinq verbes sont la seule porte d'écriture ; `hb.active` se LIT
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
| `hb.active` | lecture seule — **champ à créer au runtime**, écrit par `hb:activate()` / `hb:deactivate()` (cycle de vie en cinq verbes, 2026-09-25) : la résolution contre la carte et le test de chevauchement doivent l'ignorer quand il est faux | (aucune porte) |
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
| CollisionBox `active` | `hb.active` ; `hb:activate()` / `hb:deactivate()` | lecture seule, écrite par les verbes (champ runtime créé) |
| CollisionBox `tag` | `hb.tag` ; `self.box_count` | lecture seule |

**Livré (2026-09-23)** : les sept portes du tableau, la sonde C `tests/native/actor_box_probe.c`, 
`tests/test_inspector_api_parity.py`, un build ROM complet sur une copie d'OrbitTest (boîte « hitbox » 
ajoutée à la tourelle, script utilisant les sept portes). Le renommage d'un tag de collision 
(`RenameCollisionTagCmd`) réécrit maintenant aussi les scripts.

**Tranche 1 close (2026-09-29), vérifiée contre l'API et les règles posées depuis.** Restent sans porte, et c'est
décidé : `parent` — la parenté est authorée et jamais assignée au runtime (v0.23), donc seule une LECTURE SEULE
aurait un sens, et elle coûte un champ par acteur (un prefab posé N fois a N parents), au rebours de la struct
`Actor` allégée ; repoussé, à rouvrir sur besoin réel. `sprite_name` — `self.active_sprite` rend l'id du composant,
pas l'asset ; la question « comment nomme-t-on l'accès à un sous-objet de l'instance ? » est déjà ouverte, en route
vers v1.0-stable ([ci-dessous](#chantier-transverse--nommer-laccès-à-un-sous-objet-de-linstance)), et la trancher
ici la trancherait deux fois. `initial_state` et `prefab_name` n'ont pas besoin de porte : `self.anim` et
`self.tag` couvrent l'usage.

### Tranche 2 — caméra, scène, calque de fond (livrée le 2026-09-30)

Classement fait en lisant le runtime C (`runtime_api_inline.h`, `gba_engine.h`) et le codegen : ce qui est un
**littéral dans le C émis** est fixé au build (lecture seule) ; ce qui vit déjà en registre ou en RAM, ou coûte un
octet de RAM pour le devenir, est modifiable. Les portes déjà là (`camera.position`, `camera.bound`, `layer.visible`,
`layer.priority`, `layer.scroll`, `layer.map`, `scene.size`) ne sont pas répétées.

| Champ d'inspecteur | Porte Lua proposée | Nature | Raison (ce que le C fait aujourd'hui) |
| --- | --- | --- | --- |
| Camera `mode` | — | repoussé | changer de mode et de cible en jeu est voulu, avec une transition : chantier [« La caméra change de cible »](#chantier-transverse--la-caméra-change-de-cible-en-jeu-avec-une-transition) (route vers v1.0-stable). Aucune porte partielle d'ici là : le suivi est un `switch` dont les cas sont émis seulement pour les caméras à cible |
| Camera `follow_target` | — | repoussé | même chantier que `mode` |
| Camera `margin_x/y` | `camera.margin` (vec2) | **modifiable** | deux littéraux du `switch` → deux octets de RAM lus par `camera_follow` |
| Camera `frame_w/h` | `camera.frame` (vec2) | **modifiable** | pilote WIN0 (`window_set(0, …)`), qui existe déjà ; un getter du rectangle de WIN0 est à ajouter |
| Camera `name` | `camera.name` (comparable par son nom) | lecture seule | `DOMAIN_CAMERA` existe ; sert à savoir quelle caméra `camera:switch` a activée |
| Scene `scroll_h/v` | `scene.scroll_h`, `scene.scroll_v` (bool) | lecture seule | choisit `(g_actors[t].x>>8)` ou `cam_x` DANS le `switch` émis |
| Scene `blend_eva/evb/evy` | — | repoussé | chantier [« L'API de blending »](#chantier-transverse--lapi-de-blending-des-calques-au-petit-oignon) (route vers v1.0-stable) : `blend.set_alpha` / `blend.set_fade` → propriétés, décidé avec le `mixer` qui pose la même question pour le son |
| Scene `blend_*_role` | — | repoussé | même chantier [« L'API de blending »](#chantier-transverse--lapi-de-blending-des-calques-au-petit-oignon) |
| Scene `backdrop_color` | — | repoussé | même chantier [« L'API de blending »](#chantier-transverse--lapi-de-blending-des-calques-au-petit-oignon) : la porte est voulue, lecture ET écriture, sans nouveau type (un `vec3` ou un entier RGB555, à trancher là-bas) |
| Scene `transition_kind/frames` | — | repoussé | chevauche l'API de blending (la transition possède les registres de blending) : même chantier [« L'API de blending »](#chantier-transverse--lapi-de-blending-des-calques-au-petit-oignon) |
| Scene `collision_layer` | `scene.collision_layer` (int) | lecture seule | index BG fixé au build |
| Scene `render_mode` | — **aucune** | — | échafaudage non offert à l'auteur (règle « anticiper est permis, l'exposer non ») |
| Scene `music`, `script`, `notes` | — | pas de porte | décidé le 2026-09-29 : `music` ne règle que la musique de DÉPART (le module `music` couvre l'état) ; `script`/`notes` ne sont pas de l'état |
| BackgroundLayer `scroll_speed` | `layer.scroll_speed` (pourcent, 100 = normal) | **modifiable** | littéral dans la ligne `BGOFS = (cam_x*speed)>>8 + …` → quatre entiers de RAM, un par fond |
| BackgroundLayer `pal_bank` | `layer.pal_bank` (int) | lecture seule (livré) | banque allouée au build |
| BackgroundLayer `background_name` | `layer.image` (comparable par son nom) | lecture seule | asset chargé au build |
| BackgroundLayer `bg_slot` | — | sans objet | c'est la clé de la référence (`layer.get(n)`) |
| BackgroundLayer `visible` | — | sans objet | visibilité du viewport ÉDITEUR seulement (le codegen ne la lit pas) |

**Décidé le 2026-09-29** : `camera.mode` et `camera.target` sortent de la tranche (chantier caméra ci-dessous).
**Décidé le 2026-09-29** : tout ce qui touche au blending et à la transition de scène sort de la tranche (chantier
« L'API de blending » plus bas), comme `camera.mode` / `camera.target` (chantier caméra).

**Livré (2026-09-30)** : `scene.collision_layer` ; `camera.margin`, `camera.frame` (modifiables), `camera.name` (lecture seule, comparable par son
nom) ; `scene.scroll_h`, `scene.scroll_v` (lecture seule) ; `layer.scroll_speed` (modifiable, en pourcent) ; `layer.pal_bank` (lecture
seule, ajouté le 2026-09-30). `layer.image` reste **sans porte** : l'image est un littéral du build et un script sait
quel fond il a posé.
Ce que le chantier a demandé en plus :

- **Trois états passent de littéral à RAM.** La zone morte du suivi (`g_cam_margin_x/y`) et le cadre écran
  (`g_cam_frame_w/h`) sont recopiés de la ligne de table de la caméra à chaque `camera_switch()` ; le `switch` de suivi émis
  lit désormais `g_cam_margin_*` au lieu d'un littéral. La vitesse de parallax de chaque fond (`g_bg_speed[4]`, Q8) est
  remise à 256 par `display_reset()` puis posée par `scene_init` ; la ligne `BGOFS` la lit. Coût : environ 32 octets.
- **`camera.frame` réutilise `camera_switch()`** : les deux passent par `camera_set_frame()`, qui borne à l'écran et
  allume ou éteint WIN0 — une seule porte vers la window de la caméra.
- **`layer.pal_bank` est en lecture seule, et c'est voulu.** La banque est gravée dans CHAQUE case de la carte (champ
  `SE_PALBANK`) : l'écrire réécrirait la carte, et un fond en streaming reviendrait de la ROM avec l'ancienne. Le
  recolorage se fait par `palette:set_bg(banque, "Nuit")`, qui change toutes les tuiles d'un coup ; la lecture sert à ne
  pas coder le numéro en dur. Elle rend la banque de BASE, résolue comme le build la grave (« palette propre » →
  le slot alloué, ou le premier du bloc d'un fond compressé) ; un fond aux tuiles peintes de banques différentes ne
  rend pas toutes celles en usage. Quatre entiers de RAM, posés par `scene_init`.
- **Arrondi dans les deux sens pour `scroll_speed`** : le pourcent est converti en Q8 avec arrondi, et relu de même.
  Sans cela `scroll_speed = scroll_speed + 1` restait bloquée (51 % → Q8 130 → relu 50 %). Tenu par la sonde native.
- **Vérifié** : `test_inspector_api_parity.py` (43 tests, dont la sonde `actor_box_probe.c` étendue à la caméra et au
  parallax) et un build ROM complet sur un projet neuf (caméra en suivi, fond parallax, script utilisant les six
  portes) — `rom.gba` produite, `main.c` inspecté.

---

## Le cache de scène — rouvrir une scène déjà visitée sans tout redécoder

### D'où vient la question (2026-09-16)

L'auteur : sélectionner une scène dans le project viewer prend une demi-seconde perceptible, même
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

- **Quoi cacher, précisément.** Deux formes envisagées avec l'auteur, pas encore choisies :
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
des scènes, déplacer et redimensionner les boîtes, déplacer les nœuds), l'auteur a demandé de
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

## Piste Collision — un `Contact` d'événement, pas une « dernière collision »

Née dans le chantier « La struct `Actor` allégée » ([archive](changelog-archive/actor-struct-lightening.md)), livré à côté de cette piste : elle reste **non verrouillée**, code non commencé.

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

### Extension proposée (2026-09-25) — la normale vaut aussi pour un contact acteur↔acteur

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

---

## L'élément d'interface appartient à sa scène — des noms locaux

### D'où vient la question (2026-10-03)

En corrigeant la démo `PongAdvanced`, un défaut silencieux : deux mises en page (`SCR_Main` et
`SCR_Victory`) portaient chacune un élément nommé `txt_press_start`. Le générateur donne à **chaque**
unité C (scène, acteur) **tous** les `#define REGION_<NOM> <index>` du projet, par nom brut ; la valeur
est l'index dans la table plate `g_ui_regions`. Deux éléments homonymes émettaient donc la même macro
avec deux valeurs, le compilateur n'en disait qu'un avertissement, et **la dernière définition gagnait** :
`interface:get("txt_press_start")` visait l'élément de l'AUTRE interface (observé : le texte de la scène
principale s'affichait dans la région de la scène de victoire). Même mécanisme pour `IMAGE_*`,
`UILIST_*` et `UIELEM_*`.

La règle écrite jusqu'ici était « un nom d'élément est unique dans le projet » (v0.12, « collision
d'ABI »). Le validateur ne vérifiait que « un même layout posé deux fois dans une scène » : un homonyme
entre deux layouts de deux scènes passait sans rien dire. **Garde-fou posé le 2026-10-03** :
`_check_ui_element_names_unique` en fait une erreur de build, avec les deux layouts nommés. Il supprime
le défaut silencieux, **pas la contrainte** : l'auteur ne peut toujours pas écrire `titre` ou `score`
dans deux scènes, alors que les noms d'acteurs sont locaux à leur scène depuis le 2026-09-20.

### Le principe (proposé, non verrouillé)

Le même que pour l'acteur : **le nom est local, le symbole C est qualifié, le qualificatif est DÉRIVÉ au
build et jamais stocké** (source de vérité unique).

- **Authoring.** L'auteur écrit `interface:get("txt_press_start")` dans chaque scène. À la compilation de
  la scène S, le nom se résout parmi les éléments des layouts POSÉS sur S.
- **C.** Les constantes se qualifient par le layout (`REGION_<Layout>_<NOM>`, de même `IMAGE_`, `UILIST_`,
  `UIELEM_`). Un nom de layout est unique (c'est un asset) et un nom d'élément l'est dans son layout :
  plus aucune collision possible, même entre scènes. Le même élément porte le même symbole partout.
- **Les index ne changent pas.** `g_ui_regions`, `g_ui_images`, `g_ui_lists` et `g_ui_elements` restent
  des tables plates, dans l'ordre de `Project.all_*()`. Le runtime C n'est pas touché.
- **L'infrastructure par scène existe déjà** : `Project.scene_ui_layouts`, `scene_ui_slots`,
  `scene_ui_images`, `scene_ui_elements`. Seule la résolution NOM → constante est globale aujourd'hui
  (`lua_compiler.py` : `region_names`, `image_names`, `element_names`, `ui_ref_kinds`).
- **Unicité par scène**, pas par projet : le contrôle du 2026-10-03 passe de « tous les layouts » à « les
  layouts posés sur une même scène ». Deux layouts d'une même scène qui partagent un nom restent une
  erreur claire.

### Ce qu'il faudrait trancher avant d'ouvrir

1. **Les scripts partagés** (caméras, compilés une seule fois, sans scène connue). Aujourd'hui ils visent
   n'importe quel élément par son nom. Avec des noms locaux : soit `interface:get` y est refusé (erreur
   claire), soit la forme qualifiée `layout.element` y est acceptée. *Penchant :* refuser d'abord ; on
   n'ajoute la forme qualifiée que si un projet réel le demande.
2. **Les colonnes `region` et `image` des tables de données** (`data_tables.py`). Une table est globale :
   y citer un nom nu devient ambigu. *Penchant :* ces colonnes stockent la forme qualifiée
   `layout.element`.
3. **Le renommage d'un élément** (`project_renames.rename_ui_element`). Il réécrit aujourd'hui les
   références Lua de TOUT le projet ; avec des noms locaux il ne doit réécrire que les scripts des
   scènes qui posent ce layout. **Cas limite à régler :** un comportement partagé par plusieurs scènes
   peut désigner, dans l'une, un élément du layout renommé et, dans l'autre, un homonyme d'un autre
   layout.
4. **Le moment où l'ambiguïté apparaît.** Poser un layout sur une scène peut créer un homonyme avec un
   layout déjà là : l'avertir au placement, pas seulement au build.
5. **La création et le renommage dans l'éditeur** (`scene_tree_panel`, `canvas_controllers`) se garantissent
   aujourd'hui l'unicité sur le projet entier (`ui_element_names`) ; ils devront la chercher parmi les
   scènes qui posent le layout.

### Ce que ça touche

- **Générateur** : `scripting/codegen.py` (bloc des `#define`, résolution de `interface:get`),
  `codegen/runtime_codegen/lua_compiler.py` (contexte par scène), `gen_ui.py`, `data_tables.py`.
- **Langage** : `scripting/checker.py` (le nom doit exister parmi les éléments de la scène),
  `scripting/project_names.py` (complétion de `interface:get("` selon la scène du script).
- **Éditeur** : `core/project.py` (`ui_element_names` et ses voisins), `core/project_renames.py`,
  `core/validator.py`, les deux écrans de création/renommage.
- **Docs et tests** : `docs/scripting-reference.md`, un test de collision entre deux scènes, et la démo
  d'origine (deux `txt_press_start`) qui doit compiler SANS avertissement.

**Migration.** Aucune des données d'un projet existant ne change, hormis les cellules des colonnes
`region`/`image` si le point 2 est retenu. Un homonyme qui était une erreur devient légal.

### Ordre d'implémentation (proposé)

1. Qualifier les symboles et résoudre par scène, sans toucher aux scripts partagés (le cœur).
2. Vérificateur, validateur et complétion.
3. Tables de données et renommage.
4. Création et renommage dans l'éditeur ; doc.
5. Vérification par un vrai build : la démo d'origine, puis un projet de plusieurs scènes qui réutilisent
   les mêmes noms.

### Ce que ça ne fait pas

- Ne change ni le runtime C, ni les index des tables `g_ui_*`.
- Ne rend pas les noms de LAYOUT locaux : ils restent uniques, ce sont des assets.
- Ne touche pas aux noms d'acteurs (déjà locaux, cf. [changelog-archive/actor-scene-local.md](changelog-archive/actor-scene-local.md)).

---

## v1.0 — Le pipeline 2D complet

### L'objectif concret — cinq genres

La v1.0 était écrite comme un jalon de *validation* (« un deuxième jeu de démo, plus
stabilisation »). Elle porte en réalité une **affirmation de capacité** : à la v1.0, le
logiciel absorbe un projet 2D de production, de bout en bout.

**Le nombre et l'étiquette sont deux choses différentes (décidé le 2026-09-27).** Ce jalon
garde le nom « v1.0 », mais sa sortie est étiquetée **v1.0-alpha** : c'est une release
publique, pas une affirmation de stabilité totale. Les retours d'usage réel la corrigent
ensuite vers **v1.0-beta** puis **v1.0-stable**, sans changer de numéro ni rouvrir le scope
du jalon. Le même principe vaut pour les prochains jalons majeurs (v2.0, v3.0) : chacun peut
sortir en `-alpha` avant sa release officielle, le temps que l'usage réel le stabilise.

**La numérotation d'une release : `Backstage-X.Y.Z-<étiquette>` (décidé le 2026-10-02).**
Trois chiffres, et une étiquette toujours écrite : `-alpha`, `-beta` ou `-stable` (jamais de
version « nue »). Une fois l'alpha publiée officiellement :

| Chiffre | Ce qu'il compte | Exemple |
|---|---|---|
| `X` | le numéro de version, l'affirmation de capacité d'un jalon majeur | `1` |
| `Y` | un jalon standard de la roadmap (`vX.Y`) | `1.1.0` |
| `Z` | tout le reste qui avance : chantier technique, correction, optimisation | `1.0.3` |

La première sortie publique est donc `1.0.0-alpha`, puis `1.0.0-beta` et `1.0.0-stable` sous
le même numéro. La version se lit dans `editor/core/app_info.py` (source unique), et le tag
de la release (`v1.0.0-alpha`) doit lui être égal : la release échoue sinon.

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

### Ce qu'une « v1.0-alpha » exige, et qui n'est pas une fonctionnalité

Quatre points sans lesquels le mot « 1.0 » ne tient pas, même en `-alpha`. Aucun n'ajoute de capacité au moteur ;
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

### Chantier transverse — le singleton `mixer`

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (extrait de v0.16 le
2026-09-27).** Proposition intacte, rien n'est tranché ni codé.

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

### Chantier transverse — nommer l'accès à un sous-objet de l'instance

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-27).** Né du
chantier v0.16 : `self:collision_box("hitbox")` est un constructeur déguisé en méthode — la règle de
provenance ne le range nulle part (le garder tel quel comme exception nommée, ou le ranger sous un
module `self.boxes.get` ?). Élargi en discutant ce point : le sprite est exactement le même genre de
composant (il n'appartient qu'à l'acteur), mais suit une forme complètement différente — ses
propriétés sont APLATIES sur `self` (`self.frame`, `self.visible`...), sans constructeur du tout,
parce qu'un acteur n'affiche jamais qu'UN SEUL sprite à la fois (aucune ambiguïté sur « lequel »).
Conséquence : on ne peut aujourd'hui interroger que l'apparence ACTIVE (`self.active_sprite`,
`self:activate_sprite(id)`) — impossible de lire les propriétés d'une apparence sprite inactive sans
l'activer d'abord.

**Si ce point se rouvre**, il doit couvrir les DEUX cas ensemble (boîtes de collision multiples,
apparences sprite inactives), pour ne pas trancher deux fois la même question — « comment
nomme-t-on l'accès à un sous-objet précis d'une instance ? » — avec deux réponses différentes.

### Chantier transverse — l'atelier Texte réuni, écrire et voir dans un même écran

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-29).** Conception
et décision verrouillée (2026-09-19) intactes, aucune étape n'est codée.

L'atelier actuel coupe le geste en deux : la source balisée vit dans un `QTextEdit` à gauche,
le rendu GBA dans `FontScreenPreview` à droite. Cette séparation a servi à poser le pipeline des
polices, mais elle oblige désormais à lire deux fois le même texte pour savoir ce que produisent
`[font]`, `[color]`, les icônes et les valeurs. Le chantier les réunit dans **une seule surface de
travail** : le texte se modifie là où son rendu est visible.

Il ne s'agit pas de confier le texte à la mise en forme de Qt : ses polices système, son retour à
la ligne et sa sélection ne sont pas ceux de la ROM. `FontScreenPreview` reste donc le moteur de
rendu fidèle (glyphes rasterisés et `layout_marked_text`) ; l'éditeur devient la couche d'entrée
et de sélection posée sur cette même surface.

#### Le contrat utilisateur

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

#### Le morceau difficile : correspondre source et rendu

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

#### Analyse technique d'implémentation

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

#### Ordre d'implémentation

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

#### Décision verrouillée (2026-09-19)

La vue balisage n'est jamais une vue source typographique Qt : les balises sont affichées en police
du moteur, dans la même composition, tandis que tout le contenu reste rendu de façon fidèle avec
les polices de preview.

#### À trancher au démarrage

- Le bouton doit-il mémoriser sa préférence par projet ou rester une bascule de session ?
- Une valeur `$score` affiche-t-elle sa valeur initiale dans la vue nette (comportement actuel de
  l'aperçu) ou le jeton `$score` pour rappeler qu'elle est dynamique ?

### Chantier transverse — préparer une image riche à l'import, recadrer et redimensionner sans toucher au PNG

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-29).** Les tranches
4bpp et 8bpp sont livrées ; reste la tranche bitmap (son propre panneau, pas commencée) et la validation à la
souris dans l'éditeur.

#### D'où vient la question (2026-09-26)

Une photo de 474×314 importée en tuilé 8bpp donne 2194 tuiles uniques pour un budget de 256 : le
Background Editor le **dit** (avertissement rouge « Exceeds VRAM ») mais ne laisse rien faire —
l'auteur n'a que le mode (tuilé/bitmap, profondeur) et un logiciel externe. Et le tuilé tronque
l'index de tuile à 10 bits (`pack_se`), donc au-delà de 1024 la carte se brouille en silence.

#### Le principe

Deux gestes sur la **préparation de la source**, avant l'encodage, portés par le sidecar :

- **Recadrer** (`import_crop`, en pixels de la source) puis **redimensionner** (`import_size`, en
  pixels de l'image préparée), dans cet ordre ;
- le PNG n'est **jamais** modifié : `prepare_source` produit une image PIL en mémoire, que
  reçoit `encode_by_mode` — l'unique endroit qui choisit l'encodeur. Tous les chemins qui
  encodent (recompression de l'inspecteur, import, resynchronisation d'un PNG retouché,
  réconciliation au chargement) lisent la MÊME préparation, sinon la ROM et l'éditeur
  divergeraient ;
- revenir en arrière = effacer la préparation (bouton « Original »), le PNG étant intact.

#### Décisions verrouillées (2026-09-26)

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

#### Mesurer le 4bpp avant d'y passer (2026-09-26)

Bouton « Analyser pour le 4bpp » dans l'inspecteur, sur l'image **préparée**, hors-thread :
couleurs par tuile (min / moyenne / max et répartition), tuiles qui tiennent en 15 couleurs,
jeux de couleurs distincts et tuiles qui en partagent un, palettes nécessaires, verdict « sans
perte » ou non. `bg_import.analyze_tile_colors` réutilise l'extraction et le packing de la
compression : le chiffre annoncé est celui que la compression trouvera. Les palettes comptées
sont celles des tuiles qui tiennent, sans la réduction — un minimum, pas une promesse.

#### Jouer avec la compression — l'inspecteur contextuel (2026-09-26)

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

#### Ce que ça ne fait pas

Pas d'annulation pas-à-pas (Ctrl+Z) : la recompression est asynchrone et « Original » suffit à
revenir. Pas de réglage de couleurs (le mode et la profondeur existent déjà dans l'inspecteur).

### Chantier transverse — la caméra change de cible en jeu, avec une transition

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-29).** Né de la tranche 2 de
« L'API dit tout ce que l'inspecteur règle » : `Camera.mode` et `Camera.follow_target` n'ont pas de porte Lua, et une
lecture seule ne suffirait pas — l'auteur doit pouvoir CHANGER de cible en jeu. Aujourd'hui le suivi est un
`switch(g_cam_active)` dont la cible est une constante par caméra ; changer de cible en cours de scène, c'est de la
RAM (mode, index de cible) lue par le suivi, et surtout un **système de transition** : passer de l'acteur A à l'acteur B
d'un coup est une téléportation de cadre. Le chantier pose les deux ensemble (état modifiable + interpolation de la
caméra vers la nouvelle cible), pour ne pas ouvrir une porte dont la première utilisation est un saut. Rien n'est
tranché ni codé.

### Chantier transverse — l'API de blending des calques, au petit oignon

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-29).** Né de la tranche 2 de
« L'API dit tout ce que l'inspecteur règle » : quatre champs d'inspecteur touchent au blending, et chacun mérite d'être pensé avec les autres plutôt que réglé à la volée. Rien n'est tranché ni codé. À rassembler :

- les poids `blend_eva/evb/evy` : aujourd'hui `blend.set_alpha` / `blend.set_fade` s'écrivent, aucune lecture ; elles deviennent des propriétés (état → propriété), **décidé avec le `mixer`** qui pose la même question pour le son ;
- les rôles (dessus / dessous) des calques, de l'OBJ et du fond de teinte : écriture indexée existante (`set_layer/obj/backdrop`), lecture absente ;
- `backdrop_color` : une porte en lecture ET écriture, sans nouveau type — un `vec3` (r, g, b) ou un entier RGB555 ; c'est ici qu'on choisit ;
- la transition de scène (`transition_kind`, `transition_frames`) : elle possède les registres de blending pendant sa durée (`transition_begin/fade/end`), donc elle ne se règle pas sans que l'API de blending soit posée.

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

### Chantier transverse — la destruction des éléments d'interface

**D'où ça vient (2026-09-27).** En discutant du critère 4 de v0.16 (« unifier absent par type »),
constat : un élément d'interface, un calque ou une fenêtre sont **statiques par construction** —
`destroy()` n'existe QUE pour `actor`/`sfx` dans le catalogue ([api.py](editor/scripting/api.py)),
posé une fois pour toutes à l'authoring, sans commande de script pour le faire disparaître. C'est
ce qui rend `interface:get("Menu") ~= nil` toujours vrai, et c'est ce qui permettait de classer ces
types comme « jamais absents » sans exception à traiter.

**La piste, non développée.** Si un projet réel demande un jour de détruire dynamiquement un
élément d'interface (un menu généré au runtime, une fenêtre jetable) plutôt que de se contenter de
`hide()`, ça romprait l'hypothèse « statique = jamais nil » du critère 4 : ces types rejoindraient
la catégorie des références de pool, avec tout ce que ça implique (`nil` testable, retrait du
`REF_TYPE_TABLE.nullable=False`, etc.). **Aucune décision prise, aucun besoin démontré** — à
rouvrir si un projet en butte contre la limite actuelle (`hide()` seul, l'élément reste en mémoire).

### Chantier transverse — les calques par nom

**D'où ça vient (v0.16).** `layer:get(n)` adresse un fond par son NUMÉRO (0 à 3, borné par le mode
vidéo de la scène) — cohérent avec la provenance « le matériel, numéroté par le matériel » de la
règle de construction. Question restée ouverte pendant le chantier : offrir aussi `layer:get("Fond")`
par un nom authoré, comme pour un élément d'interface.

**Pourquoi ce n'est pas fait maintenant.** Recommandation retenue à l'époque : attendre un besoin
réel avant d'ajouter une seconde façon d'adresser la même chose — deux provenances pour un fond
recréerait exactement le doublon que la grammaire de l'API refuse ailleurs. **Aucune décision
prise, aucun besoin démontré.**

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
