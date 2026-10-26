# PoolPlaced

Projet de test d'un acteur **posé** dont l'emplacement est **repris par un spawn** (le pool partagé ne couvre que les
emplacements au-delà des posés ; un posé détruit du même prefab est repris avant le pool). Comme `PoolIngame`, il joue son
scénario lui-même et écrit `PASS` ou `FAIL` dans le log de mGBA.

## Lancer

```
python tools/run_pool_ingame.py --project PoolPlaced
```

## Ce que le scénario vérifie (`assets/scripts/Tests.lua`)

| Test | Vérification |
| --- | --- |
| A | Le posé (`Marcheur`, prefab `Mover`) existe et avance : son `on_update` tourne. |
| B | Détruit, il ne compte plus et son nom ne désigne plus rien. |
| C | Un spawn de `Mover` reprend son emplacement : le nom de la scène le désigne de nouveau. |
| D | L'instance née dans l'emplacement posé est mise à jour (elle avance). |
| E | Une seconde instance naît dans le pool : les deux cohabitent, sont distinctes, et celle du pool avance. |
| F | Tout détruire rend les deux emplacements ; trois naissances les reprennent, et les trois sont atteignables. |
| J | Une chaîne d'acteurs POSÉS `Chef > Bras > Pointe` : les enfants se nomment depuis une référence (`chef.Bras`, `bras.Pointe`), `parent` et `root` remontent la chaîne, détruire le maillon du milieu laisse l'enfant vivant sans parent mais avec le sommet pour racine, détruire le sommet ne laisse plus de racine. |
| L | `actor:clear("Mover")` détruit d'un coup l'instance posée reprise et celles du pool, et rend leur nombre. |

Le compteur `oam=` du log suit aussi le scénario : trois sprites de plus pour la chaîne `Chef > Bras > Pointe` jusqu'au test J,
puis 1 sprite tant que le `Mover` posé vit, 0 une fois détruit, 1 après le spawn qui reprend l'emplacement, 2 avec l'instance du pool.

## Ce qu'il ne couvre pas

Ni l'interaction, ni le rendu visuel : le scénario compte, il ne regarde pas.
