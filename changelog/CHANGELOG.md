# Changelog

Une entrée courte par version **livrée**, dans l'ordre numérique des versions (une version
reste une identité, pas un rang, voir [ROADMAP.md](../ROADMAP.md)). Pour le détail complet
d'une version (décisions verrouillées, pièges rencontrés, mesures), voir
[archives/](archives/). Pour ce qui reste à faire, voir [ROADMAP.md](../ROADMAP.md).

## v0.2 - Gestion des palettes de couleurs

Centralisez les palettes du projet et recolorez vos décors sans modifier les images sources.
Un écran dédié permet de créer, importer et ajuster les couleurs.

→ [détail](archives/v0.2.md)

## v0.3 - Background vivant, texte et interface in-game

Affichez les textes et l'interface de votre jeu avec vos propres polices. Pilotez les
calques du décor, les fenêtres et les mélanges de couleurs depuis les scripts.

→ [détail](archives/v0.3.md)

## v0.4 - Animation de décor

Animez les éléments du décor et changez les palettes pendant le jeu. Les animations
préparées dans l'éditeur sont intégrées à la ROM.

→ [détail](archives/v0.4.md)

## v0.5 - Sauvegarde (SRAM)

Enregistrez la progression du joueur dans des emplacements de sauvegarde. Les données
restent lisibles lorsque les variables du jeu évoluent.

→ [détail](archives/v0.5.md)

## v0.6 - Polish de la boucle de jeu

Affinez les déplacements avec le suivi de caméra, les collisions sur les pentes et
les transformations de sprites. Ajoutez des fondus, secousses et effets visuels pour
renforcer les actions du jeu.

→ [détail](archives/v0.6.md)

## v0.7 - Structures de données

Organisez les données du jeu dans des tableaux et écrivez des actions successives
avec des attentes. Les constructions Lua non prises en charge sont signalées
à la ligne concernée.

→ [détail](archives/v0.7.md)

## v0.8 - Son : la musique par scène, les transitions, le mixage

Associez une musique à chaque scène et réglez les transitions, jingles et effets
depuis l'écran de mixage. Seules les musiques utilisées sont intégrées à la ROM.

→ [détail](archives/v0.8.md)

## v0.9 - Traduction des jeux créés avec l'éditeur

Traduisez les textes du jeu et permettez au joueur de changer de langue. Une police
de remplacement affiche les caractères absents de la police active.

→ [détail](archives/v0.9.md)

## v0.10 - Distribution Linux

Utilisez l'éditeur sous Linux grâce au paquet AppImage. Sous Linux comme sous Windows,
un double-clic sur le fichier `.project` ouvre le projet.

→ [détail](archives/v0.10.md)

## v0.11 - Traduction de l'éditeur (infra)

Choisissez la langue de l'éditeur au démarrage. Les libellés et messages sont regroupés
pour faciliter leur traduction, avec des aides présentées de façon cohérente.
La traduction française reste à venir.

→ [détail](archives/v0.11.md)

## v0.12 - Vue d'ensemble (graphe des scènes)

Visualisez les scènes et leurs transitions dans un graphe. Regroupez les scènes,
modifiez la destination d'une transition par glisser-déposer et ouvrez le script
correspondant d'un double-clic.

→ [détail](archives/v0.12.md)

## v0.14 - Diagnostic (ce que le jeu fait, et ce qu'il coûte)

*Livrée le 2026-08-20.*

Suivez les messages de débogage et le coût du jeu en temps de calcul et en sprites
dans mGBA. Basculez entre les modes Debug et Release depuis le projet.

→ [détail](archives/v0.14.md)

## v0.15 - Visibilité des éléments d'interface

Affichez ou masquez les textes, panneaux et images depuis l'éditeur ou les scripts.
Masquer un panneau masque aussi tous ses éléments enfants.

→ [détail](archives/v0.15.md)

## v0.16 - L'API : la règle de construction, et le rangement

