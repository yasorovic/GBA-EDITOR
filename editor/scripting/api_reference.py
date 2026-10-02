"""Loader pour api_reference.json — la PRÉSENTATION de l'API (groupes, ordre,
descriptions rédigées, exemples choisis).

`api.py` reste la source de vérité de ce qui EXISTE ; ce fichier ne décide que
de la mise en rayon. Les deux ont divergé en silence : le JSON proposait encore
`display.print`, `display.clear` et `text.draw_box`, retirées de l'API, tout en
ignorant `scene.switch`, `interface.draw_text` et douze autres. Un utilisateur cherchant
comment écrire du texte y trouvait donc trois fonctions mortes et pas la vivante.

D'où la réconciliation ci-dessous, faite à chaque chargement : le JSON est
FILTRÉ par le catalogue (une fonction retirée disparaît de l'écran) puis COMPLÉTÉ
par lui (une fonction ajoutée apparaît sans qu'on ait à toucher au JSON). Le
fichier peut donc rester incomplet ou en retard sans jamais mentir.
"""
from __future__ import annotations
import json
from pathlib import Path

from scripting.api import RUNTIME_API, RUNTIME_PROPS, REMOVED_API, canonical_key

from scripting import api_snippets
from ui.common.labels import label
from ui.common.tooltip import tooltip

_JSON_PATH = Path(__file__).parent / "api_reference.json"
_cache: list[dict] | None = None

# Renseignés par la réconciliation, à fin de diagnostic. Vides en régime normal.
STALE: list[str] = []      # décrit par le JSON, inconnu du catalogue
RELABELED: list[str] = []  # libellé du JSON permuté par rapport au catalogue

# Catégorie d'accueil des méthodes d'actor ajoutées au catalogue sans avoir été
# rangées à la main. Les `self:*` sont répartis entre plusieurs catégories
# (Mouvement, Animation, Position…), donc leur module ne suffit pas à déduire
# laquelle : on ne devine pas, on les regroupe visiblement.
_ACTOR_FALLBACK = "Actor"
_MISC_FALLBACK  = "Other"

# ─── `group` interne des catégories ─────────────────────────────────
# Étiquette héritée que chaque catégorie porte encore (dans le JSON, ou posée
# par les fallbacks ci-dessous). Elle ne pilote plus AUCUNE navigation depuis
# le rangement en 8 sections (ROADMAP v0.16) : les trois « grosses parties »
# Gameplay/Scripting/Hardware ont disparu de la sidebar, remplacées par une
# navigation unique par NOM (cf. `SECTIONS`). On garde le champ tel quel pour
# ne pas toucher au JSON — il n'a simplement plus de lecteur.
GROUP_GAMEPLAY  = "gameplay"
GROUP_LANGUAGE  = "language"
GROUP_HARDWARE  = "hardware"
_FALLBACK_GROUP: dict[str, str] = {
    _ACTOR_FALLBACK: GROUP_GAMEPLAY,
    _MISC_FALLBACK:  GROUP_GAMEPLAY,
}

# ─── Les 8 sections — une par CHOSE qu'on tient (ROADMAP v0.16) ──────
# La navigation de la sidebar. Chaque section absorbe plusieurs des 24
# catégories du catalogue, qui deviennent de simples SOUS-TITRES en son sein
# (`blend` reste `blend` pour qui le connaît, mais cesse d'être une porte
# d'entrée). L'ordre ici est l'ordre d'affichage ; une catégorie inconnue de
# cette table n'est jamais perdue — `get_sections` lui rend sa propre section
# en queue.
# Le premier terme est une CLÉ de label (résolue par l'UI : base anglaise dans
# labels.json, français dans labels_fr.json) — la sidebar traduit, cette couche
# ne code pas de texte visible en dur.
SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("scrsb.sec.actor",   ("Transform", "Movement", "Physics", "Collision", "Animation", "Juiciness", "Actor")),
    ("scrsb.sec.scenery", ("Layer", "Tilemap", "Palette", "Window", "Blend")),
    ("scrsb.sec.sound",   ("Audio",)),
    ("scrsb.sec.text_ui", ("Text", "Interface")),
    ("scrsb.sec.data",    ("Save", "Arrays")),
    ("scrsb.sec.script",  ("Math", "Sequences", "Debug")),
    ("scrsb.sec.scene",   ("Scene", "Camera", "Language")),
    ("scrsb.sec.player",  ("Input",)),
)

