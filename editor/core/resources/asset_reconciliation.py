"""Orchestration d'encodage GBA déclenchée par l'apparition/suppression d'un
fichier asset sur disque (ProjectWatcher, dialogues d'import UI). Calcule
l'encodage (délégué à core.bg_import / core.sprite_import) et l'applique au
sidecar JSON (BackgroundAsset / SpriteAsset) — jamais le PNG source.

Deux déclencheurs, un seul geste : `sync_*` pour UN fichier qui apparaît
maintenant, `reconcile_*` (en fin de module) pour le dossier entier à
l'ouverture d'un projet, quand des fichiers ont été déposés éditeur fermé."""

from pathlib import Path
from typing import Optional

from core.models.background import BackgroundAsset
from core.models.sprite import SpriteAsset, IMAGE_FILE_EXTS
from core.models.audio import MUSIC_FILE_EXTS, SFX_FILE_EXTS, WAV_BITS_OK


def _relink_source(store, asset, rel: str, cited: Optional[Path]) -> None:
    """Raccroche un asset au fichier qui PORTE SON NOM, quand celui que son
    sidecar cite a disparu.

    Les trois familles à sidecar (fonds, sprites, polices) sont keyées par le
    stem de leur fichier source. Une planche renommée dans l'explorateur laisse
    donc le sidecar citer un chemin mort : l'asset s'affiche vide, et le fichier
    renommé en crée un SECOND à côté — c'est le doublon observé dans l'écran
    Police. Le fichier trouvé sous le nom de l'asset est la seule source
    plausible : on le raccroche, plutôt que de laisser une entrée sans image.

    Ne fait rien tant que le fichier cité existe — c'est ce qui empêche de
    voler sa source à un asset bien portant. `rel` s'écrit dans la convention
    de la famille (chemin relatif au projet, ou simple nom de fichier pour un
    fond) : c'est l'appelant qui la connaît, comme il connaît `cited`."""
    if cited is not None and cited.exists():
        return
    asset.asset = rel
    store.save(asset)


def _sourced_by(store, path: Path, resolve) -> bool:
    """Ce fichier est-il DÉJÀ la source d'un asset de la famille ?

    Le pendant du raccrochage : quand un asset cite un fichier sous un autre
    nom que le sien (un renommage qui n'a pas pu emporter le PNG, un `.fnt` qui
    nomme sa page), ce fichier ne doit pas fonder un second asset sur la même
    image. `resolve` rend le chemin absolu que cite un asset — la convention de
    la famille, encore une fois."""
    return any(resolve(a) == path for a in store)


def check_audio_file(path) -> Optional[str]:
    """None si le fichier est utilisable, sinon la raison du refus, rédigée
    pour être affichée telle quelle à l'auteur.

    Ce contrôle n'est pas une ceinture de plus : c'est le SEUL. mmutil ne
    renvoie jamais un code d'erreur — ni sur un wav 24 bits (dont il émet
    quand même la constante, donc un effet muet dans la ROM), ni sur une
    extension inconnue. S'il n'y a pas de refus ici, il n'y en a nulle part.

    Appelé à l'import ET par le validateur, parce que le ProjectWatcher
    ramasse aussi les fichiers déposés à la main dans assets/.
    """
    from pathlib import Path
    path = Path(path)
    ext = path.suffix.lower()

    if ext in MUSIC_FILE_EXTS:
        # Le contenu décide, pas l'extension : c'est la règle de la v0.8.1, et
        # elle vaut d'autant plus avec quatre formats — un `.xm` renommé `.mod`
        # se joue très bien, et un `.mod` qui n'en est pas un doit se refuser
        # ici, puisque mmutil ne dira jamais non.
        from core.engine_emulation.module_model import load_module
        try:
            mod = load_module(path)
        except ValueError as e:
            return f"{e} — the extension says \"{ext[1:]}\", the content does not."
        except Exception as e:
            return f"module illisible ({e})."
        if not mod.order:
            return "module without an order table — no pattern to play."
        if not any(s.data.size for s in mod.samples):
            return "module without any sample — it would make no sound."
        return None

    if ext == ".wav":
        import wave
        try:
            with wave.open(str(path)) as w:
                bits = w.getsampwidth() * 8
        except wave.Error as e:
            return (f"WAV not recognised ({e}). Uncompressed 8 or 16-bit PCM is "
                    "required.")
        except Exception as e:
            return f"cannot be read ({e})."
        if bits not in WAV_BITS_OK:
            return (f"WAV {bits} bits: mmutil only converts 8 and 16 bits. It would build"
                    " the ROM without saying so, with a silent result.")
        return None

    accepted = ", ".join(sorted(SFX_FILE_EXTS | MUSIC_FILE_EXTS))
    return f"extension {ext or '(none)'} not supported — accepted: {accepted}."


