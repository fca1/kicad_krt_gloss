# Auto gloss : recherche commune longueur / segments — 7 septembre 2026

## Proposition testée

Prototype `tools/joint_gloss.py`, copie statique et isolée des deux fonctions de
recherche/traitement de `dgloss/algorithm.py` au commit 9cd6a43. Production et KRT
inchangés. Activation uniquement dans le banc de diagnostic par `--joint-gloss`.
Le patch est mono-thread et restauré même sur exception. G4 est désactivé.

Le graphe de recherche reçoit simultanément les raccourcissements et les
simplifications à longueur égale. La longueur reste prioritaire et le nombre de
segments départage les longueurs égales. Les segments colinéaires consécutifs
orientés dans le même sens sont fusionnés **dans les candidats**, avant filtrage
et validation KRT. Aucune suppression aveugle de petit segment, aucun déplacement
de cuivre pendant cette fusion, aucun arrondi ajouté. Les contrôles KRT exacts,
la connectivité, les règles de jonction et les seuils de gain sont conservés.

Le même moteur commun est appelé à l'emplacement G3 et à l'ancien emplacement
G3.5, après les déplacements de vias/pads/jonctions. Ces deux emplacements sont
conservés pour les modifications intermédiaires : les objectifs sont réunis,
mais il reste deux occasions de recherche dans le pipeline. Les caches existants
sont réutilisés. Aucune file auto gloss, aucune boucle supplémentaire de passes.
Le chemin `stay_in_corridor=True` conserve son comportement de production ; cette
expérience mesure uniquement le chemin général `stay_in_corridor=False`.

**Limite importante :** les sommets du graphe restent ceux présents au début de
la recherche. Les candidats peuvent avoir leurs propres coudes, mais ceux-ci ne
sont pas ajoutés comme nouveaux sommets pour d'autres candidats pendant ce même
appel. Ce prototype teste donc l'unification des objectifs et la simplification
des candidats existants, pas encore une reconstruction générale qui compose des
transformations autour de nouveaux sommets, ni le déplacement couplé via/coude.
Les fusions entre plusieurs candidats sélectionnés restent à l'étape de fusion
existante. Il ne faut pas assimiler cette version à une résolution locale optimale.

## Protocole

164 nets de tildagon_base, carte complexe PACK0, voisins fixes à la géométrie
originale. Chaque net repart de la carte source. Une séquence par net, sans
préchauffage ni répétition statistique ; les appels successifs mesurent la
convergence et incluent une confirmation sans modification. G4 et Centering
désactivés, grille 0,1 mm, limite 50 appels/120 secondes par net, non atteinte.
Le seuil marginal de 1 % n'intervient pas dans ce diagnostic de point fixe.

Comparaison aux deux mesures historiques du même protocole. Les temps sont des
observations uniques, pas une estimation statistique de performances. Aucun test
unitaire parallèle au benchmark de cette nouvelle variante. Les gains sont des
sommes d'expériences indépendantes, pas le résultat d'une carte combinée.

## Résultats

Les temps cumulent les appels algorithmiques, hors initialisation, restauration
et G5 final. Le débit compte 164 nets uniques, confirmation comprise.

| Mesure | Production de référence | Auto gloss, file de chaînes | Recherche commune |
|---|---:|---:|---:|
| Temps premiers appels | 31,855 s | 39,709 s | 45,395 s |
| Gain premiers appels | 75,8117 mm | 82,0615 mm | 83,0155 mm |
| Temps jusqu'à stabilité confirmée | 50,044 s | 55,787 s | 60,828 s |
| Nets/sec jusqu'à confirmation | 3,28 | 2,94 | 2,70 |
| Gain jusqu'à confirmation | 88,7359 mm | 90,0613 mm | 87,4026 mm |
| Nombre total d'appels | 343 | 329 | 326 |
| Nets avec plusieurs appels productifs | 33 | 23 | 20 |
| Maximum d'appels, confirmation comprise | 5 | 5 | 4 |
| G5 valide | 164/164 | 164/164 | 164/164 |

Recherche commune : 24 nets en un appel, 120 en deux, 18 en trois, deux en quatre.
La durée totale augmente de 21,5 % par rapport à la référence et le gain final
baisse de 1,3333 mm (1,50 %). Stabiliser plus vite en nombre d'appels n'implique
donc ni une exécution plus rapide ni une meilleure solution géométrique.

