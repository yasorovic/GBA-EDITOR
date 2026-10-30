"""Le manifeste des paquets devkitPro que l'installateur Windows télécharge : chaque paquet
est épinglé (version, URL, empreinte), et l'installateur ne livre que des fichiers qui existent."""
from __future__ import annotations

import json
import re
from pathlib import Path

PACKAGING = Path(__file__).resolve().parents[2] / "packaging" / "windows"
MANIFEST = PACKAGING / "devkitpro_manifest.json"
MIRROR = "https://github.com/yasorovic/backstage-toolchain/releases/download/"
OFFICIAL = ("https://pkg.devkitpro.org/packages/", "https://repo.msys2.org/msys/x86_64/")


def _packages() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["packages"]


def test_chaque_paquet_est_epingle():
    for package in _packages():
        assert re.fullmatch(r"[0-9a-f]{64}", package["sha256"]), package["name"]
        assert package["size"] > 0, package["name"]
        assert package["layout"] in ("devkitpro", "msys2"), package["name"]
        assert package["url"].startswith(MIRROR), package["name"]
        assert package["origin"].startswith(OFFICIAL), package["name"]
        assert package["version"] in package["url"], f"{package['name']} : la version n'est pas celle de l'URL"


def test_pas_de_paquet_en_double():
    names = [p["name"] for p in _packages()]
    assert len(names) == len(set(names))


def test_le_manifeste_porte_de_quoi_construire_une_rom():
    """Ce que le script d'installation exige après l'extraction vient de ces paquets."""
    names = {p["name"] for p in _packages()}
    assert {"devkitarm-gcc", "devkitarm-binutils", "devkitarm-newlib", "devkitarm-crtls", "devkitarm-rules",
            "libgba", "maxmod-gba", "grit", "mmutil", "general-tools", "gba-tools"} <= names
    # make, sh, mkdir et rm du Makefile du runtime, avec leurs bibliothèques.
    assert {"msys2-runtime", "bash", "make", "coreutils", "libintl", "libiconv", "gcc-libs"} <= names


def test_l_installateur_depose_les_fichiers_qu_il_lance():
    nsi = (PACKAGING / "installer.nsi").read_text(encoding="utf-8-sig")
    for name in ("install_devkitpro.ps1", "devkitpro_manifest.json"):
        assert (PACKAGING / name).is_file()
        assert f'File "{name}"' in nsi
    assert not (PACKAGING / "finish_devkitpro.ps1").exists()
    assert "finish_devkitpro" not in nsi


def test_le_script_d_installation_garde_son_encodage():
    """Avec BOM : sans lui, PowerShell 5.1 lit les accents de l'interface en page de code ANSI."""
    assert (PACKAGING / "install_devkitpro.ps1").read_bytes().startswith(b"\xef\xbb\xbf")


LINUX_PACKAGES = Path(__file__).resolve().parents[2] / "packaging" / "linux" / "devkitpro_packages.txt"


def _linux_packages() -> dict[str, dict]:
    rows = {}
    for line in LINUX_PACKAGES.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name, version, sha256, size, url = line.split(" ")
        rows[name] = {"version": version, "sha256": sha256, "size": int(size), "url": url}
    return rows


def test_la_liste_linux_est_epinglee():
    for name, row in _linux_packages().items():
        assert re.fullmatch(r"[0-9a-f]{64}", row["sha256"]), name
        assert row["size"] > 0, name
        assert row["url"].startswith(MIRROR), name
        assert row["version"] in row["url"], f"{name} : la version n'est pas celle de l'URL"


def test_les_paquets_communs_sont_les_memes_sous_windows_et_sous_linux():
    """Les paquets `any` (libgba, maxmod, newlib...) sont les mêmes fichiers : une version qui
    diverge entre les deux listes serait une chaîne différente selon la plateforme."""
    windows = {p["name"]: p for p in _packages()}
    for name, row in _linux_packages().items():
        if "-any." in row["url"]:
            assert windows[name]["sha256"] == row["sha256"], name


def test_le_script_linux_et_le_paquet_deb_livrent_la_liste():
    assert LINUX_PACKAGES.is_file()
    build = (LINUX_PACKAGES.parent / "build_packages.sh").read_text(encoding="utf-8")
    assert "devkitpro_packages.txt" in build
    assert (LINUX_PACKAGES.parent / "backstage-setup-devkitpro").read_bytes().count(b"\r") == 0


def test_l_installateur_suit_l_avancement_du_script():
    """La seconde barre de l'assistant lit le fichier que le script ecrit : les deux doivent
    s'accorder sur son nom, sur son format (pourcentage|etape|...) et sur l'annulation."""
    nsi = (PACKAGING / "installer.nsi").read_text(encoding="utf-8-sig")
    script = (PACKAGING / "install_devkitpro.ps1").read_text(encoding="utf-8-sig")
    assert '-ProgressFile "${TOOLCHAIN_PROGRESS}"' in nsi
    assert "[string]$ProgressFile" in script
    for step in ("|download|", "|extract|", "100|done", "-1|error|"):
        assert step in script, step
    assert '"${TOOLCHAIN_PROGRESS}.cancel"' in nsi and '"$ProgressFile.cancel"' in script
