# Raccordement build vectoriel — **LIVRÉ**

> **Livré le 2026-09-12.** Le build matérialise un
> `FontAsset` en `RasterGlyph` éphémères, puis en tuiles 4bpp : la même police
> sert à l'émission C, au choix tilemap/composition et au budget VRAM. Aucune
> planche dérivée n'est écrite ; les sources bitmap et les projets antérieurs
> conservent leur chemin historique.

### La chaîne, en une ligne

```
Font (source) → Glyph → RasterGlyph → représentation GBA
```

Chaque flèche est une couche, et chacune ignore les suivantes. Le `Glyph` est le caractère et
ses métriques ; le `RasterGlyph` est sa forme rasterisée, **indépendante du format GBA** ; la
conversion en tuiles et palette n'arrive qu'à l'export. Le bitmap est une représentation de
**rendu**, jamais le modèle principal du texte.

### Les couches, et où chacune vit

| Couche | Nature | Où | État |
| --- | --- | --- | --- |
| **`Font`** | source de glyphes — l'intrinsèque *disponible* dans le fichier (glyphes présents, codepoints, métriques) | sidecar `.json` à côté de la source, dans `assets/fonts/` (inchangé) | livré |
| **`Glyph`** | caractère + métriques (rect ou vectoriel, `advance`, `ox/oy`) | dans le sidecar `Font` | existe |
| **`FontAsset`** | usage projet : sources par variante (regular / bold / italic / bold italic), ordre de fallback, params de traitement (taille de rendu, cellule cible, bpp, seuil/dither, chasse) | un `.json` par asset, dans `project/fonts_assets/` | livré |
| **`RasterGlyph`** | forme bitmap d'un glyphe, **grille de couverture** (gris/alpha), sans index GBA | calculé à la demande pour l'aperçu et le build | livré |
| **`Text` / `TextStyle` / `Layout` / `TextEffect`** | contenu / apparence / placement / transformations | en aval — **hors de ce jalon** | partiels |
| **Build** | résout `FontAsset` → sous-ensemble requis → rasterise → tuiles + palette | `codegen/font_build.py` puis `font_emit.py` | premier raccord livré |

**Le `FontAsset` ne duplique jamais les données intrinsèques d'un `Font`.** Le sidecar décrit la
ressource ; le `FontAsset` décrit son usage. C'est pourquoi `bg_color` / `space_color` — qui
disent *comment lire* une planche bitmap — quittent `Font` pour devenir des params de traitement
du `FontAsset`, spécifiques aux sources bitmap : une source vectorielle n'a ni fond à trouer ni
chasse à mesurer, le rasterizer lui donne couverture et métriques directement.

### La chaîne de couverture — et ce que la langue conserve

Un `FontAsset` est une **police logique** qui résout **chaque codepoint requis** par une
**chaîne ordonnée de sources**. Un codepoint prend la première source de la chaîne qui sait le
rendre :

```
dialog (FontAsset)
  1. source primaire   (regular / bold / italic…)   ← couvre le Latin
  2. fallback          (ark-pixel-ja)                ← couvre ce que 1 ne couvre pas
```

L'axe n'est **pas la langue**, c'est la **couverture de glyphes** ; la langue ne fait qu'induire
quels codepoints sont requis — ce que `scene_codepoints()` calcule déjà, sur l'union des langues.
Une police Unicode « juste marche » (la chaîne ne retombe jamais) ; une police pixel Latin-only
reçoit un fallback pour les écritures qu'elle ne couvre pas, sans qu'on nomme jamais une langue.

La chaîne de couverture ne remplace pas le choix produit « police par défaut de la langue » :
`Language.default_font` peut remapper la police par défaut du projet, tandis que les fallbacks
d'un `FontAsset` résolvent les caractères absents DANS cette police. Le runtime conserve donc
`g_lang_font` pour ce premier choix, puis le build matérialise la recette de l'asset retenu. La
scène nomme toujours la police logique par défaut ; la décision doit être reflétée au build dans
le sous-ensemble, la palette et la surface de composition.

### Le rasterizer est appelé par le build

`FontRasterizer` est une **fonction pure** `(source, glyphe, params) → RasterGlyph`. L'aperçu
de l'éditeur et `codegen/font_build.py` l'appellent ; le build ne possède donc aucune seconde
implémentation. C'est la règle qu'on tient déjà ailleurs (`is_proportional()` partagé
par l'émetteur et l'aperçu, `key_out()` qui reflète `key_colors()`) : si l'aperçu et l'émetteur
divergent, le canvas ment sur ce qui part en ROM.

- **La rasterisation est résolue au BUILD, jamais au runtime.** Le jeu ne comprend aucun TTF/OTF
  — il ne manipule que des données de police déjà préparées pour la GBA. Le `RasterGlyph` n'est
  calculé que pour le **sous-ensemble requis** (clés de texte littérales, imposées par le
  checker) : la propriété « jeu fini d'images de glyphes » ne vit plus dans la *source* mais dans
  la *sortie de build* — et c'est suffisant pour garder le sous-ensemble par scène, le garde-fou
  VRAM et le CJK.
- **`RasterGlyph` = grille de couverture, pas d'index GBA.** Une source vectorielle produit de
  l'anti-crénelage naturel ; une source bitmap indexée donne une couverture binaire. La
  **quantisation couverture → N index de palette** (seuil ou dither) est l'étape *export GBA*,
  dans `font_emit._encode_raster_font()`.
  C'est cette grille abstraite, gardée jusqu'au dernier moment, qui rendra les couleurs, styles
  et effets simples à implémenter dans leur jalon à eux.
