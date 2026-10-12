# Gloss : présélection des zones et des contacts — 12 octobre 2026

## Cause établie et périmètre

Le diagnostic de `8121a1d` a trouvé deux coûts évitables. Sur azukar_fpga,
502 constructions de modèles de zones cumulent 447 840 visites de pistes :
KRT échantillonne aussi celles trop éloignées pour atteindre la grille. Sur
tildagon_base, 6 797 537 des 6 893 383 paires de segments observées dans les
contrôles de même net ont des rectangles englobants éloignés. La direction du
candidat et les clés de ses voisins sont recalculées dans ces parcours.

Les profils localisent ces coûts ; leurs temps cumulés ne sont pas des temps
de production et ne doivent pas être additionnés entre fonctions imbriquées.
Le prototype préalable de zones conserve cellule par cellule les 539 modèles
reconstruits sur azukar_fpga et tildagon_base. Il ne donne pas de gain utile
sur les grandes zones de tildagon_base, ce qui motive le chemin direct conservé.

## Intégration

- `zone_models` transmet à KRT une vue contenant seulement les pistes et vias
  dont l'enveloppe peut atteindre la grille d'une petite zone. La marge inclut
  les rayons, les clearances des classes et deux cellules, avec arrondi vers
  l'extérieur. Les pads, contours, keepouts et règles restent ceux de la carte.
- Les grilles couvrant au moins un quart du rectangle de la carte conservent
  le chemin original. Ce seuil ne modifie que le coût de la présélection.
  Tout échec de cette préparation retombe sur KRT avec la carte entière.
- KRT construit, publie et interroge ses modèles. Sa publication dans le cache
  secondaire est conservée, y compris le franchissement de 64 entrées. Les
  invalidations et la restauration suivent les chemins existants.
- `SameNetSegments` est un instantané ordonné, local à une recherche de chaîne,
  de connecteur de pad ou de réduction locale. Sa grille paresseuse garde une
  marge de 1e-6 mm, supérieure à la tolérance de colinéarité de 1e-7 mm. Les
  longues requêtes et les ensembles riches en longs segments emploient un
  filtre vectorisé des rectangles ; les petits ensembles restent parcourus.
- Les contacts d'extrémités utilisent les clés de position KRT exactes. Les
  prédicats d'intersection, de recouvrement et d'angle restent inchangés et
  reçoivent les voisins dans leur ordre initial. La direction du candidat est
  calculée une fois par segment. Les vias conservent leurs contrôles complets.

Ni source KRT, ni réglage public, ni ordre de recherche, ni nombre de passes,
ni précision, ni contrôle de clearance, de corridor ou de connectivité ne sont
réduits. Les réutilisations supplémentaires de certificats électriques et des
tableaux de cuivre évoquées pendant l'analyse ne font pas partie de ce changement.

## Vérifications

361 tests ciblés réussissent en 1,48 s, dont 52 nouveaux cas : comparaison
cellule par cellule avec KRT, rotations et translations, épaisseurs de zones,
clearances de classes, pistes larges, vias sur d'autres couches, pads et keepouts,
invalidations et restauration, erreurs de préparation, seuil du cache secondaire,
comparaison aux parcours non indexés, frontières de cellules, quasi-colinéarité,
grands segments, ordre des voisins et clés d'extrémités KRT.


## Mesures finales

34 exécutions chronométrées couvrent 13 configurations. Les pistes et vias ont
exactement la même signature géométrique avant/après ; toutes les statistiques
hors chronométrage sont identiques, G5 valide partout, aucun budget expiré.
Les trois essais de chart_plotter_hat et environment_sensor avec corridor sont
résumés par leur médiane ; les autres cases correspondent à un essai par version.
Une réduction négative indique un temps plus long.

