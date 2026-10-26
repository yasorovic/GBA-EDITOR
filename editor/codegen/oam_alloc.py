"""editor/codegen/oam_alloc.py — la géométrie des acteurs d'une scène, PAR SCÈNE.

Source de vérité UNIQUE pour « quel emplacement de `g_actors[]` occupe chaque
acteur posé et chaque instance de pool d'UNE scène », et « quelle entrée d'ÉTAT
d'affichage (`g_oam_entries[]`) porte chacun », sur le modèle de `palette_alloc.py`
pour les 16 banques de palette. Résolu au BUILD, en Python : le nombre d'acteurs
d'une scène ne change pas en cours de partie.

Deux choses que ce fichier NE confond plus : l'ÉTAT d'affichage d'un acteur
(`g_oam_entries[e]` : frame, flips, palette… ; une entrée par acteur à sprite, sans
plafond) et l'EMPLACEMENT matériel qu'il occupe dans les 128 de l'OAM, que le tick
attribue à la frame, dans l'ordre, aux seuls sprites actifs, visibles et à l'écran
(cf. `gen_affine.oam_window_open`). La bande d'interface, elle, tient les `ui`
premiers emplacements, fixes.

Le fait matériel qui autorise ce fichier : **une seule scène est vivante à la
fois** sur GBA. Chaque `scene_init` repart donc de zéro — ses acteurs posés d'abord, puis le pool partagé
des acteurs qui naissent dans CETTE scène, sans porter ceux des autres scènes.
`g_actors[]` est dimensionné sur la scène la plus gourmande (max, pas somme),
et la RAM est partagée entre scènes.

Avant ce module, la géométrie OAM était **éparpillée et recalculée en trois
endroits qui devaient rester d'accord sans se parler** : la boucle `pool_offset`
de `headers.generate_actor_types`, `_pool_info` de `main_gen`, et les décomptes
de `actor_budget` (disparu depuis). `oam_alloc` est la géométrie ; `headers` et
`main_gen` en sont des LECTEURS.

Deux unités à ne pas confondre, converties ici :

  - les acteurs posés et le pool partagé : un prefab que les scripts de la scène spawnent naît dans le pool, qui
    n'a pas de taille à régler (`OBJECT_CAPACITY` moins les posés) ;
  - un pool se PAIE en slots — un prefab à sous-arbre occupant un groupe contigu par instance.

Le plafond est celui du matériel : l'OAM de la GBA compte 128 entrées, mais il ne borne que les
sprites affichés ENSEMBLE, pas ceux qui existent. Il ne se règle nulle part — ce n'est pas une
préférence. Un acteur SANS sprite n'a aucune entrée d'état (cf. [[project_v17_scene_pool]]).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from codegen.actor_appearance import has_oam_entry
from codegen.c_names import sym as c_sym
from codegen.pool_model import model_members, prefab_group
from codegen.ui_obj_budget import scene_ui_obj_slots
from core.models.scene import Scene

# Les 128 entrées de l'OAM. Le seul plafond du fichier, et il vient du matériel.
OAM_LIMIT = 128

# Le nombre d'acteurs qu'une scène peut contenir EN TOUT : les acteurs posés, puis tout ce qui naît en
# cours de partie. Un seul pool, partagé par tous les modèles, dont la taille est ce qui reste. La valeur
# est une décision du build, pas de l'auteur, et elle est bornée par le CPU, pas par la RAM : mesuré,
# environ 300 instances scriptées et animées tiennent dans une image, et seuls 128 sprites s'affichent à
# la fois. À 256 emplacements le pool prend environ 30 Ko d'EWRAM sur 256 Ko ; la RAM n'est donc pas ce qui
# limite, et le build se contente de CONTRÔLER après le lien qu'il reste `rom_report.EWRAM_MARGIN` de marge.
# Elle vit ICI, en un seul endroit (`scene_object_capacity`).
OBJECT_CAPACITY = 256


def scene_object_capacity(project, scene: Scene) -> int:
    """Les emplacements d'acteurs de cette scène, posés compris."""
    return OBJECT_CAPACITY

def scene_has_model(project, scene: Scene, prefab) -> bool:
    """Ce prefab a-t-il un modèle dans CETTE scène : il y naît (un script le spawne), ou des acteurs
    posés en sont des instances ? Per-scène : chaque scène paie EXACTEMENT son layout."""
    return scene_oam_layout(project, scene).pool_for(prefab) is not None


