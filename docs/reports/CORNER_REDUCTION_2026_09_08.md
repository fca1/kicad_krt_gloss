# Réduction des pointes dans le corridor — 8 septembre 2026

Intégration après `a49a833`, KRT inchangé à
`0aff32c04fa51b4d53ecabc843b09b356aaef94b`. Pas de nouveau ZIP dans cette passe.

## Diagnostic et correction

Sur `test_centering2`, net `/A`, enlever le recouvrement collinéaire économisait
2,8200 mm mais conservait une pointe au point (146,255 ; 90,445). Les directions
individuelles étaient octolinéaires : les anciens tests ne détectaient donc pas
le défaut de raccordement. G5 ne certifiait pas l'absence de pointe.

Les raccourcis directs proposés après ce nettoyage économisaient 12,7059 mm.
Leur destination était libre, mais le déplacement testé approchait U1.1 à
0,246167 mm pour 0,2524 mm exigés (clearance et demi-largeur). Leur refus ne
prouvait pas l'impossibilité d'une autre réduction. G3 local n'essayait que les
connecteurs canoniques et les positions extrêmes du glissement ; G3.5 ne pouvait
pas inventer une réduction nécessitant davantage de segments.

`corner_reduction.py` ajoute une famille locale de raccords successifs à 45°.
Les supports intermédiaires tournent entre les deux directions incidentes et
s'éloignent du sommet avec un paramètre commun. Leurs intersections construisent
le raccord. La limite provient soit de l'absorption d'une extrémité, soit du premier
contact physique certifié par KRT. La recherche dichotomique résout ce contact à
`FP_EPS_MM`, indépendamment du pas de routage ; ce n'est pas un échantillonnage de
positions sur une grille. La longueur minimale existante reste appliquée aux
segments émis. Aucun rayon de contrôle ou chanfrein de taille imposée n'est ajouté.

Les surfaces balayées sont des polygones convexes emboîtés. Leur triangulation
utilise le sommet initial et les nouveaux raccords, avec la largeur physique du
cuivre. Le refus d'une surface interdit de poursuivre au-delà dans cette famille :
une destination redevenue libre après un obstacle n'est pas acceptée. Les branches
du même net sont également contrôlées sur le bord et à l'intérieur de la surface.
Le garde électrique, les contrôles de contact avec le reste du net et G5 demeurent.
L'ajout de segments est permis pour un gain de longueur ; les ancres restent fixes.

PACK0 a révélé une seconde cause : des déplacements de vias produisaient de
nouvelles pointes après G3, et la réduction locale finale était désactivée avec
corridor. Cela existait dans le ZIP `a49a833` : net 70 d'azukar et nets 59/60 de
tildagon. `optimization.py` réexamine maintenant les nets effectivement modifiés
par les étapes vias/pads/T/fusions, avant G5 et indépendamment de G4. Le corridor
reste transmis à cette recherche ; aucun traitement n'est ajouté après Centering.

## Validation

- Suite complète : **399 réussites, un échec préexistant**, le test Centering
  `test_a_later_gloss_completely_removes_a_longer_centering_path` (zéro porte).
- Tests de contact physique, rotation par multiples de 45°, réflexion, indépendance
  du pas, obstacle franchissable seulement à destination, cuivre du même net,
  minimum de longueur, expiration, rejet électrique et reprise après déplacement
  de via avec G4 désactivé. Le test de delta isole explicitement sa stratégie.
- Le test ancien « aucun résultat si le raccourci rencontre un obstacle » est
  remplacé par la vérification du refus direct et de l'acceptation d'une réduction
  partielle certifiée : son ancienne attente était précisément la limitation corrigée.
- Dix exécutions PACK0 finales : G5 valide, zéro régression de connectivité,
  zéro nouvelle direction non octolinéaire, zéro nouvelle pointe hors ancres
  pad/via détectée, aucun budget expiré, sources SHA-256 inchangées.

### Reproduction native `/A`

Fichier `C:/Users/frant/Downloads/kicad_centering/test_centering1/test_centering2.kicad_pcb`,
SHA-256 `02444ca7e2856235f09683a66ef85a7206e1280926a436f780a5c1019d133cec`.
Python KiCad 10.0.6, grille 0,1 mm, corridor actif, une passe G4 maximale.

| Mesure | Entrée | Sortie |
| --- | ---: | ---: |
| Longueur `/A` | 63,412149 mm | 54,594283 mm |
| Nombre de pistes du net | 8 | 9 |
| Recouvrements collinéaires | 1 | 0 |
| Pointes détectées | 1 | 0 |

