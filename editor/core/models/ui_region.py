"""UILayout — géométrie AUTHORÉE des éléments d'interface d'une scène.

**Quatre types.** Un `UIText` (là où du texte se pose), un `UIContainer` (le
conteneur), un `UIList` (un conteneur qui se PARCOURT) et un `UIImage` (un sprite
à état). Les deux conteneurs dessinent un fond — c'est une CAPACITÉ (`FillMixin`,
`can_fill`), pas un type.

`UIList` a d'abord été un drapeau du conteneur (`is_list`, v0.22). Le
motif tenait — « le moteur prend la NAVIGATION, pas la mise en page » — mais pas
le rangement : le C avait déjà `UIListInfo` et ses sept fonctions, l'API disait
déjà `list.*`, et `to_dict` écrivait cinq clés selon un booléen. Un objet qui n'a
pas la même forme selon un champ est un type qui s'ignore. Cf. `UIList`.

Le type « zone de texte » a existé à côté de `UIText` et a été RETIRÉ : les deux
portaient la même géométrie, le même ancrage, la même allocation OBJ et la même
entrée de `g_ui_regions`, et ne différaient que par l'écrivain — le script pour
l'une, `scene_init` pour l'autre. Ce n'était pas deux types mais un type et un
champ vide : un `UIText` sans `text_key` EST une zone que le script remplit.
Deux widgets pour ça obligeaient à choisir avant de savoir, et à convertir
ensuite. Cf. `UIText`.

**Un élément de texte ne dessine rien.** Il dit *où* le texte se pose, jamais à
quoi il ressemble — même contrat que la window matérielle (`WindowSlot`), qui
est un pochoir et pas un cadre. C'est pour ça que le mot était « région » et non
« frame » : dans GB Studio, `frame.png` EST l'image de bordure 9-slice, et le
mot promettrait donc un dessin que le moteur ne fait pas. Le vocabulaire est
celui que fixe ROADMAP v0.3.2 (« région, layer, tilemap — jamais dialogue,
message, textbox ») ; `frame` collisionnerait de surcroît avec les frames
d'animation (`Sprite.frame_w`) et la frame vidéo.

**Ce qui reste au script.** L'élément porte la GÉOMÉTRIE, pas l'enchaînement :
rien ici ne dit quel texte s'affiche quand, ni sur quel événement. Un contenu
authoré est posé une fois à l'init ; tout ce qui CHANGE reste au Lua
(`interface.draw_text("boite_bas", "village_garde")`) — c'est ce qui empêche cet objet
de devenir un éditeur de dialogue par accident, refus tenu depuis ROADMAP
v0.3.2.

**L'ancrage et la cible appartiennent au nœud, pas à l'élément (v0.25).** Un nœud
`Interface` (`UILayout`) porte UN `anchor` + UN `target` ; tout son sous-arbre en
hérite. Une scène qui a besoin de deux chemins matériels pose deux nœuds. Ces
deux réglages ne sont pas libres : ils contraignent la mémoire.

  écran  — fixe sur 240×160. Cible BG. C'est ce que `Scene.text_bg` est déjà.
  monde  — défile avec la caméra. Cible BG, mais le cas le plus dur : la région
           entre et sort de la fenêtre de tilemap, il faut la réécrire au wrap.
  actor  — suit un acteur à l'offset près. **Cible OBJ, sans alternative** : un
           actor bouge au pixel, la grille BG avance par 8, une bulle en texte
           BG sauterait donc par crans de 8 px. Ce n'est pas une préférence de
           qualité, c'est une impossibilité — d'où `forced_target()`, calculé une
           fois sur le nœud, et l'inspecteur affiche la cible imposée au lieu de
           laisser composer une combinaison qui ne peut pas exister.

**Tout est stocké en PIXELS**, une seule unité, comme `WindowSlot`. Le BG exige
un alignement à la tuile : c'est `snap_to_tile()` qui le pose, pas le format de
stockage — sinon on aurait deux unités selon la cible et un champ dont il
faudrait deviner le sens.

**Pas de `FieldValue` ici, volontairement.** Les champs numériques de composant
acceptent une référence de variable (`{"var": ...}`) ; une région ne le peut
pas. Tout l'intérêt de déclarer la géométrie est que l'empreinte VRAM devienne
connue AVANT le build (cf. `font_emit.scene_text_tiles`) : une position qui ne
se connaît qu'au runtime rendrait ce chiffre faux, c'est-à-dire pire
qu'absent. Une position calculée reste possible — par `text:draw(tx, ty, id)`,
qui ne disparaît pas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models.resource import Resource

TILE = 8

# Ancrages
ANCHOR_SCREEN = "screen"   # Fixe sur l'écran.
ANCHOR_WORLD  = "world"    # défile avec la caméra (conteneur posé dans le décor)
ANCHOR_ACTOR  = "actor"    # suit un acteur (bulle) — impose la cible OBJ

ANCHORS = (ANCHOR_SCREEN, ANCHOR_WORLD, ANCHOR_ACTOR)

# Cibles de rendu
# Les cibles BG et OBJ utilisent des budgets VRAM distincts.
TARGET_BG  = "bg"
TARGET_OBJ = "obj"

TARGETS = (TARGET_BG, TARGET_OBJ)

ALIGNS = ("left", "center", "right")

# Types d'élément
# Une mise en page est une liste ordonnée : son ordre fixe l'empilement et l'arbre.
KIND_CONTAINER  = "container"  # Groupe ; une racine porte l'ancrage.
KIND_LIST   = "list"     # conteneur qui se PARCOURT — ses enfants sont ses rangées
KIND_TEXT   = "text"     # texte (authoré ET/OU écrit par un script) — feuille
KIND_IMAGE  = "image"    # sprite à état posé sur l'interface — feuille

# Types écrits dans les nouveaux fichiers.
KINDS = (KIND_CONTAINER, KIND_LIST, KIND_TEXT, KIND_IMAGE)

# Types hérités, lus seulement pour migrer les anciens fichiers.
KIND_REGION = "region"
KIND_PANEL_LEGACY = "panel"

# Types qui occupent une entrée de `g_ui_regions`.
KIND_SLOTS = (KIND_TEXT,)

# Fonds de conteneur
# Un fond décrit l'apparence du conteneur, indépendamment de sa géométrie.
FILL_NONE   = "none"
FILL_COLOR  = "color"
FILL_NINE   = "nine_slice"
FILL_BG     = "background"
FILL_SPRITE = "sprite"
FILL_KINDS = (FILL_NONE, FILL_COLOR, FILL_NINE, FILL_BG, FILL_SPRITE)

# Fonds réellement pris en charge par cible de rendu.
_FILL_TARGETS = {
    FILL_NONE:   (TARGET_BG, TARGET_OBJ),
    FILL_COLOR:  (TARGET_BG,),
    FILL_NINE:   (TARGET_BG,),
    FILL_BG:     (TARGET_BG,),
    FILL_SPRITE: (TARGET_OBJ,),
}


def fill_allowed(fill_kind: str, target: str) -> bool:
    """Ce mode de fond est-il compatible avec cette cible de rendu ?"""
    return target in _FILL_TARGETS.get(fill_kind, ())


def can_fill(el) -> bool:
    """Cet élément peut-il dessiner un FOND ? (les conteneurs : conteneur, liste)

    La question que posent l'allocateur de palettes, le validateur et les
    émetteurs de fond. Ils la posaient sous la forme `kind == KIND_CONTAINER`, ce qui
    demandait le TYPE pour obtenir la CAPACITÉ — juste tant qu'un seul type en
    portait une, et faux le jour où la liste a gagné un fond. Cf. `FillMixin`."""
    return bool(getattr(el, "can_fill", False))


def region_fill_container(lay, el):
    """Le conteneur dont CETTE zone de texte prend le fond, ou None.

    Le fond le plus PROCHE gagne, d'où l'arrêt au premier ancêtre qui en porte
    un : un conteneur Color posé entre la zone et un nine-slice plus lointain
    masque ce dernier de ses tuiles pleines, et recomposer le cadre sous le
    texte montrerait un cadre que rien n'affiche.

    Un seul endroit pour cette règle — le codegen l'émet (`scene_region_colors`
    pour un aplat, `scene_region_backdrops` pour une carte), la banque de
    palettes la lit (`palette_alloc`) et l'inspecteur la montre : c'est AUSSI la
    banque d'encre qu'un texte imbriqué PREND (RegionFill.bank au runtime), là où
    un texte libre lit celle de sa police. La laisser réécrire ailleurs, c'est se
    garantir qu'un jour une zone ait deux fonds, ou aucun."""
    for anc_name in lay.ancestors(el.name):
        anc = lay.get(anc_name)
        if not can_fill(anc):
            continue
        if getattr(anc, "fill_kind", FILL_NONE) == FILL_NONE:
            continue
        return anc
    return None

# Les modes bitmap n'ont pas de tilemap : le texte doit être rendu en sprites.
BITMAP_MODES = (3, 4, 5)


def forced_target(anchor: str, render_mode: int = 0) -> str | None:
    """Cible imposée par le contexte, ou None si l'auteur a le choix.

    Deux contraintes, toutes deux matérielles :
      • ancrage sur un actor → OBJ (le BG ne sait pas se poser hors grille) ;
      • scène en mode bitmap → OBJ (plus de tilemap du tout).
    Retourner None est ce qui autorise l'inspecteur à proposer un menu ; sinon
    il affiche la valeur et sa raison."""
    if anchor == ANCHOR_ACTOR:
        return TARGET_OBJ
    if render_mode in BITMAP_MODES:
        return TARGET_OBJ
    return None


class RectGeometryMixin:
    """Géométrie en pixels d'un élément — pure arithmétique sur x/y/w/h.

    Un mixin plutôt qu'une méthode par type : les trois kinds portent le MÊME
    rectangle, et trois copies de l'arrondi à la tuile finiraient par diverger.
    Aucun champ ici — les dataclasses restent seules à déclarer les leurs."""

    def snap_to_tile(self) -> None:
        """Aligne sur la grille 8×8. À appeler quand la cible résolue est BG :
        le moteur y écrit des entrées de tilemap, l'origine ne peut pas tomber
        entre deux tuiles. Taille arrondie vers le HAUT — rogner couperait du
        texte pour faire joli."""
        self.x -= self.x % TILE
        self.y -= self.y % TILE
        self.w = max(TILE, _ceil_tile(self.w) * TILE)
        self.h = max(TILE, _ceil_tile(self.h) * TILE)

    def tile_rect(self) -> tuple[int, int, int, int]:
        """(tx, ty, w, h) en TUILES, bornes arrondies vers l'extérieur.

        Un glyphe posé à x=13 mord sur la tuile 1 : elle fait partie de
        l'empreinte, exactement comme `text_layout` arrondit la sienne avant de
        préparer la surface."""
        tx = self.x // TILE
        ty = self.y // TILE
        tw = _ceil_tile(self.x % TILE + self.w)
        th = _ceil_tile(self.y % TILE + self.h)
        return tx, ty, max(1, tw), max(1, th)

    def footprint_tiles(self) -> int:
        _, _, tw, th = self.tile_rect()
        return tw * th


