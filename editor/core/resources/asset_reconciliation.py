"""Encodage GBA d'un asset existant : le calcule (délégué à core.bg_import / core.sprite_import) et l'applique à
l'asset (BackgroundAsset / SpriteAsset) — jamais au fichier source. Un fichier qui apparaît n'est PAS un asset : on
le crée par *Create asset* (cf. `core.asset_creation`). `reconcile_*` (en fin de module) répare, à l'ouverture d'un
projet, les assets dont l'encodage manque ou dont la source a été retouchée éditeur fermé."""

from pathlib import Path
from typing import Optional

from core.models.background import BackgroundAsset
from core.models.sprite import SpriteAsset, IMAGE_FILE_EXTS
from core.models.audio import MUSIC_FILE_EXTS, SFX_FILE_EXTS, WAV_BITS_DECODED, JINGLE_MAX_CHANNELS


def _citing(store, path: Path, resolve) -> list:
    """Les assets de `store` qui POINTENT ce fichier — plusieurs, quand l'auteur en a tiré plusieurs assets. Un asset ne se
    retrouve pas par le nom de son fichier : il n'en est plus le sidecar."""
    target = Path(path).resolve()
    found = []
    for asset in store:
        cited = resolve(asset) if getattr(asset, "asset", "") else None
        if cited is not None and Path(cited).resolve() == target:
            found.append(asset)
    return found


def wav_too_long(path) -> Optional[str]:
    """La raison pour laquelle ce WAV ne tiendra pas dans un module de musique,
    ou None. Une piste devient un module dont chaque segment est un échantillon : sa
    durée est bornée par la table d'ordres (cf. `wav_module`)."""
    import wave
    from core.wav_module import max_seconds
    limit = max_seconds()
    try:
        with wave.open(str(path)) as w:
            seconds = w.getnframes() / max(1, w.getframerate())
    except Exception:
        return None          # `check_audio_file` dit déjà pourquoi il est illisible
    if seconds > limit:
        return (f"WAV of {seconds:.0f} s: a music track is limited to "
                f"{limit:.0f} s once turned into a module.")
    return None


def check_audio_file(path, into: Optional[str] = None, at_import: bool = True) -> Optional[str]:
    """None si le fichier est utilisable, sinon la raison du refus, rédigée
    pour être affichée telle quelle à l'auteur.

    Ce contrôle n'est pas une ceinture de plus : c'est le SEUL. mmutil ne
    renvoie jamais un code d'erreur — ni sur un wav 24 bits (dont il émet
    quand même la constante, donc un effet muet dans la ROM), ni sur une
    extension inconnue. S'il n'y a pas de refus ici, il n'y en a nulle part.

    Appelé à l'import ET par le validateur, parce que le ProjectWatcher
    ramasse aussi les fichiers déposés à la main dans assets/.

    `at_import=False` : le validateur, pour lequel une piste trop longue n'est
    pas un refus (cf. `wav_too_long`).

    `into` nomme le dossier de `assets/` où le fichier ira, à l'import : le rôle
    d'un module (musique, jingle) est celui de son DOSSIER, et à l'import le
    fichier n'y est pas encore. Sans lui, c'est le dossier du fichier lui-même.
    """
    from pathlib import Path
    path = Path(path)
    ext = path.suffix.lower()
    folder = into or path.parent.name

    if ext in MUSIC_FILE_EXTS and ext != ".wav":
        # Le contenu décide, pas l'extension : c'est la règle de la v0.8.1, et
        # elle vaut d'autant plus avec quatre formats — un `.xm` renommé `.mod`
        # se joue très bien, et un `.mod` qui n'en est pas un doit se refuser
        # ici, puisque mmutil ne dira jamais non.
        from core.engine_emulation.module_model import is_pattern_order, load_module
        try:
            mod = load_module(path)
        except ValueError as e:
            return f"{e} — the extension says \"{ext[1:]}\", the content does not."
        except Exception as e:
            return f"module illisible ({e})."
        # La table est brute : `[255]` ou `[254, 255]` n'est pas vide, mais ne joue rien.
        if not any(is_pattern_order(o) for o in mod.order):
            return "module without an order table — no pattern to play."
        if not any(s.data.size for s in mod.samples):
            return "module without any sample — it would make no sound."
        if folder == "jingles" and mod.num_channels > JINGLE_MAX_CHANNELS:
            # maxmod ne donne que 4 canaux à la couche jingle : le reste serait
            # joué tronqué, et un morceau tronqué s'entend comme un morceau raté.
            return (f"{mod.num_channels} channels — maxmod only gives {JINGLE_MAX_CHANNELS} to a "
                    "jingle, the others would be silent. Reduce the module, or keep it "
                    "as a music.")
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
        if bits not in WAV_BITS_DECODED:
            return f"WAV {bits} bits: only 8, 16, 24 and 32 bits PCM are read."
        if at_import and folder in ("music", "jingles"):
            # Refusé à l'import. Dans le validateur, le même constat n'est qu'un
            # avertissement : un fichier trop long qu'aucun état ne joue ne
            # coûte rien, et celui qui est joué échoue au build (`wav_to_xm`).
            return wav_too_long(path)
        return None

    accepted = ", ".join(sorted(SFX_FILE_EXTS | MUSIC_FILE_EXTS))
    return f"extension {ext or '(none)'} not supported — accepted: {accepted}."


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
    erreurs d'encodage (contrairement à la création depuis une source, qui les avale en
    tâche de fond watcher)."""
    from core.sprite_import import detect_sprite_import_mode, encode_sprite
    warning = detect_sprite_import_mode(png_path).get("warning")
    apply_sprite_encoding(sprite, encode_sprite(png_path, method or sprite.quantize_method))
    return warning


def citing_sprites(project, png_path: Path) -> list:
    """Les sprites qui POINTENT ce fichier, où qu'il soit rangé."""
    return _citing(project.sprites, png_path, lambda s: project.asset_abs(s.asset))