| Carte | Sans corridor : avant → après | Réduction | Avec corridor : avant → après | Réduction |
|---|---:|---:|---:|---:|
| complete1 | 4,281 → 4,143 s | 3,2 % | 2,142 → 2,057 s | 4,0 % |
| micro_dmm | 0,630 → 0,627 s | 0,5 % | 0,236 → 0,214 s | 9,1 % |
| chart_plotter_hat | 5,501 → 5,440 s | 1,1 % | 3,680 → 3,734 s | -1,5 % |
| environment_sensor | 3,846 → 3,810 s | 0,9 % | 2,174 → 2,123 s | 2,3 % |
| azukar_fpga | 30,666 → 16,608 s | 45,8 % | 21,967 → 10,704 s | 51,3 % |
| tildagon_base | 51,217 → 47,610 s | 7,0 % | 33,384 → 28,822 s | 13,7 % |
| PACK0 cumulé | 91,861 → 74,096 s | 19,3 % | 61,441 → 45,597 s | 25,8 % |

Le seuil de 20 % est dépassé sur azukar_fpga et sur le cumul PACK0 avec corridor,
mais pas sur chaque carte ni sur le cumul sans corridor (19,3 %). La petite
hausse de chart_plotter_hat avec corridor est conservée dans le bilan :
3,680 → 3,734 s en médiane, soit +1,5 %. On ne peut donc pas annoncer une absence
universelle de régression temporelle. Aucun résultat géométrique n'est dégradé
sur les essais réalisés.

complete1 à vias fixes, sans G4 : 3,009 → 2,866 s, gain de cuivre toujours
8,4176 mm. Avec vias mobiles et G4 : gains conservés de 14,7240 mm sans corridor
et 7,4974 mm avec corridor.

Les deux sorties complete1 avec vias mobiles et G4 sont écrites et relues :
signatures identiques après sérialisation, clearance valide sur les 111 nouvelles
pistes et les 7 vias déplacés, partitions électriques des 47 nets conservées.
Les cartes d'entrée restent inchangées.

Les [données chiffrées et empreintes](data/gloss_spatial_filters_2026_10_12.json)
conservent les temps individuels, les signatures du code et des résultats.

## Protocole et limites

Référence : `8121a1d`, copiée avant les modifications. Les processus sont neufs
et exécutés séquentiellement, avec la même révision KRT et le même runtime.
Les entrées sont complete1 réimporté et les cinq cartes PACK0, dont les SHA-256
sont vérifiés. Vias mobiles, une passe G4, avec et sans corridor ; le budget
de 600 s écarte les interruptions temporelles de la comparaison de résultats.
Ce n'est pas le budget par défaut de l'interface. Parsing et écriture sont exclus
du chronométrage ; contexte et certification sont inclus.
complete1 utilise une clearance de 0,1524 mm, un retrait au bord de 0,3 mm et
une clearance entre trous de 0,254 mm. PACK0 garde les règles résolues par les
valeurs par défaut du CLI pour chaque carte. Les grilles sont à 0,1 mm.

Les essais exploratoires des index intermédiaires sont séparés des mesures de
la version finale. Les empreintes du code accompagnent ces dernières. Une
réduction sur le temps cumulé de PACK0 ne signifie pas cette réduction sur
chaque carte. Les petits écarts de temps ne permettent pas de conclure à une
accélération systématique. Les comparaisons ne remplacent pas un DRC natif KiCad,
une qualification d'autres plateformes ou une preuve universelle de non-régression.

## Traces locales

Dans `C:/Users/frant/Downloads/cube_pcb1/comparaison_gloss_20261012/` :

- `deep_profile.py`, `deep_audit.py`, `deep_zones.py` : diagnostic préalable ;
- `spatial_release_compare.py` et `spatial_release_comparison.jsonl` : mesures
  de la version finale ;
- `spatial_verify_written.py`, `spatial_written_before.json`,
  `spatial_written_after.json` : contrôles après écriture/relecture ;
- `complete1_spatial_before.kicad_pcb`, `complete1_spatial_after.kicad_pcb` :
  sorties de comparaison, distinctes des fichiers d'entrée.

Aucune installation du plugin ni création de ZIP n'est impliquée.
