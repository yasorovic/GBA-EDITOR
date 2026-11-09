/* SPDX-License-Identifier: Zlib
   Copyright (c) 2026 Yasor Rovic

   Licence zlib — PAS la GPL de l'éditeur (cf. runtime/LICENSE). Ce fichier est
   recopié dans le projet de l'utilisateur au build, puis compilé dans sa ROM :
   le jeu produit lui appartient entièrement, il peut le vendre, et il n'a
   aucune notice à joindre à sa ROM. */
/* runtime_api_inline.h — la moitié INLINE de l'API runtime que voient les scripts
   (actor/camera/math/input/collision), plus les `extern` de l'état runtime posé
   par main.c. Écrit à la main (l'autre moitié — prototypes, énums, régions de
   window — est GÉNÉRÉE dans runtime_api.h, qui inclut ce fichier ensuite).
   Recompilé dans chaque unité de scène/acteur, d'où `static inline`.
   Dépend de : actor_types.h (inclus avant ce fichier). */
#ifndef RUNTIME_API_INLINE_H
#define RUNTIME_API_INLINE_H

#include "gba_debug.h"   /* actor_exists_warn, actor_active_warn : le log d'un appel sur un acteur disparu */
#include "obj_state.h"    /* OBJ_STATE_STRIDE : la taille d'un bloc d'état de script */

/* Les constantes que voient les unités de script — énumérations matérielles
   nommées (modes OAM, directions, blending, ease) ET régions de window
   (`WINR_*`) — ne sont PLUS ici : leurs `#define` sont GÉNÉRÉS dans `runtime_api.h`
   (cf. api_prototypes — les énums depuis api.py, les WINR extraites de
   gba_engine.h), qui inclut ce fichier juste après. Les impls inline ci-dessous
   les voient donc, et il n'y a plus de valeur à tenir d'accord à la main. */



/* Globaux définis dans main.c, visibles par tous les scripts */
extern Actor g_actors[];
extern u16 *g_actor_floor;
extern u8 *g_drop_through;   /* frames restantes où un corps ignore les faces à sens unique, par `Actor.slot_index` */
extern u8 g_drop_live;       /* au moins un compteur ci-dessus est non nul : le décompte de la frame ne tourne que alors */
/* L'état de script de TOUS les acteurs : un bloc de `OBJ_STATE_STRIDE` octets par emplacement de
   `g_actors`, à l'indice `Actor.slot_index`. Chaque script y range sa structure d'état (la plus grande
   du projet fixe la taille d'un bloc) ; un emplacement n'en porte qu'une à la fois. */
extern u32 g_obj_state[];
extern OamEntry g_oam_entries[];
/* L'entrée OAM qu'un acteur affiche, par le lien `Actor.oam_entry` (cf.
   actor_types_static.h). Seuls les accesseurs de script passent par ici : le C
   émis au build connaît l'indice et adresse `g_oam_entries[k]` directement.

   Un acteur SANS sprite (contrôleur, déclencheur, marqueur de prefab) a un lien
   à -1 : il n'affiche rien, donc il n'a pas d'entrée. Ses accesseurs restent
   pourtant appelables — `self.frame`, `self.visible = true` — et le contrat est
   « lecture = 0, écriture sans effet » : on leur rend une entrée NULLE remise à
   zéro à chaque appel (`affine_slot` à -1 : pas de matrice), que rien ne lit. */
static inline OamEntry* actor_oam_entry(const Actor* s) {
    static OamEntry none;
    if (s->oam_entry >= 0) return &g_oam_entries[s->oam_entry];
    none = (OamEntry){0};
    none.affine_slot = -1;
    return &none;
}
/* Constantes d'activation des apparences de la scène active — une ligne par
   apparence de chaque porteur multi-apparence (cf. AppearanceInit). Définie dans
   main.c, repointée par chaque scene_init. */
extern const AppearanceInit* g_appearance_init;

/* get_actor par NOM résolu à l'exécution — pour un script PARTAGÉ (caméra) qui
   n'a pas de scène connue au build (« L'acteur appartient à sa scène »,
   décision C). Rend l'acteur VIVANT de ce nom dans la scène active, ou nil.
   Défini dans main.c (il connaît g_current_scene et les slots par scène) ;
   un script de scène, lui, passe par le TAG résolu à la compilation. */
extern Actor* runtime_get_actor(int name_id);
/* Nombre d'acteurs POSÉS de la scène active — la borne de get_actor(i). */
extern int g_scene_placed;
/* La HIÉRARCHIE, posés comme nés : pour chaque emplacement, l'emplacement de son parent (-1 pour une racine), sa
   profondeur (0 pour une racine : l'ordre de la composition, parents avant enfants), sa visibilité propre et sa
   position LOCALE, décalage depuis le parent en Q8. Le constructeur remet le lien à zéro ;
   `actor_link_slot` le pose : `scene_init` pour un posé qui a un parent de scène, le spawn pour une partie d'un modèle.
   `g_slot_depth` est la profondeur maximale de la scène (0 : aucune hiérarchie, ni composition ni cascade). */
extern SlotLink g_slot_link[];
extern int g_slot_depth;
static inline int slot_parent(int slot) { return g_slot_link[slot].parent; }
static inline void actor_link_slot(int slot, int parent, int depth, int visible, int ox, int oy) {
    SlotLink* l = &g_slot_link[slot];
    l->parent = parent; l->depth = depth; l->visible = visible;
    l->ox = ox; l->oy = oy;
}
extern u32   _g_keys_held;
extern u32   _g_keys_pressed;

/* Caméra — une zone de taille écran fixe (SCREEN_W×SCREEN_H) dont l'origine
   (cam_x, cam_y) est en espace-monde. Tout le reste (scroll BG, position
   écran des sprites) se dérive de cette seule zone plutôt que de littéraux
   240/160/120/80 épars (cf. project_camera_abstraction). */
#define SCREEN_W 240
#define SCREEN_H 160
extern int cam_x, cam_y;
extern int g_scene_w, g_scene_h;   /* taille du monde de la scène (px), posée par scene_init */
/* Défilement autorisé par la scène (cases « Scroll H/V ») : posé par scene_init, lecture seule
   côté script — le suivi émis en a fait un choix de build. */
extern int g_scene_scroll_h, g_scene_scroll_v;
extern int g_scene_collision_layer;   /* index BG (0-3) portant la carte de collision */
/* Gravité de la scène en Q8 (256 = 1 px/frame²), posée par scene_init puis modifiable par script (`scene.gravity`).
   `g_support_normal` est le côté d'appui qui en découle : 1 bas, 2 haut, 3 droite, 4 gauche (axe dominant ; le bas sans
   gravité, comme avant). Un seul endroit le recalcule : scene_set_gravity. */
extern int g_gravity_x, g_gravity_y;
extern u8 g_support_normal;
extern int g_spool_start, g_actor_slot_end;
static inline Vec2 scene_get_gravity(void) { return (Vec2){ g_gravity_x, g_gravity_y }; }
static inline void scene_set_gravity(Vec2 g) {
    int ax = g.x < 0 ? -g.x : g.x, ay = g.y < 0 ? -g.y : g.y;
    if (g.x != g_gravity_x || g.y != g_gravity_y) {   /* un Rigid endormi doit tomber dans la nouvelle gravité */
        for (int i = 0; i < g_scene_placed; i++) g_actors[i].physics_sleep = 0;
        for (int i = g_spool_start; i < g_actor_slot_end; i++) g_actors[i].physics_sleep = 0;
    }
    g_gravity_x = g.x; g_gravity_y = g.y;
    g_support_normal = ax > ay ? (g.x > 0 ? 3 : 4) : (g.y < 0 ? 2 : 1);
}
static inline void camera_set_position(Vec2 p)  { cam_x=p.x; cam_y=p.y; }
static inline Vec2 camera_get_position(void)     { return (Vec2){ cam_x, cam_y }; }

/* Bornes de scroll — la zone scrollable du monde, un RECTANGLE (origine
   x/y + taille w/h en pixels). g_bounds_* (définis dans main.c) valent 0 par
   défaut (axe illimité). Réglées à l'activation d'une caméra (camera_switch,
   depuis ses bounds_x/y/w/h) ou par un script via camera.bound — débloquer
   une nouvelle zone au runtime, par exemple. */
extern int g_bounds_x, g_bounds_y, g_bounds_w, g_bounds_h;
static inline void camera_set_bounds(Rect b) {
    g_bounds_x = b.x; g_bounds_y = b.y;
    g_bounds_w = b.w; g_bounds_h = b.h;
}
static inline Rect camera_get_bounds(void) {
    return (Rect){ g_bounds_x, g_bounds_y, g_bounds_w, g_bounds_h };
}
/* Appliquée une fois par frame par le moteur (scene tick), après tout code
   ayant pu écrire cam_x/cam_y cette frame-là — suivi authoré ou script :
   un seul point de vérité pour les bornes, peu importe qui a bougé la
   caméra. */
static inline void camera_apply_bounds(void) {
    if (g_bounds_w > 0) {
        int lo = g_bounds_x, hi = g_bounds_x + g_bounds_w - SCREEN_W;
        if (hi < lo) hi = lo;   /* monde plus étroit que l'écran : collé au bord, pas dehors */
        if (cam_x < lo) cam_x = lo;
        if (cam_x > hi) cam_x = hi;
    }
    if (g_bounds_h > 0) {
        int lo = g_bounds_y, hi = g_bounds_y + g_bounds_h - SCREEN_H;
        if (hi < lo) hi = lo;
        if (cam_y < lo) cam_y = lo;
        if (cam_y > hi) cam_y = hi;
    }
}

/* ── Caméras nommées ─────────────────────────────────────────────
   Une configuration de cadrage est une DONNÉE (un asset de l'éditeur), pas du
   code : la table ci-dessous est émise dans main.c, une entrée par caméra du
   projet, l'entrée 0 étant toujours la caméra par défaut. Une seule est active
   à la fois — la GBA n'a qu'un écran.

   `mode` : 0 fixe, 1 suivi, 2 script. La CIBLE du suivi n'est pas ici : elle
   est un index d'acteur, donc propre à chaque scène, et vit dans une table par
   scène émise à côté du tick.

   `frame_w`/`frame_h` : taille du rendu à l'écran (WIN0), réglée le
   2026-08-24. 240×160 = plein écran, WIN0 reste éteinte — comportement
   identique à avant ces deux champs. Plus petit → camera_switch() pose WIN0 et
   l'active. WIN0 appartient donc à la caméra active ; WIN1 reste authorable
   par la scène (Scene.windows) — allocation fixe, jamais négociée à
   l'exécution puisqu'une seule caméra est active à la fois. */
typedef struct {
    u8  mode;
    u8  margin_x, margin_y;   /* zone morte du suivi */
    s16 x, y;                 /* cadrage posé à l'activation */
    s16 bounds_x, bounds_y;   /* origine de la zone scrollable */
    s16 bounds_w, bounds_h;   /* taille du monde ; 0 = axe illimité */
    u8  frame_w, frame_h;     /* taille du rendu écran (WIN0) ; 240×160 = plein écran */
    void (*on_start)(void);   /* script de la caméra, ou NULL */
    void (*on_update)(void);
} Camera;

extern const Camera g_cam_table[];
extern int g_cam_active;

/* État MODIFIABLE de la caméra active — copié de sa ligne de table à chaque
   camera_switch(), puis réglable par script. Zone morte du suivi (`camera.margin`)
   et cadre écran (`camera.frame`) : le suivi émis et WIN0 les lisent ici, jamais
   dans la table (const, en ROM). */
extern int g_cam_margin_x, g_cam_margin_y;
extern int g_cam_frame_w, g_cam_frame_h;

static inline Vec2 camera_get_margin(void) { return (Vec2){ g_cam_margin_x, g_cam_margin_y }; }
static inline void camera_set_margin(Vec2 m) {
    /* Au plus la demi-largeur : au-delà les deux bords du suivi se croisent et la caméra oscille. */
    g_cam_margin_x = m.x < 0 ? 0 : m.x > SCREEN_W / 2 ? SCREEN_W / 2 : m.x;
    g_cam_margin_y = m.y < 0 ? 0 : m.y > SCREEN_H / 2 ? SCREEN_H / 2 : m.y;
}

/* Nom de la caméra active : l'index de la table est la constante CAM_<NOM>. */
static inline int camera_get_active(void) { return g_cam_active; }

/* Cadre écran : 240×160 = plein écran, WIN0 éteinte ; plus petit, WIN0 le découpe.
   Borné à l'écran, et à 1 pixel au moins. */
static inline Vec2 camera_get_frame(void) { return (Vec2){ g_cam_frame_w, g_cam_frame_h }; }
static inline void camera_set_frame(Vec2 f) {
    g_cam_frame_w = f.x < 1 ? 1 : (f.x > SCREEN_W ? SCREEN_W : f.x);
    g_cam_frame_h = f.y < 1 ? 1 : (f.y > SCREEN_H ? SCREEN_H : f.y);
    if (g_cam_frame_w < SCREEN_W || g_cam_frame_h < SCREEN_H) {
        window_set(0, 0, 0, g_cam_frame_w, g_cam_frame_h);
        window_show(0, 1);
    } else {
        window_show(0, 0);
    }
}

