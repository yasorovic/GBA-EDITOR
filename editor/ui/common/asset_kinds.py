"""
ui/common/asset_kinds.py — LE catalogue des familles d'assets.

Un seul endroit qui dit, pour chaque famille : où elle vit, comment on la
renomme, comment on la supprime, comment on en crée une. Les écrans n'en
choisissent que les familles qui les concernent :

    AssetFinder("Data finder",    [DATA_TABLES])
    AssetFinder("Project viewer", [SCENES, PREFABS, SCRIPTS])
    AssetFinder("Sound finder",   [SFX, MUSIC, JINGLES])

Avant ce fichier, chaque écran réécrivait ces quatre réponses pour sa propre
famille — d'où huit panneaux qui divergeaient. Cf. docs/asset-finder.md.

Les renommages passent TOUS par `Project.rename_*` et jamais par le store :
seul le projet réécrit aussi ce qui cite l'asset par son nom (les scènes, les
prefabs, les scripts Lua). Renommer dans le store laisserait des références
pendantes, silencieusement.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from pathlib import Path

from ui.common.icons import get as _ico, COLOR_DEFAULT
from ui.common.theme import QSS
from ui.common.asset_finder import AssetKind, store_nodes, dir_nodes, store_file, own_path

from core.models.unique_name import unique_name
from core.models.resource import (
    MIME_ANIMATED_BG, MIME_MUSIC, MIME_PREFAB_TEMPLATE, MIME_SCRIPT,
)
from core.history import (
    get_history, DeleteResourceCmd, DeleteFileCmd, RenameFileCmd,
)


# ──────────────────────────────────────────────────────────────────
#  Plomberie commune
# ──────────────────────────────────────────────────────────────────

def _renamer(method: str):
    """Adapte un `Project.rename_*` au contrat `AssetKind.rename`.

    Les `rename_*` ne rendent pas tous la même chose (rien, un booléen, le nom
    appliqué) ; ce qui est vrai dans tous les cas, c'est que `obj.name` porte le
    nom retenu APRÈS l'appel — y compris quand le projet a dédupliqué ou refusé."""
    def rename(project, obj, new_name: str) -> str:
        getattr(project, method)(obj, new_name)
        return obj.name
    return rename


def _store_deleter(attr: str):
    """Bâtit la suppression annulable d'un asset d'un `ResourceStore` (Ctrl+Z).

    Rend la commande SANS la pousser : le finder la pousse seule, ou groupe tout
    un lot dans un seul `MacroCmd` pour un unique Ctrl+Z (cf. AssetKind.delete)."""
    def delete(project, obj):
        return DeleteResourceCmd(getattr(project, attr), obj)
    return delete


def _store_duplicator(family: str):
    """Bâtit la duplication d'un LOT d'assets d'un `ResourceStore` : une `Duplication` par asset, commandes NON poussées.
    La copie pointe la même source (cf. core/asset_duplication) ; le finder pousse le lot en une entrée d'historique."""
    def duplicate(project, objs):
        from core import asset_duplication
        return asset_duplication.duplicate_many(project, family, objs)
    return duplicate


def _duplicate_scripts(project, paths):
    """Un script est un fichier : sa copie est un fichier voisin, sous un nom libre parmi TOUS les scripts du projet
    (un behavior se retrouve par son nom)."""
    from core import asset_duplication
    from core.command_dispatcher import get_dispatcher
    from core.lua_scripts import lua_files
    taken = {path.stem for path in lua_files(project)}
    copies = []
    for path in paths:
        command, target = asset_duplication.duplicate_script(path, taken, around=get_dispatcher().suspended)
        taken.add(target.stem)
        copies.append(asset_duplication.Duplication(command, target))
    return copies


def _font_source_deleter(project, obj):
    """Une suppression de source met aussi à jour les familles vectorielles."""
    from core.history import DeleteFontSourceCmd
    return DeleteFontSourceCmd(project, obj)


