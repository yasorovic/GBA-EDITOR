```{toctree}
:hidden:
:maxdepth: 2

Getting Started <user-guide/index>
Guides <guides/index>
Manual <manual/index>
Architecture <architecture/index>
Lua API <lua-api/index>
About <about/index>
```

```{image} assets/backstage-study.svg
:class: backstage-home-mascot
:alt: La mascotte de Backstage, lunettes sur le nez, un livre à la main
```

```{raw} html
<p class="backstage-home-kicker">Documentation de Backstage</p>
```

# Créez votre jeu Game Boy Advance

:::{div} backstage-home-lead
Backstage est un logiciel libre pour fabriquer des jeux Game Boy Advance depuis une interface visuelle. Créez, construisez, Backstage s'occupe de la technique.
:::

::::{div} backstage-home-actions
:::{button-ref} user-guide/index
:ref-type: doc
:class: backstage-btn backstage-btn-primary
Créer mon premier jeu
:::
:::{button-ref} about/index
:ref-type: doc
:class: backstage-btn backstage-btn-secondary
Découvrir Backstage
:::
::::

Essayez le jeu de démonstration de Backstage. Utilisez les **flèches** de votre clavier pour vous déplacer et la touche **Z** pour sauter, ou les commandes tactiles sur téléphone.

```{raw} html
<iframe class="backstage-home-demo" src="platformer/index.html"
        title="Platformer, jeu de démonstration de Backstage" loading="lazy"
        allow="autoplay; fullscreen; gamepad"></iframe>
```

Pour modifier le jeu dans Backstage, suivez le guide {doc}`Premiers pas <user-guide/first-steps>`.

## Aller plus loin

::::{grid} 1 1 3 3
:gutter: 3
:class-container: backstage-cards

:::{grid-item-card} Lua API
:link: lua-api/index
:link-type: doc
:class-card: backstage-card backstage-card-purple

Vous savez programmer ? Écrivez le comportement de vos acteurs et parcourez toutes les fonctions disponibles.
:::

:::{grid-item-card} About
:link: about/index
:link-type: doc
:class-card: backstage-card backstage-card-blue

Ce qu'est Backstage, ce qu'il fait, et ce que vous avez le droit d'en faire. _Cette section arrive bientôt._
:::

:::{grid-item-card} Architecture
:link: architecture/index
:link-type: doc
:class-card: backstage-card backstage-card-teal

Curieux de la technique ? Comment un projet devient une ROM. _Cette section arrive bientôt._
:::
::::

```{note}
Backstage est en alpha : cette documentation grandit avec lui. Le **Manuel**, qui décrira le fonctionnement de l'éditeur, arrive bientôt.
```

## Participer

Backstage est un projet libre, développé publiquement. 
Vous pouvez suivre son développement sur Github ou en installant le logiciel et en suivant les mises à jour. Vos retours aident à améliorer la documentation comme le logiciel : une explication n'est pas claire, une page introuvable, une fonction qui manque.

- Signalez un problème ou proposez une idée sur le [dépôt GitHub](https://github.com/yasorovic/GBA-EDITOR/issues).
- Téléchargez la dernière version sur la page des [releases](https://github.com/yasorovic/GBA-EDITOR/releases).
- Suivez les prochains chantiers dans la [roadmap](https://github.com/yasorovic/GBA-EDITOR/blob/main/ROADMAP.md).
