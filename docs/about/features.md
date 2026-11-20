# Fonctionnalités

Backstage est un logiciel qui rassemble les éléments nécessaires pour construire un jeu sur Game Boy Advance, puis les transforme en ROM `.gba` avec devkitPro.

## Construire le jeu

- **Scènes et décors** : composez les plans de fond, la caméra, les collisions et les transitions entre scènes.
- **Acteurs et prefabs** : réutilisez un même modèle, animez-le, modifiez ses propriétés et créez des variantes.
- **Physique et zones** : donnez aux acteurs des corps physiques, des collisions, des déclencheurs et des zones
  d'effet.
- **Texte et interface** : importez une police, affichez des textes et composez des éléments d'interface.
- **Sons et musique** : ajoutez des effets sonores, jingles et morceaux à votre projet.

## Écrire le comportement

Les scripts utilisent une forme volontairement limitée de Lua. Elle donne accès aux acteurs, scènes, caméras, textes,
sons et données du projet, puis le Build les traduit en C pour la console.

Les [guides](../guides/index.md) présentent les gestes courants. Le [catalogue Lua](../lua-api/index.md) décrit chaque fonction disponible.

## Produire et partager

- **Build & Run** compile une ROM et la lance dans mGBA.
- **Build WEB** prépare un ZIP jouable dans un navigateur et compatible avec itch.io.
- Les fichiers du projet restent dans un dossier lisible : ressources, scènes, scripts, palettes et données peuvent
  être rangés avec vos propres noms.

```{note}
Backstage est encore en alpha. Certaines parties de l'éditeur et de la documentation évoluent encore et vos retours
d'utilisation sont les bienvenus.
```

Pour connaître les grands axes à venir, consultez la [roadmap du projet](https://github.com/yasorovic/GBA-EDITOR/blob/main/ROADMAP.md).
