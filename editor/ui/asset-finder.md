# Asset finder unique — état des lieux et conception

Chantier : remplacer les 8 panneaux « finder » de l'éditeur par **un seul
composant**, sur le modèle d'interaction du Script finder (arbre de dossiers,
sous-sections repliables, ligne = icône + nom).

Périmètre demandé : sprites, scènes, prefabs, backgrounds, scripts, fonts,
palettes, sfx, musics, datatables.

---

## 1. Ce qui existe aujourd'hui

Huit panneaux, écrits séparément, pour la même intention « lister les assets
d'une famille et en choisir un ». Trois modèles de widget différents, aucun
partagé :

| Écran | Panneau | Familles listées | Widget | Lignes |
|---|---|---|---|---|
| Scene Manager | `assets_finder_panel.py` | scenes, prefabs, scripts | `QTreeWidget` | 689 |
| Script Editor | `script_finder_panel.py` | scripts (+ globals/constants) | widgets custom sur disque | 309 |
| Sprite Editor | `sprite_finder_panel.py` | sprites (+ animations) | `QTreeWidget` | 483 |
| Palette Editor | `palette_finder_panel.py` | palettes | `QTreeWidget` | 291 |
| Data Editor | `data_finder_panel.py` | datatables | `QTreeWidget` | 216 |
| Text Editor | `font_finder_panel.py` | fonts | `QListWidget` | 101 |
| Text Editor | `text_table.py` | textes | `QTreeWidget` (mode table) | 520 |
| Sound Mixer | `sound_panel.py` (section) | sfx, musics | `QTreeWidget` ×2 | — |
| Background Editor | `background_editor_screen.py` (section) | backgrounds | `FinderSection` | — |

Ce qui est **déjà** partagé : `W.finder_bar()`, `FinderSection`,
`W.section_bar()`, `QSS.tree_widget` (cf. `ui/common/widgets.py`). C'est
l'habillage. Ce qui ne l'est pas : le peuplement, le renommage en place, le
menu contextuel, la suppression, la sélection — réécrits huit fois.

---

## 2. Le constat qui commande la conception

**Neuf des dix familles demandées sont des `ResourceStore`** (cf.
`core/resource_store.py`) : un dossier **plat** de `<nom>.json`, chargé en
mémoire à l'ouverture du projet. La collection en mémoire est la source de
vérité ; le disque est sa persistance.

```
project.sprites  = ResourceStore(assets/sprites,     SpriteAsset)
project.backgrounds, prefabs, scenes, sfx, music, fonts, palettes, data_tables
```

**Les scripts sont la seule exception** : de simples fichiers `.lua`/`.c`,
sans modèle `Resource`, dans une arborescence **imbriquée**
(`actors/`, `behaviors/`, `cameras/`, `scenes/`). Là, le disque **est** la
source de vérité — c'est pour ça que le Script finder parcourt les dossiers.

Deux conséquences :

1. **Le composant unique doit lire le `ResourceStore`, pas re-parcourir le
   disque.** Re-parcourir créerait une deuxième source de vérité qui diverge :
   un asset renommé en mémoire mais pas encore sauvé, un `soft_delete` dont le
   JSON existe toujours jusqu'à la fermeture, un import en cours. Le Script
   finder a le droit de lire le disque *parce que* c'est sa vérité ; les neuf
   autres non.

2. **Les dossiers qui donnent son allure au Script finder n'ont pas
   d'équivalent ailleurs.** Les neuf `ResourceStore` sont plats par
   construction : `_path()` s'écrit `dir / f"{name}.json"`, et le nom est
   l'identité globale de l'asset — celle que le codegen et les scripts citent
   (`actor:spawn("Ball")`, `data.Heyo`).

C'est **le** point de décision du chantier : l'allure demandée repose sur une
hiérarchie que neuf familles sur dix n'ont pas.

---

## 3. Décision

**L'utilisateur pourra créer sa propre arborescence de dossiers.** La hiérarchie
n'est donc pas une particularité des scripts : c'est le modèle cible de toutes
les familles.

