# Auto-Gloss : extension au-delà du cas des vias

Analyse des 33 nets de tildagon_base (PACK0) nécessitant des transformations
après leur premier passage. Les statistiques des 164 séquences existantes sont
réutilisées sans nouvelle campagne de performance. Quatre relectures diagnostiques
complémentaires capturent les géométries de chaque étape pour les nets 66, 141,
39 et 176. Aucun changement des algorithmes de production ou de KRT.

## Le mécanisme des vias n'est pas général

| Situation pendant toute la séquence | Nets parmi les 33 |
|---|---:|
| Aucun via sur le net | 9 |
| Vias présents, mais aucun mouvement G3.1/G3.4 | 17 |
| Au moins un mouvement G3.1/G3.4 | 7 |

26/33 = 78,8 % des nets n'ont aucun mouvement de via. Les neuf nets sans via
sont 32, 66, 70, 72, 91, 93, 105, 106 et 141. Ils réfutent directement l'idée
que toutes les reprises autonomes sont dues au déplacement d'un via.

Les sept séquences contenant un mouvement de via sont celles des nets 59, 60,
138, 150, 170, 175 et 176. Cette présence n'attribue pas causalement toutes les
reprises à ce mouvement. Exemple : sur 138, la seconde passe ne fait que réduire
le nombre de segments à longueur égale.

Les 26 séquences sans mouvement de via totalisent 5,2260 mm de gain après le
premier passage ; les sept autres 7,6981 mm. Ce sont les gains d'expériences
indépendantes avec voisins figés, pas un gain combiné validé sur un PCB.

## Quatre cas détaillés

| Net | Vias | Appels, confirmation comprise | Observation |
|---|---:|---:|---|
| 66 /GPIO/CLS5 | 0 | 3 | G3 seul modifie la piste aux passes 1 et 2 |
| 141 /LED_DATA | 0 | 5 | G3 et local à la passe 1, puis G3 seul aux passes 2 à 4 |
| 39 /GPIO/ALS1 | 2 fixes | 3 | Reprise de réduction à longueur égale à la passe 2 |
| 176 /INT_ACCEL | 4 | 5 | Un via bouge à la passe 1 ; il reste fixe pendant les trois reprises |

### 66 : G3 ne ferme pas ses propres transformations

À la passe 1, G3 déplace notamment un coude de (130,5 ; 108,0) à
(130,5 ; 108,282843), et l'autre extrémité de la diagonale de (129,05 ; 106,55)
à (128,767157 ; 106,55). Les autres étapes de cette passe ne changent pas le net.

À la passe 2, G3 utilise cette nouvelle extrémité (130,5 ; 108,282843) pour
réécrire une fenêtre de trois segments : la portion horizontale passe de y=106,55
à y=106,75, avec les coudes voisins ajustés. Gain supplémentaire : 0,1657 mm.

Le code de `_best_chain_replacement` construit les alternatives depuis les points
de la chaîne reçue. Une fois la géométrie retenue appliquée, `shorten_routes`
passe à la chaîne suivante ; il ne reconstruit pas immédiatement les possibilités
de la chaîne modifiée jusqu'à stabilité. Les nouvelles positions intermédiaires
ne deviennent donc des points d'entrée pour une nouvelle recherche qu'au passage
suivant. Il s'agit d'une limite de fermeture des transformations, même sans via
et sans intervention d'une étape ultérieure.

### 141 : quatre transformations successives sans aucun via

Gains par passe : 0,4293 / 0,5657 / 0,1464 / 0,1657 / 0 mm.
La première G3 crée une petite portion verticale de 0,1 mm près de (96 ; 75).
Le local de fin de passe réécrit cette zone autour de x=96,2. La G3 suivante
déplace cette portion à x=96,6. La passe 3 remplace un angle par un raccord
diagonal, créant le point (96,6 ; 75,05). La passe 4 reprend une fenêtre adjacente
avec cette nouvelle extrémité et raccourcit encore le trajet.

Deux mécanismes se succèdent : interaction G3/local à la première passe, puis
G3 qui profite des nouveaux points produits par sa propre exécution précédente.
La dernière reprise gagne plus que l'avant-dernière : la décroissance des gains
par passe n'est pas monotone.

### 39 : stabilité de longueur et stabilité de géométrie sont différentes

Les deux vias restent fixes. À la passe 1, G3, la réduction à longueur égale,
la fusion et le local modifient différentes portions. Le local réécrit notamment
des coordonnées proches de (117,9405 ; 77,25) et (120,0284 ; 78,04).

À la passe 2, G3.5 remplace quatre segments entre (117,9405 ; 77,25) et
(120,238406 ; 78,25) par deux segments, sans gain de longueur significatif.
La trace établit cette succession ; elle ne permet pas d'attribuer exclusivement
le déblocage au petit arrondi plutôt qu'aux autres modifications de la passe 1.

Les neuf séquences sans gain supplémentaire significatif ont une activité de
réduction à longueur égale à la seconde passe. Elles ne sont donc pas assimilables
à neuf recherches totalement inutiles.

### 176 : un via intervient, mais ne bouge pas à chaque reprise

Le via concerné est déplacé à la passe 1, puis ses coordonnées restent
(92,4 ; 123,5) pendant les passes 2, 3, 4 et 5. Les gains supplémentaires sont
1,3826 / 0,4971 / 0,1657 mm, essentiellement portés par G3.
Ce cas n'est donc pas la même alternance répétée via/coude que /GPIO/BTN4.
Le rôle déclencheur éventuel du premier déplacement n'est pas isolé par un
contre-essai : on ne conclut pas que le via est sans influence.

## Conséquences pour les correctifs

1. La correction couplée via/coudes reste pertinente pour les cas tels que BTN4,
   mais elle ne résoudra pas la majorité des reprises autonomes recensées ici.
2. G3 devrait pouvoir réexaminer les fenêtres affectées par ses propres nouveaux
   points, plutôt que d'attendre un nouveau passage de toute la chaîne globale.
3. Une modification tardive de type local/fusion/réduction à longueur égale doit
   pouvoir réactiver les recherches voisines devenues pertinentes.
4. Ce réveil devrait être local et borné : relancer toute la recherche G3 coûteuse
   jusqu'à stabilité après chaque changement pourrait dégrader le temps réel.

La programmation dynamique sélectionne un chemin dans les candidats générés à
partir d'une géométrie donnée ; elle ne prouve pas l'optimalité sur toutes les
géométries que des réécritures successives pourraient créer. Cette distinction
explique pourquoi un appel complet peut produire de nouveaux candidats utiles
au prochain appel, sans contradiction avec le choix du meilleur chemin courant.

## Validation et données

Les quatre traces atteignent les mêmes nombres d'appels que la mesure initiale,
passent G5 et conservent les SHA256 des sources. Aucun nouveau chronométrage
comparatif, aucun DRC natif KiCad, aucune intégration de correctif.

Reproduction, une fois par net :
`python tools/trace_btn4_passes.py --net <66|141|39|176> --output <trace.json>`.

Données : `data/self_gloss_extended_traces_2026_09_07.json`.
Statistiques initiales : `data/net_self_convergence_tildagon_2026_09_07.json`.

Voir aussi [le cas BTN4](BTN4_PASS_ANALYSIS_2026_09_07.md).