def _menu_choice(entries):
    """Petit menu au curseur — `entries` = [(libellé, action[, icône]) | (None, None)].

    Un menu plutôt qu'une enfilade de modales : le « + » d'une famille qui a
    plusieurs façons de naître (créer en 16 ou 256 couleurs, importer) pose la
    question en un clic, et l'asset naît nommé, renommable en place."""
    from PyQt6.QtWidgets import QMenu
    from PyQt6.QtGui import QCursor
    menu = QMenu()
    menu.setStyleSheet(QSS.menu)
    chosen = {}
    for entry in entries:
        label, fn = entry[0], entry[1]
        if label is None:
            menu.addSeparator()
            continue
        act = menu.addAction(_ico(entry[2], COLOR_DEFAULT), label) if len(entry) > 2 else menu.addAction(label)
        chosen[act] = fn
    act = menu.exec(QCursor.pos())
    fn = chosen.get(act)
    return fn() if fn else None


# ──────────────────────────────────────────────────────────────────
#  Monde — scènes, prefabs
# ──────────────────────────────────────────────────────────────────

SCENES = AssetKind(
    label         = "Scenes",
    label_key = 'akind.scenes',
    icon          = "scene",
    nodes         = store_nodes("scenes"),
    rename        = _renamer("rename_scene"),
    delete        = _store_deleter("scenes"),
    delete_prompt = lambda s: label('akind.delete_scene_name_ctrl_z_to_undo', name=s.name),
    add_tooltip_key = 'akind.new_scene',     # l'écran crée (scène active à reporter)
    file_of       = store_file("scenes"),
    folder_family = "scenes",
    add_menu      = True,                    # scène ou groupe : le « + » déroule un menu
    duplicate     = _store_duplicator("scenes"),
)

PREFABS = AssetKind(
    label         = "Prefabs",
    label_key = 'common.prefabs',
    icon          = "prefab",
    nodes         = store_nodes("prefabs"),
    rename        = _renamer("rename_prefab"),
    delete        = _store_deleter("prefabs"),
    delete_prompt = lambda p: label('akind.delete_prefab_name_ctrl_z_to_undo', name=p.name),
    add_tooltip_key = 'akind.new_prefab',
    # Glisser un prefab sur le canvas l'y instancie.
    mime          = (MIME_PREFAB_TEMPLATE, lambda project, pf: pf.name),
    file_of       = store_file("prefabs"),
    duplicate     = _store_duplicator("prefabs"),
)


# ──────────────────────────────────────────────────────────────────
#  Logique — scripts (seule famille dont le DISQUE est la vérité)
# ──────────────────────────────────────────────────────────────────

def _script_icon(path: Path):
    return _ico("script_lua" if path.suffix == ".lua" else "script_file",
                COLOR_DEFAULT)


def _rename_script(project, path: Path, new_text: str) -> str:
    """Un script est un fichier : le renommer, c'est renommer le fichier.

    L'arbre affiche le nom COMPLET (avec extension) et c'est ce texte qu'on
    édite ; si l'utilisateur n'a pas tapé une extension de script reconnue, on
    conserve celle d'origine plutôt que de la perdre sans un mot."""
    new_path = (path.parent / new_text if Path(new_text).suffix in (".lua", ".c")
                else path.parent / f"{new_text}{path.suffix}")
    if new_path == path:
        return path.name
    get_history().push(RenameFileCmd(path, new_path))
    return new_path.name


SCRIPTS = AssetKind(
    label         = "Scripts",
    label_key = 'akind.scripts',
    icon          = "script_lua",
    icon_of       = _script_icon,
    nodes         = dir_nodes("assets_dir", (".lua", ".c"), prune_empty=True),
    rename        = _rename_script,
    delete        = lambda project, path: DeleteFileCmd(path),
    delete_prompt = lambda p: label('akind.delete_name_ctrl_z_to_undo', name=p.name),
    add_tooltip_key = 'akind.new_script',
    add_menu      = True,                    # script ou behavior : le « + » déroule un menu
    # Glisser un script sur un actor lui attache un ScriptComponent. La charge
    # utile est le chemin RELATIF au projet : un chemin absolu ne survivrait pas
    # au déplacement du dossier de projet.
    mime          = (MIME_SCRIPT,
                     lambda project, path: (project.asset_rel(path)
                                            if project else path)),
    file_of       = own_path,
    duplicate     = _duplicate_scripts,
)


# ──────────────────────────────────────────────────────────────────
#  Entités — sprites
# ──────────────────────────────────────────────────────────────────