def citing_backgrounds(project, png_path: Path) -> list:
    """Les fonds qui POINTENT ce fichier, où qu'il soit rangé."""
    return _citing(project.backgrounds, png_path, project.background_image_path)


def resync_sprite_png(project, png_path: Path) -> Optional[str]:
    """La planche a changé sur le disque : recalcule les palettes de CHAQUE sprite qui la pointe (cf. `_resync_sprite`).
    Renvoie les avertissements réunis, None s'il n'y en a pas."""
    warnings = [w for w in (_resync_sprite(project, sprite, png_path)
                            for sprite in citing_sprites(project, png_path)) if w]
    return " ".join(warnings) or None


def _resync_sprite(project, sprite, png_path: Path) -> Optional[str]:
    """La planche d'un sprite EXISTANT a changé sur le disque : recalculer ses
    palettes depuis les nouveaux pixels. Pendant de `_resync_background`.

    Moins grave qu'un fond — le build fait relire le PNG par grit, donc la ROM
    est juste — mais l'éditeur affichait, lui, les anciennes couleurs : aperçu
    d'acteur, coût en palettes, allocation de banques. Tout ce que l'auteur a
    dessiné (découpe en frames, états, directions, miroirs) ne dépend pas des
    couleurs et reste intact ; `apply_sprite_encoding` ne touche qu'aux
    palettes."""
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


# ── Fichiers source d'une ressource ───────────────────────────────
# D'une ressource vers le(s) fichier(s) du disque qu'elle POINTE : ce que lisent l'arbre Disk, la détection
# des sources manquantes, le déplacement et *Relink source…*. Supprimer l'asset n'efface pas ces fichiers.


def sprite_source_paths(project, sprite) -> list[Path]:
    p = project.asset_abs(sprite.asset)
    return [p] if p else []


def palette_source_paths(project, bank) -> list[Path]:
    return [project.palettes.hex_path(bank)]


def background_source_paths(project, bg) -> list[Path]:
    return [project.background_image_path(bg)] if bg.asset else []


def sound_source_paths(project, snd) -> list[Path]:
    """Sfx comme Music : un unique fichier audio cité par `asset`."""
    p = project.asset_abs(snd.asset)
    return [p] if p else []


