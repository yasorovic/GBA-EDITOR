# Parenté et accesseurs

Ce guide traite de deux sujets liés : comment composer un acteur à partir de plusieurs pièces
(la **parenté**), et comment un script atteint les autres éléments du jeu (les **accesseurs**).

**Ce qu'il vous faut :** une scène. L'exemple construit une tourelle : un socle, un canon et un
voyant.

## 1. La parenté

Créez trois acteurs : `Tourelle` (le socle), `Canon` et `Voyant`, chacun avec son sprite. Dans
l'arbre de la scène, faites glisser `Canon` et `Voyant` sur `Tourelle`. Ils deviennent ses
**enfants** : ils suivent le déplacement, la rotation et l'échelle de leur parent.

La parenté sert à :

- composer une silhouette en plusieurs sprites (corps, arme, ombre) ;
- animer une pièce séparément, tout en gardant l'ensemble solidaire ;
- déplacer un groupe en déplaçant un seul acteur.

Gardez la collision principale sur le parent. Un enfant est un acteur à part entière : il a son
propre sprite, ses composants et son script.

Un **prefab** peut contenir des enfants de la même façon : toutes les instances reçoivent la
composition complète.

## 2. Atteindre un enfant : `self.nom`

Depuis le script du parent, un enfant se désigne **par son nom**, directement sur `self` :

```lua
function on_start()
    self.Voyant:hide()
end

function on_update()
    if input:pressed("a") then
        self.Canon:play_anim("tir")
        self.Voyant:show()
    end
end
```

`self.Canon` est l'acteur enfant : toutes les méthodes d'un acteur s'y appliquent (`hide`, `show`,
`play_anim`, `destroy`...). Une animation se cherche dans les états du sprite de l'enfant, pas dans
ceux du parent : ici `tir` doit exister sur le sprite du canon. Le nom est résolu au Build, sans recherche pendant le jeu : cet accès
ne coûte rien. Un nom qui n'est ni une propriété de l'acteur ni un enfant est refusé au Build, avec
la liste des enfants disponibles.

## 3. Les autres accesseurs

Le même principe, nommer ce qu'on veut atteindre, vaut pour tous les éléments du jeu.

| Je veux... | J'écris... | Résultat |
| --- | --- | --- |
| un enfant de cet acteur | `self.Canon` | l'acteur enfant |
| un acteur de la scène, par son nom | `actor:get("Porte")` | l'acteur, ou `nil` s'il est absent ou détruit |
| le n-ième acteur de la scène | `actor:get(i)` (de 1 à `actor:count()`) | idem, dans l'ordre de la scène |
| la n-ième instance vivante d'un prefab | `actor:get("Bullet", i)` (de 1 à `actor:count("Bullet")`) | l'instance, ou `nil` |
| une boîte de collision de l'acteur | `self:collision_box("body")` | la boîte, ou `nil` |
| un élément d'interface | `interface:get("Score")` | l'élément, du type réel (texte, image, liste...) |
| une valeur partagée | `global.score` | la globale |
| qui je touche | `other.name` (dans `on_collision_enter`) | le nom de l'autre acteur |

Deux règles pour les acteurs :

- **Testez avant d'utiliser.** `actor:get("Porte")` rend `nil` si la porte n'existe plus : écrivez
  `local porte = actor:get("Porte")` puis `if porte then ... end`.
- **Un acteur désigné par son nom connaît ses animations.** `local boss = actor:get("Boss")` puis
  `boss:play_anim("rage")` : `rage` est cherché dans les états du sprite de `Boss`, et refusé au Build
  s'il n'y est pas. Même chose pour un prefab né par `actor:spawn("Bullet", pos)`. Avec
  `actor:get(i)`, l'acteur n'est connu qu'en jeu : seules les méthodes sans nom d'état s'appliquent.
  Pour le garder d'une image à l'autre, déclarez `local cible = nil` en tête de script et affectez-le
  dans un handler : la référence vaut `nil` dès que l'acteur est détruit, même si un autre naît au
  même emplacement.
- **Les exports d'un acteur nommé se lisent et s'écrivent.** `boss.hp = boss.hp - 1`,
  `boss.state = "RAGE"` : le nom est celui de l'export, sans préfixe. Les nombres, booléens et
  énumérations se manipulent tels quels, un vecteur par son constructeur (`boss.home = vec2(8, 9)`),
  une référence ou un texte par son nom (`boss.target = "Player"`). Le Build refuse un nom inconnu
  en listant ceux qui existent.
- **Un acteur disparu ne plante rien.** Une action ou un export sur une référence détruite,
  désactivée ou `nil` est sautée, et un build debug l'écrit dans le log de l'émulateur.
- **Le nom est local à la scène.** Un acteur posé s'appelle `Gardien` dans sa scène, deux scènes
  peuvent donc avoir chacune un `Gardien`. Un script atteint seulement les acteurs de la scène en
  cours.

Pour parcourir tous les acteurs posés :

```lua
for i = 1, actor:count() do
    local a = actor:get(i)
    if a and a.name == "Piege" then
        a:hide()
    end
end
```

Le nom comparé (`"Piege"`) doit être celui d'un acteur ou d'un prefab du projet : le Build refuse
un nom inconnu, avec la liste des noms connus.

## 4. Un exemple complet

Le script de `Tourelle` : le voyant s'allume quand un acteur nommé `Joueur` est présent, et le
canon s'éteint si le joueur disparaît.

```lua
function on_update()
    local joueur = actor:get("Joueur")
    if joueur then
        self.Voyant:show()
    else
        self.Voyant:hide()
        self.Canon:hide()
    end
end
```

## À savoir

- Les éléments d'interface ont leur propre hiérarchie : masquer un conteneur masque ses enfants
  (voir [Variables et affichage](variables-affichage.md)).
