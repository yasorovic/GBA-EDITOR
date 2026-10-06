# L'écran resynchronisé à sa revisite — voir les catalogues à jour en revenant sur un écran — **LIVRÉ**

> **Livré le 2026-09-20.** Contrat d'écran en deux temps : `load_project` à la première
> visite, `refresh()` (crochet optionnel, appelé au centre par `Window._show_screen`) aux
> visites suivantes. Les colmatages `showEvent → refresh` par écran et l'abonnement eager
> `palettes_changed → Palette editor` sont retirés. Cinq étapes livrées (contrat, point central,
> écrans, tests, doc). Tests : `tests/ui/test_screen_revisit_refresh.py` + les trois
> `test_*_screen_resync.py` repointés. Doc : `ARCHITECTURE.md`, « Ce qui reste à la charge de la
> fenêtre ».

Le pendant de [« L'écran construit à sa première visite »](lazy-screen-build.md) :
celui-là a rendu la construction paresseuse ; celui-ci s'occupe de ce qui se passe aux visites
SUIVANTES, quand l'écran existe déjà mais que le projet a bougé sous lui.

### D'où vient la question (2026-09-18)

Née en marge d'une session de debug du copier/coller de zones de texte. Symptôme rapporté par
l'auteur : l'éditeur de texte affichait « 1 of 8 shown » — huit textes dans le projet, un seul dans
la table. Cause : une zone de texte créée dans le Scene Manager ajoute son entrée à `project.texts`
([ui_inspector.py:1071](editor/ui/scene_manager/inspectors/ui_inspector.py:1071)), mais
`Window._load_screen_for_project` ([window.py:901](editor/window.py:901)) ne charge un écran qu'à
sa **première** visite (le garde `_project_loaded_screen_indices`). Revenir sur l'écran Texte ne le
rechargeait donc pas : sa table restait figée sur son ancien contenu, alors que le pied de page
lisait le total à jour du projet — d'où le « 1 of 8 ».

L'audit des huit écrans a montré que le trou n'est pas propre au texte. Le seul rafraîchissement
cross-écran câblé aujourd'hui vise les panneaux du **Scene Manager** (`project_tree_changed`,
`actors_list_changed`, … → `assets_finder_panel.refresh` / `scene_tree_panel.refresh`,
[window.py:654](editor/window.py:654)) et l'**écran Palettes** (`palettes_changed` → `refresh`,
[window.py:688](editor/window.py:688)). Tout autre écran qui affiche un catalogue écrit ailleurs se
périme à sa première visite passée :

- **Scripts** (le plus grave) — la sidebar RÉFÉRENCES et surtout l'**autocomplétion** capturent
  sprites, fonds, sons, globals, polices, constantes via `names_by_domain`
  ([project_names.py:31](editor/scripting/project_names.py:31)) au `load_project`. Un nom né ensuite
  ailleurs manquait **en silence** — aucune erreur, juste une complétion incomplète.
- **Backgrounds / Animations** — la grille « + du catalogue » lit `project.palettes` à l'ouverture.
  Une palette ajoutée/renommée/retirée dans l'écran Palettes n'y apparaissait pas.
- **Datas** — *pas* de bug : les listes de choix des colonnes de référence sont dérivées **en
  direct** à l'ouverture du menu déroulant (`data_column_choices` →
  [project.py:422](editor/core/project.py:422)), depuis les listes partagées du projet.
- **Sounds** — rien d'externe n'écrit l'audio ; sans objet.

### Ce qui a déjà été colmaté (2026-09-18), à consolider ici

