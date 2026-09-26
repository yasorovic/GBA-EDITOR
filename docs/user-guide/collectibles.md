# Ajouter des collectibles et un score

Ce guide reprend après [Créer un mouvement de plateforme](platformer-movement.md). Nous allons créer une pièce ramassable, en faire un **prefab** réutilisable, puis afficher un score partagé par la scène.

## 1. Préparer une variable de score

Ouvrez l'écran **Scripts**. Dans la section **Globals**, cliquez sur **+**, puis donnez à la nouvelle variable le nom `score` et la valeur par défaut `0`.

Une globale appartient au projet, pas à un acteur : le joueur, une pièce et l'interface peuvent donc tous lire ou modifier `global.score`. Ne cochez **Persist** que si vous souhaitez garder le score après avoir éteint la console.

## 2. Créer une pièce et l'exposer comme prefab

Dans le **Scene Manager**, ajoutez un acteur, choisissez le sprite de votre pièce et ajoutez-lui une boîte **Collision** en mode **Trigger**. Avec la pièce sélectionnée, utilisez **Expose to Prefab** dans l'inspecteur, puis nommez le prefab `Piece`.

Ajoutez un composant **Script** au prefab et créez `Piece.lua` :

```lua
function on_collision_enter(other, my_box, other_box)
    if other.tag == "Joueur" then
        global.score = global.score + 1
        self:destroy()
    end
end
```

`on_collision_enter` n'est appelé qu'à la première frame de contact : le score ne peut donc pas augmenter à chaque image. Remplacez `"Joueur"` par le nom de votre acteur joueur ou de son prefab.

## 3. Placer plusieurs pièces

Ajoutez plusieurs instances du prefab `Piece` dans la scène et déplacez-les sur le canvas. Elles gardent le même comportement ; modifier le prefab met à jour ses instances liées.

Lancez **Build & Run**. Si une pièce ne réagit pas, vérifiez que le joueur et la pièce ont chacun une boîte de collision active, et que le script est attaché au prefab.

## 4. Afficher le score

Créez dans l'écran **Text** une entrée `hud_score` dont le contenu est :

```text
Score : $score
```

Ajoutez une **Interface** à la scène, puis un élément **Texte** nommé `Score`. Dans le script de scène, affichez l'entrée au démarrage :

```lua
function on_start()
    interface:get("Score"):draw("hud_score")
end
```

Le marqueur `$score` lit la valeur de `global.score` lorsque le texte est rendu. Il n'est donc pas nécessaire de redessiner le HUD à chaque frame.

## Continuer

Votre niveau contient désormais des objectifs et un score. Passez à [Ajouter des ennemis](enemies.md).
