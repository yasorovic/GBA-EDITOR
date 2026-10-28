# Se repérer dans l'éditeur

La fenêtre de Backstage se découpe en six zones. Les mêmes se retrouvent d'un écran à l'autre,
seul leur contenu change : une fois la logique comprise sur l'écran **Scenes**, les autres
écrans deviennent familiers.

```{figure} img/editor-tour.png
:alt: L'éditeur avec six zones numérotées : barre du haut, colonne de gauche, zone centrale, inspecteur, panneau du bas, barre matérielle.
:class: backstage-screenshot

Les six zones de l'écran **Scenes**.
```

## Les six zones

1. **La barre du haut.** À gauche, le bouton **Run** (`F5`) construit la ROM et la lance, puis
   **Undo** et **Redo** annulent et rétablissent. Au centre, la barre de navigation ouvre les
   écrans. À droite, le nom du projet et l'indicateur d'enregistrement.
2. **La colonne de gauche.** Elle liste ce que contient le projet. Sur l'écran **Scenes**, le
   haut montre le contenu de la scène active (ses acteurs, ses éléments d'interface) et le bas
   la **Scene library** (scènes et prefabs). Un second onglet, **Disk**, montre les fichiers du
   dossier du projet.
3. **La zone centrale.** C'est là que l'on travaille : le canvas d'une scène, l'aperçu d'un
   décor, la planche d'un sprite. Sa barre d'outils et la position du curseur se trouvent au-dessus.
4. **L'inspecteur.** Il règle l'élément sélectionné : la scène quand rien n'est sélectionné, un
   acteur quand vous cliquez dessus.
5. **Le panneau du bas.** Trois onglets : **Disk** (les fichiers), **Console** (le journal de
   construction) et **Diagnostics** (les avertissements et erreurs, avec le fichier et la ligne
   concernés).
6. **La barre matérielle.** Elle suit les limites de la console pour la scène affichée :
   sprites (**OAM**), tuiles et palettes, mémoire. Une valeur passe au jaune puis au rouge à
   l'approche d'une limite. C'est un tableau de bord, pas une étape obligatoire.

## Les écrans

La barre de navigation ouvre huit écrans, tous bâtis sur la même disposition : une liste à
gauche, l'espace de travail au centre, les réglages à droite.

| Écran | Utilité |
| --- | --- |
| **Scenes** | Construire les scènes : placer les acteurs, les collisions et l'interface. |
| **Backgrounds** | Préparer les décors et les cadres d'interface. |
| **Animations** | Découper une planche de sprites et composer les animations. |
| **Palettes** | Créer, importer et ajuster les couleurs partagées par le jeu. |
| **Texts** | Écrire les textes affichés, préparer les traductions et les polices. |
| **Sounds** | Ajouter les effets sonores et la musique. |
| **Scripts** | Écrire le comportement en Lua et consulter l'API disponible. |
| **Datas** | Définir des tableaux de données pour les objets, ennemis ou dialogues. |

```{figure} img/backgrounds-screen.png
:alt: L'écran Backgrounds sur le décor Level : la bibliothèque des fonds, l'image au centre et l'inspecteur.
:class: backstage-screenshot

L'écran **Backgrounds** reprend la même disposition : la bibliothèque à gauche, le travail au centre,
l'inspecteur à droite.
```

## Gestes de base

- Les séparateurs entre les panneaux se déplacent à la souris.
- `Ctrl+S` enregistre, `Ctrl+Z` annule, `Ctrl+Y` rétablit, `F5` lance **Run**.
- `F2` renomme la ressource sélectionnée. Un clic droit sur une ressource propose renommer,
  dupliquer, voir ses utilisations ou supprimer.
- Le **+** d'une section crée ou importe une ressource, selon la famille.
- Sur chaque canvas, un clic sur la position du curseur bascule entre **pixels** et **tuiles**
  (8 px), dans tous les canvas à la fois.
- Les autres raccourcis se consultent et se personnalisent dans **File → Settings → Shortcuts**.

Suite : [Comprendre un projet](understanding-a-project.md).
