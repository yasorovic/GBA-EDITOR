"""editor/codegen/palette_alloc.py — allocation des banques de palette par scène.

Source de vérité UNIQUE (pipeline grit + main_gen) pour :
- quelles couleurs occupent chacune des 16 banques matérielles d'un pool
  (OBJ / BG) d'une scène,
- l'index de banque de chaque asset : palette RÉFÉRENCÉE (pal_bank 0-15) ->
  son slot ; palette PROPRE (pal_bank == OWN_PAL_BANK) -> slot libre
  auto-alloué à sa palette d'origine.

La palette propre d'un asset = couleurs du PNG (index 0 transparent), extraite
à la volée via extract_palette_from_image, mémoïsée par (chemin, mtime).

Déterministe : les mêmes (project, scene, pool) donnent toujours le même
layout, donc pipeline.py (grit -mp) et main_gen.py (g_pal_* + g_actors) restent
cohérents sans se coordonner explicitement.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.models.palette import OWN_PAL_BANK
from core.models.scene import Scene, scene_font_pal_bank
from core.project import Project
from codegen.oam_alloc import scene_pool_instances
from core.models.gba_color import extract_palette_from_image
from core.models.gba_color import RESERVED_SLOT_COLOR
from core.palette_presets import DEFAULT_PAL_BANK_COLORS

# Cache des palettes propres, invalidé par mtime du PNG.
_own_cache: dict[tuple[str, float], list[int]] = {}

# Cache OPTIONNEL de `scene_bank_layout`, à PORTÉE DE CONTEXTE. Éteint par
# défaut : le build — et tout appelant hors du canvas — recalcule toujours,
# aucun risque de servir une allocation périmée. Le canvas l'active le seul
# temps de PRÉ-CHAUFFER les items d'une scène (cf. GBAScene.set_ui_regions) :
# plusieurs régions d'une même scène partagent alors UNE allocation au lieu
# d'en refaire une chacune (la résolution des polices y coûte cher). Clé par
# IDENTITÉ — le contexte ne vit que le temps d'un lot de calculs sur des objets
# figés, jamais à travers une édition.
_layout_cache: "dict | None" = None


@contextmanager
def scene_layout_cache():
    """Active la mémoïsation de `scene_bank_layout` pour la durée du bloc.
    Réentrant : seul le contexte le plus externe crée et jette le cache."""
    global _layout_cache
    outer = _layout_cache
    if outer is None:
        _layout_cache = {}
    try:
        yield
    finally:
        _layout_cache = outer


def own_palette(png_path) -> list[int]:
    """Palette propre d'un PNG (couleurs d'origine, index 0 transparent),
    mémoïsée par chemin+mtime. [] si le fichier est absent/illisible."""
    p = Path(png_path)
    try:
        key = (str(p), p.stat().st_mtime)
    except OSError:
        return []
    cached = _own_cache.get(key)
    if cached is None:
        try:
            cached = extract_palette_from_image(p)
        except Exception:
            cached = []
        _own_cache[key] = cached
    return cached


class SceneBankLayout:
    """Résultat de l'allocation pour une scène + un pool."""

    def __init__(self, slot_colors: list[Optional[list[int]]],
                 own_slot: dict[tuple, Optional[int]],
                 bg_block: Optional[dict[tuple, Optional[int]]] = None):
        self.slot_colors = slot_colors      # 16 entrées : couleurs BGR555 ou None
        self._own_slot   = own_slot          # tuple(colors) -> index de banque (None si débordement)
        self._bg_block   = bg_block or {}    # clé palettes fond compressé -> offset de bloc (None si débordement)

    def bank_index(self, pal_bank: int, own_colors: Optional[list[int]]) -> Optional[int]:
        """Index de banque hardware d'un asset :
        - référencé (0-15) -> pal_bank tel quel ;
        - OWN -> slot alloué à sa palette propre (None si débordement >16)."""
        if pal_bank != OWN_PAL_BANK:
            return pal_bank if 0 <= pal_bank < 16 else None
        if not own_colors:
            return None
        return self._own_slot.get(tuple(own_colors))

    def bg_block_offset(self, ba) -> Optional[int]:
        """Offset (première banque) du bloc alloué à un BackgroundAsset
        compressé (ses N sous-palettes occupent des banques contiguës) —
        None si débordement (pas assez de banques libres contiguës)."""
        key = _bg_palettes_key(ba)
        return self._bg_block.get(key)

    def bank_count(self) -> int:
        """Nombre de banques réellement occupées (référencées + propres)."""
        return sum(1 for c in self.slot_colors if c)

    def overflow(self) -> bool:
        """True si au moins une palette propre (ou un bloc de fond compressé)
        n'a pas trouvé de place libre."""
        return (any(v is None for v in self._own_slot.values())
                or any(v is None for v in self._bg_block.values()))


def effective_palette_colors(p: Project, pal_bank: int, png_path,
                             active_names: list, own_pal=None) -> Optional[list[int]]:
    """Couleurs vers lesquelles quantifier un asset (grit) :
    - OWN -> sa palette propre (`own_pal` = métadonnées sprite si fournies ;
      sinon extraction du PNG, cas BG) ;
    - référencé -> les couleurs de la banque nommée du slot ;
    - None si rien de résoluble (slot vide / palette absente)."""
    if pal_bank == OWN_PAL_BANK:
        # `own_pal` (sprite.own_palette) est stocké SANS le slot 0 réservé (cf.
        # own_palette_from_source) — on le préfixe ici pour obtenir la forme
        # 16-slots attendue par GritSprites.run() (quantize_asset direct_index
        # + remap_tiles_to_bank). `own_palette(png_path)` (fallback BG) inclut
        # déjà ce slot (extract_palette_from_image) — pas de double préfixe.
        if own_pal:
            return [RESERVED_SLOT_COLOR] + list(own_pal)
        return own_palette(png_path) or None
    if 0 <= pal_bank < len(active_names):
        name = active_names[pal_bank]
        bank = p.get_palette(name) if name else None
        return list(bank.colors) if bank and bank.colors else None
    return None


