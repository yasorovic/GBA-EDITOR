# La grammaire de la struct `Actor` — chantier technique

**Ouvert le 2026-08-23. Livré dans le commit `df73c18` (ligne V0.9), vérifié et
archivé le 2026-09-05.** Chantier *technique* : il ne change rien pour qui joue
au jeu produit avec l'éditeur, seulement pour qui modifie le code — donc pas de
ligne au [README](../../README.md) ni au [CHANGELOG](../CHANGELOG.md), et pas de
numéro `vX.Y`. Référencé par son nom.

## Vérification à la clôture (2026-09-05)

La décision verrouillée « le compilateur est le vérificateur exhaustif » exigeait
de **builder réellement la ROM**, pas seulement de lancer les tests. Encaissé :

- **Build ROM réel** de `Project Demo/MyGame` (`build/` supprimé d'abord),
  `finished=True` en 12,1 s, ROM de 100 444 octets. Les 15 unités de compilation
  — dont `actor_Flying_Note.c` et les trois scènes, qui passent par les
  accesseurs de la struct découpée — compilent sous `-Wall` et lient sans une
  erreur. Un site oublié n'aurait pas compilé ; aucun ne l'était.
- `test_affine_model.py` + tests scripting : 117 passés, 1 skip.
- Suite complète : **499 passés, 51 skip, 0 échec**.

Confronté au code au moment de la clôture, chaque décision ci-dessous est en
place : struct découpée, accesseurs migrés vers `->sprite.`/`->collision.`,
abréviations C supprimées (surface Lua conservée), `affine_transform` porté par
le `SpriteComponent`, gardes de slot retirées, checker en `warning`, recopies
Relink/Expose supprimées, et `ARCHITECTURE.md` déjà migré aux noms imbriqués.

## D'où vient la question

Posée le 2026-08-23, en relisant l'architecture : l'éditeur distingue trois
choses — un **actor** (logique de jeu), un **sprite** (son rendu), un
**background** (le décor). Est-ce que l'API C tient la même distinction ?

Non. Côté C il n'existe **qu'une struct**, `Actor`, et elle porte les trois
familles à plat : la logique (`x, y, vx, vy, timer, tag`), le rendu OBJ
(`frame, anim_*, flip_*, pal_bank, obj_mode, priority, sprite_rot,
sprite_scale_*, offset_*`) et la collision (`boxes, box_count, grounded, last_x,
slope_acc`). 37 `int` et 4 `CollisionBox`, sans frontière visible.

Le background, lui, n'a **pas** de type C, et c'est correct : le calque **est**
le matériel (`layer_*(int bg, …)`, `tilemap_*(int bg, …)` et les registres
ombres `g_bgcnt_sh[4]`, `g_bg_ofs_x/y[4]`). Il y a quatre plans dans la machine ;
leur donner un type instanciable suggérerait qu'on peut en créer un cinquième.
**Ce point ne bouge pas.**

## Ce que ce jalon n'est pas

Il ne sépare **pas** `Actor` en deux structs. Le rapport est 1:1 (un actor porte
au plus un `SpriteComponent`), et l'indirection coûterait un déréférencement par
accès sur un ARM7TDMI sans cache. Le merge est **assumé** ; ce qui change, c'est
qu'il devient lisible.

## Ce que la lecture du code a écarté, et pourquoi

Trois pistes ouvertes le 2026-08-23, deux refermées le jour même après lecture :

- **« Supprimer la recopie par tick de
  `anim_length`/`anim_loop`/`anim_finished` ».** Écartée. `anim_length` n'est pas
  `state_len[state]` : c'est la longueur du bloc de la **direction actuellement
  jouée**, que `_anim_tick_lines` trouve par un parcours de `anim_dirs[]` avec
  repli sur la direction omni. La recopie **mémoïse le parcours que le tick fait
  déjà**. Exposer les tables aux scripts déplacerait la boucle dans chaque
  lecture de `self.anim_length` — plus lent, pas plus propre. `anim_finished` en
  dérive. Reste `anim_loop`, seule copie réellement pure : l'effacer coûterait un
  `const SpriteDef*` de 4 octets pour économiser un `int` de 4 octets, plus une
  indirection. Gain nul.
- **« Découpler le slot OAM de l'index d'acteur ».** Hors périmètre par décision
  existante : c'est le *Chantier transverse — l'allocateur de ressources
  matérielles*, qui attend son deuxième consommateur, et dont une décision
  verrouillée dit déjà qu'« un arbitrage OAM par frame est un vrai coût CPU ; il
  se décide sur un cas mesuré, pas à l'avance ».
- **`frame_w`/`frame_h` par instance.** Ressemblent à une duplication de
  `SpriteAsset.frame_w/h`. N'en sont pas : le script d'un prefab poolé est une
  fonction C partagée par toutes ses instances, elle ne peut pas les recevoir en
  `#define`.

L'argument mémoire n'existe de toute façon pas : `g_actors` est en EWRAM
ordinaire — 128 entrées de ~172 octets, soit ~22 Ko sur 256.

## Décisions verrouillées

- **Trois blocs, calqués sur les composants de l'éditeur.** Pas une taxonomie
  inventée pour l'occasion (`render`/`body`) : la décomposition existe déjà,
  c'est celle que l'inspecteur affiche. `Actor` racine ↔ `Actor` éditeur,
  `Actor.sprite` ↔ `SpriteComponent`, `Actor.collision` ↔
  `CollisionBoxComponent`. Le C émis dit alors la même chose que l'UI — c'est la
  grammaire unique appliquée à la struct.

  | Bloc | Champs |
  | --- | --- |
  | `Actor` | `x, y, vx, vy, timer, tag, active, dir_x, dir_y, rotation, scale_x, scale_y, visible, priority, pal_bank, obj_mode, flip_h, flip_v` |
  | `Actor.sprite` | `frame, anim_state, anim_speed, anim_length, anim_loop, anim_finished, frame_w, frame_h, auto_dir, rotation, scale_x, scale_y, offset_x, offset_y, affine_slot` |
  | `Actor.collision` | `grounded, last_x, slope_acc, box_count, boxes[]` |

- **La réservation affine appartient au sprite, pas à l'actor** *(2026-08-25)*.
  `affine_transform` vivait sur l'`Actor` et s'affichait dans une carte
  « Affine » à part, dont le commentaire de l'inspecteur disait déjà pourquoi :
  « ce n'est pas un PLACEMENT mais une capacité de RENDU ». C'est l'argument exact
  qui la met sur le `SpriteComponent` — le composant de rendu, le seul qui
  s'affiche aussi sur une racine de prefab. Trois conséquences :

  - la carte « Affine » de l'inspecteur disparaît ; la case passe dans la carte du
    SpriteComponent, et Rotation/Scale de l'actor remontent dans **Transform**
    (ils y étaient déjà masqués sur une racine de prefab — rien ne change de ce
    côté) ;
  - côté C, `affine_slot` suit le flag et passe dans le bloc `sprite` : c'est le
    principe même de ce jalon, le C émis dit la même chose que l'UI ;
  - `Prefab.affine_transform` délègue au SpriteComponent de son actor racine, et
    les deux recopies manuelles de `command_dispatcher` (Relink/Expose)
    disparaissent — le `deepcopy(components)` qui les précède transporte déjà le
    flag.

- **`Actor.rotation`/`scale` sont du STOCKAGE, pas un privilège du slot**
  *(2026-08-25)*. Les accesseurs étaient gardés par `if (affine_slot >= 0)` :
  sans slot, setter no-op et getter identité — `self.rotation = self.rotation + 1`
  n'incrémentait rien, la valeur ne faisait même pas l'aller-retour. Les champs
  existent dans **chaque** `Actor` de toute façon ; seule l'écriture de la matrice
  OAM a besoin du slot. Les gardes tombent donc.

  Le checker **garde son contrôle mais descend d'un cran** : `error` → `warning`.
  Il reste le seul endroit qui voit qu'un script écrit `self.rotation`, et c'est
  l'oubli réel qu'il faut signaler ; ce qui change est qu'il ne refuse plus le
  build. Même registre que le cas parent/enfant juste à côté : le jeu tourne,
  c'est l'affichage qui ment. Une valeur qu'un script peut lire, écrire et relire
  sans effet visible est un modèle plus simple à expliquer qu'une propriété qui
  s'évapore. `BuildContext.affine_transform` reste donc, alimenté désormais par le
  SpriteComponent.

- **Les trois abréviations disparaissent avec le namespace qui les rendait
  nécessaires.** `sprite_rot` → `sprite.rotation`, `sprite_scale_x/y` →
  `sprite.scale_x/y`, `offset_x/y` → `sprite.offset_x/y`. Elles n'existaient que
  parce que la struct était plate. La règle « jamais d'abréviation » redevient
  tenue sans exception.

- **La surface Lua ne bouge pas d'un caractère.** `self.frame`,
  `self.sprite_scale`, `self.anim_length` passent tous par les accesseurs de
  `actor_api_static.h` : `scripting/api.py`, `codegen.py`, `checker.py` et
  `expr_types.py` ne touchent aucun champ directement. Ce jalon n'est pas une
  rupture pour les projets existants.

- **Le compilateur est le vérificateur exhaustif.** Un site oublié ne compile
  pas. La condition est donc de builder réellement la ROM à la fin, pas seulement
  de lancer les tests — sans quoi la garantie n'est pas encaissée. *(Encaissée le
  2026-09-05, cf. en-tête.)*

