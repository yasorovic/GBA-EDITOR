#!/bin/sh
# Installe la dernière version de Backstage depuis les releases GitHub :
#   curl -fsSL https://github.com/yasorovic/GBA-EDITOR/releases/latest/download/install.sh | sh
#
# Debian/Ubuntu : paquet .deb. Fedora/RHEL/openSUSE : paquet .rpm. Autres distributions :
# l'AppImage, posée dans ~/.local/bin. Le fichier téléchargé est vérifié contre SHA256SUMS.
# Variable BACKSTAGE_VERSION (ex. 0.30.0-alpha) : installe cette version au lieu de la dernière.
set -eu

REPO="yasorovic/GBA-EDITOR"

die() { echo "Erreur : $*" >&2; exit 1; }

[ "$(uname -s)" = "Linux" ] || die "ce script ne couvre que Linux."
[ "$(uname -m)" = "x86_64" ] || die "seul x86_64 est fourni pour l'instant."

if [ -n "${BACKSTAGE_VERSION:-}" ]; then
    VERSION="$BACKSTAGE_VERSION"
    TAG="v$VERSION"
else
    # Le tag est la version précédée de "v" (release.yml l'exige).
    TAG="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
        | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n 1)"
    [ -n "$TAG" ] || die "impossible de trouver la dernière release."
    VERSION="${TAG#v}"
fi
BASE="https://github.com/$REPO/releases/download/$TAG"

# Famille de distribution, d'après os-release.
ID_LIKE_ALL=""
if [ -r /etc/os-release ]; then
    ID_LIKE_ALL="$(. /etc/os-release; echo "${ID:-} ${ID_LIKE:-}")"
fi
KIND=appimage
case " $ID_LIKE_ALL " in
    *" debian "*|*" ubuntu "*) command -v apt-get >/dev/null 2>&1 && KIND=deb ;;
    *" fedora "*|*" rhel "*|*" centos "*|*" suse "*|*" opensuse "*)
        if command -v dnf >/dev/null 2>&1 || command -v zypper >/dev/null 2>&1; then KIND=rpm; fi ;;
esac

case "$KIND" in
    deb) FILE="Backstage-${VERSION}-amd64.deb" ;;
    rpm) FILE="Backstage-${VERSION}-x86_64.rpm" ;;
    *)   FILE="Backstage-${VERSION}-x86_64.AppImage.tar.gz" ;;
esac

if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
    if [ "$KIND" != "appimage" ] && ! command -v sudo >/dev/null 2>&1; then
        die "sudo est requis (ou lancez ce script en root)."
    fi
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# apt (utilisateur _apt) doit pouvoir lire le fichier : mktemp crée en 0700.
chmod 755 "$WORK"
cd "$WORK"

echo "Téléchargement de $FILE..."
curl -fL --progress-bar -o "$FILE" "$BASE/$FILE"
curl -fsSL -o SHA256SUMS "$BASE/SHA256SUMS"
grep " $FILE\$" SHA256SUMS > expected || die "$FILE absent de SHA256SUMS."
sha256sum -c expected >/dev/null || die "empreinte SHA-256 invalide pour $FILE."

case "$KIND" in
    deb)
        $SUDO apt-get install -y "./$FILE"
        ;;
    rpm)
        if command -v dnf >/dev/null 2>&1; then
            $SUDO dnf install -y "./$FILE"
        else
            # Le paquet n'est pas signé.
            $SUDO zypper --non-interactive --no-gpg-checks install "./$FILE"
        fi
        ;;
    appimage)
        mkdir -p "$HOME/.local/bin"
        tar -xzf "$FILE"
        mv "Backstage-${VERSION}-x86_64.AppImage" "$HOME/.local/bin/Backstage.AppImage"
        chmod +x "$HOME/.local/bin/Backstage.AppImage"
        echo "Installé : $HOME/.local/bin/Backstage.AppImage"
        echo "(sur Ubuntu 24.04, l'AppImage demande libfuse2 : sudo apt install libfuse2)"
        ;;
esac

echo
echo "Backstage $VERSION est installé."
if [ "$KIND" != "appimage" ]; then
    echo "Lancez-le avec : backstage"
    echo "Pour compiler des ROM, installez devkitPro : backstage-setup-devkitpro"
else
    echo "Pour compiler des ROM, installez devkitPro : https://devkitpro.org/wiki/Getting_Started"
fi