/* `window_set`/`window_show` viennent du bloc de prototypes de runtime_api.h, émis avant ce fichier. */

/* Activer une caméra POSE son cadrage et ses bornes : c'est ce que « caméra
   fixe » veut dire, et une caméra en suivi se recale dans la frame même. Les
   bornes ne sont donc écrites qu'ici — un script qui appelle camera.set_bounds
   ensuite garde la main jusqu'à la prochaine activation. WIN0 suit le même
   principe pour le cadre écran : posée ici, elle reste telle quelle jusqu'à la
   prochaine activation (rien d'autre n'y touche, WIN0 n'appartenant plus qu'à
   la caméra). */
static inline void camera_switch(int idx) {
    if (idx < 0) return;
    const Camera *c = &g_cam_table[idx];
    g_cam_active = idx;
    cam_x = c->x; cam_y = c->y;
    camera_set_bounds((Rect){ c->bounds_x, c->bounds_y, c->bounds_w, c->bounds_h });
    g_cam_margin_x = c->margin_x; g_cam_margin_y = c->margin_y;
    camera_set_frame((Vec2){ c->frame_w, c->frame_h });
    if (c->on_start) c->on_start();
}

/* ── Secousse ────────────────────────────────────────────────────
   Un ÉVÉNEMENT, pas un état de la caméra : ses valeurs vivent à l'appel.
   L'amplitude retombe linéairement à zéro sur la durée — c'est la décroissance,
   sans troisième réglage à comprendre.

   Le décalage est appliqué APRÈS le clamp aux bornes (une secousse au bord du
   monde doit se voir) et RETIRÉ au début de la frame suivante : la logique de
   suivi ne voit donc jamais une caméra tremblée, et rien d'autre dans le moteur
   n'a à connaître la secousse. */
extern int g_shake_amp, g_shake_left, g_shake_total, g_shake_dx, g_shake_dy;
extern u32 g_shake_seed;

static inline void camera_shake(int amplitude, int frames) {
    if (amplitude <= 0 || frames <= 0) { g_shake_left = 0; return; }
    g_shake_amp = amplitude; g_shake_left = frames; g_shake_total = frames;
}

static inline int _shake_offset(int a) {
    g_shake_seed = g_shake_seed * 1664525u + 1013904223u;
    return (int)((g_shake_seed >> 16) % (u32)(2 * a + 1)) - a;
}

static inline void camera_shake_undo(void) {
    cam_x -= g_shake_dx; cam_y -= g_shake_dy;
    g_shake_dx = 0; g_shake_dy = 0;
}

static inline void camera_shake_apply(void) {
    if (g_shake_left <= 0) return;
    g_shake_left--;
    int a = (g_shake_amp * g_shake_left) / g_shake_total;
    if (a <= 0) return;
    g_shake_dx = _shake_offset(a);
    g_shake_dy = _shake_offset(a);
    cam_x += g_shake_dx; cam_y += g_shake_dy;
}

/* Décalages `a << n` / `a >> n` du Lua. Un `int` est un registre ARM de 32 bits ;
   le C seul laisse deux écarts avec le Lua que ces fonctions ferment :
     - un décalage d'au moins 32 bits est INDÉFINI en C. Ici il vaut 0 (comme en
       Lua, où un décalage de la largeur entière ou plus vide la valeur) ; un
       compte négatif vaut 0 aussi — le checker refuse déjà un littéral hors 0..31 ;
     - `>>` d'un `int` signé propage le signe en C (ASR). Le `>>` du Lua est
       LOGIQUE (LSR) : les bits qui entrent à gauche sont des 0.
   Passer par `unsigned` rend aussi `<<` défini quand le bit 31 déborde. Avec un
   compte constant, -O2 replie l'appel en un seul LSL/LSR. */
static inline int bits_shl(int a, int n) { return (unsigned)n < 32u ? (int)((unsigned)a << n) : 0; }
static inline int bits_shr(int a, int n) { return (unsigned)n < 32u ? (int)((unsigned)a >> n) : 0; }

/* Vec2/Vec3 — opérateurs composante à composante. Pas d'opérateur `+`/`-`/`*`
   sur les structs en C : ce sont ces fonctions que le codegen appelle pour
   `a + b` / `a - b` / `v * k` sur deux valeurs vec2 ou vec3 (jamais mélangées
   entre elles — cf. scripting/vec_types.py, seul juge du type). */
static inline Vec2 vec2_add  (Vec2 a, Vec2 b) { return (Vec2){ a.x+b.x, a.y+b.y }; }
static inline Vec2 vec2_sub  (Vec2 a, Vec2 b) { return (Vec2){ a.x-b.x, a.y-b.y }; }
static inline Vec2 vec2_scale(Vec2 v, int k)  { return (Vec2){ v.x*k,   v.y*k   }; }
static inline Vec3 vec3_add  (Vec3 a, Vec3 b) { return (Vec3){ a.x+b.x, a.y+b.y, a.z+b.z }; }
static inline Vec3 vec3_sub  (Vec3 a, Vec3 b) { return (Vec3){ a.x-b.x, a.y-b.y, a.z-b.z }; }
/* `*` et `/` entre deux vecteurs : composante par composante (division entière).
   Avec un entier, le codegen passe par `*_splat` pour `/`, par `*_scale` pour `*`.
   `dot(a, b)` : la somme des produits composante par composante, un ENTIER. */
static inline Vec2 vec2_mul  (Vec2 a, Vec2 b) { return (Vec2){ a.x*b.x, a.y*b.y }; }
static inline Vec3 vec3_mul  (Vec3 a, Vec3 b) { return (Vec3){ a.x*b.x, a.y*b.y, a.z*b.z }; }
static inline int  vec2_dot  (Vec2 a, Vec2 b) { return a.x*b.x + a.y*b.y; }
static inline int  vec3_dot  (Vec3 a, Vec3 b) { return a.x*b.x + a.y*b.y + a.z*b.z; }
/* Une composante divisée par 0 vaut 0 : la division matérielle n'a pas de résultat défini. */
static inline Vec2 vec2_div  (Vec2 a, Vec2 b) { return (Vec2){ b.x ? a.x/b.x : 0, b.y ? a.y/b.y : 0 }; }
static inline Vec3 vec3_div  (Vec3 a, Vec3 b) { return (Vec3){ b.x ? a.x/b.x : 0, b.y ? a.y/b.y : 0, b.z ? a.z/b.z : 0 }; }
static inline Vec3 vec3_scale(Vec3 v, int k)  { return (Vec3){ v.x*k,   v.y*k,   v.z*k   }; }
/* Un entier mêlé à un vecteur par `+`/`-` vaut ce vecteur dont TOUTES les
   composantes sont cet entier : `v + 2` = `v + vec2(2, 2)`. */
static inline Vec2 vec2_splat(int k) { return (Vec2){ k, k }; }
static inline Vec3 vec3_splat(int k) { return (Vec3){ k, k, k }; }

/* Transform — position instantanée, sans notion de temps ni de vitesse.
   s->x/s->y sont en Q8 en interne (256 = 1 px), mais
   self.position continue de rendre des PIXELS — décision verrouillée : un
   projet existant ne change pas de comportement, et un auteur qui n'a pas
   besoin de sous-pixel n'en entend jamais parler. L'écriture perd donc toute
   fraction sous-pixel accumulée (ex: par self:apply_velocity()) — c'est
   attendu d'un appel qui dit « l'acteur est ICI, au pixel », pas « avance ». */
/* Un script qui déplace un enfant déplace son décalage local : `ox/oy = position monde − position du parent`, lue au
   moment de l'écriture. Sans cela, la composition (`slot_compose`) remettrait l'enfant sur son ancien décalage dans
   la même image. Appelée par les quatre écritures de position du script (`position`, `move`, `move_to`,
   `apply_velocity`) ; le pas physique du moteur ne l'appelle pas (corps d'un enfant : hors de ce contrat). */
static inline void slot_local_from_world(const Actor* s) {
    if (!g_slot_depth) return;
    SlotLink* l = &g_slot_link[s->slot_index];
    if (l->parent < 0) return;
    const Actor* p = &g_actors[l->parent];
    l->ox = s->x - p->x;
    l->oy = s->y - p->y;
}
static inline void actor_set_position(Actor* s, Vec2 p) {
    s->x=p.x<<8; s->y=p.y<<8; s->physics_sleep=0;
    slot_local_from_world(s);
}
static inline Vec2 actor_get_position(const Actor* s)   { return (Vec2){ s->x>>8, s->y>>8 }; }

/* get_actor rend un acteur qui EXISTE, ou nil : un acteur détruit au runtime (`self:destroy()` →
   alive=0) n'est plus « là », et le dire au script est une information de
   gameplay (« ma cible existe-t-elle encore ? »). Un acteur seulement désactivé existe
   toujours : on l'atteint (pour le réactiver), ses actions sont sautées tant qu'il l'est
   (cf. `actor_active_warn`). Le chemin compile-time de get_actor passe par ce filtre — coût :
   un test du drapeau alive. */
static inline Actor* actor_live(Actor* s) { return (s && s->alive) ? s : (Actor*)0; }

/* Le pool PARTAGÉ de la scène : les emplacements d'acteurs que n'importe quel modèle simple prend en
   naissant. Posés par `scene_init` (début, fin, première entrée d'état) ; `g_actor_slot_end` est le plus haut
   emplacement utilisé + 1 : les boucles du tick (`POOL_EACH`, actor_types_static.h) s'arrêtent là au lieu de
   parcourir tout le pool, et sautent les blocs de 32 emplacements sans vivant (`g_alive_bits`).
   `g_spool_free` est le curseur du spawn : aucun emplacement libre en dessous. Le spawn cherche à partir
   de lui (au lieu de parcourir le pool depuis le début à chaque naissance) ; une destruction le ramène
   en arrière, un spawn l'avance. */
extern int g_spool_start, g_spool_end, g_actor_slot_end, g_spool_entry, g_spool_free;

/* Un modèle à PARTIES occupe un groupe d'emplacements contigus (le script atteint la partie k par
   `self + k`). `Actor.type_id` dit alors AUSSI quelle partie l'emplacement occupe : la racine porte l'identité
   du modèle, sa partie k cette identité + k. Une table par type d'emplacement, posée par `scene_init` (nulle pour
   une scène sans modèle à parties) : g_spool_part[type] = rang de la partie (k), 0 pour une racine ou un modèle plat.
   Elle ne sert qu'à l'allocation du pool (`group_root_slot`, `spool_slot_free`) : le parent d'une partie est dans
   `g_slot_link`, comme celui d'un posé. */
extern const u8 *g_spool_part;

/* OÙ EST LA PARTIE k D'UN GROUPE ? Aujourd'hui à `racine + k` : un groupe est une série contiguë d'emplacements,
   et l'entrée d'état d'une partie suit son emplacement (une entrée par emplacement du pool). Ces quatre fonctions sont
   le SEUL endroit qui le sait : le runtime et le C émis n'écrivent plus `+ k` ni `- rang`. Des groupes non contigus ne
   changeraient qu'elles et l'allocateur de spawn.
     group_slot(r, k)       emplacement de la partie k du groupe dont la racine est l'emplacement r (k = 0 : la racine) ;
     group_entry(e, k)      entrée d'état de la partie k, `e` étant celle de la racine ;
     group_part(a, k)       l'acteur de la partie k du groupe de la racine `a` (pointeur, sans lecture : `self.Canon`) ;
     group_root_slot(s)     emplacement de la racine du groupe de l'emplacement s (lui-même pour une racine ou un modèle plat). */
static inline int group_slot(int root, int k)              { return root + k; }
static inline int group_entry(int root_entry, int k)       { return root_entry + k; }
static inline Actor* group_part(Actor* root, int k)        { return root + k; }
static inline int group_root_slot(int slot) {
    return slot - (g_spool_part ? g_spool_part[g_actors[slot].type_id] : 0);
}

/* `boss.Canon` sur une RÉFÉRENCE : la partie k du groupe de `root`, ou nil si la référence est nil/périmée ou si la partie a été
   détruite. À la différence de `group_part` (pour `self`, jamais nil), elle ne fabrique pas un pointeur à partir de NULL. */
static inline Actor* actor_child(Actor* root, int k) {
    Actor* c = root ? group_part(root, k) : (Actor*)0;
    return (c && c->alive) ? c : (Actor*)0;
}

/* `a.root` et `a.parent` (propriétés en lecture seule du catalogue), posé ou né : le sommet de sa chaîne (lui-même pour
   une racine) et son parent (nil pour une racine), lus dans `g_slot_link`. nil si `a` est nil ou détruit. Détruire un
   parent détruit ses enfants (`actor_destroy_internal`) : un enfant vivant a toujours un parent vivant. */
