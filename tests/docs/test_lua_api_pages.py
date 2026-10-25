"""Le site de documentation publie TOUT le catalogue de l'API, sans rien perdre en route."""
from __future__ import annotations

import re
import sys

from conftest import REPO_DIR

sys.path.insert(0, str(REPO_DIR / "docs"))

from _gen.lua_api import generate  # noqa: E402
from scripting.api_reference import get_sections  # noqa: E402


def _expected_anchors():
    return [e["doc_anchor"]
            for s in get_sections() for key in ("iteration", "engine")
            for g in s[key] for e in g["entries"]]


def test_every_catalog_entry_is_published_once(tmp_path):
    out = tmp_path / "api"
    written = generate(out)

    expected = _expected_anchors()
    assert sorted(written) == sorted(expected)

    pages = "\n".join(p.read_text(encoding="utf-8") for p in out.rglob("*.md"))
    published = re.findall(r"^\(([^)]+)\)=$", pages, flags=re.M)
    assert sorted(published) == sorted(expected)


def test_every_entry_is_in_its_group_summary_table(tmp_path):
    out = tmp_path / "api"
    generate(out)

    pages = "\n".join(p.read_text(encoding="utf-8") for p in out.rglob("*.md"))
    linked = re.findall(r"^\| \[`[^|]*`\]\(#([^)]+)\) \|", pages, flags=re.M)
    assert sorted(linked) == sorted(_expected_anchors())


def test_glossary_has_a_card_for_every_group(tmp_path):
    out = tmp_path / "api"
    generate(out)

    glossary = (out / "index.md").read_text(encoding="utf-8")
    group_pages = [p for p in out.rglob("*.md") if p.parent != out and p.name != "index.md"]
    assert group_pages
    for page in group_pages:
        link = f":link: {page.parent.name}/{page.stem}\n"
        assert link in glossary, page

    for s in get_sections():
        slug = s["label"].removeprefix("scrsb.sec.").replace("_", "-")
        assert (out / slug / "index.md").exists()
        assert f"\n{slug}/index\n" in glossary


def test_group_definitions_agree_with_the_language_declarations(tmp_path):
    """Le bloc « Définition » ne contredit pas `REF_TYPE_TABLE` : le type C annoncé est le vrai, et chaque
    type de référence se retrouve soit par une fabrique du catalogue, soit par un texte `obtained` écrit."""
    import json
    from _gen.lua_api import GROUP_DEFINITIONS, _factories
    from scripting.api import REF_TYPE_TABLE

    definitions = json.loads(GROUP_DEFINITIONS.read_text(encoding="utf-8"))
    factories = _factories(get_sections())

    for ref, info in definitions["references"].items():
        assert ref in REF_TYPE_TABLE, ref
        assert f"`{REF_TYPE_TABLE[ref].c_type}`" in info["in_rom"], ref

    for name, spec in definitions["groups"].items():
        if "ref" in spec:
            assert spec["ref"] in definitions["references"], name
            assert spec.get("obtained") or factories.get(spec["ref"]), name
        else:
            assert spec.get("note"), f"{name} : ni type de référence, ni note"


def test_every_group_page_opens_with_a_definition(tmp_path):
    out = tmp_path / "api"
    generate(out)

    pages = [p for p in out.rglob("*.md") if p.parent != out and p.name != "index.md"]
    assert pages
    for page in pages:
        assert "## Définition" in page.read_text(encoding="utf-8"), page


def test_search_index_covers_every_function_and_group(tmp_path):
    """L'index de l'auto-complétion a une entrée par fonction et par groupe, et chaque lien vise une page
    et une ancre qui existent."""
    import json

    out, index_path = tmp_path / "api", tmp_path / "static" / "lua-api-index.json"
    generate(out, index_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))

    functions = [e for e in index if e["t"] == "fn"]
    assert sorted(e["u"].split("#")[1] for e in functions) == sorted(_expected_anchors())
    assert len([e for e in index if e["t"] == "group"]) == len({e["u"].split("#")[0] for e in functions})

    for e in index:
        page, _, anchor = e["u"].partition("#")
        assert page.startswith("lua-api/api/") and page.endswith(".html"), e
        source = out / page.removeprefix("lua-api/api/").replace(".html", ".md")
        assert source.exists(), e
        if anchor:
            assert f"({anchor})=" in source.read_text(encoding="utf-8"), e