Chaque écran touché a reçu, séparément, un `showEvent → refresh` bon marché (relire des noms/banques
déjà en mémoire, pas de re-décodage d'asset). Ce sont ces colmatages ponctuels que le chantier doit
remplacer par un mécanisme unique :

- Texte — `TextEditorScreen.showEvent` → `refresh()`
  ([text_editor_screen.py:183](editor/ui/text_editor/text_editor_screen.py:183)).
- Scripts — `ScriptEditorScreen.showEvent` → `_refresh_catalogs()`
  ([script_editor.py:245](editor/ui/script_editor/script_editor.py:245)).
- Backgrounds / Animations — `showEvent` → `refresh_palette_catalog()` du panneau
  ([background_editor_screen.py:1221](editor/ui/background_editor/background_editor_screen.py:1221),
  [sprite_editor_screen.py:74](editor/ui/sprite_editor/sprite_editor_screen.py:74)).
- Tests de non-régression : `tests/ui/test_text_editor_screen_resync.py`,
  `test_script_editor_screen_resync.py`, `test_asset_editor_palette_resync.py`.

Ces correctifs FONCTIONNENT mais traitent des cas, pas la cause : chaque nouvel écrivain cross-écran
rouvre le trou en silence, et rien ne force un écran neuf à se doter de son `showEvent`.

### L'esquisse

Faire du rafraîchissement un point du contrat `ProjectScreen`, appelé **au centre**, plutôt qu'un
`showEvent` réécrit dans chaque écran :

1. **`ProjectScreen.refresh()` (ou `on_reveal()`) devient contractuel** — chaque écran expose une
   méthode de re-dérivation idempotente et bon marché : relire les catalogues DÉJÀ en mémoire, sans
   toucher au disque ni re-décoder d'asset, en conservant sélection et état d'édition. Les écrans
   déjà pourvus (`refresh` existe sur Texte, Datas) n'ont qu'à s'y conformer.
2. **`Window._show_screen` l'appelle** juste après `setCurrentIndex`, si l'écran est construit ET
   déjà chargé pour ce projet — l'exact symétrique du garde `_load_screen_for_project`. Plus de
   `showEvent` par écran, plus d'oubli possible : un écran qui n'implémente pas `refresh` ne
   rafraîchit rien, mais le contrat le rend visible à la revue.

### Décisions verrouillées (2026-09-20)

Les deux inconnues laissées ouvertes ont été tranchées par lecture du code, pas par supposition.

- **Le rafraîchissement est un point central de `_show_screen`, jamais un `showEvent` par écran.**
  Vérifié : le stack ne connaît que **deux** `setCurrentIndex` — le démarrage (index 0, avant
  projet) et `_show_screen` ([window.py:910](editor/window.py:910)). Un écran déjà construit ne
  redevient donc visible **que** par `_show_screen` ; une restauration de fenêtre ne change pas
  l'écran courant, donc rien n'a bougé sous lui. L'inconnue « un écran réapparaît sans passer par
  `_show_screen` » est levée : ça n'arrive pas. Et le `showEvent` qui lève une exception **abort**
  le process (exit 139, rencontré aux colmatages) — argument décisif de plus pour le chemin Python.
- **`refresh()` est appelé après `setCurrentIndex`, gardé par `index in _project_loaded_screen_indices`.**
  Le symétrique exact de `_load_screen_for_project` : **première** visite → `load_project` (déjà en
  place) ; visite **suivante** → `refresh()`. Un écran qui n'implémente pas `refresh` ne rafraîchit
  rien, mais le manque est visible à la revue (pas un `abort` silencieux).
- **Pas d'abonnement au bus pour un écran EMPILÉ.** Le bus est vidé à chaque changement d'écran
  ([window.py:912](editor/window.py:912)) : la synchro live inter-écrans n'est pas le modèle. Un
  écran caché n'a pas à suivre l'état ; il re-dérive à la revisite. L'inconnue « écran composite qui
  doit suivre le bus en direct » est levée pour le périmètre stacké : **la synchro live intra-écran
  reste le câblage propre de l'écran, hors de ce contrat.**
- **Les abonnements `_d.on(...)` du Scene Manager restent tels quels.** Ils pilotent l'écran 0
  **visible** en réponse directe aux événements moteur (`actors_list_changed`, `project_tree_changed`,
  `palettes_changed`, `_refresh_graph_if_visible`…) : ce n'est pas de la synchro « écran caché », c'est
  la mise à jour de l'écran actif. Le contrat de revisite ne les touche pas.
- **`refresh()` est idempotent et bon marché** — re-dérive les catalogues DÉJÀ en mémoire, sans
  toucher au disque, sans re-décoder d'asset, sans raster, en conservant sélection et état d'édition.
  Même exigence que le [cache de scène](../../ROADMAP.md#le-cache-de-scène-rouvrir-une-scène-déjà-visitée-sans-tout-redécoder) (chantier encore ouvert).
- **`refresh()` est le crochet OPTIONNEL de revisite, à côté du contrat obligatoire.** Il n'entre
  PAS dans le `Protocol` `ProjectScreen` (qui garde `load_project` seul) : l'y déclarer ferait échouer
  le contrôle `isinstance` de `_ensure_screen` pour tout écran ne l'implémentant pas. Il vit donc dans
  `editor/ui/screens.py` sous forme d'un helper `refresh_screen(widget)` qui appelle `widget.refresh()`
  s'il existe, sinon ne fait rien — le « défaut no-op » centralisé en un seul point. Un écran sans
  `refresh` est visible à la revue (le contrat le nomme), sans erreur runtime.
- **Les colmatages `showEvent → refresh` ponctuels sont RETIRÉS** une fois le chemin central en place
  (Texte, Scripts, Backgrounds, Animations) — l'ancien supprimé avant de dire terminé. Les tests de
  resync existants doivent rester verts via le nouveau chemin.
- **L'abonnement `palettes_changed → Palette editor` est RETIRÉ aussi** (rustine de la même famille) :
  `save_palette` n'est émis que par le Sprite et le Background Editor, donc toujours quand l'écran
  Palettes est caché — sa revisite le rafraîchit au retour, rafraîchir un écran invisible ne servait
  à rien. À NE PAS confondre avec les abonnements `_d.on(...)` du Scene Manager, qui pilotent l'écran
  VISIBLE et restent tels quels. Les invalidations paresseuses (`invalidate_script_usages`,
  `flush_script_edits`) restent aussi : elles marquent un cache périmé, ce n'est pas un refresh eager.

### Ordre d'implémentation

1. **Le contrat.** ✅ **Fait.** Documenter `refresh` comme crochet optionnel de revisite dans
   `ProjectScreen` (`editor/ui/screens.py`) et fournir le helper `refresh_screen(widget)` (no-op si
   absent). `load_project` reste le seul membre du `Protocol` vérifié par `isinstance`.
2. **Le point central.** ✅ **Fait.** `_show_screen` capture la revisite AVANT
   `_load_screen_for_project` (qui ajoute l'index à la première visite), puis, après
   `setCurrentIndex`, appelle `_refresh_screen_for_project(index)` uniquement en revisite. Cette
   méthode (symétrique de `_load_screen_for_project`) appelle `refresh_screen(widget)`, entourée pour
   un écran de plugin.
3. **Les écrans.** ✅ **Fait.** `refresh()` public et idempotent (re-dérivation mémoire) sur Texte
   (existait déjà), Scripts (`_refresh_catalogs`), Backgrounds et Animations
   (`refresh_palette_catalog`) ; les `showEvent` ponctuels **retirés**. ⚠️ Les trois tests de resync
   pilotent encore `showEvent` directement → rouges jusqu'à leur repointage vers le chemin central
   (étape 4).
4. **Les tests.** ✅ **Fait.** Les trois tests de resync repointés sur `refresh()` (chemin central) au
   lieu de `showEvent`, verts. Nouveau `tests/ui/test_screen_revisit_refresh.py` : pilote les vraies
   méthodes de `MainWindow` sur un stub léger (pas de widget Qt) et verrouille « refresh à la 2ᵉ
   visite, pas à la 1ʳᵉ » + « pas de refresh sans projet ». 6/6 verts.
5. **La doc.** ✅ **Fait.** Contrat d'écran en deux temps (`load_project` première visite / `refresh`
   revisites) consigné dans `ARCHITECTURE.md`, section « Ce qui reste à la charge de la fenêtre »,
   avec le corollaire « pas d'abonnement bus pour rafraîchir un écran caché ».

### Recouvrement

- Avec [« L'écran construit à sa première visite »](lazy-screen-build.md) : ce
  chantier est le garde que celui-ci contourne ; il en est la moitié « visites suivantes ».
- Avec [Le cache de scène](../../ROADMAP.md#le-cache-de-scène-rouvrir-une-scène-déjà-visitée-sans-tout-redécoder) (chantier encore ouvert) :
  même famille de questions (que refait-on en revenant sur une vue), et même exigence que le
  `refresh` ne paie pas le décodage.