static inline Actor* actor_root(Actor* a) {
    if (!a || !a->alive) return (Actor*)0;
    int s = a->slot_index;
    for (int p = slot_parent(s); p >= 0; p = slot_parent(s)) s = p;
    return &g_actors[s];
}
static inline Actor* actor_parent(Actor* a) {
    if (!a || !a->alive) return (Actor*)0;
    int p = slot_parent(a->slot_index);
    return p >= 0 ? &g_actors[p] : (Actor*)0;
}

/* `boss.Bras` quand `boss` est un acteur POSÉ de la scène : le bras est un autre acteur posé, à une adresse que le build connaît.
   nil si la référence à `boss` est nil, ou si le bras a été détruit. */
static inline Actor* actor_placed_child(Actor* parent, Actor* child) {
    return (parent && child->alive) ? child : (Actor*)0;
}

/* L'emplacement `k` du pool est-il libre pour un spawn ? Un acteur DÉTRUIT (alive = 0) libère le sien, sauf une
   PARTIE détruite dont la racine vit encore : elle reste dans son groupe, qui n'est rendu qu'avec la racine. */
static inline int spool_slot_free(int k) {
    if (g_actors[k].alive) return 0;
    int root = group_root_slot(k);
    if (root != k && g_actors[root].alive) return 0;
    return 1;
}

/* Les instances d'un MODÈLE (un prefab dans la scène) se retrouvent par sa table `g_model_*` (les
   posées, et sa réserve à part s'il en a une) puis, pour un modèle du pool partagé (`root_type_id` ≠ 0), par
   `Actor.type_id`. `actor:count("Bullet")` compte celles qui existent ; `actor:get("Bullet", i)` rend la
   i-ème (0-based ici), ou nil. L'indice est celui des instances VIVANTES, dans l'ordre : détruire une
   instance en cours de boucle décale les suivantes, comme retirer d'une liste. */
static inline int actor_model_count(const ModelSlot* t, int n, int root_type_id) {
    int c = 0;
    for (int k = 0; k < n; k++) c += g_actors[t[k].slot].alive;
    if (root_type_id) {
        /* La part du pool ne se recompte que si quelqu'un est né ou mort depuis la dernière fois : une boucle
           `for i = 1, actor:count("Balle")` relit sa borne à chaque tour. */
        if (g_nth.count_epoch != g_alive_epoch || g_nth.count_root_type_id != root_type_id) {
            int pc = 0;
            POOL_EACH(k)
                pc += g_actors[k].alive && g_actors[k].type_id == root_type_id;
            g_nth.count_epoch = g_alive_epoch; g_nth.count_root_type_id = root_type_id; g_nth.count = pc;
        }
        c += g_nth.count;
    }
    return c;
}
static inline Actor* actor_model_nth(const ModelSlot* t, int n, int root_type_id, int n0) {
    if (n0 < 0) return (Actor*)0;
    for (int k = 0; k < n; k++)
        if (g_actors[t[k].slot].alive && n0-- == 0) return &g_actors[t[k].slot];
    if (!root_type_id) return (Actor*)0;
    /* `n0` est maintenant le rang demandé parmi les instances du pool. Le même rang qu'à l'appel précédent rend le même
       acteur ; le rang suivant se cherche à partir de son emplacement : une boucle en avançant de 1 coûte un parcours du
       pool en tout, et non un par tour. Un changement de vie depuis (époque) ou un autre modèle : parcours complet. */
    if (g_nth.epoch == g_alive_epoch && g_nth.root_type_id == root_type_id) {
        if (n0 == g_nth.rank) return &g_actors[g_nth.slot];
        if (n0 == g_nth.rank + 1) {
            for (int k = g_nth.slot + 1; k < g_actor_slot_end; k++)
                if (g_actors[k].alive && g_actors[k].type_id == root_type_id) {
                    g_nth.rank = n0; g_nth.slot = k;
                    return &g_actors[k];
                }
            return (Actor*)0;
        }
    }
    int rank = n0;
    POOL_EACH(k)
        if (g_actors[k].alive && g_actors[k].type_id == root_type_id && rank-- == 0) {
            g_nth.epoch = g_alive_epoch; g_nth.root_type_id = root_type_id; g_nth.rank = n0; g_nth.slot = k;
            return &g_actors[k];
        }
    return (Actor*)0;
}

/* Une RÉFÉRENCE d'acteur rangée dans une variable qui survit à l'image (variable de tête d'un script,
   état d'une instance) est un entier : la génération de l'emplacement dans les 16 bits hauts, son
   indice dans `g_actors` PLUS UN dans les 16 bits bas (pour que 0 reste « aucun acteur », quelle que soit
   la génération). Le bit de signe peut donc être pris : on ne compare une référence qu'à 0, jamais à un ordre.
   Elle ne résout que tant que l'emplacement n'a pas changé de main : détruit, ré-occupé par un spawn ou
   quitté avec sa scène, il rend nil. Un acteur désactivé (`deactivate`) résout toujours, il peut
   être réactivé. */
static inline int actor_ref_make(const Actor* a) {
    return a ? (int)(((u32)a->gen << 16) | (u32)(a - g_actors + 1)) : 0;
}
static inline Actor* actor_ref_get(int h) {
    if (!h) return (Actor*)0;
    Actor* a = &g_actors[(h & 0xFFFF) - 1];
    return (((u32)h >> 16) == a->gen) ? a : (Actor*)0;
}

/* Un acteur désactivé peut démarrer. Une naissance différée ne vise que son occupant initial. */
static inline void actor_start(int ref, void (*on_start)(Actor*)) {
    Actor* actor = actor_ref_get(ref);
    if (actor && actor->alive) on_start(actor);
}

/* Un script qui agit sur une RÉFÉRENCE d'acteur (`boss:move(...)`, `b:hide()`, `boss.hp`) : l'acteur a pu
   être détruit ou désactivé depuis qu'on l'a obtenu, ou la référence vaut nil. Rien n'est exigé de
   l'auteur (il n'est pas obligé de tester) ; l'appel est simplement sauté, et un build DEBUG
   l'écrit dans le log mGBA. En release `debug_*` est vide : il reste le test du drapeau.
   Deux exigences, selon ce que l'appel touche :
     - `actor_exists_warn` : l'acteur EXISTE (alive). Pour ce qui le concerne en tant qu'objet : son
       état d'export, et son cycle de vie (`activate`, `deactivate`, `destroy` s'appliquent aussi à un
       acteur désactivé) ;
     - `actor_active_warn` : l'acteur est de plus ACTIF. Pour tout ce qui agit dans le jeu (bouger,
       animer, afficher) : un acteur désactivé est en sommeil. */
static inline int actor_exists_warn(const Actor* a, const char* what) {
    if (a && a->alive) return 1;
    debug_write_str("warning: ");
    debug_write_str(what);
    debug_write_str(" skipped, the actor is destroyed or nil");
    debug_flush();
    return 0;
}
static inline int actor_active_warn(const Actor* a, const char* what) {
    if (a && a->active) return 1;
    debug_write_str("warning: ");
    debug_write_str(what);
    debug_write_str(" skipped, the actor is destroyed, inactive or nil");
    debug_flush();
    return 0;
}

/* get_actor(i) — adressage DYNAMIQUE par index (« L'acteur appartient à sa
   scène »). `i0` est déjà 0-based (le codegen a replié le 1-based du langage,
   comme pour data.Table[i]). Borné à [0, g_scene_placed) puis filtré par
   `actor_live` : un index hors de la scène, ou un acteur détruit, rend nil. */
static inline Actor* actor_at(int i0) {
    return (i0 >= 0 && i0 < g_scene_placed) ? actor_live(&g_actors[i0]) : (Actor*)0;
}

/* Racine carrée entière (algorithme bit à bit) — pas de FPU sur GBA, et le
   BIOS Sqrt coûte un appel SWI pour un résultat qu'on ne calcule qu'une fois
   par mouvement. Sert à normaliser une direction dans move()/move_to(). */
static inline int isqrt(int n) {
    if (n <= 0) return 0;
    int res = 0, bit = 1 << 30;
    while (bit > n) bit >>= 2;
    while (bit != 0) {
        if (n >= res + bit) { n -= res + bit; res = (res >> 1) + bit; }
        else res >>= 1;
        bit >>= 2;
    }
    return res;
}

/* Movement — déplacement étalé sur plusieurs frames : appelées depuis
   on_update à chaque frame, elles avancent d'au plus `speed` px CE frame-là.
   `speed` et `target` restent des PIXELS entiers, comme avant v0.19 — ce sont
   des arguments Lua, et le sous-ensemble Lua reste entier (décision
   verrouillée). Aucun état gardé sur l'Actor (ni cible, ni reste
   fractionnaire) : la direction est recalculée à chaque appel depuis la
   position courante.

   actor_move accumule en Q8 (dx/dy/mag restent petits — une direction, pas
   une distance monde — aucun risque de débordement à multiplier speed<<8) :
   un bonus de précision, gratuit, sur un calcul qui tronquait avant. */
static inline void actor_move(Actor* s, Vec2 dir, int speed) {
    int dx = dir.x, dy = dir.y;
    int mag = isqrt(dx*dx + dy*dy);
    if (mag == 0) return;
    s->physics_sleep = 0;
    s->x += dx * (speed<<8) / mag;
    s->y += dy * (speed<<8) / mag;
    slot_local_from_world(s);
}
/* actor_move_to, à l'inverse, calcule dx/dy/dist contre la position ARRONDIE
   (cx/cy) : `target` est une distance MONDE, potentiellement grande, et
   speed<<8 dans le même produit déborderait un int 32 bits. Le résultat est
   remis à l'échelle Q8 seulement à l'écriture — la même règle qu'ailleurs
   dans ce chantier : un seul arrondi, jamais dans le calcul intermédiaire. */
static inline void actor_move_to(Actor* s, Vec2 target, int speed) {
    int cx = s->x>>8, cy = s->y>>8;
    int dx = target.x - cx, dy = target.y - cy;
    int dist = isqrt(dx*dx + dy*dy);
    if (speed < 0) speed = 0;   /* vitesse négative : sur place, et jamais dist == 0 en diviseur */
    if (speed > 0) s->physics_sleep = 0;
    if (dist <= speed) { s->x = target.x<<8; s->y = target.y<<8; }
    else { s->x += (dx * speed / dist) << 8; s->y += (dy * speed / dist) << 8; }
    slot_local_from_world(s);
}

/* Physics — vélocité stockée sur l'Actor, lue par get_velocity. Ne déplace
   rien seule : c'est le script qui l'applique, via actor_apply_velocity
   (cf. Ball.lua) ou en l'ignorant.

   self.velocity change de SENS — s->vx/s->vy sont Q8, et
   get/set_velocity ne convertissent plus rien (contrairement à la position,
   qui reste pixels). Un script qui lisait/écrivait self.velocity en pixels
   avant cette version doit être migré : c'est la rupture assumée qui rend le
   sous-pixel utilisable sans un second nom (self.velocity_q8) à côté du
   premier. */
static inline Actor* actor_get_physics_body(Actor* s) { return s; }
static inline void actor_set_velocity(Actor* s, Vec2 v) {
    s->vx=v.x; s->vy=v.y; if(v.x||v.y) s->physics_sleep=0;
}
static inline void actor_add_velocity(Actor* s, Vec2 dv){
    s->vx+=dv.x; s->vy+=dv.y; if(dv.x||dv.y) s->physics_sleep=0;
}
static inline Vec2 actor_get_velocity(const Actor* s)    { return (Vec2){ s->vx, s->vy }; }
/* `physics_body:drop_through(n)` : ignorer les faces à sens unique (carte et acteurs) pendant `n` frames, celle de
   l'appel comprise. Sans effet dans un projet qui n'en a aucune (`g_drop_through` est alors nul).
   L'appel retire aussi le contact au sol : un acteur immobile n'est pas relu par la carte (`grounded` garde sa valeur) et
   un script qui n'applique la gravité qu'en l'air ne le ferait jamais tomber ; sans contact il tombe dès la frame suivante,
   et un sol plein sous lui le reprend aussitôt. */
static inline void actor_drop_through(Actor* s, int frames){
    if (!g_drop_through) return;
    g_drop_through[s->slot_index] = frames < 0 ? 0 : (frames > 255 ? 255 : (u8)frames); g_drop_live = 1;
    if (frames > 0) {
        s->collision.grounded = 0;
        for (int i = 0; i < s->collision.box_count; i++) s->collision.boxes[i].grounded = 0;
        if (g_actor_floor) g_actor_floor[s->slot_index] = 0;
    }
}
/* Applique la vélocité Q8 stockée à la position Q8 stockée — l'accumulateur
   sous-pixel est LITTÉRALEMENT s->x/s->y, donc rien à reporter ailleurs
   (contrairement à slope_acc, qui corrige une AUTRE fraction : le cosinus de
   pente en collision, cf. resolve_actor_tiles). Remplace l'ancien idiome
   `self.position = self.position + self.velocity`, qui n'a plus de sens dès
   que les deux membres ont des échelles différentes. C'est l'appel du SCRIPT : le pas physique du moteur
   (`body_motion_step`) ajoute la vitesse lui-même, sans toucher au décalage d'un enfant. */
