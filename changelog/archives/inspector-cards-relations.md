# Les inspecteurs en cartes, et les relations parent/enfants - **LIVRÉ**

> **Chantier technique** : mise en cohérence de l'interface de l'éditeur, rien de visible pour qui joue au jeu produit.
> Il n'a donc ni numéro, ni ligne au [README](../../README.md), ni entrée au [CHANGELOG](../CHANGELOG.md) (cf. les
> [chantiers techniques](../../docs/development/TODO.md#état-des-pistes)). Il touche le chantier important 0.5 (fonds) pour
> l'écran Fond, et la carte Relations prolonge les enfants de prefab (v0.23, « Ce qu'un boss demande »).

> **Livré le 2026-10-23.** L'écran Fond, l'écran Animations et les inspecteurs d'acteur, d'élément d'interface et de scène
> suivent le même gabarit (des cartes repliables, un état d'ouverture par défaut). La carte *Children* d'un prefab devient
> la carte *Relations*, présente aussi sur l'acteur de scène.

### D'où vient la question (2026-10-23)

Un tour de l'éditeur à l'écran a relevé des écarts de gabarit et trois défauts de comportement :

- l'inspecteur de l'écran Animations n'était pas en cartes alors que ceux des fonds, des acteurs et des scènes l'étaient ;
- l'état d'ouverture des cartes à la première ouverture variait d'un inspecteur à l'autre (tout ouvert, sauf ce qui avait
  été replié à la main) ;
- sur l'écran Fond, l'outil par défaut était le pinceau, et quitter l'outil « select » pouvait rendre la gomme ;
- les enfants d'un prefab ne s'éditaient que dans une carte réservée aux prefabs, alors que les acteurs de scène ont eux
  aussi des enfants (champ `parent`), seulement sans carte pour les atteindre.

### Décisions verrouillées

- **Un seul gabarit d'inspecteur** : des `CollapsibleCard` espacées de 6 px, dans une gouttière de 8 px (celui du Scene
  Inspector). L'inspecteur de l'écran Animations le reprend : *Canvas size*, *Animation*, *Directions*, *Palette*.
- **État d'ouverture par défaut**, posé à la création de chaque inspecteur (rien n'est mémorisé d'une session à l'autre) :

  | Inspecteur | Ouvertes | Repliées |
  | --- | --- | --- |
  | Fond | Type, Color mode | Canvas, Palettes, Image adjustments, Compression |
  | Acteur | Note | Transform, Components, Relations |
  | Élément d'interface | la carte propre à l'élément (Text, Background, Image) | Geometry, Visibility |

  Image adjustments et Compression s'ouvrent encore d'elles-mêmes quand l'image ne tient pas telle quelle ou que des
  réglages existent déjà (`_compression_needs_attention`) : c'est une règle plus ancienne, inchangée.
- **Un sprite est toujours sélectionné à l'ouverture de l'écran Animations** : le dernier retenu pour ce projet, sinon le
  premier de la library (`AssetLibrary.first`, `SpriteLibraryPanel.select_default`). Le nom est retenu dans `QSettings`
  (`SpriteEditor`, clé `last_sprite/<racine du projet>`), préférence d'affichage locale comme le repli des libraries :
  elle ne s'écrit pas dans le projet.
- **L'écran Fond s'ouvre sur l'outil « select »** (celui qui pose l'image dans son canvas). Le retour d'outil ne mémorise
  jamais la gomme (elle purge les calques) : quitter « select » rend le dernier outil de peinture, par défaut le pinceau.
- **Une seule taille de pinceau**, un bouton qui défile : une icône de brosse fixe et un bouton 8, 16, 32 qui passe à la
  valeur suivante à chaque clic, puis revient à 8 (`CanvasTopBar.add_cycle`, qui remplace `add_choice`).
- **Sur l'écran Fond, Palettes monte sous Canvas**, et « Extract palette from source » entre dans cette carte (il était
  ferré en bas de l'inspecteur).
- **Inspecteur de scène** : la liste *Transition* n'a plus d'entrée « From project ». Une scène sans réglage propre montre
  la valeur qu'elle obtient réellement (celle du projet), sans rien écrire ; le modèle (`Scene.transition_kind` vide =
  suit le projet) et le build ne changent pas. Le libellé de la carte *Scene prefabs* vide devient « No prefab is placed
  or spawned ».
