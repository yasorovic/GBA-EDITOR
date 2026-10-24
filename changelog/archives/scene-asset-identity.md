# L'identité des assets et des membres de scène : LIVRÉ (première tranche)

**Ouvert et livré le 2026-10-24.** Chantier technique, sans numéro de version : il change le format des fichiers du
projet, pas le jeu produit. Le reliquat (nom ou id dans l'API Lua, index des fonds) reste dans le
[TODO](../../docs/development/TODO.md#identité-des-assets-et-des-membres-de-scène-en-tête-name--id--source).

## D'où vient la question

Les sidecars écrivaient déjà `name` puis `id`, mais le chemin du fichier source portait un nom différent selon la famille
(`asset` presque partout), les palettes n'avaient pas d'id, et ce qui est posé dans une scène n'avait pas d'identité à lui :
un acteur ne connaissait son prefab que par son nom, ce qui obligeait `rename_prefab` à réécrire toutes les scènes. La demande
de l'auteur : un seul en-tête, `name` / `id` / `source`, pour tous les assets, puis le même pour tout élément posé dans une scène.

## Ce qui est livré

- **Un en-tête commun pour les assets.** `Resource.header()` compose `name`, `id`, puis `source` si l'asset a un fichier source ;
  `body()` donne le reste, `from_header()` rend `source` à l'attribut du modèle (`source_field`). `ResourceStore.save` écrit
  `{**header, **body}` ; aucun modèle n'écrit lui-même ces clés. L'attribut Python garde son nom (`asset`, 47 fichiers) ; seule
  la clé sur disque devient `source`. Un sidecar qui dit encore `asset` se lit tel quel et passe au nouveau format à sa prochaine
  écriture. `source_field` est posé sur sprite, fond, police, palette, sfx, musique et jingle.
- **Les palettes reçoivent un id** et suivent la même forme (`name`, `id`, `source`, `size`) ; `PaletteStore` attribue l'id à
  la lecture si le sidecar n'en a pas.
- **Un en-tête commun pour les éléments de scène** (`core/models/scene_member.py`) : acteurs, calques de fond, caméras,
  fenêtres, interfaces et parties de prefab. `name` est la poignée dans la scène, `id` l'identité unique dans la scène, `source`
  l'id de l'asset dont l'élément est l'instance. `Scene.members()` les liste, `assign_member_ids` attribue les ids (le premier
  garde le sien en cas de doublon, ce qui couvre la copie d'un acteur), `Scene.ensure_member_names` nomme un calque ou une
  interface sans nom (`BG0`, ou le nom de l'asset posé).
- **Nom en mémoire, id sur disque** (`core/scene_sources.py`). `Actor.prefab_name`, `BackgroundLayer.background_name` et
  `InterfaceNode.layout_name` restent ce que le build lit. `resolve_scene_sources` (à l'ouverture) fait gagner l'id ;
  `stamp_scene_sources`, branchée sur `ResourceStore.before_save` des scènes, convertit le nom en id avant chaque écriture.
  `prefab_name` n'est plus écrit. Renommer un prefab ne réécrit plus aucune scène.
- **Une validation** : `validator._check_scene_sources` bloque le build quand la `source` d'un acteur ou d'une interface ne
  désigne plus aucun prefab ni aucune mise en page. Une `source` orpheline n'est jamais effacée en silence.
- **La colonne `prefab` de la table de données.** Même famille que `sprite` et `background` : choix filtrable, index du prefab
  dans le catalogue en ROM (`data_tables.reference_index`), commentaire C qui nomme l'élément, renommage du prefab suivi.

## Décisions

- `source` dit toujours une **origine** : un chemin dans un sidecar d'asset, un id dans un élément de scène. Un seul mot, deux
  types, écrit noir sur blanc dans ARCHITECTURE.md.
- L'id d'un élément de scène est unique **dans la scène** ; l'en-tête est mutualisé entre `Resource` et `SceneMember`, pas le
  stockage : un acteur de scène n'est pas une `Resource` et n'a pas de fichier.
- Les **calques de fond** écrivent `source` ET `background_name` : le catalogue des fonds est paresseux, et retrouver un nom
  depuis un id obligerait à lire tous les sidecars à l'ouverture.
- `Actor.parent`, `Camera.follow_target` et `InterfaceNode.anchor_actor` citent toujours un nom. Un nom OU un id dans l'API Lua
  et dans les champs de l'interface est un chantier à part, sans donnée à migrer puisque les ids sont déjà écrits.
- Un prefab ne peut pas encore être instancié depuis une colonne : `actor:spawn` n'accepte qu'un nom littéral (une fonction de
  spawn par prefab et par scène). La colonne est une donnée de référence.

## Vérification

`test_common_sidecar_header.py` (ordre des clés, absence de `source` sans fichier, lecture d'un sidecar d'avant l'en-tête),
`test_scene_member_header.py` (ids uniques, `source` d'un prefab, renommage sans réécriture de la scène, acteur d'avant
l'en-tête) et `test_data_asset_references.py` (colonne `prefab`) passent, avec les dossiers `tests/scene` et `tests/project`
et les tests de palettes et de validation. Trois tests qui attendaient l'ancien format de sidecar de palette ont été alignés.

**Non vérifié** : l'éditeur n'a pas été ouvert sur un projet réel après le changement de format, et la suite complète n'a pas
été lancée. Les démos ne sont pas réécrites ; elles passeront au nouveau format à leur prochain enregistrement.
