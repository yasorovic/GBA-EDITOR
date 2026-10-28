# Caméra

Ce guide fait suivre un acteur par la caméra dans une scène plus grande que l'écran de la Game Boy
Advance (240 × 160 pixels). La caméra détermine la partie de la scène que le joueur voit. Pour un
suivi simple, aucun script n'est nécessaire.

**Ce qu'il vous faut :** une scène plus grande que l'écran, avec un acteur que vous pouvez
déplacer (voir [Déplacer un acteur](deplacer-acteur.md)).

## 1. Créer une caméra

Dans l'écran **Scenes**, ouvrez le menu **+** de l'arbre de la scène et ajoutez une **Camera**.
Donnez-lui un nom, par exemple `Joueur`, puis sélectionnez-la. Dans la carte **This camera** de
l'inspecteur, choisissez-la comme **Starting camera** : elle sera active au lancement de la scène.

## 2. Suivre l'acteur

Dans l'inspecteur de la caméra :

1. choisissez le mode **Follow an Actor** ;
2. sélectionnez votre acteur dans la liste de suivi ;
3. commencez avec des marges de `40` pixels sur X et `20` pixels sur Y.

La caméra ne bouge pas tant que l'acteur reste dans cette zone centrale. Les marges évitent que
le cadre ne bouge à chaque pixel parcouru. Réduisez-les pour un suivi plus serré, augmentez-les
pour laisser plus d'espace devant le joueur.

## 3. Définir les limites du monde

Dans la carte **World bounds**, donnez la taille de la zone jouable. Si vos décors couvrent déjà
toute la scène, **Recompute from backgrounds** propose ces valeurs. Les limites empêchent la
caméra de montrer l'extérieur du monde. Pour une scène de 640 × 320 pixels qui commence à
l'origine :

```text
Origin : X 0, Y 0
Size   : W 640, H 320
```

Laissez une dimension à `0` seulement si la caméra doit défiler sans limite sur cet axe.

## 4. Tester

Lancez **Run** et déplacez l'acteur vers le bord de l'écran :

- la caméra commence à suivre quand l'acteur atteint la marge ;
- elle s'arrête au bord de la zone définie ;
- le cadre ne révèle aucune zone vide hors du décor.

Le rectangle de la caméra, visible sur le canvas, est déplaçable : il sert à choisir le cadrage de
départ, le mode de suivi prend ensuite le relais pendant le jeu.

## Quand écrire un script de caméra ?

Le suivi déclaratif convient à la majorité des scènes. Un script de caméra devient utile pour un
comportement particulier : cinématique, changement de cadrage, secousse. Les fonctions
disponibles sont regroupées dans le panneau **API** du Script Editor, sous **Caméra**.
