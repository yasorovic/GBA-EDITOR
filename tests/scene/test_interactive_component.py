"""Le composant Interactive (tranche 2 du chantier « Interagir avec un acteur ») : son modèle et sa
sérialisation, la taille de sa boîte implicite, le tag de collision réservé, et ses vérifications au build."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.models.components import (
    INTERACTIVE_DEFAULT_BOX, CollisionBoxComponent, InteractiveComponent, COMPONENT_REGISTRY,
    component_type_name, components_from_list, components_to_list, interactive_box_size,
)
from core.models.settings import (
    DEFAULT_COLLISION_TAGS, INTERACTIVE_COLLISION_TAG, RESERVED_COLLISION_TAGS,
)


# ── Le modèle ─────────────────────────────────────────────────────────

def test_les_valeurs_par_defaut():
    c = InteractiveComponent()
    assert (c.input_mode, c.interaction, c.box_tag, c.box_w, c.box_h) == ("pressed", "hover", "", 0, 0)
    assert c.hold_frames >= 1
    assert COMPONENT_REGISTRY["interactive"] is InteractiveComponent
    assert component_type_name(c) == "interactive"


def test_aller_retour_de_la_serialisation():
    c = InteractiveComponent(input_mode="hold", hold_frames=45, interaction="facing",
                             box_tag="reach", box_w=24, box_h=12)
    (relu,) = components_from_list(components_to_list([c]))
    assert relu == c


def test_une_valeur_inconnue_retombe_sur_le_defaut():
    c = InteractiveComponent(input_mode="turbo", interaction="x-ray", hold_frames=0, box_w=-3)
    assert (c.input_mode, c.interaction) == ("pressed", "hover")
    assert c.hold_frames >= 1 and c.box_w == 0


# ── La boîte implicite ────────────────────────────────────────────────

def test_la_taille_de_la_boite_implicite():
    c = InteractiveComponent()
    assert interactive_box_size(c) == (INTERACTIVE_DEFAULT_BOX,) * 2          # sans sprite : 16×16
    assert interactive_box_size(c, 32, 24) == (32, 24)                        # le cadre du sprite
    assert interactive_box_size(InteractiveComponent(box_w=8), 32, 24) == (8, 24)   # l'auteur gagne, par axe


# ── Le tag de collision réservé ───────────────────────────────────────

def test_interactive_est_un_tag_reserve_et_declare_d_office():
    assert INTERACTIVE_COLLISION_TAG == "Interactive"
    assert INTERACTIVE_COLLISION_TAG in RESERVED_COLLISION_TAGS
    assert INTERACTIVE_COLLISION_TAG in DEFAULT_COLLISION_TAGS


def test_les_commandes_refusent_de_renommer_ou_retirer_un_tag_reserve():
    from core.history import RemoveCollisionTagCmd, RenameCollisionTagCmd
    projet = SimpleNamespace(settings=SimpleNamespace(), scenes=[], prefabs=[])
    with pytest.raises(ValueError, match="reserved"):
        RenameCollisionTagCmd(projet, INTERACTIVE_COLLISION_TAG, "Autre")
    with pytest.raises(ValueError, match="reserved"):
        RemoveCollisionTagCmd(projet, INTERACTIVE_COLLISION_TAG)


def test_un_projet_ancien_retrouve_le_tag_reserve(tmp_path):
    """`collision_tags` est vide dans un ancien projet : le tag réservé est recréé, pas migré."""
    from core.project import Project
    projet = Project.create(tmp_path / "Game", "Game")
    projet.settings.collision_tags = ["Player", "body"]
    assert INTERACTIVE_COLLISION_TAG in projet.collision_tags()
    assert projet.collision_tags().count(INTERACTIVE_COLLISION_TAG) == 1


# ── Les vérifications au build ────────────────────────────────────────

LUA_AVEC_HANDLER = """function on_interact(who)
end
"""
LUA_SANS_HANDLER = """function on_update()
end
"""

def _messages(components, lua: str | None = None, tmp_path=None):
    """Ce que `_check_interactive` dit d'un acteur `Chest` portant ces composants. `lua` : le texte de
    son script (un `ScriptComponent` est alors ajouté), sinon l'acteur n'a pas de script."""
    from core.models.components import ScriptComponent
    from core.validator import ValidationContext, _check_interactive
    components = list(components)
    root = tmp_path
    if lua is not None:
        (root / "chest.lua").write_text(lua, encoding="utf-8")
        components.append(ScriptComponent(script="chest.lua"))
    actor = SimpleNamespace(name="Chest", components=components)
    hero = SimpleNamespace(name="Hero", components=[], is_player=True)
    project = SimpleNamespace(scenes=[SimpleNamespace(name="S", actors=[actor, hero])], prefabs=[],
                              asset_abs=lambda rel: root / rel)
    ctx = ValidationContext.__new__(ValidationContext)
    ctx.project, ctx._msgs, ctx._focus, ctx._scripts = project, [], "", {}
    _check_interactive(ctx)
    return [(m.level, m.message) for m in ctx._msgs]


def _forme(messages):
    """Les messages de forme, sans l'avertissement « handler » (il a ses propres tests)."""
    return [m for m in messages if "on_interact" not in m[1]]


