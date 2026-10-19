
# Roadmap

Ce document explique **le pourquoi** derrière les jalons et chantiers non clos : le scope,
les décisions déjà verrouillées, les tranches déjà livrées quand elles éclairent le reliquat,
et les questions volontairement laissées ouvertes.

Une fois un jalon **entièrement livré**, son détail quitte ce fichier : la discussion complète (décisions
verrouillées, pièges rencontrés, mesures) part dans [changelog/archives/](changelog/archives/), un
fichier par version, ou par chantier, pour un [chantier technique](#chantiers-techniques). Un
jalon **produit** gagne en plus une ligne au [CHANGELOG](changelog/CHANGELOG.md) ; un chantier technique
n'y va jamais, il ne concerne que le code. Rien n'est perdu, ça change juste d'endroit. Pour
rouvrir une décision passée, c'est là qu'elle est.

Six documents, six rôles :

| Fichier | Pour qui | Contenu |
| --- | --- | --- |
| [README](README.md) | un visiteur | une ligne par version |
| [CHANGELOG](changelog/CHANGELOG.md) | qui veut savoir ce qui a changé | une entrée courte par version livrée |
| [changelog/archives/](changelog/archives/) | qui rouvre une décision passée | le détail complet d'une version livrée |
| **ce fichier** | qui décide de la suite | scope, décisions, reliquat ouvert (jalons et chantiers **non clos**) |
| [ARCHITECTURE](ARCHITECTURE.md) | qui modifie le code | comment c'est construit |
| [Référence de scripting](docs/scripting-reference.md) | qui écrit un script | le Lua accepté, et ce qui ne l'est pas |

Convention : **Décisions verrouillées** = tranché, à implémenter tel quel. On ne rouvre
pas sans raison neuve. **Ouvert** = identifié mais volontairement non tranché : à rouvrir
quand le chantier démarre réellement, le contexte du moment valant mieux que des
suppositions faites à l'avance.

Un **jalon produit** porte un numéro (`vX.Y`) : il figure dans le tableau qui suit, et une fois
livré, une ligne rejoint le [README](README.md). C'est ce qu'un visiteur vient chercher. Un
**chantier technique** n'en porte pas : né en cours de route (une question posée à
l'architecture, une dette relevée en marchant), il ne change rien pour qui joue au jeu produit
avec l'éditeur, seulement pour qui modifie le code. Il vit dans sa propre section,
[Chantiers techniques](#chantiers-techniques), à l'écart du tableau et du README, jamais
numéroté, jamais mélangé aux jalons produit.

---

## Où on en est

Ce fichier garde les jalons et chantiers **non clos**. C'est son rôle propre, cf. le tableau des six
documents en tête. Une version entièrement livrée (v0.2 à v0.28 à ce jour) a son entrée dans le
[CHANGELOG](changelog/CHANGELOG.md) et son détail complet dans [changelog/archives/](changelog/archives/) ;
elle ne reste pas ici en doublon.

**Un seul jalon produit est ouvert : [v0.29](#v029-diffuser-une-rom-dans-le-navigateur-itchio)**
(empaqueter une ROM pour le navigateur, ouvert le 2026-10-05, aucune ligne de code). Pour mémoire,
v0.16 (« L'API : règle de construction et
rangement ») s'est fermé le 2026-09-27 (huit sections, cinq renommages, `REF_TYPE_TABLE`, cycle
de vie en cinq verbes, éléments d'interface typés, `module:fonction()` généralisé, garde-fou du
catalogue). Voir le [CHANGELOG](changelog/CHANGELOG.md) et son [détail](changelog/archives/v0.16-api-construction.md).
Le singleton `mixer`, seule chose restée non tranchée, est sorti en chantier transverse (route
vers v1.0-stable, voir [ci-dessous](#au-delà-de-la-v10)) plutôt que de garder v0.16 ouvert pour
une proposition qui ne le concerne plus vraiment.

**v0.13** (« Édition mixte, les appels d'API en blocs ») a été retiré le 2026-09-27 : jamais
engagé (aucune ligne de code), et hors scope. Ce logiciel n'est pas un outil de visual
scripting. Son numéro n'est pas réattribué (une version reste une identité, pas un rang) ; son
détail (désormais purement historique) reste consultable dans l'historique git de ce fichier.

---

## Frictions relevées en construisant la démo tactique (2026-09-20)

La démo tactique (type Advance Wars) est le **deuxième jeu de démo** exigé par la v1.0, un
jeu de validation, dont le rôle est précisément de faire remonter ce sur quoi un projet non
trivial bute. La boucle complète a été construite et compile (grille + curseur, sélection,
stats pilotées par `data.Units`, portée surlignée par pool spawné, déplacement d'unité, menu
d'action, tour sauvegardé), assets 100 % auto-générés passés par le vrai pipeline d'import.
Voici les points de friction rencontrés en chemin, **par ordre d'importance**. Ce ne sont pas
des bugs de la démo mais des manques de l'outil qu'elle a révélés. Les cinq premiers
toucheront TOUT projet non trivial, pas seulement ce genre. Les points 1 et 2 ont été
relevés en construisant la boucle ; le 2 a été confirmé par le **test d'échelle** (40 scènes /
200 sprites, cf. la note en fin de section).

1. ~~**Aucun moyen d'adresser un acteur dynamique.**~~ **Corrigé (2026-09-20)**. `actor.get`
   accepte un index dynamique 1-based (`actor:get(i)`), voir [test_actor_scene_naming.py](tests/scripting/test_actor_scene_naming.py).
   La piste restée ouverte à l'époque (les `exports_values` par instance non câblées au codegen)
   est depuis livrée. Voir [le chantier des exports de script](changelog/archives/script-exports.md).

2. **Les acteurs posés ne sont pas namespacés par scène.** Deux scènes qui posent chacune un
   acteur nommé « Cursor » (ou « Enemy », « Boss »…) collisionnent sur un seul symbole C :
   `actor_Cursor.c` de la seconde écrase celui de la première, et `ACTOR_CURSOR` est défini deux
   fois avec des valeurs différentes. Les prefabs et les scripts de scène, eux, SONT qualifiés
   (`<Scène>_<Prefab>`, `<Scène>_scene`) ; les acteurs posés font exception. Le validateur
   l'attrape et nomme le doublon (bien), mais dans un jeu à 40 scènes, réutiliser un nom
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
   ~~`actor:get(...):méthode()` en chaîne directe ne transpile pas~~ **Corrigé (2026-09-20)**,
   voir [test_lua_subset.py](tests/scripting/test_lua_subset.py) (`test_get_actor_chaine_directe_une_methode`).
   **Reste** : un `vec2` ne se stocke toujours pas dans un local (`local c = …:get_position()`
   devient `int c = /* ignoré */`). Lire `self.position.x` **inline** ; et `get_position()`
   n'existe pas comme méthode (seulement la propriété `self.position`) (`editor/scripting/codegen.py`
   `_invoke`, `editor/scripting/api.py`).

7. **Pas de pose instantanée d'un acteur tiers.** Seul `self.position = …` est sûr ; l'écriture
   de propriété sur un handle (`u.position = …`) n'est ni documentée ni fiable. Un déplacement
   instantané d'une autre unité s'obtient par le détour `u:move_to(cible, 999)` (vitesse énorme
   pour ne pas étaler sur plusieurs frames), ce qui n'est pas son intention (`editor/scripting/api.py`
   `self:move_to`).

8. **Aucune API headless « builder le projet ».** Le codegen n'est pas exposé comme une simple
   fonction : il a fallu instancier `BuildWorker` (un `threading.Thread`/`EventEmitter`) et
   appeler `run()` en câblant les callbacks. Pire, `run()` **couple build et lancement mGBA**.
   En headless il a fallu sous-classer pour neutraliser `_step_launch_mgba`, sinon le worker
   rapporte `finished(False)` alors que la ROM est bel et bien produite. Il manque un point
   d'entrée « build seul, sans run », utile à la CI et à toute génération automatisée
   (`editor/codegen/rom_build.py`).

9. **Création programmatique d'un projet : pas de raccourcis, et un piège.** Ajouter un sprite
   depuis un PNG impose d'enchaîner soi-même `encode_sprite_asset` + `file_stamp` + `append` +
   `save` (les sidecars portent des champs calculés (`source_stamp`, palettes quantifiées,
   mapping de tuiles), donc rien à écrire à la main) ; rien n'expose ça comme une opération
   unique. Et `Project.create` écrit une `Scene_01` de starter **sur le disque** : remplacer la
   liste de scènes en mémoire ne l'efface pas, et le build recompile alors une scène fantôme.
   Il faut `project.scenes.delete()` explicitement. Aucun chemin évident « remplace la scène par
   défaut » (`editor/core/project.py`, `editor/core/resources/asset_reconciliation.py`).

**Le test d'échelle (Temps 2). Le point « vérification à l'échelle » de la v1.0 est validé.**
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
v0.22). **Les sept sont désormais livrés**, dans cet ordre. Voir le [CHANGELOG](changelog/CHANGELOG.md)
pour chacun. Le détail du raisonnement (pourquoi ce rang plutôt qu'un autre) reste consultable
dans l'historique git de ce fichier.

---

## v0.29 (Diffuser une ROM dans le navigateur (itch.io))

**Ouvert le 2026-10-05. Faisabilité vérifiée, aucune ligne de code.**

### D'où vient la question

Un jeu fini doit pouvoir être **joué sans installer d'émulateur**. itch.io n'héberge pas de ROM
jouable : une page « HTML5 » est un zip dont l'`index.html` tourne dans une iframe. Il faut donc
livrer, avec la ROM, un émulateur compilé pour le navigateur et la page qui le pilote. La ROM
reste intacte ; c'est l'émulateur qui la fait tourner. Ce jalon livre le **générateur** de ce zip.

### Ce que ça livre

Une **fenêtre Qt indépendante** : on choisit à la main la ROM `.gba` à empaqueter, on règle
quelques options de page, on obtient un **zip prêt à envoyer sur itch.io**. Elle vit dans le dépôt
mais **hors du build du logiciel** : ni installateur, ni exécutable de l'éditeur, aucun lien avec
le projet ouvert dans l'éditeur. Le générateur prend une ROM et rend un dossier web ; il ne sait
rien d'où elle vient.

### Faisabilité (vérifiée le 2026-10-05)

- **L'émulateur existe en WebAssembly.** mGBA compilé avec Emscripten, publié sous
  [`@thenick775/mgba-wasm`](https://www.npmjs.com/package/@thenick775/mgba-wasm) (2.5.1 à la date
  de la vérification) : six fichiers, environ 2,8 Mo, aucune dépendance, `mgba.js` + `mgba.wasm`.
  C'est le moteur de gbajs3. Dépôt : [`thenick775/mgba`](https://github.com/thenick775/mgba).
- **Licence MPL-2.0**, redistribuable : il faut joindre le texte de la licence et un lien vers les
  sources dans le zip, et ajouter l'entrée à `THIRD-PARTY-NOTICES.md`. Le BIOS est émulé par mGBA :
  **aucun BIOS Nintendo n'est livré**.
- **API suffisante** : `new mGBA({ canvas })`, `FSInit()`, `uploadRom()`, `loadGame()` ;
  sauvegardes (`getSave`, `uploadSaveOrSaveState`) ; audio (`pauseAudio`, `resumeAudio`,
  `setVolume`) ; touches (`bindKey`, `buttonPress`). Le système de fichiers virtuel d'Emscripten
  est accessible via `Module.FS`.
- **Précédent** : au moins un jeu GBA est jouable dans le navigateur sur itch.io par ce moteur.
- **Pas d'Emscripten ni de Node chez l'auteur du jeu** : le binaire est vendorisé, pas recompilé.

### Décisions verrouillées (2026-10-05)

- **Hors de l'éditeur dans un premier temps** : fenêtre Qt autonome, ROM choisie à la main. Une
  intégration à l'éditeur (étape finale du build) se reconsidère une fois le générateur éprouvé,
  pas avant.
- **On vendorise le binaire npm, on ne le recompile pas.** Version épinglée, empreinte contrôlée ;
  jamais « latest ».
- **Le générateur ne publie pas.** Il produit le zip ; l'envoi sur itch.io reste un geste de
  l'auteur du jeu (pas de `butler` dans ce jalon).
- **Pas de fonctions d'émulateur qui n'ont rien à faire là** : rembobinage, états de sauvegarde
  rapides, filtres d'écran. Une page de diffusion, pas un émulateur de confort.

### Le point dur (les threads)

Le cœur mGBA est multi-thread : la page doit être **isolée** (en-têtes COOP/COEP) pour que
`SharedArrayBuffer` existe, et `mgba.js`/`mgba.wasm` sont servis **depuis la même origine** (les
workers sont chargés depuis l'URL du script). Côté itch.io :

- il existe une case « SharedArrayBuffer support » dans les réglages du projet, marquée
  expérimentale, qui fait servir les en-têtes d'isolation (`COEP: credentialless`) ;
- **le générateur ne peut pas la cocher** : elle se coche sur la page itch, à la main. Le README
  du zip et la fenêtre doivent le dire ;
- `credentialless` est mal supporté hors Chromium ; une erreur `SharedArrayBuffer` sur Firefox est
  signalée dans les échanges d'itch. **Risque principal, non levé.**

Limites itch (relevées dans des extraits de forum, pas dans la documentation officielle, à
reconfirmer) : un fichier extrait de 200 Mo au plus, 500 Mo au total, 1000 fichiers, `index.html`
à la racine du zip. Une ROM GBA fait 32 Mo au plus : aucune n'est atteinte.

### Déroulé

1. **Prototype jetable** : une page HTML + le binaire 2.5.1 + une ROM de démo, servis en local avec
   les en-têtes COOP/COEP. Vérifie : la ROM démarre, le son marche après un clic, la sauvegarde
   survit à un rechargement. Rien n'est gardé de ce code que le gabarit qui a fait ses preuves.
2. **Essai sur itch.io** avec un projet **privé** : case SharedArrayBuffer cochée, test sur
   Chrome, Firefox et Safari. **Si Firefox ou Safari échouent**, on tranche ici (voir « Ouvert »)
   avant d'écrire la moindre fenêtre.
3. **Le gabarit de page** : canvas, écran « Cliquer pour jouer » (l'audio ne démarre qu'après un
   geste), mise à l'échelle entière sans flou, plein écran, mapping clavier affiché, persistance
   de la `.sav` dans IndexedDB (copie du FS virtuel, relue au chargement).
4. **Le générateur** (module sans Qt) : ROM + options → dossier web → zip. Copie le binaire
   vendorisé, la licence MPL-2.0 et le lien vers les sources. Contrôle le zip produit
   (`index.html` à la racine, chemins relatifs, taille, empreinte du binaire).
5. **La fenêtre Qt** : choix de la ROM, titre, facteur d'échelle, couleur de fond, dossier de
   sortie. Elle appelle le module de l'étape 4 et ne contient aucune logique de génération.
6. **Tests** : le générateur (structure du zip, options injectées, refus d'une ROM absente ou
   trop grosse) ; l'équivalence du gabarit se vérifie à l'étape 2, pas en test automatique.
7. **Documentation** : une page du guide utilisateur (de la ROM à la page itch, y compris la case
   à cocher), `THIRD-PARTY-NOTICES.md`, ARCHITECTURE.md. Le détail part ensuite dans
   `changelog/archives/v0.29.md`, une ligne au CHANGELOG et au README.
8. **Nettoyage** : le prototype de l'étape 1 est supprimé avant de dire terminé.

### Fichiers annoncés

Création : le module du générateur, la fenêtre Qt, le gabarit de page, le binaire vendorisé et
son empreinte, les tests, la page de guide. Modification : `THIRD-PARTY-NOTICES.md`,
`ARCHITECTURE.md`, `ROADMAP.md`. **Non touchés** : le build ROM, le codegen, le runtime, le
packaging de l'éditeur (`packaging/`, PyInstaller, installateur). C'est précisément ce que
« hors de l'éditeur » garantit.

### Ouvert

- **Où vit le code dans le dépôt**, et comment il reste hors du build du logiciel (dossier à
  part, exclusion explicite de l'installateur) : à décider à l'étape 4, pas avant.
- **Si Firefox ou Safari ne passent pas avec `credentialless`** : documenter « Chromium seulement »,
  ou chercher un cœur sans threads (build mono-thread de mGBA, ou autre émulateur) ? Dépend du
  résultat de l'étape 2.
- **Vendoriser dans le dépôt ou télécharger à la demande** (comme la toolchain devkitPro) : les
  quelque 3 Mo plaident pour le dépôt, mais l'empreinte épinglée doit rester la source de vérité.
- **Intégration à l'éditeur** (une étape « Exporter pour le web » après le build) : reportée
  volontairement, à rouvrir quand le générateur autonome a servi.
- **Contrôles tactiles pour mobile** : utiles sur itch, mais hors du minimum ; à trancher après
  l'étape 3.
- **Le nom et la marque** : la page produite doit éviter d'afficher « GBA » comme marque (même
  risque Nintendo que celui noté au point « Une licence » de la v1.0) ; à relire à l'étape 5 sur
  les textes de la fenêtre.

---

## Chantiers techniques

Un chantier technique ne livre rien de visible pour qui joue au jeu produit avec l'éditeur,
seulement une réécriture, une clarification ou une garantie côté code. Il n'apparaît ni dans le
[README](README.md) ni dans le [CHANGELOG](changelog/CHANGELOG.md), et ne porte pas de numéro `vX.Y` : une
fois refermé, son détail rejoint [changelog/archives/](changelog/archives/) comme n'importe quel
jalon, mais référencé par son nom plutôt que par un numéro. C'est là qu'est l'index complet des
chantiers clos ; ce tableau ne garde que ceux **non clos**.

**Livré le 2026-10-17, [Le gabarit commun des pop-up](changelog/archives/common-popups.md).**
Les messages d'information, d'attention, d'erreur et de confirmation des 22 modules concernés
passent par `ui/common/popup.py` : illustrations adaptées au type de message, boutons et
styles partagés, icônes cohérentes par type. Le détail et les vérifications sont archivés.

| Chantier | Ouvert le | État |
| --- | --- | --- |
| Préparer une image riche à l'import, recadrer, redimensionner | 2026-09-26 | Route vers v1.0-stable, non prioritaire pour l'alpha (décidé le 2026-09-29) ; tranches 4bpp/8bpp livrées, reste la tranche bitmap et la validation à la souris. Voir [ci-dessous](#chantier-transverse-préparer-une-image-riche-à-limport-recadrer-et-redimensionner-sans-toucher-au-png) |
| L'API dit tout ce que l'inspecteur règle | 2026-09-23 | **En cours**, tranche 1 (acteur, sprite, collision) livrée le 2026-09-23, sauf `parent` et `sprite_name`, **la collision est rouverte le 2026-09-24** (boîte = référence typée, `collision_box.get_tile`) ; tranches 2 (caméra, scène, calque) et 3 (interface) à suivre. Voir [ci-dessous](#lapi-dit-tout-ce-que-linspecteur-règle) |
| Piste Collision, un `Contact` d'événement | 2026-09-25 | À ouvrir, non verrouillée (normale acteur↔acteur), extraite de la struct `Actor` allégée, code non commencé. Voir [ci-dessous](#piste-collision-un-contact-dévénement-pas-une--dernière-collision-) |
| Le cache de scène | 2026-09-16 | À ouvrir. Voir [ci-dessous](#le-cache-de-scène-rouvrir-une-scène-déjà-visitée-sans-tout-redécoder) |
| Undo/redo des sidecars d'éditeur | Non renseigné | À ouvrir, envisagé pour **V2**, voir [ci-dessous](#undoredo-des-sidecars-déditeur-annuler-la-création-dun-groupe-un-déplacement-de-nœud) |
| L'écran Texte n'édite et ne range que du contenu | 2026-10-10 | **À ouvrir**, conception proposée, **rien de verrouillé**, code non commencé ; retire l'aperçu écran et édite le contenu dans la table. Remplace « L'atelier Texte réuni » (abandonné). Voir [ci-dessous](#lécran-texte-nédite-et-ne-range-que-du-contenu) |
| L'écran Données, une grille de jeu, pas un tableur | 2026-10-14 | **En cours, première tranche livrée le 2026-10-17** : grille et barre d'actions revues, couleurs de colonnes, références aux assets sprite/background et sélecteurs filtrables partagés ; reste la saisie en série, la navigation vers les références et la validation d'usage. Voir [ci-dessous](#lécran-données-une-grille-de-jeu-pas-un-tableur) |
| L'écran Son montre le geste sans recalculer l'onde | 2026-10-12 | **Livré pour l'essentiel (2026-10-12)**, plus aucun rendu pendant qu'un potard est tenu, bascule Onde \| Scope (oscilloscope du mix, tiré du son qui joue), durée sur la règle, barres des canaux qui suivent le volume ; **reste ouvert** : les repères sonores de musique sont **livrés le 2026-10-14** (quatre natures, voir ci-dessous) ; les repères de **jingle** sont livrés le 2026-10-14 (tranche 1, en temps) ; restent l'appel d'événement et les points de sortie pour les music box (**chantier à décider**), un indicateur de marge du mix (proposé, **non décidé**), un scope par canal. Voir [ci-dessous](#lécran-son-montre-le-geste-sans-recalculer-londe) |
| Un pont entre l'écran Texte et les tables de données, créer un dialogue sans tout renseigner à la main | 2026-10-10 | **À ouvrir**, besoin posé, pistes A (Texte → table) et B (« Nouveau texte » dans la cellule) **retenues**, le reste non verrouillé, code non commencé ; le dialogue reste une table de données (pas d'éditeur de dialogue). Voir [ci-dessous](#un-pont-entre-lécran-texte-et-les-tables-de-données-créer-un-dialogue) |
| La chaîne `if/elseif` sur une constante devient un `switch` C | 2026-10-06 | Route vers v1.0-stable, non prioritaire pour l'alpha ; piste de réflexion, **rien de verrouillé**, code non commencé, gain de perf non mesuré. Voir [ci-dessous](#chantier-transverse-la-chaîne-ifelseif-sur-une-constante-devient-un-switch-c) |
| Les prefabs, l'instance garde ce qu'elle surcharge, le reste suit le prefab | 2026-10-13 | **À ouvrir**, modèle décidé par l'auteur (surcharges par champ), **dix points à trancher** avant d'ouvrir (unité d'une surcharge, structure, sens d'Expose, migration, enfants…), priorité **non arbitrée**, code non commencé. Règle le cas « prefab » de la fluidité des réglages (un seul fichier écrit). Voir [ci-dessous](#les-prefabs-linstance-garde-ce-quelle-surcharge-le-reste-suit-le-prefab) |
| L'élément d'interface appartient à sa scène, des noms locaux | 2026-10-03 | À ouvrir, priorité non arbitrée ; conception proposée, **aucune décision verrouillée**, code non commencé. Garde-fou en place : un nom en double entre deux layouts est une erreur de build. Voir [ci-dessous](#lélément-dinterface-appartient-à-sa-scène-des-noms-locaux) |
| Tout ce que l'auteur manipule vit dans `assets/` | 2026-10-10 | **En cours**, scènes, prefabs, mises en page, boîtes sonores, tables de données, polices logiques, textes, variables : de `project/` vers `assets/`. Voir [ci-dessous](#tout-ce-que-lauteur-manipule-vit-dans-assets) |
| Une seule règle de nom libre | 2026-10-09 | **En cours**, huit règles de suffixe coexistent (`_2`, `_02`, `_copy`, `_1`, `Camera 2`, `axis1`, `Actor_0`, `Palette 2`) ; toutes passent à `coin`, `coin_2`, `coin_3`. Voir [ci-dessous](#une-seule-règle-de-nom-libre) |
| Source ≠ asset, l'arborescence du disque et l'id stable | 2026-10-09 | **Livré pour l'essentiel (2026-10-11)**, ids dans tous les sidecars, extension par type d'asset, assets et sources rangés où l'on veut sous `assets/` (fonds, palettes, scripts compris), onglet Disk (glisser-déposer, *Create asset*, suppression annulable, détachement complet source ≠ asset) ; **reste** : dossiers virtuels des autres finders (**Sound finder livré le 2026-10-11** : effets, musiques et jingles, dans le store partagé de la session ; sprites, fonds, palettes, tables, polices et prefabs restent à plat), références par id, associations de fichiers (installateur, zip portable, AppImage). Voir [ci-dessous](#source--asset-larborescence-du-disque-et-lid-stable) |
| Créer un asset : deux gestes, aucun dossier titulaire | 2026-10-19 | **À ouvrir**, principe demandé par l'auteur (*Create from source* et *Create blank*, plus de dossier de famille), contrat proposé, **tranches 1 (`PaletteStore`) et 2 (les deux commandes, onglet Disk) livrées le 2026-10-19**, reste les autres appelants et le retrait des `*_dir`. Voir [ci-dessous](#créer-un-asset--deux-gestes-aucun-dossier-titulaire) |
| Finder et Disk, « Asset library » et « Project files » | 2026-10-14 | **À ouvrir**, renommage décidé (asset finder → asset library, dossier de l'auteur → Project files), **quatre points à trancher** (nom affiché ou dossier sur disque, périmètre de « library »), code non commencé. Voir [ci-dessous](#finder-et-disk--asset-library--et--project-files-) |
| La compression d'un fond se joue, elle ne s'attend pas | 2026-10-14 | **À ouvrir**, analyse du parcours faite (lecture du code, rien mesuré à l'usage), sept frictions relevées, direction non arbitrée entre feedback en direct, perception de la perte et réglage par objectif ; code non commencé. Voir [ci-dessous](#la-compression-dun-fond-se-joue-elle-ne-sattend-pas) |
| Le fond est un plan de travail, canvas, image posée, comparaison source/compressé | 2026-10-15 | **À ouvrir**, modèle décidé par l'auteur le 2026-10-15 (canvas-size distinct de l'image, image déplaçable qui peut déborder, barre source/compressé, une seule image visible), **six points à vérifier ou trancher** avant de coder (palette indexée préservée, limites du canvas tuilé, miroir dans le canvas, types UI/animé, peintures par tuile), code non commencé. Remplace la piste « un seul espace » de la compression. Voir [ci-dessous](#le-fond-est-un-plan-de-travail-canvas-image-posée-comparaison-sourcecompressé) |
| Briques de base et assemblages, `Text` (chaîne) et `Textbox` (boîte), écrits directement dans le canvas | 2026-10-14 | **Livré pour l'essentiel (2026-10-14)**, deux types de texte, menu d'ajout en deux familles, `Text` posé en un point et édité sur place avec un curseur clignotant ; **reste** : emprise d'une chaîne qui suit son contenu, sélection non dessinée, vérification à la main et build ROM. Voir [ci-dessous](#briques-de-base-et-assemblages-text-chaîne-et-textbox-boîte) |
| TextBox, plusieurs entrées pour préparer un dialogue | 2026-10-17 | **Livré pour l’essentiel (2026-10-17)**, pages éditables, aperçu, références et build multi-page, export/mise à jour de Data Table annulables ; **reste** : nommage des layouts partagés, suivi des noms scène/objet, duplication des textes et déplacement des blocs. Voir [ci-dessous](#textbox-plusieurs-entrées-pour-préparer-un-dialogue) |
| Écran Texte, suites liées aux TextBox et aux tables | 2026-10-17 | **Link/Relink, Apply et +/− livrés**, édition structurelle sur les blocs, état précis et synchronisation fixés en bas. Reste l'export autonome des suites sans TextBox. Voir [ci-dessous](#écran-texte-suites-liées-aux-textbox-et-aux-tables) |
| La fiabilité du journal de build | 2026-10-03 | **Tranche 1 livrée le 2026-10-03** (aucune erreur avalée, tout script vérifié, fautes injectées) ; **tranche 2 livrée le 2026-10-03** (diagnostic unique, `build.log`, sortie des outils classée) ; reste ouvert : les codes stables, si le besoin apparaît. Voir [ci-dessous](#la-fiabilité-du-journal-de-build) |

---

## L'écran Données (une grille de jeu, pas un tableur)

### Le problème (2026-10-14)

L'écran a la bonne sémantique : une table est typée, ses références sont contrôlées,
et son rang est l'index que lit `data.Table[i]`. En revanche, ses gestes essentiels restent
peu découvrables : renommer une colonne demande un double-clic, modifier sa structure ou
une ligne passe principalement par le clic droit, et l'écran ne rappelle pas assez ce que
déplacer une ligne implique pour le script.

Le but n'est donc pas de fabriquer un tableur. Un tri ou un filtre donnerait à voir un ordre
différent de celui que le runtime indexe ; des formules changeraient la nature de cette donnée
`const` en ROM. Le but est une grille compacte qui permet de créer et corriger rapidement des
données de jeu, tout en rendant leurs contraintes explicites.

### Livré (2026-10-17)

- **Présentation de la grille.** Nom de table, résumé lignes/colonnes et indexation à partir de 1,
  barre « + Ligne / Dupliquer / Supprimer / + Colonne », en-têtes compacts avec badges de type
  colorés, alternance discrète des lignes et sélection continue avec repère de cellule active.
  Les insertions/suppressions au milieu annoncent le décalage des indices Lua.
- **Couleurs de colonnes.** Le clic droit sur un en-tête reprend les pastilles du menu des
  dossiers : cinq couleurs et une croix pour revenir au rendu neutre. La couleur habille
  l'en-tête, est enregistrée dans le fichier `.table` et passe par Annuler/Rétablir ; elle ne
  change ni les valeurs ni leur émission en ROM. Le widget est partagé avec le menu Disk.
- **Références graphiques explicites.** Les types proposés comprennent `sprite` et `background`,
  chacun alimenté par son catalogue d'assets ; les cellules suivent le renommage de l'asset.
  `image` n'est plus proposé : il désignait un élément d'interface, pas un asset. Les anciennes
  colonnes de ce type restent lisibles, sans conversion automatique vers une autre référence.
- **Sélecteurs d'assets filtrables.** Les cellules de référence ouvrent le popup partagé
  `ScriptPickerPopup` : recherche, icônes et aperçu des palettes, avec un choix « Aucun ».
  Choisir écrit par l'historique de la grille ; fermer ou appuyer sur Échap conserve la valeur,
  même si sa cible n'existe plus. Un popup ouvert avant un rechargement ne peut pas écrire
  dans la nouvelle table. Le filtre porte uniquement sur les choix d'assets, jamais sur les lignes.

**Vérification.** Tests ciblés de grille, de couleurs (widget partagé, persistance, annulation),
de références graphiques (catalogues, validation, génération et renommage) et de sélecteur
(filtre, choix, effacement, fermeture et rechargement). Rendu contrôlé, ouverture clavier et
Échap vérifiés ; l'usage prolongé sur une table de jeu dense reste à valider.

### Direction retenue et suite

1. **La table dit ce qu'elle est.** L'en-tête central porte le nom, le nombre de lignes et de
   colonnes, et rappelle que les rangs commencent à 1. Chaque en-tête de colonne affiche un
   badge discret de type (`int`, `bool`, `text`…).
2. **Les gestes qui changent la structure sont visibles.** Une barre compacte propose
   « + Ligne », « Dupliquer », « Supprimer » et « + Colonne ». Le menu contextuel reste un
   raccourci, pas le seul moyen de découvrir ces actions.
3. **L'ordre est annoncé là où il compte.** Insérer ou supprimer une ligne hors de la fin
   avertit que les indices utilisés par les scripts seront décalés. Le rang reste visible à
   gauche et ne devient jamais un identifiant artificiel.
4. **La référence reste une valeur contrôlée.** La grille continue à montrer la clé, et le
   panneau droit montre ce qu'elle désigne. Il peut proposer « Ouvrir le texte » ou l'asset
   correspondant, sans dupliquer son éditeur dans cet écran.
5. **La saisie en série est le prochain seuil utile.** Copier/coller TSV, sélection de plage,
   `Suppr` pour vider une cellule ou une sélection et duplication de ligne apportent un vrai
   gain dès qu'une table dépasse quelques lignes. Les cellules restent validées par leur type.

### À ne pas faire

- Ni tri, ni filtre des lignes : l'ordre affiché doit toujours être l'ordre réel des index Lua.
  Le filtre du sélecteur de références ne change pas cet ordre.
- Ni formules, ni calculs de feuille : les tables sont des données authorées, lues en ROM.
- Ni panneau droit transformé en second éditeur : il explique et mène à la ressource citée ;
  l'écriture passe toujours par la grille et son historique unique.

### Points restant à vérifier

1. **La confirmation de décalage.** La montrer à chaque insertion/suppression au milieu serait
   sûre mais possiblement pénible ; une option « ne plus demander pour cette session » peut
   concilier les deux. À tester sur une table réellement citée par des scripts.
2. **Le collage.** Définir le comportement face à une référence inconnue, à une cellule hors
   plage, ou à une valeur entière invalide : prévisualisation, refus atomique, ou collage
   partiel. La sûreté des données doit primer sur la commodité.
3. **La place de l'inspecteur.** Le réduire et le garder repliable est probablement plus utile
   que le supprimer ; à confirmer avec une référence textuelle longue et une table dense.
4. **Le message de changement de type.** L'interface doit dire la vérité : les valeurs de la
   colonne sont effacées (et restaurables par Annuler), elles ne sont pas converties.

### Références graphiques : la ROM ne les consomme pas encore (constaté le 2026-10-18)

**Le besoin (auteur).** Lier une donnée à un élément visuel, portraits affichés dans un dialogue, tables de monstres.
Ce que le script en fait reste le choix de l'auteur du jeu.

**Ce qui est vrai aujourd'hui.** Une colonne `sprite` ou `background` est une référence d'éditeur complète (choix filtrable,
renommage suivi, validation). En ROM, la cellule vaut la position de l'asset dans la liste du projet
(`reference_index` dans `data_tables.py`), et **rien ne la lit** : aucune table de ROM, aucune fonction de script. Les assets
que seules les tables citent ne sont pas chargés en VRAM. Une cellule vide vaut 0, comme pour les autres références.

**Décision (2026-10-18) : on s'arrête là pour la ROM.** Ni catalogue, ni API, ni code runtime tant que la consommation n'est
pas tranchée : ce n'est pas un choix à prendre à la légère. La table reste l'outil d'authoring.

**Pistes relevées, rien de verrouillé.** Le moteur sait déjà copier depuis la ROM vers un bloc VRAM réservé (`BgTileAnim`,
frames d'un sprite contiguës par direction, `UIImageInfo` pour les images d'interface). Un « emplacement » réservé, rempli à la
demande depuis un catalogue ROM des seuls assets cités, couvrirait portrait (sprite ou image d'interface) et fond. Questions
ouvertes à trancher avant d'y toucher : (1) emplacement chargé à la demande ou assets tous résidents ; (2) animation chargée
en entier ou première frame seulement ; (3) candidats de tailles différentes, rognés avec avertissement ou refusés ; (4) un
fond se copie écran éteint (jusqu'à 32 Ko de tuiles), donc une transition ; (5) budget VRAM et palettes signalés par un
avertissement, sans bloquer.

### Prochaines étapes

1. Valider les gestes sur une vraie table de jeu, la place de l'inspecteur et le message de
   changement de type : il doit annoncer l'effacement des valeurs, restaurables par Annuler.
2. Sélection de plage, copier/coller TSV et suppression clavier, avec tests de validation.
3. Navigation vers la ressource référencée, puis recherche / « aller à la ligne » si les
   tables de projet en justifient le besoin.

---

## L'écran Son montre le geste sans recalculer l'onde

### D'où vient la question (2026-10-12)

L'onde de l'écran Son doit suivre **en direct** ce qui se règle (volume, tempo, hauteur), et nous butions sur le
rendu Qt. Le chantier a d'abord cherché à rendre l'onde plus vite, puis a changé de question : l'onde est-elle la bonne chose
à recalculer ?

### Ce qui a été mesuré (démo PongAdvanced, 2026-10-12)

| Mesure | Résultat |
| --- | --- |
| Rendu complet d'un module (`render_track`) | 0,15 à 0,7 s ; **plancher ≈ 0,5 s**, indépendant du taux (554 / 491 / 458 ms à 13,4 / 6,7 / 3,3 kHz) : c'est la boucle Python par tick (4488 ticks pour 75 s), pas le mixage |
| `peak_envelope` | 10 à 40 ms |
| Repeinture complète de l'onde (1400 px, boucle) | 42 ms → **19 ms** (28 → 11 ms à 700 px) une fois le remplissage fait en numpy |
| Enveloppe rendue au tempo ×0,8 à ×1,5, comparée à l'enveloppe de base étirée | 0,1 à 3,7 % d'écart, corrélation ≥ 0,967 ; durée exactement `durée / tempo` |
| Enveloppe rendue à la hauteur ×0,8 et ×1,25 | 0,1 à 3,2 % d'écart ; durée inchangée |
| Attente d'un thread concurrent pendant un rendu (le thread audio tire le deck en Python) | jusqu'à **44 ms** (p95 22 ms) pour un tampon audio de 50 ms ; **2,7 ms** avec `sys.setswitchinterval(0,2 ms)`, sans ralentir le rendu |

Conséquence : l'enveloppe ne change presque pas avec le tempo (la frise tient la largeur : seule la règle se regradue) ni avec la
hauteur (un pixel vaut 50 ms : une hauteur ne s'y voit pas). Recalculer l'onde pendant un glisser courait après une différence
invisible, et un rendu complet ne pouvait de toute façon pas rafraîchir l'écran plus de deux fois par seconde.

### Ce qui a été essayé, puis retiré

- **Throttle, annulation et rendu progressif** : le minuteur de rendu devenu un throttle, un rendu qui s'annule en route
  (`RenderCancelled`, point de contrôle tous les 32 ticks), un début de rendu affiché à la place du début de l'onde, la suite en
  retrait. Cela a révélé un défaut plus ancien : un rendu terminé était **jeté** dès qu'une demande plus récente existait, donc
  aucune onde complète ne s'affichait pendant un glisser. Corrigé, puis l'ensemble a été jugé insatisfaisant : le plancher de
  0,5 s restait. L'affichage progressif a été **retiré** ; le point de contrôle annulable et le correctif GIL restent.
- **Vue « Notes »** (un trait par canal, hauteur de la note, décalée par le réglage de hauteur) : essayée, **non convaincante**,
  retirée avec `ChannelLevels.semitones` et ses tests.

### Ce qui est livré

- **Aucun rendu tant que la main tient un potard.** L'onde (gain) et la règle (tempo) suivent sans rendu ; un rendu exact part au
  repos pour la frise de scrub du deck, et il est abandonné si la main reprend (`_schedule_retune`, `_retune`).
- **Bascule Onde \| Scope** au bout de la règle : un oscilloscope du mix, les 30 dernières ms que le lecteur fait entendre
  (`_DeckDevice.tail` → `_AudioOutput.heard_window` → `BoxPlayer.scope_window`), décalées de l'avance du deck sur la carte son,
  avec déclenchement sur un passage montant par zéro. Il suit donc le tempo, la hauteur et le volume **à chaque cran**. À
  l'arrêt : une fenêtre fixe du rendu à la poignée de départ. Dans le scope, la frise (bandes, boucle, fondus, poignées) et le
  glisser horizontal sont désactivés.
- **Durée totale** lue au bout de la règle, à l'accent quand le tempo la change.
- **Corps de l'onde en numpy** (image à couverture fractionnaire au lieu d'un polygone rempli) : 2,2 à 2,6 fois plus rapide,
  même rendu à l'œil.
- **Barres des canaux** : elles multiplient le pic du rendu par le volume de la musique (le lecteur l'applique en jouant ; le rendu
  ne le contient pas), donc elles rétrécissent quand le volume baisse (`ChannelMeters.set_gain`, `MusicEditor._show_mix`).
- **Tests ajoutés** : `tests/audio/test_render_checkpoint.py`, `tests/ui/test_waveform_scope.py` (scope, tampon du lecteur, worker
  annulé, glisser sans rendu puis un seul au relâchement, rendu abandonné par un cran, barres et volume).

### Ce que la mesure du mix a appris (2026-10-12, aucun code)

Les barres de canaux affichent le **pic** d'échantillon : elles collent en haut dès qu'un canal joue au volume par défaut (73 % des
ticks de `bs-p2-dungeon`, 8 % de `bs-p2-greenhatwake`). Ce n'est pas un défaut : un module chiptune est fait d'ondes carrées, dont
le pic et le niveau efficace (RMS) sont identiques (rapport 1,00 sur la plupart des canaux ; 0,49 à 0,71 seulement sur le bruit et
le triangle). Passer les barres en RMS ne les ferait donc pas bouger.

Pour la saturation, la **somme des pics** des canaux (à l'échelle de `to_stereo16`) ne manque aucune saturation sur les deux modules
qui saturent (100 % des ticks saturés signalés) mais donne des fausses alertes (7 % sur `dungeon`, 61 % sur `mblaster`, 21 % des ticks
de `1-u` qui ne sature jamais). La racine de la somme des RMS² ne prédit pas mieux le pic du mix (corrélation 0,82 / 0,93 / 0,92 / 0,87
contre 0,75 / 0,92 / 0,94 / 0,95). Le mix émulé de `dungeon` sature réellement (26,9 % des échantillons), celui de `mblaster` à
2,9 %.

### Ouvert

- **Des repères sonores sur la musique, LIVRÉS (2026-10-14)**, quatre natures. Un repère est un drapeau posé sur la voie
  au-dessus des sections de la barre de structure ; la lecture le joue **à chaque passage** (chaque tour de boucle le rejoue).
  - **Natures** : action de SoundBox, action de JingleBox, effet direct, jingle direct (`MusicCue`, `Music.cues`, dans l'unité de
    la musique : ordre pour un module, ms pour un WAV). Geste : clic droit sur la voie (menu inline comme celui d'une frame de
    sprite, un sous-menu par nature), glisser pour déplacer, clic droit sur un drapeau pour le changer ou le supprimer.
  - **Build** : `music_cue_tick()` en C, une fois par frame après `music_loop_tick`, observe `mmGetPosition()` et joue la ligne de
    `g_music_cue` (résolue au build : index d'action, constante d'effet ou de jingle, volume). Un WAV est recoupé à chaque repère
    (`wav_boundaries`) pour qu'il tombe à la ligne près. Un effet ou jingle cité **seulement** par un repère entre en ROM
    (`referenced_sound_names`, source ⑥).
  - **Aperçu** : le deck mixe les sons de repère par-dessus la musique, au bon échantillon (`MusicDeck.set_cues`), avec les
    mêmes positions que la ROM (`music_cue_rows`). La tête de lecture traverse la barre de structure et avance en continu dans
    sa case : sur l'onde (échelle du temps) et sur la barre (échelle des ordres), un même instant n'est pas au même x, ce qui
    donnait une impression de décalage à l'écoute.
  - **Validateur** : cible inconnue, position hors fichier (erreur), repère sur un séparateur de la table d'ordres, repère
    sans cible (avertissements). Un jingle ignore ses repères (signalé).
  - **Canaux** : le plafond de la courbe de polyphonie retranche 1 canal si la musique a un repère d'effet, 4 si elle a un repère de
    jingle. **Majorant NON MESURÉ** : on ne sait pas quels repères se recouvrent, ni si les 4 canaux de la couche jingle
    se prennent bien sur le même pool que les effets. À mesurer sur ROM.
  - **Non prouvé sur console** : que le son parte au bon pas (le C compile et la table est la bonne : `tests/rom_build/test_music_cues_build.py`).
    La politique d'un jingle envers la musique (duck, pause) ne s'écoute pas à l'aperçu ; les repères ne sont posés dans
    l'aperçu MusicBox qu'au démarrage d'un état, pas après un fondu.
- **Reste ouvert, l'appel d'événement.** Une frame de sprite appelle une fonction du script de l'acteur ; une musique n'a pas
  d'acteur. Ni « fonction du script de la scène » ni « callback global » n'est retenu : nous avons posé la question d'un
  **signal** (diffusé, reçu par tout script abonné). Le moteur n'a aucun bus de signaux (vérifié) : ce serait un mécanisme nouveau,
  à poser une fois pour tous les usages (musique, frames, collisions), **jalon à part, à décider**.
- **Repères de jingle, LIVRÉS (2026-10-14, tranche 1)**, en **temps**. maxmod n'offre aucune lecture de position sur la couche
  jingle (`mmGetPosition`/`Row`/`Tick` ne lisent que la principale ; seule `mmActiveSub()` dit s'il joue encore, vérifié dans
  `maxmod.h`) : la ROM **compte les images** depuis `mmJingle` (`g_jingle_frame`, remis à zéro par chaque `music_jingle`) et
  `music_cue_jingle_tick()` joue la ligne de `g_jingle_cue` dont l'image est atteinte.
  - **Toujours en millisecondes, module ou WAV.** Mesuré sur la démo : **13 jingles sur 19 n'ont qu'un seul ordre** ; un repère par
    ordre n'aurait pu viser que leur début. Conséquence : aucun rendu au build (`ms → images` est un produit :
    `jingle_cue_frames`), donc pas de coût. Les 19 jingles de la démo se rendent en 26 à 319 ms chacun (1,5 s au total) : c'est
    ce que la piste « ordres » aurait coûté, et elle est abandonnée.
  - **Cadence** : 16 777 216 / 280 896 = **59,7275 images/s** (`VBLANK_HZ`), pas 60. Le deck de l'aperçu tourne à 60 par commodité
    (écart ~45 ms sur 10 s), **non corrigé, à mesurer** (tranche 2).
  - **Ce qu'un jingle peut lancer** : un effet ou une action de SoundBox (`JINGLE_CUE_KINDS`). Pas un autre jingle : il
    remplacerait celui qui sonne (avertissement du validateur, pas de ligne en ROM).
  - **Éditeur** : la bande d'un jingle montre une cellule en ms avec la voie des repères, sans sections ; le menu ne propose que
    les deux natures permises. **Aperçu** : un jingle joué seul, ou lancé par un repère de musique, emporte ses repères comme des
    voix à retard (`MusicDeck.start_voices`).
  - **Non prouvé** : la dérive du compteur d'images contre l'audio réel de maxmod (mesure sur ROM ou mGBA à faire, comme pour
    les sections) ; le tir d'un repère à l'image 0 tombe à la frame suivant `music_jingle`.
- **Reste ouvert, des points de sortie pour les music box** : des endroits d'une musique où la boîte peut la quitter. À décider :
  leur définition (une position posée à la main, ou les débuts d'ordre que la frise connaît déjà) ; leur rapport avec la coupe
  à la position qui existe déjà dans les boîtes (`TRANSITION_CUT`, les repères d'ordre du `Track`) ; ce que la boîte fait
  quand une sortie est demandée entre deux points. La voie des repères est un emplacement naturel pour les poser.
- **Un indicateur de marge du mix** : une jauge, la somme des pics par rapport au seuil de saturation, à côté des barres (niveaux
  déjà capturés dans `ChannelLevels`, aucun nouveau calcul moteur). Proposé, **non décidé**.
- **Un scope par canal** : le scope du mix devient du bruit sur un morceau dense ; il demanderait de capturer les échantillons de
  chaque canal dans le moteur, avec une option pour ne pas ralentir le rendu complet.
- **À juger à l'usage** : la lisibilité du scope sur un morceau dense, et la place de la bascule au bout de la règle.
- **Limite assumée** : le scope ne bouge que pendant la lecture ; à l'arrêt, l'effet d'une hauteur n'apparaît qu'au rendu exact, environ
  0,6 s après le lâcher.
- **Non mesuré** : si la console sature comme `to_stereo16` (échelle 190 × 128) le fait. Les taux de saturation ci-dessus sont ceux de
  l'émulation de l'éditeur, sur quatre modules d'un seul projet.
- **Plancher du rendu** : 0,5 s par rendu complet reste vrai ; l'abaisser demanderait un moteur plus rapide (les tests d'équivalence
  avec la ROM en dépendent) ou un rendu par morceaux (l'état du module se propage d'un tick à l'autre).

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

### Tranche 1 (aucun silence (livrée le 2026-10-03))

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

Livré : `tests/scripting/test_silent_except.py` (la garde, 23 handlers annotés `# tolerated:` avec leur raison),
`_check_scripts_parse` dans `core/validator.py` (qui absorbe la lecture des behaviors de
`_check_behaviors_without_self`), `tests/rom_build/test_build_fault_injection.py` (sept cas, dont un projet sain
comme témoin ; désactiver le contrôle en fait échouer cinq). Ajouté le même jour : un prefab qu'aucune scène ne
déclare n'était que parsé ; `lua_compiler` le fait maintenant passer par le checker (une fois, par la
première scène), donc une faute sémantique sort avant qu'une scène ne le déclare. Un script attaché à
rien reste vérifié pour sa seule syntaxe : sans propriétaire, il n'a pas de contexte (`self`, événements)
contre lequel être jugé.

### Tranche 2 (un seul diagnostic, un journal conservé (livrée le 2026-10-03))

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

Livré : `tests/rom_build/test_build_diagnostics.py` (douze cas : l'objet, le classement de la sortie des outils, le
verdict, `build.log` réécrit) et trois cas d'interface dans `tests/ui/test_diagnostics_panel.py`. Un build
réel de la démo `PongAdvanced` (17 s) donne `[build] 0 error(s), 1 warning(s)` et un `build.log` de 19 Ko.
Mécanique décrite dans ARCHITECTURE.md, « Le journal de build ».

**Suite (2026-10-03), gcc cite le script.** Pas de table de correspondance : le générateur pose
`#line N "Script.lua"` avant chaque statement (la ligne vient du parseur, `Stmt*.line`) et rend gcc à son
`.c` en fin de corps de fonction, avec le numéro calculé sur le texte final. Une erreur de gcc sur le C
émis sort donc comme un diagnostic `Script.lua:N`, cliquable. Un behavior inliné porte ses propres
lignes. Le C d'un appelant sans nom de script (tests unitaires) reste sans directive. Vérifié par un vrai
gcc (`tests/rom_build/test_gcc_cites_the_script.py`) et par la démo, dont la ROM garde sa taille.

Ce que ça ne fait pas : un réglage « avertissements = erreurs ».

### Tranche 3 (la couverture, mesurée (livrée le 2026-10-03))

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



### Tranche 4 (la couverture, tenue (livrée le 2026-10-03))

La matrice de la tranche 3 était un script jetable de 31 cas écrits à la main. Mesurée (274 sites qui
peuvent émettre un diagnostic, comptés dans le code puis comparés à ceux qui se déclenchent
réellement) : la matrice en atteint 28 (10 %), la suite entière 97, les deux réunis 107 (39 %). Les 167
autres ne se déclenchent jamais : audio, tables de données, caméras, budgets, vecteurs et tableaux du
checker, conversion grit.

1. **Des invariants testés en masse.** `tests/rom_build/test_build_invariants.py` corrompt un à un des fichiers de
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

**Isolés le 2026-10-04.** `test_build_fault_injection.py`, `test_build_diagnostics.py`, `test_build_invariants.py`, `test_gcc_cites_the_script.py`, `test_smoke_test.py` et un cas de `test_codegen_diagnostics.py` compilent un projet entier par cas : lancés à chaque modification, la suite durait ~20 min. Ils portent le marqueur `slow`, exclu par défaut (`addopts` de `pyproject.toml`) ; `pytest -m slow` les lance, et le job `slow-tests` de `release.yml` les exige avant toute publication.

### Tranche 5 (les 175 sites jamais atteints (livrée le 2026-10-03, réduite le 2026-10-04))

Les 175 sites ont d'abord tous été exercés : 274 sur 278. C'était un compteur satisfait, pas une
garantie : ces ~170 tests vérifiaient qu'un fragment de message sort, pas qu'il est juste, et ne m'ont
trouvé que trois vrais défauts (deux libellés restés en français, un faux « site » dans l'outil de
couverture). Ils ont été **réduits à un échantillon de 52 tests** qui portent une vraie logique :
l'accord de listes internes (api.py ↔ en-têtes du runtime, lua_subset ↔ luaparser, domaines, colonnes),
les budgets (palettes, fenêtres, structure de musique), les promesses que l'éditeur fait sans que le
build les tienne, les pannes de lecture, et un cas par famille de faute du checker. Trois fichiers :
`tests/scripting/test_checker_diagnostics.py`, `tests/scripting/test_validator_diagnostics.py`,
`tests/rom_build/test_codegen_diagnostics.py`.

La référence est relevée à **172 sites exercés sur 278** (103 avant la tranche). Ce n'est pas un objectif
à remonter : le cliquet avertit d'un site couvert qui ne l'est plus, il ne demande pas de tout couvrir.

Corrigé en chemin : trois messages restés en français ; l'outil de couverture comptait à tort les appels à
une fonction locale `_warn` ; et le déplacement de `ValidationMessage`, `build_error` et `build_warning`
vers `core/diagnostic.py`, module de base, pour fermer la boucle d'import que l'unification des
diagnostics avait ouverte entre `core.validator` et les générateurs (que `check_architecture` signalait).

Trouvé en chemin : deux messages restés en français (`frame_w/h invalides`, `l'image`, et deux libellés
d'audio), corrigés ; et l'outil de couverture comptait à tort les appels à une fonction locale `_warn` comme
des sites, un conduit, désormais ignoré.

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
- **Boîtes de collision** : ~~adressées par leur tag, en requêtes indexées~~, **rouvert le
  2026-09-24**, voir [l'amendement ci-dessous](#amendement-2026-09-24-la-boîte-de-collision-devient-une-référence-typée).
  La forme initiale (`self:box_rect("hitbox")`, `self:set_box_solid(...)`) avait écarté l'idée
  `self:box("tag").w` parce qu'une propriété sur une boîte exige un TYPE de référence dans le
  checker et le codegen. Ce coût est maintenant accepté : la boîte est un composant à part entière
  (id, tag, active, solid, offset, size), elle mérite son propre objet et son propre module.
- **Interface** : décision remplacée par l'amendement v0.16 du 2026-09-25 : le singleton
  `interface` acquiert un élément typé (`interface:get("Nom")`) ; l'élément porte ses
  propriétés et méthodes. Les fonctions qui recevaient un nom d'élément en premier argument
  migrent avec la surface décrite dans « Interface, singleton et éléments typés ».

### Amendement (2026-09-24) (la boîte de collision devient une référence typée)

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
| `self:collision_box(tag)` | constructeur de référence, `nil` possible | s.o. |
| `hb.tag` | lecture seule | la clé des anciens appels |
| `hb.active` | lecture seule, **champ à créer au runtime**, écrit par `hb:activate()` / `hb:deactivate()` (cycle de vie en cinq verbes, 2026-09-25) : la résolution contre la carte et le test de chevauchement doivent l'ignorer quand il est faux | (aucune porte) |
| `hb.solid` | modifiable | `self:box_solid` / `self:set_box_solid` |
| `hb.offset`, `hb.size` | modifiables, bornés (offset −128..127, taille 0..255) | `self:box_rect` / `self:set_box_rect` |
| `hb.bounds` | lecture seule, rect monde | le calcul que chaque script refaisait |
| `hb:overlaps(other)` | méthode, bool | s.o. |
| `hb.is_grounded` | lecture seule, bool | (aucune porte par boîte), `self.grounded` reste, et en est le OU |
| `hb:get_collision_tile(x, y)` | méthode, requête indexée (point monde ABSOLU) | `tile.get` (la carte lue est la carte de collision ; le verbe `get` est juste ici : le tile n'est pas un champ de la boîte) |
| `self.box_count` | lecture seule, inchangée | s.o. |

`overlaps(other)` prend un acteur (« ma hitbox touche-t-elle N'IMPORTE QUELLE boîte de cet
acteur ? ») ou une autre boîte (« ... précisément sa hurtbox ? »), la même distinction que
`on_collide(other, my_box, other_box)`. `touches_tile` a été écartée : `hb:get_collision_tile` sur
`hb.bounds` fait la même chose sans nouvelle action. Le point de `get_collision_tile` est absolu : la
boîte sert de porte d'entrée (une boîte absente répond 0) mais ne relativise rien.

Ce que le chantier ajoute, hors renommage : des **propriétés sur une référence** (jusqu'ici une
référence n'a que des méthodes, comme `sfx` et les éléments d'interface). Le checker doit typer la lecture et
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
  comparait à des offsets en pixels, deux boîtes à 5 px ne se voyaient pas comme se chevauchant, donc
  `on_collide` / `on_collision_enter` ne se déclenchaient qu'à moins d'1/256 de pixel. Régression tenue
  par la sonde native (`overlap_5px`, `actors_overlap`).
- **La référence est un entier** (rang de l'acteur × `MAX_BOXES` + rang de la boîte + 1, 0 = absente),
  comme le handle d'un `sfx` : `if not hb` compile en `!hb`. Les propriétés d'une référence passent par
  `resolve_prop(expr, ref_types)`, sans jamais retomber sur les champs d'actor (`hb.tag` n'est pas
  `self.name`). Le renommage d'un tag suit aussi `hb.tag == "hitbox"` (`refactor._iter_prop_refs`).
- **Vérifié** : sonde native (`actor_box_probe.c`), `test_inspector_api_parity.py`, et un build ROM complet
  sur une copie d'OrbitTest (deux boîtes sur la tourelle dont une inactive au départ, une sur Moon, script
  utilisant toute l'API), `rom.gba` produite.

### Tranche 1 (acteur, sprite, collision)

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
`tests/scripting/test_inspector_api_parity.py`, un build ROM complet sur une copie d'OrbitTest (boîte « hitbox » 
ajoutée à la tourelle, script utilisant les sept portes). Le renommage d'un tag de collision 
(`RenameCollisionTagCmd`) réécrit maintenant aussi les scripts.

**Tranche 1 close (2026-09-29), vérifiée contre l'API et les règles posées depuis.** Restent sans porte, et c'est
décidé : `parent`, la parenté est authorée et jamais assignée au runtime (v0.23), donc seule une LECTURE SEULE
aurait un sens, et elle coûte un champ par acteur (un prefab posé N fois a N parents), au rebours de la struct
`Actor` allégée ; repoussé, à rouvrir sur besoin réel. `sprite_name`, `self.active_sprite` rend l'id du composant,
pas l'asset ; la question « comment nomme-t-on l'accès à un sous-objet de l'instance ? » est déjà ouverte, en route
vers v1.0-stable ([ci-dessous](#chantier-transverse-nommer-laccès-à-un-sous-objet-de-linstance)), et la trancher
ici la trancherait deux fois. `initial_state` et `prefab_name` n'ont pas besoin de porte : `self.anim` et
`self.name` couvrent l'usage.

### Tranche 2 (caméra, scène, calque de fond (livrée le 2026-09-30))

Classement fait en lisant le runtime C (`runtime_api_inline.h`, `gba_engine.h`) et le codegen : ce qui est un
**littéral dans le C émis** est fixé au build (lecture seule) ; ce qui vit déjà en registre ou en RAM, ou coûte un
octet de RAM pour le devenir, est modifiable. Les portes déjà là (`camera.position`, `camera.bound`, `layer.visible`,
`layer.priority`, `layer.scroll`, `layer.map`, `scene.size`) ne sont pas répétées.

| Champ d'inspecteur | Porte Lua proposée | Nature | Raison (ce que le C fait aujourd'hui) |
| --- | --- | --- | --- |
| Camera `mode` | s.o. | repoussé | changer de mode et de cible en jeu est voulu, avec une transition : chantier [« La caméra change de cible »](#chantier-transverse-la-caméra-change-de-cible-en-jeu-avec-une-transition) (route vers v1.0-stable). Aucune porte partielle d'ici là : le suivi est un `switch` dont les cas sont émis seulement pour les caméras à cible |
| Camera `follow_target` | s.o. | repoussé | même chantier que `mode` |
| Camera `margin_x/y` | `camera.margin` (vec2) | **modifiable** | deux littéraux du `switch` → deux octets de RAM lus par `camera_follow` |
| Camera `frame_w/h` | `camera.frame` (vec2) | **modifiable** | pilote WIN0 (`window_set(0, …)`), qui existe déjà ; un getter du rectangle de WIN0 est à ajouter |
| Camera `name` | `camera.name` (comparable par son nom) | lecture seule | `DOMAIN_CAMERA` existe ; sert à savoir quelle caméra `camera:switch` a activée |
| Scene `scroll_h/v` | `scene.scroll_h`, `scene.scroll_v` (bool) | lecture seule | choisit `(g_actors[t].x>>8)` ou `cam_x` DANS le `switch` émis |
| Scene `blend_eva/evb/evy` | s.o. | repoussé | chantier [« L'API de blending »](#chantier-transverse-lapi-de-blending-des-calques-au-petit-oignon) (route vers v1.0-stable) : `blend.set_alpha` / `blend.set_fade` → propriétés, décidé avec le `mixer` qui pose la même question pour le son |
| Scene `blend_*_role` | s.o. | repoussé | même chantier [« L'API de blending »](#chantier-transverse-lapi-de-blending-des-calques-au-petit-oignon) |
| Scene `backdrop_color` | s.o. | repoussé | même chantier [« L'API de blending »](#chantier-transverse-lapi-de-blending-des-calques-au-petit-oignon) : la porte est voulue, lecture ET écriture, sans nouveau type (un `vec3` ou un entier RGB555, à trancher là-bas) |
| Scene `transition_kind/frames` | s.o. | repoussé | chevauche l'API de blending (la transition possède les registres de blending) : même chantier [« L'API de blending »](#chantier-transverse-lapi-de-blending-des-calques-au-petit-oignon) |
| Scene `collision_layer` | `scene.collision_layer` (int) | lecture seule | index BG fixé au build |
| Scene `render_mode` | **aucune** | s.o. | échafaudage non offert à l'auteur (règle « anticiper est permis, l'exposer non ») |
| Scene `music`, `script`, `notes` | s.o. | pas de porte | décidé le 2026-09-29 : `music` ne règle que la musique de DÉPART (le module `music` couvre l'état) ; `script`/`notes` ne sont pas de l'état |
| BackgroundLayer `scroll_speed` | `layer.scroll_speed` (pourcent, 100 = normal) | **modifiable** | littéral dans la ligne `BGOFS = (cam_x*speed)>>8 + …` → quatre entiers de RAM, un par fond |
| BackgroundLayer `pal_bank` | `layer.pal_bank` (int) | lecture seule (livré) | banque allouée au build |
| BackgroundLayer `background_name` | `layer.image` (comparable par son nom) | lecture seule | asset chargé au build |
| BackgroundLayer `bg_slot` | s.o. | sans objet | c'est la clé de la référence (`layer.get(n)`) |
| BackgroundLayer `visible` | s.o. | sans objet | visibilité du viewport ÉDITEUR seulement (le codegen ne la lit pas) |

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
  allume ou éteint WIN0, une seule porte vers la window de la caméra.
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
  portes), `rom.gba` produite, `main.c` inspecté.

---

## Le cache de scène (rouvrir une scène déjà visitée sans tout redécoder)

### D'où vient la question (2026-09-16)

L'auteur : sélectionner une scène dans le project viewer prend une demi-seconde perceptible, même
pour une scène triviale (title screen, deux zones de texte). Trois causes indépendantes trouvées
en investiguant `window._on_scene_selected` ([window.py:1128](editor/window.py:1128)) :

1. **Corrigé (2026-09-16).** `AssetsFinderPanel.refresh()` reconstruisait les 3 arbres (Scenes,
   Prefabs, Scripts) à chaque clic, alors que rien n'y change quand on change simplement de scène
   active. Remplacé par un simple surlignage de la scène active, sans repeuplement,
   `highlight_active_scene` ([assets_finder_panel.py](editor/ui/scene_manager/assets_finder_panel.py)),
   posé sur `AssetFinder.highlight_selection` déjà existant.
2. **Pas de bug.** `_refresh_diagnostics` → `validate_project` → `project.load_all_resources()`
   ([validator.py:126](editor/core/validator.py:126)) est déjà gardé par
   `_deferred_resource_collections` ([project.py:339](editor/core/project.py:339)) : le coût réel
   (stat + hash de tout le catalogue) n'est payé qu'à la toute première scène ouverte d'une
   session ; ensuite chaque `load_*` est un test d'ensemble vide, donc quasi gratuit.
3. **Ce chantier.** `SceneEditor.load_project` ([scene_canvas.py:721](editor/ui/scene_manager/scene_canvas.py:721))
   reconstruit le canvas ENTIER à chaque sélection, y compris en revenant sur une scène déjà
   visitée dans la même session, où rien n'a changé :
   - `compose_frame_image` ([sprite_compose.py:15](editor/core/sprite_compose.py:15)) rouvre et
     redécode depuis le disque le PNG source du sprite pour CHAQUE acteur, à CHAQUE visite,
     aucun cache, même quand le fichier n'a pas bougé depuis la visite précédente.
   - `bg_pixmap` / `BgLayerRaster.render` ([canvas_raster.py:171](editor/ui/scene_manager/canvas/canvas_raster.py:171))
     recompose le rendu tuile par tuile du fond à chaque visite. Le tileset lui-même est déjà en
     mémoire (`BackgroundAsset`, pas de disque ici), mais le raster complet est refait à zéro.
   - `_reload_ui_regions` / `set_ui_regions` ([canvas_scene.py:440](editor/ui/scene_manager/canvas/canvas_scene.py:440))
     détruit et recrée tous les items d'interface et recalcule les couleurs de banque
     (`_compute_bank_colors`, documenté à ~15 ms/région) à chaque visite.

### Ce qu'il faudrait trancher avant d'ouvrir

- **Quoi cacher, précisément.** Deux formes envisagées avec l'auteur, pas encore choisies :
  - un cache des **décodages disque** purs (PNG source des sprites/fonds), invalidé par mtime,
    la composition par frame/scène (flips, palette, overrides live) continue de tourner à chaque
    visite. Scope net, risque faible : rien ne peut devenir périmé, seul le pixel brut du fichier
    est mémorisé, jamais un résultat qui dépend de l'état vivant du projet.
  - un cache du **canvas complet par scène** (QGraphicsScene/items déjà construits), pour rouvrir
    une scène visitée sans rien recalculer, même pas le raster de palette/bank colors. Gain plus
    net, mais très invasif (`SceneEditor.load_project` en profondeur) et risque de
    désynchronisation si un asset ou une palette change pendant que la scène est en cache
    (édition d'un sprite ou d'une palette depuis un autre écran), demanderait une invalidation
    explicite, pas seulement un mtime.
- **Recouvrement avec CanvasRework.** Le chantier de refonte du canvas est en cours (`scene_graph`,
  `scene_graph_state`, non encore committés à l'ouverture de cette entrée) : ouvrir un cache de
  scène avant que cette refonte se stabilise risque de dupliquer le travail ou de mettre en cache
  un état que CanvasRework va remplacer. À revérifier au moment d'ouvrir.
- **Mesurer avant de trancher.** Aucune mesure chiffrée prise pour l'instant, seulement une lecture
  de code. Profiler `load_project` sur un projet réel donnerait la vraie proportion entre
  décodage sprite, raster de fond et reconstruction des régions UI, plutôt que de deviner laquelle
  des trois mérite le cache en premier.

---

## Undo/redo des sidecars d'éditeur (annuler la création d'un groupe, un déplacement de nœud)

### D'où vient la question (2026-09-16)

En revue du chantier « groupes du Graphe de scènes » (créer/supprimer/renommer un groupe, y ranger
des scènes, déplacer et redimensionner les boîtes, déplacer les nœuds), nous avons demandé de
vérifier que **toutes** les opérations introduites étaient reliées à undo/redo. Constat :

- **Reliée.** La *suppression de scène* (clic-droit du Graphe) pousse `DeleteResourceCmd` dans
  l'historique, exactement la commande du project viewer. C'est une vraie mutation de `Resource`.
- **Non reliées, et à dessein.** Tout le reste (créer / supprimer / renommer / colorer un groupe,
  ranger une scène (`move_member`), déplacer une carte, déplacer ou redimensionner un cadre)
  écrit dans **deux sidecars d'éditeur** : `AssetFolderStore` (les groupes, partagés viewer ↔
  Graphe) et `SceneGraphState` (positions des nœuds, géométrie des cadres). Aucun ne passe par
  `get_history()`. Les opérations de dossiers du project viewer n'y sont **jamais** passées non
  plus, avant ce chantier. Ce n'est pas une régression.

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
  même touche dans le Scene Manager. Décider laquelle répond (selon le focus (Graphe/viewer vs
  canvas), selon le dernier geste, ou une pile unifiée) sans que Ctrl+Z devienne imprévisible.
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

## Piste Collision (un `Contact` d'événement, pas une « dernière collision »)

Née dans le chantier « La struct `Actor` allégée » ([archive](changelog/archives/actor-struct-lightening.md)), livré à côté de cette piste : elle reste **non verrouillée**, code non commencé.

Une boîte peut toucher plusieurs tuiles ou plusieurs acteurs dans une même frame. Lui demander
`my_box:get_collision()` ou `get_collision_vector()` imposerait de choisir arbitrairement une
« dernière » collision, information instable, perdue dès que deux contacts coexistent. La
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

### Extension proposée (2026-09-25) (la normale vaut aussi pour un contact acteur↔acteur)

**Non verrouillée.** Aujourd'hui la normale n'existe que pour les tuiles (`on_tile_collide(normal_x,
normal_y)`, deux entiers) ; un contact acteur↔acteur n'en porte aucune (`on_collision_enter(other,
my_box, other_box)`). Distinguer « on me marche dessus » de « on me touche » impose donc deux boîtes
Trigger dédiées (`tete`, `pieds`) et la comparaison de deux tags (`my_box.tag == "tete"`, cf.
`docs/user-guide/enemies.md`). Le `Contact` ci-dessus ne le règle que si la normale s'y trouve aussi :

```lua
function on_collision_enter(contact)
  if contact.other.name ~= "Joueur" then return end
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
- **Point ouvert, le calcul.** Le runtime ne dérive aujourd'hui aucune normale entre deux boîtes. Pour
  deux AABB, la normale est l'axe de plus petit recouvrement, de signe donné par les centres. À
  vérifier : coût par paire (le budget de détection est un budget de scanline), comportement en
  diagonale (recouvrements égaux : choisir une règle et l'écrire), boîte contenue dans l'autre, et
  vitesse relative très élevée (traversée en une frame). La normale d'un contact tuile, elle, est déjà
  connue.
- **Point ouvert, la valeur.** Comme pour le `Contact` de tuile, l'introduction attend la vérification
  que le sous-ensemble Lua (`lua_subset.py`) sait porter une valeur structurée (`contact.normal.y`,
  `contact.other.name`) et qu'un paramètre de handler peut en être une.
- **Migration.** Les trois signatures (`on_collision_enter(other, my_box, other_box)`,
  `on_collision_exit`, `on_tile_collide(nx, ny)`) migrent ENSEMBLE vers un `Contact`, avec le renommage
  `on_tile_collide` → `on_tile_collision`. Retrait sec, comme le reste. Le guide utilisateur
  (`enemies.md`, `collectibles.md`, `gameplay-loop.md`, `boss.md`) et les démos sont à migrer avec la
  tranche ; les boîtes `tete`/`pieds` du guide disparaissent au profit d'une seule boîte et de la normale.
- **Ce que ça ne change pas.** `hb:overlaps(other)` reste la requête booléenne pour un test ponctuel
  hors événement ; le `Contact` n'est délivré qu'aux handlers.

---

## L'élément d'interface appartient à sa scène (des noms locaux)

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
- Ne touche pas aux noms d'acteurs (déjà locaux, cf. [changelog/archives/actor-scene-local.md](changelog/archives/actor-scene-local.md)).

---

## Les prefabs (l'instance garde ce qu'elle surcharge, le reste suit le prefab)

### D'où vient la question (2026-10-13)

Née de l'inventaire des écrans qui écrivent à chaque cran (cf. « 2e. Fluidité des réglages » de l'écran Son) : régler un
champ d'un prefab écrit le prefab **plus toutes les scènes qui en portent une instance**, à chaque valeur. L'auteur a
demandé pourquoi la scène ne charge pas simplement le prefab à l'ouverture, un seul fichier écrit, propagé par le
chargement. La réponse est que le modèle actuel est celui de la copie, auquel on a ajouté une propagation.

### Ce qui existe (lu dans le code le 2026-10-13)

- **Une instance est une copie complète** : `Actor.components` est écrit dans le JSON de la scène, avec `prefab_name`. Le
  commentaire de `core/models/scene.py` dit encore « aucun lien vivant après la création ».
- **`save_prefab` propage quand même** (`command_dispatcher.save_prefab`) : il remplace les composants de **toutes** les
  instances dont `prefab_name` correspond, dans toutes les scènes, puis écrit le prefab et chaque scène touchée. La
  propagation ne regarde pas l'état « lié/non lié » : une valeur réglée sur une instance est écrasée à l'enregistrement
  suivant du prefab. La seule protection est « Unlink » (`prefab_name = None`).
- **« Lié » veut dire « même chemin de compilation »** (`actor_prefab_linked`, décision du 2026-08-21) : mêmes types de
  composants, mêmes ids, même ordre, même fichier `.lua`. Valeurs de champs, exports, décalages et `active` sont des
  *paramètres d'instance* qui ne délient pas, et que la propagation écrase pourtant.
- **Expose / Relink** : Expose pousse composants, palette et notes de l'instance vers le prefab, puis `save_prefab` propage ;
  Relink reprend ceux du prefab. La POSE (x, y, rotation, parent, priorité…) reste à l'instance et n'est jamais propagée.
- **L'instance d'un prefab n'écrit jamais le prefab** : seul l'inspecteur du prefab et Expose le font.
- **Ce qui rend le chantier faisable :** `Project.load` charge déjà les prefabs avant les scènes ; le codegen, le
  validateur, l'inspecteur et le canvas travaillent sur des `Actor` en mémoire (environ 75 occurrences de `.components`,
  dans 25 fichiers hors modèle, lectures et écritures confondues) et ne résolvent aucun prefab : si les composants sont
  résolus en mémoire au chargement, aucun d'eux ne devrait changer, à confirmer fichier par fichier avant d'ouvrir.

### Décision (2026-10-13, de l'auteur) (le modèle à surcharges)

L'instance garde **ce qu'elle surcharge** ; **tout le reste suit le prefab**. Une scène n'écrit, pour une instance, que
`prefab_name`, sa pose et ses surcharges ; les composants sont résolus en mémoire à l'ouverture. Conséquences voulues :

- régler un prefab n'écrit **que le prefab** (la propagation reste immédiate, mais en mémoire : le canvas et
  l'inspecteur de la scène active suivent le geste) ;
- modifier une valeur sur une instance dans le canvas **n'écrit jamais le prefab** : elle enregistre une surcharge sur
  cette instance ;
- **« Expose »** est le geste qui fait passer les surcharges d'une instance dans le prefab, donc aux autres instances ;
  **« Relink »** efface les surcharges de l'instance ;
- les autres modèles étudiés sont écartés : le statu quo (tout écrasé), et le « tout ou rien » (toute modification
  détache complètement l'instance, simple, mais une instance dont on a réglé une valeur ne recevrait plus un composant
  ajouté au prefab).

### Ce qu'il faudrait trancher avant d'ouvrir

1. **L'unité d'une surcharge.** Un champ d'un composant (adressé par l'`id` du composant, qui survit à un réordonnancement),
   y compris chaque export d'un script ? Ou un composant entier ?
2. **Les changements de structure sur une instance** (ajouter ou retirer un composant, changer le fichier `.lua` d'un
   script). Proposé : ils **délient** l'instance (le badge « unlinked » actuel, qui garde son sens de chemin de
   compilation), et seules les valeurs sont des surcharges. À confirmer : « lié/non lié » reste-t-il cette distinction ?
3. **Le sens exact d'Expose** : toutes les surcharges de l'instance, ou un choix champ par champ ? Une autre instance qui
   surcharge le même champ garde-t-elle sa valeur (proposé : oui) ?
4. **L'affichage** : comment l'inspecteur montre un champ surchargé, et le geste « revenir à la valeur du prefab » pour un
   champ (marqueur + bouton ?).
5. **Une surcharge périmée** : le prefab a retiré ou renommé le champ (un export de script renommé). Proposé : elle est
   ignorée avec un avertissement, jamais silencieusement.
6. **Le prefab absent** (supprimé, fichier manquant) : l'instance n'a plus de composants à résoudre. Le badge « missing »
   existe ; il faut une règle pour le build (erreur claire, proposé) et pour l'édition.
7. **La migration.** Les scènes existantes portent des composants complets. Proposé : au chargement, les surcharges sont
   calculées comme **la différence** entre l'instance et son prefab, sans perte ; le fichier n'est réécrit qu'au prochain
   enregistrement. À vérifier sur les projets de démo (aucune instance ne doit changer de comportement).
8. **Les prefabs à enfants** (v0.23) : `instantiate_actor_from_prefab` ne copie que l'acteur racine. Ce que deviennent
   les enfants d'une instance posée dans une scène n'a **pas été vérifié**.
9. **Le rechargement à chaud** : un fichier prefab ou scène modifié hors de l'éditeur doit relancer la résolution.
10. **Où le placer.** Le modèle change ce que l'auteur voit (ce qui suit le prefab, ce qui est surchargé) : un chantier
    technique, comme ici, ou un jalon numéroté ? Et la priorité face à v0.29, **non arbitrée**.

### Ce que ça touche (à confirmer en lisant le code avant d'ouvrir)

`core/models/scene.py` (sérialisation de l'`Actor`, surcharges, `actor_prefab_linked`) ; `core/models/components.py` (différence
et application champ par champ) ; `core/project.py` (résolution après `prefabs.load()` / `load_scenes()`, rechargement à
chaud) ; `core/command_dispatcher.py` (`save_prefab`, `relink_actor_to_prefab`, `expose_actor_to_prefab`,
`instantiate_prefab`) ; `core/project_renames.py` ; `ui/scene_manager/inspectors/actor_inspector.py` (marqueur de surcharge,
badge, `_persist`) ; `core/history.py` (les commandes qui ajoutent ou retirent un composant : **vérifier qu'elles passent toutes
par `_persist`**, c'est le point de contrôle prévu pour enregistrer une surcharge) ; ARCHITECTURE.md. Le codegen ne devrait
pas changer, à prouver, voir l'ordre ci-dessous.

### Ordre d'implémentation (proposé)

1. **Un filet avant tout :** figer le C généré des projets de démo ; il doit rester **identique à l'octet** après
   migration.
2. Le modèle seul : surcharges, différence et application, aller-retour de sérialisation. Aucune interface.
3. Le chargement : résolution, migration, rechargement à chaud.
4. Le dispatcher : `save_prefab` n'écrit plus que le prefab ; Expose et Relink sur le nouveau modèle.
5. L'inspecteur : marqueur de surcharge, retour à la valeur du prefab, badge.
6. Supprimer l'ancienne propagation (la boucle sur toutes les scènes) ; documentation.

### Ce que ça ne fait pas

- Ne rend pas la POSE d'une instance dépendante du prefab (elle n'en a jamais fait partie).
- N'imbrique pas les prefabs (une partie n'est pas un autre prefab, cf. v0.23).
- Ne change ni le runtime C, ni le format émis, ni `actor.spawn`.

---

## Tout ce que l'auteur manipule vit dans `assets/`

### D'où vient la question (2026-10-10)

Le chantier « Source ≠ asset » a posé que `assets/` est le dossier de l'auteur, qu'il organise lui-même (modèle Unity /
Godot / Unreal). Or une partie de ce qu'il manipule vivait encore sous `project/` : l'onglet Disk n'en montrait rien. La
décision avait été de garder `project/` pour « ce qui n'a pas de source à relier » ; elle est **révisée** : `project/`
n'est plus pour l'auteur, `assets/` l'est pour tout.

### Décisions verrouillées (2026-10-10)

- **Tout ce que l'auteur a le droit de manipuler passe de `project/` à `assets/`**, sous le MÊME nom de dossier (un seul
  geste, déplacer sans renommer ; normaliser (`prefab` → `prefabs`…) viendra avec les dossiers librement déplaçables) :

  | Avant | Après |
  | --- | --- |
  | `project/scenes/` | `assets/scenes/` |
  | `project/prefab/` | `assets/prefab/` |
  | `project/ui_layouts/` | `assets/ui_layouts/` |
  | `project/music_boxes/`, `jingle_boxes/`, `sound_boxes/` | `assets/music_boxes/`, `jingle_boxes/`, `sound_boxes/` |
  | `project/data/` (tables de données) | `assets/data/` |
  | `project/fonts_assets/` (polices logiques) | `assets/fonts_assets/` |
  | `project/texts.json`, `texts_<langue>.json` | `assets/texts.json`, `assets/texts_<langue>.json` |
  | `project/variables.json` | `assets/variables.json` |

- **`project/` ne garde que ce qui n'est pas à l'auteur** : `editor/` (positions du Graphe, dossiers virtuels, manifeste de
  rattrapage, l'état interne de l'éditeur), `licenses/` et `README.md`.
- Les textes et les variables sont des tables du projet entier, pas des assets nommés : ils se posent à la RACINE de
  `assets/`, pas dans un sous-dossier. `assets/data/` est lu comme « une table par fichier » et les avalerait.
- Les projets existants se migrent par `tools/migrate_project_to_assets.py` (comme pour les ids : aucune lecture de
  l'ancien emplacement dans l'éditeur, le projet n'étant pas diffusé), appliqué aux deux démos et au starter.

### Ce que ça touche

- **Chemins** : les propriétés de `core/project_paths.py` (une dizaine), plus les emplacements écrits en dur, la création
  des dossiers à l'ouverture (`Project.load`, `Project.create`), la surveillance (`ProjectWatcher`), les traductions
  (`texts_<langue>.json`), la copie d'un starter.
- **L'onglet Disk** : ces fichiers y apparaissent ; ils doivent être marqués ASSET (famille, icône) et non « Non géré ».
- **Tests** : ceux qui construisent un projet à la main ou citent `project/<famille>` (une quinzaine).
- **Docs** : ARCHITECTURE (la disposition d'un projet), les en-têtes de module qui citent `project/`.

### Ordre d'implémentation

1. Les chemins et leurs utilisateurs (code, surveillance, starters).
2. L'onglet Disk reconnaît ces familles.
3. Le script de migration, appliqué aux démos et au starter.
4. Les tests, les docs, la chasse au code mort.

---

## Créer un asset : deux gestes, aucun dossier titulaire

### D'où vient la question (2026-10-19)

Créer un asset a deux gestes, **créer depuis une source** et **créer vierge**, et l'onglet Disk les suit déjà
(`window._disk_create_from_sources`, `_disk_create_blank`, qui passent par `core.asset_creation` /
`core.blank_assets` puis `CreateAssetCmd`). Mais d'autres chemins font la même chose chacun à sa façon, et quelques
familles gardent un dossier « à elles ». Deux exceptions justifiaient ces dossiers (les scripts de **behavior** et les
**palettes**) ; elles sont levées : un behavior se reconnaît à son contenu (`-- @behavior`), une palette pointe son `.hex`
comme les autres assets pointent leur source. Plus aucune famille n'a de raison d'être titulaire d'un dossier.

### Demandé par l'auteur (2026-10-19)

- **Deux commandes, pas une de plus** : *Create from source* et *Create blank*. Tout écran, tout bouton « + », toute
  importation y passe.
- **Plus aucun asset ne possède un dossier.** Un asset naît dans le dossier que l'auteur désigne (celui que l'onglet Disk
  affiche, sinon la racine de `assets/`), et se range ensuite où il veut.

### Ce que le code dit aujourd'hui (lu le 2026-10-19, rien d'exécuté)

- **`ResourceStore` cherche déjà partout.** Il indexe tout `assets/` par extension (`root`) ; son `dir` ne sert que de
  **lieu de naissance** par défaut (`resource_store.py`, `_path`). Retirer le dossier de famille ne change donc pas la
  découverte des assets existants : seulement où naît un asset dont l'appelant n'a pas dit le dossier.
- **`PaletteStore` est la vraie exception** (`palette_store.py`) : (1) un `.hex` déposé dans `assets/palettes/` devient
  d'office une palette (`load`, `self.dir.glob("*.hex")`), ce qui contredit « créer est un geste, jamais la conséquence de
  l'apparition d'un fichier » ; (2) une palette neuve voit son `.hex` posé dans `self.dir` même quand son sidecar part
  dans un autre dossier (`save`, `hex_path`) : les deux fichiers se séparent dès la naissance.
- **Les behaviors** : `scripts_behaviors_dir` n'a qu'un lecteur, `script_creation.py`, qui écrit le `.lua` sans passer
  par l'historique (pas annulable), contrairement à l'onglet Disk (`CreateFileCmd`).
- **Chemins parallèles** à ramener aux deux commandes : les `add` de `asset_kinds.py` (polices, palettes, sfx / musiques /
  jingles, tables de données), `script_creation.py` (menu partagé par le Script finder et l'assets finder), l'import de
  sprite (`import_png_dialog.py`), l'écran Background (import et fond vierge).
- **Les propriétés `*_dir`** de `project_paths.py` (une quinzaine, dont `palettes_dir`, `font_assets_dir`,
  `scripts_behaviors_dir`) alimentent `ResourceStore(dir, cls, assets_dir)` dans `Project.__init__`.

### Le contrat proposé (non verrouillé)

- `asset_creation.create_from_source(project, family, paths, folder)` et `asset_creation.create_blank(project, kind, folder)`
  rendent **une commande annulable** (`CreateAssetCmd`, `CreateFileCmd`, `MacroCmd` pour un lot). `folder` est obligatoire :
  l'appelant le prend à `import_folder()` s'il n'en a pas d'autre. Le message d'état reste affaire de la fenêtre.
- Les scripts et les behaviors sont deux types de `create_blank` comme les autres ; `script_creation.py` disparaît.
- `ResourceStore(root, cls)` : plus de `directory`. Un asset sans dossier donné naît à la racine de `root`.
- Une palette neuve naît avec son `.hex` **à côté de son sidecar**, dans le même dossier ; plus d'adoption d'un `.hex`
  déposé à la main (il redevient une source libre, qu'on transforme par *Create from source*).
- Les propriétés `*_dir` de famille disparaissent, `scripts_behaviors_dir` et `font_assets_dir` comprises.

### Ce que ça touche (à confirmer en lisant le code avant d'ouvrir)

- `core/asset_creation.py`, `core/blank_assets.py`, `core/resources/resource_store.py`, `core/resources/palette_store.py`,
  `core/project_paths.py`, `core/project.py` (construction des stores, ligne du PNG de fond), `window.py` (callbacks Disk).
- `ui/common/asset_kinds.py`, `ui/common/asset_finder.py`, `ui/common/script_creation.py` (supprimé),
  `ui/script_editor/script_finder_panel.py`, `ui/scene_manager/assets_finder_panel.py`, `component_editors/script.py`
  (non lu), `ui/sprite_editor/import_png_dialog.py`, `ui/background_editor/background_editor_screen.py`.
- **Tests** : ceux qui construisent un projet à la main et comptent sur `project/<famille>/` ou sur l'adoption d'un `.hex`
  (palettes). **Docs** : ARCHITECTURE, `docs/development/`, en-têtes de module qui citent un dossier de famille.
- Les deux démos et les starters ne sont pas réécrits sans accord de l'auteur ; leurs fichiers restent où ils sont.

### Décisions (2026-10-19, de l'auteur)

1. **Les starters et un projet neuf ne livrent plus de dossiers vides par famille** (`sprites/`, `scenes/`…).
2. **Pas de migration des `.hex`** des démos : ils restent où ils sont. Le starter, lui, livre désormais le `.palette`
   de chacune de ses palettes (sans quoi elles disparaîtraient avec l'adoption).
3. **`FontAsset` suit la même règle** : il naît dans le dossier désigné, `font_assets_dir` disparaît avec les autres.

### Livré (2026-10-19)

- **Tranche 1, `PaletteStore`** : plus d'adoption d'un `.hex` déposé à la main (c'est une source libre) ; une palette neuve
  naît avec son `.hex` à côté de son `.palette`, dans le dossier où elle naît. Tests ciblés verts.
- **Tranche 2, les deux commandes** : `asset_creation.create_from_source(project, family, paths, folder)` et
  `create_blank(project, kind, folder)` rendent un `Gesture` dont `command` est UNE commande annulable (un lot de sources =
  une `MacroCmd`, un script = `CreateFileCmd`). L'onglet Disk les appelle et ne garde que ses messages d'état.
  L'ancienne création immédiate, sans historique, devient `create_from_source_now` (tests, outils).
- **Tranche 3a, les scripts** : `script_creation.py` et `scripts_behaviors_dir` supprimés. Le « + » des deux finders appelle
  `asset_kinds.add_script`, qui passe par `create_blank` dans le dossier que l'onglet Disk affiche (annulable).
- **Tranche 3b, import de sprite** : `import_new_sprite` copie la source puis appelle `create_from_source` (une seule
  entrée d'historique).
- **Tranche 3c, import de fond** : `create_from_source(..., defer_encoding=True)` crée le fond sans l'encoder ; `_import_png`
  l'appelle, règle le fond puis pousse la commande (annulable) ; annuler annule aussi la compression en cours. La copie du
  PNG dans le dossier, elle, n'est pas annulée (la source reste une source libre). **Reste** : le fond vierge de l'écran
  Background (`_create_blank_background` écrit un PNG puis importe).
- **Tranche 3d, les « + » de `asset_kinds`** : tables de données, palettes (16 / 256 couleurs) et polices logiques passent par
  `create_blank` (`font_asset` rejoint `BLANK_KINDS`, donc le menu *Create blank* de Disk) ; SFX, musiques et jingles
  passent par `ui/common/source_import.py` (choisir un fichier, le copier dans le dossier affiché, *Create from source*,
  une seule entrée d'historique) : **un son ne naît plus sans fichier**. Le sprite utilise le même helper. Reste hors des
  deux gestes : l'import de palette `.gpl` / `.pal` (il convertit un format étranger, sans pointer sa source).

- **Tranche 3e, les trois chemins hors liste** : (1) le script créé depuis l'inspecteur d'acteur passe par `create_blank`
  (`name`, `template="actor"`), dans le dossier affiché, annulable (un nom déjà pris est suffixé au lieu de relier l'ancien
  script) ; (2) un nœud `Interface` est une mise en page vierge plus son nœud de scène, `asset_creation.create_interface`
  (UNE commande) : « + Interface » de l'arbre la pousse dans l'historique, `_ensure_layout` du canvas l'exécute SANS historique
  (un undo qui la retirerait casserait les éléments dessinés ensuite) ; (3) scènes et prefabs des « + » passent par
  `create_blank` (`window._create_blank`), `add_scene` / `add_prefab` du dispatcher sont supprimés. Reste hors des deux
  gestes : « Expose to prefab » et la copie de prefab (ils partent d'un acteur existant), `save_palette` (palette extraite d'un
  sprite ou d'un fond).

### Ordre d'implémentation (proposé)

1. `PaletteStore` d'abord (l'exception réelle), avec son test : `.hex` à côté du sidecar, plus d'adoption.
2. `asset_creation` : les deux entrées rendant une commande ; l'onglet Disk les appelle.
3. Les chemins parallèles, un par un (scripts, sons, tables, polices, palettes, sprite, background).
4. `ResourceStore(root, cls)` et la suppression des `*_dir` de famille.
5. Tests, docs, chasse au code mort ; l'ancien code est supprimé avant de dire terminé.

### Ce que ça ne fait pas

- Ne déplace aucun fichier d'un projet existant.
- N'ajoute aucun type d'asset ni aucun geste de création : il en retire.
- Ne touche ni à la règle des noms libres (`coin`, `coin_2`) ni au chantier « Finder et Disk » (renommage).

---

## Finder et Disk (« Asset library » et « Project files »)

### D'où vient la question (2026-10-14)

Deux mots prêtent à confusion. **« Asset finder »** désigne à la fois la famille de panneaux (Project viewer, Sprite
finder, Script finder, Sound finder…) et le mécanisme commun (`AssetFinder`) ; **« Assets »** désigne à la fois ce que le
projet *contient* (les assets nommés) et le dossier de l'auteur (`assets/`, racine de l'onglet Disk). Le chantier
« Tout ce que l'auteur manipule vit dans `assets/` » a encore élargi ce second sens : le dossier contient désormais des
scènes, des tables, des textes, qui ne sont pas des « assets » au sens d'un sprite ou d'un fond. Renommer lève
l'ambiguïté et rend le code plus clair à maintenir.

### Décisions verrouillées (2026-10-14)

- **L'« asset finder » devient l'« asset library »** : le nom change partout où il vit, le vocabulaire visible
  (libellés, infobulles), les classes et modules (`AssetFinder`, `asset_finder.py`, `*_finder_panel.py`), les tests, la
  doc (`editor/ui/asset-finder.md`, ARCHITECTURE). Aucun alias de l'ancien nom : une fois le renommage fait, plus un
  « finder » ne reste.
- **Le dossier de l'auteur devient « Project files »** : c'est le nom que l'auteur voit pour ce qu'il organise lui-même
  (racine de l'onglet Disk, aujourd'hui « Assets »).
- **Sprite, Script et Sound rejoignent le modèle de l'asset library** : ils cessent d'être des « finders » à part. Il n'y a
  plus qu'un seul modèle (l'asset library) dont ils sont des vues par type d'asset, au lieu de quatre panneaux qui
  portent chacun leur nom (« Sprite finder »…). Les `*_finder_panel.py` disparaissent comme noms de famille.
- **Le « Project viewer » (un temps nommé « Scene viewer ») est la « Scene library »** : à l'usage c'est la bibliothèque
  de la scène. L'auteur y ouvre une scène, y prend un prefab. Ce n'est pas une vue du projet entier (« Project files »
  prend ce rôle) mais une **instance du même modèle d'asset library**, comme les trois autres, avec trois filtres :
  **scene / prefab / script**. Le filtre **script** pourrait même être retiré (à trancher, point 2) : le Script
  finder a déjà sa propre bibliothèque.

### À trancher avant de commencer

1. **« Project files » : nom affiché seulement, ou aussi nom du dossier sur disque ?** Le renommage sur disque
   (`assets/` → `project_files/`, ou autre) touche `core/project_paths.py`, la surveillance, les starters, les deux démos,
   la migration et une quinzaine de tests, comme le chantier `project/` → `assets/`. Le nom affiché seul est gratuit.
2. **Les quatre bibliothèques : une instance du même modèle chacune, ou une seule avec filtre ?** Réglé : Sprite,
   Script, Sound et Scene en font partie ; la Scene library a trois filtres (scene / prefab / script). Reste la forme
   (aujourd'hui chaque écran embarque son finder) et **le filtre script de la Scene library : le retire-t-on**, puisque
   la Script library existe ? Le retirer enlève un doublon, mais `script_creation.py` partage aujourd'hui le menu de
   création entre les deux.
3. **L'ancien mot « asset » dans `assets_finder_panel.py`, `asset_kinds.py`, le dep-graph** : reste-t-il le mot juste
   pour un asset nommé (sprite, fond, palette), distinct de « Project files » qui contient aussi du non-asset ? Proposé :
   oui, « asset » ne désigne plus que l'objet nommé.
4. **Les clés de traduction** (`labels.json` / `labels_fr.json`, dont `disk.root`) et les raccourcis (`keybindings.py`)
   suivent le renommage, avec la traduction FR ajoutée d'office.

### Ce que ça touche

- ~70 occurrences dans 24 fichiers (relevé du 2026-10-14) : `editor/ui/common/asset_finder.py`, `asset_kinds.py`,
  `*_finder_panel.py`, `window.py` (onglet « Project viewer » → « Scene library », voir aussi `script_creation.py`,
  `script_finder_panel.py`, `assets_finder_panel.py` qui le citent), les écrans qui embarquent un finder, `tools/check_ui_text.py`, `core/keybindings.py`.
- **Tests** : `test_asset_finder_folders.py`, `test_finder_locate.py`, `test_sound_finder_folders.py`, `conftest.py`.
- **Docs** : `editor/ui/asset-finder.md` (renommé), ARCHITECTURE, ROADMAP (les sections qui citent « finder »).

### Ordre d'implémentation

1. Trancher les points ci-dessus.
2. Le renommage du code (classes, modules, tests) en un seul geste, sans alias.
3. Les libellés, les infobulles, les clés FR.
4. Si le dossier change de nom sur disque : chemins, surveillance, migration des démos et du starter.
5. Les docs, la chasse au code mort.

---

## La compression d'un fond se joue, elle ne s'attend pas

### D'où vient la question (2026-10-14)

L'auteur voudrait que la compression, dans le Background Editor, soit un moment **créatif** plutôt qu'une étape
barbante : on bouge des potards et on attend. Analyse du parcours faite le même jour, **en lisant le code**
(`background_editor_screen.py`, `bg_import.py`, `bg_inpaint_canvas.py`). Rien n'a été chronométré ni essayé à la
souris. Les points 7 et 8 ci-dessous sont à vérifier avant de s'appuyer dessus.

### Le parcours actuel

1. Un fond est sélectionné ; la carte « Compression » est repliée, sauf si l'image « ne tient pas » ou si des réglages
   existent déjà (`_compression_needs_attention`).
2. Layout et profondeur sont **mis en attente** (`_staged`), rien ne se compresse.
3. Les curseurs (palettes, couleurs/palette, couleurs globales, tuiles), la méthode, le dithering et son type se règlent.
4. Après 300 ms de pause, un encodage complet part en arrière-plan ; le canvas montre le résultat avec un badge
   « computing » puis « ready » (`_on_compress_preview`, un seul calcul à la fois, le dernier réglage passe après).
5. « Compress », en bas de l'inspecteur, valide : le résultat du cache (8 entrées), sinon un nouvel encodage.

À garder : non destructif, hors-thread, cache, validation sans recalcul, source jamais touchée.

### Les frictions relevées

1. **Les chiffres ne suivent pas l'aperçu** (la plus grosse). Les overlays d'info (tuiles/budget, palettes) et
   d'avertissement (`_info_lines`, `_compression_lines`) lisent le fond **déjà compressé**. Le résultat d'aperçu porte
   pourtant `unique_tiles`, `final_palettes`, `tiles_merged`, `tiles_reduced` : il ne sert qu'à dessiner l'image, puis
   est jeté. Pour savoir si un réglage tient dans le budget, il faut cliquer sur « Compress ».
2. **Pas de comparaison avant/après.** L'aperçu remplace le rendu, il ne s'y compare pas (aucun split, bascule ni carte
   d'écart dans `ui/background_editor/`). L'aperçu exclut aussi les calques de peinture : l'image jugée n'est pas
   exactement l'image finale.
3. **Les curseurs parlent la langue de l'encodeur** (`palettes_max`, `colors_per_palette`, `global_colors`,
   `tile_target`), et leurs liens sont invisibles : le dithering se grise en 4bpp tant que « Global colors » est à Off ;
   surtout, dès qu'un curseur s'écarte du défaut, `_asks_for_reduction_4bpp` coupe le chemin « indexé direct » qui
   préservait la palette d'auteur, une **falaise** que l'interface n'annonce pas.
4. **L'objectif réel n'est pas exprimé.** Nous voulons « que ça tienne sur GBA » (tuiles, 16 palettes, VRAM) avec le
   moins de dégâts ; seule la cible de tuiles est orientée but. Les diagnostics savent quel levier répare quel problème
   mais s'affichent en texte jaune sans action. `analyze_tile_colors` (couleurs par tuile, tuiles partagées, palettes
   nécessaires) est écrit et testé, mais son bouton est masqué (« sert surtout à déboguer »).
5. **Latence et attente opaques.** Chaque réglage relance un encodage complet depuis zéro ; le cache est exact (clé sur
   tous les réglages), donc un glissement de curseur le manque presque toujours ; le calcul en cours ne s'annule pas.
   L'attente n'a qu'un badge et une barre indéterminée, alors que l'encodeur a des étapes nettes (extraction, packing,
   indexation, dédup, fusion).
6. **Le geste est dispersé et mal nommé.** Mode en haut, curseurs dans une carte repliée, « Compress » en bas d'un
   panneau qui défile et visible seulement quand un réglage est en attente. « Compress » est un faux ami : l'aperçu
   **est** la compression, le bouton la valide. Pas de « revenir au compressé actuel » : « Reset » remet les
   **défauts**. Deux aperçus de nature différente (ajustements en direct, compression différée) se partagent canvas et
   badge.
7. **À vérifier**, ce que devient un réglage en attente quand on change de fond (`_staged` est un état du panneau ;
   le chemin de rechargement n'a pas été lu).
8. **Mesuré le 2026-10-14** (`encode_by_mode`, poste de l'auteur, une seule passe, sans l'UI) :
   - **PNG indexé de pixel art** (démo Platformer 544×224, PongAdvanced 240×160) : de 0,04 à 0,55 s, tous réglages
     confondus. Le jeu en direct est possible tel quel.
   - **Photo RGBA 540×540** (`PongAdvanced/assets/backgrounds/untitled.png`, 4561 tuiles uniques) : **4bpp défaut
     10,7 s** (24 s sous cProfile), 4bpp global 64 + dithering 8,2 s, **4bpp cible 256 tuiles 32 s**, 8bpp 1,7 s.
   - **Où part le temps** (profil du 4bpp défaut, 24 s) : `_pack_palettes` **13,3 s**, soit plus de la moitié ; or sur une
     photo il ne sert qu'à compter `pre_merge_palettes`, un chiffre de **diagnostic** (`encode_background`, branche
     « max_tile_colors > editable »). Le résultat n'alimente pas l'encodage. Avec une cible de tuiles, `_ward_groups`
     ajoute 13,2 s. Le clustering de palettes (3,5 s) et l'extraction (2,7 s) sont le reste utile.
   - **Conséquence** : sur une photo, un curseur ne peut pas se jouer en direct (10 à 30 s par réglage, le cache exact
     ne sert pas). Il y a au moins un gain quasi gratuit (calculer `pre_merge_palettes` à la demande plutôt qu'à chaque
     encodage) ; au-delà, il faudra un aperçu **dégradé et rapide** (image réduite) distinct de l'encodage final.

9. **Une réduction cachée, relevée le 2026-10-14** (capture de l'auteur : « Image scaled → 240×133 » et « > 256 colors.
   Reduced to 256 »). Les deux encodeurs **bitmap** (`_encode_background_indexed_bitmap`, `encode_background_bitmap`)
   ajustent l'image en « contain » dans 240×160 **eux-mêmes**, par-dessus le recadrage et la taille que l'auteur a posés ;
   et l'import choisit le bitmap tout seul pour une photo (`detect_import_mode`). Un gros fichier est donc rétréci sans que
   l'auteur l'ait décidé, alors que le recadrage et le redimensionnement existent pour qu'il le décide. Le tuilé, lui, ne
   redimensionne jamais (il ne fait que remplir jusqu'au multiple de 8). Les 256 couleurs, en revanche, sont la compression
   elle-même, pas une réduction de géométrie. **Conséquence pour la comparaison à la source** : en bitmap, l'image compressée
   (240×133) n'a pas la grille de l'image préparée. La carte d'écart par tuile n'a pas de sens tant que cette réduction est
   cachée dans l'encodeur.

### Le problème de fond (relevé le 2026-10-15, d'après deux captures de l'auteur et la lecture du code)

L'écran mélange **trois images** et ne dit jamais laquelle il montre :

1. **le fichier** de l'auteur (`_src_size`, en pixels du PNG) ;
2. **l'image préparée**, recadrée, redimensionnée, miroitée, ajustée : ce que l'auteur a décidé (`_prepared_size`) ;
3. **l'image encodée**, ce que la GBA affichera, avec sa propre géométrie : le tuilé remplit jusqu'au multiple de 8, le
   bitmap est **ajusté en 240×160** par l'encodeur.

S'y ajoute un quatrième axe, **validé / en attente** (layout et curseurs mis en attente, aperçu non appliqué).

Le canvas montre l'image (3), les outils de préparation travaillent dans l'espace de l'image (2), les avertissements
décrivent (3) mais ne lisent que l'état **validé**, et chaque outil a reçu sa rustine locale. Ce que ça donne :

- **Redimensionner en bitmap : poignées et image désynchronisées.** `begin_resize(_prepared_size())` pose le cadre à la
  taille préparée (482×269 sur la capture), alors que `pix_item` dessine l'image encodée (240×134) à l'origine du même
  repère. Le miroir a eu sa rustine (`set_mirror(..., prepared, display)`, « seul un bitmap est ajusté à l'encodage »),
  le redimensionnement non.
- **Le recadrage, lui, remplace la vue par le fichier** (`begin_crop` cache l'image encodée et montre la source) : on
  change donc de repère en entrant dans l'outil, et le curseur `x:… y:…` change d'unité avec.
- **Le « W×H » en haut à droite** est un `QLabel` nu (`set_canvas_size`) alimenté par trois sources sans libellé : la taille
  encodée hors geste, celle du cadre de recadrage (en pixels du fichier) pendant un recadrage, la cible pendant un
  redimensionnement. Même emplacement, trois sens.
- **Les avertissements ne suivent pas le layout.** `_info_lines` / `_validation_lines` lisent le fond **validé** ;
  mettre le layout en attente ne les recalcule pas. L'aperçu les met à jour depuis le 2026-10-14 (tuilé) et le
  2026-10-15 (bitmap, qui laissait ceux du layout précédent), mais seulement une fois l'aperçu calculé.
- **L'auteur ne voit jamais son fichier tel quel** : l'import choisit le layout, l'encodeur réduit, et le canvas montre
  le résultat (« une version tronquée » (auteur, 2026-10-15)) avec des constats qui disent ce que l'encodeur a fait,
  pas ce que l'auteur doit faire pour que ce soit compatible.

**Piste remplacée le 2026-10-15** par le chantier [Le fond est un plan de travail](#le-fond-est-un-plan-de-travail-canvas-image-posée-comparaison-sourcecompressé), plus radical : l'auteur y pose
l'image dans un canvas à lui plutôt que de la voir à travers un cadre matériel. Le texte qui suit est l'état de départ.

**Piste (non verrouillée), un seul espace, celui du fichier préparé.** Le canvas montre l'image de l'auteur **entière**,
à sa taille ; le matériel est un **cadre** posé dessus (240×160 en bitmap, la grille 8×8 en tuilé), le hors-cadre grisé.
Recadrer et redimensionner agissent dans cet espace et le cadre bouge avec : plus de désynchronisation possible. Les
constats deviennent une **liste de choses à faire** (« dépasse de 242×109 px → recadrer / ajuster au cadre »), chacune avec
le geste qui la résout, au lieu d'un compte rendu de l'encodeur. L'encodeur bitmap ne rétrécit plus en douce : ce qui
dépasse du cadre est ce que le cadre montre, grisé en dehors. À trancher : voir « À trancher avant d'ouvrir », point 5.

### Directions possibles (proposées, rien de verrouillé)

- **Budget en direct** : les jauges tuiles / palettes / VRAM suivent l'aperçu, depuis les diagnostics déjà calculés
  (friction 1). Le plus petit geste, et il débloque les autres.
- **Voir la perte** : comparaison curseur ou bascule avec la source, et carte des tuiles sacrifiées (tuiles > 15 couleurs,
  tuiles fusionnées). Le diagnostic par tuile existe (frictions 2 et 4).
- **Diagnostics actionnables** : un avertissement devient un bouton qui pose le curseur qui le règle (friction 4).
- **Réglage par objectif** : « tenir en N tuiles », « garder le plus de couleurs possible », les curseurs passant au
  second plan (frictions 3 et 4).
- **Attente racontée** : étapes de l'encodage au lieu d'une barre indéterminée ; annulation du calcul périmé
  (friction 5).

### Ordre retenu (2026-10-14)

1. **Petits gains de latence**, *livré le 2026-10-14.* `_pack_palettes` teste l'union par différence d'ensembles au
   lieu de la reconstruire : sortie **identique octet pour octet** sur les cinq fonds de la démo (4bpp, réglage par
   défaut et réduit, 12 cas comparés par empreinte), `_pack_palettes` passe de 13,3 s à 6,6 s sur la photo. Le calcul de
   `pre_merge_palettes` n'est **pas** sorti du chemin chaud : il reste la moitié du temps restant.
2. **Jauges en direct** (friction 1), *livré le 2026-10-14, pas vérifié à la souris.* Quand l'aperçu d'une compression est
   montré, les overlays du canvas portent **ses** chiffres : tuiles uniques et palettes en jauge de texte (rouge au-delà
   du budget), « (actuel : N) » à côté, tuiles réduites / fusionnées, et les mêmes avertissements que pour un fond
   compressé (`_compression_lines_from`, règles uniques). Le fond compressé reprend la main quand l'aperçu disparaît.
   Bitmap : pas de jauge (ni tuiles ni palettes). Le chiffre d'un aperçu **exclut les calques de peinture**, comme
   l'image. Pendant le calcul, les chiffres affichés sont ceux de l'état précédent.
3. **Comparer à l'image source** (frictions 2 et 4), demandé par l'auteur le 2026-10-14 : le diagnostic se lit **contre
   le fichier source**, pas seulement en chiffres (carte d'écart par tuile, fidélité globale, bascule source/compressé).
   À concevoir ; le coût dépend de la taille, donc sur photo à calculer sur une version réduite.

### À trancher avant d'ouvrir

1. Par quelle direction commencer (feedback en direct, perception de la perte, ou réglage par objectif) ? *Tranché :
   jauges en direct d'abord, puis comparaison à la source (voir « Ordre retenu »).*
2. Le bouton « Compress » change-t-il de nom et de place, puisque l'aperçu est déjà la compression ?
3. La falaise du chemin « indexé direct » (friction 3) : la signale-t-on, ou change-t-on le comportement ?
4. Que fait-on du bouton « Analyser » masqué : réintégré dans le tableau de bord, ou retiré ?
5. ~~Le canvas montre-t-il le fichier préparé entier avec le cadre matériel posé dessus ?~~ **Tranché le 2026-10-15** :
   un canvas à soi, l'image posée dedans. Voir [Le fond est un plan de travail](#le-fond-est-un-plan-de-travail-canvas-image-posée-comparaison-sourcecompressé).
   L'encodeur qui ajuste seul est écarté (règle posée, voir friction 9).

### Ce que ça touche (à confirmer en lisant le code avant d'ouvrir)

`editor/ui/background_editor/background_editor_screen.py` (inspecteur, aperçu, cache, `_info_lines`,
`_compression_lines`), `bg_inpaint_canvas.py` (badge, rendu d'aperçu), `editor/core/bg_import.py` (diagnostics,
`encode_background`), `labels.json` / `labels_fr.json` (la traduction FR s'ajoute d'office).

### Ce que ça ne fait pas

Ne change ni l'encodeur ni le format du sidecar : c'est un chantier d'interface sur ce que l'encodeur sait déjà dire.
Pas d'outil de dessin (voir « Jouer avec la compression » plus haut : le jeu reste sur les réglages).

---

## Le fond est un plan de travail (canvas, image posée, comparaison source/compressé)

### D'où vient la question (2026-10-15)

Deux captures de l'auteur sur un fond bitmap (« Image scaled → 240×134 », poignées de redimensionnement qui ne
correspondent pas à l'image) ont montré que l'écran mélange **trois images** (le fichier, l'image préparée, l'image
encodée) sans dire laquelle il montre ; le détail est dans « Le problème de fond » de [La compression d'un fond se
joue](#la-compression-dun-fond-se-joue-elle-ne-sattend-pas). Les rustines locales (miroir, recadrage) ne suffisent pas :
chaque outil a son repère. L'auteur attend qu'à l'import on **voie son fichier**, et qu'on lui dise ce qu'il lui reste
à faire pour le rendre compatible.

### Le modèle (décidé par l'auteur, 2026-10-15)

À la manière de Photoshop ou d'Affinity, mais **sans jamais plus d'une image à traiter en même temps** :

1. **On importe une image : un asset se crée, c'est un fond.** Un mode par défaut est posé à l'import
   (`detect_import_mode`) ; l'auteur le change quand il veut (tuilé / bitmap).
2. **Une nouvelle valeur, la taille du canvas** (*canvas-size*), distincte de la taille de l'image importée et modifiable.
3. **L'image est posée dans le canvas**, déplaçable librement. Elle peut **déborder** (ce qui dépasse est rogné à
   l'usage) ou être **plus petite**. L'image entière reste visible, le hors-canvas est grisé : d'un coup d'œil, l'auteur
   voit que son image est trop grande, puisqu'elle sort du cadre.
4. **À l'import, tout est déjà réglé** : le mode par défaut, la taille du canvas qui va avec, l'image à sa taille
   d'origine en (0, 0). Rien n'est rétréci. À partir de là, le plan de travail est prêt à recevoir les gestes de l'auteur.
5. **Le mode « compress view »** fait apparaître une **barre verticale** sur le plan de travail, sur le modèle des barres
   de miroir : d'un côté la source, de l'autre la version compressée, à la même grille. C'est ce qui rend enfin
   possible la comparaison à la source et la carte d'écart par tuile (voir « La compression se joue »).
6. **Une seule image visible, jamais de panneau de calques.** Les calques existent déjà dans le code (décidé par l'auteur :
   l'utilisateur ne les voit jamais, et c'est le but). On reste simple : pas de composition de plusieurs images, pas de
   peinture. La règle « pas un outil de dessin » tient.

**Proposé, non verrouillé** : trois boutons d'aide au placement, **Ajuster** (tout l'image dans le canvas), **Remplir**
(le canvas entier couvert), **1:1** ; sans eux, une photo de 1000 px s'ouvre sur son coin haut-gauche.

### Ce que ça résout

- **Un seul repère.** Les outils agissent sur l'image là où elle est dessinée, dans l'espace du canvas : la désynchronisation
  des poignées devient impossible, et le recadrage n'a plus de repère à lui (voir ci-dessous).
- **Plus de réduction cachée.** Le « contain » 240×160 des deux encodeurs bitmap disparaît : l'encodeur reçoit un canvas
  qui a déjà la bonne taille.
- **Une valeur lisible.** La taille du canvas, la taille de l'image et la position sont des champs nommés ; l'étiquette
  muette du haut à droite disparaît.
- **Des constats qui se calculent sans encoder** : l'image déborde, ou ne couvre pas le canvas. Ils se recalculent à
  l'instant du changement de layout, sans attendre un aperçu.
- **La comparaison à la source** a la même grille des deux côtés.
- **Moins d'outils.** Recadrer = la fenêtre du canvas sur l'image : l'outil Recadrer se fond dans « déplacer + taille du
  canvas ». Redimensionner devient l'échelle de l'image.

### Les données et la migration

- Nouveaux champs du sidecar : taille du canvas, position de l'image (entiers), échelle de l'image. Ils remplacent
  `import_crop` et `import_size`.
- **Migration sans perte, proposée** : un recadrage `(x, y, w, h)` avec une taille `(W, H)` devient une échelle
  `W / w`, une position `(−x·échelle, −y·échelle)` et un canvas `W×H`. À vérifier par test : le rendu d'un fond migré est
  identique, pixel pour pixel, à celui d'avant.
- L'ordre de `prepare_source` aujourd'hui : recadrer, redimensionner, miroir, ajuster. Demain : mettre à l'échelle,
  poser dans le canvas, miroir, ajuster.

### À vérifier avant de coder

1. **La palette indexée d'auteur.** Un PNG indexé garde sa palette grâce au chemin « indexé direct » de l'encodeur
   (`_indexed_direct_source`, non relu à ce jour). Si le canvas est composé en RGBA, ce chemin est perdu : il faut composer
   en mode `P`, avec l'index de transparence, et rééchantillonner au plus proche voisin comme aujourd'hui.
2. **Les limites du canvas tuilé.** « Libre » doit tenir dans les limites des cartes de tuiles de la GBA et dans ce que le
   streaming des fonds sait déjà faire (voir « Background editor », limites Mode 0). Proposé : arrondi à 8, avec un
   avertissement au-delà de ce qui tient.
3. **Les fonds de type UI et animé.** Leurs marges (nine-slice) et leur grille de frames dépendent de la géométrie de
   l'image, et les outils de préparation leur sont déjà fermés (`_prep_available`). Proposé : hors du modèle au début,
   canvas verrouillé sur l'image.
4. **Les peintures par tuile** (inpainting, par scène) sont posées sur la grille encodée : déplacer l'image sous elles
   change ce qu'elles recouvrent, comme le fait déjà un recadrage. À vérifier, pas à craindre.
5. **Les consommateurs de la taille** : `pixel_size()` (Scene Manager), le placement d'animés, la taille déclarée en ROM.
   Tous lisent aujourd'hui la taille préparée ; ils doivent lire la taille du canvas.

### À trancher

1. **Le miroir** agit-il dans l'espace de l'image ou dans celui du canvas ? Proposé : le canvas. On réfléchit la
   composition. (Non tranché explicitement par l'auteur.) --> Dans le canvas, décision tranchée (15/10/26 19h50)
2. **Passer d'un layout à l'autre** : tuilé → bitmap ramène le canvas à 240×160 et garde la position de l'image par rapport
   à l'origine ; bitmap → tuilé garde le canvas tel quel. À confirmer --> Existe-t-il des techniques de streaming d'image bitmap ? Comment fonctionne un flux vidéo sur GBA ? Comment fonctionne un aperçu 3D également. On a peut-être des pistes pour étendre l'affichage d'une image bitmap.
3. **Le canvas change de taille alors qu'un bitmap est fixe** : la taille est-elle simplement grisée, ou masquée ? (l'image déborde du canvas, l'utilisateur peut la repositionner --> Importance de créer un nouvel outil de sélection simple dans la barre d'outils qui deviendra l'outils par défaut de cet écran et qui permettra de simplement déplacer l'image dans le canvas)

### Au-delà de 240×160 : étendre un fond bitmap (étude du 2026-10-16, réponse au point 2)

*Étude seulement : rien n'est codé, rien n'est exécuté sur émulateur.*

**Ce que le matériel offre.** Le Mode 4 a deux pages de 240×160 en 8 bpp (bit 4 de DISPCNT) mais une seule palette,
partagée entre elles : une palette par image se change donc exactement à la bascule. Le Mode 3 n'a pas de double tampon
(75 Ko sur 96 Ko). Le Mode 5 en a deux, en 160×128 et 15 bpp, agrandissables par l'affine de BG2. En bitmap il ne reste
que BG2 (plus de BG0/BG1/BG3 : le texte et l'UI actuels doivent passer par des sprites ou du dessin logiciel) et les
sprites perdent la moitié de leur VRAM (tuiles 512 à 1023).

**Le double tampon ne fait pas défiler.** Il cache le redessin : on écrit dans la page invisible, puis on bascule au
VBlank. Le défilement vient d'une **source plus grande que l'écran, gardée en ROM**, dont un DMA copie la fenêtre visible
vers la page cachée, ligne par ligne avec le stride de la source. Ordre de grandeur (à mesurer) : 38 Ko par image, soit
40 000 à 80 000 cycles sur les 280 000 d'une image, 60 fps sans décodage CPU tant que la source n'est pas compressée.
L'affine de BG2 ajoute déplacement sous-pixel, rotation et zoom gratuits, mais seulement à l'intérieur de la page (pas de
bouclage en bitmap).

**Pourquoi c'est utile malgré les calques tuilés.** Une peinture sans répétition dépasse les 1024 tuiles d'un charblock
8 bpp : elle ne peut pas défiler en tuilé. Le bitmap fenêtré comble ce cas (grand décor non tuilable). Autres usages du
double tampon : rendu logiciel (v3.0), transitions et diaporamas (image suivante préparée en arrière-plan), vidéo.

**Vidéo.** Possible mais hors de portée d'un asset ordinaire : un flux séquentiel en ROM (32 Mo max), décodé image par
image dans l'IWRAM (delta, RLE ou LZ77 BIOS, palette réduite), synchronisé sur l'horloge audio, avec un seul écrivain du
volume (voir la politique musique des jingles). Il n'entre ni dans la déduplication de tuiles ni dans `palette_alloc` :
c'est un `kind` à part, qui réserve le fond et la palette de la scène pendant la lecture. Le transcodage se ferait hors
éditeur (outil externe type ffmpeg, à trancher : vendorisé ou demandé à l'auteur), et le recadrage ou la cadence restent
des gestes explicites de l'auteur (pas de réduction cachée).

**Ce que le code fait aujourd'hui.** Le bitmap n'existe que dans l'éditeur : `rom_build.py` (lignes 330, 671, 836, 876)
et `gen_scene_query.py` sautent les fonds bitmap avec un avertissement. Il n'y a ni DISPCNT en Mode 4, ni bascule de
page, ni blit. La borne 240×160 est `BITMAP_SIZE` (`models/background.py`) et `_require_bitmap_canvas` /
`encode_by_mode` (`bg_import.py`), qui rognent le surplus.

**Découpage proposé, dans cet ordre.**

| Étape | Contenu | Dépend de |
| --- | --- | --- |
| A | Émission ROM d'un bitmap 240×160 statique : buffer 8 bpp, palette de 256 couleurs, DISPCNT Mode 4, `render_mode` de la scène, cap OBJ à partir de la tuile 512 | (à valider sur émulateur d'abord) |
| B | Bascule de page et rendu hors écran (substrat commun avec le rendu logiciel de la v3.0) | A |
| C | Canvas bitmap **libre** côté éditeur (par exemple 1024×160), puis blit fenêtré en runtime | A, B |
| D | Vidéo : flux en ROM, codec, synchronisation audio | A, B |

**Ce qui rouvre une décision.** L'étape C contredit la décision du 2026-10-15 (« un bitmap a un canvas fixe de 240×160 »).
Elle ne la supprime pas : le canvas serait libre en option, et la fenêtre de 240×160 deviendrait une valeur du runtime.
Le sidecar porte déjà `canvas_size`. Un buffer 8 bpp de 1024×160 fait 160 Ko en ROM.

**À vérifier avant C.** (1) Si la caméra (v0.6) peut piloter l'origine de la fenêtre comme elle pilote les calques
tuilés ; ce serait l'intégration la plus propre. (2) Compressé ou non : sous environ 200 Ko décompressé, une
décompression LZ77 BIOS en EWRAM au chargement de la scène permet un DMA depuis la RAM, plus rapide que depuis la ROM.
(3) Le coût des sprites et de l'UI en bitmap (BG2 seul).

### Réglages et résultats : l'encodage à la fin (réflexion de l'auteur, 2026-10-15)

Pile voulue : **source** (le PNG) → **préparée** (canvas, échelle, miroir, ajustements, `prepare_source`, en mémoire) →
**filtre de compression** (réduction de couleurs, fusion de tuiles, dithering) → **encodée** (tuiles, tilemap, palettes,
buffer bitmap : ce que le build lit). L'encodage appelé à la création d'un asset, avec les réglages par défaut, remplit un
cache : l'asset est utilisable tout de suite. Ce qui ne va pas, c'est que chaque geste de préparation relance un encodage.
*Livré le 2026-10-15* : (1) `apply_bg_encoding` ne touche plus à aucun réglage. Le layout se pose par
`BackgroundAsset.choose_layout` ; (2) le sidecar a deux blocs, `settings` et `encoded` (voir ARCHITECTURE.md), lecture
tolérante d'un sidecar à plat, démos migrées. *Pas fait, à décider* : un seul geste « Appliquer » qui encode (canvas et miroir
compris, aujourd'hui commités à la sortie du geste) ; une empreinte réglages + source qui dise si `encoded` est périmé ;
couper `encode_background` en filtre puis encodage (le chemin « indexé direct » est déjà l'encodage seul) ; les caches par
étage ; que devient une retouche d'après-encodage (surcharges de palette, peinture) quand un réglage change en amont.

### Décisions, état et reste à faire (point du 2026-10-16)

**Décisions prises**

- **Pas d'« Ajuster » à l'import, jamais de réduction cachée.** Un bitmap a un canvas FIXE de 240×160 : l'image garde sa taille
  en (0, 0), déborde, le surplus est rogné. Le canvas est une valeur du fond, pas du layout : bitmap → tuilé garde 240×160.
- **Un encodage ne range que son résultat.** Les réglages (layout, profondeur, méthode, canvas, palettes citées, retouches) sont
  posés par l'appelant (`choose_layout`), jamais par `apply_bg_encoding`. Le sidecar a deux blocs : `settings` et `encoded`.
- **Outils gelés le temps du chantier** (`PREPARATION_TOOLS_ENABLED`) : compression, ajustements, miroir. Recadrer et
  Redimensionner sont supprimés, remplacés par le canvas.
- **L'outil « select », en tête de la barre flottante, EST le mode Canvas** ; la barre reste pour tous les fonds. Un
  **passe-partout** permanent garde visible, grisé, ce qui sort du canvas. Choisir un autre outil applique, Échap annule.
- **Les palettes d'un fond sont des RÉFÉRENCES au catalogue, par nom, jamais des copies.** « + » ajoute une référence ; un
  override (palette dérivée remplacée par une banque) en est une aussi ; leurs couleurs viennent du catalogue et ne se changent
  pas depuis le fond ; éditer une banque met à jour les fonds qui la citent ; le renommage les répare.
- **La peinture de tuiles est un calque attaché au canvas, par case.** Elle ne se pose que sur une palette AJOUTÉE, et se range
  par la POSITION de cette palette : un encodage qui change les palettes dérivées ne la déplace pas, et ne la perd pas.
- **L'encodage vise la fin du traitement, en arrière-plan.** Pile : source → préparée → filtre de compression → encodée. Pas
  d'étapes montrées à l'auteur ; une petite fenêtre d'état (à jour, en attente, en calcul, échec) avec un bouton « Run
  encoding » à l'état « en attente » ; l'encodage part tout seul quand il est bon marché. En attente, on montre l'image
  préparée, avec la mention « pas encore le rendu GBA ».
- **Tests : ciblés en cours de route**, la suite complète seulement à la livraison d'une fonctionnalité.

**Fait (testé en ciblé ; pas essayé à la souris au-delà des premiers essais de l'auteur)**

- Modèle du canvas (`canvas_size`, `image_pos`, `image_size`), `prepare_source`, bitmap sans ajustement caché, canvas bitmap fixe.
- Mode Canvas : outil « select », poignées (Maj, Ctrl), passe-partout, carte « Canvas » de l'inspecteur (la taille se règle en
  tuilé et suit le layout CHOISI, avant même la compression ; en bitmap une ligne « fixe ») ; labels FR/EN.
- Sidecar en deux blocs, lecture tolérante d'un sidecar à plat, `apply_bg_encoding` sans réglage, `choose_layout`.
- Palettes par référence : `added_palettes` et `palette_overrides` dans `settings` ; `resolve_palettes` recompose le cache
  `palettes` (dérivées, overrides, ajoutées) après chaque encodage, « + », remplacement, retrait, ou édition d'une banque ;
  banque disparue = dernières couleurs gardées + avertissement du validateur ; override sans palette dérivée = levé et dit ;
  usages et renommage au courant ; la bande de peinture ne propose que les palettes ajoutées en Paint ; un fond vierge reçoit
  d'office la première palette du projet.
- Retours de l'auteur du 2026-10-16, corrigés : la boîte de compression suit le layout et la profondeur CHOISIS (avant la
  compression) et se range dans l'ordre où l'encodeur résout (4bpp : global colors → dithering → méthode → colors / palette →
  palettes → tiles ; 8bpp : méthode → colors → dithering → tiles, un réglage ne refait que ce qui le suit) ; la carte
  Ajustements se replie ; « Reset » et « Recompute » ; choisir Bitmap (ou Tuilé) fait suivre la carte Canvas, la fenêtre du
  mode Canvas et le cadre du passe-partout ; le miroir a de nouveau un point sur sa barre, la flèche est décalée.

**Reste à faire**

1. ~~Documentation~~ : ARCHITECTURE.md décrit les palettes par référence (fait le 2026-10-16).
1 bis. **Trous dans une grande image, constaté le 2026-10-16, SANS solution encore.** Sur une image de 1650×952 (22 798 tuiles
   uniques), des tuiles noires apparaissent, et le rendu est brouillé par bandes. Deux causes lues dans le code, reproduites sur
   une image de test : (a) l'index de tuile est codé sur 10 bits (`pack_se`) et tronqué en silence au-delà de 1023. Les index
   1024, 2048… retombent sur la tuile 0, d'où un trou sur ~1 tuile sur 1024 ; (b) `merge_tiles` ne fait rien au-delà de
   `MAX_TILES = 6000` tuiles (sa matrice de coûts est carrée), donc « Tiles » est ignoré sans le dire. Notre souhait : une
   tuile retirée doit être REMPLACÉE par une tuile réutilisée visuellement proche, jamais devenir un trou. Pistes à étudier (rien
   n'est décidé) : plafond dur à 1024 index dans l'encodeur, passage préalable bon marché qui ramène les tuiles sous 6000 avant
   la fusion, avertissement clair quand un fond dépasse 64×64 tuiles ou 1024 tuiles uniques. Une couche de fond GBA ne dépasse
   pas 64×64 tuiles (512 px) : une image de cette taille ne tient pas comme un seul fond, quoi que fasse la fusion.
2. ~~Inpainting~~ : fait le 2026-10-17, même règle que la peinture. Un repeint ne cible qu'une palette AJOUTÉE et se range par
   sa POSITION dans `added_palettes` (`BackgroundAsset.repaint_bank` la rend en numéro de banque) ; la bande de peinture ne
   propose plus que ces palettes, en Inpaint comme en Paint. Le sidecar l'écrit sous `settings.tile_repaint` ; l'ancienne clé
   `tile_palette_overrides` (des numéros de banque) se relit, position pour une palette ajoutée, **abandon** pour un repeint
   qui visait une palette dérivée du PNG. Aucune démo n'avait de repeint. Aussi livré : un petit slider du passe-partout dans la
   barre du canvas (l'intensité du grisé, 59 % par défaut, propre à la session).
3. **Un seul geste « Appliquer » imperceptible** : un service d'encodage unique (réglages → pause → calcul → validation,
   le dernier réglage gagne), l'état explicite avec empreinte réglages + source, l'affichage provisoire (image préparée),
   la fenêtre d'état. À trancher : le seuil de coût « bon marché » (~1,5 s mesuré sur le dernier encodage ?), et le
   processus de travail séparé, à MESURER d'abord : les boucles Python pures de l'encodeur peuvent saccader l'interface même
   dans un thread, et un thread ne s'annule pas.
3 ter. **Plan du service d'encodage unique, décidé le 2026-10-17.** Seuil « bon marché » de l'encodage automatique : **~4 s**
   (en dessous il part tout seul après la pause, au-dessus l'état reste « en attente » avec un bouton « Run encoding »).
   **Révisé le 2026-10-17 : seuil éteint par défaut** (`auto_seconds=None`). Bloquer un encodage de 4 s surprenait plus qu'il
   ne protégeait ; le mécanisme reste pour la phase 5. Le
   bouton vit dans la fenêtre d'infos du canvas. Phases : 0 mesure (faite, ci-dessous) ; **1 empreinte et état (faite le
   2026-10-17)** : `encoded.encoded_for`, `encode_settings_fingerprint()`, `encoding_is_current(source_stamp)` ; **2 le service (fait le
   2026-10-17)** : `ui/background_editor/background_encoding.py` (`EncodingJob`, `BackgroundEncodingService`, `ThreadExecutor`),
   un seul chemin, le dernier réglage gagne, un calcul à la fois, validation automatique, états à jour / en attente / en calcul /
   échec, cache de 8 résultats, exécuteur interchangeable ; l'écran n'a plus que `_commit_job` (validation), `_on_encoding_wanted`
   (curseurs), `_on_run_encoding` (bouton) et `_compress_async` (geste, immédiat) ; l'aperçu non appliqué et son bouton « Compress »
   sont supprimés ; **3 la ligne d'état (faite le 2026-10-17)** : dans le canvas, au-dessus des infos (`set_encoding_state`), « En attente / Encodage… / Échec » avec le layout voulu, et le bouton **Run encoding** (attente ou échec) ; l'échec se lit en ligne, plus de fenêtre ; tant que le fond n'est pas à jour le canvas montre l'image préparée de ce qui est voulu (badge « pas encore le rendu GBA »), `service.cancel` quand l'auteur revient aux réglages validés ; le bouton « Recompute » et la barre d'attente de l'inspecteur sont retirés ; **4 nettoyage et build (fait le 2026-10-17)** : `_check_background_encoding_current` (validateur) avertit, sans bloquer, qu'un fond dont les réglages ont changé depuis son encodage embarquerait l'ancien résultat ; (ancienne ligne :) la fenêtre d'état et l'affichage provisoire de l'image préparée ; 4 nettoyage des trois anciens
   chemins, le build qui vérifie l'empreinte, suite complète ; 5 le processus séparé, pour les grandes images.
3 bis. **Phase 0 mesurée le 2026-10-17** (poste de l'auteur, un `QTimer` de 16 ms sur le thread de l'interface pendant l'encodage,
   thread Qt contre processus séparé ; rendu non peint, donc un MINIMUM de saccade ; scripts jetables, rien d'écrit dans le projet) :

   | image | réglage | calcul | thread : écart max entre deux ticks | processus : écart max |
   |---|---|---|---|---|
   | photo 540×540 (4561 tuiles) | 4bpp défaut | 2,4 s | **99 ms** (4 % de ticks perdus) | 17 ms |
   | idem | 8bpp | 0,5 s | 21 ms | 17 ms |
   | idem | 4bpp, cible 256 tuiles | 5,6 s | **81 ms** | 17 ms |
   | photo 1650×950 (23 167 tuiles) | 4bpp défaut | 14,2 s | **562 ms**, 5 gels > 100 ms (7 % perdus) | 18 ms |
   | idem | 8bpp | 2,6 s | 59 ms | 17 ms |

   Lecture : (1) l'encodage est bien plus rapide que le 2026-10-14 (photo 540 : 4bpp défaut 10,7 → 2,4 s, cible 256 32 → 5,6 s,
   8bpp 1,7 → 0,5 s) ; (2) un thread suffit pour une image qui tient dans une couche de fond, un à-coup de ~100 ms au pire ; (3) sur une
   grande image il fait vraiment saccader (562 ms), parce que l'indexation, la déduplication et le regroupement sont des
   boucles Python pures qui gardent le verrou ; (4) un processus séparé garde l'interface fluide (≤ 18 ms) pour le MÊME temps de
   calcul, et le seul moyen d'annuler un calcul de 14 s. Conséquence : bâtir le service avec un exécuteur interchangeable, le
   thread d'abord, le processus (préchauffé, avec le cache d'étage dedans) ensuite. Pour le seuil « bon marché » : une photo de
   540 px prend 2,4 s en 4bpp ; un seuil à 1,5 s la mettrait au bouton, à ~4 s au tout-automatique, à trancher.
4. **Couper `encode_background` en filtre de compression puis encodage** (le chemin « indexé direct » est déjà l'encodage seul,
   et se réutilise tel quel), puis des caches par étage.
5. **Dégeler** compression, ajustements et miroir ; miroir dans l'espace du canvas ; mode « compress view » (barre source /
   compressé) ; constats géométriques en liste de choses à faire ; chasse au code mort (`prep_crop` / `prep_resize` icônes
   inutilisées, étiquette muette).
6. **Limite réelle du canvas tuilé** (cartes de tuiles, streaming) : à lire et à poser à la place du garde-fou de 4096 px.
7. **Sprites** : ils partagent le mécanisme de sous-palettes (`SubPaletteAssetMixin`) et gardent des copies ; non touchés.
8. **À vérifier à la souris** : le cadrage à l'ouverture du mode Canvas (la vue est mise en page tard), l'empilement
   passe-partout / grille 8×8 ; l'opacité du grisé est fixe (60 %), réglable plus tard comme dans Blender.
9. **Données de démo** : la lecture à plat d'un sidecar d'avant les blocs, et celle des anciennes palettes ajoutées en copie, se
   retirent quand les projets ont été resauvegardés ; `tools/create_build_benchmark.py` écrit encore à plat. Le fond `Background`
   de PongAdvanced n'a plus ses traits de peinture (cause non établie : effacés dans l'éditeur, ou défaut du script de migration)
   ; la banque `untitled palette 1`, créée par ce script, n'est plus citée par personne et attend notre accord pour être
   supprimée. Plus aucun script ne touche aux démos : nous y travaillons dans l'éditeur.
10. **Suite complète** à lancer quand le chantier est livré.

### Ordre d'implémentation (proposé)

*Étape 3 livrée le 2026-10-15, vérifiée par tests ciblés seulement (rendu hors écran compris), pas encore à la souris :*
mode Canvas (fichier posé, grisé hors cadre, déplacer / poignées, Maj / Ctrl) et carte « Canvas » de l'inspecteur
(taille du canvas, position et taille de l'image, Ajuster / Remplir / 1:1). Voir ARCHITECTURE.md. Le plafond des champs
est 4096 px, un garde-fou : **la limite réelle du canvas tuilé (cartes de tuiles, streaming) reste à lire et à poser**.
*Retour de l'auteur, 2026-10-15 (premier essai) :* le mode devient l'outil « select », en tête de la barre flottante (qui
reste visible, même pour un bitmap) ; et ce qui sort du canvas reste TOUJOURS visible, grisé, comme le passe-partout d'une
caméra de Blender, corrigé le jour même.

1. *Livré le 2026-10-15.* Le modèle (`canvas_size`, `image_pos`, `image_size`) et `prepare_source` qui compose dans le
   canvas, tests d'identité pixel pour pixel avec l'ancien « recadrer puis redimensionner » (`tests/graphics/test_bg_prepare.py`).
   **Écart avec le texte plus haut** : `resize(box=)` n'est PAS identique à `crop` puis `resize` (le filtre lit au-delà de
   la boîte) ; on rogne d'abord. **Migration** : pas de code dans le produit. Il n'y avait que deux sidecars de démo
   (`Photo1`, `562c…_high`), convertis une fois à la main ; un sidecar qui porterait encore `import_crop` / `import_size`
   les ignore. Aucun template concerné. Outils Recadrer / Redimensionner et leurs fichiers
   (`bg_prepare_overlay`, `bg_prepare_geometry`) supprimés ; compression, ajustements et miroir gelés
   (`PREPARATION_TOOLS_ENABLED`).
2. *Livré le 2026-10-15.* L'encodeur bitmap cesse d'ajuster. **Décision** : pas d'« Ajuster » à l'import, et
   un bitmap a un canvas fixe de 240×160 (posé par `encode_by_mode`). L'image garde sa taille en (0, 0) et **déborde**,
   le surplus est rogné ; plus petite, elle laisse du vide transparent. Aucune erreur à l'import (l'idée d'une erreur
   franche, écrite plus haut, est abandonnée). Tuilé → bitmap garde donc l'image où elle est. **Le canvas est une valeur du fond, pas du
   layout** (tranché par l'auteur) : l'encodage d'un bitmap l'ENREGISTRE (`canvas_size` = 240×160, `apply_bg_encoding`),
   donc **bitmap → tuilé garde 240×160** au lieu de retomber sur la taille de l'image.
   **Tranché par l'auteur le 2026-10-15 : pas d'« Ajuster » à l'import, même en transition.** L'auteur doit voir
   l'image qu'il a importée ; tant que l'interface du plan de travail n'existe pas, une photo trop grande en bitmap
   donne une erreur, et on avance pas à pas. Les fonctions qui ne servent pas ce chantier (à lister avec
   l'auteur : compression, ajustements, recadrage, redimensionnement, miroir) sont **désactivées temporairement** le temps
   de bâtir le canvas, valeur distincte de la taille de l'image.
3. Le canvas : image posée, hors-canvas grisé, déplacement et échelle à la souris, taille du canvas éditable ; les outils
   Recadrer et Redimensionner s'y fondent.
4. Le miroir dans l'espace du canvas.
5. Le mode compress view : la barre source / compressé.
6. Les constats géométriques (déborde, ne couvre pas) comme liste de choses à faire, chacune avec son geste.
7. Libellés (FR d'office), docs, chasse au code mort (`import_crop`, `import_size`, l'étiquette muette).

### Ce que ça ne fait pas

Pas de plusieurs images, pas de panneau de calques, pas de peinture. Ne change ni les algorithmes de compression, ni la
latence des photos, ni les jauges en direct (indépendantes, livrées). Les fonds UI et animés restent hors du modèle dans
un premier temps.

---

## Briques de base et assemblages (`Text` (chaîne) et `Textbox` (boîte))

### D'où vient la question (2026-10-14)

Le menu d'ajout d'interface proposait `Text`, `Container`, `List`, `Image` sur un seul rang. Or trois
sont des **briques** que le moteur dessine telles quelles (texte, conteneur, image) et deux sont des
**assemblages** qui rangent selon une règle (la liste se parcourt, la boîte de texte coupe). La
distinction est celle d'Illustrator : une chaîne se pose en un point, une boîte de texte se dessine
comme une surface.

### Décisions (2026-10-14, de l'auteur)

- **Deux types, un seul emplacement runtime.** `UIText` = une chaîne (une ligne, jamais coupée ni
  alignée) ; `UITextbox` = le rectangle est la largeur de coupe. Même entrée de `g_ui_regions` ; seul
  `UIRegionInfo.nowrap` change le rendu. Ce n'est pas le retour du type « zone de texte » retiré
  (qui ne différait que par l'écrivain) : ici le comportement du rendu diffère.
- **Le mot « textbox » est de nouveau permis** (il était exclu du vocabulaire par v0.3.2).
- **Familles dans le menu** (arbre et toolbar du canvas) : briques = Text, Container, Image ;
  assemblages = Textbox, List.
- **Migration** : tout `kind: "text"` d'avant la séparation se relit en boîte (il coupait déjà) ;
  seule la chaîne écrit un marqueur `point`.
- **`Text` n'est pas un rectangle redimensionnable** : un clic le pose, le canvas n'en montre que
  l'origine (une croix) et le texte, sans cadre ni poignées. `Textbox` garde rectangle et poignées.
- **On écrit dans le canvas**, pour les deux types : double-clic, saisie dessinée avec la police du
  jeu et un curseur clignotant (un champ Qt invisible ne fait que recevoir le clavier). Clic = replacer
  le curseur, flèches, début/fin ; Entrée valide une chaîne, Ctrl+Entrée une boîte ; Échap annule ;
  annulable par l'historique. Un texte lié à la table ne s'édite pas ici.

### Ce que ça touche

`core/models/ui_region.py` (`UITextbox`, `is_text`, `KINDS_BRICK`/`KINDS_ASSEMBLY`), `font_emit.py` et
`gba_engine.h` (`nowrap`), `scene_tree_panel.py` et `canvas_toolbar.py` (menu), `canvas_region_item.py`
(point d'origine, édition en place), `ui_inspector.py`, `project_names.py` (une boîte se cite comme
une chaîne en Lua), tests `tests/interface/test_ui_textbox_type.py`.

### Ouvert

- **L'emprise d'une chaîne reste fixe** (96×16 au canvas, 80×16 depuis l'arbre) : le build s'en sert
  pour réserver la VRAM et coupe au-delà, alors que le canvas ne coupe pas. La faire suivre le contenu
  suppose de mesurer la police au build ; le texte écrit par script n'a pas de contenu connu.
- Le validateur de débordement mesure encore une chaîne comme une boîte.
- La sélection de texte (Maj+flèches, glisser) existe dans le champ mais **n'est pas dessinée** ; le
  glisser est désactivé pendant l'édition.
- Le curseur d'une boîte alignée au centre ou à droite reste calé à gauche.
- Pas de `textbox:draw` côté Lua : une boîte et une chaîne s'écrivent par `interface:get(nom):draw`.
- **Non vérifié à la main** : l'édition en place a été corrigée à trois reprises sur retour de
  l'auteur (raccourcis, déplacement, focus) ; aucun build ROM complet n'a été fait avec `nowrap`.

---

## TextBox (plusieurs entrées pour préparer un dialogue)

### État au 2026-10-17 (livré pour l'essentiel)

Les quatre étapes convenues sont implémentées : modèle de pages, blocs dans l'inspecteur,
prise en compte de toutes les pages au build, puis **Export as table / Update table**.
Le périmètre demandé (préparer les répliques et les rendre accessibles au script) fonctionne.
Le chantier reste ici pour les arbitrages de nommage, de duplication des textes et de
manipulation de l'ordre décrits en fin de section.

### Le parcours livré

- Les TextBox affichent des blocs multi-lignes dans l'inspecteur. Les réglages de police,
  couleur et alignement sont communs à toutes leurs pages ; `Text` conserve son champ unique.
- **+** insère une page après le bloc concerné, crée son entrée dans Texte et lui donne le focus.
  **−** détache une page supplémentaire et conserve son entrée dans Texte. La première page reste.
- Le bloc actif est entouré de rose et prévisualisé dans le rectangle du canvas. Ce choix est
  transitoire : il ne change pas la première page enregistrée pour l'affichage initial en jeu.
- Une boîte vide présente un bloc vide sans créer d'entrée. La première saisie crée l'entrée ;
  le premier ajout crée les deux pages correspondant aux deux blocs.
- Le premier geste d'édition, d'ajout ou d'export reprend le contenu historique : une entrée
  liée reste la même ; un texte local devient une véritable entrée. La simple sélection et
  l'ouverture du projet ne convertissent rien.
- La saisie modifie directement l'entrée de Texte. Les traductions restent attachées à son id.
  Saisie, conversion, ajout, retrait, export et mise à jour de table sont annulables.

### Identités et nommage actuels

`UITextbox.page_ids` conserve l'ordre des références stables ; le contenu reste dans les `Text`.
La première page est résolue par id, avec `text_key` comme pont de compatibilité pour les
lecteurs existants. Les numéros attribués ne sont pas réutilisés après un retrait.

Une nouvelle entrée est rangée sous **scène / nom de l'élément TextBox / numéro**, par exemple
`Village / Dialogue / 01`. Sa clé suit la règle existante de `Text` : segments normalisés,
séparés par `_`, avec suffixe d'unicité en cas de collision. Une entrée déjà liée conserve son
identité, son rangement et ses traductions lors de la conversion.

À la création, le contexte vient de la scène ouverte ; les ajouts suivants réutilisent la
scène d'origine de la première entrée si elle est renseignée. Les règles à affiner pour les
layouts partagés et les renommages de scène/objet sont listées plus bas.

### Export vers Données (contrat implémenté)

**Export as table** crée une Data Table ordinaire, nommée `<Scène>_<TextBox>` avec suffixe
si le nom est pris, et une colonne `replique` de type `text`. Les lignes suivent l'ordre des
pages. Elles contiennent les clés des entrées, jamais une copie des chaînes.

Exemple : `interface:get("Dialogue"):draw(data.Village_Dialogue[1].replique)`.
Les indices commencent à 1. Le script décide quand avancer et quand terminer le dialogue.
Une correction du contenu ou d'une traduction est partagée ; elle ne nécessite pas de mise
à jour de la table tant que les références et l'ordre des pages ne changent pas.

La TextBox mémorise l'id de la table et un jeton d'association, indépendants de son nom.
**Update table** retrouve les lignes par une identité persistante, pas par leur position :
les colonnes ajoutées à la main (portrait, son, locuteur…) restent attachées aux bonnes pages.

Avant une mise à jour, un récapitulatif présente les ajouts, retraits, déplacements,
références de texte rétablies, lignes manquantes recréées et lignes manuelles conservées.
Annuler ce récapitulatif ne modifie rien ; appliquer crée une seule commande annulable.

| Modification dans Données | Comportement de la mise à jour |
| --- | --- |
| Valeur d'une colonne supplémentaire modifiée | Valeur conservée avec sa page |
| Référence de texte modifiée dans la colonne exportée | Référence de la page rétablie, annoncé dans le récapitulatif |
| Ligne exportée supprimée | Ligne recréée pour sa page, autres colonnes à leurs valeurs par défaut |
| Ligne ajoutée manuellement ou dupliquée dans la grille | Ligne conservée à la fin ; une duplication ne copie pas la propriété de l'export |
| Page détachée de la TextBox | Ligne exportée retirée avec ses autres valeurs, annoncé avant application |
| Colonne exportée renommée | Lien suivi ; elle reste la colonne propriétaire |
| Colonne exportée supprimée ou devenue non-`text` | Mise à jour bloquée jusqu'à restauration de la colonne |
| Table renommée | Association conservée par id |
| Table supprimée ou indisponible | Nouvel export possible sous une nouvelle identité, sans adopter une table homonyme |
| Table, boîte ou layout dupliqué | La copie ne conserve pas la propriété de l'export de l'original |

La mise à jour respecte aussi les renommages de clés de texte, y compris lors de son
annulation/rétablissement. Elle ne recopie jamais automatiquement des cellules de Données
vers la liste de pages. Ce parcours réutilise le [pont Texte / Données](#un-pont-entre-lécran-texte-et-les-tables-de-données-créer-un-dialogue),
sans nouvel asset « Dialogue ».

### Build et vérifications réalisées

- Une seule entrée runtime et un seul rectangle réservé par TextBox ; seule la première
  page est dessinée à l'initialisation. La sélection de l'aperçu n'intervient pas au build.
- Toutes les pages et traductions alimentent les glyphes, les polices balisées et les
  diagnostics de débordement/couverture. Une page absente bloque le build avec son numéro.
- Le budget de glyphes animés prend le **maximum** entre pages et langues, jamais leur somme.
  Une portée `[font]` sur une page suivante peut imposer une surface composée ; celle-ci
  reste unique pour la boîte.
- L'index des usages couvre toutes les pages, les scripts et les cellules `text` des tables.
  Les cellules suivent les renommages de clés ; les pages conservent leurs références par id.
- Vérifications du 2026-10-17 : **335 tests passent**, dont un build ROM réel avec devkitPro.
  Le test ROM utilise le véritable export, renomme table et colonne, puis fait lire la deuxième
  réplique depuis Lua. Les marqueurs du journal mGBA confirment le démarrage et l'appel de
  dessin de cette page à la frame 30 ; ce contrôle ne compare pas les pixels de l'écran.

Tests : `tests/text/test_textbox_pages.py`, `tests/text/test_textbox_pages_build.py`,
`tests/text/test_textbox_table_export.py`, `tests/ui/test_textbox_page_editor.py` et
`tests/rom_build/test_textbox_pages_rom.py` (lent ; exécution mGBA si son frontend SDL est présent).
Le modèle et les mécanismes de persistance sont détaillés dans `ARCHITECTURE.md`.

### Reliquat ouvert

Le [chantier des suites dans l’écran Texte](#écran-texte-suites-liées-aux-textbox-et-aux-tables)
prépare les associations inverses, les états et la synchronisation explicite depuis ce nouvel écran.

- **Layouts partagés :** confirmer à l'usage le contexte de nommage actuel, fondé sur la scène
  ouverte puis sur l'origine de la première entrée, ou proposer un choix explicite d'origine.
- **Renommage de scène ou d'objet :** les références restent stables, mais les clés déjà créées
  ne sont pas recalculées automatiquement d'après ces noms. Trancher ce suivi en respectant
  les clés nommées manuellement.
- **Duplication des textes :** une copie de boîte partage actuellement les références de pages,
  tout en détachant son export. Décider si elle doit plutôt créer ses propres textes et traductions.
- **Déplacement d'une page existante :** l'ordre est stocké et pris en compte par l'export,
  mais l'inspecteur ne propose pas encore de geste dédié pour déplacer un bloc ; il permet
  l'insertion après un bloc et le retrait des pages supplémentaires.

### Hors du périmètre livré

Déroulement automatique du dialogue, passage sur appui, temporisation, effet machine à écrire,
choix branchés, arbre de conversation et découpage automatique d'un long texte en pages.
La prévisualisation des traductions dans le canvas reste rattachée au chantier de l'écran Texte.

---

## Écran Texte (suites liées aux TextBox et aux tables)

### Demande et état du chantier (2026-10-17)

L'écran Texte est retravaillé en parallèle pour privilégier la création et l'édition du contenu.
Les entrées partageant un préfixe de clé et un suffixe numérique sont présentées sous un en-tête
commun. Nous souhaitons ajouter **+ / −** sur ces blocs, puis **Create table / Update table**
et **Update TextBox**. Avant ces actions, l'écran doit connaître ses cibles réelles et leur état.

**Étape 1 livrée : contexte des liens en lecture seule.** `core/text_sequence_context.py` résout
les correspondances par ids, ordre et occurrences. L'en-tête affiche la TextBox, la table exportée
et les écarts observés ; l'infobulle détaille toutes les candidates, leurs scènes et les usages
en cellules. La table est reconnue par son id et son jeton, puis ses colonne et lignes gérées
sont vérifiées. Les liens partiels ou multiples ne créent aucune association implicite.

Les filtres conservent le périmètre complet du groupe, trié numériquement comme à l'écran.
Les notifications d'usages actualisent le contexte sans reconstruire les champs ni déplacer le
curseur ; la revisite recalcule aussi les références. Aucune écriture, migration ou identité de
suite n'est créée par cette lecture. Les états décrivent les écarts, sans attribuer de direction
de mise à jour au groupe visuel. Validation : 77 tests ciblés, dont 20 nouveaux tests de contexte
et d'intégration, et contrôle visuel du cas réel `SCR_Arena / textbox_2` avec table conforme.
**Étape 2a livrée : identité persistante et Relink.** `core/text_sequences.py` conserve les
suites explicitement adoptées dans le champ optionnel `sequences` de `texts.json`, avec ids de
textes, ordre/occurrences et placements attendus. Link mémorise une suite ; Relink peut adopter
une correspondance partielle puis réintégrer les entrées choisies en une commande annulable.
La destination proposée d'un ancien groupe sans historique est indiquée dans l'infobulle ;
elle est reconstruite depuis l'ordre de la boîte et les conventions des entrées présentes,
pas présentée comme un ancien rangement récupéré avec certitude.

L'en-tête présente le nombre d'entrées hors du groupe et un bloc repliable avec Retrouver,
Relink individuel et Relink tout. La suite demeure visible même vidée de toutes ses entrées.
Le contenu, les traductions et les lignes de table ne sont ni recréés ni supprimés par Relink ;
les références suivent les renommages de clés habituels. Les filtres restent un affichage.
L'association de boîte utilise l'id du layout et un `UITextbox.sequence_id` attribué uniquement
à cette première action ; les duplications détachent ce lien. Renommer le préfixe ou déplacer
le dossier complet conserve l'identité de suite ; déplacer une feuille crée un écart.
Un état des références gérées de table est mémorisé, sans les contenus ni les colonnes libres.
Les collisions de clés et destinations déjà associées sont refusées.

**Apply livré pour les suites liées à une TextBox.** `core/text_sequence_apply.py` prépare un
plan sans mutation depuis la suite complète, indépendamment des filtres et de la langue.
Les entrées écartées sortent des projections mais leurs `Text` et traductions restent disponibles.
Les occurrences sont conservées et les nouvelles entrées du groupe sont ajoutées à la suite.
Le plan réutilise le rapprochement de lignes de `plan_export(..., text_ids=...)`, sans créer de
boîte invisible ni dupliquer cet algorithme. La numérotation consommée par une nouvelle page
est réservée pour les créations suivantes dans l'inspecteur.

**Apply reste dans l’écran Texte, sans fenêtre modale.** Le bouton applique la suite
complète en un pas d’historique. L’option de création de table, les erreurs et les conflits
restent dans le bandeau inférieur. Une table liée absente, un lien ambigu ou un schéma invalide
sont refusés sans redirection ni recréation silencieuse. Un groupe ancien peut être adopté
explicitement par Apply, puis projeté, en un seul pas d’historique.

Un conflit avec une modification de TextBox ou de références gérées en table demande une case
explicite dans le bandeau. Cette acceptation est périmée dès que l’état concerné change, même
si seul un champ libre en table a changé. Contenus et traductions restent compatibles avec
les mêmes ids. Les références de textes absents sont nommées dans l’écran ; chaque référence
peut être retirée explicitement et de façon annulable avant Apply.
L'application et l'undo coordonnent suite, layout et table, en conservant les objets de ligne
pour les commandes de cellule antérieures. Les autres usages des textes ne sont pas des cibles.
Les notifications rafraîchissent Données, Disk et le contexte de texte, avec conservation des filtres.
Validation : 171 tests ciblés, plus contrôle visuel en lecture seule du cas réel de la capture.
**Commandes +/− et bandeau fixe livrés.** Chaque entrée possède ses contrôles en bas à droite.
`EditTextSequenceCmd` insère un `Text` vide après l'entrée choisie dans l'ordre de la suite ;
le champ prend le focus, y compris sous un filtre ou pendant la traduction. L'entrée neuve
reste temporairement visible sous le filtre sans modifier celui-ci. Une première action peut
adopter explicitement un groupe libre ou lié. Le compteur `TextSequence.next_number` réserve
les numéros consommés, même après retrait, Apply et suppression ultérieure d'un texte écarté.
Apply transmet aussi ce compteur à la TextBox pour ses créations suivantes.

**Révision du 2026-10-17 : liste explicite et retrait prévisible.** À la première
édition structurelle, la suite conserve sa liste ordonnée indépendamment du classement.
Les numéros affichés sont les positions continues `#01`, `#02`… ; les clés et ids restent
stables. Le − retire exactement l'occurrence choisie, sans déplacer le `Text`. Annuler
restaure sa position. Le + insère après la ligne choisie. Les deux boutons utilisent des
icônes dans le champ, sur une ligne de contrôles distincte du défilement. La zone de saisie
s’agrandit avec le contenu jusqu’à une hauteur plafonnée. Le fond utilise `BG_INPUT` et les
libellés restent transparents, conformément à la charte.

Pour une suite liée, le texte retiré reste disponible pour ses anciennes références jusqu'à
Apply. Apply actualise les pages et lignes gérées, puis supprime le texte et ses traductions
s'il n'a plus aucun usage. Les scripts, autres éléments d'interface, autres suites et cellules
manuelles ou colonnes libres protègent un texte partagé. Le bandeau explique les conservations ;
les usages sont revérifiés à l'application. Sans destination, un texte exclusif est supprimé
immédiatement. Les deux opérations sont annulables, données et traductions comprises.

Le Finder et la liste centrale utilisent la même projection des entrées actives et sont
rafraîchis ensemble à chaque ajout, retrait, undo et redo. Un texte partagé conservé reste
accessible comme entrée libre, sans déplacement de son rangement. Une suite vide reste
visible avec un compteur nul et son bouton +. Les anciennes suites sont lues sans migration
sur ouverture ; leur première édition structurelle rend leur ordre explicite.

Les commandes générales d'ajout/suppression ont quitté la barre supérieure ; Nouveau texte
reste disponible en bas pour les entrées libres et les projets vides. Le contexte technique
de correspondance reste consultable en infobulle, sans ligne « Partial correspondence ».
Le nombre précis d'entrées écartées/à ajouter et les actions Link/Relink/Apply vivent dans un
bandeau fixé sous la liste et suivent le groupe actif. La liste des entrées écartées se déplie
dans une zone de défilement plafonnée. Validation de la correction : tests ciblés sur Apply
direct, les conflits, les références manquantes et la hauteur des champs, avec contrôle visuel
dans l’écran complet sur une fixture isolée. Reste la création de table autonome sans TextBox.

### Séquences dérivées, liées ou libres (décidé le 2026-10-18 (REMPLACE l'adoption explicite))

L'auteur ne veut jamais « mettre à jour » une table ou une TextBox à la main : la
synchronisation est **intrinsèque à l'état**. Tout ce qui précède dans ce chantier
(`TextSequence`, Adopt/Relink/Apply, `sequences` dans `texts.json`, `textbox_export` et
marqueurs `$editor`, `sequence_id`, `table_export_*`) est **retiré** au profit de ce qui suit.

- **Séquence = dérivée, jamais stockée.** Les textes dont la clé finit par `_<chiffres>`
  (n'importe quel suffixe : `_1`, `_Page01`, `_007`) et qui partagent le même préfixe forment une
  séquence à partir de **deux textes**. L'ordre est la valeur numérique du suffixe. Aucune
  identité, aucun fichier : renommer ou ranger un texte la fait apparaître ou disparaître.
- **État d'une séquence : liée ou libre**, calculé. *Liée* = au moins un consommateur (une table
  de l'écran Données dont `text_link.prefix` est ce préfixe ; une TextBox qui la lit). *Libre* =
  aucun : l'en-tête propose **Link to existing table** et **Create table**.
- **État d'une table : liée ou libre.** *Liée* = `text_link` posé. *Libre* : l'écran Données
  propose **Link to text sequence**. Une table liée a ses lignes pilotées par la séquence (une
  ligne = une clé de la colonne `text`), les autres colonnes sont à l'auteur.
- **Synchronisation intrinsèque.** Ajouter, retirer, renommer ou réordonner un texte d'une
  séquence liée réécrit ses consommateurs **dans la même commande** (un seul pas d'historique,
  Ctrl+Z restitue texte et lignes). Il n'y a ni bouton Update, ni aperçu périmé, ni conflit.
  Une page retirée emporte sa ligne, colonnes libres comprises.
- **Ce qui reste du code actuel :** `core/text_table_link.py` (`text_link`, `LinkTableCmd`,
  `UnlinkTableCmd`), généralisé de `_PageXX` à `_<chiffres>`.
- **Livré le 2026-10-18 :** dérivation pure (`core/text_sequences.py`) ; tables synchronisées dans
  l'historique (`after_execute`) ; en-tête Texte lié/libre ; **`page_ids` retiré**, une TextBox
  suit une séquence par `sequence_prefix` (ou affiche son `text_key`), les pages sont dérivées ;
  ancien moteur supprimé (adoption, Apply, export de TextBox, ~17 fichiers de tests). Les anciens
  `page_ids`, `sequences` et `$editor` sont ignorés à la lecture : une boîte multipage d'avant
  garde son `text_key` et doit être reliée à la main à sa séquence.
- **Reste :** contrôle visuel de l'en-tête et de l'inspecteur ; test ROM `test_textbox_pages_rom`
  adapté mais non relancé (devkitPro) ; libellés `txtseq.*` orphelins à purger.

### Le chemin est dérivé de la clé (plus de libellés stockés (décidé le 2026-10-18))

`Text.path` (les libellés des niveaux, avec accents et espaces) dupliquait la clé et se
désynchronisait dès qu'un renommage ne le recalait pas (Finder à `Page03` pour la clé `Page02`,
après une renumération). **Il n'est plus stocké** : `Text.path` est une propriété en lecture
seule, les segments de `key`. `texts.json` n'écrit plus `path` ; un ancien fichier se lit
sans erreur (le champ est ignoré, sauf pour dériver une clé manquante).

- **Ranger, c'est renommer la clé.** Glisser-déposer, renommer un dossier du Finder, éditer un
  niveau depuis l'inspecteur : chacun calcule les nouvelles clés (`Project.text_path_keys`) et les
  applique en un lot (`rename_text_keys`), scripts, cellules de table, boîtes et séquences liées
  suivent. Plus de renommage « cosmétique » d'un libellé.
- **Affichage** : le segment tel qu'il est dans la clé. Les libellés libres (`La forêt`) disparaissent ;
  taper `La forêt` pour un dossier donne le segment `LaForet`.
- **Retiré** : le champ `path`, `path_from_key`, l'alignement des libellés après chaque renommage,
  l'ancien `SetTextPathCmd` à deux modes (libellé seul / clé).

### Simplification de la clé (décidée le 2026-10-18)

Deux exceptions retirées, pour qu'il reste un comportement attendu et fiable :
- **`auto_key` est supprimé** (champ, badge, cadenas, `RelinkTextKeyCmd`, renommage de feuille
  du Finder qui visait la clé). La clé porte la structure ; renommer un libellé ne la touche
  jamais ; la renommer ou déposer le texte dans un autre dossier la change partout où elle est
  citée. Les anciens `texts.json` qui contiennent `auto_key` se lisent sans erreur.
- **Une page peut apparaître plusieurs fois dans une TextBox.** Aucun besoin n'est présumé :
  la règle n'a simplement pas de cas particulier. Seule la renumérotation d'un texte partagé
  reste refusée, puisqu'on ne peut pas renuméroter une même entrée deux fois.

### Constats vérifiés dans le code et le projet de la capture

| Sujet | État actuel |
| --- | --- |
| Groupe numéroté | Vue calculée à partir du dossier et du préfixe ; Link/Relink peut désormais lui donner une identité éditoriale persistante |
| Numérotation | Les suffixes numériques suffisent au regroupement ; ils n'ont pas besoin d'être consécutifs |
| Ordre à l'écran | Tri numérique pour un groupe libre ; ordre mémorisé de la suite après adoption, occurrences conservées dans le modèle |
| Bloc et en-tête | `TextEntry` porte un `Text` ; l'en-tête porte le contexte calculé et les actions Link/Relink, l'association persistante reste dans le modèle |
| Usages | `TextUsageIndex` fournit les scripts, les couples `(layout, élément)` et les cellules `(table, ligne, colonne)`. L'écran affiche des compteurs et détails, sans résoudre un propriétaire de suite |
| TextBox | `page_ids` donne l'ordre réel des textes par id ; `table_export_id` et `table_export_token` désignent son export |
| Table exportée | `DataTable.textbox_export` conserve la colonne et les paires `text_id` / `row_id` ; les lignes gérées portent leur marqueur `$editor` |
| État de mise à jour | `plan_export` sait comparer une table à sa TextBox. Il ne compare pas une suite modifiée dans Texte à une TextBox encore inchangée |
| Actions de Texte | Le + général crée une entrée dans le rangement sélectionné ; la suppression générale supprime des `Text`. Ni l'une ni l'autre ne modifie les pages d'une TextBox |
| Rafraîchissement | Usages invalidés puis recalculés paresseusement ; contexte des liens actualisé sans reconstruire les champs, relecture à la revisite et après undo. Aucun historique de synchronisation de suite n'est encore maintenu |

**Cas concret vérifié sans modifier les fichiers :** dans `Project Demo/PongAdvanced`, le groupe
`scr_arena_textbox_2` contient trois textes. Leurs ids, dans l'ordre affiché, correspondent aux
pages de `SCR_Arena.layout / textbox_2`. La table `SCR_Arena_textbox_2` porte le même id et le même
jeton que le lien de la boîte ; ses enregistrements de pages sont cohérents avec les trois ids.
Les données nécessaires existent donc pour ce cas ; leur exploitation manque à l'écran Texte.
Ce constat ne permet pas de généraliser à tous les groupes ayant un nom ressemblant à une boîte.

### Les pièges à traiter avant les boutons

- **Un nom n'est pas un lien.** Un groupe peut être sans usage, référencé par plusieurs TextBox,
  partagé entre scènes ou cité dans plusieurs tables. Une cellule `text` est un usage, pas la
  preuve que sa table est l'export géré de la boîte.
- **Le suffixe n'est pas l'ordre de lecture.** Une insertion entre 01 et 02 peut créer la page 04 :
  la TextBox lit `01, 04, 02, 03`, tandis que le groupe actuel affiche `01, 02, 03, 04`.
  Renommer ou ranger une entrée peut aussi la faire sortir du regroupement visuel sans changer
  ses références. Ne jamais renuméroter les clés pour remettre artificiellement ces ordres d'accord.
- **Les filtres ne définissent pas la suite.** Recherche, dossier, Empty, Unused et langue peuvent
  ne montrer qu'une partie des membres. Les opérations structurelles doivent porter sur la suite
  entière, en annonçant leur portée, jamais sur la seule liste des blocs visibles.
- **Le contenu est déjà partagé.** Modifier une source ou sa traduction ne nécessite aucune copie
  vers la boîte ou la table. Ce sont les membres et leur ordre qui peuvent diverger.
- **Un retrait n'est pas une suppression globale.** Réutiliser la suppression générale de Texte
  pour le − d'une suite pourrait casser une autre boîte, une table ou un script.
- **Une comparaison ne révèle pas toujours l'intention.** Si la suite et la boîte ont changé
  séparément depuis leur dernier accord, un simple remplacement perdrait l'un des deux travaux.

### Première étape (résoudre les références et exposer leur état)

Créer une requête métier partagée, indépendante des widgets, par exemple
`resolve_text_sequence_context(project, text_ids)`. Elle doit conserver l'ordre et les occurrences,
retourner les candidats et les raisons des états, et ne rien modifier ni enregistrer.

1. Retrouver les TextBox par leurs références effectives : correspondance ordonnée complète,
   même ensemble dans un autre ordre, recouvrement partiel et usages extérieurs. Pour une boîte,
   retrouver aussi le layout et toutes les scènes qui l'instancient.
2. Résoudre la table réellement liée par id et jeton ; vérifier la colonne, les lignes gérées,
   leurs références et les lignes manuelles. Distinguer cet export des autres usages de table.
3. Ne désigner une cible unique que lorsqu'elle est établie. Plusieurs candidats restent une
   liste explicite ; aucune cible ne doit être choisie à partir du nom du groupe.
4. Fournir un contexte à l'en-tête sans en faire un propriétaire : cibles identifiées, état
   de chacune, détails consultables et actions permises. Les compteurs d'usage restent distincts.

Les correspondances partielles servent à expliquer et proposer des candidats ; elles ne suffisent
pas à créer une association persistante. Une première association doit être explicite lorsque les
références ne la déterminent pas sans ambiguïté. Une entrée utilisée plusieurs fois dans une boîte
ne doit pas être confondue avec une seule occurrence dans le groupe visuel actuel.

| État à présenter | Signification / conséquence |
| --- | --- |
| Sans lien | Textes libres ; création d'une association possible |
| À jour | Membres, ordre et références de la projection concordent |
| TextBox à mettre à jour | La suite a changé ; la boîte conserve son dernier état synchronisé |
| Table à créer / à mettre à jour | Export absent ou projection différente ; les valeurs des colonnes libres ne rendent pas la table « périmée » |
| Référence indisponible | Boîte, layout, table, colonne ou texte manquant ; proposer une action adaptée |
| Plusieurs destinations | Choisir la cible concernée avant une opération structurelle |
| Modifications concurrentes | La suite et sa projection ont changé depuis leur dernier accord ; montrer les différences avant de trancher |

« À mettre à jour » suppose une association et une direction connues. Pour un ancien groupe sans
historique commun, présenter un écart à résoudre plutôt que prétendre savoir quel côté est récent.
Les états de TextBox et de table sont indépendants : l'une peut être à jour et l'autre non.

### Modèle retenu (première partie livrée, projections à poursuivre)

**Recommandation : une suite éditoriale persistante et ordonnée**, distincte du simple groupe de
présentation, identifiée par un id stable et contenant des références de `Text`. Son libellé,
son préfixe et son rangement ne déterminent pas son identité. Cette donnée reste dans l'éditeur ;
elle ne constitue ni un nouvel asset Dialogue, ni un moteur de conversation.

Le bouton **Update TextBox** implique que la suite puisse évoluer sans modifier immédiatement
la boîte. Cette liste et son ordre doivent survivre à une réouverture, y compris sans TextBox.
Les seules clés numérotées et les compteurs d'usage ne suffisent donc pas à porter ce contrat.
Une association vers la boîte résiste à son renommage : l'id d'asset du layout et le nouvel
identifiant opaque `UITextbox.sequence_id` sont mémorisés au moment de l'association explicite.
La duplication retire cet identifiant sur la copie.

Conserver les derniers états synchronisés des projections pour distinguer une modification d'un
seul côté d'un conflit. À la reprise des projets existants, préserver les ids de textes, jetons
et ids de lignes déjà exportées. Ne pas créer de suites en masse à la simple ouverture de l'écran :
la lecture déduit un contexte ; une première action explicite peut matérialiser la suite.

Pour une suite liée, l'ordre affiché doit suivre cette donnée, et non les suffixes des clés.
Les groupes libres non matérialisés peuvent garder leur présentation actuelle.

### Contrat proposé pour les actions

- **+ sur un bloc :** créer une nouvelle entrée après celui-ci dans la suite complète, lui donner
  le focus et préserver toutes les identités existantes. Ce n'est pas un retour à la ligne dans
  le texte courant. Le compteur de nommage ne doit pas réutiliser les numéros retirés.
- **− sur un bloc :** retirer son occurrence sans déplacement ; Apply supprime le `Text` et ses traductions s'il n'a plus d'autre usage (révision du 2026-10-17).
  Les projections deviennent à mettre à jour ; leurs changements ne se font pas en silence.
- **Create table :** exporter la suite (création depuis une suite sans TextBox encore à faire) ; **Update table :** projeter son ordre
  et ses références avec le même récapitulatif et la même préservation des colonnes personnalisées
  que l'export existant. Les lignes manuelles restent traitées selon ce contrat.
- **Update TextBox :** proposer la liste et l'ordre à appliquer à la cible choisie, sans toucher à
  son rectangle, sa police ou ses couleurs. Annoncer un éventuel changement de première page,
  puisque celle-ci constitue l'affichage initial en jeu.
- Chaque geste est annulable avec ses créations et associations. Apply coordonne explicitement
  les destinations associées ; l'export depuis l'inspecteur de scène reste un parcours distinct.
  Une traduction utilise la même structure de suite que
  la source : ajouter une entrée ne crée pas une structure indépendante pour cette langue.

L'export partage désormais son rapprochement de lignes avec la source ordonnée passée par
`text_ids`. L'extraction d'un export autonome sans TextBox reste à faire. **Ne pas simuler une boîte
invisible pour exporter un groupe libre**, et ne pas recopier l'algorithme de rapprochement des
lignes dans l'écran Texte. Une table projetée depuis la suite ne doit pas rester prisonnière de
l'ancien ordre d'une TextBox que l'auteur n'a pas encore choisi de mettre à jour.

### Ordre d'implémentation recommandé

1. **Contexte en lecture seule, livré :** requête inverse, état des cibles, branchement à l'en-tête et
   tests des groupes libres, liés, partiels et ambigus. Aucun +/− structurel à ce stade.
2. **Identité et ordre, première partie livrée :** modèle de suite, associations stables,
   état de référence, reprise explicite du cas existant et Relink individuel/en lot.
3. **Apply, livré pour les suites liées :** plan d'export partagé, aperçu des changements et
   application aux seules destinations associées, avec comparaison et gestion des conflits.
   Commandes +/− et bandeau fixe livrés ; reste l'export autonome des suites sans TextBox.
4. **Réactivité et validation :** invalidations après édition structurelle, commandes de scène,
   modifications de table, renommage, suppression, watcher et undo/redo. Conserver le focus,
   le curseur et les filtres lors d'une simple actualisation de l'état.

Les suites sont désormais persistées avec les textes dans `texts.json` ; l'association explicite
persiste aussi l'identité de boîte dans le layout. Les autres projections passeront par leurs
commandes de persistance propres. Les notifications actuelles d'usages actualisent aussi le
contexte de suite ; Apply notifie aussi les différentes destinations après application et undo.
Validation de l'étape 2a : 139 tests ciblés sur les suites, le contexte, les pages/export,
les références, l'écran Texte, les déplacements, la sauvegarde de projet et la duplication.

### Critères de validation

- Cas réel `SCR_Arena / textbox_2` : résolution de la boîte et de sa table exportée, état cohérent.
- Groupe numéroté libre, suffixes troués, clé renommée, entrée rangée ailleurs : aucun lien inventé.
- Insertion donnant `01, 04, 02, 03` : ordre préservé dans Texte, TextBox et table après mise à jour.
- Filtres et langues : opérations sur la bonne suite complète, sans perdre les traductions.
- Plusieurs boîtes/scènes/tables et références répétées : destinations et occurrences explicites.
- Retrait d'une entrée partagée : aucun `Text` supprimé, autres usages intacts.
- Création de table sans boîte ; mise à jour de table alors que la boîte est encore en retard.
- Conservation des portraits/sons/autres colonnes, lignes manuelles et identités de lignes.
- Modification indépendante dans le Scene Manager ou Données : écart/conflit expliqué ; aucun
  remplacement silencieux ni aperçu périmé appliqué.
- Renommage, duplication, cible supprimée, undo/redo, sauvegarde/réouverture et changement d'écran.
- ROM lisant les répliques de la table exportée ; aucun nouveau déroulement automatique du dialogue.

### Points à trancher avant la deuxième étape

Adopter le modèle de suite proposé et sa place de stockage ; définir l'identité des occurrences
si une même entrée est répétée ; fixer les associations autorisées et la sélection d'une cible
parmi plusieurs ; préciser le retrait du dernier bloc et l'emplacement des actions communes dans
l'en-tête. La direction de synchronisation et la résolution des modifications concurrentes doivent
être établies avant d'activer Update TextBox ou de changer le propriétaire d'un export existant.

---

## Une seule règle de nom libre

### D'où vient la question (2026-10-09)

En préparant le chantier « Source ≠ asset » (un nom d'asset est unique dans le projet, un nom déjà pris est
suffixé), un balayage du code a trouvé **huit** façons de suffixer un nom déjà pris :

| Règle | Suite | Où |
| --- | --- | --- |
| `unique_name` | `coin`, `coin_2`, `coin_3` | scènes, prefabs, scripts, caméras (dispatcher), pistes, variables, dossiers |
| copies à la main de la même règle | `_2`, `_3` | groupe de dossier, id de composant, table et colonne de données, variable d'export |
| numéro sur 2 chiffres | `boite_bas`, `boite_bas_02` | éléments d'interface, clés de texte, mise en page renommée ou créée pour une scène |
| duplicata d'acteur | `Hero_copy`, `Hero_copy2` | `_copy_name` |
| instance de prefab | `Ball`, `Ball_1`, `Ball_2` | dispatcher |
| caméra de départ | `Camera`, `Camera 2` | `Project.seed_default_camera` |
| toujours numéroté, sans séparateur | `axis1`, `input1`, `lang1`, `tag1`, `sequence1`, `Part1` | cartes de l'inspecteur |
| acteur posé au canvas | `Actor_0`, `Actor_1` | `canvas_tools` |
| assets, polices, palettes | `Palette`, `Palette 2` | `asset_kinds._unique` |

Deux gestes donnaient deux suites différentes pour le même objet (un acteur depuis l'arbre ou depuis le canvas ;
une caméra de départ ou ajoutée ensuite).

### Décision (2026-10-09)

**Une seule règle : `base`, puis `base_2`, `base_3`…**, celle de `unique_name`. Elle vit dans
`core/models/unique_name.py` (couche modèle, sans dépendance), et tout le monde l'appelle. Sont **supprimés**,
pas conservés à côté : `_copy_name` (un duplicata d'acteur devient `Hero_2`, la distinction « copie » /
« création » est abandonnée), `unique_region_name` et `unique_element_name`, `asset_kinds._unique`, et chaque
boucle écrite à la main. Les noms déjà enregistrés dans un projet ne changent pas : seule la suite des
NOUVEAUX noms change.

---

## Source ≠ asset (l'arborescence du disque et l'id stable)

### D'où vient la question (2026-10-09)

L'auteur a rangé ses sons dans une arborescence (`assets/sfx/platformer/wav/…`, 556 fichiers dont 175 `.wav`
réels). L'éditeur ne la voit pas : la synchronisation fait `glob("*")` à plat
(`asset_reconciliation.reconcile_sfx_and_music`), et l'identité d'un asset est **le nom du fichier sans
extension** (`path.stem`). Le sidecar `GOAL.json` porte `"name"` et `"asset"`, aucun id. 10 noms de `.wav`
apparaissent dans plusieurs dossiers (`coin`, `die`, `fireball`…).

Le but à terme : un dossier `assets/` **vierge** que l'auteur organise comme il veut (modèle Unity / Godot /
Unreal), puis un clic droit sur une **source** → *Create asset* (l'auteur choisit le type d'asset à en tirer).
Un script ne référence jamais une source, toujours un asset.

### Ce que font les trois moteurs

Tous séparent l'identité de l'emplacement : Unity un GUID dans un `.meta` voisin du fichier ; Godot le chemin
`res://` plus, depuis la 4.4, un `uid://` ; Unreal le chemin de package complet. Deux `coin` dans deux dossiers
ne se heurtent dans aucun des trois, et l'auteur choisit une référence en la sélectionnant plutôt qu'en tapant
un nom.

### Ce qui existe déjà

| Objet | Identité | Où |
| --- | --- | --- |
| Variables | id opaque, nom renommable | `core/models/ids.py`, `project_variables.py` |
| Textes | id opaque, la clé est proposée | `assets/texts.json`, `project_texts.py` |
| Dossiers d'assets et de scène, notes du Graphe | id opaque, imbricables (`parent_id`) | `core/asset_folder_store.py`, `core/scene_tree_state.py` |
| **Assets** (sfx, sprites, fonds, musiques…) | **le nom** | sidecars `*.json` |

`asset_folder_store` range des assets par dossiers d'éditeur. **Ses `members` sont des ids depuis le 2026-10-10**
(famille Scenes, la seule qui en ait) ; ils étaient des noms, et renommer ou déplacer le fichier d'une scène la
faisait sortir de son dossier. Le store ne connaît que des clés opaques ; `ResourceStore.id_of(nom)` /
`name_of(id)` traduisent, et le Graphe (qui pense en noms de carte) ne traduit qu'en deux méthodes
(`_scene_id`, `_folder_of_scene`). Aucun outil de migration : un `asset-folders.json` d'avant garde des noms que
`prune` efface à l'ouverture (aucun projet connu n'en portait).
**Pour étendre à une autre famille :** lui bâtir un `FolderScheme` qui passe `asset.id`, et ne lancer son `prune`
qu'une fois la famille entièrement chargée. Une famille à chargement différé (sprites, fonds, sons) n'a pas
tous ses ids tant qu'elle n'est pas lue, et un `prune` anticipé viderait ses dossiers.

### Décisions verrouillées (2026-10-09)

- **Un seul format d'id, partout : 12 chiffres hexadécimaux (48 bits), en chaîne**, tirés par `ids.new_id`
  avec garde d'unicité. **Livré le 2026-10-09** pour les variables, les textes (et leurs sides), les dossiers
  (assets et scènes) et les notes du Graphe ; avant, les deux premiers étaient des entiers de 12 chiffres
  décimaux et les autres un `uuid4().hex` de 32 caractères. Le projet n'étant pas diffusé, aucune lecture de
  l'ancien format n'est conservée : `tools/migrate_ids_to_hex.py` convertit un projet (réécriture textuelle,
  idempotente), appliqué aux démos `PongAdvanced` et `Platformer`. Un nom de variable ne peut pas avoir la
  forme d'un id (`{"var": <id|nom>}` les distingue à cette seule forme). La sauvegarde SRAM garde les 8
  derniers chiffres de l'id (`save_id32`).
- **Le sidecar d'un asset porte un `id` opaque** (`ids.new_id`), c'est lui qui est stocké par les références
  de données. *Pas encore fait*. Seule la forme de l'id est livrée. Le nom reste renommable ; le chemin du fichier
  source est un simple emplacement. Même règle que les variables et les textes : un id dans les données, un nom lisible dans le Lua.

- **Le nom d'asset est unique dans le projet** (2026-10-09). Il se tranche à la création (*Create asset*
  propose la stem de la source et refuse ou suffixe un nom déjà pris) ; les SOURCES peuvent être homonymes
  librement. Le Lua écrit toujours `sfx.play("coin")` et les symboles C n'embarquent aucun nom de dossier.
- **Deux vues, deux questions, pas de conflit de dossiers** (2026-10-09). L'*asset finder* et les panneaux de
  famille (Sound…) montrent ce qui EXISTE dans le projet, les assets, rangés par type dans des dossiers
  virtuels (`asset-folders.json`) ; le panneau Sound reste une liste plate. Un futur onglet **Disk** de la
  zone Build / debug, façon Unity / Unreal, montrera une représentation fidèle du disque : les vraies
  arborescences et les SOURCES. C'est là que vit *Create asset* (clic droit sur une source). Un asset n'est pas
  une source : le même son ne s'affiche donc jamais à deux endroits.

- **L'asset et sa source vivent indépendamment** (2026-10-09), comme dans Unreal et non comme dans Unity (où le
  `.meta` voyage avec le fichier). L'asset a son propre fichier, avec son `id` ; il ne fait que POINTER sa
  source (`asset`, un chemin). Déplacer, renommer ou supprimer la source sur le disque ne détruit, ne renomme et
  ne déplace jamais l'asset : ses références (par id) tiennent.

- **Le fichier de l'asset vit dans le dossier `assets/` de l'auteur** (2026-10-09), comme avant, et non sous
  `project/`. Il est créé à côté de sa source par défaut, puis l'auteur le déplace où il veut, comme dans Unity.
  `project/` reste réservé à ce qui n'a pas de fichier source à relier (les scènes : un dossier virtuel
  suffit à les ranger). Les scènes pourraient, plus tard, vivre elles aussi dans `assets/`.

- **Source déplacée ou absente : *Relink source* et erreur de build** (2026-10-09). L'asset est « sans
  source » : il reste dans le projet, signalé, et l'auteur le relie à un autre fichier. Le build l'indique comme
  une erreur claire tant que la source manque (le mécanisme des assets manquants existe déjà). Aucune copie des
  données importées n'est conservée dans l'asset : la légèreté du projet passe avant l'autonomie de l'asset.

- **Un nom déjà pris est suffixé, comme partout dans l'éditeur** (2026-10-09). Le but est d'éviter la
  collision de NOM, pas de départager des fichiers : l'éditeur réutilise `unique_name`
  (`core/command_dispatcher.py`) (`coin`, `coin_2`, `coin_3`…) à *Create asset* comme au scan de `assets/`.
  Le scan retrouve chaque asset par son `id`, où qu'il soit ; si un fichier copié dans l'Explorateur apporte un
  nom ou un id déjà pris, il reçoit un nouvel id et un nom suffixé, et le journal le dit. Aucune notion
  d'« original » ni de date de fichier.

### Ce qu'il faudrait trancher avant d'ouvrir

1. **Source sans asset.** Visible dans l'onglet Disk (grisée si le format n'est pas pris en charge, avec
   infobulle) ; absente de l'asset finder et du projet tant qu'aucun *Create asset* n'a été fait.
2. **Migration.** Les sidecars existants restent où ils sont et reçoivent leur id ; `asset-folders.json` passe
   de membres-par-nom à membres-par-id.

### Ordre d'implémentation (proposé)

1. **Livrée le 2026-10-09.** L'id dans le sidecar + migration, sur les SFX (famille pilote). Rien de visible : le
   panneau Sound ne change pas. `Sfx.id` (pas encore sur la base `Resource`, pour ne pas écrire un `"id": ""` dans
   les sidecars des autres familles) ; `asset_reconciliation.assign_sfx_ids` donne un id à ceux qui n'en ont pas et un
   NOUVEL id au second d'un doublon, au chargement de l'audio ; `sync_sfx_file` et la création depuis le finder en
   attribuent un d'emblée. Les 5 sidecars de `PongAdvanced` portent leur id. Le reste du chantier (arbre du disque,
   déplacement libre) reste à faire : `ResourceStore` repère encore un sidecar par son nom, à plat.
2. **Livrée le 2026-10-09, L'onglet Disk, en lecture seule** (zone Build / debug). Un arbre fidèle du dossier `assets/`, où chaque
   fichier est marqué : source reconnue sans asset, source déjà reliée à un asset, format non pris en charge. Le
   comportement ne change pas : la création automatique d'un asset à partir d'un fichier reste active. C'est la
   tranche qui rend les sources VISIBLES, avant de leur retirer quoi que ce soit.
   Livré : l'onglet **Disk**, racine **Assets**, dans le panneau Build / debug (les deux, scènes et scripts) ;
   **vue à plat**, le contenu d'un dossier, une icône et un nom par entrée, un fil d'ariane pour remonter, double-clic
   pour entrer (le bandeau « Build / Debug » a disparu, Clear a rejoint la barre de la console) ;
   `core/disk_tree.py` classe chaque fichier, `ui/common/disk_view.py` l'affiche, `Project.source_families()` est la
   table unique famille → fichiers sources (déjà dupliquée deux fois dans `project.py`). L'arbre se relit à l'ouverture
   de l'onglet et au bouton Refresh, après `load_all_resources()`. **Constat :** le scan actuel étant plat, un `.wav` posé
   dans un SOUS-dossier de `sfx/` ressort comme source libre, tandis qu'un `.wav` posé à la racine de `sfx/` devient un
   asset d'office, la création automatique que la tranche 3 retire.
3. **La lecture récursive** (ordre choisi le 2026-10-10 : elle passe AVANT *Create asset*). Un sidecar peut vivre dans un
   sous-dossier de son dossier de famille (`assets/sfx/platformer/wav/coin.json`) : l'index d'un magasin le trouve, et
   lecture, sauvegarde, suppression et renommage le traitent là où il est, sans le ramener à la racine. Un nouvel asset
   peut être posé dans un dossier donné. C'est ce qui permettra de créer l'asset à côté de sa source. Deux sidecars de
   même nom dans deux dossiers : le premier (le moins profond) est lu, l'autre est ignoré et signalé. **Pas encore** :
   déplacer un asset hors du dossier de sa famille (un sidecar reste dans le dossier de SA famille, `assets/sfx/…`), la
   création automatique d'un nom suffixé pour le doublon, le suivi en direct des sous-dossiers par le surveillant.
4. **Livrée le 2026-10-11, *Create asset* au clic droit sur une source, et fin de la création automatique.** `core/asset_creation.py` (un format de source → les types qu'il peut devenir : `.png` sprite / fond / police, `.wav` effet / musique / jingle, `.mod .xm .s3m .it` musique / jingle, `.ttf .otf .fnt` police, `.hex` palette ; l'asset naît À CÔTÉ de sa source, nommé d'après le fichier et unique dans son type), `core/blank_assets.py` (les assets vierges : scène, prefab, mise en page, trois boîtes, table de données, palette ; scripts et behaviors sont des fichiers), `core/disk_commands.py` (importer, déplacer, créer et renommer un dossier, créer un fichier : tous annulables) et `CreateAssetCmd`. Dans l'onglet Disk : un « + » (Import…, Create ▸, New folder) ; un bouton « Create *nom* » quand UNE source libre est sélectionnée (la flèche propose les autres types) ; au clic droit, *Create* sur une source (grisé en multi-sélection, avec la raison) et *Delete* sur des assets. **Supprimer un asset ne supprime plus sa source** ; plus aucun asset ne naît de l'apparition d'un fichier (réconciliation d'ouverture et surveillant), ni ne suit un fichier renommé ; `reconcile_manifest` retiré ; la corbeille ne contient que les fichiers d'asset. **Détachement achevé (2026-10-11) :** `sync_*`, `_relink_source`, `_sourced_by` supprimés ; l'import d'un sprite depuis son finder copie puis crée l'asset en UNE entrée d'historique ; l'inspecteur d'acteur choisit un SPRITE (asset), plus un PNG ; l'appariement des renommages et le signal `asset_renamed` du surveillant sont retirés (un renommage = disparu + apparu) ; supprimer un asset prévient de ce qui le cite encore (`core/asset_usages.py` : composants de sprite, calques de fond, prefabs posés, palettes, scène de départ, scripts, un avertissement, pas un refus). **Création en lot (2026-10-11) :** *Create* n'est plus limité à UNE source, la sélection peut en compter plusieurs, tant que toutes sont des sources et qu'un même type leur convient (`shared_create_options` : l'intersection des types de chacune, dans l'ordre de la première ; plusieurs `.wav` offrent effet / musique / jingle). Le lot est UNE entrée d'historique (`MacroCmd` de `CreateAssetCmd`) ; les noms sont uniques ENTRE EUX aussi (deux `coin.wav` de deux dossiers : `coin`, `coin_2`) ; une source qui ne convient pas est signalée et les autres sont créées. Grisé, avec sa raison : des formats sans type commun (PNG + WAV), ou autre chose que des sources dans la sélection. Le callback `create_from_source` est devenu `create_from_sources(chemins, famille)`. Ancien énoncé :  Les deux vont ensemble :
   « une source n'est un asset qu'après *Create asset* » n'a de sens que si le geste existe. L'asset est créé à côté de sa
   source (grâce à la tranche 3). L'import par dialogue (copie d'un fichier venu de l'extérieur, asset créé d'office) reste
   un second chemin vers le même résultat. Le nom d'asset est tranché ici (règle commune, unique dans le projet).
5. **L'asset devient indépendant de sa source et librement déplaçable** (découpée le 2026-10-10, une tranche à la fois) :
   - **5a. Un id dans tous les sidecars.** Le magasin (`ResourceStore`) l'écrit juste après le nom et le relit lui-même :
     aucun modèle n'a à le porter (une douzaine ont leur propre sérialisation). Attribué à l'enregistrement et au
     chargement ; deux items qui portent le même id (une copie dans l'Explorateur) : le second en reçoit un nouveau.
     Remplace `Sfx.id` de la tranche 1. Les palettes (`.hex` + sidecar) viendront à part.
   - **5b. La source qui manque. Livrée le 2026-10-10.** Une erreur de build, UNE par fichier manquant, pour toutes les
     familles adossées à un fichier (`core/asset_relink.py`, `validator._check_missing_sources`) : elle remplace les
     quatre avertissements que sprites, fonds, polices et sons émettaient chacun de leur côté. L'action *Relink source…*
     du menu du finder relie l'asset à un autre fichier, sans le recréer (nom, id, réglages gardés ; sprites et fonds
     ré-encodés depuis le nouveau fichier, par asset et non par nom de fichier) ; un fichier qui ne convient pas est
     refusé, l'asset inchangé. **Limite :** un fond ne se relie qu'à un fichier directement dans `assets/backgrounds/`
     (son encodage ne retient que le nom du fichier).
   - **5c. Le déplacement libre sous `assets/`, décidé le 2026-10-10 : une extension par type d'asset.** Le sidecar
     cesse de s'appeler `<nom>.json` : son extension dit sa famille (`Player.sprite`, `boom.sfx`), le contenu reste du
     JSON (lisible, diffable, fusionnable). Le balayage global lit donc le TYPE dans le nom du fichier, sans ouvrir son
     contenu : plus de cache d'empreintes, plus d'étiquette de famille dans le sidecar, et un asset peut vivre n'importe où
     sous `assets/`. Noms nus (sans préfixe), une table unique `type → extension` (module de nommage), toutes les familles.
     | Famille | Extension | | Famille | Extension |
     |---|---|---|---|---|
     | sprites | `.sprite` | | scènes | `.scene` |
     | fonds | `.background` | | prefabs | `.prefab` |
     | effets sonores | `.sfx` | | mises en page d'interface | `.layout` |
     | musiques | `.music` | | boîtes musique / jingle / sonore | `.musicbox` `.jinglebox` `.soundbox` |
     | jingles | `.jingle` | | tables de données | `.table` |
     | polices | `.font` | | assets de police | `.fontasset` |
     | palettes | `.palette` (le `.hex` reste le format d'échange) | | | |
     **Restent en `.json`** : `texts.json`, `texts_<langue>.json`, `variables.json` (un fichier pour tout le projet, pas un
     par asset). Aucune extension de sidecar ne reprend celle d'un format de source (`.png .wav .mod .xm .s3m .it .ttf .otf
     .fnt .hex .lua`). Trois temps : (1) **livré le 2026-10-10**, module de nommage (`core/models/asset_extensions.py`, une constante `sidecar_extension` par modèle) + `tools/migrate_sidecar_extensions.py`, appliqués aux deux démos et au starter Basic (76 fichiers) ; le surveillant et l'arbre Disk suivent la nouvelle extension ;
     (2) **livré le 2026-10-10**, chaque magasin cherche ses sidecars sous TOUT `assets/` (`ResourceStore(dossier, classe, racine)` : le dossier de la famille ne sert plus qu'à y faire naître un nouvel asset) ; un asset se lit, s'écrit, se renomme et se supprime là où il est, deux types peuvent partager un dossier et un nom ; un homonyme du même type plus profond est ignoré et signalé, son chemin est donné depuis `assets/` ; les palettes restent dans `assets/palettes/` (leur `.hex` y vit avec elles) ; (3) **livré le 2026-10-10**, déplacer fichiers et dossiers par glisser-déposer dans l'onglet Disk (arbre et vue à plat), `core/disk_move.py` étant la seule écriture. Règles : un sidecar se déplace seul (l'asset pointe sa source par chemin) ; une source citée par un asset se déplace avec mise à jour du chemin de l'asset ; une source libre ou un fichier non géré se déplace librement ; un dossier se déplace avec tout son contenu, chemins des assets réécrits ; rien n'est jamais écrasé (un fichier du même nom à destination = refus, sans rien déplacer) ; pas de déplacement d'un dossier dans lui-même. **Refusés** : textes et variables (un seul fichier pour tout le projet) ; les palettes, les images de fonds et les scripts `.lua` se déplacent désormais (temps 4), un script déplacé voyant réécrites ses attaches dans les scènes, caméras, acteurs et prefabs. Le surveillant est suspendu pendant l'opération : un fichier déplacé n'est jamais pris pour un nouvel import. Au survol, le dossier qui peut recevoir est surligné et les entrées glissées passent à demi transparentes ; un dossier qui ne peut pas recevoir (palettes, textes…) montre le curseur « interdit » et dit pourquoi dans la barre d'état dès le survol, pas seulement au dépôt (`disk_move.drop_verdict`, la même règle que le déplacement). **Temps 4, libres partout (décidé le 2026-10-10, non commencé).** **Modèle (précisé le 2026-10-10) : un asset n'est plus le sidecar d'un fichier source.** C'est un objet à part entière, qui ne fait que POINTER une source par un chemin explicite ; plus aucun lien implicite entre les deux, ni nom commun, ni dossier commun : l'asset ne suit pas sa source (renommée, déplacée), la source ne suit pas son asset. Les conventions qui supposaient ce couplage disparaissent avec *Create asset* : un asset nommé d'après le stem de son fichier, la création automatique à l'apparition d'un fichier, le suivi d'un fichier renommé par le surveillant. Les trois pas ci-dessous se conçoivent dans ce modèle. Lever les derniers refus de `core/disk_move.py`, un par un, chacun avec sa migration, ses tests et le retrait du refus correspondant : (a) **images de fonds, livré le 2026-10-10** (`tools/migrate_background_paths.py` ; `Project.background_image_path` ; renommer un fond ne renomme plus son image ; `disk_move` et `asset_relink` n'ont plus de cas à part ; restent, pour *Create asset*, la création d'un fond à l'apparition d'un PNG dans `assets/backgrounds/` et le raccrochage par le nom) : `BackgroundAsset.asset` passe du seul NOM de fichier à un chemin relatif au projet, comme sprites et sons ; une seule fonction rend le chemin réel de l'image d'un fond et remplace la vingtaine de `background_images_dir / nom` (build, codegen, éditeur de fonds, canvas, inspecteurs, réconciliation) ; la relier à un fichier hors de `assets/backgrounds/` devient possible (`asset_relink`) ; (b) **palettes, livré le 2026-10-10** : le `.palette` cite son `.hex` par un champ `asset` (chemin relatif au projet), les couleurs restent dans le `.hex` et ne sont jamais dupliquées ; l'un et l'autre se rangent où l'on veut sous `assets/` ; les palettes rejoignent `source_families()` (déplacement, relink, source manquante, corbeille : le cas général) ; renommer une palette ne renomme pas son `.hex` ; un `.palette` d'avant le champ le reçoit à la première ouverture (le `.hex` voisin) ; une palette dont le `.hex` a disparu n'est pas chargée et son `.palette` reste intact ; (c) **scripts, option B, livré le 2026-10-10** (`core/lua_scripts.py`, `tools/migrate_behavior_markers.py`, tests `tests/scripting/test_behavior_marker.py`) : le rôle d'un script ne vient plus de son dossier mais de son contenu : une première ligne `-- @behavior` marque un behavior ; `require("behaviors/<nom>")` reste l'appel écrit (le mot `behaviors/` devient un espace de noms, plus un dossier), résolu par NOM parmi les fichiers marqués, où qu'ils soient ; les scripts attachables sont tous les `.lua` non marqués de `assets/` ; deux behaviors de même nom = erreur de build ; « New behavior » écrit le marqueur ; un outil migre les projets d'avant (marqueur ajouté aux fichiers de `scripts/behaviors/`) ; le finder de scripts montre tous les `.lua` de `assets/` (les dossiers sans script sont masqués) ; le surveillant suit les `.lua` de tous les dossiers de `assets/`, les autres sources n'y étant suivies que dans les dossiers de famille. **Ne bougent jamais** : `texts.json`, `texts_<langue>.json`, `variables.json` (un fichier pour tout le projet). **Ensuite, hors de cette
     tranche :** associations de fichiers (installateur Windows en `HKCU\Software\Classes`, proposition à l'utilisateur
     pour le zip portable, fichier MIME + `.desktop` pour l'AppImage) et un éditeur qui ouvre un sidecar passé en argument.
   - **Plus tard : les références par id** (une scène qui cite un sprite par son id et non par son nom) : un chantier à
     part, qui touche toutes les scènes.
6. Extension aux musiques, jingles, sprites, fonds.

**Livré aussi (2026-10-10) :** l'arbre vertical de tout `assets/` vit dans la colonne de gauche, sous un onglet **Disk**
à côté de **Project viewer** (qui devient lui-même un onglet : on ne touche pas au mécanisme d'`AssetFinder`). Choisir un
dossier de l'arbre l'affiche, à plat, dans l'onglet Disk du panneau du bas, comme le fait Unity ; la vue du bas se
navigue aussi seule (double-clic, fil d'ariane). Le sens inverse (un double-clic en bas qui sélectionne le dossier
dans l'arbre) n'est pas fait.
**Un `assets/` vierge, des imports dans le dossier affiché, un surveillant sans dossiers imposés (2026-10-19).** Créer ou ouvrir
un projet ne crée plus aucun sous-dossier (seulement `assets/`) : chaque écriture crée le dossier qu'elle vise. Tout bouton
d'import d'un écran (importer un sprite, un fond ; remplacer l'image d'un sprite ou d'un fond ; *Save as PNG*) pose le fichier
dans le dossier que l'onglet Disk affiche (`core/asset_creation.import_folder`, branché une fois par la fenêtre dans
`ui/common/import_folder.py`), sinon à la racine de `assets/`. Le surveillant suit tous les dossiers sous `assets/` à toute
profondeur, avec tous les types de fichiers : plus de liste de dossiers de famille ni de `parent.name == "sprites"`. Un
fichier retouché est relié à ce qui le CITE (fond, sprite, police), un sidecar à son extension. *Reste :* l'import de
palettes (les `.hex` vivent dans `assets/palettes`), les dossiers vides des projets de démo, créés avant ce changement.
**Un « + » et une loupe sur l'arbre (2026-10-10).** L'onglet n'est plus strictement en lecture seule : le « + » crée un
vrai dossier sur le disque, dans le dossier choisi (ou la racine), nommé d'office `New folder`, `New folder_2`… puis
renommé EN PLACE dans l'arbre (pas de fenêtre) ; un nom vide, interdit (`/ \ : * ? " < > |`, point ou espace final) ou
déjà pris est refusé avec un message et le dossier garde son nom. `core/disk_folders.py` est la seule écriture et refuse
tout ce qui sort de `assets/`. La loupe filtre l'arbre par nom (`W.filter_tree`, déjà partagé). Un dossier vide n'est pas
suivi par git tant qu'il ne contient aucun fichier.
**Renommer depuis les deux vues (2026-10-11).** un clic sur le nom d'une entrée déjà choisie, F2 ou « Rename » au clic droit, dans l'arbre comme dans la vue à plat : un dossier,
une source ou un script se renomme EN PLACE (`disk_move.rename_in_place`, un déplacement sur place : les assets qui citent le
chemin le suivent, annulable). Les autres assets gardent leur renommage dans leur écran ; les tables du projet sont refusées.
**Noms trop longs (2026-10-10).** Un nom passe d'abord à la ligne (deux lignes dans la vue à plat, une dans l'arbre) ; s'il est
ENCORE trop long, son extension est gardée et le début coupé : `monnomquiestbeaucouptroplong.extension` devient
`monnomq... .extension` (sur deux lignes, l'extension reste seule sur la seconde). Le retour à la ligne est fait par
`ui/common/elide_name.py`, pas par Qt : en mode icônes Qt ne coupe qu'aux espaces, donc un nom sans espace n'était jamais
replié mais abrégé par un « … » qui mangeait l'extension. Même règle dans la vue à plat et dans l'arbre vertical.
Le retour à la ligne choisit sa coupe dans cet ordre : **juste avant l'extension** (`Falling Asleep` puis `.json`), sinon à une
**espace** (jamais au milieu d'un mot : `Out of Energy` puis `Game Over.json`), sinon en pleine lettre mais sans laisser une ou
deux lettres seules sur la seconde ligne (`.jso` / `n`). La largeur dont le texte dispose est demandée au STYLE de Qt (`SE_ItemViewItemText`), pas devinée : une marge devinée un peu
trop grande, et Qt abrégeait de nouveau le nom déjà coupé (`Vi... .m…`), vu dans l'arbre, avec sa feuille de style.
**Iconographie et dossiers (2026-10-10).** La vue à plat reprend les icônes de l'éditeur : un fichier relié à un asset
prend l'icône de sa famille (sprite, fond, effet, musique, jingle, police, palette, script), une source sans asset celle de
son format (`.wav` effet, `.png` image, les deux formats partagés entre deux familles donnent le cas courant). Un dossier
**plein** est un dossier où l'on peut descendre ; l'entrée **« ... »**, en filet, est toujours la première hors de la
racine et remonte d'un niveau ; **à la racine**, où il n'y a rien à remonter, cette place est tenue par une icône de **disque dur**
nommée `assets`, dont le double-clic ouvre le vrai dossier dans l'explorateur de fichiers du système. `DiskNode.family` porte la famille ; `Project.source_families()` rend `(famille, store,
fichiers)`. L'onglet Disk est **tout à gauche**, avec une icône de disque (le seul onglet à en avoir une), dans la colonne
de gauche (avant Project viewer) comme dans le panneau du bas (avant Console).

### Ce que ça ne fait pas

- Ne change ni le runtime C ni le format de la ROM.
- Ne fait pas de l'éditeur un outil de dessin généraliste (cf. périmètre). Le **Color Tile
  Painter**, s'il est ouvert, est l'exception volontairement étroite : il sert à poser un fond
  de prototype en couleurs pleines, pas à retoucher ou illustrer une image.

---

## L'écran Texte n'édite et ne range que du contenu

### D'où vient la question (2026-10-10)

L'écran Texte fait aujourd'hui deux métiers : **ranger et écrire** du contenu (la table, la clé, le
rangement, les langues, la barre de balisage), et **montrer le rendu GBA** de ce contenu (`FontScreenPreview`,
un écran 240×160 aux vrais glyphes, avec son sélecteur de police et son bouton « Afficher le balisage »).
Le second brouille le message du premier : l'œil va vers le rectangle noir, pas vers la liste qu'on est venu
mettre en ordre. Le rendu fidèle a servi à poser le pipeline des polices ; il a un autre lieu naturel (la
scène, l'écran Police). L'écran Texte ne doit plus chercher qu'**une chose : éditer et ranger le contenu**.

### Le parcours visé (précisé les 2026-10-10 et 2026-10-17)

Deux lieux, deux métiers, et ils ne se recouvrent pas :

- **Le scene canvas règle l'aspect.** C'est là que l'auteur configure une boîte de dialogue, sa police, sa
  taille, sa couleur, et voit le texte tel qu'il sera. Tout ce qui est apparence vit ici.
- **L'écran Texte règle ce qui entre dedans.** Le contenu, sa clé, son rangement, ses langues, son balisage.
  Il ne sait pas dans quelle boîte le texte va tomber ; il n'a donc pas à en montrer le rendu.

Conséquence assumée : **l'écran Texte ne dit pas si un texte est tronqué**, ni s'il déborde de sa boîte. Pas
dans un premier temps ; si le besoin se fait sentir, ce sera un retour de la scène vers la table (un texte
signalé depuis son lieu d'usage), pas un rendu recréé dans l'écran Texte.

Ce que le canvas fait déjà (vérifié dans le code, 2026-10-10) : rendu aux vrais glyphes avec le placement du
moteur, et liseré ambre quand la boîte tronque. Ce qu'il ne fait pas encore : montrer une **traduction**. Il
n'affiche que la langue source. Décidé qu'il prévisualisera la langue choisie, dans une mesure non définie (voir
point 4 de « À trancher »).

### Ce que ça change pour l'auteur

- **L'aperçu écran disparaît** de l'atelier : plus de rectangle 240×160, plus de sélecteur de police d'aperçu,
  plus de bouton « Afficher le balisage » (la source balisée est la seule vue du contenu).
- **Décision du 2026-10-17 : le contenu occupe la place principale.** Remplacer les lignes
  compactes `Key / Content / Used` par de grands blocs de texte multi-lignes directement éditables,
  comme sur la maquette. Le traducteur ou le correcteur doit pouvoir lire et travailler les textes
  longs sans les retrouver comprimés dans une cellule. Cette direction remplace le délégué de
  cellule initialement proposé le 2026-10-10.
- **Regrouper les blocs par scène**, avec un en-tête repliable. Une indication discrète au-dessus
  du contenu situe l'objet et la scène ; les clés et les informations d'usage ne prennent plus
  la place du texte. Le traitement des entrées partagées ou sans scène reste à définir.
- **Alléger les outils autour du contenu.** Garder accessibles langue, balisage, clé et rangement,
  sans maintenir par principe l'atelier du bas ou l'inspecteur actuels. Leur disposition exacte
  reste à dessiner ; la priorité est la surface de lecture et d'édition.

### Find (rejoindre le lieu d'usage (décision du 2026-10-17))

Depuis l'écran Texte, un bouton **Find** permet de retrouver un texte dans le projet lorsqu'il
est référencé : ouvrir la scène concernée et sélectionner/révéler l'élément qui l'utilise.
La maquette place également une loupe dans l'en-tête de scène pour rejoindre ce contexte.
L'emplacement exact des actions scène et texte reste à préciser, mais l'accès doit être direct.

- Un seul lieu d'usage : navigation directe vers la cible.
- Plusieurs lieux : proposition d'une liste de destinations explicites (scène, objet, script ou
  table selon la référence), sans choisir arbitrairement une scène.
- Aucune référence : état « non référencé », sans destination inventée.

Les deux derniers comportements sont proposés pour préciser le contrat. Il faudra distinguer
les références directes d'une TextBox, celles d'un script et celles d'une Data Table : une cellule
de table identifie un usage, mais ne prouve pas dans quelle scène le script affichera son texte.
Le bouton s'appuie sur les références réelles, pas seulement sur le nom ou le rangement de l'entrée.
Compléter l'index des usages si nécessaire, notamment avec toutes les pages des TextBox et les
colonnes `text` des tables ; gérer aussi les mises en page partagées entre plusieurs scènes.

### Le conflit avec l'ancien chantier

Ce chantier **remplace** « L'atelier Texte réuni, écrire et voir dans un même écran » (2026-09-19), qui
allait à l'opposé : faire du rendu GBA la surface d'édition (projection source ↔ affichage, caret et
sélection dessinés par `FontScreenPreview`, vue balisage en police moteur). Cette direction est abandonnée :
elle aurait fait de l'aperçu la pièce centrale de l'écran, là où l'on veut le retirer. Sa décision verrouillée
du 2026-09-19 tombe avec elle ; la section qui la portait n'est plus qu'un renvoi ici.

**Constat de code, à dire avant d'ouvrir :** l'ancien chantier était annoncé « aucune étape codée »,
mais `TextWorkbench` monte déjà `FontScreenPreview` en surface **éditable** (`set_editable(True)`, signaux
`edited` / `committed`) et y branche `MarkupToolbar`. Le code est donc à mi-chemin d'une direction qu'on
abandonne : l'état d'arrivée de ce chantier est désormais la liste de blocs éditables décidée le 2026-10-17.

### Ce que ça touche

| Fichier | Sort |
| --- | --- |
| `font_screen_preview.py` | **supprimé**, seul `TextWorkbench` le monte |
| `text_workbench.py` | perd `_build_preview`, le `QSplitter`, `_preview`, le sélecteur de police d'aperçu, `_btn_markup` ; garde l'identité (clé, rangement, langues) et la barre de balisage |
| `text_table.py` | remplacer la présentation compacte par des blocs multi-lignes regroupés par scène ; préciser si le composant est refondu ou remplacé |
| `text_panel.py` | reste l'arbitre des modifications annulables ; sélection, regroupement et actions Find |
| `markup_toolbar.py` | vise le bloc en cours plutôt que `FontScreenPreview`, son contrat (`source()`, `selection_source()`, `replace_source()`) est déjà abstrait ; désactivée hors édition |
| `text_editor_screen.py`, `text_inspector.py` | `preview_font_changed` / `set_font` : voir « À trancher » |
| `markup_highlighter.py` | **conservé**, `ui_inspector.py` l'utilise aussi |
| `tests/ui/test_text_preview_font_assets.py` | retiré avec l'aperçu |
| `labels.json`, `labels_fr.json` | clés `txtwb.show_markup_*`, `txtwb.preview_font_*` retirées |

`core.text_markup`, `texts.json`, les sides de traduction et la ROM ne bougent pas : c'est un chantier d'**interface**.
`ScreenTextPreview` (la jauge de longueur de l'inspecteur de script) est un autre composant, il reste.
Find touche également l'index des usages (`core/project_texts.py`) et la navigation vers les
scènes, leurs éléments, les scripts et les tables. Vérifier ces points dans le code au démarrage.

### À trancher avant d'ouvrir

1. **Ce que le bloc montre au repos.** La source balisée (ce qu'on édite = ce qu'on lit, balises teintées),
   ou le texte résolu comme aujourd'hui (plus propre pour parcourir, mais deux représentations du même
   contenu). Penchant : la source, une seule représentation.
2. **Dimensionnement des blocs.** Le contenu multi-ligne doit être lisible, décision du 2026-10-17.
   Fixer la hauteur minimale, un éventuel plafond pour les très longs textes et le comportement
   sur des centaines d'entrées ; la ligne compacte avec `⏎` n'est plus la cible.
3. **Ce que devient la police d'aperçu.** Elle alimente encore l'inspecteur (caractères manquants via
   `missing_chars()`) et la liste des icônes de la barre de balisage. Sans sélecteur : la « Default Font » du
   projet (v0.9) comme police de référence, ou le sélecteur déménage dans l'inspecteur de droite. Si l'apparence
   appartient à la scène, la police n'a plus de raison d'être choisie ici : la couverture des glyphes
   (`missing_chars()`) est-elle encore une question de contenu, ou passe-t-elle aussi à la scène ?
4. ~~La troncature~~, **tranché le 2026-10-10** : hors de l'écran Texte, pas dans un premier temps (voir « Le
   parcours visé »). Prémisse **vérifiée dans le code le 2026-10-10** : le scene canvas rend déjà le texte d'une
   boîte avec les vrais glyphes (`canvas_region_item.py` : `_paint_text` → `layout_text` / `layout_marked_text`,
   mêmes fonctions que la ROM ; police par `font_emit.scene_default_font`, encre par `font_palette`) et signale
   déjà la troncature (liseré ambre en bas de la boîte). **Un trou : la langue.** `_text_content` et
   `_text_source` lisent `t.content`, donc toujours la langue source ; le canvas n'a ni sélecteur de langue ni
   appel à `Project.text_content(t, lang)`. Une traduction plus longue que l'original peut déborder sans que rien
   ne le montre, et l'aperçu de l'atelier, qui suivait l'onglet de langue, était le seul endroit où on la voyait
   dans sa boîte. **Décidé le 2026-10-10 : le canvas prévisualisera la langue choisie.** La **mesure** reste à
   définir : où se choisit la langue (canvas seul, ou partagée avec l'écran Texte), si elle est mémorisée par
   scène ou par session, si le liseré ambre de troncature suit la langue affichée, si l'on peut voir plusieurs
   langues à la fois. Rien de tout cela n'est arrêté. Ce n'est pas un prérequis du retrait de l'aperçu, mais
   tant que ce n'est pas livré l'auteur qui traduit perd un repère : le dire dans la clôture.
5. **Édition de la traduction.** Disposer la source en lecture seule à côté ou au-dessus du bloc
   traduit, en gardant une grande surface d'édition ; fixer la place du sélecteur de langue.
6. **Regroupement et Find.** Place des textes sans scène et des textes partagés, ordre des pages,
   gestion des usages indirects et destinations multiples ; fixer le retour vers le texte après navigation.

### Ordre d'implémentation (proposé)

1. **Liste de blocs éditables** : regroupement par scène, contenu multi-ligne et traduction,
   modifications annulables via `text_panel`, conservation de la recherche et de la sélection.
2. **Rebrancher `MarkupToolbar`** sur le bloc actif et alléger les panneaux annexes.
3. **Retirer l'aperçu** : `FontScreenPreview`, splitter, sélecteur, bouton, signaux de police, clés de
   traduction, test dédié. Trancher le point 3 avant cette étape.
4. **Chercher le mort** : signaux sans abonné, `set_font` orphelin, helpers de rendu qu'aucun autre écran
   n'appelle ; mettre à jour `ARCHITECTURE.md` (arbre des fichiers, section de l'écran Texte).
5. **Find** : indexer les usages nécessaires et câbler les destinations ; vérifier navigation,
   absence de référence, références multiples, mises en page partagées et pages de dialogue.
6. Vérifier la lecture et l'édition de textes longs, les traductions, l'annulation et le comportement
   sur un projet contenant de nombreuses entrées.

### Ce que ça ne fait pas

- Ne retire pas le rendu fidèle de l'éditeur : il reste dans l'écran Police et en scène.
- Ne change ni `texts.json`, ni le format des traductions, ni la ROM.
- Dans cet écran, les blocs sont la surface d'édition du contenu ; les TextBox peuvent aussi éditer
  les mêmes entrées depuis la scène, conformément au chantier des pages de dialogue.

---

## Dupliquer un asset, et régler SFX et jingles

### D'où vient la question (2026-10-12)

Deux besoins, dans cet ordre parce que le premier donne son sens au second.

1. **Plusieurs assets sur une même source, avec des réglages différents.** Le modèle « source ≠ asset » le permet
   (un asset pointe un fichier par un chemin, rien d'autre ne les lie), mais le geste manque : seule la palette sait
   se dupliquer (`_duplicate_palette`, `ui/common/asset_kinds.py`). Pour un effet, nous voulons `coin` et `coin_high`
   (même `.wav`, hauteur différente) sans réimporter ni recréer.
2. **Un SFX n'a aujourd'hui que deux réglages** (`volume`, `sample_rate`) et un jingle, qui est une `Music`, n'en
   montre qu'un ou deux. La question posée : qu'est-ce que l'auteur voudra vraiment régler ?

### État au 2026-10-13

| Tranche | État | Où lire le détail |
| --- | --- | --- |
| 1. Duplication (assets, sources, scripts ; finders et Disk) | **Livrée le 2026-10-12** | « Ordre d'implémentation », 1 |
| 2a. Découpe non destructive d'un SFX | **Livrée le 2026-10-12** | 2a |
| Constantes sonores nommées d'après l'ASSET, plus d'après un fichier | **Livré (2026-10-12, repris le 2026-10-13)** : correction du modèle, découverte en route | 2a, « Constat » |
| 2b. Hauteur et panoramique par défaut | **Livrés le 2026-10-13** | 2b |
| 2c. Variation aléatoire de hauteur, fondu de sortie | **Livrés le 2026-10-13** | 2c |
| Correctif : un son court ne s'entendait pas à l'aperçu | **Corrigé le 2026-10-13**, confirmé par l'auteur | 2c, « Correctif » |
| Correctif : un WAV 24 ou 32 bits était refusé (effet, musique, jingle) | **Corrigé le 2026-10-13** ; reste à confirmer à l'oreille par l'auteur | 2c, « Correctif : WAV 24 bits » |
| 2d. Poignée de fondu, vue par canal, oscilloscope sur l'éditeur d'effet | **Livrés le 2026-10-13** (demandés par l'auteur) | 2d |
| 2e. Écoute A/B du taux, avec le poids ROM à côté | **Livrée le 2026-10-13** | « Proposé » 2, point 5 ; voir « 2f » |
| 3. Jingles : politique vis-à-vis de la musique | **Livrée le 2026-10-14** (runtime + inspecteur) ; l'aperçu à l'éditeur reste à faire | « Proposé » 3, point 1 |
| 3. Jingles : plage jouée | **Livrée le 2026-10-14** pour un module (plage d'ordres) ; un WAV avait déjà sa plage en ms | « Proposé » 3, point 2 |
| 3. Jingles : avertissement de canaux | **Reste**, non commencé | « Proposé » 3, point 3 |
| Barre de découpe aux effets (retire les poignées de l'onde) ; champs avec unité dehors (`UnitSpin`) | **Livrés le 2026-10-14** (demandés par l'auteur) | s.o. |
| Panoramique d'un effet : un axe gauche–droite à la table Mix (retiré de l'inspecteur) ; bouton « Import WAV… » retiré de l'inspecteur d'effet | **Livrés le 2026-10-14** (demandés par l'auteur) | s.o. |

**Ce que la session a changé hors du périmètre annoncé** (chaque point est détaillé plus bas) :

- le build ne dépend plus du nom d'un fichier pour nommer un son dans la ROM. `MmutilAudio._number_ids` réécrit `SFX_*` /
  `MOD_*` d'après l'asset (un défaut du modèle « source ≠ asset », que la duplication a rendu visible à chaque geste) ;
- `Sfx` gagne six champs (`trim_start`, `trim_end`, `pitch`, `panning`, `pitch_variation`, `fade_out`), tous à leur défaut dans
  un sidecar d'avant ;
- `core/sfx_render.py` devient l'unique endroit qui découpe, fond et ré-échantillonne un effet, pour le build ET pour l'aperçu ;
- l'aperçu d'un effet joue enfin le taux du projet, la découpe, le fondu et la hauteur (le panoramique reste inaudible à
  l'aperçu : le lecteur est mono) ;
- `WaveformView` sert aussi les effets (règle en millisecondes, bascule Onde | Scope et poignée de départ masquables, rampe de
  fondu) ;
- `BoxPlayer.sounding` suit ce que la carte son a joué.

**Vérifications restantes, à la charge de l'auteur :** écouter sur émulateur un effet à hauteur variable et un effet à
panoramique réglé (seuls les tests de génération et un test C compilé sur l'hôte les couvrent) ; rien d'autre : le correctif
de l'aperçu est confirmé sur les effets qu'il avait signalés.

### Décisions verrouillées (2026-10-12)

- **Ordre** : (1) la duplication, (2) les réglages d'un SFX, (3) les réglages d'un jingle.
- **Une source se duplique aussi** (2026-10-12) : la copie est une source libre.
- **Le défaut est dans le modèle, pas dans le build** (2026-10-13) : le nom d'un son ne vient pas d'un nom de fichier.
- **Le tirage de la variation de hauteur a son propre générateur, à graine fixe** (2026-10-13) : il ne consomme jamais `math.rand`.
- **Un fondu d'effet est en frames** (2026-10-13), comme tous les fondus de l'éditeur.

### Proposé, non verrouillé

#### 1. Dupliquer

- **Une seule fonction**, `core/asset_duplication.py` (sur le modèle de `core/asset_creation.py`), appelée par le finder
  ET par l'onglet Disk. Aucune copie de logique dans l'interface.
- **La copie** passe par la sérialisation du sidecar : mêmes réglages, **même champ `asset`** (la source n'est jamais
  copiée), **nouvel id**, nom libre selon la règle commune (`coin`, `coin_2`), posée à côté de l'original. Les sections
  d'une musique sont copiées en profondeur.
- **Indépendante** : aucun lien vivant avec l'original. Un asset « variante » qui hérite de son parent est une autre
  question, hors de cette tranche.
- **Annulable** : UNE entrée d'historique (`AddResourceCmd`), un `MacroCmd` pour une multi-sélection.
- **Interface** : entrée *Duplicate* (clé `common.duplicate`, déjà au catalogue), Ctrl+D, puis renommage EN PLACE de la
  copie (pas de fenêtre), comme le bouton « + ». Chaque `AssetKind` la reçoit par `actions` ; une famille qui ne peut pas
  l'avoir (textes, variables : un fichier pour tout le projet) n'en déclare pas.
- **Disk** : *Duplicate* sur une entrée qui EST un asset. Pas sur une source libre : copier le fichier ne répond pas au
  besoin, et le geste d'une source est *Create*. (À confirmer par l'auteur.)
- **Vérifié avant de coder (2026-10-12)** : sprites et fonds portent leur encodage dans le sidecar ; une palette copie ses
  couleurs dans son propre `.hex` ; les ids internes d'une scène sont locaux ; un script se copie comme fichier
  (les attaches se font par nom : la copie n'en reçoit aucune).

#### 2. Réglages d'un SFX (par ordre de valeur)

1. **Découpe non destructive**, début et fin (en ms), dans le sidecar ; le fichier source reste intact. Un effet pèse
   un octet par frame : couper la queue de silence se lit directement dans le poids ROM. L'onde existe déjà
   (`ui/sound_mixer/waveform_view.py`). Le build l'applique, au même endroit que le taux : `codegen/sfx_encode.py`.
2. **Hauteur et panoramique par défaut.** Le runtime les expose déjà dans `sfx` (`pitch`, `panning`), l'asset ne les
   porte pas. Règle du volume : la ressource propose, l'API surcharge à l'appel. Avec la duplication, c'est ce qui donne
   deux effets depuis une seule source.
3. **Variation aléatoire de hauteur (± %)** : rend naturels les sons répétés (pas, coups). Un tirage côté C au moment du
   déclenchement ; à décider : le générateur de nombres du runtime est-il déterministe (rejeu, démo) ?
4. **Fondu de sortie au build**, pour que la découpe ne tombe pas sur un clic (même motif que la jointure de boucle d'un WAV).
5. **Écoute A/B du taux avec le poids ROM à côté.** À vérifier : l'aperçu joue-t-il déjà le fichier ré-échantillonné ?

**Hors de cette tranche** : une priorité entre effets quand les canaux sont pleins, et un délai minimum entre deux
déclenchements du même effet. `mm_sound_effect` ne porte pas de priorité (comme pour la musique, cf. « Ce que Maxmod
tient ») : ce serait de la logique C à nous, donc un chantier de runtime à part.

#### 3. Réglages d'un jingle (par ordre de valeur)

1. **Politique vis-à-vis de la musique**, par jingle : *mélanger*, *baisser la musique de X % puis la remonter en fondu*,
   ou *mettre la musique en pause puis la reprendre*. Le matériel a un scaler par couche (cf. « le singleton `mixer` »),
   l'idée ne ment donc pas. C'est le réglage attendu d'une fanfare de victoire. Chantier de runtime : le jingle doit
   savoir quand il se termine.

   **Livré le 2026-10-14.** `Jingle.music_policy` (`mix` par défaut = l'ancien comportement, `duck`, `pause`), `duck_level` (%, 30 par
   défaut) et `duck_release` (frames, 30 par défaut). Décisions : (1) **un seul point d'écriture du volume de la musique**,
   `music_write_volume()`, qui multiplie par un duck 0–1024. Les 12 appels directs à `mmSetModuleVolume` y passent, pour ne pas
   refaire le défaut de la caméra ; (2) la chute est immédiate, la remontée est une rampe (arrondie par excès pour tenir dans
   `duck_release`) ; (3) la fin du jingle se lit par `mmActiveSub()`, une fois par frame (`music_jingle_tick`, avant le pas des
   fondus) ; (4) `mmPause` ne touche que la couche principale (lu dans `libmm.a`), donc la pause ne coupe pas le jingle ; une musique
   lancée pendant la pause attend aussi (`music_apply`) ; une musique arrêtée n'est pas ressuscitée ; (5) un jingle qui en remplace un
   autre prend SA politique ; (6) la politique est celle de l'ASSET : `music.jingle("X")` émet `music_jingle(id, volume, politique,
   niveau, remontée)`, le script ne dit pas ce qui arrive à la musique. Le duck manuel (`music.set_volume` + `jingle_box.set_volume`)
   reste possible et se multiplie au duck automatique. La case **Loop** disparaît de l'inspecteur d'un jingle. Tests :
   `tests/audio/test_jingle_policy.py` (le C généré compilé sur l'hôte contre un maxmod simulé), `tests/ui/test_jingle_inspector_policy.py` ;
   la ROM de PongAdvanced se construit avec le nouveau runtime. **Reste :** l'aperçu, `music_deck.py` ne connaît pas la couche jingle,
   donc la politique ne s'entend qu'à l'émulateur ; et l'écoute à l'oreille de la remontée.
2. **Plage jouée (début / fin).** Un jingle tiré d'un long module a besoin d'un point d'arrêt. Réemploie la machinerie
   des sections avec UNE plage implicite, pas la liste complète (un jingle n'a pas de sections, cf. [l'asset `.music`](changelog/archives/music-asset.md)).

   **Livré le 2026-10-14, autrement que prévu.** Le runtime ne PEUT pas le faire : `mmPosition` / `mmGetPosition` ne parlent
   qu'à la couche principale (lu dans `libmm.a`), aucune position de la couche jingle n'est lisible ni posable. La plage est donc
   cuite au BUILD : `Jingle.order_start` / `order_end` (positions de la table brute, fin exclue, 0 = jusqu'au bout), et
   `core/module_trim.cut_orders` (l'unique fonction, lue par le build (`build/music/<asset>.<ext>`) ET par l'aperçu) réécrit
   la table d'ordres du module. Par format : XM raccourcit la table ; IT et S3M gardent leur taille (les adresses qui suivent
   sont absolues) et finissent la table par 255 ; MOD réécrit aussi ses motifs (le nombre de motifs se lit dans la table et
   décalerait les échantillons), renumérotés à partir de 0. Écran : le bouton **Rogner** de l'éditeur, une barre d'ordres
   (`OrderRangeBar`) au lieu de la barre en ms, poignées entre deux cellules. **Limites :** les SAUTS écrits dans les motifs
   (Bxx) ne sont pas renumérotés ; les repères (`cues`, en ms) d'un jingle dont on coupe le début ne glissent pas ; un module à
   un seul ordre n'a rien à rogner. Tests : `tests/audio/test_module_order_cut.py`, `tests/ui/test_order_range_ui.py`, et trois
   builds ROM réels (`-m slow`).
3. **Avertissement sur les canaux** : maxmod ne donne que 4 canaux à la couche jingle (`JINGLE_MAX_CHANNELS`), un module
   qui en demande plus est joué tronqué sans erreur. L'écran dit « ce module en utilise N » ; le validateur avertit.
   Pas de muet par canal : Maxmod n'a pas d'API pour ça.
4. **Fondu de sortie** : existe dans `Music`, mais un jingle « n'applique que son volume » (décidé le 2026-10-11) ; à
   rouvrir seulement si la politique (1) ne le rend pas inutile.

#### 4. Rogner un WAV (musiques et jingles (demandé par l'auteur le 2026-10-14 ; livré le même jour pour les musiques et jingles WAV))

L'effet se rogne (`Sfx.trim_start` / `trim_end`, cf. « 2a ») ; nous avons demandé le même geste pour une musique ou un jingle dont la
source est un `.wav`, et pensé une fonctionnalité **commune aux `.wav`** (tout ce qui n'est pas un module tracker) plutôt que trois
copies. **Décisions :** (1) sections qui ne bougent pas quand on rogne : d'accord ; (2) des fondus pour les jingles,
« sur le même modèle que les effets et les musiques » ; (3) un bouton **Rogner** à cocher, qui montre une nouvelle barre SOUS l'onde,
avec ses deux poignées, réutilisable pour les trois sons.

**Livré :**
- `core/wav_edit.py` : l'unique endroit qui rogne et fond un WAV (`trim_of`, `trim_window`, `kept_range`, `kept_frames`,
  `trim_problem`, `apply_fades`, `MIN_TRIM_MS`), repris de `sfx_render` ; l'effet et la piste WAV en dépendent tous deux.
- `Music` (donc `Jingle`) gagne `trim_start` / `trim_end`, même convention qu'un effet (ms depuis le début du fichier, fin à 0 = jusqu'au
  bout, les deux à 0 = rien : un sidecar d'avant relit l'ancien comportement).
- `wav_to_xm` rogne le signal AVANT le plan (la coupe est à l'échantillon près) ; l'aperçu, le poids ROM et le build passent par lui,
  donc par `music_structure.wav_cut`, l'unique lecture des réglages. Test d'équivalence : le module écrit par le build est octet pour
  octet celui de l'aperçu (`tests/audio/test_wav_music_trim.py`).
- **Fondus des jingles WAV :** cuits dans la piste, comme ceux d'un effet (un jingle n'a pas de rampe d'exécution : il joue sur l'autre
  couche de Maxmod). Ceux d'une MUSIQUE restent appliqués par la console, jamais cuits (deux fois sinon). Un jingle MODULE n'a pas de
  fondu : les curseurs sont grisés, et `jingle_ignored_settings` le dit.
- Écran : `ui/sound_mixer/trim_bar.py` (`TrimBar` : le fichier entier en vignette, deux poignées, le reste estompé, double-clic = fichier
  entier) et, dans l'éditeur de musique, un bouton **Rogner** à cocher (un asset déjà rogné s'ouvre barre visible). Seul un WAV l'a. Le
  validateur refuse une découpe qui ne laisse rien, avertit qu'un module ignore la sienne.

**Écart avec la proposition du 2026-10-14 matin, à confirmer par l'auteur :** les sections d'un WAV sont dans le temps de la
**plage gardée** (celui de l'onde, que l'éditeur de musique dessine à partir du rendu du module), et NON dans le temps du fichier.
Elles ne bougent pas par rapport au SON : quand une poignée se déplace, `music_structure.retrim` les fait glisser avec lui. Pourquoi : ce
que l'éditeur lit sur `Music.sections` (le tableau, la bande, les poignées de l'onde, le plan du build) est en ms de la piste rendue ;
les garder dans le temps du fichier aurait demandé un décalage à chacun de ces endroits. **Le prix :** une section que la plage ne
contient plus est écrêtée, ou retirée (et dite dans la note sous la barre) ; réélargir la plage ne la ramène pas. Une section entièrement
DANS la plage suit le son dans les deux sens, sans perte. La boucle d'un morceau rogné boucle sur la plage gardée (comme sur le fichier
entier avant) : non contredit par l'auteur.

**Reste :** l'éditeur d'EFFET garde ses poignées de découpe sur l'onde ; la barre est faite pour le remplacer (même geste, même modèle)
mais ce déménagement, qui touche beaucoup de tests, n'est pas fait. Un jingle MODULE ne se rogne pas (point 3.2 ci-dessus : sa « plage
jouée » reste à faire, en positions d'ordre). L'écoute à l'oreille d'une coupe de jingle.

### Ce que ça touche (provisoire)

`core/asset_duplication.py` (nouveau) ; `ui/common/asset_kinds.py` (`actions` de chaque famille) ;
`ui/common/asset_finder.py` (menu, Ctrl+D, renommage en place) ; `ui/common/disk_view.py` et le callback de Disk ;
`core/models/audio.py` (champs `Sfx` : découpe, hauteur, panoramique ; champs `Jingle` : politique, plage) ;
`codegen/sfx_encode.py` (découpe, fondu) ; `ui/sound_mixer/sound_panel.py` (inspecteurs) ; le runtime audio généré pour
la hauteur par défaut, la variation et la politique du jingle ; `core/validator.py` ; `labels.json` et `labels_fr.json`
(clés FR d'office) ; tests dans `tests/audio/`.

### Ordre d'implémentation (proposé)

1. **Duplication, livrée le 2026-10-12.** `core/asset_duplication.py` (`duplicate`, `duplicate_many`, `duplicate_script`,
   `copy_name`) ; `AssetKind.duplicate` (chaque famille de finder la déclare par `_store_duplicator`) ; *Duplicate* + Ctrl+D
   (la touche réglée pour `common.duplicate`) dans le menu des finders, simple (« Duplicate ») et de lot (« Duplicate N items ») ;
   dans l'onglet Disk (les deux vues), `DiskCallbacks.duplicate_items` / `duplicable`, `window._disk_duplicate_items`.
   La copie : champs de l'original relus par la sérialisation du sidecar, MÊME `asset`, nouvel id, nom `coin_2` (dupliquer
   `coin_2` donne `coin_3`, pas `coin_2_2`), rangée à côté de l'original et, dans un finder, dans le même dossier d'auteur.
   Un finder ouvre aussitôt le renommage en place de l'unique copie. Un lot est UNE entrée d'historique (`MacroCmd`) et ses
   copies ont des noms uniques entre elles. **Disk : tout ou rien**. L'entrée n'apparaît que si TOUTE la sélection est faite
   d'assets duplicables et de sources (ni dossier, ni fichier non lu, ni texte/variables). **Une source se duplique aussi
   (demandé le 2026-10-12, sur la décision précédente de s'en abstenir)** : `asset_duplication.duplicate_sources` copie le
   fichier à côté de l'original, sous un nom libre dans SON dossier (toutes extensions confondues), en UNE commande annulable
   (`ImportFilesCmd`) ; la copie est une source LIBRE, aucun asset ne la cite. C'est ce qui permet de repartir d'un `.wav`
   retouché sans toucher à celui que des assets pointent. *Create* reste le geste qui en tire un asset ; un lot peut mêler
   assets et sources. `_duplicate_palette` (l'ancienne entrée « Duplicate » de la seule palette) est retirée : la palette
   passe par le même chemin. **Constats des vérifications :** sprites et fonds portent leur encodage DANS le sidecar, la
   copie n'est donc pas ré-encodée ; une palette copie ses couleurs et reçoit SON `.hex` (deux palettes ne partagent jamais
   un `.hex`, cf. `asset_creation.palette_is_taken`) ; les ids internes d'une scène sont locaux (ids de composants), aucun
   doublon à craindre ; un script se copie comme fichier, sous un nom libre parmi TOUS les `.lua`. **Restent :** les palettes
   n'ont pas encore d'id (5a), la copie n'en reçoit donc pas non plus ; annuler la copie d'une palette laisse son `.hex`
   (le `.palette` seul est retiré), comme pour la création, un `.hex` laissé dans `assets/palettes/` redevient une palette
   au chargement suivant. Tests : `tests/project/test_duplicate_asset.py`, `tests/ui/test_duplicate_ui.py`.
2. **SFX** : découpe (modèle, build, interface), puis hauteur et panoramique par défaut, puis le reste selon l'usage.
   - **2a. La découpe, livrée le 2026-10-12.** `Sfx.trim_start` / `Sfx.trim_end` (ms depuis le début du fichier ; fin à 0 = jusqu'à
     la fin ; les deux à 0 = l'effet entier, ce que relit un sidecar d'avant). `core/sfx_render.py` est le SEUL endroit qui
     découpe et ré-échantillonne (il reprend `effective_rate` et le rendu de `codegen/sfx_encode.py`) : le build et l'aperçu
     l'appellent tous les deux, donc ce qu'on voit et entend est ce que la ROM porte. La découpe se fait à la frame, sur le
     fichier au taux d'origine, AVANT le ré-échantillonnage ; sortie 16 bits mono, mmutil descend à 8. Écran : un nouvel
     éditeur d'effet (`ui/sound_mixer/sfx_editor.py`) prend la colonne centrale à la place de l'éditeur de musique, l'onde du
     fichier (`WaveformView`, les poignées sont celles de la boucle d'un WAV), deux champs début / fin en ms, *Reset trim*, et le
     poids annoncé (« 3,9 Kio en ROM au lieu de 7,8 Kio »), qui suit aussi le taux. `WaveformView` gagne une règle en ms pour une
     piste courte, et peut cacher la bascule Onde | Scope et la poignée de départ (ni l'un ni l'autre n'a de sens pour un
     effet). L'aperçu (`box_playback._prepare`) joue le rendu de la ROM, donc aussi le taux du projet, ce que l'aperçu d'un
     effet ignorait jusque-là. Le validateur avertit d'une découpe qui ne laisse rien (l'effet entier part alors en ROM, et
     le build le dit). Tests : `tests/audio/test_sfx_render.py`, `tests/ui/test_sfx_editor.py`.
   - **Constat, corrigé au passage (2026-10-12, repris le 2026-10-13) : le nom d'un son dans la ROM ne vient plus d'un nom de
     fichier.** mmutil numérote par POSITION (les effets dans l'ordre où on les lui passe, puis les modules) mais nomme
     `SFX_*` / `MOD_*` d'après le fichier (mesuré : `Coin Two.wav` donne `SFX_COIN_TWO` ; trois fois le même `coin.wav` donne
     trois lignes `SFX_COIN` numérotées 0, 1, 2. Il ne déduplique pas). Depuis qu'un asset pointe sa source, un effet nommé
     autrement que son fichier (`coin_2` sur `coin.wav`, ce que la duplication produit à chaque geste, mais aussi tout second
     asset créé depuis un `coin.wav`) faisait échouer le contrôle d'ids du build (« SFX_COIN_2 absent de soundbank.h »).
     Un premier correctif recopiait chaque fichier sous le nom de son asset (`stage_by_name`) ; **c'était un contournement**, et
     l'auteur l'a dit : le défaut est dans le modèle, l'identité d'un son dépendait d'un fichier de build alors qu'un asset
     ne devrait rien devoir à sa source. **Décision (2026-10-13) :** `MmutilAudio._number_ids` lit le RANG de chaque ligne
     `SFX_*` / `MOD_*` de `soundbank.h`, vérifie qu'il est celui attendu (effets puis modules, 0..n-1, dans l'ordre
     donné, le contrôle d'ids d'avant, qui cherchait des NOMS, devient un contrôle de rang), puis réécrit la ligne avec la
     constante de l'ASSET (`sfx_constant`, et `c_names.module_constant`, désormais le seul endroit qui écrit `MOD_*` : `main.c`,
     les tables de boîtes et le build s'y réfèrent). Les lignes `MSL_*` restent. Idempotent (un build en cache relit le header
     déjà réécrit). Deux assets dont les noms donneraient la même constante C (`coin 2` et `coin_2`) bloquent le build avec
     les deux noms. Plus aucune copie de fichier : `stage_by_name` est supprimé, seuls les fichiers réellement rendus
     (découpe, taux) passent par `build/sfx/<asset>.wav`, nommés d'après l'asset pour ne pas s'écraser entre eux ; les WAV de
     musique encapsulés s'appellent de même `<asset>.xm`. **Reste :** deux assets sur la même source sans réglage différent
     portent deux fois les mêmes octets en ROM (mmutil ne déduplique pas) ; à mesurer avant de s'en préoccuper.
     Tests : `tests/audio/test_soundbank_ids.py` (dont un mmutil réel sur trois effets d'un même `coin.wav`).
   - **2b. Hauteur et panoramique par défaut, livrés le 2026-10-13.** `Sfx.pitch` (% de la hauteur du fichier, 100 = tel quel,
     bornes 25–400 : `SFX_PITCH_MIN` / `SFX_PITCH_MAX`) et `Sfx.panning` (−100 gauche .. +100 droite, 0 centre) : la règle du
     volume, la ressource propose, l'API surcharge. `sfx:set_pitch` / `sfx:set_panning` posent une valeur ABSOLUE sur une
     lecture, quelle que soit celle de la ressource (la doc de l'API le disait déjà : « absolue »). **Rien ne change dans les
     octets de la ROM :** le build émet deux tables dans `main.c` (`sound_emit.sfx_default_tables`), une case par effet dans
     l'ordre du soundbank (l'`id` que reçoit `sfx_play`), que `sfx_play` lit à la place des constantes `1024` et `128`
     (`headers.py`). Comme `sfx_set_pitch` raisonne sur la hauteur COURANTE de chaque poignée (`g_sfx_rate`, qui existe parce
     qu'`mmEffectScaleRate` est cumulatif), `sfx_play` y range la hauteur de DÉPART et non plus 1024 ; sans cela, un
     `set_pitch` sur un effet réglé à 150 % se serait calculé sur une base fausse. Aucun site d'appel de `sfx_play` n'a changé
     (scripts, SoundFxComponent, boîtes sonores, frames d'animation, destruction d'acteur : tous passent l'`id`). Inspecteur
     d'effet : deux champs, Pitch et Panning. **Limites assumées :** l'aperçu de l'éditeur fait entendre la hauteur (le rendu
     est déclaré à un taux plus haut ou plus bas : mêmes échantillons, joués plus vite ou plus lentement) mais PAS le
     panoramique. Le lecteur joue un module mono au centre ; l'onde de la découpe ne bouge pas avec la hauteur (elle montre le
     fichier). Tests : `tests/audio/test_sfx_defaults.py`, `tests/ui/test_sfx_inspector_defaults.py`.
   - **2c. Variation aléatoire de hauteur et fondu de sortie, livrés le 2026-10-13.**
     **Variation :** `Sfx.pitch_variation` (± %, 0–50 : `SFX_PITCH_VARIATION_MAX`). À chaque lecture `sfx_play` tire la hauteur de
     départ dans `pitch` ± ce pourcentage, au dixième de pour cent près (1 % vaut déjà ~17 cents, un pas entier s'entendrait).
     **Décision, posée ici parce que le ROADMAP la laissait ouverte : le tirage a SON générateur** (`g_sfx_seed`, un LCG défini
     dans `main.c` et partagé par tous les fichiers C, comme la graine de la secousse de caméra), jamais celui de `math.rand`,
     régler la variation d'un effet ne doit pas changer ce que le jeu tire au hasard (une partie rejouée, un test de
     non-régression, un déterminisme que l'auteur croit tenir). **Et la graine est fixe** : la même suite de sons à chaque mise
     sous tension, comme `math.rand` ; l'amorcer sur le temps ou les touches est un choix de jeu, pas un défaut du moteur. La
     valeur tirée est mémorisée comme hauteur COURANTE (`g_sfx_rate`) : `set_pitch` reste absolu. Table de plus
     (`g_sfx_default_spread`). Le C généré de `sfx_play` est compilé sur l'hôte avec un `mmEffectEx` factice (gcc de msys2, test
     `test_the_generated_sfx_play_draws_inside_the_spread_and_never_outside`) : 2 000 tirages restent dans la marge et
     l'explorent en entier. L'aperçu de l'éditeur joue la hauteur de départ, sans tirage.
     **Fondu de sortie :** `Sfx.fade_out`, en FRAMES (1/60 s) comme tous les fondus de l'éditeur (« une durée ne s'écrit pas de
     deux façons selon l'écran »). Cuit dans l'échantillon par `core/sfx_render.render_sfx`, APRÈS la découpe et le
     ré-échantillonnage : rampe linéaire sur les dernières frames de la plage GARDÉE, jusqu'à un zéro exact sur le dernier
     échantillon. C'est lui qui supprime le clic d'une découpe en plein signal. Ni durée ni poids ne changent, et la console ne
     calcule rien. Un fondu SEUL suffit à faire rendre l'effet par le build (`sfx_render.is_edited`). Plus long que l'effet, il
     le couvre en entier. Écran : un champ *Fade out* (frames) à côté de la plage, et la rampe dessinée sur l'onde (une
     diagonale, la part étouffée assombrie) à la fin de la plage gardée ; l'aperçu joue le même rendu. Le fondu de sortie des
     MUSIQUES (`Music.fade_out`, appliqué à `music_stop`) reste un autre mécanisme, à l'exécution. **Le fondu d'entrée et l'écoute
     A/B du taux, qui restaient, sont livrés : voir « 2f ».** Tests : `tests/audio/test_sfx_render.py`, `tests/audio/test_sfx_defaults.py`,
     `tests/ui/test_sfx_editor.py`, `tests/ui/test_sfx_inspector_defaults.py`.
   - **2d. L'éditeur d'effet reprend trois outils de l'éditeur de musique, livrés le 2026-10-13.**
     **La poignée du fondu de sortie :** un rond sur le bas de l'onde (même bande et même geste que les poignées de fondu d'une
     musique), posé au début de la rampe (sur la fin de la plage gardée tant qu'il n'y a pas de fondu), qu'on glisse vers la
     gauche. Elle n'est pas collée au bord du FICHIER : un effet fond sur la fin de sa plage gardée. Plafonnée à 600 frames
     et au début de la plage ; le champ *Fade out* suit pendant le glisser, l'effet n'est écrit qu'au relâchement (comme la
     plage). Elle passe avant la poignée de fin de plage dans la bande du bas, comme les fondus d'une musique. Nouveau :
     `WaveformView.ramp_moving` / `ramp_changed`, `set_ramp_editable`.
     **La vue par canal :** `ChannelMeters`, le même widget qu'une musique, à droite de l'onde, une barre par canal du PROJET
     (`sound_channels`), dont l'effet occupe la première (un échantillon mono = une voix) ; elle suit le volume de l'effet et la
     tête de lecture. Elle lit le `Track` de l'aperçu (`BoxPlayer.track_for`), donc le son découpé, fondu et réglé en hauteur.
     **L'oscilloscope :** la bascule Onde | Scope réapparaît pour un effet, alimentée par le lecteur (`scope_window`) pendant
     l'écoute, et, à l'arrêt, par le début du rendu (un effet n'a pas de poignée de départ). **La tête de lecture** se pose sur
     le FICHIER : début de la plage gardée + durée de lecture × hauteur de départ (la hauteur accélère le rendu).
     `SfxEditor(track_provider)` ; sans fournisseur (tests, outils) ni canal ni scope. **Limite :** un effet est rendu une fois
     par réglage qui change son rendu (plage, fondu, taux, hauteur) dans le fil de l'interface, négligeable pour un effet
     court ; **mesuré le 2026-10-13 sur un effet long : voir « 2f »**. Tests : `tests/ui/test_sfx_editor.py` (glisser réel à la souris,
     plafonds, canaux, scope, tête de lecture).
   - **2e. Fluidité des réglages, panoramique et variation entendus, livrés le 2026-10-13.**
     **Constat :** chaque cran d'un champ de l'inspecteur d'effet écrivait le sidecar, reconstruisait l'explorateur et
     re-rendait l'aperçu, dont Panning et Variation, qui ne changent pas le rendu. **Décisions :**
     (1) *Écriture différée.* Une seule file, `ui/common/deferred_writes.py` (`DeferredWrites` : `schedule(clé, écriture)`
     fusionne par clé, `flush()`, `has_pending()`), qui nourrit le même état « Unsaved changes » que les scripts et le canvas
     (`window._has_pending_changes`). Elle part toute seule après un court silence, et AVANT tout ce qui lit le disque ou
     le quitte : changement d'écran, build, ouverture/création d'un projet, Ctrl+S, fermeture, perte du focus de la fenêtre.
     L'inspecteur d'asset sonore et l'éditeur d'effet l'adoptent ; les autres écrans à écriture en boucle (à recenser) la
     rejoindront un par un. (2) *Panoramique entendu, en stéréo :* la console l'est. `mmMixerMix` lit l'octet de panoramique
     de chaque voix et en tire un volume gauche (`256 − pan`) et un droit (`pan`), la loi linéaire du rendu de l'éditeur ;
     l'aperçu pose donc `panning_to_hardware(Sfx.panning)` dans le panoramique d'échantillon du module qu'il encapsule
     (`wav_to_xm(pan=…)`), sans que le build, qui n'en donne jamais, change d'un octet. (3) *Variation entendue :* à chaque ▶,
     l'aperçu tire la hauteur dans `pitch ± variation`, au dixième de pour cent comme `sfx_play`. Les rendus sont mis en cache
     par hauteur. Un réglage qui ne change pas le rendu (panoramique, variation) ne re-rend plus et n'actualise plus l'explorateur.
     **Ce que ça change dans le code :** `schedule_save(store, item)` (même fichier) est l'unique chemin d'écriture de
     l'inspecteur d'asset sonore (les trois familles) et de l'éditeur d'effet. Leurs écritures d'un même asset se fusionnent
     sous une clé ; elle ne réécrit pas un asset supprimé dans l'intervalle. `SfxEditor.refresh_soon` rend l'aperçu 150 ms
     après le dernier cran (le poids annoncé suit tout de suite). `_AssetInspectorBase._manager` / `_save`, que plus rien
     n'appelait, deviennent `_store(projet)`. `PAN_CENTER` devient public (`core/models/audio.py`), `varied_pitch` vit dans
     `core/sfx_render.py`. **Limites :** le tirage de l'aperçu ne bouge pas la frise (la tête de lecture) ; chaque hauteur
     tirée est rendue au premier ▶ qui la tire (non mesuré sur un effet long) ; la loi de panoramique de l'aperçu est la
     linéaire de maxmod (`256 − pan`, `pan`), vérifiée dans le désassemblage de `mmMixerMix`, pas à l'oreille sur émulateur ;
     seuls l'inspecteur d'asset sonore et l'éditeur d'effet passent par la file, les autres écrans qui écrivent à chaque
     cran (à recenser) restent à y rejoindre. Tests : `tests/ui/test_deferred_writes.py`, `tests/ui/test_sfx_preview_stereo.py`,
     `tests/ui/test_sfx_inspector_defaults.py`, `tests/ui/test_sfx_editor.py`.
     **Extension (2026-10-13), inventaire des écrans qui écrivaient à chaque cran, et étape 1.** Constat : les inspecteurs
     d'acteur, de scène et d'élément d'interface poussent un `SetFieldCmd` par valeur ; `SetFieldCmd.execute/undo` appelle
     `persist_fn` à chaque fois (la fusion ne fusionne que l'annulation), et l'inspecteur d'interface écrivait avec
     `save_all()` (`Project.save()`, une vingtaine de collections) pour un seul pixel de géométrie. **Livré :** l'inspecteur
     d'acteur (cas « scène ») et celui de scène écrivent la scène via `schedule_save(project.scenes, scène)` ; l'inspecteur
     d'interface planifie `save_all` sous la clé `"save_all"`. Seule l'ÉCRITURE est différée : `changed` et
     `scene_sprites_changed` (qui rafraîchissent canvas et autres écrans) restent immédiats. **Étape 2, livrée le même jour :**
     l'inspecteur d'interface n'appelle plus `save_all` pour un champ. Ce qu'un champ peut toucher est la mise en page qui
     porte l'élément, `texts.json` (le contenu qu'il affiche) et la scène (banque de palette du texte) : trois écritures
     ciblées, une fois chacune (`schedule_save` / `schedule_unwatched`, ce dernier posant la suspension du watcher une fois
     pour toutes) ; les marges nine-slice écrivent le seul fond qui les porte (`project.backgrounds`) ; le RENOMMAGE d'un
     élément garde `save_all` (`_persist_all`), parce qu'il réécrit scripts et références. **Reste, dans l'ordre :**
     (3) le cas « prefab » de l'inspecteur d'acteur, dont `save_prefab` propage
     en mémoire dans toutes les scènes et écrit N scènes, **renvoyé au chantier « Les prefabs, l'instance garde ce qu'elle
     surcharge »** (2026-10-13), qui le règle à la racine (le prefab seul s'écrit) ; scinder propagation et écriture n'a pas
     été retenu, ce serait du travail jeté. **Étapes 3 (hors prefab) et 4, livrées le même jour :** passent par la file
     l'éditeur de fond (découpe, taille de frame, vitesse, placement : `_persist_bg`, la notification du canvas reste
     immédiate), la vitesse d'animation du sprite (`SpriteRightPanel._save`), l'inspecteur d'asset de police
     (`_after_font_asset_change`), la caméra (`CameraInspector._save`), le calque de fond de l'inspecteur de scène
     (`_persist_scene`) et les réglages du projet (six écritures de `project.json` sous une clé commune,
     `_save_settings_soon`). **Le minuteur de 400 ms de la fenêtre (`_save_timer`) est supprimé** : son filet, `save_all`
     après un champ d'inspecteur d'acteur, passe par la même file (clé `"save_all"`), donc l'indicateur « Unsaved changes »
     et chaque vidage (écran, build, Ctrl+S, fermeture, perte du focus) le voient, deux mécanismes pour une même idée
     devenaient un seul. **Limite, volontaire :** ce filet réécrit encore tout le projet, une fois par geste ; l'enlever
     demande de prouver qu'aucun chemin d'écriture d'un acteur ne compte sur lui. **Ne passent PAS encore par la file** (gestes
     ponctuels, ou écrans sans écriture en boucle repérée) : l'éditeur de texte et celui de données (validation sur
     `editingFinished` ou commande), l'inpainting de fond et la peinture de sprite (une écriture par trait), l'inspecteur de
     projet (auteur, version). Tests : `tests/ui/test_inspector_deferred_save.py`.
   - **2f. Fondu d'entrée, écoute A/B du taux, mesure du rendu et décodage vérifié, livrés le 2026-10-13 (« termine l'écran SFX »).**
     **Fondu d'entrée :** `Sfx.fade_in`, en FRAMES comme le fondu de sortie, cuit dans les premières frames de la plage GARDÉE
     par `core/sfx_render.render_sfx`, le même code que le build, donc `sfx_encode`, l'aperçu et l'écran sont d'accord. Rampe
     linéaire depuis un zéro exact sur le premier échantillon ; les deux fondus se multiplient ; plus long que l'effet, il le
     couvre. Un fondu seul suffit à faire rendre l'effet (`is_edited`) ; le fichier d'aperçu porte son empreinte. Un sidecar
     d'avant le champ vaut 0. Écran : un champ *Fade in* à côté de *Fade out*. **Pas de poignée sur l'onde :** `WaveformView`
     ne porte qu'une rampe (celle de la sortie) et c'est un fichier que l'auteur modifie ; le champ suffit pour l'instant.
     **Écoute A/B du taux :** le ROADMAP demandait de vérifier si l'aperçu jouait déjà le fichier rééchantillonné, oui
     (`preview_file` applique le taux effectif). Il manquait de quoi COMPARER : un bouton *File rate* dans l'éditeur d'effet fait
     jouer le même effet au taux de son fichier (`BoxPlayer.set_original_rate`), découpe, fondus et hauteur restant appliqués.
     Il n'est disponible que si les deux taux diffèrent, retombe quand on ouvre un autre effet, et le résumé affiche à côté le
     poids ROM au taux du fichier. Ne change que l'aperçu : le build garde le taux de l'effet ou du projet. **Mesure du rendu
     (2026-10-13, hôte de l'auteur, WAV 44,1 kHz) :** de la lecture du fichier à l'onde (rendu du WAV de l'aperçu, rendu du module,
     enveloppe). 0,3 s : ~50 ms ; 3 s : ~130 ms ; 8 s : ~290 ms ; 20 s : ~560 ms, dont le rendu du module est les deux tiers. Un
     effet de GBA est court (un octet par frame en ROM : 8 s à 16 kHz pèsent environ 125 Kio) ; **pas de rendu hors du fil de l'interface**
     tant qu'un effet de plusieurs secondes n'est pas un cas d'usage, la minuterie de 150 ms de `refresh_soon` borne déjà le
     nombre de rendus d'un geste. **Décodage :** `tests/audio/test_wav_decode_depths.py` couvre 8, 16, 24 et 32 bits entiers (signe,
     échelle, ordre des octets), le même signal lu pareil à toute profondeur, le mixage stéréo, la réécriture en 16 bits mono d'un
     24 bits intact, et le refus du WAV flottant. Tests : `tests/audio/test_sfx_fade_in.py`, `tests/ui/test_sfx_editor.py`.
     **Ce qui reste de l'écran SFX :** rien de décidé ni de demandé, l'écoute sur émulateur d'un 24 bits, la mesure de la
     duplication d'octets en ROM, et une poignée de fondu d'entrée sur l'onde si l'auteur la veut.
   - **2g. La table de mixage d'un effet, livrée le 2026-10-14 (« voir le modèle »).** Volume,
     hauteur, variation aléatoire de la hauteur et les deux fondus se règlent à des CURSEURS verticaux, ceux d'une musique
     (`MixFaders`) : trois colonnes V, P, VAR et deux fondus IN, OUT, en bas de la colonne de droite (`SfxEditor.mix_panel`, que
     l'écran monte à la place de la table d'une musique ; une seule se montre). `MixFaders` reçoit désormais la liste de ses
     curseurs (`SFX_FADERS`, `SFX_FADES`) : même widget, même double-clic qui remet la valeur neutre, même saisie au clavier.
     La variation a sa valeur neutre à zéro, une extrémité de la course (pas d'aimant). Sortis de l'inspecteur d'effet, qui ne
     garde que le taux et le panoramique ; sortis aussi de la rangée de l'éditeur, les champs *Fade in* / *Fade out*. La poignée
     de fondu de l'onde écrit l'effet par le MÊME chemin qu'un curseur tenu (`_on_mix`). Seul ce que le curseur change à l'écran se
     rafraîchit : le volume règle la barre du canal ; la hauteur et les fondus re-rendent l'aperçu après un silence ; la variation
     ne rafraîchit rien. Écriture du sidecar par la file différée (une fois, après le geste). Trois infobulles nouvelles
     (`sfxedit.mix_*_tip`), quatre retirées. **Reste :** le panoramique est resté dans l'inspecteur. Voir « Le panoramique » plus bas.
     Tests : `tests/ui/test_sfx_editor.py`, `tests/ui/test_sfx_inspector_defaults.py`, `tests/ui/test_sound_screen_music.py`.
   - **Le panoramique d'un effet : piste (a) retenue par l'auteur le 2026-10-14, non codée.** Aujourd'hui `Sfx.panning` est une position FIXE
     par asset (−100 gauche .. +100 droite), que `sfx:set_panning` surcharge à l'appel. Or le panoramique d'un son vient
     d'ordinaire de la PROVENANCE de la source par rapport à un point de référence (l'écran, la caméra, le joueur), pas d'une
     constante de l'asset. **Ce qui existe déjà :** Maxmod règle un volume gauche et un droit PAR VOIX (`mmEffectPanning`,
     modifiable pendant la lecture) ; un script peut donc déjà panoramiquer d'après `actor.x`, à la main. **Ce que le moteur
     saurait faire seul :** un son joué depuis un acteur (script attaché, `SoundFxComponent`, frame d'animation, boîte sonore) connaît
     son émetteur ; sa position à l'écran (`x − caméra`, sur 240 px) donnerait le panoramique à `sfx_play`, sans script. **Pistes :**
     (a) garder le panoramique fixe par asset et ajouter un mode positionnel au PROJET (réglage global : actif ou non, point de
     référence (le centre de l'écran par défaut), largeur pour le panoramique maximal), l'asset gardant sa valeur pour les sons
     sans émetteur ; (b) remplacer le champ de l'asset par un simple « positionnel : oui / non » (un son d'interface ne l'est
     pas), le reste vivant au projet ; (c) retirer le panoramique de l'asset et ne le laisser qu'au script. **À trancher :** le
     rôle du champ de l'asset si le mode positionnel existe ; ce qui compte comme émetteur ; si un son qui dure se met à jour
     pendant que l'émetteur bouge (coût : un appel par frame et par voix) ; la loi de panoramique (celle de Maxmod est linéaire,
     la somme des deux côtés vaut 1 au centre, donc un son centré est plus faible dans chaque oreille qu'un son à fond d'un côté).
     **À savoir :** le haut-parleur de la GBA est monophonique, le panoramique ne s'entend qu'au casque ou à l'émulateur.
     **Décision (2026-10-14, de l'auteur) : la piste (a).** Le champ `Sfx.panning` reste, pour la position fixe d'un son sans émetteur
     (un son d'interface, par exemple) ; un réglage de PROJET ajoute le mode positionnel (actif ou non, point de référence, largeur du
     panoramique maximal), et un son joué depuis un acteur se place d'après sa position à l'écran. **Reste à écrire avant d'ouvrir :** le
     réglage et son écran (Project Settings, carte Sound), le calcul dans `sfx_play` (un acteur émetteur à passer, ou une variante
     `sfx_play_at`), l'effet sur un son qui dure, l'aperçu de l'éditeur (un point mobile pour l'entendre), et les tests. Aucune de ces
     questions n'est tranchée.
   - **Correctif (2026-10-13) : un son COURT ne s'entendait pas à l'aperçu.** Signalé sur des effets de l'auteur (`ball_roll`, `bomb_lay2`,
     `break`, `bump`…, 0,13 à 0,2 s ; `blade` et `bomb`, plus longs, jouaient). Le deck tire loin devant la carte son : un effet
     court est tout entier produit dès le premier paquet, `deck.playing` retombe aussitôt, et `_refresh_rom_progress` (qui
     décoche le bouton quand `BoxPlayer.sounding` est faux) fermait la carte son avant qu'on ait entendu quoi que ce soit.
     Ce n'était ni le format (24 bits stéréo 44,1 kHz : les 63 effets du dossier `fx-wav` se rendent, démarrent et produisent de
     l'audio dans un test sans carte son) ni les réglages. `sounding` suit désormais ce que la carte son a JOUÉ :
     `_DeckDevice.sound_frames` (les trames tirées jusqu'à la fin du son) et `_AudioOutput.still_audible`, calculé sur les valeurs
     que `_publish` donne déjà à l'interface (qui ne touche pas à la carte son depuis son thread). Test sans carte son :
     `tests/audio/test_short_sound_stays_audible.py`. **Confirmé à l'oreille par l'auteur (2026-10-13)** sur les effets qu'il avait signalés.
   - **Correctif (2026-10-13) : un WAV 24 ou 32 bits était refusé à l'import.** Signalé sur les 21 effets d'un dossier `platformer/wav`
     (tous en 24 bits). `check_audio_file` les écartait parce que mmutil ne convertit que le 8 et le 16 bits, et qu'il construit la
     ROM sans le dire, avec un effet muet. **Le refus était juste, mais il tombait au mauvais endroit :** l'éditeur ré-encode déjà
     un effet pour la découpe et le taux, dans le dossier de build, sans toucher au fichier. Il le fait donc aussi pour la
     profondeur. `sfx_render.read_wav` décode le 24 bits (trois octets little-endian posés en tête d'un entier 32 bits signé) et le
     32 bits entier ; `write_sfx` réécrit en 16 bits mono, que mmutil reçoit. `sfx_encode` et `preview_file` ré-encodent tout WAV dont
     la largeur n'est pas 8 ou 16 bits, même sans découpe ni changement de taux (`sfx_render.WAV_BITS_OK_BYTES`).
     **Étendu aux musiques et aux jingles le même jour :** `wav_module._read_mono` lit par ce décodeur unique (plus de second
     décodeur), donc `wav_to_xm` encapsule un WAV 24 bits comme un 16. `WAV_BITS_DECODED` (`core/models/audio.py`) = ce que l'import
     accepte, pour les trois familles ; `WAV_BITS_OK` reste ce que mmutil lit tel quel. Seul un autre format (flottant, ADPCM,
     fichier abîmé) est encore refusé, avec la raison. Un essai sur `coin.wav` (24 bits) : accepté comme musique et comme jingle,
     module de 7 693 octets. Tests : `tests/project/test_create_asset.py` (le cas « refusé » est désormais un fichier illisible,
     plus un 24 bits) ; `tests/audio/test_sfx_render.py`, `tests/audio/test_wav_music.py` inchangés et verts.
     **Le test dédié au décodage 24/32 bits est écrit** (`tests/audio/test_wav_decode_depths.py`, 2026-10-13). **Reste :**
     l'écoute sur émulateur d'un effet sorti d'un 24 bits.
3. **Jingle** : politique vis-à-vis de la musique, puis plage jouée, puis l'avertissement de canaux.

### Ce que ça ne fait pas

- Ne modifie jamais le fichier source.
- Ne lie pas une copie à son original.
- N'ajoute ni priorité ni délai entre effets (voir plus haut).
- Ne fait pas de l'éditeur un outil de montage audio : découper, régler, jamais composer.

---

## Un pont entre l'écran Texte et les tables de données (créer un dialogue)

**Parcours livré le 2026-10-17 :** le chantier
[TextBox à plusieurs entrées](#textbox-plusieurs-entrées-pour-préparer-un-dialogue) fournit
**Export as table / Update table** depuis la boîte, vers les tables ordinaires et leurs colonnes
`text`. Le contrat de mise à jour, de conservation des colonnes personnalisées et des lignes
manuelles est implémenté et décrit dans cette section. Les pistes A et B ci-dessous restent
des parcours complémentaires.

### D'où vient la question (2026-10-10)

Depuis la v0.21, un dialogue est une **table de données** dont une colonne est de type `text`
(`data.Dialogues[i].replique`) : le script la parcourt, et la réplique reste traduisible. Le modèle est
bon ; **la saisie est fastidieuse**. Pour écrire dix répliques, l'auteur doit :

1. créer la table dans l'écran Données et lui ajouter une colonne `text` ;
2. pour chaque réplique, aller dans l'écran Texte, créer l'entrée, la ranger, lui donner un contenu ;
3. revenir dans la grille, ouvrir la cellule de la ligne et y choisir la clé au milieu de toutes les autres.

Deux écrans, un aller-retour par réplique, et la clé (qui n'a d'intérêt que pour la machine) au centre du geste.
L'infobulle de la cellule montre bien le contenu (`_text_preview`), mais seulement une fois la clé posée.

### Le principe

**Le pont ne crée pas de modèle.** Un dialogue n'est ni un nouvel asset ni un nouvel écran : c'est toujours une
`DataTable` et des `Text`, écrits par les commandes annulables qui existent déjà (`InsertRowCmd`, `SetCellCmd`,
`CreateTextForElementCmd`…). Le pont est un **geste** qui enchaîne ces écritures, pas une structure de plus. Il
tient la ligne posée dès la v0.3 : pas d'arbre de conversation, pas de choix branchés, pas d'éditeur de dialogue
(cf. [Table de textes](ARCHITECTURE.md#textes-du-joueur--table-de-chaînes) et « Ce qui reste au script »).

### Pistes (proposées, non verrouillées)

- **A. Depuis l'écran Texte : « Envoyer vers une table ».** L'auteur sélectionne des textes dans la table
  (l'ordre de la sélection est l'ordre des lignes), choisit une table de données existante ou en crée une, et
  chaque texte devient une ligne dont la colonne `text` porte sa clé. C'est le geste de qui écrit d'abord ses
  répliques puis les assemble.
- **B. Depuis la grille de données : « Nouveau texte » dans la cellule.** Une cellule de type `text` offre, en
  tête de sa liste, *Nouveau texte…* : l'entrée est créée à l'instant (clé proposée par le rangement, jamais
  tapée), rangée sous le nom de la table, et la cellule la référence. C'est le geste de qui construit la
  conversation ligne à ligne. Le contenu s'écrit ensuite dans l'écran Texte, ou sur place si la cellule le permet.
- **C. Les deux sens se rejoignent sur le rangement.** Le chemin d'un texte donne sa clé à la création ; si le
  rangement d'un dialogue porte le nom de sa table, la clé de la réplique `n` se dérive d'elle-même
  (`<table>_<n>`) et plus personne ne la nomme à la main. Le lien table ↔ rangement reste une convention de
  création, jamais une contrainte (les deux peuvent diverger ensuite).

**Décidé le 2026-10-10 : A et B, les deux.** A sert à l'écriture, B à l'assemblage. Ordre de livraison proposé :
**B d'abord** (une entrée de plus dans une liste déroulante qui existe), puis A, qui demande une action de
sélection multiple vers un écran voisin. C reste une convention de création, à trancher avec les deux.

### Ce que ça touche (provisoire)

| Fichier | Sort |
| --- | --- |
| `ui/data_editor/data_grid_panel.py` | `_DataCellDelegate` : l'éditeur de cellule `text` gagne l'entrée « Nouveau texte… » (piste B) |
| `ui/data_editor/data_commands.py` | une commande qui crée le texte et pose la cellule **dans une seule annulation** |
| `ui/text_editor/text_panel.py`, `text_table.py` | menu de la sélection : « Envoyer vers une table… » (piste A) |
| `ui/text_editor/text_commands.py` | `CreateTextForElementCmd` est le modèle à suivre : création d'un texte rangé, clé dérivée |
| `ui/screens.py` | aucune navigation entre écrans n'existe aujourd'hui : voir « À trancher » |

`core/models/text.py`, `core/models/data_table.py`, le checker, le build et la ROM ne bougent pas.

### À trancher avant d'ouvrir

1. ~~A, B, ou les deux ?~~, **tranché le 2026-10-10 : les deux** (B puis A, voir « Pistes »).
2. **Le contenu s'écrit où ?** Avec la piste B, l'auteur crée la réplique depuis la grille : l'écrit-il dans la
   cellule (qui doit alors devenir un petit éditeur de texte) ou est-il renvoyé à l'écran Texte ? C'est la même
   question que « le contenu s'édite dans la table » du chantier [L'écran Texte n'édite et ne range que du contenu](#lécran-texte-nédite-et-ne-range-que-du-contenu) :
   les deux chantiers partagent le délégué de contenu et doivent se décider ensemble.
3. **Aller d'un écran à l'autre.** L'infobulle de la cellule est aujourd'hui la seule jonction. Faut-il un « Ouvrir
   dans l'écran Texte » (sélection du texte, bascule d'écran) ? Aucun mécanisme de navigation entre écrans n'est
   encore posé : c'est le coût caché de la piste A comme du point précédent.
4. **Que contient une ligne de dialogue ?** Une colonne `text` suffit à une réplique ; un dialogue réel veut aussi
   un locuteur, un portrait, un son. Le pont crée-t-il les colonnes d'un **gabarit** (réplique seule, ou
   locuteur + réplique), ou laisse-t-il l'auteur les ajouter ? Un gabarit ne doit pas devenir un type « Dialogue ».
5. **Le rangement du dialogue.** Le nom d'une table est un identifiant (`Dialogues`), un rangement est une liste
   de libellés libres : la dérivation de la piste C marche-t-elle sans les confondre ?
6. **Ordre.** Une table a un ordre, la table de textes est triée à l'écran : l'ordre de l'envoi doit être celui de
   la sélection, pas celui de l'affichage. À vérifier à l'usage.

### Ce que ça ne fait pas

- Ne crée ni asset « Dialogue », ni écran de dialogue, ni arbre de conversation, ni choix branchés.
- Ne dit rien de l'enchaînement : *quand* une réplique s'affiche reste au script.
- Ne change ni `texts.json`, ni le format des tables de données, ni la ROM.

---

## v1.0 (Le pipeline 2D complet)

### L'objectif concret (cinq genres)

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
de « V-Rally 3 » pour la v3.1, une cible se compare, une capacité s'étend indéfiniment :

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

### Le deuxième jeu de démo (la démo tactique)

Le genre tactique a été choisi et la boucle complète a été construite : grille, curseur,
sélection, statistiques pilotées par table, portée, déplacement, menu d'action et tour
sauvegardé. Le test à 40 scènes / 200 sprites a également validé le passage à l'échelle.
Les frictions que cette démo a mises au jour sont consignées [plus haut](#frictions-relevées-en-construisant-la-démo-tactique-2026-09-20) ; elles bornent le reliquat de
stabilisation plutôt que de laisser le choix du jeu de validation ouvert.

Le reste de la version demeure la stabilisation du runtime et de l'éditeur, ainsi que la
documentation utilisateur.

### Ce qu'une « v1.0-alpha » exige, et qui n'est pas une fonctionnalité

Quatre points sans lesquels le mot « 1.0 » ne tient pas, même en `-alpha`. Aucun n'ajoute de capacité au moteur ;
tous conditionnent le fait que quelqu'un puisse réellement bâtir dessus. **Trois sont
réglés** ; il reste le contenu de départ qui accompagne l'auteur.

- ~~**Une licence.**~~ **FAIT.** Le point était plus aigu ici qu'ailleurs : l'éditeur **copie
  son propre C dans la ROM de l'utilisateur** (`gba_engine.h` et les sources générées), donc
  sous une licence unique tout jeu construit avec l'outil serait devenu un travail dérivé sous
  GPL. D'où **deux licences, et c'est la découpe qui compte** : `LICENSE` (GPL-3.0-only) couvre
  l'ÉDITEUR, `runtime/LICENSE` (zlib) couvre le moteur recopié dans la ROM. Le jeu et sa ROM
  appartiennent entièrement à leur auteur, sans rien à publier ni à demander.
  `THIRD-PARTY-NOTICES.md` recense les composants redistribués, obligation déjà active
  puisqu'ils sont dans l'installateur. Reste hors de ce point, et à trancher ailleurs : le nom
  et la marque, où « GBA » porte un risque Nintendo.
- ~~**Des formats que git sait relire.**~~ **FAIT dans la v0.24.** Les grilles s'écrivent par
  rangée et les couleurs en hexadécimal ; les anciens formats restent lisibles. La migration a
  réduit le projet de démo de 14 444 à 3 679 lignes, donnée pour donnée, et le détail est dans
  [l'archive v0.24](changelog/archives/v0.24.md).
- **Des modèles de départ.** Un seul projet de démo existe (Pong). Un modèle « platformer »
  enseigne l'API sans qu'on lise une ligne de documentation, et c'est ce qui décide qu'on
  reste après la première heure. Même famille que le deuxième jeu de démo : du contenu qui
  enseigne, pas une fonctionnalité.
- ~~**La vérification que ça tient à l'échelle.**~~ **FAIT.** Le projet de test à 40 scènes /
  200 sprites passe de bout en bout ; les mesures et les limites relevées sont consignées dans
  [les frictions de la démo tactique](#frictions-relevées-en-construisant-la-démo-tactique-2026-09-20).

### Ouvert

- Le contenu exact du modèle de départ : il doit enseigner l'API dès la première heure, sans
  devenir une fonctionnalité supplémentaire du moteur.
- ~~Les menus et listes (curseur, défilement, sélection)~~ **Tranché le 2026-08-19 : le moteur
  en prend une part, et c'est la v0.22.** La question posée ici (« si les trois genres à menus
  le rendent pénible, c'est ici que ça se verra ») a reçu sa réponse d'un projet cible à arbre
  de compétences, inventaire et équipement : ce n'est pas un confort qu'on juge après coup,
  c'est un tiers du contenu, entièrement à la charge de l'auteur.

---

## Au-delà de la v1.0

### Diffuser un jeu desktop (le Backstage Player)

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le
2026-10-10).** Une ROM `.gba` reste le coeur et le format universel du jeu, mais elle ne
constitue pas à elle seule une expérience de diffusion grand public : le joueur doit installer
et configurer un émulateur. Après l'export navigateur/itch.io de la v0.29, Backstage doit pouvoir
produire un **package desktop jouable directement**.

Le package ne transforme pas la ROM en binaire PC. Il rassemble la ROM et un lecteur générique,
nommé provisoirement **Backstage Player**, qui l'exécute au moyen du coeur mGBA. Le joueur lance
le jeu, pas un émulateur : aucune interface mGBA ne doit apparaître.

**Première cible : Windows.** Avant un installateur, un ZIP portable est suffisant pour valider
la chaîne et l'expérience. Le Player doit démarrer directement sur le jeu, gérer le plein écran
(`F11` et `Alt+Entrée`), la mise à l'échelle entière sans flou, la pause à la perte de focus, le
clavier, la manette, le volume et des sauvegardes rangées par jeu. Le titre, l'icône, l'image de
fond éventuelle, la taille de fenêtre et le démarrage en plein écran sont les métadonnées de
l'export. macOS et Linux restent hors de ce premier périmètre.

Le Player est une **application de jeu native à fenêtre unique**, pas une fenêtre d'émulateur
rhabillée : ses réglages et sa pause vivent dans un overlay rendu au-dessus du jeu, comme des
menus du jeu lui-même. Aucune barre de menus ni surface de réglages mGBA ne doit être visible.
Selon le choix de l'auteur, la sortie est soit nue (pixels nets, jeu seul), soit composée avec un
fond, un cadre, un logo et des éléments décoratifs. Le rendu du jeu reste une surface distincte :
elle peut recevoir un profil de shader fourni (pixels stricts, LCD doux, CRT léger…) ou un shader
GLSL personnalisé, sans que cela affecte l'habillage ni le coeur d'émulation.

**Une API de plateforme, pas une API Steam dans la ROM.** Le runtime exposera à terme des actions
neutres telles que `platform:unlock_achievement("first_boss")`, `platform:set_stat(...)` et
`platform:increment_stat(...)`. Elles émettent un événement vers le Player par un pont ROM →
lecteur ; elles ne dépendent ni d'un App ID ni du SDK Steam. Le lecteur décide ensuite : aucun
service, succès locaux, ou Steamworks. Une ROM lancée dans un émulateur ordinaire reste jouable ;
ces actions n'en deviennent jamais une dépendance.

**Steam est une cible d'export facultative.** Pour un jeu publié sur Steam, le Player initialise
Steamworks, transmet succès et statistiques, puis pourra prendre en charge le Cloud et la présence.
Chaque jeu a son propre App ID et ses succès, définis par son auteur dans Steamworks : Backstage ne
les crée pas et n'embarque aucun identifiant de développement. Le package Steam reste tolérant à
l'absence du client pour les builds non-Steam ; le comportement Steam-only éventuel relève de
l'auteur du jeu. Le premier périmètre exclut le Workshop, le multijoueur, l'inventaire et le DRM.

### Décisions verrouillées

- La ROM est inchangée et reste exportable seule ; le desktop est une cible supplémentaire.
- Le lecteur est générique et habillé avec les métadonnées du jeu, pas un fork par projet.
- L'expérience de base (plein écran, pixels nets, contrôles, sauvegardes) précède Steam.
- Le coeur mGBA est intégré nativement au Player : jamais lancement ou encapsulation de
  l'application mGBA installée sur la machine.
- Le Player est une fenêtre unique dont pause, volume, contrôles, plein écran et quitter sont un
  overlay maison ; ils font partie de l'expérience de jeu, pas du chrome système.
- L'auteur choisit l'habillage (aucun, ou fond/cadre/logo/décor) et le rendu de la surface du jeu
  (profil de shader livré ou shader GLSL personnalisé).
- L'API de script est indépendante de tout distributeur ; Steamworks vit uniquement dans le
  Player et seulement dans l'export Steam.
- L'intégration Steam commence par succès, statistiques, Cloud et présence ; le reste est hors
  périmètre.

### Ouvert

- Le format du pont ROM → Player et la persistance éventuelle de succès locaux.
- Le moment où l'export quitte le ZIP portable pour un installateur signé, et les critères pour
  ouvrir macOS puis Linux.
- La place dans l'interface : générateur autonome éprouvé d'abord, puis éventuellement étape
  finale du build de l'éditeur.

### Chantier transverse (le singleton `mixer`)

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
| `mixer.music` / `mixer.jingle` | propriétés lecture seule : lecture active, ou `nil` | s.o. |

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

**Avancé, les boîtes ne disparaissent pas, elles changent de niveau.** Elles restent des
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

### Chantier transverse (nommer l'accès à un sous-objet de l'instance)

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-27).** Né du
chantier v0.16 : `self:collision_box("hitbox")` est un constructeur déguisé en méthode. La règle de
provenance ne le range nulle part (le garder tel quel comme exception nommée, ou le ranger sous un
module `self.boxes.get` ?). Élargi en discutant ce point : le sprite est exactement le même genre de
composant (il n'appartient qu'à l'acteur), mais suit une forme complètement différente, ses
propriétés sont APLATIES sur `self` (`self.frame`, `self.visible`...), sans constructeur du tout,
parce qu'un acteur n'affiche jamais qu'UN SEUL sprite à la fois (aucune ambiguïté sur « lequel »).
Conséquence : on ne peut aujourd'hui interroger que l'apparence ACTIVE (`self.active_sprite`,
`self:activate_sprite(id)`), impossible de lire les propriétés d'une apparence sprite inactive sans
l'activer d'abord.

**Si ce point se rouvre**, il doit couvrir les DEUX cas ensemble (boîtes de collision multiples,
apparences sprite inactives), pour ne pas trancher deux fois la même question (« comment
nomme-t-on l'accès à un sous-objet précis d'une instance ? ») avec deux réponses différentes.

### Chantier transverse (la chaîne `if/elseif` sur une constante devient un `switch` C)

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (piste notée le 2026-10-06).**
Piste de réflexion, **rien de verrouillé, code non commencé.** Le parseur Lua reste la porte
d'entrée de tous les scripts ; une syntaxe `switch` maison obligerait à préparser le texte avant
l'AST (numéros de ligne décalés, `case A : …` ambigu avec un appel de méthode Lua, `switch`
disparu avant que le codegen puisse l'émettre), **écartée**. Le C brut l'est aussi : le script
sortirait de l'AST sans analyse (identité des variables, types, graphe de dépendances, garde-fous du
sous-ensemble Lua).

**Piste retenue : zéro syntaxe nouvelle.** Le codegen reconnaît une chaîne
`if s == A … elseif s == B … else … end` dont la variable `s` est la même d'un bout à l'autre et dont
les valeurs sont des constantes ou des membres d'énumération, et émet un `switch` C. Le Lua reste du
Lua pur ; l'optimisation est invisible pour qui écrit le script.

**Ce que ça apporte, et ce que ça n'apporte pas.** Ce n'est **pas** présenté comme une optimisation :
sur l'ARM7TDMI, la table de sauts coûte un saut indirect (pipeline vidé, ~3 cycles) et une lecture en
ROM avec wait states ; pour 3-4 cas une chaîne de comparaisons peut être plus rapide, et GCC choisit
lui-même selon la densité des valeurs. Les raisons de le faire : la lisibilité du C généré, et
`-Wswitch` qui signale un enum non couvert. **Gain de perf non mesuré** : à vérifier par `objdump`
sur une machine à états réelle (~8 états) avant d'en parler comme d'un gain.

**À trancher avant d'ouvrir** : la forme exacte reconnue (`==` seulement ? chaînes imbriquées ?
cas sans `else` ?) ; ce qui se passe quand deux branches testent la même valeur (erreur de build ou
première gagnante, comme en Lua) ; si le warning d'énumération non couverte est émis côté éditeur
ou laissé à GCC.

### Chantier transverse (l'atelier Texte réuni, écrire et voir dans un même écran, **ABANDONNÉ**)

**Remplacé le 2026-10-10** par [L'écran Texte n'édite et ne range que du contenu](#lécran-texte-nédite-et-ne-range-que-du-contenu). Ce chantier voulait faire du rendu GBA la surface d'édition (projection source ↔ affichage, vue balisage en police moteur) ; on retire au contraire l'aperçu de l'écran et le contenu s'édite dans la table. Sa décision verrouillée du 2026-09-19 est caduque.

### Chantier transverse (préparer une image riche à l'import, recadrer et redimensionner sans toucher au PNG)

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-29).** Les tranches
4bpp et 8bpp sont livrées ; reste la tranche bitmap (son propre panneau, pas commencée) et la validation à la
souris dans l'éditeur.

#### D'où vient la question (2026-09-26)

Une photo de 474×314 importée en tuilé 8bpp donne 2194 tuiles uniques pour un budget de 256 : le
Background Editor le **dit** (avertissement rouge « Exceeds VRAM ») mais ne laisse rien faire,
l'auteur n'a que le mode (tuilé/bitmap, profondeur) et un logiciel externe. Et le tuilé tronque
l'index de tuile à 10 bits (`pack_se`), donc au-delà de 1024 la carte se brouille en silence.

#### Le principe

Deux gestes sur la **préparation de la source**, avant l'encodage, portés par le sidecar :

- **Recadrer** (`import_crop`, en pixels de la source) puis **redimensionner** (`import_size`, en
  pixels de l'image préparée), dans cet ordre ;
- **Miroir** (`mirror_x`, `mirror_y`) : une barre verticale ou horizontale à poignée centrale, posée
  par un bouton de l'en-tête du canvas ; le côté gauche (haut) se reflète de l'autre côté. Appliqué
  après le redimensionnement et **avant** la compression (il peut changer le nombre de tuiles) ;
- le PNG n'est **jamais** modifié : `prepare_source` produit une image PIL en mémoire, que
  reçoit `encode_by_mode`, l'unique endroit qui choisit l'encodeur. Tous les chemins qui
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
  préservée), Lanczos sinon, aucun réglage exposé.
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
sont celles des tuiles qui tiennent, sans la réduction, un minimum, pas une promesse.

#### Jouer avec la compression (l'inspecteur contextuel (2026-09-26))

L'auteur règle la compression avec des curseurs et voit le rendu au canvas ; un réglage relance
l'encodage hors-thread après 250 ms. **L'inspecteur est contextuel** : chaque mode (tuilé
4bpp / 8bpp, bitmap 8 / 16bpp) a sa boîte de réglages, absente des autres. Aucun refus d'office :
une image hors budget s'encode quand même, et les mesures disent ce que ça coûte.

**Tranche 1, tuilé 4bpp (livrée).** Réglages portés par le sidecar (`BackgroundAsset.compression`,
seuls les écarts au défaut sont écrits) :

- **Palettes** (1–16) et **couleurs par palette** (2–15). Sans perte quand l'image le permet (pixel art :
  packing exact) ; sinon `core/bg_palette_cluster.py` regroupe les tuiles qui se ressemblent, taille une
  palette par groupe depuis ses pixels réels et affine, l'ancienne méthode (garder les 16 palettes les
  plus employées, renvoyer le reste au plus proche) laissait l'océan d'une photo sans ses bleus, même
  au réglage par défaut ;
- **Couleurs globales** : réduire toute l'image avant le découpage en tuiles. C'est ce qui rend
  les tuiles voisines compatibles, donc ce qui fait rentrer une photo (le 4bpp par défaut y perd
  la moitié de l'image) ;
- **Tuiles** : cible de tuiles uniques ; `core/bg_tile_merge.py` regroupe par **plus faible perte**
  (agglomération de Ward, coût pondéré par les cases couvertes, distance qui pèse la luminance),
  garde la tuile la plus centrale de chaque groupe et renvoie les autres cases vers la variante
  gardée la plus proche. Le premier essai (garder « les plus employées ») écrasait le bas de
  l'image : sur une photo toutes les tuiles sont employées une fois, et l'égalité tombait sur
  l'ordre de balayage. Reste à explorer : réutiliser une tuile sous une autre banque de palette ;
- **Méthode** de réduction dans une tuile, et le **dithering** (agit sur la réduction globale).

**Tranche 2, tuilé 8bpp (livrée).** Même boîte, contextuelle : **Couleurs** de l'unique palette
(2–255, `palette_colors`), **Tuiles** (la même fusion par plus faible perte, budget 256 par charblock),
**méthode** de quantification (median-cut, octree, couverture max, quantifieurs de PIL) et
**dithering**. Le dithering des modes 8bpp et bitmap était sans effet : `Image.quantize(dither=…)`
ignore l'option tant qu'on ne lui donne pas de palette. Corrigé pour les deux (`_quantize_rgb`),
test à l'appui. Reste la tranche bitmap : son propre panneau.

#### Ce que ça ne fait pas

Pas d'annulation pas-à-pas (Ctrl+Z) : la recompression est asynchrone et « Original » suffit à
revenir. Pas de réglage de couleurs (le mode et la profondeur existent déjà dans l'inspecteur).

### Chantier produit à planifier (Color Tile Painter : commencer un niveau sans assets)

**Noté le 2026-10-12. Livré pour l'essentiel le 2026-10-14. Voir la section « L'écran Fond », ci-dessous ; le texte qui suit est l'état de départ, gardé pour mémoire.** Un auteur qui arrive sans
assets ne doit pas être bloqué avant même de pouvoir tester son level design. Ce petit outil lui
permet de composer vite un fond de prototype, jouable immédiatement, puis de le remplacer ou de
le retravailler plus tard avec ses vrais visuels.

#### Le minimum utile

- Choisir une palette existante, puis une des **16 couleurs** sous forme de pastilles rondes ; la
  première correspond à la transparence.
- Peindre sur une grille, par clic ou glisser, avec un pinceau carré aligné sur les tuiles de
  **8 px, 16 px ou 32 px**. Le pinceau 32 px reste une pose de couleur par cellules de base, pas
  une image redimensionnée.
- Créer ou mettre à jour un **BackgroundAsset éditable** : le projet conserve les indices de
  palette et la grille, pas seulement une image aplatie, afin que l'auteur puisse changer une
  couleur ou repeindre plus tard.
- Exporter ce même résultat en **PNG**, pour l'archiver, le partager ou le poursuivre dans un
  outil graphique externe.

#### Décisions déjà claires

- C'est un outil de **blockout**, délibérément limité aux aplats : ni pinceau libre, ni import
  d'illustration, ni retouche photo. Il ne remet donc pas en cause le refus d'un éditeur d'image
  généraliste.
- Le résultat suit le pipeline de fonds existant et ses contraintes GBA (palette indexée,
  transparence, tuilage) dès la première peinture : pas de conversion opaque au moment du build.
- Un fond créé ainsi reste un fond normal dans le projet ; l'export PNG est une sortie
  complémentaire, jamais sa seule forme sauvegardée.

#### À trancher au démarrage

- Où placer l'entrée dans l'interface : mode du Background Editor, ou création de fond vierge
  depuis le navigateur d'assets.
- Les dimensions initiales et le comportement hors limites (agrandir le canevas, ou demander une
  taille à la création).
- L'annulation/historique de peinture, et les raccourcis pour le sélecteur, la gomme et les trois
  tailles de pinceau.

### L'écran Fond (ce qui est livré le 2026-10-14, et les pistes notées pour plus tard)

**Livré (2026-10-14).** Le Color Tile Painter ci-dessus est devenu un pinceau à deux modes
(*Inpaint* : surcharge de palette ; *Paint* : couleur posée en CALQUE par-dessus l'image, `BackgroundAsset.tile_paint`, que
la gomme et le clic droit retirent) ; « Create empty » écrit un vrai PNG indexé transparent dans le dossier affiché par
l'onglet Disk ; « Save as PNG » cuit tout dans un PNG **indexé par banques** (`core/bg_bake.py` : index = banque × 16 +
couleur, tRNS) que l'importateur relit à l'identique, banques comprises ; « Export to PNG… » ; « Relink source… » (annulable,
ré-import natif d'une image) ; deux cartes dans l'inspecteur, *Image adjustments* (teinte, saturation, luminosité,
contraste : `core/bg_adjust.py`, aperçu en direct) et *Compression* (méthode, curseurs, type de dithering, diffusion ou
trames ordonnées de Bayer 4×4 / 8×8) ; plus aucun curseur ne compresse : « Compress » est le seul geste, un aperçu de la
compression se calcule en arrière-plan avec un cache de 8 résultats. Tests : `tests/ui/test_tile_painter.py`,
`tests/graphics/test_bg_bake.py`, `tests/graphics/test_bg_adjust.py`.

**Pistes notées, rien de décidé ni de codé :**

- **Le cache de l'aperçu par ÉTAPE.** Mesuré : 240×160 ≈ 0,7 s, 512×512 ≈ 2,2 s, 5,8 s avec une cible de tuiles. Le temps part
  dans l'extraction des couleurs par tuile (ne dépend que de l'image, des ajustements et de « Global colors »), le
  regroupement des palettes et la fusion des tuiles. Garder chaque étape séparément éviterait de refaire l'extraction quand
  seuls « Palettes » ou « Colors / palette » bougent. Aujourd'hui seul le résultat final est en cache.
- **L'aperçu de compression avec les calques.** Il montre l'image seule : la peinture et les surcharges de palette ne s'y
  voient qu'après « Compress ». Les composer demanderait d'appliquer `tile_paint` au résultat non encore appliqué.
- **La mémoire du cache.** Huit résultats complets, c'est lourd pour une très grande image : la taille du cache pourrait suivre
  le poids des résultats.
- **Le relink des autres familles.** Seul le fond relance l'import natif ; un sprite garde son ré-encodage, et le relien d'un
  fond reste synchrone (une grande image peut figer l'interface un instant).
- **Les trames ordonnées sans réduction globale.** En 4bpp, le dithering n'agit que si « Global colors » est au-dessus de Off ;
  une trame par tuile (sur la réduction à 15 couleurs) n'existe pas.
- **« Save as PNG » hors du 4bpp tuilé.** Un fond en 8bpp ou en bitmap ne s'écrit qu'en RGBA à l'export, et n'a pas de
  « Save as ».
- **Des filtres créatifs de plus**, toujours non destructifs et rangés avec la préparation de la source : remap sur une palette
  du projet, posterize, pixelate à la tuile, duotone / carte de dégradé. Pas de suite de filtres généraliste (périmètre).
- **L'aperçu des ajustements est AVANT la réduction de couleurs.** Fiable pour la teinte et la luminosité, approximatif sur une
  photo ; un aperçu sur image réduite a été écarté (les tuiles et palettes dépendent de la taille réelle).
- **L'écran Son.** La courbe de polyphonie d'un WAV a disparu au profit de la barre de rognage : le plafond de canaux réduit
  par les repères (effets, jingles) ne se lit plus nulle part pour un WAV. Le test « pas de défilement » ne couvre que des
  hauteurs de fenêtre (520 à 1000 px) à 900 px de large.
- **La suite complète s'arrête vers 80 %** sans message dans `tests/ui` (vue dans `test_music_editor.py` puis
  `test_asset_finder_folders.py`) ; non élucidé, voir « Pièges de la suite de tests ».
- **Un défaut corrigé le 2026-10-14** : un PNG indexé prenait toujours le chemin « palette d'auteur gardée » et ignorait donc
  les curseurs de compression (le nombre de palettes ne bougeait pas). Désormais, dès qu'un curseur de réduction s'écarte du
  défaut, le packing déduit prend le relais ; le type de dithering seul n'y change rien.

### Chantier transverse (la caméra change de cible en jeu, avec une transition)

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-29).** Né de la tranche 2 de
« L'API dit tout ce que l'inspecteur règle » : `Camera.mode` et `Camera.follow_target` n'ont pas de porte Lua, et une
lecture seule ne suffirait pas, l'auteur doit pouvoir CHANGER de cible en jeu. Aujourd'hui le suivi est un
`switch(g_cam_active)` dont la cible est une constante par caméra ; changer de cible en cours de scène, c'est de la
RAM (mode, index de cible) lue par le suivi, et surtout un **système de transition** : passer de l'acteur A à l'acteur B
d'un coup est une téléportation de cadre. Le chantier pose les deux ensemble (état modifiable + interpolation de la
caméra vers la nouvelle cible), pour ne pas ouvrir une porte dont la première utilisation est un saut. Rien n'est
tranché ni codé.

### Chantier transverse (l'API de blending des calques, au petit oignon)

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-29).** Né de la tranche 2 de
« L'API dit tout ce que l'inspecteur règle » : quatre champs d'inspecteur touchent au blending, et chacun mérite d'être pensé avec les autres plutôt que réglé à la volée. Rien n'est tranché ni codé. À rassembler :

- les poids `blend_eva/evb/evy` : aujourd'hui `blend.set_alpha` / `blend.set_fade` s'écrivent, aucune lecture ; elles deviennent des propriétés (état → propriété), **décidé avec le `mixer`** qui pose la même question pour le son ;
- les rôles (dessus / dessous) des calques, de l'OBJ et du fond de teinte : écriture indexée existante (`set_layer/obj/backdrop`), lecture absente ;
- `backdrop_color` : une porte en lecture ET écriture, sans nouveau type, un `vec3` (r, g, b) ou un entier RGB555 ; c'est ici qu'on choisit ;
- la transition de scène (`transition_kind`, `transition_frames`) : elle possède les registres de blending pendant sa durée (`transition_begin/fade/end`), donc elle ne se règle pas sans que l'API de blending soit posée.

### Chantier transverse (l'allocateur de ressources matérielles)

Ne porte pas de numéro de version : il **se déclenche par un événement**, pas par une date,
le jour où une ressource matérielle a son deuxième consommateur. Le viewport de caméra
(`Camera.frame_w/h`, réglé le 2026-08-24) a d'abord semblé ne PAS en être un, une seule
caméra active à la fois, allocation fixe WIN0=caméra/WIN1=scène. **Corrigé le 2026-08-25** :
c'en était bien un. Le second consommateur n'a pas besoin d'être simultané À L'EXÉCUTION pour
poser le problème. Il suffit que deux INTENTIONS différentes (le cadre d'une caméra, un
panneau UI) veuillent la même ressource dans la MÊME scène, même si une seule caméra tourne à
la fois. `codegen/window_alloc.py` est livré : c'est la première instance réelle de ce
chantier, cf. ARCHITECTURE.md, « Windows, le pochoir ». Le candidat qui reste vraiment ouvert
est l'**écran partagé** de la v2.0 (plusieurs caméras actives SIMULTANÉMENT, un arbitrage
différent, à l'exécution).

#### Le problème

Les ressources du matériel ne correspondent pas aux concepts du game design. Une window GBA
n'est pas une fonctionnalité : c'est une ressource. Or une caméra veut une région de rendu,
l'UI un rectangle de découpe, un acteur un masque de visibilité, un effet un pochoir, quatre
intentions distinctes qui réclament le même stock de trois slots.

Écrire `camera.window = WIN0`, `ui.window = WIN1` fabrique le bug le plus classique de
l'ingénierie logicielle : chaque fonctionnalité marche parfaitement, jusqu'au jour où deux
d'entre elles servent en même temps. Et les windows ne sont que le premier exemple, sprites,
palettes, VRAM, OAM, DMA, canaux sonores, matrices affines posent le même problème.

Le principe et ses trois niveaux (intention / ressource logique / ressource matérielle) sont
décrits dans [ARCHITECTURE](ARCHITECTURE.md), « Ressources matérielles, l'auteur ne les nomme
jamais ». Ce jalon est son implémentation.

#### Décisions verrouillées

- **Deux allocateurs, pas un.** Ce qui se résout au BUILD (palettes, VRAM, tuiles) et ce qui
  se résout à la FRAME (OAM, DMA, windows disputées) ne partagent qu'un vocabulaire. Le
  premier peut être coûteux et **doit** parler à l'auteur ; le second tourne 60 fois par
  seconde et n'a personne à qui parler. `palette_alloc.py` et `vram_alloc.py` sont déjà des
  instances correctes du premier. Ce chantier ne les refait pas, il leur donne une famille.
- **Le rang fait partie de la ressource.** `WINR_0` > `WINR_1` > `WINR_OBJ` > `WINR_OUT` est
  une priorité câblée : traiter deux slots comme équivalents produit une allocation valide et
  une image fausse. C'est le mode de panne à empêcher par construction, parce que rien ne le
  signalera au runtime.
- **Déterminisme avant optimalité.** Pas d'ordonnancement par priorités déclarées
  (`critical`/`high`/`medium`) : une allocation qui change parce que l'auteur a posé un sprite
  sans rapport casse son UI sans qu'il puisse faire le lien. Un ordre de résolution stable,
  documenté et ennuyeux vaut mieux qu'un ordre optimal. Il est prévisible, et il est
  testable.
- **Les solutions de repli proposées doivent exister matériellement.** Fusionner deux masques
  identiques, reprogrammer par scanline en HBlank (donne réellement plus de régions, au prix
  de cycles), renoncer au masquage, assigner à la main. Pas de « clipping logiciel » pour un
  calque tuilé en mode 0 : il faudrait réécrire la tilemap. Une liste courte et vraie, sinon
  l'éditeur promet ce que la machine ne fait pas.
  - **Précisé le 2026-08-25, pour les windows** : « renoncer au masquage » silencieusement est
    justement le pire cas ici, une région qui ne cache rien à la place d'une région découpée
    est un bug visuel sans signal. `window_alloc.py` choisit donc l'échec de build NOMMÉ
    plutôt que ce repli-là : pas de fusion possible (rangs différents, `WINR_0`/`WINR_1` ne
    sont pas interchangeables), pas de HBlank par scanline (hors périmètre v1), pas
    d'assignation à la main proposée (ce serait renommer la ressource matérielle). Un futur
    consommateur d'un AUTRE type de ressource peut légitimement choisir un vrai repli parmi la
    liste. Ce n'est pas une règle générale, c'est ce que « exister matériellement » a donné
    pour CE cas.
- **L'assignation matérielle reste visible, dans un panneau avancé.** Le principe « l'auteur
  peut descendre jusqu'au matériel » n'est pas suspendu : il ne nomme plus la ressource pour
  obtenir un masque, mais il peut voir laquelle lui a été donnée, et la forcer.

#### Ce qui est fait (2026-08-25) (les windows)

1. **Le principe est écrit** (cf. ARCHITECTURE), pour que rien de neuf ne lie un concept de
   haut niveau à un slot matériel.
2. **`WindowSlot.region` n'est plus un index matériel côté auteur**, renommé `.name`, résolu
   par `codegen/window_alloc.py`.
3. **La rupture assumée sur l'API Lua est faite pour les windows** :
   `window.set`/`window.show`/`window.is_visible` adressent maintenant par nom
   (`DOMAIN_WIN_REGION`), comme `window.set_layer` le faisait déjà, un seul schéma, plus de
   numéro matériel brut atteignable depuis un script.

#### Ouvert

- Jusqu'où va l'allocateur de frame (OAM, DMA, matrices affines). Un arbitrage par frame est
  un vrai coût CPU ; il se décide sur un cas mesuré, pas à l'avance, les windows n'en avaient
  pas besoin (résolubles au build, cf. ARCHITECTURE.md « Deux allocateurs, pas un »).
- L'assignation matérielle « visible dans un panneau avancé, et forçable » (décision
  verrouillée ci-dessus) n'est pas construite pour les windows, l'auteur voit le budget
  (N/2) mais pas quelle intention a reçu quel rang. À rouvrir si un projet réel en a besoin
  pour déboguer un recouvrement.

#### Le cas mesuré de l'allocateur de frame (l'OAM dynamique (2026-09-10))

La décision « l'allocateur de frame se décide sur un cas mesuré » (« Ouvert » ci-dessus) a son cas.
Trois familles de consommateurs OAM apparaissent ou disparaissent **en cours de partie**, et aucune
n'a de place dans le partitionnement build de la scène :

- **Les projectiles**, un acteur poolé les sert déjà (v0.17) : ils ont position, vélocité,
  collision, un brin de logique. Ce ne sont PAS un cas pour une primitive à part, seulement pour une
  bonne API de spawn/despawn. Ils prennent leurs slots dans le pool de leur scène.
- **Les particules**, le vrai cas hors-budget : des centaines, éphémères, sans collision ni script.
  Un `Actor` plein par particule est absurde, et 128 OAM sature instantanément. Elles veulent
  probablement un modèle À PART (cap fixe, ou effet BG), peut-être pas de l'OAM du tout.
- **L'UI en sprites**, déjà des consommateurs OAM légers (texte, images), placés au build et
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
projet réel qui en a besoin, pas avant, fidèle à la règle du chantier.

### Chantier transverse (le Sprite, source visuelle unique)

Ne porte pas de numéro : c'est un remaniement de **données**, déclenché par le constat qu'un même
dessin animé a aujourd'hui **plusieurs pipelines de définition** selon qui l'affiche. Un acteur
pointe un `SpriteAsset` (ses tables d'anim émises en ROM) ; une image d'UI pointe une autre voie ;
un futur projectile ou une particule ne pointent rien. Le dessin, ses frames, ses états et ses
directions sont pourtant la même chose, celle qu'on édite dans **l'écran d'animation**.

**La direction (2026-09-10)** : tout ce qui s'affiche (acteur, image d'UI, projectile, particule)
**référence un seul `Sprite`**, l'asset de l'écran d'animation. C'est « source de vérité unique »
appliquée au visuel. Distinct des deux questions OAM ci-dessus : celles-ci partagent le STOCK
matériel (les 128 slots) ; celle-ci partage la DÉFINITION (l'asset). Un consommateur peut être léger
côté runtime (une particule ne porte pas de logique) tout en pointant le même Sprite qu'un acteur
lourd.

**Ce que ça ne décide pas** : cela ne choisit pas la représentation mémoire de l'Actor (la
découpe Sprite optionnel relève du chantier « Actor allégé » ci-dessus) et ne crée pas de runtime
commun. C'est la couche asset qui s'unifie, pas la couche entité.

**Ouvert** : l'inventaire des pipelines actuels (SpriteAsset côté acteur, la voie image de l'UI) et
lequel absorbe l'autre ; et si le décor animé (v0.4) relève de ce même `Sprite` ou reste une voie BG
à part.

### Chantier transverse (la Liste d'interface est un contrôleur, pas une collection)

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
source de vérité. Dans l'inspecteur, une Liste choisira une source déclarée (un vecteur d'état ou
un catalogue Data) ; le script lira et modifiera l'état directement avec `global.*`, et lira les
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

### Chantier transverse (la destruction des éléments d'interface)

**D'où ça vient (2026-09-27).** En discutant du critère 4 de v0.16 (« unifier absent par type »),
constat : un élément d'interface, un calque ou une fenêtre sont **statiques par construction**,
`destroy()` n'existe QUE pour `actor`/`sfx` dans le catalogue ([api.py](editor/scripting/api.py)),
posé une fois pour toutes à l'authoring, sans commande de script pour le faire disparaître. C'est
ce qui rend `interface:get("Menu") ~= nil` toujours vrai, et c'est ce qui permettait de classer ces
types comme « jamais absents » sans exception à traiter.

**La piste, non développée.** Si un projet réel demande un jour de détruire dynamiquement un
élément d'interface (un menu généré au runtime, une fenêtre jetable) plutôt que de se contenter de
`hide()`, ça romprait l'hypothèse « statique = jamais nil » du critère 4 : ces types rejoindraient
la catégorie des références de pool, avec tout ce que ça implique (`nil` testable, retrait du
`REF_TYPE_TABLE.nullable=False`, etc.). **Aucune décision prise, aucun besoin démontré**, à
rouvrir si un projet en butte contre la limite actuelle (`hide()` seul, l'élément reste en mémoire).

### Chantier transverse (les calques par nom)

**D'où ça vient (v0.16).** `layer:get(n)` adresse un fond par son NUMÉRO (0 à 3, borné par le mode
vidéo de la scène), cohérent avec la provenance « le matériel, numéroté par le matériel » de la
règle de construction. Question restée ouverte pendant le chantier : offrir aussi `layer:get("Fond")`
par un nom authoré, comme pour un élément d'interface.

**Pourquoi ce n'est pas fait maintenant.** Recommandation retenue à l'époque : attendre un besoin
réel avant d'ajouter une seconde façon d'adresser la même chose, deux provenances pour un fond
recréerait exactement le doublon que la grammaire de l'API refuse ailleurs. **Aucune décision
prise, aucun besoin démontré.**

### v2.0 (Cible cartouche : le matériel embarqué façonne le langage, **JALON OUVERT**)

> La famille v2.0 n'est pas rangée. Ce jalon est **posé, pas ordonnancé** : quand on y sera,
> on fera le point de tout ce qui s'y accumule et on décidera de la découpe. Ce qui suit fixe
> l'**intention** et les décisions déjà prises (2026-09-10), pas un périmètre daté.

Un **profil de cartouche** décrit ce que la cartouche embarque **physiquement**, capteurs,
rumble, RTC, type et taille de sauvegarde. Il reste **100% GBA** : les limites mémoire (IWRAM,
EWRAM, VRAM, OAM, palettes) sont fixes pour toute la gamme et **ne bougent pas**. Cibler un
matériel aux limites différentes (NDS…) serait un second backend d'émission, un autre modèle
mémoire, **hors de ce jalon**, écarté explicitement le 2026-09-10.

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
   **n'existe pas**, pas grisé. Ce sont des modules **moteur spécialisés et nommés**, jamais de
   l'itération par défaut (cf. la règle des deux couches).
2. **Éditeur.** Les nœuds et champs qui dépendent d'une capacité absente ne s'affichent pas. Le
   *pourquoi* d'une absence ne sort qu'en notice niveau 3, désactivable, l'éditeur ne commente
   pas le matériel.
3. **Émission ROM.** Le codegen n'inclut le driver (lecture capteur, IRQ RTC, registre rumble)
   que si la capacité est déclarée. Pas de code mort dans une ROM qui n'a pas le hardware.

#### Décision verrouillée (2026-09-10) (le profil ABSORBE la sauvegarde)

La config SRAM de la v0.5 est déjà un morceau de « ce que porte la cartouche » qui vit à côté.
Le profil **l'absorbe** : une seule source de vérité, pas deux partielles. C'est un **vrai
chantier de migration**, migration du modèle de save existant et relecture du codegen de
sauvegarde, l'ancien supprimé avant de dire terminé, pas un bonus glissé dans autre chose.

#### État au 2026-10-17 (aperçu des circuits dans le panneau Build)

**Première tranche intégrée, chantier ouvert.** Le panneau Build des réglages du projet
affiche une photo de circuit avec des repères **ROM / SRAM / pile**, la capacité ROM visée,
la référence du circuit photographié et ses crédits. L'aperçu suit le choix de capacité et
l'annulation/rétablissement. Le moteur reste sur sa sauvegarde **SRAM de 32 Kio** ; aucun
nouveau pilote de sauvegarde n'a été ajouté.

**Références documentées déjà intégrées :**

| ROM visée | Circuit photographié | Sauvegarde et pile | Correspondance |
| --- | --- | --- | --- |
| 4 Mio | AGB-E06-01 (F-Zero: Maximum Velocity) | SRAM 32 Kio, pile CR1616 retirée sur la photo | mêmes capacité ROM et type/taille de sauvegarde |
| 8 Mio | AGB-E06-10 (Wario Land 4) | SRAM 32 Kio, pile CR1616 montée | mêmes capacité ROM et type/taille de sauvegarde |
| 16 / 32 Mio | même photo de la carte de 8 Mio | SRAM 32 Kio, pile CR1616 montée | exemple explicitement signalé ; aucune correspondance ROM revendiquée |

**Règle retenue :** une photo illustre un spécimen identifié, pas une carte détectée ni une
garantie de compatibilité avec une cartouche physique. Une pile retirée pour la photo ne
décrit pas une sauvegarde sans pile. Capacité ROM, type/taille de sauvegarde et rôle de la
pile restent des caractéristiques distinctes ; quatre capacités ROM ne constituent pas
quatre formats de circuits.

Les photos originales, leurs sources et licences sont conservées dans
[`editor/ui/common/images/cartridges/`](editor/ui/common/images/cartridges/README.md).
Les photos affichées proviennent de la Game Boy hardware database, sous **CC BY-SA 4.0** ;
les crédits et les images sont inclus dans la distribution. Vérification : **49 tests ciblés
passent**, rendu du dialogue contrôlé pour 4, 8 et 32 Mio. Le contrôle d'architecture global
signale encore des problèmes hors de ce chantier.

**Reste à faire :** trouver des spécimens documentés pour les ROM de 16 et 32 Mio avec la
sauvegarde correspondante ; étendre les références aux circuits avec et sans pile en
précisant son rôle (sauvegarde ou horloge). La sélection effective de SRAM / EEPROM / Flash
reste liée à la migration du profil et à l'implémentation des pilotes moteur/codegen :
ajouter une photo ne débloque pas le matériel associé. Le jalon v2.0 reste non ordonnancé.

**Préparation du catalogue (2026-10-17)** : la [matrice des cartes, composants et photos](docs/development/cartridge-hardware-matrix.md)
recense douze configurations ordinaires avec des jeux de référence, les cartes spéciales,
les composants à photographier et les 36 fiches de scans retrouvées sur Archive.org.
Les associations observées sont distinguées des montages encore à confirmer. Aucun nouveau
visuel n'a été téléchargé pour cette recherche ; la collecte attend cet inventaire.

**Six profils simplifiés en aperçu (2026-10-17)** : sans sauvegarde, SRAM 32 Kio,
EEPROM 512 octets / 8 Kio, Flash 64 / 128 Kio, FRAM 32 Kio et Flash 128 Kio + horloge.
Le sélecteur « Matériel à visualiser » est disponible **depuis les sources uniquement**.
Première étape : SRAM conservait ses photos documentées ; les autres profils utilisaient
un schéma provisoire. Ces schémas sont désormais remplacés par les photos décrites ci-dessous.

Ce choix reste **local au dialogue** : ni réglage de projet ni donnée de compilation ; changer
la ROM ou annuler ce changement conserve le profil visualisé. La compilation et ses contrôles
restent en SRAM 32 Kio, quelle que soit la prévisualisation. Les versions distribuées
(`IS_FROZEN`, y compris Nuitka) n'exposent que SRAM. Les tests vérifient l'absence d'effet
sur les réglages, l'historique et le pilote de sauvegarde généré, ainsi que ce filtrage.

**Activation ultérieure en release** : implémenter et valider le pilote, la capacité et les
contrôles de sauvegarde dans le modèle/codegen/moteur, puis relier le vrai réglage au profil
et lever son filtrage. Le drapeau d'aperçu ne constitue pas une prise en charge matérielle.

**Photos récupérées (2026-10-17)** : [bibliothèque de travail des six profils](research/cartridges/README.md),
31 images vérifiées (12 cartes nues recto/verso et 19 vues assemblées, variantes ou détails).
Les sources, auteurs, licences, dimensions et empreintes sont conservés avec les fichiers.
Les vues de composants sont disponibles sur les assemblages ; les détourages individuels
et leur superposition sur les cartes nues restent à faire. Les sources Archive.org à licence non précisée
restent dans `research/`, hors des images empaquetées avec l'application.

**Photos intégrées au panneau Build (2026-10-17)** : neuf exemplaires documentés,
18 vues recto/verso sous CC BY-SA 4.0, couvrent les six profils et leurs capacités.
Les repères identifient la ROM, la sauvegarde, la pile et le RTC selon le montage.
La capacité réelle de la ROM photographiée reste indiquée, avec mention si elle diffère
de la cible. Les crédits ouvrent la fiche source et la licence. Les vues et profils
restent locaux au dialogue ; la compilation demeure en SRAM 32 Kio.

Le mode « Carte nue » consulte les fichiers de recherche depuis les sources uniquement,
sans repères de composants ni mention de composants présents. Il est désactivé pour
AGB-E06-10 faute de scan correspondant. Aucun scan Archive.org à licence non précisée
n’est empaqueté. Les versions distribuées conservent uniquement le profil SRAM.
Un schéma identifié sert de secours si une photo assemblée est absente.
Validation : 56 tests ciblés réussis et vérification visuelle FR/EN du panneau.

#### Deux pièges matériels à encoder

- **Capteurs analogiques mutuellement exclusifs.** Une cartouche GBA porte *un* capteur
  analogique (tilt **ou** solaire), pas les deux, même ligne d'acquisition. Le profil doit
  interdire la combinaison, sinon on laisse décrire une cartouche qui n'existe pas.
- **Le tilt n'est pas un axe de pad.** Il rend un angle bruité à calibrer/filtrer. L'exposer
  comme un axe propre mentirait sur le matériel : valeur brute, et au plus un helper de
  calibration nommé.

#### Le catalogue « cartouche conseillée » (trois tiers (2026-09-10))

Le catalogue s'inscrit dans une démarche homebrew/retrodev : on ne propose que des cartouches
qu'un utilisateur peut **réellement obtenir ou fabriquer**. Décisions de cadrage :
**marques écartées** (pas de nom de flashcart commercial dans l'UI, cf. le risque « GBA » de
`project_licensing_model`), **flashcarts reprogrammables dépriorisées** au profit des vraies
cartouches, et **priorité aux créateurs indépendants**.

**Tier 1, Profils de base : cartouches réelles historiques reproductibles.** Les configs que
la logithèque GBA a réellement portées, reproductibles avec des puces standard et un gabarit
`kicad-gamepaks` (djedditt, contours aux dimensions des coques officielles). La vraie variable
est la puce de save + le périphérique embarqué :

| Profil de base | Matériel embarqué | Équivalent historique |
| --- | --- | --- |
| Save, SRAM | SRAM sur pile | gros de la logithèque |
| Save, Flash | Flash 64/128K | jeux à grosse sauvegarde |
| Save, EEPROM | EEPROM 4/64K | petits jeux |
| RTC | horloge + Flash | RPG jour/nuit (Pokémon G3) |
| Solaire + RTC | photodiode + RTC | Boktai |
| Rumble | moteur + driver | Drill Dozer, Pinball R/S |

**Tier 2, Options « cool » : créateurs indépendants.** Cartouches à matériel embarqué,
buildables. Référence mature : **insideGadgets** (RTC+Rumble, Solar+RTC, FRAM sans pile, kits
*build-it-yourself*). Écosystème : **GBMake** (fabrication indé de cartouches sur mesure),
`kicad-gamepaks` (la brique de conception open source qui rend le Tier 1 fabricable).

**Frontière, documentée, pas livrée comme profil.** De la R&D, pas des cibles stables :
`jojolebarjos/gba-cartridge` (cartouche **FPGA**, TinyFPGA BX, mappers/périphériques custom) et
`konsumer/dkart` (framework open hardware avec **ESP32 + SD** soudés, « cartouche
intelligente »). Notés comme horizon, hors catalogue conseillé.

#### Convention de nommage (capacité d'abord, board number en note)

Les cartouches historiques portent une nomenclature Nintendo, mais deux schémas coexistent :
`AGB-002/013/019…` désigne la **coque/famille physique** (inutile ici) ; `AGB-Exx-nn` est le
**PCB du jeu** qui encode save + périphérique (p. ex. `AGB-E05-01` = RTC + Flash, la carte
Pokémon Gen 3, le seul rock-solid). Le fil nesdev le confirme : pour un jeu GBA, les seules
variables sont **taille de ROM, type de save, taille de save, présence d'un RTC**, donc notre
modèle de capacités *est* déjà la bonne granularité.

**On ne nomme PAS les profils par `AGB-Exx`** : c'est une désignation interne Nintendo (marque,
écartée), le catalogue de référence est mort (Pocket Heaven, reconstituer une table exhaustive
serait deviner), et le numéro n'encode rien qu'un nom de capacité ne dise mieux. Les profils
sont nommés **par capacité** ; le board number n'apparaît qu'en **note historique** pour les cas
sûrs (« profil RTC, équivalent historique `AGB-E05` »), jamais comme identifiant.

#### Références externes à surveiller

- [`kicad-gamepaks`](https://github.com/djedditt/kicad-gamepaks), gabarits KiCad aux dimensions
  des cartouches officielles (la brique de fabrication du Tier 1).
- [insideGadgets](https://shop.insidegadgets.com/), cartouches à RTC / Solar / Rumble / FRAM
  (référence Tier 2, kits *build-it-yourself*).
- [GBMake](https://gbmake.com/us), fabrication indé de cartouches GB/GBA sur mesure.
- [`jojolebarjos/gba-cartridge`](https://github.com/jojolebarjos/gba-cartridge), cartouche
  FPGA (TinyFPGA BX, KiCad), frontière.
- [`konsumer/dkart`](https://github.com/konsumer/dkart), framework cartouche open hardware
  ESP32 + SD, frontière.

#### Ouvert

- La découpe : ce jalon face aux autres candidats v2.0 (Backgrounds affines ci-dessous, etc.),
  et s'il se scinde par capacité.
- La forme exacte du profil dans le projet, et où il vit par rapport au reste de la config projet.
- L'ordre de livraison des capacités (RTC, rumble et les saves sont sûrs et fabricables ;
  l'ordre des capteurs analogiques dépend de la demande réelle). **Le tilt/gyro reste hors
  catalogue** : historique et réel, mais non reproductible (soudé dans la cartouche OEM, aucune
  flashcart ni repro ne l'embarque), documenté « OEM-only », jamais proposé comme cible.

### v2.0 (Backgrounds affines (« Mode 7 »))

Un calque affine ajoute rotation et zoom, au prix de perdre des calques réguliers ailleurs,
et il adresse sa carte différemment, donc c'est un **second chemin de génération de code**,
pas « un calque de plus ».

Volontairement décrit à haut niveau : la portée exacte dépendra de ce qui aura été appris en
construisant les fondations précédentes.

#### Ce que la v2.0 n'est PAS (l'objectif V-Rally 3 n'est pas ici)

Cet objectif a été rangé dans cette version pendant une journée, sur une lecture de captures
d'écran qui concluait au Mode 7 : sol texturé fuyant vers l'horizon, décor en sprites mis à
l'échelle, HUD en calque normal. **Cette lecture était fausse**, et la mesure l'a montrée
(2026-08-13, visualiseur de cartes mGBA sur la ROM) :

| Relevé | Lecture |
| --- | --- |
| Fond de tuile : *s.o.* | aucune base de tuiles, le fond n'est pas tuilé |
| Taille : 240×160 | un écran, pas une carte |
| Fond de carte : `0x0600A000` | VRAM + 0xA000 = **frame 1 du mode 4** |

Le mode 3 n'a pas de second tampon et le mode 5 afficherait 160×128 : c'est donc le **mode 4**,
240×160 en 8bpp double-tamponné. Un framebuffer rempli par le processeur. Confirmé par des
maillages qui tournent dans les menus.

La leçon vaut d'être gardée : **un rasteriseur logiciel et un sol affine produisent la même
image.** Une capture ne distingue pas les deux. Seul le mode vidéo le fait. Aucune décision
de rendu ne se verrouille sur une image, ici ou ailleurs.

L'objectif part donc en **v3.1**, derrière le framebuffer dont il dépend. La v2.0 redevient
ce qu'elle était : une capacité, sans cible de jeu.

#### Piste posée (l'abstraction « caméra » sera remise en cause ici)

La caméra est en train de devenir une entité, en absorbant les fenêtres de la v0.3.2, auquel
cas ce n'est plus « où on regarde » mais **une configuration d'écran nommée qu'on active** :
cadrage, suivi, et régions qui découpent l'affichage. Comme les caméras sont mutuellement
exclusives, deux fenêtres par caméra n'impliquent jamais plus de deux rectangles à l'écran :
la contrainte matérielle tient.

Nom de travail : **Caméra2D** (convention Godot, immédiatement lisible). Réserve à garder en
tête, il promet une Caméra3D qui n'existera jamais sur GBA. Le Mode 7 n'est pas de la 3D mais
une transformation affine en 2D. Le vrai axe est donc *régulière* contre *affine*, pas 2D
contre 3D.

Une chose à traiter à ce moment-là, pas avant : l'**écran partagé**, qui rouvrira la question
« une région appartient-elle à une caméra, ou l'inverse ? ». Tant que les caméras sont
exclusives (une seule active par scène à la fois), la question ne se pose pas.

*Mise à jour 2026-08-24* : « unifier les mécanismes de caméra concurrents » (l'autre point que
cette piste listait) est réglé. C'est fait depuis la v0.6.1, et l'objet nommé porteur d'un
état existe déjà. Ce qui a bougé depuis n'est pas cet axe-là mais la PROPRIÉTÉ de la caméra :
elle appartient désormais à sa scène plutôt qu'au projet (cf. `changelog/archives/v0.6.md`,
« Révisé le 2026-08-24 »). Ça ne contredit pas Caméra2D (une caméra reste exclusive, une
seule active à la fois) et ça ne change rien à ce qui reste ouvert ici.

*Mise à jour 2026-08-24 (suite)* : la question « une région appartient-elle à une caméra, ou
l'inverse ? » posée ci-dessus est **réglée pour le cas à une seule caméra active**, la
caméra possède désormais un viewport (`Camera.frame_w/h`, cf. `ARCHITECTURE.md`, « Windows,
le pochoir ») : WIN0 lui appartient, WIN1 reste à la scène. Une allocation FIXE, décidée une
fois, pas un arbitrage à l'exécution, donc pas l'allocateur de ressources générique que ce
chantier réserve. Ce qui reste ouvert ici, sans changement, c'est l'**écran partagé** :
plusieurs caméras actives SIMULTANÉMENT (split-screen), qui redemanderait de vrais
arbitrages entre plusieurs propriétaires possibles des mêmes deux rectangles.

### v2.1 (Physique et collision)

Le moteur n'a aujourd'hui aucune physique à lui : un script décide du mouvement, la
résolution de la v0.6.3 ne fait que le corriger. Cette version est **le renversement de cette
règle**, pas son extension. C'est pour ça qu'elle est ici et pas en v0.6.4 : tant que les
fondations 2D ne sont pas finies, un moteur qui décide du mouvement à la place du script
coûterait plus qu'il ne rendrait.

#### Périmètre

- **Collision par normale.** Le contact rend une direction, pas seulement un booléen. C'est
  ce qui distingue « je touche » de « je glisse le long de », et c'est la condition de tout
  le reste.
- **Gravité**, et deux milieux qui la modulent : **air** (traînée) et **viscosité**
  (résistance d'un fluide). Trois réglages qui vivent quelque part entre la scène et
  l'acteur, l'endroit reste ouvert.
- **Nouvelles primitives** : cercle de collision et maillage de collision. Ce sont des
  primitives **2D** ; le mot « mesh » ne promet pas de volume. La distinction devient
  critique une fois la v3.1 au programme : deux choses différentes porteront le même mot si
  personne n'y veille.
- **Nouveaux types de collision**, en remplacement du booléen `solid` actuel :

  | Type | Sens |
  | --- | --- |
  | `rigidbody` | réactif, le moteur calcule sa réponse au contact |
  | `actor` | simplifié, se déplace, se bloque, ne réagit pas |
  | `solid` | immobile, ne bouge jamais, sert de décor de collision |

- **Import de carte de collision**, un nouvel asset, pour des collisions fidèles à l'image.

#### Décisions verrouillées

- **Jamais avant la v2.0.** Décidé explicitement (2026-08-12) : les fondations 2D passent
  d'abord. La section « Ouvert » de la v0.6.3 reste donc vraie jusque-là, elle n'est pas
  contredite. Elle est datée.
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
  migre pas les formats, cf. `core/project.py`).
- Où vivent gravité, air et viscosité : propriétés de scène, de zone, ou d'acteur ? Les trois
  se défendent et le choix dépend du premier jeu qui s'en sert.
- Le maillage de collision est-il authoré, dérivé de l'image importée, ou les deux ? Dérivé
  est cohérent avec le refus de l'outil de dessin ; authoré est ce que réclame une forme qui
  n'existe dans aucune image.
- Rien n'est dit du coût réel. Il se mesure sur un cas, pas avant. C'est la règle qui a
  servi pour les animés de décor (v0.4.1, « L'ordre de grandeur, mesuré »).

### v2.2 (Distorsion d'image)

Déformer un fond pour l'eau, la chaleur, la vitesse. Rangé ici parce que c'est **la même
plomberie que le sol affine de la v2.0** : dans les deux cas on réécrit des registres de
rendu à chaque scanline, seuls les registres visés et la table de valeurs changent. Construire
l'un donne l'autre presque gratuitement. C'est la raison de leur voisinage, et l'ordre entre
les deux n'a pas d'importance.

#### Décisions verrouillées

- **Sur un fond tuilé, la distorsion est PAR LIGNE, jamais par pixel.** On réécrit les
  registres de décalage du calque à chaque scanline (HDMA). C'est l'effet eau/chaleur
  classique, réel et bon marché sur ce matériel. Une flow map par pixel suppose un
  framebuffer : elle appartient donc à la v3.0, et n'a pas de sens avant.
- **Les sprites n'en font pas partie.** Un OBJ ne connaît que la transformation affine
  (rotation, échelle) ; il n'y a pas de distorsion libre à lui appliquer. Le proposer
  promettrait un rendu que le matériel ne produit pas, même règle que les modes de mélange
  *multiply* et *overlay*, absents pour cette raison.

#### Ouvert

- La forme d'authoring : une courbe par calque, une table d'amplitudes, ou un script qui
  écrit la table lui-même ? Le troisième cas existe de toute façon, la question est ce que
  le déclaratif couvre.

### v2.3 (Rendu isométrique)

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
  seule formule, mais elle doit vivre **au même endroit pour l'éditeur et pour le moteur**,
  sinon le canvas ment sur l'emplacement des choses (c'est déjà le rôle de
  `core/engine_emulation/`).
- **La collision en espace isométrique.** Une boîte alignée à l'écran n'est pas une boîte
  alignée dans le monde. À raccorder à la v2.1, qui aura introduit les normales et les
  nouvelles primitives. Les deux versions se touchent ici.
- **L'authoring.** Poser un acteur au canvas doit se faire dans la grille du monde, pas dans
  les pixels du losange.

#### Ouvert

- Le coût du tri par frame, et son plafond. Trier N acteurs à chaque frame sur un ARM7TDMI a
  un prix ; le nombre d'entités simultanées s'en déduira, il ne se décrète pas.
- Vraie isométrique (2:1) ou projection libre ? La première se tuile proprement, la seconde
  ouvre des cas qui ne se rangent pas dans une grille.
- La hauteur. Un décor isométrique sans élévation est une grille inclinée ; avec élévation,
  le tri cesse d'être un tri sur Y. À décider avant, parce que ça change la donnée de carte.

### v2.4 (Sucre syntaxique Lua (+=, ++, ?:))

Demandé le 2026-08-14 : `x += 1` / `x -= 1` / `x *= 2` / `x /= 2`, `x++` / `x--`, et
`cond ? a : b`. **Aucun des trois n'est du Lua**. Lua n'a jamais eu d'affectation composée ni
d'opérateur ternaire, choix délibéré du langage, et `luaparser` (un vrai parseur ANTLR) les
refuse net :

```
x += 1          → no viable alternative at input 'x +'
x++             → no viable alternative at input 'x+'
a ? b : c       → token recognition error at: '?'
```

Donc ce n'est pas « étendre l'AST » : `parser.py` reçoit le texte source tel quel et le passe
à `luaparser.ast.parse()` sans passe intermédiaire (`scripting/parser.py::parse()`). Accepter
cette syntaxe demande une **réécriture du texte AVANT `luaparser`**, un dialecte Lua-like, pas
du Lua strict.

**Le ternaire a déjà un équivalent qui ne coûte rien** : `cond and a or b` est du Lua valide
aujourd'hui et couvre tout ce que ce sous-ensemble manipule (entiers, vec2/vec3, chaînes),
sauf le cas où `a` vaut `false`, où Lua bascule sur `b` alors qu'un vrai `? :` ne le ferait
pas. À vérifier si ce cas se présente en pratique avant d'écrire quoi que ce soit.

#### Ce que le fork coûterait, si tranché « oui »

- **La coloration syntaxique du Script Editor** (`lua_editor.py`) devrait apprendre ces tokens
  en plus, sinon ils s'afficheraient comme une erreur alors qu'ils compileraient.
- **Un vrai script Lua copié ailleurs** (interpréteur externe, autre colorateur) ne le
  reconnaîtrait plus comme du Lua valide.
- **Les numéros de ligne/colonne d'une vraie erreur de syntaxe** se décaleraient : `luaparser`
  rapporterait la position dans le texte RÉÉCRIT, pas dans ce que l'auteur a tapé, une faute
  ailleurs sur la ligne verrait son message mentir sur l'endroit fautif.
- `? :` est le plus dur à réécrire sûrement en texte (imbrication, `?`/`:` à l'intérieur d'une
  chaîne…), une regex naïve est fragile ; il faudrait un petit tokenizer dédié, pas un
  remplacement de texte.
- `+=`/`++`/`--` sont plus simples : réécriture au niveau de l'instruction complète
  (`NOM (+=|-=|*=|/=) EXPR` ou `NOM (\+\+|--)`), sans ambiguïté de priorité d'opérateurs.

### v3.0 (Le second moteur de rendu)

**Décidé (2026-08-13) : l'éditeur porte DEUX moteurs de rendu.** Un moteur 2D (tout ce qui
existe jusqu'à la v2.2 incluse, calques tuilés et OBJ) et un moteur 3D, qui est le sujet de
cette version.

L'ancienne v3.0 « modes bitmap » disparaît en tant que jalon et **devient le substrat de
celle-ci**. Elle n'avait jamais été un jalon pour l'auteur de jeu : personne ne veut « le
support du mode 4 », on veut ce qu'il permet. Elle reste décrite ci-dessous parce que ses
contraintes ne changent pas, mais elle ne se livre plus seule.

Ce n'est pas un mode de plus dans le moteur existant. C'est **un second moteur**, et cette
version consiste autant à réoutiller l'éditeur qu'à écrire un rasteriseur.

#### Le substrat (les modes bitmap)

Famille complètement différente des modes tuilés : un seul calque, pas de tuiles ni de cartes,
un framebuffer direct. Le budget des sprites y est par ailleurs divisé par deux.

| Mode | Résolution | Couleur | Tampons |
| --- | --- | --- | --- |
| 3 | 240×160 | 16 bits directs | 1 seul |
| 4 | 240×160 | 8 bits indexés | 2 (double tampon) |
| 5 | 160×128 | 16 bits directs | 2, résolution réduite |

**Priorité au mode 4** : 256 couleurs, double tampon, pleine résolution. Il évite le
déchirement d'image du mode 3 et la résolution réduite du mode 5. C'est aussi celui que le
jeu de référence emploie (relevé du 2026-08-13).

**Exclu délibérément des fondations v0.3** : les modes bitmap cassent tout le pipeline actuel
(tilesets réutilisables, palettes par banque) au profit d'un framebuffer brut, et c'est aussi
pourquoi de vrais jeux commerciaux les emploient rarement.

Une brique est déjà là : `BackgroundAsset.mode == "bitmap"` existe côté éditeur (image plein
écran, détectée à l'import) et n'attend que son émission ROM. C'est le plus petit usage du
framebuffer, sans géométrie, un bon premier pas dans cette version.

**Ce que le framebuffer débloque, et rien d'autre ne débloquera** : la vraie *flow map* (une
distorsion décidée par pixel, et non par ligne comme en v2.2) et le rendu de géométrie
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
de moteur puisque le matériel OBJ est le même. Mieux, c'est en 3D qu'ils portent le CIEL
(cf. « rôles inversés » ci-dessous).

#### Ce qui se DÉDOUBLE, et à quel niveau

- **La scène.** `Scene.render_mode` existe déjà en ébauche : c'est le bon endroit, et
  l'arbitrage est **par scène, pas par projet**. Un jeu veut ses menus en 2D et sa course en
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
  moteur, et le checker refuser un appel 2D dans une scène 3D. Sinon la faute n'apparaît
  qu'au `make`, sur une ligne générée, jamais sur la cause. C'est le même défaut que les deux
  listes de prototypes du moteur, et il se règle au même endroit : dans le catalogue.
- **Les écrans de l'éditeur.** Le Background Editor n'a pas d'objet en 3D ; le Palette Editor
  et le Sprite Editor gardent le leur ; le Scene Manager change de nature. Un écran doit
  pouvoir déclarer les moteurs où il s'applique, faute de quoi l'utilisateur voit des outils
  qui ne peuvent rien produire pour la scène ouverte.

#### L'aperçu fidèle (une source, deux compilations)

`core/engine_emulation/` existe parce que **l'éditeur refait en Python ce que la console fait
en C**, pour montrer le vrai résultat plutôt qu'une approximation : le layout de texte, les
formules de mélange, le mixeur. Promesse tenue jusqu'ici, à un coût connu, deux
implémentations à tenir d'accord.

Un moteur 3D aurait mis cette promesse en défaut : porter un rasteriseur en Python fait de la
double implémentation un vrai risque, et ses divergences sont **invisibles**, un arrondi en
virgule fixe qui diffère ne plante pas, il donne une autre image. L'autre issue était d'admettre
un aperçu approximatif, c'est-à-dire de mentir pour la première fois.

**Décision (2026-08-13) : ni l'un ni l'autre. Le rasteriseur s'écrit UNE fois, en C portable,
et se compile DEUX fois**, pour la GBA (ARM, en IWRAM), et pour l'hôte en bibliothèque
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
  dira jamais si la frame tient dans le budget. mGBA reste l'outil de la cadence, appelé, pas
  incorporé, et le lancement de ROM est déjà outillé.
- **Un compilateur C hôte devient une dépendance de build**, pour ce composant seulement.
  Relevé sur la machine de développement (2026-08-13) : aucun compilateur hôte, et le msys2
  livré avec devkitPro n'expose que les dépôts `msys`, `dkp-libs`, `dkp-windows`, pas de
  mingw-w64. C'est donc une installation à part, et elle ne concerne que qui touche au
  rasteriseur : l'éditeur se distribue avec la bibliothèque déjà compilée, et le reste du
  travail Python n'en a pas besoin.
- **TCC pour développer, gcc pour publier.** TCC (Tiny C Compiler) tient en quelques
  mégaoctets et un seul dossier, et sort la bibliothèque directement (`tcc -shared`) : c'est
  le coût d'entrée le plus bas pour itérer sur le rasteriseur. Il convient d'autant mieux que
  la source doit de toute façon rester du C conservateur et sans dépendances. Elle compile
  pour un ARM7TDMI avec devkitARM, ce qui interdit déjà tout ce que TCC ne saurait pas
  digérer. Les builds de **release** passent par gcc (w64devkit, ou la CI qui en fournit un
  gratuitement), pour du code optimisé et un compilateur éprouvé.

  Le risque de TCC est réel mais borné : moins éprouvé que gcc, et une compilation fausse
  donnerait une **image fausse** plutôt qu'un plantage. Deux garde-fous tombent tout seuls :
  la même source tourne sur le vrai matériel (mGBA), et la présence des deux chaînes fait du
  build de release un **test différentiel gratuit**, si l'image TCC et l'image gcc diffèrent,
  l'un des deux compilateurs a tort et on le sait avant l'utilisateur.

  **Ce choix n'engage rien.** Le compilateur hôte est un détail de build, pas une décision
  d'architecture : la source étant du C portable dans les deux cas, remplacer TCC par autre
  chose ne déplace aucune ligne, aucun format, aucune structure. À rouvrir librement, sans
  que ce soit une reprise de décision.

#### Ouvert

- Le nom des deux moteurs, dans le code comme dans l'interface. Il sera lu partout et pour
  longtemps.
- Une scène peut-elle mélanger les deux ? Le matériel dit non pour les calques, mais les OBJ
  traversent, donc « pas de mélange » est faux tel quel, et « mélange libre » est faux
  aussi.
- Ce que devient un projet dont l'auteur bascule une scène d'un moteur à l'autre. Rien ne se
  convertit ; la question est ce que l'éditeur en dit.

### v3.1 (Le rasteriseur)

Le moteur 3D proprement dit, une fois le substrat et le réoutillage de la v3.0 en place.

#### L'objectif concret (V-Rally 3)

**Un jeu du niveau de V-Rally 3 sur GBA doit être constructible avec l'éditeur.** Premier
objectif de la roadmap énoncé comme un résultat visible plutôt que comme une capacité. C'est
ce qui rend sa portée décidable : une capacité s'étend indéfiniment, une cible se compare.

#### Décisions verrouillées

- **C'est un rasteriseur logiciel, mesuré, pas supposé.** Relevé mGBA du 2026-08-13 : mode 4,
  framebuffer 240×160 8bpp double-tamponné (`0x0600A000` = frame 1), aucune base de tuiles, et
  des maillages qui tournent dans les menus. **Confirmé en course**, où toute la scène passe
  par ce même framebuffer. Le doute « les menus seulement » est levé, il n'y a pas de chemin
  hybride. Le détail du relevé et l'erreur qu'il corrige sont conservés en v2.0, « Ce que la
  v2.0 n'est PAS ».
- **Le framebuffer d'abord, sans alternative.** Le rendu écrit chaque pixel : il lui faut le
  substrat bitmap de la v3.0, et il n'y a aucun chemin par les calques tuilés. Ce n'est pas
  une préférence d'ordonnancement, c'est une dépendance, d'où la découpe v3.0 / v3.1.
- **La GBA n'a ni FPU ni matériel 3D.** Tout est en virgule fixe et coûte des cycles
  proportionnels au nombre de triangles. C'est le seul renderer de la roadmap dont le coût
  dépend du contenu de la scène et non de sa configuration. Le budget est donc un sujet de
  conception, pas une optimisation de fin de chantier.
- **Le vocabulaire ne change pas de règle pour autant.** « 3D » décrit ici ce que le
  PROGRAMME calcule, jamais une capacité du matériel : pas de calque 3D, pas de mode vidéo
  3D. La réserve de la v2.0 sur « Caméra3D » tombe en revanche. Une caméra à projection
  perspective a un sens dans cette version, parce que quelque chose la calcule enfin.
- **Les rôles fond/sprite sont INVERSÉS par rapport à tout le reste de l'éditeur.** Relevé en
  course (2026-08-13) : le monde entier (sol, route, panneaux publicitaires, bâtiments,
  public) est rasterisé dans l'unique fond disponible, et **c'est le ciel qui est fait de
  sprites**.

  Mesuré : un seul fond porte toute la scène, aucun élément de décor n'est un OBJ, l'arrière-
  plan lointain en est un. Déduit : en mode bitmap il ne reste qu'un fond (BG2 = le
  framebuffer), donc aucun calque pour le ciel ; et remplir le ciel dans le framebuffer
  coûterait du CPU à chaque pixel de chaque frame, quand le matériel OBJ le peint pour rien.
  Le rasteriseur ne dessine que sous l'horizon.

  Trois conséquences, toutes structurantes :

  - **Le vocabulaire actuel de l'éditeur ne tient pas ici.** Ce que l'auteur appelle « le
    fond » (le ciel) est de l'OBJ ; ce que le matériel appelle le fond est la cible de rendu,
    que personne n'authore. Les deux sens du mot se croisent, à trancher avant d'écrire le
    moindre écran, sous peine d'un inspecteur qui ment sur ce qu'il configure.
  - **Le budget OBJ devient un sujet.** Les modes bitmap divisent déjà la VRAM des sprites
    par deux (cf. v3.0), et le ciel vient maintenant en réclamer une part. Un ciel en bandes
    répétées, avare en tuiles uniques, n'est pas une optimisation tardive : c'est la
    condition pour qu'il reste des sprites au jeu.
  - **Aucune contrainte affine ne s'applique.** Les 32 jeux de paramètres OBJ, invoqués tant
    que la lecture était « décor en sprites mis à l'échelle », ne concernent rien ici.

#### Ouvert

- Tout le reste. Format des maillages, texturage ou faces plates, élimination des faces
  cachées, tri en profondeur, découpage, budget par scène, et ce que l'éditeur montre d'un
  maillage sans devenir un modeleur. Le refus de l'outil de dessin s'applique ici aussi, et
  il est bien plus dur à tenir face à de la géométrie que face à des tuiles.
- **Le ciel est-il authoré comme un fond, ou comme des sprites ?** Les deux réponses coûtent
  quelque chose. « Comme un fond » garde le modèle mental de l'auteur. Il dessine un ciel,
  le build le découpe en OBJ, mais c'est l'éditeur qui commente le matériel au lieu de le
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

- **Multijoueur par câble Link**, envisagé après la v1.0, pas avant. Très spécifique et
  coûteux à implémenter proprement.
