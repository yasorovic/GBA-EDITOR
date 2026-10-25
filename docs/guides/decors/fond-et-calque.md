# Fond et calque : quelle différence ?

L'éditeur emploie deux mots qui se ressemblent : le **fond** (*background*) et le **calque** (*background
layer*). Ils ne désignent pas la même chose, et les distinguer évite de nombreuses confusions.

**Ce qu'il vous faut :** un décor importé et une scène (voir [Importer un décor](importer-un-decor.md)).

## 1. Le fond : l'image importée

Un **fond** est la ressource que vous importez depuis l'écran **Backgrounds**. Il correspond à **un fichier
PNG**, et porte le résultat de sa conversion : les tuiles, les palettes et la carte (voir
[Qu'est-ce qu'une tilemap ?](tilemap.md)). Il peut servir de décor de scène, d'image d'interface ou de planche
animée.

Un fond appartient au **projet**. Il ne sait pas dans quelles scènes il sert.

## 2. Le calque : l'emploi d'un fond dans une scène

Un **calque** est l'emploi d'un fond dans **une scène**. Il appartient à la scène, comme un acteur y est placé,
et il désigne le fond qu'il montre par son nom. Il porte les réglages qui ne concernent que cette scène :

- **l'emplacement matériel**, de **BG0** à **BG3** : la console superpose jusqu'à quatre fonds tuilés ;
- **la vitesse de défilement**, relative à la caméra, qui produit l'effet de profondeur (parallaxe) ;
- **la banque de palette** que le calque emploie ;
- **sa visibilité** dans l'éditeur.

## 3. Pourquoi deux notions

L'image est préparée une seule fois, le calque dit seulement comment une scène s'en sert. Le même fond peut
donc servir dans deux scènes avec des réglages différents : un ciel qui défile lentement dans un niveau, et
immobile dans un autre.

| | Fond | Calque |
| --- | --- | --- |
| Ce que c'est | l'image importée et sa conversion | l'emploi d'un fond dans une scène |
| Où il vit | dans le projet, écran **Backgrounds** | dans la scène, section **Background layers** |
| Ce qu'il porte | tuiles, palettes, carte | emplacement BG0 à BG3, vitesse, palette |
| Combien | autant que vous importez d'images | jusqu'à quatre par scène |

## 4. Dans un script

Un script parle toujours du **calque**, jamais du fond : on désigne un calque par son **numéro**, de 0 à 3, celui
qu'affiche l'inspecteur de la scène.

```lua
function on_start()
    layer:get(2):hide()                 -- cache le calque BG2
    layer:get(1).scroll_speed = 50      -- le calque BG1 défile à moitié de la vitesse de la caméra
end
```

Les réglages d'un calque (`scroll`, `scroll_speed`, `priority`, `visible`, `pal_bank`) et les fonctions
(`show`, `hide`, `scroll_by`) sont dans le [groupe Layer](../../lua-api/api/scene/layer.md) du catalogue de l'API.

## À savoir

- Changer l'image d'un fond change l'image de **tous** les calques qui l'emploient, dans toutes les scènes.
- Changer le réglage d'un calque ne change que **cette** scène.
