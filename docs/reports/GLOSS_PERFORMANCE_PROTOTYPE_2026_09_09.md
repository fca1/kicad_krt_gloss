# Prototype de performances Gloss — 9 septembre 2026

## Statut et périmètre

Prototype isolé dans `tools/prototype_gloss_perf.py`, basé sur `f704f48`.
Il n'est activé ni par le plugin ni par `gloss.py`, et n'entre pas dans le ZIP.
KRT reste inchangé. Aucun changement de recherche géométrique, de grille,
d'ordre des candidats ou de certificat final. Pas de Centering, G4 désactivé.

## Variantes

- `early` : rejet immédiat lorsque la première distance condamne un segment,
  au lieu de calculer encore les autres distances. Mêmes prédicats.
- `pads` : préparation par couche des coins/arêtes des pads fixes et des
  règles. Calculs exacts repris, sans arrondir les coordonnées.
- `vias` : présélection par rectangles englobants physiques des segments et
  vias avant les prédicats KRT inchangés. Les perçages du même net restent
  pris en compte. Les pads restent tous vérifiés : filtrage partiel volontaire.
  `nextafter` élargit les comparaisons d'un nombre représentable, pas d'une
  largeur géométrique arbitraire. Les caches suivent l'identité des listes.
- `references` : conservation des références électriques des nets inchangés
  sans zone. Tous les nets possédant une zone sont invalidés après chaque
  modification, même si leur modèle KRT n'est plus en cache. Cette première
  version conservatrice ne tente pas une invalidation spatiale fine des zones.
- `views` : les parcours terminaux et de branches reçoivent la vue du net
  concerné. Pas de réécriture incrémentale de la topologie.

## Protocole

Sélection par nets entiers. Grille 0,1 mm, budget initial 120 s, G4 et
Centering désactivés, avec et sans corridor. Une exécution par variante et
configuration, sans préchauffage ni profileur. Référence d'abord sans corridor,
prototype d'abord avec corridor. Les mesures uniques restent sensibles à la
charge du poste et ne constituent pas des moyennes ni une garantie de gain.

Chronométrage moteur avec contexte et G5, hors parsing/configuration,
application native et audits. Les PCB ne sont jamais sauvegardés ; leurs
SHA256 sont vérifiés contre PACK0 avant et après chaque essai.

Comparaison des coordonnées exactes, couches, largeurs et dimensions des vias
par empreinte de géométrie, sans arrondi. Audits supplémentaires par le code
de production non patché : clearance du nouveau cuivre non exempté,
octolinéarité, nouvelles pointes hors ancres. Ils ne sont pas un DRC KiCad complet.

Commandes :

```text
python tools/benchmark_gloss_perf.py --boards chart_plotter_hat --variants early pads vias references views combined --output .build/gloss_perf_isolated.json
python tools/benchmark_gloss_perf.py --output .build/gloss_perf_pack0.json --budget 120
```

## Défaut préexistant découvert par un test adversarial

Le balayage d'un via de (-5, 0) à (5, 0), diamètre 0,6 mm, peut être déclaré
libre face à une piste étrangère de (0, -1) à (0, 1), largeur 0,2 mm, F.Cu.
La référence sans prototype donne déjà cette réponse : le prédicat KRT
`check_segment_overlap` utilisé ici ne signale pas ce croisement précis.
Le filtre du prototype conserve bien l'obstacle ; il ne crée pas ce défaut.

Le test `test_existing_perpendicular_via_sweep_gap` est conservé comme
`xfail(strict=True)` documenté, séparé des tests de non-régression. Il ne faut
pas annoncer « aucun artefact possible » à partir de ces mesures. Corriger
cette limite demanderait une intervention géométrique distincte de cette
expérience de performance, sans modifier KRT.

## Résultats PACK0 — temps réels

| Carte | Sans corridor : réf. → proto. | Gain | Avec corridor : réf. → proto. | Gain |
|---|---:|---:|---:|---:|
| micro_dmm | 0.403 → 0.321 s | 20.3 % | 0.245 → 0.230 s | 6.1 % |
| chart_plotter_hat | 3.480 → 3.357 s | 3.5 % | 3.733 → 3.408 s | 8.7 % |
| environment_sensor | 3.405 → 2.778 s | 18.4 % | 2.422 → 2.292 s | 5.4 % |
| azukar_fpga | 28.279 → 26.498 s | 6.3 % | 26.194 → 24.315 s | 7.2 % |
| tildagon_base | 39.487 → 27.273 s | 30.9 % | 29.404 → 26.361 s | 10.4 % |

Total : 75,053 → 60,226 s sans corridor (−19,8 %) ; 61,998 → 56,605 s
avec corridor (−8,7 %). Les 20 exécutions passent G5 sans expiration.
Les 10 comparaisons ont une empreinte géométrique exacte identique, zéro
nouvelle direction non octolinéaire, zéro nouvelle pointe hors ancres et zéro
défaut de clearance sur nouveau cuivre non exempté. Gains de longueur inchangés.

| Phase tildagon | Sans corridor réf. → proto. (s) | Avec corridor réf. → proto. (s) |
|---|---:|---:|
| G3 | 18.145 → 11.827 | 9.381 → 8.537 |
| G3.1 | 1.017 → 0.785 | 2.398 → 2.136 |
| G3.2 | 2.572 → 1.407 | 4.440 → 3.680 |
| G3.3 | 0.967 → 0.791 | 1.076 → 1.090 |
| G3.4 | 1.259 → 0.778 | 1.512 → 1.306 |
| G3.5 equal length | 5.354 → 3.787 | 3.090 → 3.039 |
| G3.5 segments | 0.853 → 0.842 | 1.077 → 1.064 |
| G3 local | 3.392 → 3.026 | 1.472 → 1.234 |
| G5 | 0.577 → 0.520 | 0.607 → 0.528 |

Détails par étape, chargement, journaux et empreintes :
[mesures PACK0](data/gloss_perf_pack0_2026_09_09.json).

## Variantes isolées : attribution encore limitée

Sur chart_plotter_hat sans corridor : référence 3,259 s ; early 3,416 ; pads
3,847 ; vias 3,911 ; references 3,877 ; views 3,946 ; combinaison 3,289.
Avec corridor : référence 3,978 s ; early 3,576 ; pads 3,914 ; vias 3,926 ;
references 3,950 ; views 3,993 ; combinaison 3,503.

Ces mesures uniques montrent des régressions et des fluctuations selon l'ordre.
Elles ne permettent pas d'attribuer individuellement le gain PACK0 aux cinq
changements, ni de déclarer chaque variante bénéfique. La combinaison est
prometteuse, mais un retrait variante par variante sur les grandes cartes
reste nécessaire avant une intégration sélective.
Données : [essais isolés](data/gloss_perf_isolated_2026_09_09.json).

## Tests et conclusion

54 tests ciblés réussis et 1 défaut préexistant explicitement marqué xfail ;
32 tests de balayage/mouvement supplémentaires passent avec le prototype activé.
Le prototype est conservé comme expérience, pas intégré à la production.
Ne pas mélanger une correction du croisement préexistant avec ce gain de temps :
ce serait une nouvelle référence géométrique à qualifier séparément.
