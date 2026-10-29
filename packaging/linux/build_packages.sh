#!/bin/sh
# Construit Backstage-<version>-amd64.deb et Backstage-<version>-x86_64.rpm depuis
# l'AppDir déjà assemblé par la CI (release.yml) : l'éditeur Nuitka, les libs xcb
# copiées et la glibc exclue sont donc EXACTEMENT ceux de l'AppImage.
#
# Usage : build_packages.sh <AppDir> <version> <dossier de sortie>
# Prérequis : fpm (gem) et rpmbuild.
set -eu

APPDIR="$1"
VERSION="$2"
OUT="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

# 0.30.0-alpha -> 0.30.0~alpha : le "-" sépare version et révision chez dpkg et rpm,
# et "~" fait trier une préversion AVANT la version finale.
PKGVER="$(printf '%s' "$VERSION" | sed 's/-/~/')"

mkdir -p "$ROOT/opt/backstage" "$ROOT/usr/bin" "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/mime/packages" "$ROOT/usr/share/pixmaps"
cp -r "$APPDIR/usr/bin/." "$ROOT/opt/backstage/"
install -m 755 "$HERE/backstage-launcher" "$ROOT/usr/bin/backstage"
install -m 755 "$HERE/backstage-setup-devkitpro" "$ROOT/usr/bin/backstage-setup-devkitpro"
install -m 755 "$HERE/backstage-clean-uninstall" "$ROOT/usr/bin/backstage-clean-uninstall"
install -m 644 "$HERE/../icon.png" "$ROOT/usr/share/pixmaps/backstage.png"
# Hors AppImage, l'icône n'est plus un fichier "icon" à la racine : elle est cherchée par
# son nom dans le thème, ici /usr/share/pixmaps/backstage.png. Le lanceur s'appelle backstage.
sed -e 's/^Exec=Backstage /Exec=backstage /' -e 's/^Icon=icon$/Icon=backstage/' \
    "$HERE/backstage.desktop" > "$ROOT/usr/share/applications/backstage.desktop"
sed -e 's/<icon name="icon"\/>/<icon name="backstage"\/>/' \
    "$HERE/backstage-project.xml" > "$ROOT/usr/share/mime/packages/backstage-project.xml"
chmod 644 "$ROOT/usr/share/applications/backstage.desktop" "$ROOT/usr/share/mime/packages/backstage-project.xml"
chmod 755 "$ROOT/opt/backstage/Backstage"

mkdir -p "$OUT"
COMMON="--name backstage --version $PKGVER --input-type dir \
  --maintainer Yasorovic --license GPL-3.0 \
  --url https://github.com/yasorovic/GBA-EDITOR \
  --description 'Éditeur de jeux Game Boy Advance' \
  --after-install $HERE/maintainer-script.sh --after-remove $HERE/maintainer-script.sh \
  --chdir $ROOT"

# Les paquets ne tirent pas devkitPro : backstage-setup-devkitpro s'en charge.
eval fpm $COMMON --output-type deb --architecture amd64 --depends "'libc6 (>= 2.35)'" \
    --package "$OUT/Backstage-${VERSION}-amd64.deb" opt usr
eval fpm $COMMON --output-type rpm --depends "'glibc >= 2.35'" --architecture x86_64 \
    --package "$OUT/Backstage-${VERSION}-x86_64.rpm" opt usr