# Priorité OBJ. `-1` hérite de l'acteur ancré ; `0` est devant et `3` derrière.
PRIORITY_INHERIT = -1


def _clamp_priority(v) -> int:
    """Ramène une priorité dans {-1, 0, 1, 2, 3} — hors plage = -1 (hérite)."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return PRIORITY_INHERIT
    return n if -1 <= n <= 3 else PRIORITY_INHERIT


# Couleur d'un texte : index dans sa banque de palette. Chaque couleur utilise des tuiles VRAM dédiées.
TEXT_COLOR_INK = 0     # Conserve les couleurs d'origine de la police.
TEXT_COLOR_MAX = 15    # L'index 0 est transparent en 4bpp.
# Surlignement : couleur derrière le texte, dans la même banque de palette.
HIGHLIGHT_NONE = 0


def _clamp_color(v) -> int:
    """Ramène un index de couleur d'UI dans sa plage — encre comme
    surlignement, qui vivent dans la même banque. Hors plage = 0, c'est-à-dire
    l'encre d'origine pour l'un, aucun surlignement pour l'autre. 1..15 est une
    contrainte MATÉRIELLE (4bpp, index 0 transparent), pas un choix — au-delà,
    le remappage de `text_recolor` déborderait son mot de 32 bits."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return TEXT_COLOR_INK
    return n if 0 <= n <= TEXT_COLOR_MAX else TEXT_COLOR_INK


