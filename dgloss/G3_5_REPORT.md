# G3.5 — conformité et réduction finale des segments

G3.5 coordonne G3 à G3.4 puis termine l'objectif lexicographique de la
spécification : après la réduction de longueur, réduire le nombre de segments
à longueur égale. Cette validation est menée avec `enable_multipasses=False` ;
elle ne constitue pas encore une nouvelle validation de G4.

## Implémentation minimale

Deux cas sont distingués :

1. Une chaîne octolinéaire non colinéaire est remplacée uniquement si un
   raccord canonique fourni par KRT a la même longueur et moins de segments.
   Le moteur, la garde de connectivité, les obstacles et les clearances de G3
   sont réemployés ; aucun générateur géométrique supplémentaire n'est créé.
2. Les alignements stricts sont confiés directement à
   `merge_collinear_segments()` de KRT. Cette primitive ne déplace aucun cuivre
   et conserve les gardes de pads, vias, T, couches, largeurs et verrouillages.

La certification finale ignore les anciens objets intermédiaires qui ne sont
plus présents. Une chaîne réémise par la fusion KRT est marquée comme
géométriquement conservatrice : elle reste tracée et comptée, sans être prise
à tort pour du cuivre déplacé.

## Matrice de conformité

| Règle de `gloss_krt.md` | Couverture G3.5 | Preuve principale |
|---|---|---|
| Règles et données d'entrée prioritaires | Contexte et contrôles KRT | `build_gloss_context`, `KrtClearanceAdapter` |
| Réduction de longueur | Couverte | G3 à G3.4, validation longueur non croissante |
| Moins de segments à longueur égale | Couverte | passage canonique égalitaire puis fusion KRT |
| Sortie octolinéaire | Couverte | générateurs KRT et certification finale |
| Aucun micro-segment créé | Couverte | seuil du pas réel et certification du cuivre final déplacé |
| Mono-net, multi-nets et liste vide | Couverte | portée `net_ids`, liste vide = tous les nets |
| Connexion complète et vias traversants | Couverte | graphes KRT, G3.1/G3.4 et grade final de connectivité |
| Autres nets comme obstacles | Couverte | retrait du seul cache du net courant |
| Changement de largeur non terminal | Couverte | chaînes séparées mais incidence globale conservée |
| Pads fixes | Couverte | point natif et garde de custody KRT |
| Conditions de mobilité des vias | Couverte | G3.1/G3.4 et attributs du via conservés |
| T colinéaires et variante non colinéaire | Couverte | G3.3 et option dédiée |
| Repli sans perte | Couverte | instantané et restauration atomique G3.5 |

## Comparatif avant/après le correctif

Budget : 20 secondes par carte. Grille : 0,1 mm. Multipasses désactivées.

| Carte | Segments G3.5 avant | Segments corrigés | Raccords égaux | Fusions KRT | Gain de longueur | Temps corrigé | Régression |
|---|---:|---:|---:|---:|---:|---:|---:|
| `dispenser` | 404 | 358 | 14 | 32 | 7,1655 mm | 2,696 s | 0 |
| `picofx_pump` | 272 | 261 | 8 | 3 | 34,6524 mm | 3,043 s | 0 |
| `ember_he` | 959 | 923 | 14 | 22 | 22,7558 mm | 8,760 s | 0 |

Le gain de longueur est inchangé : les nouvelles opérations appliquent le
troisième objectif uniquement après le second. Leur surcoût algorithmique
mesuré est de 192,3 ms, 246,4 ms et 1 101,7 ms respectivement.

## Tests

- 40 tests dgloss et d'architecture réussissent.
- La suite KRT `test_811_merge_collinear.py` réussit intégralement : chaîne
  complète, kink conservé, retour arrière refusé, T, via, largeur, couche,
  verrouillage, custody des pads, write-list et portée des nets.
- Les trois cartes réelles terminent sous le budget normal sans régression de
  connectivité.
