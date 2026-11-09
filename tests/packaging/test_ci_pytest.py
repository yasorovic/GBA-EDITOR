"""Le résumé CI distingue un échec de test d'un incident du contrôle."""
import pytest

from ci_pytest import verdict


@pytest.mark.parametrize(
    ("code", "counts", "expected"),
    [
        (0, 'tests="3" skipped="1"', "2 réussi(s), 1 ignoré(s)"),
        (0, 'tests="1" skipped="1"', "Aucun test n’a rendu de verdict"),
        (1, 'tests="1" failures="1"', "Échec de test"),
        (1, 'tests="1" errors="1"', "Contrôle sans verdict"),
        (1, None, "sans résultat de test exploitable"),
        (5, None, "aucun test sélectionné"),
        (139, 'tests="1" failures="1"', "arrêt anormal du processus"),
    ],
)
def test_ci_verdict(tmp_path, code, counts, expected):
    report = tmp_path / "pytest.xml"
    if counts is not None:
        report.write_text(f"<testsuites><testsuite {counts}/></testsuites>", encoding="utf-8")
    assert expected in verdict(code, report)