## Ce que ça touche

| Fichier | Sites | Nature |
| --- | --- | --- |
| `editor/codegen/runtime_codegen/main_gen.py` | 162 | `g_actors[i].champ` dans des f-strings |
| `runtime/include/actor_api_static.h` | ~90 | `s->champ` dans les accesseurs |
| `runtime/include/actor_types_static.h` | 1 | la struct elle-même |
| `tests/graphics/test_affine_model.py` | 3 | assertions sur le C émis |
| `editor/codegen/runtime_codegen/headers.py` | commentaire | l'en-tête de `actor_types.h` |

Et pour la réservation affine passée au sprite :

| Fichier | Nature |
| --- | --- |
| `editor/core/models/components.py` | `SpriteComponent.affine_transform` |
| `editor/core/models/scene.py` | retrait de `Actor.affine_transform`, migration à la lecture, délégation `Prefab` |
| `editor/ui/scene_manager/inspectors/actor_inspector.py` | carte « Affine » supprimée, Rotation/Scale remontés dans Transform |
| `editor/ui/scene_manager/inspectors/component_editors/sprite.py` | la case, et le grisage qui la lit |
| `editor/scripting/checker.py` | le contrôle passe de `error` à `warning` |
| `editor/scripting/api.py` | « Nécessite … sur l'actor » → « ne s'affiche que si le sprite … » (6 docs) |
| `editor/codegen/runtime_codegen/lua_compiler.py` | le flag se lit sur le sprite (`_affine_reserved`) |
| `editor/core/command_dispatcher.py` | les deux recopies Relink/Expose disparaissent |
| `editor/ui/scene_manager/scene_canvas.py` | le rendu éditeur lit le flag sur le sprite |

## Le point « Ouvert » à l'ouverture, résolu à la clôture

`ARCHITECTURE.md` portait les anciens noms plats (`Actor.obj_mode`,
`g_actors[i].rotation`, `Actor.last_x`, `Actor.grounded`…). Ils étaient justes
tant que le découpage n'était pas fait : ce fichier décrit le code tel qu'il est,
il servait donc de **liste de contrôle** du chantier plutôt que de dette à
corriger d'avance. À la clôture, il est migré aux noms imbriqués
(`g_actors[i].sprite.rotation`, `Actor.collision.last_x`, `Actor.sprite.affine_slot`…) ;
`Actor.obj_mode` reste tel quel, `obj_mode` étant un champ **racine** dans le
découpage aussi.