static inline void actor_apply_velocity(Actor* s) { s->x+=s->vx; s->y+=s->vy; slot_local_from_world(s); }

/* Animation — play_anim reçoit l'index d'état (résolu à la compile par le transpileur) */
/* 255 = « cet état n'existe pas dans l'apparence courante » (marche 3c : la table de
   correspondance d'un acteur multi-apparence le rend pour un nom absent) — un
   no-op, jamais un index hors table. */
static inline void actor_play_anim(Actor* s, int id) {
    OamEntry* o = actor_oam_entry(s);
    if (id == 255) return;
    if (o->anim_state != id) { o->anim_state = id; o->frame = 0; o->timer = 0; }
}

/* Apparences (marche 3) : un acteur affiche UN sprite parmi plusieurs. Changer
   d'apparence est un GESTE, comme play_anim : l'animation repart de l'état 0,
   frame 0, et les constantes du sprite d'arrivée (tailles, palette, direction
   auto) sont reposées depuis la table de la scène. Sans entrée OAM (acteur sans
   sprite), sans effet ; le rang est celui d'un composant sprite de l'acteur,
   résolu à la compile par le transpileur (SPRITE_*). */
static inline void actor_set_appearance(Actor* s, int n) {
    if (s->oam_entry < 0) return;
    OamEntry* o = &g_oam_entries[s->oam_entry];
    if (!o->appearance_base) return;                 /* une seule apparence : rien à activer */
    const AppearanceInit* a = &g_appearance_init[o->appearance_base - 1 + n];
    o->appearance = (u8)n;
    o->frame = 0; o->timer = 0; o->anim_state = 0;
    o->frame_w = a->frame_w; o->frame_h = a->frame_h;
    o->pal_bank = a->pal_bank; o->facing_auto = a->facing_auto;
}
static inline int actor_get_appearance(const Actor* s) { return actor_oam_entry(s)->appearance; }
/* État courant, en LECTURE — comparable par son nom (self.anim == "Walk"),
   symétrique de play_anim qui l'écrit par son nom. Pas de setter : changer
   d'état est un geste (self:play_anim), pas une propriété qu'on assigne. */
static inline int  actor_get_anim(const Actor* s)    { return actor_oam_entry(s)->anim_state; }
static inline int  actor_get_anim_speed(const Actor* s) { return actor_oam_entry(s)->anim_speed; }
static inline void actor_set_anim_speed(Actor* s, int v) { actor_oam_entry(s)->anim_speed = v; }
/* Lecture seule : recopiées chaque tick depuis les tables du sprite, cf.
   OamEntry.anim_length/anim_loop/anim_finished (actor_types_static.h). */
static inline int  actor_get_anim_length(const Actor* s)   { return actor_oam_entry(s)->anim_length; }
static inline int  actor_get_anim_loop(const Actor* s)     { return actor_oam_entry(s)->anim_loop; }
static inline int  actor_get_anim_finished(const Actor* s) { return actor_oam_entry(s)->anim_finished; }
/* Lecture seule : posées à l'init/au spawn, cf. OamEntry.frame_w/frame_h. */
static inline int  actor_get_frame_w(const Actor* s) { return actor_oam_entry(s)->frame_w; }
static inline int  actor_get_frame_h(const Actor* s) { return actor_oam_entry(s)->frame_h; }
static inline int  actor_get_frame(const Actor* s)   { return actor_oam_entry(s)->frame; }
static inline void actor_set_frame(Actor* s, int f)  { actor_oam_entry(s)->frame=f; }
static inline int  actor_get_visible(const Actor* s) { return actor_oam_entry(s)->visible; }
static inline void actor_set_visible(Actor* s, int v){ actor_oam_entry(s)->visible=v; }
static inline int  actor_get_active(const Actor* s)  { return s->active; }
static inline void actor_set_active(Actor* s, int v) { s->active=v; }
/* Booléens (self.flip_h = true/false) — le sens du flip est porté par l'état,
   pas par un signe passé à l'ancien self:set_flip_h. */
static inline int  actor_get_flip_h(const Actor* s)  { return actor_oam_entry(s)->flip_h; }
static inline void actor_set_flip_h(Actor* s, int v) { actor_oam_entry(s)->flip_h = v ? 1 : 0; }
static inline int  actor_get_flip_v(const Actor* s)  { return actor_oam_entry(s)->flip_v; }
static inline void actor_set_flip_v(Actor* s, int v) { actor_oam_entry(s)->flip_v = v ? 1 : 0; }

/* ── Transform affine au runtime ──────────────────────────────────────────
   Champs de l'entrée d'affichage (`OamEntry.rotation/scale_x/scale_y`, cf. actor_types_static.h), et non des globaux
   par slot : un script de prefab poolé est UNE fonction C partagée par toutes ses instances, mais chaque instance a sa
   propre entrée. Des globaux dans ce header `static` créeraient une COPIE par unité de compilation (main.c vs actor_*.c).
   Pas de FPU sur GBA : SIN_LUT est une table degrés→Q8 (×256) écrite en dur.
   gba_cos se déduit d'un déphasage de 90° plutôt qu'une seconde table. */
static const s16 SIN_LUT[91] = {
    0, 4, 9, 13, 18, 22, 27, 31, 36, 40, 44, 49,
    53, 58, 62, 66, 71, 75, 79, 83, 88, 92, 96, 100,
    104, 108, 112, 116, 120, 124, 128, 132, 136, 139, 143, 147,
    150, 154, 158, 161, 165, 168, 171, 175, 178, 181, 184, 187,
    190, 193, 196, 199, 202, 204, 207, 210, 212, 215, 217, 219,
    222, 224, 226, 228, 230, 232, 234, 236, 237, 239, 241, 242,
    243, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 254,
    255, 255, 255, 256, 256, 256, 256,
};
/* Un angle en degrés ramené à [0, 360) SANS division : le moteur est compilé en Thumb, qui n'a pas de multiplication
   longue, donc `% 360` devient un appel de bibliothèque de plusieurs dizaines de cycles — et une rotation qu'un script
   incrémente à chaque image sort vite de [0, 360). Au-delà de ±46 000 degrés (le produit déborderait), le reste
   se fait à l'ancienne. */
static inline int gba_norm_deg(int deg) {
    if ((unsigned)deg < 360u) return deg;
    if (deg > -46000 && deg < 46000) {
        deg -= ((deg * 46603) >> 24) * 360;              /* 46603 = 2^24 / 360 */
        while (deg < 0) deg += 360;
        while (deg >= 360) deg -= 360;
        return deg;
    }
    deg %= 360;
    return deg < 0 ? deg + 360 : deg;
}
/* La table couvre 0..90° ; les trois autres quadrants s'en déduisent par symétrie. `deg` est dans [0, 360). */
static inline int gba_sin_n(int deg) {
    int neg = deg >= 180;
    if (neg) deg -= 180;
    if (deg > 90) deg = 180 - deg;
    return neg ? -SIN_LUT[deg] : SIN_LUT[deg];
}
static inline int gba_sin(int deg) { return gba_sin_n(gba_norm_deg(deg)); }
static inline int gba_cos(int deg) { return gba_sin_n(gba_norm_deg(deg + 90)); }
/* Sinus ET cosinus d'un même angle, réduit une seule fois. */
static inline void gba_sincos(int deg, int* s, int* c) {
    deg = gba_norm_deg(deg);
    *s = gba_sin_n(deg);
    *c = gba_sin_n(deg >= 270 ? deg - 270 : deg + 90);
}
/* La matrice affine 8.8 d'un sprite (PA = cos / échelle x, PB = sin / échelle x, PC = -sin / échelle y, PD =
   cos / échelle y), `sxq`/`syq` en Q8 (256 = ×1). Les seules divisions par une variable sont l'inverse de chaque
   échelle (2^22 / s, en Q14) : une seule quand l'échelle est la même sur les deux axes, aucune à l'échelle 1,0. Le
   produit cos × inverse tient en 31 bits (256 × 2^22 au plus). */
static inline void gba_affine_matrix(int cosA, int sinA, int sxq, int syq, int* pa, int* pb, int* pc, int* pd) {
    int isx = sxq == 256 ? 16384 : (sxq ? 4194304 / sxq : 0);
    int isy = syq == sxq ? isx : (syq == 256 ? 16384 : (syq ? 4194304 / syq : 0));
    *pa = cosA * isx / 16384;  *pb = sinA * isx / 16384;
    *pc = -sinA * isy / 16384; *pd = cosA * isy / 16384;
    if (!*pa && !*pb) *pa = 1;
    if (!*pc && !*pd) *pd = 1;
}
/* Le calcul affine d'un sprite, mémoïsé PAR ENTRÉE D'AFFICHAGE (`g_aff_cache[entrée]`, défini dans main.c quand le projet a
   un sprite affine). La clé est ce dont le résultat dépend, tel que le C de rendu le lit : rotation et échelle du sprite,
   pivot et flips. Un sprite dont rien de cela n'a bougé depuis l'image précédente relit les six résultats au lieu de refaire
   sinus, cosinus, inverses et produits. La clé est comparée en entier, jamais résumée : un résultat périmé ne peut pas
   sortir. `fl` vaut 0 tant que l'entrée n'a rien rangé, 0x80 plus les flips ensuite.

   Ranger coûte (une quinzaine d'écritures) : un sprite dont la rotation ou l'échelle change à CHAQUE image ne le fait donc
   pas. `vrot`, `vsx`, `vsy` retiennent ces trois valeurs de l'image précédente (trois écritures, toujours) ; on ne range
   et on ne relit qu'à partir de la deuxième image où elles sont restées les mêmes. */
typedef struct AffCache {
    s16 vrot, vsx, vsy;                 /* rotation et échelle du sprite à l'image précédente */
    s16 rot, sx, sy;
    s8 px, py;
    u8 fl;
    s16 pa, pb, pc, pd;                 /* la matrice, avant le flip */
    s16 u, v;                           /* le recentrage sur le pivot */
} AffCache;
/* fin de la trigonométrie du moteur */

/* Un sprite dont « Affine transform » est coché a `affine_slot` >= 0 (cf.
   gen_affine.compute_affine_info) ; le rendu lui prend alors une matrice à la frame.

   Ces accesseurs ne le CONSULTENT PAS : la valeur est de l'état de jeu, toujours lisible et écrivable. Sans slot,
   elle ne s'affiche simplement pas, et le build le signale par un avertissement du checker.

   Transform du sprite (self.sprite_rotation / self.sprite_scale / self.sprite_offset) : rotation et échelle autour
   du pivot, l'offset déplace le cadre depuis la position de l'acteur. */
static inline void actor_set_sprite_rotation(Actor* s, int deg) {
    actor_oam_entry(s)->rotation = deg;
}
static inline void actor_set_sprite_scale(Actor* s, Vec2 v) {
    actor_oam_entry(s)->scale_x = v.x * 256 / 100;
    actor_oam_entry(s)->scale_y = v.y * 256 / 100;
}
static inline void actor_set_sprite_offset(Actor* s, Vec2 o) {
    actor_oam_entry(s)->offset_x = o.x;
    actor_oam_entry(s)->offset_y = o.y;
}
static inline void actor_set_sprite_pivot(Actor* s, Vec2 o) {
    actor_oam_entry(s)->pivot_x = o.x;
    actor_oam_entry(s)->pivot_y = o.y;
}
static inline int  actor_get_sprite_rotation(const Actor* s) {
    return actor_oam_entry(s)->rotation;
}
static inline Vec2 actor_get_sprite_scale(const Actor* s) {
    return (Vec2){ actor_oam_entry(s)->scale_x * 100 / 256, actor_oam_entry(s)->scale_y * 100 / 256 };
}
static inline Vec2 actor_get_sprite_offset(const Actor* s) {
    return (Vec2){ actor_oam_entry(s)->offset_x, actor_oam_entry(s)->offset_y };
}
static inline Vec2 actor_get_sprite_pivot(const Actor* s) {
    return (Vec2){ actor_oam_entry(s)->pivot_x, actor_oam_entry(s)->pivot_y };
}

/* Direction 8-axes pour l'animation (0=override, 1=N..8=NW) */
static inline int  actor_get_dir(const Actor* s)          { static const s8 _lut[3][3]={{8,1,2},{7,0,3},{6,5,4}}; return _lut[s->dir_y+1][s->dir_x+1]; }
static inline void actor_set_dir(Actor* s, int dir)       { static const s8 _dx[]={0,0,1,1,1,0,-1,-1,-1}; static const s8 _dy[]={0,-1,-1,0,1,1,1,0,-1}; if(dir>=0&&dir<=8){s->dir_x=_dx[dir];s->dir_y=_dy[dir];} }
static inline void actor_set_facing_auto(Actor* s, int v) { actor_oam_entry(s)->facing_auto=v?1:0; }
static inline int  actor_get_facing_auto(const Actor* s)  { return actor_oam_entry(s)->facing_auto; }