# ── Sources d'assets « palette propre » d'une scène ──────────────────────────

def _owner_sprites(p: Project, owner) -> list:
    """Les sprites de TOUTES les apparences d'un porteur (prefab, partie ou
    acteur). Tout résident (marche 3) : une apparence inactive au départ n'en a
    pas moins besoin de sa banque quand on l'active, donc chacune la réserve.
    Un prefab segmenté a un sprite par partie, chacune pouvant porter sa propre
    palette."""
    from core.models.components import sprite_components
    sprites = (p.get_sprite(c.sprite_name) for c in sprite_components(owner) if c.sprite_name)
    return [sp for sp in sprites if sp]


def _sprite_own_palette(sp) -> list[int]:
    """Palette propre (compression) d'un sprite = ses métadonnées
    `own_palette` (BGR555), source de vérité du modèle non-destructif. []
    si absent."""
    return list(getattr(sp, "own_palette", None) or []) if sp else []


def ui_image_own_palettes(p: Project, scene: Scene, pool: str) -> list[list[int]]:
    """Palettes propres des sprites affichés par les IMAGES d'interface.

    Le pendant de `ui_fill_encoded_sources` pour un sprite : une image dessine
    des tuiles qui citent une sous-palette, il lui faut donc une banque. Sans
    cette collecte, elle sortait avec les couleurs de son voisin — en pratique
    celles de la POLICE, seule occupante connue de la banque d'interface, donc
    une silhouette monochrome au mieux, invisible au pire.

    Le pool compte : une image en cible BG lit `PAL_BG_RAM`, une image en cible
    OBJ lit `PAL_OBJ_RAM`. Les deux pools sont disjoints sur GBA, réclamer dans
    le mauvais laisserait le trou exactement où il était."""
    from core.models.ui_region import TARGET_BG
    rm = int(getattr(scene, "render_mode", 0) or 0)
    want_bg = (pool == "bg")
    out: list[list[int]] = []
    for lay, im in p.scene_ui_images(scene):
        if (lay.resolved_target(im, rm) == TARGET_BG) != want_bg:
            continue
        sp = p.get_sprite(getattr(im, "sprite_name", "") or "")
        cols = _sprite_own_palette(sp)
        if cols:
            out.append(cols)
    return out


def ui_image_sprite_pools(p: Project) -> dict:
    """{nom de sprite: "bg"|"obj"} — le pool où atterrit chaque sprite posé par
    une image d'interface.

    grit convertit un sprite UNE fois pour tout le projet, mais une palette
    RÉFÉRENCÉE ne se lit pas au même endroit selon la cible : `active_bg_
    palettes` ou `active_obj_palettes`, deux listes différentes au même index.
    Quantifier vers la mauvaise donne des tuiles calées sur des couleurs que la
    banque affichée ne contient pas.

    Première cible rencontrée gagne : un même sprite posé dans les deux pools
    ne peut de toute façon être quantifié que vers un seul. C'est au validateur
    de le dire, pas à la conversion de choisir en silence."""
    from core.models.ui_region import TARGET_BG
    out: dict[str, str] = {}
    for scene in p.scenes:
        rm = int(getattr(scene, "render_mode", 0) or 0)
        for lay, im in p.scene_ui_images(scene):
            name = getattr(im, "sprite_name", "") or ""
            if name and name not in out:
                out[name] = ("bg" if lay.resolved_target(im, rm) == TARGET_BG
                             else "obj")
    return out


def _actor_own_palettes(p: Project, scene: Scene) -> list[list[int]]:
    """Palettes propres des ACTEURS de la scène en mode OWN (métadonnées
    sprite.own_palette). Les prefabs poolés de la scène s'y ajoutent via
    `_scene_prefab_own_palettes` — même pool de dédup, cf. `scene_bank_layout`."""
    out: list[list[int]] = []
    for a in scene.actors:
        if not a.active or getattr(a, "pal_bank", OWN_PAL_BANK) != OWN_PAL_BANK:
            continue
        for sp in _owner_sprites(p, a):
            cols = _sprite_own_palette(sp)
            if cols:
                out.append(cols)
    return out


def _scene_prefab_own_palettes(p: Project, scene: Scene) -> list[list[int]]:
    """Palettes propres (mode OWN) des prefabs que CETTE scène poole — racine ET
    parties (ROADMAP v0.17 T5).

    Per-scène depuis que le spawn l'est (T1) : une scène ne réserve de banque OBJ
    que pour les prefabs qu'ELLE spawne, dans SES slots libres, au lieu du slot
    commun à toutes les scènes qu'imposait l'ancien `spawn_X` global. Un prefab
    poolé dans deux scènes peut donc occuper une banque différente dans chacune —
    les tuiles 4bpp ne gravent qu'un index 0-15, la banque venant de `pal_bank`
    à l'OAM (posé au spawn depuis le layout de la scène).

    Racine ET parties : une partie de prefab segmenté (ROADMAP v0.23) porte son
    propre sprite, donc sa propre palette — l'allocation globale d'avant ne
    réservait que la racine, et une partie en mode propre retombait en silence
    sur la banque 0. Ordre déterministe (catalogue de prefabs, racine puis
    parties), dédup par couleurs."""
    out: list[list[int]] = []
    seen: set[tuple] = set()

    def _add(owner):
        if getattr(owner, "pal_bank", OWN_PAL_BANK) != OWN_PAL_BANK:
            return
        for sp in _owner_sprites(p, owner):
            cols = _sprite_own_palette(sp)
            key = tuple(cols)
            if cols and key not in seen:
                seen.add(key)
                out.append(cols)

    for pf in p.prefabs:
        if scene_pool_instances(scene, pf) <= 0:
            continue
        _add(pf)
        for part in (getattr(pf, "children", []) or []):
            _add(part)
    return out


