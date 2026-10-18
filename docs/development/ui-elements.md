# Éléments d'interface (`UILayout`)

Le détail de `UIText`, `UITextbox`, `UIContainer`, `UIList`, `UIImage` : nœud et asset, chemin BG/OBJ, fonds, couleurs, listes. Extrait d'ARCHITECTURE.md.

## Éléments d'interface — `UIText` / `UITextbox` / `UIContainer` / `UIList` / `UIImage` dans un `UILayout`

### Séquences de textes — dérivées, liées ou libres

`core/text_sequences.py` ne stocke rien. Les textes dont la clé finit par un segment numérique
(`Dialogue_1`, `Dialogue_Page01`) et qui partagent le même préfixe forment une **séquence** dès
deux textes, ordonnée par la valeur du numéro. Elle est **liée** quand un consommateur la cite,
**libre** sinon. Deux consommateurs : une `DataTable` (`text_link = {prefix, column}`) et une
`UITextbox` (`sequence_prefix`). `Project.textbox_pages(box)` dérive les pages de la boîte à
chaque lecture (sa séquence, sinon son `text_key`) ; `region_text`, `region_texts`, le validateur,
l'index des usages et la réservation des polices passent tous par elle. Aucun `page_ids`.

La table garde ses lignes (les autres colonnes sont à l'auteur) : `CommandHistory.after_execute` est branché par le dispatcher
sur `sync_linked_tables`, qui réaligne les lignes sur la séquence dans la MÊME entrée d'historique et rend de quoi les restaurer
à l'undo — aucun bouton « mettre à jour ». Un groupe renommé d'un bloc emporte ses consommateurs (`Project.consumers_follow`,
autour de `rename_text_key(s)` et de `SetTextPathCmd`) ; un groupe éclaté les laisse et la synchro retire les lignes.

L'écran Texte monte un en-tête par séquence (`TextEntryGroup` + `SequenceTableBar`) : son état (reliée à une table / libre) et,
si libre, de la relier ou de créer une table ; `+` ajoute le texte suivant (`next_key`, numéro max + 1), `−` supprime l'entrée.
L'inspecteur de TextBox (`inspectors/textbox_sequence.py`) lie à une séquence (le champ de texte unique s'efface) ou délie.

`core/models/ui_region.py`, stockage dans `assets/ui_layouts/<nom>.layout`. Un élément de
texte répond à **où** le texte se pose ; il remplace les arguments de géométrie que
`text_draw_box` prenait dans le script, donc invisibles depuis l'éditeur et incalculables
avant le build.

**Cinq types, deux familles.** Les **briques de base** : `UIText` (une chaîne posée en un point : une ligne, jamais coupée ni
alignée), `UIContainer` (le groupe) et `UIImage` (un sprite à état). Les **assemblages**, qui rangent selon une règle : `UIList` (un
conteneur qui se PARCOURT) et `UITextbox` (le rectangle est la largeur de coupe, le texte s'y aligne) — la distinction d'une chaîne
et d'une boîte de texte ; le menu d'ajout la montre en deux sections (`KINDS_BRICK` / `KINDS_ASSEMBLY`). Les deux types de texte
partagent la même entrée de `g_ui_regions` ; seul `UIRegionInfo.nowrap` (émis depuis `UIText.wraps`) change le rendu. Un ancien
`kind: "text"` sans marqueur `point` se relit comme une **boîte** ; seule la chaîne écrit `point`. Toute question « cet élément
porte-t-il du texte ? » passe par `is_text`, jamais par `kind == KIND_TEXT`. Le type « zone de texte » a été RETIRÉ : **un `UIText`
sans `text_key` EST une zone qu'un script remplit** (`KIND_REGION` ne survit que comme alias de désérialisation ; l'espace de
constantes reste `REGION_*`).

**Deux capacités traversent ces types, et ce sont elles que le code interroge.**
`can_contain` dit ce qu'un type accueille (un tuple de kinds : rien pour une feuille, tout
pour un conteneur, `KIND_TEXT` seul pour une liste dont les enfants SONT les rangées) ;
`can_fill` (le mixin `FillMixin`) dit ce qui dessine un fond. Les émetteurs demandaient
`kind == KIND_PANEL` — juste tant qu'un seul type portait un fond, faux le jour où la liste
en a gagné un. Une capacité se déclare sur le type et se lit partout ; un test de type se
réécrit à huit endroits et en oublie un.

