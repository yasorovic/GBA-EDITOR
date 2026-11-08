"""Assemblage du lecteur web et d'une ROM déjà compilée.

Un seul lecteur (index.html, main.js, player.css), deux habillages :
- Built-in : `style.css` fourni, réglé par `theme.css` que ce module écrit à partir
  des réglages `web_*` du projet. Seules des variables CSS changent, jamais la mise
  en page.
- Custom : le lecteur vierge, ou le dossier `web_template/` éjecté dans le projet,
  et `custom.css`, écrit à chaque build depuis `web_custom_css`. Le champ du projet
  est la seule source de ce CSS : un `custom.css` posé dans le dossier éjecté est
  ignoré, ce qui évite d'écraser l'un par l'autre.
"""

import html
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from core.app_paths import WEB_PLAYER_DIR
from core.models.settings import ProjectSettings
from core.resources.resource_store import replace_with_retry


EJECTED_TEMPLATE = "web_template"      # dossier du projet
FRAME_SIZE = (272, 208)                # contour à la résolution native

# Le lecteur vierge : tout ce qu'il faut pour jouer, sans habillage.
_PLAYER_FILES = (
    "LICENSE", "main.js", "shaders.js", "player.css", "BackStage-logo-long-white.svg",
    "save.js", "vendor/mgba.js", "vendor/mgba.wasm", "vendor/mgba.sdk.js",
    "vendor/mgba.config.js", "vendor/mgba.manifest.js", "vendor/mgba.options.js",
    "vendor/mgba.zip.js", "vendor/mgba.sdk.ts", "vendor/mgba_shim.c", "vendor/MPL-2.0.txt",
    "vendor/NOTICE.txt",
)
_BUILTIN_FILES = (
    "style.css",
    "Sniglet-Regular.ttf", "Sniglet-OFL.txt",
    "BalsamiqSans-Bold.ttf", "BalsamiqSans-OFL.txt",
)
_PROTOTYPE_BLOCK = re.compile(r"[ \t]*<!-- prototype -->.*?<!-- /prototype -->\n?", re.S)
_SKIN_LINK = '<link rel="stylesheet" href="style.css">'
_ROM_MARKER = 'data-rom=""'
_FRAME_MARKER = 'data-frame="backstage"'
_TITLE = re.compile(r"<title>.*?</title>", re.S)
_FRAME_SUFFIXES = (".png", ".webp", ".svg")


class WebTemplateError(ValueError):
    """Le gabarit ou un réglage du lecteur web empêche l'export."""


def _replace_once(page: str, old: str, new: str, what: str) -> str:
    if page.count(old) != 1:
        raise WebTemplateError(f"Web template must contain a single {what}.")
    return page.replace(old, new)


def _page(mode: str, settings: ProjectSettings, title: str) -> str:
    """index.html du lecteur fourni, préparé pour l'habillage du mode."""
    page = (WEB_PLAYER_DIR / "index.html").read_text(encoding="utf-8")
    page = _PROTOTYPE_BLOCK.sub("", page)
    page = _TITLE.sub(f"<title>{html.escape(title)}</title>", page, count=1)
    if mode == "builtin":
        page = _replace_once(page, _SKIN_LINK,
                             f'{_SKIN_LINK}\n    <link rel="stylesheet" href="theme.css">',
                             "style.css link")
        return _replace_once(page, _FRAME_MARKER, f'data-frame="{settings.web_frame}"',
                             "backstage frame attribute")
    return _replace_once(page, _SKIN_LINK, '<link rel="stylesheet" href="custom.css">',
                         "style.css link")


def eject_template(destination: Path, title: str) -> None:
    """Copie le lecteur vierge dans `destination` (le dossier `web_template/` du
    projet). Les fichiers du lecteur sont remplacés, les autres sont laissés."""
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "index.html").write_text(
        _page("custom", ProjectSettings(), title), encoding="utf-8", newline="\n")
    for name, source in _player_files():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def _player_files():
    """(nom dans le paquet, fichier source) du lecteur vierge, shaders compris."""
    for name in _PLAYER_FILES:
        yield name, WEB_PLAYER_DIR / name
    # Les shaders de mGBA (un dossier par shader, avec sa licence).
    for path in sorted((WEB_PLAYER_DIR / "shaders").rglob("*")):
        if path.is_file():
            yield path.relative_to(WEB_PLAYER_DIR).as_posix(), path


def _project_image(root: Path, relative: str, suffixes: tuple, what: str) -> Path:
    path = root / relative
    if path.suffix.lower() not in suffixes:
        raise WebTemplateError(f"Web player {what} must be one of: {', '.join(suffixes)} ({relative}).")
    if not path.is_file():
        raise WebTemplateError(f"Web player {what} not found: {relative}")
    return path


