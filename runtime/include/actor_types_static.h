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

typedef struct CollisionBox {
    s8  x, y;   /* offset relatif au pivot (pixels) */
    u8  w, h;   /* dimensions (pixels) */
    u8  solid;  /* 1=physique, 0=trigger */
    u8  active; /* 0 = la boîte n'existe plus pour personne : ni carte, ni chevauchement */
    u8  tag;    /* BOXTAG_* */
    u8  grounded; /* cette boîte reposait-elle sur le sol à la fin de la frame ? Écrit par
                     resolve_actor_tiles ; reste 0 pour une boîte non solide, que la carte ignore */
} CollisionBox;

/* Vec2/Vec3/Rect — les valeurs COMPOSÉES du sous-ensemble Lua (vec2(x,y),
   vec3(x,y,z), rect(x,y,w,h)). Des entiers, rien d'autre : pas de virgule
   flottante sur GBA. + et - composante à composante et * par un entier ne
   valent que pour vec2/vec3 — cf. actor_api_static.h (vec2_add et consorts)
   et scripting/vec_types.py côté transpileur, seul et même repère de type
   entre checker.py et codegen.py. */
typedef struct { int x, y; }    Vec2;
typedef struct { int x, y, z; } Vec3;
typedef struct { int x, y, w, h; } Rect;

/* Deux tables, deux unités (ROADMAP « La struct Actor allégée », marche 0a) :

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
    u8 auto_dir;           /* SpriteComponent.auto_dir de cette apparence */
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
    u8 auto_dir;           /* 1 = recalcule dir_x/dir_y depuis vx/vy chaque frame */
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
       valeur, la changer en jeu n'aurait donc aucun effet. Reste 0 pour un
       acteur poolé, dont le rendu ignore le drapeau. */
    u8 screen_space;
    /* Slot de matrice affine OAM (0-31), ou -1. Réservé au build à tout
       sprite dont « Affine transform » est coché (cf. main_gen.
       _compute_affine_info) — c'est une capacité de RENDU. -1 = OAM normale :
       le transform monde de l'acteur et le transform local ci-dessus gardent
       leur valeur, mais aucune matrice n'est écrite et rien ne les affiche. */
    s8 affine_slot;
} OamEntry;

typedef struct Actor {
    /* Position et vélocité MONDE, en Q8 (256 = 1 pixel) depuis la ROADMAP
       v0.19 (2026-08-20) — le point fixe existait déjà dans cette même
       struct pour scale_x/y, il n'avait simplement jamais atteint la
       position. self.position (script) continue de ne rendre/accepter que
       des pixels entiers ; self.velocity, elle, expose le Q8 directement —
       rupture assumée plutôt qu'un second nom (self.velocity_q8) à côté du
       premier. self:apply_velocity() ajoute vx/vy à x/y SANS convertir :
       c'est exactement ce qui fait vivre le sous-pixel d'une frame à
       l'autre. */
    int x, y;               /* position monde, Q8 */
    int vx, vy;             /* vélocité, Q8 */
    /* Transform MONDE (cf. ARCHITECTURE.md « Le modèle affine »). C'est de
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
    s16 tag;               /* TAG_* — type de l'acteur (≥ 255 dès qu'un pool est grand) */
    /* Indice de son entrée dans g_oam_entries[] (cf. l'en-tête ci-dessus), -1 = sans. */
    s16 oam_entry;
    u8 active;             /* 0 = ignoré (update + rendu désactivés) */
    s8 dir_x;              /* direction X courante : -1 | 0 | 1 */
    s8 dir_y;              /* direction Y courante : -1 | 0 | 1 */

    /* ── collision ↔ CollisionBoxComponent ────────────────────────────── */
    struct {
        /* Résolution contre la carte de collision — écrits par
           resolve_actor_tiles, lus par elle à la frame suivante (cf. ROADMAP
           v0.6.3) :
             grounded : y avait-il un sol sous les pieds à la fin de la frame ?
                        C'est ce que rend actor_on_ground() ;
             last_x   : abscisse à la fin de la frame précédente, en PIXELS (pas
                        Q8, contrairement à x — resolve_actor_tiles travaille en
                        pixels du début à la fin, cf. gba_engine.h, ROADMAP
                        v0.19). Le déplacement horizontal RÉELLEMENT parcouru
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
        CollisionBox boxes[MAX_BOXES];
    } collision;
} Actor;

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
