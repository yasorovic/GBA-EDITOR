# Textes et dialogues

Ce guide explique comment écrire des textes, les afficher dans une zone de l'interface, leur donner
un rythme et les traduire. L'exemple est un villageois qui change de réplique à la seconde rencontre.

**Ce qu'il vous faut :** une scène avec un acteur pour le villageois et un sprite.

## 1. Une zone de dialogue

Ajoutez à la scène une **Interface**, puis un élément **Texte** nommé `Dialogue`. Cette zone est
l'endroit où les répliques s'affichent. Sa position, sa taille, sa police et son habillage se
règlent visuellement dans l'éditeur, pas dans le script.

Donnez ensuite au villageois une boîte **Collision** en mode **Trigger**, assez large pour couvrir
la zone où le joueur doit venir lui parler.

## 2. Écrire les textes

Ouvrez l'écran **Texts** et créez les entrées. La **clé** sert au script ; le **contenu** est ce que
le joueur lit.

| Clé | Texte |
| --- | --- |
| `villageois_bonjour` | Bonjour, voyageur ! [pause=20] La forêt est dangereuse. |
| `villageois_apres_bonjour` | Tu es déjà prêt à partir ? |

Les balises règlent le rendu : `[pause=20]` crée une courte pause, et `[speed=4]` en tête d'un texte
le fait apparaître comme une machine à écrire. Préfixer les clés par `villageois_` les garde
regroupées quand le projet contient beaucoup de dialogues.

Un texte peut aussi contenir une valeur du jeu avec un marqueur `$nom` (voir
[Variables et affichage](variables-affichage.md)).

## 3. Afficher une réplique

```lua
local rencontre = 0

function on_collision_enter(other, my_box, other_box)
    if other.name ~= "Joueur" then
        return
    end

    if rencontre == 0 then
        interface:get("Dialogue"):draw("villageois_bonjour")
        rencontre = 1
    else
        interface:get("Dialogue"):draw("villageois_apres_bonjour")
    end
end
```

`on_collision_enter` est appelé à la première frame de contact entre deux boîtes. Remplacez
`"Joueur"` par le nom de votre acteur joueur. `rencontre` retient où en est la discussion : `0` avant
la première réplique, `1` après.

Pour une troisième étape, créez une clé telle que `villageois_quete`, ajoutez
`elseif rencontre == 1 then`, puis passez `rencontre` à `2`. Gardez les clés et les conditions dans
le même ordre : c'est la forme la plus simple d'un arbre de dialogue.

`rencontre` est remise à zéro quand la scène est rechargée. Pour que le villageois se souvienne
après un changement de scène, utilisez une globale (par exemple `global.villageois_rencontre`) à la
place. Cochez **Persist** pour la conserver aussi après l'extinction de la console.

## 4. Traduire

Dans les réglages du projet, ajoutez une langue, par exemple l'anglais. L'écran **Texts** affiche
alors une colonne par langue : conservez les clés et écrivez la traduction dans la colonne
correspondante.

Le script ne change pas : il demande toujours `"villageois_bonjour"`, et c'est l'éditeur qui choisit
la version de la langue active. Les clés décrivent donc l'intention (`villageois_bonjour`), jamais le
texte français lui-même.

## À savoir

- Un texte écrit directement dans le script (`draw("Bonjour")`) devient une entrée interne : il
  n'apparaît pas dans l'écran **Texts** et ne peut pas être traduit. Dès qu'une langue est déclarée,
  le Build le signale par un avertissement.
- Pour un dialogue déclenché par un appui plutôt que par un contact, combinez ce guide avec
  [Interaction](interaction.md).
