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

/* Les constantes que voient les unités de script — énumérations matérielles
   nommées (modes OAM, directions, blending, ease) ET régions de window
   (`WINR_*`) — ne sont PLUS ici : leurs `#define` sont GÉNÉRÉS dans `runtime_api.h`
   (cf. api_prototypes — les énums depuis api.py, les WINR extraites de
   gba_engine.h), qui inclut ce fichier juste après. Les impls inline ci-dessous
   les voient donc, et il n'y a plus de valeur à tenir d'accord à la main. */



/* Globaux définis dans main.c, visibles par tous les scripts */
extern Actor g_actors[];
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
        if (cam_x < lo) cam_x = lo;
        if (cam_x > hi) cam_x = hi;
    }
    if (g_bounds_h > 0) {
        int lo = g_bounds_y, hi = g_bounds_y + g_bounds_h - SCREEN_H;
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
    g_cam_margin_x = m.x < 0 ? 0 : m.x;
    g_cam_margin_y = m.y < 0 ? 0 : m.y;
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

/* Déclarées en avance : camera_switch() les appelle avant le bloc Windows
   plus bas (redéclaration légale en C, mêmes signatures — même raison que les
   constantes WINR_* dupliquées en tête de fichier). */

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
static inline Vec2 vec2_div  (Vec2 a, Vec2 b) { return (Vec2){ a.x/b.x, a.y/b.y }; }
static inline Vec3 vec3_div  (Vec3 a, Vec3 b) { return (Vec3){ a.x/b.x, a.y/b.y, a.z/b.z }; }
static inline Vec3 vec3_scale(Vec3 v, int k)  { return (Vec3){ v.x*k,   v.y*k,   v.z*k   }; }
/* Un entier mêlé à un vecteur par `+`/`-` vaut ce vecteur dont TOUTES les
   composantes sont cet entier : `v + 2` = `v + vec2(2, 2)`. */
static inline Vec2 vec2_splat(int k) { return (Vec2){ k, k }; }
static inline Vec3 vec3_splat(int k) { return (Vec3){ k, k, k }; }

/* Transform — position instantanée, sans notion de temps ni de vitesse.
   ROADMAP v0.19 : s->x/s->y sont en Q8 en interne (256 = 1 px), mais
   self.position continue de rendre des PIXELS — décision verrouillée : un
   projet existant ne change pas de comportement, et un auteur qui n'a pas
   besoin de sous-pixel n'en entend jamais parler. L'écriture perd donc toute
   fraction sous-pixel accumulée (ex: par self:apply_velocity()) — c'est
   attendu d'un appel qui dit « l'acteur est ICI, au pixel », pas « avance ». */
static inline void actor_set_position(Actor* s, Vec2 p) { s->x=p.x<<8; s->y=p.y<<8; }
static inline Vec2 actor_get_position(const Actor* s)   { return (Vec2){ s->x>>8, s->y>>8 }; }

/* get_actor rend un acteur VIVANT, ou nil (ROADMAP « L'acteur appartient à sa
   scène », décision C') : un acteur détruit au runtime (`self:destroy()` →
   active=0) n'est plus « là », et le dire au script est une information de
   gameplay (« ma cible existe-t-elle encore ? »). Le chemin compile-time de
   get_actor passe donc par ce filtre — coût : un test du drapeau active. */
static inline Actor* actor_live(Actor* s) { return (s && s->active) ? s : (Actor*)0; }

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
    s->x += dx * (speed<<8) / mag;
    s->y += dy * (speed<<8) / mag;
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
    if (dist <= speed) { s->x = target.x<<8; s->y = target.y<<8; return; }
    s->x += (dx * speed / dist) << 8;
    s->y += (dy * speed / dist) << 8;
}

/* Physics — vélocité stockée sur l'Actor, lue par get_velocity. Ne déplace
   rien seule : c'est le script qui l'applique, via actor_apply_velocity
   (cf. Ball.lua) ou en l'ignorant.

   ROADMAP v0.19 : self.velocity change de SENS — s->vx/s->vy sont Q8, et
   get/set_velocity ne convertissent plus rien (contrairement à la position,
   qui reste pixels). Un script qui lisait/écrivait self.velocity en pixels
   avant cette version doit être migré : c'est la rupture assumée qui rend le
   sous-pixel utilisable sans un second nom (self.velocity_q8) à côté du
   premier. */
