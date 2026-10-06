# La struct `Actor` allégée — l'acteur entité légère, le sprite (et l'OAM) deviennent un composant — **LIVRÉ**

**Décidé le 2026-09-21 : à faire quoi qu'il arrive.** Ce dossier fixe le POURQUOI et les marches ;
les décisions fines se tranchent à l'ouverture.

### D'où vient la question

Le modèle runtime est aujourd'hui **plat** : une seule struct `Actor`
([runtime/include/actor_types_static.h](runtime/include/actor_types_static.h)), un tableau
`g_actors[]`, le `tag` distingue le type. Deux coûts assumés en découlent :

1. **La struct grasse.** Chaque `Actor` porte l'union de tous les champs possibles — dont le
   sous-struct `sprite` complet. Un acteur-logique (contrôleur, spawner, directeur d'IA, déclencheur)
   qui ne veut que x/y paie tout. Ce n'est pas théorique : `g_actors[]` a dû **migrer en EWRAM** faute
   de tenir en IWRAM (cf. Correctifs).
2. **Le budget OAM ment par prudence.** `oam_alloc` compte `128 − acteurs actifs − UI`, alors que son
   propre commentaire reconnaît qu'« un acteur sans sprite ne consomme aucune entrée OAM ; le budget
   les compte quand même ». Un acteur-logique grignote donc un plafond matériel qu'il n'utilise pas.

### Le principe

Faire de `Actor` une **entité légère**, et déplacer la logique d'affichage sur un **composant sprite** :
la règle « **1 acteur = 1 slot OAM** » devient « **un sprite component affiché = 1 slot OAM** ».
Conséquences visées :

- **Un acteur sans sprite est gratuit** (0 slot OAM, pas de sous-struct sprite) — les acteurs-logique
  cessent de peser sur les 128 et sur l'IWRAM.
- **Le budget OAM devient honnête** : `128 − sprites affichés − UI`, la vérité du matériel (OAM =
  objets affichés, pas entités). Cohérent avec « le matériel façonne le langage ».
- **Swap d'apparence** : un acteur peut porter **plusieurs** sprite components dont **un seul affiché**
  — changer de planche sans second acteur ni second slot.

### Le rôle de l'Actor — racine de composition, pas fourre-tout

L'Actor est le **type stable et simple** que manipule le gameplay. Il porte ce qui existe pour
toute entité : identité, durée de vie, transform (`position`, orientation), mouvement courant
(`velocity`) et script. Les composants lui ajoutent une capacité optionnelle ; ils ne changent
ni son identité ni le fait qu'un script peut tenir une référence d'Actor.

| Porteur | Responsabilité publique | Coût matériel |
| --- | --- | --- |
| `Actor` | identité, `active`, `destroy`, position, vélocité, helpers de gameplay | aucun OAM par lui-même |
| `Sprite` | dessin, animation, palette, priorité et taille de frame | une entrée OAM seulement s'il est affiché |
| `Collision` | formes, contacts, résolution contre le monde | aucun OAM |
| `CollisionBox` | une forme précise, ses réglages et ses requêtes avancées | aucun OAM |
| `SoundFx` / script | émission sonore et logique de l'entité | aucun OAM |

Cette composition est une **forme d'API et d'authoring**, pas l'obligation d'un ECS par pointeurs
au runtime. La GBA peut garder une représentation compacte — champs à plat pour le chaud,
side-array pour le Sprite optionnel — tant que le contrat public reste le même. Les composants
ne sont donc pas un prétexte pour déplacer toute propriété derrière une indirection.

L'Actor conserve des **helpers de gameplay agrégés**, parce qu'ils répondent à l'intention la
plus fréquente sans obliger à connaître la forme qui la réalise. La forme cible est une
propriété, jamais `is_grounded()` :

```lua
if self.grounded then                 -- au moins une collision porte l'Actor
  self:add_velocity(vec2(0, -900))
end

local collision = self.collision      -- nil si l'Actor n'a pas cette capacité
local feet = collision:get_box("feet")
```

`self.grounded` vaut `false` sans composant Collision. Il agrège les contacts porteurs de la
capacité Collision, pas une box particulière : le helper survit donc à plusieurs boîtes, et
plus tard à une autre représentation de collision. Les détails — tag, géométrie, activation,
requêtes par boîte — restent sur `Collision` et `CollisionBox`.

### Ce qui existe déjà à ne pas confondre

- Les **AnimStates** : une entité, plusieurs visuels d'une MÊME planche, un slot. (déjà là)
- Les **prefabs segmentés** (v0.23) : une entité, PLUSIEURS parties = plusieurs slots (enfants). (déjà là)
- Le neuf ici : (a) l'acteur **zéro sprite** gratuit, (b) N planches **distinctes** swappables, 1 affichée.

### Ce qu'il faudrait trancher avant d'ouvrir

- **Quelle découpe compacte porte le Sprite optionnel** : index nullable vers un side-array de
  sprite-components, ou bloc hot/cold absent des acteurs sans Sprite. Dans les deux cas, aucun
  Actor logique ne garde le sous-struct sprite complet ; le choix doit éviter la fragmentation
  d'identité vue à la tranche poolé des exports.
- **La VRAM, pas l'OAM, est le vrai plafond du multi-apparence.** « 1 affiché » économise un slot OAM,
  mais les tuiles + palette de CHAQUE apparence doivent être résidentes (ou streamées). À trancher :
  tout résident vs streaming.
- **Le budget reste au build mais devient un pire-cas.** Avec un affichage dynamique, le build borne le
  **max concurrent de sprites affichés** par scène. Reste de l'allocation au build — **pas « un autre
  moteur »**, contrairement au spawn dynamique.
- **Ne PAS construire un ECS général.** Position, durée de vie et mouvement restent le socle
  chaud de l'Actor. Collision devient une capacité publique parce qu'elle est déjà optionnelle
  et porte ses propres formes ; cela ne justifie pas de mettre chaque champ dans une table de
  composants. La séparation physique vise d'abord Sprite/OAM, là où la douleur matérielle est
  concentrée.

### Le verrou réel : un seul indice pour trois choses (constaté le 2026-09-25)

Dans le C émis, `idx` est **à la fois** l'entrée `g_actors[idx]`, le slot `shadow_oam[idx]` et
le numéro d'acteur que connaissent le tick d'animation, le writer OAM et le spawn. Le writer est
**entièrement déroulé**, un bloc par acteur, avec les constantes du sprite écrites en dur
(`sh`, `sz`, `bt`, `tiles_per_frame`) : `main_gen.py` (boucles « OAM actors scène » et « OAM
prefab pool »), `gen_sprite.anim_tick_lines`, `gen_affine`. Deux conséquences :

- **`g_actors` a la taille de l'empreinte OAM, pas du nombre d'acteurs.** Sa dimension est
  `max(placed + ui + pool_slots)` sur les scènes (`Actor g_actors[n_actors]`, `main_gen.py`) : les
  slots d'interface OBJ (`ui`), qui n'ont **aucun acteur**, réservent chacun une struct entière.
  Le gaspillage existe déjà, indépendamment de ce chantier.
- **Compter seulement les porteurs de sprite dans le budget ne libère rien** tant que l'indice
  d'acteur EST le slot OAM : un acteur-logique garde son entrée `g_actors` et son numéro OAM.

**Le side-array a un coût d'exécution nul dans le C généré, mais pas dans les accesseurs.**
Le writer OAM et le tick d'animation étant déroulés par porteur, le build connaît l'emplacement
de chaque entrée : `g_oam_entries[k].frame` est un accès à adresse fixe, comme
`g_actors[idx].sprite.frame` aujourd'hui. En revanche, les accesseurs de script prennent un
`Actor*` (`actor_get_frame(const Actor* s)`) : il leur faut `g_oam_entries[s->oam_entry]`, donc
**un déréférencement** — celui que redoute le commentaire de `actor_types_static.h` (décision
v0.25) — plus un cas « pas de sprite » (`oam_entry < 0` : lecture = 0, écriture = sans effet).
Ce coût ne pèse que sur les lectures/écritures de script, pas sur le rendu ; il reste à peser
contre le gain de RAM. Le commentaire de la struct sera à réécrire avec la marche 2.

### Ce que le transpileur pèse (mesuré le 2026-09-25)

Le transpileur est **découplé du layout C** : `editor/scripting/api.py` déclare chaque propriété
`self.*` en `ApiProp(c_getter=…, c_setter=…)`, et `codegen.py` n'émet que l'appel à l'accesseur
(`actor_get_frame(self)`). Aucun accès de champ n'est écrit par le transpileur. Le layout
vit donc dans un seul fichier, `runtime/include/runtime_api_inline.h` (60 accesseurs, dont 26
touchent `sprite.*`).

- Sur les 29 propriétés `self.*` de `RUNTIME_PROPS`, une vingtaine sont du domaine Sprite :
  `rotation`, `scale`, `sprite_rotation/scale/offset`, `visible`, `anim`, `anim_speed/length/
  loop/finished`, `frame`, `frame_w/h`, `flip_h/v`, `pal`, `obj_mode`, `priority`, `auto_dir`,
  `screen_space`, `affine`. Restent à l'Actor : `position`, `velocity`, `active`, `tag`,
  `direction` ; à la Collision : `grounded`, `box_count`.
- **Déplacer le layout (marche 2) ne change aucun script utilisateur** : seuls les accesseurs de
  `runtime_api_inline.h` et le writer/tick/spawn changent. C'est ce qui rend la marche 2
  invisible pour l'auteur.
- **Compartimenter l'API** (`self.sprite.frame` au lieu de `self.frame`) est en revanche un
  changement de surface : les noms passent par `RUNTIME_PROPS`, `api_reference.py` (catégories),
  `api_reference.json`, le checker (`checker.py`, liste des propriétés de transform), la
  complétion, le refactor, `SCRIPTING.md` / `docs/scripting-reference.md` et les tests
  (`test_scripting_api.py`). Elle est indépendante de la marche 2 et peut la précéder.
- Piège : `actor:get(i)` → `actor_at(i0)` (index 1-based côté Lua) expose l'indice `g_actors`.
  Tant que l'indice d'acteur est le slot OAM, il n'y a pas de sujet ; **la marche 0 doit
  garder cet indice stable et documenté** (un acteur-logique a un indice mais pas de slot).
  De même, `UIImageInfo.actor` et la bande de texte OBJ référencent `g_actors` par indice
  (`gba_engine.h`) : à réviser quand `ui` sort de `g_actors`.

### Le modèle figé : `g_oam_entries[]` réserve l'OAM, `g_actors[]` ne porte que des acteurs

**Proposé par l'auteur le 2026-09-25.** Le tableau qui réservait les slots OAM change de propriétaire :

| Tableau | Un indice = | Taille (max sur les scènes) | Porte |
| --- | --- | --- | --- |
| `g_oam_entries[]` | **une entrée OAM** | `used` = sprites d'acteurs + OBJ d'interface/texte + sprites de pools (≤ 128) | l'état d'affichage |
| `g_actors[]` | **un acteur** | acteurs posés + instances de pools × parties | identité, position, vélocité, tag, collision, lien `oam_entry` |

- **L'invariant migre de l'acteur au sprite** : `shadow_oam[k]` ↔ `g_oam_entries[k]`, même `k`. Le writer
  reste déroulé et à adresse fixe ; seule la clé change. `used` devient LE nombre honnête : un slot
  par consommateur réel.
- **Les consommateurs OAM réels** (inventaire du 2026-09-25 — quatre écrivains de `shadow_oam[]`) :
  (1) sprites d'acteurs posés, (2) sprites des pools de prefabs (`main_gen`) ; (3) bandes de texte
  OBJ et (4) images d'UI OBJ (`gba_engine.h`, via `g_obj_oam_base + oam_rel`). Chacun occupe une
  bande contiguë de `g_oam_entries[]`, connue au build ; `oam_rel` des zones de texte/UI devient un
  décalage dans cette table, plus dans un « slot fantôme » de `g_actors`.
- **`Actor` → `OamEntry` par un lien nullable** : `Actor.oam_entry` = indice dans `g_oam_entries[]`, ou -1. Un
  acteur-logique, un marqueur de prefab (point de tir, ancre de hitbox) n'ont **ni slot ni état
  d'affichage**. Aujourd'hui un marqueur réserve quand même un slot (`attr0=0x0200`).
- **Ce que porte une entrée `OamEntry`** : `frame`, `anim_state/speed/length/loop/finished`, `timer`
  d'animation (le tick d'animation écrit `timer`, aujourd'hui sur l'Actor), `frame_w/h`, `auto_dir`,
  les registres OAM (`visible`, `flip_h/v`, `pal_bank`, `obj_mode`, `priority`), le transform
  **local** (`rotation`, `scale`, `offset`), `affine_slot`, `screen_space`. Le transform **monde**
  (`rotation`, `scale_x/y`) reste sur l'Actor : c'est de l'état de jeu, lisible sans sprite.