- **La carte *Relations* remplace *Children*** et vaut pour les trois cas :
  - *acteur de scène* : Parent (lien qui le sélectionne) et Enfants (liste des acteurs dont `parent` le nomme, double-clic
    pour en sélectionner un) ; un « + » crée un acteur « Child » rattaché à l'acteur courant, posé sur lui ;
  - *racine de prefab* : ses parties (`Prefab.children`) avec « + », « - » et glisser-déposer pour les rattacher entre
    elles ; un double-clic ouvre une partie avec les champs d'un acteur, **sans poser le prefab dans une scène** ;
  - *partie de prefab ouverte* : Parent (une autre partie, ou la racine) et ses sous-parties, simple navigation.

  La carte est toujours là (le « + » crée le premier enfant) ; ses sections Parent et Enfants ne s'activent que si la
  relation de parenté existe réellement.

### Pourquoi deux mécanismes d'enfants restent distincts

Un acteur de scène exprime sa hiérarchie par son champ `parent` (combo *Parent* de la carte Transform, glisser-déposer
dans l'arbre de scène), et le codegen la résout par `_parent_compose_lines`. Un prefab est un seul template que `spawn()`
doit faire naître avec son sous-arbre : sa liste `Prefab.children` réserve un groupe contigu d'entrées par instance
(`_pool_compose_lines`). Même formule de composition, deux modèles, parce que le besoin diffère. La carte Relations unifie
l'**accès** (une seule carte), pas le modèle.

### Défaut corrigé au passage : la flèche d'un parent n'apparaissait pas après un glisser

Lâcher un acteur sur un autre, dans l'arbre de scène, mettait le modèle à jour et repeuplait l'arbre en pleine opération de
glisser. Qt retire ensuite de la vue les lignes sélectionnées (action « déplacer ») : la sélection portait alors sur l'arbre
repeuplé, donc la ligne de l'enfant disparaissait et le parent restait sans flèche jusqu'au rafraîchissement suivant.
Les lâchers que le modèle traite lui-même répondent maintenant « ignorer » à Qt (`_accept_drop_handled`) : acteur sous un
acteur, retour à la racine, déplacement dans un dossier, glisser d'un élément d'interface. La cause est déduite de la
lecture du code et de Qt ; elle n'a pas été reproduite par un test (un test hors écran ne rejoue pas la séquence réelle du
glisser).

### Ce qui a été retiré

- `CanvasTopBar.add_choice` (plus aucun appelant).
- L'ancienne carte *Children* de l'inspecteur d'acteur et ses clés `actorinsp.card.children`, remplacées par
  `actorinsp.card.relations`, `actorinsp.rel.parent`, `actorinsp.rel.children`, `actorinsp.rel.parent_tip` ;
  `actorinsp.children_tip` et `actorinsp.children_note` sont réécrites pour valoir aussi hors prefab.
- Les libellés `sceneinsp.from_project`, `sceneinsp.inherited_transition` et `sceneinsp.transition_frames`.
- Le bouton « extraire » à contour de 38 px du pied de l'inspecteur Fond.

### Restes ouverts

- **Le rattachement n'est pas annulable.** Le Ctrl+Z annule la création de l'acteur « Child », mais le parent est posé juste
  après, hors historique ; c'est aussi le cas du glisser-déposer de l'arbre de scène aujourd'hui.
- **L'outil « select » montre le fichier source.** Tant qu'il est actif (donc par défaut), l'aperçu des ajustements
  (teinte, luminosité) n'apparaît pas sur le canvas ; il faut quitter l'outil pour le voir.
- **Durée d'un fondu hérité.** Tant que la scène suit un fondu du projet, la liste le montre mais le champ de durée reste
  caché : il faut choisir un fondu explicitement pour le régler.
- **La ligne 0.5 du ROADMAP** dit encore « Conception en cours » alors que le plan de travail (canvas, position et taille de
  l'image, Ajuster / Remplir / 1:1) est livré ; seule la comparaison source/compressé reste à faire.

### Tests

`tests/ui/test_tile_painter.py` (outil par défaut, retour d'outil, taille de pinceau, tests existants recalés sur
« select » par défaut), `tests/ui/test_sprite_default_selection.py`, `tests/ui/test_actor_relations_card.py`,
`tests/ui/test_scene_inspector_inherited_transition.py`. Les tests d'inspecteurs d'acteur et d'élément d'interface, ceux du
catalogue de libellés et ceux de l'arbre de scène passent ; l'affichage réel n'a pas été vérifié à la souris.
