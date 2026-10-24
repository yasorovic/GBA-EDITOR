# Assets et disque : tout ce que l'auteur manipule vit dans `assets/` (**LIVRÉ**)

*Chantier important (0.3). Livré le 2026-10-23, avant toute release publique : il n'a ni entrée de CHANGELOG ni numéro de version.*

Ce fichier garde la discussion complète du chantier, extraite de la TODO à sa livraison : les décisions, les pièges et ce qui a été
abandonné en route. Plusieurs sections décrivent un état intermédiaire que la suite a remplacé ; les « Reste » et « Pas encore » du texte
sont ceux du jour où ils ont été écrits, le reliquat vivant est dans la TODO.

## Ce que le chantier livre

- **Un `assets/` à l'auteur.** Scènes, prefabs, mises en page, boîtes sonores, tables, polices logiques, textes et variables vivent dans
  `assets/`, rangés où il veut ; `project/` ne garde que l'état interne de l'éditeur, les licences et le README.
- **Des assets indépendants de leur source.** Un id hexadécimal stable dans chaque sidecar, une extension par type d'asset (`.sprite`,
  `.background`, `.sfx`…), l'asset *pointe* sa source par un chemin (fonds, palettes et scripts compris) ; déplacer ou renommer l'un ne
  touche jamais l'autre. Source absente : une erreur de build et *Relink source…*.
- **L'onglet Disk.** Arbre fidèle de `assets/` et vue à plat, glisser-déposer (`core/disk_move.py`), dossier créé et renommé en place,
  écraser plutôt que suffixer à l'import, suppression annulable.
- **Créer un asset en deux gestes.** *Create from source* et *Create blank* (`core/asset_creation.py`), une commande annulable, dans le
  dossier que Disk affiche ; plus aucun dossier titulaire par famille, plus de création automatique à l'apparition d'un fichier.
- **Une seule règle de nom libre.** `base`, `base_2`, `base_3` (`core/models/unique_name.py`), les huit anciennes règles supprimées.
- **Une library par famille** ([Finder et Disk](finder-to-library.md)), la duplication d'asset et l'ouverture d'un asset passé en argument
  au lancement (pas d'association système des extensions d'asset).

## Ce qui n'est pas dans ce chantier

Les **références par id** (une scène qui cite un asset par son id plutôt que par son nom) en sont sorties le 2026-10-23 : elles touchent toutes
les scènes et se décident avec [le stockage des références](../../docs/development/TODO.md#le-stockage-des-références-nom-ou-id-dans-les-cellules).
Le reliquat de finition figure dans la [TODO](../../docs/development/TODO.md#assets-et-disque-ce-qui-reste-après-la-livraison-de-la-03).
Les réglages des SFX et des jingles, sortis de la 0.3 le 2026-10-22, restent dans la TODO (« Dupliquer un asset, et régler SFX et jingles »).

---

### Source ≠ asset (l'arborescence du disque et l'id stable)

#### D'où vient la question (2026-10-09)

L'auteur a rangé ses sons dans une arborescence (`assets/sfx/platformer/wav/…`, 556 fichiers dont 175 `.wav`
réels). L'éditeur ne la voit pas : la synchronisation fait `glob("*")` à plat
(`asset_reconciliation.reconcile_sfx_and_music`), et l'identité d'un asset est **le nom du fichier sans
extension** (`path.stem`). Le sidecar `GOAL.json` porte `"name"` et `"asset"`, aucun id. 10 noms de `.wav`
apparaissent dans plusieurs dossiers (`coin`, `die`, `fireball`…).

Le but à terme : un dossier `assets/` **vierge** que l'auteur organise comme il veut (modèle Unity / Godot /
Unreal), puis un clic droit sur une **source** → *Create asset* (l'auteur choisit le type d'asset à en tirer).
Un script ne référence jamais une source, toujours un asset.

#### Ce que font les trois moteurs

Tous séparent l'identité de l'emplacement : Unity un GUID dans un `.meta` voisin du fichier ; Godot le chemin
`res://` plus, depuis la 4.4, un `uid://` ; Unreal le chemin de package complet. Deux `coin` dans deux dossiers
ne se heurtent dans aucun des trois, et l'auteur choisit une référence en la sélectionnant plutôt qu'en tapant
un nom.

#### Ce qui existe déjà

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

#### Décisions verrouillées (2026-10-09)

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