- **Table uniforme, types étroits.** Les slots d'UI/texte ont une entrée qu'ils n'utilisent pas ;
  plutôt que des unions par nature de consommateur (complexité), l'entrée est **étroite** (`u8`/`s8`/
  `s16`, ~24 o au lieu de ~100) : le rétrécissement des types n'est plus « à part », il rend la table
  uniforme bon marché. Alternative écartée : un registre de propriétaires + un second tableau d'états.
- **Accesseurs** : `actor_get_frame(const Actor*)` passe par `g_oam_entries[s->sprite]` ; `sprite < 0` →
  lecture 0, écriture sans effet (`self.visible = true` sur un acteur sans sprite ne fait rien). Le
  coût d'un déréférencement, décrit plus haut, reste borné aux accès de script.
- **La marche 3 s'y loge sans changer le modèle** : les N apparences d'un acteur sont des données ROM ;
  le slot porte l'identifiant de l'apparence courante. Un swap change l'état du slot, il n'ajoute pas
  d'entrée. VRAM : tout résident (tranché, voir « Marche 3 »).
- **Le budget** : `over_budget` porte sur `used` de `g_oam_entries[]`. Les acteurs sans sprite n'y figurent
  pas ; le plafond de 128 vaut pour `g_oam_entries[]`, celui de `g_actors[]` est la RAM.
