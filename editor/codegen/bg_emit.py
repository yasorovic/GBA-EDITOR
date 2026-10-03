"""codegen/bg_emit.py — émet un fond COMPRESSÉ (métadonnées BackgroundAsset) en C.

Produit des tableaux compatibles grit ({sym}Tiles / {sym}TilesLen / {sym}Map)
pour réutiliser tel quel le chargement de main_gen (copy16 + load_map). La
différence vs grit : les SE portent un pal_bank PAR TUILE et le fond utilise
jusqu'à 16 palettes (chargées via g_pal_bg, cf. main_gen), là où grit ne fait
qu'une palette de 16.
"""
from __future__ import annotations


def _tile_words(hextile: str) -> list[int]:
    """Tuile (64 nibbles hex, index 0-15) -> 8 mots u32 (format tuile 4bpp GBA :
    pixel i de la rangée dans le nibble i)."""
    idx = [int(ch, 16) for ch in hextile]
    return [sum((idx[r * 8 + i] & 0xF) << (4 * i) for i in range(8)) for r in range(8)]


def _tile_words_8bpp(hextile: str) -> list[int]:
    """Tuile 8bpp (128 hex, 64 index 0-255) -> 16 mots u32 (format tuile 8bpp GBA :
    chaque rangée de 8 octets = 2 mots u32, pixel i dans l'octet i)."""
    idx = [int(hextile[i:i + 2], 16) for i in range(0, len(hextile), 2)]
    out: list[int] = []
    for r in range(8):
        row = idx[r * 8:r * 8 + 8]
        out.append(sum((row[i] & 0xFF) << (8 * i) for i in range(4)))
        out.append(sum((row[4 + i] & 0xFF) << (8 * i) for i in range(4)))
    return out


def tileset_words(tileset: list, bpp: int = 4) -> list[int]:
    out: list[int] = []
    pack = _tile_words_8bpp if bpp == 8 else _tile_words
    for t in tileset:
        out += pack(t)
    return out


def emit_bg_c(sym: str, tileset: list, tilemap: list, pal_offset: int = 0,
              bpp: int = 4) -> tuple[str, str]:
    """Retourne (source .c, header .h) compatibles grit pour un fond compressé.

    `pal_offset` : banque physique de la 1ère sous-palette de ce fond dans
    PAL_BG_RAM (allouée par palette_alloc.scene_bank_layout — plusieurs fonds
    compressés d'une même scène occupent des blocs de banques distincts). Les
    SE stockent un pal_bank LOCAL (0..N-1, relatif à la palette de l'asset) ;
    on le décale ici vers sa banque physique réelle. `bpp` : 4 (tuiles 8 u32) ou
    8 (tuiles 16 u32, pal_bank ignoré par le hardware → pal_offset sans effet)."""
    tiles = tileset_words(tileset, bpp)
    se = [(w + (pal_offset << 12)) & 0xFFFF for w in tilemap] if pal_offset else list(tilemap)
    tiles_len = len(tiles) * 4
    attr = '__attribute__((aligned(4)))'
    c = (
        f"const unsigned int {sym}Tiles[{len(tiles)}] {attr}=\n"
        "{" + ",".join(f"0x{w:08X}" for w in tiles) + "};\n\n"
        f"const unsigned short {sym}Map[{len(se)}] {attr}=\n"
        "{" + ",".join(f"0x{w:04X}" for w in se) + "};\n"
    )
    h = (
        f"#ifndef GRIT_{sym.upper()}_H\n#define GRIT_{sym.upper()}_H\n\n"
        f"#define {sym}TilesLen {tiles_len}\n"
        f"extern const unsigned int {sym}Tiles[{len(tiles)}];\n\n"
        f"extern const unsigned short {sym}Map[{len(se)}];\n\n"
        f"#endif // GRIT_{sym.upper()}_H\n"
    )
    return c, h


def emit_bg_anim_c(sym: str, tables: list) -> tuple[str, str]:
    """Tables d'images des fonds ANIMÉS d'une scène — (source .c, header .h).

    `tables` = [(nom du symbole, [entrées de carte])], chaque table contenant
    toutes les images à la suite (cf. bg_anim.frame_table). Les entrées portent
    déjà leur décalage de tuile et de banque : le runtime ne fait que recopier un
    rectangle, il ne calcule rien.

    Groupées PAR SCÈNE dans leur propre fichier, et non avec le calque : la
    banque de palette d'un animé dépend de l'allocation de la scène, alors que le
    C d'un calque est partagé entre les scènes qui le posent. Les mêlerait-on que
    la première scène compilée imposerait ses couleurs aux autres."""
    parts, decls = [], []
    attr = '__attribute__((aligned(4)))'
    for name, se in tables:
        parts.append(
            f"const unsigned short {name}[{len(se)}] {attr}=\n"
            "{" + ",".join(f"0x{w:04X}" for w in se) + "};\n"
        )
        decls.append(f"extern const unsigned short {name}[{len(se)}];")
    c = "\n".join(parts) if parts else "/* no animated background in this scene */\n"
    h = (
        f"#ifndef {sym.upper()}_H\n#define {sym.upper()}_H\n\n"
        + "\n".join(decls) + ("\n\n" if decls else "\n")
        + f"#endif // {sym.upper()}_H\n"
    )
    return c, h


def emit_bg_tileanim_c(sym: str, tables: list, bpp: int = 4) -> tuple[str, str]:
    """Tables de PIXELS des fonds animés en mode `shared` — (source .c, header .h).

    `tables` = [(nom du symbole, [tuiles hex])], les tuiles rangées image par
    image puis case par case. Contrairement au mode `instance`, ce qui voyage
    vers la VRAM à chaque changement d'image n'est pas une entrée de carte mais
    la tuile elle-même — d'où des mots de 32 bits, au format tuile du matériel.

    Fichier séparé de celui des tables d'entrées : rien ne les lie, et le mode
    d'un animé peut changer d'une session à l'autre."""
    parts, decls = [], []
    attr = '__attribute__((aligned(4)))'
    for name, tiles in tables:
        words = tileset_words(tiles, bpp)
        parts.append(
            f"const unsigned int {name}[{len(words)}] {attr}=\n"
            "{" + ",".join(f"0x{w:08X}" for w in words) + "};\n"
        )
        decls.append(f"extern const unsigned int {name}[{len(words)}];")
    c = "\n".join(parts) if parts else "/* no shared animated background in this scene */\n"
    h = (
        f"#ifndef {sym.upper()}_H\n#define {sym.upper()}_H\n\n"
        + "\n".join(decls) + ("\n\n" if decls else "\n")
        + f"#endif // {sym.upper()}_H\n"
    )
    return c, h
