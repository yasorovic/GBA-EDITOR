"""editor/codegen/oam_alloc.py — allocation des 128 entrées OAM, PAR SCÈNE.

Source de vérité UNIQUE pour « quelle entrée de `g_actors[]` occupe chaque
acteur posé et chaque instance de pool d'UNE scène », sur le modèle de
`palette_alloc.py` pour les 16 banques de palette. Résolu au BUILD, en Python :
le nombre d'acteurs d'une scène ne change pas en cours de partie.

Le fait matériel qui autorise ce fichier : **une seule scène est vivante à la
fois** sur GBA. Chaque `scene_init` réutilise donc la même fenêtre OAM en
repartant de l'entrée 0 — ses acteurs posés d'abord, puis les pools de prefabs
QU'ELLE déclare (`Scene.prefab_pools`), sans porter ceux des autres scènes.
`g_actors[]` est dimensionné sur la scène la plus gourmande (max, pas somme),
et la RAM est partagée entre scènes.

Avant ce module, la géométrie OAM était **éparpillée et recalculée en trois
endroits qui devaient rester d'accord sans se parler** : la boucle `pool_offset`
de `headers.generate_actor_types`, `_pool_info` de `main_gen`, et les décomptes
de `actor_budget`. `oam_alloc` est la géométrie ; ces trois-là en deviennent des
LECTEURS.

Deux unités à ne pas confondre, converties ici :

  - un pool se DÉCLARE en instances (`Scene.prefab_pools`) ;
  - un pool se PAIE en slots — instances × parties, un prefab à sous-arbre
    occupant un groupe contigu par instance (ROADMAP v0.23).

Le plafond est celui du matériel : l'OAM de la GBA compte 128 entrées. Il ne se
règle nulle part — ce n'est pas une préférence. Un acteur SANS sprite ne
consomme aucune entrée OAM ; le budget les compte quand même (un seul nombre
lisible vaut mieux que deux plafonds — cf. [[project_v17_scene_pool]]).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from codegen.c_names import sym as c_sym
from codegen.grit_conversion import count_frames
from core.models.components import displayed_sprite_component, sprite_components
from core.models.scene import Scene
from core.project import Project

# Les 128 entrées de l'OAM. Le seul plafond du fichier, et il vient du matériel.
# `actor_budget` (façade de l'inspecteur) le ré-exporte pour ne pas le dupliquer.
OAM_LIMIT = 128


def owner_appearances(project, owner) -> list[tuple]:
    """Les apparences RÉELLES d'un porteur (acteur, prefab, partie de prefab) :
    [(SpriteComponent, SpriteAsset)] dans l'ordre de ses composants, pour ceux
    dont le sprite existe et a une image. Un composant vide ou orphelin n'est pas
    une apparence — il n'a rien à afficher, donc rien à charger en VRAM."""
    out = []
    for c in sprite_components(owner):
        sprite = project.get_sprite(c.sprite_name) if c.sprite_name else None
        if sprite and sprite.asset:
            out.append((c, sprite))
    return out


def initial_appearance(project, owner) -> int:
    """Rang (dans `owner_appearances`) de l'apparence affichée au départ, ou -1 si
    aucun composant n'est actif : l'entrée existe alors, mais cachée."""
    shown = displayed_sprite_component(owner)
    for n, (c, _sprite) in enumerate(owner_appearances(project, owner)):
        if c is shown:
            return n
    return -1


def has_oam_entry(project, owner) -> bool:
    """Ce porteur peut-il afficher un sprite ? Seul un porteur d'AU MOINS UNE
    apparence occupe une entrée de `g_oam_entries[]` (marche 0b) : un contrôleur,
    un déclencheur ou un marqueur (point de tir, ancre de hitbox) n'en réserve
    aucune. Un porteur dont aucune apparence n'est active en réserve une, cachée
    (marche 3) : activer une apparence plus tard ne doit pas demander de slot.
    Le writer OAM et le budget lisent CE prédicat — jamais chacun le sien."""
    return bool(owner_appearances(project, owner))