static inline void actor_set_velocity(Actor* s, Vec2 v) { s->vx=v.x; s->vy=v.y; }
static inline void actor_add_velocity(Actor* s, Vec2 dv){ s->vx+=dv.x; s->vy+=dv.y; }
static inline Vec2 actor_get_velocity(const Actor* s)    { return (Vec2){ s->vx, s->vy }; }
/* Applique la vélocité Q8 stockée à la position Q8 stockée — l'accumulateur
   sous-pixel est LITTÉRALEMENT s->x/s->y, donc rien à reporter ailleurs
   (contrairement à slope_acc, qui corrige une AUTRE fraction : le cosinus de
   pente en collision, cf. resolve_actor_tiles). Remplace l'ancien idiome
   `self.position = self.position + self.velocity`, qui n'a plus de sens dès
   que les deux membres ont des échelles différentes. */
static inline void actor_apply_velocity(Actor* s) { s->x+=s->vx; s->y+=s->vy; }

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
    o->pal_bank = a->pal_bank; o->auto_dir = a->auto_dir;
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
   Champs PAR-ACTOR de la struct Actor (cf. actor_types_static.h), et non des
   globaux par slot : un script de prefab poolé est UNE fonction C partagée par
   toutes ses instances, mais chaque instance a sa propre struct Actor et un
   slot différent (OamEntry.affine_slot). Des globaux dans ce header `static`
   créaient une COPIE par unité de compilation (main.c vs actor_*.c) — les
   écritures self.rotation/self.scale n'atteignaient jamais le rendu.
   Pas de FPU sur GBA : SIN_LUT est une table degrés→Q8 (×256) écrite en dur.
   gba_cos se déduit d'un déphasage de 90° plutôt qu'une seconde table. */
static const s16 SIN_LUT[360] = {
    0, 4, 9, 13, 18, 22, 27, 31, 36, 40, 44, 49,
    53, 58, 62, 66, 71, 75, 79, 83, 88, 92, 96, 100,
    104, 108, 112, 116, 120, 124, 128, 132, 136, 139, 143, 147,
    150, 154, 158, 161, 165, 168, 171, 175, 178, 181, 184, 187,
    190, 193, 196, 199, 202, 204, 207, 210, 212, 215, 217, 219,
    222, 224, 226, 228, 230, 232, 234, 236, 237, 239, 241, 242,
    243, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 254,
    255, 255, 255, 256, 256, 256, 256, 256, 256, 256, 255, 255,
    255, 254, 254, 253, 252, 251, 250, 249, 248, 247, 246, 245,
    243, 242, 241, 239, 237, 236, 234, 232, 230, 228, 226, 224,
    222, 219, 217, 215, 212, 210, 207, 204, 202, 199, 196, 193,
    190, 187, 184, 181, 178, 175, 171, 168, 165, 161, 158, 154,
    150, 147, 143, 139, 136, 132, 128, 124, 120, 116, 112, 108,
    104, 100, 96, 92, 88, 83, 79, 75, 71, 66, 62, 58,
    53, 49, 44, 40, 36, 31, 27, 22, 18, 13, 9, 4,
    0, -4, -9, -13, -18, -22, -27, -31, -36, -40, -44, -49,
    -53, -58, -62, -66, -71, -75, -79, -83, -88, -92, -96, -100,
    -104, -108, -112, -116, -120, -124, -128, -132, -136, -139, -143, -147,
    -150, -154, -158, -161, -165, -168, -171, -175, -178, -181, -184, -187,
    -190, -193, -196, -199, -202, -204, -207, -210, -212, -215, -217, -219,
    -222, -224, -226, -228, -230, -232, -234, -236, -237, -239, -241, -242,
    -243, -245, -246, -247, -248, -249, -250, -251, -252, -253, -254, -254,
    -255, -255, -255, -256, -256, -256, -256, -256, -256, -256, -255, -255,
    -255, -254, -254, -253, -252, -251, -250, -249, -248, -247, -246, -245,
    -243, -242, -241, -239, -237, -236, -234, -232, -230, -228, -226, -224,
    -222, -219, -217, -215, -212, -210, -207, -204, -202, -199, -196, -193,
    -190, -187, -184, -181, -178, -175, -171, -168, -165, -161, -158, -154,
    -150, -147, -143, -139, -136, -132, -128, -124, -120, -116, -112, -108,
    -104, -100, -96, -92, -88, -83, -79, -75, -71, -66, -62, -58,
    -53, -49, -44, -40, -36, -31, -27, -22, -18, -13, -9, -4,
};
static inline int gba_sin(int deg) { deg = ((deg % 360) + 360) % 360; return SIN_LUT[deg]; }
static inline int gba_cos(int deg) { return gba_sin(deg + 90); }

