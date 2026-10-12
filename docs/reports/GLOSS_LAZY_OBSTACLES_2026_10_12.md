# Gloss : obstacles à la demande et cache G4 — 12 octobre 2026

## Référence et diagnostic préalable

Référence de comparaison : `44c6c16cf020a28610eddaef2925b00adda57771`.
Le diagnostic a établi deux coûts évitables, avant modification du moteur :

- Les pads, vias, jonctions et recherches locales préparent une carte sur grille
  sans l'utiliser. Sur complete1 avec une passe G4, 596 demandes sur 658 ne sont
  suivies d'aucune sonde de grille ; avec corridor, aucune des 573 demandes ne
  l'est. Les validations exactes utilisent un autre chemin.
- Le cache de 8 192 distances aux pads évince des résultats utiles entre passes.
  Avec G4, 9 589 des 25 029 calculs effectifs répètent une requête identique.
  Sans G4, seuls 189 des 13 880 calculs répètent une requête : le bénéfice du
  cache est donc dépendant du scénario.

Les scripts de diagnostic exécutent toujours les prédicats originaux. Leurs
chronométrages instrumentés servent à identifier les coûts, pas à mesurer une
accélération de production.

## Intégration

`build_gloss_context` prépare les règles, les coordonnées et les validations
exactes sans construire la grille KRT. La première sonde réelle de chanfrein
demande la carte à `foreign_obstacles`, qui la construit depuis le cuivre courant.
Les modifications antérieures à cette première demande sont donc incluses.
Une fois construite, la carte suit le mécanisme KRT de mise à jour existant.
Les étapes qui ne consultent pas la grille ne provoquent plus sa préparation.

Le cache des distances exactes aux pads passe à 32 768 entrées au maximum.
Il reste propre à une exécution ; les coordonnées ne sont pas arrondies et les
pads/règles restent fixes pendant cette durée. La mémoire maximale augmente.

L'ordre des candidats, les seuils, les précisions, G4, les validations exactes,
la certification du corridor et G5 ne changent pas. Le filtrage supplémentaire
des trous et l'indexation des pistes du même net proposés dans l'analyse ne
sont pas intégrés dans ce changement. Aucune source KRT modifiée.

## Protocole de comparaison

Une copie du moteur de référence est conservée dans
`.build/global_perf_reference_44c6c16`. Chaque essai charge soit cette copie,
soit le moteur modifié, avec le même environnement Python et le même KRT.

Sur complete1 : trois essais par version et par mode, ordre avant/après alterné,
vias mobiles, une passe G4 supplémentaire, grille 0,1 mm, clearance 0,1524 mm,
bord 0,3 mm et trous 0,254 mm. Les temps sont les médianes, sans profileur.

Sur les cinq cartes PACK0 : un essai avant/après par carte et par mode de
corridor, vias mobiles et une passe G4 supplémentaire. Les règles sont lues
par le même CLI sur les mêmes cartes originales ; les SHA-256 sont contrôlés.
Cette campagne diffère du protocole PACK0 initial : budget de 120 s, G4 limité
à une passe supplémentaire et deux modes de corridor. Le parsing et l'écriture
sont exclus du chronométrage ; les comparaisons ne tournent pas en parallèle.

Les signatures comparent exactement les coordonnées orientées, couches,
largeurs, nets et protections des pistes, ainsi que les positions, dimensions,
couches, nets et verrous des vias. Aucun arrondi n'est appliqué à cette première
comparaison. Une expiration de budget empêcherait de conclure à travail égal.

## Résultats

| Carte | Sans corridor avant → après | Réduction | Corridor avant → après | Réduction |
|---|---:|---:|---:|---:|
| complete1, médianes de 3 essais | 5,487 → 4,214 s | 23,2 % | 3,403 → 2,092 s | 38,5 % |
| micro_dmm | 0,701 → 0,614 s | 12,3 % | 0,571 → 0,202 s | 64,7 % |
| chart_plotter_hat | 6,184 → 5,421 s | 12,3 % | 4,795 → 3,645 s | 24,0 % |
| environment_sensor | 3,920 → 3,772 s | 3,8 % | 2,697 → 2,134 s | 20,9 % |
| azukar_fpga | 31,367 → 30,220 s | 3,7 % | 24,169 → 21,681 s | 10,3 % |
| tildagon_base | 51,570 → 49,725 s | 3,6 % | 37,180 → 30,051 s | 19,2 % |

Le cumul PACK0 passe de 93,742 à 89,753 s sans corridor (−4,3 %) et de
69,412 à 57,714 s avec corridor (−16,9 %). L'objectif de 20 % supplémentaires
est dépassé sur complete1 avec G4, mais pas sur chaque carte ni sur le cumul
PACK0. Les grands circuits sont dominés par d'autres coûts. Les petites
différences sur PACK0, mesurées une seule fois, ne sont pas une garantie de gain.

Un contrôle complémentaire de complete1 à vias fixes et sans G4 conserve
8,4176 mm de gain, avec 3,092 → 2,843 s (−8,1 %, un essai par version).
Ce cas profite peu de l'augmentation du cache, conformément au diagnostic.
Avec vias mobiles et G4, les gains de cuivre restent exactement 14,7240 mm
sans corridor et 7,4974 mm avec corridor.

Les 34 exécutions chronométrées couvrent 13 configurations. Pour chacune,
les signatures géométriques avant/après sont identiques. G5 valide dans tous
les cas, aucun budget expiré, aucune entrée réécrite. Les cinq empreintes PACK0
correspondent au manifeste original. Les échecs historiques d'azukar_fpga et
les expirations historiques de tildagon_base ne se reproduisent pas dans cette
campagne, avec ces versions et ce protocole ; cela ne réécrit pas leur historique.

336 tests ciblés passent en 1,55 s : patterns de glissement, rotations/réflexions,
pads, transitions, vias, topologie, corridor, périmètre, G4 et caches. Les deux
nouveaux tests vérifient que la première construction tient compte d'un obstacle
déplacé avant elle, puis que les exclusions de nets restent synchronisées ;
ils vérifient aussi un pipeline corridor complet avec G4 sans création de grille.

Sur complete1 avec vias mobiles et G4, les sorties des deux versions sont
écrites puis réimportées : leurs signatures au nanomètre sont identiques.
Les 111 pistes différentes de l'entrée passent la clearance KRT après relecture,
ainsi que les 7 vias déplacés. Les partitions électriques des 47 nets routés
sont conservées.

## Traces reproductibles

La [synthèse chiffrée](data/gloss_lazy_obstacles_2026_10_12.json) est conservée
dans le dépôt avec les signatures de résultat des 13 configurations.

Dans `C:/Users/frant/Downloads/cube_pcb1/comparaison_gloss_20261012/` :

- `global_audit.py` et les fichiers `global_audit_*.json` : diagnostic préalable ;
- `global_compare.py`, `global_campaign.py` : comparaison des deux moteurs ;
- `global_optimization_comparison.jsonl` : mesures, signatures et journaux ;
- `global_optimization_summary.json` : synthèse des 13 configurations ;
- `global_verify_written.py` : contrôles supplémentaires après écriture/relecture.

Les fichiers PCB d'entrée sont conservés. Cette intervention ne constitue ni
une installation du plugin, ni un DRC natif KiCad/Fusion complet. Les mesures
n'incluent pas l'import natif et le rafraîchissement de l'interface KiCad.
