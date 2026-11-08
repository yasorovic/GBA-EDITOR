"""Le modèle affine : la décision vit sur
le SPRITE (`SpriteComponent.affine_transform` — réserver un slot de matrice OAM
est une capacité de rendu), et le rendu lit au runtime le transform du sprite
(rotation et échelle autour du pivot, offset depuis la position de l'acteur). Un
acteur n'a ni rotation ni échelle (retirées le 2026-11-08).

Deux régressions sont scellées ici, toutes deux découvertes en refondant ce
modèle :
  * l'ancien `g_affine_*[]` était `static` dans un header multi-inclus → une
    COPIE par unité de compilation ; les écritures d'un script n'atteignaient
    jamais le rendu. Le stockage est maintenant par entrée d'affichage (OamEntry) ;
  * l'ancien seed scène lisait `flip_h` sur le SpriteComponent (champ
    inexistant → toujours faux) au lieu de l'Actor.
"""
from __future__ import annotations

from core.models.components import SpriteComponent
from core.models.scene import Actor
from codegen.runtime_codegen.gen_affine import (
    affine_entry, compute_affine_info, affine_oam_lines,
)


def _actor(**kw) -> Actor:
    a = Actor(name="A")
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _sc(**kw) -> SpriteComponent:
    s = SpriteComponent()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# ── L'allocation est pilotée par le SPRITE ──────────────────────────

def test_non_affine_ne_reserve_aucun_slot():
    assert affine_entry(_sc()) is None
    assert affine_entry(None) is None                 # pas de sprite


def test_affine_est_affine_meme_a_identite():
    """`affine_transform` coché rend le sprite affine même si scale/rotation valent
    leur défaut : c'est ce qui laisse le rendu écrire une matrice (prise à la frame)."""
    e = affine_entry(_sc(affine_transform=True))
    assert e is not None and "slot" not in e
    assert e["sprite_scale_x"] == 256 and e["sprite_scale_y"] == 256   # Q8, 100%


def test_le_scale_rotation_sans_affine_sont_ignores():
    """Un scale/rotation sur le sprite SANS « Affine transform » ne crée pas de
    slot : sans réservation, aucune matrice n'est écrite."""
    sc = _sc(scale_x=2.0, rotation=45)
    assert affine_entry(sc) is None


def test_le_transform_du_sprite_finit_dans_l_entree():
    sc = _sc(affine_transform=True,
             rotation=45, scale_x=1.5, scale_y=0.25, offset_x=-8, offset_y=12)
    e = affine_entry(sc)
    assert "rotation" not in e and "scale_x" not in e   # un acteur n'a ni rotation ni échelle
    assert e["sprite_rotation"] == 45
    assert e["sprite_scale_x"] == 384     # Q8 : 1.5×256
    assert e["sprite_scale_y"] == 64      # Q8 : 0.25×256
    assert (e["offset_x"], e["offset_y"]) == (-8, 12)


def test_compute_affine_info_designe_les_poses_affines():
    a1 = _actor()
    a1.components.append(_sc(affine_transform=True))
    a2 = _actor()
    a2.components.append(_sc(affine_transform=True))
    a3 = _actor()                       # sprite sans affine → pas de slot
    a3.components.append(_sc())
    scene_actors = [(a1, None), (a2, None), (a3, None)]
    info = compute_affine_info(offset := 10, scene_actors, [])
    assert set(info) == {10, 11}          # a1 et a2, pas a3 ; aucune matrice réservée
    assert all("slot" not in e for e in info.values())


# ── Le C émis reflète la composition ────────────────────────────────

def test_oam_dynamic_appelle_le_moteur():
    class SpriteShape:
        frame_w, frame_h = 8, 8
        oam_shape, oam_size = 1, 0     # 8×8 affine
        tiles_per_frame = 1

    lines = "\n".join(affine_oam_lines(7, SpriteShape(), bt=0))
    # Le calcul vit dans le moteur (`oam_write_affine`, un seul exemplaire en IWRAM) : le C émis lui passe l'acteur, son
    # entrée d'affichage et son cache, la caméra, puis les constantes du sprite (cadre 8x8, tuile 0, 1 tuile par frame,
    # forme 1, taille 0). La composition elle-même est mesurée par les sondes natives (test_affine_anchor_native).
    assert lines.strip() == ("_oamn=oam_write_affine(&g_actors[7],&g_oam_entries[7],&g_aff_cache[7],_oamn,&_affn,"
                             "cam_x,cam_y,8,8,0,1,1,0);")
    assert "cam_x" not in "\n".join(affine_oam_lines(7, SpriteShape(), bt=0, screen_space=True))