/* Un matrix slot est réservé au build quand « Affine transform » est coché sur
   le OamEntry (cf. main_gen._compute_affine_info) ; sprite.affine_slot
   est alors >= 0 et le rendu écrit une matrice.

   Ces accesseurs ne le CONSULTENT PAS. Ils l'ont fait — setter no-op et getter
   identité sans slot — et c'était un piège : `self.rotation = self.rotation + 1`
   n'incrémentait rien, la valeur ne faisait même pas l'aller-retour. Ces champs
   occupent leur place dans chaque Actor de toute façon ; ils sont donc de
   l'ÉTAT DE JEU, toujours lisible et écrivable. Sans slot, ils ne s'affichent
   simplement pas — le build le signale par un avertissement du checker. */

/* Transform MONDE (self.rotation / self.scale). */
static inline void actor_set_rotation(Actor* s, int deg) {
    s->rotation = deg;
}
static inline void actor_set_scale(Actor* s, Vec2 v) {
    s->scale_x = v.x * 256 / 100;
    s->scale_y = v.y * 256 / 100;
}
static inline int  actor_get_rotation(const Actor* s) {
    return s->rotation;
}
static inline Vec2 actor_get_scale(const Actor* s) {
    return (Vec2){ s->scale_x * 100 / 256, s->scale_y * 100 / 256 };
}

/* Transform LOCAL du sprite (self.sprite_rotation / self.sprite_scale /
   self.sprite_offset), composé par-dessus le monde : la rotation s'AJOUTE,
   le scale se MULTIPLIE, l'offset déplace le sprite dans le repère de l'actor. */
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
static inline void actor_set_auto_dir(Actor* s, int v)    { actor_oam_entry(s)->auto_dir=v?1:0; }
/* La lecture manquait : `auto_dir` s'écrivait sans pouvoir se relire, donc un
   script qui voulait le basculer devait tenir son propre drapeau à côté. */
static inline int  actor_get_auto_dir(const Actor* s)     { return actor_oam_entry(s)->auto_dir; }

/* Direction : vecteur discret (-1|0|1) indépendant du flip */
static inline Vec2 actor_get_direction(const Actor* s) {
    return (Vec2){ s->dir_x, s->dir_y };
}
static inline void actor_set_direction(Actor* s, Vec2 v) {
    s->dir_x = (v.x > 0) - (v.x < 0);   /* clamp à -1/0/1 */
    s->dir_y = (v.y > 0) - (v.y < 0);
}

