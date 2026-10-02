# Guide utilisateur

Ce guide explique comment utiliser Backstage pour construire un jeu, sans présumer que vous
connaissez déjà les formats Game Boy Advance ou le code généré. Les limites de la console sont
signalées dans l'application quand elles deviennent utiles.

## Le projet en une idée

Un projet est un dossier autonome. Il contient les ressources de votre jeu (images, sons,
scripts, scènes, palettes et données) ainsi que les réglages nécessaires pour fabriquer une
ROM. Vous travaillez toujours dans ce dossier ; l'éditeur enregistre et relie les ressources
entre elles.

```text
Créer ou ouvrir un projet → importer ou créer des ressources → construire une scène
→ ajouter du comportement → Build & Run
```

Vous pouvez faire des allers-retours entre ces étapes. Par exemple, un sprite peut être importé
après la création d'une scène, et un script peut être ajouté dès que l'acteur existe.

## Commencer un projet

À l'ouverture, l'écran d'accueil propose vos projets récents et des modèles.

1. Cliquez sur **Créer un projet**.
2. Donnez-lui un nom et choisissez son emplacement.
3. Ouvrez-le : le **Scene Manager** devient l'espace de travail principal.

Le projet de démonstration Pong, disponible dans l'onglet des modèles, est un bon point de
départ pour observer une scène, un sprite, un script et du son déjà reliés.

Pour reprendre un projet existant, utilisez **Charger** depuis l'accueil ou **Fichier → Ouvrir
un projet**. Ouvrez toujours le dossier racine du projet, pas un sous-dossier `assets`.

## Se repérer dans l'éditeur

La barre de navigation ouvre les écrans spécialisés :

| Écran | Utilité |
| --- | --- |
| **Scene Manager** | Construire les scènes, placer les acteurs, collisions et éléments d'interface. |
| **Backgrounds** | Préparer les décors et les cadres d'interface. |
| **Sprites** | Découper une planche de sprites et composer les animations. |
| **Palettes** | Créer, importer et ajuster les couleurs partagées par le jeu. |
| **Text** | Écrire les textes affichés, préparer les traductions et les polices. |
| **Sound** | Ajouter les effets sonores, la musique et les transitions. |
| **Scripts** | Écrire le comportement et consulter l'API disponible. |
| **Data** | Définir des tableaux de données pour les objets, ennemis ou dialogues. |

Dans la plupart des écrans, la colonne de gauche liste les ressources, la zone centrale sert à
les modifier ou les prévisualiser, et l'inspecteur à droite règle l'élément sélectionné. Les
panneaux se redimensionnent en faisant glisser leurs séparateurs.

Quelques raccourcis utiles : `Ctrl+S` enregistre, `Ctrl+Z` annule, `Ctrl+Y` rétablit et `F5`
lance **Build & Run**. Les autres raccourcis peuvent être consultés et personnalisés dans
**Fichier → Réglages → Raccourcis**.

## Créer, importer, modifier : trois gestes distincts

Les sections de ressources utilisent le bouton **+**. Selon la famille, il crée une ressource,
ouvre un choix, ou lance un import. Une ressource nouvelle reçoit un nom provisoire que vous
pouvez modifier immédiatement ; `F2` renomme également une ressource sélectionnée.

- **Créer** convient aux scènes, prefabs, scripts, palettes, données et entrées audio : la
  ressource naît dans le projet, puis vous la configurez dans l'inspecteur.
- **Importer** copie un fichier source dans le dossier du projet et crée ou met à jour la
  ressource correspondante. L'original, hors du projet, n'est pas modifié.
- **Modifier** se fait dans l'écran de la ressource ou son inspecteur. Les changements sont
  enregistrés avec le projet et peuvent généralement être annulés avec `Ctrl+Z`.

