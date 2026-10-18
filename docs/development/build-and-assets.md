# Build de la ROM, sauvegarde et compression d'assets

Le pipeline de build en neuf étapes, le journal de build, la SRAM, la compression non destructive des fonds et sprites. Extrait d'ARCHITECTURE.md.

## Pipeline de build (ROM)

```
① Validation du projet (scenes, sprites, scripts)

② Fonds — par layer de scène (dédup par image+bg_slot, ou par scène si inpainting)
   fond COMPRESSÉ (cas courant : tileset + sous-palettes déjà dans le BackgroundAsset)
       → bg_emit           → build/grit_out/{layer}.c/.h   (émission directe, PAS grit)
   fond legacy non compressé
       → grit              → build/grit_out/{layer}.c/.h
   (bitmap Mode 4 : ignoré au build — cf. Système de palette)

③ Sprites — union de toutes les scènes + prefabs (dédupliqués par nom)
   assets/sprites/{name}.png  quantifié vers sa palette effective (propre ou banque
   référencée, résolue par palette_alloc)
       → grit              → build/grit_out/sprite_{name}.c/.h
       → cache : empreinte du PNG, du sidecar, de la palette effective et de grit

④ Audio (optionnel)
   assets/sounds/*.wav/.mod
       → mmutil + bin2s     → build/grit_out/soundbank.*
       → cache : empreinte des sources retenues, de leurs réglages et des deux outils

⑤ Génération des headers C
   assets/ + sprites
       → codegen            → build/src/actor_types.h
                            → build/src/actor_api.h

⑥ Transpilation Lua → C — toutes les scènes en une passe
   script attaché à une scène   → build/src/{scene}_scene.c
   script attaché à un acteur   → build/src/actor_{name}.c
   (un script se range où l'on veut sous assets/ ; un behavior se reconnaît à sa première ligne `-- @behavior`, cf. core/lua_scripts.py)
   (globals partagés)            → build/src/globals.c / globals.h

⑦ Génération de main.c
   all_scene_data + prefabs
       → codegen            → build/src/main.c

⑧ Compilation + link
   build/src/*.c + build/grit_out/*.c
       → arm-none-eabi-gcc  → build/obj/*.o
       → make (Makefile)    → build/rom.elf → build/rom.gba

⑨ Lancement
   build/rom.gba → mgba
```

Orchestré par `editor/codegen/rom_build.py` (`BuildWorker`), déclenché depuis
`ui/common/build_panel.py`.

### Le journal de build — un diagnostic, un fichier

