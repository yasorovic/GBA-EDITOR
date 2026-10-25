"""Coloration syntaxique du site : les couleurs d'accent de la palette, sur un fond gris.

Deux styles, un par thème, qui n'emploient que des couleurs de la palette :
- `BackstageStyle` (thème sombre) : fond `#171717`, où le turquoise, l'orange et le jaune sont lisibles (5 à 12:1) ;
  le violet, le rouge et le bleu, trop sombres pour du petit texte, n'y servent pas.
- `BackstageLightStyle` (thème clair) : fond `#f0f0f0`, où seuls le violet, le bleu et le rouge ont assez de
  contraste (environ 4:1) ; le turquoise, l'orange et le jaune y seraient illisibles.
"""
from pygments.style import Style
from pygments.token import (Comment, Error, Generic, Keyword, Name, Number, Operator, Punctuation, String,
                            Token)

TEXT = "#d4d4d4"
TEAL = "#2faeb4"
ORANGE = "#f29a25"
YELLOW = "#e7d642"
RED = "#f23325"
PURPLE = "#aa50b4"
BLUE = "#2f6bb4"


class BackstageStyle(Style):
    name = "backstage"
    background_color = "#171717"
    highlight_color = "#2b2b2b"
    default_style = ""

    styles = {
        Token: TEXT,
        Comment: "#8a8a8a",
        Comment.Preproc: TEAL,
        Keyword: TEAL,
        Name.Builtin: TEAL,
        Name.Function: f"bold {TEXT}",
        String: ORANGE,
        Number: YELLOW,
        Operator: TEXT,
        Punctuation: TEXT,
        Generic.Deleted: RED,
        Generic.Error: RED,
        Generic.Strong: "bold",
        Generic.Emph: "italic",
        Error: RED,
    }


class BackstageLightStyle(Style):
    name = "backstage-light"
    background_color = "#f0f0f0"
    highlight_color = "#dcdcdc"
    default_style = ""

    styles = {
        Token: "#1a1a1a",
        Comment: "#686868",
        Comment.Preproc: PURPLE,
        Keyword: PURPLE,
        Name.Builtin: PURPLE,
        Name.Function: "bold #1a1a1a",
        String: BLUE,
        Number: RED,
        Operator: "#1a1a1a",
        Punctuation: "#1a1a1a",
        Generic.Deleted: RED,
        Generic.Error: RED,
        Generic.Strong: "bold",
        Generic.Emph: "italic",
        Error: RED,
    }
