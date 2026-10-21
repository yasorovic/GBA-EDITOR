# Documentation de développement

Ces documents expliquent des choix internes de Backstage. Ils s'adressent aux personnes qui
modifient l'éditeur, pas aux personnes qui créent un jeu.

- [Todo](TODO.md) : notre document de travail (pistes, décisions en cours, chantiers ouverts).
- [Textes de l'interface](ui-text.md) : catalogues, traductions et contrôles des textes de
  l'éditeur.
- [Pipeline de rendu des polices](font-render-pipeline.md) : préparation des polices utilisées
  par le moteur.
- [Cartouches : correspondances matérielles et photos](cartridge-hardware-matrix.md) : cartes,
  composants observés, jeux de référence et inventaire des visuels à réunir.

- [Scripting : la chaîne Lua → C](scripting-internals.md) : catalogue d'API, grammaire, domaines, séquences,
  état des prefabs poolés.
- [Éléments d'interface](ui-elements.md) : `UILayout`, nœud et asset, chemin BG/OBJ, fonds, listes.
- [Textes et polices](texts-and-fonts.md) : notices, libellés, table de chaînes, balisage, pipeline des polices.
- [Build de la ROM, sauvegarde et compression d'assets](build-and-assets.md) : pipeline en neuf étapes, journal,
  SRAM, fonds et sprites.
- [Packaging et environnement de dev](packaging.md) : Nuitka, NSIS, GitHub Releases, venv figé sur la CI.