# ─── La couche MOTEUR — repliée sous « Aller plus loin » ────────────
# La frontière itération / moteur est une MARQUE sur l'entrée, pas une seconde
# navigation (ROADMAP v0.16) : dans chaque section, l'itération se montre, le
# moteur se replie. Elle est PLUS FINE que la catégorie — `sfx.play` est de
# l'itération, `sound_box.set_state` du moteur, alors qu'ils partagent « Audio »
# —, d'où une liste d'entrées et non de catégories. Curée à la main, comme
# `_PROP_HOME` : aucune règle ne la dérive, c'est un choix de mise en rayon.
# Tout ce qui n'y figure pas est de l'itération (le défaut, le cas courant).
_ENGINE_KEYS: frozenset[str] = frozenset({
    # Le décor : les registres avancés du matériel. Le calque garde sa face
    # simple (show/scroll/priority) ; seul le rebranchement de screenblock est
    # moteur. Fenêtre et mélange sont du pur pochoir/BLDCNT.
    "background_layer.map",
    "window.get", "window_region:show", "window_region:hide", "window_region.visible",
    "window_region:set", "window_region:set_layer", "window_region:get_layer",
    "window_region:set_obj", "window_region:set_blend",
    "blend.set_layer", "blend.set_obj", "blend.set_backdrop",
    "blend.set_alpha", "blend.set_fade", "blend.mode",
    # Le son : les trois boîtes (états, déclencheurs). `sfx`/`music` restent
    # l'itération.
    "sound_box.set_state", "sound_box.set_volume",
    "jingle_box.set_state", "jingle_box.set_volume",
    "music_box.trigger",
    # L'interface : le module moteur nommé par la ROADMAP. `text.*` (afficher un
    # texte ponctuel) reste l'itération ; les zones nommées, images et listes
    # sont le moteur.
    "interface.get", "ui_element:show", "ui_element:hide", "ui_element.visible",
    "list:row", "list:activate", "list:deactivate",
    "list.count", "list.index", "list.first", "list.active",
    "image:play", "image:pause", "image.state", "image.offset",
    "text_region:draw", "text_region:clear", "text_region:skip", "text_region.reading",
})

