/* SPDX-License-Identifier: Zlib
   Copyright (c) 2026 Yasor Rovic

   Licence zlib — PAS la GPL de l'éditeur (cf. runtime/LICENSE). Ce fichier est
   recopié dans le projet de l'utilisateur au build, puis compilé dans sa ROM :
   le jeu produit lui appartient entièrement, il peut le vendre, et il n'a
   aucune notice à joindre à sa ROM. */
/* actor_types_static.h — structs et constantes GBA (partie non générée).
   Inclus depuis actor_types.h (généré par build.py). */
#ifndef ACTOR_TYPES_STATIC_H
#define ACTOR_TYPES_STATIC_H

#define MAX_BOXES 4   /* boxes de collision max par acteur */

typedef struct CollisionShape {
    s8  x, y;   /* offset relatif au pivot (pixels) */
    u8  w, h;   /* dimensions (pixels) */
    u8  solid;  /* 1=physique, 0=trigger */
    u8  active; /* 0 = la boîte n'existe plus pour personne : ni carte, ni chevauchement */
    u8  tag;    /* BOXTAG_* */
    u8  grounded; /* cette boîte reposait-elle sur le sol à la fin de la frame ? Écrit par
                     resolve_actor_tiles ; reste 0 pour une boîte non solide, que la carte ignore */
} CollisionShape;

/* Une Area : une zone de jeu posée dans la scène, sans sprite, sans OAM, sans script et hors du pool d'acteurs. Elle porte une
   boîte (la forme de sa CollisionShapeComponent) ; `x`/`y` sont en Q8 comme ceux d'un acteur, pour que la même lecture
   (`>>8`) serve les deux. `g_areas[]` est rempli à l'entrée de chaque scène par le build. */
typedef struct Area {
    int x, y;            /* position monde, Q8 */
    CollisionShape box;  /* la forme : offset, taille, tag */
    u8  active;          /* 0 = l'Area ne touche plus personne (un `exit` part au partenaire encore actif) */
    u8  held;            /* 1 = son parent est inactif ou détruit : elle ne touche personne, sans avoir été éteinte (recalculé à chaque frame) */
    u16 parent;          /* emplacement de l'acteur posé qu'elle suit, plus un ; 0 = aucun. Sa position est alors recomposée à chaque
                            frame (cf. `area_parent_lines`) : une écriture de script est sans effet. */
} Area;

/* Vec2/Vec3/Rect — les valeurs COMPOSÉES du sous-ensemble Lua (vec2(x,y),
   vec3(x,y,z), rect(x,y,w,h)). Des entiers, rien d'autre : pas de virgule
   flottante sur GBA. + et - composante à composante et * par un entier ne
   valent que pour vec2/vec3 — cf. actor_api_static.h (vec2_add et consorts)
   et scripting/vec_types.py côté transpileur, seul et même repère de type
   entre checker.py et codegen.py. */
typedef struct { int x, y; }    Vec2;
typedef struct { int x, y, z; } Vec3;
typedef struct { int x, y, w, h; } Rect;

/* Une instance d'un MODÈLE (un prefab) : l'emplacement de sa racine dans `g_actors[]` et l'entrée
   d'état d'affichage de ses membres (-1 : aucun n'affiche rien). Chaque modèle a sa table, émise
   par le build (`g_model_<Scène>_<Prefab>[]`) : le spawn la parcourt pour trouver un emplacement
   libre, `actor:count("M")` et `actor:get("M", i)` pour parcourir les instances vivantes. */
typedef struct ModelSlot { u16 slot; s16 entry; } ModelSlot;
/* Seules les instances POSÉES d'un modèle et celles de sa réserve à part y figurent ; celles qui naissent
   dans le pool partagé se retrouvent à `Actor.type_id`. */