def sync_sprite_png(project, png_path: Path) -> Optional[str]:
    """Appelé quand un PNG apparaît dans assets/sprites/ (watcher/import). Crée
    le SpriteAsset + son sidecar si absent, via le pipeline aligné sur les
    backgrounds : Validator (détection) → Encodage non-destructif → asset
    éditable. Un sprite déjà connu n'est jamais ré-encodé automatiquement ; il
    est en revanche RACCROCHÉ à cette planche si celle qu'il cite a disparu
    (cf. `_relink_source`).
    Renvoie un éventuel avertissement d'import (palette réduite), None sinon."""
    name = png_path.stem
    sprite = project.sprites.get(name)
    warning = None
    if sprite is not None:
        _relink_source(project.sprites, sprite, project.asset_rel(png_path),
                       project.asset_abs(sprite.asset))
    else:
        # Cette planche appartient peut-être déjà à un sprite qui porte un autre
        # nom — un renommage qui n'a pas pu emporter le PNG (nom déjà pris).
        # En fonder un second, c'est deux sprites sur une image, dont un vide
        # de tout ce qui a été découpé.
        if _sourced_by(project.sprites, png_path,
                       lambda s: project.asset_abs(s.asset)):
            return None
        sprite = SpriteAsset(name=name, asset=project.asset_rel(png_path),
                             frame_w=8, frame_h=8)
        # Validator + encodage : métadonnées uniquement, PNG jamais modifié.
        try:
            warning = encode_sprite_asset(sprite, png_path)
        except Exception:
            pass
        project.sprites.append(sprite)
    # Le sidecar de CE sprite, pas celui qui porterait le nom du PNG : les deux
    # ne coïncident que tant que personne n'a renommé (cf. ResourceStore.path_of).
    if not project.sprites.path_of(sprite).exists():
        project.sprites.save(sprite)
    return warning


def apply_sprite_encoding(sprite: "SpriteAsset", c: dict):
    """Applique un résultat d'`encode_sprite` au SpriteAsset (calcul/application
    séparés, comme apply_bg_encoding). Peuple la PAL_BANK (sous-palettes) +
    le pont de compat `own_palette`. Nouvelle baseline restaurable."""
    sprite.palettes = [list(p) for p in c["palettes"]]
    sprite.source_palettes = [list(p) for p in c["palettes"]]
    sprite.palette_overrides = {}
    sprite.own_palette = list(c["own_palette"])     # pont de compat build/preview
    sprite.quantize_method = c["quantize_method"]


def encode_sprite_asset(sprite: "SpriteAsset", png_path: Path, method: str = None) -> Optional[str]:
    """Détecte + encode `png_path` sur `sprite` (métadonnées, PNG intact).
    Calcul/application séparés comme `apply_sprite_encoding` : ici les deux
    sont enchaînés pour le cas simple (import/remplacement UI). Renvoie un
    éventuel avertissement d'import (palette réduite), None sinon. Propage les
    erreurs d'encodage (contrairement à `sync_sprite_png`, qui les avale en
    tâche de fond watcher)."""
    from core.sprite_import import detect_sprite_import_mode, encode_sprite
    warning = detect_sprite_import_mode(png_path).get("warning")
    apply_sprite_encoding(sprite, encode_sprite(png_path, method or sprite.quantize_method))
    return warning


def resync_sprite_png(project, png_path: Path) -> Optional[str]:
    """La planche d'un sprite EXISTANT a changé sur le disque : recalculer ses
    palettes depuis les nouveaux pixels. Pendant de `resync_background_png`.

    Moins grave qu'un fond — le build fait relire le PNG par grit, donc la ROM
    est juste — mais l'éditeur affichait, lui, les anciennes couleurs : aperçu
    d'acteur, coût en palettes, allocation de banques. Tout ce que l'auteur a
    dessiné (découpe en frames, états, directions, miroirs) ne dépend pas des
    couleurs et reste intact ; `apply_sprite_encoding` ne touche qu'aux
    palettes."""
    sprite = project.sprites.get(png_path.stem)
    if sprite is None:
        return None
    before = len(sprite.palettes)
    pal_overrides = dict(sprite.palette_overrides)
    try:
        warning = encode_sprite_asset(sprite, png_path)
    except Exception as e:
        return f"“{sprite.name}”: image could not be re-read ({e})."
    sprite.source_stamp = file_stamp(png_path)
    if len(sprite.palettes) == before:
        # Autant de sous-palettes qu'avant : les renvois au catalogue visent
        # toujours les mêmes, on les garde.
        sprite.palette_overrides = pal_overrides
    project.sprites.save(sprite)
    if pal_overrides and len(sprite.palettes) != before:
        return (f"“{sprite.name}”: palette count changed, "
                f"{len(pal_overrides)} palette link(s) could not be kept.")
    return warning


def remove_sprite_png(project, png_path: Path):
    """PNG supprimé de assets/sprites/ : suppression différée du JSON."""
    sprite = project.sprites.get(png_path.stem)
    if sprite:
        project.sprites.soft_delete(sprite)


# ── Renommages ────────────────────────────────────────────────────
# Un fichier source renommé dans l'explorateur pendant que l'éditeur tourne.
# Le watcher apparie la disparition et l'apparition (cf. project_watcher,
# `_on_dir_changed`) ; ici, l'asset SUIT son fichier plutôt que d'être détruit
# et recréé — sinon un simple renommage de planche coûtait la découpe en
# frames d'un sprite, ou les caractères assignés d'une police.
#
# Deux gestes, dans cet ordre, et aucun n'est nouveau : le `rename_*` du
# projet (qui renomme la ressource, déplace son sidecar et réécrit ce qui la
# cite — scènes, prefabs, scripts), puis le `sync_*` du fichier neuf, dont le
# raccrochage (`_relink_source`) repointe la source. Un fichier dont aucun
# asset ne portait le nom n'est pas un renommage : c'est une apparition.


def rename_sprite_png(project, old_path: Path, new_path: Path) -> Optional[str]:
    """La planche d'un sprite renommée sur le disque."""
    sprite = project.sprites.get(old_path.stem)
    if sprite is None:
        return sync_sprite_png(project, new_path)
    project.rename_sprite(sprite, new_path.stem)
    return sync_sprite_png(project, new_path)


