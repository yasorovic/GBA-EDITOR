# Finder et Disk, devenus des *libraries* — **LIVRÉ**

> **Chantier technique** : renommage et rangement, rien de visible pour qui joue au jeu produit. Il n'a donc ni numéro,
> ni ligne au [README](../../README.md), ni entrée au [CHANGELOG](../CHANGELOG.md) (cf. les
> [chantiers techniques](../../docs/development/TODO.md#état-des-pistes)). Il compte dans le chantier important 0.3 (assets et disque).

> **Livré le 2026-10-22.** Les finders sont des *asset libraries* dans le code, la Scene library ne montre que scènes et prefabs,
> `Project.user_library_dir` remplace `assets_dir`, et « View uses » d'un script vit dans le Script Editor.

### D'où vient la question (2026-10-14)

Deux mots prêtent à confusion. **« Asset finder »** désigne à la fois la famille de panneaux (Project viewer, Sprite
finder, Script finder, Sound finder…) et le mécanisme commun (`AssetFinder`) ; **« Assets »** désigne à la fois ce que le
projet *contient* (les assets nommés) et le dossier de l'auteur (`assets/`, racine de l'onglet Disk). Le chantier
« Tout ce que l'auteur manipule vit dans `assets/` » a encore élargi ce second sens : le dossier contient désormais des
scènes, des tables, des textes, qui ne sont pas des « assets » au sens d'un sprite ou d'un fond. Renommer lève
l'ambiguïté et rend le code plus clair à maintenir.

### Décisions verrouillées (2026-10-14)

- **L'« asset finder » devient l'« asset library »** : le nom change partout où il vit, le vocabulaire visible
  (libellés, infobulles), les classes et modules (`AssetFinder`, `asset_finder.py`, `*_finder_panel.py`), les tests, la
  doc (`editor/ui/asset-finder.md`, ARCHITECTURE). Aucun alias de l'ancien nom : une fois le renommage fait, plus un
  « finder » ne reste.
- **Le dossier de l'auteur devient « Project files »** : c'est le nom que l'auteur voit pour ce qu'il organise lui-même
  (racine de l'onglet Disk, aujourd'hui « Assets »).
- **Sprite, Script et Sound rejoignent le modèle de l'asset library** : ils cessent d'être des « finders » à part. Il n'y a
  plus qu'un seul modèle (l'asset library) dont ils sont des vues par type d'asset, au lieu de quatre panneaux qui
  portent chacun leur nom (« Sprite finder »…). Les `*_finder_panel.py` disparaissent comme noms de famille.
- **Le « Project viewer » (un temps nommé « Scene viewer ») est la « Scene library »** : à l'usage c'est la bibliothèque
  de la scène. L'auteur y ouvre une scène, y prend un prefab. Ce n'est pas une vue du projet entier (« Project files »
  prend ce rôle) mais une **instance du même modèle d'asset library**, comme les trois autres, avec trois filtres :
  **scene / prefab / script**. Le filtre **script** pourrait même être retiré (à trancher, point 2) : le Script
  finder a déjà sa propre bibliothèque.

### Décisions du 2026-10-22 (elles remplacent les noms de la section précédente)

- **Pour l'auteur, rien ne change : l'onglet s'appelle « Disk » et son dossier `assets/`** (« Project files » est
  abandonné). **`user_library` est un nom interne** : partout où le code désigne le dossier physique de l'auteur,
  il emploie ce nom (classes, variables, modules, commentaires), jamais dans l'interface. Le dossier sur disque
  reste `assets/` : aucun renommage de chemin, donc ni migration ni touche à la surveillance.
