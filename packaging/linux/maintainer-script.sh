#!/bin/sh
# Après installation et après désinstallation (.deb et .rpm) : rafraîchit les bases
# du bureau pour que le type MIME .project et le lanceur soient pris en compte.
# Jamais d'échec : l'absence de ces outils (serveur sans bureau) n'est pas une erreur.
command -v update-mime-database >/dev/null 2>&1 && update-mime-database /usr/share/mime >/dev/null 2>&1
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database /usr/share/applications >/dev/null 2>&1
exit 0
