"""Émission du Character solver : carte de collision, murs et pentes."""
from __future__ import annotations

from codegen.runtime_codegen.physics.oneway import oneway_common_lines




def _one_way_scan_lines() -> list[str]:
    """La recherche d'une face à sens unique dans la carte : la condition partagée, puis `oneway_hit`."""
    return [
        *oneway_common_lines(),
        "/* One-way faces. `dir` is the NORMAL of the face: 1 up, 2 down, 3 left, 4 right.",
        "   A face is a line, at the top (up, left) or at the far edge (down, right) of",
        "   its tile. [lo,hi] is the range of coordinates the box edge swept this frame",
        "   along that axis, [c0,c1] the span of the box on the other axis. Returns the",
        "   coordinate of the first face met in the direction of travel, -1 if none.",
        "   The caller decides WHETHER the move crosses against the normal; this only",
        "   finds the face. */",
        "/* Toujours inlinée : `dir` est une constante à chaque appel, la direction se replie à la compilation. Une",
        "   rangée (face verticale) ou une colonne (face horizontale) que `g_ow_rows` / `g_ow_cols` déclarent sans",
        "   face de ce sens n'est pas lue. */",
        "static inline __attribute__((always_inline)) int oneway_hit(int dir,int lo,int hi,int c0,int c1){",
        "    if(!(g_ow_any&(1u<<dir))||lo>hi) return -1;",
        "    int vert=dir<=2, off=(dir==2||dir==4)?TILE_SIZE:0;",
        "    int t0=(lo-off+TILE_SIZE-1)>>3, t1=(hi-off)>>3;",
        "    int n=vert?g_cmap_h:g_cmap_w;",
        "    if(t0<0) t0=0;",
        "    if(t1>=n) t1=n-1;",
        "    const u8* tab=vert?g_ow_rows:g_ow_cols;",
        "    int asc=(dir&1), eo=asc?lo:hi;   /* the edge BEFORE the move: the swept range starts there */",
        "    for(int i=0;i<=t1-t0;i++){",
        "        int t=asc?t0+i:t1-i;",
        "        if(tab&&!(tab[t]&(1u<<dir))) continue;",
        "        /* Seule une ligne qui peut porter une face arrive ici : les colonnes ne sont bornées qu'à ce moment. */",
        "        if(!g_active_cmap) return -1;",
        "        int k0=c0>>3, k1=c1>>3, m=vert?g_cmap_w:g_cmap_h;",
        "        if(k0<0) k0=0;",
        "        if(k1>=m) k1=m-1;",
        "        int ks=vert?1:g_cmap_w, ts=vert?g_cmap_w:1;",
        "        const u8* q=g_active_cmap+t*ts+k0*ks;",
        "        for(int k=k0;k<=k1;k++,q+=ks)",
        "            if(g_tile_oneway[*q]==dir&&oneway_open(dir,eo,t*TILE_SIZE+off)) return t*TILE_SIZE+off;",
        "    }",
        "    return -1;",
        "}",
    ]


def _one_way_x_lines(dirs) -> list[str]:
    """Résolution horizontale des faces gauche (3) et droite (4) présentes dans les cartes, dans la boucle des boîtes."""
    L = ["        /* ── X: one-way faces. Stops only a box that was entirely on the",
         "           open side of the face LAST frame and crosses it this frame. ── */"]
    if 3 in dirs:
        L += ["        if(!drop&&a->vx>0){",
              "            int f=oneway_hit(3,a->collision.last_x+(int)b->x+(int)b->w,_px+(int)b->x+(int)b->w,_oy+(int)b->y,_oy+(int)b->y+(int)b->h-1);",
              "            if(f>=0){_px=f-(int)b->x-(int)b->w; a->vx=0; hr=1; if(cb)cb(a,1,0);}",
              "        }"]
    if 4 in dirs:
        L += ["        if(!drop&&a->vx<0){",
              "            int f=oneway_hit(4,_px+(int)b->x,a->collision.last_x+(int)b->x,_oy+(int)b->y,_oy+(int)b->y+(int)b->h-1);",
              "            if(f>=0){_px=f-(int)b->x; a->vx=0; hl=1; if(cb)cb(a,-1,0);}",
              "        }"]
    return L


