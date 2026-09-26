"""scripting/project_names.py — l'univers des noms du projet, par domaine.

« Quel nom un argument de ce domaine peut-il porter ? » — `sfx:play("…")` prend un
nom de Sfx, `scene:switch("…")` un nom de scène. La réponse vivait en DOUBLE :
inline dans `sidebar_panel.set_project` (pour les boutons de la sidebar) et dans
`lua_compiler` (pour le `BuildContext` du checker). Cette fonction en est la source
unique — la sidebar la lit pour ses boutons, et l'autocomplétion pour ne proposer
QUE ce que le checker accepte (ROADMAP v0.27, phase 3).

Le projet est DUCK-TYPÉ : ses collections se lisent par `getattr`, sans importer
`Project`. Un projet sans telle famille rend simplement une liste vide — le
domaine correspondant est alors absent, et la complétion n'y propose rien, comme
pour un enum matériel vide.
"""
from __future__ import annotations

from scripting.api import (
    DOMAIN_SCENE, DOMAIN_CAMERA, DOMAIN_SFX, DOMAIN_MUSIC, DOMAIN_PREFAB,
    DOMAIN_FONT, DOMAIN_PALETTE, DOMAIN_TEXT, DOMAIN_LANG, DOMAIN_ACTOR,
    DOMAIN_UI_ELEMENT, DOMAIN_GLOBAL, REF_TYPE_TABLE,
    DOMAIN_SOUND_BOX_STATE, DOMAIN_JINGLE_BOX_STATE, DOMAIN_MUSIC_BOX_TRIGGER,
    DOMAIN_KEY, DOMAIN_WIN_REGION, WIN_REGIONS, DOMAIN_BOX_TAG,
)
from core.models.settings import BUTTON_NAMES


def _names(items) -> list[str]:
    return [n for n in (getattr(it, "name", None) for it in (items or [])) if n]


def ui_ref_kinds(project) -> dict[str, str]:
    """{nom d'élément d'interface → type de référence} : ce que `interface:get(nom)` rend.

    La NATURE d'un élément (`UILayout` : liste, image, zone de texte, conteneur) se lit
    dans la mise en page, et la table de types (`REF_TYPE_TABLE`) dit quel type la
    porte — ni l'une ni l'autre n'est réécrite ici. Un `kind` que la table ne connaît
    pas retombe sur le type de base : il garde au moins son cycle de vie."""
    by_kind = {t.ui_kind: name for name, t in REF_TYPE_TABLE.items() if t.ui_kind}
    base = next(name for name, t in REF_TYPE_TABLE.items() if t.ui_kind and not t.base)
    all_elements = getattr(project, "all_elements", None)
    return {el.name: by_kind.get(getattr(el, "kind", ""), base)
            for _lay, el in (all_elements() if all_elements else [])}


def data_column_kinds(project) -> dict[str, str]:
    """{`data.Table.colonne` → type de référence} pour les colonnes de données qui stockent le
    handle d'un type (`RefType.column` : `region` → `text_region`, `image` → `image`).

    Le build range dans ces colonnes l'INDEX de la zone ou de l'image — exactement la valeur du
    type —, donc `data.Dialogue[i].boite:draw("…")` se juge et se traduit comme
    `interface:get("boite"):draw("…")`, sans nom d'élément à citer. Les clés se fabriquent par
    `expr_types.data_column_key`, le même chemin que celui qui les lira."""
    from scripting.expr_types import data_column_key
    by_column = {t.column: name for name, t in REF_TYPE_TABLE.items() if t.column}
    return {data_column_key(table.name, col.name): by_column[col.type]
            for table in (getattr(project, "data_tables", None) or [])
            for col in table.columns if col.type in by_column}


def names_by_domain(project, scene=None) -> dict[str, list[str]]:

    """{domaine → noms valides}, pour ce projet (et sa scène active, ou `scene`
    si fournie). Les domaines vides sont OMIS.

    Les domaines PROPRES AU SCRIPT (`sequence` — les `on_sequence_*` du fichier)
    ou À L'ACTEUR (`anim` — les animations du sprite qui porte le script), et
    ceux qui dépendent d'un AUTRE argument (`image_state`), n'y sont pas : ils ne
    se dérivent pas du seul projet. La complétion les traitera à leur source."""
    if project is None:
        return {}

    def has(name):
        return getattr(project, name, None)

    out: dict[str, list[str]] = {
        DOMAIN_SCENE:   _names(has("scenes")),
        DOMAIN_SFX:     _names(has("sfx")),
        DOMAIN_MUSIC:   _names(has("music")),
        DOMAIN_PREFAB:  _names(has("prefabs")),
        DOMAIN_FONT:    _names(has("fonts")),
        DOMAIN_PALETTE: _names(has("palettes")),
        DOMAIN_GLOBAL:  _names(has("globals")),
        # `const.nom` est un accès pointé aux constantes du projet, comme
        # `global.nom` aux variables — pas un domaine d'argument (il n'y a pas de
        # `DOMAIN_CONST`), mais l'autocomplétion des membres le lit ici, sous la
        # clé qui EST le qualificateur écrit (`const`).
        "const":        _names(has("constants")),
        # Boutons matériels + actions déclarées par le projet.
        DOMAIN_KEY:     list(BUTTON_NAMES) + _names(getattr(has("settings"), "inputs", [])),
    }

    # Textes : la CLÉ, pas le nom — et `build_texts()` plutôt que `texts`, pour
    # que les littéraux de `text.draw` (entrées anonymes) comptent aussi, comme
    # côté build.
    texts = project.build_texts() if hasattr(project, "build_texts") else (has("texts") or [])
    out[DOMAIN_TEXT] = [t.key for t in texts if getattr(t, "key", None)]

    # Caméras et fenêtres : des méthodes, pas des collections d'objets.
    if hasattr(project, "camera_names"):
        out[DOMAIN_CAMERA] = sorted(project.camera_names())
    if hasattr(project, "collision_tags"):
        out[DOMAIN_BOX_TAG] = list(project.collision_tags())
    windows = sorted(project.window_names()) if hasattr(project, "window_names") else []
    out[DOMAIN_WIN_REGION] = list(WIN_REGIONS) + windows

    # Langues déclarées (source + `settings.languages`).
    settings = has("settings")
    if settings is not None and hasattr(settings, "all_languages"):
        out[DOMAIN_LANG] = [l.code for l in settings.all_languages()]

    # Interfaces — toutes mises en page confondues.
    if hasattr(project, "ui_element_names"):
        out[DOMAIN_UI_ELEMENT] = list(project.ui_element_names())

    # Boîtes sonores — l'import du modèle est celui que le checker fait déjà.
    if hasattr(project, "sound_state_names"):
        from core.models.sound_box import KIND_SOUND, KIND_JINGLE
        out[DOMAIN_SOUND_BOX_STATE]  = list(project.sound_state_names(KIND_SOUND))
        out[DOMAIN_JINGLE_BOX_STATE] = list(project.sound_state_names(KIND_JINGLE))
    if hasattr(project, "sound_trigger_names"):
        out[DOMAIN_MUSIC_BOX_TRIGGER] = list(project.sound_trigger_names())

    # Acteurs : ceux de la scène ACTIVE (comme la sidebar et le checker) — une
    # référence à un acteur d'une AUTRE scène n'a pas de cible où on écrit.
    sc = scene if scene is not None else has("active_scene")
    if sc is not None:
        out[DOMAIN_ACTOR] = _names(getattr(sc, "actors", []))

    return {dom: names for dom, names in out.items() if names}
