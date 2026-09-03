# Rapport historique — G3.3 — validation des T glissants

Date : 2026-09-02  
Branche : `gloss_final`  
Version du plugin : `0.21.3`

## Périmètre

- rail colinéaire conservé sans modification ;
- branche du T déplacée avec les directions et contrôles KRT ;
- raccord à 90° avec le rail explicitement autorisé ;
- pad et via au nœud prioritaires sur le glissement ;
- aucune modification Rust ou des algorithmes KRT.

## Résultats ciblés

| PCB | T déplacés | Gain propre G3.3 | Régression de connectivité |
|---|---:|---:|---:|
| `dispenser.kicad_pcb` | 0 | 0,0000 mm | 0 |
| `picofx_pump.kicad_pcb` | 1 | 1,1573 mm | 0 |
| `ember_he.kicad_pcb` | 8 | 7,6457 mm | 0 |

Sur `picofx_pump`, le segment diagonal du net `+5V` est remplacé par un
segment horizontal qui rejoint le rail vertical à 90°. Le rail reste intact.
Le cas valide donc explicitement qu'un raccord perpendiculaire peut être la
solution minimale d'un T glissant.
