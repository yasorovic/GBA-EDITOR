# Textes et polices

Les textes de l'éditeur (notices, libellés), la table de chaînes du joueur, le balisage et le pipeline des polices. Extrait d'ARCHITECTURE.md.

## Textes de l'ÉDITEUR — les notices, trois niveaux et un catalogue

À ne pas confondre avec la section suivante : celle-ci parle de ce que l'ÉDITEUR dit à son
utilisateur, l'autre de ce que le JEU affiche au joueur. Deux corpus, deux fichiers, deux
jalons (v0.11 et v0.9) — mais **la même grammaire**, et c'est délibéré.

**Deux catalogues frères, un seul cœur.** `ui/common/catalog.py` porte toute la mécanique —
maître `<nom>.json` + side `<nom>_<code>.json` joints par clé, repli sur la source quand une
entrée manque, pluriel `singular`/`plural` choisi par l'argument `n`, `format(**args)`, et un
`set_language(code)` global à tous les catalogues. Deux catalogues l'utilisent :

- **`ui/common/notice.py`** + `notices/notices.json` — le contenu INFORMATIF (constats,
  avertissements, astuces), qui porte un TON et un NIVEAU (voir ci-dessous).
- **`ui/common/labels.py`** + `labels/labels.json` — `label("clé", **args)` : tout le reste
  du texte visible (libellés de champs, titres de cartes et d'écrans, entrées de menu, états
  vides, boutons, et les `setToolTip` posés à la main). Un libellé n'a ni ton ni niveau —
  d'où un catalogue à part, plat, plutôt qu'un champ mort dans chaque entrée de notice.

Distinct de `core/project_langs.py` (les textes du JEU, couche `core`, id opaque) : ici on
est dans l'UI, et la clé est lisible. **La règle de nommage** est `<écran>.<slug>` en
snake_case, avec un préfixe `common.*` pour les atomes universels (browse, cancel, close,
open, create…) traduits une seule fois.

Ce que le catalogue de libellés ne reçoit PAS, délibérément : les libellés d'annulation (`SetFieldCmd label=…`, corpus à
part), les identifiants techniques (`int`/`bool`…), les noms de format (BGR555, PNG), les données de l'utilisateur et les
diagnostics reçus du cœur ou d'outils externes. [Le contrat des textes](docs/development/ui-text.md) précise les
exceptions et les limites du contrôle ciblé `tools/check_ui_text.py`, intégré au contrôle d'architecture.

**Le niveau est choisi par l'appelant, le ton est écrit dans le catalogue.** Le niveau est
une question de place dans l'écran ; le ton est une propriété du message. Les mélanger est
exactement ce qui produisait des `setStyleSheet(f"color:{C.ACCENT_YLW}")` posés au jugé, avec
deux messages de gravité opposée dans la même teinte.

```
note(layout, clé="")           1  une ligne sans cadre, sous un W.section()
notice(clé, ancre, layout)     2  info/accent → infobulle ; build/render → encadré
tip(clé, layout)               3  encadré à ampoule, coupé par Settings ▸ Interface
```

**L'interrupteur des astuces est un réglage d'APPLICATION**
(`core/interface_preferences.py`, à côté de `toolchain`/`external_tools`/`keybindings`), pas
un champ de `ProjectSettings`. Deux raisons, la seconde décisive : le manifeste
`<Nom>.project` est versionné, donc couper les astuces les couperait pour toute l'équipe ; et un réglage de
projet passe par `SetFieldCmd`, donc annuler une édition de scène rebasculerait une
préférence de machine.

Quatre tons : `info` (muet), `accent` (périwinkle — une PORTÉE, un renvoi ailleurs), `build`
(jaune ⚠ — le build va écarter ou rogner), `render` (jaune 👁 — ça s'émet, mais l'écran ne
montrera pas ce qui est authoré). **Une seule couleur d'alerte, deux icônes** : la même règle
que les familles d'icônes, « la forme, pas la teinte ». `ACCENT_RED` n'entre pas dans le
gabarit — il reste aux erreurs bloquantes du validateur et à la suppression, et un inspecteur
qui parle rouge banalise la seule couleur qui devait arrêter quelqu'un. Cela ne définit pas une
palette par famille d'asset : les types se distinguent par leurs formes, et chaque outil choisit
seulement les couleurs nécessaires à son propre fonctionnement.