- **Indices exposés à ne pas casser** : `actor:get(i)` → `actor_at(i0)` et `UIImageInfo.actor`
  restent des indices de `g_actors[]`, désormais vraiment « d'acteur » (plus jamais un slot OAM).

**Le nom (tranché le 2026-09-25).** Le type est `OamEntry`, le tableau `g_oam_entries[]`, le lien
`Actor.oam_entry`. Écartés : `Sprite` (déjà défini par libgba, `gba_sprites.h`), `SpriteComponent` (le
composant d'acteur de l'éditeur : un seul des consommateurs de la table), `SpriteOAM` (mêle le
sprite et la mémoire OAM entière). « Entrée de l'OAM » est le mot que le code emploie déjà
(`oam_alloc`, « OBJ »), et l'entrée est l'état logiciel derrière un `OBJATTR` de `shadow_oam`.

À trancher à l'implémentation (0b) : la forme exacte du lien pour un groupe de pool dont certains
membres n'ont pas d'entrée (table de build, pas un simple décalage).

### Les marches (staging, sans réécriture ECS)

0. **Introduire `g_oam_entries[]`.** En deux temps, pour rester vérifiable :
   - **0a — miroir. LIVRÉE (2026-09-25).** `g_oam_entries[]` créé ; le sous-struct `sprite` et les
     registres OAM de la racine (`visible`, `flip_h/v`, `pal_bank`, `obj_mode`, `priority`,
     `screen_space`, `timer`) y migrent. `Actor.oam_entry` = même indice que l'acteur, `g_actors[]`
     gardant sa taille. Le transform monde (`rotation`, `scale_x/y`) reste à l'Actor. Déplacement
     mécanique de `runtime_api_inline.h`, du writer, du tick d'animation, de `gen_affine`, du spawn
     et de `scene_init` ; `project_oam_entry_count` distingue déjà les deux tailles (égales en 0a).
     Vérifié : 4 projets démo se buildent à froid, et leur `main.c` d'avant, renommé par les mêmes
     règles, ne diffère de celui d'après que par les ajouts voulus (déclaration, remise à zéro,
     pose du lien). Le code de la ROM grossit de 100 à 170 octets : l'indirection des accesseurs.
   - **0b — géométrie. LIVRÉE (2026-09-25).** `oam_alloc.py` calcule deux espaces :
     `g_actors[]` = `[posés][pools]`, `g_oam_entries[]` = `[posés à sprite][interface][pools à
     sprite]`. `has_oam_entry` est LE prédicat (writer et budget le partagent) ; `Actor.oam_entry`
     vaut -1 pour un acteur sans sprite ou un marqueur de prefab ; les accesseurs de script y sont
     neutres (entrée nulle) ; les bandes texte/UI s'ancrent à `OamLayout.ui_start` ; le budget
     (`actor_budget`, validateur) compte des entrées, plus des acteurs. Le spawn avance dans les
     deux espaces (`_i += groupe`, `_e += entrées par instance`). MyGame : `g_actors[4]` → `[1]`.
     Vérifié : 4 démos à froid, et une démo synthétique (contrôleur sans sprite en tête, marqueur
     enfant de prefab, UI forcée à 2) qui compile et émet le C attendu. Non vérifié sur émulateur.
     *Décision prise en route :* un budget qui compte les entrées fait que les tests d'allocation
     doivent dire quels acteurs affichent (`tests/oam_fixtures.py`). Intention d'origine : on brise l'identité : `g_actors[]` se compacte (sans `ui`, sans marqueurs),
     les bandes UI/texte s'ancrent dans `g_oam_entries[]`, `scene_oam_layout` calcule les deux tailles
     (`test_0a_les_deux_tables_ont_la_meme_taille` marque cette frontière et devra changer).
     C'est là que les prefabs poolés (groupes contigus) demandent une table de build.