@dataclass
class UIText(RectGeometryMixin):
    """Un emplacement de TEXTE de la mise en page — feuille (jamais parent).

    **Un seul type pour les deux façons d'y écrire.** `text_key` pointe une
    entrée de la table : renseignée, le build pose le contenu à l'init
    (`scene_init` émet le `text_draw_in`) ; vide, l'élément est un emplacement
    que le script remplit quand il veut (`interface.draw_text`). Rien n'interdit les
    deux — le dernier écrivain gagne, et c'est exactement ce qu'on veut pour un
    libellé par défaut qu'un script remplace.

    C'est ce qui a fait disparaître le type « zone de texte » : il n'apportait
    que « ce champ est vide », au prix d'un widget de plus, d'un inspecteur de
    plus, et d'une conversion à faire dès qu'on changeait d'avis.

    Le contenu ne vit pas dans l'élément : il est dans la table, pour ne pas
    dupliquer un littéral qui échapperait à l'édition centralisée, donc à la
    traduction et à l'interpolation `$nom` ([[project-text-table]]).

    **Le rectangle EST la largeur de coupe** — `text_draw_box` prenait un
    `wrap`, et le dupliquer dans un champ séparé garantirait qu'un jour les deux
    divergent. Un champ « multiligne » a existé ici et a été retiré pour la même
    raison : il ne changeait que la façon de TRONQUER un texte trop long (au mot
    plutôt qu'au pixel), pour le prix d'un second chemin de rendu. Le
    débordement, lui, est signalé par le validateur.
    """
    kind = KIND_TEXT         # attribut de classe (pas un champ dataclass)
    can_contain = ()         # feuille : n'accueille jamais d'enfants
    name:   str = "text"
    # Nom du parent. Une chaîne vide ou une référence absente désigne la racine.
    parent: str = ""
    # Visibilité locale. La visibilité effective tient compte des ancêtres.
    visible: bool = True
    # Géométrie en pixels, relative au parent.
    x: int = 0
    y: int = 0
    w: int = 96
    h: int = 16
    # Clé du texte initial. Vide : le script fournit le contenu.
    text_key: str = ""
    # Police utilisée ; vide pour la police par défaut de la scène.
    font_name: str = ""
    # Poids natif de la police au format OS/2, par exemple 400 ou 700.
    font_weight: int = 400
    # Sélectionne la face italique native.
    font_italic: bool = False
    align: str = "left"
    # Texte de mesure affiché dans l'éditeur quand aucune clé n'est définie.
    preview_text: str = ""
    # Couleur du texte, dans sa banque de palette.
    text_color: int = TEXT_COLOR_INK
    # Couleur de surlignement derrière le texte. Elle n'est pas héritée du conteneur.
    highlight_color: int = HIGHLIGHT_NONE
    # Priorité OBJ. Sans effet pour le rendu BG.
    priority: int = PRIORITY_INHERIT
    # Les glyphes ANIMÉS — les caractères qui sortent de la bande pour recevoir
    # un effet (`[wave]`, `[shake]`) — ne sont PAS un champ.
    #
    # Ils l'ont été, déclarés à la main dans l'inspecteur, au motif que le texte
    # affiché peut être une décision de script prise au runtime. Mais dans le
    # cas COURANT — une zone dont `text_key` est renseigné — le contenu est
    # connu au build et `ParsedText.animated_glyphs` les compte exactement :
    # le champ demandait donc de recompter à la main ce que le parseur savait
    # déjà, et une erreur en moins dégradait l'effet sans un mot.
    #
    # Ils se DÉRIVENT désormais du texte que la zone affiche —
    # `Project.region_animated_glyphs`, qui prend aussi le maximum sur les
    # traductions (une langue peut animer plus large que la source). Pour une
    # zone sans entrée, c'est son échantillon (`preview_text`) qui sert de
    # mesure, et le runtime ÉCRÊTE au-delà comme il l'a toujours fait : un
    # effet qui dégrade est une perte cosmétique, là où un dépassement d'OAM
    # corromprait les sprites des acteurs.

    # ── Géométrie ─────────────────────────────────────────────────
    # snap_to_tile / tile_rect / footprint_tiles viennent de RectGeometryMixin.
    # La cible (BG/OBJ) n'est plus une question posée à l'élément : elle appartient
    # au nœud, cf. `UILayout.resolved_target`.

    def to_dict(self) -> dict:
        return {
            "kind": KIND_TEXT,
            "name": self.name, "parent": self.parent, "visible": self.visible,
            "text_color": self.text_color,
            "highlight_color": self.highlight_color,
            "priority": self.priority,
            "x": self.x, "y": self.y, "w": self.w, "h": self.h,
            "text_key": self.text_key,
            "font_name": self.font_name, "font_weight": self.font_weight,
            "font_italic": self.font_italic,
            "align": self.align,
            "preview_text": self.preview_text,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UIText":
        """Relit AUSSI un `kind: "region"` d'avant la fusion — mêmes champs, le
        `text_key` manquant valant "" (c'est précisément ce qui faisait d'une
        zone une zone). `wrap` d'un fichier ancien est ignoré (cf. docstring) :
        la relecture ne le rend pas, la prochaine sauvegarde ne le réécrit pas.

        Les défauts de taille suivent le `kind` LU et non la classe : une zone
        d'avant la fusion vaut 240×32 (une boîte basse), un texte 96×16 (une
        ligne de libellé). Prendre un seul défaut redimensionnerait en silence
        les éléments d'un fichier qui ne portait pas le champ.

        `anchor`/`anchor_actor`/`target` d'un ancien fichier sont IGNORÉS ici :
        ils ont migré vers le nœud `Interface`, que `UILayout.from_dict` remonte
        depuis les racines avant de perdre l'info (cf. `_migrate_anchor_target`)."""
        align  = d.get("align", "left")
        was_region = d.get("kind") == KIND_REGION
        return cls(
            name         = str(d.get("name", "region" if was_region else "text")),
            parent       = str(d.get("parent", "")),
            visible      = bool(d.get("visible", True)),
            text_color   = _clamp_color(d.get("text_color", TEXT_COLOR_INK)),
            highlight_color = _clamp_color(d.get("highlight_color", HIGHLIGHT_NONE)),
            priority     = _clamp_priority(d.get("priority", PRIORITY_INHERIT)),
            x = int(d.get("x", 0)), y = int(d.get("y", 0)),
            w = int(d.get("w", 240 if was_region else 96)),
            h = int(d.get("h", 32 if was_region else 16)),
            text_key     = str(d.get("text_key", "")),
            font_name    = str(d.get("font_name", "")),
            font_weight  = max(1, min(1000, int(d.get("font_weight", 400)))),
            font_italic  = bool(d.get("font_italic", False)),
            align        = align if align in ALIGNS else "left",
            # `animated_glyphs` d'un ancien fichier est IGNORÉ : la valeur se
            # dérive du texte désormais. La clé disparaît du JSON au prochain
            # enregistrement — « une seule forme ÉCRITE », cf. core/project.py.
            preview_text = str(d.get("preview_text", "")),
        )


def _ceil_tile(px: int) -> int:
    return (max(0, int(px)) + TILE - 1) // TILE


# ── Bande OBJ : géométrie d'allocation ────────────────────────────
# Une zone en cible sprite est couverte par une BANDE de sprites : des OBJ de
# 64×8 px posés côte à côte sur le rectangle, dans lesquels le texte se compose
# exactement comme il se compose dans la surface BG.
#
# **La bande ne dépend pas de la police.** On aurait pu poser un OBJ par LIGNE
# de texte, mais l'interligne vient de la police, qui peut être choisie par la
# zone, héritée de la scène, ou changée par un script — l'allocation
# deviendrait alors indécidable au build. Un pavage en blocs de 8 px de haut
# donne le même compte d'OAM dans le cas courant (interligne 8) et reste vrai
# quelle que soit la police.
#
# **32 px est la largeur maximale d'un sprite de 8 px de haut.** Le matériel ne
# propose, en forme « large », que 16×8, 32×8, 32×16 et 64×32 : un 64×8 n'existe
# pas. Aller chercher les 64 px de large imposerait donc des blocs de 32 px de
# haut, qui arrondiraient la hauteur de la zone vers le haut et gâcheraient des
# tuiles (une zone de 40 px en réserverait 64). On paie en OAM ce qu'on refuse
# de gâcher en VRAM.
#
# La dernière colonne prend la plus grande taille qui rentre, pas 32
# systématiquement : sinon une zone de 40 px allouerait 64 px de tuiles et
# déborderait du rectangle que l'auteur a dessiné.
OBJ_WIDTHS = (32, 16, 8)
STRIP_ROW_H = 8

# Un glyphe animé sort de la bande et reçoit son propre sprite. On lui réserve
# un OBJ 16×16, soit 4 tuiles : un glyphe 8×8 posé à une position quelconque
# chevauche jusqu'à 2×2 tuiles (les chasses proportionnelles ne tombent pas sur
# la grille). Une taille uniforme garde l'allocation décidable sans connaître la
# police — le point qui avait déjà fait choisir un pavage de 8 px pour la bande.
ANIM_GLYPH_TILES = 4
# Plafond dur, aligné sur TEXT_ANIM_MAX du runtime (tableaux de capture de
# taille fixe : pas d'allocation dynamique sur cible).
ANIM_GLYPH_MAX = 32


def strip_columns(w: int) -> list[int]:
    """Largeurs (px) des OBJ couvrant `w`, de gauche à droite."""
    out, left = [], max(8, int(w))
    while left > 0:
        # La plus grande taille d'OBJ qui rentre ; 8 px en dernier recours,
        # quitte à dépasser de quelques pixels (une largeur qui n'est pas une
        # somme de puissances de deux ne peut pas être couverte exactement).
        out.append(next((c for c in OBJ_WIDTHS if c <= left), 8))
        left -= out[-1]
    return out


def strip_geometry(region: "UIText", animated: int = 0) -> dict:
    """Ce qu'une zone en cible OBJ consomme.

    `oam` = nombre de slots OAM, `tiles` = tuiles de VRAM OBJ. Les deux sont
    connus depuis la seule géométrie authorée — c'est ce qui rend la jauge
    exacte au lieu d'estimée.

    `animated` est FOURNI par l'appelant, pas lu sur la zone : le compte de
    glyphes animés se déduit du texte que la zone affiche, et le modèle ne
    résout pas la table de textes — même convention que `image_frames` dans
    `layout_obj_budget`. `Project.region_animated_glyphs` est ce qui le
    calcule ; 0 par défaut, c'est-à-dire la bande seule."""
    cols = strip_columns(region.w)
    rows = max(1, _ceil_tile(region.y % STRIP_ROW_H + region.h))
    tiles_per_row = sum(c // 8 for c in cols)
    anim = max(0, min(ANIM_GLYPH_MAX, int(animated or 0)))
    return {
        "cols": cols,
        "rows": rows,
        "anim": anim,
        "strip_oam":   len(cols) * rows,
        "strip_tiles": tiles_per_row * rows,
        "oam":   len(cols) * rows + anim,
        "tiles": tiles_per_row * rows + anim * ANIM_GLYPH_TILES,
    }


# ── Images : géométrie d'allocation ───────────────────────────────
# Une image est UN sprite, pas une bande : sa frame a déjà une forme OAM légale
# (VALID_FRAME_SIZES l'impose au Sprite Editor), donc un seul slot suffit et il
# n'y a rien à paver.
#
# **Toutes les frames de toutes les directions sont résidentes**, pas seulement
# celles de l'état déclaré. Un script peut basculer d'état à n'importe quelle
# frame (c'est la raison d'être du widget) ; recopier des tuiles depuis la ROM
# à cet instant-là, hors VBlank, ferait clignoter l'image. On paie en VRAM ce
# qu'on refuse de payer en déchirure — et le sprite est déjà tout entier en
# VRAM pour un acteur qui l'emploie, donc le coût est connu de l'auteur.


def sprite_grid(el, frame_w: int, frame_h: int) -> tuple[int, int]:
    """(colonnes, rangées) de frames pour couvrir `el`.

    Un `UIImage` fait toujours (1, 1) : sa taille EST celle de la frame
    (`sync_size_from`). Un `UIContainer` à fond sprite, lui, garde son rectangle de
    conteneur — le fond le PAVE, parce qu'un OBJ ne s'étire pas sans mode
    affine et qu'un conteneur dont la taille serait dictée par son fond ne serait
    plus un conteneur. La dernière colonne/rangée déborde plutôt que d'être
    rognée : le matériel ne sait pas couper un sprite, et un fond qui s'arrête
    3 px trop tôt se voit plus qu'un fond qui dépasse sous ses voisins."""
    fw = max(1, int(frame_w or 1))
    fh = max(1, int(frame_h or 1))
    if not can_fill(el):
        return 1, 1
    return (max(1, -(-int(el.w) // fw)), max(1, -(-int(el.h) // fh)))


def image_geometry(el, n_frames: int = 1,
                   frame_w: int = 0, frame_h: int = 0) -> dict:
    """Ce qu'une image (ou un fond sprite de conteneur) consomme. `n_frames` =
    total des frames du sprite, que seul l'appelant connaît (le modèle ne résout
    pas les noms d'asset) ; `frame_w`/`frame_h` = taille de la frame, à donner
    pour un conteneur dont le rectangle n'est pas celui de la frame.

    `oam` vaut 0 en cible BG et `cols * rows` en OBJ — mais `tiles` compte
    pareil dans les deux cas : le chemin BG copie les mêmes tuiles dans le
    charblock d'UI, il ne change que l'endroit et le fait d'écrire une carte
    par-dessus (`map_tiles` entrées de tilemap). Un pavage ne coûte AUCUNE tuile
    de plus — les N sprites pointent tous la même frame."""
    fw = int(frame_w) or int(el.w)
    fh = int(frame_h) or int(el.h)
    cols, rows = sprite_grid(el, fw, fh)
    per = max(1, _ceil_tile(fw)) * max(1, _ceil_tile(fh))
    frames = max(1, int(n_frames))
    return {"tiles_per_frame": per, "frames": frames,
            "tiles": per * frames, "map_tiles": per * cols * rows,
            "frame_w": fw, "frame_h": fh,
            "cols": cols, "rows": rows, "oam": cols * rows}


def layout_obj_budget(layout: "UILayout", render_mode: int = 0,
                      image_frames: dict | None = None,
                      image_frame_size: dict | None = None,
                      animated_by_name: dict | None = None) -> dict:
    """Budget OBJ d'une mise en page entière, et le placement RELATIF de chaque
    élément dedans.

    Relatif et non absolu : une même mise en page sert plusieurs scènes, qui
    n'ont pas le même nombre d'acteurs donc pas la même base. Seul le décalage
    interne est intrinsèque à la mise en page — exactement le raisonnement de
    `FontInfo.slot`, relatif au bloc alloué au texte.

    **L'ordre d'allocation EST l'ordre de profondeur.** Un slot OAM bas passe
    devant un slot haut, donc : les bandes de texte d'abord, les images ensuite,
    les FONDS de conteneur en dernier — un fond doit être derrière ce que son
    conteneur contient, et la priorité OBJ seule n'y suffirait pas (elle ne
    départage pas deux OBJ de même priorité). Une seule numérotation continue :
    deux allocations séparées se recouvriraient au premier oubli de chaîner
    leurs bases.

    `image_frames` = {nom: nombre de frames}, `image_frame_size` = {nom: (w, h)},
    `animated_by_name` = {nom: glyphes animés} — le modèle ne résout ni les noms
    d'asset ni la table de textes, c'est à l'appelant qui les connaît (le
    codegen) de les fournir. Absents, une image compte pour une frame, un
    conteneur pour un seul sprite et une zone pour sa bande seule :
    sous-réserver n'est pas anodin."""
    frames_by_name = image_frames or {}
    size_by_name = image_frame_size or {}
    anim_by_name = animated_by_name or {}
    place, oam, tiles = {}, 0, 0
    for r in layout.slots:
        if layout.resolved_target(r, render_mode) != TARGET_OBJ:
            continue
        g = strip_geometry(r, anim_by_name.get(r.name, 0))
        place[r.name] = {"oam_rel": oam, "tile_rel": tiles, **g}
        oam += g["oam"]
        tiles += g["tiles"]
    # Images puis fonds de conteneur — cf. l'ordre de profondeur ci-dessus.
    for im in sorted(layout.images, key=can_fill):
        if layout.resolved_target(im, render_mode) != TARGET_OBJ:
            continue
        fw, fh = size_by_name.get(im.name, (0, 0))
        g = image_geometry(im, frames_by_name.get(im.name, 1), fw, fh)
        # Un sprite d'interface consomme des slots OAM et AUCUNE tuile de ce
        # budget : ses pixels sont déjà en VRAM OBJ, chargés avec le sprite
        # comme pour un acteur (cf. main_gen.ui_image_sprites). Sa base de
        # tuiles est celle du sprite, pas une allocation d'interface — en
        # réserver une seconde doublerait le coût du même dessin.
        place[im.name] = {"oam_rel": oam, "tile_rel": 0, **g}
        oam += g["oam"]
    return {"place": place, "oam": oam, "tiles": tiles}


# ── Navigation d'une liste ────────────────────────────────────────
# Le SENS dans lequel les index se suivent dans la grille. Avec `nav_columns`,
# ces deux valeurs couvrent les quatre parcours qu'un menu demande, sans qu'un
# seul champ ait à encoder deux choses indépendantes :
#
#   verticale     nav_columns = 1, majeur indifférent (une seule colonne)
#   horizontale   nav_columns = nombre de rangées, majeur = rangée
#   en Z          nav_columns = N, majeur = rangée   (gauche→droite puis dessous)
#   en W          nav_columns = N, majeur = colonne  (haut→bas puis à droite)
#
# Un énuméré à quatre valeurs aurait de toute façon dû s'accompagner du compte de
# colonnes — sans lui, le moteur ne sait pas de combien sauter en changeant de
# rangée, et le parcours ne se calcule pas.
NAV_ROW    = "row"       # les index avancent le long d'une rangée
NAV_COLUMN = "column"    # les index avancent le long d'une colonne
NAV_MAJORS = (NAV_ROW, NAV_COLUMN)

# Comment le curseur rejoint la rangée choisie. « Posé » est le curseur de menu
# classique, « glissant » celui qui parcourt la distance — d'où une vitesse, sans
# laquelle un glissement n'est pas défini.
CURSOR_SNAP  = "snap"
CURSOR_SLIDE = "slide"
CURSOR_MODES = (CURSOR_SNAP, CURSOR_SLIDE)


# ── Le fond, en capacité plutôt qu'en type ────────────────────────

@dataclass
class FillMixin:
    """Les champs de FOND, portés par les deux conteneurs — `UIContainer` et `UIList`.

    **Une capacité (`can_fill`), pas un type.** Le code qui alloue les palettes,
    valide les assets et émet les tuiles demande « est-ce que ça peut dessiner un
    fond ? » ; il l'a longtemps demandé sous la forme `kind == KIND_CONTAINER`, ce qui
    a marché tant qu'un seul type en portait un, et aurait laissé la liste dehors
    sans rien dire. Le pendant de `RectGeometryMixin`, qui range de la même façon
    la géométrie commune aux quatre types.

    La sérialisation vit ici aussi : deux copies des sept clés auraient divergé au
    premier mode de fond ajouté.

    **Le fond sprite est une image de plus dans `g_ui_images`.** Il n'a pas sa
    propre table : un conteneur à fond sprite et un `UIImage` demandent la même
    chose au moteur (un sprite, un état, une animation, une banque de palette), à
    la répétition près. D'où la surface d'accès commune en fin de classe
    (`sprite_name`, `state_name`, `playing`, `state_index`) : le codegen n'a pas à
    savoir lequel des deux types il tient. Bénéfice non cherché mais réel : un
    script peut changer l'état du fond d'un conteneur comme celui d'une image,
    `IMAGE_<nom du conteneur>` existant lui aussi.

    Ces accès-là sont des PROPRIÉTÉS et non des champs : la donnée reste `fill_*`,
    il n'y a jamais deux valeurs à tenir d'accord. Vides quand le fond n'est pas
    un sprite, donc l'élément sort du chemin d'émission de lui-même. `priority`,
    elle, EST un champ (`UIImage` en a un aussi) : elle se surcharge par élément."""
    can_fill = True
    fill_kind: str = FILL_NONE
    fill_palette: str = ""   # nom de PaletteBank (fond couleur)
    fill_index: int = 0      # index 0-15 dans la palette (fond couleur)
    fill_asset: str = ""     # nom d'asset (nine-slice / background)
    fill_sprite: str = ""    # nom d'un SpriteAsset (fond sprite)
    fill_state: str = ""     # "" = premier état du sprite
    # SURCHARGE de la vitesse d'animation de l'état, en ticks entre deux frames.
    # 0 = celle du sprite (`AnimState.speed`), qui reste la source de vérité :
    # sans ce zéro, corriger une vitesse dans le Sprite Editor cesserait d'avoir
    # effet ici sans que rien ne le dise. Cf. `UIImage`, qui refuse pour la même
    # raison de recopier frames et vitesses.
    fill_speed: int = 0
    # Priorité OBJ du fond sprite — surchargeable comme celle d'une image
    # (-1 = PRIORITY_INHERIT, hérite de l'acteur ancré ; 0-3 explicite). Un champ
    # et non plus une propriété figée : chaque élément d'UI porte SA priorité, et
    # l'inspecteur l'édite dans la carte Geometry. Cf. `UIImage.priority`.
    priority: int = PRIORITY_INHERIT

    def fill_to_dict(self) -> dict:
        return {"fill_kind": self.fill_kind, "fill_palette": self.fill_palette,
                "fill_index": self.fill_index, "fill_asset": self.fill_asset,
                "fill_sprite": self.fill_sprite, "fill_state": self.fill_state,
                "fill_speed": self.fill_speed, "priority": self.priority}

    @staticmethod
    def fill_from_dict(d: dict) -> dict:
        """Les clés de fond en kwargs, prêtes pour un `cls(...)`."""
        fk = d.get("fill_kind", FILL_NONE)
        return {"fill_kind": fk if fk in FILL_KINDS else FILL_NONE,
                "fill_palette": str(d.get("fill_palette", "")),
                "fill_index": int(d.get("fill_index", 0) or 0),
                "fill_asset": str(d.get("fill_asset", "")),
                "fill_sprite": str(d.get("fill_sprite", "")),
                "fill_state": str(d.get("fill_state", "")),
                "fill_speed": max(0, min(255, int(d.get("fill_speed", 0) or 0))),
                "priority": _clamp_priority(d.get("priority", PRIORITY_INHERIT))}

    @property
    def sprite_name(self) -> str:
        return self.fill_sprite if self.fill_kind == FILL_SPRITE else ""

    @property
    def state_name(self) -> str:
        return self.fill_state

    @property
    def anim_speed(self) -> int:
        return int(self.fill_speed or 0)

    @property
    def playing(self) -> bool:
        # Un fond animé joue ; le figer se fait en choisissant un état d'une
        # seule frame, ou depuis un script (`interface.image_play`). Un champ de plus
        # ici doublerait ce que l'état dit déjà.
        return True

    def state_index(self, sprite) -> int:
        """Index de l'état nommé — même règle que `UIImage.state_index`."""
        states = list(getattr(sprite, "states", []) or [])
        if not self.fill_state:
            return 0
        return next((i for i, s in enumerate(states)
                     if s.name == self.fill_state), 0)


# ── Mise en page ──────────────────────────────────────────────────

@dataclass
class UIContainer(RectGeometryMixin, FillMixin):
    """Conteneur — grouper un sous-arbre, dessiner un fond.

    **Il ne se PARCOURT pas** : la navigation a son type depuis le 2026-09-02
    (`UIList`). Elle a été un champ d'ici (`is_list` et quatre compagnons), et
    l'en-tête du module dit pourquoi ça ne tenait pas. Le conteneur garde tout son
    sens sans elle.

    Sans fond (`fill_kind == FILL_NONE`), c'est un simple groupe invisible ; les
    quatre modes de fond et leur surface commune avec `UIImage` sont décrits dans
    `FillMixin`.

    Géométrie en pixels comme la zone. L'ancrage et la cible ne sont plus portés
    ici : ils appartiennent au nœud `Interface` (`UILayout`), pour tout le
    sous-arbre (v0.25)."""
    kind = KIND_CONTAINER
    can_contain = KINDS      # n'importe quel type d'enfant
    name: str = "container"
    parent: str = ""
    # Cf. `UIText.visible` — même contrat. Un conteneur caché cache tout son
    # sous-arbre : c'est `UILayout.is_visible` qui remonte la chaîne, pas ce
    # champ qui se propage aux enfants.
    visible: bool = True
    x: int = 0
    y: int = 0
    w: int = 64
    h: int = 32

    def to_dict(self) -> dict:
        return {"kind": KIND_CONTAINER, "name": self.name, "parent": self.parent,
                "visible": self.visible,
                "x": self.x, "y": self.y, "w": self.w, "h": self.h,
                **self.fill_to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> "UIContainer":
        return cls(
            name=str(d.get("name", "container")), parent=str(d.get("parent", "")),
            visible=bool(d.get("visible", True)),
            x=int(d.get("x", 0)), y=int(d.get("y", 0)),
            w=int(d.get("w", 64)), h=int(d.get("h", 32)),
            **cls.fill_from_dict(d))


@dataclass
class UIList(RectGeometryMixin, FillMixin):
    """Un conteneur qui se PARCOURT — la navigation d'un menu, d'un inventaire ou
    d'une grille, prise en charge par le moteur.

    **Ses RANGÉES sont ses enfants**, des zones de texte, dans l'ordre de l'arbre :
    rien à déclarer, ce qu'on voit dans la mise en page est ce que la liste
    parcourt. Le nombre d'ITEMS, lui, est de la donnée — il se règle au script
    (`list.set_count`), parce qu'un inventaire ne connaît sa longueur qu'en jeu ;
    à défaut il vaut le nombre de rangées, ce qui suffit à un menu statique.

    **Ce que la liste ne fait PAS : dessiner.** Elle dit quel item est sélectionné
    et lequel s'affiche sur quelle rangée ; le contenu reste écrit par le script
    (`interface.draw_text(list.row(...), ...)`), avec les outils de texte qui existent.
    C'est la même frontière que partout ailleurs ici — un item est une ligne de
    DONNÉE, pas un objet d'interface, et c'est ce qui fait qu'un inventaire, un
    arbre de compétences et un menu de sauvegarde partagent un seul mécanisme.

    Elle dessine un fond comme le conteneur (`FillMixin`) : une liste est presque
    toujours posée dans un cadre, et l'obliger à s'emboîter dans un conteneur pour
    l'obtenir aurait ajouté un élément par menu sans rien dire de plus."""
    kind = KIND_LIST
    # Ses enfants SONT ses rangées. Accueillir une image reviendrait à poser dans
    # la liste un élément qu'elle ne parcourt pas et que le build ignore — ce que
    # l'arbre laissait faire tant que la liste était un drapeau du conteneur.
    can_contain = (KIND_TEXT,)
    name: str = "list"
    parent: str = ""
    # Cf. `UIText.visible` — même contrat, même remontée par `UILayout.is_visible`.
    # C'est L'AFFICHAGE ; ne pas le confondre avec `active` juste en dessous, qui
    # est la sélection.
    visible: bool = True
    x: int = 0
    y: int = 0
    w: int = 96
    h: int = 48
    # Ancrage et cible appartiennent au nœud `Interface` (`UILayout`), plus à la
    # liste — cf. `UIText` (v0.25).

    # ── Navigation ────────────────────────────────────────────────
    # La liste consomme-t-elle la croix directionnelle ? C'est la SÉLECTION qu'on
    # coupe, pas l'affichage : une liste inactive reste dessinée et garde son
    # index. Sans ce champ, deux listes visibles — un menu et son sous-menu —
    # bougent ensemble au même appui, ce que `ui_list_tick` faisait faute de
    # savoir laquelle a la main. Le script bascule (`list.set_active`), parce que
    # c'est lui qui sait quel écran est au premier plan.
    active: bool = True
    # La GRILLE en deux nombres — cf. `NAV_ROW`/`NAV_COLUMN` pour les quatre
    # parcours qu'ils couvrent et pourquoi un énuméré n'y suffisait pas.
    nav_columns: int = 1
    nav_major: str = NAV_COLUMN
    # Le curseur repasse-t-il du dernier au premier ? Vrai est ce qu'on attend
    # d'un menu court, faux ce qu'on attend d'un inventaire long.
    wrap: bool = True
    # Cadence de répétition quand la touche reste enfoncée, en frames :
    # `repeat_delay` avant le premier renvoi, `repeat_rate` entre les suivants.
    # 0 = suivre le réglage du PROJET — même politique d'héritage que la
    # transition de scène (v0.6.2), et c'est elle qui évite trois listes à trois
    # cadences dans le même jeu.
    repeat_delay: int = 0
    repeat_rate: int = 0

    # ── Curseur ───────────────────────────────────────────────────
    # La liste POSSÈDE son curseur : elle NOMME un `UIImage` de la même mise en
    # page et le moteur le pose sur la rangée choisie. Ce n'est pas un enfant
    # (les enfants sont les rangées) et ce n'est pas un type de plus — « le
    # curseur est ce qui existe déjà » (v0.22). Le déplacement passe par le même
    # chemin que `interface.image_move` : une implémentation, deux portes.
    #
    # "" = aucun curseur ; la sélection se lit alors au surlignement plus bas.
    cursor_image: str = ""
    cursor_mode: str = CURSOR_SNAP
    # Vitesse du mode glissant, en pixels par frame — un glissement sans vitesse
    # n'est pas défini. Sans objet en mode posé.
    cursor_speed: int = 2

    # ── Style de la rangée choisie ────────────────────────────────
    # Ce que la rangée SÉLECTIONNÉE affiche en plus : exactement les deux réglages
    # qu'une zone de texte porte déjà (`UIText.text_color`, `.highlight_color`),
    # appliqués par le moteur en suivant l'index au lieu d'être réécrits par le
    # script à chaque déplacement. Même plage, même banque d'UI, même zéro.
    #
    # Une ANIMATION sur la rangée choisie n'est pas offerte : sur cible BG elle
    # réécrirait des tuiles à chaque frame, et ce coût-là se mesure avant de se
    # promettre.
    selected_text_color: int = TEXT_COLOR_INK
    selected_highlight_color: int = HIGHLIGHT_NONE

    def to_dict(self) -> dict:
        return {"kind": KIND_LIST, "name": self.name, "parent": self.parent,
                "visible": self.visible,
                "x": self.x, "y": self.y, "w": self.w, "h": self.h,
                "active": self.active,
                "nav_columns": self.nav_columns, "nav_major": self.nav_major,
                "wrap": self.wrap,
                "repeat_delay": self.repeat_delay,
                "repeat_rate": self.repeat_rate,
                "cursor_image": self.cursor_image,
                "cursor_mode": self.cursor_mode,
                "cursor_speed": self.cursor_speed,
                "selected_text_color": self.selected_text_color,
                "selected_highlight_color": self.selected_highlight_color,
                **self.fill_to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> "UIList":
        """Relit AUSSI un `{"kind": "panel", "is_list": true}` d'avant le
        2026-09-02 — même recette que `KIND_REGION`, et jamais réécrit sous cette
        forme. `list_wrap`/`list_repeat_*` y perdent leur préfixe, redondant sur
        un type qui EST une liste ; `list_axis` disparaît au profit de la grille,
        et le cas horizontal se termine dans `UILayout.from_dict`, seul endroit à
        connaître le nombre de rangées."""
        major = d.get("nav_major", NAV_COLUMN)
        mode = d.get("cursor_mode", CURSOR_SNAP)
        return cls(
            name=str(d.get("name", "list")), parent=str(d.get("parent", "")),
            visible=bool(d.get("visible", True)),
            x=int(d.get("x", 0)), y=int(d.get("y", 0)),
            w=int(d.get("w", 96)), h=int(d.get("h", 48)),
            active=bool(d.get("active", True)),
            nav_columns=max(1, int(d.get("nav_columns", 1) or 1)),
            nav_major=major if major in NAV_MAJORS else NAV_COLUMN,
            # `list_*` : les noms d'avant le 2026-09-02, lus une dernière fois.
            wrap=bool(d.get("wrap", d.get("list_wrap", True))),
            repeat_delay=max(0, int(d.get("repeat_delay",
                                          d.get("list_repeat_delay", 0)) or 0)),
            repeat_rate=max(0, int(d.get("repeat_rate",
                                         d.get("list_repeat_rate", 0)) or 0)),
            cursor_image=str(d.get("cursor_image", "")),
            cursor_mode=mode if mode in CURSOR_MODES else CURSOR_SNAP,
            cursor_speed=max(1, min(255, int(d.get("cursor_speed", 2) or 2))),
            selected_text_color=_clamp_color(
                d.get("selected_text_color", TEXT_COLOR_INK)),
            selected_highlight_color=_clamp_color(
                d.get("selected_highlight_color", HIGHLIGHT_NONE)),
            **cls.fill_from_dict(d))


@dataclass
class UIImage(RectGeometryMixin):
    """Un SPRITE À ÉTAT posé sur l'interface — feuille (jamais parent).

    **Rien de neuf côté données d'animation.** L'élément ne fait que DÉSIGNER un
    `SpriteAsset` et l'un de ses `AnimState` : états, directions, frames, vitesse
    et bouclage restent dans le sprite, édités dans le Sprite Editor. Recopier
    ici une vitesse ou une liste de frames donnerait deux vérités pour un même
    dessin — c'est le même refus que le contenu d'un texte, qui reste dans la
    table.

    **La taille n'est pas libre** : `w`/`h` valent la frame du sprite, resynchro-
    nisées quand on en choisit un autre (`sync_size_from`). Le matériel ne sait
    pas étirer un OBJ sans mode affine, et une image BG est un pavage de tuiles :
    un rectangle plus grand que la frame ne dirait rien de ce qui s'affichera.

    **La direction n'entre pas ici.** Un élément d'interface n'a pas de cap ; le
    runtime lit la direction 0 (omnidirectionnelle) de l'état, celle-là même que
    la boucle des acteurs prend en repli. Ajouter un champ « direction »
    exposerait au HUD une notion qui n'a de sens que dans le monde.

    Cible BG ou OBJ, dérivée du nœud `Interface` comme pour un texte (cf.
    `UILayout.resolved_target`) : sous un nœud ancré à l'écran l'image est écrite
    dans la tilemap et ne coûte aucun OAM ; sous un nœud ancré sur un acteur elle
    passe en sprite, seule façon de se poser au pixel."""
    kind = KIND_IMAGE
    can_contain = ()         # feuille : n'accueille jamais d'enfants
    name: str = "image"
    parent: str = ""
    # Cf. `UIText.visible` — même contrat, même remontée par `UILayout.
    # is_visible`. Remplace l'état interne que `ui.image_show` bascule
    # aujourd'hui côté runtime (`g_ui_img[img].visible`) : ce champ-ci n'est
    # que l'état AUTHORÉ de départ, le script continue de décider ensuite.
    visible: bool = True
    x: int = 0
    y: int = 0
    # Renseignés depuis le sprite (cf. `sync_size_from`) ; les défauts ne servent
    # qu'à l'élément fraîchement dessiné, avant qu'un sprite soit choisi.
    w: int = 16
    h: int = 16
    # Ancrage et cible appartiennent au nœud `Interface` (`UILayout`) — cf.
    # `UIText` (v0.25).
    sprite_name: str = ""    # nom d'un SpriteAsset du projet
    state_name: str = ""     # "" = premier état du sprite
    # Pendant de `UIContainer.fill_speed` : une image ne surcharge pas la vitesse de
    # l'état, elle DÉSIGNE un sprite. Propriété constante plutôt que champ, pour
    # que le codegen lise la même chose sur les deux types.
    anim_speed = 0
    # 0 = l'image se fige sur la première frame de l'état. Un HUD est plein
    # d'icônes qui ne bougent pas, et les faire tourner coûterait un tick et une
    # réécriture de tilemap par image et par frame.
    playing: bool = True
    # Priorité OBJ (0 = devant, 3 = derrière). -1 = PRIORITY_INHERIT : l'image
    # prend, en cible OBJ, la priorité de l'acteur auquel son nœud est ancré —
    # elle vit à la profondeur de cet acteur, en direct (un `self.priority` en
    # jeu l'emporte). Une valeur explicite 0-3 SURCHARGE cet héritage : deux
    # images d'un même conteneur qui se recouvrent à dessein (jauge + cadre)
    # gardent ainsi leur ordre. Sous un nœud écran/monde, hériter retombe sur 0.
    priority: int = PRIORITY_INHERIT

    def to_dict(self) -> dict:
        return {"kind": KIND_IMAGE, "name": self.name, "parent": self.parent,
                "visible": self.visible,
                "x": self.x, "y": self.y, "w": self.w, "h": self.h,
                "sprite_name": self.sprite_name, "state_name": self.state_name,
                "playing": bool(self.playing), "priority": self.priority}

    @classmethod
    def from_dict(cls, d: dict) -> "UIImage":
        return cls(
            name=str(d.get("name", "image")), parent=str(d.get("parent", "")),
            visible=bool(d.get("visible", True)),
            x=int(d.get("x", 0)), y=int(d.get("y", 0)),
            w=int(d.get("w", 16)), h=int(d.get("h", 16)),
            sprite_name=str(d.get("sprite_name", "")),
            state_name=str(d.get("state_name", "")),
            playing=bool(d.get("playing", True)),
            priority=_clamp_priority(d.get("priority", PRIORITY_INHERIT)))

    # ── Taille asservie au sprite ─────────────────────────────────
    def sync_size_from(self, sprite) -> bool:
        """Repose `w`/`h` sur la frame de `sprite`. True si ça a bougé.

        Appelé au choix du sprite plutôt que calculé à la lecture : le canvas,
        le codegen et le validateur lisent tous `w`/`h` sans avoir à résoudre un
        nom d'asset, et une référence cassée garde la dernière taille connue au
        lieu de faire disparaître l'élément."""
        if sprite is None:
            return False
        w = max(TILE, int(getattr(sprite, "frame_w", TILE) or TILE))
        h = max(TILE, int(getattr(sprite, "frame_h", TILE) or TILE))
        if (w, h) == (self.w, self.h):
            return False
        self.w, self.h = w, h
        return True

    def state_index(self, sprite) -> int:
        """Index de l'état nommé dans `sprite.states`, 0 par défaut.

        Par NOM dans les données et par INDEX à l'exécution : renommer un état
        du sprite ne doit pas déplacer silencieusement l'image sur un autre, et
        le runtime ne peut pas comparer des chaînes."""
        states = list(getattr(sprite, "states", []) or [])
        if not self.state_name:
            return 0
        return next((i for i, s in enumerate(states)
                     if s.name == self.state_name), 0)


# Registre kind → constructeur. Un dict sans `kind` est un fichier d'avant la
# généralisation multi-types : que des zones de texte, donc `UIText`. Même
# entrée que `KIND_REGION`, pour la même raison.
_ELEMENT_FROM_DICT = {
    KIND_REGION:       UIText.from_dict,       # hérités — cf. KIND_REGION
    KIND_PANEL_LEGACY: UIContainer.from_dict,
    KIND_CONTAINER:    UIContainer.from_dict,
    KIND_LIST:         UIList.from_dict,
    KIND_TEXT:         UIText.from_dict,
    KIND_IMAGE:        UIImage.from_dict,
}


def element_from_dict(d: dict):
    """Désérialise un élément selon son `kind` (texte par défaut, format hérité).

    Deux formes anciennes se lisent ici, et aucune ne se réécrit :
      • `{"kind": "panel", "is_list": true}` d'avant le 2026-09-02 ressort en
        `UIList` — le drapeau ÉTAIT le type, il devient le type ;
      • `{"kind": "panel"}` tout court ressort en `UIContainer`, qui portait ce
        nom jusqu'au même jour.
    Le prochain enregistrement porte `"list"` ou `"container"`, et rien n'est
    perdu au passage."""
    kind = d.get("kind", KIND_REGION)
    if kind == KIND_PANEL_LEGACY and d.get("is_list"):
        kind = KIND_LIST
    return _ELEMENT_FROM_DICT.get(kind, UIText.from_dict)(d)


@dataclass
class UILayout(Resource):
    """Le nœud `Interface` : un jeu d'éléments d'UI, avec SON chemin matériel.

    **Un asset, pas une donnée de scène.** Rangé dans `project/ui_layouts/` et
    référencé par NOM : une boîte de dialogue dessinée une fois sert les
    quarante scènes du jeu et se corrige en un endroit. Stockée dans la scène,
    elle serait à redessiner — et à recorriger — quarante fois. Une scène en
    référence plusieurs (v0.25) : un HUD fixe en BG et une bulle actor-OBJ sont
    deux nœuds `Interface`, chacun son couple ancrage/cible.

    Contrepartie à assumer dans l'UI : éditer un élément depuis le canvas d'une
    scène modifie un objet PARTAGÉ. Le dire à l'écran (« partagée — N scènes »)
    fait partie de la feature, sans quoi on casse N scènes en croyant en ajuster
    une.

    **Le nœud possède `anchor` + `target`, source de vérité unique** (v0.25). Ils
    vivaient sur chaque élément racine (`forced_target()` par élément) ; ils sont
    remontés ici, et tout le sous-arbre en hérite. Une capacité qui se lisait
    comme un cas particulier de chaque élément devient une propriété de son
    propriétaire — même réparation que « la liste devient un TYPE ».

    `name` est la clé de référence, comme partout ailleurs dans le projet
    (`<asset>_name`), donc ce qui entre dans le graphe de dépendances.
    """
    name:    str = "ui_layout"
    # Liste ordonnée de TOUS les éléments (textes, conteneurs, images) — l'ordre
    # fixe l'empilement et l'ordre des frères. `slots` et `images` en exposent
    # les vues par type, chacune faisant l'index d'une table C.
    elements: list = field(default_factory=list)
    # ── Chemin matériel du nœud (v0.25) ───────────────────────────
    # `anchor` : screen (fixe 240×160) / world (défile) / actor (suit un acteur).
    # `anchor_actor` : nom de l'Actor suivi, seulement si anchor == actor.
    # `target` : BG / OBJ. "" = dérivée de l'ancrage (cf. `resolved_target`) ;
    #   ne porte une valeur que lorsque l'auteur a fait un choix RÉEL — donc
    #   jamais quand `forced_target()` tranche.
    anchor:       str = ANCHOR_SCREEN
    anchor_actor: str = ""
    target:       str = ""
    notes:   str = ""

    @property
    def slots(self) -> list:
        """Éléments qui occupent une entrée de `g_ui_regions` (cf. KIND_SLOTS) :
        les emplacements de TEXTE, dans l'ordre de `elements`.

        C'est cet ordre-là qui devient l'index dans la table C. Un conteneur en
        est exclu (il dessine un fond, il n'accueille pas de glyphes), une image
        aussi — elle a sa propre table, `g_ui_images`."""
        return [e for e in self.elements
                if getattr(e, "kind", KIND_TEXT) in KIND_SLOTS]

    @property
    def images(self) -> list:
        """Éléments qui posent un SPRITE, dans l'ordre de `elements` — l'index de
        `g_ui_images`, donc des constantes `IMAGE_*`.

        Deux types y entrent : un `UIImage`, et un `UIContainer` dont le fond est un
        sprite. Ce n'est pas un raccourci d'implémentation — ils demandent au
        moteur exactement la même chose (un sprite, un état, une animation, une
        banque de palette), à la répétition près, que `UIContainer` expose par la
        même surface d'accès. Une seconde table aurait dupliqué `ui_image_update`
        pour en changer deux lignes.

        Une table à part de `g_ui_regions` en revanche, parce que là les deux ne
        partagent que le rectangle et l'ancrage : fusionner aurait donné une
        structure dont la moitié des champs est morte selon le type, et un
        runtime qui teste le kind à chaque frame."""
        return [e for e in self.elements
                if getattr(e, "kind", "") == KIND_IMAGE
                or (can_fill(e) and getattr(e, "fill_kind", "") == FILL_SPRITE)]

    def get(self, name: str):
        """N'importe quel élément par son nom (tous types confondus)."""
        return next((e for e in self.elements if e.name == name), None)

    def can_contain(self, name: str, kind: str = "") -> bool:
        """`name` peut-il accueillir un enfant — et, si `kind` est donné, un
        enfant DE CE TYPE ?

        Sans `kind` la question reste « est-ce un conteneur ? », ce qu'elle a
        toujours été. Avec, elle vaut aussi pour une liste, qui n'accueille que
        des zones de texte : ses enfants SONT ses rangées, et une image déposée
        là serait ignorée par le build sans que rien ne l'ait dit."""
        e = self.get(name)
        if e is None:
            return False
        accepted = getattr(e, "can_contain", ())
        return bool(accepted) and (not kind or kind in accepted)

    def region_names(self) -> list[str]:
        """Noms des emplacements de texte — ceux qui se résolvent en `REGION_*`."""
        return [e.name for e in self.slots]

    def image_names(self) -> list[str]:
        """Noms des images — ceux qui se résolvent en `IMAGE_*`."""
        return [e.name for e in self.images]

    def element_names(self) -> list[str]:
        """Noms de TOUS les éléments — l'espace de nommage à garder unique pour
        que les refs `parent` soient sans ambiguïté (un conteneur et un texte ne
        peuvent pas partager un nom)."""
        return [e.name for e in self.elements]

    # ── Hiérarchie (dérivée des refs `parent`) ────────────────────
    # L'arbre n'est jamais stocké : `elements` reste une liste plate et ces
    # helpers le reconstruisent, TOUS types confondus. L'ORDRE de la liste fixe
    # l'ordre des frères (et le z-order entre éléments qui dessinent). Une ref
    # `parent` pendante est traitée comme racine — supprimer un parent ne casse
    # rien, ses enfants remontent d'un cran à l'affichage.

    def children(self, name: str) -> list:
        """Enfants directs de `name`, dans l'ordre de la liste."""
        return [e for e in self.elements if e.parent == name]

    def roots(self) -> list:
        """Éléments de premier niveau : sans parent, ou parent pendant."""
        names = {e.name for e in self.elements}
        return [e for e in self.elements if not e.parent or e.parent not in names]

    def ancestors(self, name: str) -> list[str]:
        """Chaîne des parents en remontant, garde-fou anti-boucle inclus (des
        données corrompues ne doivent pas faire tourner l'éditeur à l'infini)."""
        out: list[str] = []
        seen: set[str] = {name}
        cur = self.get(name)
        while cur is not None and cur.parent and cur.parent not in seen:
            out.append(cur.parent)
            seen.add(cur.parent)
            cur = self.get(cur.parent)
        return out

    def would_cycle(self, name: str, new_parent: str) -> bool:
        """Vrai si parenter `name` sous `new_parent` fermerait une boucle : soit
        on se prend soi-même, soit la nouvelle cible est déjà un descendant."""
        if not new_parent or new_parent == name:
            return new_parent == name
        # boucle ⟺ `name` figure parmi les ancêtres de `new_parent`
        return name in self.ancestors(new_parent)

    def descendants(self, name: str) -> list:
        """Tout le sous-arbre sous `name` (DFS, ordre de liste), `name` exclu."""
        out: list = []
        for child in self.children(name):
            out.append(child)
            out.extend(self.descendants(child.name))
        return out

    def is_visible(self, name: str) -> bool:
        """Visibilité EFFECTIVE de `name` : son propre `visible` ET celui de
        chacun de ses ancêtres. Jamais stockée, jamais propagée à l'écriture —
        recalculée à la lecture depuis `ancestors()`, exactement comme le reste
        de l'arbre. Cacher un enfant puis remontrer son parent laisse donc
        l'enfant caché : chaque nœud ne porte que son propre bit.

        Un nom introuvable est traité comme invisible (rien à montrer) plutôt
        que de lever — les autres lecteurs de l'arbre (`children`, `get`) sont
        tout aussi tolérants aux refs mortes."""
        e = self.get(name)
        if e is None or not getattr(e, "visible", True):
            return False
        return all(getattr(self.get(a), "visible", True)
                   for a in self.ancestors(name))

    def in_tree_order(self):
        """(profondeur, élément) en parcours préfixe, l'ordre de liste faisant foi
        entre frères — ce que consomme la vue arbre. Défensif contre les refs
        pendantes (racines) et les cycles (chaque nœud visité une fois)."""
        seen: set[str] = set()
        out: list = []

        def walk(node, depth: int) -> None:
            if node.name in seen:
                return
            seen.add(node.name)
            out.append((depth, node))
            for child in self.children(node.name):
                walk(child, depth + 1)

        for e in self.roots():
            walk(e, 0)
        # Nœuds jamais atteints (cycle pur entre eux) : rattachés en racine, pour
        # qu'aucun élément ne disparaisse de l'arbre.
        for e in self.elements:
            if e.name not in seen:
                walk(e, 0)
        return out

    # ── Ordre / z-order (réordonnancement des frères) ─────────────
    # L'ordre de `elements` EST le z-order (frère tardif = au-dessus) et l'ordre
    # des frères dans l'arbre. Trois consommateurs le lisent : l'arbre (via
    # `children`), le canvas (empilement) et le codegen (ordre de dessin des
    # fonds). Pour qu'ils s'accordent, un réordonnancement RÉÉCRIT `elements` en
    # DFS canonique — parent avant ses enfants, frères dans l'ordre voulu — via
    # `_flatten`. Une liste non canonique (héritée d'un reparentage qui ne
    # déplaçait pas dans la liste) est ainsi normalisée au passage.

    def _flatten(self, order_override: dict | None = None) -> list:
        """`elements` réordonné en DFS canonique. `order_override` :
        {nom_parent: [noms de frères...]} force l'ordre des enfants de ce parent
        ("" = racines) ; les frères non cités gardent leur ordre courant, à la
        suite. Défensif : cycles purs rattachés en fin, aucun élément perdu."""
        override = order_override or {}
        out: list = []
        seen: set[str] = set()

        def ordered(children_list, key):
            if key not in override:
                return children_list
            by_name = {c.name: c for c in children_list}
            forced = [by_name[n] for n in override[key] if n in by_name]
            rest = [c for c in children_list if c.name not in set(override[key])]
            return forced + rest

        def emit(node) -> None:
            if node.name in seen:
                return
            seen.add(node.name)
            out.append(node)
            for child in ordered(self.children(node.name), node.name):
                emit(child)

        for root in ordered(self.roots(), ""):
            emit(root)
        for e in self.elements:            # cycles purs : ne rien perdre
            if e.name not in seen:
                out.append(e)
                seen.add(e.name)
        return out

    def _parent_key(self, element) -> str:
        """Clé du parent pour `_flatten`/`children` : "" si racine (sans parent
        ou parent pendant), sinon le nom du parent."""
        p = getattr(element, "parent", "")
        return p if (p and self.get(p) is not None) else ""

    def _siblings(self, parent_key: str) -> list:
        """Frères sous `parent_key` dans l'ordre courant ("" = racines)."""
        return self.roots() if parent_key == "" else self.children(parent_key)

    def move_sibling(self, name: str, direction: str) -> bool:
        """Déplace `name` parmi ses frères : "up"/"down" d'un cran, "top"/"bottom"
        à une extrémité. Réécrit `elements` (DFS canonique) et renvoie True si ça
        a bougé, False sinon (introuvable, déjà en bout, direction inconnue)."""
        e = self.get(name)
        if e is None:
            return False
        key = self._parent_key(e)
        names = [s.name for s in self._siblings(key)]
        if name not in names:
            return False
        i, n = names.index(name), len(names)
        order = names[:]
        order.pop(i)
        if direction == "up":
            if i == 0:
                return False
            order.insert(i - 1, name)
        elif direction == "down":
            if i >= n - 1:
                return False
            order.insert(i + 1, name)
        elif direction == "top":
            if i == 0:
                return False
            order.insert(0, name)
        elif direction == "bottom":
            if i >= n - 1:
                return False
            order.append(name)
        else:
            return False
        self.elements[:] = self._flatten({key: order})
        return True

    def place_child(self, name: str, new_parent: str,
                    before_name: str | None = None) -> bool:
        """Rattache `name` à `new_parent` ("" = racine) et le pose JUSTE AVANT
        `before_name` parmi ses (nouveaux) frères, ou en dernier si `before_name`
        est None/absent. Refuse feuille-comme-parent et cycle (`can_contain`,
        `would_cycle`). Réécrit `elements` en DFS canonique. True si un changement
        a bien eu lieu — reparentage, repositionnement, ou les deux."""
        e = self.get(name)
        if e is None:
            return False
        if new_parent and not self.can_contain(new_parent,
                                               getattr(e, "kind", "")):
            return False
        if self.would_cycle(name, new_parent):
            return False
        key = new_parent if (new_parent and self.get(new_parent) is not None) else ""
        before = [x.name for x in self.elements]      # pour détecter un no-op
        old_parent = e.parent
        e.parent = key
        names = [s.name for s in self._siblings(key) if s.name != name]
        if before_name and before_name in names and before_name != name:
            names.insert(names.index(before_name), name)
        else:
            names.append(name)
        new_flat = self._flatten({key: names})
        if [x.name for x in new_flat] == before and key == old_parent:
            e.parent = old_parent      # rien n'a changé : ne pas salir l'historique
            return False
        self.elements[:] = new_flat
        return True

    def retarget_parent(self, old: str, new: str) -> int:
        """Rebranche les enfants d'un élément renommé (`old` → `new`) et renvoie
        le nombre de refs mises à jour. À appeler par le flux de renommage, comme
        on met à jour les scripts qui citent une clé — sinon renommer un élément
        orphelinerait ses enfants (leur `parent` pointant l'ancien nom)."""
        n = 0
        for e in self.elements:
            if e.parent == old:
                e.parent = new
                n += 1
        return n

    # ── Ancrage & origine : portés par le NŒUD ────────────────────
    # L'ancrage et la cible appartiennent au nœud `Interface` (self), plus à
    # chaque élément racine (v0.25) : tout le sous-arbre les partage. Un enfant
    # se positionne en pixels RELATIFS à son parent, et ces helpers remontent la
    # chaîne des offsets — mais le socle (écran, ou position de l'acteur suivi) est
    # celui du nœud, une seule fois.

    def root_of(self, name: str):
        """Élément top-level de la branche de `name` (remontée des parents, sûre
        face aux cycles et aux refs pendantes). Helper d'arbre pur — l'ancrage,
        lui, vit sur le nœud (cf. `effective_anchor`), plus sur ce root."""
        cur = self.get(name)
        seen: set[str] = set()
        while cur is not None and cur.parent and cur.name not in seen:
            seen.add(cur.name)
            nxt = self.get(cur.parent)
            if nxt is None:        # parent pendant → `cur` est le root effectif
                break
            cur = nxt
        return cur

    def effective_anchor(self, element=None) -> tuple[str, str]:
        """(anchor, anchor_actor) DU NŒUD — tout élément les partage. `element`
        est accepté pour la compatibilité des appelants et ignoré ; l'argument
        disparaîtra quand codegen et inspecteur seront repris (v0.25, temps 3/4)."""
        return self.anchor, self.anchor_actor

    def resolved_target(self, element=None, render_mode: int = 0) -> str:
        """Cible BG/OBJ DU NŒUD : imposée par `forced_target()` (ancrage actor, ou
        scène bitmap), sinon le choix de l'auteur, sinon BG. `element` accepté et
        ignoré — cf. `effective_anchor`."""
        forced = forced_target(self.anchor, render_mode)
        if forced:
            return forced
        return self.target if self.target in TARGETS else TARGET_BG

    def absolute_origin(self, element, actor_pos) -> tuple[int, int, bool]:
        """(x, y, resolved) : position ÉCRAN de l'origine de `element`, en sommant
        les offsets jusqu'à la racine, puis en ajoutant le socle du NŒUD — (0,0)
        en écran/monde, la position de l'acteur en ancrage actor. `actor_pos` =
        callable nom→(x,y) ou None. `resolved` est faux si l'acteur du nœud est
        introuvable (la position affichée n'est alors pas celle du jeu)."""
        chain = [element] + [self.get(a) for a in self.ancestors(element.name)]
        chain = [e for e in chain if e is not None]
        ox = sum(int(e.x) for e in chain)
        oy = sum(int(e.y) for e in chain)
        resolved = True
        if self.anchor == ANCHOR_ACTOR:
            ap = actor_pos(self.anchor_actor) if actor_pos else None
            if ap is None:
                resolved = False
            else:
                ox += ap[0]
                oy += ap[1]
        return ox, oy, resolved

    def absolute_tile_rect(self, element, actor_pos) -> tuple[int, int, int, int]:
        """(tx, ty, w, h) en TUILES, en écran ABSOLU — même arrondi que
        `UIText.tile_rect()` (bornes vers l'extérieur), mais résolu à travers
        la chaîne parent/enfant au lieu du seul offset LOCAL de `element`.

        Ce que l'allocation de la surface de composition doit lire (cf.
        `scene_text_reservation`, `surf_layout`) : deux enfants d'un même
        parent décalés localement de quelques pixels occupent des tuiles
        ÉCRAN très différentes selon où vit ce parent — `tile_rect()` seul
        (qui ignore les ancêtres) confondrait leur position avec celle du
        frame."""
        x, y, resolved = self.absolute_origin(element, actor_pos)
        tx, ty = x // TILE, y // TILE
        tw = _ceil_tile(x % TILE + int(element.w))
        th = _ceil_tile(y % TILE + int(element.h))
        return tx, ty, max(1, tw), max(1, th)

    def parent_origin(self, element, actor_pos) -> tuple[int, int]:
        """(x, y) écran de l'origine du PARENT de `element` — ou le socle du
        frame si `element` est un root. Sert à reconvertir une position absolue
        du canvas en coordonnées RELATIVES au parent, au relâchement d'un geste."""
        parent = self.get(element.parent) if element.parent else None
        if parent is None:
            if self.anchor == ANCHOR_ACTOR:
                ap = actor_pos(self.anchor_actor) if actor_pos else None
                return (ap[0], ap[1]) if ap else (0, 0)
            return (0, 0)
        ax, ay, _ = self.absolute_origin(parent, actor_pos)
        return ax, ay

    def frame_size(self, element) -> tuple[int, int]:
        """Cadre dans lequel un preset place `element` : son PARENT, ou l'écran
        s'il est racine. C'est le repère dans lequel son x/y vit déjà."""
        parent = self.get(getattr(element, "parent", "")) if element.parent else None
        if parent is not None:
            return int(parent.w), int(parent.h)
        return SCREEN_W, SCREEN_H

    def bg_regions(self, render_mode: int = 0) -> list:
        """Slots de texte rendus sur le BG."""
        return [r for r in self.slots
                if self.resolved_target(r, render_mode) == TARGET_BG]

    def obj_regions(self, render_mode: int = 0) -> list:
        return [r for r in self.slots
                if self.resolved_target(r, render_mode) == TARGET_OBJ]

    def bg_images(self, render_mode: int = 0) -> list:
        """Images écrites dans la tilemap — celles qui pèsent sur le charblock
        d'UI plutôt que sur l'OAM."""
        return [im for im in self.images
                if self.resolved_target(im, render_mode) == TARGET_BG]

    def sprite_names(self) -> set[str]:
        """Sprites que les images de cette mise en page réclament en VRAM.

        Le pendant exact de `font_names` : ce que la mise en page DÉCLARE, à
        charge de l'appelant d'y ajouter ce que les scripts font venir. Un nom
        vide (image pas encore reliée) n'entre pas — il ne coûte rien."""
        return {im.sprite_name for im in self.images if im.sprite_name}

    def font_names(self) -> set[str]:
        """Polices explicitement nommées par les slots. Un slot qui hérite de la
        scène n'apparaît PAS ici : c'est à l'appelant d'ajouter le défaut, lui
        seul connaît la scène. L'oublier ferait sous-réserver le bloc de glyphes
        — le texte s'écrirait alors dans les tuiles du décor."""
        return {r.font_name for r in self.slots if r.font_name}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "anchor": self.anchor,
            "anchor_actor": self.anchor_actor,
            "target": self.target,
            "elements": [e.to_dict() for e in self.elements],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UILayout":
        # `elements` (nouveau, multi-types) ou `regions` (hérité : que des zones,
        # sans `kind`). `element_from_dict` retombe sur la région par défaut.
        raw = d.get("elements")
        if raw is None:
            raw = d.get("regions", [])
        anchor = d.get("anchor")
        anchor_actor = d.get("anchor_actor")
        target = d.get("target")
        if anchor is None:                      # forme d'avant v0.25
            anchor, anchor_actor, target = cls._anchor_from_roots(raw)
        lay = cls(
            name     = str(d.get("name", "ui_layout")),
            anchor   = anchor if anchor in ANCHORS else ANCHOR_SCREEN,
            anchor_actor = str(anchor_actor or ""),
            target   = target if target in TARGETS else "",
            elements = [element_from_dict(e) for e in raw],
            notes    = str(d.get("notes", "")),
        )
        lay._migrate_list_axis(raw)
        return lay

    @staticmethod
    def _anchor_from_roots(raw: list) -> tuple[str, str, str]:
        """Remonte `anchor`/`anchor_actor`/`target` d'un fichier d'avant v0.25, où
        ils vivaient sur chaque élément RACINE, vers le nœud. La PREMIÈRE racine
        décide : un nœud n'a qu'un couple, et le cas multi-racines à ancrages
        divergents — rare — se règle désormais en plusieurs nœuds `Interface`, pas
        en une seule mise en page. `target` prend celui de la première racine qui
        en porte un (seul un `UIText` en avait). Champs relus une fois, jamais
        réécrits — « une forme ancienne se lit, une seule s'écrit »."""
        dicts = [e for e in raw if isinstance(e, dict)]
        names = {str(e.get("name", "")) for e in dicts}
        roots = [e for e in dicts
                 if not e.get("parent") or e.get("parent") not in names]
        first = roots[0] if roots else {}
        anchor = first.get("anchor", ANCHOR_SCREEN)
        anchor_actor = first.get("anchor_actor", "")
        target = next((e.get("target") for e in roots if e.get("target")), "")
        return anchor, anchor_actor, target

    def _migrate_list_axis(self, raw: list) -> None:
        """`list_axis: "horizontal"` d'avant le 2026-09-02 → une grille d'une
        seule rangée. La conversion se termine ICI et pas dans `UIList.from_dict`
        parce qu'elle a besoin du nombre de RANGÉES, c'est-à-dire des enfants —
        que l'élément seul ne connaît pas. Une liste verticale n'a rien à
        convertir : elle est déjà le défaut (`nav_columns == 1`)."""
        horizontal = {str(e.get("name", "")) for e in raw
                      if isinstance(e, dict) and e.get("list_axis") == "horizontal"}
        if not horizontal:
            return
        for e in self.elements:
            if getattr(e, "kind", "") != KIND_LIST or e.name not in horizontal:
                continue
            e.nav_columns = max(1, len([c for c in self.children(e.name)
                                        if getattr(c, "kind", "") == KIND_TEXT]))
            e.nav_major = NAV_ROW


# ── Le nœud Interface : l'instance d'un UILayout DANS une scène ────
# Un `UILayout` est un asset de CONTENU réutilisable (éléments, géométrie,
# glyphes) ; sa CIBLE DE RENDU — ancrage, cible BG/OBJ, acteur suivi, et le slot
# BG, donc sa place dans la pile de composition — est un fait PAR INSTANCE dans
# une scène (ROADMAP v0.12, « distinguer un asset de sa cible de rendu, le
# z-order en fait partie »). Le nœud porte ce chemin matériel ; l'asset n'en sait
# rien. Cela ACHÈVE la v0.25, qui disait déjà « le nœud possède anchor+target »
# mais le représentait par un simple nom faute de corps.

@dataclass
class InterfaceNode:
    """Une instance d'un `UILayout` dans une scène : réf de l'asset (par nom) +
    sa cible de rendu propre. Le pendant de `BackgroundLayer` pour l'UI.

    `anchor == ""` est le marqueur d'un nœud MIGRÉ depuis un simple nom (avant
    v0.12) dont la cible n'a pas encore été recopiée depuis l'asset : la première
    résolution par `Project.scene_ui_layouts` la remplit (cf. `BoundInterface`)."""
    layout_name:  str = ""            # nom du UILayout référencé (cf. BackgroundLayer.background_name)
    anchor:       str = ANCHOR_SCREEN  # "" = à migrer depuis l'asset
    anchor_actor: str = ""
    target:       str = ""             # "" = dérivée de l'ancrage (cf. resolved_target)
    bg_slot:      int = 1              # slot BG (0-3) quand la cible résout à BG ; ex-Scene.text_bg

    def to_dict(self) -> dict:
        return {
            "layout_name":  self.layout_name,
            "anchor":       self.anchor,
            "anchor_actor": self.anchor_actor,
            "target":       self.target,
            "bg_slot":      self.bg_slot,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InterfaceNode":
        # `anchor == ""` (marqueur « à migrer depuis l'asset ») est PRÉSERVÉ, pas
        # ramené à `screen` : un nœud nu sauvegardé avant sa première résolution
        # doit rester à migrer, sinon la cible réelle de l'asset serait perdue.
        anchor = d.get("anchor", ANCHOR_SCREEN)
        return cls(
            layout_name  = str(d.get("layout_name", "")),
            anchor       = anchor if (anchor in ANCHORS or anchor == "") else ANCHOR_SCREEN,
            anchor_actor = str(d.get("anchor_actor", "")),
            target       = d.get("target") if d.get("target") in TARGETS else "",
            bg_slot      = int(d.get("bg_slot", 1)),
        )


class BoundInterface:
    """Un `InterfaceNode` résolu contre son `UILayout` : la vue COMPOSÉE que
    `Project.scene_ui_layouts` rend, et que lisent canvas, codegen et inspecteurs.

    Le CONTENU (éléments, arbre, slots, images, géométrie) est délégué à l'asset.
    Ce qui est PAR-NŒUD à ce stade (v0.12, routage du slot) : `bg_slot`, lu du
    nœud. L'ancrage et la cible BG/OBJ restent portés par l'ASSET tant que leur
    routage par nœud n'existe pas au runtime — les champs `anchor`/`target` du
    nœud sont réservés pour cette étape, mais NE sont pas la source de vérité ici :
    les lire du nœud divergerait de `g_ui_regions` (qui grave la cible de l'asset)
    dès que l'auteur édite l'asset. On les lit donc de l'asset.

    La surface de méthodes reste celle d'un `UILayout`, pour que les appelants
    historiques (`.slots`, `.resolved_target(...)`, `.absolute_origin(...)`) ne
    changent pas."""

    def __init__(self, node: InterfaceNode, layout: "UILayout"):
        self.node = node
        self.layout = layout

    # ── Cible de rendu ────────────────────────────────────────────────
    # `bg_slot` : par nœud. `anchor`/`target`/`anchor_actor` : de l'asset (cf.
    # docstring — leur passage par nœud attend le routage runtime correspondant).
    @property
    def anchor(self) -> str:
        return self.layout.anchor

    @property
    def anchor_actor(self) -> str:
        return self.layout.anchor_actor

    @property
    def target(self) -> str:
        return self.layout.target

    @property
    def bg_slot(self) -> int:
        return self.node.bg_slot

    @property
    def layout_name(self) -> str:
        return self.node.layout_name

    def __getattr__(self, name):
        # Tout ce que la vue ne définit pas est du CONTENU : délégué à l'asset.
        # (Appelé seulement quand l'attribut manque sur l'instance/la classe, donc
        # jamais pour node/layout ni les propriétés/méthodes ci-dessus.)
        return getattr(self.layout, name)

    # ── Méthodes matérielles (ex-UILayout, lisant désormais le nœud) ──────
    def resolved_target(self, element=None, render_mode: int = 0) -> str:
        forced = forced_target(self.anchor, render_mode)
        if forced:
            return forced
        return self.target if self.target in TARGETS else TARGET_BG

    def effective_anchor(self, element=None) -> tuple[str, str]:
        return self.anchor, self.anchor_actor

    def absolute_origin(self, element, actor_pos) -> tuple[int, int, bool]:
        chain = [element] + [self.layout.get(a) for a in self.layout.ancestors(element.name)]
        chain = [e for e in chain if e is not None]
        ox = sum(int(e.x) for e in chain)
        oy = sum(int(e.y) for e in chain)
        resolved = True
        if self.anchor == ANCHOR_ACTOR:
            ap = actor_pos(self.anchor_actor) if actor_pos else None
            if ap is None:
                resolved = False
            else:
                ox += ap[0]
                oy += ap[1]
        return ox, oy, resolved

    def absolute_tile_rect(self, element, actor_pos) -> tuple[int, int, int, int]:
        x, y, _resolved = self.absolute_origin(element, actor_pos)
        tx, ty = x // TILE, y // TILE
        tw = _ceil_tile(x % TILE + int(element.w))
        th = _ceil_tile(y % TILE + int(element.h))
        return tx, ty, max(1, tw), max(1, th)

    def parent_origin(self, element, actor_pos) -> tuple[int, int]:
        parent = self.layout.get(element.parent) if element.parent else None
        if parent is None:
            if self.anchor == ANCHOR_ACTOR:
                ap = actor_pos(self.anchor_actor) if actor_pos else None
                return (ap[0], ap[1]) if ap else (0, 0)
            return (0, 0)
        ax, ay, _ = self.absolute_origin(parent, actor_pos)
        return ax, ay

    def bg_regions(self, render_mode: int = 0) -> list:
        return [r for r in self.layout.slots
                if self.resolved_target(r, render_mode) == TARGET_BG]

    def obj_regions(self, render_mode: int = 0) -> list:
        return [r for r in self.layout.slots
                if self.resolved_target(r, render_mode) == TARGET_OBJ]

    def bg_images(self, render_mode: int = 0) -> list:
        return [im for im in self.layout.images
                if self.resolved_target(im, render_mode) == TARGET_BG]


# ── Presets de placement ──────────────────────────────────────────
# Le bouton « Layout » de Godot et sa grille, ramenés à ce que le matériel
# permet : poser une boîte de dialogue basse sans taper x=0 y=120 w=240 h=40.
#
# Le CADRE de référence est le parent, ou l'écran pour un élément racine — le
# repère dans lequel x/y sont déjà stockés (cf. `absolute_origin`), donc le
# preset n'a aucune conversion à faire.
SCREEN_W, SCREEN_H = 240, 160

H_LEFT, H_CENTER, H_RIGHT = "left", "center", "right"
V_TOP, V_MIDDLE, V_BOTTOM = "top", "middle", "bottom"


def preset_rect(w: int, h: int, frame_w: int, frame_h: int,
                hpos: str, vpos: str,
                stretch_h: bool = False, stretch_v: bool = False,
                tile: bool = True) -> tuple[int, int, int, int]:
    """(x, y, w, h) d'un élément posé dans un cadre `frame_w × frame_h`.

    **Placer ne redimensionne pas.** Sans `stretch_*`, w/h ressortent tels
    quels : arrondir la taille au passage surprendrait (« j'ai cliqué en bas à
    gauche et ma boîte a grandi »). L'émetteur arrondit de toute façon vers le
    haut pour une cible BG.

    `tile` cale l'origine sur la grille 8×8 : le moteur écrit des entrées de
    tilemap, une origine entre deux tuiles n'existe pas. On cale vers le BAS
    (donc vers l'intérieur du cadre) — arrondir vers le haut pousserait un
    élément ferré à droite hors du cadre. Avec une taille déjà multiple de 8 et
    un cadre qui l'est aussi (240×160), le calage ne change rien : le cas
    courant tombe juste."""
    if stretch_h:
        x, w = 0, max(TILE, int(frame_w))
    else:
        w = max(TILE, int(w))
        x = {H_LEFT: 0, H_CENTER: (frame_w - w) // 2}.get(hpos, frame_w - w)
    if stretch_v:
        y, h = 0, max(TILE, int(frame_h))
    else:
        h = max(TILE, int(h))
        y = {V_TOP: 0, V_MIDDLE: (frame_h - h) // 2}.get(vpos, frame_h - h)
    if tile:
        x -= x % TILE
        y -= y % TILE
        if stretch_h:
            w = _ceil_tile(w) * TILE
        if stretch_v:
            h = _ceil_tile(h) * TILE
    return int(x), int(y), int(w), int(h)


def unique_element_name(taken, base: str = "element") -> str:
    """Nom d'élément libre mais unique dans `taken` — générique, tous types
    (alias de `unique_region_name`, dont la logique ne dépend pas du type)."""
    return unique_region_name(taken, base)


def unique_region_name(taken, base: str = "region") -> str:
    """Nom libre mais unique **dans tout le projet** — `taken` est l'ensemble
    des noms déjà pris (cf. `Project.region_names()`).

    Pourquoi projet et pas mise en page : le nom se résout en `REGION_<NOM>`,
    un index dans une table C plate, exactement comme une clé de texte ou un
    nom de police. Deux régions homonymes dans deux mises en page rendraient
    la constante indécidable.

    Conséquence assumée : deux mises en page ne peuvent pas avoir chacune leur
    « boite_bas » ; la seconde devient `boite_bas_02`. Le jour où l'on voudra
    qu'un même script vise « la boîte basse de la mise en page COURANTE », il
    faudra une indirection par scène — la constante ne bougerait pas, seule sa
    résolution changerait, donc ce n'est pas une impasse."""
    taken = set(taken)
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n:02d}" in taken:
        n += 1
    return f"{base}_{n:02d}"