/* Le DESCRIPTEUR d'un type d'emplacement : ce que le runtime lit au modèle, pour un acteur posé comme pour un
   acteur né, par `Actor.type_id`. Une table par scène (`g_model_desc_<Scène>[]`), émise par le build et rangée en
   IWRAM. Le type 0 ne décrit rien ; un champ nul veut dire « rien ».
     body_mode      : 0 aucun mouvement automatique (pas de corps, ou Static), 1 Character, 2 Kinematic, 3 Rigid ;
     can_sleep      : un Rigid peut s'endormir ;
     tile_mask      : les rangs des boîtes résolues contre la carte de collision, 0 si le type ne la rencontre pas ;
     interactor     : 1 le type porte le tag d'acteur Player (il interagit), 2 de même sans sprite (son regard suit
                      sa vitesse hors du tick d'animation) ;
     gravity_scale  : facteur de la gravité de scène, Q8 (256 = x1) ; 0 pour un corps qui l'ignore ;
     sfx, sfx_vol   : l'effet du SoundFxComponent déclenché par un bouton ou une action, et son volume ;
     sfx_input      : le masque de ce bouton ou de cette action, 0 sans déclencheur par l'input ;
     on_tile        : le `on_tile_collide` du script du type ;
     on_crushed     : le `on_crushed` d'un Character (appelé aussi quand la carte arrête un transport) ;
     on_update, on_late_update : les crochets d'image du script du type ;
     on_contact     : `on_collision_enter`, `on_collide`, `on_collision_exit` du script du type (soi, l'autre, tag de sa
                      boîte, tag de celle de l'autre), dans cet ordre ; NULL s'il n'y répond pas. */
struct Actor;   /* défini plus bas : sans cette déclaration, le nom ne vivrait que dans le prototype des crochets */
typedef struct ModelDesc {
    u8 body_mode; u8 can_sleep; u8 tile_mask; u8 interactor;
    s16 gravity_scale; s16 sfx; u16 sfx_input; u8 sfx_vol;
    void (*on_tile)(struct Actor*, int, int);
    void (*on_crushed)(struct Actor*, struct Actor*);
    void (*on_update)(struct Actor*);
    void (*on_late_update)(struct Actor*);
    void (*on_contact[3])(struct Actor*, struct Actor*, u8, u8);
} ModelDesc;
enum { BODY_MODE_NONE = 0, BODY_MODE_CHARACTER = 1, BODY_MODE_KINEMATIC = 2, BODY_MODE_RIGID = 3 };

/* Les modules à PAIRES (blocage, appui au sol) se lisent par couple de types, que les deux emplacements soient posés
   ou nés : une table par module et par scène donne, pour un type et un type partenaire, la suite `n` de ses entrées
   à partir de `first` (couples de boîtes et réglages, propres au module). */
typedef struct PairRun { u16 first; u8 n; } PairRun;

/* Le lien d'un emplacement à son parent (`g_slot_link`, runtime_api_inline.h). */
typedef struct SlotLink { s16 parent; u8 depth; u8 visible; int ox, oy; s16 rot; u16 sx, sy; } SlotLink;

/* Deux tables, deux unités :

     g_actors[]      — un indice = un ACTEUR : identité, position, vélocité,
                       transform MONDE, collision, et le lien `oam_entry` vers
                       son affichage ;
     g_oam_entries[] — un indice = une ENTRÉE de l'OAM : tout l'état d'affichage.
                       C'est ce tableau que `shadow_oam[k]` double, entrée pour
                       entrée.

   `Actor.oam_entry` est l'indice, dans `g_oam_entries[]`, de l'entrée que l'acteur
   affiche. Le writer OAM et le tick d'animation, émis au build, connaissent cet
   indice à l'avance (adresse fixe, aucun déréférencement) ; seuls les accesseurs
   de script, qui reçoivent un `Actor*`, passent par le lien (`actor_oam_entry`).

   Les deux tables n'ont plus le même indice ni la même taille : un acteur SANS
   sprite (contrôleur, déclencheur, marqueur de prefab) n'a pas d'entrée — son
   `oam_entry` vaut -1 —, et les OBJ d'interface et de texte ont une entrée sans
   acteur. `Actor.oam_entry` est le lien, jamais l'identité. La géométrie (qui a
   quelle entrée) est calculée au build par `codegen/oam_alloc.py`, seule source.

   Le décor n'a pas de type parce que le calque EST le matériel (les layer_ et
   tilemap_ de gba_engine.h, indexées par le numéro de plan). */

/* L'état d'affichage derrière UNE entrée de l'OAM (un `OBJATTR` de shadow_oam),
   quel que soit son consommateur : le sprite d'un acteur aujourd'hui, les bandes
   de texte et l'interface à la marche 0b. D'où `OamEntry` : ce n'est ni le
   `SpriteComponent` de l'éditeur (un seul consommateur), ni le `Sprite` de libgba
   (le nom est pris). Sa DÉFINITION n'est pas ici : les états, les directions et
   les vitesses vivent en ROM, dans les tables
   `sprite_{nom}_anim_dirs/_state_start/_state_speed/_state_loop` émises par
   main_gen. La coupure est const/variable, pas classe/classe. */
