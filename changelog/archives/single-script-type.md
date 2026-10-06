# Un seul type de script — le propriétaire donne le contexte — **LIVRÉ**

### D'où vient la question (2026-09-26)

Les scripts se présentent en plusieurs « types » (scène, caméra, acteur/prefab, behavior) qui ont tous
accès à la même API. Vérification faite : le type n'est jamais saisi, il est déduit de l'attache, et
`self` n'existe déjà que pour un acteur ou un prefab (`CodegenContext.has_self` côté codegen). Ce qui distingue
réellement ces « types » appartient au **propriétaire**, pas au script : le jeu d'événements admis, le
symbole C émis, le stockage par instance d'un prefab poolé. Unity et Godot n'ont, eux aussi, qu'un seul
concept de script.

### La règle

Un script est un fichier Lua. Son contexte vient de ce à quoi il est attaché.

- `self` désigne sans ambiguïté l'instance à laquelle le script est attaché, et n'est admis que pour un
  script attaché à un acteur ou à un prefab. Partout ailleurs, `self` est une **erreur**.
- Le « type » est un attribut **dérivé**, jamais choisi par l'auteur.
- Le **behavior** reste : c'est un module (`require`), sans propriétaire ni événements. `self` y est
  refusé ; l'acteur passe en paramètre.

### Décisions verrouillées (2026-09-26)

1. **Un fichier, une famille de propriétaire.** Attacher le même script à des propriétaires de familles
   différentes (par exemple un acteur et la scène) est **refusé au build**, avec une erreur nommant les
   deux attaches. On n'autorise pas ce cas au prix d'un `self` ambigu : ce serait de la complexité.
2. **Les événements sont validés par propriétaire.** `on_collision_enter` dans un script de caméra reste
   refusé au build. L'éditeur le **filtre en amont** : l'auto-complétion ne propose que les événements de
   la famille du propriétaire du script édité, et les modèles de nouveau script suivent le même critère.
3. **Le behavior est conservé** comme module distinct.

### Ce que ça touche

- `scripting/codegen.py` / `checker.py` : `is_scene` et `hook_kind` deviennent une notion de
  propriétaire ; erreur explicite sur `self` hors acteur/prefab ; refus de l'attache multi-familles.
- `scripting/completion.py` : filtrage des événements selon le propriétaire (la fonction lit déjà un
  `context` actor/scene/behavior/camera/unknown).
- `scripting/script_templates.py` : le `kind` saisi devient « ce que l'éditeur propose selon l'endroit de
  création ».
- Docs : `docs/scripting.md`, `docs/scripting-reference.md`, `ARCHITECTURE.md`.

Le comportement des projets valides ne change pas ; seuls les cas déjà ambigus deviennent des erreurs.

**Livré (2026-09-26)** : refus au build (`self`, événements, fichier multi-familles, `self` en
behavior), complétion contextuelle, `is_scene`/`hook_kind` remplacés par `owner_kind`/`has_self`.
Chantier clos, rien d'ouvert.
