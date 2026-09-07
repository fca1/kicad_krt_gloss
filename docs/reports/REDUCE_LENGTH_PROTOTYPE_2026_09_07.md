# Prototype réduction de longueur — 7 septembre 2026

Tag demandé : `before_reduce_length`, sur `b2344a73c075d178eeef36941475a82c95693211`.
Il marque le code commité avant prototype ; les changements préexistants
d'interface, version et packaging sont laissés dans le répertoire de travail.

## Périmètre

Le prototype est activé uniquement par `tools/reduction_motion.py`, dans le
processus d'essai. Deux points d'appel internes inactifs par défaut sont ajoutés
aux déplacements de vias et de jonctions. Aucune option d'interface n'est
ajoutée ; KRT n'est pas modifié. Le plugin normal n'active pas le prototype.

1. Mouvement conjoint des segments et de leur extrémité commune mobile : même
   paramètre temporel pour chaque branche incidente. Le corps et le perçage
   du via suivent le même mouvement et passent par `via_clears` KRT.
2. Certificat adaptatif : une enveloppe au milieu de l'intervalle couvre le
   déplacement de tout l'intervalle, par inflation du rayon cuivre/perçage.
   Si KRT la valide, l'intervalle est terminé. Sinon, subdivision jusqu'à une
   profondeur 10 ou 128 intervalles par proposition. Une limite atteinte ou
   un délai expiré refuse la proposition. Il n'y a ni recherche exhaustive de
   positions ni recherche d'un itinéraire alternatif autour d'un obstacle.
3. Approches de pads : variante à certification précoce. Le premier candidat
   valide de chaque famille monotone est certifié immédiatement ; les familles
   qui ne peuvent battre le meilleur résultat certifié sont arrêtées. Un
   résultat déjà certifié reste disponible si le budget expire ensuite.

La troisième proposition concerne G3.2 uniquement. L'énumération et la
certification tardive de G3/G3.3 ne sont pas réécrites par ce prototype.

## Protocole demandé : plusieurs cartes, aucune répétition

Un seul passage par variante sur chaque carte, sans échauffement : neuf essais.
Ordre alterné entre les cartes. Parsing séparé avant chaque essai, aucun PCB
enregistré, hash source vérifié après chacun. Grille 0,1 mm, budget 20 s,
**stay_in_corridor=True**, réglages Gloss par défaut pour les autres opérations,
Centering désactivé. Temps mural sans profileur, contexte et G5 compris,
parsing exclu. Les compteurs du certificat sont inclus dans le temps mesuré.

La référence est le comportement du tag (points d'appel inactifs), avec
`stay_in_corridor=True` mais sans certificat de mouvement des vias/jonctions.
Les deux variantes sont « mouvement » et « mouvement + pads précoces ».
Les anciens temps sans contrainte de corridor ne sont pas directement comparables.

## Mesures

| Carte | Variante | Temps | Gain total du Gloss | Segments finaux |
|---|---|---:|---:|---:|
| dispenser | Référence | 2,482 s | 11,9936 mm | 366 |
| dispenser | Mouvement | 2,420 s | 11,9936 mm | 366 |
| dispenser | Mouvement + pads précoces | 2,417 s | 11,9936 mm | 366 |
| picofx_pump | Référence | 3,011 s | 61,7528 mm | 256 |
| picofx_pump | Mouvement | 3,181 s | 56,8770 mm | 260 |
| picofx_pump | Mouvement + pads précoces | 3,066 s | 56,8770 mm | 260 |
| ember_he | Référence | 11,812 s | 31,0373 mm | 932 |
| ember_he | Mouvement | 11,581 s | 30,4936 mm | 933 |
| ember_he | Mouvement + pads précoces | 11,634 s | 30,4936 mm | 933 |

Entrées : dispenser 440 segments ; picofx_pump 347 ; ember_he 1 018.
Les neuf essais convergent après deux passes G4 et passent G5, avec zéro
régression de connectivité rapportée. Les hashes restent identiques.

Coût direct du certificat sur la variante mouvement :

| Carte | Temps cumulé | Propositions vias / jonctions | Refus | Intervalles | Limites atteintes |
|---|---:|---:|---:|---:|---:|
| dispenser | 48,4 ms | 2 / 0 | 0 | 24 | 0 |
| picofx_pump | 79,7 ms | 8 / 3 | 6 | 111 | 0 |
| ember_he | 40,9 ms | 10 / 18 | 9 | 29 | 0 |

La variante pads conserve les gains de la variante mouvement sur les trois
cartes. Les différences de temps total ne constituent pas un gain statistique
démontré : il n'y a qu'une mesure par variante, et les refus modifient aussi
les recherches ultérieures. Le certificat a un coût réel même lorsque le temps
total observé baisse. Le gain réduit de picofx/ember ne prouve pas que tous les
raccourcis refusés étaient invalides : un certificat conservateur peut refuser
un mouvement admissible par une autre déformation.

## Vérifications ciblées

Cinq cas synthétiques nouveaux : jonction libre acceptée, saut d'obstacle
refusé avec entrée/sortie KRT valides, corps du via bloqué alors que la
déformation des segments est admissible, délai expiré refusé, approche de pad
certifiée conservée après expiration ultérieure du budget.

Avec les tests microsegments, corridor, glissement et politique :
**40 tests réussis en 0,51 s**. Les tests synthétiques ne sont pas des répétitions
des benchmarks sur cartes. Aucun DRC natif KiCad ni remplissage natif des zones.

## Limites avant une éventuelle intégration

- Le prototype certifie une déformation particulière. Un échec, un raccordement
  non reconnu ou une limite atteinte conduit au refus, sans recherche alternative.
- Les connexions entre segments et extrémités mobiles sont conservées par
  construction ; le graphe électrique final reste contrôlé par KRT. Le graphe
  complet des contacts aux zones n'est pas recalculé à chaque instant du mouvement.
- Les obstacles sont ceux pris en charge par l'adaptateur KRT existant. Le
  contrôle supplémentaire des contacts avec les autres pistes du même net,
  précédemment mis de côté, n'est pas réintroduit. Ce prototype ne démontre donc
  pas à lui seul la totalité de la définition générale du corridor pour toutes
  les topologies de cuivre.
- L'expiration pendant l'énumération G3/G3.3 reste un sujet distinct ; seul le
  cas G3.2 a ici une variante à certification précoce.
- Les chemins d'essai sont Gloss avec corridor. Ni les performances de l'action
  Centering sur une carte entière ni l'application native ne sont mesurées ici.

## Reproduction et sources

```powershell
python -m pytest -q -p no:cacheprovider tests/test_reduction_motion_prototype.py tests/test_local_micro_cleanup.py tests/test_corridor.py tests/test_segment_sliding.py tests/test_gloss_policy.py
python tools/benchmark_motion_corridor.py C:/Users/frant/Documents/KiCad/10.0/projects/dispenser/dispenser.kicad_pcb C:/Users/frant/Documents/kicad_track_gloss_stress/sources/set21/picofx_pump.kicad_pcb C:/Users/frant/Documents/kicad_track_gloss_stress/sources/set21/ember_he.kicad_pcb --output .build/motion_corridor_known_boards.json --budget 20
```

Résultats bruts, configurations, compteurs, logs et hashes :
`.build/motion_corridor_known_boards.json`.