**Une zone ne dessine rien** — même contrat que la window matérielle : elle dit où, jamais à quoi ça ressemble. D'où le mot
« région » et non « frame » (qui promettrait une image de bordure 9-slice et collisionnerait avec les frames d'animation).

**Ce qui reste au script** : la zone porte la géométrie, pas l'enchaînement. Rien ici ne dit quel texte s'affiche quand — c'est ce
qui empêche l'objet de devenir un éditeur de dialogue par accident.

### Le chemin matériel appartient au NŒUD, pas à l'élément (v0.25)

L'ancrage (`anchor`) et la cible (`target`) ne vivent pas sur chaque élément : ils sont portés par le nœud `Interface`
(`UILayout`), une seule fois, et **tout le sous-arbre en hérite** (`effective_anchor()` / `resolved_target()`). Une capacité qui se
lisait comme un cas particulier de chaque élément devient une propriété de son propriétaire, à source de vérité unique ;
l'élément ne porte que sa géométrie.

Ces deux réglages ne sont pas libres — ils contraignent la mémoire :

| Ancrage | Comportement | Cible |
| --- | --- | --- |
| `screen` | fixe sur 240×160 (HUD, boîte basse) | BG |
| `world` | défile avec la caméra (conteneur posé dans le décor) | BG |
| `actor` | suit un acteur à l'offset près (bulle) | **OBJ, sans alternative** |

Un actor bouge au pixel, la grille BG avance par 8 : une bulle en texte BG sauterait par crans de 8 px. C'est une impossibilité,
pas une préférence — d'où `forced_target()`, calculé **une fois sur le nœud** ; l'inspecteur du nœud (`UINodeInspector`) affiche la
cible imposée ET sa raison (notices `ui.anchor.forced_*` : une contrainte muette se lit comme un bug de l'éditeur). Même mécanique
pour une scène en mode bitmap (plus de tilemap, donc OBJ). `target` ne porte une valeur que lorsque l'auteur a fait un choix réel.

Une scène qui a besoin de deux chemins pose **deux nœuds** `Interface` (un HUD fixe en BG, une bulle actor-OBJ). Basculer un nœud
d'une cible à l'autre transfère la charge entre **deux budgets disjoints** — VRAM BG (64 Ko, `codegen/vram_alloc.py`) et VRAM OBJ
(32 Ko) — ce qui est l'échappatoire quand un charblock est plein.

### Le slot BG appartient à l'INSTANCE dans la scène, pas à l'asset (v0.12)

Chaque interface doit pouvoir se ranger indépendamment dans la pile de composition du Scene Tree (contexte **Priority**) : le
principe qui tranche est de **distinguer un asset de sa cible de rendu, et le z-order en fait partie**.

- **`InterfaceNode`** (`models/ui_region.py`, le pendant de `BackgroundLayer`) est l'instance d'un layout DANS une scène :
  `{layout_name, anchor, anchor_actor, target, bg_slot}`. Le champ **par-scène** en vigueur est `bg_slot`, le slot BG où
  l'interface se compose (il remplace l'ancien `Scene.text_bg` unique) : un HUD partagé peut être sur BG0 dans une scène et BG2
  dans une autre. `BoundInterface` est la vue COMPOSÉE que rend `scene_ui_layouts(scene)` : contenu délégué à l'asset, `bg_slot`
  lu du nœud ; `anchor`/`target` restent lus de l'**asset** (les lire du nœud figerait une valeur périmée dès qu'on édite l'asset).
- **Routage de rendu par scène.** Les tables de contenu (`g_ui_regions` / `g_ui_images`, indexées par nom d'élément UNIQUE au projet,
  d'où l'ABI `REGION_*`/`IMAGE_*`) restent per-asset ; c'est la **cible** qui sort en table de routage par scène : `scene_init` pose
  `scene_route_region(r, slot)` / `scene_route_image`, et `text_draw_in`, l'effacement, les listes et `ui_image_update` lisent le
  slot du nœud (`region_layer_of`). L'écriture libre garde `text_set_layer`.
- **VRAM multi-slot** (`vram_alloc.scene_layout(..., ui_slots=…)`) : une map (SBB) par slot d'UI utilisé, les **glyphes partagés**
  dans un seul charblock ; `dispcnt`/`bg_cnt` activent chaque slot.
- **Édition.** L'inspecteur du nœud porte un combo **BG slot** (les slots que le mode vidéo expose, masqué en OBJ) ; le contexte
  Priority range chaque nœud sous son slot, et le glisser d'un Background à l'autre change `bg_slot`. Le z-order du canvas suit
  ce slot (`hw_layer_z`).
- **Validation** (`_check_ui_node_slots`, `_check_bg_text_cbb_conflict`), en erreur : slot indisponible dans le mode vidéo
  (`BG_SLOTS_BY_MODE`) ; même layout posé deux fois dans une scène (collision de noms d'élément) ; interface partageant son slot
  avec un décor (charblock écrasé).

**Ouvert — routage par nœud de `anchor`/`target`.** Les champs existent sur `InterfaceNode` mais sont DORMANTS : ils
restent per-asset. Les router par scène demande la copie vivante runtime portant target/anchor et, pour la divergence
**BG↔OBJ**, d'émettre le placement OBJ inconditionnellement, de réconcilier la géométrie BG/OBJ et de résoudre l'`actor`
PAR scène — vérifiable seulement sur un vrai build ROM. Reporté à un chantier dédié.

### Tout en pixels, une seule unité

Le BG exige un alignement à la tuile, mais c'est `snap_to_tile()` qui le pose, pas le
format de stockage — sinon le sens d'un champ dépendrait de la cible. La taille est
arrondie vers le **haut** : rogner reviendrait à couper du texte pour faire joli.
`tile_rect()` arrondit vers l'extérieur, parce qu'un glyphe posé à x=13 mord sur la
tuile 1 et qu'elle fait partie de l'empreinte — exactement comme `text_layout` arrondit la
sienne avant de préparer la surface.

**Pas de `FieldValue` ici, volontairement.** Les champs numériques de composant acceptent
une référence de variable ; une zone ne le peut pas. Tout l'intérêt de déclarer la
géométrie est que l'empreinte VRAM soit connue **avant** le build ; une position qui ne se
connaîtrait qu'au runtime rendrait ce chiffre faux, c'est-à-dire pire qu'absent. Une
position calculée reste possible par `text:draw(x, y, …)`, qui ne disparaît pas.

`w` est **aussi** la largeur de coupe. Un champ séparé garantirait qu'un jour les deux
divergent.

### Un nœud est un asset, pas une donnée de scène — et une scène en référence PLUSIEURS

`UILayout` est rangé dans `assets/ui_layouts/` et référencé par nom. Une scène en référence
une **liste de nœuds** (`Scene.ui_layouts`, désormais `list[InterfaceNode]`, v0.12) : chaque
nœud est l'INSTANCE d'un layout dans cette scène, et porte sa `bg_slot` (cf. la sous-section
suivante). Une même scène peut poser un HUD-BG et une bulle actor-OBJ côte à côte. Une boîte
dessinée une fois sert les quarante scènes du jeu et se corrige en un endroit — d'où le
partage : éditer un élément depuis le canvas modifie un objet **partagé**, et
`ui_layout_users()` alimente le badge « partagée — N scènes », sans quoi on casserait N
scènes en croyant en ajuster une.

Les formes anciennes — `Scene.ui_layout` (nom unique), puis une liste de NOMS — se relisent, seule la liste de nœuds
s'écrit (*une forme ancienne se lit, une seule s'écrit*, `_ui_nodes_from_dict`).

`Project.scene_ui_layouts(scene)` résout la liste ; `scene_ui_slots` / `scene_ui_images` /
`scene_ui_elements` en donnent les paires `(nœud, élément)` que les émetteurs **par scène**
itèrent (codegen, validateur, jauge OAM). `scene_ui_layout` (singulier) subsiste pour le seul
cas où « un défaut » suffit — l'outil widget dépose un élément dessiné dans le nœud PRIMAIRE
(le premier). Les tables projet-globales (`all_regions` / `all_images` / `all_elements`)
itèrent, elles, TOUS les nœuds du projet : un nœud orphelin (référencé par aucune scène)
émettrait donc quand même ses `REGION_*`/`IMAGE_*` — c'est pourquoi supprimer le dernier
usage d'un nœud emporte l'asset (`DeleteInterfaceCmd`).

### Du canvas à la ROM

`project.all_regions()` donne l'ordre **stable** qui devient l'index dans la table C
`g_ui_regions` (`font_emit.emit_ui_regions_c`), et `api.region_constant()` les `REGION_*`.
Un nom de zone inconnu est une **erreur** de checker (`DOMAIN_REGION`), pas un
avertissement.

Le runtime a deux chemins, choisis par `UIRegionInfo.target` — un drapeau **par entrée**, émis au build en résolvant
`resolved_target()` du NŒUD porteur : le runtime ne connaît aucune notion de « nœud », juste des entrées à la cible déjà tranchée.

- **BG** — `text_render_cp_al()` avec la position, la largeur de coupe et l'alignement de la zone : le chemin libre, avec une
  géométrie qui vient d'une table. Seule la hauteur de boîte (`R->h`) s'ajoute : une zone AUTEURE prépare toute sa boîte avant de
  composer, sinon un texte plus court que le précédent laisse l'encre de l'ancien rendu hors de la nouvelle étendue. L'écriture libre
  (`text_draw`) garde l'étendue mesurée seule. Préparer n'est pas SURLIGNER : seule l'étendue rendue reçoit le surlignement.
- **OBJ** — la zone est couverte d'une **bande de sprites** de 8 px de haut, où le texte se compose par le même code (seul le bloc de
  destination change). Blocs de 8 px et non un sprite par ligne : l'interligne vient de la police, qu'un script peut changer, donc
  une allocation qui en dépendrait ne serait pas calculable au build. `strip_columns()` découpe en 32/16/8 px (**un OBJ 64×8
  n'existe pas**) et `text_strip_col` doit reproduire ce découpage à l'identique.

Le placement OBJ (`layout_obj_budget`) est **relatif** à la mise en page (une même mise en page sert plusieurs scènes, qui n'ont pas
la même base) : `text_obj_set_base()` reçoit la base absolue à l'init de scène ; à −1, les zones OBJ ne s'affichent pas plutôt que
d'écrire dans les sprites des acteurs.

`animated_glyphs` est **déclaré, jamais déduit** : quel texte atterrit dans une zone est une
décision de script prise au runtime, et une portée d'effet change de longueur avec le
texte. Le build ne peut que réserver ce que l'auteur annonce ; au-delà, le runtime **écrête**
et les glyphes en trop rendent en statique dans la bande. Un effet qui dégrade est une perte
cosmétique, un dépassement d'OAM corrompt les sprites des acteurs.

### API et surface d'édition

| Lua | Effet |
| --- | --- |
| `zone:draw(id)` (`interface:get("zone"):draw(id)`) | le texte de la table dans la zone |
| `text.draw_in_upto(zone, id, n)` | idem, n premiers caractères (machine à écrire) |
| `text.draw_num_in(zone, valeur)` | un nombre, aligné et polices héritées — **intérimaire** |
| `zone:clear()` | vide la zone, BG **ou** OBJ |

**Grammaire : conteneur (ou position) d'abord, contenu ensuite**, pour toute la famille `text.*` (c'est le contenu qui grandira avec
les valeurs interpolées, pas la géométrie). L'ordre est le même en Lua et en C parce que `codegen._emit_api_call` mappe les arguments
par **position** ; tous étant des `int`, le compilateur ne verrait pas une permutation, d'où `validator._check_api_prototypes`, qui ne
signale que les *permutations* (un renommage délibéré reste juste sur le fond).

