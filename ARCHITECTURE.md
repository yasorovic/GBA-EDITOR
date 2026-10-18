# Architecture

Détails techniques du projet — terminologie, structure des fichiers, pipeline de build. Le [README](README.md) reste le point d'entrée pour un utilisateur ; ce document est pour qui modifie le code.

---

## Arborescence

```
backstage/
├── editor/                          ← application Python (PyQt6)
│   ├── main.py, window.py           ← point d'entrée ; MainWindow + onglets
│   ├── core/                        ← tout ce qui ne dessine rien
│   │   ├── project.py               ← classe Project (registres, scène active, save/load), en tranches :
│   │   │                              project_paths / _variables / _texts / _langs / _renames
│   │   ├── models/                  ← modèle de domaine (dataclasses + sérialisation), un fichier par sous-domaine ;
│   │   │                              `tile_codec.py` est une FEUILLE (n'importe rien)
│   │   ├── resources/               ← persistance disque ↔ modèles, sans dépendre de Project
│   │   │                              (index nom → chemin sans lire les JSON, ResourceStore générique, `.temp/` des suppressions)
│   │   ├── engine_emulation/        ← ce que l'éditeur REFAIT en Python parce que la console le fait en C :
│   │   │                              DEUX implémentations à tenir d'accord (mise en page du texte, BLDCNT, rendu des modules
│   │   │                              façon maxmod, transitions de musique)
│   │   ├── disk_*.py, asset_*.py    ← l'onglet Disk et ses gestes annulables (arbre de `assets/`, déplacer, relier une source,
│   │   │                              créer un asset, ce qui cite encore un asset avant de le supprimer)
│   │   ├── toolchain.py             ← détection devkitPro/mGBA (PATH, config, emplacements connus) + `config_dir()`
│   │   └── …                        ← le reste est un module par sujet (polices, textes et balisage, audio, watcher de projet)
│   ├── codegen/                     ← du projet à la ROM
│   │   ├── rom_build.py             ← orchestration du build (BuildWorker)
│   │   ├── grit_conversion.py       ← grit (sprites, fonds, sons) ; `asset_cache.py` : sorties déjà converties
│   │   ├── vram_alloc.py, palette_alloc.py, oam_alloc.py, window_alloc.py ← allocateurs matériels
│   │   └── runtime_codegen/         ← génération de main.c, des scènes et des acteurs (`gen_*.py`, `data_tables.py`)
│   ├── scripting/                   ← compilation Lua → C (voir section dédiée)
│   │   ├── parser.py / checker.py / codegen.py ← Lua texte → AST → C
│   │   ├── api.py                   ← RUNTIME_API : catalogue unique de l'API Lua ↔ C
│   │   └── lua_subset.py            ← le Lua accepté, et le refus qui dit quoi écrire (→ docs/scripting-reference.md)
│   ├── plugins/                     ← plugins chargés dynamiquement (spec_from_file_location)
│   ├── project_starters/            ← modèles de projet proposés à la création
│   └── ui/                          ← rangé par écran, pas par type de widget
│       ├── screens.py               ← le contrat d'un écran (ProjectScreen), le descripteur EditorScreen, `register_screen()`
│       │                              pour les plugins (cf. « Ajouter un écran »)
│       ├── common/                  ← transverse : theme.py (C couleurs / T typographie — jamais de valeur en dur),
│       │                              three_column_body.py (le squelette finder | centre | inspecteur), catalog.py,
│       │                              labels.py et notice.py (textes de l'éditeur, cf. « Textes de l'ÉDITEUR »), locate_bus.py
│       │                              (cf. « Locate et Reveal »), panneaux Build et Disk
│       └── <écran>/                 ← home, scene_manager, sprite_editor, background_editor, palette_editor, data_editor,
│                                      sound_mixer, script_editor, text_editor : un fichier par sous-zone
│                                      (`*_finder_panel` | centre | `*_inspector*`), assemblées par `*_screen.py`
│                                      (scene_manager : `inspectors/`, un fichier par classe d'inspecteur, routés par
│                                      `dynamic_inspector.py` qui construit chaque inspecteur à sa PREMIÈRE venue)
├── runtime/                         ← le moteur GBA écrit À LA MAIN, en C. Aucun .py : pour l'éditeur c'est de la DONNÉE,
│   │                                  jamais importée, seulement recopiée dans build/ (cf. app_paths.RUNTIME_DIR)
│   ├── Makefile                     ← copié dans build/, pilote arm-none-eabi-gcc
│   └── include/
│       ├── gba_engine.h             ← le gros du moteur : VRAM, layers, windows, blending, palettes, fonds animés, texte, SRAM.
│       │                              Inclus UNE SEULE FOIS, depuis le main.c généré
│       ├── runtime_api_inline.h     ← l'API des scripts écrite à la main, incluse par chaque unité de compilation après le
│       │                              `runtime_api.h` GÉNÉRÉ (cf. « Prototypes et énumérations »)
│       ├── actor_types_static.h     ← structs et constantes GBA, partie non générée
│       └── gba_debug.h              ← sortie de debug
├── packaging/                       ← packaging Nuitka + CI (voir section dédiée) : nuitka_build.py (commande unique, CI et local),
│                                      check_deps.py (requirements.txt vs imports réels), windows/installer.nsi, linux/ (AppImage)
├── tools/                           ← check_architecture.py (les règles de ce document, rendues exécutables, cf. « Les règles
│                                      ci-dessus se vérifient toutes seules »), check_ui_text.py, migrations ponctuelles de format
├── tests/                           ← `pytest tests` — un dossier par tâche (rom_build, scripting, graphics, text, ui, audio, …).
│                                      Les tests d'erreurs SILENCIEUSES (pas d'exception, une ROM fausse) sont dans graphics/ et
│                                      text/ ; `text/test_text_layout_native` = ÉQUIVALENCE Python ↔ C (compile le vrai
│                                      gba_engine.h, saute sans compilateur C hôte, cf. `CC`) ; `native/` = la sonde C et des
│                                      en-têtes libgba bidon, de quoi compiler le moteur sur PC
├── .github/workflows/               ← tests.yml (contrôle d'architecture + tests à chaque poussée), release.yml (build + release)
└── Project Demo/                    ← modèles de projet téléchargeables (voir README)
    └── <Projet>/
        ├── <Projet>.project         ← manifeste : config racine (scène de départ, auteur, version) ET point d'entrée du
        │                              double-clic ; le nom du projet EST le nom du fichier
        ├── assets/                  ← TOUT ce que l'auteur manipule ; il l'organise lui-même. Un asset = un fichier (+ sidecar
        │                              JSON pour une image) : sprites, backgrounds, scripts Lua, palettes, scenes, prefab, data
        │                              (.table), ui_layouts, boîtes sonores, fonts_assets ; à la racine texts.json (corpus),
        │                              texts_<code>.json (traductions jointes par id) et variables.json
        ├── project/                 ← ce qui n'est PAS à l'auteur : editor/ (état interne), licenses/, README.md
        └── build/                   ← 100% généré, gitignored — compile assets/
```

---

## Conventions d'écriture

Comment nommer et écrire, dans les trois langages que le projet fait cohabiter (Python de l'éditeur, C généré, C écrit à la main). La règle n'est pas esthétique : chaque casse **porte une information**, et un lecteur doit pouvoir déduire la nature d'un identifiant de sa seule forme.

### Visibilité Qt et micro-fenêtres

**Toujours donner un parent à un widget enfant avant `show()` ou `setVisible(True)`.**
Sans parent, Qt le considère comme une fenêtre indépendante : le montrer puis le
rattacher à un layout provoque une micro-fenêtre qui apparaît et disparaît à la
construction de l'interface. Créer l'enfant avec son parent, attacher ses layouts,
puis appliquer sa visibilité. Un layout encore détaché ne garantit pas le parentage.
Lors d'une reconstruction, masquer aussi un enfant visible **avant** `setParent(None)`.

Garde-fou : `tests/ui/test_cartridge_preview.py::test_project_settings_never_show_temporary_top_level_widgets`
observe les événements Qt `Show` : aucune fenêtre pendant la construction. Ne pas le traiter par un délai
ou un masquage tardif.

### La casse dit la nature

| Casse | Nature | Exemples |
|---|---|---|
| `snake_case` | variable, fonction, méthode, argument — Python **et** C | `frame_w`, `bg_se_addr()`, `resolve_actor_tiles()`, `pal_bank` |
| `PascalCase` | classe / dataclass Python, struct C, concept du domaine | `BackgroundLayer`, `CollisionBoxComponent`, `struct Actor` |
| `UPPER_SNAKE` | constante de module, `#define` C, énumération matérielle | `RUNTIME_API`, `DOMAIN_SCENE`, `WINR_0`, `OBJ_MODE_WINDOW` |
| `_leading_underscore` | **interne**, non-API : fonction/méthode/attribut qu'on ne doit ni importer ni appeler de l'extérieur | `_emit_api_call()`, `_check_args()`, `self._vec_types` |
| `g_`, `_sh` | préfixe/suffixe C réservés au moteur : `g_` = état global runtime, `_sh` = registre *shadow* (copie RAM d'un registre write-only) | `g_actors[]`, `g_bgcnt_sh[4]`, `g_bg_ofs_x[4]` |

**Le fichier suit son contenu** : un fichier Python est nommé d'après la classe qu'il porte, en `snake_case` (`background_layer.py` → `BackgroundLayer`, `assets_finder_panel.py` → `AssetsFinderPanel`). Un écran range ses fichiers par sous-zone, pas par type de widget (cf. `ui/`).

**La seule exception à `snake_case` en Python : les surcharges Qt.** Une méthode qui *redéfinit* un slot de Qt garde la casse de Qt (`paintEvent`, `mousePressEvent`, `sizeHint`, `eventFilter`) — c'est un contrat imposé de l'extérieur, pas un nom qu'on choisit. Tout le reste du code Python, y compris nos propres méthodes sur une sous-classe de widget, reste `snake_case`. Pas de `camelCase` maison nulle part.

### Les symboles C générés portent leur origine dans leur nom

Le C émis se relit avec le vocabulaire de l'éditeur — un symbole généré nomme d'où il vient, par un préfixe stable dérivé du concept :

| Concept éditeur | Symbole C généré | Forme |
|---|---|---|
| table de données `Objets` | `g_data_Objets` | `g_data_<Table>` |
| paire de fonctions d'une scène `X` | `scene_init_X` / `scene_tick_X` | `scene_<verbe>_<Scene>` |
| instanciation d'un `Prefab` poolé par une scène | `spawn_Arene_Balle` | `spawn_<Scene>_<Prefab>` (per-scène, rend `Actor*`/`NULL`) |
| variable globale / constante de projet | `g_<nom>` / `CONST_<NOM>` | accès pointé `global.nom` / `const.nom` |
| entrée de domaine (`DOMAIN_SCENE`…) | `SCENE_<Nom>`, `PAL_<Nom>`, `CAM_<Nom>` | `<PREFIX>_<Nom>` (cf. `api.py`) |

Ces préfixes ne sont pas décoratifs : ils garantissent l'unicité dans l'espace de noms C plat (pas de collision entre une scène et une palette homonymes) et rendent un identifiant traçable jusqu'à la donnée-source d'un coup d'œil.

### Un concept, un seul mot — la grammaire unique

C'est la règle qui prime sur tout le reste : **un concept a un seul nom, écrit identiquement dans le C généré, la classe Python et le label UI.** L'éditeur doit être transparent sur ce qu'il produit ; l'utilisateur ne doit pas apprendre deux vocabulaires.

- **Pas d'abréviation**, même « évidente » : `CollisionBox`, jamais `CollBox` ; `rotation`, jamais `rot` ; `scale_x`, jamais `sx`. Les rares abréviations historiques qui subsistaient (`sprite_rot`, `offset_x`) ont été résorbées vers la forme longue (`sprite.rotation`, `sprite.offset_x`).
- **Suffixe `Component`** obligatoire pour tout composant attachable à un `Actor` — jamais `Comp`, `Behavior`, `System` : `SpriteComponent`, `CollisionBoxComponent`, `ScriptComponent`.
- **Le nom C reflète exactement le concept Python** sans le raccourcir : `CollisionBox` en C ↔ `CollisionBox`/`CollisionBoxComponent` en Python.
- **Renommer, c'est renommer partout.** Un changement de nom touche la classe, le fichier, les labels et les références — pas seulement le libellé UI. Un renommage éditeur (`Project.rename_*`) réécrit d'ailleurs les références Lua par repérage **structurel**, jamais textuel : ni les commentaires ni les chaînes sans rapport ne bougent.

Avant de nommer un nouveau type (struct C, classe Python, label UI), vérifier que le **même mot** est employé aux trois endroits. En cas de doute entre « juste le libellé » et « renommage complet », c'est toujours le renommage complet.

### Locate et Reveal — deux gestes, deux noms

Montrer où vit un fichier a deux sens, et ils ne se mélangent pas :

| Geste | Où il mène | Libellé | Code |
|---|---|---|---|
| **Locate** | l'onglet **Disk** de l'éditeur, le fichier sélectionné | `common.locate` (« Locate ») | `ui/common/locate_bus.py` → `window._locate_file` |
| **Reveal** | l'**explorateur du système**, le fichier sélectionné (son dossier s'il n'y a pas moyen) | `common.reveal` (« Reveal ») | `ui/common/reveal.py` |

Locate part de partout (l'icône ferrée à droite de chaque ligne d'un finder, le clic-droit d'un acteur du canvas ou de l'arbre de scène) et aboutit en un seul endroit, la fenêtre, qui possède l'onglet Disk : l'émetteur dit seulement QUEL fichier, jamais comment l'afficher. Reveal, lui, n'a pas besoin de la fenêtre. Un finder tient les deux derrière `AssetKind.file_of` (le fichier d'un asset, la même table que l'arbre Disk) : une famille qui le déclare gagne l'icône et les deux entrées de menu, sans autre câblage. Le bouton « dossier » qui ouvrait seul le dossier d'une famille n'existe plus.

---

## Terminologie

### Correspondances éditeur ↔ GBA / grit

Ces concepts ont un équivalent direct dans le hardware ou la toolchain.

| Éditeur | GBA / grit | Description |
|---------|------------|--------------|
| `SpriteAsset` | tiles OBJ VRAM | PNG converti par grit en tiles 8×8 chargées dans OBJ VRAM |
| `TileCell` | tile index VRAM | Une tile 8×8 référencée par son index dans VRAM |
| `AnimFrame` | plage de tile indices | Un état visuel = N tiles dans VRAM |
| `Actor` | `struct Actor` + `OBJATTR` (OAM) | Une entrée de `g_actors[]` en EWRAM ; son affichage est une entrée de `g_oam_entries[]` (`OamEntry`), que `Actor.oam_entry` désigne. `CollisionBoxComponent` → `Actor.collision` (cf. « Deux tables runtime : acteurs et entrées OAM ») |
| `BackgroundLayer` | charblock (CBB=`bg_slot`) + screenblock | `{image, bg_slot, scroll_speed, pal_bank, tile_palette_overrides}` — un plan BG physique **de la scène** |
| `BackgroundAsset` | tileset + sous-palettes | Sidecar (`assets/backgrounds/{image}.background`), keyé par nom comme `SpriteAsset` — PNG source jamais modifié
| `Scene.background_layers` | jusqu'à 4 `REG_BGxCNT` | Liste de `BackgroundLayer` inline dans le JSON de la scène (chacun référence un `BackgroundAsset` par nom d'asset) |
| `PaletteBank` | 16 couleurs BGR555 | Palette nommée du catalogue (`assets/palettes/*.json`), partagée OBJ/BG |
| `Scene.active_obj_palettes` / `Scene.active_bg_palettes` | 16 banques `PAL_OBJ`/`PAL_BG` | Sélection ordonnée (index = banque hardware) des palettes actives de la scène ; `pal_bank` indexe dans cette liste |
| `Scene` | `scene_init_X` / `scene_tick_X` | Paire de fonctions C dispatchées via vtable dans `main.c` |
| `ScriptComponent` (Lua) | fonction C compilée | Le Lua est transpilé vers C, pas interprété à l'exécution |

### Abstractions pures de l'éditeur

Ces concepts n'ont pas d'équivalent direct dans grit ou le hardware GBA.

| Concept | Rôle | Résolution au build |
|---------|------|----------------------|
| `Prefab` | Template d'acteur réutilisable | Chaque instance génère son propre code C |
| `AnimState` | État d'animation nommé (`Idle`, `Walk`…) | Converti en index entier, pas de concept GBA natif |

### Components

| Nom | Rôle | API Lua |
|-----|------|---------|
| `SpriteComponent` | Lien vers un `SpriteAsset`, état initial, vitesse d'animation... | `self:play_anim("state")` `self.anim` (lecture, comparable par nom) `self.anim_speed = n` (surcharge, 0 = vitesse de l'état) `self.anim_length` / `self.anim_loop` / `self.anim_finished` (lecture) `self.frame_w` / `self.frame_h` (lecture) `self.frame = n` `self:show()` / `self:hide()` (écriture) et `self.visible` (lecture seule) `self.flip_h = bool` `self.pal = n` `self.priority = n` |
| `CollisionBoxComponent` | AABB de collision. `solid` ne décide que d'une chose : la box est-elle arrêtée par la carte de collision de la scène | handlers du script de l'actor (pas du composant) : `on_collision_enter(other, my_box, other_box)` `on_collision_exit(...)` `on_collide(...)` `on_tile_collide(nx, ny)` |
| `SoundFxComponent` | Déclenche un effet sonore lié à l'acteur | `sfx:play("name")` |
| `ScriptComponent` | Attache un script Lua à l'acteur — **un seul actif par actor** (le compilateur n'en lit de toute façon qu'un seul) | `on_start()` `on_update()` `on_late_update()` |
| `PathComponent` | Chemin de déplacement (waypoints) | — (en cours) |