def _bg_own_sources(p: Project, scene: Scene) -> list[Path]:
    """PNG des layers BG en mode OWN de la scène, hors fonds COMPRESSÉS
    (ceux-ci ont déjà leurs propres sous-palettes en métadonnées — gérés à
    part par `_bg_encoded_sources`/allocation par bloc, cf.
    [[project_palette_system_design]])."""
    srcs: list[Path] = []
    for layer in getattr(scene, "background_layers", []):
        if not layer.background_name or getattr(layer, "pal_bank", OWN_PAL_BANK) != OWN_PAL_BANK:
            continue
        ba = p.get_background(layer.background_name)
        if ba and getattr(ba, "tileset", None):
            continue
        png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
        srcs.append(p.background_images_dir / png)
    return srcs


def _bg_encoded_sources(p: Project, scene: Scene) -> list:
    """BackgroundAsset compressés (mode OWN) des layers de la scène, dans
    l'ordre des layers. Chacun peut avoir jusqu'à 16 sous-palettes (une par
    groupe de tuiles) — il lui faut un BLOC de banques contiguës, pas un slot
    unique (cf. `_find_free_block`)."""
    out = []
    for layer in getattr(scene, "background_layers", []):
        if not layer.background_name or getattr(layer, "pal_bank", OWN_PAL_BANK) != OWN_PAL_BANK:
            continue
        ba = p.get_background(layer.background_name)
        if ba and getattr(ba, "tileset", None):
            out.append(ba)
    return out


def bg_animation_sources(p: Project, scene: Scene) -> list:
    """Animés POSÉS sur les fonds des calques de la scène.

    Un animé dessine ses propres tuiles, qui citent leurs propres sous-palettes :
    il lui faut son bloc de banques, exactement comme au fond qui l'héberge. Sans
    cette collecte il sortirait avec les couleurs de son hôte — une cascade aux
    teintes du rocher derrière elle, sans rien pour signaler l'erreur.

    Le placement vit chez l'hôte : c'est donc en parcourant les fonds des calques
    qu'on trouve les animés, jamais l'inverse (cf. codegen/bg_anim)."""
    from codegen.bg_anim import host_palettes

    class _Synth:
        """Porteur de palette pour l'allocateur. Une fusion n'appartient à aucun
        asset : ses couleurs viennent de l'hôte ET de l'animé, elle n'est donc
        pas dans `ba.palettes` de l'un ni de l'autre. Le bloc est dédupliqué par
        contenu, comme pour les fonds — deux fusions aux mêmes couleurs partagent
        leur banque."""
        def __init__(self, name, pal):
            self.name, self.palettes, self.bpp = name, [pal], 4

    out = []
    for layer in getattr(scene, "background_layers", []):
        if not getattr(layer, "background_name", ""):
            continue
        host = p.get_background(layer.background_name)
        if host is None or not getattr(host, "tileset", None):
            continue
        for i, pal in enumerate(host_palettes(p, host)):
            out.append(_Synth(f"{host.name}#anim{i}", pal))
    return out


def _scene_font_palettes(p: Project, scene: Scene) -> list[tuple]:
    """(nom de police, pal_bank, contenu de banque) pour chaque police dont la
    scène a un usage LIBRE — un texte qui n'est enfant d'aucun conteneur à fond.

    Une police est un asset qui porte ses couleurs comme un sprite
    (`font_palette`), et sa banque se traque dans la sélection de la scène. Mais
    un texte ENFANT d'un conteneur à fond hérite de la banque de ce conteneur
    (cf. `region_fill_container`, « le fond le plus proche gagne ») : sa police ne
    prend alors AUCUN slot. Une police utilisée uniquement dans des conteneurs
    n'apparaît donc pas ici — le conteneur, lui, est déjà tracé (fond couleur =
    une palette de scène, nine-slice/background = son bloc de banques).

    `pal_bank` = `OWN_PAL_BANK` (palette propre à allouer) ou un slot de scène
    (override), lu via `scene_font_pal_bank`. Police par défaut d'abord (ordre
    stable). Une écriture libre (`text.draw`) ou un script indécidable comptent
    comme un usage libre de la police PAR DÉFAUT — repli sûr (cf. ROADMAP)."""
    from core.models.ui_region import region_fill_container
    from codegen.font_emit import (
        encodable_project_fonts,
        scene_font_names, default_font_name, font_palette, scene_writes_free)

    fonts = encodable_project_fonts(p)
    if not fonts:
        return []
    by_name = {f.name: f for f in fonts}
    default = default_font_name(fonts, scene, getattr(p.settings, "default_font", ""))
    project_default = getattr(p.settings, "default_font", "") or ""

    # Polices à usage LIBRE : celles d'un texte hors conteneur à fond. Un texte
    # sans `font_name` prend la police par défaut de la scène.
    free: set[str] = set()
    for lay, el in p.scene_ui_slots(scene):
        if region_fill_container(lay, el) is None:
            free.add(getattr(el, "font_name", "") or default)
    # Écriture libre (`text.draw`) ou script indécidable : la police d'init
    # (défaut) a un usage libre potentiel, celui qu'obtient un `text.draw` sans
    # `text.set_font`.
    if default and (scene_writes_free(p, scene)
                    or scene_font_names(p, scene, default) is None):
        free.add(default)

    # Le runtime remplace la *police par défaut du projet* par celle de la
    # langue active. Ce n'est pas une police explicitement choisie par le texte
    # : elle conserve donc la même sélection de palette que le défaut logique
    # (clé ``""`` dans Scene.font_pal_banks). Sans cela, le substitut tombait
    # dans le cas « seulement imbriqué » et lisait la banque 15, même lorsqu'un
    # texte libre avait choisi une banque de scène dans l'inspecteur.
    language_defaults: set[str] = set()
    if default == project_default and default in free:
        language_defaults = {
            getattr(language, "default_font", "")
            for language in getattr(p.settings, "languages", [])
            if getattr(language, "default_font", "")
        }
        free |= language_defaults

    ordered = ([default] if default in free and default in by_name else []) \
        + sorted(n for n in free if n != default and n in by_name)

    out: list[tuple] = []
    for name in ordered:
        f = by_name[name]
        png = p.asset_abs(f.asset) if f.asset else None
        if not png and getattr(f, "raster_glyphs", None) is None:
            continue
        cols = font_palette(f, png)
        if cols:
            palette_name = default if name in language_defaults else name
            out.append((name, scene_font_pal_bank(scene, palette_name, default), cols))
    return out