1. **Le budget compte les slots de `g_oam_entries[]`.** Conséquence de 0b, plus « `oam_alloc` seul ».
2. **L'entrée OAM devient optionnelle** → LIVRÉE avec la 0b : `Actor.oam_entry` nullable (-1),
   `g_actors[]` dimensionné sur les seuls acteurs. L'acteur ne porte plus aucun champ d'affichage.
   Sans coût d'exécution (voir ci-dessus).
3. **N sprite components, 1 actif** → swap d'apparence. **OUVERTE (2026-09-25), conception figée
   ci-dessous, code non commencé.** La plus grosse marche.

#### Marche 3 — le modèle (décisions de l'auteur, 2026-09-25)

- **VRAM : tout résident.** Toutes les apparences déclarées restent en VRAM, comme tous les sprites le
  sont déjà : `sprite_offsets_for` donne à chaque sprite une base fixe, calculée sur le PROJET (pas par
  scène), et chaque `scene_init` recopie ceux de sa scène plus les sprites de prefab. N apparences =
  N sprites de plus sous le même plafond de 1024 tuiles OBJ, vérifié au build par le contrôle
  existant. Pas de streaming : ce serait un mécanisme nouveau (copie à la demande, allocation
  dynamique, partage entre acteurs), sans besoin démontré.
