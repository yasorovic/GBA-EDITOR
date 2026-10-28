# Changelog

> **Numérotation.** Aucune release publique n'existe encore : la version du logiciel est
> `0.1.x` (le numéro de la première release publique sera décidé plus tard ; l'alpha dure jusqu'à `1.0.0-stable`). Les titres `v0.2` à `v0.28` ci-dessous
> sont les **jalons de développement** livrés avant, gardés tels quels ; ils ne sont pas des
> versions du logiciel. Les entrées de release suivront en tête de ce fichier, à partir de `0.1.0-alpha`.

Une entrée courte par jalon **livré**, dans l'ordre numérique des versions (une version
reste une identité, pas un rang). Pour ce qui reste à faire, voir [ROADMAP.md](../ROADMAP.md).

## 0.1.0-alpha - Version de départ (pas encore publiée)

*Le compteur repart de zéro, voir la note ci-dessus.*

Créer un jeu Game Boy Advance de bout en bout depuis l'éditeur, puis le compiler en ROM `.gba`.
Cette première version réunit tout ce qui a été livré jusqu'ici (jalons v0.2 à v0.28, puis les chantiers
importants 0.2 à 0.6, livrés avant toute release publique) :

- **Scènes et décors** : placement des acteurs, collisions et pentes, caméra, fonds animés,
  palettes, polices et sprites importés depuis des images.
- **Scripts** : un Lua simplifié traduit en C, avec complétion, diagnostics et références
  à l'API vérifiées à la construction.
- **Son et texte** : musique par scène, effets, jingles, textes traduisibles, dialogues
  pilotés par des tables de données, menus et listes.
- **Jeu et données** : sauvegarde (SRAM), collections persistantes, sous-pixel, inputs
  personnalisés, projets lisibles par git.
- **Éditeur** : graphe des scènes, éditeur traduit, fenêtre *Updates* qui signale les
  nouvelles versions (vérification désactivable).
- **Assets et disque** : tout ce qui est manipulé vit dans `assets/`, rangé où l'on veut, avec
  l'onglet Disk ; un asset se crée depuis une source ou vide, et se duplique.
- **Texte et données** : l'écran Texte et ses séquences de dialogue, `Text` et `Textbox` écrits dans
  le canvas, l'écran Données pensé pour un jeu.
- **Fonds** : un plan de travail pour poser et cadrer l'image, une compression réglée en direct,
  l'écran Fond (Inpainting, Painting).
- **Interaction avec un acteur** : le joueur désigné, le composant Interactive (appui, maintien, relâchement ;
  recouvrement ou visée dans son regard) et l'événement `on_interact`, sans coût pour les objets qui n'en ont pas besoin.


## v0.2 - Gestion des palettes de couleurs

Centraliser les palettes du projet et recolorer les décors sans modifier les images sources.
Un écran dédié permet de créer, importer et ajuster les couleurs.


## v0.3 - Background vivant, texte et interface in-game

Afficher les textes et l'interface du jeu avec ses propres polices. Piloter les
calques du décor, les fenêtres et les mélanges de couleurs depuis les scripts.


## v0.4 - Animation de décor

Animer les éléments du décor et changer les palettes pendant le jeu. Les animations
préparées dans l'éditeur sont intégrées à la ROM.


## v0.5 - Sauvegarde (SRAM)

Enregistrer la progression du joueur dans des emplacements de sauvegarde. Les données
restent lisibles lorsque les variables du jeu évoluent.


## v0.6 - Polish de la boucle de jeu

Affiner les déplacements avec le suivi de caméra, les collisions sur les pentes et
les transformations de sprites. Ajouter des fondus, secousses et effets visuels pour
renforcer les actions du jeu.


## v0.7 - Structures de données

Organiser les données du jeu dans des tableaux et écrire des actions successives
avec des attentes. Les constructions Lua non prises en charge sont signalées
à la ligne concernée.


## v0.8 - Son : la musique par scène, les transitions, le mixage

Associer une musique à chaque scène et régler les transitions, jingles et effets
depuis l'écran de mixage. Seules les musiques utilisées sont intégrées à la ROM.


## v0.9 - Traduction des jeux créés avec l'éditeur

Traduire les textes du jeu et permettre au joueur de changer de langue. Une police
de remplacement affiche les caractères absents de la police active.


## v0.10 - Distribution Linux

Utiliser l'éditeur sous Linux grâce au paquet AppImage. Sous Linux comme sous Windows,
un double-clic sur le fichier `.project` ouvre le projet.


