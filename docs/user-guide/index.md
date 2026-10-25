# Vue d'ensemble

Ce guide explique comment utiliser Backstage pour construire un jeu, sans présumer que vous
connaissez déjà les formats Game Boy Advance ou le code généré. Il commence par une visite de
l'éditeur, de vos fichiers et d'une première scène ; chaque page prend quelques minutes et prépare
la suivante.

```{figure} overview/img/editor-overview.png
:alt: La fenêtre de Backstage sur le projet Platformer : la scène au centre, les listes à gauche, l'inspecteur à droite.
:class: backstage-screenshot

L'écran **Scenes** du projet de démonstration Platformer.
```

Backstage fabrique des jeux Game Boy Advance depuis une interface visuelle. Vous importez vos
images, vos sons et vos textes, vous les assemblez dans des **scènes**, vous ajoutez du
comportement avec des scripts Lua, puis un seul bouton, **Run**, produit la ROM et la lance dans
l'émulateur mGBA. L'éditeur s'occupe des contraintes de la console et les signale au fur et à
mesure.

## Le parcours

1. [Se repérer dans l'éditeur](overview/editor-tour.md) : les six zones de la fenêtre, les écrans et les raccourcis.
2. [Le projet en une idée](overview/project-idea.md) : ressources, acteurs, et les gestes créer, importer, modifier.
3. [Le dossier assets](overview/assets-folder.md) : où vivent vos fichiers et l'onglet **Disk**.
4. [Importer votre première ressource](overview/first-import.md) : depuis l'éditeur, ou depuis le dossier assets.
5. [Construire une première scène](overview/first-scene.md) : créer une scène, placer un acteur, lancer la ROM.

## Continuer

- Pour un premier résultat complet, suivez le tutoriel [Votre première scène jouable](first-playable-scene.md).
- Pour assembler un jeu entier, suivez [Un mini-jeu de plateforme](mini-game.md).
- Pour un sujet précis (déplacement, collisions, caméra, prefabs, dialogues, dégâts...), ouvrez le [guide](../guides/index.md) correspondant : chacun se lit seul.
- Pour écrire du comportement, passez au [guide de scripting](../scripting.md).
- Pour comprendre une erreur de compilation, lisez d'abord le fichier et la ligne cités dans l'onglet **Diagnostics** : l'erreur est généralement liée à l'élément ou au script concerné.

```{toctree}
:hidden:
:maxdepth: 1

Se repérer dans l'éditeur <overview/editor-tour>
Le projet en une idée <overview/project-idea>
Le dossier assets <overview/assets-folder>
Importer une première ressource <overview/first-import>
Construire une première scène <overview/first-scene>
Tutoriel : première scène jouable <first-playable-scene>
Tutoriel : mini-jeu de plateforme <mini-game>
```