`text_render_region_cp()` prend une suite de codepoints et non un id de table (la table n'est qu'une source parmi d'autres ; un
second chemin pour les nombres dériverait du premier). `text_clear_in()` applique **la police de la zone avant d'effacer** : une
police composée range ses pixels dans les tuiles de surface, une mono pose des index dans le tilemap, et effacer avec la police
d'à côté vide le mauvais des deux.

Côté éditeur : outil « Widget d'interface » (T) au canvas de scène — un bouton, trois types au dropdown (zone /
conteneur / texte), même geste rectangle, création du nœud à la volée si la scène n'en a pas (`UIWidgetTool` +
`create_element`, qui dépose dans le nœud primaire). `UIList` et `UIImage` se créent depuis l'arbre de scène. `UIRegionItem`
est déplaçable avec snap 8 px en BG et 1 px en OBJ ; les descendants d'un conteneur suivent visuellement pendant le drag
(leur modèle est relatif au parent) ; `MoveUIRegionCmd` est annulable et fusionnable.

**Deux inspecteurs, deux niveaux.** Le NŒUD (`UINodeInspector`, `UILayoutSelection`) porte ancrage, cible et badge de partage (clic
sur la racine « Interface »). L'ÉLÉMENT (`UIInspector`, `UIRegionSelection`) porte la géométrie ; il **lit** la cible héritée
(`resolved_target`) pour adapter le pas de grille et le fond, sans menu qui la change. Le nom se change dans l'en-tête partagé
(`AssetHeaderBar`).

