"""ui/background_editor/bg_prepare_geometry.py — géométrie du recadrage et du
redimensionnement d'une source de fond.

Pur calcul, sans Qt : l'item graphique (bg_prepare_overlay) ne fait que tenir la
souris et dessiner, les règles de modificateurs vivent ici pour être testées.

Les deux gestes partagent la même grammaire :
  · Maj  = garder les proportions ;
  · Ctrl = accrocher à la grille 8×8 du matériel.
Ce que « proportions » désigne diffère : au redimensionnement, celles de l'image
au début du geste ; au recadrage, celles de l'image D'ORIGINE (on découpe un
morceau qui a la forme du tout).

Toutes les valeurs sont en pixels entiers de l'image concernée (la source pour
un recadrage, l'image préparée pour un redimensionnement).
"""
from __future__ import annotations

SNAP = 8
MIN_SIZE = 8


def _snap_coord(v: float) -> int:
    return int(round(v / SNAP)) * SNAP


def _snap_size(v: float) -> int:
    return max(SNAP, _snap_coord(v))


# ── Redimensionnement ─────────────────────────────────────────────────────────

def resize_target(w: int, h: int, handle: str, dx: float, dy: float,
                  shift: bool, ctrl: bool) -> tuple[int, int]:
    """Nouvelle taille (w, h) quand la poignée `handle` (un coin « nw »…, un bord
    « n », « e », « s », « w ») est tirée de (dx, dy) pixels. Tirer vers l'extérieur
    agrandit : le sens dépend du côté tenu — la gauche et le haut grandissent vers
    l'intérieur du repère, d'où le signe. Où l'image se pose ensuite est l'affaire
    de l'appelant (le côté opposé reste fixe)."""
    nw = float(w)
    nh = float(h)
    if "e" in handle:
        nw = max(1.0, w + dx)
    elif "w" in handle:
        nw = max(1.0, w - dx)
    if "s" in handle:
        nh = max(1.0, h + dy)
    elif "n" in handle:
        nh = max(1.0, h - dy)
    if shift:
        # Le côté tiré commande, l'autre suit ; à un coin, celui qui a le plus
        # changé en proportion.
        if handle in ("e", "w"):
            wide = True
        elif handle in ("n", "s"):
            wide = False
        else:
            wide = abs(nw / w - 1) >= abs(nh / h - 1)
        if wide:
            nw = _snap_size(nw) if ctrl else nw
            nh = nw * h / w
        else:
            nh = _snap_size(nh) if ctrl else nh
            nw = nh * w / h
    elif ctrl:
        nw, nh = _snap_size(nw), _snap_size(nh)
    return max(1, round(nw)), max(1, round(nh))


# ── Recadrage ─────────────────────────────────────────────────────────────────

def crop_target(rect: tuple, bounds: tuple, handle: str, dx: float, dy: float,
                shift: bool, ctrl: bool) -> tuple[int, int, int, int]:
    """Nouveau rectangle (gauche, haut, droite, bas) du recadrage. `rect` est le
    rectangle au début du geste, `bounds` = (largeur, hauteur) de la source ;
    `handle` : un coin ("nw"…), un bord ("n", "e", "s", "w") ou "move"."""
    l, t, r, b = rect
    bw, bh = bounds
    if handle == "move":
        w, h = r - l, b - t
        nl, nt = l + dx, t + dy
        if ctrl:
            nl, nt = _snap_coord(nl), _snap_coord(nt)
        nl = round(min(max(0, nl), bw - w))
        nt = round(min(max(0, nt), bh - h))
        return nl, nt, nl + w, nt + h

    if "w" in handle:
        l += dx
    if "e" in handle:
        r += dx
    if "n" in handle:
        t += dy
    if "s" in handle:
        b += dy
    if ctrl:
        if "w" in handle:
            l = _snap_coord(l)
        if "e" in handle:
            r = _snap_coord(r)
        if "n" in handle:
            t = _snap_coord(t)
        if "s" in handle:
            b = _snap_coord(b)
    mini = min(MIN_SIZE, bw, bh)
    if "w" in handle:
        l = min(max(0, l), r - mini)
    if "e" in handle:
        r = max(min(bw, r), l + mini)
    if "n" in handle:
        t = min(max(0, t), b - mini)
    if "s" in handle:
        b = max(min(bh, b), t + mini)
    if shift:
        l, t, r, b = _keep_aspect(l, t, r, b, handle, bw, bh, (rect[1] + rect[3]) / 2,
                                  (rect[0] + rect[2]) / 2)
    return round(l), round(t), round(r), round(b)


def _keep_aspect(l, t, r, b, handle, bw, bh, cy, cx):
    """Ramène le rectangle aux proportions de la source (bw : bh), sans sortir de
    l'image. `cx`/`cy` = centre du rectangle de départ, gardé sur l'axe que le
    geste ne commande pas (un bord tiré ne doit pas faire glisser l'autre côté)."""
    a = bw / bh
    w, h = r - l, b - t
    if len(handle) == 2:
        # Coin : le coin opposé est fixe, le rectangle pousse depuis lui.
        fx = r if "w" in handle else l
        fy = b if "n" in handle else t
        max_w = fx if "w" in handle else bw - fx
        max_h = fy if "n" in handle else bh - fy
        if w / a >= h:
            h = w / a
        else:
            w = h * a
        if w > max_w:
            w, h = max_w, max_w / a
        if h > max_h:
            w, h = max_h * a, max_h
        l, r = (fx - w, fx) if "w" in handle else (fx, fx + w)
        t, b = (fy - h, fy) if "n" in handle else (fy, fy + h)
        return l, t, r, b

    if handle in ("e", "w"):
        max_w = bw - l if handle == "e" else r
        w = min(w, max_w, bh * a)
        h = w / a
        l, r = (l, l + w) if handle == "e" else (r - w, r)
        t = min(max(0, cy - h / 2), bh - h)
        return l, t, r, t + h
    # "n" / "s"
    max_h = bh - t if handle == "s" else b
    h = min(h, max_h, bw / a)
    w = h * a
    t, b = (t, t + h) if handle == "s" else (b - h, b)
    l = min(max(0, cx - w / 2), bw - w)
    return l, t, l + w, b