Le finder est par conséquent **hiérarchique nativement**, dès maintenant. Sa
source n'est pas une liste mais un **arbre de nœuds** (`AssetNode` : un dossier,
ou un asset). Aujourd'hui les scripts en rendent un vrai, construit depuis le
disque, et les neuf `ResourceStore` n'en rendent qu'un seul niveau. Le jour où
`ResourceStore` saura les sous-dossiers, ils rendront un arbre — **et le finder
ne bougera pas d'une ligne**.

C'est la couture du chantier : l'arbre de nœuds. Elle permet de livrer
maintenant sans toucher au modèle (§4 « option A »), sans fermer la porte aux
vrais dossiers (§4 « option B »), et sans avoir à réécrire l'UI le jour venu.

Les options ci-dessous restent consignées pour mémoire — c'est le **modèle de
stockage** qu'elles départagent, une question désormais distincte de l'UI.

## 4. Les trois façons de trancher (le stockage — chantier séparé)

### A — Groupes présentation seulement (aucun changement de modèle)
Le finder affiche des sous-sections quand la famille en propose (scripts :
`actors/`, `behaviors/`… ; sprites : par `kind` ; backgrounds : par `kind`
scene/ui/animated, qui existe déjà). Les familles sans axe de regroupement
naturel restent une liste plate sous une seule section.

- *Pour* : zéro risque, le nom reste l'identité, rien à migrer.
- *Contre* : l'allure « dossiers » n'apparaît pas partout — palettes,
  datatables, fonts resteront plates.

### B — Vrais sous-dossiers dans `ResourceStore`
`load()` devient récursif, `_path()` retient un chemin relatif, et chaque asset
gagne un « dossier » indépendant de son nom.

- *Pour* : l'allure demandée, partout, avec de vrais dossiers rangeables.
- *Contre* : chantier profond — `save`/`rename`/`delete`/`load_one` à revoir,
  l'unicité du nom reste globale (le codegen cite le nom, pas le chemin), et
  les projets existants doivent continuer à s'ouvrir. À faire séparément, pas
  au milieu d'une refonte d'UI.

### C — Dossier virtuel porté par l'asset
Un champ `folder: str` sur `Resource`, purement de rangement, le fichier restant
`dir/<nom>.json`.

- *Pour* : l'allure partout, sans toucher à l'I/O ni à l'identité.
- *Contre* : un dossier qu'on ne voit pas dans l'explorateur de fichiers —
  déposer un PNG dans `assets/sprites/` ne le range nulle part.

---

## 4. Ce que serait le composant, quelle que soit l'option

`ui/common/asset_finder.py` — un panneau, paramétré par une **description de
famille** et non par des sous-classes :

```python
AssetKind(
    label      = "Sprites",
    store      = lambda p: p.sprites,      # la source de vérité
    icon       = "sprite",
    groups     = lambda p, item: item.kind,  # axe de regroupement, ou None
    on_rename  = lambda p, item, new: p.rename_sprite(item, new),
    on_delete  = ...,
    on_add     = ...,
)
```

Le panneau fournit une fois pour toutes : peuplement, sous-sections repliables,
filtre par nom, renommage en place, menu contextuel, suppression annulable,
sélection via le bus. Chaque écran déclare ses familles et branche ses signaux.

Les scripts gardent un `store` qui parcourt le disque — même interface,
vérité différente, ce que la description rend explicite.

**Hors périmètre** : `text_table.py` ne liste pas des assets fichiers mais des
entrées d'une table de textes avec sa propre grammaire de clés — et elle a ses
propres colonnes (rangement, usages) qu'aucun finder n'a ; et les sous-arbres *métier* (animations d'un sprite, glyphes d'une
police) restent chez eux.

---

## 5. Ordre de marche proposé

1. Trancher §3 (A, B ou C).
2. Écrire `ui/common/asset_finder.py` + la table des familles.
3. Migrer écran par écran, **en supprimant l'ancien panneau à chaque étape**
   (pas de cohabitation : deux finders pour une famille, c'est deux vérités).
4. Les huit fichiers listés au §1 disparaissent ou se réduisent à leur partie
   métier.
