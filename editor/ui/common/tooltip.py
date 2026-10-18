"""Composition des infobulles de l'éditeur.

Le catalogue ne contient que du texte traduisible. Ce module rend la structure
commune : titre, raccourci, précision en italique et avertissement léger.
"""
from __future__ import annotations

from html import escape
import re


TOOLTIP_WAKEUP_MS = 600
TOOLTIP_DURATION_MS = 10000
TOOLTIP_MAX_WIDTH = 420

_RICH_TAG = re.compile(
    r"<\s*/?\s*(?:qt|html|body|p|br|b|strong|i|em|span|div|table|tr|td|"
    r"ul|ol|li|pre|code|a|font|h[1-6])\b[^>]*>", re.IGNORECASE)


def tooltip_html(text: str) -> str:
    """Keep composed rich tips; preserve line breaks in ordinary widget/item tips."""
    if _RICH_TAG.search(text):
        return text
    return escape(text).replace("\n", "<br>")


def tooltip(*, title: str, body: str = "", shortcut: str = "", note: str = "",
            warning: str = "") -> str:
    """Construit une infobulle riche sans exposer de HTML aux traductions.

    Avec un raccourci, l'en-tête devient « raccourci en gras | effet en italique » ;
    sans raccourci, le titre est en gras.
    Les précisions et avertissements restent visuellement secondaires.
    """
    def text(value: str) -> str:
        return escape(value).replace("\n", "<br>")

    if shortcut:
        header = f"<b>{text(shortcut)}</b> | <i>{text(title)}</i>"
    else:
        header = f"<b>{text(title)}</b>"

    lines = [header]
    if body:
        lines.append(text(body))
    if note:
        lines.append(f"<i>{text(note)}</i>")
    if warning:
        lines.append(f"⚠ <i>{text(warning)}</i>")
    return "<br>".join(lines)