**Seul le niveau 3 a le droit d'expliquer.** Les niveaux 1 et 2 disent ce qui est actionnable
et probablement non voulu ; ils ne commentent pas le matériel. C'est l'interrupteur qui rend
le niveau 3 acceptable : une explication optionnelle ne peut pas noyer un avertissement.

**Le catalogue reprend la grammaire des traductions du jeu** (`core/project_langs.py`) : un
maître qui porte la structure, un side `notices_<code>.json` qui ne porte que la traduction,
et **une entrée absente vaut la SOURCE, jamais une chaîne vide**. Une seule différence — ici
la clé EST la jointure, là où le jeu utilise un id opaque : la clé est écrite dans du Python
versionné, un id y serait illisible, et la renommer est un changement de code qui emporte les
sides dans le même commit.

Deux règles qui viennent de ce que la traduction exige, et qu'aucun test n'aurait imposées :

- **Le Python passe des VALEURS, jamais des morceaux de phrase.** L'ordre des mots n'est pas
  le même d'une langue à l'autre ; une phrase assemblée par concaténation n'est traduisible
  dans aucune. Un message composé injecte un autre message ENTIER, par `text()`.
- **Le pluriel est déclaré** (`singular`/`plural`, choisi par l'argument `n`), pas écrit
  `"s" if n > 1`. Un champ `code` porte l'expression Lua qu'un champ miroite ; il vit dans le
  maître seul, parce qu'une expression d'API ne se traduit pas.

`tools/check_architecture.py` vérifie les deux sens, pour les DEUX catalogues (notices ET libellés) : toute clé citée
existe, toute entrée est citée. Sans lui l'extraction se déferait toute seule — une clé mal tapée donne un message vide,
et **un message vide ne se plaint jamais**.

**Piège de mise en œuvre.** `label` est aussi un nom de variable tentant. Un `for k, label in …`
ou un `label = …` dans une méthode qui appelle par ailleurs `label("clé")` masque la fonction
importée et casse l'appel (`UnboundLocalError`) — invisible en statique, à la construction du
widget. On renomme la variable locale (`lbl`, `disp`, `lbl_key`…) dès qu'un `label()` vit dans
la même méthode.

## Textes du joueur — table de chaînes

`assets/texts.json`, modèle dans `core/models/text.py`. Un seul fichier maître plutôt
qu'un par entrée (contrairement aux palettes) : des centaines d'entrées courtes, qu'un
traducteur veut voir d'un coup. Chaque langue déclarée possède à côté un side
`texts_<code>.json`, partiel et joint au maître par `id` (cf. `core/project_langs.py`).

**Deux identifiants, un seul résolvable** — c'est la décision structurante :

| Champ | Rôle | Résolvable ? |
| --- | --- | --- |
| `id` | opaque (12 chiffres hexadécimaux), tiré une fois, jamais affiché | dans les **fichiers de données** — insensible au renommage |
| `key` | poignée lisible, ce qu'écrit un script Lua | oui, **au build** uniquement → index de table C, comme `SFX_*` |

`Text.path` existe, mais comme **propriété dérivée** : les segments de la clé, jamais stockés
Un libellé stocké à côté de la clé la dupliquait et se
désynchronisait au premier renommage qui ne le recalait pas. Le confort de lecture est rendu par l'UI —
autocomplétion et aperçu du contenu en ligne — pas par un second chemin de résolution.

**La clé situe, elle ne résume pas.** Elle est dérivée de la *place* du texte
(`village_garde`), jamais du contenu : le contenu est réécrit vingt fois pendant
l'écriture, la place dans le jeu bouge rarement. Une clé tirée du contenu
(`garde_je_suis`) devient un mensonge dès que le garde devient un mendiant.

**La clé porte la structure ; une seule règle, sans exception.** Chaque `_` de la clé ouvre
un niveau, et `Text.path` en est la liste des segments (`SCR_Arena_Page01` ↔ `SCR › Arena › Page01`).
Il n'existe ni libellé libre, ni clé « automatique » ou « nommée à la main » : **ranger, c'est
renommer la clé** —
- **renommer une clé** la change partout où elle est citée (scripts, zones d'interface,
  cellules de table, boîtes et séquences liées) ;
- **déposer un texte dans un autre dossier**, **renommer un dossier** du Library ou **éditer un niveau**
  depuis l'inspecteur calculent les nouvelles clés du lot (`Project.text_path_keys`) et les appliquent
  d'un coup (`rename_text_keys`, échanges compris) ; `SetTextPathCmd` les pose et les restitue à l'undo.
La même règle vaut partout où un nom devient un chemin : un nom de scène ou de TextBox
(`SCR_Arena`) ou un nom tapé s'éclate sur `_` (`SCR`, `Arena`), via `norm_path`, seul
point de conversion ; `key_segment` retire accents et espaces (`La forêt` → `LaForet`).
Une collision prend le rang `_2`, `_3`… (la règle unique `unique_name`).

L'arbre de l'écran Textes est une **vue** — `texts.json` reste plat (sans champ `path` ; un ancien
fichier se lit sans erreur), les nœuds sont dérivés à chaque reconstruction (rien à garbage-collecter,
diffs git lisibles, dep-graph inchangé). Contrepartie assumée : **pas de nœud vide**, créer un
rangement veut dire y créer un texte.

`_repair_texts()` rattrape un fichier édité à la main (id ou clé manquant/dupliqué, chemin mal formé) : l'id prime, c'est
l'identité ; une clé en double est celle qu'on renumérote.

Un `Text` est destiné au **joueur**, donc traduisible — c'est ce qui le distingue d'un
`string` technique (nom de fichier, code interne), qui reste un littéral dans le script.

### Le balisage est résolu au BUILD — aucun parseur en ROM

Une entrée peut porter des balises à la BBCode (`core/text_markup.py`) : ponctuelles
(`[speed=n]`, `[pause=n]`, `[icon=nom]`), de portée (`[wave]`, `[shake]`, `[color=n]`), plus
le marqueur de valeur `$nom`. Tout est résolu par `emit_texts_c`, qui sort **trois pistes** :
les codepoints affichables, une piste d'événements de tempo et d'effets, et la table des
sources à interpoler.

Trois gains, et c'est ce qui justifie de tout faire au build : `text.length` reste la
longueur *affichée*, le moteur n'embarque pas de parseur, et un littéral écrit dans un
script suit exactement le même chemin puisque le codegen le voit aussi.

**Un `$nom` a trois sorts, et c'est ce qui garde l'encodeur simple :**

| Ce que `$nom` désigne | Ce qui est émis |
| --- | --- |
| une **constante** | ses chiffres sont **cuits** dans les codepoints — elle ne change jamais, la lire au runtime coûterait une indirection pour rien |
| un **global** | une place réservée (le non-caractère U+FFFF, donc jamais un vrai glyphe) + un **pointeur** vers la variable C. Un pointeur et pas un index : `globals.h` déclare des variables nommées, pas les cases d'une table |
| **ni l'un ni l'autre** | écrit littéralement, exactement comme l'aperçu de l'éditeur le montre, et signalé dans le log de build |

La substitution passe par une **réécriture de la source suivie d'une ré-analyse**, jamais
par un rapiéçage du résultat : une constante vaut « 7 » comme « 100 », donc décale tout ce
qui suit — recalculer les positions à la main les ferait diverger au premier oubli.

**Au runtime**, un texte porteur de valeurs est recopié en RAM avec les chiffres substitués
(même procédé que l'affichage d'un nombre, donc un seul chemin de rendu). Les positions des
événements se décalent d'autant : une **carte index source → index matérialisé** les recale
toutes en une fois, plutôt qu'un rattrapage au fil de l'eau qui devrait rejouer à la main
les portées à cheval sur une valeur.

**La tête de lecture appartient à la ZONE, pas à l'appel** — c'est la raison pour laquelle
le tempo est ignoré par un `text.draw` à coordonnées libres : une tête doit s'accrocher à
quelque chose de nommé. Un texte sans marqueur de tempo s'affiche entier, immédiatement : ne
pas en mettre est une décision d'auteur, pas un oubli à compenser par une vitesse par
défaut. Et `zone:draw` est **idempotent** tant que la lecture court, sinon un appel depuis
`on_update` la relancerait soixante fois par seconde et le texte n'avancerait jamais.

`[color=n]` ne fonctionne que sur les chemins COMPOSÉS : le chemin tilemap pose une tuile
déjà encrée et partagée par toutes ses occurrences, la recolorer recolorerait le texte
entier. Signalé aux deux endroits qui peuvent le savoir, le build et l'inspecteur. La plage
1..15 est une contrainte matérielle (4bpp, l'index 0 est la transparence), pas un choix.

## Polices — un asset, deux points d'entrée

`core/models/font.py` + `core/font_import.py`, sidecar à côté de la source dans `assets/fonts/`. Les sources bitmap sont un
**PNG nu** ou un **BMFont `.fnt`** ; les sources vectorielles **TTF**/**OTF** reçoivent leur sidecar dès que le watcher les voit,
sans fabriquer de planche : `core/font_rasterizer.py` les lit à la demande avec FreeType, pour l'aperçu comme pour le build. Sa
sortie `RasterGlyph` est une grille de couverture indépendante des tuiles et de la palette GBA. Un format d'entrée n'est qu'une
façade sur le même sidecar (comme `detect_import_mode` pour les fonds).

`build_font_asset` passe une table `faces` à travers la rasterisation : chaque fichier source n'est chargé qu'**une fois** pour tous
ses glyphes (locale à l'appel, aucun état de module), et l'extraction de couverture est **vectorisée** (numpy).

Une `FontAsset` porte sa politique `pixel_fit` : `auto` choisit une bitmap strike seulement si elle correspond exactement à la
hauteur demandée, sinon aligne sur la grille à 6 px ou moins et garde le rendu natif au-dessus ; `native`, `grid_fit` et
`bitmap_strike` sont des choix d'auteur. La recette est déterministe dans l'aperçu et reprise telle quelle par le build.

**Découverte : une source, un usage possible.** À l'apparition d'un PNG, `.fnt`, TTF ou OTF, `sync_font_file()` crée ou réconcilie
un `FontAsset` (les sources bitmap reçoivent un asset du même nom ; les vectorielles de même famille fusionnent leurs faces natives
dans un seul). La réconciliation complète les faces ou retire les références disparues, sans jamais remplacer les paramètres de
rasterisation ni les fallbacks de l'auteur. Elle distingue deux échecs : **dur** (format illisible, planche introuvable) → aucun
asset créé ; **mou** (planche lisible, aucun glyphe) → asset créé avec avertissement. `reconcile_fonts()` traite les `.fnt` d'abord :
le descripteur fait foi et sa page ne crée pas de doublon.

Un TextBox référence la police logique par `font_name` (le nom d'un `FontAsset`) et son `font_weight` natif (400, 700…). Un ancien
fichier qui cite une source reste lisible : le sélecteur propose l'asset qui la contient sans réécriture silencieuse.

**Le modèle est à rectangles, pas à grille.** Chaque `Glyph` porte son rectangle dans la planche, ce qui accueille BMFont (glyphes
posés librement) ; une planche régulière est le cas où tous les rectangles sont identiques, `cell_w`/`cell_h` ne restant qu'une aide.

- **Le charset n'est pas un champ** : c'est `"".join(g.char for g in glyphs)`, une seule source de vérité.
- **PNG nu = cas dégradé** : `detect_grid()` note les découpages réguliers (un nombre de cases d'un charset connu pèse le plus
  lourd, puis les cellules carrées, puis les multiples de 8) et `propose_charset()` fait une première attribution, corrigeable. Les
  cases vides **en fin** de planche sont du bourrage ; une case vide *au milieu* est légitime (l'espace).
- **`.fnt` = rien à deviner** : codepoints, rectangles, `xadvance` et `lineHeight` sont déclarés, et `xadvance` prime sur toute
  mesure d'encre. Formats texte et XML ; le binaire lève une erreur explicite plutôt que de produire une police vide.
- **`advance`** a trois sources, par ordre d'autorité : le `xadvance` d'un `.fnt`, sinon le marqueur d'espacement désigné à la
  pipette, sinon **mono** (chasse = cellule). Pas de repli sur une mesure d'encre : sans flanc déclaré, une chasse proportionnelle
  colle les lettres, là où du mono reste lisible.
- **`tile_count()`** donne le coût VRAM en tuiles 8×8 (dans le charblock du layer d'UI, en concurrence avec le décor).
- **`missing_chars()`** croise une police avec un texte et signale les caractères manquants *avant* la console (par exemple un `ß`
  qu'apporte une traduction).

### Du sidecar à la ROM

```
assets/fonts/ (Font, source) ─┐
                               ├─ FontAsset ─→ RasterGlyph ─→ tuiles + palette 4bpp ─→ ROM
assets/fonts/fonts_assets/ ───┘       ↑              ↑                  ↑
                                  recette auteur   preview/build     rendu + budget VRAM
```

`codegen/font_build.py` résout la chaîne de sources d'un `FontAsset` et le
matérialise temporairement en glyphes raster. Rien de cette étape n'est persisté.
`codegen/font_emit.py` encode ensuite ces mêmes glyphes en tuiles 4bpp et émet
les tables C ; `main_gen` les pose dans `main.c` et charge la police au début de
chaque scène. Les vieilles sources bitmap non encore couvertes par un FontAsset
continuent de passer par l'encodeur historique, afin de garder les projets
existants ouvrables.

- **Une seule matérialisation par état de projet.** La représentation de build
  est mémorisée et invalidée si une recette, un texte, une traduction ou le
  fichier source change. L'allocateur, l'émetteur et le canvas ne rerastérisent
  donc pas chacun leur propre copie de la police.
- **La sortie est décidée au dernier moment.** Binaire et tramage donnent une
  encre binaire ; le mode couverture est quantifié sur les 15 index d'encre
  utilisables d'une palette 4bpp. `RasterGlyph` reste lui une couverture 0..255
  jusqu'à cet instant.
- **Le budget lit les mêmes glyphes.** `is_proportional()`,
  `render_composited()` et `font_vram_tiles()` travaillent sur la police
  matérialisée. Une police à chasse proportionnelle réserve ainsi la surface de
  composition ; une police mono réserve ses tuiles de glyphes. Ce n'est pas une
  estimation séparée de l'encodage.

- **Un glyphe → `tiles_x × tiles_y` tuiles** (une seule pour du 8×8), déposées à la suite dans le charblock du texte. Leur base
  vient de l'allocateur de charblock (`text_set_tile_base()`, `codegen/vram_alloc.py`), qui glisse le texte dans les trous du
  décor ; `FONT_TILE_BASE_DEFAULT = 1` n'est que le repli. La tuile 0 reste vide (celle de `text_clear()`). La palette d'une police
  libre est chargée dans une banque allouée ; `Scene.font_pal_banks` peut la remplacer par une banque BG de la scène, héritée par
  les zones d'un conteneur.
- **Deux chemins de rendu, choisis par la donnée.** `font_emit.is_proportional()` /
  `render_composited()` décident, et `FontInfo.composited` désigne le CHEMIN, pas la
  typographie. *Tilemap* : les tuiles de glyphes vont en VRAM, écrire du texte revient à
  poser des index — coût nul par appel, mais plafonné à un charblock. *Composition* : les
  glyphes restent en ROM et servent de source, le moteur compose pixel par pixel dans une
  surface de tuiles. Le second est pris dès qu'il est moins cher (police
  proportionnelle, ou plus de ~240 tuiles de glyphes — c'est ce qui rend une police CJK
  possible). Chasses, interligne et avance de secours sont émis **déjà résolus**
  (`font_line_px`, `font_fallback_adv_px`) : sans ça, basculer de chemin changerait
  l'interligne en silence.
- **La surface de composition est allouée PAR ZONE, pas partagée.** Une zone authorée a un rectangle connu au build :
  `scene_text_reservation` lui donne son propre bloc (`surf_layout` → `text_set_region_surf`, `RegionSurf` dans `gba_engine.h`), et
  l'adressage borné (la branche `g_blit_h != 0` de `text_surf_tile`) tronque hors cadre au lieu de replier chez le voisin. La surface
  PARTAGÉE de 240 tuiles, adressée `(tx % 30, ty % 8)`, ne subsiste que pour l'**écriture libre** (`text.draw`, `text.clear`), et
  n'est réservée que si un script de la scène en appelle une (`font_emit.scene_writes_free`). Partagée, elle faisait s'écraser en
  VRAM un titre en haut et une boîte en bas ; le coût suit désormais ce que l'auteur déclare, et un dépassement est une erreur
  d'allocation franche.
- **Le remplacement de la police par langue entre dans cette décision** : la police par défaut peut rester une Font8x8 latine et être
  remappée vers Misaki pour le japonais (`g_lang_font`). `region_is_composited()` examine donc toutes les polices EFFECTIVES de la
  zone ; si l'une est composée, `scene_text_reservation()` crée son `surf_layout`. Résoudre la langue au seul runtime donnerait une
  police bien choisie mais sans l'espace VRAM où composer ses pixels. Le canvas lit la même règle.
- **La banque d'encre d'une police est un réglage de scène persistant** : `Scene.font_pal_banks` associe une police logique à une
  banque BG (la clé vide désigne la police par défaut), lu par l'inspecteur, l'allocateur de palettes, le canvas et
  `text_set_font_pal()`. Une banque propre reste l'absence de clé.
- **Un texte est émis en codepoints `u16`, pas en glyphes.** La correspondance
  caractère → tuile se fait au runtime, par dichotomie sur la table triée de la police
  courante. C'est ce qui rend un texte **indépendant de la police** : une traduction peut
  exiger un autre jeu de glyphes. Le coût est une recherche par caractère à l'affichage,
  pas par frame.
- **Le slot BG d'une zone appartient à son nœud `Interface`, par scène** : chaque `InterfaceNode.bg_slot` dit où SA zone se
  rend ; `scene_init` installe une table de routage (`scene_route_region`/`scene_route_image`) que le rendu lit au lieu
  d'un layer global. L'API texte n'a pas de paramètre `layer` : la zone porte le sien, et l'écriture libre (`text.draw`)
  garde un layer courant par défaut, posé au premier slot d'UI de la scène. Cf. « Éléments d'interface ».
- **Une seule police résidente** à la fois : `text_set_font()` recopie glyphes et palette
  en VRAM. C'est un appel délibéré, pas un coût par frame.
- **Celle que `scene_init` charge est `Scene.font_name`**, et `font_emit.scene_default_font()` est le point UNIQUE qui la résout
  (émission, réservation VRAM, sous-ensembles de glyphes, validateur de débordement, aperçu du canvas) : réserver pour une police
  et en charger une autre écrit le texte DANS le décor, sans erreur avant l'exécution. `""` ou un nom introuvable retombent sur la
  première police encodable (le second cas est un avertissement du validateur).
- L'ordre des tables fait foi : `project_fonts()` (dans `main_gen`) est la source unique
  dont `lua_compiler` dérive les `#define FONT_*`, et l'ordre de `project.texts` donne les
  `TEXT_*`. Les deux côtés doivent voir la même liste, sinon un script pointerait sur la
  mauvaise entrée.
- **`project_fonts()` n'émet que les polices UTILISÉES** : `project_used_font_names()` fait l'union, sur toutes les scènes, de
  `scene_font_names()` (mise en page + `text.set_font`, plus la police par défaut de la scène) et de la police par défaut de chaque
  langue (`Language.default_font`). Une scène indécidable (police choisie au runtime) fait retomber sur `None` → toutes les polices
  encodables, sans élagage. `encodable_project_fonts()` reste la liste NON élaguée, que l'éditeur utilise pour remplir un sélecteur
  encore vide (`scene_inspector._reload_scene_font`).

Une clé de texte ou un nom de police inconnus sont une **erreur** de checker, pas un
avertissement : le `#define` n'existerait pas et la compilation C échouerait de toute
façon, avec un message bien moins clair.