def font_source_paths(project, font) -> list[Path]:
    """Une police vit sur DEUX fichiers possibles : planche + descripteur `.fnt`."""
    return [p for p in (project.asset_abs(font.asset),
                        project.asset_abs(font.descriptor)) if p]


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


def resync_background_png(project, png_path: Path) -> Optional[str]:
    """L'image a changé sur le disque : recompresse CHAQUE fond qui la pointe (cf. `_resync_background`).
    Renvoie les avertissements réunis, None s'il n'y en a pas."""
    warnings = [w for w in (_resync_background(project, ba, png_path)
                            for ba in citing_backgrounds(project, png_path)) if w]
    return " ".join(warnings) or None


def _resync_background(project, ba, png_path: Path) -> Optional[str]:
    """Le PNG d'un fond EXISTANT a changé sur le disque : recalculer sa
    compression depuis les nouveaux pixels.

    `reconcile_backgrounds` ne rattrape que les sidecars SANS tileset. Un fond retouché gardait donc ses anciennes tuiles
    pour toujours — à l'écran ET dans la ROM, puisque le build lit `ba.tileset`
    et non le PNG.

    Les réglages sont conservés — `apply_bg_encoding` n'y touche pas : le mode (`encode_background_asset` ne
    re-détecte pas), le `kind`, le rôle UI, les marges de découpe, les animations, les palettes ajoutées et les
    overrides (références au catalogue), la peinture et les repeints. La peinture et les repeints par tuile sont rangés par
    (colonne, ligne) : si la géométrie a bougé, ils restent en place mais peuvent recouvrir d'autres tuiles.

    Renvoie un avertissement dans ce cas, None sinon.
    """
    before = (ba.tiles_w, ba.tiles_h, len(ba.source_palettes))
    encode_background_asset(ba, png_path, lookup=catalogue_lookup(project))
    ba.source_stamp = file_stamp(png_path)
    project.backgrounds.save(ba)

    kept = len(ba.tile_palette_overrides) + len(ba.tile_paint)
    if kept and (ba.tiles_w, ba.tiles_h, len(ba.source_palettes)) != before:
        return (f"“{ba.name}”: image geometry changed, {kept} palette "
                f"repaint(s) kept in place — they may now cover other tiles.")
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


def apply_bg_encoding(ba: "BackgroundAsset", c: dict, lookup=None):
    """Applique un résultat de compression (dict de bg_import.encode_background)
    à un BackgroundAsset. Séparé du calcul pour permettre une compression
    hors-thread : le worker calcule `c`, le thread UI applique via ce helper.

    Ne touche ni à `ba.asset` (l'asset POINTE sa source, que l'encodage ne change pas) ni à AUCUN réglage : layout,
    profondeur, méthode, canvas, retouches de tuiles sont ceux que l'appelant a posés (cf. `BackgroundAsset.choose_layout`).
    Un encodage ne range que son RÉSULTAT — le bloc `encoded` du sidecar.

    Les palettes AJOUTÉES et les overrides sont des réglages (références au catalogue) : l'encodage refait les palettes
    dérivées du PNG, puis `resolve_palettes` y remet les overrides et les ajoutées, d'après `lookup(nom) -> couleurs`
    (cf. `catalogue_lookup`). Sans `lookup`, une ajoutée garde ses couleurs en cache. Un override devenu sans objet
    (le nouvel encodage a moins de palettes dérivées) est levé et noté dans les diagnostics."""
    kept = ba.added_palette_colors()
    ba.palettes = c["palettes"]
    # Nouvelle baseline dérivée du PNG : snapshot restaurable.
    ba.source_palettes = [list(p) for p in c["palettes"]]
    ba.diagnostics = dict(c.get("diagnostics", {}))
    if c.get("mode", "tiled") == "bitmap":
        ba.bitmap = c["bitmap"]
        ba.out_w = c["out_w"]
        ba.out_h = c["out_h"]
        # Pas de représentation tuilée en bitmap.
        ba.tileset = []
        ba.tilemap = []
        ba.tiles_w = 0
        ba.tiles_h = 0
    else:
        ba.tileset = c["tileset"]
        ba.tilemap = c["tilemap"]
        ba.tiles_w = c["tiles_w"]
        ba.tiles_h = c["tiles_h"]
        ba.bitmap = ""
        ba.out_w = 0
        ba.out_h = 0
    dropped = ba.resolve_palettes(lookup, kept)
    if dropped:
        ba.diagnostics["palette_overrides_dropped"] = dropped
    # « Ce résultat vient de ces réglages » : ceux que l'appelant a posés avant d'appeler, donc ceux de l'encodage.
    ba.encoded_for = ba.encode_settings_fingerprint()