def rename_background_png(project, old_path: Path, new_path: Path) -> Optional[str]:
    """L'image d'un fond renommée sur le disque. La compression déjà calculée
    (tuiles, palettes, repeints par tuile) survit : ce sont les mêmes pixels."""
    bg = project.backgrounds.get(old_path.stem)
    if bg is None:
        return sync_background_png(project, new_path)
    project.rename_background(bg, new_path.stem)
    return sync_background_png(project, new_path)


def rename_sfx_file(project, old_path: Path, new_path: Path) -> Optional[str]:
    """Un fichier d'effet sonore renommé sur le disque."""
    sfx = project.sfx.get(old_path.stem)
    if sfx is None:
        sync_sfx_file(project, new_path)
        return None
    sfx.asset = project.asset_rel(new_path)
    project.rename_sound(sfx, new_path.stem)     # sauvegarde le sidecar
    return None


def rename_music_file(project, old_path: Path, new_path: Path) -> Optional[str]:
    """Un module de musique renommé sur le disque."""
    music = project.music.get(old_path.stem)
    if music is None:
        sync_music_file(project, new_path)
        return None
    music.asset = project.asset_rel(new_path)
    project.rename_sound(music, new_path.stem)   # sauvegarde le sidecar
    return None


def rename_font_file(project, old_path: Path, new_path: Path) -> Optional[str]:
    """Un fichier de police renommé sur le disque.

    Une police vit sur DEUX fichiers possibles (planche + descripteur `.fnt`),
    dont les noms peuvent différer : on met à jour celui qui a bougé, et on ne
    renomme la police que si c'est le fichier qui LUI DONNE SON NOM — renommer
    la page d'un `.fnt` ne renomme pas la police."""
    font = project.fonts.get(old_path.stem)
    if font is None:
        for f in project.fonts:
            if any(rel and project.asset_abs(rel) == old_path
                   for rel in (f.asset, f.descriptor)):
                font = f
                break
    if font is None:
        return sync_font_file(project, new_path)
    rel_new = project.asset_rel(new_path)
    if font.asset and project.asset_abs(font.asset) == old_path:
        font.asset = rel_new
    if font.descriptor and project.asset_abs(font.descriptor) == old_path:
        font.descriptor = rel_new
    if font.name == old_path.stem:
        project.rename_font(font, new_path.stem)   # sauvegarde le sidecar
    else:
        project.fonts.save(font)
    return None


def remove_background_png(project, png_path: Path):
    """PNG supprimé de assets/backgrounds/ : suppression différée du JSON."""
    bg = project.backgrounds.get(png_path.stem)
    if bg:
        project.backgrounds.soft_delete(bg)


def remove_sfx_file(project, path: Path):
    """Fichier audio supprimé de assets/sfx/ : suppression différée du JSON."""
    sfx = project.sfx.get(path.stem)
    if sfx:
        project.sfx.soft_delete(sfx)


def remove_music_file(project, path: Path):
    """Fichier audio supprimé de assets/music/ : suppression différée du JSON."""
    music = project.music.get(path.stem)
    if music:
        project.music.soft_delete(music)


def remove_font_file(project, path: Path):
    """Fichier supprimé de assets/fonts/ : suppression différée du JSON.

    Une police vit sur DEUX fichiers possibles (planche + descripteur `.fnt`),
    dont les noms peuvent différer. On retire donc la police que ce fichier
    porte réellement — par son stem, ou parce qu'elle le référence comme
    planche/descripteur — plutôt que de supposer stem == nom de police."""
    font = project.fonts.get(path.stem)
    if font is None:
        for f in project.fonts:
            for rel in (f.asset, f.descriptor):
                if rel and project.asset_abs(rel) == path:
                    font = f
                    break
            if font:
                break
    if font:
        project.fonts.soft_delete(font)


# ── Fichiers source d'une ressource ───────────────────────────────
# L'inverse des `remove_*_file` : d'une ressource vers le(s) fichier(s) du
# disque qui la font naître. Lu à la fermeture pour que la suppression
# DÉFINITIVE emporte aussi la source — sinon `reconcile_*` la ressusciterait au
# prochain lancement depuis le PNG / `.fnt` / module resté en place, et la
# suppression depuis le finder ne tiendrait pas (cf. project.commit_all_removals).


def sprite_source_paths(project, sprite) -> list[Path]:
    p = project.asset_abs(sprite.asset)
    return [p] if p else []


def background_source_paths(project, bg) -> list[Path]:
    img = bg.image_name()
    return [project.background_images_dir / img] if img else []


def sound_source_paths(project, snd) -> list[Path]:
    """Sfx comme Music : un unique fichier audio cité par `asset`."""
    p = project.asset_abs(snd.asset)
    return [p] if p else []


def font_source_paths(project, font) -> list[Path]:
    """Une police vit sur DEUX fichiers possibles : planche + descripteur `.fnt`."""
    return [p for p in (project.asset_abs(font.asset),
                        project.asset_abs(font.descriptor)) if p]


def sync_sfx_file(project, path: Path):
    """
    Appelé quand un fichier audio apparaît dans assets/sfx/.
    Crée le sidecar JSON à côté si absent, l'ajoute à project.sfx si nécessaire.
    """
    from core.models.audio import Sfx
    name = path.stem
    sfx = project.sfx.get(name)
    if sfx is None:
        sfx = Sfx(name=name, asset=project.asset_rel(path))
        project.sfx.append(sfx)
    sidecar = path.with_suffix(".json")
    if not sidecar.exists():
        project.sfx.save(sfx)
    return sfx


