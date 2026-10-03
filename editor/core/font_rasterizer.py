"""Rasterisation éphémère des sources vectorielles.

Ce module est le seul endroit où une fonte TTF/OTF devient une grille de
couverture. Il ne connaît ni tuiles, ni palette, ni Qt : la même sortie peut
donc être consommée par le build et par l'aperçu de l'éditeur.

Rien n'est écrit sur disque. Les fichiers vectoriels restent des sources dans
``assets/fonts/`` ; le sous-ensemble de glyphes ne sera matérialisé qu'au
moment de l'export GBA.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


class FontRasterizerError(RuntimeError):
    """Une source vectorielle ne peut pas être rasterisée."""


class FontRasterizerUnavailable(FontRasterizerError):
    """La dépendance FreeType de build n'est pas installée."""


@dataclass(frozen=True)
class RasterGlyph:
    """Un glyphe raster, avant toute décision propre à la GBA.

    ``coverage`` contient ``width * height`` octets, de 0 (transparent) à 255
    (encre pleine), rangés par lignes. ``bearing_y`` est mesuré au-dessus de la
    ligne de base : il permet d'aligner des sources de repli sans que le
    rasterizer ne connaisse le layout qui les emploie.
    """

    char: str
    width: int
    height: int
    coverage: bytes
    advance: int
    bearing_x: int
    bearing_y: int
    source_name: str = ""
    # RGB source, trois octets par pixel, facultatif pour les fontes
    # vectorielles. Une planche bitmap le renseigne afin que l'encodage conserve
    # ses indices/couleurs de palette au lieu de la réduire à un masque alpha.
    colors: bytes = b""

    def __post_init__(self):
        if len(self.char) != 1:
            raise ValueError("RasterGlyph expects exactly one character")
        if self.width < 0 or self.height < 0:
            raise ValueError("the dimensions of a RasterGlyph must not be negative")
        if len(self.coverage) != self.width * self.height:
            raise ValueError("the coverage does not match the dimensions")
        if self.colors and len(self.colors) != self.width * self.height * 3:
            raise ValueError("the colours do not match the pixels")

    def coverage_at(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return 0
        return self.coverage[y * self.width + x]

    def color_at(self, x: int, y: int) -> tuple[int, int, int] | None:
        """Couleur source d'un pixel bitmap, ou ``None`` pour une couverture
        vectorielle (qui sera mise en palette par l'encodeur)."""
        if not self.colors or not (0 <= x < self.width and 0 <= y < self.height):
            return None
        offset = (y * self.width + x) * 3
        return tuple(self.colors[offset:offset + 3])


def _freetype():
    try:
        import freetype
    except ImportError as exc:
        raise FontRasterizerUnavailable(
            "Vector rasterisation requires freetype-py. Install the editor's "
            "dependencies."
        ) from exc
    return freetype


def _face(freetype, source_path, faces=None):
    """La ``Face`` FreeType du fichier source.

    ``faces`` (optionnel) est une table ``{chemin: Face}`` LOCALE à un lot de
    rasterisations — cf. ``build_font_asset``, qui rastérise des dizaines de
    glyphes d'une même police. Sans elle, chaque glyphe re-parsait le fichier
    entier (une ``Face`` par appel, ×2 avec ``glyph_exists``) : c'était le coût
    dominant de l'ouverture d'un projet. Avec elle, le fichier n'est lu qu'UNE
    fois par source. La table ne vit que le temps de l'appel qui la crée (aucun
    état de module, donc rien à invalider ni à partager entre threads) ; les
    ``Face`` se libèrent à sa disparition. ``set_pixel_sizes``/``load_char``
    restent réappliqués à chaque glyphe, la réutilisation est donc sûre."""
    key = str(source_path)
    if faces is None:
        return freetype.Face(key)
    face = faces.get(key)
    if face is None:
        face = freetype.Face(key)
        faces[key] = face
    return face


def _load_flags(freetype, hinting: str, *, grid_fit: bool = False) -> int:
    """Traduit le vocabulaire persistant en choix FreeType, localement."""
    flags = freetype.FT_LOAD_RENDER
    if hinting == "none":
        return flags | freetype.FT_LOAD_NO_HINTING
    if hinting == "light":
        return flags | freetype.FT_LOAD_TARGET_LIGHT
    if hinting == "mono" or grid_fit:
        return flags | freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_MONOCHROME
    return flags


def resolved_pixel_fit(pixel_fit: str, pixel_height: int, *, has_bitmap_strike: bool) -> str:
    """Résout la recette demandée en une opération réalisable par FreeType.

    À très petite taille, l'alignement mono est plus prévisible qu'une simple
    réduction de contours anti-crénelés. Une strike exactement à la taille
    demandée reste toutefois la meilleure réponse quand la fonte en propose.
    """
    if pixel_fit == "bitmap_strike" and has_bitmap_strike:
        return "bitmap_strike"
    if pixel_fit == "auto" and has_bitmap_strike:
        return "bitmap_strike"
    if pixel_fit == "grid_fit" or (pixel_fit == "auto" and pixel_height <= 6):
        return "grid_fit"
    return "native"


def _select_embedded_strike(face, pixel_height: int) -> bool:
    """Choisit seulement une strike dont la taille correspond exactement.

    Une strike proche modifierait la recette demandée par l'auteur. Sans
    équivalent exact, ``set_pixel_sizes`` laisse FreeType vectoriser la face.
    """
    for index, size in enumerate(getattr(face, "available_sizes", ())):
        y_ppem = getattr(size, "y_ppem", 0)
        height = getattr(size, "height", 0)
        if y_ppem == pixel_height * 64 or height == pixel_height:
            face.select_size(index)
            return True
    return False


def _has_embedded_strike(face, pixel_height: int) -> bool:
    """Une strike exacte existe-t-elle, sans changer la taille active ?"""
    return any(
        getattr(size, "y_ppem", 0) == pixel_height * 64
        or getattr(size, "height", 0) == pixel_height
        for size in getattr(face, "available_sizes", ())
    )


def _coverage(bitmap, freetype) -> bytes:
    """Normalise les bitmaps Gray ou mono de FreeType en 0..255.

    Vectorisé (numpy) : le tampon entier est traité d'un bloc au lieu d'un
    double `for` par pixel. Sortie octet-pour-octet identique à l'ancienne
    boucle — `np.rint` arrondit au pair le plus proche, comme `round`."""
    width, rows, pitch = int(bitmap.width), int(bitmap.rows), int(bitmap.pitch)
    if not width or not rows:
        return b""
    stride = abs(pitch)
    # Tampon brut en (rows, stride), dans l'ordre mémoire des lignes source.
    raw = np.frombuffer(bytes(bitmap.buffer), dtype=np.uint8)[:rows * stride]
    raw = raw.reshape(rows, stride)
    mono = bitmap.pixel_mode == freetype.FT_PIXEL_MODE_MONO
    if mono:
        # 1 bit/pixel, MSB d'abord (0x80 >> (x % 8)) : dépaquetage direct.
        bits = np.unpackbits(raw, axis=1)          # (rows, stride*8), MSB-first
        out = np.where(bits[:, :width] != 0, 255, 0).astype(np.uint8)
    else:
        vals = raw[:, :width].astype(np.int32)     # Gray brut (0..grays-1)
        grays = max(2, int(getattr(bitmap, "num_grays", 256)))
        # FT_GRAY_NUM_GRAYS vaut normalement 256, mais cette formule garde la
        # sortie correcte pour une strike à autre profondeur.
        out = np.rint(vals * 255 / (grays - 1)).astype(np.uint8)
    if pitch < 0:                                  # lignes de bas en haut
        out = out[::-1]
    return out.tobytes()


def glyph_exists(source_path: Path, char: str, faces=None) -> bool:
    """Vrai si la face possède réellement ce caractère, hors .notdef."""
    if len(char) != 1:
        return False
    freetype = _freetype()
    try:
        face = _face(freetype, source_path, faces)
        return bool(face.get_char_index(ord(char)))
    except Exception as exc:  # FreeType expose plusieurs classes d'erreur.
        raise FontRasterizerError(f"Cannot read \"{source_path.name}\": {exc}") from exc


def rasterize_vector_glyph(
    source_path: Path,
    char: str,
    *,
    pixel_height: int,
    hinting: str = "normal",
    pixel_fit: str = "auto",
    prefer_bitmap_strike: bool = True,
    offset_x: int = 0,
    offset_y: int = 0,
    source_name: str = "",
    faces=None,
) -> RasterGlyph:
    """Rastérise un caractère TTF/OTF en couverture, sans effet de bord."""
    if len(char) != 1:
        raise ValueError("rasterize_vector_glyph expects exactly one character")
    if pixel_height < 1:
        raise ValueError("pixel_height must be positive")
    freetype = _freetype()
    try:
        face = _face(freetype, source_path, faces)
        fit = resolved_pixel_fit(
            pixel_fit, pixel_height,
            has_bitmap_strike=(pixel_fit == "bitmap_strike" or prefer_bitmap_strike)
            and _has_embedded_strike(face, pixel_height),
        )
        used_strike = fit == "bitmap_strike" and _select_embedded_strike(face, pixel_height)
        if not used_strike:
            face.set_pixel_sizes(0, pixel_height)
        if not face.get_char_index(ord(char)):
            raise FontRasterizerError(f"\"{char}\" is not covered by {source_path.name}")
        face.load_char(ord(char), _load_flags(freetype, hinting, grid_fit=fit == "grid_fit"))
        slot, bitmap = face.glyph, face.glyph.bitmap
    except FontRasterizerError:
        raise
    except Exception as exc:
        raise FontRasterizerError(f"Cannot rasterise \"{source_path.name}\": {exc}") from exc

    return RasterGlyph(
        char=char,
        width=int(bitmap.width), height=int(bitmap.rows),
        coverage=_coverage(bitmap, freetype),
        advance=round(slot.advance.x / 64),
        bearing_x=int(slot.bitmap_left) + offset_x,
        bearing_y=int(slot.bitmap_top) + offset_y,
        source_name=source_name,
    )


_BAYER_2X2 = ((0, 2), (3, 1))
_BAYER_4X4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def display_coverage(value: int, x: int, y: int, *, raster_mode: str,
                     threshold: int, dither_pattern: str) -> int:
    """Applique la recette de sortie à un pixel, pour preview ou export.

    Le mode ``coverage`` conserve l'anti-crénelage. Les deux autres donnent
    une encre binaire ; le dither déplace localement le seuil, pas le glyphe.
    """
    value = max(0, min(255, int(value)))
    if raster_mode == "coverage":
        return value
    if raster_mode == "dither" and dither_pattern != "none":
        matrix = _BAYER_2X2 if dither_pattern == "bayer_2x2" else _BAYER_4X4
        size = len(matrix)
        # ± la moitié d'un pas : un seuil 128 garde la couverture moyenne.
        threshold += round(((matrix[y % size][x % size] + .5) / (size * size) - .5) * 255)
    return 255 if value >= max(0, min(255, threshold)) else 0


def raster_glyph_cell(raster: RasterGlyph, cell_w: int, cell_h: int, *, raster_mode: str,
                      threshold: int, dither_pattern: str, anchor_h: int | None = None
                      ) -> tuple[list[list[int]], list[list]]:
    """L'ANCRAGE et le CLIP réels d'un glyphe dans sa cellule GBA.

    Le glyphe est posé par son bearing : la ligne de base virtuelle est à
    ``anchor_h`` de son sommet (l'interligne DÉCLARÉ, en pixels bruts —
    ``anchor_h`` par défaut à ``cell_h`` si on ne le précise pas), ``bearing_y``
    au-dessus. Tout pixel qui tombe hors de ``cell_w`` x ``cell_h`` (la cellule
    arrondie à la tuile) est perdu — pas reporté sur une tuile suivante.
    ``anchor_h`` et ``cell_h`` divergent dès que l'interligne n'est pas déjà un
    multiple de 8 : l'ancrage reste au pixel brut, seul le clip est arrondi.
    C'est le SEUL calcul de placement/clip ; l'encodeur GBA et l'aperçu de
    l'éditeur l'appellent tous deux, pour ne jamais promettre un rendu que
    l'autre ne tient pas.

    Renvoie deux grilles ``cell_h`` x ``cell_w`` : la couverture (déjà passée
    par ``display_coverage``) et la couleur source (``None`` pour une police
    vectorielle, un ``(r,g,b)`` pour une planche bitmap que l'appelant devra
    mettre en palette).
    """
    anchor = cell_h if anchor_h is None else anchor_h
    base_y = max(0, anchor - raster.bearing_y)
    coverage = [[0] * cell_w for _ in range(cell_h)]
    color = [[None] * cell_w for _ in range(cell_h)]
    for y in range(raster.height):
        dy = base_y + y
        if not 0 <= dy < cell_h:
            continue
        for x in range(raster.width):
            dx = raster.bearing_x + x
            if not 0 <= dx < cell_w:
                continue
            coverage[dy][dx] = display_coverage(raster.coverage_at(x, y), dx, dy,
                                                raster_mode=raster_mode, threshold=threshold,
                                                dither_pattern=dither_pattern)
            color[dy][dx] = raster.color_at(x, y)
    return coverage, color


def _asset_source_names(asset, variant: str, weight: int | None = None,
                        italic: bool | None = None) -> list[str]:
    """La chaîne explicite a priorité ; les faces auto servent de défaut."""
    names = asset.source_names(variant)
    # Une chaîne regular configurée à la main est la réponse explicite pour
    # Regular. Pour un autre poids, les faces de famille sont prioritaires :
    # sélectionner Bold ne doit jamais rasteriser Regular par accident.
    if names and (weight is None or weight == 400) and (italic is None or not italic):
        return names
    wanted = {
        "regular": (400, False), "bold": (700, False),
        "italic": (400, True), "bold_italic": (700, True),
    }.get(variant, (400, False))
    target_weight = wanted[0] if weight is None else weight
    target_italic = wanted[1] if italic is None else italic
    return [face.source_name for face in asset.faces
            if face.weight == target_weight and face.italic == target_italic]


def rasterize_asset_glyph(project, asset, char: str, variant: str = "regular",
                           weight: int | None = None, italic: bool | None = None,
                           faces=None) -> RasterGlyph:
    """Résout la couverture d'un ``FontAsset`` dans l'ordre de ses sources.

    L'accès au projet sert uniquement à résoudre les noms et chemins. Dès que
    la source est choisie, l'opération délègue à ``rasterize_vector_glyph``, la
    fonction pure que le build utilisera également.

    ``faces`` : table ``{chemin: Face}`` optionnelle, partagée sur toute une
    passe de rasterisation pour ne charger chaque police qu'une fois (cf.
    ``_face`` et ``build_font_asset``).
    """
    names = _asset_source_names(asset, variant, weight, italic)
    if not names:
        raise FontRasterizerError("This asset has no source for this variant.")
    problems: list[str] = []
    for name in names:
        source = project.fonts.get(name)
        if source is None:
            problems.append(f"{name} was not found")
            continue
        # `asset_abs` fait un `.resolve()` (appel filesystem, lent sur Windows) :
        # inchangé pour tous les glyphes d'une même source, on le mémoïse sur la
        # passe plutôt que de le refaire à chaque caractère.
        if faces is None:
            path = project.asset_abs(source.asset)
        else:
            pkey = ("path", source.asset)
            if pkey in faces:
                path = faces[pkey]
            else:
                path = project.asset_abs(source.asset)
                faces[pkey] = path
        if not path or not path.exists():
            problems.append(f"the file of {name} was not found")
            continue
        if source.source_format in ("png", "fnt"):
            glyph = source.glyph(char)
            if glyph is None:
                problems.append(f"{name} does not cover this character")
                continue
            try:
                from PIL import Image
                # Même remède que `_face` pour le chemin vectoriel : la planche
                # PNG était rouverte et redécodée à CHAQUE glyphe (1000+ pour une
                # police japonaise), coût dominant de l'ouverture d'un projet à
                # polices bitmap. Réutilisée depuis la table de passe si fournie.
                ikey = ("img", str(path))
                image = faces.get(ikey) if faces is not None else None
                if image is None:
                    image = Image.open(path).convert("RGBA")
                    if faces is not None:
                        faces[ikey] = image
                # Vectorisé (numpy) : le rectangle du glyphe est découpé et
                # transformé d'un bloc au lieu d'un double `for` par pixel — le
                # coût dominant de l'ouverture d'un projet à polices bitmap.
                # Sortie octet-pour-octet identique à l'ancienne boucle.
                arr = np.asarray(image)                    # (H, W, 4) uint8
                H, W = int(arr.shape[0]), int(arr.shape[1])
                gw, gh, gx, gy = glyph.w, glyph.h, glyph.x, glyph.y
                coverage = np.zeros((gh, gw), dtype=np.uint8)
                colors = np.zeros((gh, gw, 3), dtype=np.uint8)
                # Rectangle clampé à la planche : un pixel hors-bord reste 0,
                # exactement comme le `continue` par pixel d'avant.
                vw = max(0, min(gw, W - gx))
                vh = max(0, min(gh, H - gy))
                if vw and vh:
                    sub = arr[gy:gy + vh, gx:gx + vw]
                    rgb, alpha = sub[..., :3], sub[..., 3]
                    colors[:vh, :vw] = rgb
                    keycols = [tuple(c) for c in source.key_colors()]
                    if keycols:
                        keyarr = np.array(keycols, dtype=np.uint8)   # (K, 3)
                        # Chaque pixel comparé à chaque key color, en bloc.
                        is_key = (rgb[:, :, None, :] == keyarr).all(-1).any(-1)
                        coverage[:vh, :vw] = np.where(is_key, 0, alpha)
                    else:
                        coverage[:vh, :vw] = alpha
                return RasterGlyph(char, gw, gh, coverage.tobytes(),
                                   glyph.advance, glyph.ox, glyph.h - glyph.oy,
                                   source_name=name, colors=colors.tobytes())
            except Exception as exc:
                problems.append(f"cannot read the bitmap of {name} ({exc})")
                continue
        if source.source_format not in ("ttf", "otf"):
            problems.append(f"{name} has a format that cannot be rendered")
            continue
        if glyph_exists(path, char, faces):
            return rasterize_vector_glyph(
                path, char, pixel_height=asset.pixel_height, hinting=asset.hinting,
                pixel_fit=asset.pixel_fit,
                prefer_bitmap_strike=asset.prefer_bitmap_strike,
                offset_x=asset.offset_x, offset_y=asset.offset_y, source_name=name,
                faces=faces,
            )
    detail = " ; ".join(problems) or "no source covers this character"
    raise FontRasterizerError(f"\"{char}\" cannot be rendered: {detail}.")
