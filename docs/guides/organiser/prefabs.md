# Prefabs et instances

Un **prefab** est un acteur modèle : son sprite, ses composants et son script sont définis une
fois, puis réutilisés en autant d'**instances** que nécessaire. Ce guide crée un prefab, en place
plusieurs copies et règle chacune séparément.

**Ce qu'il vous faut :** une scène et un sprite. L'exemple fabrique une lanterne qui clignote.

## 1. Créer le prefab

Ajoutez un acteur avec le sprite de la lanterne, puis, avec l'acteur sélectionné, utilisez
**Expose to Prefab** dans l'inspecteur et nommez le prefab `Lanterne`. L'acteur de la scène devient
une instance du prefab. Les prefabs se retrouvent dans la section **Prefabs** de la **Scene
library** et sur le disque, dans l'onglet **Disk**.

On peut aussi créer un prefab vide depuis la section **Prefabs**, avec **+**.

## 2. Lui donner un script réglable

Ajoutez un composant **Script** au prefab et créez `Lanterne.lua` :

```lua
exports = {
    periode = { type = "int", default = 30, label = "Période", min = 2, max = 120 },
}

function on_update()
    if scene.frame % periode == 0 then
        if self.visible then
            self:hide()
        else
            self:show()
        end
    end
end
```

La lanterne s'éteint puis se rallume toutes les `periode` frames. `periode` est un **export** : un
réglage proposé dans l'inspecteur de chaque instance (voir
[Déplacer un acteur](../acteurs/deplacer-acteur.md) pour le principe).

## 3. Placer plusieurs instances

Ajoutez plusieurs instances du prefab `Lanterne` dans la scène et déplacez-les sur le canvas. Dans
l'inspecteur d'une instance, changez **Période** : chaque lanterne clignote à son propre rythme,
tandis que le sprite et la logique restent communs au prefab.

L'inspecteur d'une instance indique le prefab dont elle vient, avec les boutons **Open prefab**
(pour modifier le modèle) et **Expose**.

## 4. Quand utiliser un prefab ?

- Plusieurs copies du même acteur : pièces, ennemis, lanternes, portes.
- Un acteur que le script crée pendant le jeu : projectiles, particules (voir
  [Créer des acteurs pendant le jeu](../faire-vivre/acteurs-au-vol.md)).
- Un acteur qui existe dans plusieurs scènes.

Un acteur unique, propre à une seule scène, n'a pas besoin d'être un prefab.

## À savoir

- Le nom d'un acteur placé est local à sa scène : deux scènes peuvent chacune avoir un `Gardien`.
  Un prefab, lui, a un nom unique dans le projet.
- Un prefab peut contenir des acteurs enfants : voir [Parenté et accesseurs](parente-accesseurs.md).
