# Construire une boucle de gameplay

Une boucle de gameplay donne un début, un objectif et une suite à votre niveau. Nous allons créer une scène de titre, une scène de niveau et une scène de victoire, puis les relier avec `scene.switch`.

## 1. Créer les scènes

Dans le **Scene Manager**, créez trois scènes : `Titre`, `Niveau1` et `Victoire`. Définissez `Titre` comme scène de départ depuis le graphe des scènes. Placez votre joueur, votre décor et vos collectibles dans `Niveau1`.

Le graphe montre les scènes atteignables et les sorties trouvées dans les scripts. C'est un bon moyen de repérer une scène sans arrivée ou une faute dans un nom de scène.

## 2. Créer une interface simple

Dans `Titre`, ajoutez une **Interface**, puis un élément **Texte** nommé `Invitation`. Créez dans l'écran **Text** l'entrée `titre_invitation`, par exemple `Appuyez sur A pour jouer`.

Ajoutez un script de scène à `Titre` :

```lua
function on_start()
    interface:get("Invitation"):draw("titre_invitation")
end

function on_update()
    if input:pressed("a") then
        scene:switch("Niveau1")
    end
end
```

Un script de scène n'est attaché à aucun acteur : il convient aux règles qui concernent tout le niveau, comme le démarrage, le HUD ou un changement de scène.

## 3. Déclencher la victoire

Créez dans `Niveau1` une zone de sortie : un acteur avec une boîte **Collision** en mode **Trigger** et ce script :

```lua
function on_collision_enter(other, my_box, other_box)
    if other.tag == "Joueur" then
        scene:switch("Victoire")
    end
end
```

Dans `Victoire`, ajoutez un texte de félicitations et un script qui retourne vers `Titre` quand le joueur appuie sur `A`.

## 4. Ajouter une transition

Ouvrez **Fichier → Réglages du projet** et choisissez une transition de scène, puis sa durée. Ce réglage s'applique à toutes les scènes. Vous pouvez aussi sélectionner une scène et remplacer ce choix dans son inspecteur, par exemple pour faire apparaître `Victoire` plus lentement.

`scene:switch("Niveau1")` effectue le changement au début de la frame suivante ; la transition choisie masque ce rechargement.

## Continuer

Votre jeu possède maintenant une structure. Passez à [Créer un boss](boss.md).