Tout ce que le build reproche au projet est un `ValidationMessage` (`core/diagnostic.py`, module de base que `core.validator` ré-exporte — les générateurs l'importent de là pour ne pas fermer une boucle d'import) :
`level` (`error`/`warning`), `source` (`validator`, `script`, `checker`, `codegen`, ou l'outil :
`make`, `grit`, `mmutil`…), `file`, `line`, `actor` (le propriétaire d'un script), et une `target`
cliquable. Le validateur, le checker Lua, le codegen et la sortie des outils passent par la même forme ;
`build_error()` / `build_warning()` la fabriquent hors du validateur.

`BuildWorker` n'émet que quatre sortes d'événements : `log_line` (information), `diagnostic`
(avertissement ou erreur, l'objet ci-dessus), `error_line` (le contexte d'un outil qui a échoué),
`progress`/`finished`. Son `_emit` est le seul point de passage : il compte les diagnostics, ajoute
`[build] N error(s), M warning(s)` devant `finished`, et copie chaque ligne dans
**`<projet>/build/build.log`** (réécrit à chaque build ; en-tête : version, outils, projet).

- La console se rend d'un diagnostic avec `console_line()` (`[error] Hit.lua:3: message`) ; la couleur
  suit `level`, pas le canal. L'onglet Diagnostics reçoit la même liste à la fin du build, et son clic lit
  `file`/`line`.
- Le stderr d'un outil est rangé par ce qu'il dit (`BuildWorker._emit_tool_line`) : `fichier:ligne:col:
  error|warning:` de gcc devient un diagnostic, `note:` de l'information, le reste du contexte (rouge
  seulement si l'outil a échoué). Le code de retour est seul juge de l'échec.
- **gcc cite le script, pas le `.c`.** `CodegenContext.lua_file`/`c_file` activent des directives `#line N
  "Script.lua"` avant chaque statement émis (`CodeGen._mark_source` ; la ligne vient de `Stmt*.line`, posée par
  `parser._block`) et un retour à `#line <n> "actor_X.c"` après chaque corps de fonction (`_emit_block`, numéro
  résolu sur le texte final par `_resolve_line_resets`, car l'état par instance est inséré après coup). Les
  statements d'un behavior inliné portent le nom du behavior.
- **Le validateur contrôle toutes les scènes.** `core/validator._check_each_scene` fait tourner les contrôles
  par scène (acteurs, fonds, événements de frame) pour CHAQUE scène via `ctx.focus(scene)`, et
  `_check_prefabs` contrôle les composants des prefabs ; le diagnostic porte sa scène (`ValidationMessage.scene`,
  rendu `[Scène/Acteur]`). `_check_scripts_parse` passe en premier : un script qui n'est pas de l'UTF-8 arrête la
  validation après son message, les autres contrôles relisant le même fichier.
  Le clic sur un tel diagnostic ouvre sa scène puis y sélectionne l'acteur (`MainWindow._select_actor_by_name`,
  qui ne relance pas la validation : la liste du build reste affichée).
- **La couverture des diagnostics est mesurée.** `tools/diagnostic_coverage.py` énumère les sites d'émission (AST,
  clé stable `fichier::fonction::empreinte du message`) et enregistre ceux qu'un run déclenche (`Recorder`, installé
  par `tests/conftest.py`). À la fin d'un run COMPLET, `pytest` AVERTIT (sans échouer) d'un diagnostic couvert qui
  ne l'est plus ou d'un nouveau jamais déclenché ; la référence est `tools/diagnostic_coverage_baseline.json`
  (un échantillon, pas un objectif de 100 % ; `DIAGNOSTIC_COVERAGE_UPDATE=1` pour la relever, `python tools/diagnostic_coverage.py` pour lister les sites
  jamais atteints). `tests/rom_build/test_build_invariants.py` (marqué `slow` : `pytest -m slow`, et `release.yml` avant publication) corrompt les fichiers de la démo un à un (une compilation réelle par cas, ~3 min à lui seul) et exige cinq
  invariants du journal (pas d'« internal error », échec = erreur, anglais sans chemin du projet, le fichier
  abîmé est nommé, un fichier cassé n'est jamais ignoré sans un mot).
- **Aucune erreur n'est avalée.** Un `except` large (`Exception`, nu, `LuaParseError`) de `codegen/`,
  `scripting/` ou `core/validator.py` lève, émet, ou porte `# tolerated: <raison>` ; `tests/
  test_silent_except.py` le garde. `core/validator._check_scripts_parse` lit tout `.lua` de `scripts/`,
  attaché ou non ; un prefab qu'aucune scène ne déclare passe en plus par le checker (`lua_compiler`, une
  fois par build) ; `tests/rom_build/test_build_fault_injection.py` rejoue des fautes connues dans un vrai build (marqué `slow`
  avec les autres tests qui compilent un projet entier : exclus par défaut, lancés par `release.yml`).

## Sauvegarde — variables persistantes en SRAM

32 Kio à `0x0E000000`, **accessibles octet par octet uniquement** : un accès 16/32 bits y
lit et écrit du n'importe quoi, d'où `sram_get32`/`sram_put32` qui décomposent en quatre
lectures/écritures sur un `vu8*`. Les waitstates du bus sont posés une fois par
`sram_init()` au tout début de `main()` — sans eux, la lecture rend des octets faux sur
matériel réel, et rien du tout côté émulateur, ce qui est le pire des deux mondes pour
diagnostiquer.

Ce qui est sauvé, ce sont les `GlobalVar` dont `persist` est vrai. Le moteur ne connaît
aucun autre état : ni scène courante, ni position d'acteur. Reprendre une partie est un
aiguillage que l'auteur écrit.

Le socle est `globals.h` : `GLOBAL_<NOM>` et `global_read/global_write(i)` (une valeur interpolée connaît une variable par
index, jamais par nom) ; `g_save_idx[]` ne contient que ces index-là.

