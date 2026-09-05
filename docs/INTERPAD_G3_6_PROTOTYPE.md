# G3.6 — premier cas Interpad

## Périmètre

Ce premier prototype ne déplace aucun segment. Il cherche une porte formée par
deux pads, vérifie qu'un seul segment de piste traverse l'espace libre, puis
mesure l'axe admissible après application des clearances.

Le code KRG n'ajoute aucune primitive Rust. Il réutilise les éléments KRT
existants : `SpatialIndex`, `pad_copper_layers` et
`point_to_pad_distance`. Le calcul est indépendant de la grille conservatrice.

## Carte et net retenus

- Carte : `magic_keys.kicad_pcb`, dans le jeu `set21`.
- Net : `Net-(A1-D4)` (identifiant 8).
- Couche : `F.Cu`.
- Pads de la porte de référence : `J3.6` et `J3.7`.
- Segment traversant : `(122.936, 55.118) -> (124.206, 53.848)`.

Cette porte est représentative parce que le segment est clairement décentré et
que le passage ne contient aucune seconde piste.

## Mesures de la porte

| Mesure | Valeur |
| --- | ---: |
| Intersection actuelle avec la porte | `(123.825, 54.229)` |
| Axe admissible pondéré | `(124.206, 54.610)` |
| Décalage vers l'axe | `0.538815 mm` |
| Distance cuivre à cuivre entre les pads | `1.892102 mm` |
| Clearance côté J3.6 | `0.2 mm` |
| Clearance côté J3.7 | `0.2 mm` |
| Largeur actuelle de piste | `0.2 mm` |
| Largeur admissible théorique sur l'axe | `1.492102 mm` |

Le même net possède une seconde porte entre `J3.5` et `J3.7`. Son décalage est
nul ; elle confirme que le calcul reconnaît aussi une piste déjà centrée. La
suite du prototype restera centrée sur la première porte.

## Temps

Le chargement de la carte prend environ `20.9 ms`. La détection est mesurée sur
30 répétitions, carte déjà chargée :

| Mesure | Temps |
| --- | ---: |
| Minimum | `5.954 ms` |
| Médiane | `6.112 ms` |
| Maximum | `7.381 ms` |

Le temps de détection comprend la construction de l'index spatial KRT et la
preuve qu'aucune autre piste ne traverse les portes candidates du net.

## Critère actuellement appliqué

Une porte est retenue lorsque les deux pads ont du cuivre sur la couche du
segment, que leur espace cuivre à cuivre est positif, qu'un seul segment de la
carte coupe cet espace et que la largeur actuelle de ce segment tient entre les
deux clearances. La recherche est limitée au net sélectionné dès la nomination
des paires de pads ; l'index des autres pistes reste consulté uniquement pour
établir l'unicité du passage.
