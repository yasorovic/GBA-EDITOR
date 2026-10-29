# Vue d'ensemble

Ce guide explique comment utiliser Backstage pour construire un jeu Game Boy Advance. Aucune
connaissance de la console n'est requise : les contraintes matérielles sont expliquées au fil des pages.

## Télécharger Backstage

Si ce n'est pas déjà fait, téléchargez Backstage !

```{raw} html
<p class="backstage-downloads">
  <a class="backstage-download backstage-download-blue" data-download="windows" href="https://github.com/yasorovic/GBA-EDITOR/releases/latest"><strong>Windows</strong><span>.exe</span></a>
  <a class="backstage-download backstage-download-blue" data-download="windows-portable" href="https://github.com/yasorovic/GBA-EDITOR/releases/latest"><strong>Windows (portable)</strong><span>.zip</span></a>
  <a class="backstage-download backstage-download-orange" data-download="linux-deb" href="https://github.com/yasorovic/GBA-EDITOR/releases/latest"><strong>Linux (Debian, Ubuntu)</strong><span>.deb</span></a>
  <a class="backstage-download backstage-download-orange" data-download="linux-rpm" href="https://github.com/yasorovic/GBA-EDITOR/releases/latest"><strong>Linux (Fedora)</strong><span>.rpm</span></a>
  <a class="backstage-download backstage-download-orange" data-download="linux" href="https://github.com/yasorovic/GBA-EDITOR/releases/latest"><strong>Linux (portable)</strong><span>.AppImage</span></a>
</p>
```

Sous Linux, une seule commande télécharge et installe la dernière version adaptée à la distribution
(`.deb`, `.rpm`, ou AppImage à défaut) :

```bash
curl -fsSL https://github.com/yasorovic/GBA-EDITOR/releases/latest/download/install.sh | sh
```

Le lanceur s'appelle ensuite `backstage`. Pour installer un paquet téléchargé à la main :

```bash
sudo apt install ./Backstage-<version>-amd64.deb
```

```bash
sudo dnf install ./Backstage-<version>-x86_64.rpm
```

L'AppImage, elle, s'utilise sans installation : extrayez l'archive `.tar.gz`, puis lancez le fichier `.AppImage`.

Backstage fabrique des jeux Game Boy Advance depuis une interface visuelle. Vous importez vos
images, vos sons et vos textes, vous les assemblez dans des **scènes**, vous ajoutez du
comportement avec des scripts Lua, puis un seul bouton, **Run**, produit la ROM et la lance dans
l'émulateur mGBA.


```{figure} overview/img/editor-overview.png
:alt: La fenêtre de Backstage sur le projet Platformer : la scène au centre, les listes à gauche, l'inspecteur à droite.
:class: backstage-screenshot

L'écran **Scenes** du projet de démonstration Platformer.
```

## Installer devkitPro

Backstage s'appuie sur **devkitPro**, la chaîne d'outils qui compile la ROM. Si vous avez téléchargé l'installateur de Backstage pour Windows, devkitPro sera installé directement et vous n'aurez rien d'autre à configurer.
La version portable pour Windows (`.zip`) n'installe pas devkitPro : il faut l'installer séparément, comme ci-dessous.
Si vous souhaitez installer devkitpro séparément, indiquez le chemin de votre installation personnelle dans **File → Settings**.

**Windows.** Téléchargez l'installateur sur la [page officielle de devkitPro](https://devkitpro.org/wiki/Getting_Started), lancez-le et cochez **GBA Development** quand il propose les composants.

**Linux (Debian, Ubuntu).** Avec le paquet `.deb` ou `.rpm`, ou le script `install.sh`, une seule commande suffit :

```bash
backstage-setup-devkitpro
```

Sans ces paquets (AppImage), ou pour le faire à la main, dans un terminal :

```bash
wget https://apt.devkitpro.org/install-devkitpro-pacman
chmod +x ./install-devkitpro-pacman
sudo ./install-devkitpro-pacman
sudo dkp-pacman -S gba-dev
```

Pour lancer la ROM, il faut aussi **l'émulateur** qui est l'environnement qui simule votre console.
Vous pouvez le télécharger séparément depuis le site officiel [mGBA](https://mgba.io/downloads.html)

## Désinstaller Backstage

**Windows.** Désinstallez Backstage depuis les paramètres de Windows (Applications) ou avec `Uninstall.exe` dans le dossier d'installation. Vos projets et votre configuration sont conservés. Cochez **Désinstallation propre** pour supprimer aussi la configuration de Backstage, ses fichiers temporaires et son dossier `plugins`.

**Linux.** Avec le paquet `.deb` ou `.rpm`, la commande suivante retire Backstage, sa configuration et ses fichiers temporaires (elle demande confirmation avant) :

```bash
backstage-clean-uninstall
```

Pour ne retirer que le programme et garder la configuration : `sudo apt remove backstage` ou `sudo dnf remove backstage`.

Dans tous les cas, vos projets (le dossier `BackstageProjects` de votre dossier personnel), devkitPro et mGBA ne sont jamais supprimés.

## Le parcours

1. [Premiers pas](first-steps.md) : ouvrir le projet Platformer, le lancer, changer la vitesse du personnage, varier un ennemi.
2. [Se repérer dans l'éditeur](overview/editor-tour.md) : les six zones de la fenêtre, les écrans et les raccourcis.
3. [Comprendre un projet](overview/understanding-a-project.md) : ressources, acteurs, et les gestes créer, importer, modifier.
4. [Le dossier assets](overview/assets-folder.md) : où vivent vos fichiers et l'onglet **Disk**.
5. [Importer votre première ressource](overview/first-import.md) : depuis l'éditeur, ou depuis le dossier assets.
6. [Tutoriel : votre première scène jouable](first-playable-scene.md) : donner un sprite à l'acteur d'un nouveau projet, le déplacer par script, lancer la ROM.

## Continuer

- Pour assembler un jeu entier, suivez [Un mini-jeu de plateforme](mini-game.md).
- Pour un sujet précis (déplacement, collisions, caméra, prefabs, dialogues, dégâts...), ouvrez le [guide](../guides/index.md) correspondant : chacun se lit seul.
- Pour écrire du comportement, passez au [guide de scripting](../scripting.md).
- Pour comprendre une erreur de compilation, lisez d'abord le fichier et la ligne cités dans l'onglet **Diagnostics** : l'erreur est généralement liée à l'élément ou au script concerné.

```{toctree}
:hidden:
:maxdepth: 1

Premiers pas <first-steps>
Se repérer dans l'éditeur <overview/editor-tour>
Comprendre un projet <overview/understanding-a-project>
Le dossier assets <overview/assets-folder>
Importer une première ressource <overview/first-import>
Tutoriel : première scène jouable <first-playable-scene>
Tutoriel : mini-jeu de plateforme <mini-game>
```
