# Guides

Un guide traite **un seul sujet** de l'éditeur et se lit sans avoir lu les autres. Chacun annonce ce
qu'il faut avoir préparé (en général un acteur et une scène), développe son propre exemple, puis
liste les pièges. Ouvrez celui dont vous avez besoin, dans l'ordre que vous voulez.

Pour une première prise en main pas à pas, commencez plutôt par le
[Getting Started](../user-guide/index.md).

## Par thème

Un thème regroupe plusieurs pages qui se lisent dans l'ordre, du plus simple au plus avancé.

::::{grid} 1 1 2 3
:gutter: 3
:class-container: backstage-cards

:::{grid-item-card} Décors
:link: decors/index
:link-type: doc
:class-card: backstage-card backstage-card-purple

Importer une image de fond, comprendre la tilemap, la différence entre un fond et un calque.
:::
::::

## Déplacer et animer

::::{grid} 1 1 2 3
:gutter: 3
:class-container: backstage-cards

:::{grid-item-card} Déplacer un acteur
:link: deplacer-acteur
:link-type: doc
:class-card: backstage-card

Lire les touches, transformer une direction en mouvement, régler la vitesse dans l'inspecteur.
:::

:::{grid-item-card} Décors et collisions
:link: decors-collisions
:link-type: doc
:class-card: backstage-card

Peindre la carte de collision, donner une boîte à un acteur, ne plus traverser les murs.
:::

:::{grid-item-card} Gravité et saut
:link: gravite-saut
:link-type: doc
:class-card: backstage-card

Le comportement d'un personnage de plateforme : tomber, marcher, sauter.
:::

:::{grid-item-card} Caméra
:link: camera
:link-type: doc
:class-card: backstage-card

Suivre un acteur dans une scène plus grande que l'écran.
:::
::::

## Organiser le contenu

::::{grid} 1 1 2 3
:gutter: 3
:class-container: backstage-cards

:::{grid-item-card} Prefabs et instances
:link: prefabs
:link-type: doc
:class-card: backstage-card

Un acteur modèle, plusieurs copies réglables.
:::

:::{grid-item-card} Parenté et accesseurs
:link: parente-accesseurs
:link-type: doc
:class-card: backstage-card

Composer un acteur en plusieurs pièces et atteindre les éléments du jeu par leur nom.
:::

:::{grid-item-card} Variables et affichage
:link: variables-affichage
:link-type: doc
:class-card: backstage-card

Local, export ou globale : où ranger une valeur, et comment l'afficher.
:::

:::{grid-item-card} Scènes et transitions
:link: scenes-transitions
:link-type: doc
:class-card: backstage-card

Relier un titre, un niveau et une victoire.
:::
::::

## Faire vivre le jeu

::::{grid} 1 1 2 3
:gutter: 3
:class-container: backstage-cards

:::{grid-item-card} Interaction
:link: interaction
:link-type: doc
:class-card: backstage-card

Réagir à un appui devant un coffre, un panneau ou un personnage.
:::

:::{grid-item-card} Textes et dialogues
:link: textes-dialogues
:link-type: doc
:class-card: backstage-card

Écrire, afficher et traduire des répliques.
:::

:::{grid-item-card} Machines d'état
:link: etats
:link-type: doc
:class-card: backstage-card

Organiser le comportement d'un acteur en états.
:::

:::{grid-item-card} Créer des acteurs pendant le jeu
:link: acteurs-au-vol
:link-type: doc
:class-card: backstage-card

Projectiles et effets : le pool et `actor:spawn`.
:::

:::{grid-item-card} Santé et dégâts
:link: sante-degats
:link-type: doc
:class-card: backstage-card

Points de vie, coups lisibles, barre de vie, frapper un point précis.
:::
::::

```{toctree}
:hidden:
:maxdepth: 1

Décors (thème) <decors/index>
Déplacer un acteur <deplacer-acteur>
Décors et collisions <decors-collisions>
Gravité et saut <gravite-saut>
Caméra <camera>
Prefabs et instances <prefabs>
Parenté et accesseurs <parente-accesseurs>
Variables et affichage <variables-affichage>
Scènes et transitions <scenes-transitions>
Interaction <interaction>
Textes et dialogues <textes-dialogues>
Machines d'état <etats>
Créer des acteurs pendant le jeu <acteurs-au-vol>
Santé et dégâts <sante-degats>
```
