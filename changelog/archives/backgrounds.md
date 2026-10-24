# Les fonds (0.5) - **LIVRÉ**

> **Chantier important 0.5.** Le texte ci-dessous est repris tel quel de [TODO](../../docs/development/TODO.md) au moment de la
> livraison : cinq sections écrites entre le 2026-09-26 et le 2026-10-23 (la compression d'un fond, le plan de travail, préparer
> une image riche, le Color Tile Painter, l'écran Fond). Les « reste à faire » qu'elles contiennent datent de leur rédaction ;
> ce qui est encore ouvert est repris dans [Fonds : ce qui reste après la livraison de la 0.5](../../docs/development/TODO.md#fonds-ce-qui-reste-après-la-livraison-de-la-05).

> **Livré le 2026-10-23.** Le plan de travail (taille du canvas, image posée, déplaçable et mise à l'échelle, aides
> Ajuster / Remplir / 1:1, passe-partout, miroir dans le canvas), la compression qui se joue (service d'encodage, jauges en
> direct, réglages contextuels), l'écran Fond (Inpainting, Painting, *Create empty*, *Save as PNG*) et la mise en cartes de son
> inspecteur ([détail](inspector-cards-relations.md)). **Non livré, classé à part** : la comparaison source/compressé.

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

### État au 2026-10-23

**Livré** : la taille du canvas, la position et la taille de l'image posée (`canvas_size`, `image_pos`, `image_size` dans le
sidecar), la carte *Canvas* de l'inspecteur, l'outil « select » (par défaut sur l'écran Fond) qui déplace l'image dans son
canvas, et les trois aides au placement **Ajuster / Remplir / 1:1** (validées à l'usage). Le miroir agit dans le canvas.

**Reste à faire** : la **comparaison source/compressé** (le « compress view » : barre verticale source d'un côté, version
compressée de l'autre, à la même grille) et la carte d'écart par tuile qu'elle rend possible. Aucun code de comparaison
n'existe encore dans `ui/background_editor/`. Le bitmap étendu au-delà de 240×160 (étude plus bas) reste une piste, non
commencée. Le détail des autres gestes de l'écran Fond livrés ce jour est dans
[les inspecteurs en cartes](inspector-cards-relations.md).

Le texte qui suit garde l'état de la conception telle qu'elle a été tranchée ; ses « À vérifier avant de coder » sont
levés pour ce qui est livré.

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

## Piste (préparer une image riche à l'import, recadrer et redimensionner sans toucher au PNG)

**Route vers v1.0-stable, non prioritaire pour la release `-alpha` (décidé le 2026-09-29).** Les tranches
4bpp et 8bpp sont livrées ; reste la tranche bitmap (son propre panneau, pas commencée) et la validation à la
souris dans l'éditeur.

### D'où vient la question (2026-09-26)

Une photo de 474×314 importée en tuilé 8bpp donne 2194 tuiles uniques pour un budget de 256 : le
Background Editor le **dit** (avertissement rouge « Exceeds VRAM ») mais ne laisse rien faire,
l'auteur n'a que le mode (tuilé/bitmap, profondeur) et un logiciel externe. Et le tuilé tronque
l'index de tuile à 10 bits (`pack_se`), donc au-delà de 1024 la carte se brouille en silence.

### Le principe

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

### Décisions verrouillées (2026-09-26)

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

### Mesurer le 4bpp avant d'y passer (2026-09-26)

Bouton « Analyser pour le 4bpp » dans l'inspecteur, sur l'image **préparée**, hors-thread :
couleurs par tuile (min / moyenne / max et répartition), tuiles qui tiennent en 15 couleurs,
jeux de couleurs distincts et tuiles qui en partagent un, palettes nécessaires, verdict « sans
perte » ou non. `bg_import.analyze_tile_colors` réutilise l'extraction et le packing de la
compression : le chiffre annoncé est celui que la compression trouvera. Les palettes comptées
sont celles des tuiles qui tiennent, sans la réduction, un minimum, pas une promesse.

### Jouer avec la compression (l'inspecteur contextuel (2026-09-26))

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

### Ce que ça ne fait pas

Pas d'annulation pas-à-pas (Ctrl+Z) : la recompression est asynchrone et « Original » suffit à
revenir. Pas de réglage de couleurs (le mode et la profondeur existent déjà dans l'inspecteur).

---

## Chantier produit à planifier (Color Tile Painter : commencer un niveau sans assets)

**Noté le 2026-10-12. Livré pour l'essentiel le 2026-10-14. Voir la section « L'écran Fond », ci-dessous ; le texte qui suit est l'état de départ, gardé pour mémoire.** Un auteur qui arrive sans
assets ne doit pas être bloqué avant même de pouvoir tester son level design. Ce petit outil lui
permet de composer vite un fond de prototype, jouable immédiatement, puis de le remplacer ou de
le retravailler plus tard avec ses vrais visuels.

### Le minimum utile

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

### Décisions déjà claires

- C'est un outil de **blockout**, délibérément limité aux aplats : ni pinceau libre, ni import
  d'illustration, ni retouche photo. Il ne remet donc pas en cause le refus d'un éditeur d'image
  généraliste.
- Le résultat suit le pipeline de fonds existant et ses contraintes GBA (palette indexée,
  transparence, tuilage) dès la première peinture : pas de conversion opaque au moment du build.
- Un fond créé ainsi reste un fond normal dans le projet ; l'export PNG est une sortie
  complémentaire, jamais sa seule forme sauvegardée.

### À trancher au démarrage

- Où placer l'entrée dans l'interface : mode du Background Editor, ou création de fond vierge
  depuis le navigateur d'assets.
- Les dimensions initiales et le comportement hors limites (agrandir le canevas, ou demander une
  taille à la création).
- L'annulation/historique de peinture, et les raccourcis pour le sélecteur, la gomme et les trois
  tailles de pinceau.

---

## L'écran Fond (ce qui est livré le 2026-10-14, et les pistes notées pour plus tard)

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