# Où ranger les PROPRIÉTÉS (RUNTIME_PROPS) : contrairement aux fonctions, un
# module (`self`) ne suffit pas à dire la catégorie — self.position est du
# Transform, self.velocity de la Physics. Une petite table à jour à la main,
# le JSON restant lui completé automatiquement (cf. `_reconcile`).
_PROP_HOME: dict[str, str] = {
    "actor.position":  "Transform",
    "actor.rotation":  "Transform",
    "actor.scale":     "Transform",
    "actor.velocity":  "Physics",
    "actor.visible":   "Actor",
    "actor.active":    "Actor",
    "actor.tag":       "Actor",
    "actor.frame":     "Animation",
    "actor.anim":      "Animation",
    "actor.active_sprite": "Animation",
    "actor.anim_speed":    "Animation",
    "actor.anim_length":   "Animation",
    "actor.anim_loop":     "Animation",
    "actor.anim_finished": "Animation",
    "actor.frame_w":   "Animation",
    "actor.frame_h":   "Animation",
    "actor.flip_h":    "Animation",
    "actor.flip_v":    "Animation",
    "actor.pal":       "Animation",
    "actor.obj_mode":  "Animation",
    "actor.priority":  "Animation",
    "actor.sprite_rotation": "Animation",
    "actor.sprite_scale":    "Animation",
    "actor.sprite_offset":   "Animation",
    "actor.direction": "Movement",
    "actor.auto_dir":  "Movement",
    "actor.grounded":  "Collision",
    "actor.box_count": "Collision",
    "ui_element.visible": "Interface",
    "background_layer.visible": "Layer", "background_layer.priority": "Layer",
    "background_layer.scroll": "Layer", "background_layer.map": "Layer",
    "background_layer.scroll_speed": "Layer", "background_layer.pal_bank": "Layer",
    "window_region.visible": "Window",
    "list.count": "Interface", "list.index": "Interface",
    "list.first": "Interface", "list.active": "Interface",
    "image.state": "Interface", "image.offset": "Interface",
    "text_region.reading": "Interface",
    "collision_box.tag":    "Collision",
    "collision_box.active": "Collision",
    "collision_box.solid":  "Collision",
    "collision_box.is_grounded": "Collision",
    "collision_box.offset": "Collision",
    "collision_box.size":   "Collision",
    "collision_box.bounds": "Collision",
    "actor.screen_space": "Actor",
    "actor.affine":    "Animation",
    "camera.position": "Camera",
    "camera.bound":    "Camera",
    "camera.margin":   "Camera",
    "camera.frame":    "Camera",
    "camera.name":     "Camera",
    "scene.size":      "Scene",
    "scene.frame":     "Scene",
    "scene.scroll_h":  "Scene",
    "scene.scroll_v":  "Scene",
    "scene.collision_layer": "Scene",
    "input.axis":      "Input",
    "blend.mode":      "Blend",
}

# Même chose pour les FONCTIONS `self:*` et celles d'une RÉFÉRENCE
# (`collision_box:*`) : leur module (`self`, ou aucun) ne dit pas la catégorie,
# donc `_reconcile` ne peut pas déduire où en ranger une nouvelle et la jetterait
# dans « Actor » ou « Other ». Ne figurent ici que celles à ranger ailleurs ; le
# reste est décrit par le JSON.
_FUNC_HOME: dict[str, str] = {
    "actor:collision_box":     "Collision",
    "collision_box:overlaps": "Collision",
    "layer.get": "Layer", "window.get": "Window",
    "background_layer:show": "Layer", "background_layer:hide": "Layer",

    "background_layer:scroll_by": "Layer",
    "background_layer:set_tile": "Tilemap", "background_layer:get_tile": "Tilemap",
    "background_layer:set_tile_palette": "Tilemap", "background_layer:set_tile_flip": "Tilemap",
    "background_layer:fill": "Tilemap",
    "window_region:show": "Window", "window_region:hide": "Window", "window_region:set": "Window",
    "window_region:set_layer": "Window", "window_region:get_layer": "Window",
    "window_region:set_obj": "Window", "window_region:set_blend": "Window",
    "collision_box:activate": "Collision",

    "collision_box:deactivate": "Collision",
    "list:row": "Interface", "list:activate": "Interface", "list:deactivate": "Interface",
    "image:play": "Interface", "image:pause": "Interface",
    "text_region:draw": "Interface", "text_region:clear": "Interface",
    "text_region:skip": "Interface",
    "collision_box:get_collision_tile": "Collision",
}


def _module_of(name: str) -> str:
    """`interface.draw_text` → `interface` ; `self:move` → `self` ; `array` → ``."""
    if name.startswith("actor:"):
        return "self"
    return name.split(".")[0] if "." in name else ""


def _label_params(label: str) -> list[str]:
    """Noms de paramètres lus dans un libellé, guillemets retirés —
    `actor:get("name")` → `["name"]`."""
    inner = label[label.find("(") + 1:label.rfind(")")]
    return [a.strip().strip('"').strip() for a in inner.split(",")] if inner.strip() else []