### Deux tables runtime : acteurs et entrées OAM

L'éditeur distingue trois choses : un **actor** (logique de jeu), un **sprite** (son rendu),
un **background** (le décor). Le C a **deux tables**, et leur unité n'est pas la même :

| Table | Un indice = | Type |
|---|---|---|
| `g_actors[]` | un **acteur** | `Actor` : identité, position, vélocité, transform monde, collision, lien `oam_entry` |
| `g_oam_entries[]` | une **entrée de l'OAM** | `OamEntry` : tout l'état d'affichage (`frame`, animation, registres OAM, transform local, `affine_slot`) |

`g_oam_entries[k]` double `shadow_oam[k]` entrée pour entrée : c'est l'état logiciel derrière un
`OBJATTR`. Le nom dit ce qu'est la chose — une entrée de l'OAM — et non un composant d'acteur :
elle n'est pas propre au sprite d'un acteur, les bandes de texte et l'interface en occupent aussi
(cf. ROADMAP, « La struct `Actor` allégée »).

**Pourquoi séparer.** Un acteur qui n'affiche rien (contrôleur, spawner, déclencheur) ne doit
pas payer un état d'affichage, ni réserver un slot OAM qu'il n'utilise pas. Tant que la struct
était plate, `g_actors[idx]` et `shadow_oam[idx]` partageaient le même indice : l'empreinte OAM
d'une scène dimensionnait les acteurs. Deux tables permettent de compter chacune dans sa propre
unité.

**Le coût d'exécution est borné.** Le writer OAM et le tick d'animation sont **émis au build**,
un bloc par entrée, et connaissent son indice : ils écrivent `g_oam_entries[k]` à adresse fixe,
sans déréférencement. Seuls les accesseurs de script, qui reçoivent un `Actor*`
(`actor_get_frame(const Actor*)`), traversent le lien : `actor_oam_entry(s)` =
`&g_oam_entries[s->oam_entry]`, un déréférencement par accès de script.

**Types étroits.** Un slot OAM se paie une entrée par frame d'écriture : `OamEntry` fait 32
octets (`s16` puis `u8`, sans remplissage) et `Actor` 68, contre 92 et 96 quand tout était `int`.
Position et vélocité restent en `int` (Q8). Les plafonds sont figés par un test qui mesure
`sizeof` avec le compilateur hôte.

**Les deux géométries.** Par scène, `codegen/oam_alloc.py` calcule :

    g_actors[]      = [acteurs posés][pools : instances × parties]
    g_oam_entries[] = [entrées des posés À SPRITE][interface & texte][entrées des pools À SPRITE]

Seul un porteur de sprite (`has_oam_entry`) occupe une entrée : un contrôleur, un déclencheur ou
un marqueur de prefab (point de tir, ancre de hitbox) existe dans `g_actors[]` avec
`oam_entry = -1`. Les bandes de texte et les images d'interface OBJ occupent des entrées sans
acteur, ancrées juste après les posés (`OamLayout.ui_start`). Les pools gardent un indice
d'acteur (`POOL_*_START`, `self - &g_actors[START]`) et une entrée de départ distincte : le
spawn avance dans les deux espaces à des pas différents (`_i += groupe`, `_e += entrées par
instance`).

**Acteur sans sprite : lecture = 0, écriture sans effet.** `self.frame`, `self:show()`
restent appelables sur un acteur sans entrée : `actor_oam_entry()` lui rend alors une entrée
nulle, remise à zéro à chaque appel, que rien ne lit.

Ce qui EST séparé de longue date, c'est la **définition** du sprite — états, directions,
vitesses, boucles — qui n'est pas une struct du tout mais des tables `static const` en ROM,
émises par sprite (`sprite_{nom}_anim_dirs`, `_state_start`, `_state_speed`, `_state_loop`, et
les `_frame_action`/`_frame_sfx`/`_frame_event` optionnelles). **La coupure est
const/variable, pas classe/classe.**

**Le background n'a pas de type parce que le calque EST le matériel.** `layer_show(int bg, …)`,
`layer_set_scroll(int bg, …)`, `tilemap_set(int bg, …)` — l'état tient dans les registres
ombres `g_bgcnt_sh[4]` et `g_bg_ofs_x/y[4]`. Il y a quatre plans dans la machine ; leur donner
un type instanciable suggérerait qu'on peut en créer un cinquième. Les seules structs BG sont
`BgAnim` et `BgTileAnim`, qui sont des **états d'animation**, pas des backgrounds.

**Nommer ses parties** (ROADMAP — chantier technique *La grammaire de la struct `Actor`*). Les
trois familles de champs se lisent avec le vocabulaire de l'inspecteur, pas un second :