- **Un acteur affiche UN seul sprite (une entrée OAM) ; ses SpriteComponent sont actifs ou non, et
  en activer un désactive le précédent.** `SpriteComponent.active` existe déjà : il devient le
  SÉLECTEUR. Un acteur peut donc porter plusieurs `SpriteComponent` (le modèle le permet déjà : les
  `id` de composants sont uniques au sein de l'acteur), avec l'invariant « au plus un actif ». Ce n'est
  pas une liste d'apparences dans un composant.
- **L'entrée OAM est réservée dès qu'au moins un composant a un sprite** (`has_oam_entry` ne teste
  plus le seul composant actif : elle teste l'existence d'un sprite). Aucun actif au départ = entrée
  réservée mais cachée.
- **Swap = changer l'apparence de l'entrée, pas l'entrée.** `OamEntry` gagne un `u8 appearance`. Les
  constantes aujourd'hui écrites en dur dans le C émis (base de tuiles `bt`, forme, taille,
  `tiles_per_frame`, tailles de frame, tables d'animation `sprite_X_anim_dirs`…) passent dans une table
  ROM par apparence ; le writer OAM et le tick d'animation lisent `appearance_table[entry.appearance]`.
  C'est le SEUL coût d'exécution de la marche 3 sur le chemin chaud ; un acteur à une seule apparence
  garde le C émis actuel (constantes), sans table. *Révisé à la 3a : pas de table ROM.* Le writer et le
  tick étant déjà déroulés par entrée avec des constantes, on les déroule aussi PAR APPARENCE — un
  `switch` sur `OamEntry.appearance`, chaque cas gardant ses constantes et ses tables d'animation
  nommées. Pas de pointeurs, pas de test de NULL sur les tables optionnelles (sfx, événements de
  frame) ; le coût est du code (proportionnel aux apparences), et un `switch` par entrée et par
  frame — seulement pour les acteurs multi-apparence.
- **À l'activation d'un composant** : l'état d'animation repart à l'`initial_state` de ce composant,
  frame 0, timer 0 ; la palette OBJ est celle du composant ; `frame_w/h` sont réécrits.
- **Affine** : le slot de matrice appartient à l'ENTRÉE (réservé au build). Si un composant de l'acteur
  est affine, l'entrée l'est ; les autres apparences sont rendues avec la matrice de l'entrée (à
  documenter à l'ouverture de 3b, ne pas laisser deviner).

#### Marche 3 — l'API de script (à trancher avant 3c)

**Tranché à l'ouverture de la 3c (2026-09-25) — à valider par l'auteur.** Forme proposée par l'auteur :
`self.sprite = self.sprite.myID`, mais `self.sprite` y désignerait deux choses (le composant actif et le
conteneur des composants), et un id valant un nom de propriété serait ambigu. Le code donne un précédent
plus net : le commentaire de `self.anim` dit que changer d'état est un GESTE (il remet frame et timer à
zéro), pas une propriété qu'on assigne — `self:play_anim(nom)`. Activer une apparence remet aussi
l'animation, les tailles et la palette : c'est le même cas. Retenu, donc, sans type de référence :

