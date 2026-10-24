# Backstage 0.1.0-alpha

Version de développement. Créez un jeu Game Boy Advance depuis une interface visuelle, puis
compilez-le en ROM `.gba`.

- Scènes, acteurs, collisions, pentes, caméra, fonds animés, palettes, polices et sprites.
- Scripts en Lua simplifié, traduits en C, avec complétion et diagnostics.
- Musique, effets et jingles ; textes traduisibles, dialogues et menus pilotés par des données.
- Sauvegarde, inputs personnalisés, projets lisibles par git.
- Assets rangés librement dans `assets/`, onglet Disk, création d'un asset depuis une source ou vide.
- Écran Texte et séquences de dialogue, écran Données ; écran Fond avec plan de travail et compression
  réglée en direct.
- Interaction : désignez le joueur, ajoutez le composant Interactive à un coffre ou un panneau, écrivez `on_interact`.
- Fenêtre *Updates* : recherche, téléchargement et installation d'une mise à jour. Vérification
  automatique au démarrage (désactivable).