def _ui_fill_containers(p: Project, scene: Scene) -> list[tuple]:
    """(conteneur, BackgroundAsset compressé) pour chaque conteneur nine-slice/
    background de la scène. Extrait commun à `ui_fill_encoded_sources`, qui
    n'en garde que l'asset (ce dont `scene_bank_layout` a besoin), et à
    `_ui_container_entries`, qui a aussi besoin du conteneur — pour NOMMER
    l'instance dans la carte « Palettes actives » de l'inspecteur."""
    from core.models.ui_region import can_fill, FILL_NINE, FILL_BG
    out = []
    for _lay, el in p.scene_ui_elements(scene):
        if not can_fill(el):
            continue
        fk = getattr(el, "fill_kind", "")
        if fk not in (FILL_BG, FILL_NINE):
            continue
        # Les deux modes citent DIRECTEMENT un BackgroundAsset : un cadre
        # étirable est un fond d'interface qui porte ses marges (kind `ui`),
        # plus un asset intermédiaire à déréférencer.
        name = getattr(el, "fill_asset", "")
        ba = p.get_background(name) if name else None
        if ba is not None and getattr(ba, "tileset", None):
            out.append((el, ba))
    return out


def ui_fill_encoded_sources(p: Project, scene: Scene) -> list:
    """BackgroundAsset compressés servant de FOND à un conteneur d'UI de la
    scène (`UIContainer.fill_kind` nine-slice ou background).

    Un fond d'UI s'affiche exactement comme un layer : ses tuiles citent des
    sous-palettes, il lui faut donc son bloc de banques. Sans cette collecte,
    une image utilisée UNIQUEMENT comme remplissage n'obtiendrait aucune banque
    et sortirait avec les couleurs du voisin."""
    return [ba for _el, ba in _ui_fill_containers(p, scene)]


def _bg_palettes_key(ba) -> tuple:
    """Clé de dédup d'un fond compressé = contenu exact de ses sous-palettes
    (deux fonds avec les mêmes couleurs partagent le même bloc de banques)."""
    return tuple(tuple(pal) for pal in getattr(ba, "palettes", None) or [])


def _find_free_block(slots: list, n: int) -> Optional[int]:
    """Offset le PLUS HAUT (0-15) tel que les n banques [offset, offset+n) soient
    toutes libres — None si aucun bloc contigu de cette taille n'existe.

    Les palettes propres partent du bout haut de PAL_RAM et descendent vers 0,
    tandis que les palettes de scène occupent leurs index fixes en partant du
    bas : elles se rencontrent au milieu, la scène l'emporte, et la banque 0
    (l'index 0 de PAL_BG_RAM = le backdrop de la scène) reste libre tant que la
    scène ne déborde pas."""
    n = max(1, n)
    for start in range(16 - n, -1, -1):
        if all(slots[start + i] is None for i in range(n)):
            return start
    return None


def _sprite_bank_content(cols) -> list[int]:
    """Contenu de banque pour une palette propre de SPRITE — `sprite.own_palette`,
    stockée SANS le slot 0 réservé (cf. own_palette_from_source : "index 1..N,
    index 0 transparent implicite, pas inclus").

    Le préfixe ne dépend PAS du pool : l'index 0 d'une tuile 4bpp est
    transparent en BG comme en OBJ, et c'est cette forme 16-slots que
    `effective_palette_colors` rend à grit, donc celle sur laquelle
    `remap_tiles_to_bank` cale les index des tuiles. Écrire la banque sans le
    préfixe alors que les tuiles ont été remappées avec décale chaque pixel
    d'un cran : le sprite sort en couleurs voisines."""
    return [RESERVED_SLOT_COLOR] + list(cols)


