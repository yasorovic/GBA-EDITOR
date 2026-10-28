# Décors

Le décor est ce qui se trouve derrière les acteurs : le sol, le ciel, les murs, une forêt qui défile. Sur la
Game Boy Advance, la console ne le dessine pas comme une grande image : elle assemble de petites tuiles
sur des **fonds tuilés**, et peut en superposer quatre. Ce thème vous apprend à importer une image,
à comprendre comment la console la dessine, puis à la manipuler depuis un script.

Les pages se lisent dans l'ordre, du plus simple au plus avancé.

## Démarrer

::::{grid} 1 1 2 2
:gutter: 3
:class-container: backstage-cards

:::{grid-item-card} Importer un décor
:link: importer-un-decor
:link-type: doc
:class-card: backstage-card backstage-card-purple

Le format de l'image, l'écran **Backgrounds**, l'affecter à une scène, puis la faire défiler avec un script.
:::
::::

## Comprendre

::::{grid} 1 1 2 2
:gutter: 3
:class-container: backstage-cards

:::{grid-item-card} Qu'est-ce qu'une tilemap ?
:link: tilemap
:link-type: doc
:class-card: backstage-card backstage-card-blue

Pourquoi la console découpe une image en tuiles, et ce que contient la carte qui les assemble.
:::

:::{grid-item-card} Fond et calque : quelle différence ?
:link: fond-et-calque
:link-type: doc
:class-card: backstage-card backstage-card-blue

Le fond est l'image importée. Le calque est la façon dont une scène l'emploie.
:::
::::

## Aller plus loin

::::{grid} 1 1 2 2
:gutter: 3
:class-container: backstage-cards

:::{grid-item-card} Collisions
:link: ../acteurs/collisions
:link-type: doc
:class-card: backstage-card backstage-card-teal

Peindre la carte de collision pour que les acteurs ne traversent plus les murs.
:::
::::

```{toctree}
:hidden:
:maxdepth: 1

Importer un décor <importer-un-decor>
Qu'est-ce qu'une tilemap ? <tilemap>
Fond et calque <fond-et-calque>
```
