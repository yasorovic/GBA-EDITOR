# L'ouverture d'un projet, et l'écran blanc — **LIVRÉ**

> **Ouvert et livré le 2026-09-13.** Chantier technique : suite directe de **L'écran construit à sa
> première visite** (même jour) et du **chargement paresseux** (v0.24). Rien ne change pour qui joue
> au jeu produit — seulement le temps et le ressenti d'ouverture de l'éditeur. Ni README ni CHANGELOG,
> pas de numéro `vX.Y`.
>
> **Résultat mesuré** (réel, fenêtre à l'écran, projet `MyGame`, venv de CI) : l'écran **blanc et figé
> au démarrage est éliminé** — le premier `show()` passe de **~5,3 s à ~0,57 s**. En amont,
> `MainWindow()` **7,6 → 3,5 s** (inspecteur paresseux) et la construction des polices **4,7 → 1,7 s**
> (cache + vectorisation + mémoïsation). **Total ~16 s → ~6,5 s.** Sortie de rasterisation
> **octet-pour-octet identique** (vérifiée : 1568 glyphes PNG réels + 10 bitmaps synthétiques pour
> `_coverage`, 0 écart) ; tests polices/palette au vert.

## D'où vient la question (2026-09-13)

Ressenti signalé : « l'écran se construit, mais s'affiche tout blanc avant de se construire vraiment ».
La mesure a contredit trois intuitions successives avant de trouver la racine — chaque hypothèse a été
profilée, jamais supposée.

`Project.load()` ne coûte que ~70 ms : **l'I/O du projet n'y est pour rien**. En instrumentant le vrai
flux de démarrage (headed, pas `offscreen` qui sous-estime ×3), le blanc s'est révélé être le
**premier `show()`**, qui bloque le thread UI pendant que la fenêtre native, déjà créée (fond blanc),
attend son premier dessin.

| Étape (avant) | Coût | Fenêtre |
| --- | --- | --- |
| `import window` | ~0,9 s | pas encore là |
| `MainWindow()` | ~7,6 s | pas encore là |
| `_open_project` | ~1,4 s | cachée |
| **`win.show()`** | **~5,3 s** | **blanche, figée** |

Ni la feuille QSS globale (mesurée : identique avec/sans), ni le canvas (`paints=1, 0 ms`), ni les
inspecteurs différés (un `QStackedWidget` ne peint que sa page visible) n'expliquaient le blanc. En
retirant le `SceneEditor` du splitter, `show()` tombait de 5148 ms à 482 ms : le coupable était **un
item peint**. Le profilage par item l'a nommé : **`UIRegionItem.paint` — 4763 ms** pour 5 régions de
texte, sur une scène de… 24 items.

La chaîne, jusqu'à la racine (chaque maillon profilé, pas déduit) :

```
GBAView premier paint (4,5 s)
 └─ UIRegionItem.paint ×5 régions de texte
     └─ _bank_colors  (cache d'item FROID au premier paint)
         └─ scene_bank_layout(p, scene, "bg")   ~730 ms ×6
             └─ _scene_font_palettes(p, scene)
                 └─ encodable_project_fonts → project_build_fonts
                     = UNE rasterisation de la police ROM entière (1425 glyphes,
                       dont 1112 japonais) ≈ 4,16 s, déclenchée par l'aperçu.
```

L'aperçu des boîtes de texte du canvas résolvait les couleurs de banque, ce qui tirait la
**construction de la police ROM complète** — au premier paint, région par région, sans partage.

## Décisions verrouillées

- **Ouvrir le projet AVANT `show()`.** `main.py` construit et peuple la fenêtre **cachée** (sous
  curseur d'attente), puis l'affiche déjà dessinée — au lieu d'exposer un éditeur vide (panneaux
  blancs) puis figé le temps du chargement. L'ancien `show()` + `processEvents()` + `singleShot`
  décalait le gel d'un tour d'événement sans le supprimer : le blanc, c'est le **premier paint
  lui-même**, qui a forcément lieu à `show()`. On ne montre donc la fenêtre qu'une fois prête.

- **L'inspecteur se construit à sa PREMIÈRE VENUE** (même schéma que « L'écran construit à sa première
  visite », un cran plus bas). `DynamicInspector` montait ses **9 sous-inspecteurs d'un coup** dans un
  `QStackedWidget` alors qu'un seul est visible. Il ne pose plus qu'un **placeholder par mode**
  (index == mode) ; une **fabrique** (`_make_scene`, `_make_actor`…) construit le vrai inspecteur — et
  branche ses signaux une fois — à la première venue de son mode, via `_ensure(mode)`. Corrige au
  passage un bug latent : `show_scene` empilait une connexion `changed` à chaque appel ; elle est
  désormais branchée une fois dans la fabrique.

