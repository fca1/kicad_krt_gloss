# Combien de fois glosser un net pour stabiliser sa propre géométrie ?

Mesure demandée sur tildagon_base, carte complexe de PACK0, le 7 septembre 2026.
Il s'agit d'isoler la dépendance A envers ses propres modifications, sans faire
intervenir les changements des nets voisins.

## Protocole

Une séquence indépendante par net, pour les 164 nets routés éligibles. Chaque
séquence repart de la carte d'entrée : les résultats du net précédent sont
restaurés avant de commencer le suivant. Les autres nets sont donc fixes à leur
géométrie originale pendant toute la séquence. Des assertions vérifient leurs
signatures après chaque séquence, puis la restauration du net testé.

Un appel exécute `_run_optimization_pass` sur le seul net : chaîne de production
G3, vias, pads, jonctions, raffinements, réductions à longueur égale, fusion et
réduction locale, avec les validations de cette chaîne. G4 est désactivé, ainsi
que Centering et le seuil de rendement de 1 %. Corridor=False, grille 0,1 mm.

On répète jusqu'à ce qu'un appel complet ne modifie plus la signature géométrique
du net. Ce dernier appel est compté comme confirmation, pas comme amélioration.
La stabilité est celle des méthodes et de leurs limites internes actuelles ;
elle ne prouve pas un optimum global de longueur.

Garde-fous de l'expérience : 50 appels ou 120 s par net, détection de cycles.
Ils ne sont atteints par aucun net. Aucun préchauffage ni répétition statistique :
les appels successifs transforment la sortie du précédent conformément au test.
Le contexte KRT est réutilisé ; à chaque restauration, les obstacles du net sont
actualisés, les modèles concernés invalidés et les caches de recherches/adapter
réinitialisés. G5 est exécuté sur le résultat final de chaque séquence.

Code de production au commit `811c37a`, KRT inchangé au commit
`0aff32c04fa51b4d53ecabc843b09b356aaef94b`.

## Nombre de passages

| Passages modifiant la géométrie | Appels nécessaires avec confirmation | Nets | Part |
|---:|---:|---:|---:|
| 0 | 1 | 24 | 14,6 % |
| 1 | 2 | 107 | 65,2 % |
| 2 | 3 | 30 | 18,3 % |
| 4 | 5 | 3 | 1,8 % |

Les 164 nets atteignent un point fixe et passent G5. Aucun cycle, aucune erreur,
aucun arrêt sur budget ou plafond de passes. 343 appels au total ; médiane de
2 appels et moyenne de 2,09, confirmation comprise.

131 nets sur 164 (79,9 %) n'ont besoin d'aucune transformation après le premier
appel. En revanche, 33 nets (20,1 %) bénéficient de transformations supplémentaires
sans aucun changement étranger. Parmi eux, 24 gagnent plus de 0,000001 mm après
le premier appel ; 9 changent de géométrie sans gain de longueur significatif.
La dépendance envers soi-même est donc observable, et pas seulement théorique.

## Gains et temps par rang d'appel

Seuls les nets encore modifiés à l'appel précédent poursuivent leur séquence.

| Rang d'appel | Nets testés | Nets modifiés | Somme des gains indépendants | Temps cumulé des appels |
|---|---:|---:|---:|---:|
| 1 | 164 | 140 | 75,8117 mm | 31,855 s |
| 2 | 140 | 33 | 10,5693 mm | 14,486 s |
| 3 | 33 | 3 | 1,5635 mm | 3,471 s |
| 4 | 3 | 3 | 0,7914 mm | 0,143 s |
| 5 | 3 | 0 | 0,0000 mm | 0,089 s |

Les reprises ajoutent 12,9241 mm aux 75,8117 mm du premier appel, soit environ
17,0 % de gain supplémentaire dans ces expériences indépendantes.
La somme finale de 88,7359 mm n'est pas la réduction d'une carte combinant tous
ces résultats : les modifications obtenues séparément ne sont pas validées
simultanément et ne doivent pas être assemblées sans revalidation.

Les appels cumulent 50,044 s, dont 18,189 s après les premiers appels. Les derniers
appels sans changement, y compris les 24 nets stables d'emblée, coûtent 11,838 s,
soit 23,7 % du temps des appels. Ce temps de confirmation n'est pas une économie
automatiquement récupérable : il faudrait un certificat permettant de l'éviter.

Mesures séparées : préparation 1,650 s, certifications G5 finales 1,032 s,
restaurations/réinitialisations 0,636 s. Le temps des appels n'inclut pas les
assertions entre séquences, l'écriture des statistiques ou ces préparations.
Il ne faut pas comparer directement ces 50 s au Gloss global à 120 s : état des
voisins, ordre des opérations et périmètres sont différents.

## Les trois nets nécessitant cinq appels

| Net | Nom | Gain appel 1 | Gain appel 2 | Gain appel 3 | Gain appel 4 | Appel 5 |
|---:|---|---:|---:|---:|---:|---|
| 59 | /GPIO/BTN4 | 0,4601 mm | 0,9200 mm | 0,9200 mm | 0,4600 mm | Stable |
| 141 | /LED_DATA | 0,4293 mm | 0,5657 mm | 0,1464 mm | 0,1657 mm | Stable |
| 176 | /INT_ACCEL | 2,7904 mm | 1,3826 mm | 0,4971 mm | 0,1657 mm | Stable |

Un gain ultérieur peut dépasser le premier ou remonter après une baisse.
Ces exemples ne suivent pas une décroissance stricte à chaque appel.
À l'inverse, le net GND est le plus coûteux (7,266 s, certification comprise),
mais n'a besoin que de trois appels ; 3V3_SYS suit avec 4,696 s et trois appels.
Le nombre de passages ne suffit donc pas à estimer la charge.

## Conséquence pour G4

La reprise immédiate du net modifié peut achever les cascades de transformations
locales sans attendre un nouveau tour global. Sur cette carte et cet état initial,
elle se stabilise en au plus quatre appels modifiants. Une fois stabilisé, le net
n'a plus à se réveiller pour ses seules anciennes modifications : il attend un
changement de dépendance extérieure ou un changement de politique de recherche.

Cette mesure motive un essai d'ordonnancement par stabilisation locale, mais ne
valide pas encore son temps global ni son résultat lorsque les voisins changent.
Aucun nouvel ordonnancement n'est intégré ici. Le critère d'arrêt sur le gain de
longueur reste distinct de la stabilité géométrique et peut ignorer des réductions
de segments à longueur égale.

## Artefacts et vérification

- [Détail de chacun des 164 nets](NET_SELF_CONVERGENCE_DETAILS_2026_09_07.md)
- Données avec les étapes de chaque appel :
  `data/net_self_convergence_tildagon_2026_09_07.json`
- Reproduction : `python tools/benchmark_net_self_convergence.py`

Les assertions contrôlent la conservation des nets étrangers, les restaurations,
le point fixe final et la cohérence des compteurs. Chaque résultat individuel
passe G5 ; le fichier PCB source reste inchangé, vérifié par SHA256. Aucun DRC
natif KiCad ni remplissage de zones n'est lancé. Aucun code de production ou
KRT modifié, aucun PCB de sortie ni ZIP créé.
