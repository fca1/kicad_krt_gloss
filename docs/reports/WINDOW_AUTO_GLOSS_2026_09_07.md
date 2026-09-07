# Auto gloss : petites fenêtres — 7 septembre 2026

## Périmètre testé

Prototype `tools/window_auto_gloss.py`, activé uniquement dans le banc de mesure
par `--window-auto-gloss`. Il réutilise auto gloss, avec un ordonnanceur différent.
Production et KRT inchangés. Aucun ajout de la variante recherche commune.
G4 et Centering désactivés.

Chaque traitement commence par les chaînes complètes de production. Après une
modification acceptée, seuls des groupes contigus de trois segments au maximum
sont remis en file : fenêtres couvrant les segments ajoutés ou les extrémités
modifiées. Pour une chaîne de deux segments, la fenêtre en contient deux.
Les fenêtres se chevauchent pour couvrir les raccords de la modification.
L'ordre de parcours et les coupures aux pads, vias, jonctions, largeurs et couches
restent ceux des chaînes d'origine. Pas de balayage de grille ajouté.

Le moteur et ses candidats restent ceux de production. Au niveau du DAG, les
candidats touchant une limite artificielle de fenêtre sont contrôlés pour ne pas
créer un angle droit avec un segment extérieur ; cette relation était auparavant
interne à la chaîne complète. Les validations KRT et les gardes de connectivité
restent actives. Les objets intermédiaires consommés ne sont pas exportés.

La reconstruction de topologie après modification est conservée : on mesure
ici la réduction du périmètre de recherche, pas une nouvelle gestion incrémentale
de la topologie. Les signatures répétées et fenêtres périmées sont ignorées.
Cela ne prouve pas la couverture de toutes les dépendances : les appels complets
de confirmation restent nécessaires pour mesurer la stabilité finale.

## Protocole

164 nets de tildagon_base (PACK0). Une séquence indépendante par net, repartant
de la carte originale avec tous les voisins fixes. Aucun préchauffage, aucune
répétition statistique. Les appels successifs transforment le résultat précédent
jusqu'à un appel sans modification. Corridor=False, grille 0,1 mm ; limites de
50 appels/120 secondes par net non atteintes. Aucun test parallèle au benchmark.

Les références sont les mesures historiques conservées du même protocole.
Les différences temporelles, notamment les petits écarts, sont indicatives.
Les gains sont des sommes d'expériences indépendantes : aucune carte combinée
n'est produite. Les débits comptent les 164 nets uniques, pas le nombre d'appels.
Les temps cumulent les appels, hors initialisation, restauration et G5 final.

## Résultat

| Mesure | Production de référence | Auto gloss chaînes | Auto gloss fenêtres |
|---|---:|---:|---:|
| Temps premiers appels | 31,855 s | 39,709 s | 36,353 s |
| Gain premiers appels | 75,8117 mm | 82,0615 mm | 80,9274 mm |
| Temps jusqu'à stabilité confirmée | 50,044 s | 55,787 s | 53,883 s |
| Nets/sec jusqu'à confirmation | 3,28 | 2,94 | 3,04 |
| Gain final | 88,7359 mm | 90,0613 mm | 90,0613 mm |
| Appels totaux | 343 | 329 | 329 |
| Nets avec plusieurs appels productifs | 33 | 23 | 23 |
| G5 valide | 164/164 | 164/164 | 164/164 |

Par rapport à auto gloss chaînes : **-1,903 s, soit -3,4 %**, même gain final
pour chaque net à 0,000001 mm près. Cela ne démontre pas une identité des
signatures géométriques finales entre variantes, non enregistrées dans ces jeux.
Par rapport à la production : **+7,7 % de temps**, pour +1,3254 mm de réduction.

La première recherche est plus rapide que l'auto gloss chaînes mais laisse
1,1341 mm de gain supplémentaire aux appels suivants. Ceux-ci coûtent 17,530 s
contre 16,078 s dans auto gloss chaînes : une partie du gain initial est donc
reconsommée pendant la convergence.

