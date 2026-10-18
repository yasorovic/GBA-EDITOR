# Faire suivre l'acteur par une caméra

Ce guide reprend après [Créer un mouvement de plateforme](platformer-movement.md). Votre acteur
peut maintenant explorer une scène plus grande que l'écran de la Game Boy Advance, qui mesure
240 × 160 pixels.

La caméra détermine la partie de cette scène que le joueur voit. Pour un suivi simple, aucun
script n'est nécessaire.

## 1. Créer une caméra

Dans le **Scene Manager**, ouvrez le menu **+** de l'arbre de la scène et ajoutez une
**Camera**. Donnez-lui un nom, par exemple `Joueur`, puis sélectionnez-la.

Dans la carte **This camera** de l'inspecteur, choisissez-la aussi comme **Starting camera**.
Elle sera alors active au lancement de la scène.

## 2. Suivre l'acteur

Dans l'inspecteur de la caméra :

1. choisissez le mode **Follow an Actor** ;
2. sélectionnez votre acteur dans la liste de suivi ;
3. commencez avec des marges de `40` pixels sur X et `20` pixels sur Y.

La caméra ne se déplace pas tant que l'acteur reste dans cette zone centrale. Les marges évitent
que le cadre bouge à chaque pixel parcouru. Réduisez-les pour un suivi plus serré, augmentez-les
pour laisser davantage d'espace devant le joueur.

## 3. Définir les limites du monde

Dans la carte **World bounds**, donnez la taille de votre zone jouable. Si vos décors couvrent
déjà toute la scène, utilisez **Recompute from backgrounds** pour proposer ces valeurs.

Les limites empêchent la caméra de montrer l'extérieur du monde. Pour une scène de 640 × 320
pixels qui commence à l'origine, utilisez :

```text
Origin : X 0, Y 0
Size   : W 640, H 320
```

Laissez une dimension à `0` seulement si vous souhaitez que la caméra puisse défiler sans limite
sur cet axe.

## 4. Tester le suivi

Lancez **Build & Run**, puis déplacez l'acteur vers le bord de l'écran :

- la caméra commence à suivre l'acteur lorsqu'il atteint la marge ;
- elle s'arrête au bord de la zone définie ;
- le cadre ne doit pas révéler une zone vide hors du décor.

Le rectangle de caméra visible dans le canvas est également déplaçable. C'est utile pour choisir
le cadrage de départ, mais le mode de suivi prendra ensuite le relais pendant le jeu.

## Quand écrire un script de caméra ?

Le suivi déclaratif convient à la majorité des scènes. Vous pourrez ajouter un script de caméra
lorsque vous voudrez un comportement particulier, par exemple une cinématique, un changement de
cadrage ou une secousse. Les fonctions disponibles sont regroupées dans le panneau **API** du
Script Editor, sous **Caméra**.

Votre scène possède maintenant un personnage jouable, des collisions, un saut et une caméra.
La suite naturelle est d'ajouter une animation qui reflète son déplacement.