**L'arbre vit dans l'arbre de SCÈNE** (`scene_tree_panel.py`) : sous chaque scène, un nœud racine par `Interface` référencé
(`_populate_ui_branch`), étiqueté « Interface » s'il est seul, par son NOM sinon, avec un badge « — N scènes » quand il est partagé.
L'arbre montre ce qu'un **script Lua peut référencer** (un actor, une zone) en clair, et un conteneur ou un texte authoré en grisé. Le
**+** crée un nœud (nouvel asset, `_add_interface`) ; son menu ajoute un widget ou le supprime (`DeleteInterfaceCmd` : retire la
référence et emporte l'asset si plus aucune scène ne l'emploie). Création, réordonnancement, renommage et suppression des éléments s'y
font aussi (`Project.rename_ui_element` ; `Project.rename_ui_layout` pour un nœud : fichier + refs de toutes les scènes).

**Z-order = ordre de `elements`** (frère tardif au-dessus), lu par trois consommateurs : l'arbre, le canvas (base `_hw_layer_z` du
layer matériel, plus un offset : l'indice du NŒUD dans la scène, puis l'ordre d'arbre en fraction — parent sous ses enfants) et le
codegen (ordre de dessin des fonds). Un réordonnancement (Monter/Descendre, ou drop entre deux frères, qui porte le parent visé ET la
position) réécrit `elements` en DFS canonique (`UILayout.move_sibling` / `place_child`) sous une commande snapshot
`UILayoutOrderCmd`, pour que les trois s'accordent. `preview_text` affiche une entrée réelle dans le canvas (`FontScreenPreview`
rejoue `text_layout` avec les vrais glyphes contre le rectangle de la zone) : le débordement se voit **à la conception**.

