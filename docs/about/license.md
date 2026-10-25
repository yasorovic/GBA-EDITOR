# Licence

Trois questions reviennent toujours : *que puis-je faire avec Backstage ?*, *que puis-je faire de mon jeu ?* et *qu'y a-t-il d'autre dans la boîte ?* Cette page répond aux trois, simplement. Les textes légaux, eux, font foi : chaque réponse renvoie vers eux.

```{note}
Cette page explique, elle ne remplace pas les textes de licence et n'est pas un conseil juridique. En cas de doute sur un projet commercial, demandez conseil à une personne compétente.
```

## Votre jeu vous appartient

C'est le point le plus important, alors le voici d'abord.

Le jeu et la ROM que vous créez avec Backstage sont à vous. Vous pouvez les **vendre, les publier ou les garder pour vous**, sans redevance et sans autorisation à demander à personne.

Pour fabriquer votre ROM, Backstage ajoute à votre projet un petit moteur de jeu, le **runtime**. Il est sous licence [zlib](https://github.com/yasorovic/GBA-EDITOR/blob/main/runtime/LICENSE), l'une des plus permissives qui existent : vous n'avez aucune mention à glisser dans votre jeu ni dans sa page de vente.

Une seule responsabilité reste de votre côté : **ce que vous importez**. Vos images, vos sons et vos musiques doivent être les vôtres, ou être utilisables légalement. Backstage ne le vérifie pas.

## L'éditeur est un logiciel libre

L'éditeur lui-même (la fenêtre où vous travaillez) est publié sous licence [GPL-3.0](https://github.com/yasorovic/GBA-EDITOR/blob/main/LICENSE). En pratique, vous avez le droit de :

- l'**utiliser**, pour n'importe quel projet, personnel ou commercial ;
- l'**étudier** : tout le code est public ;
- le **modifier** pour l'adapter à vos besoins ;
- le **redistribuer**, modifié ou non.

La contrepartie de la GPL est simple : si vous redistribuez Backstage ou une version modifiée, vous la redistribuez sous la même licence, avec ses sources. Elle ne touche pas aux jeux que vous créez avec : la licence de l'éditeur ne s'étend pas à votre ROM.

## Ce qui vient d'ailleurs

Backstage repose sur le travail d'autres personnes. L'application embarque notamment Qt (l'interface), Python, Pillow et NumPy (le traitement des images), FreeType (les polices), FFmpeg (l'audio), ainsi que la police Balsamiq Sans et des jeux d'icônes. Chacun garde sa propre licence, et ces licences sont compatibles avec la distribution de Backstage.

Deux outils ne sont pas inclus : **devkitPro** (qui compile la ROM) et **mGBA** (qui la lance). Vous les installez vous-même, sous leurs propres conditions.

La liste complète, avec les versions et les textes, se trouve dans le fichier [THIRD-PARTY-NOTICES](https://github.com/yasorovic/GBA-EDITOR/blob/main/THIRD-PARTY-NOTICES.md).

(legal-homebrew)=

## Est-ce légal de développer pour la Game Boy Advance ?

Créer un jeu original compatible avec une console existante n'est pas, en soi, interdit. On parle de **homebrew** pour ces créations indépendantes. Une ROM peut donc être le fichier de votre propre jeu.

Votre projet doit respecter les droits sur le code, les images, les personnages et les musiques qu'il utilise, ainsi que les licences des outils et bibliothèques employés. Le fait de viser la GBA ne donne aucune autorisation de reprendre le contenu des jeux Nintendo ou d'autres créateurs. En France, le [Code de la propriété intellectuelle](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006278911) encadre notamment la reproduction des œuvres.

La création du jeu et les moyens utilisés pour l'exécuter sont des questions distinctes : les règles sur les dispositifs de contournement et la distribution peuvent varier selon les pays. Backstage est un projet indépendant, sans affiliation avec Nintendo.

### Une ROM est-elle forcément une copie de jeu ?

Non. Le fichier `.gba` produit par Backstage contient le programme et les ressources de votre projet, avec le moteur d'exécution et les bibliothèques nécessaires. Le format ROM désigne ici le fichier destiné à la console ; il ne dit rien, à lui seul, sur la provenance ou la légalité de son contenu.

Vous pouvez créer et distribuer votre propre jeu en respectant les droits sur ses contenus et les licences de ses composants. Copier ou diffuser un jeu existant sans autorisation est une autre question : le fait de pouvoir l'ouvrir dans un émulateur ne donne aucun droit de le redistribuer.

### mGBA et le BIOS de la console

Un émulateur reproduit le fonctionnement d'une machine par logiciel. Il faut distinguer ce programme, les jeux qu'il exécute et le **BIOS**, le petit programme interne de la console qui assure notamment son démarrage et certaines fonctions utilisées par les jeux.

[mGBA dispose de sa propre implémentation des fonctions du BIOS](https://github.com/mgba-emu/mgba#features). Il peut ainsi exécuter des jeux sans vous demander de fournir une copie du BIOS Nintendo. Vous pouvez tester votre ROM homebrew avec cette implémentation intégrée, sans télécharger de BIOS Nintendo ni de ROM commerciale.

Cette possibilité ne signifie pas que mGBA serait le seul émulateur légal, ni qu'un émulateur qui utilise un BIOS externe serait automatiquement illégal. Les droits sur l'émulateur, sur le BIOS éventuellement fourni et sur chaque jeu s'apprécient séparément. Utiliser mGBA ne rend donc pas légal un fichier obtenu ou diffusé sans les droits nécessaires.

## Un mot sur Nintendo

Backstage est un projet indépendant. Il n'est ni affilié à Nintendo, ni approuvé par Nintendo. *Game Boy Advance* est une marque de Nintendo, utilisée ici seulement pour désigner la console que Backstage cible.

## En résumé

| Je veux… | C'est permis ? | Sous quelle licence |
| --- | --- | --- |
| Vendre ou publier un jeu fait avec Backstage | Oui, sans redevance | Le jeu est à vous ; le runtime est sous [zlib](https://github.com/yasorovic/GBA-EDITOR/blob/main/runtime/LICENSE) |
| Utiliser Backstage pour un projet commercial | Oui | [GPL-3.0](https://github.com/yasorovic/GBA-EDITOR/blob/main/LICENSE) |
| Lire et modifier le code de l'éditeur | Oui | [GPL-3.0](https://github.com/yasorovic/GBA-EDITOR/blob/main/LICENSE) |
| Redistribuer une version modifiée de l'éditeur | Oui, sous GPL-3.0 et avec ses sources | [GPL-3.0](https://github.com/yasorovic/GBA-EDITOR/blob/main/LICENSE) |
| Savoir ce que contient l'application | Liste complète | [THIRD-PARTY-NOTICES](https://github.com/yasorovic/GBA-EDITOR/blob/main/THIRD-PARTY-NOTICES.md) |
