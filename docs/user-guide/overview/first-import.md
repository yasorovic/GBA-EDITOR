# Importer votre première ressource

Deux chemins mènent au même résultat : une ressource utilisable dans le projet. Le premier part
de l'écran de la ressource, le second du dossier **assets**. Dans les deux cas, le fichier
d'origine, hors du projet, n'est pas modifié.

Cette page suit un exemple : une planche de personnage au format PNG.

## Chemin 1 : depuis l'éditeur

C'est le chemin le plus court. L'éditeur copie le fichier dans le projet, vérifie son format et
crée la ressource en une seule fois.

1. Ouvrez l'écran qui correspond au fichier : **Animations** pour un sprite.
2. Dans la liste **Sprites**, cliquez sur **+** et choisissez le PNG. Plusieurs fichiers peuvent
   être choisis à la fois.
3. Sélectionnez le sprite dans la liste. Dans l'inspecteur, réglez **Canvas size** (la taille
   d'une frame), puis composez les animations dans la timeline.

```{figure} img/animations-screen.png
:alt: Un sprite importé dans l'écran Animations, avec sa timeline de quatre frames.
:class: backstage-screenshot

Un sprite importé : la frame au centre, la planche à droite de la frame, la timeline en bas.
```

Le **+** existe sur chaque écran de ressources :

| Vous avez... | Ouvrez... | Action |
| --- | --- | --- |
| Une planche de personnages ou d'objets en PNG | **Animations** | **+** de la liste des sprites. |
| Un décor, une image d'interface ou une planche animée | **Backgrounds** | **+** de la section correspondante. |
| Une palette `.gpl`, `.pal` ou une liste de couleurs | **Palettes** | **+**, puis **Import**. |
| Un effet sonore WAV ou un morceau tracker | **Sounds** | Créez l'entrée avec **+**, puis **Import** dans l'inspecteur. |

## Chemin 2 : depuis le dossier assets

Ce chemin convient quand vous préparez beaucoup de fichiers à la fois, ou que vous les rangez
déjà dans votre propre arborescence. Il se fait en deux temps : le fichier **entre** dans le
projet, puis vous décidez **ce qu'il devient**.

1. **Faites entrer le fichier.** Copiez-le dans le dossier `assets/` (par l'explorateur du
   système) ou, dans l'onglet **Disk**, utilisez **Import...** ou glissez-déposez le fichier. Il
   apparaît avec un point jaune : c'est une source sans ressource.
2. **Créez la ressource.** Faites un clic droit sur le fichier et choisissez **Create as**, puis la
   famille voulue (**Sprite**, **Background**, **Sound effect**, **Music**, **Font**,
   **Palette**...). Le menu ne propose que les familles possibles pour ce format. La ressource naît
   à côté de sa source.

```{figure} img/disk-create-as.png
:alt: L'onglet Disk avec une source à point jaune sélectionnée et le menu clic droit Create as : Sprite, Background, Font.
:class: backstage-screenshot

Clic droit sur une source : **Create as** propose les familles possibles pour ce fichier.
```

Sélectionner plusieurs sources du même format permet d'en créer plusieurs ressources en un geste.

```{note}
Une police se prépare toujours par ce chemin : un fichier PNG, `.fnt`, `.ttf` ou `.otf`
déposé dans le projet n'est pas une police tant que vous ne l'avez pas créée avec **Create as**.
```

## Vérifier l'import

Dans les deux cas, sélectionnez la ressource dans sa liste : l'inspecteur indique ce qui manque
éventuellement et les réglages à vérifier. Un avertissement de palette, de format ou de budget ne
modifie pas le fichier source ; il indique seulement ce que la ROM pourra utiliser.

Si un fichier de même nom existe déjà dans le dossier, l'éditeur demande s'il faut écraser, garder
les deux ou annuler. Tout autre nom déjà pris est complété (`coin_2`) sans question.

Suite : [Tutoriel : votre première scène jouable](../first-playable-scene.md).