## v0.11 - Traduction de l'éditeur (infra)

Choisir la langue de l'éditeur au démarrage. Les libellés et messages sont regroupés
pour faciliter leur traduction, avec des aides présentées de façon cohérente.
La traduction française reste à venir.


## v0.12 - Vue d'ensemble (graphe des scènes)

Visualiser les scènes et leurs transitions dans un graphe. Regrouper les scènes,
modifier la destination d'une transition par glisser-déposer et ouvrir le script
correspondant d'un double-clic.


## v0.14 - Diagnostic (ce que le jeu fait, et ce qu'il coûte)

*Livrée le 2026-08-20.*

Suivre les messages de débogage et le coût du jeu en temps de calcul et en sprites
dans mGBA. Basculer entre les modes Debug et Release depuis le projet.


## v0.15 - Visibilité des éléments d'interface

Afficher ou masquer les textes, panneaux et images depuis l'éditeur ou les scripts.
Masquer un panneau masque aussi tous ses éléments enfants.


## v0.16 - L'API : la règle de construction, et le rangement

Retrouver les commandes de script dans huit rubriques centrées sur les objets du jeu.
Des noms et des actions communs rendent l'API plus cohérente à apprendre et à utiliser.


## v0.17 - Le pool par scène

*Livrée le 2026-09-19.*

Régler le nombre d'instances de chaque prefab scène par scène. Chaque scène réserve
uniquement les ressources dont elle a besoin, avec un contrôle du budget de sprites
avant la compilation.


## v0.18 - La valeur affichée : d'où elle vient

*Livrée le 2026-09-20, première tranche.*

Afficher une valeur locale directement dans un texte écrit dans le script, par exemple
les points de vie. Cela évite de créer une variable globale pour un affichage ponctuel.


## v0.19 - Le sous-pixel

*Livrée le 2026-08-20.*

Régler les mouvements avec une précision inférieure au pixel. Accélérations, sauts et
reculs conservent leur précision lors des collisions.


## v0.20 - L'état du monde : les collections persistantes

*Livrée le 2026-08-20.*

Sauvegarder des collections d'états, comme les coffres ouverts, dans une seule variable
globale à plusieurs cases. Le stockage compact limite la place occupée dans la sauvegarde.


## v0.21 - Le texte adressable : le dialogue piloté par la donnée

*Livrée le 2026-08-21.*

Piloter les dialogues depuis une table de données. Un script peut parcourir les
répliques d'une conversation, qui restent traduisibles.


## v0.22 - Menus, listes et curseur

*Livrée le 2026-09-05.*

Créer des menus en liste ou en grille avec navigation et curseur gérés par le moteur.
Afficher un menu et son sous-menu ensemble, puis choisir lequel reçoit les commandes.


## v0.23 - Ce qu'un boss demande

*Livrée le 2026-08-21.*

Construire des acteurs composés, comme un boss dont les parties se déplacent ensemble.
Répéter des actions avec des attentes et filtrer les collisions entre catégories d'acteurs.


## v0.24 - Le projet à l'échelle d'une équipe

*Livrée le 2026-09-19.*

Travailler à plusieurs avec des fichiers plus faciles à comparer dans Git. Le
chargement à la demande et la réutilisation des conversions accélèrent le travail :
sur le projet mesuré, une compilation sans changement passe de 13,7 à 4,2 secondes.


## v0.25 - L'interface possède son chemin matériel

*Livrée le 2026-09-03.*

Ancrer un groupe d'interface à l'écran, au monde ou à un acteur. Régler son mode de
rendu une seule fois pour tous ses textes et images, par exemple un HUD fixe ou
une bulle qui suit un personnage.


## v0.26 - Les polices : sources, assets et aperçu

*Livrée le 2026-09-12.*

Importer des polices PNG, BMFont, TTF ou OTF et régler leur rendu avec un aperçu
commun aux écrans d'édition. Adapter la police à chaque langue tout en conservant
les couleurs choisies.


## v0.27 - L'éditeur souffle le mot juste

*Livrée le 2026-09-07.*

Écrire les scripts avec des suggestions de commandes, variables et noms du projet
sous le curseur. Les propositions suivent l'API disponible et affichent l'aide associée.


## v0.28 - Les inputs personnalisés

*Livrée le 2026-09-27.*

Définir des combinaisons de boutons, des séquences et des axes dans les réglages
du projet. Réutiliser ces commandes par leur nom dans les scripts, avec gestion
des appuis longs et du tampon de saisie.