## Où se situe le surcoût mesuré ?

| Temps d'étape cumulé | Référence | Recherche commune |
|---|---:|---:|
| G3 | 32,275 s | 34,337 s |
| Ancien G3.5 longueur égale | 2,645 s | 11,328 s |
| G3 local | 6,444 s | 6,910 s |

L'ancien emplacement G3.5 effectue désormais la recherche générale, ce qui
représente +8,682 secondes, soit environ 80 % de l'écart temporel global observé.
Ce tableau localise le coût dans le pipeline ; il ne sépare pas la génération
des candidats, les validations KRT et le traitement des caches. La variante
évalue davantage de possibilités après les autres transformations.

Les libellés internes du pipeline restent historiques : `G3.5 equal length`
et son compteur `saved_mm=0` ne décrivent plus l'objectif de cet emplacement dans
le prototype. Les gains du rapport proviennent des longueurs réelles avant/après
chaque appel, pas de la somme de ces compteurs d'étapes.

## Convergence et qualité

| Net | Appels référence → commun | Observation |
|---|---:|---|
| 15 GND | 3 → 2 | Gain final conservé. |
| 39 /GPIO/ALS1 | 3 → 2 | Simplification absorbée plus tôt ; écart final négligeable. |
| 66 /GPIO/CLS5 | 3 → 2 | Gain final conservé. |
| 59 /GPIO/BTN4 | 5 → 4 | G3.5 peut désormais raccourcir après le via, mais le couplage reste non résolu. |
| 141 /LED_DATA | 5 → 4 | Des nouveaux sommets restent à exploiter à l'appel suivant. |
| 176 /INT_ACCEL | 5 → 3 | Gain final conservé. |
| 175 /USBSEL | 3 → 2 | Stabilisation plus précoce, mais perte de gain de 0,9891 mm. |
| 150 3V3_SYS | 3 → 3 | Perte de gain de 0,7000 mm. |

Autre perte notable : net106, 0,0586 mm. Gains supplémentaires sur les nets38
(+0,2485 mm) et133 (+0,1657 mm). Des écarts plus petits existent aussi ; tableau
exhaustif ci-dessous.

Sur USBSEL, la référence déplace le via avec un gain de 0,1491 mm au premier
appel puis de 0,7200 mm au deuxième ; le prototype obtient 0,7200 mm dès le premier
appel et ne progresse plus ensuite. Cela démontre une trajectoire d'optimisation
différente, sans prouver à lui seul quelle contrainte géométrique bloque la suite.
Sur 3V3_SYS, le déplacement de via rapportant 0,7 mm au deuxième appel de référence
n'apparaît plus. Une trace géométrique serait nécessaire pour attribuer précisément
ces pertes ; elles ne sont pas expliquées par les seuls compteurs d'étapes.

## Vérifications et décision

164 points fixes, aucun cycle externe, aucune erreur, aucun plafond atteint.
G5 valide chaque expérience (partition des terminaux et clearance du cuivre
modifié). Assertions : nets étrangers inchangés, restauration du net, aucun
segment de sortie périmé et SHA256 source inchangé. Ce n'est pas un DRC KiCad
complet et les pertes de qualité ci-dessus sont des régressions d'optimisation.
24 tests ciblés distincts passent : sept tests du prototype et les 17 tests
existants microsegments/glissement. Un test construit dans une même recherche
une simplification neutre et un raccourcissement, puis vérifie avec KRT leur
acceptation conjointe. Les autres couvrent les deux objectifs et la fusion
colinéaire sans suppression de retour en arrière ou de petit segment.

**Ne pas activer cette variante en production en l'état.** Réunir les objectifs
est réalisable mais ne suffit pas : la structure des candidats conserve une
partie de la séparation géométrique, et l'appel général à l'ancien emplacement
G3.5 est coûteux. La prochaine correction devrait construire des candidats
composés autour des nouveaux sommets, sur des fenêtres bornées, et traiter le
via avec ses coudes lorsque cette dépendance existe. Ces évolutions ne sont pas
implémentées dans cette variante.

## Détail par net