- **La preview ne persiste rien.** La différence nette avec le point d'entrée FreeType supprimé
  le 2026-09-03 (chantier *Les formats acceptés à l'import*) : ce hack rasterisait **à l'import**
  et **écrivait un PNG comme asset**. `FontRasterizer` rasterise **à la demande** (build +
  aperçu) et ne persiste que le `.json` du `FontAsset`. Ce n'est pas une ré-addition du hack,
  c'est un étage de première classe qui le remplace — et il ramène `freetype-py`, cette fois
  comme dépendance de **build**, documentée.

### Décisions verrouillées

- **Séparation stricte des couches.** `Font` ne connaît ni traductions, ni effets, ni layout, ni
  couleurs. `FontAsset` ne duplique pas l'intrinsèque de `Font`. `RasterGlyph` ignore le format
  GBA. La conversion GBA vit au build, et nulle part avant.
- **La résolution passe par la couverture, pas par la langue.** Un `FontAsset` = une chaîne
  ordonnée de sources ; un codepoint prend la première qui le couvre.
- **La primaire du `FontAsset` gouverne l'interligne** ; les glyphes de fallback s'y alignent.
  Une ligne mixte (rare — une traduction est presque toujours mono-script) reste donc régulière.
  Un override par plage de codepoints est une **porte** laissée ouverte, pas une fonctionnalité
  de ce jalon.
- **Un seul `FontRasterizer`, appelé par le build ET l'aperçu.** Résolution au build, jamais au
  runtime ; aucune persistance d'asset généré.
- **Deux dossiers, deux natures.** Les sources restent dans `assets/fonts/` (inchangé) — le
  fichier importé et son sidecar `Font`, l'intrinsèque. Les `FontAsset` vivent dans
  `project/fonts_assets/`, un fichier par asset, avec identité et référençables par nom, comme
  une palette. `assets/` = source décrite, `project/` = objet moteur ; aucune migration.
- **Bold / italic = faces NATIVES de la source, pas de synthèse.** Si la source vectorielle
  porte nativement ses faces bold / italic / bold-italic, le rasterizer les rend ; sinon la
  variante n'existe pas — une planche PNG n'a pas de style. Pas de faux-gras ni de cisaillement
  (le faux-gras sur une police pixel est laid). La synthèse reste une **porte** ultérieure
  (« pour l'instant »).

### Ce que ce jalon précise dans la v0.9

Trois décisions verrouillées de la v0.9 (section Traduction) sont **précisées** ici — signalées
là-bas par un renvoi vers ce jalon, pour ne pas laisser deux vérités vivantes :

- « Une langue n'a pas de police : elle a éventuellement un REMPLACEMENT » → la substitution
  de `Language.default_font` reste le choix de police par défaut de la langue ; la couverture
  du `FontAsset` ajoute des replis de caractères dans cette police, sans multiplier les
  remplacements.
- « Une scène ne change jamais de police selon la langue… par une table de remap » → la scène
  nomme toujours `dialog` ; `g_lang_font` conserve le remap de la police par défaut et la
  chaîne de couverture résout ensuite les caractères absents. `font_de.fnt` ne crée jamais ce
  lien automatiquement.
- « PNG et `.fnt` seulement… un TTF rendu au build ne donnerait pas ça » → les sources
  vectorielles sont acceptées via `FontRasterizer` ; le « jeu fini de glyphes » se déplace de la
  source vers la sortie de build, et l'argument tient toujours.

### Prolongements hors v0.26

- **Le seuil / dither** couverture → index : réglage par `FontAsset`, ou déduit du bpp cible ?
- **`TextStyle` / `TextEffect`** : leur propre jalon, en aval — ce qu'il faut, c'est que la
  grille de couverture reste manipulable jusqu'à l'export pour qu'ils restent simples.

### Ce que le raccordement build touche

| Fichier | Ce qui change |
| --- | --- |
| `core/models/font_asset.py` | **création** — `FontAsset` (chaîne de sources, variantes, params de traitement) |
| `core/font_rasterizer.py` | **création** — `FontRasterizer` (fonction pure) + `RasterGlyph` |
| `core/models/font.py` | dégraissage : `bg_color`/`space_color` sortent vers `FontAsset` ; `Font` devient source intrinsèque, vectorielle ou bitmap |
| `core/font_import.py` | lecture de source + extraction cmap/métriques ; plus aucun point d'entrée qui *fabrique* une planche |
| `codegen/font_emit.py` | réorganisé autour de `RasterGlyph` ; `emit_lang_fonts_c` conserve le remplacement de la police par défaut par langue |
| `codegen/runtime_codegen/main_gen.py` | émet les tables de `FontAsset` et le remap de police par langue |
| `core/models/settings.py` | `Language.default_font` conserve le choix de police par défaut de chaque langue |
| `ui/scene_manager/inspectors/languages_card.py` | la carte expose ce choix de police par défaut |
| `runtime/include/gba_engine.h` | `g_lang_font` remappe la police par défaut ; le rendu et la réservation tiennent compte de la police effective |
| `core/project_paths.py` | `fonts_assets_dir` ajouté (`project/fonts_assets/`) ; `assets/fonts/` inchangé |
| `core/project.py` | `ResourceStore[FontAsset]` monté sur `fonts_assets_dir` |
| `core/resources/asset_reconciliation.py` | synchro : sidecar `Font` (`assets/fonts/`) distinct du `FontAsset` (`project/fonts_assets/`) |
| `tests/` | `test_lang_font_remap.py` supprimé, sondes natives nettoyées ; tests neufs `FontRasterizer`/`FontAsset`/couverture |
| `requirements.txt` | `freetype-py` revient comme dépendance de build |
| `ARCHITECTURE.md` | la section police réécrite autour des couches (fait à l'étape suivante) |

