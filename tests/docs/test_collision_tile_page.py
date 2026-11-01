"""La page « Types de tuile de collision » dit la même chose que le modèle : un index, une constante, une famille."""
from __future__ import annotations

import re
from pathlib import Path

from core.models import collision_tiles as CT

PAGE = Path(__file__).resolve().parents[2] / "docs" / "guides" / "acteurs" / "types-de-tuile-collision.md"
FAMILLES = {CT.KIND_EMPTY: "Vide", CT.KIND_SOLID: "Plein", CT.KIND_FLOOR: "Sol",
            CT.KIND_CEILING: "Plafond", CT.KIND_ONEWAY: "Sens unique"}


def _lignes():
    return [tuple(c.strip() for c in ligne.strip("|").split("|")[:3])
            for ligne in PAGE.read_text(encoding="utf-8").splitlines()
            if re.match(r"\|\s*\d+\s*\|", ligne)]


def test_la_page_liste_chaque_type_une_fois_avec_sa_constante_et_sa_famille():
    constantes = {valeur: nom for nom, valeur in vars(CT).items()
                  if nom.startswith("TILE_") and isinstance(valeur, int) and nom != "TILE_COUNT"}
    lignes = _lignes()
    assert [int(i) for i, *_ in lignes] == list(range(CT.TILE_COUNT))
    for index, constante, famille in lignes:
        assert constante == f"`{constantes[int(index)]}`"
        assert famille == FAMILLES[CT.kind_of(int(index))]


def test_la_page_annonce_le_bon_nombre_de_types():
    assert f"**{CT.TILE_COUNT} types**" in PAGE.read_text(encoding="utf-8")