Gain total : **8,817866 mm**, soit 5,997866 mm de plus que le ZIP précédent.
Application native : 3 pistes retirées, 4 ajoutées ; directions vérifiées après
conversion sur la grille entière native, tolérance d'un nanomètre. G5 valide,
source non sauvegardée. Dernière mesure moteur : 98,365 ms (hors application).
`tools/reproduce_corridor_fold.py` contrôle désormais les raccordements et
l'application sur carte détachée, pas seulement les directions du moteur.
Ce n'est ni une validation visuelle dans l'éditeur ni un DRC complet.

## PACK0 : temps réels, G4 désactivé

Une exécution finale par carte et configuration, sans préchauffage ni profileur.
Grille 0,1 mm, budget 60 s, toutes les pistes admissibles, sans Centering.
Temps muraux du moteur incluant préparation, contexte et G5, hors parsing,
application native et audits supplémentaires. Les valeurs ne constituent pas
des moyennes ; la charge de la machine a varié pendant les essais de mise au point.
Les données et journaux sont dans
[le relevé JSON](data/corner_reduction_2026_09_08.json).

| Carte | Sans corridor (s) | Avec corridor (s) | Gain sans (mm) | Gain avec (mm) |
| --- | ---: | ---: | ---: | ---: |
| micro_dmm | 0,423 | 0,316 | 8,4240 | 2,5919 |
| chart_plotter_hat | 3,170 | 3,202 | 62,6098 | 39,5795 |
| environment_sensor | 2,732 | 2,054 | 22,4942 | 13,8244 |
| azukar_fpga | 23,399 | 20,712 | 116,7258 | 64,4087 |
| tildagon_base | 35,021 | 22,984 | 88,9842 | 41,6603 |

### Détail G3 sur tildagon_base (secondes)

La colonne de référence vient d'une exécution rapprochée du moteur extrait du
ZIP `a49a833`, également sans G4. Les géométries de référence correspondent aux
empreintes des précédentes mesures sans G4. Il ne faut pas comparer seulement
les anciens temps de 27,823/40,393 s aux nouveaux pour annoncer une accélération.

| Phase | Référence avec corridor | Corrigé avec corridor | Corrigé sans corridor |
| --- | ---: | ---: | ---: |
| G3 réduction initiale | 6,601 | 7,194 | 14,385 |
| G3.1 vias | 1,834 | 1,830 | 0,820 |
| G3.2 pads | 3,350 | 3,383 | 2,044 |
| G3.3 T | 0,864 | 0,846 | 0,792 |
| G3.4 affinage vias | 1,229 | 1,271 | 1,043 |
| G3.5 nombre à longueur égale | 2,305 | 2,334 | 4,678 |
| G3.5 fusion | 0,747 | 0,751 | 1,175 |
| G3 local final | absent | 1,161 | 4,536 |
| G5 | 0,427 | 0,436 | 0,772 |
| Moteur complet | 21,122 | 22,984 | 35,021 |

La nouvelle recherche initiale ajoute environ 0,594 s sur cette mesure ; la reprise
locale après les autres phases coûte 1,161 s et gagne 1,5187 mm. Total : +1,862 s
(environ +8,8 %) pour un gain passant de 34,1421 à 41,6603 mm. Sur azukar,
19,722 → 20,712 s, gain 59,0485 → 64,4087 mm. La correction n'est donc pas gratuite.
Sur tildagon corrigé avec corridor, les phases G3 totalisent 18,771 s ; environ
3,777 s restent dans la préparation et les autres contrôles hors G5.

## Limites explicitement conservées

- C'est une famille locale supplémentaire, pas un solveur de toutes les classes
  de contournement, ni une garantie d'optimum global. Un contact peut empêcher
  toute réduction de cette famille ou laisser trop peu de place pour des segments
  conformes à la longueur minimale ; la géométrie est alors conservée.
- Un raccord aigu préexistant reste sur le net 150 de tildagon, dans les deux
  configurations. Ne pas annoncer « aucune pointe sur toute carte ».
- L'audit de clearance final retrouve des défauts sur des objets issus de fusions
  certifiées conserver le cuivre : 11/40 objets avec corridor sur environment/tildagon,
  6/53 sans corridor. Aucun objet non exempté de cette manière ne rate cet audit.
  Cela ne signifie pas que les PCB sont initialement exempts de défauts.
- Les conditions `.kicad_dru` non modélisées par KRT, le test Centering préexistant
  et les limites de certification décrites dans le guide restent applicables.
- Le benchmark retourne désormais un échec en cas de nouvelle pointe hors ancres
  ou de défaut de clearance sur cuivre non exempté, en plus des contrôles G5,
  directions et intégrité des sources. L'audit n'assimile pas les jonctions dans
  les pads et les articulations de vias à des coudes ordinaires.

Reproduction : `python tools/benchmark_architecture.py --budget 60 --no-g4
--details --audit-clearance --output resultat.json`, ajouter `--corridor` pour
l'autre configuration. Les fichiers PCB ne sont jamais sauvegardés.
