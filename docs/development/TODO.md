# Todo

Notre document de travail : pistes, réflexions, décisions en cours, le bazar. Il garde le
**pourquoi** des chantiers non clos : le scope, les décisions déjà verrouillées, les tranches déjà
livrées quand elles éclairent le reliquat, et les questions volontairement laissées ouvertes.

Ce fichier est interne. La vue publique (les prochains gros chantiers et leur état d'avancement)
est le [ROADMAP](../../ROADMAP.md) ; il se met à jour à partir d'ici.

Documents voisins :

| Fichier | Pour qui | Contenu |
| --- | --- | --- |
| [README](../../README.md) | un visiteur | une ligne par version |
| [ROADMAP](../../ROADMAP.md) | le public | les prochains gros chantiers et leur avancement |
| [CHANGELOG](../../changelog/CHANGELOG.md) | qui veut savoir ce qui a changé | une entrée courte par chantier important livré (archive officielle) |
| [changelog/archives/](../../changelog/archives/) | qui rouvre une décision passée | le détail complet d'un chantier livré |
| **ce fichier** | nous | scope, décisions, reliquat ouvert, pistes |
| [ARCHITECTURE](ARCHITECTURE.md) | qui modifie le code | comment c'est construit |
| [Référence de scripting](../scripting-reference.md) | qui écrit un script | le Lua accepté, et ce qui ne l'est pas |

Convention : **Décisions verrouillées** = tranché, à implémenter tel quel. On ne rouvre
pas sans raison neuve. **Ouvert** = identifié mais volontairement non tranché : à rouvrir
quand le chantier démarre réellement.

Plan du fichier :

1. [Versionnement](#versionnement) : ce que veulent dire `X`, `Y` et `Z`.
2. [Chantiers importants](#chantiers-importants-y) : ce qui donnera les prochaines versions `0.Y.0`.
3. [Vers 1.0.0-stable](#vers-100-stable) : l'affirmation de capacité qui clôt l'alpha.
4. [Pistes](#pistes) : tout ce qui est ouvert sans être (encore) un chantier important.
5. [Plus tard](#plus-tard) : ce qui est envisagé mais ni planifié ni numéroté.
6. [Repères](#repères) : l'état des lieux et les retours d'expérience qui bornent le reste.
7. [Hors périmètre](#hors-périmètre-pour-linstant).

---

## Versionnement

Une release s'écrit `X.Y.Z-<étiquette>`, l'étiquette toujours écrite. Tant que le produit n'est pas
stable, c'est `-alpha`, et l'alpha dure jusqu'à **`1.0.0-stable`**. La version actuelle est `0.1.x-alpha`
(aucune release publique pour l'instant). **Quand et sous quel numéro sortira la première release
publique : on le décidera plus tard.** La version vit dans `editor/core/app_info.py`, le tag la confirme.

| Chiffre | Ce qu'il compte | Où ça se lit |
|---|---|---|
| `X` | une release majeure : `0` jusqu'à l'affirmation de capacité, puis `1.0.0-stable` | [Vers 1.0.0-stable](#vers-100-stable) |
| `Y` | un **chantier important**, composé de plusieurs chantiers plus petits | une entrée du [CHANGELOG](../../changelog/CHANGELOG.md), un fichier de [changelog/archives/](../../changelog/archives/) |
| `Z` | s'incrémente à chaque commit et dit ce qui a été fait concrètement | le message de commit, l'historique git |

`Z` n'est pas un chantier suivi dans ce fichier. Le message de commit nomme ce qui a été fait :

```
chantier Y : modification de telle chose
bugfix : correction d'un widget cassé
patch : reload asset when button pressed
```

Conséquences :

- Un **chantier important** a sa section dans [Chantiers importants](#chantiers-importants-y). Quand il
  est livré, son détail part dans `changelog/archives/` et une entrée courte rejoint le CHANGELOG.
- Les anciens « chantiers techniques » ne sont plus une catégorie : ce sont des [pistes](#pistes)
  sans numéro. Quand une piste grossit assez pour justifier une release, elle est promue chantier
  important ; sinon, elle avance par commits `Z`.
- Les noms `v0.2` à `v0.31` qu'on retrouve dans ce fichier, le CHANGELOG et les archives sont les
  **jalons de développement** d'avant la remise à zéro (2026-10-21). Ils sont gardés comme
  historique et ne sont **pas** des versions du logiciel.

---

# Chantiers importants (Y)

Ce qui donnera les prochaines versions `0.Y.0`. **Liste figée le 2026-10-22** ; l'ordre de `0.2` à `0.7`
est une suggestion, il peut bouger. Le premier chiffre de ce tableau n'est pas une date de sortie :
le moment et le numéro de la première release publique se décident plus tard.

| Y | Chantier important | Il regroupe |
| --- | --- | --- |
| 0.1 | État actuel (base) | tout l'existant, jalons v0.2 à v0.28 (voir le [CHANGELOG](../../changelog/CHANGELOG.md)) |
| 0.2 | [Mises à jour](../../changelog/archives/updates-from-about.md) | **livré le 2026-10-22** : la fenêtre *Updates* ; reste à essayer la pop-up au lancement et le téléchargement sur build empaqueté |
| 0.3 | [Assets et disque](../../changelog/archives/assets-and-disk.md) | **livré le 2026-10-23** : `assets/` à l'auteur, ids stables, onglet Disk, *Create from source* / *Create blank* ; les références par id en sont sorties, reste le [reliquat](#assets-et-disque-ce-qui-reste-après-la-livraison-de-la-03) |
| 0.4 | [Texte et données](../../changelog/archives/text-and-data.md) | **livré le 2026-10-23** : écran Texte et séquences de dialogue, `Text`/`Textbox`, écran Données ; reste le [reliquat](#texte-et-données-ce-qui-reste-après-la-livraison-de-la-04) |
| 0.5 | [Fonds](../../changelog/archives/backgrounds.md) | **livré le 2026-10-23** : le plan de travail (canvas, image posée, Ajuster / Remplir / 1:1), la compression qui se joue, l'écran Fond (Inpainting, Painting) ; reste le [reliquat](#fonds-ce-qui-reste-après-la-livraison-de-la-05), dont la comparaison source/compressé, **non classée** |
| 0.6 | [Interaction avec un acteur](#interagir-avec-un-acteur-on_interact-et-le-composant-interactive) | `on_interact` et le composant `interactive` |
| 0.7 | [Export navigateur](#diffuser-une-rom-dans-le-navigateur-itchio) | itch.io, ROM jouable dans le navigateur |

Non classés pour l'instant (restent des [pistes](#pistes)) : le son, dont [les réglages des SFX et des jingles](#dupliquer-un-asset-et-régler-sfx-et-jingles)
(sortis du 0.3 le 2026-10-22 ; la duplication d'asset, livrée, y est décrite aussi), les prefabs, la famille « API et
scripts » (mixer, sous-objets, listes d'interface, calques par nom).

## Diffuser une ROM dans le navigateur (itch.io)

*Chantier important. Ancien nom : jalon v0.29.*

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

## Interagir avec un acteur (`on_interact` et le composant `interactive`)

*Chantier important. Ancien nom : jalon v0.31.*

**Ouvert le 2026-10-21. Conception posée, aucune ligne de code.** Rien n'est verrouillé : la demande tient en
trois pièces, le reste est proposé.

### D'où vient la question

« Appuyer sur A devant un coffre, un panneau, un PNJ » est le geste le plus courant d'un jeu d'aventure, et
il n'a aujourd'hui aucune expression. Il faut l'écrire à la main dans le script de l'objet : un
`on_update` qui, à chaque frame, lit `input:pressed("a")` et teste un recouvrement avec le joueur. C'est
du Lua exécuté pour tous les objets, à chaque frame, pour un événement qui n'arrive qu'à l'appui.

### Ce que ça livre (demandé)

- **Un événement `on_interact`** dans `EVENT_REGISTRY` (`scripting/api.py`), délivré au script de l'acteur
  interactif. Proposé : `function on_interact(who)`, `who` étant l'acteur qui interagit (le joueur).
  Signature C : `void {prefix}_on_interact(Actor* self, Actor* who)`.
- **Un composant `interactive`** (`core/models/components.py`, entrée de `COMPONENT_REGISTRY`) qui définit
  **comment** l'événement est déclenché. Plusieurs manières sont prévues, d'où un champ `mode`.
- **Une entrée interne `interact`**, liée par défaut au bouton **A** (décidé le 2026-10-21). Elle est
  interne comme les dix boutons (`BUTTON_NAMES`) et comme les axes `horizontal`/`vertical`, qui « existent
  toujours, même sans axe déclaré » (v0.28) : elle existe dans tous les projets sans migration, ne se
  supprime pas, et **son nom ne se change pas**. Son **réglage**, lui, est libre : A par défaut, mais
  l'auteur choisit n'importe quel bouton (`B`, `up`…) ou un accord de plusieurs (`up + a`), avec les mêmes
  cases à icônes et la même validation que toute entrée (`InputBinding.buttons`, sous-ensemble de
  `BUTTON_NAMES`). Elle apparaît dans *Project Settings → Input → Inputs*, ligne au nom verrouillé.
  Le nom `interact` est **refusé au build** à toute entrée, axe ou séquence de l'auteur, par le diagnostic
  unique (le même journal que les autres erreurs de build), avec un message qui dit quoi renommer.

### Décisions verrouillées (2026-10-23, relecture du code avec l'auteur)

- **Préalable : deux notions distinctes sur l'acteur.** `dir_x`/`dir_y` est la **trajectoire** (calculée
  depuis la vitesse, 0 à l'arrêt). `facing_x`/`facing_y` est le **rendu** : la dernière valeur non nulle de
  la direction, conservée à l'arrêt, sur les deux axes. Le `dir_x` seul ne pouvait pas porter `facing`
  (il retombe à 0 à l'arrêt, `actor_types_static.h`), et il n'existait aucune mémoire en Y. Les quatre
  champs sont dans `Actor` (variables de base, lisibles et modifiables à la main par les scripts) ; leur
  **calcul** seul est conditionnel. `face_x` quitte l'entrée OAM (`gen_sprite.py`) pour devenir
  `facing_x` de l'acteur.
- **`auto_dir` devient `facing_auto`** (API, composant sprite, `api_reference.py`, codegen, tests). Le calcul de
  `facing` n'est compilé que pour un acteur qui le déclare ; celui de `dir` reste compilé **partout, quoi qu'il
  arrive**, tant qu'il n'existe ni rigid body ni static body qui permettraient de savoir statiquement si un
  acteur se déplace.
- **Pas de migration** : aucun utilisateur. Le repli de direction du sprite à l'arrêt peut changer d'affichage
  (il lira aussi `facing_y`) sans traitement des anciens projets.
- **Le test de recouvrement se fait par couple de tags**, comme `actors_overlap_mask` : `actors_overlap_boxes`
  rend le premier couple trouvé et peut prendre la mauvaise box du joueur.
- **`facing` est une visée, pas un recouvrement** (décidé le 2026-10-24, remplace la règle du signe des
  centres) : la box de l'interacteur est **projetée dans sa direction de `facing`** sur une portée `reach`
  (boîte étirée, pas un rayon fin : en diagonale, 8 directions, un rayon passerait entre deux boîtes), et on
  teste le recouvrement de cette boîte avec la box de la cible. Le joueur arrêté contre un obstacle déclenche
  donc l'interaction sans marge de portée sur la zone. **Ne traverse pas les murs** : la visée est arrêtée par
  la carte de collision (`tile_wall_at` échantillonné de la box à la cible, sur la frame d'appui seulement).
  Un `facing` encore à 0 (jamais posé) n'interagit pas ; le facing initial vient du sélecteur de direction de
  l'inspecteur, comme `dir_x`/`dir_y`. **`reach`** est un réglage de projet unique (**4 px par défaut**, dans
  les settings). La box de visée de l'interacteur **se crée automatiquement, même sans boîte de collision**.
- **Plusieurs cibles ou plusieurs interacteurs au même appui : le plus proche** (le long de la visée en
  `facing`, écart de centres en `hover`), passe supplémentaire sur la frame d'appui seulement.
- **`Player` absent ou renommé : recréé** (l'éditeur est mis à jour de force, pas de projet ancien à préserver).
- **`hold` avec un accord** : le plus petit des compteurs fait foi (proposé, non contesté).
- **`released`** ne déclenche que si l'interacteur est **encore dans la zone** au relâchement ; sinon aucun
  événement.
- **Renommer ou supprimer le tag d'une boîte désignée** met à jour `interactive` : `RenameCollisionTagCmd`,
  `RemoveCollisionTagCmd` et `rename_lua_refs` le couvrent, annulation comprise.
- **Le composant a un coût** (une boîte de plus sur l'acteur, un emplacement de `MAX_BOXES`) : normal, il est
  chiffré au protocole de mesure. Un acteur déjà plein est une erreur de build qui le dit.
- **Les saisies (`pressed`, `hold`, `released`) lisent l'entrée interne `interact`** (bouton A par défaut,
  réglable) : ce sont des *gestes*, pas un choix de bouton.

### Les deux sélecteurs (précisé le 2026-10-23, remplace la table des trois modes)

`interactive` est un système **automatisé** qui réutilise des blocs déjà émis par le codegen. Deux sélecteurs
indépendants, qui se croisent :

| Sélecteur | Valeurs | Réutilise |
| --- | --- | --- |
| **Saisie** | `pressed` (front montant), `hold` (tenu `n` frames), `released` (relâché) | les gestes d'entrée existants (`input_pressed`, compteurs de boutons v0.28, anneau `released`) |
| **Interaction** | `hover` : l'interacteur **recouvre** la zone ; `facing` : la box de l'interacteur, **projetée dans son `facing`** sur `reach` et arrêtée par les murs, touche la zone | le test de recouvrement par couple de tags (`hover`), la boîte projetée (`facing`) |

- **La zone** reste une `CollisionBoxComponent`, pas une géométrie nouvelle : une zone, une seule source de
  vérité, déjà dessinée au canvas. Deux façons de l'obtenir :
  - **Boîte implicite** : le composant crée lui-même une boîte minimale, sans que l'auteur en dessine une.
    Taille réglable, **16×16 px par défaut** sans sprite, **la taille du canvas du sprite** sinon ; tag
    `Interactive`, **réservé et non modifiable**, présent d'office comme `Player` (même casse) ; `solid` à
    trancher (voir « Ouvert »). Le calcul de la boîte (16×16 ou taille du canvas du sprite) est **une seule
    fonction**, appelée par le canvas et par le codegen.
  - **Boîte existante** : si l'acteur en porte déjà une, le composant la désigne par son tag.
- **Pas de mode `contact`** (décidé le 2026-10-21). Entrer dans une zone sans bouton, c'est
  `on_collision_enter` sur une boîte `solid=False` : même suivi par paire, même masque, déjà livré. Tous les
  modes de `interactive` reposent donc sur une entrée, ce qui est ce que `on_collision_enter` n'exprime pas.
- **L'interacteur est désigné par le tag d'ACTEUR `Player`** (précisé le 2026-10-24) : seul un acteur portant ce
  tag déclenche les interactions. **Ce n'est pas le tag de collision `Player`** (celui de
  `DEFAULT_COLLISION_TAGS`). Constaté dans le code le 2026-10-24 : **la notion de tag d'acteur n'existe pas
  aujourd'hui** (`Actor` n'a ni groupe ni étiquette, seuls les tags de BOÎTES existent). C'est donc un
  concept neuf, à définir (voir « Ouvert »). Le coût reste linéaire : un test par interacteur, jamais
  « n'importe quel acteur ». `who` est l'acteur qui interagit.
- **Reste de l'ancienne conception, à réviser** : *« l'étiquette de collision `Player` est réservée »*
  (décidé le 2026-10-21) ne se justifie plus si `interactive` dépend du tag d'acteur. Texte conservé pour mémoire : ni renommable, ni supprimable dans
  *Project Settings → Collisions*, puisque `interactive` en dépend. Aujourd'hui rien ne l'empêche
  (`RenameCollisionTagCmd` et `RemoveCollisionTagCmd` l'acceptent comme n'importe quel tag, et
  `DEFAULT_COLLISION_TAGS` ne la distingue pas de `body`). Le garde-fou se pose **dans les deux
  commandes**, pas seulement dans l'interface : l'écran grise le champ et la corbeille, mais c'est la
  commande qui refuse, sinon un autre appelant contourne l'écran. Une constante nommée
  (`PLAYER_COLLISION_TAG`) devient la seule source du nom, lue par le codegen et par l'interface ; ses
  cases de matrice (paires activées ou non avec les autres tags) restent, elles, **éditables**.
- **L'entrée** est un nom d'`InputBinding`, comme le `trigger` de `SoundFxComponent`. Par défaut
  `interact`. Un accord à plusieurs boutons marche sans cas particulier.

### Le coût par acteur qui consomme le composant

Chiffré en lisant le codegen et le runtime ; **aucune mesure sur cible**, le protocole est plus bas.

**Principe du coût : le composant se compile en code de scène, comme le déclencheur `SoundFx`.** Il n'ajoute
aucun champ à `struct Actor`, aucun appel Lua, aucune vtable. Le codegen émet, dans la boucle de la scène,
un bloc par **nom d'entrée distinct** (le patron de `sfx_by_trigger`, `main_gen.py`), et seuls les acteurs
dont le script **définit** `on_interact` y sont appelés (comme pour les événements de collision : le
codegen regarde quelles fonctions le `.lua` définit).

| Poste | Coût (`pressed`, `hold`, `released` ; `hover`, `facing`) |
| --- | --- |
| RAM par acteur (`Actor`) | 0 octet |
| RAM statique | 0 octet |
| ROM | une ligne C par consommateur (test d'activité + recouvrement + appel), une boucle par prefab poolé |
| CPU, frame **sans** appui | un seul test de masque, **partagé** par tous les consommateurs de la même entrée : coût nul par acteur |
| CPU, frame **avec** appui | un test de recouvrement par consommateur et par interacteur : `actors_overlap_boxes`, au plus `MAX_BOXES²` = 16 `box_overlap`, en pratique 1 (une zone contre un corps) |
| Pool de prefabs | `taille du pool / groupe` tests, seulement sur la frame d'appui |

- **Le gain tient au verrou d'entrée.** Le test de recouvrement n'est évalué que si l'entrée vient d'être
  pressée. Avec `pressed`, `hold` et `released`, 64 coffres ne coûtent qu'un test de masque tant que personne
  n'appuie ; le script équivalent écrit à la main paie son `on_update` à chaque frame.
- **Pas de rejet gratuit.** Le test de recouvrement est le seul filtre spatial : il n'y a pas de grille.
  Le coût d'une frame d'appui croît donc linéairement avec le nombre de consommateurs **actifs** de la scène,
  multiplié par le nombre d'interacteurs (en pratique 1).
- **Si plusieurs zones se recouvrent au même appui**, la règle simple est « tous déclenchent », mais c'est
  rarement ce que veut un jeu (deux panneaux côte à côte). Une règle « un seul, le plus proche » coûte une
  passe de plus **sur la frame d'appui seulement** (le plus petit écart de centres). À trancher.
- **Ce que le composant ne paie pas** : pas de `on_update`, pas de script requis pour la détection, pas de
  champ dans `Actor`. Un acteur sans `on_interact` défini ne génère aucune ligne (avertissement au build :
  composant sans consommateur).

**Protocole de mesure** (à faire à l'ouverture, avant de promettre un chiffre) : une scène de test avec
8, 32 et 128 acteurs `interactive`, chaque mode, en frame d'appui et hors appui ; lecture en lignes de balayage
(`VCOUNT`, l'unité du budget de détection) dans mGBA ; comparaison à la même scène écrite en `on_update`. Les
valeurs mesurées remplaceront le tableau qualitatif ci-dessus, dans cette section.

### Déroulé (proposé)

0. **Préalable : le facing de l'acteur** (voir les décisions ci-dessus). **Livré le 2026-10-24, tests ciblés au
   vert, ROM non rebuildée ni jouée.** `facing_x`/`facing_y` dans `Actor` ; `auto_dir` renommé `facing_auto` ;
   `dir_x`/`dir_y` recalculés depuis la vitesse à chaque frame (0 à l'arrêt : avant, le calcul ne tournait que
   si `vx` ou `vy` était non nul, donc `dir` gardait la dernière valeur à l'arrêt) ; le regard est le **vecteur**
   de la dernière direction non nulle (après droite puis haut : `(0,-1)`) ; **la direction d'animation lit le
   regard**, plus la trajectoire ; l'API gagne `self.facing` (vecteur ou boussole, comme `self.direction`) et
   `self.facing_auto` remplace `self.auto_dir`. `face_x` reste dans l'OAM (mémoire du côté pour le repli de
   rendu, par axe, à part du vecteur) et suit désormais `facing_x`. **`Actor` passe de 68 à 72 octets**
   (2 octets de champs, 4 facturés par l'alignement) ; le plafond du test est relevé en conséquence.
   Reste à faire : le projet Platformer écrit `self.direction = vec2(move_dir, 0)` (Player.lua:36) pour piloter
   l'animation, il doit écrire `self.facing` (démo non modifiée sans accord) ; le calcul du regard est gardé par
   un drapeau d'exécution (`facing_auto`), pas encore par une compilation conditionnelle.
1. **L'entrée interne `interact`** (**livrée le 2026-10-24, tests ciblés au vert, pas vérifiée à l'écran** :
   `ProjectSettings.interact_buttons`, A par défaut, écrit seulement s'il diffère ; masque `interact` toujours dans
   `compute_input_layout`, donc lisible aussi par `input:pressed("interact")` ; le nom est une erreur de build
   pour un accord, un axe ou une séquence de l'auteur ; ligne verrouillée en tête de la carte Inputs, un accord
   vide est refusé ; libellés EN/FR). Non fait : le choix de `interact` dans le déclencheur d'un `SoundFx`,
   le guide utilisateur. Texte d'origine : déclarée avec les entrées internes, validée comme nom réservé, listée
   (verrouillée) dans *Project Settings → Input → Inputs*. Petit, indépendant, testable seul.
2. **Le composant** : `InteractiveComponent`, enregistrement, sérialisation, inspecteur
   (`component_editors/`), menu « + Component », libellés EN et FR. **Livré le 2026-10-24, tests ciblés au vert,
   pas vérifié à l'écran** : champs `input_mode` (pressed / hold / released), `hold_frames`, `interaction`
   (hover / facing), `box_tag` (vide = boîte propre), `box_w`/`box_h` (0 = auto) ; `interactive_box_size`, la
   fonction unique de la taille implicite (cadre du sprite, sinon 16×16), que l'inspecteur utilise déjà pour
   écrire « Auto (n) » ; un seul composant par acteur (le menu masque l'entrée) ; le tag de collision
   **`Interactive`** est réservé (déclaré d'office, recréé dans un projet ancien, `RenameCollisionTagCmd` et
   `RemoveCollisionTagCmd` le refusent, la matrice grise son nom et sa corbeille, ses cases restent éditables) ;
   vérifications au build (`_check_interactive` : boîte désignée absente, plus de place pour la boîte propre,
   plusieurs composants). **Pas encore** : la boîte implicite n'existe ni au canvas ni dans le C émis, rien ne
   déclenche `on_interact` (étapes 3 et 4), `reach` n'est pas encore dans les settings.
3. **L'événement** : entrée de `EVENT_REGISTRY`, stub, icône, checker, documentation de l'API
   (`api_reference.json`). **Livré le 2026-10-24, tests ciblés au vert, ROM non buildée** : `on_interact(who)`
   dans `EVENT_REGISTRY` (signature C `void {prefix}_on_interact(Actor* self, Actor* who)`, icône `ev_interact`,
   le checker refuse un paramètre que le moteur ne passe pas), les deux listes d'`extern` de `main_gen.py` la
   connaissent ; **`interact_reach`** (4 px par défaut, 0 à 64, écrit seulement s'il diffère) est un champ de
   `ProjectSettings` réglé dans la ligne `interact` de Project Settings → Input ; le build avertit d'un composant
   Interactive dont le script n'a pas `on_interact`, et d'un `on_interact` sans composant actif. **Rien ne
   l'appelle encore** : c'est l'étape 4.
4. **Le codegen** : le bloc par entrée dans `main_gen.py`, la variante prefab poolé. **Livré le 2026-10-24, les
   trois modes de saisie et les deux d'interaction d'un coup ; un vrai build gcc d'un projet interactif
   passe (`tests/rom_build/test_interactive_rom.py`, lent) ; pas joué sur console, pas mesuré.**
   Nouveau module `codegen/runtime_codegen/interact_gen.py` : aides C (`interact_pick`, visée, mur) émises
   seulement si le projet a un composant actif ; dans la boucle de scène, **un test de geste par (mode,
   durée)** puis, par interacteur, la recherche du consommateur atteint le plus proche, à partir de tables
   par geste (acteur, rang de zone, visée, fonction) ; un acteur sans `on_interact` n'entre dans aucune
   table. `hold` = le plus petit compteur vaut exactement `n` (plafonné à 254, les compteurs saturent à 255) ;
   `released` = relâché alors que l'interacteur est encore dans la zone. `effective_collision_boxes` pose la
   boîte propre (`Interactive`, non solide) en dernier sur l'acteur ou le prefab, une seule fonction pour le
   build et, plus tard, le canvas. **L'interacteur est `Actor.is_player`** (case « Joueur » de l'inspecteur,
   scènes seulement) ; sa boîte de visée est la première boîte solide active, sinon la première active, sinon le
   cadre de son sprite. Le build avertit d'une scène à zones sans joueur. **Projet d'essai** : `Project Test/Interact` (joueur, coffre en Pressed + Facing, lampe en Held + Facing, plaque en Released + Hover), généré par le vrai pipeline (création d'assets, composants), qui se valide sans message et se compile en ROM ; jamais joué sur console. **Retouche du 2026-10-24** : un prefab peut être « Player » (case sur sa racine, `Prefab.is_player` sérialisé seulement s'il est posé, repris par l'instanciation, Expose et Relink, pas propagé aux instances déjà posées comme `pal_bank` ; un pool de prefabs Player est parcouru par une boucle) ; un interacteur sans sprite suit son regard dans le bloc Interactive, car le tick d'animation (où se calcule le regard) n'existe que pour un acteur avec sprite ; un prefab poolé reçoit `facing_auto` au spawn comme un acteur de scène (parité : jusqu'ici un acteur poolé n'avait aucun calcul de direction). La case est dans l'inspecteur, sous « Active on start » (elle était dans la carte Transform, repliée par défaut, donc introuvable) ; l'acteur « Player » de la scène de départ d'un projet neuf (`Project.create`) porte le tag.
   **Finition livrée le 2026-10-24** : la boîte propre est dessinée au canvas, en jaune, avec la MÊME
   fonction que le build (`owner_effective_boxes`, qui dimensionne d'après le cadre du sprite affiché) ; le
   guide utilisateur [Faire interagir le joueur avec un acteur](../user-guide/interact.md) est écrit, lié depuis
   les deux index. Les diagnostics neufs du validateur sont testés mais la référence
   `tools/diagnostic_coverage_baseline.json` n'est pas relevée (elle ne se relève qu'après une suite complète).
   **Limites connues** : un joueur dont le sprite est
   affine garde le cadre non centré pour sa boîte de repli ; un prefab ne se marque pas « joueur » ; la
   visée d'un joueur de plusieurs boîtes n'utilise que la première solide ; `facing` teste les murs entre
   centres (une zone qui recouvre déjà le joueur derrière un mur est bloquée).
5. **Les sélecteurs** un par un, `pressed` + `hover` d'abord (c'est le cas qui rend la mesure utile), puis `facing`,
   puis `hold` et `released`.
6. **La mesure**, puis la section « coût » remplacée par les valeurs.
7. **Documentation** : `docs/user-guide/` (un guide « interagir », qui remplace le recouvrement écrit à la
   main), ARCHITECTURE.md ; le détail part ensuite dans `changelog/archives/v0.31.md`.
8. **Tests ciblés** : sérialisation du composant, émission du bloc par entrée, entrée par défaut. Pas de
   suite complète.

### Fichiers annoncés (à confirmer en relisant le code)

`core/models/components.py`, `core/models/settings.py` (`PLAYER_COLLISION_TAG`, l'entrée interne),
`core/project.py` (`create`, seulement pour `Player`), `ui/scene_manager/inspectors/inputs_card.py`,
`codegen/runtime_codegen/input_layout.py` (résolution du nom en masque),
`RenameCollisionTagCmd` et `RemoveCollisionTagCmd`, `CollisionsPanel` (`project_settings_dialog.py`), `scripting/api.py`
(`EVENT_REGISTRY`, `api_reference.json`), `codegen/runtime_codegen/main_gen.py` (+ l'en-tête qui déclare les
fonctions `extern`), `ui/scene_manager/inspectors/component_editors/`, les deux `labels*.json`, les
infobulles, ARCHITECTURE.md, `docs/user-guide/`.

### Ouvert

- **Où vit le réglage de `interact`** : l'entrée est interne, donc absente de `settings.inputs`. Proposé :
  un champ de `ProjectSettings` (`interact_buttons`, défaut `["a"]`), écrit seulement s'il diffère du défaut,
  donc aucun projet existant ne change. Le codegen (`input_layout.py`) le résout comme un accord ordinaire.
  Un accord vide (aucun bouton coché) est refusé à la saisie : l'entrée ne peut pas devenir inatteignable.
- **L'appui qui ferme un dialogue** (point à vérifier au codegen, tranche 4) : `input_pressed` est un état
  global de la frame, rien ne le consomme, et le bloc `interact` tourne après les `on_update`. À vérifier : qui
  lit A pour avancer ou fermer une `Textbox` (le moteur, ou le Lua de l'auteur) ? Si c'est le moteur, l'auteur
  n'y peut rien et il faut une garde.
- **L'interacteur doit déclarer `facing_auto`** pour le mode `facing` : avertissement au build si un acteur
  portant la box `Player` n'a pas le calcul de facing.
- **`who` dans `on_interact`** : retenu comme un `Actor` (voir plus haut). Reste à fixer ce qu'un script
  peut en lire, comme pour le `other` de `on_collision_enter`.
- **Un délai de rechargement** (empêcher le rebond d'un appui) : probablement un champ `cooldown` en frames,
  qui coûterait un `u8` par consommateur ; non proposé tant que le besoin n'est pas là.
- **Interaction avec la pause et les boîtes de dialogue** : un appui sur A qui ferme un dialogue ne doit
  pas rouvrir le coffre. Dépend de la façon dont le texte consomme l'entrée ; non étudié.

---

# Vers 1.0.0-stable

## Le pipeline 2D complet (`1.0.0-stable`)

> **Mise à jour du 2026-10-21 : les compteurs sont remis à zéro.** La version actuelle
> est `0.1.x-alpha` (pas `1.0.0-alpha`), l'alpha dure jusqu'à `1.0.0-stable`, et le numéro de la
> première release publique sera décidé plus tard. Ce jalon garde son contenu (l'affirmation de
> capacité, les cinq genres) : le texte ci-dessous, écrit avant, parle encore de « v1.0-alpha » ;
> lire « version alpha » pour une sortie intermédiaire, et `1.0.0-stable` pour le jour où l'affirmation de capacité sera tenue. Voir [Versionnement](#versionnement).

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

**La numérotation** (`X.Y.Z`, `0.1.x-alpha` jusqu'à `1.0.0-stable`) est décrite dans [Versionnement](#versionnement).

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

### Présenter le projet : trois démos jouables (objectif posé le 2026-10-24)

Avant de montrer Backstage à des amis, l'auteur veut **trois démos jouables de bout en bout** : un **jeu
d'aventure**, un **jeu de plateforme** et la **démo Pong**. Objectif de présentation, pas un jalon de
version : rien n'est planifié ni chiffré, et l'état de chacune reste à qualifier en la jouant.

| Démo | Point de départ | Ce qui est connu |
| --- | --- | --- |
| **Aventure** | `Project Test/Interact` (joueur, coffre, lampe, plaque) ; `Project Test/Village` à relire comme source possible | Le chantier « Interagir avec un acteur » en est la base : composant Interactive, joueur tagué, blocage des obstacles. Il manque ce qui en fait un jeu (dialogues, transitions entre scènes, un but), à choisir. |
| **Plateforme** | `Project Demo/Platformer` | Dépend du blocage en plateforme (voir « Suite prévue » dans la piste des collisions) dès qu'un acteur sert de sol. |
| **Pong** | `Project Demo/PongAdvanced`, aussi le modèle téléchargeable | À jouer de bout en bout et à terminer ; le dépôt contient des modifications non committées de l'auteur sur ce projet. |

À décider avant d'ouvrir : ce que chaque démo doit **prouver** (une idée par démo, pas toutes), si elles
partagent le même thème visuel, et comment les montrer (ROM jouée dans mGBA, ou le paquet web de la v0.29).
Chaque démo se vérifie **en la jouant**, pas par les tests : les tests actuels n'ont validé que les builds
et des sondes natives, jamais une partie sur console ou émulateur.

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
  [l'archive v0.24](../../changelog/archives/v0.24.md).
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

# Pistes

## État des pistes

Une piste est un sujet ouvert qui n'a pas (ou pas encore) de numéro de version : une réécriture, une
clarification, une garantie côté code, ou une idée à instruire. Elle avance par commits (`Z`) et n'entre
pas au CHANGELOG ; si elle grossit au point de justifier une release, elle est promue
[chantier important](#chantiers-importants-y). Une fois close, son détail rejoint
[changelog/archives/](../../changelog/archives/), référencé par son nom. Ce tableau ne garde que les
pistes **non closes**.

**Livré le 2026-10-23, un thème clair aux rôles de fond tenus.** Chaque fond a un rôle et un seul : `BG_DEEP`
les creux (fenêtre, canvas, graphes, listes du Disk, barres de statut), `BG_BASE` le corps d'une library,
`BG_PANEL` les inspecteurs et le fond des écrans, `BG_RAISED` les barres et menus, `BG_INPUT` les champs et les
petits boutons. `CANVAS_BG` et `GRAPH_BG` sont supprimés (ils valaient `BG_DEEP` en sombre, un gris à part en clair) ;
les gris du thème clair codés en dur sont remplacés par ces rôles ; les racines des écrans Sprites, Fonds et Texte
passent en `BG_PANEL` comme les autres. `tools/light_theme_tuner.py` règle les gris du thème clair avec un aperçu
(il lit `_LIGHT` dans `theme.py`, ne l'écrit pas). **Piège corrigé** : une feuille de style posée sur un panneau
sans sélecteur (`background:…; border-left:…`) se recopie sur TOUS ses enfants, d'où des barres verticales à gauche
de chaque widget ; les neuf cas trouvés sont scopés sur la classe du panneau. Même cause pour l'en-tête de library,
qui était `transparent` et prenait la couleur de l'écran parent : il peint maintenant `BG_PANEL`. **Non vérifié à
l'écran** (seulement importé et rendu hors écran).

**Livré le 2026-10-23, un seul fond de canvas.** Le fond du sprite editor (creux `BG_DEEP`, grille grise, halo au
survol) devient le fond de TOUS les canvas, via `ui/common/canvas_backdrop.py` (`paint_backdrop`,
`GridBackdropViewMixin`, `GridBackdropScrollArea`) : canvas de scène, graphe de scènes, palette, planche de glyphes
et aperçu écran des polices ; l'éditeur de fonds et le sprite editor l'utilisaient déjà. Pas encore alignés : la
comparaison de polices (`font_asset_preview.py`), le graphe de musique et les machines à états (fond propre).
L'éditeur de fonds montre aussi la case que le prochain clic touchera (pinceau, gomme, seau) et l'aperçu du
rectangle pendant le glisser. **Non vérifié à l'écran.**

**Livré le 2026-10-17, [Le gabarit commun des pop-up](../../changelog/archives/common-popups.md).**
Les messages d'information, d'attention, d'erreur et de confirmation des 22 modules concernés
passent par `ui/common/popup.py` : illustrations adaptées au type de message, boutons et
styles partagés, icônes cohérentes par type. Le détail et les vérifications sont archivés.

**Livré le 2026-10-20, la matrice des collisions ne rogne plus** (Project Settings → Collisions).
La zone de la matrice prend l'espace libre de la page, les lignes restent en haut, le « + » suit la
dernière ligne, et un défilement n'apparaît que si la fenêtre est trop petite. Les lignes gagnent un
espacement et un survol. **Non vérifié à l'écran** (seulement compilé) ; une coche dans les cases
cochées n'a pas été ajoutée.

**Livré le 2026-10-20, l'éditeur écrit ses fichiers texte en LF.** Le dépôt est canonique en LF
(`.gitattributes` : `* text=auto eol=lf`, sauf `*.nsi` en CRLF), mais Python écrit en CRLF sous Windows :
chaque sauvegarde de l'éditeur laissait du CRLF sur le disque, d'où des avertissements Git à chaque commande
et des fichiers aux fins de ligne mélangées. Les 20 écritures de texte qui n'en précisaient pas portent
maintenant `newline="
"` (`atomic_write`, `build_output.write`, préférences, scripts créés, journaux, `tools/`),
et les 138 fichiers suivis qui avaient du CRLF (démos comprises) ont été reconvertis, `installer.nsi` restant en
CRLF. Une écriture neuve de ce genre doit porter `newline="
"` ; `git ls-files --eol | grep "w/crlf"` montre
un oubli. `atomic_write` saute l'écriture d'un contenu identique, sans tenir compte des fins de ligne : un
fichier repassé en CRLF par un outil externe ne se corrige qu'à sa prochaine vraie modification. Suite complète
non relancée (seuls `test_disk_commands` et `test_interrupted_write` l'ont été).

**Livré le 2026-10-22, les correctifs urgents et le palier 2 du journal d'un utilisateur** (un petit jeu
topdown réalisé sur Backstage, journal du 2026-10-20 au 21, classé du meilleur rapport gain/coût au pire).
- *Plantages et fausses promesses* : la liste Music de l'inspecteur de scène appelait une méthode inexistante
  (`_refresh_music`) ; `actor:get(i)` est accepté par le vérificateur (le générateur de C et la doc l'acceptaient déjà) ;
  `scripting.md` dit que `wait` dans un `if` est refusé au Build (pas au diagnostic en direct) et qu'un `return` en tête
  de `on_update` saute l'avancement des séquences.
- *Interface invisible* : avertissement quand un décor est devant une interface (le plus petit BG est devant) ; une
  interface neuve se crée sur BG0 (`InterfaceNode.bg_slot = 0`, un ancien fichier sans la clé garde BG1).
- *Champs illisibles* : un champ numérique ne descend plus sous 56 px (`MIN_SPIN_WIDTH`), sélectionne son contenu au
  focus, et `W.pair` replie X/Y l'un sous l'autre quand la place manque. Les champs de la carte Canvas de l'éditeur de
  fonds sont lisibles (« 24 » n'était que « 240 » tronqué), avec l'unité en px. Une case cochée porte une coche.
  En thème clair, les icônes de fichiers du Disk sont d'un gris plus doux (`icon_mark_color`).
- *Imports* : le « + » (sons, sprites, fonds) accepte plusieurs fichiers, en une entrée d'historique ; la ressource
  sélectionnée dépliait mal sa section (corrigé) ; un build qui échoue à réécrire la ROM parce qu'un émulateur la tient
  ouverte le dit. Une copie de source n'est suffixée que face à un fichier de **même extension** : `village.xm` et
  `village.png` coexistent (le nom d'asset est unique par type, pas dans tout le projet).
- *Renommage* : F2 et « Rename state » sur un état d'animation, un nouvel état s'ouvre en édition ; un nom d'élément
  d'interface déjà pris ouvre un message (utiliser le nom suffixé, ou garder l'ancien et en choisir un autre), sans option
  d'écrasement : l'homonyme vit souvent dans une autre interface et des scripts le citent.
- *Divers* : l'inspecteur de scène se relit à la fermeture des Project Settings ; la position du curseur se lit en
  pixels ou en tuiles (un clic bascule, tous les canvas à la fois, préférence machine `cursor_unit`, y compris le
  canvas et la planche du sprite) ; le champ de contenu de l'écran Texte garde le focus quand renommer une clé
  reconstruit la table.

Refusé : une aide à la création musicale (Backstage n'est ni un tracker ni un DAW). Écarté après vérification : un
rechargement à chaud de la ROM dans mGBA (0.10.5 n'a aucune option de ligne de commande pour charger un script) ; l'ajout
rapide de composants qui « n'était pas pris » (un test enchaîne quatre ajouts sans perte, c'était le pilotage du
testeur). **Non vérifié à l'écran** : tout a été éprouvé par des tests ciblés hors écran. La suite complète n'a montré
que l'échec intermittent du `make` de devkitPro (`fatal error - add_item`), les deux fichiers concernés repassent seuls.

| Piste | Ouvert le | État |
| --- | --- | --- |
| Identité des assets et des membres de scène (en-tête `name` / `id` / `source`) | 2026-10-24 | **Première tranche livrée le 2026-10-24**, détail dans [l'archive](../../changelog/archives/scene-asset-identity.md) ; reste le reliquat : nom ou id dans l'API Lua et les champs de l'interface, index `id → nom` des fonds, prefab dérivé d'un prefab ([section](#identité-des-assets-et-des-membres-de-scène-en-tête-name--id--source)) |
| Texte et données : ce qui reste après la livraison de la 0.4 | 2026-10-23 | **Livré**, détail dans [l'archive](../../changelog/archives/text-and-data.md) ; reste le reliquat : références graphiques non consommées par la ROM, finition de l'interface Texte (Find, code mort), vérifications à la main, test ROM. Voir [ci-dessous](#texte-et-données-ce-qui-reste-après-la-livraison-de-la-04) |
| Coller un tableau dans la grille (presse-papiers seulement) | 2026-10-23 | **Reporté**, chantier technique sans numéro, pas d'usage constaté ; périmètre retenu : presse-papiers, jamais de fichier. Dépend du stockage des références. Voir [ci-dessous](#coller-un-tableau-dans-la-grille-presse-papiers-seulement) |
| Le stockage des références dans les cellules (nom ou id) | 2026-10-23 | **À ouvrir**, chantier technique sans numéro, **rien de verrouillé**, code non commencé ; il porte aussi les « références par id » (une scène qui cite un asset par son id), sorties de la 0.3 le 2026-10-23 car elles touchent toutes les scènes. Voir [ci-dessous](#le-stockage-des-références-nom-ou-id-dans-les-cellules) |
| Une seule navigation « ouvrir cet élément » entre les écrans | 2026-10-23 | **À ouvrir**, chantier technique sans numéro, **rien de verrouillé**, code non commencé ; un point d'entrée unique dans `Window`, `select_text` à ajouter, les « utilisations » à ramener dessus. Voir [ci-dessous](#une-seule-navigation-ouvrir-cet-élément-entre-les-écrans) |
| Le rôle des collisions contre le mode de résolution physique | 2026-10-23 | **À ouvrir**, réflexion, **rien de verrouillé**, code non commencé ; `solid` ne repousse aucun acteur (seulement la carte de collision) : séparer le rôle d'une box de son mode de résolution (Solid contre Overlap, composants RigidBody / StaticBody / CharacterBody), à trancher avec la section « Physique et collision ». Voir [ci-dessous](#piste-le-rôle-des-collisions-contre-le-mode-de-résolution-physique) |
| Des cartes de valeurs peintes par l'auteur, lues à l'exécution | 2026-10-23 | **À ouvrir**, réflexion, **rien de verrouillé**, code non commencé ; généraliser la carte de collision en cartes nommées d'entiers (gameplay, pas de rendu), la frontière avec « pas un outil de dessin » est écrite dans la section. Voir [ci-dessous](#piste-des-cartes-de-valeurs-peintes-par-lauteur-lues-à-lexécution) |
| Une seule primitive pour retenir et rendre des cases de tilemap | 2026-10-23 | **À ouvrir**, réflexion, **rien de verrouillé**, code non commencé ; le fond de conteneur (redessin suivi) et l'image BG (copie des cases) font chacun leur version du même geste, et une API de scripts `layer:save/restore/release` l'exposerait. Voir [ci-dessous](#piste-une-seule-primitive-pour-retenir-et-rendre-des-cases-de-tilemap) |
| Retours d'un utilisateur sur un petit projet topdown | 2026-10-22 | **Paliers 1 et 2 livrés (2026-10-22), palier 3 en cours (2026-10-23)**. Livré au palier 3 : le Refaire clavier (Ctrl+Y était ambigu sous Windows et ne faisait rien, c'est la vraie cause du « Redo perdu » ; l'annulation du pinceau, elle, est correcte : 16 coups = 16 entrées), le pinceau de collision (trait continu entre deux événements souris, pinceau 16 aligné sur la grille de 16 px), « Effacer la collision » dans la barre du canvas de scène, un glisser d'élément vers une autre interface refusé à voix haute (le déplacement réel entre interfaces reste à décider : cibles BG/OBJ différentes, interface partagée entre scènes), et le diagnostic en direct qui montre une attente dans un `if` (`structure_errors` : le même vérificateur que le Build, sur un contexte vide, limité aux fautes de structure). Écarté : le cadre d'un conteneur qui reste affiché malgré « Shown at scene start » (entre en collision avec le masquage d'un élément dans la scène). Livré ensuite : « Extract from PNG » du sprite dit si la palette est créée ou mise à jour ; le champ largeur d'un `Text` (grisé par construction) dit pourquoi, et le conseil de débordement renvoie vers la `Textbox` ; un « + » dans la bibliothèque de textes ; l'inspecteur d'acteur défile jusqu'à la carte Components quand on clique ou ajoute un composant ; la ligne racine de l'arbre de scène montre l'inspecteur de la scène. Palier 3 clos : une image BG masquée ou déplacée rend ce qu'elle recouvrait (le fond du conteneur) au lieu d'écrire la tuile 0 (`ui_image_snapshot_bg` / `ui_image_clear_bg` dans `gba_engine.h`, 64 cases au plus retenues par image, 2 Ko ; au-delà l'image s'efface comme avant). Vérifié par une sonde native qui pose, masque, repose et déplace une image sur un fond (`tests/native/ui_image_probe.c`, `test_ui_image_hide_native.py`) et par la compilation de vraies ROM, pas jouée sur console. Le fond d'un CONTENEUR (couleur ou nine-slice, écrit en tuiles à l'init) se masque et se remontre avec `hide()`/`show()` : le moteur le retient (`ui_fill_rect_tracked` / `ui_fill_map_tracked`, 8 fonds au plus par scène, index du conteneur émis par `scene_init`), l'efface après le texte et le repose avant lui, et un conteneur caché au départ n'est pas dessiné (`tests/native/ui_fill_probe.c`, `test_ui_container_hide_native.py`). Builds de ROM et suites interface/texte/graphismes au vert, pas joué sur console. Piste notée : une API `layer:save/restore/release` sur un rectangle de tuiles, réutilisant ce mécanisme (pool fixe à dimensionner, cartes streamées à traiter). Palier 4 : interface dessinée dans le canvas, `return` dans `on_update` avec séquences, guide topdown, import d'une planche en N états, zoom de la planche, couleur d'encre. **Décision ouverte** : sprites devant l'interface par défaut (priorité d'un fond UI = son slot, celle d'un acteur = 0). |
| Le pool ne dépend plus de l'OAM | 2026-10-20 | **Livré pour l'essentiel (2026-10-20)**, pool automatique (8 par défaut) pour un prefab spawné, entrées OAM par priorité (interface, acteurs posés, pools), avertissements OAM et matrices affines, code mort retiré ; reste une liste libre d'entrées, optionnelle (`editor/codegen/improvement.md`). Voir [ci-dessous](#le-pool-ne-dépend-plus-de-loam) |
| L'API dit tout ce que l'inspecteur règle | 2026-09-23 | **En cours**, tranche 1 (acteur, sprite, collision) livrée le 2026-09-23, sauf `parent` et `sprite_name`, **la collision est rouverte le 2026-09-24** (boîte = référence typée, `collision_box.get_tile`) ; tranches 2 (caméra, scène, calque) et 3 (interface) à suivre. Voir [ci-dessous](#lapi-dit-tout-ce-que-linspecteur-règle) |
| Piste Collision, un `Contact` d'événement | 2026-09-25 | À ouvrir, non verrouillée (normale acteur↔acteur), extraite de la struct `Actor` allégée, code non commencé. Voir [ci-dessous](#piste-collision-un-contact-dévénement-pas-une--dernière-collision-) |
| Le cache de scène | 2026-09-16 | À ouvrir. Voir [ci-dessous](#le-cache-de-scène-rouvrir-une-scène-déjà-visitée-sans-tout-redécoder) |
| Undo/redo des sidecars d'éditeur | Non renseigné | À ouvrir, envisagé pour **V2**, voir [ci-dessous](#undoredo-des-sidecars-déditeur-annuler-la-création-dun-groupe-un-déplacement-de-nœud) |
| L'écran Son montre le geste sans recalculer l'onde | 2026-10-12 | **Livré pour l'essentiel (2026-10-12)**, plus aucun rendu pendant qu'un potard est tenu, bascule Onde \| Scope (oscilloscope du mix, tiré du son qui joue), durée sur la règle, barres des canaux qui suivent le volume ; **reste ouvert** : les repères sonores de musique sont **livrés le 2026-10-14** (quatre natures, voir ci-dessous) ; les repères de **jingle** sont livrés le 2026-10-14 (tranche 1, en temps) ; restent l'appel d'événement et les points de sortie pour les music box (**chantier à décider**), un indicateur de marge du mix (proposé, **non décidé**), un scope par canal. Voir [ci-dessous](#lécran-son-montre-le-geste-sans-recalculer-londe) |
| La chaîne `if/elseif` sur une constante devient un `switch` C | 2026-10-06 | Route vers v1.0-stable, non prioritaire pour l'alpha ; piste de réflexion, **rien de verrouillé**, code non commencé, gain de perf non mesuré. Voir [ci-dessous](#piste-la-chaîne-ifelseif-sur-une-constante-devient-un-switch-c) |
| Les prefabs, l'instance garde ce qu'elle surcharge, le reste suit le prefab | 2026-10-13 | **À ouvrir**, modèle décidé par l'auteur (surcharges par champ), **dix points à trancher** avant d'ouvrir (unité d'une surcharge, structure, sens d'Expose, migration, enfants…), priorité **non arbitrée**, code non commencé. Règle le cas « prefab » de la fluidité des réglages (un seul fichier écrit). Voir [ci-dessous](#les-prefabs-linstance-garde-ce-quelle-surcharge-le-reste-suit-le-prefab) |
| L'élément d'interface appartient à sa scène, des noms locaux | 2026-10-03 | À ouvrir, priorité non arbitrée ; conception proposée, **aucune décision verrouillée**, code non commencé. Garde-fou en place : un nom en double entre deux layouts est une erreur de build. Voir [ci-dessous](#lélément-dinterface-appartient-à-sa-scène-des-noms-locaux) |
| Assets et disque : ce qui reste après la livraison de la 0.3 | 2026-10-23 | **Livré**, détail dans [l'archive](../../changelog/archives/assets-and-disk.md) ; reste le reliquat de finition (références par id portées par le stockage des références, outil de benchmark, détails d'import et de Disk, vérification à la main). Voir [ci-dessous](#assets-et-disque-ce-qui-reste-après-la-livraison-de-la-03) |
| Fonds : ce qui reste après la livraison de la 0.5 | 2026-10-23 | **Classé à part** : la comparaison source/compressé (le « compress view » et la carte d'écart), les trous d'une grande image, la limite du canvas tuilé, le bitmap au-delà de 240×160, le service d'encodage. Voir [ci-dessous](#fonds-ce-qui-reste-après-la-livraison-de-la-05) |
| La fiabilité du journal de build | 2026-10-03 | **Tranche 1 livrée le 2026-10-03** (aucune erreur avalée, tout script vérifié, fautes injectées) ; **tranche 2 livrée le 2026-10-03** (diagnostic unique, `build.log`, sortie des outils classée) ; reste ouvert : les codes stables, si le besoin apparaît. Voir [ci-dessous](#la-fiabilité-du-journal-de-build) |

---

## Identité des assets et des membres de scène (en-tête `name` / `id` / `source`)

**Première tranche livrée le 2026-10-24**, détail dans [l'archive](../../changelog/archives/scene-asset-identity.md) :
en-tête `name` / `id` / `source` pour tout sidecar et tout élément posé en scène, `source` toujours une origine
(chemin pour un fichier, id pour une instance), colonne `prefab` de la table de données. Documenté dans ARCHITECTURE.md
(section « Identité »).

**Reliquat ouvert.**

1. **Nom OU id dans l'API Lua et dans les champs de l'interface** (décidé de principe le 2026-10-24, à instruire).
   `Actor.parent`, `Camera.follow_target` et `InterfaceNode.anchor_actor` citent encore un NOM, et le build, le
   canvas et les scripts le lisent partout. Autoriser l'un ou l'autre dans `actor:get(...)` et dans les champs
   éditables ferait survivre un renommage d'acteur à tout ce qui le cite. Les ids de membres sont déjà dans les
   scènes : ce chantier n'aura aucune donnée à migrer. Questions : comment distinguer un nom d'un id dans un
   littéral (un nom de 12 chiffres hexadécimaux est déjà interdit pour les variables, cf. `ids.is_id`), et ce que
   l'autocomplétion propose.
2. **Les calques de fond écrivent `source` ET `background_name`.** Le catalogue des fonds est paresseux : retrouver
   un nom depuis un id exigerait de lire tous les sidecars à l'ouverture. Un fond renommé hors de l'éditeur n'est
   donc rattrapé par son id que s'il est déjà chargé. Sortie possible : un petit index `id → nom` des fonds, sans
   lire leur contenu. À faire seulement si le cas se présente.
3. **Un prefab dérivé d'un prefab** pourrait porter l'id du prefab parent dans son `source` (même champ, même
   sens). Non fait ; à relier à la règle d'héritage parent → enfant.
4. **`tools/migrate_background_paths.py` lit encore la clé `asset`** : à adapter avant de le relancer.
5. **Non vérifié à l'écran** : l'éditeur n'a pas été ouvert sur un projet réel après le changement de format. La
   documentation est à jour (ARCHITECTURE, section « Identité »).

## Texte et données : ce qui reste après la livraison de la 0.4

La 0.4 est **livrée** ; sa discussion complète est dans [l'archive](../../changelog/archives/text-and-data.md). Ne restent ici que les fils encore ouverts.

### Chantiers techniques nés de la 0.4

[Une seule navigation « ouvrir cet élément »](#une-seule-navigation-ouvrir-cet-élément-entre-les-écrans),
[le stockage des références](#le-stockage-des-références-nom-ou-id-dans-les-cellules),
[coller un tableau dans la grille](#coller-un-tableau-dans-la-grille-presse-papiers-seulement) (reporté).

### Écran Données

#### Références graphiques : la ROM ne les consomme pas encore (constaté le 2026-10-18)

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

#### Points restant à vérifier

1. **La confirmation de décalage.** La montrer à chaque insertion/suppression au milieu serait sûre mais possiblement pénible ; une option
   « ne plus demander pour cette session » peut concilier les deux. À tester sur une table réellement citée par des scripts.
2. **La place de l'inspecteur** avec une référence textuelle longue et une table dense (l'aperçu du texte y est désormais corrigeable).
3. **Valider les gestes sur une vraie table de jeu** : l'usage prolongé d'une table dense reste à éprouver à la main.

### Texte à l'écran (`Text` et `Textbox`)

#### Ouvert

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

### TextBox et séquences

#### Reliquat ouvert

- **Layouts partagés et renommages :** la clé d'une nouvelle page vient du rangement ; renommer une scène ou un objet ne recalcule pas les
  clés déjà créées. Trancher ce suivi en respectant les clés nommées à la main.
- **Duplication d'une boîte :** vérifier à l'usage ce que partage la copie (la séquence lue) et décider si elle doit plutôt créer ses
  propres textes et traductions.
- **Vérification à la main** de l'en-tête de séquence et de l'inspecteur, et relance du test ROM (devkitPro).

### Écran Texte : la finition de l'interface

Relu dans le code le 2026-10-23. Les blocs éditables et le retrait visible de l'aperçu sont livrés (voir [l'archive](../../changelog/archives/text-and-data.md)) ; restent :

- **Code mort à retirer.** L'atelier (`TextWorkbench`) est masqué dans `TextPanel` mais monte toujours `FontScreenPreview`, son sélecteur de police d'aperçu
  et le bouton de balisage ; les signaux `preview_font_changed` / `set_font` et les clés `txtwb.show_markup_*`, `txtwb.preview_font_*` vivent encore.
  Trancher d'abord ce que devient la police de référence pour `missing_chars()` (la « Default Font » du projet ?), puis supprimer et mettre à jour `ARCHITECTURE.md`.
- **Find (rejoindre le lieu d'usage).** Aucun bouton ni navigation depuis une entrée vers sa scène, son script ou sa table. Le socle existe désormais :
  `Window.open_element` ; reste l'index des usages à compléter (pages de TextBox, colonnes `text`, layouts partagés) et le contrat (un lieu : direct ; plusieurs :
  liste ; aucun : « non référencé »).
- **Prévisualiser une traduction dans le canvas.** `canvas_region_item` lit toujours la langue source (`page.content`) ; une traduction plus longue peut déborder
  sans signal. Décidé qu'il prévisualisera la langue choisie ; la mesure (où se choisit la langue, mémoire, liseré de troncature, plusieurs langues) n'est pas arrêtée.
- **Regroupement.** Décidé « par scène » ; les blocs se rangent aujourd'hui par clé (le rangement est la clé). À reprendre ou à abandonner explicitement.

### Vérifications non faites

- Le test ROM `tests/rom_build/test_textbox_pages_rom.py` (lent, devkitPro) est adapté au modèle dérivé mais **non relancé** depuis la refonte.
- Le contrôle à la main de l'en-tête de séquence, de l'inspecteur de TextBox et des nouveautés de l'écran Données.

---

## Coller un tableau dans la grille (presse-papiers seulement)

**Chantier technique, sans numéro de version, jamais au README ni au CHANGELOG. Reporté le 2026-10-23 : aucun usage constaté pour l'instant.**
Rien n'est verrouillé au-delà du périmètre ci-dessous ; code non commencé.

### Le besoin, s'il revient

Préparer des monstres, des objets ou des répliques dans un tableur (Excel, LibreOffice, Google Sheets), copier un bloc de cellules et le
coller d'un coup dans l'écran Données. Le presse-papiers porte alors du texte où les colonnes sont séparées par une tabulation (TSV).
Il n'existe aujourd'hui ni sélection de plage, ni collage, ni `Suppr` multiple ; le bouton « Supprimer » ne retire que la ligne courante.

### Périmètre retenu (décidé le 2026-10-23)

- **Presse-papiers seulement.** Jamais d'import ni d'export de fichier `.tsv` : un fichier garde des noms d'assets périmés après un
  renommage, le presse-papiers est consommé aussitôt.
- **Deux fonctions uniques**, `format_cell(colonne, valeur)` (copie) et `parse_cell(colonne, texte)` (collage), sont le seul endroit qui
  connaît le format d'échange. Aucun autre code ne le lit. Un changement de stockage des références ne touche qu'elles.
- **Refus atomique.** Une valeur invalide (entier illisible, nom de texte, sprite ou son inconnu, cellule hors plage) : rien n'est collé,
  le message nomme la cellule fautive. Un collage réussi est une seule commande annulable.
- **Les cellules restent validées par leur type** ; les noms se résolvent contre le catalogue du moment (uniques par famille).

### À faire le moment venu

1. Sélection de plage dans la grille, puis `Suppr` pour vider une cellule ou une plage.
2. Copie (`format_cell`) et collage (`parse_cell`), avec le refus atomique.
3. Tests : colonnes scalaires, références valides et inconnues, plage hors table, annulation en un pas.

### Dépend de

[Le stockage des références](#le-stockage-des-références-nom-ou-id-dans-les-cellules) : tant que nom ou id n'est pas tranché, `parse_cell`
et `format_cell` restent l'unique point à adapter, mais le choix doit être fait avant d'écrire du code de collage.

### Ce que ça ne fait pas

Ne change ni le format des projets, ni la ROM. Ne trie ni ne filtre les lignes : le rang reste l'index que lit `data.Table[i]`.

---

## Le stockage des références (nom ou id dans les cellules)

**Chantier technique, sans numéro de version, jamais au README ni au CHANGELOG. Ouvert le 2026-10-23, rien de verrouillé, code non commencé.**

### Constaté dans le code

- Une cellule de référence (`text`, `sprite`, `background`, `sfx`, `palette`…) **stocke le nom** de l'asset (`"line": "scr_arena_textbox_Page01"`
  dans le `.table`). Le renommage réécrit les cellules (`_rename_data_asset_refs`, `project_renames.py`).
- Les assets portent déjà un id hexadécimal stable dans leur sidecar. Les « références par id » (une scène citera un
  asset par son id plutôt que par son nom), sorties de la 0.3 le 2026-10-23, posent la même question que le stockage des cellules : ce chantier les porte.
- En ROM, une cellule `sprite` ou `background` vaut le **rang** de l'asset dans la liste du projet (`reference_index`). Ce rang change
  quand on ajoute ou supprime un asset ; c'est sans conséquence tant que la ROM est régénérée, mais un script ne doit pas l'écrire en dur.

### Pourquoi le décider avant d'échanger avec l'extérieur

Un tableur ne connaît ni les ids ni les noms futurs : il ne voit que des chaînes. Tout échange tabulaire (collage TSV, import, export)
fige un nom qui peut être renommé ensuite. Tant que le stockage n'est pas tranché, aucun format d'échange ne doit s'y appuyer.

### Direction proposée (non verrouillée)

1. **Séparer stockage et échange.** Le stockage (nom aujourd'hui, id demain) est une affaire du modèle ; l'échange est le texte que
   l'auteur voit dans la cellule.
2. **Deux fonctions uniques**, `format_cell(colonne, valeur)` et `parse_cell(colonne, texte)`, sont le seul endroit qui connaît le format
   d'échange. Un changement de stockage ne touche qu'elles.
3. **Presse-papiers seulement, jamais de fichier `.tsv`** : un fichier garde des noms périmés, le presse-papiers est consommé aussitôt.
4. **Nom inconnu au collage : refus atomique** (rien n'est collé, la cellule fautive est nommée), annulable en un seul pas.
5. **Ne pas trancher sous la pression du TSV** : le choix nom ou id appartient au chantier des références par id.

### À trancher

- Le stockage final : le nom (suivi par renommage, comme aujourd'hui) ou l'id (stable, mais illisible dans un `.table` relu par git).
- Les noms de colonnes de référence côté Lua restent-ils des identifiants lisibles quel que soit le stockage ?
- Que devient la valeur ROM (rang du catalogue) si l'id devient la clé ?

### Ce que ça ne fait pas

Ne change ni le format actuel des projets, ni la ROM, ni l'écran Données. Le [collage dans la grille](#coller-un-tableau-dans-la-grille-presse-papiers-seulement) en est le premier consommateur, reporté (2026-10-23).

---

## Une seule navigation « ouvrir cet élément » entre les écrans

**Chantier technique, sans numéro de version, jamais au README ni au CHANGELOG. Ouvert le 2026-10-23, rien de verrouillé, code non commencé.**

### D'où vient la question

Le besoin vient de l'écran Données : une cellule `text`, `sprite` ou `background` désigne un élément, et
l'inspecteur droit le décrit sans permettre d'y aller. La voie évidente existe presque : `Window._open_disk_asset`
(`window.py`) sait déjà ouvrir l'écran d'une famille d'asset et y sélectionner l'élément (palettes, sons, polices, tables de
données, sprites, fonds, scènes, prefabs, scripts).

### Constaté dans le code

- **Un point d'entrée utilisable, mais privé.** `_open_disk_asset(family, name, path)` fait `_switch_screen` puis la sélection, après
  le changement d'écran (`_show_screen` vide le bus de sélection). Aucun écran ne l'appelle directement : il n'est branché qu'à l'onglet Disk.
- **Plusieurs chemins qui font la même chose.** « Voir les utilisations » d'un script (`ScriptUsesPanel.target_requested` puis
  `_show_script_user`), la carte USAGE de la palette (`usage_activated` puis `_open_palette_usage`) et le Disk (`_open_disk_asset`)
  déclarent chacun leur signal et leur gestionnaire. `_open_disk_asset` délègue d'ailleurs à `_open_palette_usage` pour sprites, fonds,
  scènes et prefabs : la logique est déjà à moitié partagée.
- **Les textes ne se sélectionnent pas.** La table des familles contient `"texts": ("Texts", None)` : l'écran s'ouvre, rien n'est choisi.
  Il manque un `select_text(clé)` sur l'écran Texte.
- **Les tables de données se sélectionnent** (`select_table`), pas encore une ligne ni une cellule.

### Livré le 2026-10-23 (première tranche)

`Window.open_element(famille, nom)` est le point d'entrée public (`_open_disk_asset` le délègue) ; `TextEditorScreen.select_text(clé)`
sélectionne un texte malgré les filtres, sans lui donner le curseur ; l'inspecteur Données affiche **Ouvrir** quand la cellule cite un
élément existant (texte, sprite, fond, sfx, musique, scène, police, palette). Test : `tests/ui/test_data_open_reference.py`.
**Reste** : ramener les « utilisations » (scripts, palettes) sur `open_element`, le retour à l'écran précédent, le contrôle à la main.

### Direction proposée

1. **Un seul point d'entrée public** (par exemple `Window.open_element(family, name)`), qui absorbe `_open_disk_asset` et
   `_open_palette_usage`. Les écrans émettent une demande `(famille, nom)` et ne connaissent ni les autres écrans ni leurs sélecteurs.
2. **`select_text(clé)`** sur l'écran Texte : sélectionne l'entrée, déplie son dossier, retire un filtre qui la masquerait.
3. **Brancher l'écran Données dessus** : « Ouvrir le texte » et « Ouvrir l'asset » dans l'inspecteur droit, sur la cellule active.
   L'inspecteur explique et mène à la ressource citée, il ne devient pas un second éditeur.
4. **Ramener les « utilisations » dessus**, écran par écran, sans changer ce que chacun affiche.

### À trancher

- Le retour : faut-il un « revenir à l'écran précédent » après avoir suivi une référence ? Aucun mécanisme n'existe.
- Une cible disparue (texte supprimé, asset renommé entre-temps) : message dans la barre d'état, comme `disk.no_editor`.
- Les cibles qui ne sont pas des assets (une page de TextBox, une ligne de table) : le nom suffit-il, ou faut-il un chemin ?

### Ce que ça ne fait pas

- Ne change aucun format de projet, ni le build, ni la ROM.
- N'ajoute pas de navigation dans l'historique d'annulation : changer d'écran n'est pas une action annulable.

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

**Isolés le 2026-10-04.** `test_build_fault_injection.py`, `test_build_diagnostics.py`, `test_gcc_cites_the_script.py`, `test_smoke_test.py` et un cas de `test_codegen_diagnostics.py` compilent un projet entier par cas : lancés à chaque modification, la suite durait ~20 min. Ils portent le marqueur `slow`, exclu par défaut (`addopts` de `pyproject.toml`) ; `pytest -m slow` les lance ; aucun job de `release.yml` ne les exige : ils ne bloquent pas une publication.

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
vers v1.0-stable ([ci-dessous](#piste-nommer-laccès-à-un-sous-objet-de-linstance)), et la trancher
ici la trancherait deux fois. `initial_state` et `prefab_name` n'ont pas besoin de porte : `self.anim` et
`self.name` couvrent l'usage.

### Tranche 2 (caméra, scène, calque de fond (livrée le 2026-09-30))

Classement fait en lisant le runtime C (`runtime_api_inline.h`, `gba_engine.h`) et le codegen : ce qui est un
**littéral dans le C émis** est fixé au build (lecture seule) ; ce qui vit déjà en registre ou en RAM, ou coûte un
octet de RAM pour le devenir, est modifiable. Les portes déjà là (`camera.position`, `camera.bound`, `layer.visible`,
`layer.priority`, `layer.scroll`, `layer.map`, `scene.size`) ne sont pas répétées.

| Champ d'inspecteur | Porte Lua proposée | Nature | Raison (ce que le C fait aujourd'hui) |
| --- | --- | --- | --- |
| Camera `mode` | s.o. | repoussé | changer de mode et de cible en jeu est voulu, avec une transition : chantier [« La caméra change de cible »](#piste-la-caméra-change-de-cible-en-jeu-avec-une-transition) (route vers v1.0-stable). Aucune porte partielle d'ici là : le suivi est un `switch` dont les cas sont émis seulement pour les caméras à cible |
| Camera `follow_target` | s.o. | repoussé | même chantier que `mode` |
| Camera `margin_x/y` | `camera.margin` (vec2) | **modifiable** | deux littéraux du `switch` → deux octets de RAM lus par `camera_follow` |
| Camera `frame_w/h` | `camera.frame` (vec2) | **modifiable** | pilote WIN0 (`window_set(0, …)`), qui existe déjà ; un getter du rectangle de WIN0 est à ajouter |
| Camera `name` | `camera.name` (comparable par son nom) | lecture seule | `DOMAIN_CAMERA` existe ; sert à savoir quelle caméra `camera:switch` a activée |
| Scene `scroll_h/v` | `scene.scroll_h`, `scene.scroll_v` (bool) | lecture seule | choisit `(g_actors[t].x>>8)` ou `cam_x` DANS le `switch` émis |
| Scene `blend_eva/evb/evy` | s.o. | repoussé | chantier [« L'API de blending »](#piste-lapi-de-blending-des-calques-au-petit-oignon) (route vers v1.0-stable) : `blend.set_alpha` / `blend.set_fade` → propriétés, décidé avec le `mixer` qui pose la même question pour le son |
| Scene `blend_*_role` | s.o. | repoussé | même chantier [« L'API de blending »](#piste-lapi-de-blending-des-calques-au-petit-oignon) |
| Scene `backdrop_color` | s.o. | repoussé | même chantier [« L'API de blending »](#piste-lapi-de-blending-des-calques-au-petit-oignon) : la porte est voulue, lecture ET écriture, sans nouveau type (un `vec3` ou un entier RGB555, à trancher là-bas) |
| Scene `transition_kind/frames` | s.o. | repoussé | chevauche l'API de blending (la transition possède les registres de blending) : même chantier [« L'API de blending »](#piste-lapi-de-blending-des-calques-au-petit-oignon) |
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
en investiguant `window._on_scene_selected` ([window.py:1128](../../editor/window.py:1128)) :

1. **Corrigé (2026-09-16).** `AssetsFinderPanel.refresh()` reconstruisait les 3 arbres (Scenes,
   Prefabs, Scripts) à chaque clic, alors que rien n'y change quand on change simplement de scène
   active. Remplacé par un simple surlignage de la scène active, sans repeuplement,
   `highlight_active_scene` ([assets_finder_panel.py](../../editor/ui/scene_manager/assets_finder_panel.py)),
   posé sur `AssetFinder.highlight_selection` déjà existant.
2. **Pas de bug.** `_refresh_diagnostics` → `validate_project` → `project.load_all_resources()`
   ([validator.py:126](../../editor/core/validator.py:126)) est déjà gardé par
   `_deferred_resource_collections` ([project.py:339](../../editor/core/project.py:339)) : le coût réel
   (stat + hash de tout le catalogue) n'est payé qu'à la toute première scène ouverte d'une
   session ; ensuite chaque `load_*` est un test d'ensemble vide, donc quasi gratuit.
3. **Ce chantier.** `SceneEditor.load_project` ([scene_canvas.py:721](../../editor/ui/scene_manager/scene_canvas.py:721))
   reconstruit le canvas ENTIER à chaque sélection, y compris en revenant sur une scène déjà
   visitée dans la même session, où rien n'a changé :
   - `compose_frame_image` ([sprite_compose.py:15](../../editor/core/sprite_compose.py:15)) rouvre et
     redécode depuis le disque le PNG source du sprite pour CHAQUE acteur, à CHAQUE visite,
     aucun cache, même quand le fichier n'a pas bougé depuis la visite précédente.
   - `bg_pixmap` / `BgLayerRaster.render` ([canvas_raster.py:171](../../editor/ui/scene_manager/canvas/canvas_raster.py:171))
     recompose le rendu tuile par tuile du fond à chaque visite. Le tileset lui-même est déjà en
     mémoire (`BackgroundAsset`, pas de disque ici), mais le raster complet est refait à zéro.
   - `_reload_ui_regions` / `set_ui_regions` ([canvas_scene.py:440](../../editor/ui/scene_manager/canvas/canvas_scene.py:440))
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
   ([window.py:878](../../editor/window.py:878), [window.py:1135](../../editor/window.py:1135)). Créer ou
   déplacer un groupe est une action *projet*, pas *scène* : on créerait un groupe, on cliquerait
   une autre scène dans le viewer → `_history.clear()` → l'entrée « annuler le groupe » aurait déjà
   disparu. Un undo qui ne survit pas au prochain clic de scène est pire que pas d'undo.
2. **Ces sidecars ne changent ni le jeu, ni le build, ni le JSON de gameplay** (cf. en-tête de
   [asset_folder_store.py](../../editor/core/asset_folder_store.py)) : un dossier ne fait que choisir le
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
  parent ([asset_folder_store.py](../../editor/core/asset_folder_store.py)) : l'undo doit restaurer
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

Née dans le chantier « La struct `Actor` allégée » ([archive](../../changelog/archives/actor-struct-lightening.md)), livré à côté de cette piste : elle reste **non verrouillée**, code non commencé.

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
- Ne touche pas aux noms d'acteurs (déjà locaux, cf. [changelog/archives/actor-scene-local.md](../../changelog/archives/actor-scene-local.md)).

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

## Assets et disque : ce qui reste après la livraison de la 0.3

La 0.3 est **livrée** ; sa discussion complète est dans [l'archive](../../changelog/archives/assets-and-disk.md). Ne restent ici que
les fils ouverts, qui ne bloquent rien :

- **Les références par id** : sorties de la 0.3, suivies avec [le stockage des références](#le-stockage-des-références-nom-ou-id-dans-les-cellules).
  Le sidecar porte déjà l'id ; ce sont les données (scènes, cellules) qui citent encore le nom.
- **`tools/create_build_benchmark.py`** écrit encore dans `project/scenes` et à plat (ancienne disposition).
- **Imports et dépôts** : l'encodage d'un sprite ou d'un fond remplacé
  n'est pas dans l'historique (annuler rend le PNG, le rechargement refait l'encodage) ; un dossier déposé garde son suffixe sans question ;
  une seule réponse vaut pour tout un lot de collisions ; aucun test de l'interface de la boîte de collision.
- **Disk** : un double-clic dans la vue du bas ne sélectionne pas le dossier dans l'arbre ; les dossiers vides des projets de démo, créés
  avant que `assets/` devienne vierge.
- **Dossiers virtuels des autres finders** : seules les familles scènes, SFX, musiques et jingles en ont (`folder_family` dans
  `asset_kinds.py`, relu le 2026-10-23) ; sprites, fonds, palettes, tables, polices et prefabs restent à plat.
- **Vérification à la main** de l'ensemble de l'onglet Disk sur un projet réel (déplacements, collisions, annulation).

---

## Fonds : ce qui reste après la livraison de la 0.5

La 0.5 est **livrée** ; sa discussion complète est dans [l'archive](../../changelog/archives/backgrounds.md). Ne restent ici que
les fils encore ouverts. **Aucun n'est rattaché à un chantier important** pour l'instant : ils sont classés à part.

### Comparer la source et la version compressée (non classé)

Le « compress view » : une barre verticale posée sur le plan de travail, la source d'un côté, la version compressée de l'autre,
à la même grille. Elle rend possibles la carte d'écart par tuile et une fidélité globale (voir « Comparer à l'image source »
dans [l'archive](../../changelog/archives/backgrounds.md#la-compression-dun-fond-se-joue-elle-ne-sattend-pas)). Aucun code de
comparaison n'existe encore dans `ui/background_editor/`. Sur une photo le coût impose de calculer sur une version réduite.

### Autres fils ouverts

Tous viennent de l'archive, où chacun est décrit avec son contexte ; rien n'y est verrouillé sauf mention.

- **Trous dans une grande image, sans solution.** L'index de tuile est codé sur 10 bits (`pack_se`) et tronqué en silence
  au-delà de 1023 ; `merge_tiles` ne fait rien au-delà de `MAX_TILES = 6000`. Une tuile retirée doit être remplacée par une
  tuile visuellement proche, jamais devenir un trou.
- **La limite réelle du canvas tuilé** (cartes de tuiles, streaming) : à lire et à poser à la place du garde-fou de 4096 px.
- **Un bitmap plus grand que 240×160** (étude du 2026-10-16, étapes A à D, rien de codé). L'étape C rouvre la décision « un
  bitmap a un canvas fixe de 240×160 ».
- **Le service d'encodage** : le processus séparé pour les grandes images (phase 5) ; couper `encode_background` en filtre de
  compression puis encodage ; les caches par étage ; l'aperçu dégradé rapide pour une photo.
- **La compression, frictions non reprises** : diagnostics actionnables, réglage par objectif, la falaise du chemin
  « indexé direct », le bouton « Analyser » masqué (à revérifier dans le code avant de rouvrir).
- **La tranche bitmap de la compression** (son propre panneau) : pas commencée.
- **Les pistes de l'écran Fond** : cache de l'aperçu par étape, aperçu avec les calques, mémoire du cache, relink des autres
  familles, trames ordonnées sans réduction globale, « Save as PNG » hors du 4bpp tuilé, filtres créatifs.
- **Les sprites** partagent le mécanisme de sous-palettes (`SubPaletteAssetMixin`) et gardent des copies : non touchés.
- **Données de démo** : la lecture à plat d'un sidecar d'avant les blocs se retire quand les projets ont été resauvegardés ;
  `tools/create_build_benchmark.py` écrit encore à plat.

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
   des sections avec UNE plage implicite, pas la liste complète (un jingle n'a pas de sections, cf. [l'asset `.music`](../../changelog/archives/music-asset.md)).

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

## Piste (le singleton `mixer`)

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

## Piste (nommer l'accès à un sous-objet de l'instance)

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

## Piste (la chaîne `if/elseif` sur une constante devient un `switch` C)

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

## Piste (l'atelier Texte réuni, écrire et voir dans un même écran, **ABANDONNÉ**)

**Remplacé le 2026-10-10** par [L'écran Texte n'édite et ne range que du contenu](../../changelog/archives/text-and-data.md#lécran-texte-nédite-et-ne-range-que-du-contenu-interface--livré-en-partie). Ce chantier voulait faire du rendu GBA la surface d'édition (projection source ↔ affichage, vue balisage en police moteur) ; on retire au contraire l'aperçu de l'écran et le contenu s'édite dans la table. Sa décision verrouillée du 2026-09-19 est caduque.

## Piste (la caméra change de cible en jeu, avec une transition)

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-29).** Né de la tranche 2 de
« L'API dit tout ce que l'inspecteur règle » : `Camera.mode` et `Camera.follow_target` n'ont pas de porte Lua, et une
lecture seule ne suffirait pas, l'auteur doit pouvoir CHANGER de cible en jeu. Aujourd'hui le suivi est un
`switch(g_cam_active)` dont la cible est une constante par caméra ; changer de cible en cours de scène, c'est de la
RAM (mode, index de cible) lue par le suivi, et surtout un **système de transition** : passer de l'acteur A à l'acteur B
d'un coup est une téléportation de cadre. Le chantier pose les deux ensemble (état modifiable + interpolation de la
caméra vers la nouvelle cible), pour ne pas ouvrir une porte dont la première utilisation est un saut. Rien n'est
tranché ni codé.

## Piste (l'API de blending des calques, au petit oignon)

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-29).** Né de la tranche 2 de
« L'API dit tout ce que l'inspecteur règle » : quatre champs d'inspecteur touchent au blending, et chacun mérite d'être pensé avec les autres plutôt que réglé à la volée. Rien n'est tranché ni codé. À rassembler :

- les poids `blend_eva/evb/evy` : aujourd'hui `blend.set_alpha` / `blend.set_fade` s'écrivent, aucune lecture ; elles deviennent des propriétés (état → propriété), **décidé avec le `mixer`** qui pose la même question pour le son ;
- les rôles (dessus / dessous) des calques, de l'OBJ et du fond de teinte : écriture indexée existante (`set_layer/obj/backdrop`), lecture absente ;
- `backdrop_color` : une porte en lecture ET écriture, sans nouveau type, un `vec3` (r, g, b) ou un entier RGB555 ; c'est ici qu'on choisit ;
- la transition de scène (`transition_kind`, `transition_frames`) : elle possède les registres de blending pendant sa durée (`transition_begin/fade/end`), donc elle ne se règle pas sans que l'API de blending soit posée.

## Piste (une seule primitive pour retenir et rendre des cases de tilemap)

**Ouverte le 2026-10-23, réflexion, rien de verrouillé, code non commencé.** Née de deux correctifs livrés le même jour dans
`gba_engine.h`, qui ont réinventé la même chose côté moteur :

- **Une image BG masquée ou déplacée rend ce qu'elle recouvrait** (`ui_image_snapshot_bg` / `ui_image_clear_bg`) : à sa pose, elle
  retient les entrées de tilemap de ses cases (jusqu'à 64 par image, un tableau par image, 2 Ko) et les restaure.
- **Le fond d'un conteneur se masque avec `hide()` et revient avec `show()`** (`ui_fill_rect_tracked` / `ui_fill_map_tracked`) : le
  moteur retient le rectangle et de quoi le REDESSINER (une tuile unie, ou une carte d'entrées), l'efface quand le conteneur est
  caché et le repose quand il revient. Deux passes autour du texte, parce que texte et fond se partagent les mêmes cases.

Les deux gèrent le même fait : **des cases de tilemap qui ont un état à rendre plus tard.** Elles le gèrent chacune à leur manière, et elles
se croisent déjà (une image dans un conteneur caché ne doit pas reposer le fond ; `ui_fill_hidden_at` existe pour cela).

**L'idée.** Un seul mécanisme moteur, « retenir un rectangle de cases, le rendre », dont le fond de conteneur et l'image deviennent deux
clients, et que l'API de scripts exposerait telle quelle (`layer:get(n):save(tx, ty, w, h)`, `restore`, `release`). Le C écrit et
éprouvé une fois, par une sonde native, sert alors trois usages : l'interface, la sauvegarde d'une zone par un script (une fenêtre qui
se ferme, un terrain destructible, un effet à retirer), et le retour au dessous d'un élément masqué. Le gain est technique : moins de
chemins qui écrivent dans la même tilemap, donc moins de cas où ils se marchent dessus.

**Ce qui est utile et ce qui ne l'est pas dans l'unification.** Le fond d'un conteneur est un cas particulier : on le REDESSINE à partir
de sa source (couleur, carte), on n'en garde pas une copie des cases. Retenir une copie des cases est ce que fait l'image, et ce que ferait
l'API de scripts. À instruire : le fond est-il un client qui retient une copie (plus simple, mais une copie périmée si le fond a changé
entre-temps), ou garde-t-il son redessin à partir de la source (ce qui existe, et ne coûte aucune mémoire de copie) ?

**Points à trancher.**

- *Mémoire* : un pool fixe de réservations. Combien, et de quelle taille ? Valeur de départ envisagée : 4 réservations d'au plus 64 cases (environ
  512 octets). Les images ont déjà 2 Ko ; si elles deviennent des clients, un seul pool devrait remplacer leur tableau.
- *Coordonnées* : en cases de la tilemap du calque, pas de l'écran, donc indépendantes du défilement.
- *Cartes streamées* : quand le fond défile par morceaux, le moteur réécrit la tilemap ; une copie faite avant un défilement est périmée.
  À interdire (valeur `nil`, ou refus à la compilation) ou à dire clairement.
- *Ordre* : texte et fond se partagent des cases ; l'ordre « le fond revient avant le texte, part après lui » doit rester vrai pour tout client.
- *API de scripts* : une réservation est un entier (le sous-ensemble Lua n'a pas de tables) ; `save` rend `nil` si le pool est plein. Pas d'objet
  « sélection » : un rectangle et une poignée suffisent. Backstage n'est pas un outil de dessin : c'est une primitive d'exécution, pas une peinture de tuiles.

**Ordre de travail envisagé.** D'abord confirmer sur une ROM jouée que `hide()` / `show()` d'un conteneur et le masquage d'une image se
comportent à l'écran comme les sondes natives le disent. Ensuite seulement, une seule primitive (avec sa sonde) sous les deux clients
existants, puis l'API de scripts.

## Piste (le rôle des collisions contre le mode de résolution physique)

**Premier pas livré le 2026-10-24 : `CollisionBoxComponent.blocks_actors`** (jamais par défaut ; case « Blocks actors » de l'éditeur de boîte ; `codegen/runtime_codegen/block_gen.py`). Un acteur actif en mouvement (vitesse non nulle) qui a une box `solid` est repoussé hors de toute box `blocks_actors` d'un autre acteur, sur l'axe de plus faible pénétration (l'horizontal en cas d'égalité), AVANT la résolution contre la carte (les murs ont le dernier mot) ; la matrice de collision filtre au build ; les pools sont gérés. Le champ est un réglage à part de `solid`, parce que changer le sens de `solid` aurait modifié tous les projets existants (Pong : balle et raquettes ont des boîtes solid par défaut). **Limites assumées** : la position seule est corrigée (ni vitesse ni `grounded`, donc pensé pour une vue de dessus : un platformer qui pose le joueur sur un bloqueur doit remettre sa gravité à zéro lui-même) ; un mobile qui en pousse un autre n'est pas géré ; `blocks_actors` s'écrit sur chaque boîte au prochain enregistrement (la sérialisation des composants est générique). **La boîte propre d'un Interactive en `facing` bloque et est solid par défaut** (un obstacle qu'on vise : coffre, panneau), celle d'un `hover` ni l'un ni l'autre (une plaque se recouvre) ; la table de blocage lit le tag de la boîte (`Interactive` compris), donc la case Player × Interactive de la matrice décide si le coffre arrête le joueur. Reste ouvert, ci-dessous : la taxonomie Solid / Overlap / RigidBody / StaticBody / CharacterBody.

**Suite prévue : le blocage en plateforme (décidé le 2026-10-24 : on le traite avec la démo de plateforme, pas avant).** Aujourd'hui le blocage ne corrige que la position : ni la vitesse ni `grounded`, donc un joueur posé sur un bloqueur doit remettre sa gravité à zéro lui-même, ce que seule une vue de dessus supporte. Conseil retenu : en attendant, faire les sols et les murs d'un platformer avec la carte de collision (elle porte déjà `grounded`, les pentes et la vitesse) et réserver « Blocks actors » aux obstacles de vue de dessus. Quand la démo de plateforme a besoin d'un acteur sur lequel on se pose (caisse, plateforme mobile), une tranche à part, dans cet ordre : (1) **fusionner le blocage dans la passe de `resolve_actor_tiles`** : ce résolveur remet `grounded` à 0 en début de passe et saute tout acteur dont la vitesse est nulle, donc un blocage posé avant lui verrait son `grounded` effacé, et un blocage qui annule la vitesse ferait sauter la résolution des murs ; (2) mettre à 0 la vitesse sur l'axe repoussé et poser `grounded` quand on est repoussé vers le haut, comme le fait la carte ; (3) décider de ce qu'une plateforme mobile emporte avec elle (le porteur suit-il ?) et d'un sol traversable par le bas, avec la taxonomie ci-dessous ; (4) vérifier sur le projet Platformer (`Project Demo/Platformer`, à ne pas modifier sans l'accord de l'auteur), avec un test natif de chaque cas (chute sur une caisse, glissement le long d'un mur, saut depuis une caisse).


**Ouverte le 2026-10-23, réflexion, rien de verrouillé, code non commencé.** Née de la conception d'`interactive` : on a découvert
en relisant le code que `CollisionBoxComponent.solid` ne repousse **aucun acteur**. Il décide d'une seule chose : la box est-elle
arrêtée par la CARTE de collision (murs, pentes, plafonds) ? Les collisions acteur contre acteur ne le consultent pas, elles
ne font que signaler le recouvrement. Un coffre ou un PNJ « solide » traverse donc le joueur, et une box `solid` posée contre un
mur est repoussée par les tuiles.

**À clarifier : séparer le rôle d'une box de la façon dont le moteur résout son contact.**

- **Le rôle** : ce que la box *est* pour le jeu (corps, zone d'interaction, boîte de coup, capteur). Aujourd'hui porté par le tag.
- **Le mode de résolution** : ce que le moteur *fait* au contact. Aujourd'hui deux valeurs seulement, et mal nommées : `solid` (la
  carte arrête la box) ou non. Pistes : **Solid** contre **Overlap** (le contact est signalé, jamais résolu), et des composants de corps
  qui portent la réponse : `RigidBody` (réactif), `StaticBody` (immobile, bloque les autres), `CharacterBody` (se déplace, se bloque,
  ne réagit pas à l'impulsion).

**Lien avec l'existant.** La section [Physique et collision](#physique-et-collision) (« Plus tard », jamais avant la v2.0) prévoit déjà
trois types, `rigidbody` / `actor` / `solid`, en remplacement du booléen. Cette piste est la même question vue du côté des composants :
type de box ou composant de corps ? À trancher ensemble, pas deux fois.

**Pourquoi ça ne peut pas attendre la v2.0.** `interactive` en dépend : tant qu'aucun corps ne bloque le joueur, la zone d'interaction
se pose sur la box de l'objet sans marge, et le recouvrement est strict (deux boxes seulement adjacentes ne se recouvrent pas). Le jour
où un `StaticBody` bloquera le joueur, la zone devra dépasser de quelques pixels, sinon le joueur arrêté contre l'obstacle ne
déclenchera plus rien. À garder en tête quand la taxonomie sera tranchée.

**Ouvert.** Le booléen `solid` change de sens (format de composant, la maison ne migre pas) ; qui possède le mode : la box ou
l'acteur ; ce qu'un script lit (`collision_box.solid` aujourd'hui) devient quoi ; la boîte implicite d'`interactive` prend quel mode
(`Overlap`, a priori).

## Piste (des cartes de valeurs peintes par l'auteur, lues à l'exécution)

**Ouverte le 2026-10-23, réflexion, rien de verrouillé, code non commencé.** Demandée par l'auteur : pouvoir peindre des entiers dans une
carte réutilisable à l'exécution, pour faire des opérations ou du gameplay (zones d'eau ou de danger, coût de déplacement d'un terrain,
points d'apparition, ce qu'un script lit pour décider).

**Ce n'est pas la peinture de tuiles écartée.** La règle « Backstage n'est pas un outil de dessin » refuse de peindre des TUILES GRAPHIQUES (un
éditeur de carte, un tileset de premier rang). Ici on peint des VALEURS : une grille de données, qui ne dessine rien à l'écran et que
le moteur ne montre pas. C'est le métier de l'écran Données (une table que le jeu lit), posé sur une grille spatiale. La frontière est à
tenir dans les deux sens : la carte de valeurs n'a aucun rendu de jeu, et l'éditeur ne gagne ni tileset ni pinceau graphique.

**Le précédent existe déjà : la carte de collision.** Une grille d'entiers par scène (`Scene.collision_map`, un type de case par tuile de 8 px : vide,
plein, pentes), peinte avec un pinceau 8 ou 16 px, un trait de pente et l'effacement, annulable (`CollisionPaintCmd`), affichée en surcouche, lue
au runtime (`collision_box.get_tile`). La piste revient à **généraliser cette carte** : plusieurs cartes nommées par scène, chacune avec ses valeurs
nommées (une légende : valeur, nom, couleur d'affichage), la collision restant la première carte, intégrée.

**Ce que l'auteur gagnerait.** Un script lit `terrain:get("cout", tx, ty)` ou compare à une valeur nommée (`TERRAIN_EAU`), au lieu de recopier une table
de coordonnées à la main. La démo tactique en a besoin (coût de déplacement par terrain, zones interdites). Et rien de plus : pas de
cases animées, pas de couches graphiques.

**Points à trancher.**

- *Une carte ou plusieurs* : généraliser `collision_map` (une carte « collision » plus N cartes nommées) ou ajouter un second mécanisme à côté ? La
  collision a des pentes, des tags et un rendu de pinceau propres : à ne pas casser. Je penche pour une structure commune, la collision en étant un cas riche.
- *Largeur d'une valeur* : un octet par case suffit-il (256 valeurs nommées au plus) ? Quatre bits pour une carte très grande ?
- *Résolution* : la tuile de 8 px, ou une cellule plus grosse (16 ou 32 px) pour une carte de gameplay moins coûteuse en ROM ?
- *Coût en ROM* : `largeur x hauteur` octets par carte et par scène. Une grande carte streamée (plusieurs milliers de cases) pèse ; une compression
  par plages (`RLE`) vaut d'être chiffrée avant de coder.
- *Lecture seule ou écriture* : lire une carte est gratuit (elle reste en ROM). L'écrire au jeu (un terrain qui change, une zone qui se vide) demande une
  copie en RAM, donc un pool à dimensionner, comme pour la piste [une seule primitive](#piste-une-seule-primitive-pour-retenir-et-rendre-des-cases-de-tilemap).
- *Lien avec la scène* : coordonnées en cases ; une aide pixels vers case (`terrain:at(x, y)`) évite que chaque script refasse la division.
- *Éditeur* : réutiliser la surcouche, le pinceau, le remplissage et l'annulation de la collision, avec une légende de valeurs en barre latérale et un
  interrupteur d'affichage par carte. Les valeurs nommées sont aussi des constantes Lua (`MAP_VALUE_*`), générées comme les autres noms du projet.
- *Diagnostics* : une carte plus petite que la scène, une valeur sans nom, une carte jamais lue par un script (un avertissement, pas un refus).

**Ordre de travail envisagé.** Chiffrer d'abord le coût ROM sur la démo tactique et un niveau plus grand, trancher « une carte ou plusieurs » avec ce que la
collision impose, puis une lecture seule (cartes nommées, valeurs nommées, `get` et `at`), et seulement ensuite l'écriture en RAM, qui dépend de la
piste sur les cases de tilemap.

## Piste (l'allocateur de ressources matérielles)

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

### Le problème

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

### Décisions verrouillées

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

### Ce qui est fait (2026-08-25) (les windows)

1. **Le principe est écrit** (cf. ARCHITECTURE), pour que rien de neuf ne lie un concept de
   haut niveau à un slot matériel.
2. **`WindowSlot.region` n'est plus un index matériel côté auteur**, renommé `.name`, résolu
   par `codegen/window_alloc.py`.
3. **La rupture assumée sur l'API Lua est faite pour les windows** :
   `window.set`/`window.show`/`window.is_visible` adressent maintenant par nom
   (`DOMAIN_WIN_REGION`), comme `window.set_layer` le faisait déjà, un seul schéma, plus de
   numéro matériel brut atteignable depuis un script.

### Ouvert

- Jusqu'où va l'allocateur de frame (OAM, DMA, matrices affines). Un arbitrage par frame est
  un vrai coût CPU ; il se décide sur un cas mesuré, pas à l'avance, les windows n'en avaient
  pas besoin (résolubles au build, cf. ARCHITECTURE.md « Deux allocateurs, pas un »).
- L'assignation matérielle « visible dans un panneau avancé, et forçable » (décision
  verrouillée ci-dessus) n'est pas construite pour les windows, l'auteur voit le budget
  (N/2) mais pas quelle intention a reçu quel rang. À rouvrir si un projet réel en a besoin
  pour déboguer un recouvrement.

### Le cas mesuré de l'allocateur de frame (l'OAM dynamique (2026-09-10))

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

## Piste (le Sprite, source visuelle unique)

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

### Piste (2026-10-23) : séparer l'outil Inpainting et l'outil Painting, et nommer « Color mapping » l'algorithme

**Constat.** La barre d'outils de l'éditeur de fonds mélange deux gestes : le pinceau porte le choix du mode (Inpaint ou
Paint), et le seau et le rectangle suivent ce mode sans le proposer. La gomme efface les deux calques.

**Livré le 2026-10-23 (non vérifié à l'écran, tests ciblés de la barre d'outils verts).** Deux outils, chacun avec ses sous-outils :

- **Inpainting** (remplacement de palette) : pinceau, rectangle, seau, et l'option « Color mapping » dans son menu.
- **Painting** (tuiles) : pinceau, rectangle, seau.
- La gomme reste un outil à part (elle purge les deux calques) ; « select » ne change pas.

Chaque bouton ouvre son menu et montre l'icône de son dernier sous-outil ; le mode (Inpainting ou Painting) suit le
bouton choisi, la couche logique (`MODE_INPAINT` / `MODE_PAINT`, les outils `brush`, `rect`, `fill`) n'a pas bougé.
`BgInpaintToolbar` : `_FAMILIES`, `_SUBTOOLS`, `_show_family_menu`.

**Ce qu'est le « palette mapping ».** Pas un outil : l'algorithme qui décide comment les couleurs d'une palette sont
redistribuées sur les pixels d'un fond portant une autre palette (palette swap). Cinq modes : index directs, couleurs
perçues les plus proches, luminosité préservée, correspondance optimale, rampe teinte/saturation
(`COLOR_MAPPING_MODES`, `_color_mapping` dans `core/models/background.py`). **Livré le 2026-10-23** : renommé « Color
mapping » (FR « Mappage des couleurs »), le mot « palette » étant déjà pris par les banques et leur assignation. Les
identifiants suivent (`BackgroundAsset.color_mapping`, `set_color_mapping`, `bginp.color_mapping_*`). La clé du sidecar
passe de `inpaint_mode` à `color_mapping` ; la lecture accepte encore l'ancienne, aucun fond existant n'a été réécrit.

**Ouvert.**

- L'inpainting de SCÈNE (palette par tuile, par calque) ne fait que réassigner la banque (`tile_palette_overrides`), soit
  le mode « direct ». Offrir les quatre autres modes à ce niveau demanderait un réglage par `BackgroundLayer`, un rendu
  du canvas de scène qui recolore les tuiles, et des tuiles variantes au build (`rom_build.py`, `grit_conversion.py`) avec
  leur coût de VRAM. **Abandonné pour l'instant (2026-10-23)** ; à rouvrir avec le point suivant.
- Le runtime : l'auteur envisage de retrouver l'algorithme dans la ROM (recolorer un fond à l'exécution). Rien n'est
  écrit côté C ; à instruire avant de décider si l'option y vit.
- Faut-il écrire cette conception dans le détail (fichiers annoncés, ordre) avant de toucher à la barre d'outils ?

## Piste (API « color swap » : recolorer à l'exécution, avec les options de Color mapping)

### D'où vient la question (2026-10-23)

L'éditeur sait déjà faire un palette swap sur un fond (l'outil Inpainting) avec un algorithme au choix, le
« Color mapping ». Ce calcul vit uniquement dans l'éditeur : il sort des tuiles variantes au build. Rien n'existe
côté C ni côté script : un jeu ne peut pas demander « recolore ce fond avec cette palette, de cette façon » pendant
qu'il tourne.

### Ce qui existe

- Les cinq algorithmes : index directs, couleurs perçues les plus proches, luminosité préservée, correspondance
  optimale, rampe teinte/saturation (`COLOR_MAPPING_MODES`, `_color_mapping` dans `core/models/background.py`).
- Le réglage est porté par le fond (`BackgroundAsset.color_mapping`, clé `color_mapping` du sidecar).
- À l'échelle d'une scène, l'inpainting ne réassigne que la banque de palette d'une tuile (`tile_palette_overrides`) :
  c'est le mode « direct ». Les quatre autres modes n'y sont pas offerts (piste abandonnée le 2026-10-23, voir
  [la séparation Inpainting / Painting](#piste-2026-10-23--séparer-loutil-inpainting-et-loutil-painting-et-nommer--color-mapping--lalgorithme)).

### Le principe (décidé le 2026-10-23)

**L'API C, quand elle sera définie, est le modèle à suivre côté outils.** Comme toujours, l'éditeur reflète le modèle
du runtime, pas l'inverse : on ne fige pas une option d'éditeur en espérant la brancher plus tard. Tant que l'API n'est
pas dessinée, l'éditeur garde les cinq options telles quelles ; une fois dessinée, l'éditeur s'aligne sur son vocabulaire
(noms, réglages, bornes), y compris pour le menu « Color mapping » et le sidecar.

### À tester (envie de l'auteur, 2026-10-23)

Deux familles d'algorithmes, à essayer côté éditeur avant de décider ce que le runtime en garde.

- **Perceptuels (déjà là).** Les modes « couleurs perçues les plus proches », « correspondance optimale » et « rampe
  teinte/saturation » travaillent en OKLab (distance perceptuelle). C'est ce qu'on veut pour un swap qui paraît juste.
  Le calcul se fait au build : l'éditeur peut se permettre OKLab, le GBA n'a pas à le jouer.
- **Old school, qui dégradent volontairement.** Pas pour bien recolorer, pour obtenir un rendu daté :
  - distance RGB brute (la correspondance « bête », qui associe des couleurs qui paraissent étrangères) ;
  - quantification des canaux (3 ou 4 bits par canal avant l'association : aplats et bandes visibles) ;
  - luminance seule (tout passe en gris, puis dans la rampe de la palette cible : l'effet d'un écran monochrome teinté) ;
  - index décalés (une rotation d'index plutôt qu'une association de couleurs : l'effet glitch).

Pour essayer : un mode de plus dans `COLOR_MAPPING_MODES` (`core/models/background.py`) avec son libellé
(`bginp.color_mapping_*`) ; le menu de l'Inpainting le propose aussitôt, rien d'autre à changer. À comparer d'abord
à l'œil sur un fond réel, puis à trancher : lesquels méritent d'exister côté runtime (voir « Ouvert »).

### Ouvert

- Précalculé au build (tuiles et palettes variantes dans la ROM, le jeu choisit laquelle afficher) ou calculé à
  l'exécution (le GBA n'a pas d'OKLab : un algorithme coûteux ne s'y joue pas tel quel) ?
- Quels algorithmes survivent côté runtime : « direct » est gratuit ; les autres demandent une table d'association
  par couple de palettes, calculable au build.
- Un fond seulement, ou aussi les sprites ? Les deux consomment des banques de palette, pas les mêmes (OBJ PAL, BG PAL).
- Le coût : VRAM des tuiles variantes, ROM des tables d'association, cycles pour appliquer un swap.
- La forme dans `runtime_api.h` et en Lua : l'appel, ses arguments (cible, palette, algorithme), ce qu'il rend, et son
  interaction avec le garde-fou VRAM.
- Où se règle le choix dans l'éditeur : par fond (comme aujourd'hui), par calque de scène, ou à l'appel dans le script.

### Ce que ça ne fait pas

Aucun code, aucune décision d'implémentation. Cette entrée garde la question et le principe ; elle se rouvre quand
l'auteur décide de dessiner l'API.

## Piste (la Liste d'interface est un contrôleur, pas une collection)

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

### Décisions verrouillées

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

### Ce que le chantier implique

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

### Ouvert

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

## Piste (la destruction des éléments d'interface)

**D'où ça vient (2026-09-27).** En discutant du critère 4 de v0.16 (« unifier absent par type »),
constat : un élément d'interface, un calque ou une fenêtre sont **statiques par construction**,
`destroy()` n'existe QUE pour `actor`/`sfx` dans le catalogue ([api.py](../../editor/scripting/api.py)),
posé une fois pour toutes à l'authoring, sans commande de script pour le faire disparaître. C'est
ce qui rend `interface:get("Menu") ~= nil` toujours vrai, et c'est ce qui permettait de classer ces
types comme « jamais absents » sans exception à traiter.

**La piste, non développée.** Si un projet réel demande un jour de détruire dynamiquement un
élément d'interface (un menu généré au runtime, une fenêtre jetable) plutôt que de se contenter de
`hide()`, ça romprait l'hypothèse « statique = jamais nil » du critère 4 : ces types rejoindraient
la catégorie des références de pool, avec tout ce que ça implique (`nil` testable, retrait du
`REF_TYPE_TABLE.nullable=False`, etc.). **Aucune décision prise, aucun besoin démontré**, à
rouvrir si un projet en butte contre la limite actuelle (`hide()` seul, l'élément reste en mémoire).

## Piste (les calques par nom)

**D'où ça vient (v0.16).** `layer:get(n)` adresse un fond par son NUMÉRO (0 à 3, borné par le mode
vidéo de la scène), cohérent avec la provenance « le matériel, numéroté par le matériel » de la
règle de construction. Question restée ouverte pendant le chantier : offrir aussi `layer:get("Fond")`
par un nom authoré, comme pour un élément d'interface.

**Pourquoi ce n'est pas fait maintenant.** Recommandation retenue à l'époque : attendre un besoin
réel avant d'ajouter une seconde façon d'adresser la même chose, deux provenances pour un fond
recréerait exactement le doublon que la grammaire de l'API refuse ailleurs. **Aucune décision
prise, aucun besoin démontré.**

---

## Le pool ne dépend plus de l'OAM

### D'où vient la question (2026-10-20)

Un build échouait sur `Turret.lua:17: implicit declaration of function 'spawn_Scene_02_Bullet'`. La scène spawnait un prefab sans
en avoir déclaré le pool : le build n'émet alors ni `spawn_<Scène>_<Prefab>` ni son unité C, et l'erreur ne sortait que du
compilateur C. Relire la v0.17 a montré que l'éditeur devait *proposer* le pool d'après les scripts (« proposer, pas imposer »),
et que cette proposition n'avait jamais été livrée : `Scene.prefab_pools` n'avait plus aucun écran qui l'écrive.

En y regardant, **la taille d'un pool servait à quatre choses sans rapport** : les slots d'acteurs de `g_actors[]`, l'état de script par
instance (EWRAM), les entrées OAM et les matrices affines. Depuis que l'acteur ne réserve plus d'entrée OAM par défaut, le
plafond de 128 répond à une question d'**affichage**, pas à un plafond d'acteurs ou de prefabs. L'auteur a demandé de découpler
les deux premiers de l'allocateur OAM.

### Décisions (2026-10-20, de l'auteur)

- **Un prefab spawné obtient un pool tout seul** : 8 instances par défaut (`POOL_DEFAULT_INSTANCES`), ou la valeur déclarée dans
  `Scene.prefab_pools`, qui sert à l'ajuster. « Spawné » se lit dans les scripts compilés pour la scène, y compris les spawns en
  chaîne (un prefab poolé qui en spawne un autre).
- **La taille du pool ne dépend plus de l'OAM.** Elle dit combien d'instances *vivent*, pas combien *s'affichent*.
- **Priorité des entrées OAM** : acteurs posés (prefabs placés compris, connus au build) et interface d'abord ; les instances de pool
  ensuite, « vivantes mais qui peuvent ne pas s'afficher correctement ».
- **Le plafond de 128 et celui des 32 matrices affines avertissent**, ils ne bloquent pas. Le compteur de la barre d'état suffit à
  l'auteur : aucun affichage de plus dans l'inspecteur.

### Livré le 2026-10-20

- **Pool automatique** : `scene_oam_layout` (`oam_alloc.py`) alloue `POOL_DEFAULT_INSTANCES` à tout prefab que
  `scripting.refactor.scene_spawned_prefabs` voit spawné par la scène ; un pool déclaré garde la main. Lecture des scripts mise en
  cache par fichier (0,47 s au premier calcul, 2 ms ensuite). `scene_pool_instances` prend maintenant `(project, scene, prefab)`
  et rend le pool effectif ; `declared_pool_instances` rend la valeur déclarée.
- **Les entrées OAM se distribuent par priorité** : interface, acteurs posés, puis instances de pool dans l'ordre du catalogue et
  des slots. Un acteur posé sans entrée a `oam_entry = -1`.
- **Une instance sans entrée vit sans s'afficher.** Les `granted` premières instances d'un pool ont leurs entrées ; les suivantes
  écrivent sur une **entrée poubelle** en fin de `g_oam_entries[]` (`OamLayout.scratch_start`, que le writer OAM ne lit jamais)
  et ne prennent aucune matrice affine. Le spawn prend le premier slot libre : les instances affichées sont celles de tête.
- **Avertissements** : `_check_actor_budget` (acteurs posés sans entrée, pool dont des instances ne s'affichent pas) et
  `_check_affine_budget` (au-delà de `AFFINE_LIMIT` = 32, les derniers sprites sont dessinés sans rotation ni échelle, et le message
  dit combien). La seule erreur qui reste : l'interface seule dépasse 128, qu'aucune dégradation ne sauve.
- **La barre d'état montre la demande** (`OamLayout.requested`) : « 140/128 » se voit. `scene_affine_requests` compte comme
  `compute_affine_info` (une instance sans entrée ne demande pas de matrice).
- **Code mort retiré** : `codegen/actor_budget.py` (seul `prefab_pool_instances` survit, dans `oam_alloc.py`), `Scene.actor_slots`
  (champ, sérialisation, clé du générateur de benchmark), `scene_actor_slots`, `scene_actor_budget`, `scene_pool_slots`, le réexport
  de `prefab_group` dans `main_gen`, le diagnostic « spawn sans pool » devenu inatteignable.
- **Vérifié** : tests ciblés (budget, OAM, palettes, pools, affine, diagnostics) ; build complet d'une copie d'OrbitTest avec un pool
  de 140 pour 127 entrées libres, sans erreur, `g_oam_entries[129]`. **Non mesuré** : cycles sur ROM, rendu sur mGBA.

### Ce qui reste ouvert

Une liste libre d'entrées au spawn (une instance prendrait et rendrait une entrée OAM, au lieu d'un slot qui en a une ou pas) est
**optionnelle** et chiffrée dans [editor/codegen/improvement.md](../../editor/codegen/improvement.md), avec les autres pistes
d'allocateurs. `tools/diagnostic_coverage_baseline.json` n'a pas été relevé (il faut un run complet de la suite).

### Ce que ça ne fait pas

- Ne change ni la VRAM (tuiles et palettes d'un sprite sont chargées une fois) ni le comportement des acteurs posés.
- Ne retire pas `Scene.prefab_pools` : la taille du pool reste un réglage de l'auteur, mais il ne règle plus de l'OAM.
- Ne devine pas la taille utile d'un pool : 8 est un point de départ, le besoin réel dépend de la logique du jeu.

---

# Plus tard

Envisagé, ni planifié ni numéroté. Rien ici n'est promis.

## Diffuser un jeu desktop (le Backstage Player)

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

---

## Cible cartouche : le matériel embarqué façonne le langage, **JALON OUVERT**

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

### Décision verrouillée (2026-09-10) (le profil ABSORBE la sauvegarde)

La config SRAM de la v0.5 est déjà un morceau de « ce que porte la cartouche » qui vit à côté.
Le profil **l'absorbe** : une seule source de vérité, pas deux partielles. C'est un **vrai
chantier de migration**, migration du modèle de save existant et relecture du codegen de
sauvegarde, l'ancien supprimé avant de dire terminé, pas un bonus glissé dans autre chose.

### État au 2026-10-17 (aperçu des circuits dans le panneau Build)

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
[`editor/ui/common/images/cartridges/`](../../editor/ui/common/images/cartridges/README.md).
Les photos affichées proviennent de la Game Boy hardware database, sous **CC BY-SA 4.0** ;
les crédits et les images sont inclus dans la distribution. Vérification : **49 tests ciblés
passent**, rendu du dialogue contrôlé pour 4, 8 et 32 Mio. Le contrôle d'architecture global
signale encore des problèmes hors de ce chantier.

**Reste à faire :** trouver des spécimens documentés pour les ROM de 16 et 32 Mio avec la
sauvegarde correspondante ; étendre les références aux circuits avec et sans pile en
précisant son rôle (sauvegarde ou horloge). La sélection effective de SRAM / EEPROM / Flash
reste liée à la migration du profil et à l'implémentation des pilotes moteur/codegen :
ajouter une photo ne débloque pas le matériel associé. Le jalon v2.0 reste non ordonnancé.

**Préparation du catalogue (2026-10-17)** : la [matrice des cartes, composants et photos](cartridge-hardware-matrix.md)
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

**Photos récupérées (2026-10-17)** : [bibliothèque de travail des six profils](../../research/cartridges/README.md),
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

### Deux pièges matériels à encoder

- **Capteurs analogiques mutuellement exclusifs.** Une cartouche GBA porte *un* capteur
  analogique (tilt **ou** solaire), pas les deux, même ligne d'acquisition. Le profil doit
  interdire la combinaison, sinon on laisse décrire une cartouche qui n'existe pas.
- **Le tilt n'est pas un axe de pad.** Il rend un angle bruité à calibrer/filtrer. L'exposer
  comme un axe propre mentirait sur le matériel : valeur brute, et au plus un helper de
  calibration nommé.

### Le catalogue « cartouche conseillée » (trois tiers (2026-09-10))

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

### Convention de nommage (capacité d'abord, board number en note)

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

### Références externes à surveiller

- [`kicad-gamepaks`](https://github.com/djedditt/kicad-gamepaks), gabarits KiCad aux dimensions
  des cartouches officielles (la brique de fabrication du Tier 1).
- [insideGadgets](https://shop.insidegadgets.com/), cartouches à RTC / Solar / Rumble / FRAM
  (référence Tier 2, kits *build-it-yourself*).
- [GBMake](https://gbmake.com/us), fabrication indé de cartouches GB/GBA sur mesure.
- [`jojolebarjos/gba-cartridge`](https://github.com/jojolebarjos/gba-cartridge), cartouche
  FPGA (TinyFPGA BX, KiCad), frontière.
- [`konsumer/dkart`](https://github.com/konsumer/dkart), framework cartouche open hardware
  ESP32 + SD, frontière.

### Ouvert

- La découpe : ce jalon face aux autres candidats v2.0 (Backgrounds affines ci-dessous, etc.),
  et s'il se scinde par capacité.
- La forme exacte du profil dans le projet, et où il vit par rapport au reste de la config projet.
- L'ordre de livraison des capacités (RTC, rumble et les saves sont sûrs et fabricables ;
  l'ordre des capteurs analogiques dépend de la demande réelle). **Le tilt/gyro reste hors
  catalogue** : historique et réel, mais non reproductible (soudé dans la cartouche OEM, aucune
  flashcart ni repro ne l'embarque), documenté « OEM-only », jamais proposé comme cible.

## Backgrounds affines (« Mode 7 »)

Un calque affine ajoute rotation et zoom, au prix de perdre des calques réguliers ailleurs,
et il adresse sa carte différemment, donc c'est un **second chemin de génération de code**,
pas « un calque de plus ».

Volontairement décrit à haut niveau : la portée exacte dépendra de ce qui aura été appris en
construisant les fondations précédentes.

### Ce que la v2.0 n'est PAS (l'objectif V-Rally 3 n'est pas ici)

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

### Piste posée (l'abstraction « caméra » sera remise en cause ici)

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

## Physique et collision

Le moteur n'a aujourd'hui aucune physique à lui : un script décide du mouvement, la
résolution de la v0.6.3 ne fait que le corriger. Cette version est **le renversement de cette
règle**, pas son extension. C'est pour ça qu'elle est ici et pas en v0.6.4 : tant que les
fondations 2D ne sont pas finies, un moteur qui décide du mouvement à la place du script
coûterait plus qu'il ne rendrait.

### Périmètre

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

### Décisions verrouillées

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

### Ouvert

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

## Distorsion d'image

Déformer un fond pour l'eau, la chaleur, la vitesse. Rangé ici parce que c'est **la même
plomberie que le sol affine de la v2.0** : dans les deux cas on réécrit des registres de
rendu à chaque scanline, seuls les registres visés et la table de valeurs changent. Construire
l'un donne l'autre presque gratuitement. C'est la raison de leur voisinage, et l'ordre entre
les deux n'a pas d'importance.

### Décisions verrouillées

- **Sur un fond tuilé, la distorsion est PAR LIGNE, jamais par pixel.** On réécrit les
  registres de décalage du calque à chaque scanline (HDMA). C'est l'effet eau/chaleur
  classique, réel et bon marché sur ce matériel. Une flow map par pixel suppose un
  framebuffer : elle appartient donc à la v3.0, et n'a pas de sens avant.
- **Les sprites n'en font pas partie.** Un OBJ ne connaît que la transformation affine
  (rotation, échelle) ; il n'y a pas de distorsion libre à lui appliquer. Le proposer
  promettrait un rendu que le matériel ne produit pas, même règle que les modes de mélange
  *multiply* et *overlay*, absents pour cette raison.

### Ouvert

- La forme d'authoring : une courbe par calque, une table d'amplitudes, ou un script qui
  écrit la table lui-même ? Le troisième cas existe de toute façon, la question est ce que
  le déclaratif couvre.

## Rendu isométrique

**Ce n'est pas un mode de rendu**, et c'est le piège du sujet : l'isométrique reste du 2D
tuilé ordinaire, sur le même matériel, avec les mêmes calques. Ce qui change est la
**convention de projection** et, surtout, l'**ordre de dessin**. Aucune ligne du moteur 2D
n'est remplacée ; il s'en ajoute.

### Périmètre

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

### Ouvert

- Le coût du tri par frame, et son plafond. Trier N acteurs à chaque frame sur un ARM7TDMI a
  un prix ; le nombre d'entités simultanées s'en déduira, il ne se décrète pas.
- Vraie isométrique (2:1) ou projection libre ? La première se tuile proprement, la seconde
  ouvre des cas qui ne se rangent pas dans une grille.
- La hauteur. Un décor isométrique sans élévation est une grille inclinée ; avec élévation,
  le tri cesse d'être un tri sur Y. À décider avant, parce que ça change la donnée de carte.

## Sucre syntaxique Lua (+=, ++, ?:)

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

### Ce que le fork coûterait, si tranché « oui »

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

## Le second moteur de rendu

**Décidé (2026-08-13) : l'éditeur porte DEUX moteurs de rendu.** Un moteur 2D (tout ce qui
existe jusqu'à la v2.2 incluse, calques tuilés et OBJ) et un moteur 3D, qui est le sujet de
cette version.

L'ancienne v3.0 « modes bitmap » disparaît en tant que jalon et **devient le substrat de
celle-ci**. Elle n'avait jamais été un jalon pour l'auteur de jeu : personne ne veut « le
support du mode 4 », on veut ce qu'il permet. Elle reste décrite ci-dessous parce que ses
contraintes ne changent pas, mais elle ne se livre plus seule.

Ce n'est pas un mode de plus dans le moteur existant. C'est **un second moteur**, et cette
version consiste autant à réoutiller l'éditeur qu'à écrire un rasteriseur.

### Le substrat (les modes bitmap)

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

### Ce qui reste PARTAGÉ entre les deux moteurs

C'est la liste la plus importante de cette version : ce qui n'y figure pas se dédouble, et
tout ce qui se dédouble est une occasion de diverger. Elle se tient courte volontairement.

Palettes, audio, table de textes, variables et sauvegarde, scripting (le langage, le parseur,
le checker, le renommage), le pipeline de build et la construction de la ROM, la découverte
d'assets et les sidecars. **Rien de tout cela ne connaît le mode de rendu**, et rien ne doit
l'apprendre.

Les sprites (OBJ) sont partagés aussi, et c'est contre-intuitif : ils survivent au changement
de moteur puisque le matériel OBJ est le même. Mieux, c'est en 3D qu'ils portent le CIEL
(cf. « rôles inversés » ci-dessous).

### Ce qui se DÉDOUBLE, et à quel niveau

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

### L'aperçu fidèle (une source, deux compilations)

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

### Ouvert

- Le nom des deux moteurs, dans le code comme dans l'interface. Il sera lu partout et pour
  longtemps.
- Une scène peut-elle mélanger les deux ? Le matériel dit non pour les calques, mais les OBJ
  traversent, donc « pas de mélange » est faux tel quel, et « mélange libre » est faux
  aussi.
- Ce que devient un projet dont l'auteur bascule une scène d'un moteur à l'autre. Rien ne se
  convertit ; la question est ce que l'éditeur en dit.

## Le rasteriseur

Le moteur 3D proprement dit, une fois le substrat et le réoutillage de la v3.0 en place.

### L'objectif concret (V-Rally 3)

**Un jeu du niveau de V-Rally 3 sur GBA doit être constructible avec l'éditeur.** Premier
objectif de la roadmap énoncé comme un résultat visible plutôt que comme une capacité. C'est
ce qui rend sa portée décidable : une capacité s'étend indéfiniment, une cible se compare.

### Décisions verrouillées

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

### Ouvert

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

## Création de contenu au runtime

**Piste d'évolution, rien n'est tranché ni codé (notée le 2026-10-23).** Étendre l'API de Backstage
pour que le jeu crée et modifie ses propres ressources pendant son exécution, en exposant les briques
que l'éditeur utilise déjà.

- **Création d'assets au runtime.** Construire des sprites, des backgrounds, des palettes, des
  musiques, des sfx et des jingles ; définir leurs états d'animation ; assembler des ressources
  existantes et les assigner aux acteurs. Distinguer les ressources **partagées** (celles de la ROM,
  en lecture seule) des **copies modifiables**.
- **Surface de dessin.** Une surface graphique manipulable par code, utilisable par les sprites ou
  les décors : dessin au pixel, copie de zones, application de masques, pour produire des effets de
  dissolution, de dégradation ou de génération procédurale.
- **Création musicale par code.** Explorer une API pour définir des notes, des rythmes et des
  séquences, puis les jouer et les transformer pendant l'exécution.

L'ensemble ouvrirait la voie à des jeux au contenu génératif, et à des expériences audiovisuelles où
image et musique sont créées, synchronisées et transformées par le code, dans l'esprit de la
demoscene et du live coding, avec des opérations adaptées aux contraintes de la GBA.

**À instruire avant d'ouvrir** (constaté, non décidé) : la VRAM, l'OAM et la palette sont des pools
fixes, une ressource créée au runtime doit donc passer par les mêmes allocateurs que celles de la
ROM (`vram_alloc`, `palette_alloc`) et pouvoir échouer proprement ; la surface de dessin a un coût
mémoire et un coût de copie vers la VRAM à chiffrer ; la frontière « ni outil de dessin, ni
éditeur de cartes, ni tracker » vise l'**interface graphique** (elle importe images et sons, elle ne
les crée pas, voir la ROADMAP) ; elle laisse donc la porte ouverte à une **API** que le jeu appelle.
Reste à tenir cette ligne : l'éditeur ne gagne aucun outil de création, c'est le code du jeu qui crée.

---

# Repères

### Où on en est

Les chantiers livrés (jalons v0.2 à v0.28) ont leur entrée dans le [CHANGELOG](../../changelog/CHANGELOG.md)
et leur détail dans [changelog/archives/](../../changelog/archives/) ; ils ne restent pas ici en doublon.

**Deux chantiers importants sont ouverts** : [l'export navigateur](#diffuser-une-rom-dans-le-navigateur-itchio)
(ouvert le 2026-10-05, aucune ligne de code) et
[l'interaction avec un acteur](#interagir-avec-un-acteur-on_interact-et-le-composant-interactive)
(ouvert le 2026-10-21, aucune ligne de code).

Pour mémoire, le jalon v0.16 (« L'API : règle de construction et rangement ») s'est fermé le
2026-09-27 ; voir son [détail](../../changelog/archives/v0.16-api-construction.md). Le singleton `mixer`,
seule chose restée non tranchée, est devenu une [piste](#piste-le-singleton-mixer). Le jalon v0.13
(« Édition mixte, les appels d'API en blocs ») a été retiré le 2026-09-27 : jamais engagé, et hors
scope (ce logiciel n'est pas un outil de visual scripting).

---

### Frictions relevées en construisant la démo tactique (2026-09-20)

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
   accepte un index dynamique 1-based (`actor:get(i)`), voir [test_actor_scene_naming.py](../../tests/scripting/test_actor_scene_naming.py).
   La piste restée ouverte à l'époque (les `exports_values` par instance non câblées au codegen)
   est depuis livrée. Voir [le chantier des exports de script](../../changelog/archives/script-exports.md).

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
   curseurs multiples, projectiles à purger en fin de phase (`codegen/oam_alloc.py`,
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
   voir [test_lua_subset.py](../../tests/scripting/test_lua_subset.py) (`test_get_actor_chaine_directe_une_methode`).
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

### Ce que la revue « projet de production » a relevé (2026-08-19)

Séance du 2026-08-19 : relecture du logiciel du point de vue d'un projet cible (metroidvania à
composante RPG, équipe de trois, cartouche réelle au bout), qui a fixé un ordre de traitement
recommandé pour sept jalons alors ouverts (v0.14 → v0.19 → v0.24 → v0.20 → v0.23 → v0.21 →
v0.22). **Les sept sont désormais livrés**, dans cet ordre. Voir le [CHANGELOG](../../changelog/CHANGELOG.md)
pour chacun. Le détail du raisonnement (pourquoi ce rang plutôt qu'un autre) reste consultable
dans l'historique git de ce fichier.

---

# Hors périmètre (pour l'instant)


- **Multijoueur par câble Link**, envisagé après la v1.0, pas avant. Très spécifique et
  coûteux à implémenter proprement.
