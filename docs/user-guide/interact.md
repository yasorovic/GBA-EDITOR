# Faire interagir le joueur avec un acteur

Ce guide explique comment réagir à un appui devant un coffre, un panneau ou un personnage, sans écrire de code qui s'exécute à chaque frame. Nous allons désigner le joueur, rendre un coffre interactif, puis choisir le geste et la façon d'atteindre la zone.

Le principe tient en trois pièces : le **joueur** est l'acteur qui interagit, le composant **Interactive** rend un acteur interactif, et l'événement `on_interact` est appelé sur le script de cet acteur quand l'interaction a lieu.

## 1. Désigner le joueur

Sélectionnez l'acteur que le joueur pilote et cochez **Player** dans l'inspecteur, juste sous **Active on start**. Dans un projet neuf, l'acteur de la scène de départ l'est déjà. C'est un tag d'**acteur**, à ne pas confondre avec les tags de collision (ceux des boîtes) : seul un acteur qui le porte déclenche les interactions de la scène. Plusieurs acteurs peuvent le porter ; chacun interagit avec la zone qu'il atteint.

Un **prefab** peut lui aussi être le joueur : sélectionnez-le et cochez la même case. Les instances créées ensuite le sont, et **Expose to Prefab** ou **Relink to prefab** reportent le tag dans un sens ou dans l'autre. Comme les autres paramètres d'instance, modifier un prefab n'en change pas les instances déjà posées. Une partie d'un prefab (un enfant) n'a pas la case.

Le joueur n'a pas besoin d'un sprite : son regard est suivi même sans lui.

Si une scène contient des acteurs interactifs mais aucun joueur, le build l'indique dans les diagnostics.

## 2. Rendre un coffre interactif

Ajoutez un acteur pour le coffre, puis **+ Component → Interactive**. Il n'y a qu'un composant Interactive par acteur. Ajoutez ensuite un composant **Script** et écrivez :

```lua
function on_interact(who)
    self:hide()
end
```

`self` est le coffre et `who` l'acteur qui interagit, c'est-à-dire le joueur. Le moteur n'appelle `on_interact` que sur un acteur dont le script la définit : un coffre sans cette fonction ne coûte rien. Si le composant et le script ne vont pas ensemble (un composant sans `on_interact`, ou l'inverse), le build vous prévient.

Lancez **Build & Run** : approchez le joueur du coffre et appuyez sur **A**.

## 3. Choisir le geste

Le sélecteur **Input** du composant choisit le geste, sur l'entrée interne `interact` :

| Geste | L'appel a lieu… |
| --- | --- |
| **Pressed** | à la frame où l'entrée s'abaisse. |
| **Held** | quand l'entrée est tenue depuis le nombre de frames réglé (**Hold**), une seule fois. |
| **Released** | quand l'entrée remonte, **si** le joueur est encore dans la zone. Sinon, rien ne se passe. |

L'entrée `interact` existe dans tous les projets, sur le bouton **A** par défaut. Pour la déplacer, ouvrez **Project Settings → Input** : sa ligne, verrouillée en tête de la carte Inputs, accepte n'importe quel bouton ou un accord de plusieurs (par exemple haut + A). Son nom ne se change pas, et le build refuse une entrée, un axe ou une séquence qui s'appelle aussi `interact`. Un script peut la lire comme les autres entrées : `input:pressed("interact")`.

## 4. Choisir comment atteindre la zone

Le sélecteur **Interaction** dit comment le joueur atteint la zone :

- **Hover** : le joueur recouvre la zone. C'est le cas d'un objet qu'on traverse ou qu'on touche.
- **Facing** : la boîte du joueur, étendue dans la direction où il regarde, touche la zone. C'est le cas d'un coffre ou d'un panneau devant lequel on s'arrête. Un mur de la carte de collision entre le joueur et la zone empêche l'interaction.

La **portée** de la visée se règle dans **Project Settings → Input**, à côté de la ligne `interact` (4 px par défaut, un réglage unique pour le projet). Un joueur qui n'a encore regardé nulle part n'atteint rien en mode Facing.

Le regard est `facing` : la dernière direction non nulle du joueur, conservée quand il s'arrête. Il suit automatiquement le mouvement (`facing_auto`, coché par défaut) et un script peut le lire ou l'écrire, `self.facing = vec2(0, -1)` ou `self.facing = "north"`. Ne le confondez pas avec `direction`, qui est la trajectoire et retombe à 0 à l'arrêt.

## 5. La zone

Le sélecteur **Zone** dit d'où vient la zone d'interaction :

- **Own box (Interactive)** : le composant crée sa propre boîte, sans que vous en dessiniez une. Elle fait 16 × 16 px sans sprite, sinon la taille du cadre du sprite, et vous pouvez imposer une largeur et une hauteur. Au canvas, elle est dessinée en jaune dès que l'acteur est sélectionné. Elle porte le tag de collision **Interactive**, réservé : il n'est ni renommable ni supprimable dans **Project Settings → Collisions**, mais ses cases de matrice restent réglables.
- **Une boîte existante** de l'acteur, désignée par son tag : utile quand le coffre a déjà une boîte de la bonne taille, ou quand la zone doit être plus grande que son sprite. Le build refuse une boîte qui n'existe pas sur l'acteur.

La boîte propre occupe un des quatre emplacements de boîtes d'un acteur ; si l'acteur est déjà plein, le build le dit.

## 6. Plusieurs zones à la fois

Quand plusieurs zones sont atteintes au même appui, seule **la plus proche du joueur** reçoit l'appel. Deux panneaux côte à côte ne se déclenchent donc pas ensemble.

## À savoir

- L'option **Solid** d'une boîte ne concerne que la carte de collision : par défaut, le joueur traverse un coffre. La boîte propre d'un composant Interactive en mode **Facing** bloque déjà les acteurs (c'est un obstacle contre lequel on s'arrête pour le viser), et celle d'un composant en mode **Hover** ne bloque pas (on doit pouvoir la recouvrir). Pour bloquer avec une autre boîte, ajoutez-la à l'acteur et cochez **Blocks actors** (ligne **Blocking**). Un acteur en mouvement qui a une boîte **Solid** est alors repoussé hors de cette boîte, et il glisse le long de l'obstacle en diagonale ; la carte de collision garde le dernier mot, donc le joueur ne peut pas être poussé dans un mur. La matrice de collision (**Project Settings → Collisions**) décide quels tags sont arrêtés par quels autres. La zone d'interaction reste une boîte à part : en mode **Facing**, elle est atteinte sans que le joueur ait besoin de la recouvrir, même arrêté contre le coffre.
- Le blocage repousse la position et ne touche pas la vitesse : un script qui ajoute la gravité à chaque frame doit la remettre à zéro lui-même quand l'acteur est posé sur un obstacle. Il est donc pensé d'abord pour une vue de dessus.
- L'appui n'est pas « consommé » : si un script lit aussi `interact` (pour fermer un dialogue, par exemple), il voit le même appui que le composant. Réservez un geste ou un bouton distinct pour cet autre usage.

## Continuer

Pour donner un dialogue à un personnage, suivez [Ennemis et PNJ](enemies.md). Pour afficher le résultat d'une interaction, voir [Ajouter des collectibles et un score](collectibles.md).
