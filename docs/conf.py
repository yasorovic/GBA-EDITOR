"""Documentation utilisateur : Markdown lu directement par Sphinx via MyST."""

project = "Backstage"
author = "Victor Rosay"
language = "fr"

extensions = ["myst_parser"]
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["__pycache__", "_build", "Thumbs.db", ".DS_Store"]
myst_enable_extensions = ["colon_fence", "attrs_inline"]
myst_heading_anchors = 3

html_theme = "furo"
html_title = "Documentation de Backstage"
html_permalinks_icon = "🔗"
html_favicon = "assets/backstage-icon.svg"
html_static_path = ["assets", "stylesheets"]
html_css_files = ["backstage.css"]
html_theme_options = {
    "light_logo": "backstage-logo.svg",
    "dark_logo": "backstage-logo-white.svg",
    "sidebar_hide_name": True,
    "light_css_variables": {
        "color-brand-primary": "#8b3a95",
        "color-brand-content": "#8b3a95",
    },
    "dark_css_variables": {
        "color-brand-primary": "#d08ad8",
        "color-brand-content": "#d08ad8",
        "color-background-primary": "#111111",
        "color-background-secondary": "#171717",
        "color-background-border": "#383838",
        "color-foreground-primary": "#d4d4d4",
        "color-foreground-secondary": "#ababab",
    },
}
html_show_sourcelink = False
html_show_copyright = False
html_show_sphinx = False
