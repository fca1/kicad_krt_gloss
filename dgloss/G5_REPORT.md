# G5 — certification finale de conformité

G5 est une certification, pas une nouvelle passe géométrique. Le résultat G4
est conservé à l'identique puis contrôlé avec les données et primitives KRT.

## Contrôles ajoutés

- comparaison avant/après de la partition des pads et zones dans le graphe de
  connectivité KRT ;
- revalidation finale des segments réellement déplacés avec les règles KRT ;
- revalidation des vias mobiles et conservation de leurs dimensions, couches,
  net, verrouillage et attributs de fabrication ;
- maintien des contrôles de longueur, d'octolinéarité et de micro-segments ;
- restauration atomique du résultat post-smooth à la moindre non-conformité.

Les segments issus de `merge_collinear_segments()` sont comptés séparément :
leur empreinte cuivre est inchangée et ils ne constituent pas un nouveau dessin
à certifier contre d'éventuelles fautes déjà présentes en entrée.

## Validation, budget de 20 secondes

| Carte | Gain total hérité de G4 | Segments finaux | Segments G5 contrôlés | Réémissions KRT | Vias G5 contrôlés | Temps G5 | Résultat |
|---|---:|---:|---:|---:|---:|---:|---|
| `dispenser` | 9,1531 mm | 356 | 58 | 59 | 2 | 81,2 ms | conforme |
| `picofx_pump` | 40,5382 mm | 252 | 73 | 5 | 2 | 39,7 ms | conforme |
| `ember_he` | 25,2830 mm | 922 | 113 | 65 | 8 | 142,7 ms | conforme |

Les trois géométries et leurs gains sont identiques au G4 corrigé. `dispenser`
et `picofx_pump` convergent respectivement en trois et deux passes. `ember_he`
termine une passe complète puis atteint le budget pendant la seconde ; la
certification finale obligatoire s'exécute ensuite.

## Amélioration G4 conservée pour étude ultérieure

Le cas `USB_D+` de `ember_he` a mis en évidence une sensibilité de G4 au
découpage des segments. Une évolution possible consistera à comparer les
contacts même-net avant/après avec le prédicat robuste KRT, puis à traiter
séparément les candidats situés à la frontière entre grille Rust et contrôle
exact. Cette évolution n'est pas intégrée à G5 et G4 reste inchangé.

## Tests

- 44 tests dgloss et d'architecture réussis ;
- aucune régression de connectivité ou de topologie sur les trois cartes ;
- aucune modification de KRT ou de Rust.
