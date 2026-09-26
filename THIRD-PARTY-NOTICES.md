# Composants tiers

L'éditeur est distribué sous GPL-3.0-only (cf. [LICENSE](LICENSE)). Il embarque
et redistribue les composants ci-dessous, chacun sous ses propres conditions.

> Le moteur GBA (`runtime/`) n'est pas concerné par cette page : il est sous
> licence zlib et n'embarque rien de tiers. Voir [runtime/LICENSE](runtime/LICENSE).

## Bibliothèques Python

| Composant | Version | Licence |
| --- | --- | --- |
| [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — Riverbank Computing | 6.11.0 | **GPL-3.0-only** |
| [PyQt6-Qt6](https://www.qt.io/) — The Qt Company | 6.11.1 | **LGPL-3.0** |
| PyQt6-sip — Riverbank Computing | 13.12.0 | BSD-2-Clause |
| [Pillow](https://python-pillow.org/) | 12.3.0 | MIT-CMU |
| [NumPy](https://numpy.org/) | 2.5.2 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| [QtAwesome](https://github.com/spyder-ide/qtawesome) | 1.4.2 | MIT |
| [luaparser](https://github.com/boolangery/py-lua-parser) | 4.1.0 | MIT |
| [QtPy](https://github.com/spyder-ide/qtpy) | 2.4.3 | MIT |
| [antlr4-python3-runtime](https://www.antlr.org/) | 4.13.2 | BSD |
| [multimethod](https://github.com/coady/multimethod) | 2.1 | Apache-2.0 |

Les quatre derniers sont des dépendances transitives (antlr4 et multimethod via
luaparser, QtPy via QtAwesome)

### Deux points qui ne sont pas de simples notices

**PyQt6 est en GPL-3.0-only.** C'est la raison pour laquelle cet éditeur est
lui-même en GPL-3.0 : Pour distribuer un binaire lié à PyQt6 sous une licence
n'est pas possible sans une licence commerciale Riverbank.

**Qt est en LGPL-3.0.** Elle impose de fournir cette notice et de ne pas
empêcher l'utilisateur de remplacer les bibliothèques Qt par une version
modifiée. La distribution étant en mode *standalone* (les `.dll` Qt sont des
fichiers séparés dans le dossier, pas fusionnées dans l'exécutable), le
remplacement reste possible.

## Fontes

| Fonte | Origine | Licence |
| --- | --- | --- |
| Font Awesome 5 / 6 | via QtAwesome | SIL OFL 1.1 (fontes) + CC BY 4.0 (icônes) |
| Elusive Icons | via QtAwesome | SIL OFL 1.1 |
| Codicon | via QtAwesome | CC BY 4.0 |

Les fontes de QtAwesome sont fournies par le paquet lui-même et leurs notices
respectives se trouvent dans son arborescence.

## Chaîne de compilation (non redistribuée)

L'éditeur ne redistribue **pas** ces outils : il détecte une installation
existante sur la machine et l'appelle. Ils ne sont donc dans aucun artefact
publié ici. Ils sont mentionnés parce qu'ils comptent pour l'utilisateur.

| Outil | Rôle |
| --- | --- |
| devkitARM, grit (devkitPro) | compilation ARM et conversion des images : outils, ils n'entrent pas dans la ROM |
| libgba, maxmod (devkitPro) | **liées dans la ROM de l'utilisateur** (`-lgba -lmm`) |
| mGBA | émulateur, lancé pour tester |

`libgba` et `maxmod` finissent dans la ROM produite : leurs conditions
s'appliquent donc à celui qui publie le jeu, pas à cet éditeur. Elles sont
permissives et compatibles avec une distribution commerciale ; les termes
exacts sont à lire chez devkitPro.