/* Regard (self.facing) : même écriture à deux portes que la direction, vecteur ou boussole. */
static inline int  actor_get_facing_named(const Actor* s) { static const s8 _lut[3][3]={{8,1,2},{7,0,3},{6,5,4}}; return _lut[s->facing_y+1][s->facing_x+1]; }
static inline void actor_set_facing_named(Actor* s, int dir) { static const s8 _dx[]={0,0,1,1,1,0,-1,-1,-1}; static const s8 _dy[]={0,-1,-1,0,1,1,1,0,-1}; if(dir>=0&&dir<=8){s->facing_x=_dx[dir];s->facing_y=_dy[dir];} }
static inline Vec2 actor_get_facing(const Actor* s) { return (Vec2){ s->facing_x, s->facing_y }; }
static inline void actor_set_facing(Actor* s, Vec2 v) {
    s->facing_x = (v.x > 0) - (v.x < 0);   /* clamp à -1/0/1 */
    s->facing_y = (v.y > 0) - (v.y < 0);
}

/* Direction : vecteur discret (-1|0|1) indépendant du flip */
static inline Vec2 actor_get_direction(const Actor* s) {
    return (Vec2){ s->dir_x, s->dir_y };
}
static inline void actor_set_direction(Actor* s, Vec2 v) {
    s->dir_x = (v.x > 0) - (v.x < 0);   /* clamp à -1/0/1 */
    s->dir_y = (v.y > 0) - (v.y < 0);
}

/* Les tables par emplacement qui vivent hors d'`Actor` (floor, drop_through, ancre de repos Rigid) : un emplacement
   les rend à zéro quand son occupant s'en va, pour que le suivant, posé ou né, parte comme un emplacement neuf.
   `scene_init` les remet à zéro pour tous les emplacements avec cette même fonction. */
extern int g_rigid_rest[][2];
static inline void actor_slot_tables_clear(int k) {
    if (g_actor_floor) g_actor_floor[k] = 0;
    if (g_drop_through) g_drop_through[k] = 0;
    g_rigid_rest[k][0] = 0; g_rigid_rest[k][1] = 0;
}

/* Le modèle fournit les valeurs initiales. L'emplacement fournit son identité
   de stockage et sa génération, y compris quand un spawn reprend un posé. */
static inline void __attribute__((unused, noinline)) actor_init_slot(
        int slot, int entry, const Actor* initial, const OamEntry* display) {
    Actor* actor = &g_actors[slot];
    u16 generation = actor->gen + 1;
    *actor = *initial;
    actor->gen = generation;
    actor->slot_index = slot;
    actor->oam_entry = entry;
    actor_slot_tables_clear(slot);
    g_slot_link[slot].parent = -1; g_slot_link[slot].depth = 0;   /* racine, jusqu'à `actor_link_slot` */
    if (entry >= 0) g_oam_entries[entry] = *display;
    actor->alive = 1;
    alive_bit_set(slot);
}

/* Activation / destruction */
static inline void slot_kill(Actor* s) {
    s->active=0; s->alive=0; s->gen++; actor_oam_entry(s)->visible=0; alive_bit_clear(s->slot_index);
    actor_slot_tables_clear(s->slot_index);
    if ((int)s->slot_index >= g_spool_start && (int)s->slot_index < g_spool_free) g_spool_free = s->slot_index;   /* l'emplacement redevient le premier libre */
}
/* Les enfants de l'emplacement `s` (`g_slot_link`), puis les leurs : chaque vivant est détruit. `release` : le sommet
   détruit était une RACINE, tout son sous-arbre est rendu ; ses emplacements perdent leur type (0), morts d'avant
   compris, et une partie de modèle redevient un emplacement libre du pool (`spool_slot_free`). Sans `release` (une
   partie détruite, sa racine vivante), le type reste : la partie garde sa place dans le groupe. */
static inline void slot_destroy_children(int s, int release) {
    SLOT_EACH(k) {
        if (g_slot_link[k].parent != s) continue;
        if (g_actors[k].alive) slot_kill(&g_actors[k]);
        else if (!release) continue;
        if (release) g_actors[k].type_id = 0;
        slot_destroy_children(k, release);
    }
}
/* Détruire un acteur détruit son sous-arbre, posé ou né. */
static inline void actor_destroy_internal(Actor* s)  {
    int release = slot_parent(s->slot_index) < 0;
    slot_kill(s);
    if (g_slot_depth) slot_destroy_children(s->slot_index, release);
}

/* La composition d'un enfant, chaque image, posé ou né : sa position monde est celle de son parent plus son décalage
   local (un acteur n'a ni rotation ni échelle, l'enfant suit en translation), sa visibilité celle de son parent ET la
   sienne. Un parent ÉTEINT éteint l'enfant (désactiver la racine désactive le
   sous-arbre) ; un enfant éteint ne se compose pas, et la racine ne le rallume pas. Appelée profondeur par
   profondeur (`slot_compose_all`) : le parent est toujours composé avant. */
static inline void slot_compose(int s) {
    const SlotLink* l = &g_slot_link[s];
    Actor* c = &g_actors[s];
    const Actor* p = &g_actors[l->parent];
    if (!p->active) { c->active = 0; return; }
    if (!c->active) return;
    c->x = p->x + l->ox;
    c->y = p->y + l->oy;
    if (c->oam_entry >= 0)
        g_oam_entries[c->oam_entry].visible = l->visible && (p->oam_entry < 0 || g_oam_entries[p->oam_entry].visible);
}
static inline void slot_compose_all(void) {
    for (int d = 1; d <= g_slot_depth; d++)
        SLOT_EACH(k) if (g_actors[k].alive && g_slot_link[k].depth == d) slot_compose(k);
}

/* Input */
/* Un masque à un bit garde le comportement historique. Avec plusieurs bits,
   les actions nommées du projet deviennent de vrais combos : tous les boutons
   doivent être tenus. `pressed` demande en plus qu'au moins l'un d'eux soit
   arrivé ce frame — le combo ne se répète donc pas pendant son maintien. */
static inline int input_held(int b) {
    return ((_g_keys_held & (u32)b) == (u32)b) ? 1 : 0;
}
static inline int input_pressed(int b) {
    return (((_g_keys_held & (u32)b) == (u32)b) &&
            (_g_keys_pressed & (u32)b)) ? 1 : 0;
}

/* Anneau des masques des derniers frames — `released`, `held(n)` et les
   séquences en dérivent. Profondeur et emplacements réels définis dans main.c. */
extern u16      _g_input_ring[];
extern int      _g_input_ring_pos;
extern const int g_input_ring_depth;

static inline u16 _input_ring_at(int frames_ago) {
    int idx = _g_input_ring_pos - frames_ago;
    while (idx < 0) idx += g_input_ring_depth;
    return _g_input_ring[idx % g_input_ring_depth];
}
static inline void _input_ring_push(u32 mask) {
    _g_input_ring_pos = (_g_input_ring_pos + 1) % g_input_ring_depth;
    _g_input_ring[_g_input_ring_pos] = (u16)mask;
}
/* Vrai si `mask` est complet à `frames_ago` et ne l'était pas au frame
   d'avant — un front montant, à une profondeur donnée de l'anneau. */
static inline int _input_edge_at(u16 mask, int frames_ago) {
    u16 now  = _input_ring_at(frames_ago);
    u16 prev = _input_ring_at(frames_ago + 1);
    return (((now & mask) == mask) && ((prev & mask) != mask)) ? 1 : 0;
}

/* Compteur de frames consécutives, un par bouton PHYSIQUE (BTN_* — bit i du
   masque). `held(nom, n)` en dérive exactement : un accord est tenu depuis n
   frames si CHACUN de ses boutons l'est. Défini dans main.c. */
extern u8 _g_key_hold_frames[10];

/* Appelé une fois par frame par main.c, juste après `_g_keys_held = keysHeld()`. */
static inline void _input_update_hold_frames(u32 mask) {
    for (int bit = 0; bit < 10; bit++) {
        if (mask & (1u << bit)) {
            if (_g_key_hold_frames[bit] < 255) _g_key_hold_frames[bit]++;
        } else {
            _g_key_hold_frames[bit] = 0;
        }
    }
}

static inline int input_held_n(int mask, int n) {
    if (n <= 1) return input_held(mask);
    for (int bit = 0; bit < 10; bit++)
        if ((mask & (1 << bit)) && _g_key_hold_frames[bit] < n) return 0;
    return 1;
}

/* `released` ne lit que le masque du frame précédent — aucun état propre. */
static inline int input_released(int mask) {
    u16 prev = _input_ring_at(1);
    return (((prev & (u16)mask) == (u16)mask) &&
            ((_g_keys_held & (u32)mask) != (u32)mask)) ? 1 : 0;
}

/* Un pas de séquence enchaîne le précédent en général sans relâcher tous ses
   boutons (down+right → right ne relâche QUE down) : le bouton du dernier pas
   est souvent déjà tenu depuis le pas d'avant, donc `_input_edge_at` (édition
   PAR BOUTON) n'y voit jamais de front. Ce qui marque vraiment l'entrée dans
   un pas est que le masque TOTAL des boutons tenus vient de changer — peu
   importe lequel a bougé. */
static inline int _input_step_entered_at(u16 mask, int frames_ago) {
    u16 now  = _input_ring_at(frames_ago);
    u16 prev = _input_ring_at(frames_ago + 1);
    return (((now & mask) == mask) && (now != prev)) ? 1 : 0;
}

/* `pressed` sur une séquence : le DERNIER pas vient de se compléter ce frame,
   et chaque pas précédent se trouve en amont, dans l'ordre, dans la fenêtre
   qui suit le pas suivant (pas celle qui suit le début de la séquence). */
static inline int input_seq_pressed(const u16* masks, int n, int window) {
    if (n <= 0 || !_input_step_entered_at(masks[n - 1], 0)) return 0;
    int cursor = 0;
    for (int i = n - 2; i >= 0; i--) {
        int found = -1;
        for (int d = cursor + 1; d <= cursor + window && d < g_input_ring_depth; d++) {
            if ((_input_ring_at(d) & masks[i]) == masks[i]) { found = d; break; }
        }
        if (found < 0) return 0;
        cursor = found;
    }
    return 1;
}

/* `buffered` consomme quand il répond vrai : un flag 1 bit par action
   interrogée (bitset, défini dans main.c — les autres actions n'en paient
   pas), remis à faux exactement au frame où l'appui redevient frais.
   PIÈGE (documenté dans scripting.md) : `if buffered("jump",6) and au_sol`
   consomme l'appui même en l'air puisque `buffered` s'évalue avant le `and` ;
   écrire `if au_sol and buffered("jump",6)` (court-circuit) pour ne
   l'évaluer qu'au sol. */
extern u8 _g_input_buffered_consumed[];

static inline int _input_buffered_get(int action_index) {
    return (_g_input_buffered_consumed[action_index >> 3] >> (action_index & 7)) & 1;
}
static inline void _input_buffered_set(int action_index, int v) {
    u8 bit = (u8)(1u << (action_index & 7));
    if (v) _g_input_buffered_consumed[action_index >> 3] |= bit;
    else   _g_input_buffered_consumed[action_index >> 3] &= (u8)~bit;
}
static inline int input_buffered(int action_index, int mask, int frames) {
    if (_input_edge_at((u16)mask, 0)) _input_buffered_set(action_index, 0);
    for (int d = 0; d < frames; d++) {
        if (_input_edge_at((u16)mask, d)) {
            if (_input_buffered_get(action_index)) return 0;
            _input_buffered_set(action_index, 1);
            return 1;
        }
    }
    return 0;
}

/* Position -1/0/1 d'un axe : la différence de deux masques (négatif/positif)
   lus sur _g_keys_held — pas d'état propre. Le codegen résout le NOM de
   l'axe ("horizontal"/"vertical", ou un `InputAxis` déclaré) en cette paire
   de masques au build ; le runtime ne
   connaît que des boutons. `get_axis(x, y)` compose deux appels dans
   `input_get_vector` — x et y restent lus le même frame, jamais
   désynchronisés. */
static inline int input_get_axis(int mask_neg, int mask_pos) {
    return (((_g_keys_held & (u32)mask_pos) == (u32)mask_pos) ? 1 : 0)
         - (((_g_keys_held & (u32)mask_neg) == (u32)mask_neg) ? 1 : 0);
}
static inline Vec2 input_get_vector(int mask_neg_x, int mask_pos_x,
                                    int mask_neg_y, int mask_pos_y) {
    Vec2 v;
    v.x = input_get_axis(mask_neg_x, mask_pos_x);
    v.y = input_get_axis(mask_neg_y, mask_pos_y);
    return v;
}

