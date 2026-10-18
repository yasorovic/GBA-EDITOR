"""Pont éphémère entre une :class:`FontAsset` et l'encodage GBA.

Les recettes restent des données d'éditeur.  Ce module les matérialise seulement
pendant le build en objets ``Font`` compatibles avec le reste du codegen.  Ainsi
le compteur VRAM, le choix tilemap/composition et l'émetteur C lisent exactement
les mêmes glyphes.
"""
from __future__ import annotations

from core.font_rasterizer import FontRasterizerError, rasterize_asset_glyph
from core.models.font import Font, Glyph


def available_project_font_names(project) -> set[str]:
    """Noms sélectionnables sans matérialiser les glyphes.

    L'inspecteur n'a besoin ici que de savoir si une recette possède au moins
    une source lisible. Appeler ``project_build_fonts`` à cette étape
    rasterisait tous les caractères de toutes les FontAsset juste pour remplir
    un menu, ce qui bloquait l'ouverture d'une scène sur les projets riches en
    texte. La matérialisation reste réservée au build et aux aperçus qui en ont
    réellement besoin.
    """
    sources = getattr(project, "fonts", ())
    out: set[str] = set()
    for asset in getattr(project, "font_assets", ()):
        for source_names in getattr(asset, "sources", {}).values():
            if any(
                (source := sources.get(name)) is not None
                and getattr(source, "asset", None)
                and project.asset_abs(source.asset).exists()
                for name in source_names
            ):
                out.add(asset.name)
                break
    # Chemin de migration : une Font brute reste sélectionnable tant qu'aucune
    # FontAsset logique ne la remplace.
    for font in sources:
        path = project.asset_abs(font.asset) if getattr(font, "asset", None) else None
        if path and path.exists() and getattr(font, "glyphs", None):
            out.add(font.name)
    return out


def project_codepoints(project) -> set[str]:
    """Caractères littéraux connus dans toutes les langues du projet.

    Les scripts dynamiques restent un cas sûr : ils ne réduisent jamais la
    police, car ``build_font_asset`` garde alors les glyphes bitmap disponibles.
    Les caractères BMP sont la limite déjà imposée par le runtime.
    """
    out = {" "}
    texts = project.build_texts() if hasattr(project, "build_texts") else getattr(project, "texts", ())
    for text in texts:
        values = [getattr(text, "content", "")]
        for code in [getattr(lang, "code", "")
                     for lang in getattr(getattr(project, "settings", None), "languages", ())]:
            values.append(project.text_content(text, code) if hasattr(project, "text_content") else "")
        for value in values:
            out.update(ch for ch in value if ord(ch) < 0x10000 and ch not in "\r\n")
    return out


def _bitmap_chars(project, asset) -> set[str]:
    out: set[str] = set()
    sources = getattr(project, "fonts", ())
    for names in getattr(asset, "sources", {}).values():
        for name in names:
            source = sources.get(name) if hasattr(sources, "get") else None
            if source and source.source_format in ("png", "fnt"):
                out.update(g.char for g in source.glyphs if len(g.char) == 1)
    return out


def build_font_asset(project, asset, chars: set[str] | None = None) -> Font:
    """Rastérise le sous-ensemble nécessaire d'un asset pour la ROM.

    ``raster_glyphs`` est volontairement attaché à l'objet temporaire, jamais
    persisté dans le sidecar. ``encode_font`` le reconnaît et ne relit donc pas
    une planche intermédiaire sur disque.
    """
    chars = set(chars or project_codepoints(project)) | _bitmap_chars(project, asset)
    glyphs, rasters = [], {}
    # Table de faces LOCALE à ce build : chaque fichier de police n'est chargé
    # qu'une fois pour tous ses glyphes (au lieu d'une Face par glyphe, ×2 avec
    # glyph_exists). Locale → aucun état partagé entre threads, libérée au retour.
    faces: dict = {}
    for char in sorted(chars, key=ord):
        try:
            raster = rasterize_asset_glyph(project, asset, char, faces=faces)
        except FontRasterizerError:
            continue
        # La cellule tient la ligne demandée ; le vrai dépôt (bearings inclus)
        # est fait par encode_font à partir du RasterGlyph.
        width = max(1, raster.width + max(0, raster.bearing_x))
        glyphs.append(Glyph(char=char, w=width, h=max(1, asset.line_height),
                            advance=max(1, raster.advance)))
        rasters[char] = raster
    font = Font(name=asset.name, source_format="raster",
                cell_w=max(1, asset.pixel_height),
                cell_h=max(1, asset.line_height),
                line_height=max(1, asset.line_height), glyphs=glyphs,
                bg_color=asset.bg_color, space_color=asset.space_color)
    font.raster_glyphs = rasters
    font.raster_mode = asset.raster_mode
    font.coverage_threshold = asset.coverage_threshold
    font.dither_pattern = asset.dither_pattern
    return font


def project_build_fonts(project) -> list[Font]:
    """Liste unique des polices compilables, nommées comme les TextBox.

    Les projets antérieurs à v0.26 restent valides : une source non couverte par
    un FontAsset conserve l'ancien chemin planche PNG/BMFont.
    """
    # Cette requête est lue à la fois par l'émission, l'allocateur et le canvas.
    # Un cache par état observable évite de rerasteriser une famille entière à
    # chaque lecteur, mais l'horodatage des sources invalide bien une retouche
    # externe détectée par le watcher.
    source_state = []
    for source in getattr(project, "fonts", ()):
        path = project.asset_abs(source.asset) if getattr(source, "asset", None) else None
        try:
            stamp = path.stat().st_mtime_ns if path else None
        except OSError:
            stamp = None
        source_state.append((source.name, stamp))
    signature = (tuple(repr(asset.to_dict()) for asset in getattr(project, "font_assets", ())),
                 tuple(source_state),
                 tuple((text.id, text.content) for text in (
                     project.build_texts() if hasattr(project, "build_texts")
                     else getattr(project, "texts", ()))),
                 repr(getattr(project, "translations", {})))
    cached = getattr(project, "_font_build_cache", None)
    if cached and cached[0] == signature:
        return cached[1]

    chars = project_codepoints(project)
    assets = list(getattr(project, "font_assets", ()))
    built = [build_font_asset(project, asset, chars) for asset in assets]
    names = {font.name for font in built}
    for font in getattr(project, "fonts", ()):
        if font.name not in names and font.asset and font.glyphs:
            path = project.asset_abs(font.asset)
            if path and path.exists():
                built.append(font)
    project._font_build_cache = (signature, built)
    return built