def test_le_pivot_est_seme_depuis_le_composant_sprite():
    sc = _sc(affine_transform=True, pivot_x=3, pivot_y={"unit": "t", "n": 1})
    e = affine_entry(sc)
    assert (e["pivot_x"], e["pivot_y"]) == (3, 8)
    assert (affine_entry(_sc(affine_transform=True))["pivot_x"]) == 0


def test_centrer_sur_le_cadre_a_la_case_affine():
    from core.models.components import (CollisionShapeComponent, SpriteComponent,
                                        center_on_frame)

    class Frame:
        frame_w, frame_h = 32, 24

    sprite_comp = SpriteComponent()
    deplacee = CollisionShapeComponent(id="a", x=0, y=0, w=16, h=8)
    reglee = CollisionShapeComponent(id="b", x=3, y=0, w=16, h=8)
    owner = _actor()
    owner.components = [sprite_comp, deplacee, reglee]

    changed = center_on_frame(owner, sprite_comp, Frame())

    assert (sprite_comp.offset_x, sprite_comp.offset_y) == (-16, -12)
    assert (deplacee.x, deplacee.y) == (-8, -4)
    assert (reglee.x, reglee.y) == (3, 0)          # réglage de l'auteur préservé
    assert sprite_comp in changed and reglee not in changed

    sprite_comp.offset_x = 5                       # offset déjà réglé : intact
    center_on_frame(owner, sprite_comp, Frame())
    assert sprite_comp.offset_x == 5


def test_script_lua_compile_avec_les_props_affine():
    """(end-to-end) parse → check → C : un script qui lit/écrit les props du sprite
    passe quand l'actor a « Affine transform », et le C émis appelle bien les setters/getters."""
    from scripting.parser import parse as lua_parse
    from scripting.checker import check as lua_check, BuildContext
    from scripting.codegen import generate as lua_generate, CodegenContext

    src = """
    function on_update(self)
        self.sprite_rotation = self.sprite_rotation + 1
        self.sprite_rotation = 45
        self.sprite_scale = vec2(150, 150)
        self.sprite_offset = vec2(-10, 6)
        local s = self.sprite_scale
        local o = self.sprite_offset
    end
    """
    script = lua_parse(src)
    ctx = BuildContext(actor_name="Ball", affine_transform=True)
    assert [str(e) for e in lua_check(script, ctx)] == []

    cg = CodegenContext(actor_name="Ball", actor_sym="Ball", anim_names=[],
                        sfx_names=[], music_names=[], global_names=set(),
                        const_names=set(), all_actor_syms=["Ball"])
    code, _, _ = lua_generate(script, cg)
    for needle in (
        "actor_get_sprite_rotation(self",
        "actor_set_sprite_rotation(self, 45",
        "actor_set_sprite_scale(self,", "actor_set_sprite_offset(self,",
        "Vec2 s = actor_get_sprite_scale(self);",
        "Vec2 o = actor_get_sprite_offset(self);",
    ):
        assert needle in code, needle


def test_script_lua_sans_affine_avertit_sans_bloquer():
    """Un sprite sans « Affine transform » n'a aucun slot : le checker le dit,
    mais en AVERTISSEMENT. La valeur, elle, s'écrit et se relit — les accesseurs
    ne consultent plus le slot ; c'est l'affichage qui manque, pas le stockage.
    Un refus de build ferait mentir `self.sprite_rotation = self.sprite_rotation + 1`."""
    from scripting.parser import parse as lua_parse
    from scripting.checker import check as lua_check, BuildContext

    src = "function on_update(self)\n    self.sprite_rotation = 1\nend\n"
    script = lua_parse(src)
    found = lua_check(script, BuildContext(actor_name="Ball", affine_transform=False))
    assert found, "le checker doit signaler un self.sprite_rotation sans slot affine"
    assert [e.level for e in found] == ["warning"] * len(found)


def test_accesseurs_affine_non_gardes_par_le_slot():
    """(régression) `if (affine_slot >= 0)` sur les setters/getters faisait
    disparaître la valeur écrite par un script quand le sprite n'était pas
    affine. Les champs sont de l'état de jeu : ils s'écrivent toujours."""
    from pathlib import Path
    api = (Path(__file__).resolve().parents[2]
           / "runtime" / "include" / "runtime_api_inline.h").read_text(encoding="utf-8")
    body = api[api.index("static inline void actor_set_sprite_rotation"):
               api.index("static inline int  actor_get_dir")]
    assert "affine_slot" not in body