def _check_frame_size(path: Path) -> None:
    """Même règle que le prototype : le contour suit la grille native, une image
    matricielle doit en être un multiple exact (un SVG garde ses proportions)."""
    if path.suffix.lower() == ".svg":
        return
    from PIL import Image
    with Image.open(path) as image:
        width, height = image.size
    scale = width // FRAME_SIZE[0]
    if scale < 1 or (width, height) != (FRAME_SIZE[0] * scale, FRAME_SIZE[1] * scale):
        raise WebTemplateError(
            f"Web player frame image is {width} x {height} px; "
            f"it must be {FRAME_SIZE[0]} x {FRAME_SIZE[1]} px or an exact multiple.")


def theme_css(settings: ProjectSettings, frame_entry: str = "") -> str:
    """Les variables de `style.css` réglées par le projet (mode Built-in)."""
    s = settings
    shadow = "0 .75rem 1.5rem #000000b3" if s.web_player_shadow else "none"
    lines = [
        ("--player-color", s.web_player_color),
        ("--player-shadow", shadow),
        ("--text-color", s.web_text_color),
        ("--button-color", s.web_button_color),
        ("--button-border-color", s.web_button_border_color),
        ("--button-border-width", f"{int(s.web_button_border_width)}px"),
        ("--accent-color", s.web_accent_color),
    ]
    if frame_entry:
        lines.append(("--frame-image", f'url("{frame_entry}")'))
    body = "\n".join(f"  {name}: {value};" for name, value in lines)
    return f"/* Generated by Backstage from the project's web player settings. */\n:root {{\n{body}\n}}\n"


def web_player_files(settings: ProjectSettings, project_root: Path, title: str, *,
                     preview: bool = False) -> tuple[dict[str, str], list[tuple[str, Path]]]:
    """Prépare les mêmes fichiers de lecteur pour l'export et l'aperçu sans ROM."""
    entries: list[tuple[str, Path]] = []   # (nom dans le paquet, source)
    texts: dict[str, str] = {}

    ejected = project_root / EJECTED_TEMPLATE
    if settings.web_player_mode == "custom" and ejected.is_dir():
        page = (ejected / "index.html").read_text(encoding="utf-8")
        for path in sorted(ejected.rglob("*")):
            name = path.relative_to(ejected).as_posix()
            if path.is_file() and name not in ("index.html", "custom.css"):
                entries.append((name, path))
    else:
        page = _page(settings.web_player_mode, settings, title)
        entries.extend(_player_files())

    if settings.web_player_mode == "custom":
        texts["custom.css"] = settings.web_custom_css
    else:
        entries.extend((name, WEB_PLAYER_DIR / name) for name in _BUILTIN_FILES)
        frame_entry = ""
        if settings.web_frame == "image" and (settings.web_frame_image or not preview):
            if not settings.web_frame_image:
                raise WebTemplateError("Web player frame is set to an image, but no image is chosen.")
            frame = _project_image(project_root, settings.web_frame_image,
                                   _FRAME_SUFFIXES, "frame image")
            _check_frame_size(frame)
            frame_entry = f"theme/frame{frame.suffix.lower()}"
            entries.append((frame_entry, frame))
        texts["theme.css"] = theme_css(settings, frame_entry)

    texts["index.html"] = page
    return texts, entries


def export_web(rom: Path, destination: Path, settings: ProjectSettings,
               project_root: Path, title: str) -> None:
    """Produit le ZIP du lecteur web et de la ROM, selon le mode du projet.
    `title` nomme la page et la ROM du paquet."""
    texts, entries = web_player_files(settings, project_root, title)
    rom_entry = f"rom/{re.sub(r'[\\/]', '_', title)}.gba"
    texts["index.html"] = _replace_once(texts["index.html"], _ROM_MARKER,
                                        f'data-rom="{quote(rom_entry)}"', "empty data-rom attribute")

    with NamedTemporaryFile(dir=destination.parent, delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        with ZipFile(temp_path, "w", compression=ZIP_DEFLATED) as archive:
            for name, text in texts.items():
                archive.writestr(name, text)
            for name, source in entries:
                archive.write(source, name)
            archive.write(rom, rom_entry)
        try:
            replace_with_retry(temp_path, destination)
        except PermissionError as exc:
            raise WebTemplateError(
                f"Could not replace {destination}. Close any app or File Explorer preview "
                "that has the ZIP open, then retry Build WEB. If the ZIP is closed, "
                "check write permissions for the file and build folder."
            ) from exc
    finally:
        temp_path.unlink(missing_ok=True)