def test_une_boite_designee_doit_exister_sur_l_acteur(tmp_path):
    absent = _forme(_messages([InteractiveComponent(box_tag="reach")], tmp_path=tmp_path))
    assert len(absent) == 1 and absent[0][0] == "error" and "reach" in absent[0][1]
    present = _forme(_messages([InteractiveComponent(box_tag="reach"),
                                CollisionBoxComponent(tag="reach")], tmp_path=tmp_path))
    assert present == []


def test_la_boite_propre_exige_un_emplacement_libre(tmp_path):
    pleins = [CollisionBoxComponent(id=f"c{i}", tag=f"t{i}") for i in range(4)]
    assert len(_forme(_messages([InteractiveComponent(), *pleins], tmp_path=tmp_path))) == 1
    assert _forme(_messages([InteractiveComponent(), *pleins[:3]], tmp_path=tmp_path)) == []
    assert _forme(_messages([InteractiveComponent(box_tag="t0"), *pleins], tmp_path=tmp_path)) == []


def test_un_composant_inactif_ou_surnumeraire(tmp_path):
    assert _forme(_messages([InteractiveComponent(active=False, box_tag="absent")], tmp_path=tmp_path)) == []
    deux = _forme(_messages([InteractiveComponent(id="a"), InteractiveComponent(id="b")], tmp_path=tmp_path))
    assert [m[0] for m in deux] == ["warning"]


def test_un_composant_sans_handler_averti(tmp_path):
    sans_script = _messages([InteractiveComponent()], tmp_path=tmp_path)
    assert [m[0] for m in sans_script] == ["warning"] and "on_interact" in sans_script[0][1]
    sans_handler = _messages([InteractiveComponent()], LUA_SANS_HANDLER, tmp_path)
    assert [m[0] for m in sans_handler] == ["warning"]
    avec = _messages([InteractiveComponent()], LUA_AVEC_HANDLER, tmp_path)
    assert avec == []


def test_un_handler_sans_composant_averti(tmp_path):
    orphelin = _messages([], LUA_AVEC_HANDLER, tmp_path)
    assert [m[0] for m in orphelin] == ["warning"] and "never called" in orphelin[0][1]
    inactif = _messages([InteractiveComponent(active=False)], LUA_AVEC_HANDLER, tmp_path)
    assert [m[0] for m in inactif] == ["warning"]


def test_une_scene_interactive_sans_joueur_averti(tmp_path):
    from core.validator import ValidationContext, _check_interactive
    coffre = SimpleNamespace(name="Chest", components=[InteractiveComponent()])
    projet = SimpleNamespace(scenes=[SimpleNamespace(name="S", actors=[coffre])], prefabs=[],
                             asset_abs=lambda rel: tmp_path / rel)
    ctx = ValidationContext.__new__(ValidationContext)
    ctx.project, ctx._msgs, ctx._focus, ctx._scripts = projet, [], "", {}
    _check_interactive(ctx)
    assert any("no actor tagged Player" in m.message for m in ctx._msgs)


def test_le_tag_joueur_survit_a_la_serialisation():
    from core.models.scene import Actor
    assert "is_player" not in Actor(name="A").to_dict()                  # défaut : aucune clé
    assert Actor.from_dict(Actor(name="A", is_player=True).to_dict()).is_player is True
    assert Actor.from_dict({"name": "A"}).is_player is False


def test_les_boites_effectives_ajoutent_la_boite_propre_en_dernier():
    from core.models.components import effective_collision_boxes, interactive_box_index
    owner = SimpleNamespace(components=[CollisionBoxComponent(tag="body"), InteractiveComponent()])
    boxes = effective_collision_boxes(owner, 24, 32)
    assert [b.tag for b in boxes] == ["body", "Interactive"]
    assert (boxes[1].w, boxes[1].h, boxes[1].solid) == (24, 32, False)
    assert interactive_box_index(boxes, owner.components[1]) == 1
    centree = effective_collision_boxes(owner, 24, 32, centered=True)
    assert (centree[1].x, centree[1].y) == (-12, -16)


