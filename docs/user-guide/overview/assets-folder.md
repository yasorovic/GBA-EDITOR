# Le dossier assets

Un projet contient trois dossiers principaux :

| Dossier | Contenu |
| --- | --- |
| `assets/` | **Votre dossier.** Tout ce que vous manipulez : images et sons sources, scènes, prefabs, scripts, palettes, textes. |
| `project/` | L'état interne de l'éditeur, les licences et le README. Il ne se modifie pas à la main. |
| `build/` | Entièrement généré à chaque construction de la ROM. |

Seul `assets/` vous concerne au quotidien. Vous pouvez l'organiser à votre guise, en créant vos
propres sous-dossiers : l'éditeur retrouve les ressources où qu'elles soient rangées.

## L'onglet Disk

L'onglet **Disk** montre le dossier `assets/` dans l'éditeur, sans passer par l'explorateur du
système. On le trouve dans le panneau du bas, à côté de **Console** et **Diagnostics**, et dans la colonne de gauche, à côté de **Scene library**.

```{figure} img/disk-tab.png
:alt: L'onglet Disk du panneau du bas : le dossier assets, ses sous-dossiers, deux prefabs et deux fichiers de données.
:class: backstage-screenshot

L'onglet **Disk** : le contenu du dossier `assets/` du projet Platformer.
```

### Ressources et sources

Il affiche deux sortes de fichiers.

- Les **ressources** : un fichier `.sprite`, `.background`, `.scene`, `.lua`... que l'éditeur sait
  ouvrir. Un double-clic l'ouvre dans son écran.
- Les **sources** : les fichiers bruts à partir desquels les ressources sont fabriquées (un PNG, un
  WAV, une police). Une source qui ne sert encore à aucune ressource porte un **point jaune**, et
  l'en-tête de l'onglet compte les « sources without asset ».

Une ressource est indépendante de sa source. Elle la cite, mais elle a son propre fichier, son
identité et ses réglages.

### Ce qu'on y fait

- **Déplacer** un fichier par glisser-déposer, ou créer un dossier (**New folder**).
- **Importer** des fichiers avec **Import...**, ou en les déposant depuis l'explorateur.
- **Créer** une ressource à partir d'une source (clic droit, **Create as**).
- **Retrouver** un fichier : **Locate** mène à l'onglet **Disk**, **Reveal** à l'explorateur du
  système.
- **Rafraîchir** : un fichier ajouté depuis l'extérieur apparaît quand la fenêtre retrouve le
  focus, ou avec le bouton **Refresh**.

```{note}
Préférez l'onglet **Disk** à l'explorateur du système pour renommer ou déplacer des fichiers de
`assets/` : l'éditeur garde alors les liens à jour et le geste s'annule avec `Ctrl+Z`.
```

Suite : [Importer votre première ressource](first-import.md).
