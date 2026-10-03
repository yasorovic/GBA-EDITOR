"""
core/app_info.py — qui est ce logiciel : son nom, son auteur, sa version.

SOURCE UNIQUE. Tout ce qui affiche ou publie l'une de ces trois valeurs la lit
ici : la fenêtre, le rapport de diagnostic, le build Nuitka, l'installateur, le
workflow de release. Aucun autre fichier ne la recopie à la main.

**La version vit dans le dépôt, le tag la CONFIRME.** On change `APP_VERSION`
dans un commit, puis on tague `v<APP_VERSION>` : la release échoue si les deux
divergent (cf. `packaging/nuitka_build.py --print-version` et le job `version`
de `.github/workflows/release.yml`). Le sens inverse — un build qui écrase ce
fichier d'après le tag — ferait dire à un lancement depuis les sources une
version qu'il n'a pas.

Convention (cf. ROADMAP) : `X.Y.Z-<étiquette>`, l'étiquette toujours écrite.
`X` = numéro de version, `Y` = jalon standard de la roadmap, `Z` = tout ce qui
avance d'autre (chantier technique, correction, optimisation). Un jalon sort
d'abord en `-alpha`, puis `-beta`, puis `-stable`, sous le même numéro :
`1.0.0-alpha`, `1.0.0-beta`, `1.0.0-stable`.

Stdlib seule, et aucune importation : ce module est lu par les scripts de
packaging, qui n'ont pas les dépendances de l'éditeur.
"""

APP_NAME = "Backstage"
APP_AUTHOR = "Yasorovic"
APP_VERSION = "1.0.0-alpha"

# Adresses publiques du produit. Le code qui les lit sait s'en passer si l'une
# est VIDE (le menu « Documentation » ou l'onglet « Modèles » ne s'affichent
# pas). Source unique : aucune adresse ne doit figurer en dur dans le code
# (les liens des README et des docs, eux, sont de la rédaction).
#
# APP_DOCS_URL      : le site de documentation ;
# APP_TEMPLATES_URL : un zip d'archive (type « branche entière » d'un dépôt) d'où
#                     se téléchargent les projets modèles. Le dossier racine du zip
#                     est lu dans l'archive elle-même.
APP_DOCS_URL = "https://yasorovic.github.io/GBA-EDITOR/"
APP_TEMPLATES_URL = "https://github.com/yasorovic/GBA-EDITOR/archive/refs/heads/main.zip"
# APP_RELEASES_URL  : les notes de version ;
# APP_ISSUES_URL    : le formulaire de rapport de problème.
APP_RELEASES_URL = "https://github.com/yasorovic/GBA-EDITOR/releases"
APP_ISSUES_URL = "https://github.com/yasorovic/GBA-EDITOR/issues/new"