def test_une_boite_designee_n_ajoute_rien():
    from core.models.components import effective_collision_boxes, interactive_box_index
    comp = InteractiveComponent(box_tag="reach")
    owner = SimpleNamespace(components=[CollisionBoxComponent(tag="body"),
                                        CollisionBoxComponent(tag="reach"), comp])
    boxes = effective_collision_boxes(owner)
    assert [b.tag for b in boxes] == ["body", "reach"]
    assert interactive_box_index(boxes, comp) == 1
    assert interactive_box_index(boxes, InteractiveComponent(box_tag="absent")) == -1


def test_la_scene_de_depart_d_un_projet_neuf_a_son_joueur(tmp_path):
    """L'acteur de départ porte le tag Joueur : un premier composant Interactive fonctionne sans
    qu'il y ait quoi que ce soit à cocher."""
    from core.project import Project
    projet = Project.create(tmp_path / "Game", "Game")
    depart = projet.scenes[0]
    assert [(a.name, a.is_player) for a in depart.actors] == [("Player", True)]
    relu = Project.open(projet.root)
    assert [(a.name, a.is_player) for a in relu.scenes[0].actors] == [("Player", True)]


# ── Un prefab peut être le joueur ─────────────────────────────────────

def test_le_tag_joueur_d_un_prefab_survit_a_la_serialisation():
    from core.models.scene import Actor, Prefab
    assert "is_player" not in Prefab(name="Coin").to_dict()                 # défaut : aucune clé
    hero = Prefab(name="Hero", actor=Actor(name="Hero", is_player=True))
    relu = Prefab.from_dict(hero.to_dict())
    assert relu.is_player is True and relu.actor.is_player is True
    assert Prefab.from_dict({"name": "Old"}).is_player is False


def test_une_instance_de_prefab_joueur_est_joueur(tmp_path):
    from core.models.scene import Actor, Prefab
    from core.project import Project
    projet = Project.create(tmp_path / "Game", "Game")
    hero = Prefab(name="Hero", actor=Actor(name="Hero", is_player=True))
    instance = projet.instantiate_actor_from_prefab(hero, "Hero_1")
    assert instance.is_player is True and instance.prefab_name == "Hero"


def test_expose_et_relink_portent_le_tag_joueur(tmp_path):
    from core.command_dispatcher import CommandDispatcher
    from core.models.scene import Actor, Prefab
    from core.project import Project
    projet = Project.create(tmp_path / "Game", "Game")
    prefab = Prefab(name="Hero", actor=Actor(name="Hero"))
    projet.prefabs.append(prefab)
    projet.prefabs.save(prefab, None)
    instance = Actor(name="Hero_1", prefab_name="Hero", is_player=True)
    projet.scenes[0].actors.append(instance)

    dispatcher = CommandDispatcher.__new__(CommandDispatcher)
    dispatcher._project = projet
    dispatcher._emit = lambda *a, **k: None
    dispatcher._save_scene = lambda: None
    dispatcher.save_prefab = lambda pf: None

    assert dispatcher.expose_actor_to_prefab(instance) is True
    assert prefab.actor.is_player is True                  # l'instance pousse son tag vers le prefab
    instance.is_player = False
    assert dispatcher.relink_actor_to_prefab(instance) is True
    assert instance.is_player is True                      # et le recharge depuis lui


# ── Les tags réservés : Player puis Interactive, en tête, et non éditables ──

def test_player_est_reserve_et_passe_en_premier(tmp_path):
    from core.history import RemoveCollisionTagCmd, RenameCollisionTagCmd
    from core.models.settings import PLAYER_COLLISION_TAG
    from core.project import Project
    assert RESERVED_COLLISION_TAGS == (PLAYER_COLLISION_TAG, INTERACTIVE_COLLISION_TAG)

    projet = Project.create(tmp_path / "Game", "Game")
    assert projet.collision_tags()[:3] == ["Player", "Interactive", "body"]

    # La liste sauvée est triée alphabétiquement (« Interactive » avant « Player ») : l'ordre affiché
    # remet les tags réservés en tête quand même.
    projet.settings.collision_tags = sorted(["Player", "body", "Interactive", "enemy"])
    assert projet.collision_tags() == ["Player", "Interactive", "body", "enemy"]

    for commande, args in ((RenameCollisionTagCmd, ("Player", "Hero")), (RemoveCollisionTagCmd, ("Player",))):
        with pytest.raises(ValueError, match="reserved"):
            commande(projet, *args)