- **Le nom d'asset est unique parmi les assets de son type** (2026-10-09 ; précisé le 2026-10-22 : un décor et une
  musique peuvent porter le même nom, la copie d'une source n'est suffixée que face à un fichier de MÊME extension). Il se tranche à la création (*Create asset*
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

#### Ce qu'il faudrait trancher avant d'ouvrir

1. **Source sans asset.** Visible dans l'onglet Disk (grisée si le format n'est pas pris en charge, avec
   infobulle) ; absente de l'asset finder et du projet tant qu'aucun *Create asset* n'a été fait.
2. **Migration.** Les sidecars existants restent où ils sont et reçoivent leur id ; `asset-folders.json` passe
   de membres-par-nom à membres-par-id.

#### Ordre d'implémentation (proposé)

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
     **Tranché et livré le 2026-10-22, réduit à l'argument** : l'éditeur lancé avec un fichier d'asset (`Hero.sprite`,
     `Level.scene`…) ou un script `.lua` ouvre le projet qui le contient (premier dossier parent à manifeste) et montre le
     fichier dans son écran, comme un double-clic de Disk (`core/launch_target.py`, `main.py`, `MainWindow.open_asset_file`).
     **Aucune association système des extensions d'asset** : `.font`, `.table`, `.scene` sont trop génériques pour qu'on les
     réclame à l'utilisateur ; seule `.project` reste associée (déjà faite, installateur et MIME).
   - **Sorties de la 0.3 le 2026-10-23, les références par id** (une scène qui cite un sprite par son id et non par son nom) : un chantier à
     part, qui touche toutes les scènes, suivi avec [le stockage des références](../../docs/development/TODO.md#le-stockage-des-références-nom-ou-id-dans-les-cellules).
6. Extension aux musiques, jingles, sprites, fonds.

**Livré aussi (2026-10-10) :** l'arbre vertical de tout `assets/` vit dans la colonne de gauche, sous un onglet **Disk**
à côté de **Project viewer** (qui devient lui-même un onglet : on ne touche pas au mécanisme d'`AssetFinder`). Choisir un
dossier de l'arbre l'affiche, à plat, dans l'onglet Disk du panneau du bas, comme le fait Unity ; la vue du bas se
navigue aussi seule (double-clic, fil d'ariane). Le sens inverse (un double-clic en bas qui sélectionne le dossier
dans l'arbre) n'est pas fait.
**Un `assets/` vierge, des imports dans le dossier affiché, un surveillant sans dossiers imposés (2026-10-19).** Créer ou ouvrir
un projet ne crée plus aucun sous-dossier (seulement `assets/`) : chaque écriture crée le dossier qu'elle vise. Tout bouton
d'import d'un écran (importer un sprite, un fond ; *Save as PNG*) pose le fichier
dans le dossier que l'onglet Disk affiche (`core/asset_creation.import_folder`, branché une fois par la fenêtre dans
`ui/common/import_folder.py`), sinon à la racine de `assets/`. Le surveillant suit tous les dossiers sous `assets/` à toute
profondeur, avec tous les types de fichiers : plus de liste de dossiers de famille ni de `parent.name == "sprites"`. Un
fichier retouché est relié à ce qui le CITE (fond, sprite, police), un sidecar à son extension. *Reste :* l'import de
palettes (les `.hex` vivent dans `assets/palettes`), les dossiers vides des projets de démo, créés avant ce changement.
**Écraser plutôt que suffixer (2026-10-20).** *Import / replace image* créait `hero_2.png` au lieu de remplacer le PNG, et le
« + » d'un fond écrasait sans rien dire. Cartographie des points d'entrée, puis une règle unique : `core/source_collisions.py`
(même nom exact = collision ; tout autre nom pris = `unique_name`) et une boîte, `ui/common/import_collision.py` (écraser /
garder les deux / annuler, avec les assets qui citent le fichier). *Remplacer l'image* (sprite, fond) écrit le fichier choisi
SUR la source de l'asset (`source_import.replace_source`) et ne demande que si un autre asset la cite ; l'import d'un sprite,
d'un fond ou d'un son et l'import ou le dépôt de l'onglet Disk posent la question sur collision. `ImportFilesCmd` garde le
contenu écrasé : annuler le restaure. *Reste :* l'encodage d'un sprite ou d'un fond remplacé n'est pas dans l'historique
(annuler rend le PNG, pas l'encodage, que le rechargement refait) ; un dossier déposé garde son suffixe sans question ; une
seule réponse vaut pour tout un lot ; aucun test de l'interface (seul l'annulable de `ImportFilesCmd` est couvert).
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

#### Ce que ça ne fait pas

- Ne change ni le runtime C ni le format de la ROM.
- Ne fait pas de l'éditeur un outil de dessin généraliste (cf. périmètre). Le **Color Tile
  Painter**, s'il est ouvert, est l'exception volontairement étroite : il sert à poser un fond
  de prototype en couleurs pleines, pas à retoucher ou illustrer une image.

---

### Une seule règle de nom libre

#### D'où vient la question (2026-10-09)

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

#### Décision (2026-10-09)

**Une seule règle : `base`, puis `base_2`, `base_3`…**, celle de `unique_name`. Elle vit dans
`core/models/unique_name.py` (couche modèle, sans dépendance), et tout le monde l'appelle. Sont **supprimés**,
pas conservés à côté : `_copy_name` (un duplicata d'acteur devient `Hero_2`, la distinction « copie » /
« création » est abandonnée), `unique_region_name` et `unique_element_name`, `asset_kinds._unique`, et chaque
boucle écrite à la main. Les noms déjà enregistrés dans un projet ne changent pas : seule la suite des
NOUVEAUX noms change.

---

### Tout ce que l'auteur manipule vit dans `assets/`

#### D'où vient la question (2026-10-10)

Le chantier « Source ≠ asset » a posé que `assets/` est le dossier de l'auteur, qu'il organise lui-même (modèle Unity /
Godot / Unreal). Or une partie de ce qu'il manipule vivait encore sous `project/` : l'onglet Disk n'en montrait rien. La
décision avait été de garder `project/` pour « ce qui n'a pas de source à relier » ; elle est **révisée** : `project/`
n'est plus pour l'auteur, `assets/` l'est pour tout.

#### Décisions verrouillées (2026-10-10)

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

#### Ce que ça touche

- **Chemins** : les propriétés de `core/project_paths.py` (une dizaine), plus les emplacements écrits en dur, la création
  des dossiers à l'ouverture (`Project.load`, `Project.create`), la surveillance (`ProjectWatcher`), les traductions
  (`texts_<langue>.json`), la copie d'un starter.
- **L'onglet Disk** : ces fichiers y apparaissent ; ils doivent être marqués ASSET (famille, icône) et non « Non géré ».
- **Tests** : ceux qui construisent un projet à la main ou citent `project/<famille>` (une quinzaine).
- **Docs** : ARCHITECTURE (la disposition d'un projet), les en-têtes de module qui citent `project/`.

#### Ordre d'implémentation

1. Les chemins et leurs utilisateurs (code, surveillance, starters).
2. L'onglet Disk reconnaît ces familles.
3. Le script de migration, appliqué aux démos et au starter.
4. Les tests, les docs, la chasse au code mort.

---

### Créer un asset : deux gestes, aucun dossier titulaire

#### D'où vient la question (2026-10-19)

Créer un asset a deux gestes, **créer depuis une source** et **créer vierge**, et l'onglet Disk les suit déjà
(`window._disk_create_from_sources`, `_disk_create_blank`, qui passent par `core.asset_creation` /
`core.blank_assets` puis `CreateAssetCmd`). Mais d'autres chemins font la même chose chacun à sa façon, et quelques
familles gardent un dossier « à elles ». Deux exceptions justifiaient ces dossiers (les scripts de **behavior** et les
**palettes**) ; elles sont levées : un behavior se reconnaît à son contenu (`-- @behavior`), une palette pointe son `.hex`
comme les autres assets pointent leur source. Plus aucune famille n'a de raison d'être titulaire d'un dossier.

#### Demandé par l'auteur (2026-10-19)

- **Deux commandes, pas une de plus** : *Create from source* et *Create blank*. Tout écran, tout bouton « + », toute
  importation y passe.
- **Plus aucun asset ne possède un dossier.** Un asset naît dans le dossier que l'auteur désigne (celui que l'onglet Disk
  affiche, sinon la racine de `assets/`), et se range ensuite où il veut.

#### Ce que le code dit aujourd'hui (lu le 2026-10-19, rien d'exécuté)

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

#### Le contrat proposé (non verrouillé)

- `asset_creation.create_from_source(project, family, paths, folder)` et `asset_creation.create_blank(project, kind, folder)`
  rendent **une commande annulable** (`CreateAssetCmd`, `CreateFileCmd`, `MacroCmd` pour un lot). `folder` est obligatoire :
  l'appelant le prend à `import_folder()` s'il n'en a pas d'autre. Le message d'état reste affaire de la fenêtre.
- Les scripts et les behaviors sont deux types de `create_blank` comme les autres ; `script_creation.py` disparaît.
- `ResourceStore(root, cls)` : plus de `directory`. Un asset sans dossier donné naît à la racine de `root`.
- Une palette neuve naît avec son `.hex` **à côté de son sidecar**, dans le même dossier ; plus d'adoption d'un `.hex`
  déposé à la main (il redevient une source libre, qu'on transforme par *Create from source*).
- Les propriétés `*_dir` de famille disparaissent, `scripts_behaviors_dir` et `font_assets_dir` comprises.

#### Ce que ça touche (à confirmer en lisant le code avant d'ouvrir)

- `core/asset_creation.py`, `core/blank_assets.py`, `core/resources/resource_store.py`, `core/resources/palette_store.py`,
  `core/project_paths.py`, `core/project.py` (construction des stores, ligne du PNG de fond), `window.py` (callbacks Disk).
- `ui/common/asset_kinds.py`, `ui/common/asset_finder.py`, `ui/common/script_creation.py` (supprimé),
  `ui/script_editor/script_finder_panel.py`, `ui/scene_manager/assets_finder_panel.py`, `component_editors/script.py`
  (non lu), `ui/sprite_editor/import_png_dialog.py`, `ui/background_editor/background_editor_screen.py`.
- **Tests** : ceux qui construisent un projet à la main et comptent sur `project/<famille>/` ou sur l'adoption d'un `.hex`
  (palettes). **Docs** : ARCHITECTURE, `docs/development/`, en-têtes de module qui citent un dossier de famille.
- Les deux démos et les starters ne sont pas réécrits sans accord de l'auteur ; leurs fichiers restent où ils sont.

#### Décisions (2026-10-19, de l'auteur)

1. **Les starters et un projet neuf ne livrent plus de dossiers vides par famille** (`sprites/`, `scenes/`…).
2. **Pas de migration des `.hex`** des démos : ils restent où ils sont. Le starter, lui, livre désormais le `.palette`
   de chacune de ses palettes (sans quoi elles disparaîtraient avec l'adoption).
3. **`FontAsset` suit la même règle** : il naît dans le dossier désigné, `font_assets_dir` disparaît avec les autres.

#### Livré (2026-10-19)

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

- **Tranche 4, `ResourceStore(root, cls)` (constatée livrée le 2026-10-22)** : plus aucun store ne reçoit de dossier de famille
  (`Project` les construit tous sur `user_library_dir`) et les propriétés `*_dir` de famille ont disparu de `project_paths.py`
  (ne restent que `user_library_dir`, `project_dir`, les dossiers de build et `legacy_sound_states_dir`, lu une fois par la
  migration des boîtes sonores). Dernier chemin parallèle retiré : le bouton « New script » du Script Editor, qui demandait
  un nom par une fenêtre et écrivait le fichier à la racine sans historique, appelle maintenant le « + » de la bibliothèque
  (*Create blank*, dossier affiché par Disk, annulable) ; `ScriptLibraryPanel.set_root` et `_root_scripts_dir` sont supprimés.
  **Reste** : le fond vierge et l'import `.gpl` / `.pal` ne sont pas des écarts (décidé le 2026-10-22), et
  `tools/create_build_benchmark.py` écrit encore `project/scenes` (ancienne disposition).

#### Ordre d'implémentation (proposé)

1. `PaletteStore` d'abord (l'exception réelle), avec son test : `.hex` à côté du sidecar, plus d'adoption.
2. `asset_creation` : les deux entrées rendant une commande ; l'onglet Disk les appelle.
3. Les chemins parallèles, un par un (scripts, sons, tables, polices, palettes, sprite, background).
4. `ResourceStore(root, cls)` et la suppression des `*_dir` de famille.
5. Tests, docs, chasse au code mort ; l'ancien code est supprimé avant de dire terminé.

#### Ce que ça ne fait pas

- Ne déplace aucun fichier d'un projet existant.
- N'ajoute aucun type d'asset ni aucun geste de création : il en retire.
- Ne touche ni à la règle des noms libres (`coin`, `coin_2`) ni au chantier « Finder et Disk » (renommage, [livré](../../changelog/archives/finder-to-library.md)).