Format d'un emplacement, écrit par `save_write` :

| Décalage | Contenu |
| --- | --- |
| 0 | `'G' 'B' 'S' 'V'` — marque de reconnaissance |
| 4 | `u16` version du format |
| 6 | `u16` nombre d'enregistrements |
| 8 | `u32` somme de contrôle du numéro d'emplacement et des enregistrements |
| 12 | `u32` numéro de l'emplacement (depuis le format 3) |
| 16 | `n` enregistrements : `u32` id, `u32` taille de charge utile, `u32` métadonnées, puis les cases empaquetées (1 à 32 bits selon leur type) |

Le format 4 réserve 24 bits des métadonnées au nombre exact de cases et 8 bits à leur largeur (bit `0x80` : type signé) :
le remplissage jusqu'au mot de 32 bits n'est jamais pris pour des cases, et un tableau agrandi garde ses valeurs par
défaut au-delà de sa longueur sauvegardée. La lecture utilise la largeur et le signe enregistrés, même si le type de la
variable a changé depuis.

Les emplacements occupent des partitions égales de la SRAM, arrondies à quatre octets : leur adresse ne dépend pas du
nombre de variables. Les formats 2 et 3 restent lisibles ; la première écriture ou suppression migre les parties
existantes vers le format 4 (un changement du nombre d'emplacements emprunte le même chemin), en gardant des
métadonnées nulles et le comportement de lecture antérieur jusqu'à la réécriture de l'emplacement par le jeu. La
migration réserve temporairement 32 Kio en RAM ; si la mémoire manque, si une ancienne partie dépasse sa nouvelle
partition ou si un emplacement serait perdu, l'opération rend 0 sans modifier la SRAM. Les lectures ne migrent rien.
Une sauvegarde passée au format 4 n'est plus lisible par les anciennes ROMs.

**Rangé par id, pas par rang.** Ajouter, retirer ou réordonner une variable persistante
laisse les sauvegardes existantes lisibles, là où un tableau positionnel aurait fait lire
à `score` la valeur de `vies`. L'id opaque fait 12 chiffres hexadécimaux (48 bits) et la SRAM se lit par mots de
32 bits : c'est un repli déterministe (les 8 derniers chiffres, `int(id, 16) & 0xFFFFFFFF`) qui est écrit, et une collision
entre deux variables persistantes **bloque le build** — improbable, et invisible en jeu.

**Trois tests avant de croire un emplacement** (marque, version, somme) : la mémoire d'une
cartouche à pile vide rend des octets plausibles, et une lecture « au mieux » restaurerait
un état inventé sans un mot. La somme est écrite en dernier, pour qu'une coupure de
courant laisse un emplacement illisible plutôt qu'une sauvegarde à moitié écrite qui se
relit très bien. `save_read` (`save.load` côté Lua) repose d'abord tous les défauts : une
lecture rend un état complet, jamais un mélange entre le fichier et la partie en cours.

**`save:read(slot, "nom")` lit UNE variable sans les trois tests ci-dessus** : elle rend le défaut de la variable dès que
`save_exists` répond faux, sinon s'arrête au premier enregistrement qui porte son id, sans jamais appeler
`global_write_at` — donc sans toucher aux globales de la partie en cours (de quoi peindre un écran de sélection de
partie). Le nom reste un argument LITTÉRAL, résolu à `GLOBAL_<NOM>` à la compilation (`codegen._emit_save_read`).

Côté build (`main_gen._save_lines`) : trois tableaux parallèles (`g_save_id`, `g_save_idx`,
`g_save_def`), émis **même vides** parce que `gba_engine.h` les déclare sans condition —
c'est `g_save_count == 0` qui dit au moteur de ne pas toucher la SRAM. La chaîne
`SRAM_V113`, que cherchent émulateurs et linkers pour détecter le type de sauvegarde,
n'est émise **que** si le projet a au moins une variable persistante : un jeu sans
sauvegarde ne doit pas faire naître un fichier `.sav` vide chez le joueur. Elle porte
`used` — rien ne la référence, et l'éditeur de liens la retirerait.

Deux erreurs bloquent le build, comme le budget de tuiles : le débordement de SRAM
(`emplacements × taille`) et la collision d'identifiants. Le checker, lui, refuse un
numéro d'emplacement littéral hors de ce que le projet déclare, et signale un `save.write`
dans un projet où rien n'est marqué persistant — un appel qui ne fait rien ne se
diagnostique pas en relisant son script.

## Système de palette & compression d'assets

Deux idées structurent tout : **un catalogue de palettes nommées** activées par scène, et des PNG sources jamais réécrits —
les couleurs et la tuilerie vivent dans des sidecars JSON, recalculés au build.

### Catalogue et sélection par scène


- **`PaletteBank`** (`core/models/palette.py`) — une palette nommée de 16 couleurs BGR555,
  catalogue illimité et **unifié** (`assets/palettes/*.json`, un fichier par palette),
  partagé entre les pools OBJ et BG. L'index 0 est toujours forcé transparent.
- **Sélection active par scène** — `Scene.active_obj_palettes` / `active_bg_palettes` :
  jusqu'à 16 noms de `PaletteBank` par pool, l'ordre = index de banque hardware. C'est
  cette sélection (pas le catalogue) qui occupe réellement les banques
  `PAL_OBJ_RAM` / `PAL_BG_RAM` au build. Les deux pools GBA sont physiquement séparés.
- **`pal_bank`** sur `Actor` / `Prefab` / `BackgroundLayer` — soit un slot `0-15` dans la
  sélection de la scène, soit le sentinel **`OWN_PAL_BANK` (-1)** = « palette issu de l'asset ».

### Allocation des banques — source de vérité unique

`codegen/palette_alloc.py::scene_bank_layout(project, scene, pool)` résout, pour une scène
et un pool, quelles couleurs occupent chacune des 16 banques hardware :

1. palettes référencées → à leur slot fixe (index dans `active_*_palettes`) ;
2. fonds compressés → un **bloc de banques contiguës** (une par sous-palette).

Déterministe : `rom_build.py` (quantification grit) et `main_gen.py` (émission des
`PAL_*_RAM`) lisent le même layout sans se coordonner. Le débordement (>16 banques) n'est
jamais silencieux : `bank_index` retombe sur la banque 0 et le validateur avertit.

### Compression non-destructive

- **Sprites** — chaque `SpriteAsset` conserve sa **palette propre** (`own_palette`, BGR555)
  dérivée d'un png indexé directement (ou déduite depuis un png non-indexé). Au build, le sprite est quantifié vers sa palette effective (propre ou
  banque référencée) et indexé, sans réécrire le PNG.