def sync_music_file(project, path: Path):
    """
    Appelé quand un fichier audio apparaît dans assets/music/.
    Crée le sidecar JSON à côté si absent, l'ajoute à project.music si nécessaire.
    """
    from core.models.audio import Music
    name = path.stem
    music = project.music.get(name)
    if music is None:
        music = Music(name=name, asset=project.asset_rel(path))
        project.music.append(music)
    sidecar = path.with_suffix(".json")
    if not sidecar.exists():
        project.music.save(music)
    return music


def sync_font_file(project, path: Path) -> Optional[str]:
    """Appelé quand une source de police apparaît dans assets/fonts/.

    Deux points d'entrée, un seul asset : le `.fnt` apporte le mapping des
    caractères, le PNG nu le fait déduire (grille + charset proposé,
    corrigeables dans l'écran Police). Une police
    déjà connue n'est jamais ré-analysée automatiquement — sinon on écraserait
    les corrections de l'utilisateur. Elle est en revanche RACCROCHÉE à ce
    fichier si la planche qu'elle cite a disparu : une planche renommée sur le
    disque laissait la police à l'écran sans image, pendant que le fichier
    renommé en créait une deuxième à côté.

    Renvoie un avertissement d'import, None si tout va bien."""
    from core.models.font import Font
    from core import font_import

    name = path.stem
    font = project.fonts.get(name)
    warning = None
    if font is not None:
        # Une planche renommée sur le disque laissait la police sans image.
        # Seule une PLANCHE raccroche : un `.fnt` n'est pas l'image, il la nomme.
        if path.suffix.lower() != ".fnt":
            _relink_source(project.fonts, font, project.asset_rel(path),
                           project.asset_abs(font.asset))
        if path.suffix.lower() in (".ttf", ".otf") and not font.family_name:
            # Sources reconnues avant l'arrivée des métadonnées : les relire
            # une fois afin que leur famille soit créée sans réimport manuel.
            try:
                from core.font_metadata import vector_font_metadata
                for key, value in vector_font_metadata(path).items():
                    setattr(font, key, value)
                project.fonts.save(font)
            except Exception as exc:
                return f"Font \"{name}\": metadata cannot be read ({exc})."
    else:
        # La planche d'un `.fnt` déjà importé ne doit pas créer une SECONDE
        # police : le descripteur fait foi (il porte le mapping des caractères)
        # et référence déjà cette image. reconcile_fonts applique cette règle en
        # ordonnant ses passes, mais un dépôt à chaud (watcher) arrive fichier
        # par fichier — d'où le garde ici, au seul endroit qui crée un Font.
        if path.suffix.lower() != ".fnt" and _sourced_by(
                project.fonts, path, lambda f: project.asset_abs(f.asset)):
            return None
        font = Font(name=name)
        # Échec dur (format illisible, planche introuvable) : aucun asset créé —
        # mieux vaut rien qu'une police vide qui traîne et se sauvegarde. Un
        # échec mou (planche lisible mais aucun glyphe trouvé) crée l'asset :
        # l'utilisateur corrigera la taille de cellule dans l'écran Police.
        try:
            suffix = path.suffix.lower()
            if suffix == ".fnt":
                fields = font_import.import_font_fnt(path)
                page = fields.pop("page_path", None)
                if page is None:
                    return (f"Font \"{name}\": the descriptor does not reference any PNG "
                            "sheet that can be found — drop the sheet next to the "
                            ".fnt.")
                font.asset = project.asset_rel(page)
                font.descriptor = project.asset_rel(path)
            elif suffix == ".png":
                # Planche opaque : le fond dominant est PROPOSÉ comme couleur
                # transparente. Une proposition, pas un verdict — l'écran
                # Police laisse la repiquer, ou l'effacer si elle est fausse.
                font.bg_color = font_import.detect_bg_color(path)
                # `space_color` est None à ce stade (rien à deviner : un
                # marqueur d'espacement ne se distingue pas d'une couleur de
                # dessin), donc la police entre en MONO. Elle passera en
                # proportionnel le jour où l'utilisateur repiquera la couleur.
                fields = font_import.import_font_png(
                    path, keys=font.key_colors(), space_color=font.space_color)
                font.asset = project.asset_rel(path)
            else:
                # Une source vectorielle ne se transforme pas à l'import : le
                # futur FontRasterizer la lira à la demande, pour le sous-
                # ensemble réellement requis. Créer le sidecar suffit pour que
                # le watcher, le finder et FontAsset puissent la référencer.
                font.asset = project.asset_rel(path)
                from core.font_metadata import vector_font_metadata
                fields = {"source_format": suffix.lstrip("."),
                          **vector_font_metadata(path)}
            font_import.apply_font_import(font, fields)
        except Exception as exc:
            return f"Font \"{name}\": import failed ({exc})."
        if not font.glyphs and font.source_format in ("png", "fnt"):
            warning = (f"Font \"{name}\": no glyph detected — check the cell size in the "
                       "Font screen.")
        project.fonts.append(font)
    # Le sidecar de CETTE police, pas celui qui porterait le nom du fichier
    # source : les deux ne coïncident que tant que personne n'a renommé, et
    # c'est justement ce cas-là qu'on rattrape ici (cf. ResourceStore.path_of).
    if not project.fonts.path_of(font).exists():
        project.fonts.save(font)
    # La source vient d'être reconnue : elle doit être immédiatement utilisable
    # dans les TextBox, même lorsqu'il s'agit d'une planche bitmap sans famille
    # typographique vectorielle. Idempotent et sans écraser les recettes déjà
    # écrites par l'auteur.
    reconcile_font_assets(project)
    return warning


def _family_key(name: str) -> str:
    """Identité de famille indépendante des espaces, tirets et capitales."""
    return "".join(char.casefold() for char in name if char.isalnum())