def prefab_group(prefab) -> int:
    """Entrées de `g_actors` qu'occupe UNE instance : la racine plus ses
    parties. Un prefab plat vaut 1.

    C'est ICI que le calcul vit désormais : `main_gen` et `actor_budget`
    l'importent (ROADMAP v0.17, le pool par scène rapatrie sa géométrie ici)."""
    return 1 + len(getattr(prefab, "children", []) or [])


def scene_pool_instances(scene: Scene, prefab) -> int:
    """Ce que CETTE scène déclare pour ce prefab — 0 si elle ne le spawne pas.

    Le pool est per-scène depuis que la compilation l'est (ROADMAP v0.17,
    T1+T2+T3) : plus de `max` inter-scènes ni de repli sur `Prefab.max_instances`
    — chaque scène paie EXACTEMENT ce qu'elle déclare."""
    return int(scene.prefab_pools.get(getattr(prefab, "name", str(prefab)), 0) or 0)


def scene_actor_slots(scene: Scene) -> int:
    """Le poste « acteurs » : les entrées que la scène occupe pour ses acteurs
    posés ACTIFS.

    0 = automatique : le poste vaut le nombre d'acteurs réellement posés — les
    acteurs se comptent, ils ne se réservent pas (ROADMAP v0.17). Une valeur > 0
    est un OVERRIDE manuel, gardé pour plus tard ; aucune scène neuve ne le pose.

    « réellement posés » = ACTIFS : le build n'émet que les acteurs actifs
    (`rom_build`, `scene_actors`), donc c'est sur eux que repose la géométrie —
    et non sur `len(scene.actors)`, qui compterait un acteur désactivé auquel
    aucune entrée OAM n'est jamais assignée."""
    if scene.actor_slots > 0:
        return scene.actor_slots
    return sum(1 for a in scene.actors if getattr(a, "active", True))


def scene_ui_obj_slots(scene: Scene, project) -> int:
    """Entrées OAM que les OBJ d'INTERFACE de cette scène consomment — bandes de
    texte en cible OBJ, images d'UI, fonds de conteneur en sprites (ROADMAP
    v0.17, T4). Posé ENTRE les acteurs et les pools : le build réserve la bande
    OBJ juste après les acteurs, et `scene_oam_layout` fait donc démarrer les
    pools à `placed + ui`.

    Défensif : un projet à demi chargé (asset manquant) ne doit pas faire
    tomber le budget — 0 alors, le poste UI reste sûrement sous-compté plutôt
    que de lever."""
    try:
        return int(scene_obj_ui_slots(project, scene) or 0)
    except Exception:
        return 0


def layout_obj_budget_resolved(p: Project, lay) -> dict:
    """Le budget OBJ d'UNE mise en page, noms d'asset résolus.

    `layout_obj_budget` (modèle) ne résout ni les sprites ni la table de textes :
    c'est ici, qui les connaît, de fournir les frames, les tailles de frame et
    les glyphes animés — sous-réserver ferait écrire une image dans les tuiles de
    la suivante. Source unique lue par `gen_text.obj_text_alloc` (placement des zones) ET
    `scene_obj_ui_slots` (le pic OBJ d'une scène, ROADMAP v0.17 T4), pour que les
    deux comptent EXACTEMENT la même chose."""
    from core.models.ui_region import layout_obj_budget
    frames, sizes = {}, {}
    for im in lay.images:
        sprite = p.get_sprite(getattr(im, "sprite_name", "") or "")
        if sprite is not None and sprite.asset:
            frames[im.name] = count_frames(p, sprite)
            sizes[im.name] = (int(getattr(sprite, "frame_w", 0) or 0),
                              int(getattr(sprite, "frame_h", 0) or 0))
    return layout_obj_budget(lay, image_frames=frames, image_frame_size=sizes,
                             animated_by_name=p.layout_animated_glyphs(lay))