Retrouvez les commandes de script dans huit rubriques centrées sur les objets du jeu.
Des noms et des actions communs rendent l'API plus cohérente à apprendre et à utiliser.

→ [détail](archives/v0.16-api-construction.md)

## v0.17 - Le pool par scène

*Livrée le 2026-09-19.*

Réglez le nombre d'instances de chaque prefab scène par scène. Chaque scène réserve
uniquement les ressources dont elle a besoin, avec un contrôle du budget de sprites
avant la compilation.

→ [détail](archives/v0.17.md)

## v0.18 - La valeur affichée : d'où elle vient

*Livrée le 2026-09-20, première tranche.*

Affichez une valeur locale directement dans un texte écrit dans le script, par exemple
les points de vie. Vous évitez de créer une variable globale pour un affichage ponctuel.

→ [détail](archives/v0.18.md)

## v0.19 - Le sous-pixel

*Livrée le 2026-08-20.*

Réglez les mouvements avec une précision inférieure au pixel. Accélérations, sauts et
reculs conservent leur précision lors des collisions.

→ [détail](archives/v0.19.md)

## v0.20 - L'état du monde : les collections persistantes

*Livrée le 2026-08-20.*

Sauvegardez des collections d'états, comme les coffres ouverts, dans une seule variable
globale à plusieurs cases. Le stockage compact limite la place occupée dans la sauvegarde.

→ [détail](archives/v0.20.md)

## v0.21 - Le texte adressable : le dialogue piloté par la donnée

*Livrée le 2026-08-21.*

Pilotez les dialogues depuis une table de données. Un script peut parcourir les
répliques d'une conversation, qui restent traduisibles.

→ [détail](archives/v0.21.md)

## v0.22 - Menus, listes et curseur

*Livrée le 2026-09-05.*

Créez des menus en liste ou en grille avec navigation et curseur gérés par le moteur.
Affichez un menu et son sous-menu ensemble, puis choisissez lequel reçoit les commandes.

→ [détail](archives/v0.22.md)

## v0.23 - Ce qu'un boss demande

*Livrée le 2026-08-21.*

Construisez des acteurs composés, comme un boss dont les parties se déplacent ensemble.
Répétez des actions avec des attentes et filtrez les collisions entre catégories d'acteurs.

→ [détail](archives/v0.23.md)

## v0.24 - Le projet à l'échelle d'une équipe

*Livrée le 2026-09-19.*

Travaillez à plusieurs avec des fichiers plus faciles à comparer dans Git. Le
chargement à la demande et la réutilisation des conversions accélèrent le travail :
sur le projet mesuré, une compilation sans changement passe de 13,7 à 4,2 secondes.

→ [détail](archives/v0.24.md)

## v0.25 - L'interface possède son chemin matériel

*Livrée le 2026-09-03.*

Ancrez un groupe d'interface à l'écran, au monde ou à un acteur. Réglez son mode de
rendu une seule fois pour tous ses textes et images, par exemple un HUD fixe ou
une bulle qui suit un personnage.

→ [détail](archives/v0.25.md)

## v0.26 - Les polices : sources, assets et aperçu

*Livrée le 2026-09-12.*

Importez des polices PNG, BMFont, TTF ou OTF et réglez leur rendu avec un aperçu
commun aux écrans d'édition. Adaptez la police à chaque langue tout en conservant
les couleurs choisies.

→ [détail](archives/v0.26.md)

## v0.27 - L'éditeur souffle le mot juste

*Livrée le 2026-09-07.*

Écrivez vos scripts avec des suggestions de commandes, variables et noms du projet
sous le curseur. Les propositions suivent l'API disponible et affichent l'aide associée.

→ [détail](archives/v0.27.md)

## v0.28 - Les inputs personnalisés

*Livrée le 2026-09-27.*

Définissez des combinaisons de boutons, des séquences et des axes dans les réglages
du projet. Réutilisez ces commandes par leur nom dans les scripts, avec gestion
des appuis longs et du tampon de saisie.

→ [détail](archives/v0.28.md)
