# Pourquoi développer pour la Game Boy Advance ?

La Game Boy Advance offre un cadre de création : un écran de **240 × 160 pixels**, des ressources mémoire limitées et un matériel pensé pour les sprites, les décors en tuiles et les palettes. Ces contraintes influencent la composition des scènes, les animations et la manière de concevoir un jeu.

**Ces limites peuvent aussi nourrir la créativité.** Avec peu de pixels, une silhouette, une couleur ou quelques images d'animation doivent suffire à rendre un personnage reconnaissable. Un petit nombre de boutons invite à imaginer des actions simples à comprendre, mais riches dans leurs usages. Réutiliser un décor, un motif ou une mécanique peut devenir un choix de mise en scène autant qu'une économie de ressources.

Ce cadre aide à choisir ce qui compte dans un projet : la lisibilité d'une scène, la sensation d'un mouvement, le rythme d'un niveau. Il laisse de la place pour expérimenter avec le pixel art, le son et le gameplay, et pour chercher des solutions personnelles à des contraintes communes. Développer pour la GBA, c'est aussi prolonger la vie d'une console en lui apportant de nouveaux jeux, avec la possibilité de les voir fonctionner sur le matériel d'origine.

La console dispose de 32 768 couleurs possibles. Leur utilisation dépend du mode graphique : les décors en tuiles et les sprites utilisent des palettes, tandis que certains modes bitmap permettent de choisir directement la couleur de chaque pixel. Le nombre de couleurs affichables ne se résume donc pas à une limite unique. Le guide [Tonc](https://gbadev.net/tonc/bitmaps.html) explique ces différents modes.

Backstage prend en charge une partie de la préparation des ressources et affiche des indicateurs pour certains budgets matériels, notamment les sprites, les tuiles et les palettes. Ces aides permettent d'aborder progressivement les contraintes de la console. Elles ne garantissent pas à elles seules les performances du jeu : la complexité des scènes et des scripts reste à prendre en compte et à tester.

## Est-ce légal de développer pour la Game Boy Advance ?

Créer un jeu original pour la GBA relève du développement **homebrew**. Vous devez notamment respecter les droits sur les contenus utilisés. La page {ref}`Licence <legal-homebrew>` détaille cette question et les conditions d'utilisation de Backstage.
