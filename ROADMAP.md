# Roadmap

Les prochains gros chantiers de Backstage et où ils en sont. Ce document décrit des intentions,
pas des promesses : l'ordre et le contenu peuvent bouger au fil des retours.

- Ce qui est déjà livré : [CHANGELOG](changelog/CHANGELOG.md).
- Une ligne par version : [README](README.md).

## Prochaines versions

Il n'y a pas encore de release publique : la version du logiciel est `0.1.x-alpha`. Le moment et le
numéro de la première release publique seront décidés plus tard ; l'alpha dure jusqu'à la première
version stable, `1.0.0-stable`. Chaque chantier important
donne une version `0.Y.0` ; les correctifs et petits chantiers, eux, incrémentent le dernier chiffre.

| Version | Chantier | État |
| --- | --- | --- |
| 0.1 | État actuel | Base : tout ce qui est déjà livré, dont les chantiers Mises à jour, Assets et disque, Texte et données, Fonds, Interaction avec un acteur |
| 0.7 | Jouer son jeu dans le navigateur (itch.io) | Conception faite, développement non commencé |
| 1.0.0-stable | Le pipeline 2D complet (affirmation de capacité) | En route |

### 0.7 : jouer son jeu dans le navigateur

Un jeu fini doit pouvoir se jouer sans installer d'émulateur. Cette version ajoute un outil qui
prend une ROM `.gba` et produit un dossier web prêt à être envoyé sur itch.io, avec un émulateur
compilé pour le navigateur. La ROM n'est pas modifiée.

- Faisabilité vérifiée.
- Reste à faire : tout le développement, puis la vérification sur les principaux navigateurs.

### 1.0.0-stable : le pipeline 2D complet

L'objectif de `1.0.0-stable` : construire un jeu 2D de bout en bout (platformer, metroidvania,
RPG, tactique, gestion). Les versions `0.Y.Z-alpha` avancent vers cet objectif.

- Fait : licences, formats de projet lisibles par git, deux jeux de démo, test d'échelle à 40
  scènes et 200 sprites.
- Reste à faire : des modèles de départ qui enseignent l'API, la documentation utilisateur et la
  stabilisation.

## Plus tard

- **Un lecteur de jeu pour le bureau** : un package Windows qui lance le jeu directement, sans
  interface d'émulateur.
- **Une cible cartouche** : prendre en compte les capacités matérielles réelles des
  cartouches GBA.
- **Annuler et refaire** étendu à davantage d'actions de l'éditeur.

## Hors périmètre

Le multijoueur par câble Link, envisagé après `1.0.0-stable` seulement.

L'interface graphique de Backstage n'est ni un outil de dessin, ni un éditeur de cartes, ni un tracker musical : il
importe images et sons, il ne les crée pas.