- **Fonds** — `core/bg_import.py` produit un `BackgroundAsset` (sidecar par image) :
  tuilerie 8×8 + déduplication + jusqu'à 16 **sous-palettes** (`SE_PALBANK` par tuile en
  4bpp). L'émission C se fait **directement** (`codegen/bg_emit.py::emit_bg_c`), sans passer
  par grit. Trois modes, **auto-détectés à l'import** (`detect_import_mode`) :

  | Mode | `BackgroundAsset` | Rendu |
  |------|-------------------|-------|
  | Tuilé 4bpp | `bpp=4`, ≤16 sous-palettes | Mode 0, `SE_PALBANK` par tuile, inpainting possible |
  | Tuilé 8bpp | `bpp=8`, 1 palette de 256 | Mode 0, occupe toute la `PAL_BG_RAM` (1 seul layer) |
  | Bitmap | `mode="bitmap"` | Mode 4 plein écran (photos) — **éditable mais pas encore émis au build** |

  **Le sidecar a deux blocs** (`BackgroundAsset._settings_dict` / `_encoded_dict`) : `settings` — ce que l'auteur a décidé
  (layout `mode`/`bpp`, dithering, méthode de quantification, canvas / pose / miroir / ajustements, compression, retouches de
  tuiles) — et `encoded` — ce que l'encodage en a tiré (tileset, tilemap, palettes, bitmap, diagnostics, `source_stamp`), que
  le build lit et qu'un nouvel encodage remplace en entier. `apply_bg_encoding` ne range que son résultat et ne touche à aucun
  réglage ; le layout se pose par `choose_layout(token)` avant l'encodage. **Les palettes d'un fond sont des références au
  catalogue, par nom** : `added_palettes` et `palette_overrides` sont des réglages, `palettes` n'en est que le cache résolu
  (`BackgroundAsset.resolve_palettes`). Un sidecar à plat d'avant les blocs se lit tel quel et passe en deux blocs à la
  prochaine sauvegarde.

  **Un résultat sait de quels réglages il vient** : `encoded.encoded_for` est l'empreinte
  (`BackgroundAsset.encode_settings_fingerprint`) des réglages qui DÉTERMINENT l'encodage (layout, profondeur, dithering,
  méthode, canvas, pose, taille, miroir, ajustements, compression — ni les palettes citées, ni la peinture).
  `encoding_is_current(source_stamp)` dit « à jour » ou « périmé » sans rien recalculer, et le build avertit
  (`validator._check_background_encoding_current`, non bloquant) d'un fond périmé : la ROM prendrait l'ancien résultat.

  **Un seul chemin pour encoder** : `ui/background_editor/background_encoding.py`. L'écran donne un `EncodingJob` à
  `BackgroundEncodingService.request` ; le service calcule hors du thread de l'interface, un calcul à la fois, le DERNIER
  réglage voulu gagne (un résultat périmé va au cache, jamais sur le fond), et valide par le rappel `commit` de l'écran. Un
  échec ne reboucle pas (`run_now` le rejoue) ; un résultat déjà vu (cache de 8) se valide sans calcul.

  **Préparation de la source** — l'image est **posée dans un canvas** de taille propre (`canvas_size`) : mise à l'échelle
  (`image_size`), posée (`image_pos`), elle peut déborder (rognée) ou laisser du vide (transparent) ; rien n'est jamais
  rétréci en douce. Un **bitmap** a un canvas FIXE de 240×160 (posé par `encode_by_mode`) : l'image garde sa taille en (0, 0) et
  déborde. Trois champs à `None` = « Original ». Le **miroir** (`mirror_x`/`mirror_y`, `core/bg_mirror.apply_mirror`) précède
  la compression, parce qu'il change les tuiles qu'elle dédupliquera. Le PNG n'est jamais modifié : `bg_import.prepare_source`
  produit une image PIL en mémoire, que reçoit `encode_by_mode(…, prep=ba.import_prep())` — le seul endroit qui l'applique,
  donc le seul que lisent le worker de l'éditeur et la réconciliation. Rééchantillonnage : plus proche voisin si la source est
  indexée, Lanczos sinon, après rognage à la partie visible. Toute la géométrie que le build ou le Scene Manager affichent vient
  de `BackgroundAsset.pixel_size()`, jamais du PNG.

