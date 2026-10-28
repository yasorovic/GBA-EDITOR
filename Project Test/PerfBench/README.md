# PerfBench

Banc de mesure du **coût CPU** des fonctions et des patrons de l'API Lua. La scène joue des phases de 70 images,
l'une après l'autre ; chacune pose ses acteurs, écrit `PHASE <nom> <n>` dans le log de mGBA, puis le runtime écrit la durée
de chaque image (`frame us=`). Aucune manette n'est nécessaire.

## Lancer

```
python tools/run_perf_bench.py
```

Le script copie le projet dans un dossier temporaire, le construit en **debug** (le chronomètre n'existe que dans ce build),
lance `mgba-sdl -l 8` une vingtaine de secondes et écrit `internal/development/perf_bench.json`.

## Lecture des résultats

- Une phase = la médiane des durées d'image, sans les 10 premières.
- Le **surcoût** est la différence avec la phase `vide`. La part fixe du build debug (environ 265 µs par image, mesurée le
  2026-10-28 : identique en debug et en release pour la charge, seul le fixe change) s'annule dans cette différence.
- Le **coût par unité** divise le surcoût par `n` : par instance pour les phases d'acteurs, par appel pour `count`.
- Mesuré sous mGBA avec BIOS émulé : sert à **comparer** des patrons et à repérer une régression, pas à promettre une durée sur
  console. Une image dure 16 743 µs.

## Les phases

| Phase | n | Ce qu'elle mesure |
| --- | --- | --- |
| `vide` | 0 | La ligne de base. |
| `balles_immobiles` | 100 | Une instance du pool dont le script ne fait rien. |
| `spinners_affines` | 30 | Une instance affine qui tourne (`self.rotation`). |
| `poursuite_directe` | 1 et 50 | `actor:get("Hero", 1)` à chaque image puis `move_to`. |
| `poursuite_en_cache` | 50 | La référence est gardée, `actor:get` seulement si elle est nulle. |
| `poursuite_un_quart` | 50 | La position de la cible n'est relue qu'une image sur quatre. |
| `poursuite_manuelle` | 50 | Un pixel par axe avec `math.sign`, sans `move_to`. |
| `parcours_get_i` | 100 | `for i = 1, actor:count("Bullet") do actor:get("Bullet", i) end`. |
| `spawn_destroy` | 10 | Dix naissances suivies de dix destructions par image. |
| `count` | 100 | Cent appels de `actor:count("Bullet")` par image. |

Ajouter un patron : une phase dans `assets/scripts/Bench.lua` (début, travail par image), et son nom dans la liste `attendues`
de `tools/run_perf_bench.py`.

## Ce que le banc ne couvre pas

- Le coût des **gardes d'acteur** (référence périmée, acteur détruit) : les scénarios ne les déclenchent pas.
- Les coûts qui dépendent du contenu de la scène : collisions contre une carte, nombre de sprites visibles, son.
