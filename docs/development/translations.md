# Traduire l’éditeur

Les textes de l’interface sont des catalogues JSON : un **maître** en anglais
(la source) et un fichier par langue, joints **par clé**. Une clé absente d’une
traduction s’affiche en anglais, jamais en blanc : on peut donc traduire par
étapes, sans rien casser.

Ce dossier explique comment participer ; les fichiers eux-mêmes restent à côté
du code qui les lit.

## Où sont les fichiers

| Catalogue | Contenu | Maître (EN) | Français |
|---|---|---|---|
| Libellés | boutons, menus, titres, infobulles | [labels.json](./editor/ui/common/labels/labels.json) | [labels_fr.json](./editor/ui/common/labels/labels_fr.json) |
| Notices | messages d’information avec un ton | [notices.json](./editor/ui/common/notices/notices.json) | [notices_fr.json](./editor/ui/common/notices/notices_fr.json) |

## Langues existantes

| Langue | Code | Rôle | Avancement |
|---|---|---|---|
| English | — | langue source (le maître) | complète par définition |
| Français | `fr` | première traduction | libellés : 1291 / 1955 · notices : 1 / 55 |

Le français est en avance sur l’interface : les nouveaux écrans y reçoivent
leur traduction en même temps que leur texte anglais. Les clés manquantes en
`fr` sont celles qu’il reste à traduire.

## Corriger ou compléter une traduction existante

1. Repérer une clé dans le maître anglais, par exemple :
   `"common.cancel": { "text": "Cancel" }`.
2. L’ajouter (ou la corriger) dans le fichier de la langue, **avec la même clé** :
   `"common.cancel": { "text": "Annuler" }`.
3. Garder les `{paramètres}` tels quels : `"Créer « {name} »"`. Une traduction
   dont les paramètres diffèrent du maître est refusée par les contrôles.
4. Pour un pluriel, fournir les deux formes comme dans le maître :
   `{ "singular": "{n} fichier", "plural": "{n} fichiers" }`.
5. Ne traduire que `text` / `singular` / `plural`. Le ton d’une notice et ses
   métadonnées restent dans le maître.

Les noms techniques restent en anglais dans toutes les langues (`OAM`, `VRAM`,
`prefab`, noms d’assets et de composants, noms d’API). La charte des textes
(infobulles, ton, typographie) est détaillée dans
[docs/development/ui-text.md](./docs/development/ui-text.md).

## Ajouter une nouvelle langue

1. Copier `labels_fr.json` en `labels_<code>.json` (par exemple `labels_es.json`)
   et faire de même pour les notices : `notices_<code>.json`.
2. Remplacer les textes ; supprimer les clés pas encore traduites si on préfère
   les laisser en anglais.
3. La langue apparaît d’elle-même dans les réglages dès qu’un fichier existe.
   Pour qu’elle porte son nom (« Español ») plutôt que son code, l’ajouter à
   `_LANGUAGE_NAMES` dans [catalog.py](./editor/ui/common/catalog.py).

## Vérifier avant de proposer

Depuis la racine du dépôt :

```bash
python tools/check_ui_text.py
python tools/check_architecture.py
```

Le premier valide le JSON, les clés et les paramètres de chaque traduction ; le
second vérifie que chaque catalogue est cohérent avec le code.

## Proposer le résultat

Ouvrir une *pull request* qui ne touche que les fichiers de traduction. Une
traduction partielle est la bienvenue : dire simplement quels écrans ou quelles
clés elle couvre.
