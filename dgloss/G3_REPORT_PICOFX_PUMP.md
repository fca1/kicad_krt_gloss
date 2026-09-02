# G3 — synthèse globale KRT / dgloss sur picofx_pump

Date : 2026-09-01  
Branche : `gloss_final`  
Version du plugin : `0.21.3`  
PCB : `C:\Users\frant\Documents\kicad_track_gloss_stress\sources\set21\picofx_pump.kicad_pcb`

## Protocole

- 39 nets comparés indépendamment depuis une copie identique du cuivre initial.
- KRT : `smooth_octolinear_chains()`.
- dgloss G3 rapide : candidats canoniques contrôlés par l'adaptateur géométrique KRT exact ; candidats glissants recherchés sur la grille Rust KRT ; validation géométrique KRT exacte obligatoire du remplacement finalement retenu.
- Une passe, vias fixes, aucune passe multinet.
- Longueurs mesurées par KRT avec `net_copper_length()`.
- Grille KRT `0,05 mm`, largeur de référence `0,254 mm`, clearance `0,20 mm`, couches `F.Cu` et `B.Cu`.
- Temps issus d'une exécution unique et donc indicatifs.

## Résultat global

| Mesure | KRT | dgloss G3 rapide |
|---|---:|---:|
| Nets | 39 | 39 |
| Longueur initiale cumulée | 2 289,7343 mm | 2 289,7343 mm |
| Réduction cumulée | 55,2979 mm | 76,7372 mm |
| Temps algorithme cumulé | 1 185,7 ms | 4 668,8 ms |
| Préparation du contexte dgloss | — | 4 982,7 ms |
| Temps dgloss total | — | 9 651,5 ms |
| Résultats invalides | 0 | 0 |
| Victoires / égalités / défaites | 1 / 28 / 10 face à dgloss | 10 / 28 / 1 face à KRT |

dgloss réduit `21,4393 mm` de plus que KRT sur l'ensemble du PCB.

## Comparaison avec le mode dgloss exact

| dgloss | Réduction | Temps algorithme |
|---|---:|---:|
| Contrôle exact de chaque candidat glissant | 84,0213 mm | 89 036,5 ms |
| Recherche rapide sur grille + validation exacte finale | 76,7372 mm | 4 668,8 ms |
| Écart | -7,2841 mm | -84 367,7 ms |

Le mode rapide conserve `91,3 %` du gain du mode exact et divise son temps algorithmique par environ `19,1`. Tous les résultats restent valides selon le contrôle de connectivité KRT, et chaque remplacement émis est validé par les primitives géométriques exactes de KRT.