def _own_bank_content(cols, pool: str) -> list[int]:
    """Contenu à écrire dans une banque matérielle pour une palette propre,
    quand la FORME de `cols` se déduit du pool : métadonnées sprite en OBJ
    (sans slot 0, à préfixer), extraction PNG en BG (`own_palette()`,
    extract_palette_from_image, qui inclut déjà ce slot — ne pas le préfixer
    une 2e fois).

    Cette déduction ne vaut donc que là où le pool BG ne reçoit QUE du BG
    legacy. Un sprite posé en cible BG (image d'UI) est l'exception : sa liste
    vient des métadonnées, pas d'une extraction — `_sprite_bank_content`."""
    return _sprite_bank_content(cols) if pool == "obj" else list(cols)


def scene_bank_layout(p: Project, scene: Scene, pool: str) -> SceneBankLayout:
    """Alloue les 16 banques d'un pool ("obj"|"bg") pour une scène :
    (1) palettes référencées à leur index fixe ; (2) pour OBJ, palettes propres
    des acteurs, des prefabs QUE LA SCÈNE POOLE (per-scène depuis T1, cf.
    `_scene_prefab_own_palettes`) et des images d'UI, dans les slots libres
    (dédup par couleurs) ; (3) pour BG, fonds/animés/polices."""
    # Mémoïsation à portée de contexte (cf. `scene_layout_cache`) : sans contexte
    # actif, `_layout_cache` est None et rien n'est caché — le build recalcule.
    if _layout_cache is not None:
        _ck = (id(p), id(scene), pool)
        _hit = _layout_cache.get(_ck)
        if _hit is not None:
            return _hit

    # (clé de dédup, contenu de banque) : la clé reste la liste BRUTE — c'est
    # elle que `bank_index` reçoit de ses appelants — mais le contenu écrit dans
    # la banque dépend de la FORME de la source, cf. `_own_bank_content`.
    if pool == "obj":
        active = list(getattr(scene, "active_obj_palettes", []))[:16]
        # Acteurs, prefabs poolés PAR CETTE SCÈNE (T5) et images d'UI : tous des
        # consommateurs de palette propre de la scène, même pool de dédup. Depuis
        # que le spawn est per-scène, un prefab n'est plus un cas à part avec un
        # slot global — c'est un OWN de plus, alloué dans les slots libres d'ici.
        own_color_lists = [
            (c, _own_bank_content(c, "obj"))                      # métadonnées sprite
            for c in (_actor_own_palettes(p, scene)
                      + _scene_prefab_own_palettes(p, scene)
                      + ui_image_own_palettes(p, scene, "obj"))]
        encoded_assets = []
    else:
        active = list(getattr(scene, "active_bg_palettes", []))[:16]
        # Deux formes se croisent ici : le BG legacy porte déjà son slot 0
        # (extraction PNG), le sprite d'une image d'UI ne le porte pas
        # (métadonnées). D'où deux constructeurs de contenu et non un seul.
        own_color_lists = (
            [(c, _own_bank_content(c, "bg"))                      # BG legacy: extraction
             for c in (own_palette(png) for png in _bg_own_sources(p, scene))]
            + [(c, _sprite_bank_content(c))                       # métadonnées sprite
               for c in ui_image_own_palettes(p, scene, "bg")]
            # Polices en mode propre : `font_palette` rend DÉJÀ le contenu de
            # banque (index 0 transparent + encre), donc clé de dédup = contenu.
            # Une police partageant ses couleurs avec un fond partage sa banque.
            + [(cols, cols) for _n, pb, cols in _scene_font_palettes(p, scene)
               if pb == OWN_PAL_BANK])
        # Layers + animés posés dessus + fonds de conteneurs d'UI : tous
        # affichent des tuiles qui citent des sous-palettes, tous ont donc besoin
        # de leur bloc. Les animés viennent juste après leurs hôtes — l'ordre
        # d'allocation est l'ordre de cette liste, et un animé dont l'hôte a
        # échoué n'aurait rien à colorier.
        encoded_assets = (_bg_encoded_sources(p, scene)
                          + bg_animation_sources(p, scene)
                          + ui_fill_encoded_sources(p, scene))

    slots: list[Optional[list[int]]] = [None] * 16
    for i, name in enumerate(active):
        bank = p.get_palette(name) if name else None
        if bank and bank.colors:
            slots[i] = list(bank.colors)

    own_slot: dict[tuple, Optional[int]] = {}

    # Fonds compressés (OWN) : bloc de banques CONTIGUËS par asset (N sous-
    # palettes), dédupliqué par contenu exact. Alloué avant les palettes
    # propres à slot unique ci-dessous (moins de fragmentation, les blocs sont
    # plus gros et plus contraints).
    bg_block: dict[tuple, Optional[int]] = {}
    for ba in encoded_assets:
        key = _bg_palettes_key(ba)
        if key in bg_block:
            continue
        if getattr(ba, "bpp", 4) == 8:
            # 8bpp : UNE palette de 256 couleurs qui occupe LES 16 banques de
            # PAL_BG_RAM (le pal_bank des SE est ignoré par le hardware). Ne peut
            # donc PAS cohabiter avec d'autres palettes BG : si des banques sont
            # déjà prises (référencées / autre asset), c'est un débordement.
            pal256 = list(key[0]) if key else []
            if all(s is None for s in slots):
                for i in range(16):
                    chunk = pal256[i * 16:(i + 1) * 16]
                    slots[i] = list(chunk) + [0] * (16 - len(chunk))
                bg_block[key] = 0
            else:
                bg_block[key] = None   # débordement (cohabitation impossible)
            continue
        n = min(len(key), 16)
        start = _find_free_block(slots, n)
        bg_block[key] = start
        if start is not None:
            for i in range(n):
                slots[start + i] = list(key[i])

    # Acteurs/layers de la scène : slots restants.
    for cols, bank_cols in own_color_lists:
        if not cols:
            continue
        key = tuple(cols)
        if key in own_slot:
            continue
        # Bout haut d'abord (15 → 0), cf. `_find_free_block` : la banque 0 =
        # backdrop reste libre, et la palette de scène (index bas fixe) gagne
        # tout conflit puisqu'elle est déjà posée quand on cherche ici.
        free = next((j for j in range(15, -1, -1) if slots[j] is None), None)
        own_slot[key] = free
        if free is not None:
            slots[free] = list(bank_cols)

    # Banque 0 de secours : uniquement en cas de VRAI débordement — un asset
    # (palette propre ou bloc de fond) qui n'a trouvé aucune banque libre retombe
    # sur la banque 0 au codegen ; on la remplit alors d'une palette déterministe
    # pour qu'il affiche des couleurs prévisibles plutôt que le backdrop ou du
    # garbage. Sans débordement, la banque 0 reste LIBRE : c'est sa place normale
    # depuis que les palettes propres s'allouent par le bout haut (elle porte le
    # backdrop de la scène, cf. `_find_free_block`).
    overflow = (any(v is None for v in own_slot.values())
                or any(v is None for v in bg_block.values()))
    if slots[0] is None and overflow:
        slots[0] = list(DEFAULT_PAL_BANK_COLORS)

    layout = SceneBankLayout(slots, own_slot, bg_block)
    if _layout_cache is not None:
        _layout_cache[(id(p), id(scene), pool)] = layout
    return layout


