"""Documentation utilisateur : Markdown lu directement par Sphinx via MyST."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

project = "Backstage"
author = "Victor Rosay"
language = "fr"

extensions = ["myst_parser", "sphinx_design", "sphinx_copybutton"]

# Blocs de code : un style par thème, sur un fond gris (voir _gen/backstage_style.py).
pygments_style = "_gen.backstage_style.BackstageLightStyle"
pygments_dark_style = "_gen.backstage_style.BackstageStyle"
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["__pycache__", "_build", "_gen", "Thumbs.db", ".DS_Store"]
myst_enable_extensions = ["colon_fence", "attrs_inline"]
myst_heading_anchors = 3

html_theme = "furo"
html_title = "Documentation de Backstage"
html_permalinks_icon = "🔗"
html_favicon = "assets/backstage-icon.svg"
# `_gen_static` reçoit l'index de recherche des fonctions, écrit par `_gen/lua_api.py` ; il doit exister avant la validation de la config.
(Path(__file__).resolve().parent / "_gen_static").mkdir(exist_ok=True)
html_static_path = ["assets", "stylesheets", "scripts", "_gen_static"]
html_css_files = ["backstage.css"]
html_js_files = [("lua-search.js", {"defer": "defer"}), ("toc-spy.js", {"defer": "defer"}), ("download-links.js", {"defer": "defer"}), ("image-zoom.js", {"defer": "defer"})]
# Couleurs d'accentuation (palette de la marque, jamais pour les fonds). Le jaune du schéma sert au logo, pas ici.
_ACCENTS = {
    "purple": (170, 80, 180),
    "red": (242, 51, 37),
    "orange": (242, 154, 37),
    "blue": (47, 107, 180),
    "teal": (47, 174, 180),
}
_ADMONITION_ACCENT = {
    "note": "blue", "seealso": "blue",
    "hint": "teal", "tip": "teal",
    "important": "purple",
    "attention": "red", "danger": "red", "error": "red",
    "caution": "orange", "warning": "orange",
}
_ADMONITIONS = {}
for _kind, _color in _ADMONITION_ACCENT.items():
    _r, _g, _b = _ACCENTS[_color]
    _ADMONITIONS[f"color-admonition-title--{_kind}"] = f"#{_r:02x}{_g:02x}{_b:02x}"
    _ADMONITIONS[f"color-admonition-title-background--{_kind}"] = f"rgba({_r}, {_g}, {_b}, 0.15)"
_ADMONITIONS["color-admonition-title"] = "#aa50b4"
_ADMONITIONS["color-admonition-title-background"] = "rgba(170, 80, 180, 0.15)"

html_theme_options = {
    "light_logo": "backstage-logo-documentation.svg",
    "dark_logo": "backstage-logo-documentation-white.svg",
    "sidebar_hide_name": True,
    "light_css_variables": {
        "color-brand-primary": "#aa50b4",
        "color-brand-content": "#aa50b4",
        "color-sidebar-link-text--top-level": "var(--color-foreground-primary)",
        **_ADMONITIONS,
    },
    "dark_css_variables": {
        # Le violet n'atteint que 3,6:1 sur ce fond (4,3:1 au mieux, sur du noir pur) : le texte accentué passe au
        # jaune de la palette (11,2:1), sans teinte inventée. Les remplissages gardent le violet.
        "color-brand-primary": "#e7d642",
        "color-brand-content": "#e7d642",
        "color-sidebar-link-text--top-level": "var(--color-foreground-primary)",
        "color-background-primary": "#1e1e1e",
        "color-background-secondary": "#171717",
        "color-background-border": "#383838",
        "color-foreground-primary": "#d4d4d4",
        "color-foreground-secondary": "#ababab",
        **_ADMONITIONS,
    },
}
html_show_sourcelink = False
html_show_copyright = False
html_show_sphinx = False


def setup(app):
    from _gen.lua_api import generate

    app.connect("builder-inited", lambda _app: generate())