- `self:activate_sprite("id")` — le geste ; « activate » reprend le mot de la case « Active » de
  l'inspecteur, et « activer l'une désactive l'autre ».
- `self.active_sprite` — lecture seule, comparable par son nom (`self.active_sprite == "blesse"`).
- `id` = celui du composant sprite ; résolu à la compile en `SPRITE_<ACTEUR>_<ID>` (domaine
  `DOMAIN_SPRITE_ID`, comme `ANIM_*`). Un id inconnu est une ERREUR du checker ; l'appel sur un autre
  acteur (`other:activate_sprite`) est refusé (l'id appartient à l'acteur qui exécute).
- Les noms de `self.sprite` / `self.sprites` restent LIBRES pour la compartimentation de l'API
  (`self.sprite.frame`) : aucun nom n'est réservé ici. Changer l'orthographe est un changement de
  table dans `api.py` (`self:activate_sprite`, `self.active_sprite`).

#### Marche 3 — les sous-étapes

- **3a — l'apparence devient une donnée (sans changement visible). LIVRÉE (2026-09-25).**
  `Appearance` (sprite, base de tuiles, origine) dans `gen_sprite.py` ; `oam_write_lines` et
  `anim_tick_variants` émettent une apparence par cas, `OamEntry.appearance` (`u8`, +1 octet : 34
  au total) choisit. Les deux writers de `main_gen` (acteurs posés, pools) et le tick passent par
  ces helpers avec UNE apparence. Vérifié : le `main.c` des 4 démos est IDENTIQUE octet pour octet
  avant/après ; un build OrbitTest où chaque acteur reçoit une 2e apparence factice (58 `switch`)
  compile ; tests unitaires dans `tests/graphics/test_oam_appearances.py`. Reste pour 3b : construire la
  liste d'apparences depuis les composants (aujourd'hui elle n'en a qu'une, le premier), et poser
  `frame_w/h`, palette, `anim_state` initial et VRAM par apparence (init, spawn, pools).
