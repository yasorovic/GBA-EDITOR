"""Génère les pages Markdown de la section Lua API à partir du catalogue de l'éditeur.

La source est `scripting.api_reference.get_sections()`, la même fonction que lit le panneau API de
l'éditeur : le site et le panneau ne peuvent pas diverger. Les fiches sont publiées telles quelles
(en anglais). Les pages vont sous `docs/lua-api/api/`, ignoré par git, et sont réécrites à chaque build.

Arborescence produite :

    api/index.md                      le glossaire : les groupes de fonctions, en cartes, par section
    api/<section>/index.md            une section et ses groupes
    api/<section>/<groupe>.md         un groupe : tableau récapitulatif, puis une fiche par fonction
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = DOCS_DIR.parent
EDITOR_DIR = REPO_DIR / "editor"
OUT_DIR = DOCS_DIR / "lua-api" / "api"
LABELS_FR = EDITOR_DIR / "ui" / "common" / "labels" / "labels_fr.json"
GROUP_DESCRIPTIONS = Path(__file__).resolve().parent / "group_descriptions.json"
SECTION_DESCRIPTIONS = Path(__file__).resolve().parent / "section_descriptions.json"
GROUP_DEFINITIONS = Path(__file__).resolve().parent / "group_definitions.json"
# Lu par le script de recherche (docs/scripts/lua-search.js) ; copié dans `_static/` par Sphinx, ignoré par git.
INDEX_PATH = DOCS_DIR / "_gen_static" / "lua-api-index.json"

_SECTION_PREFIX = "scrsb.sec."
# Une couleur d'accent de la palette par section, dans l'ordre d'affichage (classes `backstage-card-<couleur>`).
_SECTION_COLORS = ("purple", "blue", "teal", "orange", "red", "yellow")
_SUMMARY_LIMIT = 140


def _section_titles() -> dict[str, str]:
    """Titres français des sections, lus dans le catalogue de libellés de l'éditeur."""
    data = json.loads(LABELS_FR.read_text(encoding="utf-8"))
    for group in data.values():
        if isinstance(group, dict) and any(k.startswith(_SECTION_PREFIX) for k in group):
            return {k: v["text"] for k, v in group.items() if k.startswith(_SECTION_PREFIX)}
    raise RuntimeError(f"No '{_SECTION_PREFIX}*' labels found in {LABELS_FR}")


def _section_slug(section_key: str) -> str:
    return section_key.removeprefix(_SECTION_PREFIX).replace("_", "-")


def _group_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _plain(text: str) -> str:
    """Échappe ce que MyST lirait comme du balisage, sauf dans les segments `code`."""
    parts = text.split("`")
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"([*<\\])", r"\\\1", parts[i])
    return "`".join(parts)


def _first_sentence(text: str) -> str:
    """La première phrase d'une description, sans jamais couper un segment `code` en deux."""
    sentence = re.split(r"(?<=[.!?])\s|\s—\s", text, maxsplit=1)[0].strip()
    if len(sentence) > _SUMMARY_LIMIT:
        sentence = sentence[:_SUMMARY_LIMIT - 1].rstrip()
        if sentence.count("`") % 2:
            sentence = sentence[:sentence.rindex("`")].rstrip()
        sentence += "…"
    return sentence


def _cell(text: str) -> str:
    """Un texte de cellule de tableau : le balisage échappé, et les barres verticales aussi (même dans un `code`)."""
    return _plain(text).replace("|", "\\|")


