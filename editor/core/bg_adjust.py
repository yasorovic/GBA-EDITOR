"""core/bg_adjust.py — teinte, saturation, luminosité, contraste d'une image PIL, avant la compression.

Une image INDEXÉE (mode 'P') est réglée par sa PALETTE : les index des pixels ne bougent pas, la palette d'auteur reste
l'autorité (le chemin « indexé direct » de `core.bg_import` s'applique donc toujours). Une image en couleurs directes est
réglée pixel par pixel, son canal alpha intact. Le fichier source n'est jamais touché."""
from __future__ import annotations

from PIL import Image, ImageEnhance


def _adjust_rgb(rgb: Image.Image, adjust) -> Image.Image:
    if adjust.hue:
        h, s, v = rgb.convert("HSV").split()
        shift = round(adjust.hue * 256 / 360)
        h = h.point([(i + shift) % 256 for i in range(256)])
        rgb = Image.merge("HSV", (h, s, v)).convert("RGB")
    if adjust.saturation:
        rgb = ImageEnhance.Color(rgb).enhance(1 + adjust.saturation / 100)
    if adjust.brightness:
        rgb = ImageEnhance.Brightness(rgb).enhance(1 + adjust.brightness / 100)
    if adjust.contrast:
        rgb = ImageEnhance.Contrast(rgb).enhance(1 + adjust.contrast / 100)
    return rgb


def apply_adjust(img: Image.Image, adjust) -> Image.Image:
    """L'image réglée ; `img` elle-même si `adjust` est neutre (ou absent)."""
    if adjust is None or adjust.is_default():
        return img
    if img.mode in ("P", "PA"):
        palette = img.getpalette() or []
        count = len(palette) // 3
        if count:
            strip = Image.new("RGB", (count, 1))
            strip.putdata(list(zip(palette[0::3], palette[1::3], palette[2::3])))
            flat = [c for pixel in _adjust_rgb(strip, adjust).getdata() for c in pixel]
            out = img.copy()
            out.putpalette(flat + palette[len(flat):])
            return out
    alpha = img.getchannel("A") if img.mode in ("RGBA", "LA", "PA") else None
    out = _adjust_rgb(img.convert("RGB"), adjust)
    if alpha is not None:
        out.putalpha(alpha)
    return out