/* Types ÉTROITS (s16/u8/s8) : cette table compte jusqu'à 128 entrées, et un acteur
   « chaud » en coûte une par frame d'écriture OAM — 32 bits par drapeau était du
   gaspillage. Deux règles :
     - les champs 16 bits d'abord, puis ceux de 8 bits : aucun remplissage ;
     - une valeur écrite par un SCRIPT tient dans son type par construction du
       domaine (indice de frame < 1024 tuiles, angle en degrés, échelle Q8 ≤ ×127,
       pixels d'offset) ; les accesseurs de runtime_api_inline.h masquent ce qui
       peut l'être (pal & 0xF, priority & 3, obj_mode & 3, flips à 0/1). */
/* Ce qu'ACTIVER une apparence pose sur l'entrée OAM (marche 3c). Une ligne par
   apparence de chaque porteur multi-apparence, dans une table ROM PAR SCÈNE
   (`g_appearance_init`) : le palette et les tailles dépendent de la scène (banques
   OBJ) et du sprite, pas de l'acteur seul. */
typedef struct AppearanceInit {
    u8 frame_w, frame_h;   /* taille de frame du sprite de cette apparence, en pixels */
    u8 pal_bank;           /* banque OBJ de sa palette */
    u8 facing_auto;        /* SpriteComponent.facing_auto de cette apparence */
} AppearanceInit;

