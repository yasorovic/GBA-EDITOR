# Gravité et saut

Ce guide donne à un acteur le comportement d'un personnage de jeu de plateforme : il tombe, marche
sur le sol et saute.

**Ce qu'il vous faut :** une scène avec un sol peint dans la carte de collision, et un acteur avec
une boîte **Collision** (Collision shape) et un script. Le corps physique est un `CharacterBody` dont le
collider est cette boîte. Ces deux éléments se préparent dans
[Collisions](collisions.md).

## 1. Ajouter la gravité

La carte de collision arrête l'acteur contre un mur, un sol ou un plafond. La gravité se règle une
fois pour le projet (**Game > Project Settings > Physics & Collisions**, en pixels par frame au carré) et
peut être remplacée par scène. Un `CharacterBody` la suit tant que la case **Use scene gravity** de son composant
est cochée (c'est le cas par défaut) : le moteur l'ajoute à sa vitesse verticale, le script n'a qu'à conserver
cette vitesse en écrivant la sienne :

```lua
function on_update()
    local body = self:physics_body()

    body.velocity = vec2(input:get_axis("horizontal") * 2 * 256, body.velocity.y)
    body:apply_velocity()
end
```

Si la case est décochée, l'acteur ne tombe pas de lui-même et le script gère la chute : il lit `scene.gravity`
(la gravité de la scène, en Q8) et l'ajoute à chaque frame quand l'acteur est en l'air.

`scene.gravity` s'exprime dans la même échelle que `body.velocity` : `256` vaut 1 pixel par frame (une
gravité de `0,25` px/frame² vaut donc `64`). Quand la boîte touche le sol peint, le moteur annule la
vitesse verticale et l'acteur reste posé. Tous les acteurs d'une scène suivent ainsi la même gravité,
et une scène peut en avoir une autre (une scène lunaire, par exemple) sans toucher aux scripts. Voir
[Corps physiques](corps-physiques.md).

Pour un jeu vu de dessus, vous n'avez pas besoin de gravité : une simple `body.velocity` suffit.

## 2. Savoir si l'acteur est au sol

Après la résolution des collisions, le moteur met à jour `body.grounded` : `true` quand la boîte
solide repose sur la carte de collision, un StaticBody ou un KinematicBody posé, `false` dans les
airs. Cette propriété empêche de sauter à chaque frame : le joueur ne saute que depuis le sol.

`body.floor` donne l'Actor qui porte actuellement le personnage (StaticBody, KinematicBody, ou un autre corps
sur lequel il repose).
Il vaut `nil` quand le personnage repose sur la carte ou se trouve dans les airs. Vous pouvez ainsi
identifier une plateforme particulière sans refaire un test de collision :

```lua
local floor = self:physics_body().floor
if floor then
    -- floor est une référence d'Actor
end
```

## Matériaux physiques

Un `PhysicMaterialComponent` porte une restitution et une friction, de `0` à `1`. Une `CollisionShape`
le désigne par son id (champ « Matériau ») : sans désignation, elle n'a ni rebond ni frottement. La
restitution décide du rebond et le contact conserve la valeur la plus élevée. La friction ralentit le
glissement tangent et le contact emploie la moyenne géométrique des deux valeurs.

Ces coefficients sont combinés au build puis écrits dans les paires physiques de la scène. Ils n'ajoutent
donc aucun état à l'`Actor` au runtime. Plusieurs formes d'un même acteur peuvent partager un matériau.

## Quelles boîtes se rencontrent

Le `tag` d'une `CollisionShape` est son groupe de collision. La matrice de **Project Settings > Physics &
Collisions** dit, pour chaque couple de tags, s'ils se rencontrent. Le build calcule les couples de boîtes
autorisés et ne les émet pas dans les tables de contacts, de blocage, de contact au sol ou d'impulsions. Il
n'ajoute donc aucun champ à l'`Actor` ni de lecture dynamique de la matrice dans la ROM.

Les méthodes Lua de requête géométrique, telles que `collision_shape:overlaps`, restent des tests de forme
explicites. Elles ne sont pas des événements automatiques et ne consultent pas la matrice.

## 3. Ajouter l'impulsion de saut

```lua
exports = {
    vitesse    = { type = "int", default = 2,   label = "Vitesse",       min = 0, max = 8 },
    force_saut = { type = "int", default = 900, label = "Force du saut", min = 0, max = 2048 },
}

function on_update()
    local body = self:physics_body()
    local vitesse_x = input:get_axis("horizontal") * vitesse * 256
    local vitesse_y = body.velocity.y            -- la gravité de la scène est déjà dedans

    if body.grounded and input:pressed("a") then
        vitesse_y = -force_saut
    end

    body.velocity = vec2(vitesse_x, vitesse_y)
    body:apply_velocity()
end
```

La touche `A` donne une vitesse négative sur l'axe vertical, donc vers le haut. La gravité
l'augmente ensuite chaque frame jusqu'au prochain contact avec le sol.

## 4. Comprendre les valeurs

`256` vaut 1 pixel par frame : une force de saut de `900` correspond à une impulsion d'environ
3,5 pixels par frame vers le haut. Le saut monte d'environ `force² / (2 × gravité)` : avec une gravité de
`64` (0,25 px/frame²), une force de `1024` donne environ 32 pixels de hauteur, et la même force sous une
gravité quatre fois plus faible monte quatre fois plus haut. **Vitesse** et **Force du saut** sont exposées
dans l'inspecteur parce qu'elles changent souvent d'un personnage à l'autre ; la gravité vient de la scène.

## 5. Tester

Lancez **Run**, déplacez l'acteur avec gauche et droite, puis appuyez sur `A` :

- il saute depuis le sol ;
- il ne peut pas sauter de nouveau en l'air ;
- il retombe et s'arrête sur le sol peint ;
- les murs peints l'arrêtent.

Si le saut ne fonctionne pas, vérifiez que le composant Physics body désigne la boîte comme collider
(sélecteur **Physics collider**) et que le sol est bien peint. Si l'acteur reste dans les airs au départ, vérifiez la gravité du projet et de la scène : à `0`, `scene.gravity`
rend `0` et rien ne le fait tomber. Vérifiez aussi que **Use scene gravity** est cochée. `body.grounded` décrit la fin de la frame précédente : juste après avoir quitté une
plateforme, il peut rester vrai une frame.
