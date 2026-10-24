# Texte et données : écrire les textes d'un jeu et les organiser — **LIVRÉ**

*Chantier important (0.4). Livré le 2026-10-23, avant toute release publique : il n'a ni entrée de CHANGELOG ni numéro de version.*

Ce fichier garde la discussion complète du chantier, extraite de la TODO à sa livraison : les décisions, les pièges et ce qui a été
abandonné en route. Plusieurs sections décrivent un état intermédiaire que la suite a remplacé ; chacune le dit en tête.

## Ce que le chantier livre

- **Écran Texte** : texte rangé par clé, séquences numérotées *dérivées* des clés (liées à une table ou à une TextBox, ou libres), **Create table**
  et **Link to existing table**, **+ / −** et glisser pour réordonner, synchronisation dans la même commande annulable.
- **Texte à l'écran** : `Text` (une chaîne) et `Textbox` (une boîte, plusieurs pages) écrits directement dans le canvas.
- **Écran Données** : une grille de jeu et non un tableur (rang = index Lua, couleurs de colonnes, références contrôlées), édition au clic,
  aperçu dans l'inspecteur (texte corrigeable, palette, image, fichier de son), accès direct à l'élément cité, « Create new » dans le sélecteur
  d'une cellule (texte `text_<Table>_01`, palette, SFX, musique).
- **Interface de l'écran Texte** : le contenu en blocs multi-lignes éditables, sans aperçu écran ; finition ouverte (Find, regroupement par scène, code mort).
- **Dialogue** : une table de données et des textes, sans éditeur de dialogue ni arbre de conversation (le script décide quand avancer).

## Ce qui n'est pas dans ce chantier

Chantiers techniques nés de la 0.4, dans la [TODO](../../docs/development/TODO.md#état-des-pistes) : une seule navigation « ouvrir cet élément »,
le stockage des références (nom ou id), le collage d'un tableau dans la grille (reporté). Le reliquat de vérification y figure aussi.

---

### L'écran Données (une grille de jeu, pas un tableur)

#### Le problème (2026-10-14)

L'écran a la bonne sémantique : une table est typée, ses références sont contrôlées,
et son rang est l'index que lit `data.Table[i]`. En revanche, ses gestes essentiels restent
peu découvrables : renommer une colonne demande un double-clic, modifier sa structure ou
une ligne passe principalement par le clic droit, et l'écran ne rappelle pas assez ce que
déplacer une ligne implique pour le script.

Le but n'est donc pas de fabriquer un tableur. Un tri ou un filtre donnerait à voir un ordre
différent de celui que le runtime indexe ; des formules changeraient la nature de cette donnée
`const` en ROM. Le but est une grille compacte qui permet de créer et corriger rapidement des
données de jeu, tout en rendant leurs contraintes explicites.

#### Livré (2026-10-17)

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
  `AssetPickerPopup` : recherche, icônes et aperçu des palettes, avec un choix « Aucun ».
  Choisir écrit par l'historique de la grille ; fermer ou appuyer sur Échap conserve la valeur,
  même si sa cible n'existe plus. Un popup ouvert avant un rechargement ne peut pas écrire
  dans la nouvelle table. Le filtre porte uniquement sur les choix d'assets, jamais sur les lignes.

**Vérification.** Tests ciblés de grille, de couleurs (widget partagé, persistance, annulation),
de références graphiques (catalogues, validation, génération et renommage) et de sélecteur
(filtre, choix, effacement, fermeture et rechargement). Rendu contrôlé, ouverture clavier et
Échap vérifiés ; l'usage prolongé sur une table de jeu dense reste à valider.

**Édition au clic (2026-10-23).** Un premier clic sélectionne la case ; un clic sur la case déjà courante l'édite (le double-clic
continue de marcher, la 2e frappe étant celle d'une case courante). `QAbstractItemView.SelectedClicked` ne convenait pas : avec la
sélection par ligne, il édite dès qu'on clique n'importe quelle case d'une ligne sélectionnée. Voir `DataGridPanel.eventFilter`.

**Aperçu contextuel dans l'inspecteur (2026-10-23).** La carte Cell montre ce que la cellule désigne (`ui/data_editor/data_cell_preview.py`) :
le contenu d'un texte, **corrigeable sur place** (langue source, validé à la perte du focus ou au changement de sélection, un pas d'historique,
même commande que l'écran Texte) ; les couleurs d'une palette ; l'image et la taille d'un sprite ou d'un fond ; le fichier source d'un son.
**Exception assumée** à « le panneau droit n'est pas un second éditeur » : le texte cité est une entrée de la table de textes, pas une valeur de
la grille ; la cellule, elle, ne s'écrit toujours que par la grille. **Reste** : traductions (la langue source seule s'édite ici), durée d'un son,
vérification à la main.