| Bloc C | Composant éditeur | Champs |
|---|---|---|
| `Actor` (racine) | `Actor` | `x, y, vx, vy, tag, active, dir_x, dir_y, rotation, scale_x, scale_y, oam_entry` (rotation/scale = transform **monde**) |
| `OamEntry` (`g_oam_entries[]`) | `SpriteComponent` (aujourd'hui, seul consommateur) | `frame, anim_state, timer, anim_speed, anim_length, anim_loop, anim_finished, frame_w, frame_h, auto_dir, visible, flip_h, flip_v, pal_bank, obj_mode, priority, screen_space, rotation, scale_x, scale_y, offset_x, offset_y, affine_slot` (rotation/scale = transform **local**) |
| `Actor.collision` | `CollisionBoxComponent` | `grounded, last_x, slope_acc, box_count, boxes[]` |

Le namespace a supprimé les trois abréviations qui n'existaient que parce que la struct était
plate : `sprite_rot` → `rotation`, `sprite_scale_x/y` → `scale_x/y`, `offset_x/y` — désormais
sur `OamEntry`, où « local » se lit par opposition au monde de l'acteur.

**La surface Lua ne bouge pas** : `self.frame`, `self.sprite_scale`, `self.anim_length`
passent par les accesseurs de `runtime_api_inline.h`, seul endroit du dépôt (avec le C émis
par le codegen) qui touche les champs. `scripting/api.py`, `codegen.py`, `checker.py` et `expr_types.py` n'en connaissent
aucun — ils n'émettent que des `&g_actors[ACTOR_*]` et des appels `actor_get/set_*`. C'est cette
couche d'accesseurs qui a rendu le découpage possible sans rupture pour les projets existants.

**`self.anim_length`/`anim_loop`/`anim_finished` sont écrites sur `OamEntry`, pas lues dans la table du sprite.**
`anim_length` n'est pas `state_len[state]` mais la longueur du bloc de la **direction actuellement jouée**, que le
tick trouve par un parcours de `anim_dirs[]` avec repli sur la direction omni : les trois champs **mémoïsent ce
parcours**, et le tick d'animation (`main_gen._anim_tick_lines`) les écrit CHAQUE frame. `frame_w`/`frame_h` sont
posées une fois à l'init/au spawn, ce qui les rend lisibles sur un AUTRE acteur (`other.frame_w`). `anim_finished`
compare la position dans la séquence à `anim_length` : vrai dès la dernière case, jusqu'à un changement d'état, et
toujours faux pour un état qui boucle. À CHAQUE tick, avant tout calcul d'avancée, un `frame` hors de
`[_fs, _fs+_fc)` est ramené à `_fs` (et `timer` à 0) : `play_anim` remet `frame` à 0, absolu dans le sheet
dédupliqué, donc hors du bloc de tout état qui ne commence pas à l'offset 0.

**`self.priority`** est un champ `int` ordinaire d'`OamEntry` (même registre OAM que `pal_bank`/`obj_mode`), posé à
l'init depuis la valeur authorée (0 pour un acteur poolé) et modifiable par script ; l'émission OAM le lit.

### Règles clés

- **Une extension par type d'asset** — un asset stocké s'appelle `<nom>.<type>` (`Player.sprite`, `boom.sfx`, `Scene_01.scene`, `Night.palette`…), le contenu reste du JSON. La table unique est `core/models/asset_extensions.py` ; chaque modèle porte la sienne (`sidecar_extension`, déclarée sur `Resource`), `ResourceStore` la lit et cherche ses sidecars sous tout `assets/` (la racine que lui donne `Project`), `tools/migrate_sidecar_extensions.py` migre un projet d'avant. Restent en `.json` : `texts.json`, `texts_<langue>.json`, `variables.json`. Le `.hex` d'une palette est sa donnée canonique, que le `.palette` POINTE par son champ `asset` (les deux se rangent où l'on veut sous `assets/`) ; `.pal` et `.gpl` ne servent qu'à l'import et l'export.
- **`assets/` vs `project/`** — `assets/` est le dossier de l'auteur : TOUT ce qu'il manipule y vit, sources brutes (une image PNG, un son) comme ce qu'il crée dans l'éditeur (scènes, prefabs, mises en page, boîtes sonores, tables de données, polices logiques, textes, variables), et il l'organise lui-même. `project/` n'est plus à lui : il ne garde que l'état interne de l'éditeur (`editor/`), les licences et le README. Avant le 2026-10-10 les données propres à l'éditeur vivaient sous `project/` ; `tools/migrate_project_to_assets.py` migre un projet d'avant.
- `assets/` → la source de vérité des assets bruts ; le JSON sidecar est auto-géré par l'éditeur
- `assets/backgrounds/` → PNG bruts (`BackgroundAsset`) ; → sidecar d'importation par image (`BackgroundAsset` : tileset + sous-palettes, PNG jamais modifié). 
- `assets/palettes/` → catalogue unifié (`PaletteBank`), un `.hex` visible par palette + sidecar JSON ; rangé avec les assets car une palette s'importe et s'exporte comme un fichier externe (`.hex`), partagé OBJ/BG
- `assets/scripts/` → scripts Lua édités par le dev ; copiés dans `build/src/` au build
- `build/grit_out/` et `build/src/` → sorties générées conservées puis balayées à la fin du build ; `build/obj/` est conservé pour la compilation incrémentale. `build/.asset-cache.json` mémorise les empreintes des conversions dont les sorties existent encore.
- `<Nom>.project` → manifeste racine (v0.10, remplace `project.json`) : c'est LUI qu'on double-clique, associé à l'éditeur sur les deux OS, et son nom de fichier EST le nom du projet (aucune clé `name` dans le JSON). Config racine uniquement (scène de démarrage, auteur, version) ; un `project.json` d'avant v0.10 se relit une fois et se réécrit dans la nouvelle forme à la première sauvegarde ; `start_scene` (point de départ du **jeu**, éditable dans le ProjectInspector) et `last_scene` (dernière scène ouverte dans l'**éditeur**, restaurée à l'ouverture) sont deux champs distincts — ouvrir une scène ne redéfinit jamais le point de départ ; toutes les autres données vivent dans `assets/**/*.json`, y compris `assets/variables.json` (globals + constants, unicité de nom vérifiée par type — un global et une constante peuvent partager un nom)
- Les assets sont référencés **par nom** (ex. `SpriteComponent.sprite_name`, `BackgroundLayer.backgroundasset_name`, palette active par nom de `PaletteBank`) — jamais par chemin absolu
- Un argument de script qui cite un élément du projet est déclaré par le `domain` de son `Param` dans `scripting/api.py` (`DOMAIN_SCENE`, `DOMAIN_SFX`, `DOMAIN_GLOBAL`…). Cette table unique sert au checker (valider), au codegen (résoudre en index physique) et à `scripting/refactor.py` (suivre les renommages) : déclarer le domaine d'un nouvel argument suffit à alimenter les trois. Un renommage éditeur (`Project.rename_*`) réécrit les références Lua correspondantes en repérage **structurel** — jamais textuel, donc ni les commentaires ni les strings sans rapport ne bougent
- Les scripts Lua sont **transpilés vers C** au build, pas interprétés à l'exécution
- Les `GlobalVar` sont des variables C partagées entre tous les scripts du jeu (`globals.h` / `globals.c` générés une fois par build, pas par scène)
- Chaque scène génère une paire C `scene_init_X` / `scene_tick_X` dispatchée via une vtable statique dans `main.c`

---

## API Lua ↔ C

Le script Lua n'est jamais traduit directement en texte C : il passe par un AST Python intermédiaire, lui-même validé et traduit via un catalogue déclaratif unique.

```
texte Lua → parser.py → AST Python → checker.py (validation) → codegen.py → texte C
                                            ↑                        ↑
                                            └── scripting/api.py ──┘
                                          (RUNTIME_API : catalogue unique)
```

- **`parser.py`** — la grammaire Lua en dataclasses (`StmtIf`, `ExprInvoke` pour `self:method()`…). Spécifique à Lua : changer de
  langage de script réécrirait ce fichier et une partie du pattern-matching de `checker.py`/`codegen.py`, pas le reste.
- **`api.py`** (`RUNTIME_API`) — source de vérité unique de toute fonction Lua exposée : nom Lua, fonction C cible, types de
  paramètres, domaine de résolution des chaînes (`DOMAIN_ANIM`, `DOMAIN_SFX`, `DOMAIN_SCENE`…). Lu par `checker.py` (valider) et
  `codegen.py` (`_emit_api_call`).
- **`checker.py`** — valide l'AST contre `RUNTIME_API` (fonction connue, nombre d'arguments, variadiques comprises, nom de
  ressource existant). Seules les erreurs (`CheckError.level == "error"`) bloquent le build ; les avertissements (valeur littérale
  hors plage dans une globale typée) sont journalisés. Appliqué à tous les scripts (actor, scène, prefab) via
  `lua_compiler.py::_compile_script`. Les behaviors (`require("behaviors/x")`, résolus PAR NOM parmi les `.lua` marqués
  `-- @behavior`, `core/lua_scripts.py`, inlinés par `codegen.py::_emit_inlined_behaviors`) passent par le même checker avec
  `check_event_names=False` ; fichier manquant ou erreur de parse y remontent en avertissement.
- **`codegen.py`** — `_emit_api_call` génère l'appel C directement depuis l'entrée `RUNTIME_API`. Les fonctions qui ne se
  traduisent pas par un simple appel (`self:destroy` → deux instructions, `sfx.play` → arguments synthétisés) sont dans deux
  tables de dispatch en fin de fichier, `_INVOKE_CUSTOM` et `_CALL_CUSTOM`, et ont quand même une entrée de catalogue.
  `global.nom`/`const.nom`, `self.position` (RUNTIME_PROPS) et `data.Objets` sont des accès POINTÉS, résolus dans la branche
  `ExprIndex` de `_expr` et validés côté checker (`_check_global_scalar`, `_check_const_scalar`…), pas par le catalogue.
- **Important pour toute nouvelle fonction Lua** : si elle se traduit par un simple appel C avec conversion d'arguments, une entrée dans `RUNTIME_API` suffit *côté traduction*. Ce n'est que si elle a besoin de logique de traduction (nom C dynamique, arguments non présents côté Lua, émission multi-instructions) qu'elle doit aussi rejoindre `_INVOKE_CUSTOM`/`_CALL_CUSTOM`.
- **Une fonction du moteur exposée a son prototype GÉNÉRÉ** (« Prototypes et énumérations » ci-dessous) ; seules les énumérations redéfinies à la main côté moteur et l'ordre des arguments sont comparés au build.
- **`lua_subset.py`** — la LISTE de ce que le langage accepte, et de ce qu'il refuse en le disant. Chaque nœud de luaparser est
  `ACCEPTED` (il se traduit), `REFUSED` (avec la phrase qui dit quoi écrire) ou `STRUCTURAL` (jamais dispatché) ; la bibliothèque
  standard de Lua reçoit le même traitement, par nom. Trois consommateurs : `checker.py` (refuser en nommant l'issue),
  `docs/scripting-reference.md` (un test échoue si un refus n'y est pas documenté) et `validator._check_lua_subset` (**erreur
  bloquante** si un nœud n'est classé nulle part). Les nœuds non traduits sont PORTÉS (`StmtUnsupported`, `ExprUnsupported`, avec
  leur ligne) : le parser décrit, le checker juge. Une faute de SYNTAXE est le seul refus que le parser prononce (`LuaParseError`
  porte `line` et une phrase, cf. `_syntax_message`).
- **`expr_types.py`** — les deux exceptions au sous-ensemble Lua scalaire. `vec2(x, y)`/`vec3(x, y, z)` sont des constructeurs de
  langage, pas des entrées `RUNTIME_API` ; `+ - * /` s'y traduisent en `vec2_add`/`vec2_sub`/`vec2_scale`/`vec2_div`
  (`runtime_api_inline.h`), un entier mêlé à un vecteur vaut ce vecteur dont toutes les composantes sont cet entier (`v + 2` =
  `v + vec2(2, 2)`), la division est entière, et `dot(a, b)` (`VEC_FUNCTIONS`) rend un entier. La seconde exception sont les
  **références** (`local pas = sfx:play("Pas")`) : une valeur composée se copie, une référence DÉSIGNE un slot de pool. Checker et
  codegen partagent ce module pour répondre à « quel type porte ce nom ? » (`self._vec_types`, remplie au fil d'un parcours à plat).

### La grammaire cible de l'API — trois formes, une par nature

**Grammaire visée (ROADMAP v0.16, non verrouillée).** Le catalogue livré emploie encore `module.action(…)` ; la forme n'est pas
un choix stylistique : elle dit au parseur quoi produire (`Invoke` pour `:`, `Index` pour `.`), donc qui décide de la résolution.

| Syntaxe | Nature | Compile en |
|---|---|---|
| `identifier:member(...)` | **méthode** — opération sur une instance, qui peut produire un effet | `actor_member(récepteur, ...)`, ou `sfx_member(...)` sur une référence |
| `identifier.member` | **propriété** — donnée que l'API expose comme un état, lue et écrite | `actor_get_member(...)` / `actor_set_member(...)` |
| `module.member` | **propriété de singleton** — état d'un système moteur | `module_get_member()` / `module_set_member()` |
| `module:member(...)` | **méthode de singleton** — opération au niveau du système | `module_member(...)` |

`identifier` dans la forme méthode est une **instance** : un acteur (`self`, `other`, une variable d'actor) ou une **référence**
rendue par un appel (`local pas = sfx:play("Pas")` → `pas:set_volume(80)`). Le catalogue range les méthodes d'acteur sous la clé
`self:` et celles d'une référence sous le TYPE qu'elle porte (`sfx:`), relevé sur le `local` par `expr_types.infer_ref_type` ; une
référence porte aussi des **propriétés** (`hb.solid = false`, déclarées dans `RUNTIME_PROPS` sous `collision_box.champ`, le
checker refusant l'écriture d'un champ en lecture seule). Un module du moteur est un **singleton**, donc un récepteur comme une
instance : états en propriétés (`camera.position`, `music.volume`), opérations en méthodes (`camera:follow(...)`). Une
bibliothèque sans état, telle que `math`, reste une exception nommée (`math.abs(x)`).

La règle de décision pour TOUTE API future, dérivée des définitions ci-dessus :

- **état intrinsèque** → propriété (`self.position`, `blend.mode`) — jamais un
  appel `get_*`/`set_*`.
- **requête pure sans argument** (`input.axis`, `scene.frame`) → c'est
  de l'état déguisé en fonction → propriété en lecture seule.
- **requête INDEXÉE** (`hb:get_collision_tile(x, y)`, `save:read(slot, "nom")`, `layer.get_*(n)`) →
  reste une fonction : une propriété ne prend pas d'argument.
- **action qui produit un effet** → méthode sur son récepteur, qu'il soit une instance
  (`self:move(...)`) ou un singleton moteur (`scene:switch(...)`, `sfx:play(...)`).
- **cycle de vie** (décision du 2026-09-25, non encore migrée dans le catalogue) → **cinq verbes
  communs**, `:show()`, `:hide()`, `:activate()`, `:deactivate()`, `:destroy()`, seule porte
  d'ÉCRITURE ; l'état se lit par `visible` / `active` en **lecture seule**. C'est la seule
  exception à « réglage runtime → lecture ET écriture » : `x.visible = false` n'existe pas, sinon
  deux portes diraient la même chose. Voir « Cycle de vie » plus bas.
- **réglage d'inspecteur** → il a TOUJOURS une porte, dont la nature dit ce que le runtime sait
  faire : modifiable au runtime → lecture ET écriture ; fixé au build (le C émis en dépend, ou il
  réserve du matériel) → lecture seule (`self.screen_space`, `self.affine`, `self.box_count`).
  Un champ édité à l'éditeur mais invisible du script est un oubli, pas un choix. Un élément
  adressé par un NOM du projet (une boîte par son tag) s'obtient par un CONSTRUCTEUR de référence
  (`local hb = self:collision_box("hitbox")`) ; ses champs sont alors des propriétés
  (`hb.solid`, `hb.size`) et ses actions des méthodes (`hb:overlaps(other)`).

Deux cas hors des trois formes : la **fonction libre** `array` (une déclaration) et les **constructeurs** (`vec2(x, y)`).
`global.nom` / `const.nom` sont de la forme PROPRIÉTÉ, sans getter/setter : `nom` est un nom de PROJET (pas d'entrée
`RUNTIME_PROPS` possible, ce serait un catalogue régénéré à chaque édition de l'écran Variables). Ils compilent en accès direct
(`g_nom` / `CONST_NOM`), validés par `BuildContext.global_counts` / `.const_names`, comme `data.Objets`.

Deux conséquences qui se paient cher si on les oublie :

- **Méthode et propriété s'écrivent sur N'IMPORTE QUEL acteur nommé**, pas seulement `self` (`other.velocity`,
  `other:move(...)`) : le catalogue les range sous la clé `self:`/`self.` — une clé, pas une restriction — et `checker.py` valide
  tous les récepteurs. Seule exception, bloquée explicitement : un argument OU une comparaison de propriété dont le nom appartient
  au sprite du RÉCEPTEUR (`other:play_anim("walk")`, `other.anim == "walk"`), que le contexte de build ne peut ni vérifier ni
  résoudre (`checker._RECEIVER_DOMAINS`, jugé dans `_check_args` ET `_check_prop_domain_value`).
- **Une propriété peut porter un domaine** (`ApiProp.domain`) et s'écrire ou se comparer par un NOM : `self.obj_mode = "window"`,
  `blend.mode == "alpha"`, `other.name == "Ball"`. C'est le même `DOMAIN_*` que sur un paramètre, jugé par les mêmes tables
  (`checker._DOMAIN_CHECKS`, `codegen._DOMAIN_CONSTANT`) ; le C ne change pas (`OBJ_MODE_WINDOW` vaut un entier). Quand la forme
  nommée n'atteint pas l'état par la même fonction C que la forme ordinaire (`self.direction` : vec2 côté calcul, boussole côté
  nom), `c_getter_named`/`c_setter_named` portent la seconde porte.

### Module, type, instance — d'où vient le récepteur (ROADMAP v0.16, non verrouillée)

Les trois formes disent **comment ça s'écrit** ; il manque **de quel TYPE est le récepteur, et où le catalogue le range**.

| Mot | Ce que c'est | Exemple |
|---|---|---|
| **module** | un namespace : un système unique (singleton), ou une **fabrique** d'instances | `camera`, `scene`, `actor` (`get`/`spawn`/`count`) |
| **type** | une sorte de chose qui a des instances ; **son nom est la clé du catalogue** | `sfx`, `collision_box`, `ui_element`, `actor` |
| **instance** | une chose précise ; `self` et `other` en sont, une variable qui tient une référence aussi | `self`, `local hb = …` |
| **référence** | la valeur qui désigne une instance quand elle ne se déduit pas du contexte | rendue par une acquisition (`actor.get`, `interface.get`) ou une action (`sfx.play`) |

**Le module gère, crée ou acquiert ; le type expose l'état et les opérations d'une instance.** Un module n'opère jamais sur UNE
instance désignée par un nom du projet : c'est soit un système sans instance (`scene`, `camera`), soit une fabrique (`actor`). Tout
ce qui porte sur une instance nommée s'écrit en méthode ou en propriété **sur la référence** :

```lua
local menu = interface:get("Menu")     -- fabrique : une chose nommée du projet
menu.index = 0                         -- propriété
menu:show()                            -- méthode
```

Le numéro de matériel reste la porte des choses numérotées par le matériel, mais c'est aussi une acquisition (`layer:get(n)`) : le
fond `n` est une référence de type `background_layer`. Les fonds qu'une scène a dépendent de son mode vidéo
(`api.LAYERS_BY_MODE` × `Scene.render_mode`, passé au checker par `lua_compiler`) ; seul le mode 0 est offert à l'auteur, et rien
de ce qu'il lit ne parle de mode (un test le garde).

**Ce qui reste à migrer** : `window.*` (7 fonctions qui reçoivent encore le nom d'une instance) et
`layer.*` (numéroté par le matériel). Le type acteur est rangé sous `actor:` ; `sfx`, `collision_box` et
`ui_element` sont des lignes de `api.REF_TYPE_TABLE`. Dans le C émis, « absent » est UNE chose : `nil` vaut 0
(`if p ~= nil` → `(p != 0)`, `tests/scripting/test_ref_type_table.py`) ; une référence d'élément d'interface est un
index connu au build, jamais absente.

**Ce que ça ne coûte pas.** Une référence à une chose STATIQUE du projet (`interface:get("Menu")`,
`window:get("Panel")`) se résout au build en constante, comme `TEXT_<clé>` : aucun slot, aucun
test à l'exécution. Seules les références de POOL (`actor.get`, `sfx.play`, `actor.spawn`) portent
une valeur qui peut être périmée ou absente.

**Déclarer un type de référence — trois gestes, aucun cas spécial** (livré, v0.16 étape b).

1. UNE ligne dans `api.REF_TYPE_TABLE` : `RefType(c_type=…, prefix=…, hint=…)`. Le type C du
   `local` qui tient la référence, la variable des snippets, la phrase ajoutée à l'erreur
   « méthode/champ inconnu ».
2. Ses entrées de catalogue : la fabrique (`ApiFunc(ret="<type>")`), les méthodes sous
   `"<type>:<méthode>"`, les propriétés sous `"<type>.<champ>"`.
3. Les fonctions C, déclarées DEUX fois (section suivante).

Tout le reste s'en dérive : le `local` typé (`codegen`), le refus d'un membre inconnu
(`checker._unknown_ref_method` / `_unknown_ref_field`), les snippets (`api_snippets`), le
renommage (`refactor`). `tests/scripting/test_ref_type_table.py` déclare un type factice `gizmo` par ces trois
gestes seulement et vérifie qu'il se vérifie et se traduit — chaîné ou non — sans toucher
`checker.py` ni `codegen.py`. Seule une traduction C réellement atypique reste un cas de
`_INVOKE_CUSTOM` (`ui_element:show` → `ui_element_show(h, 1)`).

**Le garde-fou.** Comme `_check_api_domains` et `test_inspector_api_parity`, un test échoue si une
entrée de `RUNTIME_API` de la forme `module.fonction` prend en premier paramètre un domaine d'INSTANCE
(`ui_list`, `image`, `region`, `win_region`…) : la règle ne tient pas sur la discipline, elle tient
sur le catalogue.

### Cycle de vie — cinq verbes, communs à tous les types (décision du 2026-09-25)

Montrer, cacher, activer, désactiver et détruire s'écrivent pareil sur toute instance :

```lua
interface:get("menu"):hide()
interface:get("menu"):deactivate()
window:get("Panel"):hide()
actor:get("Boss"):destroy()
if menu.visible then ... end      -- lecture seule
```

| Verbe | Effet | Propriété de lecture |
|---|---|---|
| `show()` / `hide()` | rendre visible / invisible | `visible` |
| `activate()` / `deactivate()` | participer / ne plus participer (collision, entrée, navigation) | `active` |
| `destroy()` | libérer l'instance ; la référence devient périmée (`nil`) | — |

Règles :

- **Une porte d'écriture, une de lecture.** Pas de `x.visible = …` en écriture, pas de
  `layer.show(n, on)` ni de `list.set_active(nom, on)` — ces portes n'existent plus. Une valeur
  calculée s'écrit avec un `if`.
- **Chaque type déclare les verbes qu'il supporte** (dans sa ligne du catalogue) ; le checker refuse
  les autres. Une `collision_box` n'a pas `show`, un `sfx` n'a aucun des quatre premiers.
- **`destroy` ne vaut que pour les instances de pool** (acteur, `sfx`). Un élément d'interface ou
  une fenêtre est statique, connu au build : `destroy` y est une erreur du checker.
- **Le type de base `ui_element` porte `show`/`hide`/`activate`/`deactivate`** ; les types concrets
  (`list`, `image`, `button`…) ajoutent leurs propres états et actions.
- **Migré** : acteur, boîte, `ui_element` et ses natures, fonds (`background_layer`) et régions de
  window (`window_region`) — ROADMAP v0.16, étape (c) et (d). Reste `self:` → `actor:` (étape e).
  Les types `background_layer` et `window_region` ne portent pas le nom de leur module : un type
  `layer` aurait donné à `layer.priority` deux lectures (propriété du type, ou fonction du module).

### Prototypes et énumérations : générés depuis le moteur

`gba_engine.h` porte l'implémentation du moteur ; les scripts d'actor et de scène sont compilés en unités de
traduction séparées qui ne l'incluent pas. Leurs prototypes sont **générés** dans `runtime_api.h`
(`codegen/runtime_codegen/api_prototypes.py`) pour le seul sous-ensemble exposé par le catalogue : une fonction
exposée ne peut plus manquer de déclaration. `runtime_api_inline.h` porte, à la main, l'API en `static inline`.

`validator._check_api_prototypes` garde ce que la génération ne couvre pas, en **erreur bloquante** :

- l'ACCORD de VALEUR des énumérations entre `api.py` (leur source, d'où sont générés les `#define`) et les
  quelques-unes que `gba_engine.h` redéfinit à la main (`BLD_MODE_*`, `BLD_SIDE_*`) : sinon `main.c` et les scripts
  verraient deux valeurs, sans erreur ;
- l'ORDRE des arguments entre `api.py` et `gba_engine.h` : une permutation compile proprement (tout est `int`) et
  range chaque valeur dans le mauvais paramètre.

### Ce que l'éditeur INSÈRE dérive du catalogue

`scripting/api_snippets.py` fabrique le Lua que la sidebar du Script Editor propose au clic, depuis `RUNTIME_API` : écrits en dur,
ces snippets pourrissaient (le checker laisse passer un appel inconnu, qui peut être un helper de l'utilisateur, donc l'erreur
n'arrivait qu'à la compilation C). `call(name, **by_domain)` remplit les arguments **par domaine** et non par position : un
réordonnancement de paramètres dans `api.py` n'invalide aucun appelant. Même logique pour `api_reference.json`, qui ne décrit que
la *présentation* (groupes, ordre, descriptions) : `api_reference.get_categories()` le filtre par le catalogue puis le complète
avec lui, si bien qu'une fonction retirée disparaît de l'écran et qu'une ajoutée y apparaît sans toucher au JSON.

### Un domaine a TROIS consommateurs, et deux ne le disaient pas

Le `domain` d'un `Param` sert à `refactor` (suivre les renommages), au `checker` (le nom existe-t-il ?) et au `codegen` (quelle
constante C émettre ?). Le premier **dérive** sa table du catalogue (`_reference_sites()`). Les deux autres sont des **tables**,
comparées à `api.ALL_DOMAINS` (dérivé des constantes `DOMAIN_*`) par `validator._check_api_domains`, en **erreur bloquante** : un
domaine absent n'y produirait aucun signal (le checker ne validerait rien, le codegen émettrait la chaîne telle quelle, donc du
texte C là où le C attend un entier, avec une panne au `make` loin de la cause). Placer un nouveau domaine dans une case fait
partie de son ajout :

| Côté | Cases |
|---|---|
| `checker` | validé par domaine (`_DOMAIN_CHECKS`) ou non validé **avec sa raison** (`_DOMAINS_UNCHECKED` — seul `tag` y est) |
| `codegen` | constante générique (`_DOMAIN_CONSTANT`) ou émetteur dédié (`_DOMAIN_EMITTED_ELSEWHERE`) |

Chacun n'expose qu'un `covered_domains()` — le contrôle demande « ce domaine
t'est-il connu ? », pas la mécanique interne.

### Un nom se vérifie par son DOMAINE, pas par le nom de l'appel

Le contrôle d'un nom s'accroche au `domain` du `Param`, jamais à la clé de l'appel : une seconde fonction prenant
`DOMAIN_SCENE` est validée sans rien ajouter. `DOMAIN_PREFAB` est une **erreur** de checker (sinon `spawn_<Scene>_<Nom>`
n'échoue qu'au `make`, sur un « implicit declaration »), contre la liste PROJET des prefabs
(`BuildContext.prefab_names`, remplie par `lua_compiler`) — le raffiner en « poolé DANS CETTE scène » est possible
depuis le spawn per-scène (ROADMAP v0.17). Ce qui reste accroché à un appel dans `_check_call_expr` : le numéro
d'emplacement d'un `save.*`. La **valeur** d'un `global.nom = v` (plage du type déclaré) se vérifie à l'ASSIGNATION
(`_check_global_write_value`, sur `StmtAssign`).

**Une collision a deux côtés, et chacun l'apprend dans son propre script.** Le tick de scène teste scène↔scène et
pool↔scène, et appelle `on_collision_enter` des DEUX acteurs dans les deux cas, avec les boxes échangées (la
`my_box` de l'un est l'`other_box` de l'autre), sur le même test de recouvrement et le même souvenir de frame
(`_pcol_`).

### Tableaux — la forme est reconnue une fois, employée deux fois

Un tableau se déclare de deux façons, et c'est `parser.array_dims()` qui les
reconnaît — un seul endroit, appelé par le checker (valider) et par le codegen
(émettre). Il rend les dimensions, ou `None` quand ce n'en est pas une :

| Écrit en Lua | Dimensions | C émis |
|---|---|---|
| `local couts = {1, 2, 4, 8}` | `(4,)` | `static int couts[4] = {1, 2, 4, 8};` |
| `local grille = array(20, 12)` | `(20, 12)` | `static int grille[20][12] = {{0}};` |

**L'ordre des arguments d'`array` est l'ordre des index** : `array(20, 12)` se
lit `grille[1..20][1..12]`. Aucun vocabulaire de largeur ni de hauteur n'entre
dans la règle — il obligerait à se rappeler lequel des deux vient en premier,
alors que la déclaration le montre.

Trois pièges, et où ils sont tenus :

- **Lua indexe à partir de 1**, et c'est `CodeGen._index()` qui traduit, à un
  seul endroit : `t[i]` devient `t[(i) - 1]`, replié tout de suite quand l'index
  est littéral (`t[1]` → `t[0]`). Le reste de l'API expose bien des index à
  partir de 0, mais ce sont des **numéros matériels**, pas des positions dans un
  conteneur du langage.
- **`#t` est une constante de compilation** (`CodeGen._array_length`) : la taille
  fait partie du type, elle n'est rangée nulle part à l'exécution.
- **Un tableau d'état est permis partout, y compris dans un prefab poolé** (cf. « L'état d'un prefab poolé »).

`Checker._check_expr` parcourt l'expression entière (opérandes, arguments, cible d'affectation) : une erreur de
bornes dans `t[9] + 1` doit se voir.

`ExprIndex` (notation pointée, un NOM connu à l'écriture) et `ExprIndexAt`
(crochets, une EXPRESSION calculée) sont deux noeuds distincts : les confondre rendrait `t[i]` indiscernable de
`t.i`, et le C lirait un champ de structure là où le script veut un élément.

### Tables de données — `data.Objets[i].prix`

`data` est l'espace de noms RÉSERVÉ des tables authorées du projet
(`parser.DATA_NS`). Un nom réservé plutôt qu'un global par table : sans lui, une
table nommée `score` masquerait un `local score`, et rien ne dirait lequel des
deux est lu.

**La traduction se compose toute seule**, parce qu'elle suit la forme de l'AST :

| Lua | AST | C |
|---|---|---|
| `data.Objets` | `ExprIndex(ExprName("data"), "Objets")` | `g_data_Objets` |
| `data.Objets[i]` | `ExprIndexAt(…, i)` | `g_data_Objets[(i) - 1]` |
| `data.Objets[i].prix` | `ExprIndex(…, "prix")` | `g_data_Objets[(i) - 1].prix` |
| `#data.Objets` | `ExprUnop("#", …)` | le nombre de lignes, en littéral |

Les trois lignes du milieu ne sont qu'une branche chacune : la première pose le
tableau, et le reste (l'indexation à partir de 1, puis l'accès au champ) est le
chemin générique déjà écrit. Le C se relit avec les mots du Lua.

**Où vit quoi**, et pourquoi ce n'est pas un `DOMAIN_*` :

- une table n'apparaît **jamais comme argument littéral d'un appel**, donc la
  mécanique de domaine — dérivée de `RUNTIME_API.params` — ne s'y applique pas.
  Lui inventer un domaine obligerait à le déclarer « traité ailleurs » des deux
  côtés de `validator._check_api_domains` pour un `Param` qui n'existe pas ;
- le CHECKER reçoit `BuildContext.data_tables` = `{nom: (colonnes, lignes)}` et
  refuse une table inconnue, une colonne inconnue, un rang hors bornes écrit en
  clair, et **toute écriture** (une table est `const` en ROM) ;
- le CODEGEN reçoit la même table, dont il ne lit que le nombre de lignes — pour
  `#data.X`, constante de compilation comme `#t` ;
- les COLONNES de référence, elles, portent bien le nom d'un domaine (`text`,
  `sfx`…), mais côté DONNÉE et non côté argument : c'est
  `codegen/runtime_codegen/data_tables.py` qui les résout en index, et
  `validator._check_data_column_types` qui tient les trois listes d'accord
  (`COLUMN_REFERENCES`, `api.ALL_DOMAINS`, `project.DATA_COLUMN_SOURCES`).

**L'émission n'emploie pas les `#define`** `TEXT_*` / `SFX_*` : ils sont écrits
par `codegen` dans CHAQUE unité de traduction d'acteur, et `data_tables.c` n'en
est pas une. L'entier est donc écrit en clair, suivi d'un commentaire qui nomme
l'élément. `data_tables.h`, lui, est **toujours** généré et **toujours** inclus —
un include conditionnel serait un second chemin pour un cas vide — alors que le
`.c` n'existe que s'il y a une table (une unité de traduction vide n'est pas du
C standard, et le Makefile ramasse `src/*.c` au glob).

---

## Layers BG vivants (shadows de registres)

Changer *un* champ d'un registre BG (la priorité, sans toucher au screenblock) suppose de
connaître les autres bits. `DISPCNT` et `BGxCNT` sont pourtant relisables (R/W) — mais
`BGxHOFS/VOFS`, eux, sont **write-only**, donc le décalage de scroll DOIT vivre en RAM de
toute façon. Plutôt que deux modèles, un seul : `gba_engine.h` garde une copie de tout —
`g_dispcnt_sh`, `g_bgcnt_sh[4]` — et **toute** écriture passe par `dispcnt_set()` /
`bg_cnt_set()`, y compris celles émises à l'init de scène par `main_gen.py`. C'est ce qui
rend modifiables en cours de jeu des choses jusque-là figées au build : visibilité,
priorité (z-order), screenblock affiché.

- `display_reset()` remet layers, windows et blending à neuf en tête de `scene_init_*`, avant que la
  scène ne les repeuple — sinon une scène hériterait des layers de la précédente.
- `g_bg_ofs_x/y[4]` = décalage **propre au layer**, distinct du scroll caméra.
  `scene_tick_*` écrit `BGOFS = (cam × vitesse de parallax) + décalage propre`, donc les
  deux se composent au lieu de se battre. Un layer sans image (UI/texte) n'est pas touché
  par le tick : pour lui, l'écriture directe de `layer_set_scroll()` fait foi.
- `bg_se_addr()` résout une coordonnée en tuiles vers l'adresse de la screen entry, en
  gérant les 4 tailles de map régulières et leur découpage en blocs 32×32 (+0x400 à
  droite, +0x800 en bas d'une map 64-large, +0xC00 au coin). Les coordonnées bouclent
  comme le matériel.
- `tilemap_set()` ne touche que les 10 bits d'index : le flip et la banque de palette de
  la case survivent. Repeindre (`tilemap_set_palette`) est l'inpainting appliqué au
  runtime — même mécanique `SE_PALBANK`, mêmes 16 banques.

Ces fonctions sont déclarées dans `gba_engine.h` et définies dans `main.c` (via
`GBA_ENGINE_IMPL`) ; `runtime_api.h` (généré) les déclare `extern` pour que les scripts
d'actor et de scène, compilés en TU séparées, puissent les appeler.

### Windows — le pochoir

Une window GBA **ne dessine rien**. C'est un pochoir : par région de l'écran, elle dit
quels layers et sprites ont le droit de s'afficher, et si le blending s'y applique.
D'où sa valeur pour l'UI — elle exprime le *où* sans jamais imposer un *à quoi ça
ressemble* (cf. `changelog/archives/v0.3.md`, v0.3.2, « neutralité de style »).

Quatre régions, par priorité décroissante : `WINR_0` (rectangle 0), `WINR_1`
(rectangle 1), `WINR_OBJ` (fenêtre-objet), `WINR_OUT` (tout le reste). Un pixel obéit à
la première qui le contient. `WININ` porte les 6 bits (BG0-3, OBJ, blending) des deux
rectangles, `WINOUT` ceux de l'extérieur et de la fenêtre-objet — d'où `win_region_sh()`,
qui mappe une région vers (shadow, décalage).

- `window_reset()` (appelé par `display_reset()`) pose **tout autorisé partout, aucune
  window active**. Sans ce défaut, activer une window éteindrait tout l'écran hors du
  rectangle : `WINOUT` régit le reste du monde dès qu'une seule window existe. C'est le
  piège matériel classique, neutralisé une fois pour toutes.
- `window_set()` clampe à 240×160 et interdit les rectangles inversés : le matériel a un
  comportement erratique sur `X1>X2` ou `X2>240`, ces cas ne sortent pas de la fonction.
- **Fenêtre-objet** : `Actor.obj_mode` (0 normal, 1 semi-transparent, 2 fenêtre) est
  injecté dans `attr0` bits 10-11 aux **trois** sites d'émission OAM de `main_gen.py`
  (acteur de scène, prefab poolé, sprite affine). En mode 2 le sprite n'est plus dessiné :
  ses pixels opaques découpent `WINR_OBJ`, ce qui donne une région de forme libre et
  animée sans interruption HBlank.

Les constantes sont préfixées `WINR_*` : libtonc définit déjà `WIN_OBJ`, `WIN_BG0`… comme
masques de bits, sémantique incompatible.

**WIN0 et WIN1 sont allouées par intention, pas par index câblé** (réglé le 2026-08-25,
`codegen/window_alloc.py`) — le premier vrai cas du chantier « l'allocateur de ressources
matérielles » (cf. ROADMAP.md, et « Ressources matérielles — l'auteur ne les nomme jamais »
plus bas). Aucun concept de haut niveau ne demande WIN0 ou WIN1 : une caméra dont le cadre
(`Camera.frame_w/h`) est plus petit que 240×160 demande *une région de rendu* ; un panneau UI
(`WindowSlot`, panneau Windows de l'inspecteur de scène) demande *un rectangle de découpe*,
et se NOMME comme une caméra ou un acteur — jamais « WIN0 »/« WIN1 ». `scene_window_layout()`
résout ça au BUILD, par scène : l'intention caméra (si elle existe) prend toujours la
première place, puis chaque `WindowSlot` nommé prend ce qui reste, dans l'ordre d'auteur. Au
build, pas à l'exécution : le pool est connu d'avance (les windows d'une scène ne changent
pas de nombre en cours de partie), et c'est ce qui permet de prévenir l'auteur — une scène
qui demande une troisième région rectangulaire fait échouer le build, nommée, plutôt que de
laisser une région s'afficher partout au lieu d'être découpée (bug visuel silencieux, sans
repli sûr possible contrairement à une palette). Le budget (« N / 2 windows ») s'affiche dans
la carte Windows du Scene inspector ET la carte Transform du Camera inspector — même chiffre,
une seule fonction (`scene_window_budget()`).

Ce que l'allocateur NE couvre PAS, par construction : `WINR_OBJ` (pas de géométrie, pilotée
par `Actor.obj_mode`, jamais disputée) et `WINR_OUT` (le complément automatique — « personne
ne peut le demander »). Le vrai **écran partagé** (plusieurs caméras actives SIMULTANÉMENT,
pas juste plusieurs caméras possibles dans une scène) reste hors périmètre — cf. ROADMAP.md,
« Piste posée — Caméra2D ».

**Les 128 entrées OAM sont allouées PAR SCÈNE** (livré 2026-09-19, `codegen/oam_alloc.py`) —
même famille que `window_alloc`, et le plus gros cas. Une seule scène est vivante à la fois sur
GBA : chaque `scene_init` efface `g_actors[]` et repose sa fenêtre OAM **depuis l'entrée 0**.
`scene_oam_layout(project, scene) -> OamLayout` est la source de vérité unique de cette
géométrie — les acteurs actifs posés `[0..placed)`, puis la bande d'interface en sprites, puis
les pools de prefabs que la scène déclare (`Scene.prefab_pools`), dans cet ordre (**acteurs → UI
→ pools**, l'index OAM bas passant devant). `headers.py` (les `ACTOR_`/`POOL_<Scene>_<Prefab>_*`),
`main_gen.py` (`spawn_<Scene>_<Prefab>`, dimensionnement de `g_actors[]`) et la façade
`actor_budget.py` en sont des **lecteurs**, comme le pipeline grit et `main_gen` lisent
`palette_alloc`. Trois conséquences que le per-scène achète :

- **`g_actors[]` est dimensionné sur la scène la plus gourmande** (le MAX, pas la somme des
  scènes) : une scène de menu ne paie plus les slots des projectiles du niveau d'action.
- **Les symboles portent la scène** : `spawn_<Scene>_<Prefab>` rend un `Actor*` (ou `NULL`
  pool plein), `ACTOR_*`/`POOL_*` repartent de 0 par scène, chaque scène recompile ses unités de
  prefab contre SA géométrie. Un état project-wide indexé par `Actor.tag` doit donc devenir
  per-scène : `g_sfx_on_destroy_id/_vol` sont désormais des tables par scène, un pointeur posé
  au `scene_init` (patron `g_active_cmap`).
- **Le budget OAM est UNIQUE et bloquant** : `validator._check_actor_budget` lit le même
  `scene_oam_layout` que le build et refuse `used > 128` — le rendu écrit `shadow_oam[<indice>]`
  (128 entrées), au-delà c'est une corruption, pas un surplus caché. L'override facultatif
  `Scene.actor_slots` (réservation d'auteur, hérité du 96/32) ne pilote PLUS la géométrie de
  build : il ne survit que dans la carte budget de l'inspecteur, comme une vue d'INTENTION.

Les appels `window.*` adressent une window rectangle par NOM (`DOMAIN_WIN_REGION` : la liste du projet, plus les
mots-clés `"object"`/`"outside"`), jamais par index matériel.

### Blending — deux jeux de cibles

`BLDCNT` porte **deux** listes de cibles, pas une : le *dessus* (bits 0-5, ce qui est
mélangé) et le *dessous* (bits 8-13, ce avec quoi — situé derrière selon les priorités).
D'où le paramètre `side` de `blend_set_layer/obj/backdrop`, 0 = dessus, 1 = dessous. En
mode alpha, aucun mélange ne se produit là où un pixel du dessus n'a pas de pixel du
dessous derrière lui : c'est la cause première des effets qui « ne marchent pas », et le
dessous manquant est très souvent le backdrop.

Trois portes en cascade, à garder en tête quand on débugge un effet absent :

1. **Le mode** (`blend_set_mode`) — 0 aucun, 1 alpha, 2 vers le blanc, 3 vers le noir.
   Les modes 2 et 3 n'utilisent que le dessus, et se dosent par `BLDY` (`blend_set_fade`),
   pas par `BLDALPHA`.
2. **Les cibles** — dessus ET dessous pour l'alpha, dessus seul pour les fondus.
3. **Les régions** — `window_set_blend()` décide *où* tout ceci s'applique. C'est la
   combinaison qui donne l'effet le plus courant d'une UI : estomper le monde dans
   `WINR_OUT`, couper l'estompe dans `WINR_0`, donc un panneau net sur un monde assombri,
   sans dépenser un octet de VRAM.

Un sprite en `obj_mode` 1 (semi-transparent) court-circuite la liste du dessus : il se
mélange quel que soit le réglage OBJ — utile pour un seul fantôme translucide.

Les **trois** registres sont shadowés (`g_bldcnt_sh`, `g_bldalpha_sh`, `g_bldy_sh`) et
`blend_flush()` est le seul endroit qui les écrive — `BLDY` a gagné sa shadow le jour où
une transition de scène a eu besoin de rendre son intensité à la scène après le fondu.
`eva`/`evb`/`evy` sont des seizièmes clampés à 0-16 par `ev_clamp()` — au-delà le matériel
sature, on préfère un comportement identique partout.

### Collision de tuiles — une géométrie, deux lecteurs

Une carte de collision est un octet par tuile de 8×8. Ce que cet octet DÉSIGNE —
un bloc plein, une pente à 26°, un plafond incliné — est décrit une seule fois,
dans `core/models/collision_tiles.py`, et deux consommateurs en dérivent :

- le **canvas** en tire son polygone (`polygon()`, le carré de la tuile découpé
  par la droite de surface) ;
- le **codegen** en tire `g_tile_surface[type][8]`, l'ordonnée de la surface dans
  chacune des 8 colonnes de pixels, émise dans `main.c`.

Tant que la forme n'existait que dans les polygones du canvas, la physique du jeu
n'en avait aucune — et l'y réécrire à la main aurait créé la même divergence que
une liste écrite deux fois. Une tuile s'y décrit par sa **droite de
surface** (ordonnées en `x=0` et `x=8`, autorisées à sortir de la tuile) et le
côté plein ; les 22 types y tiennent, pentes raides comprises.

La résolution (`resolve_actor_tiles`, émise par `main_gen`) ne résout qu'une
**vélocité** : un acteur dont `vx` et `vy` sont nuls n'a pas été conduit cette frame, elle
le laisse tel quel (`grounded` garde sa valeur). `self.position` est donc une
téléportation qui ignore la carte — ni arrêt contre un mur, ni remontée sur une pente — et
`self.velocity` le déplacement physique. Quand elle tourne, elle suit un ordre qui est
la règle :

1. **X d'abord**, et seul `TILE_SOLID` repousse — une pente qui bloquerait
   l'horizontale serait un mur, personne ne la gravirait ;
2. **plafond**, si l'acteur monte : la surface la plus basse des trois sondes ;
3. **sol** : les deux coins bas et le centre de la box, la surface la plus haute
   l'emportant. Chaque sonde balaie trois tuiles — celle au-dessus des pieds, celle des
   pieds, celle du dessous — car sur une pente la matière de la colonne suivante vit dans
   la tuile d'au-dessus ; une surface plus haute que la box est écartée. L'acteur qui
   pénètre est remonté dessus, sans plafond de marche ;
4. **vitesse le long du sol** : le pas horizontal est réduit du cosinus de la pente gravie
   (`g_tile_scale`, précalculé — la GBA n'a pas de racine carrée), reste reporté au 1/256 de
   pixel. C'est la seule chose que le moteur défait de ce qu'un script a demandé, d'où ses
   deux garde-fous : être au sol à la frame précédente, et un pas qui tient dans une tuile ;
5. **collage** en descente, tant que l'écart reste sous `|Δx|×2 + 1` — la chute
   maximale qu'une pente à 63° peut creuser pour le déplacement réellement
   parcouru (`Actor.collision.last_x`), donc sans constante ni réglage.

Hors carte vaut **plein** dans les quatre directions : le monde est une boîte close.
Sans ça un acteur qui rate une plateforme tombe sans fin, et son sprite reboucle en
haut de l'écran tous les 256 px — l'OAM ne code Y que sur 8 bits.

Deux conséquences à connaître : la sonde ne porte qu'à une tuile au-delà des pieds,
donc **rien n'agit à distance** (un acteur ne se pose pas sur un sol
lointain — le moteur n'a pas de gravité, c'est au script de l'y amener) ; et
`Actor.collision.grounded`, ce que rend `actor_on_ground()`, décrit la FIN de la frame
précédente, la résolution s'exécutant après les `on_update`.

Enfin, `CollisionBox.solid` ne décide que de ceci : cette box est-elle arrêtée
par la carte ? Les collisions acteur-contre-acteur ne l'ont jamais consulté.

### Caméra — une donnée, pas du code

`cam_x`/`cam_y` est l'origine d'une zone de taille écran, dont tout se dérive (scroll BG,
position écran des sprites, bords de zone morte, clamp aux bornes). Ce qui DÉCIDE de cette
origine est une **caméra**, possédée par sa scène (`Scene.cameras`, inline dans le JSON de la
scène — comme `actors`/`background_layers`) : mode, cible, zone morte, bornes, script. Une
scène peut en posséder plusieurs ; une seule est active à la fois — la GBA n'a qu'un écran.

- **Table en ROM, index actif en RAM.** `main_gen` aplatit les caméras de TOUTES les scènes
  dans une seule table `g_cam_table[]` (`Camera` défini dans `runtime_api.h`) et
  `g_cam_active`. L'entrée **0 est toujours la caméra par défaut** — fixe à l'origine, sans
  bornes — celle qu'obtient une scène qui n'en désigne aucune. La donner comme entrée réelle
  évite un cas particulier à chaque activation.
- **`camera_switch(i)` pose le cadrage ET les bornes**, puis appelle le `on_start` de la
  caméra. C'est le seul endroit qui écrit `g_cam_max_x/y` : un script qui appelle ensuite
  `camera.set_bounds()` garde la main jusqu'à la prochaine activation.
- **L'ordre dans `scene_tick` est la règle** : retrait de la secousse de la frame
  précédente → suivi déclaratif → script de la caméra → clamp aux bornes → secousse. Le
  script peut donc ajuster ce que le déclaratif vient de poser (usage déclaratif, scripté
  ou hybride sans réglage de bascule), le clamp a toujours le dernier mot sur la position
  logique, et la secousse se pose par-dessus lui — trembler au bord du monde doit se voir.
  Elle est retirée en début de frame suivante, si bien que la zone morte ne raisonne jamais
  sur une position tremblée et que rien d'autre dans le moteur ne connaît la secousse.
- **La cible se résout dans la scène propriétaire.** Une caméra n'appartient qu'à une seule
  scène, et cite son acteur suivi par nom ; ce nom est donc toujours local à CETTE scène, sans
  ambiguïté à lever. Le tick de la scène porte un `switch` sur `g_cam_active` où ne figurent
  que ses propres caméras capables de suivre quelqu'un — cible et marges devenant des
  constantes. Ailleurs (aucun acteur de ce nom dans la scène), la caméra reste immobile, et
  `_check_cameras` le dit avant le build.
- **Le nom d'une caméra reste unique à l'échelle du PROJET**, même si elle n'appartient qu'à
  une scène : `camera:switch("Nom")` n'est pas qualifié par scène côté Lua, et chaque caméra
  reçoit une constante C globale `CAM_<NOM>` (même mécanique que `LAYER_<NOM>`). Deux scènes
  ne peuvent donc pas nommer leur caméra pareil.
- **`frame_w`/`frame_h` pilotent WIN0** (réglé le 2026-08-24, cf. « Windows — le pochoir » plus
  bas) : `camera_switch(i)` pose `window_set(0, 0, 0, frame_w, frame_h)` et l'active si le
  cadre est plus petit que 240×160, sinon WIN0 reste éteinte. 240×160 (le défaut) préserve le
  comportement d'avant que ces champs existent.
- **Le script d'une caméra emprunte le chemin des scripts de scène** (pas de `self`), avec
  `owner_kind="camera"` : seul le mot du symbole C change (`<sym>_camera_on_update`). Deux
  points d'entrée et non trois — le moteur n'exécute ce script qu'à un seul moment de la
  frame, un `on_late_update` s'y enchaînerait sans que rien ne l'en sépare.

### Transitions de scène — le fondu possède les registres

Un changement de scène joue un fondu à la fermeture puis à l'ouverture
(`changelog/archives/v0.6.md`, v0.6.2). Trois faits structurent l'implémentation :

1. **Le séquencement vit dans la boucle principale générée**, seul endroit qui connaisse
   les deux scènes — `scene_switch()` ne fait que poser `g_next_scene`. La machine à états
   (`g_trans_phase` : 0 aucune, 1 fermeture, 2 ouverture) et `scene_enter()` sont émises
   par `main_gen.py`, et **uniquement si au moins une scène a une transition** : un projet
   qui n'en veut pas retrouve la bascule sèche, au bit près.
2. **Entre `transition_begin()` et `transition_end()`, le fondu possède `BLDCNT`/`BLDY`.**
   `blend_flush()` cesse de descendre les shadows au matériel, mais les shadows, elles,
   continuent d'enregistrer : le `display_reset()` en tête de `scene_init` et tout le
   réglage de mélange que la scène pose derrière lui s'écrivent normalement, et prennent
   effet d'un coup à la fin du fondu. Sans cette règle, l'écran se rallumerait au milieu
   du chargement de la scène entrante, en pleine lumière et sur une image à moitié
   construite. C'est aussi pourquoi le backdrop est première cible du fondu : pendant
   l'init, les layers sont éteints et c'est *lui* qu'on voit.
3. **La scène sortante gèle** : son `tick()` n'est plus appelé dès la première frame de la
   fermeture. Le reste de la frame (VBlank, `mmFrame()`, compteur, lecture des touches)
   continue — une transition est un effet d'affichage, pas une pause du moteur.

L'héritage projet→scène (`ProjectSettings.transition_kind/frames`, surchargés par
`Scene.transition_kind/frames`) est résolu **au build**, par `transition_of()` : le runtime
ne reçoit qu'un couple `(mode, frames)` par scène dans la vtable. Chaque scène décrit sa
propre disparition et sa propre apparition, donc deux scènes ne peuvent pas se disputer une
bascule.

---

## Sens des dépendances

L'empilement visé, du haut vers le bas — **une couche ne dépend jamais de ce qui est
au-dessus d'elle** :

```
ui/            l'interface
core/          la logique éditeur et le projet ouvert
core/models/   les données du projet, et le format binaire qu'elles décrivent
codegen/       la génération du C, qui consomme le modèle
```

Trois règles pratiques en découlent :

- **`core/models/tile_codec.py` n'importe rien.** Le format d'une tuile et d'une entrée de carte est réclamé par les
  modèles, l'import, la génération et le canvas ; logé plus haut, il refermait une boucle de dix modules, masquée par
  des imports posés au fond des fonctions. Un module feuille ne peut participer à aucun cycle.
- **`Project` ne connaît pas l'application.** Il énonce des faits sur son propre `EventEmitter` (`renamed`, `status`)
  et reçoit sa `rename_scope` (le gestionnaire de contexte dans lequel dérouler un renommage). `CommandDispatcher.setup()`
  s'y abonne, met les faits en mots et rafraîchit les vues : un projet ouvert sans interface (build en ligne de
  commande, test) est muet de lui-même, sans repli à écrire.
- **Un nom s'importe du module qui le DÉFINIT** : `from core.models.scene import Scene`, jamais à travers `core.project`.
  Qu'un module ait un nom sous la main (`OWN_PAL_BANK` dans `scene.py`) ne fait pas de lui la source.

**Un import posé dans une fonction est un signal.** Il y en a de légitimes (coupure d'un
coût de démarrage, dépendance optionnelle), mais quand il évite une boucle, il la cache :
Python ne proteste jamais, et l'outillage non plus. En cas de doute, remonter l'import en
tête de fichier : s'il échoue, la boucle était réelle.

**Et un import différé n'est vérifié par rien.** Charger tous les modules ne l'exécute
pas ; il n'échoue que le jour où l'utilisateur emprunte ce chemin-là. Après tout
déplacement de symbole, résoudre *tous* les `from … import …` du dépôt — importer le
module cité et vérifier que chaque nom y existe — plutôt que se fier au démarrage.

### Les règles ci-dessus se vérifient toutes seules

```
python tools/check_architecture.py
```

Huit contrôles, sortie non nulle si l'un échoue : boucles d'import, sens des dépendances, imports résolus, **noms
résolus** (une fonction retirée d'un module qui continuait de l'appeler), code mort, frontières respectées (symboles
privés importés d'ailleurs).

Les boucles restantes sont **assumées et datées** : elles s'affichent avec leur raison sans faire échouer la
commande (un contrôle rouge en permanence n'est plus lancé par personne) ; toute boucle nouvelle échoue. Les
exemptions se justifient **par écrit dans le script** (`BOUCLES_ACCEPTEES`, `VIVANTS_SANS_APPELANT`).

Le huitième contrôle ne tourne qu'à la demande, `python tools/check_architecture.py --fresh` (~55 s) : il importe
chaque module **seul, dans un interpréteur neuf**, seul moyen de voir une boucle qui dépend de l'ORDRE (le premier
import réussi amorce le cache et masque le problème aux suivants).

**Corollaire : un `__init__.py` de paquet ne devrait rien importer au chargement** — importer un module d'un paquet
exécute d'abord son `__init__.py`. Ce qu'il expose se donne paresseusement (`__getattr__`, PEP 562).

### Deux implémentations qu'il faut tenir d'accord — `core/engine_emulation/`

Certains calculs existent **en double, dans deux langages** : le C les fait sur la console,
Python les refait pour l'aperçu. Où atterrit chaque glyphe d'un texte, comment se mélangent
deux couches, comment sonne un MOD passé au mixeur Maxmod. C'est inévitable — le C tourne
sur l'ARM, Python dessine dans une fenêtre — mais c'est le **pire mode de panne du
projet** : corriger une formule d'un seul côté ne casse rien, ne lève aucune erreur, et
produit un éditeur qui montre autre chose que ce que la ROM fabrique. L'utilisateur n'a
alors aucun moyen de savoir lequel des deux ment.

D'où un dossier dont le nom est la règle. Ce qui entre dans `core/engine_emulation/` a un
jumeau dans `runtime/`, et son en-tête le nomme.

À ne pas confondre avec du code **partagé** : quand le build et l'aperçu appellent la même
fonction (`nine_slice`, `models/tile_codec`), il n'y a qu'une implémentation, donc rien à
tenir d'accord. Le test avant d'ajouter un fichier ici est celui-là, et pas « est-ce que ça
sert à l'aperçu ».

### `Project` est découpé en tranches, pas en collaborateurs

`core/project.py` garde ce qui fait de lui un tout (registres d'assets, scène active, recherches, `save`/`load`) ;
`project_paths`, `project_variables`, `project_texts` et `project_renames` vivent à côté, en **mixins** dont
`Project` hérite. Des mixins et non des objets délégués : la découpe sert la LECTURE et ne coûte rien à l'écriture
(`project.rename_scene(...)` s'écrit comme avant, sans saut d'appel). Le prix, assumé : ces fichiers ne sont pas
autonomes, chacun suppose le reste de `Project` (`self._notify_renamed`, `self.texts_file`), et aucun ne doit importer
`core.project` (cycle immédiat).

---

## Chargement différé — indexer d'abord, matérialiser au besoin

L'ouverture d'un projet ne désérialise plus systématiquement tous les sidecars
de sprites, fonds et sons. `ResourceIndex` inventorie chaque collection sous la
forme `nom → chemin`, sans lire son JSON ; `ResourceStore` garde ensuite les
objets déjà matérialisés et charge une entrée dans `get(nom)` si elle est
réellement demandée.

`Project.load()` indexe ces quatre collections, charge les scènes et précharge
seulement les sprites et fonds directement cités par la scène active : le canvas
peut donc être prêt sans ouvrir le catalogue entier. Les écrans Backgrounds,
Animations et Sounds demandent explicitement leur collection lors de leur
première visite. À l'inverse, build, validation et opérations transversales
appellent `Project.load_all_resources()` : leur contrat exige une vue complète,
pas une approximation paresseuse.

La réconciliation des fichiers source reste attachée à la matérialisation de
sa collection. Ainsi, le démarrage interactif ne paie pas le rattrapage d'un
PNG que l'utilisateur ne consulte pas, tandis que l'écran qui le rend ou une
opération globale travaille toujours avec des données à jour.

Le point d'entrée **ouvre le projet fenêtre cachée, puis l'affiche déjà dessinée** : `main.py` construit `MainWindow`,
peuple l'éditeur (`_open_project`, sous curseur d'attente) et n'appelle `show()` qu'ensuite, le premier `show()` (mise
en page et paint de tout l'arbre de widgets) étant l'endroit coûteux. Pas d'écran de chargement séparé.

Deux coûts ont été sortis de ce premier paint : le **`DynamicInspector`** construit ses neuf sous-inspecteurs à leur
première venue, et l'**aperçu des boîtes de texte du canvas** (qui tirait la rasterisation de la police ROM entière)
est **pré-chauffé hors écran** à la reconstruction des items (`GBAScene.set_ui_regions`), en partageant une seule
allocation de scène (`palette_alloc.scene_layout_cache()`, un cache à portée de contexte que le build n'ouvre jamais).

---

## Ajouter un écran — le catalogue et le contrat

Un écran est une donnée du catalogue, pas du code épelé à plusieurs endroits de `window.py` : deux listes parallèles
dont l'accord ne tenait que par un commentaire décalaient l'une sans un mot dès qu'un écran s'insérait.

**Il n'y a plus qu'une liste**, `MainWindow._screen_catalogue()`. Les libellés
de la barre de navigation, l'ordre du `QStackedWidget` et la propagation du
projet en dérivent tous. Ajouter un écran, c'est une ligne et une fabrique :

```python
EditorScreen("Sound Editor", self._make_sound_editor)
```

- **`ProjectScreen`** (`ui/screens.py`) nomme le contrat : `load_project(project)`. Un `Protocol` et non une classe de
  base : un écran est un `QWidget` d'abord.
- **Le contrat est vérifié à la CONSTRUCTION** (`_ensure_screen`), pas statiquement : un écran venu d'un plugin n'existe
  pour personne avant ce moment. Un écran qui ne le remplit pas est monté quand même et le défaut est annoncé, dans la
  même boîte que les erreurs de plugin (sinon un écran muet ne se distingue pas d'un écran vide).
- **L'écran natif se construit à sa PREMIÈRE VISITE** : `_build_screens` ne bâtit au démarrage que le Scene Manager et
  les écrans de plugin, et pose un placeholder pour les autres ; `_ensure_screen` le remplace. Les imports lourds
  (QtMultimedia + numpy, grammaire luaparser) quittent le chemin de démarrage. Les **plugins** restent construits au
  démarrage : leur contrat doit se constater tout de suite. Un accès transversal (build, réglages, undo) à un écran non
  construit le saute (`getattr(self, "_x", None)`) ; l'écran lira l'état frais à sa venue.
- **Une fabrique et non une classe** dans le descripteur : le Scene Manager est assemblé par la fenêtre, et les plugins
  sont chargés après la `QApplication` mais avant le catalogue (construire un widget à l'import planterait). Le
  branchement propre à un écran vit dans sa fabrique.
- **`SceneManagerScreen`** porte ce contrat ; ses trois colonnes restent des attributs de la fenêtre (lues d'une
  trentaine d'endroits).
- Les écrans de plugin sont ajoutés **après** les natifs : les index de ces
  derniers ne bougent pas quand un plugin est installé, et l'ordre de nav
  enregistré par l'utilisateur survit. Leurs appels sont entourés d'un
  `try` — du code tiers dans un slot Qt fait abandonner le process.

### Le panneau de build — un seul, accroché à l'écran affiché

Console, diagnostics et onglet Disk vivent dans **un seul** `BuildPanel` (`MainWindow._make_build_panel`), qui
n'appartient à aucun écran.

- **Chaque écran est bâti sur `ThreeColumnBody`** (`ui/common/three_column_body.py`)
  et l'expose en `body`. La colonne centrale y est un splitter vertical
  `[centre | emplacement du panneau]` : le panneau se loge sous le centre de
  l'écran, jamais en pleine largeur. Un écran sans `body` (plugin) n'a pas de panneau.
- **`_show_screen` l'accroche** (`_move_build_panel_to`) : Qt reparente le widget,
  console et onglets restent intacts. **Fermé = replié à zéro dans le splitter**, pas
  masqué : la poignée reste au bord bas du centre, c'est elle qu'on tire pour ouvrir.
  Le Sound Mixer, dont l'éditeur de boîtes (`_machines_panel`) est caché le temps de son
  recentrage, garde sa colonne pour la même raison : on ne masque pas la colonne, seulement son
  contenu. Le **lecteur** (`BoxPlayer` + sa barre, hauteur fixe de 42 px) n'est PAS dans ce
  panneau masqué : il est ancré en bas de la colonne centrale, sous un stretch, et sert
  l'aperçu d'un asset du Sound finder comme celui d'une boîte ; Espace le lance / l'arrête.
- **Création depuis des sources (onglet Disk).** `disk_view.shared_create_options(nodes, callbacks)`
  est la seule règle de « quels types pour cette sélection » (intersection des types de chaque source),
  partagée par le bouton *Create*, le clic droit de la vue à plat et celui de l'arbre.
  `DiskCallbacks.create_from_sources(chemins, famille)` crée le lot en UNE entrée d'historique.
- **Ouvert ou fermé est une donnée du catalogue** : `EditorScreen.build_panel_open`
  (ouvert : Scenes, Datas, Scripts ; fermé : les autres et les plugins). C'est la
  valeur de départ ; `_build_panel_open` retient le dernier état de chaque écran pour
  la session, pas entre deux lancements. Build & Run l'ouvre sur l'écran affiché,
  menu View › « Panneau de build » le bascule.
- **L'onglet courant** (Disk au premier lancement, puis le dernier vu) est commun à
  tous les écrans, puisqu'il n'y a qu'un panneau ; il est écrit dans `QSettings`
  (`Layout/build_tab`).

### Les trois surfaces d'extension d'un plugin

| Portée | Point d'entrée | Exemple |
|---|---|---|
| un composant | `COMPONENT_REGISTRY` + `@register` | `plugins/example_path/` |
| une règle de build | `@register_validator` | `core/validator.py` |
| un écran entier | `register_screen(nom, fabrique)` | `plugins/example_screen/` |

### Ce qui reste à la charge de la fenêtre

Le catalogue ne couvre que le montage et le projet. Un écran qui doit réagir à
un événement moteur (`_d.on("actors_list_changed", …)`) le déclare toujours dans
`_build_scene_manager_screen` — c'est de l'abonnement, pas du cycle de vie.

**Le cycle de vie d'un écran a deux temps** (chantier « L'écran resynchronisé à sa
revisite ») :

- **Première visite → `load_project(project)`**, le contrat obligatoire, appelé une
  fois par `_load_screen_for_project`. Il peuple l'écran.
- **Visites suivantes → `refresh()`**, le crochet OPTIONNEL, appelé par
  `_show_screen` juste après `setCurrentIndex` quand l'écran est *déjà* chargé
  pour ce projet (`index in _project_loaded_screen_indices`). Un écran a pu se
  périmer pendant qu'on éditait ailleurs (un texte, une palette, un sprite nés
  dans un autre écran) : `refresh` re-dérive ses catalogues **depuis la mémoire**,
  jamais depuis le disque, en conservant sélection et état d'édition.

`refresh` n'entre PAS dans le `Protocol` `ProjectScreen` (l'y mettre casserait le
contrôle `isinstance` de `_ensure_screen` pour tout écran ne l'implémentant pas) :
c'est un crochet optionnel, appelé via le helper `ui/screens.refresh_screen(widget)`
qui ne fait rien s'il est absent. Un écran sans `refresh` est visible à la revue
(le contrat le nomme), sans erreur au runtime.

**Corollaire — on n'abonne PAS un écran empilé au bus pour se rafraîchir caché.**
Le bus est vidé à chaque changement d'écran, un seul écran est visible à la fois :
un événement qui touche un écran non visible n'a pas à le rafraîchir sur-le-champ,
sa revisite s'en charge. C'est pourquoi l'écran Palettes n'a **pas** d'abonnement
`palettes_changed` alors que `save_palette` (Sprite/Background Editor) l'émet — il
est toujours caché à ce moment-là. Les abonnements `_d.on(…)` qui subsistent
pilotent l'écran **visible** (le Scene Manager) ; les invalidations paresseuses
(`invalidate_script_usages`) marquent un cache périmé, ce n'est pas un refresh.

Le **routage des assets** (`MainWindow._ASSET_ROUTES`) est une autre table : elle associe `assets/<dossier>/*.ext` aux
fonctions d'`asset_reconciliation` que le watcher appelle. Elle porte les fonctions elles-mêmes, pas des noms de
méthodes appelés par `getattr` (un nom périmé n'était vu par rien, et levait un `AttributeError` dans un slot Qt).
Elle a **trois** fonctions par famille : créer, supprimer, **renommer**. Un renommage arrive du système de fichiers
comme une disparition ET une apparition dans le même événement ; le watcher les **apparie** (même taille, même date
à la nanoseconde, `project_watcher.pair_renames`), et l'asset **suit son fichier** : `asset_reconciliation.rename_*`
appelle le `Project.rename_*` de la famille, donc le sidecar se déplace et les références sont réécrites.

**Le nom de fichier fait foi** : `ResourceStore.load` adopte le stem du fichier quand le champ `name` a dérivé, et
`asset_reconciliation._relink_source` raccroche un asset dont le fichier cité a disparu à celui qui porte son nom.

---

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

---

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
(ROADMAP, « Le chemin est dérivé de la clé »). Un libellé stocké à côté de la clé la dupliquait et se
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
- **déposer un texte dans un autre dossier**, **renommer un dossier** du Finder ou **éditer un niveau**
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

---

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
assets/fonts_assets/ ─────────┘       ↑              ↑                  ↑
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

---

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

---

## Le modèle affine — rotation/scale monde × local

Rotation et scale d'un sprite passent par une **matrice affine** OAM (`ATTR_AFFINE`),
au prix d'un des 32 jeux de paramètres (`pa..pd`) du matériel. Deux couples de valeurs
le demandent à la fois — le transform **monde** de l'actor et le transform **local** du
sprite — et la GBA ne possède qu'UNE matrice par slot. Le modèle les compose donc à la
frame, et le C émis n'écrit que la matrice composée.

La décision vit sur le **sprite** : `SpriteComponent.affine_transform` (case « Affine
transform » dans la carte du composant Sprite), portée dans la struct runtime par
`OamEntry.affine_slot`. Un sprite coché **réserve un des 32 slots au build, même à
l'identité**. Décoché, aucun slot : les champs de transform gardent leur valeur, mais rien
ne les affiche.

C'est une capacité de **RENDU**, pas un PLACEMENT — d'où le composant de rendu, et non
l'actor. C'est aussi ce qui la rend décidable sur un **template** : la carte du
SpriteComponent est la seule que montre une racine de prefab, là où x/y/priority/direction
n'ont de sens que pour un actor posé dans une scène. `Prefab.affine_transform` délègue donc
au SpriteComponent de son actor racine, et vaut pour **toutes les copies de son pool** :
chacune réserve son propre slot. Deux conséquences que le pool impose :

- le **slot appartient à la scène** (le même prefab n'a pas le même numéro d'une scène à
  l'autre : il est distribué par `_compute_affine_info` au seed de chaque scène) ;
- `spawn_X()` remet l'`Actor` à zéro (`(Actor){0}`) : il doit donc **préserver le slot et
  reposer les échelles neutres** (256 = ×1) du template. Sans cela une instance spawnée
  repart avec une échelle de zéro — matrice dégénérée — et avec le slot 0, celui d'un
  autre actor.

Deux niveaux de transform, séparés par qui les possède :

| | Qui possède | Éditeur | API Lua | Runtime |
| --- | --- | --- | --- | --- |
| **Monde** | l'`Actor` | carte Transform : rotation (0-359°), scale X/Y | `self.rotation`, `self.scale` | `g_actors[i].rotation`, `.scale_x/y` (Q8, 256 = 100%) |
| **Local** | le `SpriteComponent` | carte Sprite : offset X/Y, rotation, scale X/Y, pivot X/Y | `self.sprite_offset`, `self.sprite_pivot`, `self.sprite_scale`, `self.sprite_rotation` | `g_oam_entries[i].offset_x/y`, `.pivot_x/y`, `.scale_x/y`, `.rotation` |

Le transform monde reste sur l'**Actor** alors que la case est passée au sprite, et ce n'est
pas une incohérence : la rotation d'un actor est un fait de son état de jeu — un script la lit,
l'écrit et la relit qu'il y ait un sprite ou non. Ce que le sprite décide, c'est si ce fait est
**visible**. Un actor qui tourne sans slot affine tourne pour la logique, pas pour l'écran.

Le local est exprimé **dans le repère de l'actor** (hérarchie parent→enfant) : quand
l'actor tourne ou scale, le sprite le suit — son offset tourne et scale avec lui. La
composition au runtime (`_affine_oam_lines_dynamic` dans `main_gen.py`, lue chaque
frame) :

- **rotation effective** = `rotation` + `sprite.rotation` (somme, degrés) ;
- **scale effectif** = `scale_x` · `sprite.scale_x` / 256 (produit, Q8) ;
- **offset** = R(rotation) · S(scale) · (`sprite.offset_x`, `sprite.offset_y`) — transformé par la
  matrice de l'ACTOR, pas par la matrice composée ;
- **position** = actor.position + offset composé : c'est le coin haut-gauche du CADRE du sprite ;
- **point de pivot** (`sprite.pivot_x/y`, `self.sprite_pivot`) : le point autour duquel rotation,
  échelle et flip s'exercent, en pixels **depuis le centre du cadre** — (0, 0) = le centre. Deux
  notions distinctes : l'**offset** dit OÙ est le sprite, le **pivot** dit AUTOUR DE QUOI il se
  transforme. Le matériel pivote toujours sur le centre de la texture (Tonc, `obj_aff_*`) : le
  pivot de l'auteur s'obtient par calcul — le point P reste fixe à l'écran et le centre de la
  boîte OAM se place à `P − M·pivot` (M = rotation·échelle·flip). Le flip n'est que l'échelle −1
  (signe de `pa/pb` ou `pc/pd`), jamais un déplacement du cadre ; l'offset ne s'inverse pas avec
  lui. Les helpers de l'API qui jouent sur l'échelle ou la rotation (`squash`, `stretch`,
  `pulse`, `wobble`…) s'exercent donc autour du pivot ; `bounce` et `shake` déplacent, ils
  écrivent l'offset ;
- **au cochage** de « Affine transform », l'éditeur place l'actor au centre du cadre
  (`center_on_frame`) : offset du sprite = `(−largeur/2, −hauteur/2)`, et les boîtes de
  collision restées à `(0, 0)` passent à `(−w/2, −h/2)`. Un réglage déjà fait par l'auteur n'est
  jamais écrasé ;
- les quatre paramètres `pa/pb/pc/pd` sont écrits à partir du cosinus/sinus de la
  rotation effective (table `SIN_LUT[91]`, Q8 : un quadrant, `gba_sin`/`gba_cos` déduisent les trois autres) et des scales,
  et le sprite est étiqueté `ATTR_AFFINE` avec son `affine_slot`.

### Pourquoi le stockage est PAR-ACTOR et non par slot

Le stockage runtime vit **dans la struct `Actor`** (`g_actors[i].rotation`, `.sprite.rotation`, …) et non dans des tableaux
indexés par slot :

1. **Un script de prefab poolé est une fonction C partagée** par toutes ses instances, chacune avec sa propre struct
   `Actor` et un `affine_slot` différent : les valeurs propres à l'instance partent de son `g_actors[i]`.
2. **Un `static` dans un header multi-inclus est une copie PAR UNITÉ DE COMPILATION** : les écritures d'un script `actor_*.c`
   n'atteindraient jamais le rendu dans `main.c`. La struct partagée supprime la distinction, et la classe de bug.

Le seed de scène écrit donc les valeurs de départ dans les champs de la struct
(`g_actors[i].rotation`, `.sprite.rotation`, `.sprite.offset_x`, …), et les getters/setters Lua
(`actor_get/set_rotation`, `actor_get/set_sprite_rotation`, … — header
`runtime_api.h`) lisent/écrivent ces mêmes champs.

### Ces accesseurs ne sont PAS gardés par le slot

Ces champs occupent leur place dans **chaque** `Actor`, qu'un slot soit réservé ou non, et les getters/setters lisent et
écrivent toujours la valeur : un `self.rotation = self.rotation + 1` qui n'incrémente rien serait un piège plus coûteux que
le diagnostic qu'il achèterait. Seule l'écriture de la matrice OAM demande le slot. Le checker garde un contrôle — le seul
endroit qui voit qu'un script écrit `self.rotation` sans « Affine transform » — au niveau `warning` : le jeu tourne, c'est
l'affichage qui ment. `BuildContext.affine_transform` est alimenté par `lua_compiler._affine_reserved`, qui lit la case sur le
SpriteComponent.

---

## L'état d'un prefab poolé

Un script de prefab poolé est **une fonction C partagée** par toutes ses instances : ses variables de tête ne peuvent donc
pas être de simples `static` de fichier, qui seraient communes aux vingt copies.

À la place, `CodeGen._emit_pool_state` émet un état dimensionné par le pool :

```c
typedef struct { int fx; int fx_t; } BallState;
static BallState g_state_Ball[POOL_BALL_INSTANCES];
static inline int Ball_pool_slot(Actor* self) { return ((int)(self - g_actors) - POOL_BALL_START) / POOL_BALL_GROUP; }

void Ball_on_update(Actor* self) {
    BallState* _st = &g_state_Ball[Ball_pool_slot(self)];
    _st->fx_t = _st->fx_t + 1;
}
```

Quatre points s'y tiennent :

- **Le pool est une plage contiguë de `g_actors[]`**, dont les bornes sont des
  constantes de build. `POOL_<SYM>_START`, `_SIZE`, `_GROUP` et `_INSTANCES` sont
  émises par `headers.py`, à l'endroit même où l'offset est calculé — le script
  transpilé est compilé une fois pour le PROJET et ne peut pas les connaître
  autrement. Le C émis se dimensionne sur le `#define`, jamais sur un littéral
  recalculé : un écart avec la boucle de pool de `main.c` serait un débordement
  silencieux.

  Les quatre ne disent pas la même chose : une instance de prefab **segmenté** occupe un GROUPE d'entrées de `g_actors` (la
  racine, puis ses parties) mais n'exécute qu'**un** script, celui de la racine. `_SIZE` compte les entrées réservées (ce qui
  est payé), `_INSTANCES` les scripts : c'est lui qui dimensionne l'état, et `_GROUP` ramène `self` à son rang d'instance
  (1 pour un prefab plat).
- **Seul ce que le script ÉCRIT est de l'état.** `assigned_names()` (codegen)
  parcourt les handlers ; un local de tête qu'aucune ligne n'assigne est une
  constante et reste un `static` de fichier. Sur `Ball.lua`, quatre des six
  locals sont dans ce cas. La règle rend aussi la mesure honnête : le build
  annonce l'état, pas la longueur de l'en-tête du fichier.
- **`pool_init` est une seule affectation de structure**, pas un champ à la
  fois : c'est ce qui réinitialise un tableau ou un vec2 sans code spécial.
  L'état de départ est un `static const` (donc en ROM), et il est recopié dans
  le slot au spawn.
- **Le slot est résolu une fois par fonction**, dans un `_st` posé en tête par
  `_close_state_scope()` — et seulement si le corps y a touché, sinon c'est un
  `-Wunused-variable`. `_state_ref()` rend donc `_st->champ`, jamais le chemin
  complet : `sizeof(Actor)` ne vaut pas une puissance de deux, la soustraction
  de pointeurs coûte une division, et surtout le chemin complet répété à chaque
  site noyait le nom écrit par l'auteur. Tous les émetteurs de corps passent par
  cette paire — handlers, stubs, `pool_init`, séquences, behaviors inlinés — de
  sorte qu'il n'existe qu'UNE forme d'accès à cet état dans le fichier émis.
- **Le build dit ce que ça coûte, il ne le plafonne pas** — `[ewram] prefab X :
  état de script N octets × M instances`. Cf. ROADMAP v0.7.6 pour pourquoi il
  n'y a pas de garde-fou bloquant ici, là où la mémoire vidéo en a un.

Ce n'est pas en contradiction avec « le stockage affine est PAR-ACTOR et non par
slot » ci-dessus, dont les deux raisons ne s'appliquent pas : l'index est ici
celui de l'instance dans `g_actors[]` (unique par instance, pas un slot de
matrice partagé), et `g_state_*` est `static` dans **un seul** `.c`, celui du
prefab — pas dans un header multi-inclus.

---

## Les séquences — une ligne droite devient un `switch`

`function on_sequence_intro()` est un handler que le build **découpe à chaque
attente** et réémet en machine à états. C'est la seule transformation du
transpileur qui change la FORME du code, et non seulement son vocabulaire.

La forme est reconnue dans `parser.py` (`sequence_name`, `wait_call`), comme
celle du tableau et du `require` : ses trois consommateurs l'appellent — le
checker, le codegen, et `rom_build` (cf. plus bas).

`CodeGen._plan_sequences` produit, par séquence, la liste de ses tranches et
l'état qu'elle demande ; `_emit_sequence` écrit le `switch`. Les deux temps sont
séparés parce que l'état doit être **déclaré avant** d'être écrit, et à un
endroit qui dépend du propriétaire.

```c
static void Hero_sequence_intro(Actor* self) {
    switch (Hero_seq_intro_step) {
    case 1: {
        Hero_seq_intro_depart = actor_get_position(self).x;
        actor_move_to(self, (Vec2){120, 80}, 60);
        Hero_seq_intro_step = 2;
    } break;
    case 2: {   /* wait_until */
        if (!((actor_get_position(self).x >= 120))) break;
        Hero_seq_intro_step = 3;
    } break;
    case 3: {   /* wait(30) */
        if (++Hero_seq_intro_timer < 30) break;
        Hero_seq_intro_timer = 0;
        Hero_seq_intro_step = 0;   /* dernière tranche : la séquence s'arrête */
    } break;
    }
}
```

(Propriétaire unique ci-dessus, donc des statiques de fichier. Dans un prefab
poolé, la même séquence ouvre sur `BallState* _st = &g_state_Ball[…];` et lit
`_st->seq_intro_step` — cf. `_state_ref` plus haut.)

Cinq points s'y tiennent :

- **Un entier suffit** : 0 = arrêtée, 1..N = l'étape en cours. `sequence.start`
  écrit 1, `stop` écrit 0, `running` teste ≠ 0 — aucune fonction C derrière les
  trois, d'où un `c_func` vide dans `RUNTIME_API`.
- **Pas de boucle autour du `switch`.** Chaque `case` rend la main : une tranche
  par frame. C'est ce qui rend impossible, par construction, qu'une séquence
  tourne en rond dans une frame — et c'est pourquoi une attente ne peut
  s'écrire qu'au PREMIER NIVEAU d'une séquence (le checker refuse ailleurs :
  dans un `if`, le `switch` ne saurait pas où reprendre).
- **Chaque `case` est accolé.** Un `local` non hissé y est déclaré, et sauter
  par-dessus une déclaration dans un `switch` nu ne serait pas correct.
- **Ce qui traverse une attente est HISSÉ dans l'état.** `referenced_names()`
  répond à « ce `local` est-il encore lu dans une tranche suivante ? » ; si oui
  il devient un champ, et son `local x = …` n'est plus qu'une affectation. Sinon
  il reste un local C, et ne coûte rien.
- **L'état vit là où vit celui du script** (`_state_ref`) : statique de fichier pour un propriétaire unique, champ de
  `g_state_<sym>[]` pour un prefab poolé.

**Le pompage vit à la fin de `on_update`** (`_emit_sequence_pump`), dans l'ordre
de déclaration. Rien n'est ajouté à la boucle de frame de `main.c`, qui appelle
déjà `on_update` pour chaque propriétaire. Un script qui n'écrit pas
d'`on_update` en reçoit un : le stub existant le porte. Le seul fil à tirer
ailleurs est dans `rom_build._collect_events`, qui ajoute `on_update` aux events
d'un script à séquences — sans ça, `main.c` ne l'appellerait pas et la séquence
démarrerait pour ne jamais avancer.

`DOMAIN_SEQUENCE` est le seul domaine dont **l'espace de noms est le script** et
non le projet : checker et codegen reçoivent l'AST et collectent les noms
eux-mêmes. Conséquence : `refactor` le dérive du catalogue comme les autres,
mais aucun renommage d'asset ne le déclenche — une séquence n'est pas un asset.

---

## Ressources matérielles — l'auteur ne les nomme jamais

Cet éditeur ne représente pas seulement des objets. Il représente **des objets qui devront
être matérialisés simultanément sur une machine minuscule**. C'est ce qui le sépare d'un
éditeur de jeu générique, et c'est la source de la classe de bugs la plus coûteuse du
projet : chaque fonctionnalité marche parfaitement, jusqu'au jour où deux d'entre elles
servent en même temps.

**La règle : aucun concept de haut niveau ne nomme une ressource matérielle.** Une caméra ne
demande pas WIN0, elle demande *une région qui limite son rendu*. L'UI ne demande pas WIN1,
elle demande *un rectangle de découpe*. Un acteur demande *un masque de visibilité*. Ce qui
satisfait ces demandes — et si deux d'entre elles peuvent partager la même ressource — n'est
pas leur affaire.

Trois niveaux, à ne jamais confondre :

| Niveau | Exemple | Qui le manipule |
| --- | --- | --- |
| **Intention** | `RenderRegion`, `ClipRegion`, `VisibilityMask` | l'auteur, dans l'éditeur |
| **Ressource logique** | un masque : géométrie + calques autorisés + règles | l'allocateur |
| **Ressource matérielle** | `WINR_0`, `WINR_1`, `WINR_OBJ`, un charblock, une entrée OAM | le backend seul |

Deux intentions qui décrivent le même masque logique ne consomment **qu'une** ressource
matérielle. C'est tout l'intérêt du niveau intermédiaire, et c'est invisible pour l'auteur.

### Deux allocateurs, pas un — la durée de vie décide

La tentation est d'écrire « un gestionnaire de ressources ». Il y en a deux, et les fusionner
serait une faute : ils partagent un vocabulaire, jamais une implémentation.

| | Résolu au BUILD | Résolu à la FRAME |
| --- | --- | --- |
| Exemples | palettes, VRAM/charblocks, tuiles de police, windows disputées | entrées OAM, canaux DMA, matrices affines |
| Où | Python, `codegen/` | C, dans le runtime |
| Coût admis | élevé — il tourne une fois | quasi nul — il tourne 60 fois par seconde |
| Peut prévenir l'auteur | **oui**, et c'est sa raison d'être | non, il n'a personne à qui parler |

Les windows sont de la colonne BUILD : le nombre d'intentions d'une scène (une caméra à cadre réduit + ses `WindowSlot`
nommés) est connu au build, ce qui permet à `window_alloc.py` de prévenir l'auteur AVANT de compiler — contrairement aux
entrées OAM dynamiques et aux canaux DMA, qui varient selon ce qu'un script fait à l'exécution.

Trois instances existent déjà et sont exactement ça : `codegen/palette_alloc.py`,
`codegen/vram_alloc.py` et `codegen/window_alloc.py` (décrits ci-dessous). Elles arbitrent,
elles replient quand ça ne tient pas — sauf les windows, où aucun repli sûr n'existe (une
région non allouée s'affiche partout au lieu d'être découpée) : `window_alloc.py` fait
échouer le build au lieu de replier. Tout nouvel allocateur de build leur
ressemble.

**Ce qui n'est allouable par personne** : le temps CPU et l'IWRAM. L'IWRAM se décide à
l'édition de liens (attributs de section), le CPU est un budget qu'on *mesure*. Les ranger
dans la même liste que l'OAM laisserait croire qu'un ordonnanceur peut les arbitrer.

`g_actors[]` est explicitement en **EWRAM** (`EWRAM_DATA`) : la table cumule les tranches
des scènes et les pools, donc son coût peut dépasser les 32 Kio d'IWRAM bien avant le plafond
d'OAM. Les accès aux acteurs ne demandent pas la latence minimale d'une boucle critique ;
l'IWRAM reste pour le code et les petits états du runtime. Ce placement est une règle du
codegen, pas une option de projet.

### Le piège propre aux windows : les slots ne sont pas interchangeables

`WINR_0` > `WINR_1` > `WINR_OBJ` > `WINR_OUT` est une priorité **câblée** (cf. « Windows — le
pochoir »). Deux rectangles qui se recouvrent ne rendent donc pas la même image selon le slot
qu'ils occupent. Un allocateur qui traiterait WIN0 et WIN1 comme équivalents produirait une
allocation *valide* et une image *fausse* — rien ne planterait, rien ne se signalerait.

La ressource n'est pas « une fenêtre » mais **« une fenêtre à un rang donné »**, et le rang
appartient au modèle. `window_alloc.py` ne le laisse pas à l'auteur pour autant :
pas de champ « priorité » authorable, l'intention caméra prend TOUJOURS la première place
(`WINR_0`) quand elle existe, déterministe et documenté — cf. « Windows — le pochoir ».

De même, `WINR_OUT` n'est pas une quatrième ressource à distribuer : c'est le complément, et
son contenu change à chaque allocation. Personne ne peut le demander.

## Allocation de la VRAM BG — `codegen/vram_alloc.py`

Les 64 Ko de VRAM BG portent DEUX choses qui se recouvrent : les tuiles (rangées en quatre
charblocks de 16 Ko) et les cartes (rangées en trente-deux screenblocks de 2 Ko). La
convention historique — « le charblock d'un layer est son index, sa carte va à la fin de ce
même charblock » — était simple mais gâchait beaucoup. L'allocateur la remplace, **par
scène**.

- **Tout se raisonne en blocs de 2 Ko** (= 1 screenblock = 64 tuiles 4bpp) : c'est la seule
  unité qui voit à la fois les tuiles et les cartes.
- **L'asymétrie qui dicte tout** : un fond est *rigide* (le champ CharBlock de son registre
  fait 2 bits, et les tuiles sont numérotées à partir de 0 — il est collé à la base d'un
  charblock) ; le texte est *souple* (c'est nous qui écrivons ses entrées de carte, en y
  ajoutant une base). **C'est donc le texte qu'on glisse dans les trous, jamais le fond.**
- **Les cartes sortent du chemin de croissance.** Posée à la fin de son propre charblock, la
  carte d'un layer murait sa propre croissance — la croissance étant contiguë, elle ne peut
  pas sauter par-dessus. Autoriser le débordement sans déplacer les cartes n'aurait rien
  donné.
- **Portée 10 bits** : un layer voit 1024 tuiles depuis la base de son charblock, soit deux
  charblocks — il déborde sur le suivant si rien ne l'occupe. Cas particulier : au-delà du
  charblock 3 commence la VRAM des sprites, donc un layer en CBB3 reste plafonné à 512.
- **Garde-fou** : le placement calculé n'est retenu que s'il donne à CHAQUE layer au moins ce
  que donnait le placement historique — sinon repli complet. Une allocation plus fine ne doit
  jamais casser un projet qui passait. Et le budget est vérifié au build, en erreur bloquante
  et non en avertissement : ici c'est de la mémoire écrasée, pas une mauvaise couleur.

Les modes bitmap restent hors périmètre — leur framebuffer occupe la VRAM BG et se traite avec le rendu bitmap. Le pendant
OBJ (128 slots OAM, 1024 tuiles) est arbitré séparément, dans `main_gen`.

---

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

---

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

---

## Packaging & distribution (Nuitka + NSIS + GitHub Releases)

À ne pas confondre avec le pipeline ROM ci-dessus : ceci construit l'**éditeur lui-même** en exécutable distribuable, pas une ROM GBA.

- **`packaging/nuitka_build.py`** — définition unique de la commande de build, utilisée à l'identique par la CI et en local (`python packaging/nuitka_build.py --version 0.3.2 --output-dir build-out`). Nuitka en mode **standalone** (dossier), pas onefile : l'installateur pose de toute façon un dossier, et le onefile ne ferait que ré-extraire à chaque lancement. Sortie : `build-out/Backstage/`.
- **`packaging/check_deps.py`** — relève les imports réels du code par AST et vérifie que `requirements.txt` les couvre tous. Lancé en CI **avant** le build : c'est le filet qui manquait quand `luaparser` est parti en release sans être déclaré.
- **`packaging/windows/installer.nsi`** — installateur NSIS **par utilisateur** (`%LOCALAPPDATA%\Programs\Backstage`, aucune élévation UAC, désinstallation sous HKCU). La désinstallation laisse volontairement en place les projets (`~/BackstageProjects`) et la config toolchain (`%APPDATA%\Backstage`).
- **`editor/core/app_paths.py`** — source unique de vérité pour « où tourne-t-on ». `IS_FROZEN` s'appuie sur `__compiled__` (le
  marqueur Nuitka ; **`sys._MEIPASS` n'existe pas** hors PyInstaller), et `APP_DIR` vaut le dossier de l'exe en distribution, la
  racine du repo depuis les sources. `RUNTIME_DIR` en dérive : tout module ayant besoin d'un chemin de données passe par ici.
- **`editor/core/app_info.py`** — source unique de « qui est ce logiciel » : `APP_NAME` (Backstage), `APP_AUTHOR` (Yasorovic), `APP_VERSION` (`X.Y.Z-alpha|beta|stable`, cf. ROADMAP, « La numérotation d'une release »). Stdlib seule, sans importation, pour que les scripts de packaging la lisent sur un Python nu. Y puisent la fenêtre, l'« À propos », le rapport de diagnostic, le dossier de config (`config_dir`), les `QSettings`, le build Nuitka (`--product-name`, `--company-name`, nom de l'exe), l'installateur et le workflow. **La version vit dans le dépôt, le tag la confirme** : `nuitka_build.py --version` échoue si le tag diverge, et le job `version` de la release lit `--print-version` ; un build qui écraserait le fichier d'après le tag ferait annoncer à un lancement depuis les sources une version qu'il n'a pas. `tests/packaging/test_app_info.py` garde l'alignement (installateur, build, workflow, libellés) et l'absence des anciens identifiants.
- **Disposition des données** — les données embarquées reproduisent l'arborescence des sources (`runtime/`, `plugins/`, `scripting/api_reference.json`), parce que les modules les résolvent via `Path(__file__).parent` et que Nuitka donne aux modules compilés un `__file__` cohérent dans la distribution. Les images référencées par les QSS ne sont **pas** embarquées : `ui/common/icons.py:qss_image()` les rend depuis qtawesome dans `%TEMP%/backstage_icons/` au démarrage (`ensure_qss_assets()`, appelé après la `QApplication` et avant `setStyleSheet`) — un cache en zone temporaire, donc toujours inscriptible même pour une installation en lecture seule.
- **`editor/plugins/`** est copié tel quel, **non compilé** : chargé dynamiquement via `importlib.util.spec_from_file_location`, ça nécessite des `.py` réels sur disque au runtime. Corollaire assumé : le code des plugins reste lisible dans la distribution, contrairement au reste.
- **`editor/smoke_test.py`** (`Backstage --smoke-test=<rapport>`) — ce que la CI exécute sur le binaire LIVRÉ avant de publier : crée un projet temporaire, le rouvre, **visite chaque écran** (importés paresseusement par leur nom : un module que Nuitka n'a pas vu n'échouerait qu'au premier clic), valide, enregistre, et contrôle les données embarquées (licences, runtime, starter, API, notices). Le verdict va dans un fichier : la distribution Windows est sans console. Sans devkitPro, il ne construit pas de ROM. **Sortie ordonnée** (`main._shutdown_qt`) : la fenêtre doit être détruite tant que la `QApplication` existe ; sinon le processus plantait à la sortie (violation d'accès, 4 fois sur 6 sous Windows) après avoir tout enregistré.
- **`packaging/windows/test_installer.ps1`** — joué par la CI sur le runner (machine propre) : installation silencieuse, mise à jour par-dessus (un fichier de l'ancienne version doit disparaître, un plugin de l'utilisateur rester), désinstallation (application, raccourci, clés supprimés ; projets et configuration conservés), smoke test après chaque installation. Il écrit dans HKCU et le menu Démarrer : il refuse de tourner hors CI sans `-AllowLocal`. Côté `installer.nsi`, `CleanPreviousInstall` purge l'ancienne installation avant la copie, **sauf `plugins\`**, et seulement si l'exécutable attendu est présent.
- **`.github/workflows/release.yml`** — se déclenche sur `release: published` (ou `workflow_dispatch` pour tester sans publier).
  Publie l'installateur Windows `.exe`, un ZIP portable et l'AppImage Linux (smoke test du fichier livré avant publication) ; le
  job `windows-rom-build` (build de ROM sous Windows, devkitPro installé en silence) est hors des `needs` tant qu'il n'a pas passé
  un `workflow_dispatch`. Le cache Nuitka est indispensable : un build à froid est nettement plus long.
- **mGBA / devkitPro ne sont jamais embarqués** — dépendances système externes, détectées à l'exécution par
  `editor/core/toolchain.py` (`resolve_mgba`, `resolve_grit`, `resolve_make`, `resolve_arm_gcc`). L'auto-téléchargement de mGBA a
  été tenté puis **abandonné délibérément** : flux 100% manuel par choix.

### Piège connu : Python de dev vs Python de CI

La CI et le build Nuitka figent Python 3.12 (évaluation immédiate des annotations) ; un poste en 3.14 les évalue
paresseusement (PEP 649). Une annotation non protégée vers une classe définie plus bas, ou un nom jamais importé, ne casse que
la CI. Remède : travailler dans le venv 3.12 ci-dessous, et citer entre guillemets toute référence en avant.

### Environnement de dev figé sur la version CI (`.venv-build312`)

Le poste tourne en Python 3.14, mais la CI **et** le build Nuitka figent 3.12 (bornes de `requirements.txt`). Pour travailler « avec ce qui sortira réellement au build » sans toucher à l'interpréteur du poste, on crée un venv 3.12 **dans le dossier du projet** — nom conventionnel `.venv-build312`, déjà ignoré par `.gitignore` (`.venv*/`) :

```powershell
py -3.12 -m venv .venv-build312
.venv-build312\Scripts\python.exe -m pip install --upgrade pip
.venv-build312\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

Deux variables d'environnement reproduisent la CI ; les omettre change le résultat :

- `QT_QPA_PLATFORM=offscreen` — PyQt6 sur une machine sans écran (sinon l'import échoue).
- `CC=C:\msys64\ucrt64\bin\gcc.exe` — sans compilateur C hôte, les tests d'équivalence Python/C sont **skippés**, et un skip natif est un **échec** en CI (`GBA_TESTS_REQUIRE_NATIVE=1`).

Contrôles locaux, identiques au job CI :

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:CC='C:\msys64\ucrt64\bin\gcc.exe'
.venv-build312\Scripts\python.exe tools\check_architecture.py --fresh
.venv-build312\Scripts\python.exe -m pytest tests -q
```

Un manque de **bibliothèque système Linux** (p. ex. `libpulse.so.0`, réclamée par `PyQt6.QtMultimedia` du mixer son) ne se voit **pas** dans ce venv Windows : il relève des workflows GitHub (listes `apt-get` de `tests.yml` / `release.yml`), pas de l'environnement Python local.

---

## Dépendances externes

- **Runtime Python** : PyQt6 (interface), Pillow (pipeline d'images), qtawesome (icônes, optionnel).
- **devkitPro** (toolchain GBA) : devkitARM (`arm-none-eabi-gcc`), grit (PNG → tuiles/palettes), libgba, mmutil (audio maxmod), make.
- **mGBA** : émulateur de Build & Run.

`PyQt6` et `Pillow` sont des paquets Python (voir `requirements.txt`). `devkitPro` et `mGBA` sont des outils système installés séparément — ils n'apparaissent pas dans un gestionnaire de paquets Python.