### Réservation VRAM du texte — pourquoi tout retombe sur `None`

Une mise en page **déclare** les polices que la scène pose (`layout_font_names`) et un script
peut en charger d'autres (`text.set_font`, repéré par DOMAINE) : `scene_font_names` croise les
deux, ce qui rend la réservation calculable **par scène** au lieu du maximum du projet.

La règle de sûreté qui explique tous les `None` du code est **asymétrique** : réserver trop
coûte des tuiles au décor, réserver trop peu fait écrire le texte DANS le décor sans une
erreur avant l'exécution. `scene_font_names` rend donc `None` dès qu'une police est choisie au
runtime, qu'un script est introuvable ou en C natif, ou que luaparser manque. **`None` veut
dire « je ne sais pas », jamais « rien »** — et `scene_text_tiles(fonts, names=None)` retombe
alors sur le projet entier. Un ensemble vide DÉDUIT (« aucune police déclarée ») et un
ensemble inconnu sont deux choses différentes ; les confondre ferait réserver zéro.

Même raisonnement pour `scene_codepoints`, qui restreint le sous-ensemble de glyphes chargé.

**Ce qui est réservé est ce qui est chargé, et ça se dérive d'un seul calcul.** Le sous-ensemble de glyphes d'une scène est
l'UNION de toutes les langues déclarées (`scene_codepoints_union`) : c'est ce qui permet à `lang.set` de recharger une scène
dans une autre langue sans reconstruire la police en VRAM. `text_set_font` recopie ce sous-ensemble **entier** quelle que soit
la langue active ; la réservation compte donc la même union, sur la même liste de langues (`main_gen._declared_lang_codes`,
point unique). Réserver la seule langue SOURCE faisait écraser par le chargement les bases des polices voisines, la surface
composée et les sprites en cible BG.