- **La résolution d'allocation de palette est mémoïsée POUR L'APERÇU, jamais pour le build.**
  `codegen/palette_alloc.scene_bank_layout` est partagé avec l'émission ROM : un cache global y
  risquerait un résultat périmé dans une compilation. Le cache est donc **à portée de contexte**
  (`scene_layout_cache()`), **éteint par défaut** — le build recalcule toujours. Le canvas l'ouvre le
  seul temps de **pré-chauffer** les couleurs de banque des régions à la (re)construction des items
  (`GBAScene.set_ui_regions`, hors écran, pendant `_open_project`) : plusieurs régions partagent alors
  UNE allocation, et le premier paint visible lit des caches d'item chauds.

- **La rasterisation ne recharge plus un fichier par glyphe.** `core/font_rasterizer.py` créait une
  `freetype.Face` (chemin vectoriel) et rouvrait la planche `Image.open` (chemin PNG) **à chaque
  glyphe** — et `project.asset_abs()` (un `.resolve()`, appel filesystem) était rappelé à chaque
  caractère. Une **table de passe** `faces`, locale à `build_font_asset` (aucun état de module, rien
  entre threads), charge chaque source **une fois** : face, planche PNG **et** chemin résolu.

- **L'extraction de couverture est vectorisée (numpy).** La boucle pixel-par-pixel Python (chemins PNG
  et `_coverage` FreeType) devient quelques opérations sur tableaux. Gain modeste ici (glyphes ~16 px)
  mais **sortie strictement identique**, vérifiée octet-pour-octet.

## La mesure, poste par poste

| Levier | Effet mesuré |
| --- | --- |
| Ouvrir avant `show()` + inspecteur paresseux | `MainWindow()` 7,6 → 3,5 s |
| `scene_layout_cache()` + pré-chauffage hors écran | **`show()` 5,3 → 0,57 s (blanc éliminé)** |
| Cache faces/planches par passe (1 chargement/police) | font build 4,7 → 3,1 s |
| Mémoïsation `asset_abs` (`.resolve()` par source, pas par glyphe) | font build 3,3 → 1,7 s |
| Vectorisation numpy de la couverture | ~0 ici (mais correcte, utile aux gros glyphes / au gris) |

## Ce qui a été écarté, et pourquoi

- **Mémoïser `scene_bank_layout` globalement** : partagé avec le build → risque de ROM incorrecte
  après une édition. Refusé au profit du cache à portée de contexte.
- **Toucher aux ~2,4 s restantes de `MainWindow()`** : profilées jusqu'à un `setFont(Inter)` unique
  (~1,65 s) — le **warmup du moteur de police Qt**, payé une fois par le premier widget qui utilise
  Inter, pas par notre code. Déjà **hors du chemin visible** (fenêtre cachée). Le déplacer ne réduit
  pas le total ; le supprimer demanderait de changer la police de toute l'app (Inter est un choix de
  design assumé). Laissé tel quel — piste « police native/libre » notée pour plus tard.

## Ce que ça touche

- `editor/main.py` — ouverture avant `show()`, curseur d'attente.
- `editor/ui/scene_manager/inspectors/dynamic_inspector.py` — placeholders + fabriques + `_ensure` ;
  `editor/window.py` — deux accès rendus tolérants au non-construit.
- `editor/codegen/palette_alloc.py` — `scene_layout_cache()` ; `editor/ui/scene_manager/canvas/canvas_scene.py`
  — pré-chauffage dans `set_ui_regions`.
- `editor/core/font_rasterizer.py` — table de passe `faces` (face/planche/chemin), vectorisation ;
  `editor/codegen/font_build.py` — création de la table ; `tests/text/test_font_build.py` — signature du stub.

## Un incident, pour mémoire

Une commande `git checkout -- editor/core/project.py` lancée pour retirer une sonde de mesure a écrasé
une refonte non commitée de ce fichier (déplacement de `asset_encoding`/`resource_store`/`palette_store`
vers `core/resources/`). Récupérée depuis une copie de l'auteur. Règle renforcée : **jamais de commande
git en écriture** (y compris `checkout`/`restore`) pour défaire ses propres éditions — on les défait à
l'outil d'édition.