/* Collision AABB — teste une paire de CollisionShape dans l'espace monde */
static inline int box_overlap(int ax, int ay, const CollisionShape*ba,
                               int bx, int by, const CollisionShape*bb) {
    int alx=ax+(int)ba->x, aly=ay+(int)ba->y;
    int blx=bx+(int)bb->x, bly=by+(int)bb->y;
    return (alx < blx+(int)bb->w) && (alx+(int)ba->w > blx) &&
           (aly < bly+(int)bb->h) && (aly+(int)ba->h > bly);
}
/* ax/ay et bx/by sont des PIXELS : les positions d'acteur sont en Q8 (v0.19).
   Les passer telles quelles comparait du Q8 à des offsets en pixels, et faisait
   rater tout chevauchement de deux acteurs distants de plus d'1/256 de pixel. */

/* Vrai si au moins une paire de boxes se chevauche.
   Écrit les tags BOXTAG_* des boxes impliquées dans *my_box / *other_box. */
static inline int actors_overlap_boxes(const Actor*a, const Actor*b,
                                        u8*my_box, u8*other_box) {
    for (int i=0; i<a->collision.box_count; i++)
        for (int j=0; j<b->collision.box_count; j++)
            if (a->collision.boxes[i].active && b->collision.boxes[j].active &&
                box_overlap(a->x>>8,a->y>>8,&a->collision.boxes[i],
                            b->x>>8,b->y>>8,&b->collision.boxes[j])) {
                *my_box    = a->collision.boxes[i].tag;
                *other_box = b->collision.boxes[j].tag;
                return 1;
            }
    return 0;
}

/* Les contacts entre deux acteurs, UN BIT PAR COUPLE DE TAGS en contact.
   Un contact est identifié par ses tags, pas par ses boxes : deux boxes de même
   tag sur un acteur comptent pour une seule (c'est la première qui la
   représente, comme `actor_get_box`) — sinon un acteur à deux boxes `player`
   déclencherait deux fois le même `on_collision_enter`.
   Bit (i*MAX_BOXES+j) = boxes i de `a` et j de `b`, canoniques. Pieds contre
   tête ET corps contre corps sont donc deux contacts distincts, suivis chacun
   d'une frame à l'autre — le premier ne masque plus le second. */
/* Le test des boîtes et la boucle des paires tournent à chaque image pour chaque paire : leurs quelques centaines d'octets
   valent l'IWRAM (ARM, sans temps d'attente). Hors GBA (sondes natives), la fonction reste ordinaire. */
#ifdef __arm__
#define BS_ATTR_IWRAM __attribute__((noinline, section(".iwram"), target("arm"), long_call))
#else
#define BS_ATTR_IWRAM __attribute__((noinline))
#endif
/* L'écriture OAM d'un sprite affine : matrice du sprite (rotation, échelle), mémoïsée dans `ac` (cf. `AffCache`), position
   autour du pivot, puis une matrice prise à la frame (une identique déjà écrite est reprise) et l'emplacement `oamn`.
   Une seule copie pour tous les types affines : déroulée dans chaque cas du rendu, elle coûtait près de 3 Ko d'IWRAM par
   type. Ce qui diffère d'un sprite à l'autre arrive en argument : la caméra (0 pour un acteur en espace écran), le cadre
   `w` x `h`, la base de tuiles, les tuiles par frame, la forme et la taille OAM. Rend le prochain emplacement libre.
   L'appelant a vérifié qu'il reste une matrice (`*affn` < 32). Formules et repères : cf. `gen_affine.affine_oam_lines`.
   Elle écrit `shadow_oam` et `g_oam_dropped`, qui n'existent qu'avec `gba_engine.h` (dans main.c) : les fichiers des
   scripts, qui incluent aussi ce header, ne la voient pas. */
#ifdef GBA_ENGINE_H
BS_ATTR_IWRAM
static int __attribute__((unused)) oam_write_affine(const Actor* a, OamEntry* o, AffCache* ac, int oamn, int* affn,
        int cx, int cy, int w, int h, int base_tile, int tiles_per_frame, int shape, int size) {
    int rot=o->rotation, sx_q=o->scale_x, sy_q=o->scale_y;
    int fh=o->flip_h, fv=o->flip_v;
    int px=o->pivot_x, py=o->pivot_y;
    int lx=o->offset_x+w/2+px, ly=o->offset_y+h/2+py;     /* le centre du cadre, depuis la position de l'acteur */
    int fl=0x80|fh|(fv<<1);
    int stb=(ac->vrot==rot&&ac->vsx==sx_q&&ac->vsy==sy_q);
    ac->vrot=rot; ac->vsx=sx_q; ac->vsy=sy_q;
    int pa,pb,pc,pd,u,v;
    if(stb&&ac->rot==rot&&ac->sx==sx_q&&ac->sy==sy_q&&ac->px==px&&ac->py==py&&ac->fl==fl){
        pa=ac->pa; pb=ac->pb; pc=ac->pc; pd=ac->pd;
        u=ac->u; v=ac->v;
    } else {
        int sinA,cosA; gba_sincos(rot,&sinA,&cosA);
        int sxs=fh?-sx_q:sx_q, sys=fv?-sy_q:sy_q;
        gba_affine_matrix(cosA,sinA,sx_q,sy_q,&pa,&pb,&pc,&pd);
        u=(cosA*sxs*px)/65536-(sinA*sys*py)/65536;
        v=(sinA*sxs*px)/65536+(cosA*sys*py)/65536;
        if(stb){
            ac->rot=rot; ac->sx=sx_q; ac->sy=sy_q; ac->px=px; ac->py=py; ac->fl=fl;
            ac->pa=pa; ac->pb=pb; ac->pc=pc; ac->pd=pd;
            ac->u=u; ac->v=v;
        }
    }
    int sx=((a->x>>8)-cx)+lx-w-u, sy=((a->y>>8)-cy)+ly-h-v;
    u16 ti=(u16)(base_tile+o->frame*tiles_per_frame);
    if(!(sx+2*w>0&&sx<240&&sy+2*h>0&&sy<160)) return oamn;     /* boîte OAM en double taille : 2w x 2h */
    if(oamn>=128){ g_oam_dropped++; return oamn; }
    u16 m0=(u16)(s16)(fh?-pa:pa), m1=(u16)(s16)(fh?-pb:pb);
    u16 m2=(u16)(s16)(fv?-pc:pc), m3=(u16)(s16)(fv?-pd:pd);
    int as=0, n=*affn;
    while(as<n&&!(shadow_oam[as*4+0].dummy==m0&&shadow_oam[as*4+1].dummy==m1
                 &&shadow_oam[as*4+2].dummy==m2&&shadow_oam[as*4+3].dummy==m3)) as++;
    if(as==n){
        *affn=n+1;
        shadow_oam[as*4+0].dummy=m0; shadow_oam[as*4+1].dummy=m1;
        shadow_oam[as*4+2].dummy=m2; shadow_oam[as*4+3].dummy=m3;
    }
    o->affine_slot=as;
    shadow_oam[oamn].attr0=(sy&0xFF)|(1<<8)|(1<<9)|(o->obj_mode<<10)|(shape<<14);
    shadow_oam[oamn].attr1=(sx&0x1FF)|(as<<9)|(size<<14);
    shadow_oam[oamn].attr2=(ti&0x3FF)|(o->priority<<10)|(o->pal_bank<<12);
    return oamn+1;
}
#endif
_Static_assert(MAX_BOXES * MAX_BOXES <= 16, "actors_overlap_mask tient sur 16 bits");
static inline int _box_canonical(const Actor*a, int i) {
    for (int k=0; k<i; k++)
        if (a->collision.boxes[k].tag == a->collision.boxes[i].tag) return k;
    return i;
}
BS_ATTR_IWRAM
static u16 __attribute__((unused)) actors_overlap_mask(const Actor*a, const Actor*b,u16 allowed) {
    u16 m = 0;
    for (int i=0; i<a->collision.box_count; i++) {
        if (!a->collision.boxes[i].active) continue;
        for (int j=0; j<b->collision.box_count; j++) {
            int ci=_box_canonical(a,i), cj=_box_canonical(b,j);
            if ((allowed & (1u << (ci*MAX_BOXES+cj))) && b->collision.boxes[j].active &&
                box_overlap(a->x>>8,a->y>>8,&a->collision.boxes[i],
                            b->x>>8,b->y>>8,&b->collision.boxes[j]))
                m |= (u16)(1u << (ci*MAX_BOXES+cj));
        }
    }
    return m;
}

/* ── Areas ────────────────────────────────────────────────────────────────────
   Une Area n'a qu'une boîte. L'acteur qui la touche apprend le contact, et le script de l'Area aussi s'il en a un. Le test est celui des
   acteurs (`box_overlap`), la mémoire d'une frame à l'autre aussi ; le masque compte un bit par RANG de boîte de
   l'acteur (canonique, comme `actors_overlap_mask`), puisqu'il n'y a qu'une boîte de l'autre côté. `allowed` : les rangs
   dont le tag rencontre celui de l'Area (la matrice des tags, cuite au build). */
BS_ATTR_IWRAM
static u16 area_overlap_mask(const Area* ar, const Actor* a, u16 allowed) {
    u16 m = 0;
    if (!ar->active || ar->held || !ar->box.active) return 0;
    for (int j=0; j<a->collision.box_count; j++) {
        int cj=_box_canonical(a,j);
        if ((allowed & (1u << cj)) && a->collision.boxes[j].active &&
            box_overlap(ar->x>>8,ar->y>>8,&ar->box, a->x>>8,a->y>>8,&a->collision.boxes[j]))
            m |= (u16)(1u << cj);
    }
    return m;
}

/* Un crochet d'Area : enter, collide, exit, dans cet ordre ; NULL si le script n'y répond pas. `AreaFn` est celui de
   l'acteur (`on_area_*`), `AreaActorFn` celui du script de l'Area (`on_actor_*`, l'Area est une constante de son fichier). */
typedef void (*AreaFn)(Actor*, Area*, u8);
typedef void (*AreaActorFn)(Actor*, u8);

/* Les acteurs posés et nés passent par le MÊME code : `area_contact_step` est le pas d'un couple (Area, emplacement),
   appelé par le parcours des emplacements avec la mémoire de chacun. Un contact qui naît appelle enter, un qui
   dure collide, un qui se défait exit — avec le tag de la boîte de l'acteur. Un acteur détruit n'apprend rien (terminal) ;
   désactivé, il l'apprend à sa réactivation seulement : le seul `exit` utile est celui d'un acteur encore en jeu.
   Les deux côtés sont prévenus par le MÊME test : l'acteur d'abord (`on`), puis l'Area (`own`, NULL sans script), qui ne
   reçoit pas un acteur que son propre crochet vient de détruire. */
BS_ATTR_IWRAM
static void __attribute__((unused)) area_contact_step(Area* ar, Actor* a, u16 allowed, const AreaFn* on,
                                                      const AreaActorFn* own, u16* prev) {
    u16 cur = a->active ? area_overlap_mask(ar, a, allowed) : 0;
    u16 prv = *prev;
    if (cur | prv)
        for (u8 b = 0; b < MAX_BOXES; b++) {
            u16 m = (u16)(1u << b);
            u8 now = (cur & m) != 0, was = (prv & m) != 0;
            if (!now && !was) continue;
            u8 event = now ? (was ? 1 : 0) : 2;           /* enter : naît ; collide : dure ; exit : se défait */
            if (event == 2 && !(a->active && a->alive)) continue;
            u8 tag = a->collision.boxes[b].tag;
            if (on[event]) on[event](a, ar, tag);
            if (own && own[event] && a->alive) own[event](a, tag);
        }
    *prev = cur;
}

/* ── Effets de zone ───────────────────────────────────────────────────────────
   Une Area qui porte un GravityOverrideComponent et/ou un ForceFieldComponent agit sur les corps dont la boîte de physique la
   recouvre. Les acteurs posés et les instances du pool passent par la MÊME fonction, appelée dans le pas de mouvement juste
   avant que la gravité (`body_motion_step`, qui l'échelonne par type) soit ajoutée à la vélocité. Les réglages sont une table `const` du build (Q8). `g_fx_rng` est le
   générateur congruentiel linéaire de la turbulence : statique du fichier, remis à 1 à l entrée de chaque scène (`area_init_lines`), donc déterministe. */
#define AREAFX_GRAVITY    1u   /* zone : remplace la gravité de la scène */
#define AREAFX_CHARACTER  2u   /* zone : agit aussi sur les CharacterBody (force, turbulence, flottaison, traînée) */
typedef struct { Area* area; s16 gx, gy, fx, fy, buoyancy; u16 turbulence, retain; u8 flags; } AreaEffect;   /* Q8 ; retain 256 = pas de traînée */
static u32 g_fx_rng __attribute__((unused)) = 1;

