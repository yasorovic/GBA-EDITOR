# Textes de licences

Ce dossier accompagne le binaire : les licences LGPL et Apache-2.0 exigent que leur
texte soit livré avec ce qui est redistribué. La liste des composants, leurs versions
et leurs conditions sont dans [THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md) ;
le texte de la GPL-3.0 de l'éditeur est dans [LICENSE](../LICENSE), celui de la
licence zlib du moteur dans `runtime/LICENSE`.

Les fichiers sont des copies, sans modification, des textes fournis avec les paquets
et les distributions concernés.

## Licences générales

| Fichier | S'applique à |
| --- | --- |
| `LGPL-3.0.txt` | Qt (PyQt6-Qt6) |
| `LGPL-2.1.txt` | FFmpeg (`avcodec`, `avformat`, `avutil`, `swresample`, `swscale`) |
| `Apache-2.0.txt` | OpenSSL, multimethod, polices Material Design Icons et Remix Icon |
| `PSF-Python.txt` | Python (interpréteur et bibliothèque standard) |

## Paquets Python (`python-packages/`)

Le texte fourni par chaque paquet. `NumPy.txt` contient aussi ceux d'OpenBLAS, de
LAPACK et de la bibliothèque runtime de GCC, embarqués dans NumPy.

| Fichier | Composant |
| --- | --- |
| `NumPy.txt` | NumPy, OpenBLAS, LAPACK, GCC runtime library |
| `Pillow.txt` | Pillow |
| `freetype-py.txt` | freetype-py (le binding ; FreeType est crédité dans THIRD-PARTY-NOTICES.md) |
| `QtPy.txt` | QtPy |
| `QtAwesome.txt` | QtAwesome |
| `luaparser.txt` | luaparser (modèle MIT fourni tel quel par le paquet, titulaire non renseigné) |
| `multimethod.txt` | multimethod (en-tête Apache-2.0, texte complet dans `Apache-2.0.txt`) |
| `PyQt6-sip.txt` | PyQt6-sip |

PyQt6 est sous GPL-3.0 : son texte est celui du fichier `LICENSE` de l'éditeur.

## Pas encore fournis

Ces composants sont listés dans THIRD-PARTY-NOTICES.md mais leur texte n'était pas
disponible dans leur distribution : à ajouter depuis leur dépôt d'origine.

- antlr4-python3-runtime (BSD) : son paquet ne contient pas son texte de licence ;
- libffi (MIT) ;
- les bibliothèques compilées dans les modules Python : expat (MIT), libmpdec
  (BSD-2-Clause), bzip2 (style BSD), liblzma (domaine public / 0BSD) ;
- les polices de QtAwesome : Font Awesome et Elusive Icons (SIL OFL 1.1), Codicon
  (CC BY 4.0), Phosphor (MIT) ;
- le runtime Visual C++ de Microsoft, redistribuable sous les conditions de Microsoft.