def project_has_model(project, prefab) -> bool:
    """Au moins une scène a un modèle de ce prefab. Ne sert qu'aux décomptes encore PROJET-WIDE : le build
    émet les tuiles d'un sprite de prefab dès qu'une scène le fait naître. La géométrie OAM, elle, est
    per-scène (`scene_oam_layout`)."""
    return any(scene_has_model(project, s, prefab) for s in project.scenes)



@dataclass
class PoolSlot:
    """Un modèle de prefab dans UNE scène. `sym` est PRÉFIXÉ PAR LA SCÈNE (`<scène>_<prefab>`) : chaque scène
    compile ses propres unités de prefab contre SA géométrie, donc les symboles ne peuvent plus être project-wide.

    Deux espaces : les ACTEURS de l'instance (racine + parties, contigus dans `g_actors[]`) et ses ENTRÉES d'état
    d'affichage (une par emplacement du pool partagé)."""
    prefab: object
    prefab_sym: str    # symbole nu du prefab (c_sym du nom)
    sym: str           # symbole scène-préfixé : f"{scene_sym}_{prefab_sym}"
    group: int
    # Pour chaque membre du groupe (racine puis parties, dans l'ordre du spawn) :
    # son rang d'entrée DANS L'INSTANCE, ou -1 s'il n'affiche rien.
    member_entries: list[int]
    # Les acteurs POSÉS qui sont des instances de ce modèle (indices parmi les acteurs actifs de la
    # scène, cf. `model_members`) : leurs emplacements et leurs entrées sont ceux de la scène.
    members: list[int] = field(default_factory=list)
    # Un modèle que la scène fait naître prend n'importe quel emplacement libre du pool partagé
    # (`OamLayout.shared`) et se reconnaît à `Actor.model`. Un modèle sans spawn n'a que ses instances posées.
    shared: bool = False
    # L'identité du modèle dans le pool partagé (1..), ou 0 s'il n'y naît pas. Un modèle à parties prend
    # `group` identités consécutives : la racine porte `model_id`, sa partie k porte `model_id + k`
    # (cf. `Actor.model`, qui dit AUSSI quelle partie un emplacement occupe).
    model_id: int = 0

    @property
    def entries_per_instance(self) -> int:
        return sum(1 for r in self.member_entries if r >= 0)


@dataclass
class SharedPool:
    """Le pool partagé d'une scène : les emplacements d'acteurs qui restent après les posés et les réserves
    à part, pris par n'importe quel modèle simple qui naît. `entries` états d'affichage (un par emplacement),
    ou 0 si aucun de ces modèles n'affiche rien."""
    start: int
    size: int
    entry_start: int
    entries: int
    models: list      # list[PoolSlot], dans l'ordre du catalogue ; `model_id` = rang + 1

    @property
    def end(self) -> int:
        return self.start + self.size


def shared_kinds(shared: Optional[SharedPool]) -> int:
    """Combien de TYPES d'emplacement le pool partagé distingue (`Actor.model` va de 1 à ce nombre) : un par
    modèle plat, et pour un modèle à parties une racine plus une par partie."""
    return sum(m.group for m in shared.models) if shared else 0


@dataclass
class OamLayout:
    """La géométrie de build d'UNE scène, base 0, en DEUX espaces :

      g_actors[]      = [acteurs actifs posés (placed)][pool partagé]
      g_oam_entries[] = [états des posés à sprite][états du pool partagé]

    L'interface n'a pas d'état d'acteur : elle tient les `ui` premiers EMPLACEMENTS de l'OAM
    matérielle, fixes ; les sprites d'acteurs prennent les suivants, à la frame.

    Lu par `headers` et `main_gen`, bâti sur `placed`."""
    scene: Scene
    scene_sym: str
    placed: int              # acteurs actifs réellement posés
    placed_entry: list[int]  # par acteur posé : son entrée d'état, ou -1 (sans sprite)
    ui: int                  # emplacements OBJ d'interface, au début de l'OAM
    pools: list[PoolSlot]
    shared: Optional[SharedPool] = None
    capacity: int = OBJECT_CAPACITY

    @property
    def placed_entries(self) -> int:
        return sum(1 for e in self.placed_entry if e >= 0)

    @property
    def pool_slots(self) -> int:
        """Acteurs que le pool partagé réserve (g_actors[])."""
        return self.shared.size if self.shared else 0

    @property
    def pool_entries(self) -> int:
        """Entrées d'état du pool partagé (g_oam_entries[])."""
        return self.shared.entries if self.shared else 0

    @property
    def table_size(self) -> int:
        """Taille de `g_oam_entries[]` pour cette scène : un état par acteur à sprite, posé ou
        instance de pool. Pas de plafond : seul l'AFFICHAGE simultané est borné par l'OAM."""
        return self.placed_entries + self.pool_entries

    @property
    def requested(self) -> int:
        """Ce que la scène peut AFFICHER au plus : l'interface, plus tous les sprites d'acteurs.
        Au-delà de `OAM_LIMIT`, ce n'est un souci que si tout est à l'écran en même temps."""
        return self.ui + self.table_size

    @property
    def actors(self) -> int:
        """Acteurs vivants de la scène — ce que `g_actors` doit couvrir."""
        return self.placed + self.pool_slots

    @property
    def free(self) -> int:
        return OAM_LIMIT - self.ui

    @property
    def over_budget(self) -> bool:
        """L'interface seule dépasse l'OAM — le seul cas qu'aucune dégradation ne sauve : les
        acteurs, eux, ne prennent que les emplacements qui restent, à la frame."""
        return self.ui > OAM_LIMIT

    @property
    def over_capacity(self) -> bool:
        """Les acteurs posés dépassent à eux seuls les emplacements de la scène."""
        return self.placed > self.capacity

    def pool_for(self, prefab) -> Optional[PoolSlot]:
        """Le PoolSlot de ce prefab dans cette scène, ou None si non déclaré."""
        name = getattr(prefab, "name", str(prefab))
        pref = c_sym(name)
        return next((pl for pl in self.pools if pl.prefab_sym == pref), None)


