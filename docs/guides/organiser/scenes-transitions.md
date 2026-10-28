# Scènes et transitions

Ce guide relie plusieurs scènes entre elles : un écran de titre, un niveau, un écran de victoire,
avec une transition entre chacun.

**Ce qu'il vous faut :** un projet vide suffit. L'exemple crée trois scènes et un acteur de
sortie.

## 1. Créer les scènes

Dans l'écran **Scenes**, créez trois scènes : `Titre`, `Niveau`, `Victoire`. Définissez `Titre`
comme scène de départ depuis le graphe des scènes (onglet **Graph** au-dessus du canvas).

Le graphe montre les scènes atteignables et les sorties trouvées dans les scripts. C'est un bon
moyen de repérer une scène sans arrivée, ou une faute dans le nom d'une scène.

## 2. L'écran de titre

Dans `Titre`, ajoutez une **Interface** avec un élément **Texte** nommé `Invitation`. Créez dans
l'écran **Texts** l'entrée `titre_invitation`, par exemple `Appuyez sur A pour jouer`. Ajoutez un
script de scène :

```lua
function on_start()
    interface:get("Invitation"):draw("titre_invitation")
end

function on_update()
    if input:pressed("a") then
        scene:switch("Niveau")
    end
end
```

Un script de scène n'est attaché à aucun acteur : il convient aux règles qui concernent tout le
niveau (démarrage, affichage, changement de scène).

## 3. Déclencher la victoire

Dans `Niveau`, créez une zone de sortie : un acteur avec une boîte **Collision** en mode
**Trigger** et ce script :

```lua
function on_collision_enter(other, my_box, other_box)
    if other.name == "Joueur" then
        scene:switch("Victoire")
    end
end
```

Dans `Victoire`, ajoutez un texte de félicitations et un script de scène qui appelle
`scene:switch("Titre")` quand le joueur appuie sur `A`. La boucle est fermée.

## 4. Ajouter une transition

Ouvrez **Game → Project Settings** et choisissez une transition de scène, puis sa durée : ce réglage
s'applique à toutes les scènes. Sélectionnez une scène pour remplacer ce choix dans son
inspecteur, par exemple pour faire apparaître `Victoire` plus lentement.

`scene:switch("Niveau")` effectue le changement au début de la frame suivante, et la transition
choisie masque le rechargement.

## À savoir

- Les noms d'acteurs sont locaux à leur scène, et une seule scène est active à la fois. Pour garder une
  valeur d'une scène à l'autre (un score, une clé ramassée), utilisez une globale
  ([Variables et affichage](variables-affichage.md)).
- Une variable `local` d'un script repart de zéro quand la scène est rechargée.
