# Variables et affichage

Ce guide explique où ranger une valeur qui change pendant le jeu (un compteur, un score, un état),
et comment l'afficher à l'écran.

**Ce qu'il vous faut :** une scène. L'exemple compte les appuis sur `A` et les affiche.

## 1. Trois endroits où ranger une valeur

| Forme | Durée de vie | Visible par | Usage |
| --- | --- | --- | --- |
| `local` dans le script | tant que la scène vit | ce script | un état interne (un minuteur, un compteur de frames). |
| **export** (`exports = {...}`) | réglée dans l'inspecteur | ce script, et l'éditeur | un réglage propre à chaque acteur (vitesse, vie maximale). |
| **globale** (`global.nom`) | tout le jeu | tous les scripts et les textes | un score, une clé ramassée, un niveau atteint. |

Une variable `local` repart de sa valeur initiale quand la scène est rechargée. Une globale
survit aux changements de scène.

## 2. Déclarer une globale

Ouvrez l'écran **Scripts**. Dans la section **Globals**, cliquez sur **+**, nommez la variable
`compteur` et donnez-lui la valeur par défaut `0`. Une globale appartient au projet, pas à un
acteur : n'importe quel script lit ou écrit `global.compteur`.

Cochez **Persist** seulement pour conserver la valeur dans la sauvegarde de la cartouche, après
extinction de la console.

## 3. La modifier depuis un script

Ajoutez un script de scène (un script attaché à la scène, et non à un acteur) :

```lua
function on_update()
    if input:pressed("a") then
        global.compteur = global.compteur + 1
    end
end
```

Un script de scène convient aux règles qui concernent tout le niveau : démarrage, affichage,
changement de scène.

## 4. L'afficher

Un texte qui contient une valeur se crée dans l'écran **Texts**. Créez une entrée `hud_compteur`
dont le contenu est :

```text
Appuis : $compteur
```

Le marqueur `$compteur` lit la valeur de `global.compteur` quand le texte est rendu. Ajoutez ensuite
une **Interface** à la scène, avec un élément **Texte** nommé `Compteur` (sa position et sa police se
règlent dans l'éditeur), puis affichez l'entrée au démarrage :

```lua
function on_start()
    interface:get("Compteur"):draw("hud_compteur")
end
```

Lancez **Run** : le texte affiche la valeur courante. Utilisez toujours le marqueur `$nom` plutôt
qu'une concaténation de texte dans le script.

## À savoir

- Les calculs utilisent des entiers : il n'y a pas de nombre à virgule dans le jeu. Pour un
  pourcentage ou une fraction, choisissez une échelle (par exemple 100).
- Un nom de globale se renomme depuis l'éditeur : les scripts qui l'utilisent suivent.
- Pour les textes eux-mêmes (clés, balises, traductions), voir [Textes et dialogues](../faire-vivre/textes-dialogues.md).
