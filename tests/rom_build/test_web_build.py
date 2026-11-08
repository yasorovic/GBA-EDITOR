"""Le paquet du lecteur web : thème Built-in, CSS personnalisé, gabarit éjecté."""
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

from codegen import web_build
from codegen.web_build import WebTemplateError, eject_template, export_web
from core.models.settings import ProjectSettings, web_player_setting
from core.project import Project

_INDEX = """<!doctype html>
<html>
  <head>
    <title>Prototype</title>
    <link rel="stylesheet" href="player.css">
    <link rel="stylesheet" href="style.css">
  </head>
  <body>
    <main>
      <!-- prototype -->
      <header>Vue mobile</header>
      <!-- /prototype -->
      <section class="player" data-frame="backstage"><button id="play" data-rom=""></button></section>
    </main>
    <script type="module" src="main.js"></script>
  </body>
</html>
"""


@pytest.fixture
def template(tmp_path, monkeypatch):
    root = tmp_path / "template"
    (root / "vendor").mkdir(parents=True)
    (root / "shaders" / "lcd.shader").mkdir(parents=True)
    (root / "index.html").write_text(_INDEX, encoding="utf-8")
    for name in web_build._PLAYER_FILES + web_build._BUILTIN_FILES:
        (root / name).write_text(name, encoding="utf-8")
    (root / "shaders" / "lcd.shader" / "manifest.ini").write_text("[shader]", encoding="utf-8")
    monkeypatch.setattr(web_build, "WEB_PLAYER_DIR", root)
    return root


@pytest.fixture
def rom(tmp_path):
    path = tmp_path / "rom.gba"
    path.write_bytes(b"ROM")
    return path


def _export(tmp_path, rom, settings):
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    destination = tmp_path / "Jeu-web.zip"
    export_web(rom, destination, settings, project, "Jeu")
    with ZipFile(destination) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


@pytest.mark.parametrize("locked", [False, True])
def test_le_remplacement_du_zip_resiste_aux_verrous(tmp_path, template, rom, monkeypatch, locked):
    destination = tmp_path / "Jeu-web.zip"
    destination.write_bytes(b"ancien ZIP")
    replace = Path.replace
    first_attempt = True

    def replace_locked(source, target):
        nonlocal first_attempt
        if target == destination and (first_attempt or locked):
            first_attempt = False
            raise PermissionError("ZIP locked")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", replace_locked)
    if locked:
        with pytest.raises(WebTemplateError, match="Close any app"):
            export_web(rom, destination, ProjectSettings(), tmp_path, "Jeu")
        assert destination.read_bytes() == b"ancien ZIP"
    else:
        export_web(rom, destination, ProjectSettings(), tmp_path, "Jeu")
        with ZipFile(destination) as archive:
            assert archive.read("rom.js") == b'globalThis.BACKSTAGE_ROM = "Uk9N";\n'
    assert set(tmp_path.iterdir()) == {destination, rom, template}


@pytest.mark.parametrize("frame", ["none", "backstage-light"])
def test_built_in_ecrit_le_theme_sans_la_page_de_prototype(tmp_path, template, rom, frame):
    settings = ProjectSettings(web_player_color="#102030", web_button_border_width=3,
                               web_player_shadow=True, web_frame=frame)
    files = _export(tmp_path, rom, settings)
    index = files["index.html"].decode()
    assert "prototype" not in index and "Vue mobile" not in index
    assert "<title>Jeu</title>" in index
    assert 'href="style.css">\n    <link rel="stylesheet" href="theme.css">' in index
    assert f'data-frame="{frame}"' in index
    assert 'data-rom="Jeu.gba"' in index
    theme = files["theme.css"].decode()
    assert "--player-color: #102030;" in theme
    assert "--page-color" not in theme
    assert "--button-border-width: 3px;" in theme
    assert "--player-shadow: none;" not in theme
    assert "style.css" in files and "custom.css" not in files
    # Jouable ouvert depuis le disque : ni module, ni fichier lu par fetch.
    assert 'type="module"' not in index
    assert index.index('src="rom.js"') < index.index('src="vendor/mgba.wasm.js"') < index.index('src="player.js"')
    assert "shaders/lcd.shader/manifest.ini" not in files
    assert '"lcd.shader/manifest.ini": "[shader]"' in files["player.js"].decode()
    assert files["vendor/mgba.wasm.js"].startswith(b'globalThis.BACKSTAGE_MGBA_WASM = "')
    assert "vendor/mgba.wasm" not in files and "main.js" not in files
    assert "vendor/mgba.js" in files and "LICENSE" in files


def test_le_contour_image_est_copie_et_verifie(tmp_path, template, rom):
    project = tmp_path / "project"
    (project / "web_theme").mkdir(parents=True)
    Image.new("RGBA", (544, 416)).save(project / "web_theme" / "cadre.png")
    settings = ProjectSettings(web_frame="image", web_frame_image="web_theme/cadre.png")
    files = _export(tmp_path, rom, settings)
    assert 'data-frame="image"' in files["index.html"].decode()
    assert '--frame-image: url("theme/frame.png");' in files["theme.css"].decode()
    assert "theme/frame.png" in files

    Image.new("RGBA", (300, 208)).save(project / "web_theme" / "cadre.png")
    with pytest.raises(WebTemplateError, match="272 x 208"):
        _export(tmp_path, rom, settings)