def scene_font_runtime_banks(p: Project, scene: Scene) -> dict:
    """{nom de police: (banque, own)} à poser par `text_set_font_pal` dans
    `scene_init`, pour les polices que la scène CHARGE. Trois cas :

    - usage LIBRE en mode propre → (banque allouée par `scene_bank_layout`, 1) :
      la police charge sa palette PNG dans sa banque, comme un sprite ;
    - usage LIBRE overridé      → (slot de scène, 0) : elle lit une palette de la
      scène, sans rien charger ;
    - usage SEULEMENT imbriqué   → (15, 0) : elle ne charge rien, chaque texte
      prenant la banque de son conteneur (cf. `text_set_region_backdrop/color`).

    Un substitut de langue du défaut suit ce même choix de banque : il reste le
    défaut logique du texte, et non une police imbriquée distincte. Source unique
    lue par l'émission de `scene_init`."""
    from codegen.font_emit import (
        scene_font_names, default_font_name, FONT_PAL_BANK, encodable_project_fonts)

    fonts = encodable_project_fonts(p)
    if not fonts:
        return {}
    by_name = {f.name: f for f in fonts}
    default = default_font_name(fonts, scene, getattr(p.settings, "default_font", ""))
    layout = scene_bank_layout(p, scene, "bg")

    free = {name: (pb, cols) for name, pb, cols in _scene_font_palettes(p, scene)}
    names = scene_font_names(p, scene, default)
    if names is None:
        names = {default} if default else set()

    out: dict = {}
    for name in set(names) | set(free):
        if name not in by_name:
            continue
        if name in free:
            pb, cols = free[name]
            if pb >= 0:
                out[name] = (pb, 0)                  # override → palette de scène
            else:
                bank = layout.bank_index(OWN_PAL_BANK, cols)   # mode propre
                out[name] = (bank if bank is not None else 0, 1)
        else:
            out[name] = (FONT_PAL_BANK, 0)           # seulement imbriqué : rien à charger
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  Vue éditeur — surface l'allocation par scène dans l'inspecteur
# ─────────────────────────────────────────────────────────────────────────────
# `scene_bank_layout` (ci-dessus) résout l'allocation AU BUILD, en silence. Ces
# structures remontent la MÊME information dans l'éditeur (carte PALETTES
# ACTIVES) : les palettes de la scène (éditables) suivies des palettes propres
# des assets (grisées), pour que l'utilisateur voie et pilote les 16 banques au
# lieu d'une boîte noire. Aucun champ de modèle nouveau : l'état « override » se
# lit dans `pal_bank` (OWN vs slot référencé), la palette propre reste toujours
# disponible (`sprite.own_palette`, modèle non-destructif).


@dataclass
class InstanceRef:
    """Un consommateur de palette propre dans la scène. Selon `kind`, `obj` et la
    façon de l'overrider diffèrent :
    - "actor" / "bg_layer" : `obj` est l'Actor / BackgroundLayer réel — muter
      `obj.pal_bank` override (ou restaure) cette instance ;
    - "ui_image" / "ui_container" : élément d'UI qui pose un sprite — pas de
      `pal_bank`, jamais overridable (toujours OWN) ;
    - "font" : `obj` est le NOM de la police — l'override vit sur la scène
      (`Scene.font_pal_banks`, clé résolue par `font_pal_key`), pas sur `obj`."""
    kind: str          # "actor" | "bg_layer" | "ui_image" | "ui_container" | "font"
    obj: object        # l'objet à muter, ou le nom de police pour kind "font"
    label: str         # nom lisible (acteur / "BG{slot}" / "{police} (police)")
    pal_bank: int      # état courant : OWN_PAL_BANK, slot scène, ou sentinel conteneur


@dataclass
class ScenePaletteEntry:
    """Une palette ACTIVE de la scène (éditable). `slot` = index de banque
    hardware (== index dans active_*_palettes, valeur de pal_bank pour la
    référencer)."""
    slot: int
    name: str
    colors: list


