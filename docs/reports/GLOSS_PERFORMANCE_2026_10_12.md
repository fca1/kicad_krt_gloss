# Gloss : réduction du coût des améliorations Fusion — 12 octobre 2026

## Cause établie

La révision `a4a10bd` améliore le résultat de `complete1`, mais ajoute des
affinements de glissement et des recherches de préfixes depuis les pads.
Le profil confirme leur coût : 3 778 sondages de glissement, contre un moteur
antérieur qui n'affinait pas le dernier intervalle. Parmi 176 affinements,
126 ne peuvent pas atteindre le gain minimal ; parmi 227 recherches de
connecteurs de pad, 126 ont une borne de gain insuffisante.
La transition de largeur est peu coûteuse : 96 recherches, environ 0,02 s
cumulée dans le diagnostic initial. Elle n'explique pas le ralentissement.

Le passage comparé de `10f4b56` à `a4a10bd` utilise la même révision KRT
`9577628635e3de81d2c1fd8ac882254c0fa7d032` et le même binaire local.
Le ralentissement constaté entre ces essais n'est donc pas une mesure de
migration KRT 0.22 → 0.23. KRT 0.23 comporte toutefois des changements de
lissage, de contacts de pads, de règles et d'invalidation de cache : son effet
général ne peut pas être déduit de cette comparaison. Un essai séparé avec
le binaire officiel 0.23 donne la même géométrie, sans ralentissement observé.

## Modifications retenues

- Avant d'affiner un intervalle de glissement refusé, calculer le gain maximal
  depuis la dérivée de longueur et la borne de déplacement. La longueur est
  affine avant inversion d'un segment. Si même cette borne ne suffit pas,
  conserver le meilleur candidat déjà trouvé sans affinement supplémentaire.
- Avant d'énumérer les familles de connecteurs d'un pad, calculer la longueur
  minimale octolinéaire entre le centre du pad et l'ancre. Abandonner seulement
  si aucune famille ne peut atteindre le gain minimal.
- Préparer l'ordre et les directions des arêtes du graphe une seule fois par
  chaîne. Les tentatives successives après rejet KRT réutilisent ces données.
  Ce cache local disparaît avec la recherche ; il ne contient aucune décision
  de clearance et n'est pas partagé entre révisions du cuivre.

Les deux bornes gardent une marge numérique conservatrice : les cas proches
du seuil suivent la recherche d'origine. Ni seuil de gain, ni précision
d'affinement, ni arrondi d'écriture, ni contrôles KRT/corridor ne sont réduits.
Le contrôle des coordonnées écrites au nanomètre est conservé intégralement.
La réutilisation des certificats exacts identiques existait déjà dans l'adaptateur ;
aucun nouveau cache de clearance n'est ajouté. Aucune source KRT modifiée.

## Mesures sur complete1

Comparaison avec `a4a10bd`, entrée `complete1_import.kicad_pcb` inchangée,
même binaire KRT local, grille 0,1 mm, clearance 0,1524 mm, bord 0,3 mm,
trous 0,254 mm, G4 désactivé, budget 20 s. Trois exécutions sans profileur
par configuration ; parsing et écriture exclus du chronométrage. Les séries
avant/après sont séquentielles, sans calcul de benchmark concurrent.

| Configuration | Avant, médiane | Après, médiane | Réduction mesurée | Gain de cuivre conservé |
|---|---:|---:|---:|---:|
| Vias fixes, sans corridor | 5,461 s | 3,875 s | 29,0 % | 8,4176 mm |
| Vias fixes, corridor | 2,327 s | 2,311 s | 0,7 % | 4,0446 mm |
| Vias mobiles, sans corridor | 5,783 s | 3,379 s | 41,6 % | 13,5903 mm |

Le corridor ne présente pas de gain temporel significatif. Les temps dépendent
de la charge et de l'état de la machine : une série exploratoire précédente
à vias fixes donnait 4,320 → 3,775 s, soit 12,6 %. Les pourcentages ci-dessus
sont les observations de la série finale, pas une garantie de vitesse.
On ne retrouve pas le temps de l'ancien moteur, qui obtenait un gain de cuivre
bien inférieur. Les contrôles exacts des candidats utiles restent nécessaires.

Le profil séparé confirme la réduction du travail indépendamment du bruit
de chronométrage : sondages de glissement 3 778 → 1 258 ; appels à
`segment_clears` 28 548 → 20 640 ; calculs de directions 142 373 → 11 865.
Les directions du graphe ne sont plus recalculées à chaque état et à chaque rejet. Les recherches de pads utiles
et les validations exactes restent les prochains postes à étudier ; aucune
réduction arbitraire du nombre de candidats n'a été introduite.

## Non-régression

Les signatures des pistes et des vias en mémoire sont strictement identiques
avant/après pour les 18 exécutions, au sein de chacun des trois modes.
Les signatures après arrondi au nanomètre sont également identiques.
G5 valide partout, sans expiration de budget.

La sortie à vias fixes est écrite et relue pour les deux versions. La sortie
optimisée conserve exactement les pistes du précédent fichier amélioré :
655 segments, 117 vias. Les 93 segments différents de l'entrée passent de
nouveau la clearance KRT après relecture. Les partitions électriques des
47 nets routés sont inchangées.

321 tests ciblés passent en 1,78 s, dont 49 nouveaux tests de filtrage :
rotations/réflexions, affinement inutile, petit gain encore utile, marge au
seuil, conservation des égalités et des résultats après rejets KRT successifs.
Cette validation ne constitue pas un DRC natif complet ou une campagne PACK0.
Le plugin n'est pas installé par cette intervention.

## Traces locales

Dans `C:/Users/frant/Downloads/cube_pcb1/comparaison_gloss_20261012/` :

- `perf_gloss.py`, `perf_profile_before.prof`, `perf_profile_bounds.prof`,
  `perf_profile_paths.prof` : mesures exploratoires et profils séparés.
- `perf_matched.py`, `perf_matched_before.json`, `perf_matched_after.json` :
  série finale ; le script recharge le code `a4a10bd` pour le mode `before`.
- `complete1_perf_before.kicad_pcb`, `complete1_perf_after.kicad_pcb` : sorties
  réimportées pour vérifier la sérialisation.
- `perf_verification.json` : clearance des 93 segments et partitions des 47 nets.

Les fichiers d'entrée et les rapports de comparaison Fusion sont conservés.
