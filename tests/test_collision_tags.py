"""Les `BOXTAG_*` de `actor_types.h` — le défaut qu'aucun test unitaire ne
voyait, parce qu'il ne se manifeste qu'au `make`.

`spawn_<Prefab>()` écrit `boxes[].tag = BOXTAG_<TAG>` pour la box d'un prefab
poolé et pour celles de ses PARTIES (ROADMAP v0.23). La liste des `#define`,
elle, ne parcourait que les acteurs de SCÈNE. Un tag porté seulement par un
prefab n'avait donc pas de constante, et le C émis ne compilait pas :

    src/main.c: In function 'spawn_Ball':
    error: 'BOXTAG_BODY' undeclared (first use in this function)

Il n'y avait pas à réécrire cette collecte : `Project.collision_tags()` la fait
déjà — scènes, prefabs, parties de prefabs — et se dit « source unique » pour le
sélecteur de tag et pour la matrice de Project Settings. Le codegen en était la
troisième lecture, et la seule qui mentait.
"""
from __future__ import annotations

from pathlib import Path

from core.models.components import CollisionBoxComponent, SpriteComponent
from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from codegen.runtime_codegen.headers import generate_actor_types


def _box(tag: str, active: bool = True) -> CollisionBoxComponent:
    return CollisionBoxComponent(id=f"box_{tag}", active=active, tag=tag)


def _projet(tmp_path: Path) -> Project:
    """Un projet minimal : une scène dont l'unique acteur porte le tag
    « Other », et un prefab poolé dont la box porte « body »."""
    p = Project(tmp_path)
    acteur = Actor(name="PADDLE", components=[_box("Other")])
    scene = Scene(name="ARENA", actors=[acteur])
    p.scenes.items = [scene]

    balle = Prefab(name="Ball")
    balle.actor.components = [SpriteComponent(), _box("body")]
    p.prefabs.items = [balle]
    # Le pool se déclare sur la SCÈNE depuis la v0.17 (plus de repli
    # `max_instances`) : c'est ce qui rend `Ball` réellement poolé.
    scene.prefab_pools = {"Ball": 4}
    return p


def _header(p: Project, tmp_path: Path) -> str:
    p.src_dir.mkdir(parents=True, exist_ok=True)
    generate_actor_types(p)
    return (p.src_dir / "actor_types.h").read_text(encoding="utf-8")


def test_le_tag_d_un_prefab_a_sa_constante(tmp_path):
    """Le défaut visé : BOXTAG_BODY manquait, et `spawn_Ball` ne compilait
    pas."""
    h = _header(_projet(tmp_path), tmp_path)
    assert "#define BOXTAG_BODY " in h
    assert "#define BOXTAG_OTHER " in h


def test_le_tag_d_une_partie_de_prefab_aussi(tmp_path):
    """Une PARTIE de prefab (ROADMAP v0.23) a ses propres boxes, et
    `spawn_<Prefab>` les écrit comme celles de la racine."""
    p = _projet(tmp_path)
    p.prefabs.items[0].children = [
        Actor(name="Ball_bras", parent=None, components=[_box("sword_hitbox")])
    ]
    h = _header(p, tmp_path)
    assert "#define BOXTAG_SWORD_HITBOX " in h


def test_une_box_inactive_garde_son_tag(tmp_path):
    """« Active » de l'inspecteur n'est que l'état de DÉPART : un script peut
    allumer la boîte (`hb:activate()`, après `self:collision_box("fantome")`),
    donc son tag doit avoir une constante."""
    p = _projet(tmp_path)
    p.prefabs.items[0].actor.components.append(_box("fantome", active=False))
    h = _header(p, tmp_path)
    assert "#define BOXTAG_FANTOME " in h


def test_chaque_tag_a_un_numero_distinct(tmp_path):
    """Les valeurs sont comparées entre elles au runtime (`my_box == other_box`)
    : deux tags qui partageraient un numéro rendraient la comparaison fausse
    sans qu'aucun avertissement ne le dise."""
    p = _projet(tmp_path)
    p.settings.collision_tags = ["hurtbox", "body"]     # déclarés dans Settings
    h = _header(p, tmp_path)
    numeros = [int(l.rsplit(" ", 1)[1]) for l in h.splitlines()
               if l.startswith("#define BOXTAG_")]
    assert numeros == sorted(set(numeros))
    # Un tag DÉCLARÉ mais posé sur aucune box a quand même sa constante : un
    # script peut le citer avant que la box existe.
    assert "#define BOXTAG_HURTBOX " in h