BS_ATTR_IWRAM
static void __attribute__((unused)) area_effects_apply(const AreaEffect* fx, u8 n, Actor* a, u8 rank, const ModelDesc* d,
                                                       int* gx, int* gy) {
    const CollisionShape* b = &a->collision.boxes[rank];
    int buoyancy = 0;
    if (!b->active) return;
    for (u8 i = 0; i < n; i++) {
        const AreaEffect* e = &fx[i];
        const Area* ar = e->area;
        if (!ar->active || ar->held || !ar->box.active) continue;
        debug_physics_fx_test();
        if (!box_overlap(ar->x>>8, ar->y>>8, &ar->box, a->x>>8, a->y>>8, b)) continue;
        /* Un corps qui ignore la gravité de scène (`gravity_scale` nul) n'en reçoit pas non plus de la zone. */
        if ((e->flags & AREAFX_GRAVITY) && d->gravity_scale) { *gx = e->gx; *gy = e->gy; }
        if (d->body_mode == BODY_MODE_CHARACTER && !(e->flags & AREAFX_CHARACTER)) continue;
        if (e->retain != 256) { a->vx = (a->vx * e->retain) >> 8; a->vy = (a->vy * e->retain) >> 8; }
        a->vx += e->fx; a->vy += e->fy;
        if (e->turbulence) {
            int span = 2 * e->turbulence + 1;
            g_fx_rng = g_fx_rng * 1664525u + 1013904223u;
            a->vx += (int)((g_fx_rng >> 16) % span) - e->turbulence;
            g_fx_rng = g_fx_rng * 1664525u + 1013904223u;
            a->vy += (int)((g_fx_rng >> 16) % span) - e->turbulence;
        }
        if (e->buoyancy) {
            int cx = (a->x>>8) + b->x + b->w/2, cy = (a->y>>8) + b->y + b->h/2;
            int ax = (ar->x>>8) + ar->box.x, ay = (ar->y>>8) + ar->box.y;
            if (cx >= ax && cx < ax + ar->box.w && cy >= ay && cy < ay + ar->box.h) buoyancy += e->buoyancy;
        }
    }
    if (buoyancy) { *gx -= (*gx * buoyancy) >> 8; *gy -= (*gy * buoyancy) >> 8; }
}

/* La référence `area` d'un script : le rang de l'Area dans `g_areas`, plus un (0 = pas d'Area), comme la référence d'une
   boîte. `g_areas` existe dans tout projet (une entrée au moins), l'extern est donc toujours satisfait. */
extern Area g_areas[];
static inline int area_ref(const Area* ar) { return (int)(ar - g_areas) + 1; }
static inline Area* _area_of(int h) { return h ? &g_areas[h - 1] : 0; }
static inline int area_get_tag(int h)    { const Area* a = _area_of(h); return a ? a->box.tag : 0; }
static inline int area_get_active(int h) { const Area* a = _area_of(h); return a ? a->active : 0; }
static inline void area_set_active(int h, int on) { Area* a = _area_of(h); if (a) a->active = on ? 1 : 0; }
/* `area:get("Door")` : la constante AREA_<SCÈNE>_<NOM> du build EST la référence, et `area.name` la rend telle quelle : le
   nom se compare donc à cette même constante. */
static inline int area_by_name(int h) { return h; }
static inline int area_get_name(int h) { return h; }
static inline Vec2 area_get_position(int h) { const Area* a = _area_of(h); return a ? (Vec2){ a->x>>8, a->y>>8 } : (Vec2){ 0, 0 }; }
/* Une Area qui suit un acteur ne se déplace pas par script : sa position est recomposée à chaque frame depuis celle de son
   parent, une écriture serait écrasée aussitôt. Elle est donc sans effet (comme sur une référence absente). */
static inline void area_set_position(int h, Vec2 p) { Area* a = _area_of(h); if (a && !a->parent) { a->x = p.x << 8; a->y = p.y << 8; } }
/* L'acteur posé qu'elle suit, ou nil : sans parent, ou si le parent est détruit. */
static inline Actor* area_get_parent(int h) {
    const Area* a = _area_of(h);
    return (a && a->parent && g_actors[a->parent - 1].alive) ? &g_actors[a->parent - 1] : (Actor*)0;
}
/* La taille de la forme : w/h tiennent dans un u8 (cf. CollisionShape), bornés ici comme `collision_shape_set_size`. Une Area
   sans forme (`box.active` à 0) garde sa taille nulle : lire ou écrire la taille ne la rallume pas. */
static inline Vec2 area_get_size(int h) {
    const Area* a = _area_of(h);
    return (a && a->box.active) ? (Vec2){ a->box.w, a->box.h } : (Vec2){ 0, 0 };
}
static inline void area_set_size(int h, Vec2 v) {
    Area* a = _area_of(h);
    if (!a || !a->box.active) return;
    a->box.w = (u8)(v.x < 0 ? 0 : v.x > 255 ? 255 : v.x);
    a->box.h = (u8)(v.y < 0 ? 0 : v.y > 255 ? 255 : v.y);
}
/* Le rectangle MONDE de la forme : position (Q8 >> 8) plus décalage, plus taille ; vide sans Area ou sans forme. */
static inline Rect area_get_bounds(int h) {
    const Area* a = _area_of(h);
    if (!a || !a->box.active) return (Rect){ 0, 0, 0, 0 };
    return (Rect){ (a->x>>8) + a->box.x, (a->y>>8) + a->box.y, a->box.w, a->box.h };
}
/* Un test GÉOMÉTRIQUE : ni matrice de tags, ni déclencheur. Une Area ou une boîte inactive ne touche personne. */
static inline int area_overlaps_actor(int h, const Actor* other) {
    const Area* a = _area_of(h);
    if (!a || !a->active || a->held || !a->box.active || !other) return 0;
    for (int j = 0; j < other->collision.box_count; j++)
        if (other->collision.boxes[j].active &&
            box_overlap(a->x>>8, a->y>>8, &a->box, other->x>>8, other->y>>8, &other->collision.boxes[j]))
            return 1;
    return 0;
}

/* Rétrocompatibilité — teste sans récupérer les tags */
static inline int actors_overlap(const Actor*a, const Actor*b) {
    u8 _a=0,_b=0; return actors_overlap_boxes(a,b,&_a,&_b);
}

/* Tag */
static inline int actor_get_name(const Actor* s) { return s->name; }

/* Palette (flash de dégâts, invincibilité…) */
static inline int  actor_get_pal(const Actor* s)    { return actor_oam_entry(s)->pal_bank; }
static inline void actor_set_pal(Actor* s, int bank) { actor_oam_entry(s)->pal_bank = bank & 0xF; }

/* Mode OAM — 0 = sprite normal, 2 = fenêtre-objet : le sprite n'est plus
   dessiné, ses pixels opaques DÉCOUPENT la région window.OBJ (forme libre,
   animable, sans interruption). Mode 1 (semi-transparent) suppose le
   blending, pas encore câblé. */
static inline void actor_set_obj_mode(Actor* s, int mode) { actor_oam_entry(s)->obj_mode = mode & 3; }
static inline int  actor_get_obj_mode(const Actor* s)     { return actor_oam_entry(s)->obj_mode; }

/* Ordre d'affichage face aux BG layers (self.priority) — même registre OAM
   que pal_bank/obj_mode ci-dessus, donc la même liberté de le lire/l'écrire. */
static inline void actor_set_priority(Actor* s, int p) { actor_oam_entry(s)->priority = p & 3; }
static inline int  actor_get_priority(const Actor* s)  { return actor_oam_entry(s)->priority; }

/* Maths */
static inline int math_abs  (int x)              { return x < 0 ? -x : x; }
static inline int math_clamp(int x, int lo, int hi){ return x<lo?lo:x>hi?hi:x; }
static inline int math_sign (int x)              { return (x > 0) - (x < 0); }
static inline int math_min  (int a, int b)       { return a < b ? a : b; }
static inline int math_max  (int a, int b)       { return a > b ? a : b; }
/* Interpolation linéaire entre a et b, à la fraction num/den (mêmes entiers
   que le reste de l'API — pas de virgule flottante sur GBA). Ex: une valeur
   qui glisse de 0 à 100 sur 30 frames : math.lerp(0, 100, frame, 30). */
static inline int math_lerp(int a, int b, int num, int den) {
    if (den == 0) return a;
    return a + (b - a) * num / den;
}
/* Comme math.lerp, mais en courbant la fraction num/den avant de l'appliquer
   (quadratique — pas de sinus/flottant sur GBA) :
     "in"     démarre lentement, accélère à l'arrivée (ex: chute) ;
     "out"    démarre vite, ralentit à l'arrivée (ex: freinage, rebond) ;
     "in_out" les deux, symétriques autour du milieu. */
static inline int math_ease(int a, int b, int num, int den, int kind) {
    if (den <= 0) return a;
    if (num <= 0) return a;
    if (num >= den) return b;
    int t = num, d = den, t2;
    switch (kind) {
        case EASE_OUT:
            t2 = d - (d - t) * (d - t) / d;
            break;
        case EASE_IN_OUT:
            if (t < d / 2) t2 = 2 * t * t / d;
            else { int u = d - t; t2 = d - 2 * u * u / d; }
            break;
        default: /* EASE_IN */
            t2 = t * t / d;
            break;
    }
    return a + (b - a) * t2 / d;
}

/* Frame counter global (défini dans main.c) */
extern int _g_frame;
static inline int scene_frame(void) { return _g_frame; }

/* Carte de collision — le type de tile à une position monde (0 = vide) */
extern int collision_map_tile(int px, int py);

/* Aléatoire — LCG 32-bit, zéro overhead, pas de division flottante */
/* La graine est définie dans main.c : `static` ici, chaque unité de script
   aurait sa propre suite, identique aux autres. */
extern u32 _g_rand_seed;
static inline int math_rand(int lo, int hi) {
    _g_rand_seed = _g_rand_seed * 1664525u + 1013904223u;
    int range = hi - lo + 1;
    if (range <= 0) return lo;
    return lo + (int)((_g_rand_seed >> 16) % (u32)range);
}

/* Trigonométrie — réutilise SIN_LUT/gba_sin/gba_cos (déjà écrits plus haut
   pour la matrice affine) : même échelle Q8 (×256) que le hardware, donc pas
   de nouvelle table à maintenir en cohérence. */
static inline int math_sin(int deg) { return gba_sin(deg); }
static inline int math_cos(int deg) { return gba_cos(deg); }

/* Racine carrée entière (méthode du chiffre binaire) — pas de sqrt() flottant
   sur GBA. Négatif ou nul → 0 plutôt que NaN. */
static inline int math_sqrt(int x) {
    if (x <= 0) return 0;
    u32 n = (u32)x, res = 0, bit = 1u << 30;
    while (bit > n) bit >>= 2;
    while (bit != 0) {
        if (n >= res + bit) { n -= res + bit; res = (res >> 1) + bit; }
        else res >>= 1;
        bit >>= 2;
    }
    return (int)res;
}

/* Angle en degrés (0-359) du vecteur (x, y) — même convention d'axes que
   self.rotation puisque calculé par dichotomie CONTRE gba_sin/gba_cos plutôt
   qu'avec une approximation séparée : toujours cohérent avec la matrice
   affine réellement posée à l'écran. sin croît et cos décroît sur [0, 90],
   donc sin(d)*ax - cos(d)*ay est monotone → la dichotomie cherche son zéro. */
static inline int math_atan2(int y, int x) {
    if (x == 0 && y == 0) return 0;
    int ax = math_abs(x), ay = math_abs(y);
    int deg;
    if (ay == 0) deg = 0;
    else if (ax == 0) deg = 90;
    else {
        int lo = 0, hi = 90;
        while (hi - lo > 1) {
            int mid = (lo + hi) / 2;
            if (gba_sin(mid) * ax >= gba_cos(mid) * ay) hi = mid; else lo = mid;
        }
        /* La dichotomie rend le premier degré PASSANT (arrondi vers le haut) ; on garde
           du couple lo/hi celui dont le produit croisé est le plus proche de zéro. */
        int err_lo = math_abs(gba_sin(lo) * ax - gba_cos(lo) * ay);
        int err_hi = math_abs(gba_sin(hi) * ax - gba_cos(hi) * ay);
        deg = (err_lo < err_hi) ? lo : hi;
    }
    if (x >= 0 && y >= 0) return deg;
    if (x <  0 && y >= 0) return 180 - deg;
    if (x <  0 && y <  0) return 180 + deg;
    return 360 - deg;
}

/* Juiciness — effets de feedback sur le sprite (self:squash, self:stretch,
   self:bounce, self:shake, self:flash, self:blink, self:pulse, self:pop,
   self:wobble). Chacun est une fonction PURE de (t, duration, amount) :
   aucun état caché, aucune coroutine (impossible sur GBA) — c'est l'appelant qui fait avancer `t` d'une frame à
   l'autre et qui décide où ce compteur vit (une variable de tête du script,
   ou une GlobalVar quand plusieurs scripts la regardent). Au-delà de
   `duration`, chacun retombe à son état neutre (scale 100, offset 0,
   rotation 0, pal 0, visible true) — rien à réinitialiser à la main.
   Ne composent QUE scripting/api.py, « self.sprite_scale/sprite_offset/
   sprite_rotation/pal/visible » et math_ease/math_lerp/math_rand
   ci-dessus : un script Lua pourrait écrire la même chose à la main. */