/* Activation / destruction */
static inline void actor_destroy_internal(Actor* s)  { s->active=0; actor_oam_entry(s)->visible=0; }

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
   séquences en dérivent. Profondeur et emplacements réels définis dans main.c
   (ROADMAP « Les inputs personnalisés » : calculée au build à partir du plus
   grand besoin du projet — un jeu sans séquence ni tampon n'en paie pas). */
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
   de masques au build (ROADMAP « Les inputs personnalisés ») ; le runtime ne
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

/* Collision AABB — teste une paire de CollisionBox dans l'espace monde */
static inline int box_overlap(int ax, int ay, const CollisionBox*ba,
                               int bx, int by, const CollisionBox*bb) {
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

/* Rétrocompatibilité — teste sans récupérer les tags */
static inline int actors_overlap(const Actor*a, const Actor*b) {
    u8 _a=0,_b=0; return actors_overlap_boxes(a,b,&_a,&_b);
}

/* Tag */
static inline int actor_get_tag(const Actor* s) { return s->tag; }

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
static u32 _rand_seed = 73244475u;
static inline int math_rand(int lo, int hi) {
    _rand_seed = _rand_seed * 1664525u + 1013904223u;
    int range = hi - lo + 1;
    if (range <= 0) return lo;
    return lo + (int)((_rand_seed >> 16) % (u32)range);
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
        deg = hi;
    }
    if (x >= 0 && y >= 0) return deg;
    if (x <  0 && y >= 0) return 180 - deg;
    if (x <  0 && y <  0) return 180 + deg;
    return 360 - deg;
}

/* Juiciness — effets de feedback sur le sprite (self:squash, self:stretch,
   self:bounce, self:shake, self:flash, self:blink, self:pulse, self:pop,
   self:wobble). Chacun est une fonction PURE de (t, duration, amount) :
   aucun état caché, aucune coroutine (impossible sur GBA, cf.
   ARCHITECTURE.md) — c'est l'appelant qui fait avancer `t` d'une frame à
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

/* Envoi d'event à tous les actors actifs (G_ACTOR_COUNT défini dans runtime_api.h) */
/* La fn C cible (event_handler) est appelée si l'actor est actif. */
/* broadcast("on_receive", 42) → tous les on_receive reçoivent (0, 42) */
/* Implémenté comme macro pour éviter les pointeurs de fonction sur GBA. */
/* Usage codegen : broadcast(tag, value) — résolu statiquement dans main.c. */
/* Note : broadcast est résolu directement dans le codegen de chaque scène. */

/* (`tile_solid_at` a été retirée : elle répondait « il y a quelque chose ici »
   sans distinguer un bloc plein d'une pente, ce qui n'a plus de sens depuis que
   la résolution connaît la géométrie. Son dernier appelant était
   `actor_on_ground`, et aucune entrée de l'API Lua ne la citait. Un script qui
   veut inspecter la carte lit `collision_box.get_tile`.) */

/* Layers BG vivants — définis dans main.c via GBA_ENGINE_IMPL (gba_engine.h).
   `bg` = bg_slot 0-3 ; tx/ty en tuiles dans la map du layer. */

/* Windows — pochoirs par région d'écran (r : 0=WIN0, 1=WIN1, 2=fenêtre-objet,
   3=extérieur). Ne dessinent rien : autorisent ou non l'affichage. */

/* Texte — le texte vit sur LE layer d'UI de la scène (Scene.text_bg) : les
   glyphes sont chargés dans le charblock de ce layer, d'où l'absence de
   paramètre `layer`. tx/ty en tuiles. `n` = nombre de caractères révélés
   (machine à écrire) ; le rythme appartient au script. */
/* GRAMMAIRE : position ou conteneur d'abord, contenu ensuite — même ordre qu'en
   Lua (cf. api.py, section Texte). */
/* Rendu dans une zone dessinée dans le canvas de scène : elle porte position,
   largeur de coupe, alignement et police. Remplace `text_draw_box`, dont la
   géométrie vivait dans le script (donc invisible dans l'éditeur).

   ATTENTION — cette liste DOUBLE celle de `gba_engine.h` : les scènes et les
   actors sont des unités de compilation distinctes qui n'incluent pas le moteur.
   Une fonction déclarée là-bas et oubliée ici passe le checker, s'émet en C, et
   échoue au `make` sur un « implicit declaration » qui ne dit rien de la cause.
   `validate_project` compare donc les deux listes plutôt que de compter sur
   la vigilance. */
/* Groupe LECTURE — état d'un texte à tempo dans sa zone. */

/* Langue (ROADMAP v0.9, phase 4) — même découpe que text_set_font juste
   au-dessus : implémentation unique dans gba_engine.h (GBA_ENGINE_IMPL),
   redéclarée ici en `extern` pour les unités de compilation qui n'incluent
   pas le moteur. */

/* Images d'interface — un sprite à état posé sur la mise en page. Rien pour
   créer ni déplacer : la géométrie est authorée, seul l'ÉTAT est au script. */

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

/* ── Listes d'interface (ROADMAP v0.22) ───────────────────────────
   La NAVIGATION d'un menu, et rien d'autre : le moteur suit un index, le
   script écrit ce que chaque rangée affiche. `list.row(...)` rend la zone de
   texte d'une rangée, à passer à `text_draw_in` — un item est une ligne de
   donnée, pas un objet d'interface. */
/* La main, pas l'affichage : une liste inactive reste dessinée et garde son
   index. C'est ce qui permet un menu et son sous-menu à l'écran ensemble. */

/* Blending — `side` 0 = le dessus (ce qui est mélangé), 1 = le dessous (ce
   avec quoi, situé derrière). Modes : 0 aucun, 1 alpha, 2 vers le blanc,
   3 vers le noir. */

/* Palettes au runtime — remplace les seize couleurs d'une banque matérielle.
   Là où le mélange ci-dessus agit sur un CALQUE entier et seulement vers le
   blanc ou le noir, une banque ne concerne que les tuiles qui la citent : on
   peut refroidir un décor en gardant ses lanternes allumées. Les deux pools
   sont physiquement distincts, d'où deux fonctions. */

/* Sauvegarde — écrit ou relit les variables globales marquées persistantes
   dans l'emplacement `slot`. Rendent 0 si l'emplacement n'existe pas, et
   save_read 0 aussi si ce qui s'y trouve n'est pas relisible (marque, version
   ou somme de contrôle) : le jeu doit pouvoir distinguer « pas de partie » de
   « partie chargée » sans deviner. Lua appelle save_read `save.load` — cf.
   save_read_var juste dessous pour ce que `save.read` désigne côté Lua. */
/* save:read(slot, "nom") côté Lua (ROADMAP v0.22) : la valeur d'UNE variable
   persistante dans un emplacement, sans toucher aux globales de la partie en
   cours — contrairement à save_read ci-dessus. `idx` est un GLOBAL_*, résolu
   par le codegen depuis le nom littéral (contrairement à global.nom, résolu
   par accès pointé — chantier global/const). */
extern int save_read_var(int slot, int idx);


/* Fonctions texte HUD — définies dans main.c via GBA_ENGINE_IMPL (wrappers TTE) */
/* draw_printf / draw_clear retirés avec libtonc TTE — cf. gba_engine.h.
   Remplacements : text_draw (libellé, depuis la table) et text_draw_num
   (valeur). */

/* Y a-t-il un sol sous les pieds ?

   Lecture du drapeau posé par la résolution contre la carte de collision, et
   non un nouveau balayage : la résolution connaît les PENTES, un balayage de
   `tile_solid_at` répondrait « non » sur toute pente puisque celle-ci n'est
   solide que dans une partie de sa colonne.

   L'état est donc celui de la FIN de la frame précédente — la résolution
   s'exécute après les `on_update`. C'est le contrat normal d'un état de
   collision, et le seul possible : pendant `on_update`, l'acteur n'a pas encore
   fini de bouger. */
static inline int actor_on_ground(const Actor*a) { return a->collision.grounded; }

/* ── Inspecteur → API : ce que l'éditeur règle, le script le lit ────────────
   Lecture seule : ces deux drapeaux sont fixés au build (le C de rendu émis
   dépend d'eux), les écrire en jeu n'aurait aucun effet. */
static inline int actor_get_screen_space(const Actor* s) { return actor_oam_entry(s)->screen_space; }
/* « Affine transform » du OamEntry : vrai si un slot de matrice OAM a
   été réservé à ce sprite (affine_slot vaut -1 sinon). Rien de plus à stocker. */
static inline int actor_get_affine(const Actor* s)       { return actor_oam_entry(s)->affine_slot >= 0; }
static inline int actor_get_box_count(const Actor* s)    { return s->collision.box_count; }

/* ── Boîtes de collision — la référence `collision_box` ─────────────────────
   Une boîte est nommée par son tag (BOXTAG_*, le champ « Tag » du
   CollisionBoxComponent), et un script la tient dans une variable :
   `local hb = self:collision_box("hitbox")`. La référence est un ENTIER — le
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
static inline CollisionBox* _box_of(int h)    { return h ? &g_actors[(h-1)/MAX_BOXES].collision.boxes[(h-1)%MAX_BOXES] : 0; }
static inline Actor*        _box_owner(int h) { return &g_actors[(h-1)/MAX_BOXES]; }

static inline int collision_box_get_tag(int h)    { const CollisionBox* b = _box_of(h); return b ? b->tag : 0; }
static inline int collision_box_get_active(int h) { const CollisionBox* b = _box_of(h); return b ? b->active : 0; }
static inline void collision_box_set_active(int h, int on) {
    CollisionBox* b = _box_of(h);
    if (b) b->active = on ? 1 : 0;
}
static inline int collision_box_get_grounded(int h) { const CollisionBox* b = _box_of(h); return b ? b->grounded : 0; }
/* La carte de collision à un point MONDE. Le point ne dépend pas de la boîte : elle sert
   de porte d'entrée (une boîte absente répond 0, comme toute lecture d'une boîte absente). */
static inline int collision_box_get_collision_tile(int h, int x, int y) {
    return h ? collision_map_tile(x, y) : 0;
}
static inline int collision_box_get_solid(int h)  { const CollisionBox* b = _box_of(h); return b ? b->solid : 0; }
static inline void collision_box_set_solid(int h, int on) {
    CollisionBox* b = _box_of(h);
    if (b) b->solid = on ? 1 : 0;
}
static inline Vec2 collision_box_get_offset(int h) {
    const CollisionBox* b = _box_of(h);
    return b ? (Vec2){ b->x, b->y } : (Vec2){ 0, 0 };
}
static inline Vec2 collision_box_get_size(int h) {
    const CollisionBox* b = _box_of(h);
    return b ? (Vec2){ b->w, b->h } : (Vec2){ 0, 0 };
}
/* x/y tiennent dans un s8, w/h dans un u8 (cf. CollisionBox) : bornés ici, un
   script ne peut pas corrompre la boîte voisine par débordement. */
static inline void collision_box_set_offset(int h, Vec2 v) {
    CollisionBox* b = _box_of(h);
    if (!b) return;
    b->x = (s8)(v.x < -128 ? -128 : v.x > 127 ? 127 : v.x);
    b->y = (s8)(v.y < -128 ? -128 : v.y > 127 ? 127 : v.y);
}
static inline void collision_box_set_size(int h, Vec2 v) {
    CollisionBox* b = _box_of(h);
    if (!b) return;
    b->w = (u8)(v.x < 0 ? 0 : v.x > 255 ? 255 : v.x);
    b->h = (u8)(v.y < 0 ? 0 : v.y > 255 ? 255 : v.y);
}
/* Le rectangle MONDE, en pixels : position de l'acteur + décalage + taille. */
static inline Rect collision_box_get_bounds(int h) {
    const CollisionBox* b = _box_of(h);
    if (!b) return (Rect){ 0, 0, 0, 0 };
    const Actor* o = _box_owner(h);
    return (Rect){ (o->x>>8) + b->x, (o->y>>8) + b->y, b->w, b->h };
}
/* Deux boîtes se chevauchent-elles ? Une boîte inactive ne touche personne. */
static inline int collision_box_overlaps_box(int h, int other) {
    const CollisionBox* a = _box_of(h);
    const CollisionBox* b = _box_of(other);
    if (!a || !b || !a->active || !b->active) return 0;
    const Actor* oa = _box_owner(h);
    const Actor* ob = _box_owner(other);
    return box_overlap(oa->x>>8, oa->y>>8, a, ob->x>>8, ob->y>>8, b);
}
/* ... ou l'une des boîtes actives de cet acteur ? */
static inline int collision_box_overlaps_actor(int h, const Actor* other) {
    const CollisionBox* a = _box_of(h);
    if (!a || !a->active || !other) return 0;
    const Actor* oa = _box_owner(h);
    for (int j = 0; j < other->collision.box_count; j++)
        if (other->collision.boxes[j].active &&
            box_overlap(oa->x>>8, oa->y>>8, a, other->x>>8, other->y>>8, &other->collision.boxes[j]))
            return 1;
    return 0;
}

#endif /* RUNTIME_API_INLINE_H */
