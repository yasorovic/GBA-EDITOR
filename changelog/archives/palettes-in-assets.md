# Les palettes, rangées avec les assets — **LIVRÉ**

> **Ouvert et livré le 2026-09-18.** Chantier technique : le catalogue de palettes quitte
> `project/palettes/` pour `assets/palettes/`. Rien ne change pour qui joue au jeu ; c'est une
> correction de rangement, alignée sur la règle « `assets/` vs `project/` » d'ARCHITECTURE.md.

## D'où vient la question (2026-09-18)

L'auteur : une palette n'est plus un objet moteur propre à l'éditeur, mais une **donnée** que
l'auteur importe et exporte — un fichier `.hex` d'échange, au même titre qu'un PNG ou un son. Or
la règle qui structure tout le projet est simple :

- `project/` → données propres à l'éditeur, sans dépendance externe (scènes, prefabs, variables…) ;
- `assets/` → ce qui dépend d'une ressource externe à l'éditeur, importable et exportable.

Le catalogue de palettes vivait sous `project/palettes/`, du mauvais côté de cette ligne. Il
rejoint `assets/`.

## Ce que la lecture du code a trouvé

Un seul point de vérité pilotait l'emplacement : `Project.palettes_dir`
([project_paths.py](../../editor/core/project_paths.py)), qui renvoyait `project_dir / "palettes"`.
Tout le reste dérive de cette propriété — `PaletteStore` la reçoit, l'éditeur de palettes la lit,
le codegen la traverse. Basculer la propriété vers `assets_dir / "palettes"` suffit à déplacer le
catalogue ; le reste n'était que du texte accompagnant ce chemin.

## Ce que ça touche

- **`palettes_dir`** ([project_paths.py](../../editor/core/project_paths.py)) → `assets/palettes`, avec
  la raison en docstring.
- **`Project.load`** ([project.py](../../editor/core/project.py)) : `project/palettes` retiré de la
  liste des sous-dossiers créés côté `project/`, ajouté côté `assets/`.
- **Le starter `Basic`** : le dossier physique
  `editor/project_starters/Basic/project/palettes` déplacé vers
  `editor/project_starters/Basic/assets/palettes` (les dix `.hex` livrés + leurs sidecars). Un
  projet neuf naît donc directement avec `assets/palettes/`.
- **Docstrings** alignées : `palette_store.py`, `palette_io.py`, `palette_presets.py`,
  `models/palette.py`.
- **ARCHITECTURE.md** : nouvelle ligne `assets/palettes/` dans les Règles clés, et les deux
  références `project/palettes/*.json` → `assets/palettes/*.json`.
- **Tests** : `tests/graphics/test_palette_store.py` aligné sur le nouveau chemin.

## Pas de migration — assumé

Comme le veut la règle du projet (« Aucune migration de format », cf.
[project_paths.py](../../editor/core/project_paths.py)), le chemin canonique change et les anciens
emplacements ne sont plus lus. Un projet d'avant ce chantier a ses palettes sous
`project/palettes/` ; l'auteur déplace le dossier à la main vers `assets/palettes/`. Décision prise
explicitement avec l'auteur plutôt que de porter une migration à l'ouverture.