def _params(params: list[dict]) -> list[str]:
    """Les paramètres d'une fonction en tableau (nom, type, et description si au moins un paramètre en a une)."""
    described = any(p.get("description") for p in params)
    header = ["Paramètre", "Type"] + (["Description"] if described else [])
    lines = [":::{table}", ":class: backstage-params", ":widths: auto", "",
             "| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    for p in params:
        cells = [f"`{p['name']}`", f"`{_cell(p['type'])}`"] + ([_cell(p.get("description", ""))] if described else [])
        lines.append("| " + " | ".join(cells) + " |")
    return lines + [":::", ""]


def _entry(entry: dict, level: int) -> list[str]:
    lines = [f"({entry['doc_anchor']})=", f"{'#' * level} `{entry['label']}`", ""]
    meta = [m for m in (entry.get("access"), f"Retourne `{entry['returns']}`" if entry.get("returns") else "") if m]
    if meta:
        lines += [" · ".join(meta), ""]
    lines += [_plain(entry["description"]), ""]
    if entry["params"]:
        lines += _params(entry["params"])
    return lines


def _summary(entries: list[dict]) -> list[str]:
    """Le tableau récapitulatif d'un groupe : une ligne par fonction, qui renvoie à sa fiche."""
    lines = ["| Fonction | Rôle |", "| --- | --- |"]
    for e in entries:
        lines.append(f"| [`{e['label']}`](#{e['doc_anchor']}) | {_plain(_first_sentence(e['description']))} |")
    return lines + [""]


def _groups(section: dict, descriptions: dict[str, str]) -> list[dict]:
    """Les groupes d'une section, chacun avec sa description et ses fonctions courantes (`iteration`) et avancées (`engine`)."""
    groups: dict[str, dict] = {}
    for layer in ("iteration", "engine"):
        for g in section[layer]:
            name = g["name"]
            if name not in descriptions:
                raise RuntimeError(f"Group '{name}' has no description in {GROUP_DESCRIPTIONS.name}")
            slot = groups.setdefault(name, {"name": name, "slug": _group_slug(name), "description": descriptions[name],
                                            "iteration": [], "engine": []})
            slot[layer].extend(g["entries"])
    return list(groups.values())


def _write_forms(entries: list[dict]) -> str:
    """Comment on écrit les fonctions d'un groupe, lu dans les modèles d'insertion (`snippet`) du catalogue :
    `self:` pour une fonction, `self.` pour une propriété, un nom nu pour une fonction sans préfixe."""
    names: dict[str, list[str]] = {}
    for e in entries:
        m = re.match(r"^([A-Za-z_]+)([:.])", e["snippet"])
        name, sep = (m.group(1), m.group(2)) if m else (re.match(r"[A-Za-z_]+", e["snippet"]).group(0), "")
        if sep not in names.setdefault(name, []):
            names[name].append(sep)
    return " ou ".join(" / ".join(f"`{name}{sep}`" for sep in seps) for name, seps in names.items())


def _write_on_reference(entries: list[dict]) -> str:
    """L'écriture d'une référence autre que l'acteur : le préfixe du catalogue (`layer:`, `tilemap:`) n'est pas du Lua
    valide tel quel, la référence s'obtient d'abord (`layer:get(0)`) et se tient dans une variable."""
    seps = {m.group(2) for e in entries if not e["snippet"].startswith("self")
            if (m := re.match(r"^([A-Za-z_]+)([:.])", e["snippet"]))}
    forms = [form for sep, form in ((":", "`ref:fonction()`"), (".", "`ref.propriété`")) if sep in seps]
    return " ou ".join(forms) + ", où `ref` est la variable qui tient la référence"


def _factories(sections: list[dict]) -> dict[str, list[str]]:
    """Pour chaque type de référence, les fonctions et les propriétés du catalogue qui en rendent une (`actor:get(...)`,
    `self.parent`)."""
    from scripting.api import RUNTIME_API, RUNTIME_PROPS, REF_TYPE_TABLE, canonical_key

    found: dict[str, list[str]] = {}
    for section in sections:
        for layer in ("iteration", "engine"):
            for g in section[layer]:
                for e in g["entries"]:
                    nom = e["label"].split("(")[0].strip()
                    # une propriété s'affiche sans récepteur (`parent(int)`) : elle se cherche sous `self.`
                    key = canonical_key(nom if (":" in nom or "." in nom) else f"self.{nom}")
                    api, prop = RUNTIME_API.get(key), RUNTIME_PROPS.get(key)
                    rendu = api.ret if api is not None else (prop.ref if prop is not None else None)
                    if rendu in REF_TYPE_TABLE:
                        # une propriété s'écrit avec son récepteur, sans son type : `self.parent`
                        ecrit = e["label"] if api is not None else (nom if ("." in nom or ":" in nom) else f"self.{nom}")
                        found.setdefault(rendu, []).append(f"`{ecrit}`")
    return found


def _definition(group: dict, definitions: dict, factories: dict[str, list[str]]) -> list[str]:
    """Le bloc « Définition » d'un groupe : ce qu'on manipule, comment l'écrire, d'où ça vient."""
    from scripting.api import REF_TYPE_TABLE

    entries = group["iteration"] + group["engine"]
    spec = definitions["groups"].get(group["name"]) or {}
    rows: list[tuple[str, str]] = []
    if "ref" not in spec:
        rows.append(("Type", "Module : on l'appelle directement, sans rien créer."))
        rows.append(("Écriture", _write_forms(entries)))
    else:
        ref = spec["ref"]
        info, table = definitions["references"][ref], REF_TYPE_TABLE[ref]
        rows.append(("Type", f"Référence ({info['name']})"))
        rows.append(("Écriture", _write_forms(entries) if ref == "actor" else _write_on_reference(entries)))
        if table.base:
            rows.append(("Hérite de", f"`{REF_TYPE_TABLE[table.base].prefix}:`"))
        obtained = spec.get("obtained") or ", ".join(factories.get(ref, []))
        if obtained:
            rows.append(("Obtenu par", obtained))
        rows.append(("Dans la ROM", info["in_rom"]))
    if spec.get("note"):
        rows.append(("À savoir", spec["note"]))
    return ["## Définition", "", ":::{div} backstage-definition", *[f"- **{k}** : {v}" for k, v in rows], ":::", ""]


def _group_page(group: dict, definitions: dict, factories: dict[str, list[str]]) -> list[str]:
    lines = [f"# {group['name']}", "", group["description"], ""]
    lines += _definition(group, definitions, factories)
    if group["iteration"]:
        lines += ["## En un coup d'œil", ""] + _summary(group["iteration"])
        for e in group["iteration"]:
            lines += _entry(e, 2)
    if group["engine"]:
        lines += ["## Aller plus loin", ""] + _summary(group["engine"])
        for e in group["engine"]:
            lines += _entry(e, 3)
    return lines


def _cards(groups: list[dict], color: str, prefix: str) -> list[str]:
    """Une carte par groupe : son titre, une courte description, puis (en pied) son nombre de fonctions."""
    lines = ["::::{grid} 1 1 2 3", ":gutter: 3", ":class-container: backstage-cards", ""]
    for g in groups:
        total = len(g["iteration"]) + len(g["engine"])
        count = f"{total} fonction" + ("s" if total > 1 else "")
        lines += [f":::{{grid-item-card}} {g['name']}", f":link: {prefix}{g['slug']}", ":link-type: doc",
                  f":class-card: backstage-card backstage-card-{color}", "",
                  g["description"], "", "+++", count, ":::", ""]
    return lines + ["::::", ""]


def _toctree(entries: list[str]) -> list[str]:
    return ["```{toctree}", ":hidden:", ":maxdepth: 1", ""] + entries + ["```", ""]


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def generate(out_dir: Path = OUT_DIR, index_path: Path = INDEX_PATH) -> list[str]:
    """Réécrit `out_dir` (par défaut `docs/lua-api/api/`) et l'index de recherche ; rend les entrées écrites, sous la forme de leurs ancres."""
    if str(EDITOR_DIR) not in sys.path:
        sys.path.insert(0, str(EDITOR_DIR))
    from scripting.api_reference import get_sections

    titles = _section_titles()
    descriptions = json.loads(GROUP_DESCRIPTIONS.read_text(encoding="utf-8"))
    section_descriptions = json.loads(SECTION_DESCRIPTIONS.read_text(encoding="utf-8"))
    definitions = json.loads(GROUP_DEFINITIONS.read_text(encoding="utf-8"))
    sections = get_sections()
    factories = _factories(sections)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    anchors: list[str] = []
    index: list[dict] = []
    seen_pages: set[str] = set()
    used_groups: set[str] = set()
    used_sections: set[str] = set()
    glossary: list[str] = [
        "# Glossaire des fonctions", "",
        "Les fonctions de l'API, rangées par catégorie. Choisissez un groupe pour voir toutes ses fiches ; "
        "les fiches sont générées à partir du catalogue de l'éditeur (le panneau **API**) et publiées telles quelles, en anglais.",
        "",
        "Les sections suivent ce que vous tenez entre les mains : un acteur, la scène, la caméra… "
        "Chaque fonction se trouve avec la chose qu'elle modifie.",
        ""]
    section_pages: list[str] = []

    for number, section in enumerate(sections):
        key = section["label"]
        if key not in titles:
            raise RuntimeError(f"Section '{key}' has no French title in {LABELS_FR.name}")
        if key not in section_descriptions:
            raise RuntimeError(f"Section '{key}' has no description in {SECTION_DESCRIPTIONS.name}")
        used_sections.add(key)
        blurb = section_descriptions[key]
        slug, title = _section_slug(key), titles[key]
        color = _SECTION_COLORS[number % len(_SECTION_COLORS)]
        groups = _groups(section, descriptions)
        section_pages.append(f"{slug}/index")

        for g in groups:
            page = f"{slug}/{g['slug']}"
            if page in seen_pages:
                raise RuntimeError(f"Two groups share the page '{page}'")
            seen_pages.add(page)
            used_groups.add(g["name"])
            url = f"lua-api/api/{page}.html"
            index.append({"t": "group", "n": g["name"], "s": g["name"], "d": g["description"], "g": title, "u": url})
            for e in g["iteration"] + g["engine"]:
                index.append({"t": "fn", "n": e["label"].split("(")[0].strip(), "s": e["label"],
                              "d": _first_sentence(e["description"]), "g": g["name"], "u": f"{url}#{e['doc_anchor']}"})
            _write(out_dir / f"{page}.md", _group_page(g, definitions, factories))
            anchors += [e["doc_anchor"] for e in g["iteration"] + g["engine"]]

        total = sum(len(g["iteration"]) + len(g["engine"]) for g in groups)
        intro = f"{total} fonctions, réparties en {len(groups)} groupes."
        _write(out_dir / slug / "index.md",
               [f"# {title}", "", blurb, "", intro, ""] + _cards(groups, color, "") + _toctree([g["slug"] for g in groups]))
        glossary += [f"## {title}", "", blurb, ""] + _cards(groups, color, f"{slug}/")

    stale_definitions = sorted(set(definitions["groups"]) - used_groups)
    if stale_definitions:
        raise RuntimeError(f"{GROUP_DEFINITIONS.name} defines groups that no longer exist: {', '.join(stale_definitions)}")
    stale_sections = sorted(set(section_descriptions) - used_sections)
    if stale_sections:
        raise RuntimeError(f"{SECTION_DESCRIPTIONS.name} describes sections that no longer exist: {', '.join(stale_sections)}")
    unused = sorted(set(descriptions) - used_groups)
    if unused:
        raise RuntimeError(f"{GROUP_DESCRIPTIONS.name} describes groups that no longer exist: {', '.join(unused)}")

    duplicates = sorted({a for a in anchors if anchors.count(a) > 1})
    if duplicates:
        raise RuntimeError(f"Duplicate doc_anchor in the API catalog: {', '.join(duplicates)}")

    _write(out_dir / "index.md", glossary + _toctree(section_pages))
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
    return anchors