def test_custom_sans_ejection_prend_le_lecteur_vierge_et_le_champ_css(tmp_path, template, rom):
    settings = ProjectSettings(web_player_mode="custom", web_custom_css="body { color: red; }")
    files = _export(tmp_path, rom, settings)
    index = files["index.html"].decode()
    assert 'href="custom.css"' in index and 'href="style.css"' not in index
    assert files["custom.css"] == b"body { color: red; }"
    assert "style.css" not in files and "theme.css" not in files
    assert {"player.css", "player.js", "vendor/mgba.js", "vendor/mgba.wasm.js", "vendor/mgba.sdk.ts"} <= files.keys()


def test_custom_ejecte_garde_son_html_et_ignore_son_custom_css(tmp_path, template, rom):
    project = tmp_path / "project"
    eject_template(project / "web_template", "Jeu")
    ejected = project / "web_template"
    assert 'href="custom.css"' in (ejected / "index.html").read_text(encoding="utf-8")
    assert not (ejected / "style.css").exists()
    page = (ejected / "index.html").read_text(encoding="utf-8").replace("<main>", "<main><p>À moi</p>")
    (ejected / "index.html").write_text(page, encoding="utf-8")
    (ejected / "custom.css").write_text("perdu", encoding="utf-8")
    (ejected / "logo.png").write_bytes(b"PNG")

    settings = ProjectSettings(web_player_mode="custom", web_custom_css="p { margin: 0; }")
    files = _export(tmp_path, rom, settings)
    assert "<p>À moi</p>" in files["index.html"].decode()
    assert files["custom.css"] == b"p { margin: 0; }"
    assert files["logo.png"] == b"PNG"


def test_un_gabarit_ejecte_sans_marqueur_de_rom_est_refuse(tmp_path, template, rom):
    project = tmp_path / "project"
    eject_template(project / "web_template", "Jeu")
    (project / "web_template" / "index.html").write_text("<html></html>", encoding="utf-8")
    with pytest.raises(WebTemplateError, match="data-rom"):
        _export(tmp_path, rom, ProjectSettings(web_player_mode="custom"))


def test_les_modules_sont_reunis_dependances_d_abord(tmp_path):
    (tmp_path / "vendor").mkdir()
    sources = {
        "main.js": 'import { load, VERSION as version } from "./vendor/sdk.js";\nload(version);\n',
        "vendor/sdk.js": ('import { helper } from "./util.js";\nexport const VERSION = 2;\n'
                          "export async function load(v) { return helper(v, import.meta.url); }\n"
                          "export default { load };\n"),
        "vendor/util.js": "function helper(v, url) { return [v, url]; }\nexport { helper };\n",
    }
    for name, code in sources.items():
        (tmp_path / name).write_text(code, encoding="utf-8")
    bundle = web_build._bundle_modules({name: tmp_path / name for name in sources}, {})
    order = [bundle.index(f'modules["{name}"] = ') for name in ("vendor/util.js", "vendor/sdk.js", "main.js")]
    assert order == sorted(order)
    assert 'const { load, VERSION: version } = modules["vendor/sdk.js"];' in bundle
    assert "return { VERSION, load, default: moduleDefault };" in bundle
    assert 'new URL("vendor/sdk.js", playerUrl).href' in bundle
    assert "import " not in bundle and "export " not in bundle


def test_une_forme_d_import_inconnue_est_refusee(tmp_path):
    (tmp_path / "main.js").write_text('import sdk from "./sdk.js";\n', encoding="utf-8")
    with pytest.raises(WebTemplateError, match="unsupported import"):
        web_build._bundle_modules({"main.js": tmp_path / "main.js"}, {})


def test_project_json_n_ecrit_que_les_reglages_changes(tmp_path):
    project = Project(tmp_path)
    project.settings.web_player_mode = "custom"
    project.settings.web_accent_color = "#ff0000"
    project.save_settings()
    text = project.project_file.read_text(encoding="utf-8")
    assert '"web_accent_color"' in text and '"web_player_color"' not in text

    # Un ancien projet peut encore contenir la couleur de fond supprimée.
    project.project_file.write_text(text.replace("{", '{"web_page_color": "#abcdef",', 1),
                                    encoding="utf-8")
    project.settings.web_player_mode = "builtin"
    project.load_settings()
    assert project.settings.web_player_mode == "custom"
    assert project.settings.web_accent_color == "#ff0000"
    project.save_settings()
    assert '"web_page_color"' not in project.project_file.read_text(encoding="utf-8")


def test_le_lecteur_livre_contient_chaque_fichier_du_paquet():
    # Le dossier réel, pas le gabarit factice : un fichier oublié casserait chaque export.
    names = ("index.html",) + web_build._PLAYER_FILES + web_build._BUILTIN_FILES
    missing = [name for name in names if not (web_build.WEB_PLAYER_DIR / name).is_file()]
    assert not missing
    # Les vrais modules du lecteur passent par l'assemblage sans forme inconnue.
    modules = {name: web_build.WEB_PLAYER_DIR / name for name in names
               if name.endswith(".js") and name != "vendor/mgba.js"}
    assert 'modules["main.js"]' in web_build._bundle_modules(modules, {})
    build = (Path(__file__).resolve().parents[2] / "packaging" / "nuitka_build.py").read_text(encoding="utf-8")
    assert "'web_player'" in build


def test_les_valeurs_hors_domaine_reviennent_au_defaut():
    assert web_player_setting("web_player_color", "red; } body {") == "#171717"
    assert web_player_setting("web_player_color", "#ABCDEF") == "#abcdef"
    assert web_player_setting("web_player_mode", "html") == "builtin"
    assert web_player_setting("web_frame", "glow") == "backstage"
    assert web_player_setting("web_frame", "backstage-light") == "backstage-light"
    assert web_player_setting("web_button_border_width", 99) == 8
