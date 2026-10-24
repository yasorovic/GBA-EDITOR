# Construire la documentation

La documentation utilisateur reste dans `docs/`, en Markdown. Sphinx la lit directement
avec MyST-Parser, sans conversion intermédiaire en reStructuredText. Le thème Furo fournit
la navigation, les modes clair/sombre et la recherche locale.

## Installation

Depuis la racine du dépôt, avec Python 3.12 ou plus récent :

```bat
python -m venv .venv-docs
.venv-docs\Scripts\python.exe -m pip install -r packaging\requirements-docs.txt
```

Sous Linux/macOS, remplacer `.venv-docs\Scripts\python.exe` par `.venv-docs/bin/python`.

## Construire et consulter

```bat
.venv-docs\Scripts\python.exe -m sphinx -b html -W --keep-going docs docs/_build/html
```

Sous Windows, `docs\build.bat` construit le site et ouvre directement la page d’accueil.

Ouvrir ensuite `docs/_build/html/index.html`. Les pages, styles et l'index de recherche sont locaux :
aucun serveur n'est nécessaire pour consulter la documentation. Pour prévisualiser avec un
serveur, exécuter `python -m http.server --directory docs/_build/html`, puis ouvrir `http://localhost:8000`.

`-W --keep-going` fait échouer la construction en cas d'avertissement tout en vérifiant
l'ensemble des pages. Après une modification de configuration, ajouter `-E -a` pour
reconstruire entièrement le site. Le dossier `docs/_build/` est généré et ignoré par Git. Ne pas modifier ses fichiers :
ils sont reconstruits depuis les sources Markdown.

## Modifier les pages

Conserver les fichiers `.md`, les liens relatifs et les blocs de code habituels. La navigation
est définie par la directive `toctree` dans `docs/index.md` : le motif `**` ajoute
automatiquement les nouvelles pages, y compris dans les sous-dossiers. Le premier titre
de la page devient son libellé. Les guides existants gardent leur ordre ; les autres pages
sont ajoutées par chemin alphabétique. Les dossiers organisent les sources ; ils ne créent
pas de rubrique vide dans le menu. Les fichiers `.rst` sont également acceptés si nécessaire.

Les directives Sphinx peuvent s'écrire directement en Markdown MyST, par exemple :

````markdown
```{note}
Le jeu utilise des coordonnées en pixels.
```
````

La configuration et les couleurs se trouvent dans `docs/conf.py`, les quelques règles de
mise en page dans `docs/stylesheets/backstage.css`, et les logos dans `docs/assets/`.

## Publication sur GitHub Pages

Dans les paramètres du dépôt GitHub, ouvrir **Settings > Pages**, puis choisir
**GitHub Actions** dans **Build and deployment > Source** (à faire une seule fois).

Le workflow `.github/workflows/docs.yml` construit et publie la documentation après un
push sur `main` qui modifie les sources `docs/`, les dépendances documentaires ou le workflow.
Il peut aussi être lancé manuellement depuis **Actions > Documentation > Run workflow**
en choisissant `main`.

Les pull requests construisent le site et fournissent une archive `documentation` à
télécharger dans leur exécution Actions, sans publier sur le site public. Une erreur ou
un avertissement Sphinx empêche la publication ; la version précédente reste en ligne.

Seul le contenu généré de `docs/_build/html/` est publié. Le workflow ne pousse aucune
branche générée et utilise le jeton GitHub Actions fourni automatiquement, sans secret
personnel à ajouter. L'URL du site publié apparaît dans le job `deploy`.