@dataclass
class AssetPaletteEntry:
    """Une palette PROPRE d'asset partagée par ≥1 instance de la scène,
    dédupliquée par couleurs. `state` :
    - "own"      → aucune instance overridée : occupe une banque libre (grisée) ;
    - "override" → toutes les instances pointent vers une palette de scène
      (`ref_slot`) : ne consomme PAS de banque en plus (pointeur)."""
    own_colors: list               # forme banque hardware (clé de dédup + rendu grisé)
    instances: list                # list[InstanceRef]
    state: str = "own"             # "own" | "override"
    ref_slot: Optional[int] = None # override : slot scène ciblé
    bank_span: int = 1             # nb de banques occupées (>1 pour fonds compressés)
    overridable: bool = True       # False pour fonds compressés/bitmap (bloc multi-banques)


@dataclass
class ScenePaletteView:
    """Vue ordonnée d'un pool ("obj"|"bg") pour une scène : palettes de scène
    (contiguës depuis slot 0) puis palettes propres d'asset (grisées/override).
    `banks_used` = banques réellement occupées (scène + assets « own », spans
    compris) — le bouton « + » n'apparaît que s'il reste de la place."""
    pool: str
    scene_entries: list            # list[ScenePaletteEntry]
    asset_entries: list            # list[AssetPaletteEntry]
    banks_used: int

    def can_add(self) -> bool:
        return self.banks_used < 16


def _obj_instance_pairs(p: Project, scene: Scene) -> list[tuple[tuple, InstanceRef]]:
    """(clé couleurs, InstanceRef) pour chaque acteur actif à composant sprite
    ayant une palette propre. La clé est la forme banque hardware (préfixe slot
    0 réservé) — cohérente avec scene_bank_layout."""
    out: list[tuple[tuple, InstanceRef]] = []
    for a in scene.actors:
        if not getattr(a, "active", True):
            continue
        for sp in _owner_sprites(p, a):
            cols = _sprite_own_palette(sp)
            if not cols:
                continue
            key = tuple(_own_bank_content(cols, "obj"))
            out.append((key, InstanceRef("actor", a, a.name,
                                         getattr(a, "pal_bank", OWN_PAL_BANK))))
    return out


def _bg_instance_pairs(p: Project, scene: Scene) -> list[tuple[tuple, InstanceRef]]:
    """(clé couleurs, InstanceRef) pour chaque layer BG legacy (non compressé)
    ayant une palette propre extractible. Les fonds compressés/bitmap sont
    exclus ici — ils occupent un BLOC de banques et sont remontés à part
    (non-overridables pour l'instant, cf. scene_palette_view)."""
    out: list[tuple[tuple, InstanceRef]] = []
    for layer in getattr(scene, "background_layers", []):
        if not getattr(layer, "background_name", ""):
            continue
        ba = p.get_background(layer.background_name)
        if ba and getattr(ba, "tileset", None):
            continue   # compressé : géré comme entrée de bloc
        png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
        cols = own_palette(p.background_images_dir / png)
        if not cols:
            continue
        key = tuple(_own_bank_content(cols, "bg"))
        out.append((key, InstanceRef("bg_layer", layer, f"BG{layer.bg_slot}",
                                     getattr(layer, "pal_bank", OWN_PAL_BANK))))
    return out


def _bg_encoded_entries(p: Project, scene: Scene) -> list[AssetPaletteEntry]:
    """Entrées d'asset pour les fonds COMPRESSÉS de la scène : chacun occupe un
    BLOC de N banques contiguës (ses N sous-palettes, SE_PALBANK par tuile) —
    pas un slot unique. Non-overridables (on ne remappe pas un bloc vers une
    seule palette de scène). Dédupliqués par contenu exact des sous-palettes ;
    l'affichage échantillonne la 1ère sous-palette.

    DEUX sources fusionnées dans le MÊME pool de dédup — layers ET conteneurs
    d'UI (conteneurs nine-slice/background) — exactement comme `scene_bank_
    layout` fusionne `_bg_encoded_sources` et `ui_fill_encoded_sources` dans un
    seul `encoded_assets` avant d'allouer : un fond posé À LA FOIS comme layer
    et comme remplissage de conteneur ne réclame qu'UN bloc, jamais deux. Les
    tenir à part aurait aussi laissé les conteneurs invisibles ici alors que
    l'allocateur leur réserve déjà des banques au build."""
    groups: dict[tuple, tuple] = {}   # key -> (ba, [InstanceRef])
    order: list[tuple] = []

    def add(ba, ref: InstanceRef):
        key = _bg_palettes_key(ba)
        if key not in groups:
            groups[key] = (ba, [])
            order.append(key)
        groups[key][1].append(ref)

    for layer in getattr(scene, "background_layers", []):
        if not getattr(layer, "background_name", ""):
            continue
        ba = p.get_background(layer.background_name)
        if not (ba and getattr(ba, "tileset", None)):
            continue
        add(ba, InstanceRef("bg_layer", layer, f"BG{layer.bg_slot} ({layer.background_name})",
                            getattr(layer, "pal_bank", OWN_PAL_BANK)))
    for el, ba in _ui_fill_containers(p, scene):
        add(ba, InstanceRef("ui_container", el, f"{el.name} (conteneur)", OWN_PAL_BANK))

    out: list[AssetPaletteEntry] = []
    for key in order:
        ba, refs = groups[key]
        pals = getattr(ba, "palettes", None) or []
        out.append(AssetPaletteEntry(
            own_colors=list(pals[0]) if pals else [],
            instances=refs, state="own", ref_slot=None,
            bank_span=max(1, len(pals)), overridable=False,
        ))
    return out


