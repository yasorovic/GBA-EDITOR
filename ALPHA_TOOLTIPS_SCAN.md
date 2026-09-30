# Tooltips manquants qui apporteraient de la valeur (brouillon)

Généré le 2026-09-30, **aucun code modifié**. Critère : on ne retient que ce qu'un tooltip
éclaire vraiment (unité, effet matériel, coût, plage, différence entre deux options).
Écartés : tout widget dont le libellé dit déjà l'action (Back, Save, Clear, Browse…, filtres,
sections de la barre latérale, onglets, en-tête de nom, pipeline texte, zoom ±).

Méthode : éditeur ouvert hors-écran sur `PongAdvanced`, puis chaque inspecteur piloté
directement (`show_scene`, `show_actor`, `show_camera`, `show_ui_node`, `show_ui_element`…),
cartes dépliées, dialogues Réglages et chaque page. Acteur / prefab / interface **synthétiques**
en mémoire (Pong n'en a aucun), avec les 4 composants (sprite, collision, sfx, script).

## 1. Inspecteur d'acteur / prefab (priorité haute, sémantique matérielle)
- **Rotation**, **Scale X / Y** : dire que ça consomme un slot de matrice affine (32 par scène).
- **Mode** (« Normal » / window) : `obj_mode`, sprite normal ou fenêtre-objet.
- **Visible** (Transform) : différence avec `Active` du composant.
- **Bouton d'unité `px`** des champs de position : c'est le sélecteur px / tuile / variable, rien ne l'indique.
- **Active** et champ **id** d'un composant ; boutons **+ / −** des cartes Components et Children ; **Open prefab**.
- Emplacements du composant sprite : **palette** (« No palette (PNG colors) »), **état initial** (« Idle »), choix du sprite.
- (Composant collision : rien remonté, les tooltips y existent déjà.)

## 2. Interface (priorité haute)
- Nœud Interface, carte « Hardware path » : **Anchor**, **Actor**, **Target**, **BG slot**. Les quatre combos portent tout le choix matériel sans aide.
- Éléments : **X / Y / W / H** (alignés sur la tuile), **Visible** (« Shown at scene start »), fond **Mode / index / Asset**, marges **L / R / T / B** (neuf-tranches), liste **Wrap** et **Speed**, sélecteur de police (graisse), **Delete element**.

## 3. Caméra et scène
- Caméra : incohérence, **Y** et **H** (Transform), **Y** (Follow), **X / Y / H** (World bounds) n'ont rien alors que leurs voisins **X / W** en ont un. Probablement un oubli de boucle.
- Scène : emplacement **Scene mode**, **bitmap background**, palette et police de « User Interface ».

## 4. Polices (panneau FontAsset, priorité haute)
Tout le panneau est nu : **Primary**, **Fallbacks**, **Pixel height**, **Line height**, **Pixel fit**, **Hinting**, **Output**, **Threshold**, **Dither**, **Offset X / Y**, **Prefer an embedded bitmap strike**. Glyph sheet : **Cell**, **Zoom**.

## 5. Palettes
- Champ hex, curseurs et spinboxes **RGB** (0-31, 5 bits par canal) et **HSB** : préciser la plage et l'arrondi GBA.
- **SwatchButton** : bouton-icône sans aucun texte.

## 6. Autres écrans (vus à l'état d'ouverture, donc partiel)
- Animations : combos de taille de cellule (w / h), **Loop**.
- Backgrounds : **Dithering**, **Import / replace image…** (remplace-t-il les tuiles peintes ?).
- Datas : combo de **type** de colonne.
- Sounds : **+ New** dans l'onglet de boîte.
- Projet : champs **Author** et **Version** (Identity).
- Réglages : **Theme**, **Language**, **Show tips**, chemins des toolchains et outils externes.

## 7. Non couvert (à refaire avec un projet riche)
Pong n'a ni sprite, ni prefab, ni interface, ni graphe de scènes. Pas exercés : éditeur de sprites avec un sprite chargé, éditeur de fonds avec un fond, mixeur de sons avec des boîtes, inspecteurs de transition / groupe / note, inspecteur de script, calques BG. La démo tactique n'est plus sur disque ; un projet de test riche permettrait de boucler ces cas.