typedef struct OamEntry {
    /* ── 16 bits ─────────────────────────────────────────────────────── */
    s16 frame;             /* index de frame dans le spritesheet */
    s16 timer;             /* ticks écoulés depuis la dernière frame (tick d'animation) */
    /* Surcharge de la vitesse (ticks entre deux frames) de l'état courant —
       même mécanisme que UIImageInfo.speed (cf. gba_engine.h), amené sur
       l'acteur. 0 = la vitesse réglée pour cet état dans le Sprite Editor,
       qui reste la source de vérité (self.anim_speed). Ne se remet pas à 0
       tout seul quand l'état change : un effet temporaire (temps ralenti)
       se referme explicitement par le script qui l'a ouvert. */
    s16 anim_speed;
    /* Écrits à CHAQUE tick d'animation par main_gen._anim_tick_lines. Ce
       n'est PAS une duplication des tables ROM : `anim_length` est la
       longueur du bloc de la DIRECTION actuellement jouée, que le tick
       trouve par un parcours de `anim_dirs[]` avec repli sur la direction
       omni. Ces trois champs MÉMOÏSENT ce parcours — un script qui lit
       self.anim_length ne le refait pas. (Évalué puis écarté en v0.25 :
       exposer les tables aux scripts déplacerait la boucle dans chaque
       lecture.)
         anim_length   : nombre de frames de la direction actuellement jouée
                         de l'état courant (self.anim_length).
         anim_loop     : 1 = l'état courant boucle (self.anim_loop).
         anim_finished : 1 = état NON bouclé, actuellement sur sa dernière
                         frame — reste vrai tant qu'on n'a pas changé
                         d'état, comme `collision.grounded` reste vrai tant
                         qu'on ne quitte pas le sol (self.anim_finished). */
    s16 anim_length;
    /* Transform LOCAL, composé PAR-DESSUS le transform monde de l'Actor
       (self.sprite_rotation / self.sprite_scale / self.sprite_offset) : la
       rotation s'AJOUTE à la rotation monde, le scale se MULTIPLIE par le scale
       monde, l'offset déplace le sprite dans le repère de l'actor (il tourne et
       scale avec lui). Le sprite n'a pas de position monde : elle reste x/y. */
    s16 rotation;          /* local, degrés */
    s16 scale_x;           /* local, Q8 */
    s16 scale_y;           /* local, Q8 */
    s16 offset_x;          /* local, pixels */
    s16 offset_y;          /* local, pixels */
    /* 1re ligne de ce porteur dans `g_appearance_init[]`, PLUS UN : la ligne de
       l'apparence n est `appearance_base - 1 + n`, et 0 veut dire « rien à activer ».
       Posé à l'init/au spawn des seuls porteurs à PLUSIEURS apparences. */
    s16 appearance_base;

    /* ── 8 bits ──────────────────────────────────────────────────────── */
    u8 anim_state;         /* index de l'AnimState courant */
    u8 anim_loop;
    u8 anim_finished;
    /* Taille de frame du sprite, en pixels — posée une fois à l'init/au
       spawn depuis SpriteAsset.frame_w/frame_h (self.frame_w/self.frame_h,
       lecture seule). Utile pour centrer un effet ou trouver les bords d'un
       AUTRE acteur (other.frame_w) sans dupliquer sa géométrie dans un
       script. Par instance et non en #define : le script d'un prefab poolé
       est une fonction C partagée par toutes ses instances. Le matériel
       plafonne un objet à 64 px. */
    u8 frame_w, frame_h;
    u8 facing_auto;        /* 1 = Actor.facing_x/facing_y suivent la dernière direction non nulle
                              (dir_x/dir_y, elles, sont toujours recalculées depuis vx/vy) */
    s8 face_x;             /* dernier dir_x NON nul vu par le tick d'animation : le côté vers lequel
                              l'acteur REGARDE. `dir_x` retombe à 0 à l'arrêt ou en montée droite ;
                              c'est ce côté-là que le repli de direction retient (cf. gen_sprite) */
    /* Registres OAM. `visible` = 0 cache l'objet ; `pal_bank`, `obj_mode` et
       `priority` sont les trois registres d'attr0/attr2, tous modifiables par
       script. `priority` : ordre d'affichage face aux BG layers (attr2 bits
       10-11), 0=devant tous, 3=derrière tous — self.priority ; posée au build
       depuis la valeur authorée (0 pour un acteur poolé, sans sens pour un
       template, cf. core/models/scene.py). */
    u8 visible;
    u8 flip_h, flip_v;     /* 1 = miroir */
    u8 pal_bank;           /* palette OAM (0-15) — self.pal */
    u8 obj_mode;           /* 0=normal, 1=semi-transparent, 2=fenêtre-objet (OBJWIN) */
    u8 priority;
    /* Laquelle des apparences de l'acteur cette entrée affiche (marche 3 : un
       acteur affiche UN sprite, mais peut en porter plusieurs). Toujours 0 tant
       qu'un acteur n'a qu'une apparence : le C émis ne le lit alors pas. */
    u8 appearance;
    /* 1 = x/y de l'acteur sont des pixels d'ÉCRAN (UI en sprite), la caméra ne
       les touche pas. Posé au build depuis l'Actor de l'éditeur ; lecture seule
       côté script (self.screen_space) : le C de rendu émis diffère selon la
       valeur, la changer en jeu n'aurait donc aucun effet. Posé de même au
       spawn d'un acteur né, depuis son prefab. */
    u8 screen_space;
    /* >= 0 : le sprite est affine (« Affine transform » coché, ou enfant qui
       tourne avec un parent affine, cf. gen_affine.compute_affine_info) ; posé à
       l'init d'un posé comme au spawn d'un né. Aucune matrice n'est réservée :
       le rendu en prend une à la frame et écrit ici son numéro (0-31). -1 = OAM
       normale : le transform monde de l'acteur et le transform local ci-dessus
       gardent leur valeur, mais aucune matrice n'est écrite et rien ne les
       affiche. */
    s8 affine_slot;
    /* Point de pivot du sprite, pixels, depuis le CENTRE du cadre ((0,0) = le
       centre). Rotation, échelle et flip s'exercent autour de lui
       (self.sprite_pivot). Sur 8 bits : un objet plafonne à 64 px, ±127 suffit
       largement et l'entrée n'y gagne que 2 octets (36 → 38). */
    s8 pivot_x, pivot_y;
} OamEntry;