static inline void actor_squash(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    Vec2 v;
    v.x = math_ease(100 + amount, 100, t, duration, EASE_OUT);
    v.y = math_ease(100 - amount, 100, t, duration, EASE_OUT);
    actor_set_sprite_scale(s, v);
}
static inline void actor_stretch(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    Vec2 v;
    v.x = math_ease(100 - amount, 100, t, duration, EASE_OUT);
    v.y = math_ease(100 + amount, 100, t, duration, EASE_OUT);
    actor_set_sprite_scale(s, v);
}
static inline void actor_bounce(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    int half = math_max(1, duration / 2);
    int y;
    if (t <= half) y = -math_ease(0, amount, t, half, EASE_OUT);
    else           y =  math_ease(-amount, 0, t - half, math_max(1, duration - half), EASE_IN);
    Vec2 o = actor_get_sprite_offset(s);
    o.y = y;
    actor_set_sprite_offset(s, o);
}
static inline void actor_shake(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    int decayed = math_ease(amount, 0, t, math_max(1, duration), EASE_OUT);
    Vec2 o;
    o.x = math_rand(-decayed, decayed);
    o.y = math_rand(-decayed, decayed);
    actor_set_sprite_offset(s, o);
}
static inline void actor_flash(Actor* s, int t, int duration, int pal) {
    actor_set_pal(s, (t >= 0 && t < duration) ? pal : 0);
}
static inline void actor_blink(Actor* s, int t, int duration, int interval) {
    if (t < 0 || t >= duration) { actor_set_visible(s, 1); return; }
    interval = math_max(1, interval);
    actor_set_visible(s, ((t / interval) % 2) == 0);
}
static inline void actor_pulse(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    int half = math_max(1, duration / 2);
    int a;
    if (t <= half) a = math_ease(100, 100 + amount, t, half, EASE_OUT);
    else           a = math_ease(100 + amount, 100, t - half, math_max(1, duration - half), EASE_IN);
    actor_set_sprite_scale(s, (Vec2){ a, a });
}
static inline void actor_pop(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    int split = math_max(1, duration * 3 / 5);
    int a;
    if (t <= split) a = math_ease(0, 100 + amount, t, split, EASE_OUT);
    else            a = math_ease(100 + amount, 100, t - split, math_max(1, duration - split), EASE_IN_OUT);
    actor_set_sprite_scale(s, (Vec2){ a, a });
}
static inline void actor_wobble(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    int period = math_max(1, duration / 3);
    int half = math_max(1, period / 2);
    int phase = t % period;
    int decayed = amount * (duration - t) / math_max(1, duration);
    int deg;
    if (phase < half) deg = math_lerp(-decayed, decayed, phase, half);
    else               deg = math_lerp(decayed, -decayed, phase - half, math_max(1, period - half));
    actor_set_sprite_rotation(s, ((deg % 360) + 360) % 360);
}

/* Caméra — suivi avec zone morte (dead-zone follow) */
static inline void camera_follow(Vec2 target, int mx, int my) {
    int tx = target.x, ty = target.y;
    if (tx - cam_x < mx)              cam_x = tx - mx;
    if (tx - cam_x > SCREEN_W - mx)   cam_x = tx - (SCREEN_W - mx);
    if (ty - cam_y < my)              cam_y = ty - my;
    if (ty - cam_y > SCREEN_H - my)   cam_y = ty - (SCREEN_H - my);
}

/* Visibilité — commune aux trois types d'élément (texte, conteneur, image) :
   `ui.get("nom")` résout au NOM d'élément DIRECTEMENT en `UIELEM_*` (cf.
   ui_element_constant), donc AUCUN appel de fonction pour `ui.get` lui-même
   — seul `self:show()`/`self:hide()` en émettent un, vers celle-ci. */
extern void ui_element_show(int idx, int on);

/* `image.offset` — le décalage d'une image, un vec2. Le moteur le tient en deux entiers
   (`ui_image_move`/`dx`/`dy`, dans gba_engine.h), qui ne connaissent pas `Vec2` : la
   conversion vit ici, dans la façade que les scripts incluent. Ces trois prototypes ne
   sont plus dans le catalogue — plus aucune entrée ne les nomme —, d'où l'`extern`. */
/* `layer.scroll` — même raison : le moteur tient le décalage d'un fond en deux entiers. */
extern void layer_set_scroll(int bg, int x, int y);
extern int  layer_get_scroll_x(int bg);
extern int  layer_get_scroll_y(int bg);
static inline Vec2 layer_get_scroll(int bg) { return (Vec2){ layer_get_scroll_x(bg), layer_get_scroll_y(bg) }; }
static inline void layer_set_scroll_to(int bg, Vec2 v) { layer_set_scroll(bg, v.x, v.y); }
/* `layer.scroll_speed` — la vitesse de parallax d'un fond, en POURCENT pour l'auteur (100 =
   suit la caméra, 50 = deux fois plus lent). Le moteur la tient en Q8 (256 = 100 %), comme
   la multiplication du tick : la conversion vit ici. Arrondie dans les deux sens : sans cela,
   `scroll_speed = scroll_speed + 1` resterait bloquée (51 % → Q8 130 → relu 50 %). */
extern int  layer_get_speed(int bg);
extern void layer_set_speed(int bg, int q8);
static inline int  layer_get_scroll_speed(int bg) { return (layer_get_speed(bg) * 100 + 128) >> 8; }
static inline void layer_set_scroll_speed(int bg, int percent) { layer_set_speed(bg, (percent * 256 + 50) / 100); }
extern void ui_image_move(int img, int dx, int dy);

extern int  ui_image_dx(int img);
extern int  ui_image_dy(int img);
static inline Vec2 ui_image_offset(int img) { return (Vec2){ ui_image_dx(img), ui_image_dy(img) }; }
static inline void ui_image_set_offset(int img, Vec2 v) { ui_image_move(img, v.x, v.y); }

/* save:read(slot, "nom") côté Lua : la valeur d'UNE variable
   persistante dans un emplacement, sans toucher aux globales de la partie en
   cours — contrairement à save_read ci-dessus. `idx` est un GLOBAL_*, résolu
   par le codegen depuis le nom littéral (contrairement à global.nom, résolu
   par accès pointé — chantier global/const). */
extern int save_read_var(int slot, int idx);


/* Y a-t-il un sol sous les pieds ?

   Lecture du drapeau posé par la résolution contre la carte de collision, et
   non un nouveau balayage : la résolution connaît les PENTES, un balayage de
   `tile_solid_at` répondrait « non » sur toute pente puisque celle-ci n'est
   solide que dans une partie de sa colonne.

   L'état est donc celui de la FIN de la frame précédente — la résolution
   s'exécute après les `on_update`. C'est le contrat normal d'un état de
   collision, et le seul possible : pendant `on_update`, l'acteur n'a pas encore
   fini de bouger. */
static inline Actor* actor_get_floor(const Actor* a) {
    if (!a || !a->alive || !a->active || !g_actor_floor) return (Actor*)0;
    u16 ref = g_actor_floor[a->slot_index];
    if (!ref) return (Actor*)0;
    Actor* floor = &g_actors[ref - 1];
    return floor->alive && floor->active ? floor : (Actor*)0;
}
static inline int actor_on_ground(const Actor*a) {
    return a && (a->collision.grounded || actor_get_floor(a));
}

/* ── Inspecteur → API : ce que l'éditeur règle, le script le lit ────────────
   Lecture seule : ces deux drapeaux sont fixés au build (le C de rendu émis
   dépend d'eux), les écrire en jeu n'aurait aucun effet. */
static inline int actor_get_screen_space(const Actor* s) { return actor_oam_entry(s)->screen_space; }
/* « Affine transform » du OamEntry : vrai si le sprite est dessiné en affine
   (affine_slot vaut -1 sinon). Rien de plus à stocker. */
static inline int actor_get_affine(const Actor* s)       { return actor_oam_entry(s)->affine_slot >= 0; }
static inline int actor_get_box_count(const Actor* s)    { return s->collision.box_count; }

/* ── Boîtes de collision — la référence `collision_shape` ─────────────────────
   Une boîte est nommée par son tag (BOXTAG_*, le champ « Tag » du
   CollisionShapeComponent), et un script la tient dans une variable :
   `local hb = self:collision_shape("hitbox")`. La référence est un ENTIER — le
   rang de l'acteur dans g_actors, puis celui de la boîte, plus un — parce que
   0 doit dire « pas de boîte » (`if not hb`), comme la référence d'un effet
   sonore. Une boîte absente se lit vide et s'écrit sans effet (même politique
   qu'un index hors plage). Deux boîtes de même tag sur un acteur : la première
   répond. Le tag est la CLÉ, donc en lecture seule. */
static inline int actor_get_box(const Actor* s, int tag) {
    for (int i = 0; i < s->collision.box_count; i++)
        if (s->collision.boxes[i].tag == tag)
            return (int)(s - g_actors) * MAX_BOXES + i + 1;
    return 0;
}
static inline CollisionShape* _box_of(int h)    { return h ? &g_actors[(h-1)/MAX_BOXES].collision.boxes[(h-1)%MAX_BOXES] : 0; }
static inline Actor*        _box_owner(int h) { return &g_actors[(h-1)/MAX_BOXES]; }

static inline int collision_shape_get_tag(int h)    { const CollisionShape* b = _box_of(h); return b ? b->tag : 0; }
static inline int collision_shape_get_active(int h) { const CollisionShape* b = _box_of(h); return b ? b->active : 0; }
static inline void collision_shape_set_active(int h, int on) {
    CollisionShape* b = _box_of(h);
    if (b) b->active = on ? 1 : 0;
}
static inline int collision_shape_get_grounded(int h) { const CollisionShape* b = _box_of(h); return b ? b->grounded : 0; }
/* La carte de collision à un point MONDE. Le point ne dépend pas de la boîte : elle sert
   de porte d'entrée (une boîte absente répond 0, comme toute lecture d'une boîte absente). */
static inline int collision_shape_get_collision_tile(int h, int x, int y) {
    return h ? collision_map_tile(x, y) : 0;
}
static inline int collision_shape_get_solid(int h)  { const CollisionShape* b = _box_of(h); return b ? b->solid : 0; }
static inline void collision_shape_set_solid(int h, int on) {
    CollisionShape* b = _box_of(h);
    if (b) b->solid = on ? 1 : 0;
}
static inline Vec2 collision_shape_get_offset(int h) {
    const CollisionShape* b = _box_of(h);
    return b ? (Vec2){ b->x, b->y } : (Vec2){ 0, 0 };
}
static inline Vec2 collision_shape_get_size(int h) {
    const CollisionShape* b = _box_of(h);
    return b ? (Vec2){ b->w, b->h } : (Vec2){ 0, 0 };
}
/* x/y tiennent dans un s8, w/h dans un u8 (cf. CollisionShape) : bornés ici, un
   script ne peut pas corrompre la boîte voisine par débordement. */
static inline void collision_shape_set_offset(int h, Vec2 v) {
    CollisionShape* b = _box_of(h);
    if (!b) return;
    b->x = (s8)(v.x < -128 ? -128 : v.x > 127 ? 127 : v.x);
    b->y = (s8)(v.y < -128 ? -128 : v.y > 127 ? 127 : v.y);
}
static inline void collision_shape_set_size(int h, Vec2 v) {
    CollisionShape* b = _box_of(h);
    if (!b) return;
    b->w = (u8)(v.x < 0 ? 0 : v.x > 255 ? 255 : v.x);
    b->h = (u8)(v.y < 0 ? 0 : v.y > 255 ? 255 : v.y);
}
/* Le rectangle MONDE, en pixels : position de l'acteur + décalage + taille. */
static inline Rect collision_shape_get_bounds(int h) {
    const CollisionShape* b = _box_of(h);
    if (!b) return (Rect){ 0, 0, 0, 0 };
    const Actor* o = _box_owner(h);
    return (Rect){ (o->x>>8) + b->x, (o->y>>8) + b->y, b->w, b->h };
}
/* Deux boîtes se chevauchent-elles ? Une boîte inactive ne touche personne. */
static inline int collision_shape_overlaps_box(int h, int other) {
    const CollisionShape* a = _box_of(h);
    const CollisionShape* b = _box_of(other);
    if (!a || !b || !a->active || !b->active) return 0;
    const Actor* oa = _box_owner(h);
    const Actor* ob = _box_owner(other);
    return box_overlap(oa->x>>8, oa->y>>8, a, ob->x>>8, ob->y>>8, b);
}
/* ... ou l'une des boîtes actives de cet acteur ? */
static inline int collision_shape_overlaps_actor(int h, const Actor* other) {
    const CollisionShape* a = _box_of(h);
    if (!a || !a->active || !other) return 0;
    const Actor* oa = _box_owner(h);
    for (int j = 0; j < other->collision.box_count; j++)
        if (other->collision.boxes[j].active &&
            box_overlap(oa->x>>8, oa->y>>8, a, other->x>>8, other->y>>8, &other->collision.boxes[j]))
            return 1;
    return 0;
}

#endif /* RUNTIME_API_INLINE_H */