def _fix_permuted(entry: dict, name: str) -> dict:
    """Regénère libellé et snippet quand le JSON décrit les MÊMES paramètres
    dans un AUTRE ORDRE que le catalogue.

    Restreint aux permutations, volontairement. Un réordonnancement rend le
    libellé faux — il enseignerait une signature que le compilateur rejette. Un
    simple renommage de paramètre (`n` devenu `frame`) reste juste sur le fond,
    et écraser à cette occasion un libellé rédigé à la main coûterait ses
    exemples choisis (`self.frame = 0` valant mieux que `self.frame = frame`).

    Description et tableau de paramètres sont conservés : c'est la prose de ce
    fichier, elle n'est pas concernée par l'ordre."""
    f = RUNTIME_API.get(name)
    if f is None:
        return entry
    cat = [p.name for p in f.params] + (["..."] if f.variadic else [])
    lab = _label_params(entry.get("label", ""))
    if lab == cat or sorted(lab) != sorted(cat):
        return entry
    RELABELED.append(name)
    gen = api_snippets.entry_dict(name)
    return {**entry, "label": gen["label"], "snippet": gen["snippet"]}


def _mark_layer(entry: dict, name: str) -> dict:
    """Pose `engine` sur une entrée : vrai pour la couche moteur (`_ENGINE_KEYS`),
    faux pour l'itération (le défaut). `name` est la clé API — le préfixe du
    libellé pour une fonction, la clé pointée pour une propriété (`blend.mode`)."""
    entry["engine"] = name in _ENGINE_KEYS
    # L'ancre se dérive de la CLÉ du catalogue : le JSON écrit `self:move_to`, le catalogue
    # `actor:move_to`, et l'ancre suit le catalogue.
    entry["doc_anchor"] = name.replace(":", "-").replace(".", "-")

    # Le snippet vient TOUJOURS du catalogue : ce que le JSON en dit (un exemple
    # écrit à la main, `actor:spawn("Bullet", vec2(116, 76))`) n'est plus inséré.
    entry["snippet"] = api_snippets.bare(name)
    return entry


def _reconcile(cats: list[dict]) -> list[dict]:
    STALE.clear()
    RELABELED.clear()
    out: list[dict] = []
    described: set[str] = set()
    # Où vit déjà chaque module — c'est ce qui range une fonction ajoutée sans
    # table de correspondance à maintenir. Un module présent dans plusieurs
    # catégories est ambigu : on ne tranche pas à sa place.
    homes: dict[str, set[str]] = {}

    for cat in cats:
        kept = []
        for entry in cat.get("entries", []):
            # Le libellé montre la forme ÉCRITE (`input:pressed`) ; le catalogue est indexé par
            # sa clé (`input.pressed`).
            name = canonical_key(entry.get("label", "").split("(")[0].strip())
            # Le rangement s'apprend de TOUTES les entrées, y compris périmées :
            # un `scene.frame()` mort dit encore que le module `scene` habite
            # « Scène ». Ne l'apprendre que des survivantes envoyait
            # `scene.switch` dans « Other » le jour où la catégorie ne gardait
            # que des entrées retirées.
            homes.setdefault(_module_of(name), set()).add(cat["name"])
            if name in REMOVED_API or name not in RUNTIME_API:
                STALE.append(name)
                continue
            kept.append(_mark_layer(_fix_permuted(entry, name), name))
            described.add(name)
        # La catégorie garde sa PLACE même vidée : c'est le JSON qui décide de
        # l'ordre, et le filtre ne doit pas réordonner l'écran. Les propriétés
        # la remplissent souvent juste après (« Transform » n'a plus que
        # celles-là) ; celles qui restent vides sont retirées à la toute fin.
        out.append({**cat, "entries": kept})

    by_name = {c["name"]: c for c in out}
    for name in RUNTIME_API:
        if name in described:
            continue
        candidates = homes.get(_module_of(name), set())
        target = (_FUNC_HOME[name] if name in _FUNC_HOME
                  else next(iter(candidates)) if len(candidates) == 1
                  else _ACTOR_FALLBACK if name.startswith("actor:")
                  else _MISC_FALLBACK)
        cat = by_name.get(target)
        if cat is None:
            cat = {"name": target, "group": _FALLBACK_GROUP.get(target, GROUP_GAMEPLAY), "entries": []}
            by_name[target] = cat
            out.append(cat)
        cat["entries"].append(_mark_layer(api_snippets.entry_dict(name), name))

    # Les PROPRIÉTÉS n'ont pas de libellé de fonction : le filtre STALE ne les
    # voit pas, et la boucle ci-dessus ne les voit pas non plus — on les ajoute
    # à part, rangées par `_PROP_HOME`.
    for name in RUNTIME_PROPS:
        target = _PROP_HOME.get(name, _MISC_FALLBACK)
        cat = by_name.get(target)
        if cat is None:
            cat = {"name": target, "group": _FALLBACK_GROUP.get(target, GROUP_GAMEPLAY), "entries": []}
            by_name[target] = cat
            out.append(cat)
        cat["entries"].append(_mark_layer(api_snippets.prop_entry_dict(name), name))

    # Un en-tête sans rien dessous n'apprend rien : les catégories que ni le
    # catalogue ni les propriétés n'ont remplies disparaissent — après, pour
    # n'avoir pas coûté leur place à celles qui se remplissent.
    return [c for c in out if c["entries"]]