Distribution : 24 nets en un appel, 117 en deux, 22 en trois, un en cinq,
confirmation comprise. BTN4 reste à cinq ; LED_DATA et INT_ACCEL restent à trois.
La dépendance via/coude n'est pas résolue par cette variante.

## Ce que montrent les compteurs

- 5 477 chaînes initiales présentées aux moteurs.
- 2 243 fenêtres mises en file, 2 164 présentées, contenant 6 411 segments au total.
- 27 modifications acceptées lors des reprises par fenêtres ; 536 lors des examens initiaux.
- 45 signatures répétées ignorées et 34 fenêtres devenues périmées.
- 563 reconstructions de topologie : **2,081 s** cumulées dans cette variante.

Les présentations ne sont pas toutes des recherches effectives : le cache de
production peut en éviter. Le ratio 27/2164 (1,25 %) mesure les reprises ayant
modifié le cuivre, pas un taux d'échec des validations KRT.

| Temps d'étape cumulé | Auto gloss chaînes | Auto gloss fenêtres |
|---|---:|---:|
| G3 | 35,958 s | 33,398 s |
| G3.5 longueur égale | 3,553 s | 3,541 s |
| G3 local | 7,466 s | 8,163 s |

La baisse se situe principalement dans G3. G3 local devient plus coûteux.
Le compteur de topologie ne comprend pas toute la gestion de file ; il ne sépare
pas non plus génération des candidats et validations KRT dans les autres temps.

## Vérification et conclusion

25 tests ciblés passent : quatre pour les fenêtres, quatre pour auto gloss et
17 tests existants microsegments/glissement. Ils couvrent notamment la borne de
trois segments, les raccords affectés, le rejet d'un angle droit à la limite et
une exécution réelle certifiée KRT avec restauration du patch.

164 points fixes, G5 valide partout, aucune erreur/cycle externe/budget atteint.
Les assertions confirment : nets étrangers inchangés, restauration du net,
absence de segment exporté périmé et SHA256 source inchangé. Ce n'est pas un DRC
KiCad complet. Les petits écarts de gain par rapport à la production restent
ceux d'auto gloss chaînes, détaillés dans son rapport ; la variante fenêtres
n'ajoute pas de perte mesurable de gain par rapport à celui-ci.

**La petite fenêtre est meilleure que la chaîne complète pour cette mesure,
mais le gain de temps reste modeste et ne rejoint pas la production.** Conserver
comme prototype. La priorité suivante serait de diminuer les fenêtres réexaminées
sans effet et la reconstruction de topologie, avec une couverture explicite des
dépendances. Le test n'établit pas qu'une fenêtre de trois segments est la taille
optimale : aucune autre taille n'a été mesurée dans cette expérience.

## Détail des 164 nets