def _sprite_group(sprite) -> str:
    """Dossier DEVINÉ d'un sprite : ce qui précède le premier « _ ». Un préfixe
    trop court ne dit rien (« a_ », « ui_ ») et ne fait pas un rangement."""
    head, sep, _rest = sprite.name.partition("_")
    return head if sep and len(head) > 2 else ""


def _rename_sprite(project, sprite, new_name: str) -> str:
    """Par le DISPATCHER et non par le projet : renommer un sprite déplace aussi
    le PNG et son sidecar, ce qui doit se faire surveillant suspendu, et les
    canvas de scène ouverts doivent être prévenus."""
    from core.command_dispatcher import get_dispatcher
    if project.sprites.get(new_name) is not None:
        return sprite.name              # nom déjà pris : refus silencieux
    get_dispatcher().rename_sprite(sprite, new_name)
    return sprite.name


def _relink_action(family: str):
    """« Relink source… » : relier l'asset à un autre fichier, quand le sien a disparu — ou pour en changer.
    Un petit sélecteur à recherche liste les fichiers du projet de CE format (ceux que la famille accepte) ; un
    refus se dit, et l'asset reste inchangé."""
    def run(project, asset):
        from PyQt6.QtGui import QCursor
        from PyQt6.QtWidgets import QApplication
        from ui.common.popup import MessageBox as QMessageBox
        from core import asset_relink
        from core.command_dispatcher import get_dispatcher
        from ui.common.theme import C
        from ui.common.widgets import ScriptPickerPopup
        title = label('akind.relink_source_title', name=asset.name)
        files = asset_relink.compatible_files(project, family)
        if not files:
            QMessageBox.information(None, title, label('akind.relink_none'))
            return
        entries = [(p.relative_to(project.assets_dir).as_posix(), str(p)) for p in files]
        popup = ScriptPickerPopup(entries, C.ACCENT, new_label=None)

        warning = {"backgrounds": "akind.relink_warn_background",
                   "sprites": "akind.relink_warn_image"}.get(family)

        def picked(chosen: str):
            # Une image relue repart de ses réglages d'import : on le dit avant, pas après.
            if warning and QMessageBox.question(
                    None, title, label(warning),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            try:
                get_dispatcher().relink_asset_source(family, asset, chosen)
            except ValueError as error:
                QMessageBox.warning(None, title, str(error))

        popup.picked.connect(picked)
        popup.adjustSize()
        pos = QCursor.pos()
        geo = (QApplication.screenAt(pos) or QApplication.primaryScreen()).availableGeometry()
        pos.setX(max(geo.left(), min(pos.x(), geo.right() - popup.width() + 1)))
        pos.setY(max(geo.top(), min(pos.y(), geo.bottom() - popup.height() + 1)))
        popup.move(pos)
        popup.show()
    return ('akind.relink_source', run)


SPRITES = AssetKind(
    label         = "Sprites",
    label_key = 'common.sprites',
    icon          = "sprite",
    nodes         = store_nodes("sprites", group_by=_sprite_group,
                                collapse_singletons=True),
    rename        = _rename_sprite,
    delete        = _store_deleter("sprites"),
    delete_prompt = lambda s: label('akind.delete_sprite_name_ctrl_z_to_undo', name=s.name),
    # Un sprite se crée uniquement par import d'une image : l'écran ouvre le
    # dialogue (il lui faut un parent), le finder ne fait que le demander.
    add_tooltip_key = 'akind.import_a_sprite_sheet',
    actions       = (_relink_action("sprites"),),
    file_of       = store_file("sprites"),
    duplicate     = _store_duplicator("sprites"),
)


# ──────────────────────────────────────────────────────────────────
#  Décor — fonds
# ──────────────────────────────────────────────────────────────────

BACKGROUNDS = AssetKind(
    label  = "Backgrounds",
    label_key = 'common.backgrounds',
    icon   = "background",
    # `kind` (scene / ui / animated) est le seul axe de rangement que le modèle
    # porte déjà : on s'en sert comme dossier tant que l'utilisateur n'a pas les
    # siens (cf. docs/asset-finder.md).
    nodes  = store_nodes("backgrounds", group_by=lambda bg: getattr(bg, "kind", "")),
    rename = _renamer("rename_background"),
    delete = _store_deleter("backgrounds"),
    actions = (_relink_action("backgrounds"),),
    file_of = store_file("backgrounds"),
    duplicate = _store_duplicator("backgrounds"),
)


_BACKGROUND_LABEL_KEYS = {'scene': 'common.backgrounds', 'ui': 'akind.ui_backgrounds', 'animated': 'akind.animated'}


def _background_of_kind(bg_kind: str, label: str, add_tooltip: str,
                        mime=None, add_menu: bool = False) -> AssetKind:
    """Une famille par `kind` de fond — le Background Editor donne à chacune sa
    propre section, parce que chacune a son propre import (« un PNG », « un
    cadre d'UI », « une planche d'animation ») : trois boutons, trois phrases,
    ce qu'une section unique ne saurait pas offrir.

    Ailleurs (Scene Manager), `BACKGROUNDS` ci-dessus montre les trois d'un coup,
    rangées par `kind`. Même store, deux façons de le présenter."""
    return AssetKind(
        label       = label,
        label_key   = _BACKGROUND_LABEL_KEYS[bg_kind],
        icon        = "background",
        nodes       = store_nodes("backgrounds",
                                  where=lambda bg, k=bg_kind: getattr(bg, "kind", "") == k),
        rename      = _renamer("rename_background"),
        delete      = _store_deleter("backgrounds"),
        add_tooltip_key = add_tooltip,      # sans `add` : l'écran ouvre l'import
        add_menu    = add_menu,
        mime        = mime,
        actions     = (_relink_action("backgrounds"),),
        file_of     = store_file("backgrounds"),
        duplicate   = _store_duplicator("backgrounds"),
    )


BACKGROUNDS_SCENE = _background_of_kind("scene", "Backgrounds", 'akind.import_a_png',
                                        add_menu=True)
BACKGROUNDS_UI    = _background_of_kind("ui", "UI backgrounds",
                                        'akind.import_a_ui_frame_or_panel_png')
# Un fond animé se POSE sur le canvas d'un fond hôte : c'est la seule famille de
# fonds qui se glisse (cf. project_v04_decor_animation).
BACKGROUNDS_ANIM  = _background_of_kind("animated", "Animated",
                                        'akind.import_an_animation_sheet_png',
                                        mime=(MIME_ANIMATED_BG,
                                              lambda project, bg: bg.name))


# ──────────────────────────────────────────────────────────────────
#  Texte — polices
# ──────────────────────────────────────────────────────────────────

FONTS = AssetKind(
    label      = "Fonts",
    label_key = 'common.fonts',
    icon       = "font",
    nodes      = store_nodes("fonts"),
    rename     = _renamer("rename_font"),
    delete     = _font_source_deleter,
    actions    = (_relink_action("fonts"),),
    file_of    = store_file("fonts"),
    duplicate  = _store_duplicator("fonts"),
    # Pas de « + » : une police se crée depuis un PNG, un .fnt, un .ttf ou un .otf, par *Create* dans l'onglet Disk
    # (core.asset_creation), comme sprites et fonds.
    empty_text_key = 'akind.no_font_drop_a_png_or_a_fnt',
    tooltip_of = lambda f: (
        tooltip(
            title=f.name,
            body=label('akind.font_source_tip', value=len(f.glyphs), cell_w=f.cell_w,
                       cell_h=f.cell_h, value_2=f.tile_count()),
            note=label('akind.font_source_note', source_format=f.source_format))
    ),
)


def _new_font_asset(project):
    """Crée une police logique, préliée à la première source disponible."""
    from core.history import AddResourceCmd
    from core.models.font_asset import FontAsset

    asset = FontAsset(name=unique_name("Font", {item.name for item in project.font_assets}))
    if project.fonts:
        asset.sources = {"regular": [project.fonts[0].name]}
    get_history().push(AddResourceCmd(project.font_assets, asset))
    return asset


FONT_ASSETS = AssetKind(
    label="Font assets",
    label_key="akind.font_assets",
    icon="font",
    nodes=store_nodes("font_assets"),
    rename=_renamer("rename_font_asset"),
    delete=_store_deleter("font_assets"),
    add=_new_font_asset,
    add_tooltip_key="akind.new_font_asset",
    file_of=store_file("font_assets"),
    duplicate=_store_duplicator("font_assets"),
    empty_text_key="akind.no_font_assets",
    tooltip_of=lambda asset: tooltip(
        title=asset.name,
        body=label("akind.font_asset_tip", pixel_height=asset.pixel_height,
                   line_height=asset.line_height),
    ),
)


# ──────────────────────────────────────────────────────────────────
#  Couleurs — palettes
# ──────────────────────────────────────────────────────────────────

def _palette_icon(bank):
    from ui.common.palette_swatch import bank_icon
    return bank_icon(bank)


def _new_palette(project, size: int):
    from core.models.palette import PaletteBank
    from core.palette_presets import hsb_ramp_bgr555
    from core.history import AddResourceCmd
    bank = PaletteBank(name=unique_name("Palette", {item.name for item in project.palettes}),
                       colors=hsb_ramp_bgr555(0, 0, steps=size), size=size)
    get_history().push(AddResourceCmd(project.palettes, bank))
    return bank


def _import_palette(project):
    """Crée une palette depuis un fichier (.gpl / .pal / liste hex) — nom = nom
    de fichier, taille déduite du nombre de couleurs."""
    from PyQt6.QtWidgets import QFileDialog
    from ui.common.popup import MessageBox as QMessageBox
    from pathlib import Path as _P
    from core.history import AddResourceCmd
    from core.palette_io import PALETTE_IMPORT_FILTER, import_palette

    path, _ = QFileDialog.getOpenFileName(
        None, label('akind.import_a_palette'), "", PALETTE_IMPORT_FILTER)
    if not path:
        return None
    try:
        bank = import_palette(_P(path), unique_name(_P(path).stem, {item.name for item in project.palettes}))
    except (OSError, ValueError) as e:
        QMessageBox.warning(None, label('akind.import'), label('akind.unreadable_file_e', e=e))
        return None
    get_history().push(AddResourceCmd(project.palettes, bank))
    return bank


def _add_palette(project):
    """Le « + » propose la taille et l'import dans un seul menu, plutôt que
    d'enchaîner deux modales avant que la palette existe (cf. la règle « inline
    plutôt que dialogues ») : la banque naît nommée, et le finder ouvre aussitôt
    son renommage en place."""
    return _menu_choice([
        (label('akind.new_16_color_palette_4bpp'),  lambda: _new_palette(project, 16), "palette"),
        (label('akind.new_256_color_palette_8bpp'), lambda: _new_palette(project, 256), "palette"),
        (None, None),
        (label('akind.import_2'),                      lambda: _import_palette(project), "import"),
    ])


PALETTES = AssetKind(
    label       = "Palettes",
    label_key = 'common.palettes',
    icon        = "palette",
    icon_of     = _palette_icon,
    nodes       = store_nodes("palettes"),
    suffix_of   = lambda bank: str(len(bank.colors)),
    rename      = _renamer("rename_palette"),
    delete      = _store_deleter("palettes"),
    delete_prompt = lambda b: label('akind.delete_palette_name_ctrl_z_to_undo', name=b.name),
    add         = _add_palette,
    add_tooltip_key = 'akind.add_palette',
    add_tip_key = 'akind.add_palette_tip',
    file_of     = store_file("palettes"),
    duplicate   = _store_duplicator("palettes"),
)


# ──────────────────────────────────────────────────────────────────
#  Audio — sfx, musiques
# ──────────────────────────────────────────────────────────────────

def _add_sound(attr: str, cls_name: str, base: str):
    """Crée un SFX / une piste nommé d'office. Pas de modale qui réclame un nom
    avant que la chose existe : le finder ouvre le renommage en place ensuite."""
    def add(project):
        import core.models.audio as audio_models
        from core.history import AddResourceCmd
        store = getattr(project, attr)
        asset = getattr(audio_models, cls_name)(name=unique_name(base, {item.name for item in store}))
        get_history().push(AddResourceCmd(store, asset))
        return asset
    return add


SFX = AssetKind(
    label         = "SFX",
    label_key = 'common.sfx',
    icon          = "sfx",
    nodes         = store_nodes("sfx"),
    rename        = _renamer("rename_sound"),
    delete        = _store_deleter("sfx"),
    delete_prompt = lambda a: label('akind.delete_sfx_name_ctrl_z_to_undo', name=a.name),
    add           = _add_sound("sfx", "Sfx", "SFX"),
    add_tooltip_key = 'akind.add_an_sfx',
    actions       = (_relink_action("sfx"),),
    file_of       = store_file("sfx"),
    folder_family = "sfx",
    duplicate     = _store_duplicator("sfx"),
)

MUSIC = AssetKind(
    label         = "Music",
    label_key = 'akind.music',
    icon          = "music",
    nodes         = store_nodes("music"),
    # Glissable vers le graphe de la MusicBox : lâchée sur un nœud, elle en
    # devient la piste ; lâchée sur le vide, elle crée l'état qui la joue.
    mime          = (MIME_MUSIC, lambda _p, m: m.name),
    rename        = _renamer("rename_sound"),
    delete        = _store_deleter("music"),
    delete_prompt = lambda a: label('akind.delete_track_name_ctrl_z_to_undo', name=a.name),
    add           = _add_sound("music", "Music", "Track"),
    add_tooltip_key = 'akind.add_a_track',
    actions       = (_relink_action("music"),),
    file_of       = store_file("music"),
    folder_family = "music",
    duplicate     = _store_duplicator("music"),
)

# Un jingle est un module comme une musique, mais d'un autre DOSSIER — et c'est
# ce dossier qui dit le rôle. Pas de `mime` : il ne se dépose pas dans le graphe
# d'une MusicBox, qui ne lit que des musiques.
JINGLES = AssetKind(
    label         = "Jingles",
    label_key = 'akind.jingles',
    icon          = "jingle",
    nodes         = store_nodes("jingles"),
    rename        = _renamer("rename_sound"),
    delete        = _store_deleter("jingles"),
    delete_prompt = lambda a: label('akind.delete_jingle_name_ctrl_z_to_undo', name=a.name),
    add           = _add_sound("jingles", "Jingle", "Jingle"),
    add_tooltip_key = 'akind.add_a_jingle',
    actions       = (_relink_action("jingles"),),
    file_of       = store_file("jingles"),
    folder_family = "jingles",
    duplicate     = _store_duplicator("jingles"),
)


# ──────────────────────────────────────────────────────────────────
#  Données — tables
# ──────────────────────────────────────────────────────────────────

def _add_data_table(project):
    """Crée une table d'UNE colonne et d'aucune ligne. Une colonne d'office
    plutôt qu'une table vide : une grille sans colonne n'a nulle part où poser
    une ligne."""
    from core.models.data_table import DataTable, DataColumn
    from core.history import AddResourceCmd

    name = unique_name("Table", {t.name for t in project.data_tables})
    table = DataTable(name=name, columns=[DataColumn(name="valeur", type="int")], rows=[])
    get_history().push(AddResourceCmd(project.data_tables, table))
    return table


def _rename_data_table(project, table, new_name: str) -> str:
    # Seul `rename_*` à rendre un booléen : le nom d'une table s'écrit comme du
    # code dans les scripts (`data.Objets`), donc il doit être un identifiant.
    # Un refus laisse `table.name` inchangé, ce que l'arbre réaffichera.
    project.rename_data_table(table, new_name)
    return table.name


def _table_state(project, table):
    return (("data_table_linked", label('akind.table_linked_tip', group=table.text_link.get("prefix", "")))
            if table.text_link else None)


DATA_TABLES = AssetKind(
    label         = "Tables",
    label_key = 'akind.tables',
    icon          = "data_table",
    nodes         = store_nodes("data_tables"),
    suffix_of     = lambda t: f"{len(t.rows)} × {len(t.columns)}",
    state_of      = _table_state,
    rename        = _rename_data_table,
    delete        = _store_deleter("data_tables"),
    delete_prompt = lambda t: label('akind.delete_table_name_ctrl_z_to_undo', name=t.name),
    add           = _add_data_table,
    add_tooltip_key = 'akind.new_table',
    file_of       = store_file("data_tables"),
    duplicate     = _store_duplicator("data_tables"),
)


ALL_KINDS = (
    SCENES, PREFABS, SCRIPTS, SPRITES, BACKGROUNDS,
    FONTS, PALETTES, SFX, MUSIC, JINGLES, DATA_TABLES,
)