def reconcile_font_assets(project):
    """Compose les familles logiques à partir des sources vectorielles.

    Les réglages d'un FontAsset n'appartiennent pas à la découverte de fichiers :
    seules ses faces auto-gérées sont remplacées. Une famille créée à la main
    avec le même nom est complétée, jamais remplacée.
    """
    from core.models.font_asset import FontAsset, FontFace

    groups: dict[str, list] = {}
    for font in project.fonts:
        if font.source_format not in ("ttf", "otf") or not font.family_name:
            continue
        groups.setdefault(font.family_name, []).append(font)
    # Mettre d'abord à jour les assets qui étaient déjà auto-composés. Cela
    # couvre aussi la dernière face d'une famille supprimée depuis le finder :
    # il est légitime que l'asset logique reste (sa recette de rendu est un
    # réglage de projet), mais il ne doit plus désigner une source disparue.
    groups_by_key = {_family_key(name): (name, fonts) for name, fonts in groups.items()}
    matched_keys: set[str] = set()
    for asset in project.font_assets:
        if not asset.auto_family:
            continue
        family = groups_by_key.get(_family_key(asset.auto_family))
        fonts = family[1] if family else []
        family_name = family[0] if family else asset.auto_family
        faces = [FontFace(font.name, font.weight, font.italic)
                 for font in sorted(fonts, key=lambda item: (item.weight, item.italic, item.name.casefold()))]
        removed_sources = {face.source_name for face in asset.faces} - {face.source_name for face in faces}
        sources = {
            variant: [name for name in names if name not in removed_sources]
            for variant, names in asset.sources.items()
        }
        if asset.faces != faces or asset.auto_family != family_name or asset.sources != sources:
            asset.faces, asset.auto_family, asset.sources = faces, family_name, sources
            project.font_assets.save(asset)
        matched_keys.add(_family_key(family_name))

    for family_name, fonts in groups.items():
        key = _family_key(family_name)
        if key in matched_keys:
            continue
        asset = next((item for item in project.font_assets
                      if _family_key(item.auto_family or item.name) == key), None)
        if asset is None:
            asset = FontAsset(name=family_name, auto_family=family_name)
            project.font_assets.append(asset)
        faces = [FontFace(font.name, font.weight, font.italic)
                 for font in sorted(fonts, key=lambda item: (item.weight, item.italic, item.name.casefold()))]
        if asset.faces != faces or asset.auto_family != family_name:
            asset.faces, asset.auto_family = faces, family_name
        # Le panneau actuel configure encore la chaîne regular : la renseigner
        # depuis la vraie face 400 non-italique sans jamais toucher aux
        # fallbacks qu'un auteur aurait ajoutés.
        regular = next((face.source_name for face in faces
                        if face.weight == 400 and not face.italic), "")
        if regular and not asset.sources.get("regular"):
            asset.sources["regular"] = [regular]
        project.font_assets.save(asset)

    # Les sources bitmap n'ont ni famille SFNT ni faces à fusionner. Chacune
    # devient donc son propre Font Asset au dépôt, afin que la source ne soit
    # jamais visible dans le dossier Fonts sans être sélectionnable par une
    # TextBox. Une recette existante a toujours priorité : jamais de mutation
    # silencieuse d'un asset que l'auteur a nommé ou configuré lui-même.
    covered = {
        name
        for asset in project.font_assets
        for names in asset.sources.values()
        for name in names
    }
    covered.update(face.source_name for asset in project.font_assets for face in asset.faces)
    for font in project.fonts:
        if font.name in covered:
            continue
        if font.source_format in ("ttf", "otf") and font.family_name:
            continue
        if project.font_assets.get(font.name) is not None:
            continue
        asset = FontAsset(name=font.name, sources={"regular": [font.name]})
        project.font_assets.append(asset)
        project.font_assets.save(asset)


def sync_background_png(project, png_path: Path) -> Optional[str]:
    """Crée un BackgroundAsset (sidecar de compression par image, keyé par le
    stem du PNG) quand un PNG apparaît dans assets/backgrounds/. Ne modifie
    pas un asset existant — sauf pour le RACCROCHER à ce PNG si celui qu'il
    cite a disparu (cf. `_relink_source`). C'est la scène qui possède ses
    layers. Renvoie un éventuel avertissement d'import (palette déduite), None
    sinon."""
    name = png_path.stem
    ba = project.backgrounds.get(name)
    if ba is not None:
        # Un fond cite son image par son seul NOM DE FICHIER, relatif à
        # background_images_dir — la convention de la famille.
        img = ba.image_name()
        _relink_source(project.backgrounds, ba, png_path.name,
                       (project.background_images_dir / img) if img else None)
    else:
        # Cette image appartient peut-être déjà à un fond qui porte un autre nom
        # (renommage qui n'a pas pu emporter le PNG) : en fonder un second
        # dupliquerait la compression, et les scènes ne sauraient plus lequel
        # elles citent.
        if _sourced_by(project.backgrounds, png_path,
                       lambda b: (project.background_images_dir / b.image_name())
                                 if b.image_name() else None):
            return None
        ba = BackgroundAsset(name=name, asset=png_path.name)
        # Nouveau dépôt : AUTO-DÉTECTION du mode (pivot indexé/non-indexé),
        # puis compression (métadonnées) sans toucher le PNG.
        warning = None
        try:
            from core.bg_import import detect_import_mode
            d = detect_import_mode(png_path)
            ba.mode = "bitmap" if d["token"] in ("bitmap", "bitmap16") else "tiled"
            ba.bpp = 8 if d["token"] == "tiled8" else 4
            warning = d["warning"]
        except Exception:
            pass
        encode_background_asset(ba, png_path)
        project.backgrounds.append(ba)
        project.backgrounds.save(ba)
        return warning
    return None