| Net | Nom | Appels réf. | Appels communs | Gain réf. mm | Gain commun mm | Temps réf. s | Temps commun s |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | /SFPs/PORTA_3V3 | 1 | 1 | 0.000000 | 0.000000 | 0.0289 | 0.0276 |
| 2 | Net-(U8-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0043 | 0.0039 |
| 13 | Net-(J8-CC1) | 2 | 2 | 0.000029 | 0.000029 | 0.0514 | 0.0534 |
| 14 | Net-(J8-CC2) | 2 | 2 | 0.000028 | 0.000028 | 0.1240 | 0.1184 |
| 15 | GND | 3 | 2 | 8.403528 | 8.403528 | 6.1722 | 7.7018 |
| 16 | Net-(AE1-FEED) | 2 | 2 | 0.248539 | 0.248539 | 0.0446 | 0.0699 |
| 17 | Net-(U1-LNA_IN) | 2 | 2 | 0.000015 | 0.000015 | 0.0125 | 0.0177 |
| 18 | /USB- | 2 | 2 | 0.000029 | 0.000029 | 0.0460 | 0.0564 |
| 19 | /USB+ | 1 | 1 | 0.000000 | 0.000000 | 0.0224 | 0.0285 |
| 25 | /~{ESPRESET} | 2 | 2 | 1.249651 | 1.249651 | 0.7400 | 1.2703 |
| 27 | /~{BOOTLOADER} | 2 | 3 | 0.849472 | 0.849485 | 0.6277 | 0.9847 |
| 28 | /~{QON} | 2 | 2 | 0.000008 | 0.000009 | 0.0613 | 0.0799 |
| 29 | /SFPs/A_NDET | 2 | 2 | 0.000209 | 0.000209 | 0.0733 | 0.0914 |
| 30 | /SFPs/A_LSEN | 2 | 2 | 0.165685 | 0.165685 | 0.0152 | 0.0186 |
| 31 | /SFPs/PORTB_3V3 | 1 | 1 | 0.000000 | 0.000000 | 0.0063 | 0.0074 |
| 32 | /SFPs/B_NDET | 3 | 2 | 0.527208 | 0.527208 | 0.0781 | 0.0845 |
| 33 | Net-(U9-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0040 | 0.0050 |
| 34 | /SFPs/B_LSEN | 1 | 1 | 0.000000 | 0.000000 | 0.0864 | 0.0973 |
| 35 | /SFPs/PORTC_3V3 | 2 | 2 | 0.911270 | 0.911270 | 0.0359 | 0.0490 |
| 36 | /SFPs/C_NDET | 2 | 2 | 0.000026 | 0.000026 | 0.0273 | 0.0368 |
| 37 | Net-(U10-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0041 | 0.0051 |
| 38 | /SFPs/C_LSEN | 2 | 2 | 0.436806 | 0.685303 | 0.0709 | 0.1196 |
| 39 | /GPIO/ALS1 | 3 | 2 | 0.434934 | 0.434950 | 0.1465 | 0.1678 |
| 40 | /GPIO/ALS2 | 2 | 2 | 0.248554 | 0.248554 | 0.1502 | 0.2538 |
| 41 | /GPIO/ALS3 | 3 | 3 | 0.536436 | 0.536436 | 0.3410 | 0.4703 |
| 42 | /GPIO/ALS4 | 2 | 2 | 0.348044 | 0.348044 | 0.1855 | 0.2436 |
| 43 | /GPIO/ALS5 | 3 | 2 | 0.579938 | 0.579938 | 0.1810 | 0.2524 |
| 44 | /GPIO/DET_A | 2 | 2 | 1.539712 | 1.539712 | 0.2959 | 0.4669 |
| 45 | /GPIO/DET_B | 1 | 1 | 0.000000 | 0.000000 | 0.0149 | 0.0191 |
| 46 | /GPIO/BLS1 | 2 | 2 | 0.322183 | 0.322183 | 0.0440 | 0.0581 |
| 47 | /GPIO/BLS2 | 2 | 2 | 0.165690 | 0.165690 | 0.0268 | 0.0381 |
| 48 | /GPIO/LED_PWR_EN | 2 | 2 | 0.297028 | 0.297028 | 0.1702 | 0.2930 |
| 49 | /GPIO/BTN1 | 2 | 2 | 0.263657 | 0.263657 | 0.1625 | 0.2754 |
| 50 | /GPIO/BTN2 | 2 | 2 | 0.579931 | 0.579931 | 0.1047 | 0.1615 |
| 51 | /GPIO/BLS3 | 2 | 2 | 0.248539 | 0.248539 | 0.0373 | 0.0513 |
| 52 | /GPIO/BLS4 | 2 | 2 | 0.662752 | 0.662752 | 0.0674 | 0.1051 |
| 53 | /GPIO/BLS5 | 2 | 2 | 0.000005 | 0.000005 | 0.0628 | 0.1007 |
| 54 | /GPIO/DET_C | 2 | 2 | 0.165686 | 0.165686 | 0.0169 | 0.0234 |
| 55 | /GPIO/DET_D | 3 | 2 | 0.414269 | 0.414269 | 0.2245 | 0.2834 |
| 56 | /GPIO/DET_E | 2 | 2 | 0.020947 | 0.020947 | 0.4089 | 0.6052 |
| 57 | /GPIO/DET_F | 2 | 2 | 0.331444 | 0.331444 | 1.6290 | 1.8709 |
| 58 | /GPIO/BTN3 | 2 | 2 | 0.353582 | 0.353582 | 0.2472 | 0.3621 |
| 59 | /GPIO/BTN4 | 5 | 4 | 2.760071 | 2.760071 | 0.4839 | 0.7144 |
| 60 | /GPIO/BTN5 | 3 | 2 | 0.840025 | 0.840025 | 0.3211 | 0.3938 |
| 61 | /GPIO/BTN6 | 2 | 2 | 0.165694 | 0.165694 | 0.1738 | 0.2342 |
| 62 | /GPIO/CLS1 | 2 | 2 | 0.000048 | 0.000048 | 0.0533 | 0.0629 |
| 63 | /GPIO/CLS2 | 2 | 2 | 0.974874 | 0.974874 | 0.0661 | 0.0815 |
| 64 | /GPIO/CLS3 | 2 | 2 | 0.008243 | 0.008243 | 0.0778 | 0.0944 |
| 65 | /GPIO/CLS4 | 2 | 2 | 0.496167 | 0.496167 | 0.0937 | 0.1298 |
| 66 | /GPIO/CLS5 | 3 | 2 | 0.339608 | 0.339608 | 0.1219 | 0.1393 |
| 67 | /USB/CC1 | 2 | 3 | 0.117159 | 0.117159 | 0.1076 | 0.1991 |
| 68 | /USB/CC2 | 2 | 2 | 0.991127 | 0.991127 | 0.0786 | 0.1045 |
| 69 | /SFPs/PORTD_3V3 | 2 | 2 | 0.499666 | 0.499666 | 0.0303 | 0.0421 |
| 70 | /SFPs/PORTE_3V3 | 3 | 2 | 1.193640 | 1.193640 | 0.0427 | 0.0468 |
| 71 | /SFPs/PORTF_3V3 | 2 | 2 | 0.248549 | 0.248549 | 0.0347 | 0.0493 |
| 72 | /SFPs/D_NDET | 3 | 3 | 0.414214 | 0.414214 | 0.0512 | 0.0650 |
| 73 | Net-(U11-SET) | 2 | 2 | 0.033137 | 0.033137 | 0.0153 | 0.0177 |
| 74 | /SFPs/E_NDET | 2 | 2 | 0.231964 | 0.231964 | 0.0452 | 0.0467 |
| 75 | Net-(U12-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0041 | 0.0049 |
| 76 | /SFPs/F_NDET | 2 | 2 | 0.836438 | 0.836438 | 0.1153 | 0.1804 |
| 77 | Net-(U13-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0049 | 0.0054 |
| 78 | /SFPs/D_LSEN | 2 | 2 | 0.165686 | 0.165686 | 0.0245 | 0.0341 |
| 79 | /SFPs/E_LSEN | 2 | 2 | -0.000000 | -0.000000 | 0.0218 | 0.0284 |
| 80 | /SFPs/F_LSEN | 2 | 2 | 1.792772 | 1.792772 | 0.0327 | 0.0458 |
| 81 | /bot-top-link/TOP_VBAT_SW | 2 | 2 | 0.687899 | 0.687899 | 0.0840 | 0.1187 |
| 82 | Net-(D2-DIN) | 1 | 1 | 0.000000 | 0.000000 | 0.0046 | 0.0053 |
| 83 | Net-(U14-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0047 | 0.0050 |
| 84 | Net-(R24-Pad1) | 1 | 1 | 0.000000 | 0.000000 | 0.0039 | 0.0047 |
| 85 | Net-(D2-DOUT) | 1 | 1 | 0.000000 | 0.000000 | 0.0037 | 0.0046 |
| 86 | /bot-top-link/LED_DATA_TOP | 1 | 1 | 0.000000 | 0.000000 | 0.0048 | 0.0064 |
| 87 | /NA_HS1 | 2 | 2 | 0.263624 | 0.263624 | 0.0562 | 0.0737 |
| 88 | /NA_HS2 | 2 | 2 | 0.530856 | 0.530856 | 0.0796 | 0.1168 |
| 89 | /NA_HS3 | 2 | 2 | 0.000005 | 0.000005 | 0.0607 | 0.0810 |
| 90 | /NA_HS4 | 2 | 2 | 0.298106 | 0.298097 | 0.0939 | 0.1345 |
| 91 | /NB_HS1 | 3 | 2 | 0.614681 | 0.614681 | 0.6119 | 0.6796 |
| 92 | /NB_HS2 | 2 | 2 | 0.190786 | 0.190786 | 0.4440 | 0.5703 |
| 93 | /NB_HS3 | 3 | 3 | 0.345149 | 0.345149 | 0.6452 | 0.8790 |
| 94 | /NB_HS4 | 2 | 2 | 0.000015 | 0.000015 | 0.2953 | 0.3379 |
| 95 | /NC_HS1 | 2 | 2 | 0.000026 | 0.000026 | 0.6681 | 0.7231 |
| 96 | /NC_HS2 | 2 | 2 | 0.000061 | 0.000061 | 0.8380 | 0.9404 |
| 97 | /NC_HS3 | 2 | 2 | 0.000100 | 0.000100 | 1.1888 | 1.2528 |
| 98 | /NC_HS4 | 2 | 2 | 0.189752 | 0.189752 | 1.0489 | 1.3003 |
| 99 | /NF_HS1 | 3 | 3 | 0.273056 | 0.273051 | 0.1954 | 0.1886 |
| 100 | /NF_HS2 | 2 | 2 | 0.594105 | 0.594105 | 0.1255 | 0.1245 |
| 101 | /NF_HS3 | 2 | 2 | 0.582860 | 0.582860 | 0.0850 | 0.0836 |
| 102 | /NF_HS4 | 2 | 2 | 0.757389 | 0.757389 | 0.1061 | 0.1045 |
| 103 | /I2C/SDA_A | 2 | 2 | 0.527311 | 0.527311 | 0.2785 | 0.3538 |
| 104 | /I2C/SCL_A | 2 | 2 | 0.576643 | 0.576643 | 0.2212 | 0.2844 |
| 105 | /I2C/SDA_B | 3 | 2 | 0.501476 | 0.501476 | 0.5963 | 0.5659 |
| 106 | /I2C/SCL_B | 3 | 2 | 0.891402 | 0.832839 | 0.5866 | 0.5468 |
| 107 | /I2C/SDA_C | 2 | 2 | 0.165685 | 0.165685 | 0.0246 | 0.0250 |
| 108 | /I2C/SCL_C | 2 | 2 | 0.165685 | 0.165685 | 0.0286 | 0.0295 |
| 109 | /I2C/SDA_D | 2 | 2 | 0.000019 | 0.000019 | 0.0545 | 0.0859 |
| 110 | /I2C/SCL_D | 2 | 2 | 0.000008 | 0.000008 | 0.1195 | 0.1124 |
| 111 | /I2C/SDA_E | 2 | 2 | 0.000073 | 0.000073 | 0.2763 | 0.3650 |
| 112 | /I2C/SCL_E | 2 | 2 | 1.168405 | 1.168405 | 0.2791 | 0.3226 |
| 113 | /I2C/SDA_F | 2 | 2 | 0.678318 | 0.678318 | 1.9864 | 2.2233 |
| 114 | /I2C/SCL_F | 3 | 3 | 0.055053 | 0.055053 | 2.1421 | 2.1793 |
| 115 | /GPIO/DLS1 | 2 | 2 | 0.351472 | 0.351472 | 0.0281 | 0.0418 |
| 116 | /GPIO/DLS2 | 2 | 2 | 0.248549 | 0.248549 | 0.0450 | 0.0503 |
| 117 | /GPIO/DLS3 | 2 | 2 | 0.000000 | 0.000000 | 0.0288 | 0.0268 |
| 118 | /GPIO/DLS4 | 2 | 2 | 0.000009 | 0.000009 | 0.0360 | 0.0351 |
| 119 | /GPIO/DLS5 | 2 | 2 | 0.000019 | 0.000019 | 0.0345 | 0.0325 |
| 120 | /GPIO/ELS1 | 2 | 2 | 0.000006 | 0.000006 | 0.1982 | 0.1947 |
| 121 | /GPIO/ELS2 | 2 | 2 | 0.165706 | 0.165706 | 0.2062 | 0.2476 |
| 122 | /GPIO/ELS3 | 2 | 2 | 0.000014 | 0.000014 | 0.1311 | 0.1466 |
| 123 | /GPIO/ELS4 | 2 | 2 | 0.248549 | 0.248549 | 0.0940 | 0.1058 |
| 124 | /GPIO/ELS5 | 1 | 1 | 0.000000 | 0.000000 | 0.0186 | 0.0250 |
| 125 | /GPIO/FLS5 | 3 | 3 | 0.248570 | 0.248570 | 0.2093 | 0.2167 |
| 126 | /GPIO/FLS4 | 2 | 2 | 0.199044 | 0.199044 | 0.2444 | 0.3094 |
| 127 | /GPIO/FLS3 | 2 | 3 | 0.329021 | 0.329021 | 0.2362 | 0.2979 |
| 128 | /GPIO/FLS2 | 2 | 2 | 0.000065 | 0.000065 | 0.2793 | 0.3472 |
| 129 | /GPIO/FLS1 | 2 | 2 | 1.406322 | 1.406322 | 0.3413 | 0.4524 |
| 130 | /NE_HS1 | 2 | 2 | 0.173993 | 0.173993 | 0.3175 | 0.4465 |
| 131 | /NE_HS2 | 3 | 2 | 0.298248 | 0.298248 | 0.5225 | 0.7245 |
| 132 | /NE_HS3 | 2 | 2 | 0.078872 | 0.078872 | 0.2838 | 0.2811 |
| 133 | /NE_HS4 | 2 | 2 | 0.248576 | 0.414261 | 0.2104 | 0.2872 |
| 134 | /ND_HS1 | 2 | 3 | 0.786704 | 0.786704 | 0.5744 | 0.9340 |
| 135 | /ND_HS2 | 2 | 2 | 0.248580 | 0.248580 | 0.4261 | 0.5399 |
| 136 | /ND_HS3 | 2 | 2 | 0.000087 | 0.000087 | 0.5081 | 0.6381 |
| 137 | /ND_HS4 | 3 | 2 | 0.331465 | 0.331465 | 0.5358 | 0.9190 |
| 138 | /SDA_SYS | 3 | 3 | 1.935205 | 1.935205 | 1.0939 | 1.3842 |
| 139 | /SCL_SYS | 2 | 2 | 1.188604 | 1.188604 | 0.8856 | 1.2124 |
| 140 | /~{INT_SYS} | 3 | 3 | 0.800668 | 0.800682 | 1.0839 | 1.3893 |
| 141 | /LED_DATA | 5 | 4 | 1.307107 | 1.307107 | 0.1192 | 0.1206 |
| 142 | Net-(U3-REGN) | 1 | 1 | 0.000000 | 0.000000 | 0.0042 | 0.0040 |
| 143 | Net-(C26-Pad1) | 2 | 2 | 0.000000 | 0.000000 | 0.0129 | 0.0130 |
| 144 | Net-(U3-BTST) | 1 | 1 | 0.000000 | 0.000000 | 0.0037 | 0.0040 |
| 145 | /USB/BAT+ | 1 | 1 | 0.000000 | 0.000000 | 0.0143 | 0.0134 |
| 146 | /USB/STAT | 3 | 3 | 4.363072 | 4.363091 | 0.3888 | 0.4577 |
| 147 | Net-(D1-A) | 1 | 1 | 0.000000 | 0.000000 | 0.0049 | 0.0048 |
| 148 | Net-(U3-ILIM) | 1 | 1 | 0.000000 | 0.000000 | 0.0058 | 0.0059 |
| 149 | Net-(U3-TS) | 2 | 2 | 0.000011 | 0.000011 | 0.0563 | 0.0559 |
| 150 | 3V3_SYS | 3 | 3 | 13.252911 | 12.552917 | 4.6121 | 6.0016 |
| 151 | Net-(U43-FB) | 1 | 1 | 0.000000 | 0.000000 | 0.0129 | 0.0132 |
| 152 | Net-(U43-SW) | 1 | 1 | 0.000000 | 0.000000 | 0.0038 | 0.0037 |
| 154 | /USB/PMID | 3 | 2 | 1.968221 | 1.968221 | 0.4263 | 0.5071 |
| 155 | /VSYS | 2 | 2 | 0.779096 | 0.779096 | 0.0784 | 0.0892 |
| 156 | /USB/HOST_D+ | 2 | 2 | 0.000038 | 0.000038 | 0.1467 | 0.1654 |
| 157 | /USB/HOST_D- | 2 | 2 | 0.000036 | 0.000036 | 0.1216 | 0.1559 |
| 158 | /SDA_HOST | 2 | 2 | 0.000084 | 0.000084 | 0.2187 | 0.2308 |
| 159 | /SCL_HOST | 2 | 2 | 0.000013 | 0.000013 | 0.3164 | 0.3232 |
| 160 | /USB/PMIC_OTG | 2 | 2 | 0.165703 | 0.165703 | 0.0859 | 0.0887 |
| 161 | /TOP_HS1 | 2 | 2 | 0.000042 | 0.000042 | 0.0520 | 0.0674 |
| 162 | /TOP_HS2 | 2 | 2 | 0.000011 | 0.000011 | 0.0396 | 0.0468 |
| 163 | /TOP_HS3 | 2 | 2 | 0.000021 | 0.000021 | 0.0841 | 0.0830 |
| 164 | /TOP_HS4 | 2 | 2 | 0.000011 | 0.000011 | 0.0462 | 0.0491 |
| 165 | /SDA_TOP | 2 | 2 | 0.331458 | 0.331458 | 0.6610 | 0.9312 |
| 166 | /SCL_TOP | 2 | 2 | 0.683550 | 0.683550 | 0.6440 | 0.9406 |
| 167 | /I2C_RESET | 3 | 2 | 0.497181 | 0.497200 | 1.0481 | 1.1005 |
| 168 | /GPIO/TLS2 | 2 | 2 | 0.000044 | 0.000044 | 0.1314 | 0.1366 |
| 169 | /GPIO/TLS1 | 3 | 3 | 0.279028 | 0.279028 | 0.1815 | 0.1889 |
| 170 | /ESP_TXD | 3 | 3 | 1.874619 | 1.874766 | 0.8032 | 0.6947 |
| 171 | /ESP_RXD | 2 | 2 | 0.358603 | 0.358605 | 0.5832 | 0.5194 |
| 172 | /VBUS | 2 | 2 | 0.504128 | 0.504128 | 0.4071 | 0.3787 |
| 173 | /DEV_USB+ | 2 | 2 | 0.372862 | 0.372862 | 0.2741 | 0.2191 |
| 174 | /DEV_USB- | 2 | 2 | 0.497157 | 0.497157 | 0.2566 | 0.2385 |
| 175 | /USBSEL | 3 | 2 | 2.679974 | 1.690857 | 0.3797 | 0.2628 |
| 176 | /INT_ACCEL | 5 | 3 | 4.835730 | 4.835730 | 0.5316 | 0.3648 |
| 177 | /USB/TX | 3 | 3 | 0.704506 | 0.704506 | 0.1947 | 0.1961 |
| 178 | /USB/RX | 2 | 2 | 0.000020 | 0.000020 | 0.0649 | 0.0425 |
| 179 | /USB/PMID_SW | 3 | 2 | 1.518847 | 1.518844 | 0.2929 | 0.1932 |
| 180 | Net-(U51-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0066 | 0.0057 |
| 181 | /VBUS_SW | 2 | 2 | 0.000000 | 0.000000 | 0.0587 | 0.0445 |
