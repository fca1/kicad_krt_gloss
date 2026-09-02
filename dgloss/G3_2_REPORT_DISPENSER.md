# G3.2 — validation ciblée sur dispenser

Date : 2026-09-01  
Branche : `gloss_final`  
Version du plugin : `0.21.3`  
PCB : `C:\Users\frant\Documents\KiCad\10.0\projects\dispenser\dispenser.kicad_pcb`

## Périmètre

- smooth KRT global sur tous les nets, puis G3, G3.1 et G3.2 ;
- règles du projet et primitives de clearance/connectivité KRT ;
- pas KRT de `0,05 mm` ;
- aucune campagne de stress et aucune modification Rust/KRT algorithmique.

## Résultat

| Mesure | Valeur |
|---|---:|
| Longueur initiale cumulée | 1 168,1932 mm |
| Gain du smooth KRT global | 15,9025 mm |
| Gain propre à G3.2 (pads) | 0,5970 mm |
| Gain dgloss G3 à G3.2 | 6,0555 mm |
| Gain cumulé | 21,9581 mm |
| Longueur finale cumulée | 1 146,2351 mm |
| Terminaisons de pad modifiées par G3.2 | 1 |
| Régressions de connectivité KRT | 0 |
| Temps G3.2 | 668,5 ms |

La transformation G3.2 concerne le net `/cpu/SW_PUSH`, pad `A1.1`. Le
nouveau cuivre termine exactement au point natif du pad `(164,262 ; 86,614)`.
La visualisation est cumulative : G3 sur User.1, G3.1 sur User.2 et G3.2 sur
User.3.