def test_seed_scene_ecrit_dans_la_struct_actor():
    """(régression) la struct Actor a bien les champs que le seed écrit : on les
    déclare dans actor_types_static.h, pas dans des globaux cachés."""
    from pathlib import Path
    hdr = (Path(__file__).resolve().parents[2]
           / "runtime" / "include" / "actor_types_static.h").read_text(encoding="utf-8")
    for f in ("affine_slot", "rotation", "scale_x", "scale_y",
              "offset_x", "offset_y"):
        assert f in hdr
    # Deux tables depuis la marche 0a : l'état d'affichage (transform local
    # compris) vit dans `OamEntry`, la collision reste un bloc de l'Actor.
    assert "} OamEntry;" in hdr and "} collision;" in hdr
    assert "int sprite_rot;" not in hdr
    # `affine_slot` a suivi la case : c'est du rendu, donc `OamEntry`.
    assert hdr.index("s8 affine_slot;") < hdr.index("} OamEntry;")
    api = (Path(__file__).resolve().parents[2]
           / "runtime" / "include" / "runtime_api_inline.h").read_text(encoding="utf-8")
    # (régression) plus de globals par slot : chaque TU en aurait une copie
    assert "g_affine_angle" not in api
    assert "g_affine_scale_x" not in api

# ── La case a déménagé : les projets d'avant suivent ─────────────────

def test_ancienne_cle_sur_l_actor_migre_vers_le_sprite():
    """Un projet enregistré avant le 2026-08-25 porte `affine_transform` sur
    l'actor. Il est relu une fois et reposé sur le SpriteComponent, sinon les
    acteurs affines de tous les projets existants perdent leur slot au premier
    chargement."""
    d = {
        "name": "Ball",
        "affine_transform": True,
        "components": [{"component_type": "sprite", "id": "sprite", "sprite_name": "Ball"}],
    }
    a = Actor.from_dict(d)
    sc = next(c for c in a.components if isinstance(c, SpriteComponent))
    assert sc.affine_transform is True
    # …et la clé n'est plus réécrite : une seule définition, sur le sprite.
    assert "affine_transform" not in a.to_dict()
    assert a.to_dict()["components"][0]["affine_transform"] is True


def test_migration_sans_sprite_ne_casse_rien():
    """Un actor coché mais sans SpriteComponent n'a jamais rien réservé
    (`compute_affine_info` passait déjà son tour) : rien à reporter."""
    a = Actor.from_dict({"name": "Trigger", "affine_transform": True, "components": []})
    assert a.components == []


def test_prefab_delegue_la_case_a_son_sprite():
    from core.models.scene import Prefab
    pf = Prefab.from_dict({
        "name": "Ball", "max_instances": 4, "affine_transform": True,
        "components": [{"component_type": "sprite", "id": "sprite", "sprite_name": "Ball"}],
    })
    assert pf.affine_transform is True
    pf.actor.get_component("sprite").affine_transform = False
    assert pf.affine_transform is False


def test_offset_du_sprite_peut_etre_une_variable():
    """Offset px/tile → entier ; variable → expression C (assignation à l'init)."""
    from core.models.field_value import FieldValue
    names = {("global", "000000000003"): "shake"}
    sc = _sc(affine_transform=True, offset_x={"unit": "t", "n": 2},
             offset_y={"var": "000000000003", "src": "global"})
    e = affine_entry(sc, names=names)
    assert e["offset_x"] == 16
    assert e["offset_y"] == "g_shake"


def test_rotation_echelle_variables_dans_le_c():
    """Rotation/échelle du sprite en variable : expression C ; l'échelle d'une variable
    est en POURCENT (100 = normal), ramenée au Q8 du moteur."""
    names = {("global", "000000000005"): "spin", ("global", "000000000006"): "zoom"}
    sc = _sc(affine_transform=True, scale_y=2.0)
    sc.rotation = {"var": "000000000005", "src": "global"}
    sc.scale_x = {"var": "000000000006", "src": "global"}
    e = affine_entry(sc, names=names)
    assert e["sprite_rotation"] == "g_spin"
    assert e["sprite_scale_x"] == "((g_zoom)*256/100)"
    assert e["sprite_scale_y"] == 512


def test_number_value_resout_la_variable_a_son_defaut():
    from core.models.field_value import number_value, number_c
    res = lambda src, key: 150 if key == "000000000006" else None
    assert number_value({"var": "000000000006", "src": "global"}, res, 1.0, ref_divisor=100) == 1.5
    assert number_value({"var": "000000000009", "src": "global"}, res, 1.0, ref_divisor=100) == 1.0
    assert number_c({"var": "000000000005", "src": "global"}, {("global", "000000000005"): "p"}, mask=3) == "((g_p)&3)"
    assert number_c(7, None, mask=3) == 3