#### Direction retenue et suite

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
5. **La saisie en série est reportée (décidé le 2026-10-23).** Copier/coller TSV, sélection de plage
   et `Suppr` multiple n'ont pas d'usage constaté pour l'instant ; on les rouvre si une table de jeu
   réelle en montre le besoin. Si le collage revient, il passe par le presse-papiers seul (jamais un
   fichier `.tsv`) et par deux fonctions uniques de conversion, voir
   [le collage dans la grille](../../docs/development/TODO.md#coller-un-tableau-dans-la-grille-presse-papiers-seulement).

#### À ne pas faire

- Ni tri, ni filtre des lignes : l'ordre affiché doit toujours être l'ordre réel des index Lua.
  Le filtre du sélecteur de références ne change pas cet ordre.
- Ni formules, ni calculs de feuille : les tables sont des données authorées, lues en ROM.
- Ni panneau droit transformé en second éditeur : il explique et mène à la ressource citée ;
  l'écriture passe toujours par la grille et son historique unique.

### Briques de base et assemblages (`Text` (chaîne) et `Textbox` (boîte))

#### D'où vient la question (2026-10-14)

Le menu d'ajout d'interface proposait `Text`, `Container`, `List`, `Image` sur un seul rang. Or trois
sont des **briques** que le moteur dessine telles quelles (texte, conteneur, image) et deux sont des
**assemblages** qui rangent selon une règle (la liste se parcourt, la boîte de texte coupe). La
distinction est celle d'Illustrator : une chaîne se pose en un point, une boîte de texte se dessine
comme une surface.

#### Décisions (2026-10-14, de l'auteur)

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

#### Ce que ça touche

`core/models/ui_region.py` (`UITextbox`, `is_text`, `KINDS_BRICK`/`KINDS_ASSEMBLY`), `font_emit.py` et
`gba_engine.h` (`nowrap`), `scene_tree_panel.py` et `canvas_toolbar.py` (menu), `canvas_region_item.py`
(point d'origine, édition en place), `ui_inspector.py`, `project_names.py` (une boîte se cite comme
une chaîne en Lua), tests `tests/interface/test_ui_textbox_type.py`.

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

---

### TextBox (plusieurs entrées pour préparer un dialogue)

#### État au 2026-10-23 (modèle dérivé)

Livré le 2026-10-17 avec un moteur d'export (`page_ids`, Export as table / Update table, `textbox_export`, marqueurs `$editor`), ce moteur a
été **retiré le 2026-10-18** au profit des séquences dérivées (voir [Écran Texte](#écran-texte-suites-liées-aux-textbox-et-aux-tables)). Ce qui
vaut aujourd'hui :

- **Les pages sont dérivées, jamais stockées.** Une TextBox lit une séquence par `UITextbox.sequence_prefix` (ou n'affiche que son `text_key`).
  Ses pages sont les textes dont la clé finit par `_<chiffres>` sous ce préfixe, dans l'ordre des numéros.
- **L'inspecteur de la boîte** présente un bloc par page : **+** insère une page après le bloc, **−** la retire, le glisser la déplace (les
  textes échangent leurs numéros, en une seule commande annulable). Les réglages de police, couleur et alignement sont communs aux pages.
- **Le lien avec une table** se fait depuis l'écran Texte, sur la séquence : **Create table** ou **Link to existing table**. Les lignes de la
  table suivent la séquence d'elles-mêmes (une ligne par clé de la colonne `text`) ; les autres colonnes restent à l'auteur. Côté script :
  `interface:get("Dialogue"):draw(data.<Table>[i].<colonne>)`, les indices commencent à 1.
- **Le build** réserve une seule entrée runtime et un seul rectangle par boîte ; seule la première page est dessinée à l'initialisation. Toutes
  les pages et traductions alimentent les glyphes, les polices balisées et les diagnostics de débordement/couverture ; le budget de glyphes
  animés prend le **maximum** entre pages et langues, jamais leur somme. Une page absente bloque le build avec son numéro.
- **Migration.** Les anciens `page_ids`, `sequences` et `$editor` sont ignorés à la lecture : une boîte multipage d'avant garde son `text_key`
  et se relie à la main à sa séquence.

Tests : `tests/text/test_text_page_group_model.py`, `tests/text/test_text_table_link.py`, `tests/ui/test_textbox_pages_inspector.py` et
`tests/rom_build/test_textbox_pages_rom.py` (lent, adapté au modèle dérivé, **non relancé** depuis la refonte ; exécution mGBA si son
frontend SDL est présent).

#### Reliquat ouvert

- **Layouts partagés et renommages :** la clé d'une nouvelle page vient du rangement ; renommer une scène ou un objet ne recalcule pas les
  clés déjà créées. Trancher ce suivi en respectant les clés nommées à la main.
- **Duplication d'une boîte :** vérifier à l'usage ce que partage la copie (la séquence lue) et décider si elle doit plutôt créer ses
  propres textes et traductions.
- **Vérification à la main** de l'en-tête de séquence et de l'inspecteur, et relance du test ROM (devkitPro).
- *Retiré de ce reliquat :* le geste de déplacement d'une page existe (glisser), de même que le nommage par le rangement.

#### Hors du périmètre livré

Déroulement automatique du dialogue, passage sur appui, temporisation, effet machine à écrire, choix branchés, arbre de conversation et
découpage automatique d'un long texte en pages.

---

### Écran Texte (suites liées aux TextBox et aux tables)

#### État au 2026-10-23

L'écran Texte range et édite le contenu ; les **suites** y sont **dérivées** des clés (voir la décision du 2026-10-18 ci-dessous). Sous
l'en-tête d'une suite : son état (**liée** à des tables ou à une TextBox, ou **libre**), **Link to existing table** et **Create table** pour une
suite libre, **+ / −** sur chaque entrée, glisser pour réordonner, filtres d'affichage (ils ne définissent jamais la suite). Ajouter, retirer,
renommer ou réordonner un texte d'une suite liée réécrit ses consommateurs dans la même commande : il n'y a ni bouton Update, ni aperçu
périmé. Les étapes antérieures (identité persistante, Link/Relink, Apply, `sequences` dans `texts.json`) ont été retirées et ne sont plus décrites.

#### Séquences dérivées, liées ou libres (décidé le 2026-10-18 (REMPLACE l'adoption explicite))

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
- **Reste (2026-10-23) :** contrôle à la main de l'en-tête et de l'inspecteur (en cours) ; test ROM `test_textbox_pages_rom`
  adapté mais non relancé (devkitPro). Aucun libellé `txtseq.*` orphelin relevé.

#### Le chemin est dérivé de la clé (plus de libellés stockés (décidé le 2026-10-18))

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

#### Simplification de la clé (décidée le 2026-10-18)

Deux exceptions retirées, pour qu'il reste un comportement attendu et fiable :
- **`auto_key` est supprimé** (champ, badge, cadenas, `RelinkTextKeyCmd`, renommage de feuille
  du Finder qui visait la clé). La clé porte la structure ; renommer un libellé ne la touche
  jamais ; la renommer ou déposer le texte dans un autre dossier la change partout où elle est
  citée. Les anciens `texts.json` qui contiennent `auto_key` se lisent sans erreur.
- **Une page peut apparaître plusieurs fois dans une TextBox.** Aucun besoin n'est présumé :
  la règle n'a simplement pas de cas particulier. Seule la renumérotation d'un texte partagé
  reste refusée, puisqu'on ne peut pas renuméroter une même entrée deux fois.

---

### Un pont entre l'écran Texte et les tables de données (créer un dialogue)

**Statut au 2026-10-23 : livré, sous une autre forme que celle proposée plus bas.**

- **Piste A (du texte vers une table)** : couverte par les séquences. Depuis l'écran Texte, une suite libre propose **Create table** (nouvelle
  table, une ligne par page) ou **Link to existing table** ; la table suit ensuite la suite d'elle-même. Ce n'est pas la sélection libre de textes
  quelconques imaginée au départ : la suite est dérivée des clés numérotées.
- **Piste B (depuis la cellule)** : livrée le 2026-10-23, voir ci-dessous.
- Le moteur « Export as table / Update table » du chantier TextBox, évoqué ici auparavant, a été retiré le 2026-10-18.
- Les points « à trancher » restent consultables mais sont en grande partie caducs : le dialogue demeure une table de données, sans nouvel
  asset ni éditeur de dialogue.

#### D'où vient la question (2026-10-10)

Depuis la v0.21, un dialogue est une **table de données** dont une colonne est de type `text`
(`data.Dialogues[i].replique`) : le script la parcourt, et la réplique reste traduisible. Le modèle est
bon ; **la saisie est fastidieuse**. Pour écrire dix répliques, l'auteur doit :

1. créer la table dans l'écran Données et lui ajouter une colonne `text` ;
2. pour chaque réplique, aller dans l'écran Texte, créer l'entrée, la ranger, lui donner un contenu ;
3. revenir dans la grille, ouvrir la cellule de la ligne et y choisir la clé au milieu de toutes les autres.

Deux écrans, un aller-retour par réplique, et la clé (qui n'a d'intérêt que pour la machine) au centre du geste.
L'infobulle de la cellule montre bien le contenu (`_text_preview`), mais seulement une fois la clé posée.

#### Le principe

**Le pont ne crée pas de modèle.** Un dialogue n'est ni un nouvel asset ni un nouvel écran : c'est toujours une
`DataTable` et des `Text`, écrits par les commandes annulables qui existent déjà (`InsertRowCmd`, `SetCellCmd`,
`CreateTextForElementCmd`…). Le pont est un **geste** qui enchaîne ces écritures, pas une structure de plus. Il
tient la ligne posée dès la v0.3 : pas d'arbre de conversation, pas de choix branchés, pas d'éditeur de dialogue
(cf. [Table de textes](../../docs/development/ARCHITECTURE.md#textes-du-joueur--table-de-chaînes) et « Ce qui reste au script »).

#### Pistes (proposées, non verrouillées)

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

#### Ce que ça touche (provisoire)

| Fichier | Sort |
| --- | --- |
| `ui/data_editor/data_grid_panel.py` | `_DataCellDelegate` : l'éditeur de cellule `text` gagne l'entrée « Nouveau texte… » (piste B) |
| `ui/data_editor/data_commands.py` | une commande qui crée le texte et pose la cellule **dans une seule annulation** |
| `ui/text_editor/text_panel.py`, `text_table.py` | menu de la sélection : « Envoyer vers une table… » (piste A) |
| `ui/text_editor/text_commands.py` | `CreateTextForElementCmd` est le modèle à suivre : création d'un texte rangé, clé dérivée |
| `ui/screens.py` | aucune navigation entre écrans n'existe aujourd'hui : voir « À trancher » |

`core/models/text.py`, `core/models/data_table.py`, le checker, le build et la ROM ne bougent pas.

#### À trancher avant d'ouvrir

1. ~~A, B, ou les deux ?~~, **tranché le 2026-10-10 : les deux** (B puis A, voir « Pistes »).
2. **Le contenu s'écrit où ?** Avec la piste B, l'auteur crée la réplique depuis la grille : l'écrit-il dans la
   cellule (qui doit alors devenir un petit éditeur de texte) ou est-il renvoyé à l'écran Texte ? C'est la même
   question que « le contenu s'édite dans la table » du chantier [L'écran Texte n'édite et ne range que du contenu](#lécran-texte-nédite-et-ne-range-que-du-contenu-interface--livré-en-partie) :
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

#### Ce que ça ne fait pas

- Ne crée ni asset « Dialogue », ni écran de dialogue, ni arbre de conversation, ni choix branchés.
- Ne dit rien de l'enchaînement : *quand* une réplique s'affiche reste au script.
- Ne change ni `texts.json`, ni le format des tables de données, ni la ROM.

### L'écran Texte n'édite et ne range que du contenu (interface : livré en partie)

> **État au 2026-10-23, relu dans le code.** Livré : les blocs multi-lignes éditables (`text_entry.py`), l'aperçu écran masqué (l'atelier est caché dans `TextPanel`), la barre de balisage, le test d'aperçu retiré. **Pas fait** : le regroupement *par scène* (les blocs se rangent par clé), le bouton **Find**, la prévisualisation d'une traduction dans le canvas, et le retrait du code devenu mort (`FontScreenPreview`, aperçu et sélecteur de police de `TextWorkbench`, signaux `preview_font_*`, clés `txtwb.*`). Ces points sont dans le reliquat de la TODO.

#### D'où vient la question (2026-10-10)

L'écran Texte fait aujourd'hui deux métiers : **ranger et écrire** du contenu (la table, la clé, le
rangement, les langues, la barre de balisage), et **montrer le rendu GBA** de ce contenu (`FontScreenPreview`,
un écran 240×160 aux vrais glyphes, avec son sélecteur de police et son bouton « Afficher le balisage »).
Le second brouille le message du premier : l'œil va vers le rectangle noir, pas vers la liste qu'on est venu
mettre en ordre. Le rendu fidèle a servi à poser le pipeline des polices ; il a un autre lieu naturel (la
scène, l'écran Police). L'écran Texte ne doit plus chercher qu'**une chose : éditer et ranger le contenu**.

#### Le parcours visé (précisé les 2026-10-10 et 2026-10-17)

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

#### Ce que ça change pour l'auteur

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

#### Find (rejoindre le lieu d'usage (décision du 2026-10-17))

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

#### Le conflit avec l'ancien chantier

Ce chantier **remplace** « L'atelier Texte réuni, écrire et voir dans un même écran » (2026-09-19), qui
allait à l'opposé : faire du rendu GBA la surface d'édition (projection source ↔ affichage, caret et
sélection dessinés par `FontScreenPreview`, vue balisage en police moteur). Cette direction est abandonnée :
elle aurait fait de l'aperçu la pièce centrale de l'écran, là où l'on veut le retirer. Sa décision verrouillée
du 2026-09-19 tombe avec elle ; la section qui la portait n'est plus qu'un renvoi ici.

**Constat de code, à dire avant d'ouvrir :** l'ancien chantier était annoncé « aucune étape codée »,
mais `TextWorkbench` monte déjà `FontScreenPreview` en surface **éditable** (`set_editable(True)`, signaux
`edited` / `committed`) et y branche `MarkupToolbar`. Le code est donc à mi-chemin d'une direction qu'on
abandonne : l'état d'arrivée de ce chantier est désormais la liste de blocs éditables décidée le 2026-10-17.

#### Ce que ça touche

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

#### À trancher avant d'ouvrir

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

#### Ordre d'implémentation (proposé)

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

#### Ce que ça ne fait pas

- Ne retire pas le rendu fidèle de l'éditeur : il reste dans l'écran Police et en scène.
- Ne change ni `texts.json`, ni le format des traductions, ni la ROM.
- Dans cet écran, les blocs sont la surface d'édition du contenu ; les TextBox peuvent aussi éditer
  les mêmes entrées depuis la scène, conformément au chantier des pages de dialogue.
