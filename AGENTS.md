# Consignes de travail pour Codex

Les consignes communes de Backstage sont dans `.claude/CLAUDE.md`.
Les lire au début de chaque session et les appliquer aussi aux travaux de Codex.

## Mémoire partagée

- Lire `.claude/memory/MEMORY.md` au démarrage, puis les fiches utiles au travail en cours.
- Enregistrer les nouvelles informations durables dans `.claude/memory/`, en mettant à jour les fiches existantes plutôt que de créer une mémoire séparée pour Codex.
- Avant de toucher une zone, lire les consignes correspondantes dans `.claude/rules/` (interface, scripting/runtime ou documentation).
- Avant un chantier de code, lire `internal/development/TODO.md` et `internal/development/ARCHITECTURE.md`, examiner le code et annoncer les fichiers à modifier.
- Les fichiers actuels du dépôt et les décisions explicites de l'utilisateur priment sur les résumés historiques.

## Documentation actuelle

Confirmation du 2026-10-26 : le site utilise Sphinx + MyST + Furo.
Configuration : `docs/conf.py`. Sources publiques : `docs/`.
Dépendances : `packaging/requirements-docs.txt`.
Déploiement GitHub Pages : `.github/workflows/docs.yml`.
MkDocs et Zensical sont des pistes historiques, pas la chaîne actuelle.
Les documents de travail internes restent dans `internal/`.

## Précautions essentielles

- Git en lecture seule sans accord explicite pour chaque opération d'écriture.
- Tests ciblés seulement ; pas de suite complète sans accord.
- Aucun script écrivant dans `Project Demo/*` sans accord pour ce script précis.
- `.claude/` et `internal/` sont locaux et ne doivent pas être publiés.