def scene_obj_ui_slots(p: Project, scene) -> int:
    """Slots OAM que l'interface en sprites de CETTE scène occupe — son pic
    (ROADMAP v0.17 T4). C'est le poste « UI » du budget OAM par scène
    (`oam_alloc.scene_ui_obj_slots`), et la largeur de la bande OBJ que
    `scene_init` réserve juste après les acteurs (ordre acteurs → UI → pools).

    Max sur les mises en page que la scène référence : une seule bande OBJ est
    active à la fois (base unique, `text_obj_set_base`), donc c'est la plus
    gourmande qui commande — exactement le `max` que le build calculait
    globalement avant, restreint à la scène. Les mises en page sont lues via leur
    ASSET brut (`bound.layout`), même résolution que `gen_text.obj_text_alloc`, pour que la
    largeur réservée et le placement des zones concordent au slot près."""
    peak = 0
    seen = set()
    for bound in p.scene_ui_layouts(scene):
        lay = getattr(bound, "layout", bound)
        if id(lay) in seen:
            continue
        seen.add(id(lay))
        peak = max(peak, layout_obj_budget_resolved(p, lay)["oam"])
    return peak


@dataclass
class PoolSlot:
    """La géométrie d'un pool de prefab dans UNE scène, repartant de la base
    0 de cette scène. `sym` est PRÉFIXÉ PAR LA SCÈNE (`<scène>_<prefab>`) :
    chaque scène compile ses propres unités de prefab contre SA géométrie
    (ROADMAP v0.17, T1), donc les symboles ne peuvent plus être project-wide.

    Deux espaces (marche 0b) : les ACTEURS de l'instance (racine + parties,
    contigus dans `g_actors[]`) et ses ENTRÉES OAM (les seules parties qui
    affichent un sprite, contiguës dans `g_oam_entries[]`)."""
    prefab: object
    prefab_sym: str    # symbole nu du prefab (c_sym du nom)
    sym: str           # symbole scène-préfixé : f"{scene_sym}_{prefab_sym}"
    start: int         # 1er ACTEUR du pool dans g_actors[]
    entry_start: int   # 1re ENTRÉE OAM du pool dans g_oam_entries[]
    instances: int
    group: int
    # Pour chaque membre du groupe (racine puis parties, dans l'ordre du spawn) :
    # son rang d'entrée DANS L'INSTANCE, ou -1 s'il n'affiche rien.
    member_entries: list[int]

    @property
    def size(self) -> int:
        """Acteurs réservés — instances × parties (ROADMAP v0.23)."""
        return self.instances * self.group

    @property
    def entries_per_instance(self) -> int:
        return sum(1 for r in self.member_entries if r >= 0)

    @property
    def entry_size(self) -> int:
        """Entrées OAM réservées : les seules parties qui affichent un sprite."""
        return self.instances * self.entries_per_instance


@dataclass
class OamLayout:
    """La géométrie de build d'UNE scène, base 0, en DEUX espaces :

      g_actors[]      = [acteurs actifs posés (placed)][pools : instances × parties]
      g_oam_entries[] = [entrées des posés à sprite][interface][entrées des pools]

    Lu par `headers` et `main_gen` ; la façade `actor_budget` le lit aussi pour
    l'inspecteur. Le poste est bâti sur `placed`, jamais sur l'override
    `Scene.actor_slots` (qui n'est qu'un indicateur de réservation)."""
    scene: Scene
    scene_sym: str
    placed: int              # acteurs actifs réellement posés
    placed_entry: list[int]  # par acteur posé : son entrée OAM, ou -1 (sans sprite)
    ui: int                  # OBJ d'interface
    pools: list[PoolSlot]

    @property
    def placed_entries(self) -> int:
        return sum(1 for e in self.placed_entry if e >= 0)

    @property
    def ui_start(self) -> int:
        """1re entrée OAM des OBJ d'interface : juste après les posés à sprite."""
        return self.placed_entries

    @property
    def pool_slots(self) -> int:
        """Acteurs que les pools réservent (g_actors[])."""
        return sum(pl.size for pl in self.pools)

    @property
    def pool_entries(self) -> int:
        """Entrées OAM que les pools réservent (g_oam_entries[])."""
        return sum(pl.entry_size for pl in self.pools)

    @property
    def used(self) -> int:
        """Empreinte OAM réelle de la scène — ce que `g_oam_entries` doit couvrir."""
        return self.placed_entries + self.ui + self.pool_entries

    @property
    def actors(self) -> int:
        """Acteurs vivants de la scène — ce que `g_actors` doit couvrir."""
        return self.placed + self.pool_slots

    @property
    def free(self) -> int:
        return OAM_LIMIT - self.used

    @property
    def over_budget(self) -> bool:
        return self.used > OAM_LIMIT

    def pool_for(self, prefab) -> Optional[PoolSlot]:
        """Le PoolSlot de ce prefab dans cette scène, ou None si non déclaré."""
        name = getattr(prefab, "name", str(prefab))
        pref = c_sym(name)
        return next((pl for pl in self.pools if pl.prefab_sym == pref), None)