### Inpainting — repeindre la palette par tuile (non-destructif)

Réassigner la banque de palette d'une tuile 8×8 sans toucher aux pixels. La baseline
(`BackgroundAsset.tilemap`) reste intacte ; `effective_tilemap()` applique les overrides.
Deux niveaux :

- **Éditeur** — `BackgroundAsset.tile_palette_overrides` : partagé par toutes les scènes
  qui utilisent ce fond (canvas du Background Editor).
- **Scène** — `BackgroundLayer.tile_palette_overrides` : propre à une scène, se superpose
  par-dessus l'inpainting éditeur (canvas du Scene Manager). La scène est source de vérité ;
  le build produit alors une map propre à la scène plutôt que la map partagée.

La gomme restaure la palette d'origine (supprime l'override).

### Garde-fous (validateur)

- **Conflit inter-scènes** — même sprite/prefab résolu vers des palettes différentes selon
  la scène → **avertissement** (une seule variante de tuiles est générée, 1ʳᵉ scène gagne).
- **Débordement de banques** (>16 par pool) → avertissement, fallback banque 0.
- **Budget VRAM tuiles** (`rom_build.BuildWorker._check_bg_tile_budget`) — un layer dont les tuiles
  générées déborderaient sur l'espace réservé à sa propre map → **erreur bloquante** (ici
  c'est de la mémoire écrasée au runtime, pas juste une mauvaise couleur).
