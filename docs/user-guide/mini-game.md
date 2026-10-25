# Tutoriel : un mini-jeu de plateforme

Ce tutoriel assemble plusieurs [guides](../guides/index.md) en un jeu complet : un personnage
traverse un niveau, ramasse des pièces et atteint la sortie. Il ne réexplique pas chaque geste :
chaque étape renvoie au guide qui le détaille.

Prérequis : avoir suivi [Votre première scène jouable](first-playable-scene.md), avec un sprite de
personnage, un sprite de pièce et un décor PNG.

## 1. Le niveau et le personnage

Créez une scène `Niveau`. Ajoutez le décor, peignez le sol et les murs dans la carte de collision, puis
donnez au personnage une boîte **Collision** en mode **Solid** :
[Décors et collisions](../guides/decors-collisions.md).

## 2. Marcher et sauter

Donnez au personnage le script de déplacement avec gravité et saut :
[Gravité et saut](../guides/gravite-saut.md). Vérifiez avec **Run** qu'il marche, saute et s'arrête
contre les murs.

## 3. Une caméra

Si votre niveau est plus large que l'écran, ajoutez une caméra qui suit le personnage :
[Caméra](../guides/camera.md).

## 4. Des pièces

Transformez une pièce en prefab, avec une boîte **Collision** en mode **Trigger**, et placez-en
plusieurs : [Prefabs et instances](../guides/prefabs.md). Son script ramasse la pièce au contact et
incrémente un score global :

```lua
function on_collision_enter(other, my_box, other_box)
    if other.name == "Joueur" then
        global.score = global.score + 1
        self:destroy()
    end
end
```

Remplacez `"Joueur"` par le nom de votre personnage. La globale `score` se déclare dans l'écran
**Scripts**, section **Globals**.

## 5. Afficher le score

Créez l'entrée de texte `Score : $score`, une zone de texte dans l'interface de la scène, et
affichez-la au démarrage : [Variables et affichage](../guides/variables-affichage.md).

## 6. La sortie

Ajoutez un acteur de sortie avec une boîte **Trigger** qui appelle `scene:switch("Victoire")` quand
le joueur la touche, puis une scène `Victoire` : [Scènes et transitions](../guides/scenes-transitions.md).

## Et ensuite

Ajoutez des ennemis qui patrouillent ([Machines d'état](../guides/etats.md)), des projectiles
([Créer des acteurs pendant le jeu](../guides/acteurs-au-vol.md)), des points de vie
([Santé et dégâts](../guides/sante-degats.md)) et des dialogues
([Textes et dialogues](../guides/textes-dialogues.md)).