def resync_background_png(project, png_path: Path) -> Optional[str]:
    """Le PNG d'un fond EXISTANT a changé sur le disque : recalculer sa
    compression depuis les nouveaux pixels.

    `sync_background_png` ne touche pas à un asset déjà connu (c'est sa règle :
    ne jamais écraser un import), et `reconcile_backgrounds` ne rattrape que les
    sidecars SANS tileset. Un fond retouché gardait donc ses anciennes tuiles
    pour toujours — à l'écran ET dans la ROM, puisque le build lit `ba.tileset`
    et non le PNG.

    Les choix de l'utilisateur sont conservés : `encode_background_asset` ne
    re-détecte pas le mode, et le `kind`, le rôle UI, les marges de découpe et
    les animations ne dépendent pas des pixels. Les repeints par tuile, eux,
    sont indexés par (colonne, ligne) : ils ne survivent que si la géométrie n'a
    pas bougé — sinon ils désigneraient d'autres tuiles que celles peintes.

    Renvoie un avertissement si des repeints ont dû être abandonnés, None sinon.
    """
    ba = project.backgrounds.get(png_path.stem)
    if ba is None:
        return None
    before = (ba.tiles_w, ba.tiles_h, len(ba.palettes))
    tile_overrides = dict(ba.tile_palette_overrides)
    pal_overrides = dict(ba.palette_overrides)

    encode_background_asset(ba, png_path)
    ba.source_stamp = file_stamp(png_path)

    same_geometry = (ba.tiles_w, ba.tiles_h, len(ba.palettes)) == before
    if same_geometry:
        # Simple retouche : les repeints désignent toujours les mêmes tuiles.
        ba.tile_palette_overrides = tile_overrides
        ba.palette_overrides = pal_overrides
    project.backgrounds.save(ba)

    dropped = len(tile_overrides) + len(pal_overrides)
    if dropped and not same_geometry:
        return (f"“{ba.name}”: image geometry changed, {dropped} palette "
                f"repaint(s) could not be kept.")
    return None


def file_stamp(path: Path) -> str:
    """Empreinte FRAÎCHE et complète d'un fichier : ``taille:date:hash``.

    Le hachage reste l'autorité — une date de fichier seule ne prouve pas
    qu'une image a bougé : le sidecar est réécrit à chaque sauvegarde du projet
    (donc presque toujours plus récent que le PNG), et certains outils de dessin
    reposent l'ancienne date en enregistrant. Mais on préfixe taille et date
    afin que ``source_changed`` puisse trancher SANS relire le fichier quand
    elles n'ont pas bougé — c'est ce préfixe qui rend l'ouverture rapide, où on
    ne lisait auparavant chaque image que pour la rehacher à l'identique.

    À n'appeler que lorsqu'on veut une empreinte fraîche à mémoriser (après un
    (ré)encodage) ; pour comparer à une empreinte stockée, passer par
    ``source_changed``, qui évite la lecture dans le cas courant."""
    import hashlib
    try:
        st = path.stat()
        data = path.read_bytes()
    except OSError:
        return ""
    return f"{st.st_size}:{st.st_mtime_ns}:{hashlib.sha1(data).hexdigest()[:16]}"


def source_changed(path: Path, stored: str) -> tuple[bool, str]:
    """L'image ``path`` a-t-elle changé depuis l'empreinte ``stored`` ?

    Renvoie ``(a_changé, empreinte_fraîche)``. Un ``stat`` d'abord (pas de
    lecture) : si la taille ET la date collent à l'empreinte stockée, le fichier
    n'a pas bougé et on ne lit RIEN — le cas courant à l'ouverture. Sinon on lit
    les octets et c'est le hachage qui tranche : une date reposée par un outil
    de dessin, ou une empreinte d'ancien format (``taille:hash``, sans date),
    force une lecture, mais une seule — l'empreinte fraîche rendue permet à
    l'appelant de la réécrire pour que l'ouverture suivante n'ait plus rien à
    lire.

    Une empreinte vide (asset antérieur au champ) « a changé » : on ré-encode
    une fois pour reprendre pied, comportement inchangé."""
    try:
        st = path.stat()
    except OSError:
        return False, stored     # source absente : rien à ré-encoder
    parts = stored.split(":")
    if len(parts) == 3 and parts[0] == str(st.st_size) and parts[1] == str(st.st_mtime_ns):
        return False, stored     # taille + date identiques : inchangé, aucune lecture
    fresh = file_stamp(path)
    stored_hash = parts[-1] if stored else ""
    fresh_hash = fresh.split(":")[-1] if fresh else ""
    changed = not (stored_hash and fresh_hash and stored_hash == fresh_hash)
    return changed, fresh


