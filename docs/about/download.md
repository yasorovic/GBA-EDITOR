# Télécharger Backstage

Les versions publiées de Backstage sont disponibles sur la page des
[releases](https://github.com/yasorovic/GBA-EDITOR/releases).

```{raw} html
<p class="backstage-downloads">
  <a class="backstage-download backstage-download-blue" data-download="windows" href="https://github.com/yasorovic/GBA-EDITOR/releases"><strong>Windows</strong><span>.exe</span></a>
  <a class="backstage-download backstage-download-blue" data-download="windows-portable" href="https://github.com/yasorovic/GBA-EDITOR/releases"><strong>Windows (portable)</strong><span>.zip</span></a>
  <a class="backstage-download backstage-download-orange" data-download="linux-deb" href="https://github.com/yasorovic/GBA-EDITOR/releases"><strong>Linux</strong><span>.deb</span></a>
  <a class="backstage-download backstage-download-orange" data-download="linux" href="https://github.com/yasorovic/GBA-EDITOR/releases"><strong>Linux</strong><span>.AppImage</span></a>
</p>
```

Choisissez le format correspondant à votre système. La version portable Windows et l'AppImage Linux s'utilisent sans
installation système.

::::{dropdown} Linux command lines

:::{rubric} Installer
:::

Une seule commande télécharge et installe la dernière version adaptée à la distribution
(`.deb`, ou AppImage à défaut) :

```bash
curl -fsSL https://raw.githubusercontent.com/yasorovic/GBA-EDITOR/main/packaging/linux/install.sh | sh
```

Le lanceur s'appelle ensuite `backstage`. Pour installer le paquet `.deb` téléchargé à la main :

```bash
sudo apt install ./Backstage-<version>-amd64.deb
```

L'AppImage s'utilise sans installation : extrayez l'archive `.tar.gz`, puis lancez le fichier `.AppImage`.

:::{rubric} Installer devkitPro
:::

Avec le paquet `.deb` ou le script `install.sh`, une seule commande suffit :

```bash
backstage-setup-devkitpro
```

Avec l'AppImage, ou pour le faire à la main :

```bash
wget https://apt.devkitpro.org/install-devkitpro-pacman
chmod +x ./install-devkitpro-pacman
sudo ./install-devkitpro-pacman
sudo dkp-pacman -S gba-dev
```

:::{rubric} Désinstaller
:::

Avec le paquet `.deb`, la commande suivante retire Backstage, sa configuration et ses
fichiers temporaires (elle demande confirmation avant) :

```bash
backstage-clean-uninstall
```

Pour ne retirer que le programme et garder la configuration : `sudo apt remove backstage`.
Vos projets (le dossier `BackstageProjects` de votre dossier personnel), devkitPro et mGBA ne sont jamais supprimés.

::::

Après le téléchargement, poursuivez la configuration en suivant le [guide utilisateur](../user-guide/index.md).
