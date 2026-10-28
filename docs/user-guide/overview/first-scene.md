# Construire une première scène

Une scène est un écran de jeu : des décors, des acteurs, des collisions, de l'interface. Cette
page pose les gestes de base et se termine par un premier lancement. Elle suppose qu'un sprite a
déjà été importé (voir [Importer votre première ressource](first-import.md)).

## 1. Créer la scène

Ouvrez l'écran **Scenes**. Dans la **Scene library**, section **Scenes**, cliquez sur **+** et
donnez un nom à la scène, par exemple `PremiereScene`. Elle devient la scène active : son
contenu apparaît en haut de la colonne de gauche, son canvas au centre.

Le canvas montre la scène à l'échelle de la console, dont l'écran fait 240 x 160 pixels. Sans rien de sélectionné, l'inspecteur
règle la scène elle-même : son mode, ses calques de décor, sa musique, sa transition.

## 2. Ajouter un acteur

Dans la barre d'outils verticale du canvas, choisissez l'outil d'ajout (le **+** dans un cercle),
puis cliquez dans la scène. Repassez ensuite sur l'outil de sélection (la flèche) et cliquez sur
l'acteur : l'inspecteur change pour afficher ses réglages.

```{figure} img/actor-selected.png
:alt: Un acteur sélectionné : son nom dans l'inspecteur, avec les sections Transform, Components et Relations.
:class: backstage-screenshot

Un acteur sélectionné : l'inspecteur montre sa **Transform**, ses **Components** et ses **Relations**.
```

Choisissez son sprite dans l'inspecteur, puis déplacez-le avec l'outil de sélection. Les
**Components** ajoutent du comportement : une boîte de collision, un script...

## 3. Ajouter un décor

Un décor se place par les calques **BG0** à **BG3** de l'inspecteur de la scène. Chaque calque
reçoit un background importé depuis l'écran **Backgrounds**. Le guide
[Collisions](../../guides/acteurs/collisions.md) détaille ce geste.

## 4. Surveiller le budget matériel

La barre du bas de la fenêtre suit les limites de la console pour cette scène : nombre de
sprites, tuiles, palettes, mémoire. Une valeur passe au jaune puis au rouge à l'approche d'une
limite. Elle ne bloque rien : prenez-la comme un tableau de bord.

## 5. Lancer la ROM

Enregistrez avec `Ctrl+S`, puis cliquez sur **Run** (`F5`). L'éditeur génère la ROM et l'ouvre
dans mGBA. Il faut pour cela que devkitPro et mGBA soient configurés : l'écran d'accueil et
**File → Settings** indiquent où les renseigner.

Lancer souvent est un bon réflexe : vérifiez chaque étape avant d'ajouter la suivante. En cas
d'échec, l'onglet **Diagnostics** du panneau du bas cite le fichier et la ligne concernés.

## Et ensuite

Pour un premier résultat complet, avec un acteur qui répond aux touches, suivez
[Créer votre première scène jouable](../first-playable-scene.md).
