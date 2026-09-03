# Rapport historique — G3.4 — validation des vias complets

Date : 2026-09-02  
Branche : `gloss_final`  
Version du plugin : `0.21.3`

## Périmètre

- reprise du moteur G3.1 sans nouvel algorithme de clearance ;
- parcours des deux chaînes simples complètes autour d'un via mobile ;
- optimisation conjointe de la position du via et des deux portions ;
- via fixe conservé comme articulation sans bloquer les autres vias du net ;
- diamètre, percement, couches, net, attribut `free` et protections conservés ;
- contrôles exacts de clearance et de connectivité fournis par KRT ;
- aucune modification Rust ou des algorithmes KRT.

## Résultats ciblés

| PCB | Vias G3.1 | Vias affinés G3.4 | Gain propre G3.4 | Temps G3.4 | Régression de connectivité |
|---|---:|---:|---:|---:|---:|
| `dispenser.kicad_pcb` | 1 | 0 | 0,0000 mm | 784,7 ms | 0 |
| `picofx_pump.kicad_pcb` | 2 | 0 | 0,0000 mm | 835,7 ms | 0 |
| `ember_he.kicad_pcb` | 1 | 7 | 2,9038 mm | 3 200,9 ms | 0 |

Sur `ember_he`, le gain cumulé KRT et dgloss atteint 34,7218 mm et la
longueur finale 3 983,0200 mm. Le pipeline complet prend 19,42 s, sous le
budget plugin prévu de 20 s.

Un test synthétique vérifie séparément le cas propre à G3.4 : G3.1 ne peut
améliorer les deux segments incidents, alors que le parcours des deux chaînes
complètes déplace le via et économise 2,3431 mm.