### Ce qu'une mise en page garde, et ce qu'un script peut animer

La géométrie d'une mise en page est **authorée** : ce qui existe, sa taille, son sprite, son
ancrage, son parent et sa profondeur se décident dans le canvas, jamais au runtime. Rouvrir ça
au script reprendrait ce que la mise en page existe pour fermer.

La **position d'une image** fait exception, et la nuance est la raison d'être de l'exception : `image.offset` pose un décalage
**relatif** à la position authorée, qui reste la vérité — `(0, 0)` rend l'image à sa mise en page sans que le script ait
mémorisé quoi que ce soit. La géométrie n'est pas rendue au script, elle est **animée**, comme `self.position` anime un acteur.
Deux `short` (`dx`, `dy`) dans `UIImageState`, remis à zéro par `ui_images_reset` ; `ui_image_update` compare l'origine à celle de
la frame précédente et, en cible BG, efface l'ancienne empreinte avant de réécrire (`ui_image_clear_bg`).

**Une zone de texte et un panneau ne se déplacent pas**, et ce n'est pas une omission : le bloc
de composition d'une zone est alloué à un rectangle fixe par `scene_init` (`RegionSurf`), et le
fond d'un panneau est peint une fois dans la tilemap. `DOMAIN_IMAGE` ne connaît que les images,
donc citer autre chose est refusé au build sans qu'un contrôle dédié existe.

**Une propriété, pas un appel de module** (`interface:get("Cursor").offset = vec2(0, 40)`) : `offset` est un `vec2` de la
famille des propriétés (`ui_image_offset` / `ui_image_set_offset`, construits dans `runtime_api_inline.h` sur les trois entiers du
moteur), et ne demande **aucune ligne** de checker ni de codegen : un membre déclaré sur un type passe par les chemins génériques.

### UI en sprite — `Actor.screen_space`

L'autre moitié de l'interface : un `UIImage` est un dessin posé dans une mise en page, un
acteur d'écran est un **acteur de jeu** (script, composants, logique) qui ne défile pas.

- **Un seul effet, au bon endroit** : l'émission OAM ne retranche pas la caméra. `x`/`y`
  cessent d'être des coordonnées de monde pour devenir des pixels d'écran — le même repère
  que les éléments d'UI ancrés à l'ÉCRAN. Trois sites suivent (acteur simple, acteur
  affine via `_affine_oam_lines_dynamic(..., screen_space=)`, et matrice affines du
  prefab) ; le **pool de prefabs reste en monde**, un prefab n'ayant pas de scène
  propriétaire unique où authorer ce choix.
- **Résolu au build.** Pas de champ dans `g_actors`, pas de setter Lua : un acteur est de
  l'UI ou du monde pour toute sa vie. Conséquence à préserver — le C émis pour un acteur
  de monde est **mot pour mot** celui d'avant l'existence du drapeau.
- **Canvas : enfant de l'item caméra**, comme les windows (`CameraItem.set_windows`). La
  position locale de l'item EST sa position dans l'écran GBA : il suit la vue sans
  recalcul, et `itemChange` lit une position déjà relative au parent, donc le drag rend
  directement la valeur à écrire dans le modèle. `GBAScene.sync_sprite_space()` est le
  point unique et idempotent (création, changement de caméra, bascule de la case).
- **Z-order face à l'UI de fond : le matériel répond.** `Actor.priority` (OAM attr2, bits
  10-11) se compare à la priorité du calque d'UI, qui vaut son `bg_slot` (`Scene.text_bg`)
  — la convention « priorité = index de layer » du projet. À priorité égale l'OBJ passe
  devant. Aucune règle implicite ajoutée par-dessus.
- **Ce qui continue de lire le monde**, et que `validator._check_screen_space` signale :
  une CollisionBox (carte de collision en pixels de monde), une caméra qui suit cet acteur
  (elle resterait immobile), un NŒUD d'interface ancré sur lui (l'ancrage est celui du nœud
  depuis v0.25 ; `text_region_origin()` retrancherait le scroll une seconde fois). Trois cas,
  trois corrections évidentes.

### Trois couleurs, trois champs — fond, encre, surlignement

Elles se ressemblent à l'écran et n'ont ni le même propriétaire, ni le même référentiel, ni le même coût :