- **3b — le modèle éditeur. LIVRÉE (2026-09-25), sauf le swap à l'exécution (3c).**
  - *Modèle* : trois fonctions dans `core/models/components.py` sont la SEULE façon de lire « le »
    sprite d'un porteur — `sprite_components`, `displayed_sprite_component` (l'actif),
    `affine_sprite_component` (l'affine appartient à l'entrée) — plus `competing_sprite_components`.
    `get_sprite_comp` a disparu ; les 22 sites ont été repris.
  - *Build* : `oam_alloc.owner_appearances/initial_appearance` (source unique) ; `has_oam_entry` =
    « au moins une apparence » (une entrée cachée est réservée si aucune n'est active) ; `rom_build`
    charge les sprites de TOUTES les apparences (`extra_sprites`, prefabs et parties compris) ;
    l'init pose `appearance = n` et cache l'entrée si aucune n'est active ; writer et tick émis par
    apparence (une apparence fixe, sans états, donne un `case` vide) ; palettes propres de chaque
    apparence réservées (`palette_alloc._owner_sprites`).
  - *Validation* : `_check_sprite_appearances` (deux actives = erreur) ; événements de frame vérifiés
    pour chaque apparence.
  - *Éditeur* : activer une apparence désactive l'autre en UNE entrée d'historique ; une apparence
    ajoutée naît inactive si une autre est affichée ; aperçu, canvas et barre de statut suivent
    l'apparence affichée (le canvas ne dessine plus un sprite que la ROM n'afficherait pas).
  - *Vérifié* : `main.c` des 4 démos identique ; builds synthétiques (acteur et prefab poolé à 2
    apparences : seconde inactive, seconde active, aucune active) compilent ; 13 tests de modèle et 5
    tests d'inspecteur. *Correction (2026-09-25)* : la jauge « sprites / tuiles / cycles » de la barre
    d'état (`GbaStatusBar.update_scene`) comptait tout acteur portant un composant sprite — même vide
    ou sans sprite résolu — et plantait sur un sprite introuvable ; elle lit maintenant le prédicat du
    build (`has_oam_entry`), compte les tuiles de toutes les apparences et le coût par scanline de la
    seule apparence affichée (`tests/ui/test_gba_status_bar.py`). Le build et le budget de l'inspecteur
    étaient déjà justes : un composant vide n'y réservait rien. *Changement de comportement* : un acteur dont le SEUL composant sprite est
    inactif réserve désormais une entrée (cachée) au lieu de n'en avoir aucune.
  - *Reste pour 3c* : les constantes propres à une apparence (`frame_w/h`, palette, `anim_state`
    initial) ne sont posées que pour l'apparence de départ ; l'ACTIVATION à l'exécution doit les
    reposer, et n'a pas encore d'API de script.