def catalogue_lookup(project):
    """`lookup(nom) -> couleurs | None` sur le catalogue de palettes du projet, pour `apply_bg_encoding` et
    `BackgroundAsset.resolve_palettes`. Sans projet, aucune banque n'est résolue (les caches servent)."""
    if project is None:
        return None

    def lookup(name: str):
        bank = project.get_palette(name)
        return list(bank.colors) if bank is not None else None
    return lookup


def encode_background_asset(ba: "BackgroundAsset", png_path: Path, method: str = None, lookup=None):
    """Calcule et stocke la compression GBA d'un fond (palettes/tileset/tilemap)
    depuis son PNG — sans modifier le fichier. cf. core/bg_import. No-op si
    illisible. Chemin SYNCHRONE (import via watcher, reconcile au chargement).
    Dispatch selon le mode DÉJÀ choisi de l'asset (`ba.mode`/`ba.bpp`) — ne
    re-détecte PAS (la détection est faite une fois à la création), pour ne
    jamais écraser un choix de mode existant lors d'un reconcile. `lookup` : cf. `catalogue_lookup`."""
    try:
        from core.bg_import import encode_by_mode
        mode_token = "bitmap" if getattr(ba, "mode", "tiled") == "bitmap" \
            else ("tiled8" if getattr(ba, "bpp", 4) == 8 else "tiled4")
        c = encode_by_mode(png_path, mode_token, method or ba.quantize_method,
                           getattr(ba, "dither", False), ba.import_prep(), ba.compression)
        apply_bg_encoding(ba, c, lookup)
    except Exception:
        pass


# ── Rattrapage à l'ouverture d'un projet ──────────────────────────
# Le ProjectWatcher voit les fichiers qui apparaissent PENDANT que l'éditeur
# tourne. Ceux déposés à l'explorateur, éditeur fermé, ne sont vus par personne :
# les `reconcile_*` ci-dessous repassent une fois par ouverture de projet.
#
# Elles bouclent sur les assets connus et rattrapent le sidecar dont
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
    ap = project.background_image_path(ba) if ba.asset else None
    if not (ap and ap.exists()):
        return
    if not ba.tileset and not ba.bitmap:
        encode_background_asset(ba, ap, lookup=catalogue_lookup(project))
        ba.source_stamp = file_stamp(ap)
        if ba.tileset or ba.bitmap:
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
        _resync_background(project, ba, ap)
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
        # Sprite créé alors que son encodage avait échoué
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
        _resync_sprite(project, sp, ap)
    elif fresh != sp.source_stamp:
        # Contenu identique, empreinte à migrer (cf. reconcile_background).
        sp.source_stamp = fresh
        project.sprites.save(sp)


def reconcile_backgrounds(project):
    """Répare chaque fond déjà connu : compression manquante, ou image retouchée éditeur fermé (cf.
    `reconcile_background`, par asset). Rien n'est CRÉÉ : un fichier qui apparaît n'est pas un asset tant que
    l'auteur n'a pas fait *Create asset* (cf. `core.asset_creation`)."""
    for ba in list(project.backgrounds):
        reconcile_background(project, ba)


def reconcile_sprites(project):
    """Répare chaque sprite déjà connu : encodage manquant, ou planche retouchée éditeur fermé (cf.
    `reconcile_sprite`, par asset). Pendant de `reconcile_backgrounds` : rien n'est CRÉÉ."""
    for sp in list(project.sprites):
        reconcile_sprite(project, sp)