| | Champ | Référentiel | Qui la dessine |
| --- | --- | --- | --- |
| **Fond** | `FillMixin.fill_palette` + `fill_index` | une palette BG **active** de la scène | `ui_fill_rect` — des tuiles pleines dans la tilemap |
| **Encre** | `UIText.text_color` | index 0-15 de la **banque d'UI** | une VARIANTE des glyphes (`scene_text_colors`) |
| **Surlignement** | `UIText.highlight_color` | index 0-15 de la **banque d'UI** | `text_surf_seed` — le fond des tuiles de surface |

- **Un texte prend le fond de son conteneur, sans rien déclarer** — et le SURLIGNEMENT le surcharge, sur l'étendue qu'il écrit. C'est
  une règle de non-destruction : le chemin tilemap remplacerait la cellule par une tuile de glyphe (index 0 transparent) et percerait
  le fond là où le texte passe. Le fond dit ce qu'il y a dessous, le surlignement ce que l'auteur veut y voir à la place.
- **Le fond d'une zone est de l'état de SCÈNE, dérivé des fonds ÉMIS.** `RegionFill` est posée par `scene_init` depuis
  `scene_color_fills` / `scene_image_fills` : un panneau que le build écarte ne peut pas colorer le texte qu'il contient.
- **Deux formes, une table** : une carte de tuiles (nine-slice, background) ou un aplat (couleur), distingués par `se == NULL` — une
  seule question (« qu'y a-t-il sous cette zone ? »), sinon une zone pourrait avoir deux fonds, ou aucun. « Le fond le plus proche
  gagne » vit dans `region_fill_panel()`, lue des deux côtés.
- **Le FOND décide de composer autant que la police** : `text_is_composited()` est vrai dès qu'une zone a un fond ou un surlignement,
  police mono comprise (sinon un texte mono trouerait un cadre nine-slice).
- **Le surlignement vit dans la banque d'UI, pas dans une palette au choix** : la tuile de surface porte UNE banque de palette
  (`g_pal_bank_bg`), le matériel n'en offre pas deux.
- **Il couvre l'étendue RENDUE**, origine comprise (`text_layout` rend le coin gauche de ce qu'il a tracé, sinon un texte centré
  surlignerait sa marge gauche). La boîte entière reste préparée : préparer efface, surligner colore, ce ne sont pas les mêmes tuiles.
- **Où loger l'aplat dépend de `scene.ui_pal_bank`.** En mode automatique la banque d'UI appartient à la police : le build y grave la
  couleur du conteneur depuis le haut (15, 14, …) en sautant les index que l'encre et les surlignements de la scène occupent —
  une réservation PAR SCÈNE. En banque désignée le build n'écrit rien (ce serait remplacer les couleurs choisies) et
  `_check_ui_text_fill_bank` exige que la banque désignée soit celle du conteneur (même contrat que le cadre nine-slice).
- **Troisième valeur : `UI_PAL_BANK_CONTAINER` (-2), « banque du conteneur ».** Désigner un numéro de banque à la main exige de
  connaître un détail d'ALLOCATION (`scene_bank_layout`, `bg_block_offset`) qui bouge dès qu'un autre asset de la scène change.
  `main_gen.scene_container_ink_bank` résout ce sentinel à partir du MÊME calcul que les deux validateurs
  (`scene_region_colors`/`scene_region_backdrops`). Il ne résout RIEN (reste en erreur) si la scène a plusieurs conteneurs
  recomposés à des banques différentes : le matériel n'offre qu'UNE banque par tuile de surface.
- **Cible OBJ : aucun fond ni surlignement** (une bande de sprites ne passe pas par la surface BG) : l'inspecteur masque le champ
  plutôt que de le proposer sans effet, comme `_FILL_TARGETS`.

### `UIList` — la navigation, pas la mise en page

`UIList` porte ce qu'un menu demande au MOTEUR : un index courant, des bornes, un pas et de quoi le faire bouger. Ses RANGÉES sont
ses enfants de type texte, dans l'ordre de l'arbre (ce qu'on voit dans l'éditeur est ce que la liste parcourt). Le nombre d'ITEMS
reste de la donnée (`menu.count = …`), à défaut le compte de rangées. Elle n'ÉCRIT pas : le contenu d'une rangée est posé par le
script (`menu:row(1):draw(...)`), parce qu'un item est une ligne de donnée et non un objet d'interface — un inventaire, un arbre de
compétences et un menu de sauvegarde partagent ainsi un seul mécanisme. C'est un type à part entière ; un ancien
`{"kind": "panel", "is_list": true}` se relit et ne se réécrit jamais.

