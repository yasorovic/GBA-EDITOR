# L'identité d'un asset et son fichier — **LIVRÉ**

> **Chantier technique** — il ne livre rien de visible pour qui joue au jeu produit avec
> l'éditeur, seulement des assets qui cessent de se dédoubler. Il n'a donc ni numéro `vX.Y`,
> ni ligne au [README](../../README.md), ni entrée au [CHANGELOG](../CHANGELOG.md) : c'est la
> convention des [chantiers techniques](../../ROADMAP.md#chantiers-techniques).

> **Livré le 2026-09-02.** Le nom de fichier fait foi, un asset dont la source a disparu est
> raccroché au fichier qui porte son nom, et un renommage n'est plus une suppression suivie
> d'une création. 13 tests dans `tests/project/test_asset_identity.py`.

## D'où vient la question

Un projet réel affichait **8 polices et 15 entrées** dans l'écran Texte, dont une moitié sans
planche. L'écran n'y était pour rien.

Un asset à sidecar porte son identité à **trois endroits** :

- le nom de son fichier `.json` — c'est la clé du `ResourceStore`, puisque `save` écrit
  toujours dans `<name>.json` ;
- le champ `name` qu'il contient — c'est ce que `load` lisait ;
- le fichier source qu'il cite (`asset`) — c'est ce que l'écran affiche.

Et le rattrapage à l'ouverture (`reconcile_*`) cherche l'asset par un **quatrième** chemin :
le stem du fichier source trouvé sur le disque. Rien ne recollait les quatre. Il suffisait
qu'un fichier soit renommé hors de l'éditeur pour que le rattrapage ne reconnaisse plus
l'asset, en crée un second, et laisse le premier affiché en pointant sur un fichier disparu.

Reproduit à l'identique avant correctif : un sidecar `japanese-condensed-kanji-01.json` citant
`Japanese Condensed Kanji 01.png` donne **deux** polices, dont une sans planche.

## Décisions verrouillées

- **Le nom de fichier fait foi.** `save` en dépend déjà ; `load` et `load_one` adoptent le
  stem du fichier quand le champ `name` a dérivé. Une ressource ne peut plus exister sous deux
  identités. La règle vaut pour toutes les familles à `ResourceStore`, pas seulement les
  polices : c'est le même `load`.
- **`path_of(item)`** — le sidecar d'une ressource se demande au store. `sync_font_file`
  décidait de sauvegarder en regardant `<stem du fichier source>.json`, qui n'est le bon
  fichier que tant que personne n'a renommé.
- **Un asset dont le fichier cité a disparu est RACCROCHÉ** au fichier qui porte son nom
  (`_relink_source`). Ne fait rien tant que le fichier cité existe : pas de vol de source à un
  asset bien portant.
- **Un fichier déjà source d'un asset n'en fonde pas un second** (`_sourced_by`). La règle
  n'existait que pour les polices, à cause du couple `.fnt` + page ; elle vaut pour les trois
  familles.
- **Un renommage n'est pas une suppression suivie d'une création.** Le watcher apparie la
  disparition et l'apparition du même événement — **même taille et même date à la
  nanoseconde**, ce que seul un renommage préserve — et émet `asset_renamed(avant, après)`.
  L'asset suit alors son fichier : `asset_encoding.rename_*` appelle le `Project.rename_*` de
  la famille, celui-là même que le finder utilise, donc le sidecar se déplace et les scènes,
  prefabs et scripts qui citent l'asset sont réécrits.
- **L'empreinte, pas un hachage.** Lire le contenu de chaque fichier à chaque frémissement
  d'un dossier d'assets coûterait à chaque sauvegarde, pour la même réponse : deux fichiers
  différents ne partagent pas taille ET date à la nanoseconde.
- **`pair_renames` est une fonction de module, hors de la classe.** C'est la seule règle du
  watcher qui se juge sur deux dictionnaires — sans dossier réel, sans Qt, donc testable.

## Ce que la lecture du code a trouvé en chemin

- **`reconcile_sprites` ne balayait pas `assets/sprites/`**, contrairement à son pendant
  `reconcile_backgrounds`. Le watcher crée bien un sprite quand un PNG apparaît en séance,
  mais le même fichier déposé — ou renommé — éditeur fermé n'était vu par personne. Le
  raccrochage des sprites en dépendait : la passe est ajoutée.
- **Renommer une planche en séance coûtait le sprite entier.** Le watcher traitant les deux
  moitiés du geste séparément, et les apparitions étant parcourues AVANT les disparitions, un
  sprite vierge (frames 8×8, aucun état) naissait du nouveau nom pendant que l'ancien —
  découpe, états, directions — était supprimé. C'est ce qui a motivé l'appariement.

## Ce que ça touche

| Fichier | Nature |
| --- | --- |
| [resource_store.py](../../editor/core/resources/resource_store.py) | le nom de fichier fait foi (`load`, `load_one`) ; `path_of` |
| [asset_reconciliation.py](../../editor/core/resources/asset_reconciliation.py) | `_relink_source`, `_sourced_by`, les cinq `rename_*`, balayage de `assets/sprites/` |
| [project_watcher.py](../../editor/core/project_watcher.py) | empreinte taille+date dans l'instantané, `pair_renames`, signal `asset_renamed` |
| [window.py](../../editor/window.py) | `_ASSET_ROUTES` porte la fonction de renommage, `_on_asset_renamed` |
| [ARCHITECTURE.md](../../ARCHITECTURE.md) | la table de routage a trois fonctions par famille, et pourquoi la troisième |
| [test_asset_identity.py](../../tests/project/test_asset_identity.py) | 13 tests : identité, raccrochage, appariement, renommage par famille |

## Ce qui reste ouvert

- **Le sidecar `.json` renommé seul à la main** n'est pas apparié : il revient par
  `sidecar_changed`, et c'est `load` qui rattrape l'identité au chargement suivant. Le geste
  est exotique ; l'apparier demanderait un second signal pour la même règle.
- **`remove_sprite_png` / `remove_background_png` cherchent par le seul stem**, là où
  `remove_font_file` retombe sur l'asset qui cite le fichier. Asymétrie connue, laissée en
  l'état : c'est une suppression, elle mérite sa propre décision.
- **Un renommage n'est pas annulable** (Ctrl+Z), pas plus que le renommage depuis le finder —
  `Project.rename_*` ne passe pas par l'historique. Inchangé par ce chantier.
