# Architecture

Comment le projet est construit, pour qui modifie le code : les couches, les règles qui tiennent l'ensemble, les pièges qui ne se voient pas en lisant une fonction. Le [README](README.md) reste le point d'entrée d'un utilisateur ; ce document garde l'essentiel, et le détail long vit dans [docs/development](docs/development/index.md).

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
│   │   │                              créer un asset, ce qui cite encore un asset avant de le supprimer, `source_collisions` : un import qui
│   │   │                              rencontre un fichier du même nom)
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
│       ├── common/                  ← transverse : theme.py (C couleurs / T typographie, jamais de valeur en dur),
│       │                              three_column_body.py (le squelette library | centre | inspecteur), catalog.py,
│       │                              labels.py et notice.py (textes de l'éditeur, cf. « Textes de l'ÉDITEUR »), locate_bus.py
│       │                              (cf. « Locate et Reveal »), panneaux Build et Disk
│       └── <écran>/                 ← home, scene_manager, sprite_editor, background_editor, palette_editor, data_editor,
│                                      sound_mixer, script_editor, text_editor : un fichier par sous-zone
│                                      (`*_library_panel` | centre | `*_inspector*`), assemblées par `*_screen.py`
│                                      (scene_manager : `inspectors/`, un fichier par classe d'inspecteur, routés par
│                                      `dynamic_inspector.py` qui construit chaque inspecteur à sa PREMIÈRE venue)
├── runtime/                         ← le moteur GBA écrit À LA MAIN, en C. Aucun .py : pour l'éditeur c'est de la DONNÉE,
│   │                                  jamais importée, seulement recopiée dans build/ (cf. app_paths.RUNTIME_DIR)
│   ├── Makefile                     ← copié dans build/, pilote arm-none-eabi-gcc
│   └── include/
│       ├── gba_engine.h             ← le gros du moteur : VRAM, layers, windows, blending, palettes, fonds animés, texte, SRAM.
│       │                              Inclus UNE SEULE FOIS, depuis le main.c généré
│       ├── runtime_api_inline.h     ← l'API des scripts écrite à la main, incluse par chaque unité de compilation après le
│       │                              `runtime_api.h` GÉNÉRÉ (cf. « Ce que le build vérifie »)
│       ├── actor_types_static.h     ← structs et constantes GBA, partie non générée
│       └── gba_debug.h              ← sortie de debug
├── packaging/                       ← packaging Nuitka + CI (voir section dédiée) : nuitka_build.py (commande unique, CI et local),
│                                      check_deps.py (requirements.txt vs imports réels), windows/installer.nsi, linux/ (AppImage)
├── tools/                           ← check_architecture.py (les règles de ce document, rendues exécutables, cf. « Les règles
│                                      ci-dessus se vérifient toutes seules »), check_ui_text.py, migrations ponctuelles de format
├── tests/                           ← `pytest tests` (un dossier par tâche : rom_build, scripting, graphics, text, ui, audio, …).
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
        └── build/                   ← 100% généré, gitignored (compile assets/)
```

---

## Conventions d'écriture

Chaque casse **porte une information** : un lecteur doit pouvoir déduire la nature d'un identifiant de sa seule forme, dans les trois langages du projet (Python de l'éditeur, C généré, C écrit à la main).

### Visibilité Qt et micro-fenêtres

**Toujours donner un parent à un widget enfant avant `show()` ou `setVisible(True)`.** Sans parent, Qt le traite comme une fenêtre indépendante : le montrer puis le rattacher à un layout provoque une micro-fenêtre qui apparaît et disparaît à la construction. Créer l'enfant avec son parent, attacher ses layouts, puis appliquer sa visibilité ; à la reconstruction, masquer un enfant visible **avant** `setParent(None)`. Garde-fou : `tests/ui/test_cartridge_preview.py::test_project_settings_never_show_temporary_top_level_widgets`. Ne pas le traiter par un délai ou un masquage tardif.

### La casse dit la nature

| Casse | Nature | Exemples |
|---|---|---|
| `snake_case` | variable, fonction, méthode, argument (Python **et** C) | `frame_w`, `bg_se_addr()`, `pal_bank` |
| `PascalCase` | classe / dataclass Python, struct C, concept du domaine | `BackgroundLayer`, `struct Actor` |
| `UPPER_SNAKE` | constante de module, `#define` C, énumération matérielle | `RUNTIME_API`, `DOMAIN_SCENE`, `WINR_0` |
| `_leading_underscore` | **interne** : ni à importer ni à appeler de l'extérieur | `_emit_api_call()`, `self._vec_types` |
| `g_`, `_sh` | réservés au moteur C : `g_` = état global runtime, `_sh` = registre *shadow* (copie RAM d'un registre write-only) | `g_actors[]`, `g_bgcnt_sh[4]` |

**Le fichier suit son contenu** : un fichier Python porte le nom de sa classe en `snake_case` (`background_layer.py` → `BackgroundLayer`) ; un écran range ses fichiers par sous-zone, pas par type de widget. **La seule exception à `snake_case` : les surcharges Qt** (`paintEvent`, `sizeHint`…), contrat imposé de l'extérieur. Pas de `camelCase` maison.

### Les symboles C générés portent leur origine dans leur nom

Un symbole généré nomme d'où il vient, par un préfixe stable : `g_data_<Table>`, `scene_init_<Scene>` / `scene_tick_<Scene>`, `spawn_<Scene>_<Prefab>` (per-scène, rend `Actor*` ou `NULL`), `g_<nom>` / `CONST_<NOM>` (accès pointé `global.nom` / `const.nom`), `SCENE_<Nom>` / `PAL_<Nom>` / `CAM_<Nom>` (`<PREFIX>_<Nom>`, cf. `api.py`). Ils garantissent l'unicité dans l'espace de noms C plat et rendent un identifiant traçable jusqu'à sa donnée source.

### Un concept, un seul mot (la grammaire unique)

**Un concept a un seul nom, écrit identiquement dans le C généré, la classe Python et le label UI.** L'utilisateur ne doit pas apprendre deux vocabulaires.

- **Pas d'abréviation**, même « évidente » : `CollisionBox`, jamais `CollBox` ; `rotation`, jamais `rot`.
- **Suffixe `Component`** pour tout composant attachable à un `Actor` (`SpriteComponent`, `CollisionBoxComponent`, `ScriptComponent`), jamais `Comp`, `Behavior`, `System`.
- **Le nom C reflète exactement le concept Python**, sans le raccourcir.
- **Renommer, c'est renommer partout** : classe, fichier, labels, références, pas seulement le libellé UI. Un renommage éditeur (`Project.rename_*`) réécrit les références Lua par repérage **structurel**, jamais textuel.

Avant de nommer un nouveau type, vérifier que le **même mot** est employé aux trois endroits. Entre « juste le libellé » et « renommage complet », c'est toujours le renommage complet.

### Locate et Reveal (deux gestes, deux noms)

**Locate** mène à l'onglet **Disk** de l'éditeur (`ui/common/locate_bus.py` → `window._locate_file`) : l'émetteur dit seulement QUEL fichier, la fenêtre qui possède l'onglet décide comment l'afficher. **Reveal** mène à l'**explorateur du système** (`ui/common/reveal.py`) et n'a pas besoin de la fenêtre. Une library tient les deux derrière `AssetKind.file_of` : une famille qui le déclare gagne l'icône et les deux entrées de menu, sans autre câblage.

### Importer sur un fichier du même nom (une règle, une question)

Tout geste qui copie un fichier dans `assets/` (le « + » des sprites, fonds et sons, l'import et le dépôt de l'onglet Disk, *Import / replace image*) suit **la même règle**, écrite une seule fois dans `core/source_collisions.py` : le **même nom exact** dans le dossier est une collision, que l'auteur tranche par une seule boîte (`ui/common/import_collision.py` : écraser, garder les deux, annuler) ; tout autre nom pris est suffixé par `unique_name` (`coin_2`), sans question. La boîte nomme aussi les assets qui citent le fichier (`source_collisions.citing`, lu dans `Project.source_families`), puisque l'écraser les change tous. **Remplacer l'image d'un asset** (`ui/common/source_import.replace_source`) n'est pas un import : le fichier choisi est écrit SUR la source que l'asset cite déjà, et la boîte ne s'ouvre que si un autre asset la cite aussi. Toutes ces copies sont des `ImportFilesCmd` poussées dans l'historique, qui garde le contenu écrasé et le remet à l'annulation. L'encodage de l'asset (sprite, fond) n'y figure pas : il se refait au rechargement de la source.

---

## Terminologie

**Éditeur ↔ GBA.** Un `SpriteAsset` est un PNG converti par grit en tuiles 8×8 d'OBJ VRAM ; une `Scene` devient une paire C `scene_init_X` / `scene_tick_X` dispatchée par une vtable de `main.c` ; un `Actor` est une entrée de `g_actors[]` (EWRAM) dont l'affichage est une entrée de `g_oam_entries[]` ; un `BackgroundLayer` est un plan BG physique **de la scène** (charblock `bg_slot` + screenblock, 4 au plus) qui cite un `BackgroundAsset` (tileset + sous-palettes, sidecar par image, PNG jamais modifié) ; une `PaletteBank` est une palette nommée de 16 couleurs BGR555 du catalogue, et `Scene.active_obj_palettes` / `active_bg_palettes` en sélectionnent jusqu'à 16 par pool (l'ordre = la banque matérielle, `pal_bank` indexe dans cette liste). Le Lua est **transpilé vers C**, jamais interprété.