- **La grille tient en deux nombres**, `nav_columns` et `nav_major`, et non en quatre modes : un parcours en Z ou en W doit savoir DE
  COMBIEN sauter en changeant de ligne. Une colonne = liste verticale, une ligne = rangée d'onglets ; le pas transverse **n'existe
  pas** quand la grille n'a qu'une ligne (sinon la croix entière piloterait un menu à un seul axe).
- **Le défilement est à la LIGNE** : une ligne vaut `nav_columns` items et la fenêtre s'aligne dessus.
- **`active` est la sélection, pas l'affichage** : une liste inactive reste dessinée, garde son index et son curseur, et cesse de lire
  la croix — c'est ce qui permet un menu et son sous-menu à l'écran ensemble.
- **La liste possède son CURSEUR** : elle nomme un `UIImage` de la même mise en page, que le moteur déplace par le chemin de
  `image.offset` (décalage RELATIF à la position authorée) de la distance qui sépare la première rangée de la rangée courante.
- **Le style de la rangée choisie, c'est `highlight` et `color`**, les deux réglages qu'une zone porte déjà : le redessin passe par
  `text_render_region` avec deux globales de surcharge (`g_row_color`, `g_row_highlight`), sans second chemin de dessin. Le texte à
  reposer vient de `g_ui_list_row_text`, une table par RANGÉE remplie par `text_draw_in` (pas des têtes de lecture, `TEXT_READ_MAX`,
  dont le plafond global laisserait dehors le troisième menu d'un jeu). Une ANIMATION de la rangée choisie n'est pas offerte : en
  BG elle réécrirait des tuiles à chaque frame.

Vérification : `tests/interface/test_ui_list_type.py` (le type, la relecture, ce que le build émet) et
`tests/interface/test_ui_list_native.py`, qui fait tourner le VRAI `ui_list_tick` compilé — le pas en
grille et le défilement sont de l'arithmétique entière sans sortie visible avant qu'une ROM
tourne.

### Fond d'un conteneur — deux chemins que la CIBLE choisit

`FillMixin.fill_kind` est polymorphe — porté par les DEUX types qui dessinent un fond, le conteneur et la liste — et
`_FILL_TARGETS` dit ce que le build ÉMET, pas ce qui serait concevable : couleur / nine-slice / background posent des tuiles et
écrivent une carte, donc **BG seulement** (`scene_color_fills`, `scene_image_fills`) ; sprite pave des OBJ, donc **OBJ
seulement**. Un mode permis mais jamais émis est pire qu'un mode absent.

- **Un fond OBJ se PAVE** (`sprite_grid`) : `⌈w/fw⌉ × ⌈h/fh⌉` cases, parce qu'un OBJ ne s'étire pas sans mode affine et qu'un panneau
  dont la taille serait dictée par son fond ne serait plus un conteneur. La dernière colonne/rangée déborde plutôt que d'être rognée.
  Coût : des slots OAM, **aucune tuile de plus** (toutes les cases pointent la même frame).
- **Aucune table de plus** : le conteneur entre dans `g_ui_images` avec les `UIImage`, et `FillMixin` expose la surface commune
  (`sprite_name`, `state_name`, `playing`, `priority`, `state_index`) en propriétés dérivées de ses champs `fill_*` ; `UIImageInfo`
  ne gagne que `cols`/`rows` et `speed`. `IMAGE_<nom du panneau>` existe donc : un script anime le fond comme une image.
  `fill_speed` est une surcharge (0 = la vitesse de l'état du sprite, qui reste la source de vérité).
- **L'ordre d'allocation OAM est l'ordre de profondeur** (`layout_obj_budget`) : bandes de
  texte, puis images, puis fonds de conteneur. Un slot bas passe devant, et la priorité OBJ
  ne départage pas deux OBJ de même priorité — c'est donc l'ordre qui met le fond au fond.
- **Le débordement OAM bloque le build** : une ROM construite avec des slots hors des 128 du matériel n'affiche rien, sans erreur.