- **3c — l'activation à l'exécution et l'API de script. LIVRÉE (2026-09-25).**
  - *Primitif C* : `actor_set_appearance(Actor*, n)` repose `frame_w/h`, `pal_bank`, `auto_dir` depuis
    `g_appearance_init` (table ROM PAR SCÈNE, `AppearanceInit`, une ligne par apparence des porteurs
    multi-apparence — `gen_appearance.py`), remet frame/timer/état à 0 ; `OamEntry.appearance_base` =
    1re ligne + 1 (0 = rien à activer : un acteur mono-apparence ne lit jamais la ligne d'un autre) ;
    sans entrée OAM, sans effet. `OamEntry` = 36 octets.
  - *Noms d'animation* : pour un acteur multi-apparence, `anim_names` est l'UNION des états de ses sprites
    et `ANIM_*` une expression qui lit l'apparence de `self` (`<sym>_anim_map[apparence][k]`, 255 = état
    absent, ignoré par `actor_play_anim`). Un acteur mono-apparence garde des constantes littérales.
  - *Script* : `self:activate_sprite`, `self.active_sprite`, domaine `DOMAIN_SPRITE_ID`, checker,
    transpileur, `sprite_ids` dans les deux contextes.
  - *Vérifié* : sonde C native (constantes reposées, sans-entrée, mono-apparence, état absent) ; 10 tests
    de script ; build TacticsDemo avec un script Lua réel (deux apparences, `Move` absent du soldat) ;
    ids inconnus et appel sur `other` refusés. Démos : seule la ligne `g_appearance_init` est ajoutée.
  - *Limites connues* : la constante `ANIM_*` d'un acteur multi-apparence utilise `self` — un helper
    de script sans `self` qui cite une animation ne compilera pas ; les scripts de PREFAB poolé ne
    reçoivent pas d'`anim_names` (héritage : `pf_anim` reste vide), donc `play_anim` y est déjà hors
    contrat.
  - *Suivi de renommage de l'`id` (livré, 2026-09-25)* : renommer l'`id` d'un composant sprite dans
    l'inspecteur réécrit `self:activate_sprite("id")` et `self.active_sprite == "id"` dans le script
    de SON propriétaire seulement (`Project.rename_sprite_id_refs`, `refactor.rename_in_files`) — deux
    acteurs peuvent avoir chacun un « blesse ». La commande `RenameSpriteIdCmd` défait l'`id` ET le
    script d'un seul Ctrl+Z. Un id vide ou déjà pris est refusé ; deux ids qui donnent la même
    constante C (`c_ident`) sont une erreur du validateur. Le suivi couvre désormais aussi
    `self.<propriété> == "nom"` (`self.anim`, `self.active_sprite`) : un renommage d'animation
    réécrit `self.anim == "walk"`, ce qu'il oubliait. *Limite* : un behavior PARTAGÉ qui cite l'id
    n'est pas réécrit — le checker signale l'id devenu inconnu au build.

**Types étroits — LIVRÉ (2026-09-25).** `OamEntry` 92 → 32 octets, `Actor` 96 → 68, mesurés par
le compilateur hôte (`test_les_tailles_des_structs_ne_regressent_pas` fige les plafonds). Champs 16
bits d'abord, puis 8 bits : aucun remplissage. `s16` : `frame`, `timer`, `anim_speed`,
`anim_length`, transform (rotation, scale Q8, offset), `tag`, `oam_entry`, `last_x`, `slope_acc` ;
`u8` : drapeaux et registres OAM, `anim_state`, `frame_w/h`, `active`, `grounded`, `box_count` ;
`s8` : `dir_*`, `affine_slot`. Position et vélocité restent en `int` (Q8, 32 bits requis). ROM
plus petite d'environ 4 Ko sur OrbitTest et TacticsDemo (moins d'octets par instruction d'accès).
*Limite assumée :* un script qui écrit une rotation locale hors de ±32767° ou une échelle hors de
×127 voit la valeur tronquée à 16 bits ; les registres à valeurs bornées sont masqués par leurs
accesseurs. Ancienne remarque, pour mémoire : les drapeaux étaient tous des `int` de 4 octets
pour des valeurs qui tiennent sur 1. Les rétrécir gagne de la place sans toucher au layout logique — à peser à part.
### Ce que ça touche (au premier regard)

`runtime/include/actor_types_static.h` (struct `Actor`), `editor/codegen/oam_alloc.py` (budget),
le writer OAM et `scene_init`/spawn dans `main_gen.py`, le modèle éditeur (un acteur porte 0..N
sprite components), et la validation (un budget par sprites affichés). À préciser à l'ouverture.

**Chantier CLOS (2026-09-25) — le modèle est complet côté code.** Marches 0a, 0b, 2, 3a, 3b, 3c
et le rétrécissement des types sont toutes livrées ; l'API de script (`self:activate_sprite`,
`self.active_sprite`) est validée par l'auteur, avec le suivi de renommage d'id. Deux points sont
sortis de ce chantier plutôt que d'y rester ouverts indéfiniment :

- la **vérification émulateur** de la marche 0b (mesurée seulement par le build headless et une
  sonde native) reste à faire — un résidu mineur, pas une décision de conception ;
- la piste **Collision — un `Contact` d'événement** (normale acteur↔acteur, non verrouillée) a été
  extraite en un chantier technique séparé, encore À OUVRIR — voir
  [ROADMAP.md](../../ROADMAP.md#piste-collision--un-contact-dévénement-pas-une-dernière-collision).