| Net | Nom | Appels chaînes | Appels fenêtres | Gain chaînes mm | Gain fenêtres mm | Temps chaînes s | Temps fenêtres s |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | /SFPs/PORTA_3V3 | 1 | 1 | 0.000000 | 0.000000 | 0.0301 | 0.0295 |
| 2 | Net-(U8-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0054 | 0.0052 |
| 13 | Net-(J8-CC1) | 2 | 2 | 0.000029 | 0.000029 | 0.0540 | 0.0643 |
| 14 | Net-(J8-CC2) | 2 | 2 | 0.000028 | 0.000028 | 0.1222 | 0.1265 |
| 15 | GND | 3 | 3 | 8.403528 | 8.403528 | 7.6449 | 7.6046 |
| 16 | Net-(AE1-FEED) | 2 | 2 | 0.248539 | 0.248539 | 0.0513 | 0.0512 |
| 17 | Net-(U1-LNA_IN) | 2 | 2 | 0.000015 | 0.000015 | 0.0159 | 0.0163 |
| 18 | /USB- | 2 | 2 | 0.000029 | 0.000029 | 0.0482 | 0.0513 |
| 19 | /USB+ | 1 | 1 | 0.000000 | 0.000000 | 0.0239 | 0.0241 |
| 25 | /~{ESPRESET} | 2 | 2 | 1.249651 | 1.249651 | 0.8595 | 0.8255 |
| 27 | /~{BOOTLOADER} | 2 | 2 | 0.849472 | 0.849472 | 0.6772 | 0.6871 |
| 28 | /~{QON} | 2 | 2 | 0.000008 | 0.000008 | 0.0696 | 0.0721 |
| 29 | /SFPs/A_NDET | 2 | 2 | 0.000209 | 0.000209 | 0.0797 | 0.0813 |
| 30 | /SFPs/A_LSEN | 2 | 2 | 0.165685 | 0.165685 | 0.0186 | 0.0189 |
| 31 | /SFPs/PORTB_3V3 | 1 | 1 | 0.000000 | 0.000000 | 0.0081 | 0.0083 |
| 32 | /SFPs/B_NDET | 2 | 2 | 0.527208 | 0.527208 | 0.0738 | 0.0711 |
| 33 | Net-(U9-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0056 | 0.0056 |
| 34 | /SFPs/B_LSEN | 1 | 1 | 0.000000 | 0.000000 | 0.0902 | 0.0906 |
| 35 | /SFPs/PORTC_3V3 | 2 | 2 | 0.911270 | 0.911270 | 0.0430 | 0.0433 |
| 36 | /SFPs/C_NDET | 2 | 2 | 0.000026 | 0.000026 | 0.0321 | 0.0319 |
| 37 | Net-(U10-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0058 | 0.0060 |
| 38 | /SFPs/C_LSEN | 2 | 2 | 0.685303 | 0.685303 | 0.1133 | 0.1061 |
| 39 | /GPIO/ALS1 | 3 | 3 | 0.434934 | 0.434934 | 0.1903 | 0.1882 |
| 40 | /GPIO/ALS2 | 2 | 2 | 0.248554 | 0.248554 | 0.1850 | 0.1783 |
| 41 | /GPIO/ALS3 | 3 | 3 | 0.536436 | 0.536436 | 0.4241 | 0.3183 |
| 42 | /GPIO/ALS4 | 2 | 2 | 0.348044 | 0.348044 | 0.1960 | 0.2100 |
| 43 | /GPIO/ALS5 | 2 | 2 | 0.579938 | 0.579938 | 0.1867 | 0.1847 |
| 44 | /GPIO/DET_A | 2 | 2 | 1.539712 | 1.539712 | 0.3457 | 0.3112 |
| 45 | /GPIO/DET_B | 1 | 1 | 0.000000 | 0.000000 | 0.0184 | 0.0172 |
| 46 | /GPIO/BLS1 | 2 | 2 | 0.322183 | 0.322183 | 0.0519 | 0.0515 |
| 47 | /GPIO/BLS2 | 2 | 2 | 0.165690 | 0.165690 | 0.0339 | 0.0333 |
| 48 | /GPIO/LED_PWR_EN | 2 | 2 | 0.297028 | 0.297028 | 0.1811 | 0.1896 |
| 49 | /GPIO/BTN1 | 2 | 2 | 0.263657 | 0.263657 | 0.2037 | 0.1882 |
| 50 | /GPIO/BTN2 | 2 | 2 | 0.579931 | 0.579931 | 0.1292 | 0.1184 |
| 51 | /GPIO/BLS3 | 2 | 2 | 0.248539 | 0.248539 | 0.0420 | 0.0425 |
| 52 | /GPIO/BLS4 | 2 | 2 | 0.662752 | 0.662752 | 0.0771 | 0.0757 |
| 53 | /GPIO/BLS5 | 2 | 2 | 0.000005 | 0.000005 | 0.0662 | 0.0698 |
| 54 | /GPIO/DET_C | 2 | 2 | 0.165686 | 0.165686 | 0.0220 | 0.0203 |
| 55 | /GPIO/DET_D | 3 | 3 | 0.414269 | 0.414269 | 0.2838 | 0.2513 |
| 56 | /GPIO/DET_E | 2 | 2 | 0.020947 | 0.020947 | 0.4239 | 0.4241 |
| 57 | /GPIO/DET_F | 2 | 2 | 0.331444 | 0.331444 | 1.8291 | 1.6850 |
| 58 | /GPIO/BTN3 | 2 | 2 | 0.353582 | 0.353582 | 0.2481 | 0.2636 |
| 59 | /GPIO/BTN4 | 5 | 5 | 2.760071 | 2.760071 | 0.5105 | 0.5282 |
| 60 | /GPIO/BTN5 | 3 | 3 | 0.840025 | 0.840025 | 0.3533 | 0.3402 |
| 61 | /GPIO/BTN6 | 2 | 2 | 0.165694 | 0.165694 | 0.2153 | 0.1958 |
| 62 | /GPIO/CLS1 | 2 | 2 | 0.000048 | 0.000048 | 0.0614 | 0.0612 |
| 63 | /GPIO/CLS2 | 2 | 2 | 0.974874 | 0.974874 | 0.0756 | 0.0744 |
| 64 | /GPIO/CLS3 | 2 | 2 | 0.008243 | 0.008243 | 0.0806 | 0.0837 |
| 65 | /GPIO/CLS4 | 2 | 2 | 0.496167 | 0.496167 | 0.1050 | 0.1093 |
| 66 | /GPIO/CLS5 | 2 | 2 | 0.339608 | 0.339608 | 0.1089 | 0.1306 |
| 67 | /USB/CC1 | 2 | 2 | 0.117159 | 0.117159 | 0.1164 | 0.1203 |
| 68 | /USB/CC2 | 2 | 2 | 0.991127 | 0.991127 | 0.0891 | 0.0868 |
| 69 | /SFPs/PORTD_3V3 | 2 | 2 | 0.499666 | 0.499666 | 0.0390 | 0.0393 |
| 70 | /SFPs/PORTE_3V3 | 2 | 2 | 1.193640 | 1.193640 | 0.0444 | 0.0436 |
| 71 | /SFPs/PORTF_3V3 | 2 | 2 | 0.248549 | 0.248549 | 0.0414 | 0.0406 |
| 72 | /SFPs/D_NDET | 3 | 3 | 0.414214 | 0.414214 | 0.0640 | 0.0602 |
| 73 | Net-(U11-SET) | 2 | 2 | 0.033137 | 0.033137 | 0.0185 | 0.0181 |
| 74 | /SFPs/E_NDET | 2 | 2 | 0.397649 | 0.397649 | 0.0618 | 0.0598 |
| 75 | Net-(U12-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0058 | 0.0061 |
| 76 | /SFPs/F_NDET | 2 | 2 | 0.836438 | 0.836438 | 0.1495 | 0.1417 |
| 77 | Net-(U13-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0061 | 0.0061 |
| 78 | /SFPs/D_LSEN | 2 | 2 | 0.165686 | 0.165686 | 0.0284 | 0.0288 |
| 79 | /SFPs/E_LSEN | 2 | 2 | -0.000000 | -0.000000 | 0.0269 | 0.0247 |
| 80 | /SFPs/F_LSEN | 2 | 2 | 1.792772 | 1.792772 | 0.0363 | 0.0361 |
| 81 | /bot-top-link/TOP_VBAT_SW | 2 | 2 | 1.267786 | 1.267786 | 0.1041 | 0.1013 |
| 82 | Net-(D2-DIN) | 1 | 1 | 0.000000 | 0.000000 | 0.0060 | 0.0078 |
| 83 | Net-(U14-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0061 | 0.0057 |
| 84 | Net-(R24-Pad1) | 1 | 1 | 0.000000 | 0.000000 | 0.0057 | 0.0057 |
| 85 | Net-(D2-DOUT) | 1 | 1 | 0.000000 | 0.000000 | 0.0050 | 0.0049 |
| 86 | /bot-top-link/LED_DATA_TOP | 1 | 1 | 0.000000 | 0.000000 | 0.0067 | 0.0067 |
| 87 | /NA_HS1 | 2 | 2 | 0.263624 | 0.263624 | 0.0683 | 0.0727 |
| 88 | /NA_HS2 | 2 | 2 | 0.530856 | 0.530856 | 0.0951 | 0.0921 |
| 89 | /NA_HS3 | 2 | 2 | 0.000005 | 0.000005 | 0.0666 | 0.0708 |
| 90 | /NA_HS4 | 2 | 2 | 0.298106 | 0.298106 | 0.1171 | 0.1102 |
| 91 | /NB_HS1 | 2 | 2 | 0.780366 | 0.780366 | 0.5143 | 0.5196 |
| 92 | /NB_HS2 | 2 | 2 | 0.190786 | 0.190786 | 0.5136 | 0.4702 |
| 93 | /NB_HS3 | 3 | 3 | 0.345149 | 0.345149 | 0.6544 | 0.6482 |
| 94 | /NB_HS4 | 2 | 2 | 0.000015 | 0.000015 | 0.3078 | 0.3054 |
| 95 | /NC_HS1 | 2 | 2 | 0.000026 | 0.000026 | 0.6933 | 0.6824 |
| 96 | /NC_HS2 | 2 | 2 | 0.000061 | 0.000061 | 0.8454 | 0.8438 |
| 97 | /NC_HS3 | 2 | 2 | 0.000100 | 0.000100 | 1.2069 | 1.2012 |
| 98 | /NC_HS4 | 2 | 2 | 0.189752 | 0.189752 | 1.2787 | 1.1251 |
| 99 | /NF_HS1 | 3 | 3 | 0.273056 | 0.273056 | 0.2406 | 0.2298 |
| 100 | /NF_HS2 | 2 | 2 | 0.594105 | 0.594105 | 0.1385 | 0.1430 |
| 101 | /NF_HS3 | 2 | 2 | 0.582860 | 0.582860 | 0.0975 | 0.0977 |
| 102 | /NF_HS4 | 2 | 2 | 0.757389 | 0.757389 | 0.1220 | 0.1223 |
| 103 | /I2C/SDA_A | 2 | 2 | 0.527311 | 0.527311 | 0.3105 | 0.3157 |
| 104 | /I2C/SCL_A | 2 | 2 | 0.576643 | 0.576643 | 0.2399 | 0.2444 |
| 105 | /I2C/SDA_B | 2 | 2 | 0.501476 | 0.501476 | 0.5864 | 0.4817 |
| 106 | /I2C/SCL_B | 3 | 3 | 0.891402 | 0.891402 | 0.6550 | 0.6146 |
| 107 | /I2C/SDA_C | 2 | 2 | 0.165685 | 0.165685 | 0.0310 | 0.0314 |
| 108 | /I2C/SCL_C | 2 | 2 | 0.165685 | 0.165685 | 0.0332 | 0.0356 |
| 109 | /I2C/SDA_D | 2 | 2 | 0.000019 | 0.000019 | 0.0597 | 0.0644 |
| 110 | /I2C/SCL_D | 2 | 2 | 0.000008 | 0.000008 | 0.1254 | 0.1324 |
| 111 | /I2C/SDA_E | 2 | 2 | 0.000073 | 0.000073 | 0.2906 | 0.3254 |
| 112 | /I2C/SCL_E | 2 | 2 | 1.168405 | 1.168405 | 0.3495 | 0.3264 |
| 113 | /I2C/SDA_F | 2 | 2 | 0.678318 | 0.678318 | 2.0277 | 2.0464 |
| 114 | /I2C/SCL_F | 3 | 3 | 0.055053 | 0.055053 | 2.1867 | 2.2010 |
| 115 | /GPIO/DLS1 | 2 | 2 | 0.351472 | 0.351472 | 0.0319 | 0.0318 |
| 116 | /GPIO/DLS2 | 2 | 2 | 0.248549 | 0.248549 | 0.0565 | 0.0573 |
| 117 | /GPIO/DLS3 | 2 | 2 | 0.000000 | 0.000000 | 0.0329 | 0.0321 |
| 118 | /GPIO/DLS4 | 2 | 2 | 0.000009 | 0.000009 | 0.0405 | 0.0419 |
| 119 | /GPIO/DLS5 | 2 | 2 | 0.000019 | 0.000019 | 0.0377 | 0.0426 |
| 120 | /GPIO/ELS1 | 2 | 2 | 0.000006 | 0.000006 | 0.2063 | 0.2049 |
| 121 | /GPIO/ELS2 | 2 | 2 | 0.165706 | 0.165706 | 0.2592 | 0.2187 |
| 122 | /GPIO/ELS3 | 2 | 2 | 0.000014 | 0.000014 | 0.1380 | 0.1402 |
| 123 | /GPIO/ELS4 | 2 | 2 | 0.248549 | 0.248549 | 0.1275 | 0.1193 |
| 124 | /GPIO/ELS5 | 1 | 1 | 0.000000 | 0.000000 | 0.0221 | 0.0214 |
| 125 | /GPIO/FLS5 | 3 | 3 | 0.248570 | 0.248570 | 0.2186 | 0.2259 |
| 126 | /GPIO/FLS4 | 2 | 2 | 0.199044 | 0.199044 | 0.2642 | 0.2564 |
| 127 | /GPIO/FLS3 | 2 | 2 | 0.329021 | 0.329021 | 0.2573 | 0.2487 |
| 128 | /GPIO/FLS2 | 2 | 2 | 0.000065 | 0.000065 | 0.2879 | 0.3049 |
| 129 | /GPIO/FLS1 | 2 | 2 | 1.406322 | 1.406322 | 0.4276 | 0.3765 |
| 130 | /NE_HS1 | 2 | 2 | 0.173993 | 0.173993 | 0.4382 | 0.3467 |
| 131 | /NE_HS2 | 2 | 2 | 0.298248 | 0.298248 | 0.5233 | 0.5390 |
| 132 | /NE_HS3 | 2 | 2 | 0.078872 | 0.078872 | 0.2889 | 0.2956 |
| 133 | /NE_HS4 | 2 | 2 | 0.414261 | 0.414261 | 0.2264 | 0.2338 |
| 134 | /ND_HS1 | 2 | 2 | 0.786704 | 0.786704 | 0.8467 | 0.6536 |
| 135 | /ND_HS2 | 2 | 2 | 0.248580 | 0.248580 | 0.4461 | 0.4505 |
| 136 | /ND_HS3 | 2 | 2 | 0.000087 | 0.000087 | 0.5248 | 0.5309 |
| 137 | /ND_HS4 | 2 | 2 | 0.331465 | 0.331465 | 0.5294 | 0.5456 |
| 138 | /SDA_SYS | 3 | 3 | 1.935205 | 1.935205 | 1.3517 | 1.2865 |
| 139 | /SCL_SYS | 2 | 2 | 1.188604 | 1.188604 | 0.9484 | 0.9609 |
| 140 | /~{INT_SYS} | 3 | 3 | 0.800668 | 0.800668 | 1.2262 | 1.1976 |
| 141 | /LED_DATA | 3 | 3 | 1.307107 | 1.307107 | 0.1234 | 0.1141 |
| 142 | Net-(U3-REGN) | 1 | 1 | 0.000000 | 0.000000 | 0.0053 | 0.0054 |
| 143 | Net-(C26-Pad1) | 2 | 2 | 0.000000 | 0.000000 | 0.0183 | 0.0170 |
| 144 | Net-(U3-BTST) | 1 | 1 | 0.000000 | 0.000000 | 0.0056 | 0.0052 |
| 145 | /USB/BAT+ | 1 | 1 | 0.000000 | 0.000000 | 0.0160 | 0.0155 |
| 146 | /USB/STAT | 3 | 3 | 4.363091 | 4.363091 | 0.4869 | 0.4065 |
| 147 | Net-(D1-A) | 1 | 1 | 0.000000 | 0.000000 | 0.0067 | 0.0066 |
| 148 | Net-(U3-ILIM) | 1 | 1 | 0.000000 | 0.000000 | 0.0089 | 0.0081 |
| 149 | Net-(U3-TS) | 2 | 2 | 0.000011 | 0.000011 | 0.0630 | 0.0598 |
| 150 | 3V3_SYS | 3 | 3 | 13.252911 | 13.252911 | 5.5604 | 5.5545 |
| 151 | Net-(U43-FB) | 1 | 1 | 0.000000 | 0.000000 | 0.0143 | 0.0144 |
| 152 | Net-(U43-SW) | 1 | 1 | 0.000000 | 0.000000 | 0.0051 | 0.0051 |
| 154 | /USB/PMID | 2 | 2 | 1.968221 | 1.968221 | 0.5010 | 0.4225 |
| 155 | /VSYS | 2 | 2 | 0.779096 | 0.779096 | 0.0907 | 0.0909 |
| 156 | /USB/HOST_D+ | 2 | 2 | 0.000038 | 0.000038 | 0.1566 | 0.1648 |
| 157 | /USB/HOST_D- | 2 | 2 | 0.000036 | 0.000036 | 0.1343 | 0.1399 |
| 158 | /SDA_HOST | 2 | 2 | 0.000084 | 0.000084 | 0.2292 | 0.2411 |
| 159 | /SCL_HOST | 2 | 2 | 0.000013 | 0.000013 | 0.3249 | 0.3250 |
| 160 | /USB/PMIC_OTG | 2 | 2 | 0.165703 | 0.165703 | 0.0908 | 0.0976 |
| 161 | /TOP_HS1 | 2 | 2 | 0.000042 | 0.000042 | 0.0589 | 0.0612 |
| 162 | /TOP_HS2 | 2 | 2 | 0.000011 | 0.000011 | 0.0472 | 0.0478 |
| 163 | /TOP_HS3 | 2 | 2 | 0.000021 | 0.000021 | 0.0903 | 0.0908 |
| 164 | /TOP_HS4 | 2 | 2 | 0.000011 | 0.000011 | 0.0537 | 0.0534 |
| 165 | /SDA_TOP | 2 | 2 | 0.331458 | 0.331458 | 0.9203 | 0.7271 |
| 166 | /SCL_TOP | 2 | 2 | 0.683550 | 0.683550 | 0.7844 | 0.6920 |
| 167 | /I2C_RESET | 3 | 3 | 0.497166 | 0.497166 | 1.2959 | 0.9913 |
| 168 | /GPIO/TLS2 | 2 | 2 | 0.000044 | 0.000044 | 0.1362 | 0.1408 |
| 169 | /GPIO/TLS1 | 3 | 3 | 0.279028 | 0.279028 | 0.1750 | 0.1760 |
| 170 | /ESP_TXD | 3 | 3 | 1.874619 | 1.874619 | 0.6665 | 0.6189 |
| 171 | /ESP_RXD | 2 | 2 | 0.358603 | 0.358603 | 0.4284 | 0.4302 |
| 172 | /VBUS | 2 | 2 | 0.504128 | 0.504128 | 0.3671 | 0.3347 |
| 173 | /DEV_USB+ | 2 | 2 | 0.372862 | 0.372862 | 0.2250 | 0.2138 |
| 174 | /DEV_USB- | 2 | 2 | 0.497157 | 0.497157 | 0.2304 | 0.2247 |
| 175 | /USBSEL | 3 | 3 | 2.679974 | 2.679974 | 0.3632 | 0.3411 |
| 176 | /INT_ACCEL | 3 | 3 | 4.835730 | 4.835730 | 0.3980 | 0.4097 |
| 177 | /USB/TX | 3 | 3 | 0.704506 | 0.704506 | 0.1953 | 0.1919 |
| 178 | /USB/RX | 2 | 2 | 0.000020 | 0.000020 | 0.0450 | 0.0510 |
| 179 | /USB/PMID_SW | 2 | 2 | 1.518844 | 1.518844 | 0.2067 | 0.2049 |
| 180 | Net-(U51-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0068 | 0.0068 |
| 181 | /VBUS_SW | 2 | 2 | 0.000000 | 0.000000 | 0.0545 | 0.0540 |
