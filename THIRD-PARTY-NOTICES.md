# Composants tiers

L'éditeur Backstage est distribué sous GPL-3.0-only (voir [LICENSE](LICENSE)). Il
embarque et redistribue les composants ci-dessous, chacun sous ses propres
conditions. Les textes de licence disponibles sont livrés dans le dossier
[licenses/](licenses/README.md) avec l'application ; lorsque le texte n'est pas
fourni par une dépendance, cette page indique son origine et sa licence.

Les dépendances Python ne sont pas verrouillées dans le dépôt : les versions
exactes d'une distribution sont celles résolues par `pip` au moment de son build.
Les bornes ci-dessous sont donc celles déclarées dans `requirements.txt`, et non
une promesse qu'un même numéro de version sera présent dans chaque release.

> Le moteur GBA (`runtime/`) n'est pas concerné par cette page : il est sous
> licence zlib et n'embarque rien de tiers. Voir [runtime/LICENSE](runtime/LICENSE).

## Bibliothèques Python

| Composant | Version déclarée | Licence |
| --- | --- | --- |
| [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — Riverbank Computing | >= 6.11, < 7 | **GPL-3.0-only** |
| [PyQt6-Qt6](https://www.qt.io/) — The Qt Company | dépendance transitive de PyQt6 | **LGPL-3.0** |
| PyQt6-sip — Riverbank Computing | dépendance transitive de PyQt6 | BSD-2-Clause |
| [Pillow](https://python-pillow.org/) | >= 12.3, < 13 | MIT-CMU |
| [NumPy](https://numpy.org/) | >= 2.5, < 3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| [freetype-py](https://github.com/rougier/freetype-py) | >= 2.5, < 3 | BSD-3-Clause (binding) ; FreeType est fourni par les wheels standards, voir ci-dessous |
| [QtAwesome](https://github.com/spyder-ide/qtawesome) | >= 1.4, < 2 | MIT |
| [luaparser](https://github.com/boolangery/py-lua-parser) | >= 4.1, < 5 | MIT |
| [QtPy](https://github.com/spyder-ide/qtpy) | dépendance transitive de QtAwesome | MIT |
| [antlr4-python3-runtime](https://www.antlr.org/) | dépendance transitive de luaparser | BSD |
| [multimethod](https://github.com/coady/multimethod) | dépendance transitive de luaparser | Apache-2.0 |

PyQt6-Qt6 et PyQt6-sip viennent avec PyQt6 ; les trois derniers sont des dépendances
transitives (antlr4 et multimethod via luaparser, QtPy via QtAwesome).

### Deux points qui ne sont pas de simples notices

**PyQt6 est en GPL-3.0-only.** C'est la raison pour laquelle cet éditeur est
lui-même en GPL-3.0 : distribuer un binaire lié à PyQt6 sous une autre licence
n'est pas possible sans une licence commerciale Riverbank.

**Qt est en LGPL-3.0.** Elle impose de fournir cette notice et de ne pas
empêcher l'utilisateur de remplacer les bibliothèques Qt par une version
modifiée. La distribution étant en mode *standalone* (les `.dll` Qt sont des
fichiers séparés dans le dossier, pas fusionnées dans l'exécutable), le
remplacement reste possible.

### FreeType

> Portions of this software are copyright © The FreeType Project
> ([www.freetype.org](https://www.freetype.org)). All rights reserved.

Les wheels standards de `freetype-py` fournissent une bibliothèque FreeType
(`libfreetype`), qui sert à rastériser les polices vectorielles importées. Une
installation depuis les sources peut, elle, utiliser une bibliothèque FreeType
déjà présente sur le système. FreeType est proposée sous la
*FreeType License* (FTL, de type BSD, avec mention obligatoire — ci-dessus) **ou**
sous la GPL v2. Cet éditeur la redistribue sous la **FTL** : la GPL v2 seule
(sans « ou ultérieure ») est incompatible avec la GPL-3.0 de l'éditeur.

## Composants natifs embarqués

Ces bibliothèques ne sont pas des paquets Python : elles sont copiées telles quelles
dans le dossier de l'application (fichiers `.dll`, séparés de l'exécutable).

| Composant | Version | Licence | Où |
| --- | --- | --- | --- |
| [Python](https://www.python.org/) (interpréteur et bibliothèque standard) | 3.12.x | PSF License 2.0 | `python312.dll` |
| [FFmpeg](https://ffmpeg.org/) — via Qt Multimédia | selon la distribution Qt résolue par `pip` | **LGPL-2.1-or-later** | `avcodec`, `avformat`, `avutil`, `swresample`, `swscale` |
| [OpenSSL](https://www.openssl.org/) | selon la distribution Python 3.12 utilisée pour le build | Apache-2.0 | `libssl-3.dll`, `libcrypto-3.dll` |
| [libffi](https://sourceware.org/libffi/) | 3.x | MIT | `libffi-8.dll` |
| [OpenBLAS](https://github.com/OpenMathLib/OpenBLAS/) — via NumPy | | BSD-3-Clause | `numpy.libs/` |
| [LAPACK](https://www.netlib.org/lapack/) (dans OpenBLAS) | | BSD-3-Clause-Open-MPI | `numpy.libs/` |
| GCC runtime library (dans OpenBLAS) | | GPL-3.0-or-later avec *GCC Runtime Library Exception 3.1* | `numpy.libs/` |
| Microsoft Visual C++ runtime | 14.x | redistribuable Microsoft (*Visual C++ Redistributable*) | `vcruntime140*.dll`, `msvcp140*.dll` |

**FFmpeg est en LGPL-2.1-or-later.** Comme pour Qt, ses `.dll` sont des fichiers
séparés : l'utilisateur peut les remplacer par une version modifiée. FFmpeg est le
moteur de Qt Multimédia, que l'éditeur utilise pour la sortie audio de l'aperçu des
musiques ; il est livré parce que ce module en dépend.

**Bibliothèques liées dans les modules compilés** (pas de `.dll` à part, donc
invisibles dans le dossier) :

- **Pillow** (`PIL/*.pyd`) embarque brotli, FreeType, HarfBuzz, Little CMS 2,
  libavif, libjpeg-turbo, libpng, libtiff, libwebp, OpenJPEG, xz et zlib-ng,
  sous des licences permissives ; leurs textes sont dans `licenses/python-packages/Pillow.txt` ;
- **Python** : `pyexpat` (expat, MIT), `_decimal` (libmpdec, BSD-2-Clause),
  `_bz2` (bzip2, style BSD) et `_lzma` (liblzma, domaine public / 0BSD) ;
- **Qt** (`qt6gui.dll` et plugins `imageformats/`) : libpng, libjpeg, zlib,
  FreeType, HarfBuzz et d'autres, recensés par la documentation de Qt.

Le plugin `multimedia/windowsmediaplugin.dll` s'appuie sur Windows Media Foundation,
fournie par le système : rien de tiers n'est livré pour lui.

Qt embarque lui-même des composants tiers (modules Qt PDF et Qt Multimédia
notamment) sous leurs propres licences ; elles sont recensées par la documentation
de Qt (« Third-party Licenses »).

L'AppImage Linux embarque en plus des bibliothèques système nécessaires au plugin
Qt « xcb » (notamment xcb, xkbcommon, fontconfig et leurs dépendances). Elles
restent sous leurs licences respectives ; la liste exacte dépend du runner de build
et doit être contrôlée dans l'AppImage produite.

## Fontes

### Livrées dans l'éditeur

| Fonte | Origine | Licence |
| --- | --- | --- |
| Font Awesome 5 / 6 | via QtAwesome | SIL OFL 1.1 (fontes) + CC BY 4.0 (icônes) |
| Elusive Icons | via QtAwesome | SIL OFL 1.1 |
| Codicon | via QtAwesome | CC BY 4.0 |
| Material Design Icons 5.9.55 / 6.9.96 | via QtAwesome | Apache-2.0 |
| Phosphor 1.3.0 | via QtAwesome | MIT |
| Remix Icon 2.5.0 | via QtAwesome | Apache-2.0 |

Les fontes de QtAwesome sont fournies par le paquet lui-même et leurs notices
respectives se trouvent dans son arborescence.

### Livrées dans le projet Starter

Le projet Starter copie ces trois polices dans **chaque projet créé** ; leur
licence est copiée avec elles, dans `project/licenses/` du projet.

| Fonte | Auteur | Licence | Notice livrée |
| --- | --- | --- | --- |
| Font8x8 Latin | Daniel Hepper (d'après des tables de Marcel Sondaar et IBM) | domaine public | `Font8x8.txt` |
| GNU Unifont JP 17.0.04 | Unifoundry / Paul Hardy | SIL OFL 1.1 (option retenue ; double licence avec la GPL v2+ et l'exception d'inclusion de fontes) | `GNU-Unifont-JP.txt` |
| Misaki Gothic (美咲フォント) | Num Kadoma | licence propre de l'auteur : usage et redistribution libres, sous réserve de joindre son texte | `Misaki.txt` |

Les polices vectorielles que **vous** importez dans un projet restent soumises à
leur propre licence : à vous de vérifier qu'elle autorise leur incorporation dans
un jeu.

## Chaîne de compilation (non redistribuée)

L'éditeur ne redistribue **pas** ces outils : il détecte une installation
existante sur la machine et les appelle. Ils ne sont donc inclus dans aucun artefact
publié ici. Ils sont mentionnés parce qu'ils comptent pour l'utilisateur.

| Outil | Rôle |
| --- | --- |
| devkitARM, grit (devkitPro) | compilation ARM et conversion des images : outils, ils n'entrent pas dans la ROM |
| libgba, maxmod (devkitPro) | **liées dans la ROM de l'utilisateur** (`-lgba -lmm`) |
| mGBA | émulateur, lancé pour tester |

`libgba` et `maxmod` finissent dans la ROM produite : leurs conditions
s'appliquent donc à celui qui publie le jeu, pas à cet éditeur. Elles sont
permissives et compatibles avec une distribution commerciale ; les termes
exacts sont à consulter auprès de devkitPro.