typedef struct Actor {
    /* Position et vélocité MONDE, en Q8 (256 = 1 pixel) depuis le
       2026-08-20 — le point fixe existait déjà dans cette même
       struct pour scale_x/y, il n'avait simplement jamais atteint la
       position. self.position (script) continue de ne rendre/accepter que
       des pixels entiers ; self.velocity, elle, expose le Q8 directement —
       rupture assumée plutôt qu'un second nom (self.velocity_q8) à côté du
       premier. self:apply_velocity() ajoute vx/vy à x/y SANS convertir :
       c'est exactement ce qui fait vivre le sous-pixel d'une frame à
       l'autre. */
    int x, y;               /* position monde, Q8 */
    int vx, vy;             /* vélocité, Q8 */
    /* Transform MONDE. C'est de
       l'ÉTAT DE JEU : toujours lisible et écrivable, avec ou sans slot de
       matrice affine. Ce qui décide s'il se VOIT est `OamEntry.affine_slot`.

       Champs PAR-ACTOR et non par slot : un script de prefab poolé est une
       fonction C partagée par toutes ses instances, mais chaque instance a sa
       propre struct Actor (donc ses propres valeurs) et un slot différent.
       Un global par slot aurait exigé de connaître le slot à l'écriture et
       violait l'inclusion mono-texte des headers (copie `static` par TU). */
    s16 rotation;          /* monde, degrés 0-359 (self.rotation) */
    s16 scale_x;           /* monde, Q8 (256 = 100%) — self.scale */
    s16 scale_y;           /* monde, Q8 */

    /* 16 bits, puis 8 bits (aucun remplissage) — cf. OamEntry pour la règle. */
    s16 name;              /* ACTOR_* — type de l'acteur (≥ 255 dès qu'un pool est grand) */
    /* Indice de son entrée dans g_oam_entries[] (cf. l'en-tête ci-dessus), -1 = sans. */
    s16 oam_entry;
    /* L'indice de CET emplacement dans `g_actors[]`, posé une fois à l'entrée de scène : c'est aussi
       celui de son bloc d'état de script dans `g_obj_state` (cf. runtime_api_inline.h). Il évite la
       division par la taille d'un `Actor` qu'une soustraction de pointeurs coûterait. */
    u16 slot_index;
    /* GÉNÉRATION de l'emplacement : +1 quand l'acteur qui l'occupait est détruit, quand un autre y
       naît, et à chaque entrée de scène. Une référence rangée dans une variable
       (`actor_ref_make`) retient la génération qu'elle a vue ; si l'emplacement a changé de
       main depuis, elle ne désigne plus rien (`actor_ref_get` rend nil) au lieu de désigner
       en silence l'acteur suivant. 16 bits : une référence périmée ne redevient valide qu'après
       65 536 générations de son emplacement (256 avec un octet). */
    u16 gen;
    u8 active;             /* 0 = ignoré (update + rendu désactivés) */
    /* L'emplacement est OCCUPÉ : posé par la scène, ou pris par un spawn. Un acteur DÉTRUIT libère
       son emplacement (alive = 0) ; un acteur seulement DÉSACTIVÉ (active = 0) le garde, reste
       adressable et peut être réactivé. Seul un emplacement libre est repris par un spawn. */
    u8 alive;
    /* Type runtime de l’acteur, posé ou spawné. Indexe le descripteur de la scène.
       Chaque partie de prefab a son propre type. Le type 0 est réservé. */
    u8 type_id;
    s8 dir_x;              /* TRAJECTOIRE X courante : -1 | 0 | 1 (0 à l'arrêt) */
    s8 dir_y;              /* TRAJECTOIRE Y courante : -1 | 0 | 1 (0 à l'arrêt) */
    /* REGARD : la dernière direction non nulle, conservée à l'arrêt (self.facing).
       Le vecteur entier, pas un côté par axe : après un pas à droite puis un pas vers le
       haut, l'acteur regarde (0,-1) et non (1,-1). Sert à viser (interactive). Écrits par le
       tick quand `facing_auto` vaut 1, libres sinon. */
    s8 facing_x;           /* -1 | 0 | 1 */
    s8 facing_y;           /* -1 | 0 | 1 */
    u8 physics_sleep;      /* frames sous le seuil de sommeil du RigidBody */

    /* ── collision ↔ CollisionShapeComponent ────────────────────────────── */
    struct {
        /* Résolution contre la carte de collision — écrits par
           resolve_actor_tiles, lus par elle à la frame suivante :
             grounded : y avait-il un sol sous les pieds à la fin de la frame ?
                        C'est ce que rend actor_on_ground() ;
             last_x   : abscisse à la fin de la frame précédente, en PIXELS (pas
                        Q8, contrairement à x — resolve_actor_tiles travaille en
                        pixels du début à la fin, cf. gba_engine.h). Le déplacement horizontal RÉELLEMENT parcouru
                        s'en déduit, quelle que soit la façon dont le script
                        bouge l'acteur (vélocité, move(), move_to(),
                        set_position()) — c'est lui qui donne la distance de
                        collage en descente, sans réglage à exposer. */
        s16 last_x;
        /* Reste de la correction de vitesse en pente, en 1/256 de pixel. Sans ce
           report, un pas de 2 px sur une pente à 45° tomberait toujours sur 1 px
           (troncature) et le personnage ramperait au lieu d'aller 1,41 fois
           moins vite. */
        s16 slope_acc;
        u8 grounded;
        u8 box_count;      /* nombre de boxes actives (0..MAX_BOXES) */
        CollisionShape boxes[MAX_BOXES];
    } collision;
} Actor;

