# Portée des branches et coût des bords sur KiCad 6738

Les branches sont identifiées aux coordonnées natives en nanomètres, sur chaque couche. Un écart de 1 nm ou de 400 nm entre deux axes arrête la sélection dans les deux sens. Cette règle délimite la sélection, indépendamment du contact éventuel entre les surfaces de cuivre. Les parcours de chaîne, de branche en T et de départ de pad comptent désormais les extrémités sur leur couche. Un via ancre les couches de son empilage. En l’absence d’empilage connu, les parcours de simplification conservent un ancrage prudent.

Les 110 tests ciblés couvrent notamment le contact exact, les changements de largeur, les pads, les jonctions, les graines multiples, la mémoire de branches et les vias traversants ou borgnes. Les régressions reproduites avant correction concernaient un écart de 400 nm et une fausse jonction F.Cu/B.Cu.

Sur copies ouvertes par IPC dans KiCad 10.99-6738, /A garde ses deux branches mémorisées et le cuivre hors portée. /B déplace un via. Les deux résultats passent G5 et correspondent au cuivre relu au nanomètre. Undo restaure les UUID et propriétés. Sur la carte avec zones, une branche de trois pistes devient une piste de 30 mm, gain de 4,1421 mm. Après remplissage des deux zones par Gloss, DRC avant et après sur exports réels, sans nouveau remplissage : zéro violation et zéro connexion manquante avec les mêmes règles et cinq contrôles ignorés par défaut.

## Attribution du temps moteur

Six tours avec rotation de l’ordre des trois configurations, processus Python neuf à chaque mesure, même éditeur, même carte et mêmes sélections. Les configurations utilisent le code de topologie précédant ce correctif pour mesurer la régression initiale. Le témoin intermédiaire combine KRT 0.24.1 avec le précédent adaptateur des bords et la fonction rectangulaire extraite du tag précédent dans un module de test externe. Les sources KRT sont intactes. Les temps ci-dessous sont les médianes du moteur en ms, hors import IPC.

| Net | 0.23.1 rectangle | 0.24.1 rectangle | 0.24.1 polygone | Effet KRT à contrôle constant | Effet des bords avec 0.24.1 |
|---|---:|---:|---:|---:|---:|
| /A, branches | 102,40 | 118,65 | 128,20 | +16,25 | +9,55 |
| /B, via | 183,60 | 211,65 | 256,70 | +28,05 | +45,05 |

Lors d'une exécution instrumentée séparée de /B, les trois variantes appellent 2 873 fois le contrôle des bords des segments. Son temps cumulé passe de 7,57 à 120,04 ms entre les deux variantes 0.24.1. Le contrôle final de bord des vias intervient trois fois et cumule moins de 0,1 ms. Les temps absolus sous cProfile incluent le coût de l’instrumentation. L'attribution dépend de ces nets et du contour rectangulaire. Les gains de longueur sont constants à 37,4697 et 105,2678 mm.

[Mesures individuelles et rapports DRC](data/topology_6738.json)
