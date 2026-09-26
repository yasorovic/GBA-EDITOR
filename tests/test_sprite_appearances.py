"""Marche 3b : un porteur affiche UN sprite mais peut porter plusieurs apparences.

Une apparence = un `SpriteComponent` ; `active` est le sélecteur (au plus un actif).
Tout est résident : les sprites de toutes les apparences sont chargés, et leurs
palettes propres réservées. Une entrée OAM existe dès qu'une apparence existe."""
from codegen.oam_alloc import (
    has_oam_entry, initial_appearance, owner_appearances, project_oam_entry_count,
    scene_oam_layout,
)
from core.models.components import (
    SpriteComponent, affine_sprite_component, displayed_sprite_component,
    sprite_components,
)
from core.models.scene import Actor, Prefab, Scene
from core.models.sprite import SpriteAsset
from core.project import Project


def _projet(tmp_path, *, sprites=("A", "B"), scenes=(), prefabs=()):
    p = Project(tmp_path)
    for nom in sprites:
        p.sprites.append(SpriteAsset(name=nom, asset=f"{nom}.png"))
    p.scenes.items = list(scenes)
    p.prefabs.items = list(prefabs)
    return p


def _acteur(*apparences):
    """Un acteur dont chaque apparence est (sprite, actif)."""
    a = Actor(name="Hero")
    for i, (nom, actif) in enumerate(apparences):
        a.components.append(SpriteComponent(id=f"s{i}", sprite_name=nom, active=actif))
    return a


# ── Lecture du modèle ─────────────────────────────────────────────────

def test_l_apparence_affichee_est_le_composant_actif_pas_le_premier():
    a = _acteur(("A", False), ("B", True))
    assert [c.id for c in sprite_components(a)] == ["s0", "s1"]
    assert displayed_sprite_component(a).id == "s1"


def test_aucune_apparence_active_n_affiche_rien():
    assert displayed_sprite_component(_acteur(("A", False), ("B", False))) is None


def test_un_composant_sans_sprite_n_est_pas_affichable():
    a = _acteur((None, True), ("B", False))
    assert displayed_sprite_component(a) is None


def test_l_affine_appartient_a_l_entree_pas_a_l_apparence():
    """Si un composant est affine, l'entrée l'est — même quand l'apparence
    affichée ne l'est pas."""
    a = _acteur(("A", True), ("B", False))
    a.components[1].affine_transform = True
    assert affine_sprite_component(a).id == "s1"
    a.components[1].affine_transform = False
    assert affine_sprite_component(a).id == "s0"          # à défaut : l'affichée


# ── Les apparences réelles ────────────────────────────────────────────

def test_seules_les_apparences_a_image_comptent(tmp_path):
    p = _projet(tmp_path, sprites=("A",))
    p.sprites.append(SpriteAsset(name="Vide", asset=None))
    a = _acteur(("A", True), ("Vide", False), ("Fantome", False), (None, False))
    assert [(c.id, sp.name) for c, sp in owner_appearances(p, a)] == [("s0", "A")]


def test_le_rang_initial_est_celui_de_l_apparence_active(tmp_path):
    p = _projet(tmp_path)
    assert initial_appearance(p, _acteur(("A", False), ("B", True))) == 1
    assert initial_appearance(p, _acteur(("A", False), ("B", False))) == -1


def test_une_entree_est_reservee_meme_sans_apparence_active(tmp_path):
    """Activer une apparence plus tard ne doit pas demander un slot."""
    p = _projet(tmp_path)
    assert has_oam_entry(p, _acteur(("A", False)))
    assert not has_oam_entry(p, Actor(name="Controleur"))


def test_deux_apparences_ne_coutent_qu_une_entree(tmp_path):
    hero = _acteur(("A", True), ("B", False))
    scene = Scene(name="S", actors=[hero])
    p = _projet(tmp_path, scenes=[scene])
    lay = scene_oam_layout(p, scene)
    assert lay.placed_entry == [0] and lay.used == 1
    assert project_oam_entry_count(p) == 1


def test_les_parties_de_prefab_ont_aussi_des_apparences(tmp_path):
    boss = Prefab(name="Boss")
    boss.components.append(SpriteComponent(id="s0", sprite_name="A", active=True))
    boss.components.append(SpriteComponent(id="s1", sprite_name="B", active=False))
    scene = Scene(name="S")
    scene.prefab_pools = {"Boss": 3}
    p = _projet(tmp_path, scenes=[scene], prefabs=[boss])
    (pool,) = scene_oam_layout(p, scene).pools
    assert pool.member_entries == [0] and pool.entry_size == 3


# ── Validation ────────────────────────────────────────────────────────

def _erreurs(p):
    from core.validator import ValidationContext, _check_sprite_appearances
    ctx = ValidationContext(p)
    _check_sprite_appearances(ctx)
    return [m for m in ctx._msgs if m.level == "error"]


def test_deux_apparences_actives_sont_une_erreur(tmp_path):
    scene = Scene(name="S", actors=[_acteur(("A", True), ("B", True))])
    (err,) = _erreurs(_projet(tmp_path, scenes=[scene]))
    assert "2 apparences" in err.message and "s0, s1" in err.message


def test_une_seule_active_ou_aucune_ne_dit_rien(tmp_path):
    scene = Scene(name="S", actors=[_acteur(("A", True), ("B", False)),
                                    _acteur(("A", False), ("B", False))])
    assert _erreurs(_projet(tmp_path, scenes=[scene])) == []


def test_le_prefab_a_deux_apparences_actives_est_une_erreur(tmp_path):
    boss = Prefab(name="Boss")
    boss.components.append(SpriteComponent(id="s0", sprite_name="A", active=True))
    boss.components.append(SpriteComponent(id="s1", sprite_name="B", active=True))
    assert len(_erreurs(_projet(tmp_path, prefabs=[boss]))) == 1


# ── Tout résident : palettes ──────────────────────────────────────────

def test_chaque_apparence_reserve_sa_palette_propre(tmp_path):
    from codegen.palette_alloc import _actor_own_palettes
    p = _projet(tmp_path, sprites=())
    p.sprites.append(SpriteAsset(name="A", asset="A.png", own_palette=[0x001F, 0x03E0]))
    p.sprites.append(SpriteAsset(name="B", asset="B.png", own_palette=[0x7C00, 0x7FFF]))
    hero = _acteur(("A", True), ("B", False))
    hero.pal_bank = -1   # OWN_PAL_BANK
    scene = Scene(name="S", actors=[hero])
    from core.models.palette import OWN_PAL_BANK
    hero.pal_bank = OWN_PAL_BANK
    palettes = _actor_own_palettes(p, scene)
    assert palettes == [[0x001F, 0x03E0], [0x7C00, 0x7FFF]]      # l'inactive aussi