/* ── Parcours des emplacements ────────────────────────────────────────────────────────────────────────
   `g_alive_bits` : un bit par emplacement de `g_actors`, à 1 tant que son occupant est VIVANT, posé ou né.
   Posé par le constructeur (`actor_init_slot` : `alive_bit_set`), effacé par `actor_destroy_internal`
   (`alive_bit_clear`), remis à zéro par `scene_init`.

   `g_actor_slot_end` est le plus haut emplacement utilisé de la scène + 1 : le pool partagé commence juste après les
   posés (`g_spool_start` = leur nombre), et une scène sans pool le pose au nombre de posés (`scene_init`).

   `SLOT_EACH(v)` parcourt tous les emplacements de la scène `[0, g_actor_slot_end)`, posés puis nés : c'est le
   parcours des passes du tick, qui ne demandent jamais si un emplacement est posé ou né. Une boucle simple :
   `g_actor_slot_end` est rabattu sur le dernier vivant à chaque image, les corps de boucle testent `active`, et une
   boucle plus grosse (le saut des blocs vides par `g_alive_bits`) chassait une phase du tick hors de l'IWRAM
   (mesuré le 2026-11-07 : Platformer +5 %). La borne est relue à chaque tour : un acteur né pendant la
   boucle est vu.

   `POOL_EACH(v)` ne parcourt que le pool partagé `[g_spool_start, g_actor_slot_end)` : `actor:count`,
   `actor:get(nom, i)` et `actor:clear` y comptent les nés après avoir lu la table des posés d'un modèle. Il saute
   d'un seul test un bloc de 32 emplacements sans vivant ; dans un bloc occupé le parcours reste linéaire.
   `continue` marche ; un `break` hors d'un `switch` ne sort que du bloc courant. */
extern int g_spool_start, g_actor_slot_end;
extern u32 g_alive_bits[];
/* Ce qui rend `actor:get("Balle", i)` et `actor:count("Balle")` rapides dans une boucle : `g_alive_epoch` avance à CHAQUE
   changement de vie d'un emplacement (naissance, destruction, entrée de scène), et `g_nth` retient la dernière réponse avec
   l'époque où elle a été donnée. Tant que l'époque n'a pas bougé, le i-ème suivant se cherche à partir du précédent et le
   nombre n'est pas recompté ; dès qu'un acteur naît ou meurt (y compris au milieu de la boucle) le curseur est ignoré et
   la recherche repart du début, comme avant : la réponse est toujours celle d'un parcours complet. */
typedef struct {
    u32 epoch;                          /* époque du dernier `get` */
    int root_type_id, rank, slot;              /* son modèle, son rang parmi les vivants du pool, son emplacement */
    u32 count_epoch;                    /* époque du dernier `count` */
    int count_root_type_id, count;             /* son modèle et son résultat (la part du pool) */
} PoolCursor;
extern PoolCursor g_nth;
extern u32 g_alive_epoch;
#define POOL_EACH(v) \
    for(int _pw_ = g_spool_start >> 5; _pw_ <= ((g_actor_slot_end - 1) >> 5); _pw_++) \
        if(g_alive_bits[_pw_]) \
            for(int v = ((_pw_ << 5) < g_spool_start ? g_spool_start : (_pw_ << 5)), _pe_ = (_pw_ << 5) + 32; \
                v < _pe_ && v < g_actor_slot_end; v++)
#define SLOT_EACH(v) for(int v = 0; v < g_actor_slot_end; v++)
static inline void alive_bit_set(int k)   { g_alive_epoch++; g_alive_bits[k >> 5] |= (1u << (k & 31)); }
static inline void alive_bit_clear(int k) { g_alive_epoch++; g_alive_bits[k >> 5] &= ~(1u << (k & 31)); }

/* Masques boutons */
#define BTN_A      0x0001
#define BTN_B      0x0002
#define BTN_SELECT 0x0004
#define BTN_START  0x0008
#define BTN_RIGHT  0x0010
#define BTN_LEFT   0x0020
#define BTN_UP     0x0040
#define BTN_DOWN   0x0080
#define BTN_R      0x0100
#define BTN_L      0x0200

#endif /* ACTOR_TYPES_STATIC_H */