def scene_oam_layout(project, scene: Scene) -> OamLayout:
    """Géométrie OAM déterministe d'une scène (base 0). Mêmes (project, scene)
    -> même layout : `headers` (TAG_/POOL_) et `main_gen` (spawn/pi/g_actors)
    restent cohérents sans se coordonner.

    Ordre des pools = ordre du catalogue `project.prefabs` (stable), pour que
    l'offset d'un pool ne dépende que de la scène, jamais de l'ordre d'appel."""
    scene_sym = c_sym(scene.name)
    posed = [a for a in scene.actors if getattr(a, "active", True)]
    placed_entry, rank = [], 0
    for a in posed:
        if has_oam_entry(project, a):
            placed_entry.append(rank)
            rank += 1
        else:
            placed_entry.append(-1)
    placed = len(posed)
    ui = scene_ui_obj_slots(scene, project)

    pools: list[PoolSlot] = []
    actor_off = placed                 # espace des acteurs
    entry_off = rank + ui              # espace OAM : après les posés et l'interface
    for pf in project.prefabs:
        n = scene_pool_instances(scene, pf)
        if n <= 0:
            continue
        pref = c_sym(pf.name)
        members = [pf] + list(getattr(pf, "children", []) or [])
        ranks, r = [], 0
        for m in members:
            if has_oam_entry(project, m):
                ranks.append(r)
                r += 1
            else:
                ranks.append(-1)
        pl = PoolSlot(
            prefab=pf, prefab_sym=pref, sym=f"{scene_sym}_{pref}",
            start=actor_off, entry_start=entry_off, instances=n,
            group=prefab_group(pf), member_entries=ranks,
        )
        pools.append(pl)
        actor_off += pl.size
        entry_off += pl.entry_size

    return OamLayout(scene=scene, scene_sym=scene_sym, placed=placed,
                     placed_entry=placed_entry, ui=ui, pools=pools)


def project_oam_entry_count(project) -> int:
    """Taille de `g_oam_entries[]` : la scène la plus gourmande (MAX, pas somme).

    Une seule scène est vivante à la fois et chaque `scene_init` repart de la
    base 0 : dimensionner sur le max suffit, la somme des unions faisait payer à
    la scène de menu les slots des balles du niveau d'action (ROADMAP v0.17).
    Plancher à 1 — un `OamEntry g_oam_entries[0]` ne compile pas."""
    return max((scene_oam_layout(project, sc).used for sc in project.scenes),
               default=0) or 1


def project_actor_count(project) -> int:
    """Taille de `g_actors[]`, même règle (MAX des scènes, plancher à 1) mais
    sur les seuls ACTEURS : les OBJ d'interface occupent `g_oam_entries[]`, pas
    `g_actors[]` (marche 0b de « La struct Actor allégée »)."""
    return max((scene_oam_layout(project, sc).actors for sc in project.scenes),
               default=0) or 1