Un clic droit sur une ressource donne accès à ses actions utiles, dont renommer, dupliquer quand
cela a du sens, voir ses utilisations ou supprimer. Supprimer demande confirmation ; si vous
venez de le faire, `Ctrl+Z` permet de revenir en arrière.

## Importer votre première ressource

Choisissez d'abord le type de ressource plutôt que de copier manuellement des fichiers dans le
projet : l'éditeur peut ainsi vérifier le format et préparer les métadonnées nécessaires.

| Vous avez… | Ouvrez… | Action |
| --- | --- | --- |
| Une planche de personnages ou d'objets en PNG | **Sprites** | Cliquez sur **+**, puis choisissez le PNG. Définissez ensuite la taille des frames et les animations. |
| Un décor, une image d'interface ou une planche animée PNG | **Backgrounds** | Utilisez le **+** de la section correspondante : décor, interface ou animation. |
| Une palette `.gpl`, `.pal` ou une liste de couleurs | **Palettes** | Cliquez sur **+**, puis **Importer**. |
| Un effet sonore WAV ou un morceau tracker | **Sound** | Créez l'effet ou la piste avec **+**, sélectionnez-le, puis utilisez **Importer** dans l'inspecteur. |
| Une police PNG ou `.fnt` | **Text** | Déposez le fichier dans `assets/fonts/` du projet ; l'éditeur le détecte et le rend disponible. |

Après un import, sélectionnez la ressource dans sa liste : l'inspecteur indique ce qui manque
éventuellement et les réglages à vérifier. Un avertissement de palette, de format ou de budget
ne modifie pas le fichier source ; il vous indique simplement ce que la ROM pourra utiliser.

## Construire une première scène

Dans le **Scene Manager**, créez une scène depuis la section **Scenes**. Son canvas représente
l'écran GBA. Ajoutez un acteur avec l'outil d'ajout, puis choisissez un sprite dans l'inspecteur
de l'acteur. Vous pouvez ensuite le déplacer avec l'outil de sélection, ajouter des collisions
ou lui attacher un script.

Le bandeau inférieur montre les ressources matérielles les plus importantes de la scène
(sprites, coût par ligne, tuiles et palettes). Elles deviennent jaunes puis rouges à
l'approche ou au dépassement d'une limite : prenez-les comme un tableau de bord, pas comme une
étape obligatoire avant de commencer.

Quand votre scène contient au moins ce que vous souhaitez tester, sauvegardez et cliquez sur
**Build & Run**. L'éditeur génère la ROM puis l'ouvre dans mGBA, si devkitPro et mGBA sont
configurés. L'écran d'accueil et **Fichier → Réglages** indiquent où les renseigner si besoin.

## Continuer

- Pour obtenir un premier résultat complet, suivez [Créer votre première scène jouable](first-playable-scene.md).
- Pour ajouter un décor, un sol et des murs, suivez [Ajouter un décor et des collisions](decor-and-collision.md).
- Pour ajouter gravité et saut, suivez [Créer un mouvement de plateforme](platformer-movement.md).
- Pour ajouter des objets à ramasser et un score, suivez [Ajouter des collectibles et un score](collectibles.md).
- Pour créer des PNJ, des dialogues et des adversaires, suivez [Ennemis et PNJ](enemies.md).
- Pour relier le titre, les niveaux et la victoire, suivez [Construire une boucle de gameplay](gameplay-loop.md).
- Pour construire un combat plus élaboré, suivez [Créer un boss et sa barre de vie](boss.md).
- Pour suivre l'acteur dans une grande scène, suivez [Faire suivre l'acteur par une caméra](camera-follow.md).
- Pour donner une réaction à un acteur, passez au [guide de scripting](../scripting.md).
- Pour comprendre les messages de compilation, commencez par lire le fichier et la ligne cités
  dans le panneau de build : l'erreur est généralement reliée à l'élément ou au script concerné.
- Cette documentation grandira ensuite avec des guides dédiés aux scènes, sprites, décors,
  texte, son et publication d'une ROM.