def _one_way_y_lines(dirs) -> list[str]:
    """Résolution verticale des faces haut (1) et bas (2) présentes dans les cartes, après la carte."""
    L = ["        /* ── Y: one-way faces, after the map has had its say ── */",
         "        left=_px+(int)b->x; right=left+(int)b->w-1;"]
    if 1 in dirs:
        L += ["        if(!drop&&_py>=_oy){",
              "            int f=oneway_hit(1,_oy+(int)b->y+(int)b->h,_py+(int)b->y+(int)b->h,left,right);",
              "            if(f>=0){_py=f-(int)b->y-(int)b->h; if(a->vy>0) a->vy=0; hb=1; if(cb)cb(a,0,1);}",
              "        }"]
    if 2 in dirs:
        L += ["        if(!drop&&_py<=_oy){",
              "            int f=oneway_hit(2,_py+(int)b->y,_oy+(int)b->y,left,right);",
              "            if(f>=0){_py=f-(int)b->y; if(a->vy<0) a->vy=0; ht=1; if(cb)cb(a,0,-1);}",
              "        }"]
    return L


def character_solver_lines(one_way_tiles=frozenset()) -> list[str]:
    """Lecture de la carte de collision, et résolution d'un acteur contre elle.

    `one_way_tiles` : les sens (1 haut, 2 bas, 3 gauche, 4 droite) des tuiles à sens unique que les cartes du projet
    contiennent, ou `True` pour tous. Une passe n'est émise que pour un sens présent : chacune coûte à chaque boîte et à
    chaque frame, même quand la carte ne contient aucune face de ce sens.

    La table de profils est ÉMISE depuis `core.models.collision_tiles`, la même
    géométrie que celle dont le canvas tire ses polygones : la physique du jeu
    et le dessin de l'éditeur ne peuvent pas diverger."""
    dirs = {1, 2, 3, 4} if one_way_tiles is True else set(one_way_tiles or ())
    from core.models.collision_tiles import (
        TILE_COUNT, kind_of, column_surfaces, speed_scale, oneway_dir,
    )
    L = [
        *(["extern u8 *g_drop_through;"] if dirs else []),
        "/* Côté du contact qui porte, pour la scène : 1 bas, 2 haut, 3 droite, 4 gauche (la normale de la surface qui",
        "   porte est l'opposé). `grounded` est le contact de CE côté, pas forcément celui du bas. */",
        "static u8 g_support_normal=1;",
        "static const u8 *g_active_cmap = NULL;",
        "static int g_cmap_w = 0, g_cmap_h = 0;",
        "/* Faces à sens unique de la carte active : `g_ow_any` a le bit `1<<sens` des sens présents, `g_ow_rows` et",
        "   `g_ow_cols` le même masque par rangée et par colonne (NULL : pas de table, on lit la carte). Posés à",
        "   l'entrée de scène ; par défaut tout est à lire. */",
        "static u8 g_ow_any = 0x1E;",
        "static const u8 *g_ow_rows = NULL, *g_ow_cols = NULL;",
        "#define TILE_SIZE 8",
        "",
        "/* Tile type profile — EMITTED from core/models/collision_tiles.py,",
        "   never written by hand here: it is the same geometry as the one",
        "   the editor draws. `surface` carries the ordinate of the surface in",
        "   each of the 8 pixel columns; for a FLOOR the material goes from there to "
        "the",
        "   bottom of the tile (8 = empty column), for a CEILING from the top down to"
        " there",
        "   (0 = empty column). */",
        "#define TK_EMPTY 0",
        "#define TK_SOLID 1",
        "#define TK_FLOOR 2",
        "#define TK_CEIL  3",
        "#define TK_ONEWAY 4",
    ]
    kinds = ", ".join(str(kind_of(t)) for t in range(TILE_COUNT))
    L.append(f"static const u8 g_tile_kind[{TILE_COUNT}] = {{ {kinds} }};")
    # Cosinus de la pente en virgule fixe 8 bits — 256 à plat. Un pas horizontal
    # sur une pente parcourt √(1+p²) fois plus de distance qu'à plat ; c'est ce
    # facteur qui le ramène à la distance demandée. Précalculé ici : pas de
    # racine carrée à l'exécution, et la table est la même géométrie que le reste.
    # u16 et non u8 : « plat » vaut 256, qui ne tient pas dans un octet.
    scales = ", ".join(str(speed_scale(t)) for t in range(TILE_COUNT))
    L.append(f"static const u16 g_tile_scale[{TILE_COUNT}] = {{ {scales} }};")
    # Sens de la face d'une tuile à sens unique : 0 aucune, 1 haut, 2 bas,
    # 3 gauche, 4 droite. Émis comme le reste depuis `collision_tiles.py`.
    oneway = ", ".join(str(oneway_dir(t)) for t in range(TILE_COUNT))
    L.append(f"static const u8 g_tile_oneway[{TILE_COUNT}] = {{ {oneway} }};")
    L.append(f"static const u8 g_tile_surface[{TILE_COUNT}][TILE_SIZE] = {{")
    for t in range(TILE_COUNT):
        row = ", ".join(f"{v}" for v in column_surfaces(t))
        L.append(f"    {{ {row} }},")
    L += [
        "};",
        "",
        "int collision_map_tile(int px,int py){",
        "    if(!g_active_cmap) return 0;",
        "    int tx=px/TILE_SIZE, ty=py/TILE_SIZE;",
        "    if(tx<0||ty<0||tx>=g_cmap_w||ty>=g_cmap_h) return 0;",
        "    return (int)g_active_cmap[ty*g_cmap_w+tx];",
        "}",
        "/* The only type that PUSHES horizontally. A slope is not a wall,",
        "   otherwise nobody could climb it: one goes up through the surface. */",
        "static int tile_wall_at(int px,int py){",
        "    if(!g_active_cmap) return 0;",
        "    int tx=px/TILE_SIZE, ty=py/TILE_SIZE;",
        "    if(tx<0||ty<0||tx>=g_cmap_w||ty>=g_cmap_h) return 1;",
        "    return g_active_cmap[ty*g_cmap_w+tx]==TK_SOLID;",
        "}",
        "/* World ordinate of the TOP of the material carrying column px.",
        "",
        "   Three tiles swept from top to bottom, the FIRST one found winning: the "
        "one",
        "   above the feet, the one at the feet, the one below. The tile ABOVE",
        "   is essential — on a slope, the material of the next column lives",
        "   in the tile above, and stopping at the feet makes the actor drop off",
        "   in the middle of the climb. A surface higher than the box is discarded "
        "(`>=top`):",
        "   it does not touch the actor, and lifting it there would teleport it onto "
        "a",
        "   platform it was passing under.",
        "",
        "   Off the map at the bottom = solid: the world is a closed box, as before",
        "   the resolution knew about slopes. Without it an actor that misses a",
        "   platform falls forever — and its sprite wraps around to the top of the "
        "screen,",
        "   since the OAM only encodes Y on 8 bits. -1 = nothing in range. */",
        "/* Type of the tile that provided the last surface returned by",
        "   tile_floor_at — it is the one carrying the actor, hence the one that says",
        "   which slope it is walking on. Returned on the side rather than as a "
        "return value:",
        "   a single caller uses it, and the sweep is not done twice. */",
        "static u8 g_floor_tile = 0;",
        "static int tile_floor_at(int px,int top,int bot){",
        "    g_floor_tile=0;",
        "    if(!g_active_cmap) return -1;",
        "    int tx=px/TILE_SIZE;",
        "    if(tx<0||tx>=g_cmap_w) return -1;",
        "    for(int i=-1;i<2;i++){",
        "        int ty=bot/TILE_SIZE+i;",
        "        if(ty<0) continue;",
        "        if(ty>=g_cmap_h) return g_cmap_h*TILE_SIZE;",
        "        int t=g_active_cmap[ty*g_cmap_w+tx];",
        "        if(t==TK_SOLID){ if(ty*TILE_SIZE>=top){g_floor_tile=(u8)t; return ty*TILE_SIZE;} continue; }",
        "        if(g_tile_kind[t]==TK_FLOOR){",
        "            int s=g_tile_surface[t][px&(TILE_SIZE-1)];",
        "            if(s<TILE_SIZE && ty*TILE_SIZE+s>=top){g_floor_tile=(u8)t; return ty*TILE_SIZE+s;}",
        "        }",
        "    }",
        "    return -1;",
        "}",
        "/* Symmetric: ordinate of the BOTTOM of the material above the head.",
        "   The sweep starts at the head and goes UP — never downward, otherwise the "
        "floor",
        "   the actor rests on would be taken for a ceiling and would push it",
        "   into it. Off the map at the top = solid, same closed box. */",
        "static int tile_ceil_at(int px,int py){",
        "    if(!g_active_cmap) return -1;",
        "    int tx=px/TILE_SIZE;",
        "    if(tx<0||tx>=g_cmap_w) return -1;",
        "    for(int i=0;i<2;i++){",
        "        int ty=py/TILE_SIZE-i;",
        "        if(ty>=g_cmap_h) continue;",
        "        if(ty<0) return 0;",
        "        int t=g_active_cmap[ty*g_cmap_w+tx];",
        "        if(t==TK_SOLID) return ty*TILE_SIZE+TILE_SIZE;",
        "        if(g_tile_kind[t]==TK_CEIL){",
        "            int s=g_tile_surface[t][px&(TILE_SIZE-1)];",
        "            if(s>0) return ty*TILE_SIZE+s;",
        "        }",
        "    }",
        "    return -1;",
        "}",
        *(_one_way_scan_lines() if dirs else []),
        "typedef void (*TileCollideCb)(Actor*,int,int);",
        "/* Resolution of an actor against the map.",
        "   The order is the rule: X first — slopes do not obstruct it —",
        "   then Y, where the surface is searched at THREE points (the two bottom "
        "corners",
        "   and the centre), the highest one winning: a wide actor does not sink",
        "   into the slope and clears an edge cleanly.",
        "   `cb` only WARNS: the velocity is cancelled in every case,",
        "   so writing the hook does not disable the physics.",
        "   The map only resolves a VELOCITY: an actor with vx == vy == 0 has not",
        "   been driven this frame, so it is left alone. That is what makes",
        "   `self.position` a teleport that ignores the map (no wall stop, no",
        "   climbing back onto a slope) and `body.velocity` the physical move. `grounded`",
        "   keeps its value: a resting actor is still resting. */",
        "static void __attribute__((unused)) resolve_actor_tiles(Actor*a,u8 body_mask,TileCollideCb cb){",
        "    if(!g_active_cmap) return;",
        "    if(!body_mask) return;",
        *(["    int drop=g_drop_through&&g_drop_through[a->inst];"] if dirs else []),
        "    if(a->vx==0&&a->vy==0){",
        "        a->collision.last_x=a->x>>8; a->collision.slope_acc=0;",
        "        return;",
        "    }",
        "    debug_physics_character_test();",
        "    /* the Actor's x/y are in Q8 (256 = 1 px), but ALL the",
        "       geometry below (tiles, boxes, slopes) is in pixels, unchanged",
        "       since v0.6.3 — rounding is done ONCE on entry (_px/_py) and",
        "       ONCE on exit. _fx/_fy carry the sub-pixel through the",
        "       function: a frame without collision on an axis gives it back EXACTLY",
        "       its input Q8 position (x == (x>>8)<<8 | x&255, two's",
        "       complement arithmetic); a frame that clamps (wall, floor, ceiling) "
        "re-emits the",
        "       fraction from BEFORE the clamp — a deliberate approximation rather "
        "than a",
        "       reset per branch, whose gain would be imperceptible here. */",
        "    int _px=a->x>>8, _py=a->y>>8, _fx=a->x&255, _fy=a->y&255;",
        "    /* Height BEFORE this frame's vertical move: apply_velocity moves x AND y",
        "       at once, so the X pass below would otherwise see a landing actor",
        "       already sunk into the floor (or into a ceiling), read that floor as a",
        "       WALL and push the actor sideways — into a neighbouring wall. Each axis",
        "       is resolved from where the other one was. */",
        "    int _oy=(a->y-a->vy)>>8;",
        "    int was_grounded=a->collision.grounded, dx=_px-a->collision.last_x;",
        "    int moved=dx<0?-dx:dx;",
        "    /* ── Constant speed ALONG the ground ─────────────────────",
        "       A horizontal step on a slope covers √(1+p²) times more",
        "       distance than on the flat: 114 % at 26°, 141 % at 45°, 224 % at 63°. "
        "Without",
        "       correction, the steeper the slope the faster the character",
        "       seems. So the step is brought back to the cosine of the slope it",
        "       climbs, read in g_tile_scale.",
        "",
        "       Two safeguards, because the engine UNDOES here a child of what",
        "       the script asked for:",
        "         - it must be on the ground on the previous frame — a jump, a",
        "           fall or a flight is not a walk;",
        "         - the step must fit in a tile. Beyond that, the resolution",
        "           already claims nothing (the probe only reaches one tile), and",
        "           that is where a script teleports rather than walks.",
        "       The remainder (1/256 of a pixel) is CARRIED OVER: without it, a 2 px "
        "step",
        "       at 45° would always land on 1 px, and the character would crawl",
        "       instead of going 1.41 times slower. */",
        "    if(was_grounded && dx && moved<=TILE_SIZE){",
        "        for(int i=0;i<a->collision.box_count;i++){",
        "            CollisionShape*b=&a->collision.boxes[i];",
        "            if(!(body_mask&(1u<<i))||!b->solid||!b->active) continue;",
        "            int l=a->collision.last_x+(int)b->x, r=l+(int)b->w-1;",
        "            int t=_py+(int)b->y;",
        "            tile_floor_at((l+r)>>1, t, t+(int)b->h-1);",
        "            int sc=g_tile_scale[g_floor_tile];",
        "            if(sc<256){",
        "                int want=dx*sc+a->collision.slope_acc;",
        "                int step=want/256;",
        "                a->collision.slope_acc=want-step*256;",
        "                _px=a->collision.last_x+step;",
        "            }",
        "            break;",
        "        }",
        "    }else a->collision.slope_acc=0;",
        "    a->collision.grounded=0;",
        "    for(int i=0;i<a->collision.box_count;i++) a->collision.boxes[i].grounded=0;",
        "    for(int i=0;i<a->collision.box_count;i++){",
        "        CollisionShape*b=&a->collision.boxes[i];",
        "        if(!(body_mask&(1u<<i))||!b->solid||!b->active) continue;",
        "        int left,right,top,bot;",
        "        int hb=0,ht=0,hl=0,hr=0;   /* contacts de cette boîte : bas, haut, gauche, droite */",
        "        /* ── X: only solid blocks push ───────────── */",
        "        if(a->vx!=0){",
        "            left=_px+(int)b->x; right=left+(int)b->w-1;",
        "            top =_oy+(int)b->y; bot  =top +(int)b->h-1;",
        "            int hit=0;",
        "            if(a->vx>0){",
        "                for(int cpy=top;cpy<=bot&&!hit;cpy+=TILE_SIZE) hit=tile_wall_at(right,cpy);",
        "                if(!hit) hit=tile_wall_at(right,bot);",
        "                if(hit){_px=(right/TILE_SIZE)*TILE_SIZE-(int)b->x-(int)b->w;",
        "                    a->vx=0; hr=1; if(cb)cb(a,1,0);}",
        "            }else{",
        "                for(int cpy=top;cpy<=bot&&!hit;cpy+=TILE_SIZE) hit=tile_wall_at(left,cpy);",
        "                if(!hit) hit=tile_wall_at(left,bot);",
        "                if(hit){_px=(left/TILE_SIZE+1)*TILE_SIZE-(int)b->x;",
        "                    a->vx=0; hl=1; if(cb)cb(a,-1,0);}",
        "            }",
        "        }",
        *(_one_way_x_lines(dirs) if dirs & {3, 4} else []),
        "        /* ── Ceiling: the LOWEST surface stops the head ─ */",
        "        left=_px+(int)b->x; right=left+(int)b->w-1;",
        "        top =_py+(int)b->y; bot  =top +(int)b->h-1;",
        "        if(a->vy<0){",
        "            int c=-1;",
        "            for(int k=0;k<3;k++){",
        "                int cpx=(k==0)?left:((k==1)?((left+right)>>1):right);",
        "                int cy=tile_ceil_at(cpx,top);",
        "                if(cy>c) c=cy;",
        "            }",
        "            if(c>=0&&top<c){_py=c-(int)b->y; a->vy=0; ht=1; if(cb)cb(a,0,-1);}",
        "        }",
        "        /* ── Floor: the HIGHEST surface carries the actor ───── */",
        "        top=_py+(int)b->y; bot=top+(int)b->h-1;",
        "        int g=-1;",
        "        for(int k=0;k<3;k++){",
        "            int cpx=(k==0)?left:((k==1)?((left+right)>>1):right);",
        "            int gy=tile_floor_at(cpx,top,bot);",
        "            if(gy>=0&&(g<0||gy<g)) g=gy;",
        "        }",
        "        if(g>=0){",
        "            int feet=bot+1;",
        "            if(feet>g){",
        "                /* Penetration: we climb back onto the surface. No walking",
        "                   ceiling — the author painted a slope, we climb it. */",
        "                _py=g-(int)b->y-(int)b->h;",
        "                if(a->vy>0) a->vy=0;",
        "                hb=1; if(cb)cb(a,0,1);",
        "            }else if(feet==g){",
        "                /* Right on the surface: on the ground, and a downward",
        "                   velocity makes no sense any more — without this it "
        "survives one more",
        "                   frame and the actor crosses the floor again before being",
        "                   pushed back. */",
        "                if(a->vy>0) a->vy=0;",
        "                hb=1;",
        "            }else if(was_grounded&&a->vy>=0&&g-feet<=moved*2+1){",
        "                /* Sticking on the way down: the maximum gap that a 63°",
        "                   slope can open for this movement. Without it, every",
        "                   descent takes off and falls back, hence jitters. */",
        "                _py=g-(int)b->y-(int)b->h;",
        "                hb=1;",
        "            }",
        "        }",
        *(_one_way_y_lines(dirs) if dirs & {1, 2} else []),
        "        /* `grounded` : le contact du côté qui porte (bas sous la gravité habituelle). */",
        "        if(g_support_normal==1?hb:g_support_normal==2?ht:g_support_normal==3?hr:hl) a->collision.grounded=b->grounded=1;",
        "    }",
        "    a->collision.last_x=_px;",
        "    a->x=(_px<<8)|_fx; a->y=(_py<<8)|_fy;",
        "}",
        "",
    ]
    return L