def apply_bg_encoding(ba: "BackgroundAsset", source_name: str, c: dict):
    """Applique un résultat de compression (dict de bg_import.encode_background)
    à un BackgroundAsset. Séparé du calcul pour permettre une compression
    hors-thread : le worker calcule `c`, le thread UI applique via ce helper."""
    ba.asset = source_name
    ba.palettes = c["palettes"]
    # Nouvelle baseline dérivée du PNG : snapshot restaurable + reset des
    # overrides (l'origine des palettes repart de la compression fraîche).
    ba.source_palettes = [list(p) for p in c["palettes"]]
    ba.palette_overrides = {}
    ba.diagnostics = c.get("diagnostics", {})
    ba.bpp = c.get("bpp", 4)
    ba.mode = c.get("mode", "tiled")
    if ba.mode == "bitmap":
        ba.bitmap = c["bitmap"]
        ba.out_w = c["out_w"]
        ba.out_h = c["out_h"]
        # Pas de représentation tuilée en bitmap.
        ba.tileset = []
        ba.tilemap = []
        ba.tiles_w = 0
        ba.tiles_h = 0
        ba.tile_palette_overrides = {}
    else:
        ba.tileset = c["tileset"]
        ba.tilemap = c["tilemap"]
        ba.tiles_w = c["tiles_w"]
        ba.tiles_h = c["tiles_h"]
        ba.quantize_method = c["quantize_method"]
        ba.bitmap = ""
        ba.out_w = 0
        ba.out_h = 0


def encode_background_asset(ba: "BackgroundAsset", png_path: Path, method: str = None):
    """Calcule et stocke la compression GBA d'un fond (palettes/tileset/tilemap)
    depuis son PNG — sans modifier le fichier. cf. core/bg_import. No-op si
    illisible. Chemin SYNCHRONE (import via watcher, reconcile au chargement).
    Dispatch selon le mode DÉJÀ choisi de l'asset (`ba.mode`/`ba.bpp`) — ne
    re-détecte PAS (la détection est faite une fois à la création), pour ne
    jamais écraser un choix de mode existant lors d'un reconcile."""
    try:
        from core.bg_import import encode_by_mode
        mode_token = "bitmap" if getattr(ba, "mode", "tiled") == "bitmap" \
            else ("tiled8" if getattr(ba, "bpp", 4) == 8 else "tiled4")
        c = encode_by_mode(png_path, mode_token, method or ba.quantize_method,
                           getattr(ba, "dither", False), ba.import_prep(), ba.compression)
        apply_bg_encoding(ba, png_path.name, c)
    except Exception:
        pass


# ── Rattrapage à l'ouverture d'un projet ──────────────────────────
# Le ProjectWatcher voit les fichiers qui apparaissent PENDANT que l'éditeur
# tourne. Ceux déposés à l'explorateur, éditeur fermé, ne sont vus par personne :
# les `reconcile_*` ci-dessous repassent une fois par ouverture de projet.
#
# C'est le même geste que les `sync_*` de ce module, appliqué au DOSSIER au lieu
# d'un fichier — d'où leur place ici : aucune n'a besoin d'importer quoi que ce
# soit, elles bouclent sur ce qui précède. Elles rattrapent aussi le sidecar dont
# l'encodage manque (import interrompu, échec avalé en tâche de fond) : le
# fichier source est là, l'encodage se recalcule.
#
# Toutes NON-DESTRUCTIVES — le PNG / le .mod source n'est jamais modifié, seul le
# sidecar JSON est écrit — et idempotentes : un asset déjà encodé est sauté.
# Appelées uniquement depuis `Project.load()`, dans l'ordre (cf. project.py).


def reconcile_background(project, ba) -> None:
    """Répare UN fond déjà chargé : compression manquante ou image retouchée.

    La moitié « par-asset » de `reconcile_backgrounds`. Extraite pour que le
    préchargement de la scène active (`Project.load_active_scene_resources`)
    puisse remettre d'aplomb les fonds qu'elle cite sans lancer la passe globale
    — un catalogue différé ne repasse pas le dossier entier à l'ouverture."""
    img = ba.image_name()
    ap = project.background_images_dir / img if img else None
    if not (ap and ap.exists()):
        return
    if not ba.tileset and ba.mode != "bitmap":
        encode_background_asset(ba, ap)
        ba.source_stamp = file_stamp(ap)
        if ba.tileset:
            project.backgrounds.save(ba)
        return
    # Le watcher ne voit que ce qui bouge pendant que l'éditeur tourne ; une
    # retouche faite à côté ne serait vue par personne, et le fond resterait
    # périmé à l'écran ET dans la ROM sans que rien ne le dise.
    #
    # Empreinte vide = asset antérieur à ce champ : on ré-encode une fois pour
    # reprendre pied. C'est sans effet si l'image n'a pas bougé (l'encodage est
    # déterministe), et ça répare justement les fonds déjà périmés au moment où
    # cette version arrive.
    changed, fresh = source_changed(ap, ba.source_stamp)
    if changed:
        resync_background_png(project, ap)
    elif fresh != ba.source_stamp:
        # Contenu identique mais empreinte à migrer (ancien format sans date, ou
        # date reposée) : la réécrire une fois pour que la prochaine ouverture
        # tranche au seul ``stat``, sans lecture.
        ba.source_stamp = fresh
        project.backgrounds.save(ba)


def reconcile_sprite(project, sp) -> None:
    """Répare UN sprite déjà chargé : encodage manquant ou planche retouchée.

    Pendant de `reconcile_background`, extraite pour la même raison (cf.
    `Project.load_active_scene_resources`)."""
    if not sp.asset:
        return
    ap = project.asset_abs(sp.asset)
    if not ap or not ap.exists():
        return
    if not sp.palettes:
        # Sprite créé par `sync_sprite_png` alors que son encodage avait échoué
        # (exception avalée en tâche de fond watcher) : la réparation est ici.
        try:
            from core.sprite_import import encode_sprite
            apply_sprite_encoding(sp, encode_sprite(ap, sp.quantize_method))
            sp.source_stamp = file_stamp(ap)
            project.sprites.save(sp)
        except Exception:
            pass
        return
    # Empreinte vide = sprite antérieur au champ : on ré-encode une fois pour
    # reprendre pied (sans effet si la planche n'a pas bougé, l'encodage étant
    # déterministe).
    changed, fresh = source_changed(ap, sp.source_stamp)
    if changed:
        resync_sprite_png(project, ap)
    elif fresh != sp.source_stamp:
        # Contenu identique, empreinte à migrer (cf. reconcile_background).
        sp.source_stamp = fresh
        project.sprites.save(sp)


