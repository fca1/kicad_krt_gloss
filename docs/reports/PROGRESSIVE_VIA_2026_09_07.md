# Via mobile : absorption et progression — prototype du 7 septembre 2026

## Modification expérimentale

`tools/progressive_via.py` est une copie isolée du moteur de via de production,
activée seulement par son contexte de diagnostic. Auto gloss par chaînes
complètes est celui intégré au commit e91b291. Aucun changement de KRT, aucune
activation des petites fenêtres, aucun changement de production, G4 désactivé.

La recherche conserve les intersections octolinéaires analytiques existantes.
Après simplification des pistes à via fixe, les deux segments incidents peuvent
être remplacés simultanément. À longueur et nombre de segments identiques, la
position la plus proche du via est choisie avant le départage par coordonnées.
Cela évite de traverser inutilement le plateau de longueur entre deux ancrages.

Si un segment s'annule à l'arrivée sur son ancrage, le via est remis immédiatement
en traitement lorsqu'il retrouve exactement deux branches sur deux couches.
On arrête au contact d'un pad, à une jonction multiple, à un autre via ou à du
cuivre verrouillé/graphique. Le contact avec un pad est conservateur : distance
KRT au cuivre du pad <= rayon du via + tolérance. Il empêche également de repartir
d'un pad lors d'une étape ultérieure.

Les deux segments peuvent s'annuler ensemble. L'absence de connecteur n'est alors
plus rejetée à elle seule : le via, la connectivité et le mouvement restent
validés. Aucun validateur KRT n'a été changé ni remplacé. Les objets intermédiaires
créés puis absorbés sont exclus des suppressions natives et des sorties finales.
Les événements de déplacement restent dans le journal de changements.

Le contact avec les pads utilise **SpatialIndex de KRT**, construit une fois par
contexte puisque les pads restent fixes. La cellule est dimensionnée pour couvrir
le rayon maximal des vias, sans changer le pas de routage ou une clearance.
Les couches réellement traversées sont obtenues par `via_copper_layers` de KRT,
y compris les couches internes d'un via traversant/enterré.

## Tests synthétiques

10 tests dédiés passent, 23 tests ciblés distincts au total avec les vérifications
auto gloss, corridor et transaction de centering.

| Cas | Résultat |
|---|---|
| Va-et-vient avec trois segments successifs à absorber | Trois déplacements dans le même traitement ; disparition du va-et-vient et arrêt au pad ; G5 valide. |
| Rotation de 90° et orientation diagonale | Même progression en trois événements ; G5 valide. |
| Segment suivant sur In2.Cu, via traversant | Progression conservée, avec prise en compte des couches internes. |
| Pad intermédiaire | Arrêt après la première absorption. |
| Jonction multiple | Arrêt après la première absorption, sans choisir arbitrairement une branche. |
| Deux segments exactement superposés devenant nuls | 12 mm économisés dans l'exemple ; pipeline et G5 valides avec corridor False et True. |
| Via déjà entre ses deux ancrages colinéaires | Aucun mouvement sans gain. |
| Obstacle sur le mouvement, arrivée libre | Mouvement rejeté lorsque le corridor est activé. |

## Carte indiquée par l'utilisateur : test_centering2, label /B

Source : `C:/Users/frant/Downloads/kicad_centering/test_centering1/test_centering2.kicad_pcb`.
Net /B, id5 dans ce chargement. Fichier source inchangé, SHA256 conservé dans les
données. Aucun Centering exécuté : c'est le Gloss du net B qui est comparé.
Chaque configuration repart de la carte d'origine, autres nets fixes.

| Corridor | Variante | Gain final | Temps appels + confirmation | G5 |
|---|---|---:|---:|---|
| False | Production actuelle | 108,0247 mm | 0,164 s | valide |
| False | Prototype | 108,0247 mm | 0,159 s | valide |
| True | Production actuelle | 108,0247 mm | 0,431 s | valide |
| True | Prototype | 108,0247 mm | 0,415 s | valide |

