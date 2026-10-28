# Comprendre un projet

Un projet est un **dossier autonome**. Il contient les ressources de votre jeu (images, sons,
scripts, scènes, palettes, données) et les réglages nécessaires pour fabriquer une ROM. Vous
travaillez toujours dans ce dossier ; l'éditeur enregistre et relie les ressources entre elles.

```text
Créer ou ouvrir un projet → importer ou créer des ressources → construire une scène
→ ajouter du comportement → Run
```

Ces étapes n'ont pas d'ordre strict. Un sprite peut être importé après la création d'une scène, et
un script ajouté dès que l'acteur existe.

## Les ressources, ou assets

Tout ce qui compose le jeu est une **ressource** (*asset*). Chaque famille a son écran :

| Ressource | Ce que c'est | Écran |
| --- | --- | --- |
| **Sprite** | Une image découpée en frames, avec ses animations. | **Animations** |
| **Background** | Un décor, un cadre d'interface ou une animation de décor. | **Backgrounds** |
| **Palette** | Les couleurs partagées par les images. | **Palettes** |
| **Sound / Music** | Effets sonores et morceaux. | **Sounds** |
| **Script** | Le comportement, écrit en Lua. | **Scripts** |
| **Scene** | Un écran de jeu : décors, acteurs, collisions, interface. | **Scenes** |
| **Prefab** | Un acteur modèle, réutilisable dans plusieurs scènes. | **Scenes** |

Une ressource se référence par son **nom**, unique parmi les ressources du même type : une musique
`village` et un décor `village` coexistent, deux décors `village` non. Un nom déjà pris est
complété (`village_2`). Renommer une ressource met à jour tout ce qui la cite.

## Les acteurs

Dans une scène, ce qui bouge, réagit ou s'affiche est un **acteur** : le joueur, un ennemi, une
pièce, un coffre. Un acteur est un assemblage : une position, un sprite, des composants
(collision, script...). Un **prefab** est un acteur modèle : modifié une fois, toutes ses
instances suivent.

## Créer, importer, modifier

Trois gestes distincts reviennent partout.

- **Créer** convient aux scènes, prefabs, scripts, palettes et tables de données : la ressource naît
  dans le projet, puis se configure dans l'inspecteur.
- **Importer** copie un fichier extérieur dans le dossier du projet et crée la ressource
  correspondante. L'original, hors du projet, n'est jamais modifié.
- **Modifier** se fait dans l'écran de la ressource ou son inspecteur. Les changements
  s'enregistrent avec le projet et s'annulent en général avec `Ctrl+Z`.

## Ouvrir un projet

À l'ouverture, l'écran d'accueil propose vos projets récents et des modèles.

1. Cliquez sur **New project**, donnez-lui un nom et choisissez son emplacement.
2. Ouvrez-le : l'écran **Scenes** devient l'espace de travail.

Le modèle **Platformer** est un bon point de départ : une scène, des sprites, des scripts, une
musique et des effets sonores y sont déjà reliés. Pour reprendre un projet existant, utilisez **Browse...** depuis l'accueil ou
**File → Open project**, et ouvrez toujours le dossier racine du projet.

Suite : [Le dossier assets](assets-folder.md).
