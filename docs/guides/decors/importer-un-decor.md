# Importer un décor

Cette page conduit une image de décor jusqu'à l'écran du jeu : choisir le bon fichier, l'importer, vérifier
l'import, l'affecter à une scène, puis la faire bouger avec un script.

**Ce qu'il vous faut :** un projet avec une scène, et une image de décor au format PNG.

## 1. Le format accepté

Un décor se prépare à partir d'un fichier **PNG**. C'est le seul format que l'éditeur accepte pour créer un
fond.

- **Le fichier n'est jamais modifié.** L'éditeur garde votre PNG tel quel et range à côté de lui le résultat
  de la conversion (les tuiles, les palettes et la carte, voir [Qu'est-ce qu'une tilemap ?](tilemap.md)).
- **Les couleurs.** Une image dont la palette est déjà compatible avec la console est conservée à
  l'identique. Sinon, l'éditeur réduit le nombre de couleurs : il peut y en avoir jusqu'à 16 palettes de 16
  couleurs, choisies tuile par tuile.
- **La taille.** Une image plus grande que l'écran (240 × 160 pixels) est un décor qui défile avec la caméra.

## 2. Importer l'image

Deux chemins mènent au même résultat.

**Depuis l'écran Backgrounds.** Ouvrez **Backgrounds**, puis cliquez sur le **+** de la section qui
correspond à l'emploi : un décor de scène, une image d'interface ou une planche animée. Choisissez le PNG.

**Depuis le dossier `assets`.** Déposez le PNG dans le projet (onglet **Disk**, **Import...**, ou glissez-déposez),
faites un clic droit sur le fichier, puis **Create** et **Background**.

Pour le détail des deux chemins, voir [Importer sa première ressource](../../user-guide/overview/first-import.md).

## 3. Vérifier l'import

Sélectionnez le fond dans la liste de l'écran **Backgrounds**. L'inspecteur indique ce qui manque
éventuellement, et les réglages à vérifier. Un avertissement de palette, de format ou de budget ne modifie pas
votre fichier : il indique seulement ce que la ROM pourra utiliser.

## 4. L'affecter à une scène

Un fond importé ne s'affiche pas tout seul : une scène doit l'employer. Dans l'inspecteur de la scène, section
**Background layers**, choisissez ce fond pour un des **calques** (**BG0** à **BG3**). L'image apparaît dans le
canvas. La différence entre le fond et le calque est expliquée dans
[Fond et calque](fond-et-calque.md).

## 5. Un petit script : faire défiler le décor

Ajoutez un script à la scène (**Add a scene script**, dans l'inspecteur de la scène), puis écrivez :

```lua
function on_update()
    layer:get(1):scroll_by(1, 0)
end
```

`layer:get(1)` désigne le calque **BG1** de la scène, et `scroll_by(1, 0)` le décale d'un pixel vers la droite à
chaque image. Choisissez le numéro du calque qui porte votre décor. Lancez **Run** : le décor défile.

## À savoir

- Le numéro donné à `layer:get` est celui du calque dans l'inspecteur de la scène (de 0 à 3), pas le nom de
  l'image.
- Pour que les acteurs ne traversent pas le décor, il faut aussi peindre une carte de collision : voir
  [Collisions](../acteurs/collisions.md).
- Les fonctions disponibles sur un calque sont dans le [groupe Layer](../../lua-api/api/scene/layer.md) du
  catalogue de l'API.