**Abstractions pures** (sans équivalent GBA) : le `Prefab` (template d'acteur ; chaque instance génère son propre code C) et l'`AnimState` (état d'animation nommé, converti en index entier).

**Composants** : `SpriteComponent` (lien vers un `SpriteAsset`, état initial, vitesse), `CollisionBoxComponent` (AABB ; `solid` ne décide que d'une chose : la box est-elle arrêtée par la carte de collision), `SoundFxComponent`, `ScriptComponent` (**un seul actif par acteur**), `PathComponent` (en cours). Les handlers de collision (`on_collision_enter`, `on_collide`, `on_tile_collide`) sont ceux du script de l'acteur, pas du composant.

### Deux tables runtime : acteurs et entrées OAM

L'éditeur distingue un **actor** (logique de jeu), un **sprite** (son rendu) et un **background** (le décor). Le C a **deux tables** : `g_actors[]` (un indice = un acteur : identité, position, vélocité, transform monde, collision, lien `oam_entry`) et `g_oam_entries[]` (un indice = une entrée de l'OAM, qui double `shadow_oam[k]` : tout l'état d'affichage, à savoir `frame`, animation, registres OAM, transform local, `affine_slot`). Les bandes de texte et l'interface occupent aussi des entrées, d'où le nom.

- **Pourquoi séparer** : un acteur qui n'affiche rien (contrôleur, spawner, déclencheur) ne paie ni état d'affichage ni slot OAM. À struct plate, l'empreinte OAM d'une scène dimensionnait les acteurs.
- **Coût borné** : le writer OAM et le tick d'animation sont **émis au build**, un bloc par entrée, à adresse fixe. Seuls les accesseurs de script, qui reçoivent un `Actor*`, traversent le lien (`actor_oam_entry(s)` = `&g_oam_entries[s->oam_entry]`).
- **Types étroits** : `OamEntry` fait 32 octets et `Actor` 68 (contre 92 et 96 en tout `int`) ; un test mesure `sizeof` avec le compilateur hôte.
- **Géométries**, calculées par scène par `codegen/oam_alloc.py` : `g_actors[]` = [acteurs posés][pools : instances × parties] ; `g_oam_entries[]` = [entrées des posés À SPRITE][interface & texte][entrées des pools À SPRITE]. Seul un porteur de sprite (`has_oam_entry`) occupe une entrée ; les autres ont `oam_entry = -1`, et sur un tel acteur `self.frame` ou `self:show()` lisent 0 / n'ont aucun effet. Les pools gardent un indice d'acteur (`POOL_*_START`) et une entrée de départ distincte.
- **La coupure est const/variable, pas classe/classe** : la **définition** d'un sprite (états, directions, vitesses, boucles) n'est pas une struct mais des tables `static const` en ROM, émises par sprite.
- **Le background n'a pas de type, parce que le calque EST le matériel** (`layer_show(int bg, …)`, registres ombres `g_bgcnt_sh[4]`) : un type instanciable suggérerait qu'on peut créer un cinquième plan. `BgAnim` et `BgTileAnim` sont des états d'animation.
- **Les champs se lisent avec le vocabulaire de l'inspecteur** : `Actor` porte `x, y, vx, vy, tag, active, dir_x/y, rotation, scale_x/y` (transform **monde**) et `oam_entry` ; `OamEntry` porte l'affichage (`frame`, `anim_*`, `frame_w/h`, `flip_*`, `pal_bank`, `obj_mode`, `priority`, `screen_space`, `rotation`, `scale_x/y`, `offset_x/y`, `affine_slot`, transform **local**) ; `Actor.collision` porte `grounded, last_x, slope_acc, box_count, boxes[]`.
- **La surface Lua ne bouge pas** : `self.frame`, `self.anim_length`… passent par les accesseurs de `runtime_api_inline.h`, seul endroit (avec le C émis) qui touche les champs. `api.py`, `codegen.py`, `checker.py` et `expr_types.py` n'émettent que des `&g_actors[ACTOR_*]` et des appels `actor_get/set_*`.
- **`anim_length` / `anim_loop` / `anim_finished` sont écrites sur `OamEntry`** : `anim_length` est la longueur du bloc de la **direction actuellement jouée** (parcours de `anim_dirs[]` avec repli sur l'omni) que le tick mémoïse et écrit CHAQUE frame (`main_gen._anim_tick_lines`). À chaque tick, un `frame` hors de `[_fs, _fs+_fc)` est ramené à `_fs` : `play_anim` remet `frame` à 0, absolu dans le sheet dédupliqué.

### Règles clés

- **Une extension par type d'asset** : `<nom>.<type>` (`Player.sprite`, `Scene_01.scene`, `Night.palette`…), contenu JSON. La table unique est `core/models/asset_extensions.py` (chaque modèle porte la sienne). Restent en `.json` : `texts.json`, `texts_<langue>.json`, `variables.json`. Le `.hex` d'une palette est sa donnée canonique, que le `.palette` POINTE par son champ `asset`.
- **`assets/` est le dossier de l'auteur** : TOUT ce qu'il manipule y vit (sources brutes comme les PNG et les sons, scènes, prefabs, mises en page, boîtes sonores, tables, polices logiques, textes, variables), et il l'organise lui-même. `project/` ne garde que l'état interne de l'éditeur, les licences et le README. `build/` est 100 % généré. Pour l'auteur c'est son dossier « assets » et l'onglet « Disk » ; **dans le code, ce dossier s'appelle toujours `user_library`** (`Project.user_library_dir`), jamais « assets » ni « project files ».
- **Bibliothèques** (`ui/common/asset_library.py` : `AssetLibrary`, un seul composant pour toutes les familles) : la **Scene library** (`ui/scene_manager/scene_library_panel.py`) ne montre que scènes et prefabs, la **Script library** (`ui/script_editor/script_library_panel.py`) les scripts. « Voir les utilisations » d'un script remplace la colonne droite du Script Editor par `ScriptUsesPanel` (`ui/script_editor/script_uses_panel.py`, base `ui/common/uses_list.py`) ; un clic sur une ligne ouvre le Scene Manager sur la cible (`MainWindow._show_script_user`). Dans le code, le dossier de l'auteur est la **user library** (`Project.user_library_dir`) ; pour l'auteur, c'est son dossier « assets » et l'onglet « Disk ».
- **Lancé avec un fichier**, l'éditeur ouvre un `<Nom>.project` (son dossier), ou un fichier d'asset / un `.lua` (le projet qui le contient, puis le fichier dans son écran : `core/launch_target.py`, `MainWindow.open_asset_file`). Seul `.project` est associé au système ; les extensions d'asset ne le sont pas.
- **`<Nom>.project`** est le manifeste racine : on le double-clique, et son nom de fichier EST le nom du projet. Config racine uniquement ; `start_scene` (départ du **jeu**) et `last_scene` (dernière scène ouverte dans l'**éditeur**) sont deux champs distincts.
- **Les assets sont référencés par nom**, jamais par chemin absolu.
- **Un argument de script qui cite un élément du projet** est déclaré par le `domain` de son `Param` dans `scripting/api.py` : cette table unique sert au checker (valider), au codegen (résoudre en index) et à `refactor.py` (suivre les renommages).
- Les `GlobalVar` sont des variables C partagées par tous les scripts (`globals.h`/`globals.c`, une fois par build). Chaque scène génère `scene_init_X` / `scene_tick_X`.

---

## API Lua ↔ C

Le script Lua n'est jamais traduit directement en texte C : `parser.py` → AST Python → `checker.py` (validation) → `codegen.py` → C, les deux derniers lisant `scripting/api.py` (`RUNTIME_API`), **catalogue unique** : nom Lua, fonction C cible, types de paramètres, domaine de résolution des chaînes. Une fonction qui se traduit par un simple appel C n'a besoin que d'une entrée de catalogue ; celle qui demande de la logique de traduction rejoint aussi `_INVOKE_CUSTOM` / `_CALL_CUSTOM`. `lua_subset.py` liste ce que le langage accepte et refuse (chaque refus dit quoi écrire ; `validator._check_lua_subset` bloque un nœud non classé). Le détail est dans [docs/development/scripting-internals.md](docs/development/scripting-internals.md).

### La grammaire de l'API (trois formes, une par nature)

| Syntaxe | Nature | Compile en |
|---|---|---|
| `identifier:member(...)` | **méthode** (opération sur une instance) | `actor_member(récepteur, ...)`, `sfx_member(...)` |
| `identifier.member` | **propriété** (donnée exposée comme un état, lue et écrite) | `actor_get_member(...)` / `actor_set_member(...)` |
| `module.member` / `module:member(...)` | **singleton** du moteur : propriété ou méthode | `module_get_member()` / `module_member(...)` |

La forme dit au parseur quoi produire (`Invoke` pour `:`, `Index` pour `.`), donc qui décide de la résolution. Règle de décision pour toute API future :

- **état intrinsèque** → propriété (jamais de `get_*`/`set_*`) ; **requête pure sans argument** → propriété en lecture seule ; **requête INDEXÉE** → fonction ;
- **action qui produit un effet** → méthode sur son récepteur ;
- **cycle de vie** → cinq verbes communs `show`/`hide`/`activate`/`deactivate`/`destroy`, seule porte d'ÉCRITURE ; l'état se lit par `visible`/`active` en lecture seule. `destroy` ne vaut que pour les instances de pool ;
- **réglage d'inspecteur** → il a TOUJOURS une porte : modifiable au runtime → lecture ET écriture ; fixé au build → lecture seule. Un champ édité mais invisible du script est un oubli.

`global.nom` / `const.nom` / `data.Table[i].champ` sont des accès pointés qui compilent en `g_nom` / `CONST_NOM` / `g_data_Table[(i) - 1].champ`, validés par nom du projet plutôt que par catalogue (une entrée par variable déclarée serait un catalogue régénéré à chaque édition).

### Module, type, instance (d'où vient le récepteur)

Un **module** est un système unique ou une **fabrique** (`camera`, `scene`, `actor`) ; un **type** a des instances et **son nom est la clé du catalogue** (`sfx`, `collision_box`, `ui_element`) ; une **référence** désigne une instance quand elle ne se déduit pas du contexte (`actor.get`, `sfx.play`). **Un module n'opère jamais sur UNE instance désignée par un nom du projet** : il l'acquiert, puis tout passe par la référence (`local menu = interface:get("Menu")`, `menu.index = 0`, `menu:show()`). Déclarer un type de référence = une ligne dans `api.REF_TYPE_TABLE`, ses entrées de catalogue, et ses fonctions C ; tout le reste (local typé, refus d'un membre inconnu, snippets, renommage) s'en dérive.

### Ce que le build vérifie

- **Prototypes générés** : les prototypes exposés sont **générés** dans `runtime_api.h` depuis `gba_engine.h` (`api_prototypes.py`) ; `validator._check_api_prototypes` garde, en erreur bloquante, l'accord de VALEUR des énumérations redéfinies à la main côté moteur et l'ORDRE des arguments (une permutation compile : tout est `int`).
- **Un domaine a TROIS consommateurs** (`refactor`, `checker`, `codegen`). Les deux derniers sont des tables comparées à `api.ALL_DOMAINS` par `validator._check_api_domains`, en erreur bloquante : un domaine absent ne produirait aucun signal, et la panne arriverait au `make`. Placer un nouveau domaine dans une case fait partie de son ajout.
- **Un nom se vérifie par son domaine**, jamais par le nom de l'appel (`DOMAIN_PREFAB` inconnu est une erreur de checker, sinon `spawn_<Scene>_<Nom>` n'échoue qu'au `make`).
- **Ce que l'éditeur insère dérive du catalogue** (`api_snippets.py`, `api_reference.get_categories()`) : une fonction retirée disparaît de la sidebar, une ajoutée y apparaît.

---

## Layers BG vivants (shadows de registres)

`DISPCNT` et `BGxCNT` sont relisables, mais `BGxHOFS/VOFS` sont **write-only** : le scroll doit vivre en RAM. Un seul modèle : `gba_engine.h` garde une copie de tout (`g_dispcnt_sh`, `g_bgcnt_sh[4]`) et **toute** écriture passe par `dispcnt_set()` / `bg_cnt_set()`, y compris à l'init de scène. Visibilité, priorité (z-order) et screenblock affiché deviennent ainsi modifiables en cours de jeu.

- `display_reset()` remet layers, windows et blending à neuf en tête de `scene_init_*`, sinon une scène hériterait des layers de la précédente.
- `g_bg_ofs_x/y[4]` est le décalage **propre au layer** ; `scene_tick_*` écrit `BGOFS = (cam × parallax) + décalage propre`. Un layer sans image (UI/texte) n'est pas touché par le tick.
- `bg_se_addr()` gère les 4 tailles de map et leur découpage en blocs 32×32 ; `tilemap_set()` ne touche que les 10 bits d'index (flip et banque de palette survivent) ; `tilemap_set_palette` est l'inpainting au runtime (`SE_PALBANK`).

### Windows (le pochoir)

Une window GBA **ne dessine rien** : c'est un pochoir qui dit, par région de l'écran, quels layers et sprites s'affichent et si le blending s'applique. Elle exprime le *où* sans imposer un *à quoi ça ressemble*, d'où sa valeur pour l'UI. Quatre régions par priorité décroissante : `WINR_0`, `WINR_1`, `WINR_OBJ` (fenêtre-objet), `WINR_OUT` (le reste) ; un pixel obéit à la première qui le contient. Les constantes sont préfixées `WINR_*` parce que libtonc définit déjà `WIN_OBJ`… avec une autre sémantique.

- `window_reset()` pose **tout autorisé partout, aucune window active** : sans ce défaut, activer une window éteindrait tout l'écran hors du rectangle (`WINOUT` régit le reste dès qu'une window existe). `window_set()` clampe à 240×160 et interdit les rectangles inversés.
- **Fenêtre-objet** : `Actor.obj_mode` (0 normal, 1 semi-transparent, 2 fenêtre) est injecté dans `attr0` aux **trois** sites d'émission OAM de `main_gen.py` (acteur de scène, prefab poolé, sprite affine).
- **WIN0 et WIN1 sont allouées par intention, pas par index câblé** (`codegen/window_alloc.py`). Une caméra dont le cadre est plus petit que 240×160 demande *une région de rendu* ; un panneau UI (`WindowSlot`) demande *un rectangle de découpe*, et se NOMME. `scene_window_layout()` résout au BUILD, par scène : l'intention caméra prend toujours la première place, puis chaque `WindowSlot` nommé dans l'ordre d'auteur. Une troisième région fait échouer le build, nommée, plutôt que de s'afficher partout (bug visuel silencieux, sans repli sûr). Le budget « N / 2 windows » vient d'une seule fonction (`scene_window_budget()`). Ne sont pas couverts : `WINR_OBJ` (piloté par `obj_mode`) et `WINR_OUT` (le complément) ; le vrai écran partagé reste hors périmètre.
- Les appels `window.*` adressent une window rectangle par NOM (`DOMAIN_WIN_REGION`), jamais par index matériel.

### Les 128 entrées OAM sont allouées PAR SCÈNE

Une seule scène est vivante à la fois : chaque `scene_init` efface `g_actors[]` et repose sa fenêtre OAM **depuis l'entrée 0**. `scene_oam_layout(project, scene) -> OamLayout` (`codegen/oam_alloc.py`) est la source de vérité unique : acteurs posés, puis bande d'interface en sprites, puis pools de prefabs (`Scene.prefab_pools`). `headers.py` et `main_gen.py` en sont des **lecteurs**.

- `g_actors[]` est dimensionné sur la scène la plus gourmande (le MAX, pas la somme).
- Les symboles portent la scène (`spawn_<Scene>_<Prefab>`, `ACTOR_*`/`POOL_*` repartent de 0 par scène) : un état project-wide indexé par `Actor.tag` doit devenir per-scène (`g_sfx_on_destroy_*` : un pointeur posé au `scene_init`).
- **Le budget OAM est UNIQUE, par priorité, et n'est jamais bloquant** (sauf une interface seule > 128) : `scene_oam_layout` donne ses entrées à l'interface, puis aux acteurs posés, puis aux instances de pool, dans l'ordre. Ce qui ne tient pas vit sans s'afficher (`oam_entry = -1`, ou l'entrée poubelle `OamLayout.scratch_start` pour un pool) et `validator._check_actor_budget` AVERTIT. La taille d'un pool (`Scene.prefab_pools`, ou `POOL_DEFAULT_INSTANCES` = 8 pour un prefab que les scripts spawnent) ne règle donc que les slots d'acteurs et l'état de script, pas l'OAM.

### Blending (deux jeux de cibles)

`BLDCNT` porte **deux** listes de cibles : le *dessus* (ce qui est mélangé) et le *dessous* (avec quoi), d'où le paramètre `side` (0 = dessus, 1 = dessous). En mode alpha, rien ne se mélange là où le dessus n'a pas de dessous derrière lui. C'est la cause première des effets qui « ne marchent pas », le dessous manquant étant souvent le backdrop. Trois portes en cascade : **le mode** (`blend_set_mode` : 0 aucun, 1 alpha, 2 vers le blanc, 3 vers le noir ; 2 et 3 se dosent par `BLDY`), **les cibles**, **les régions** (`window_set_blend()` décide *où* l'effet s'applique). Un sprite en `obj_mode` 1 court-circuite la liste du dessus. Les trois registres sont shadowés et `blend_flush()` est le seul à les écrire ; `eva`/`evb`/`evy` sont des seizièmes clampés à 0-16.

### Collision de tuiles (une géométrie, deux lecteurs)

Une carte de collision est un octet par tuile de 8×8. Ce que l'octet DÉSIGNE (bloc plein, pente, plafond incliné) est décrit une seule fois, dans `core/models/collision_tiles.py` : le **canvas** en tire son polygone, le **codegen** en tire `g_tile_surface[type][8]` (l'ordonnée de la surface dans chacune des 8 colonnes). Sans cette source commune, la physique n'aurait aucune forme.

`resolve_actor_tiles` (émise par `main_gen`) ne résout qu'une **vélocité** : un acteur à `vx = vy = 0` n'a pas été conduit cette frame et reste tel quel. `self.position` téléporte (ignore la carte), `self.velocity` déplace physiquement. Ordre de résolution, qui EST la règle :

1. **X d'abord**, et seul `TILE_SOLID` repousse (une pente qui bloquerait l'horizontale serait un mur) ;
2. **plafond**, si l'acteur monte ; 3. **sol** : deux coins bas et centre de la box, la surface la plus haute l'emportant ;
4. **vitesse le long du sol** réduite du cosinus de la pente gravie (`g_tile_scale`, précalculé), reste reporté au 1/256 de pixel ;
5. **collage** en descente tant que l'écart reste sous `|Δx|×2 + 1`.

Hors carte vaut **plein** dans les quatre directions (monde = boîte close ; l'OAM ne code Y que sur 8 bits). Rien n'agit à distance (le moteur n'a pas de gravité), et `grounded` décrit la FIN de la frame précédente (la résolution suit les `on_update`). `CollisionBox.solid` ne décide que de la carte : les collisions acteur-contre-acteur ne le consultent pas.

### Caméra (une donnée, pas du code)

`cam_x`/`cam_y` est l'origine d'une zone de taille écran, dont tout se dérive. Ce qui la DÉCIDE est une **caméra**, possédée par sa scène (`Scene.cameras`) : mode, cible, zone morte, bornes, script. Plusieurs par scène, une seule active.

- **Table en ROM, index actif en RAM** : `main_gen` aplatit toutes les caméras dans `g_cam_table[]` (`Camera` est défini dans `runtime_api_inline.h`) ; l'entrée **0 est la caméra par défaut** (fixe, sans bornes), pour éviter un cas particulier à chaque activation.
- **`camera_switch(i)` pose le cadrage ET les bornes** (seul écrivain de `g_cam_max_x/y`), appelle le `on_start` de la caméra, et pose `window_set(0, …)` si `frame_w/h` < 240×160.
- **L'ordre dans `scene_tick` est la règle** : retrait de la secousse précédente → suivi déclaratif → script de la caméra → clamp aux bornes → secousse. Le clamp a le dernier mot sur la position logique ; la secousse se pose par-dessus et rien d'autre ne la connaît.
- **La cible se résout dans la scène propriétaire** (nom local, `_check_cameras` le vérifie) ; **le nom d'une caméra est unique à l'échelle du PROJET** (`camera:switch("Nom")`, constante globale `CAM_<NOM>`).
- Le script d'une caméra emprunte le chemin des scripts de scène (`owner_kind="camera"`, deux points d'entrée seulement).

### Transitions de scène (le fondu possède les registres)

Un changement de scène joue un fondu à la fermeture puis à l'ouverture. (1) **Le séquencement vit dans la boucle principale générée**, seule à connaître les deux scènes (`scene_switch()` ne pose que `g_next_scene`) ; la machine à états `g_trans_phase` n'est émise que si au moins une scène a une transition. (2) **Entre `transition_begin()` et `transition_end()`, le fondu possède `BLDCNT`/`BLDY`** : `blend_flush()` cesse de descendre les shadows au matériel, qui continuent d'enregistrer et prennent effet d'un coup à la fin ; sans quoi l'écran se rallumerait sur une scène à moitié construite. (3) **La scène sortante gèle** dès la première frame de fermeture. L'héritage projet → scène (`transition_kind/frames`) est résolu **au build** par `transition_of()`.

---

## Sens des dépendances

L'empilement visé, du haut vers le bas (**une couche ne dépend jamais de ce qui est au-dessus d'elle**) :

```
ui/            l'interface
core/          la logique éditeur et le projet ouvert
core/models/   les données du projet, et le format binaire qu'elles décrivent
codegen/       la génération du C, qui consomme le modèle
```

- **`core/models/tile_codec.py` n'importe rien** : un module feuille ne peut participer à aucun cycle.
- **`Project` ne connaît pas l'application** : il énonce des faits sur son `EventEmitter` (`renamed`, `status`) et reçoit sa `rename_scope`. `CommandDispatcher.setup()` s'y abonne ; un projet ouvert sans interface (build en ligne de commande, test) est muet de lui-même.
- **Un nom s'importe du module qui le DÉFINIT** (`from core.models.scene import Scene`), jamais à travers `core.project`.
- **Un import posé dans une fonction est un signal** : légitime pour un coût de démarrage, mais quand il évite une boucle, il la cache. Au doute, le remonter en tête de fichier : s'il échoue, la boucle était réelle. **Un import différé n'est vérifié par rien** : après un déplacement de symbole, résoudre *tous* les `from … import …` du dépôt.
- **Un `__init__.py` de paquet ne devrait rien importer au chargement** (il s'exécute avant tout module du paquet) ; ce qu'il expose se donne paresseusement (`__getattr__`, PEP 562).

### Les règles ci-dessus se vérifient toutes seules

`python tools/check_architecture.py` : boucles d'import, sens des dépendances, imports résolus, **noms résolus**, code mort, frontières respectées, plus les catalogues de textes (`tools/check_ui_text.py`). Sortie non nulle si l'un échoue. Les boucles restantes sont **assumées et datées** (affichées sans faire échouer : un contrôle rouge en permanence n'est plus lancé) ; toute boucle nouvelle échoue, et les exemptions se justifient par écrit dans le script (`BOUCLES_ACCEPTEES`, `VIVANTS_SANS_APPELANT`). `--fresh` (~55 s) importe chaque module **seul, dans un interpréteur neuf**, seul moyen de voir une boucle qui dépend de l'ORDRE.

### Deux implémentations qu'il faut tenir d'accord (`core/engine_emulation/`)

Certains calculs existent **en double, dans deux langages** : où atterrit chaque glyphe, comment deux couches se mélangent, comment sonne un module passé au mixeur Maxmod. C'est le **pire mode de panne du projet** : corriger une formule d'un seul côté ne casse rien et produit un éditeur qui montre autre chose que ce que la ROM fabrique. Ce qui entre dans `core/engine_emulation/` a un jumeau dans `runtime/`, et son en-tête le nomme. À ne pas confondre avec du code **partagé** (le build et l'aperçu appellent la même fonction : une seule implémentation, rien à tenir d'accord).

### `Project` est découpé en tranches, pas en collaborateurs

`core/project.py` garde les registres d'assets, la scène active, les recherches et `save`/`load` ; `project_paths`, `project_variables`, `project_texts` et `project_renames` sont des **mixins**. La découpe sert la LECTURE sans rien coûter à l'écriture (`project.rename_scene(...)`). Le prix : ces fichiers ne sont pas autonomes (ils supposent le reste de `Project`) et aucun ne doit importer `core.project`.

---

## Chargement différé (indexer d'abord, matérialiser au besoin)

`ResourceIndex` inventorie chaque collection (`nom → chemin`) sans lire son JSON ; `ResourceStore` matérialise une entrée dans `get(nom)` quand on la demande. `Project.load()` indexe, charge les scènes et précharge seulement les sprites et fonds cités par la scène active ; les écrans Backgrounds, Animations et Sounds demandent leur collection à leur première visite. **Build, validation et opérations transversales appellent `Project.load_all_resources()`** : leur contrat exige une vue complète. La réconciliation des fichiers source reste attachée à la matérialisation de sa collection.

Le point d'entrée **ouvre le projet fenêtre cachée, puis l'affiche déjà dessinée** (le premier `show()` est l'endroit coûteux). Le `DynamicInspector` construit ses sous-inspecteurs à leur première venue, et l'aperçu des boîtes de texte du canvas est pré-chauffé hors écran en partageant une seule allocation de scène (`palette_alloc.scene_layout_cache()`, que le build n'ouvre jamais).

---

## Ajouter un écran (le catalogue et le contrat)

Il n'y a qu'**une liste**, `MainWindow._screen_catalogue()` : libellés de navigation, ordre du `QStackedWidget` et propagation du projet en dérivent. Ajouter un écran, c'est une ligne et une fabrique : `EditorScreen("Sound Editor", self._make_sound_editor)`.

- **`ProjectScreen`** (`ui/screens.py`) est un `Protocol` : `load_project(project)`. Il est vérifié à la **construction** (`_ensure_screen`) ; un écran qui ne le remplit pas est monté quand même et le défaut est annoncé.
- **L'écran natif se construit à sa PREMIÈRE VISITE** (placeholder jusque-là) ; les plugins sont construits au démarrage. Un accès transversal à un écran non construit le saute.
- **Cycle de vie à deux temps** : première visite → `load_project` ; visites suivantes → `refresh()` (crochet OPTIONNEL, via `ui/screens.refresh_screen`) qui re-dérive les catalogues **depuis la mémoire**, jamais depuis le disque. **On n'abonne pas un écran empilé au bus pour se rafraîchir caché** : sa revisite s'en charge ; les `_d.on(…)` restants pilotent l'écran visible.
- **Un seul `BuildPanel`** (console, diagnostics, onglet Disk), hors de tout écran ; chaque écran est bâti sur `ThreeColumnBody` et lui prête un emplacement sous son centre. Ouvert/fermé est une donnée du catalogue (`EditorScreen.build_panel_open`).
- **Trois surfaces d'extension pour un plugin** : un composant (`COMPONENT_REGISTRY` + `@register`), une règle de build (`@register_validator`), un écran entier (`register_screen`). Les écrans de plugin passent après les natifs ; leurs appels sont entourés d'un `try` (du code tiers dans un slot Qt fait abandonner le process).
- **Le routage des assets** (`MainWindow._ASSET_ROUTES`) associe `assets/<dossier>/*.ext` aux fonctions d'`asset_reconciliation` (créer, supprimer, **renommer**). Le watcher **apparie** un renommage (disparition + apparition de même taille et même date, `project_watcher.pair_renames`) pour que l'asset suive son fichier. **Le nom de fichier fait foi** : `ResourceStore.load` adopte le stem quand `name` a dérivé.

---

## Textes et polices

- **Textes de l'éditeur** : deux catalogues frères sur un cœur commun (`ui/common/catalog.py`), `notice.py` (contenu informatif, avec ton et niveau 1/2/3) et `labels.py` (`label("clé")`, tout le reste). Le Python passe des VALEURS, jamais des morceaux de phrase ; le pluriel est déclaré ; une entrée absente vaut la SOURCE. `tools/check_architecture.py` vérifie que toute clé citée existe et que toute entrée est citée (un message vide ne se plaint jamais). Seul le niveau 3 a le droit d'expliquer, et l'interrupteur des astuces est un réglage d'APPLICATION, pas de projet.
- **Textes du joueur** (`assets/texts.json`, `core/models/text.py`), voir ci-dessous. Détail et balisage : [docs/development/texts-and-fonts.md](docs/development/texts-and-fonts.md).
- **Polices** : un `FontAsset` (recette de l'auteur) est matérialisé en `RasterGlyph` (couverture 0..255), encodé en tuiles 4bpp par `font_emit.py`. Deux chemins de rendu choisis par la donnée (`is_proportional()` / `render_composited()`) : *tilemap* (index posés, coût nul, plafonné à un charblock) ou *composition* (le moteur compose pixel par pixel). Le budget VRAM lit les mêmes glyphes que l'encodeur. **`scene_font_names` rend `None` pour « je ne sais pas », jamais « rien »**, et la réservation retombe alors sur le projet entier : réserver trop coûte des tuiles, réserver trop peu écrit le texte DANS le décor.

### Textes du joueur (table de chaînes)

Un fichier maître, un side `texts_<code>.json` par langue (partiel, joint par `id`). **Deux identifiants, un seul résolvable** : l'`id` est opaque (12 chiffres hexadécimaux), jamais affiché, utilisé dans les fichiers de données et insensible au renommage ; la `key` est la poignée lisible qu'écrit un script, résolue **au build** en index C (`TEXT_*`). **La clé situe, elle ne résume pas** (la place dans le jeu bouge rarement ; le contenu est réécrit vingt fois). **La clé porte la structure** : chaque `_` ouvre un niveau et `Text.path` en est la liste des segments (dérivée, jamais stockée) ; **ranger, c'est renommer la clé**, ce qui la change partout où elle est citée. `norm_path` est le seul point où un nom devient un chemin ; une collision prend `_2`, `_3` (`unique_name`). L'arbre de l'écran Textes est une **vue** : pas de nœud vide.

Des textes dont la clé finit par un segment numérique et qui partagent un préfixe forment une **séquence** (`core/text_sequences.py`, rien de stocké) : **liée** quand une `DataTable` ou un `UITextbox` la cite, **libre** sinon ; `CommandHistory.after_execute` réaligne les tables liées dans la MÊME entrée d'historique.

**Le balisage (BBCode, `core/text_markup.py`) est résolu au BUILD, aucun parseur en ROM** : `emit_texts_c` sort trois pistes (codepoints, événements de tempo/effets, sources à interpoler). Un `$nom` désignant une constante est cuit dans les codepoints, un global devient une place réservée (U+FFFF) + un pointeur vers la variable C, et ni l'un ni l'autre est écrit littéralement et signalé. La tête de lecture appartient à la ZONE, pas à l'appel ; `[color=n]` ne fonctionne que sur les chemins COMPOSÉS.

---

## Sauvegarde (variables persistantes en SRAM)

32 Kio, **accessibles octet par octet uniquement** (`sram_get32`/`sram_put32` décomposent en quatre accès), waitstates posés par `sram_init()` au début de `main()`. Ce qui est sauvé, ce sont les `GlobalVar` dont `persist` est vrai : le moteur ne connaît aucun autre état, reprendre une partie est un aiguillage que l'auteur écrit. Les enregistrements sont **rangés par id, pas par rang** (repli déterministe de l'id sur 32 bits ; une collision **bloque le build**), si bien qu'ajouter ou réordonner une variable laisse les sauvegardes lisibles. **Trois tests avant de croire un emplacement** (marque, version, somme) ; la somme est écrite en dernier, pour qu'une coupure laisse un emplacement illisible plutôt qu'une sauvegarde à moitié écrite. Les formats 2 et 3 restent lisibles et migrent au format 4 à la première écriture. `save:read(slot, "nom")` lit UNE variable sans toucher aux globales. La chaîne `SRAM_V113` n'est émise **que** s'il y a une variable persistante (pas de `.sav` vide chez le joueur). Détail : [docs/development/build-and-assets.md](docs/development/build-and-assets.md).

---

## Le modèle affine (rotation/scale monde × local)

Rotation et scale passent par une **matrice affine** OAM (`ATTR_AFFINE`), au prix d'un des 32 jeux de paramètres du matériel. Deux couples le demandent à la fois (le transform **monde** de l'actor et le transform **local** du sprite) pour une seule matrice par slot : le modèle les compose à la frame.

La décision vit sur le **sprite** (`SpriteComponent.affine_transform`, portée par `OamEntry.affine_slot`) : un sprite coché **réserve un des 32 slots au build, même à l'identité**. C'est une capacité de **RENDU**, pas de PLACEMENT, donc décidable sur un **template** (`Prefab.affine_transform` délègue au sprite de la racine et vaut pour tout le pool) ; le slot **appartient à la scène**, et `spawn_X()` doit préserver le slot et reposer les échelles neutres (256 = ×1).

| | Qui possède | API Lua | Runtime |
| --- | --- | --- | --- |
| **Monde** | l'`Actor` | `self.rotation`, `self.scale` | `g_actors[i].rotation`, `.scale_x/y` (Q8) |
| **Local** | le `SpriteComponent` | `self.sprite_offset`, `sprite_pivot`, `sprite_scale`, `sprite_rotation` | `g_oam_entries[i].offset_x/y`, `.pivot_x/y`, `.scale_x/y`, `.rotation` |

Le monde reste sur l'Actor parce que la rotation est un fait de son état de jeu ; le sprite décide si ce fait est **visible**. Le local est exprimé **dans le repère de l'actor** et composé chaque frame (`_affine_oam_lines_dynamic`) : rotation = somme, scale = produit (Q8), offset transformé par la matrice de l'ACTOR, position = actor + R·S·(offset + demi-cadre) : le cadre entier, centre compris, tourne et scale comme un corps rigide autour de la position de l'actor. Le **pivot** (pixels depuis le centre du cadre) dit AUTOUR DE QUOI le sprite se transforme, l'offset OÙ il est ; le matériel pivote toujours sur le centre, donc le centre de la boîte OAM se place à `P − M·pivot` (M = rotation·échelle·flip). `pa/pb/pc/pd` viennent de `SIN_LUT[91]` (Q8 : un quadrant, `gba_sin`/`gba_cos` déduisent les autres). Au cochage, l'éditeur centre l'actor sur le cadre (`center_on_frame`) sans écraser un réglage de l'auteur.

**Le stockage est PAR-ACTOR, pas par slot** : un script de prefab poolé est une fonction C partagée (les valeurs partent du `g_actors[i]` de l'instance), et un `static` dans un header multi-inclus serait une copie PAR unité de compilation (les écritures d'un script `actor_*.c` n'atteindraient jamais `main.c`). Les accesseurs ne sont **pas gardés par le slot** ; seule l'écriture de la matrice OAM le demande, et le checker avertit (`warning`) d'un `self.rotation` sans « Affine transform ».

---

## État des prefabs poolés et séquences

Les variables de tête d'un script de prefab poolé vivent dans un état **dimensionné par le pool** (`CodeGen._emit_pool_state`) : `g_state_<Sym>[POOL_<SYM>_INSTANCES]`, un `_st` résolu une fois par fonction. `POOL_*_START/_SIZE/_GROUP/_INSTANCES` sont émises par `headers.py` ; un prefab **segmenté** occupe un groupe d'entrées mais n'exécute qu'un script (`_SIZE` compte les entrées, `_INSTANCES` les scripts). Seul ce que le script ÉCRIT est de l'état (`assigned_names()`). Le build dit ce que ça coûte (`[ewram] prefab X : …`), sans plafond bloquant.

Une `function on_sequence_*()` est découpée à chaque attente et réémise en machine à états (`switch` sur un entier : 0 arrêtée, 1..N l'étape). C'est la seule transformation qui change la FORME du code. Pas de boucle autour du `switch` (une tranche par frame), donc une attente ne s'écrit qu'au PREMIER NIVEAU ; ce qui traverse une attente est hissé dans l'état ; le pompage vit à la fin de `on_update`. Détail : [docs/development/scripting-internals.md](docs/development/scripting-internals.md).

---

## Ressources matérielles (l'auteur ne les nomme jamais)

Cet éditeur représente **des objets qui devront être matérialisés simultanément sur une machine minuscule** : chaque fonctionnalité marche, jusqu'au jour où deux d'entre elles servent en même temps. **Aucun concept de haut niveau ne nomme une ressource matérielle.** Une caméra ne demande pas WIN0, elle demande *une région qui limite son rendu*. Trois niveaux, à ne jamais confondre : l'**intention** (`RenderRegion`, `ClipRegion`, ce que l'auteur manipule), la **ressource logique** (un masque : géométrie + calques + règles, ce que l'allocateur manipule), la **ressource matérielle** (`WINR_0`, un charblock, une entrée OAM, que le backend seul voit). Deux intentions qui décrivent le même masque logique ne consomment qu'une ressource matérielle.

### Deux allocateurs, pas un (la durée de vie décide)

Ils partagent un vocabulaire, jamais une implémentation. Résolu au **BUILD** (palettes, VRAM/charblocks, tuiles de police, windows) : Python, `codegen/`, coût élevé admis, **peut prévenir l'auteur**. Résolu à la **FRAME** (entrées OAM dynamiques, canaux DMA, matrices affines) : C, dans le runtime, coût quasi nul, personne à qui parler. Les trois allocateurs de build existants (`palette_alloc.py`, `vram_alloc.py`, `window_alloc.py`) arbitrent et replient quand ça ne tient pas. Pour les windows, sans repli sûr, le build échoue. **Ne sont allouables par personne** : le temps CPU (qu'on mesure) et l'IWRAM (édition de liens). `g_actors[]` est en **EWRAM** (`EWRAM_DATA`) : règle du codegen, pas option de projet.

### Le piège propre aux windows : les slots ne sont pas interchangeables

`WINR_0` > `WINR_1` > `WINR_OBJ` > `WINR_OUT` est une priorité **câblée** : deux rectangles qui se recouvrent ne rendent pas la même image selon leur slot. Traiter WIN0 et WIN1 comme équivalents produirait une allocation *valide* et une image *fausse*. La ressource est **« une fenêtre à un rang donné »**, et `window_alloc.py` ne laisse pas le rang à l'auteur : l'intention caméra prend TOUJOURS `WINR_0`. `WINR_OUT` est le complément, personne ne peut le demander.

---

## Allocation de la VRAM BG (`codegen/vram_alloc.py`)

Les 64 Ko portent DEUX choses qui se recouvrent : les tuiles (quatre charblocks de 16 Ko) et les cartes (trente-deux screenblocks de 2 Ko). L'allocateur remplace la convention « le charblock d'un layer est son index, sa carte va à la fin », **par scène**.

- **Tout se raisonne en blocs de 2 Ko** (1 screenblock = 64 tuiles 4bpp), seule unité qui voit tuiles et cartes.
- **L'asymétrie qui dicte tout** : un fond est *rigide* (champ CharBlock de 2 bits, tuiles numérotées depuis 0 : collé à la base d'un charblock) ; le texte est *souple* (c'est nous qui écrivons ses entrées de carte). **C'est le texte qu'on glisse dans les trous, jamais le fond.** Posé pile à la base d'un charblock, le texte est décalé d'une tuile : s'il remplit ses blocs, il lui en faut un de plus.
- **Les cartes sortent du chemin de croissance** (sinon la carte d'un layer mure sa propre croissance contiguë).
- **Portée 10 bits** : un layer voit 1024 tuiles depuis la base de son charblock ; en CBB3, la VRAM des sprites commence après, donc 512 au plus.
- **Garde-fou** : le placement calculé n'est retenu que s'il donne à CHAQUE layer au moins ce que donnait le placement historique, sinon repli complet. Le budget est vérifié au build en **erreur bloquante** (de la mémoire écrasée, pas une mauvaise couleur). Les modes bitmap restent hors périmètre ; le pendant OBJ (128 slots, 1024 tuiles) est arbitré dans `main_gen`.

---

## Système de palette & compression d'assets

Un **catalogue de palettes nommées** (`PaletteBank`, `assets/palettes/*`, un fichier par palette, index 0 toujours transparent) est activé **par scène** : seule la sélection (`Scene.active_*_palettes`, jusqu'à 16 par pool) occupe les banques `PAL_OBJ_RAM` / `PAL_BG_RAM`. `pal_bank` sur un `Actor` / `Prefab` / `BackgroundLayer` est un slot `0-15` de cette sélection ou `OWN_PAL_BANK` (-1) = la palette de l'asset. Les PNG sources ne sont **jamais réécrits** : couleurs et tuilerie vivent dans des sidecars recalculés au build.

**Allocation des banques, source de vérité unique** : `codegen/palette_alloc.py::scene_bank_layout(project, scene, pool)` place les palettes référencées à leur slot fixe, puis les fonds compressés en un bloc de banques contiguës. Déterministe : `rom_build.py` (quantification grit) et `main_gen.py` (`PAL_*_RAM`) lisent le même layout sans se coordonner. Un débordement (> 16 banques) n'est jamais silencieux (`bank_index` retombe sur 0 et le validateur avertit).

- **Sprites** : chaque `SpriteAsset` garde sa **palette propre** (`own_palette`) et est quantifié au build vers sa palette effective.
- **Fonds** : `core/bg_import.py` produit un `BackgroundAsset` (tuilerie 8×8 dédupliquée, jusqu'à 16 sous-palettes), émis **directement** en C par `codegen/bg_emit.py` (pas par grit). Trois modes auto-détectés à l'import (`detect_import_mode`) : tuilé 4bpp, tuilé 8bpp (toute la `PAL_BG_RAM`, un seul layer), bitmap Mode 4 (éditable, **pas encore émis au build**). **Le sidecar a deux blocs** : `settings` (ce que l'auteur a décidé) et `encoded` (ce que l'encodage en a tiré, que le build lit et qu'un nouvel encodage remplace en entier) ; `encoded.encoded_for` est l'empreinte des réglages qui déterminent l'encodage, et le build avertit d'un fond périmé. Les palettes d'un fond sont des **références au catalogue, par nom** ; le PNG n'est jamais modifié, la préparation (canvas, miroir) s'applique en mémoire par `bg_import.prepare_source`.
- **Inpainting** : réassigner la banque d'une tuile sans toucher aux pixels (`tile_palette_overrides`), à deux niveaux, sur l'asset (partagé par toutes les scènes) ou sur le `BackgroundLayer` (propre à la scène, qui est alors source de vérité et produit sa propre map).
- **Garde-fous** : conflit inter-scènes (même sprite résolu vers des palettes différentes : avertissement), débordement de banques (avertissement), budget de tuiles VRAM d'un layer (**erreur bloquante**).

---

## Pipeline de build (ROM)

Orchestré par `editor/codegen/rom_build.py` (`BuildWorker`), déclenché depuis `ui/common/build_panel.py` : ① validation → ② fonds (compressés par `bg_emit`, legacy par grit) → ③ sprites (quantifiés vers leur palette effective, grit) → ④ audio optionnel (mmutil + bin2s) → ⑤ headers C → ⑥ transpilation Lua → C, toutes les scènes en une passe → ⑦ `main.c` → ⑧ compilation et link (`arm-none-eabi-gcc` via `make`) → ⑨ lancement dans mGBA. Les conversions grit/mmutil sont mises en cache par empreinte (PNG, sidecar, palette effective, outil, et le code de conversion lui-même : `asset_cache.pipeline_signature`).

### Le journal de build (un diagnostic, un fichier)

Tout ce que le build reproche au projet est un `ValidationMessage` (`core/diagnostic.py`) : `level`, `source` (validator, script, checker, codegen, ou l'outil), `file`, `line`, `actor`, et une cible cliquable. `BuildWorker` n'émet que `log_line`, `diagnostic`, `error_line`, `progress`/`finished` ; son `_emit` est le seul point de passage, il compte les diagnostics et copie chaque ligne dans **`<projet>/build/build.log`**. Le stderr d'un outil est rangé par ce qu'il dit (gcc `fichier:ligne: error` devient un diagnostic) ; le code de retour est seul juge de l'échec. **gcc cite le script, pas le `.c`** (directives `#line`). **Aucune erreur n'est avalée** : un `except` large de `codegen/`, `scripting/` ou `core/validator.py` lève, émet, ou porte `# tolerated: <raison>` (gardé par `tests/test_silent_except.py`). Le validateur contrôle toutes les scènes (`_check_each_scene`).

---

## Packaging, environnement de dev et dépendances

Nuitka (mode standalone) + NSIS + GitHub Releases, `app_paths.py` / `app_info.py` comme sources uniques (où tourne-t-on, quelle version), smoke test sur le binaire livré, venv de dev figé sur Python 3.12 (celui de la CI) : tout est dans [docs/development/packaging.md](docs/development/packaging.md). mGBA et devkitPro ne sont **jamais embarqués** : dépendances système détectées à l'exécution par `core/toolchain.py`.
