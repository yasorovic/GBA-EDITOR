"""Assemblage du lecteur web et d'une ROM déjà compilée.

Un seul lecteur (index.html, main.js, player.css), deux habillages :
- Built-in : `style.css` fourni, réglé par `theme.css` que ce module écrit à partir
  des réglages `web_*` du projet. Seules des variables CSS changent, jamais la mise
  en page.
- Custom : le lecteur vierge, ou le dossier `web_template/` éjecté dans le projet,
  et `custom.css`, écrit à chaque build depuis `web_custom_css`. Le champ du projet
  est la seule source de ce CSS : un `custom.css` posé dans le dossier éjecté est
  ignoré, ce qui évite d'écraser l'un par l'autre.

Le ZIP doit aussi jouer ouvert depuis le disque (file://), où le navigateur refuse
les modules ES et `fetch`. L'export réunit donc les modules en un script classique
(`player.js`, shaders compris) et écrit la ROM et le moteur wasm en base64 dans des
scripts (`rom.js`, `vendor/mgba.wasm.js`).
"""

import base64
import html
import json
import posixpath
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
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
_MODULE_SCRIPT = '<script type="module" src="main.js"></script>'
_ENGINE_WASM = "vendor/mgba.wasm"
_ENGINE_GLUE = "vendor/mgba.js"        # script classique, chargé par le SDK
_SHADER_SOURCES = (".ini", ".fs", ".vs")
_IMPORT = re.compile(r"""^import\s*\{([^}]*)\}\s*from\s*["'](\.{1,2}/[^"']+)["'];?[ \t]*$""", re.M)
_EXPORT_DECLARATION = re.compile(
    r"^export\s+((?:async\s+)?(?:function\*?|class|const|let)\s+([A-Za-z_$][\w$]*))", re.M)
_EXPORT_LIST = re.compile(r"^export\s*\{([^}]*)\};?[ \t]*$", re.M)
_EXPORT_DEFAULT = re.compile(r"^export\s+default\s+", re.M)
_MODULE_SYNTAX_LEFT = re.compile(r"^\s*(?:import|export)\b|\bimport\s*\(|\bimport\.meta\b", re.M)


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


def _bundle_modules(sources: dict[str, Path], shader_files: dict[str, str]) -> str:
    """Réunit les modules ES du lecteur, depuis `main.js`, en un script classique.
    Chaque module garde sa portée dans une fonction ; ses exports deviennent un objet
    que les modules suivants déstructurent. Seules les formes d'import et d'export
    employées par le lecteur sont acceptées."""
    visited: set[str] = set()
    bodies: list[str] = []      # dépendances d'abord : un module s'écrit après ses imports

    def visit(name: str) -> None:
        if name in visited:
            return
        if name not in sources:
            raise WebTemplateError(f"Web player module not found: {name}")
        visited.add(name)
        code = sources[name].read_text(encoding="utf-8").replace("\r\n", "\n")

        def take_import(match: re.Match) -> str:
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), match[2]))
            visit(target)
            names = [part.strip().replace(" as ", ": ") for part in match[1].split(",") if part.strip()]
            return f"const {{ {', '.join(names)} }} = modules[{json.dumps(target)}];"

        code = _IMPORT.sub(take_import, code)
        members = [match[2] for match in _EXPORT_DECLARATION.finditer(code)]
        code = _EXPORT_DECLARATION.sub(r"\1", code)
        for match in _EXPORT_LIST.finditer(code):
            for part in filter(None, (part.strip() for part in match[1].split(","))):
                local, _, exported = part.partition(" as ")
                members.append(f"{exported.strip()}: {local.strip()}" if exported else local)
        code = _EXPORT_LIST.sub("", code)
        if _EXPORT_DEFAULT.search(code):
            code = _EXPORT_DEFAULT.sub("const moduleDefault = ", code)
            members.append("default: moduleDefault")
        code = code.replace("import.meta.url", f"new URL({json.dumps(name)}, playerUrl).href")
        if _MODULE_SYNTAX_LEFT.search(code):
            raise WebTemplateError(f"Web player module uses an unsupported import or export form: {name}")
        bodies.append(f"// {name}\nmodules[{json.dumps(name)}] = (() => {{\n{code}\n"
                      f"return {{ {', '.join(members)} }};\n}})();\n")

    visit("main.js")
    return ("globalThis.BACKSTAGE_SHADER_FILES = "
            f"{json.dumps(shader_files, ensure_ascii=False, sort_keys=True)};\n"
            '(() => {\n"use strict";\nconst playerUrl = document.currentScript.src;\n'
            "const modules = {};\n" + "".join(bodies) + "})();\n")


def _for_local_files(texts: dict[str, str], entries: list[tuple[str, Path]],
                     rom: Path, rom_name: str) -> list[tuple[str, Path]]:
    """Rend le paquet jouable depuis le disque : modules réunis dans `player.js`,
    ROM et moteur en base64. Renvoie les fichiers restants à copier tels quels."""
    files = dict(entries)
    if _ENGINE_WASM not in files:
        raise WebTemplateError(f"Web player file not found: {_ENGINE_WASM}")
    shader_files = {name.removeprefix("shaders/"): path.read_text(encoding="utf-8")
                    for name, path in files.items()
                    if name.startswith("shaders/") and path.suffix in _SHADER_SOURCES}
    modules = {name: path for name, path in files.items()
               if name.endswith(".js") and name != _ENGINE_GLUE}
    texts["player.js"] = _bundle_modules(modules, shader_files)
    wasm = base64.b64encode(files[_ENGINE_WASM].read_bytes()).decode()
    texts[f"{_ENGINE_WASM}.js"] = f'globalThis.BACKSTAGE_MGBA_WASM = "{wasm}";\n'
    texts["rom.js"] = f'globalThis.BACKSTAGE_ROM = "{base64.b64encode(rom.read_bytes()).decode()}";\n'
    page = _replace_once(texts["index.html"], _ROM_MARKER,
                         f'data-rom="{html.escape(rom_name)}"', "empty data-rom attribute")
    texts["index.html"] = _replace_once(
        page, _MODULE_SCRIPT,
        f'<script src="rom.js"></script>\n    <script src="{_ENGINE_WASM}.js"></script>\n'
        '    <script src="player.js"></script>', "main.js module script")
    bundled = set(modules) | {_ENGINE_WASM} | {f"shaders/{name}" for name in shader_files}
    return [(name, path) for name, path in entries if name not in bundled]


def export_web(rom: Path, destination: Path, settings: ProjectSettings,
               project_root: Path, title: str) -> None:
    """Produit le ZIP du lecteur web et de la ROM, selon le mode du projet.
    `title` nomme la page et la ROM du paquet."""
    texts, entries = web_player_files(settings, project_root, title)
    # Le nom de la ROM est aussi la clé de sa sauvegarde dans le navigateur.
    entries = _for_local_files(texts, entries, rom, f"{re.sub(r'[\\/]', '_', title)}.gba")

    with NamedTemporaryFile(dir=destination.parent, delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        with ZipFile(temp_path, "w", compression=ZIP_DEFLATED) as archive:
            for name, text in texts.items():
                archive.writestr(name, text)
            for name, source in entries:
                archive.write(source, name)
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
