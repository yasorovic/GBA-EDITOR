"""Présente le verdict de pytest dans le résumé GitHub Actions."""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def verdict(code: int, report: Path) -> str:
    if code not in (0, 1):
        reason = {
            2: "collecte en échec ou exécution interrompue",
            3: "erreur interne de pytest",
            4: "impossible de lancer pytest avec cette configuration",
            5: "aucun test sélectionné",
            6: "limite d’avertissements dépassée",
        }.get(code, "arrêt anormal du processus")
        return f"**Contrôle sans verdict** : {reason} (code {code})."

    try:
        suites = ET.parse(report).getroot().findall("testsuite")
    except (OSError, ET.ParseError):
        suites = []

    failures = sum(int(suite.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.get("errors", "0")) for suite in suites)
    skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
    total = sum(int(suite.get("tests", "0")) for suite in suites)
    if code == 0:
        if not suites:
            return "**Validé par pytest** (code 0, rapport détaillé indisponible)."
        if total == skipped:
            return f"**Aucun test n’a rendu de verdict** : {skipped} ignoré(s), pytest a renvoyé 0."
        return f"**Validé** : {total - skipped} réussi(s), {skipped} ignoré(s)."
    if failures or errors:
        lines = []
        if failures:
            lines.append(f"**Échec de test** : {failures} test(s) en échec.")
        if errors:
            lines.append(f"**Contrôle sans verdict** : {errors} erreur(s) de préparation ou de nettoyage des tests.")
        return "\n\n".join(lines)
    return "**Contrôle sans verdict** : pytest a échoué (code 1), sans résultat de test exploitable."


if __name__ == "__main__":
    title, code = sys.argv[1:]
    message = verdict(int(code), Path(os.environ["RUNNER_TEMP"]) / "pytest.xml")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(f"### {title}\n\n{message}\n\nConsulter le journal de l’étape de test pour le détail.\n")