def _ui_image_pairs(p: Project, scene: Scene, pool: str) -> list[tuple[tuple, InstanceRef]]:
    """(clé couleurs, InstanceRef) pour chaque élément d'UI qui pose un SPRITE
    dans ce pool — `UIImage` et `UIContainer` à fond sprite (`lay.images`, cf.
    `UILayout.images`). Le pendant, côté vue éditeur, de `ui_image_own_
    palettes` côté allocateur — MÊME format de retour que `_obj_instance_
    pairs`/`_bg_instance_pairs`, pour rejoindre leur pool de dédup : un acteur
    et une image d'UI aux couleurs identiques partagent une banque au build
    (`scene_bank_layout` fusionne les deux listes avant de dédupliquer), les
    tenir à part ici aurait affiché deux entrées pour une seule banque réelle.

    Ni `UIImage` ni `UIContainer` ne portent de `pal_bank` (aucune surcharge
    possible, contrairement à un acteur ou un layer) : toujours OWN."""
    from core.models.ui_region import TARGET_BG, can_fill
    rm = int(getattr(scene, "render_mode", 0) or 0)
    want_bg = (pool == "bg")
    out: list[tuple[tuple, InstanceRef]] = []
    for lay, im in p.scene_ui_images(scene):
        if (lay.resolved_target(im, rm) == TARGET_BG) != want_bg:
            continue
        cols = _sprite_own_palette(p.get_sprite(getattr(im, "sprite_name", "") or ""))
        if not cols:
            continue
        # Palette de SPRITE dans les deux pools — cf. `_sprite_bank_content` ;
        # la vue montre alors la banque 16 slots que la ROM écrit vraiment.
        key = tuple(_sprite_bank_content(cols))
        label = f"{im.name} (conteneur)" if can_fill(im) \
                else f"{im.name} (image UI)"
        out.append((key, InstanceRef("ui_image", im, label, OWN_PAL_BANK)))
    return out


def scene_palette_view(p: Project, scene: Scene, pool: str) -> ScenePaletteView:
    """Construit la vue éditeur d'un pool pour une scène (cf. ScenePaletteView).

    Dérivé du modèle, sans mutation : énumère les instances de la scène,
    regroupe par palette propre (dédup couleurs) et lit `pal_bank` pour l'état
    own/override. Ordre stable (première apparition)."""
    active = list(getattr(scene, f"active_{pool}_palettes", []))

    scene_entries: list[ScenePaletteEntry] = []
    for i, name in enumerate(active):
        if not name:
            continue
        bank = p.get_palette(name)
        scene_entries.append(ScenePaletteEntry(
            slot=i, name=name,
            colors=list(bank.colors) if bank and bank.colors else [],
        ))

    pairs = _obj_instance_pairs(p, scene) if pool == "obj" else _bg_instance_pairs(p, scene)
    # Images d'UI (et conteneurs à fond sprite) : MÊME pool de dédup que les
    # acteurs/layers, cf. `_ui_image_pairs`.
    pairs = pairs + _ui_image_pairs(p, scene, pool)
    # Polices : la scène traque leur palette comme celle d'un sprite. Cible BG
    # seulement — une bande de texte OBJ se décide plus tard (cf. ROADMAP). MÊME
    # pool de dédup : une police et un fond aux mêmes couleurs partagent la banque.
    if pool == "bg":
        pairs = pairs + [(tuple(cols), InstanceRef("font", name, f"{name} (police)", pb))
                         for name, pb, cols in _scene_font_palettes(p, scene)]

    groups: dict[tuple, list[InstanceRef]] = {}
    order: list[tuple] = []
    for key, ref in pairs:
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(ref)

    asset_entries: list[AssetPaletteEntry] = []
    for key in order:
        refs = groups[key]
        own_refs = [r for r in refs if r.pal_bank == OWN_PAL_BANK]
        if own_refs:
            state, ref_slot = "own", None
        else:
            # Toutes overridées : slot de référence commun (elles partagent la
            # même palette propre, donc convergent normalement vers le même).
            state, ref_slot = "override", refs[0].pal_bank
        # Ni `UIImage` ni `UIContainer` ne portent de `pal_bank` : un groupe
        # composé UNIQUEMENT d'images d'UI n'a donc rien à overrider — le
        # bouton mentirait (il changerait un attribut que rien ne relit,
        # cf. `_ui_image_pairs`). Un groupe MIXÉ (acteur/layer + image de
        # mêmes couleurs) reste overridable : c'est l'instance overridable
        # qui compte, l'image suit sans rien casser.
        overridable = any(r.kind != "ui_image" for r in refs)
        asset_entries.append(AssetPaletteEntry(
            own_colors=list(key), instances=refs, state=state, ref_slot=ref_slot,
            overridable=overridable,
        ))

    # BG compressé : blocs de banques (non-overridables) après les entrées à
    # slot unique, dans l'ordre des layers — `_bg_encoded_entries` y fusionne
    # aussi les conteneurs d'UI (nine-slice/background), cible BG uniquement
    # (`FILL_TARGETS` ne leur permet pas l'OBJ, cf. core/models/ui_region.py).
    if pool == "bg":
        asset_entries += _bg_encoded_entries(p, scene)

    banks_used = (len(scene_entries)
                  + sum(e.bank_span for e in asset_entries if e.state == "own"))
    return ScenePaletteView(pool, scene_entries, asset_entries, banks_used)