Chaque cas comporte un appel productif puis une confirmation inchangée. Ces
petits écarts de temps ne constituent pas une preuve d'accélération.
Sans corridor : via (97 ; 56,1) → (135,9 ; 74,4), dans G3.4.
Avec corridor : (97 ; 56,1) → (114,7 ; 63), dans G3.1, puis → (135,9 ; 74,4), dans G3.4.
Production et prototype suivent les mêmes positions et s'arrêtent au pad.
**B valide ce déplacement réel, mais ne révèle pas d'amélioration par le prototype.**
Les absorptions successives nouvelles sont démontrées par les exemples synthétiques.

## tildagon_base : 164 nets indépendants, G4 désactivé

Une séquence par net et par variante, voisins fixes à leur géométrie originale,
aucun préchauffage ni répétition statistique. Corridor=False, grille 0,1 mm,
confirmation par appel sans changement. Limites de 50 appels/120 s par net non
atteintes. Les gains sont des sommes d'expériences indépendantes, pas une carte
finale combinée. La référence auto gloss est la mesure historique conservée.

| Mesure | Auto gloss de référence | Auto gloss + prototype final |
|---|---:|---:|
| Temps appels jusqu'à confirmation | 55,7866 s | 55,1651 s |
| Nets/sec, 164 nets uniques | 2,94 | 2,97 |
| Gain final | 90,0613 mm | 87,9928 mm |
| Appels totaux | 329 | 329 |
| Nets avec plusieurs appels productifs | 23 | 23 |
| G5 valide | 164/164 | 164/164 |

Temps du même ordre (-1,1 % observé, référence historique), mais **2,0685 mm de
réduction perdue**. Les écarts de gain non négligeables sont :

| Net | Nom | Différence de gain prototype − référence |
|---:|---|---:|
| 112 | /I2C/SCL_E | -1,002691 mm |
| 150 | 3V3_SYS | -0,788873 mm |
| 161 | /TOP_HS1 | +0,147333 mm |
| 170 | /ESP_TXD | -0,424264 mm |

Aucune erreur, aucun cycle externe ni budget atteint. La confirmation requiert
24 nets en un appel, 117 en deux, 22 en trois et un en cinq. Le protocole vérifie
les autres nets, la restauration et le SHA256 source. G5 vérifie le cuivre modifié
et les partitions terminales ; ce n'est pas un DRC KiCad complet.

Les règles nouvelles d'arrêt au pad et de départage des positions modifient les
choix possibles. Les compteurs seuls ne permettent pas d'attribuer précisément
les pertes à l'une de ces règles : une trace géométrique ciblée est nécessaire.
On ne présente donc pas ces résultats comme une amélioration globale du Gloss.

## Mise au point du temps réel

Deux versions préparatoires distinctes ont également été mesurées, une seule
séquence par version : 63,7051 s avec recherche linéaire des contacts pads, puis
56,3522 s avec index KRT. La version finale ajoute la couverture KRT de toutes les
couches et évite de rechercher les ancrages si le via n'a pas bougé : 55,1651 s.
Les trois versions ont produit les mêmes gains finaux par net sur cette carte.
Ce sont des évolutions de code, pas des répétitions statistiques. Les données
finales et le cas B sont archivés dans `docs/reports/data` ; les sorties de mise
au point restent dans `.build/progressive_via_tildagon.json` et
`.build/progressive_via_indexed_tildagon.json`.

## Limites et décision

Conserver comme prototype, **ne pas intégrer à ce stade**. Le défaut du connecteur
vide et la progression après absorption sont traités, mais les régressions de
qualité sur les trois nets doivent être expliquées.

Ce prototype ne cherche pas encore un optimum conjoint via/coudes mobiles. Il
conserve les candidats d'intersection actuels : si l'ancrage de destination est
bloqué alors qu'une position intermédiaire serait valide, cette position peut
encore manquer. Il ne résout donc pas tous les blocages colinéaires en présence
d'obstacles et n'ajoute aucune marche à petits pas pour les contourner.