def scene_oam_layout(project, scene: Scene) -> OamLayout:
    """Géométrie déterministe d'une scène (base 0). Mêmes (project, scene)
    -> même layout : `headers` (ACTOR_/POOL_) et `main_gen` (spawn/pi/g_actors)
    restent cohérents sans se coordonner.

    Ordre des pools = ordre du catalogue `project.prefabs` (stable), pour que
    l'offset d'un pool ne dépende que de la scène, jamais de l'ordre d'appel."""
    scene_sym = c_sym(scene.name)
    posed = [a for a in scene.actors if getattr(a, "active", True)]
    ui = scene_ui_obj_slots(scene, project)
    placed_entry, rank = [], 0
    for a in posed:
        if has_oam_entry(project, a):
            placed_entry.append(rank)
            rank += 1
        else:
            placed_entry.append(-1)
    placed = len(posed)

    # Les rangs d'état de chaque prefab, puis les modèles de la scène : ceux que ses scripts spawnent naissent dans le
    # pool partagé, ceux dont des acteurs posés sont des copies liées ne sont que ces instances.
    from scripting.refactor import scene_spawned_prefabs
    spawned = scene_spawned_prefabs(project, scene)
    shapes = {}
    for pf in project.prefabs:
        ranks, r = [], 0
        for m in [pf] + list(getattr(pf, "children", []) or []):
            ranks.append(r if has_oam_entry(project, m) else -1)
            r += ranks[-1] >= 0
        shapes[pf.name] = (ranks, r)
    members = model_members(project, posed)

    capacity = scene_object_capacity(project, scene)
    # `Actor.model` est un octet : au-delà de 255 types d'emplacement, les modèles suivants ne naissent plus
    # (le validateur le dit, cf. `shared_kinds`).
    kinds, shared_names = 0, []
    for pf in project.prefabs:
        if pf.name in spawned and kinds + prefab_group(pf) <= 255:
            kinds += prefab_group(pf)
            shared_names.append(pf.name)

    pools: list[PoolSlot] = []
    for pf in project.prefabs:
        placed_members = members.get(pf.name, [])
        if pf.name in shared_names or not placed_members:
            continue
        pref = c_sym(pf.name)
        pools.append(PoolSlot(
            prefab=pf, prefab_sym=pref, sym=f"{scene_sym}_{pref}",
            group=prefab_group(pf), member_entries=shapes[pf.name][0], members=placed_members,
        ))

    shared = None
    if shared_names:
        size = max(capacity - placed, 0)
        shows = any(shapes[n][1] for n in shared_names)
        shared_models = []
        next_id = 1
        for pf in project.prefabs:
            if pf.name not in shared_names:
                continue
            pref = c_sym(pf.name)
            shared_models.append(PoolSlot(
                prefab=pf, prefab_sym=pref, sym=f"{scene_sym}_{pref}",
                group=prefab_group(pf), member_entries=shapes[pf.name][0],
                members=members.get(pf.name, []), shared=True, model_id=next_id,
            ))
            next_id += prefab_group(pf)
        shared = SharedPool(start=placed, size=size, entry_start=rank,
                            entries=size if shows else 0, models=shared_models)
        pools += shared_models

    return OamLayout(scene=scene, scene_sym=scene_sym, placed=placed,
                     placed_entry=placed_entry, ui=ui, pools=pools, shared=shared, capacity=capacity)