- **Les finders deviennent des *assets library* dans le code** (classes, modules, tests, doc ; aucun alias de
  l'ancien nom).
- **Le « Project viewer » devient la *Scene library*, avec deux filtres seulement : scènes et prefabs.** Le filtre
  script est retiré : le Script finder a sa propre bibliothèque.
- Réponses aux points 1 et 2 ci-dessous. Le point 3 est tranché (voir plus bas) ; le point 4 (clés de traduction et raccourcis
  suivent) reste à confirmer.

### Livré le 2026-10-22

- **finder devient library, partout** (code, tests, libellés, docs ; aucun alias) : `AssetLibrary`
  (`ui/common/asset_library.py`), `library_fold_state.py`, `SpriteLibraryPanel`, `ScriptLibraryPanel`, `TextLibrary`,
  `SceneLibraryPanel` (`ui/scene_manager/scene_library_panel.py`, ancien `AssetsFinderPanel`). Les préfixes de clés de
  libellés suivent : `assetlibrary.*`, `scenelibrary.*`, `spritelibrary.*`, `scriptlibrary.*`. Doc : `editor/ui/asset-library.md`.
- **La Scene library ne montre plus que scènes et prefabs.** « View uses » d'un script, qui n'existait que là, passe
  dans la Script library (clic droit sur un script) : la colonne droite du Script Editor affiche alors
  `ScriptUsesPanel` (`ui/script_editor/script_uses_panel.py`, base commune `ui/common/uses_list.py`) ; un clic sur une
  ligne ouvre le Scene Manager et y sélectionne l'acteur, le prefab ou la scène (`window._show_script_user`), « v »
  revient à la bibliothèque. Le mode « utilisations de script » de `DynamicInspector` est retiré. « Edit script » est
  abandonné : un clic simple ouvre déjà le script.
- **`Project.user_library_dir`** remplace `assets_dir` (≈ 420 usages, 69 fichiers). Le chemin sur disque, `assets/`, ne bouge pas.
- Tests ciblés verts (les sept fichiers renommés, duplication, dossiers virtuels, gestes vierges, import de source).
- **Clés EN et FR relues (2026-10-22)** : les 26 clés des bibliothèques qui n'avaient pas de FR l'ont maintenant (noms des
  bibliothèques, confirmations de suppression, états et directions d'animation) ; aucun raccourci ne portait l'ancien nom.
  Contrôles de libellés et tests `i18n` verts. 

### À trancher avant de commencer

1. **« Project files » : nom affiché seulement, ou aussi nom du dossier sur disque ?** Le renommage sur disque
   (`assets/` → `project_files/`, ou autre) touche `core/project_paths.py`, la surveillance, les starters, les deux démos,
   la migration et une quinzaine de tests, comme le chantier `project/` → `assets/`. Le nom affiché seul est gratuit.
2. **Les quatre bibliothèques : une instance du même modèle chacune, ou une seule avec filtre ?** Réglé : Sprite,
   Script, Sound et Scene en font partie ; la Scene library a trois filtres (scene / prefab / script). Reste la forme
   (aujourd'hui chaque écran embarque son finder) et **le filtre script de la Scene library : le retire-t-on**, puisque
   la Script library existe ? Le retirer enlève un doublon, mais `script_creation.py` partage aujourd'hui le menu de
   création entre les deux.
3. ~~Le mot « asset »~~, **tranché le 2026-10-22** : un **asset est un fichier de l'éditeur** (sprite, fond, scène,
   prefab, palette, table…), qui référence ou non un fichier source. Le mot garde ce sens partout. Une **source** est un
   fichier brut de l'auteur (PNG, WAV, `.lua`…), qui peut vivre sans asset. La `user_library` contient les deux.
4. **Les clés de traduction** (`labels.json` / `labels_fr.json`, dont `disk.root`) et les raccourcis (`keybindings.py`)
   suivent le renommage, avec la traduction FR ajoutée d'office.

### Ce que ça touche

- ~70 occurrences dans 24 fichiers (relevé du 2026-10-14) : `editor/ui/common/asset_finder.py`, `asset_kinds.py`,
  `*_finder_panel.py`, `window.py` (onglet « Project viewer » → « Scene library », voir aussi `script_creation.py`,
  `script_finder_panel.py`, `assets_finder_panel.py` qui le citent), les écrans qui embarquent un finder, `tools/check_ui_text.py`, `core/keybindings.py`.
- **Tests** : `test_asset_finder_folders.py`, `test_finder_locate.py`, `test_sound_finder_folders.py`, `conftest.py`.
- **Docs** : `editor/ui/asset-finder.md` (renommé), ARCHITECTURE, ROADMAP (les sections qui citent « finder »).

### Ordre d'implémentation

1. Trancher les points ci-dessus.
2. Le renommage du code (classes, modules, tests) en un seul geste, sans alias.
3. Les libellés, les infobulles, les clés FR.
4. Si le dossier change de nom sur disque : chemins, surveillance, migration des démos et du starter.
5. Les docs, la chasse au code mort.
