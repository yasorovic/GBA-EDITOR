# Backstage

**Créez des jeux Game Boy Advance depuis une interface visuelle, puis compilez-les en véritables ROMs `.gba`.**

Backstage réunit scènes, sprites, collisions, son et scripts dans un même projet. Les scripts utilisent une syntaxe Lua simplifiée, traduite en C au Build, pour produire des jeux jouables sur émulateur et sur console.

## Ce que vous pouvez faire

- Construire des scènes, placer les acteurs, collisions, caméra et interface.
- Importer et préparer sprites, décors, palettes, polices et sons.
- Écrire le comportement du jeu avec des scripts simples, ou réutiliser des behaviors.
- Compiler, vérifier et lancer votre ROM avec **Build & Run**.

## Commencer

1. Téléchargez Backstage depuis la page des releases du projet.
   - **`Backstage-<version>-windows-setup.exe`** installe l'application pour votre compte utilisateur, sans droits administrateur.
   - **`Backstage-<version>-windows-portable.zip`** se décompresse où vous voulez ; lancez ensuite `Backstage.exe`.
2. Installez les deux outils utilisés pour fabriquer et tester les ROMs :

   | Outil | Rôle | Lien |
   | --- | --- | --- |
   | **devkitPro** (devkitARM, grit, make) | Compile la ROM `.gba` à partir du projet. | [Installation](https://devkitpro.org/wiki/Getting_Started) |
   | **mGBA** | Lance la ROM avec **Build & Run**. | [Téléchargement](https://mgba.io/downloads.html) |

L'éditeur détecte ces installations automatiquement.

## Guides et exemples

- [Documentation](docs/index.md) : toute la documentation du projet.
- [Guide utilisateur](docs/user-guide/index.md) : créer ou ouvrir un projet, naviguer, importer des ressources et lancer une première ROM.
- [Guide de scripting](docs/scripting.md) : écrire le comportement d'un acteur.
- [Référence de scripting](docs/scripting-reference.md) : vérifier la syntaxe disponible et les limites du langage.

Le détail des travaux en cours et des prochaines versions se trouve dans la [roadmap](ROADMAP.md).

## Licence

### Votre jeu vous appartient

Vous pouvez vendre, publier ou garder privé le jeu et la ROM créés avec Backstage, sans redevance ni autorisation à demander. Le runtime ajouté à votre projet au Build est sous licence [zlib](runtime/LICENSE).

### L'éditeur

Backstage est un logiciel libre sous [GPL-3.0-only](LICENSE). Vous pouvez l'utiliser, l'étudier, le modifier et le redistribuer sous cette même licence. Les composants logiciels redistribués et leurs notices sont listés dans [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
