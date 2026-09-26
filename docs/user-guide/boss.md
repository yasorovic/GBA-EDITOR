# Créer un boss et sa barre de vie

Ce guide réunit deux outils utiles pour un combat : la **parenté** entre acteurs, et une valeur de vie affichée dans l'interface.

## 1. Créer le boss et ses éléments enfants

Créez un acteur ou un prefab nommé `Boss`, avec son sprite, une boîte de collision et un script. Ajoutez ensuite ses éléments visuels séparés, comme une arme ou une ombre.

Dans l'arbre de scène, faites glisser chaque élément sur `Boss`. Il devient son enfant : il suit le déplacement, la rotation et l'échelle de son parent. Gardez la collision principale sur le parent ; les enfants servent surtout à composer une silhouette ou à animer des parties du boss.

## 2. Ajouter des points de vie

Dans le script du boss, exposez ses points de vie et préparez une fonction de dégâts :

```lua
exports = {
    vie_max = { type = "int", default = 20, label = "Vie maximale", min = 1, max = 999 },
}

local vie

function on_start()
    vie = vie_max
end

function subir_degats(degats)
    vie = math.max(0, vie - degats)
    if vie == 0 then
        self:destroy()
    end
end
```

`vie_max` se règle pour chaque boss dans l'inspecteur ; `vie` est un état temporaire du combat. Lorsque vous ajouterez une attaque de joueur, appelez `subir_degats(1)` au moment de son impact.

## 3. Poser une barre de vie

Ajoutez une **Interface** à la scène du boss, puis un **Conteneur** nommé `BarreVie`. Ajoutez dedans une **Image** ou un second conteneur coloré nommé `Remplissage`, placé en haut de l'écran.

Préparez cinq états dans l'image d'interface : `vie_0` vide jusqu'à `vie_4` pleine. Le script du boss peut choisir l'état selon la vie restante :

```lua
function on_update()
    local remplissage = interface:get("Remplissage")
    local etat = vie * 4 / vie_max
    if etat == 0 then
        remplissage.state = "vie_0"
    elseif etat == 1 then
        remplissage.state = "vie_1"
    elseif etat == 2 then
        remplissage.state = "vie_2"
    elseif etat == 3 then
        remplissage.state = "vie_3"
    else
        remplissage.state = "vie_4"
    end
end
```

Le calcul utilise des entiers, ce qui donne cinq étapes lisibles sans coût inutile.

## 4. Tester le combat

Lancez la ROM et vérifiez que le boss et ses enfants se déplacent ensemble. Faites temporairement appeler `subir_degats(1)` depuis un bouton pour observer la barre, puis remplacez ce test par la collision de l'attaque du joueur.
