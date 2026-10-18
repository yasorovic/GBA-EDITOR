# Le gabarit commun des pop-up — **LIVRÉ**

**Ouvert et livré le 2026-10-17.** Chantier de l'interface de l'éditeur, centralisé
dans `editor/ui/common`, sans modification du jeu produit.

## D'où vient la question

Les messages utilisaient la présentation standard de Qt et ses icônes système.
L'ajout de `BUILD-STUDY.svg` a conduit à définir un gabarit commun inspiré de la
fenêtre de crash, puis à l'appliquer à tous les messages de l'éditeur.

## Ce qui est livré

- **Un composant commun.** `MessageBox`, dans
  [popup.py](../../editor/ui/common/popup.py), reprend les appels d'information,
  d'attention, d'erreur et de confirmation, ainsi que les boîtes à boutons personnalisés.
  Les 22 modules concernés l'importent directement ; le filtre global couvre aussi
  les messages Qt ouverts par des plugins tiers.
- **Une présentation partagée.** Illustration à gauche, proportions conservées ; mascottes
  sur toute la hauteur du contenu, symboles d'attention et de question limités à 72 px et
  centrés verticalement. Texte sur fond transparent et boutons à droite. Les réponses, boutons par défaut,
  annulations et détails dépliables conservent leur fonctionnement.
- **Quatre illustrations.** Information : `BUILD-STUDY.svg` ; attention :
  `Warning_icon.svg` ; question / confirmation : `QuestionMark_icon.svg` ; erreur :
  `BUILD-FAILED.svg`. Les fichiers sont dans `ui/common/CustomIcons` ;
  [eliding_style.py](../../editor/ui/common/eliding_style.py) fournit les mêmes icônes
  de secours. Les couleurs et styles des boutons viennent de `ui/common/theme.py`.
- **La confirmation de fermeture harmonisée.** Les changements non enregistrés utilisent
  le même gabarit et l'illustration de question, avec Enregistrer / Ne pas enregistrer / Annuler.

## Vérification

Les tests ciblés couvrent les quatre types, l'application du gabarit sans filtre global,
les réponses et boutons par défaut, les illustrations personnalisées et les détails
dépliables. Un contrôle des imports empêche les écrans de contourner le composant commun.
Les tests de sauvegarde, suppression, confirmations et édition concernés passent ; les
quatre types ont aussi été contrôlés visuellement.

Le contrôle d'architecture valide la syntaxe, les imports et les dépendances. Il signale
encore des problèmes hors de ce chantier dans le code mort et les catalogues de textes.