def reconcile_backgrounds(project):
    """(1) PNG déposés hors éditeur dans assets/backgrounds/ → crée le
    BackgroundAsset + sa compression. (2) Fonds dont le sidecar existe sans
    tileset → compression recalculée depuis le PNG. (3) Fonds dont le PNG a été
    RETOUCHÉ éditeur fermé → compression refaite depuis les nouveaux pixels.

    (2) et (3) délèguent à `reconcile_background`, par asset.

    Sautée quand l'empreinte du dossier n'a pas bougé (cf. `reconcile_sprites`)."""
    d = project.background_images_dir
    if project.reconcile_manifest.matches(d, IMAGE_FILE_EXTS):
        return
    for f in (sorted(d.glob("*")) if d.exists() else []):
        if f.is_file() and f.suffix.lower() in IMAGE_FILE_EXTS:
            sync_background_png(project, f)
    for ba in list(project.backgrounds):
        reconcile_background(project, ba)
    project.reconcile_manifest.record(d, IMAGE_FILE_EXTS)


def reconcile_sprites(project):
    """(1) PNG déposés hors éditeur dans assets/sprites/ → crée le SpriteAsset,
    et raccroche un sprite dont la planche a été renommée. (2) Sprites dont le
    sidecar existe sans PAL_BANK → encodage recalculé depuis le PNG source.
    (3) Sprites dont la planche a été RETOUCHÉE éditeur fermé → palettes
    refaites depuis les nouveaux pixels. (2) et (3) délèguent à
    `reconcile_sprite`, par asset.

    Pendant de `reconcile_backgrounds`. La passe (1) y manquait : le watcher
    crée bien un sprite quand un PNG apparaît pendant que l'éditeur tourne, mais
    le même fichier déposé — ou renommé — éditeur fermé n'était vu par
    personne.

    Sautée quand l'empreinte du dossier n'a pas bougé depuis le dernier
    rattrapage (cf. `ReconcileManifest`) : la passe est idempotente, la refaire
    à vide ne trouverait rien."""
    d = project.sprites_dir
    if project.reconcile_manifest.matches(d, IMAGE_FILE_EXTS):
        return
    for f in (sorted(d.glob("*")) if d.exists() else []):
        if f.is_file() and f.suffix.lower() in IMAGE_FILE_EXTS:
            sync_sprite_png(project, f)
    for sp in list(project.sprites):
        reconcile_sprite(project, sp)
    project.reconcile_manifest.record(d, IMAGE_FILE_EXTS)


def reconcile_sfx_and_music(project):
    """Crée les sidecars manquants pour les fichiers audio bruts déjà présents
    dans assets/sfx/ et assets/music/.

    Sautée quand les deux dossiers ont l'empreinte de leur dernier rattrapage
    (cf. `reconcile_sprites`) ; sinon les deux tournent et se réenregistrent."""
    from core.models.audio import SFX_FILE_EXTS, MUSIC_FILE_EXTS
    manifest = project.reconcile_manifest
    if (manifest.matches(project.sfx_dir, SFX_FILE_EXTS)
            and manifest.matches(project.music_dir, MUSIC_FILE_EXTS)):
        return
    for f in sorted(project.sfx_dir.glob("*")) if project.sfx_dir.exists() else []:
        if f.is_file() and f.suffix.lower() in SFX_FILE_EXTS:
            sync_sfx_file(project, f)
    for f in sorted(project.music_dir.glob("*")) if project.music_dir.exists() else []:
        if f.is_file() and f.suffix.lower() in MUSIC_FILE_EXTS:
            sync_music_file(project, f)
    manifest.record(project.sfx_dir, SFX_FILE_EXTS)
    manifest.record(project.music_dir, MUSIC_FILE_EXTS)


def reconcile_fonts(project):
    """Même rôle pour assets/fonts/ : planches PNG et descripteurs `.fnt`
    déposés hors ligne.

    Le `.fnt` passe en premier : quand les deux fichiers sont là, c'est lui qui
    fait foi (il porte le mapping des caractères), et il référence sa planche —
    laquelle ne doit donc pas créer une seconde police en doublon.

    Rend la liste des avertissements d'import. Elle était jetée : un `.fnt`
    déposé sans sa planche, un conteneur illisible, une planche dont aucun
    glyphe ne ressort — `sync_font_file` le disait, et personne ne l'écoutait.
    L'utilisateur voyait « No font. » sans un mot, dans un panneau qui l'invite
    justement à déposer un `.fnt`, c'est-à-dire le cas qui échoue seul."""
    from core.models.font import FONT_FILE_EXTS
    if not project.fonts_dir.exists():
        return []
    files = [f for f in sorted(project.fonts_dir.glob("*"))
             if f.is_file() and f.suffix.lower() in FONT_FILE_EXTS]
    warnings: list[str] = []
    pages = set()
    for f in [x for x in files if x.suffix.lower() == ".fnt"]:
        w = sync_font_file(project, f)
        if w:
            warnings.append(w)
        font = project.fonts.get(f.stem)
        if font and font.asset:
            pages.add(project.asset_abs(font.asset))
    for f in [x for x in files if x.suffix.lower() != ".fnt"]:
        if f not in pages:
            w = sync_font_file(project, f)
            if w:
                warnings.append(w)
    return warnings