def get_categories() -> list[dict]:
    """Catégories de la section API, réconciliées avec `RUNTIME_API` (en cache)."""
    global _cache
    if _cache is None:
        raw = json.loads(_JSON_PATH.read_text(encoding="utf-8")).get("categories", [])
        _cache = _reconcile(raw)
    return _cache


def get_sections() -> list[dict]:
    """`get_categories()`, regroupée en 8 sections (ROADMAP v0.16) — la
    navigation de la sidebar.

    Rend, dans l'ordre de `SECTIONS`, une liste de
    `{"label", "iteration", "engine"}`. `iteration` et `engine` sont chacune une
    liste de sous-groupes `{"name", "entries"}` : le NOM est l'ancienne catégorie
    (un SOUS-TITRE, plus une porte), et une même catégorie peut apparaître des
    deux côtés (le calque a une face simple et une face avancée). `engine` est ce
    qui se replie sous « Aller plus loin » ; `iteration` se montre.

    Une catégorie hors de `SECTIONS` n'est jamais perdue : elle rend sa propre
    section en queue — même garantie que `_reconcile`, rien ne disparaît en
    silence."""
    cats = {c["name"]: c for c in get_categories()}

    def split(cat: dict) -> tuple[list[dict], list[dict]]:
        it = [e for e in cat["entries"] if not e.get("engine")]
        en = [e for e in cat["entries"] if e.get("engine")]
        return it, en

    used: set[str] = set()
    out: list[dict] = []
    for label_, cat_names in SECTIONS:
        iteration, engine = [], []
        for cname in cat_names:
            cat = cats.get(cname)
            if cat is None:
                continue
            used.add(cname)
            it, en = split(cat)
            if it:
                iteration.append({"name": cname, "entries": it})
            if en:
                engine.append({"name": cname, "entries": en})
        if iteration or engine:
            out.append({"label": label_, "iteration": iteration, "engine": engine})

    for cname, cat in cats.items():
        if cname in used:
            continue
        it, en = split(cat)
        out.append({
            "label": cname,
            "iteration": [{"name": cname, "entries": it}] if it else [],
            "engine":    [{"name": cname, "entries": en}] if en else [],
        })
    return out


def make_tooltip(entry: dict) -> str:
    """Génère une aide brève pour une entrée API à insérer."""
    sig    = entry.get("label", "")
    desc   = entry.get("description", "")
    ret    = entry.get("returns", "")
    access = entry.get("access", "")  # "Read Only" / "Read and Write" — propriétés seulement
    return tooltip(title=sig, body=desc, note=access or ret)
