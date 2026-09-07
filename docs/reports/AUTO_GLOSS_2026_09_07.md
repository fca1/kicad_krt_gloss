# Prototype auto gloss — tildagon_base — 7 septembre 2026

## Périmètre et protocole

Prototype isolé dans `tools/auto_gloss.py`, activé uniquement par le banc de mesure.
Aucun changement du comportement de production, G4 désactivé, aucun Centering.
164 nets de tildagon_base (PACK0), chaque net repart de la carte originale,
les autres nets restant fixes. Une seule séquence par net, sans répétition
statistique. Les appels successifs servent à mesurer la convergence du net et
incluent un dernier appel sans modification. Ils ne constituent pas une activation
de G4. Corridor=False, grille 0,1 mm, maximum 50 appels/120 secondes par net.

Comparaison avec la séquence historique du même protocole, conservée dans
`net_self_convergence_tildagon_2026_09_07.json`. Les temps sont des observations
uniques, non une estimation statistique. Les tests unitaires courts ont aussi été
exécutés pendant une partie de cette mesure : une comparaison temporelle contrôlée
reste nécessaire avant toute décision d'intégration.

## Mécanisme réellement testé

Dans chacun des traitements G3, G3.5 et G3 local, le prototype remplace la liste
figée des chaînes par une file. Après une modification acceptée, il reconstruit
la topologie et remet en file les chaînes contenant les nouveaux segments ou
incidentes aux extrémités modifiées. Les chaînes inchangées sans contact ne font
pas l'objet d'une nouvelle recherche. Les candidats, leurs seuils, le nettoyage
microsegments existant et toutes les validations KRT restent inchangés.

La granularité est **la chaîne complète entre ancrages**, pas encore la fenêtre
de deux ou trois segments. Il n'y a dans cette version ni nouveau candidat
combinant via et coude, ni nouveau nettoyage des candidats avant validation,
ni réveil d'une étape précédente après une étape ultérieure. C'est une première
isolation de l'effet du réexamen des nouveaux sommets, pas l'ensemble des pistes
évoquées dans la discussion.

Les segments intermédiaires consommés dans le même traitement sont retirés des
sorties et des demandes de suppression natives. La signature géométrique évite
le recyclage de la même chaîne dans un traitement ; cette protection ne prouve
pas la stabilité de tout le net. Les appels complets de confirmation restent
nécessaires, notamment pour les dépendances entre étapes et les influences de
chaînes sans extrémité commune. La limite temporelle du moteur reste active.
Le patch est réservé au diagnostic mono-thread et est retiré même sur exception.

## Résultats

Les temps ci-dessous cumulent uniquement les appels algorithmiques ; les débits
comptent les **164 nets uniques**, pas le nombre d'appels. Les gains sont des
sommes d'expériences indépendantes, pas le gain d'une carte finale combinée.

| Indicateur | Référence | Auto gloss |
|---|---:|---:|
| Temps des premiers appels | 31,855 s | 39,709 s |
| Débit des premiers appels | 5,15 nets/s | 4,13 nets/s |
| Gain des premiers appels | 75,8117 mm | 82,0615 mm |
| Temps jusqu'à confirmation | 50,044 s | 55,787 s |
| Débit jusqu'à confirmation | 3,28 nets/s | 2,94 nets/s |
| Gain jusqu'à confirmation | 88,7359 mm | 90,0613 mm |
| Nombre total d'appels | 343 | 329 |
| Nets avec changements après le premier appel | 33 | 23 |
| Maximum d'appels, confirmation comprise | 5 | 5 |
| Nets stables et G5 valide | 164 | 164 |

Auto gloss : 24 nets en un appel, 117 en deux, 22 en trois, un en cinq.
Initialisation : 1,602 s ; certification G5 cumulée : 1,065 s, séparées des temps
algorithmiques. Le premier appel coûte 24,7 % de plus ; l'ensemble jusqu'à
confirmation coûte 11,5 % de plus, pour 1,3254 mm supplémentaires (+1,49 %).
Le temps des appels ultérieurs baisse de 18,189 à 16,078 s, insuffisamment pour
compenser le surcoût du premier traitement.

558 modifications de chaînes, 558 reconstructions de topologie, 591 remises
en file, 6014 présentations de chaînes au moteur (certaines peuvent être évitées
par son cache), 54 signatures déjà vues ignorées. Ces compteurs ne ventilent pas
le temps entre reconstruction, recherche et validation KRT : on ne peut donc pas
attribuer précisément le ralentissement à l'une de ces composantes.

## Cas révélateurs

| Net | Appels référence → auto gloss | Lecture |
|---|---:|---|
| 66 /GPIO/CLS5 | 3 → 2 | Le nouveau sommet est exploité dans le premier appel. |
| 141 /LED_DATA | 5 → 3 | Le réexamen absorbe deux appels ; une dépendance entre étapes subsiste. |
| 176 /INT_ACCEL | 5 → 3 | Même réduction du nombre d'appels, via déplacé lors du premier appel dans la référence. |
| 59 /GPIO/BTN4 | 5 → 5 | L'alternance via/coude entre étapes reste entière. |

Cinq nets gagnent chacun 0,1657 à 0,5799 mm supplémentaires en fin de séquence :
38, 74, 81, 91, 133. Le changement d'ordre peut donc aussi conduire à une autre
solution stable. Quelques écarts inférieurs à 0,00002 mm subsistent : net146
+0,0000190 mm, net167 -0,0000152 mm, net179 -0,0000023 mm. Il ne s'agit donc pas
d'une identité géométrique des résultats, ni d'une dominance stricte sur tous les nets.

Aucune erreur, aucun cycle externe, aucun budget/plafond atteint. G5 vérifie les
partitions terminales et la clearance du cuivre modifié pour chaque expérience.
Les assertions vérifient l'absence de modification des nets étrangers, la
restauration de chaque net, l'absence de segment exporté périmé et le SHA256
inchangé du fichier source. Cela ne constitue pas un DRC KiCad complet.
Quatre tests ciblent la file, les signatures, la restauration du patch et la
suppression des objets intermédiaires ; les 17 tests microsegments/glissement
existants passent également (21 tests distincts au total).

## Conclusion de cette version

Le réexamen immédiat des sommets fonctionne, mais cette granularité par chaîne
n'est pas convaincante pour le temps réel. Garder ce code comme prototype.
La prochaine piste serait une file de petites fenêtres conservant la topologie,
puis un réveil explicite des opérations dépendantes (notamment via/coude).
Ces deux évolutions ne sont pas implémentées ni mesurées ici.

## Détail des 164 nets

Temps : appels algorithmiques cumulés, confirmation comprise.

| Net | Nom | Appels réf. | Appels auto | Gain réf. mm | Gain auto mm | Temps réf. s | Temps auto s |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | /SFPs/PORTA_3V3 | 1 | 1 | 0.000000 | 0.000000 | 0.0289 | 0.0301 |
| 2 | Net-(U8-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0043 | 0.0054 |
| 13 | Net-(J8-CC1) | 2 | 2 | 0.000029 | 0.000029 | 0.0514 | 0.0540 |
| 14 | Net-(J8-CC2) | 2 | 2 | 0.000028 | 0.000028 | 0.1240 | 0.1222 |
| 15 | GND | 3 | 3 | 8.403528 | 8.403528 | 6.1722 | 7.6449 |
| 16 | Net-(AE1-FEED) | 2 | 2 | 0.248539 | 0.248539 | 0.0446 | 0.0513 |
| 17 | Net-(U1-LNA_IN) | 2 | 2 | 0.000015 | 0.000015 | 0.0125 | 0.0159 |
| 18 | /USB- | 2 | 2 | 0.000029 | 0.000029 | 0.0460 | 0.0482 |
| 19 | /USB+ | 1 | 1 | 0.000000 | 0.000000 | 0.0224 | 0.0239 |
| 25 | /~{ESPRESET} | 2 | 2 | 1.249651 | 1.249651 | 0.7400 | 0.8595 |
| 27 | /~{BOOTLOADER} | 2 | 2 | 0.849472 | 0.849472 | 0.6277 | 0.6772 |
| 28 | /~{QON} | 2 | 2 | 0.000008 | 0.000008 | 0.0613 | 0.0696 |
| 29 | /SFPs/A_NDET | 2 | 2 | 0.000209 | 0.000209 | 0.0733 | 0.0797 |
| 30 | /SFPs/A_LSEN | 2 | 2 | 0.165685 | 0.165685 | 0.0152 | 0.0186 |
| 31 | /SFPs/PORTB_3V3 | 1 | 1 | 0.000000 | 0.000000 | 0.0063 | 0.0081 |
| 32 | /SFPs/B_NDET | 3 | 2 | 0.527208 | 0.527208 | 0.0781 | 0.0738 |
| 33 | Net-(U9-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0040 | 0.0056 |
| 34 | /SFPs/B_LSEN | 1 | 1 | 0.000000 | 0.000000 | 0.0864 | 0.0902 |
| 35 | /SFPs/PORTC_3V3 | 2 | 2 | 0.911270 | 0.911270 | 0.0359 | 0.0430 |
| 36 | /SFPs/C_NDET | 2 | 2 | 0.000026 | 0.000026 | 0.0273 | 0.0321 |
| 37 | Net-(U10-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0041 | 0.0058 |
| 38 | /SFPs/C_LSEN | 2 | 2 | 0.436806 | 0.685303 | 0.0709 | 0.1133 |
| 39 | /GPIO/ALS1 | 3 | 3 | 0.434934 | 0.434934 | 0.1465 | 0.1903 |
| 40 | /GPIO/ALS2 | 2 | 2 | 0.248554 | 0.248554 | 0.1502 | 0.1850 |
| 41 | /GPIO/ALS3 | 3 | 3 | 0.536436 | 0.536436 | 0.3410 | 0.4241 |
| 42 | /GPIO/ALS4 | 2 | 2 | 0.348044 | 0.348044 | 0.1855 | 0.1960 |
| 43 | /GPIO/ALS5 | 3 | 2 | 0.579938 | 0.579938 | 0.1810 | 0.1867 |
| 44 | /GPIO/DET_A | 2 | 2 | 1.539712 | 1.539712 | 0.2959 | 0.3457 |
| 45 | /GPIO/DET_B | 1 | 1 | 0.000000 | 0.000000 | 0.0149 | 0.0184 |
| 46 | /GPIO/BLS1 | 2 | 2 | 0.322183 | 0.322183 | 0.0440 | 0.0519 |
| 47 | /GPIO/BLS2 | 2 | 2 | 0.165690 | 0.165690 | 0.0268 | 0.0339 |
| 48 | /GPIO/LED_PWR_EN | 2 | 2 | 0.297028 | 0.297028 | 0.1702 | 0.1811 |
| 49 | /GPIO/BTN1 | 2 | 2 | 0.263657 | 0.263657 | 0.1625 | 0.2037 |
| 50 | /GPIO/BTN2 | 2 | 2 | 0.579931 | 0.579931 | 0.1047 | 0.1292 |
| 51 | /GPIO/BLS3 | 2 | 2 | 0.248539 | 0.248539 | 0.0373 | 0.0420 |
| 52 | /GPIO/BLS4 | 2 | 2 | 0.662752 | 0.662752 | 0.0674 | 0.0771 |
| 53 | /GPIO/BLS5 | 2 | 2 | 0.000005 | 0.000005 | 0.0628 | 0.0662 |
| 54 | /GPIO/DET_C | 2 | 2 | 0.165686 | 0.165686 | 0.0169 | 0.0220 |
| 55 | /GPIO/DET_D | 3 | 3 | 0.414269 | 0.414269 | 0.2245 | 0.2838 |
| 56 | /GPIO/DET_E | 2 | 2 | 0.020947 | 0.020947 | 0.4089 | 0.4239 |
| 57 | /GPIO/DET_F | 2 | 2 | 0.331444 | 0.331444 | 1.6290 | 1.8291 |
| 58 | /GPIO/BTN3 | 2 | 2 | 0.353582 | 0.353582 | 0.2472 | 0.2481 |
| 59 | /GPIO/BTN4 | 5 | 5 | 2.760071 | 2.760071 | 0.4839 | 0.5105 |
| 60 | /GPIO/BTN5 | 3 | 3 | 0.840025 | 0.840025 | 0.3211 | 0.3533 |
| 61 | /GPIO/BTN6 | 2 | 2 | 0.165694 | 0.165694 | 0.1738 | 0.2153 |
| 62 | /GPIO/CLS1 | 2 | 2 | 0.000048 | 0.000048 | 0.0533 | 0.0614 |
| 63 | /GPIO/CLS2 | 2 | 2 | 0.974874 | 0.974874 | 0.0661 | 0.0756 |
| 64 | /GPIO/CLS3 | 2 | 2 | 0.008243 | 0.008243 | 0.0778 | 0.0806 |
| 65 | /GPIO/CLS4 | 2 | 2 | 0.496167 | 0.496167 | 0.0937 | 0.1050 |
| 66 | /GPIO/CLS5 | 3 | 2 | 0.339608 | 0.339608 | 0.1219 | 0.1089 |
| 67 | /USB/CC1 | 2 | 2 | 0.117159 | 0.117159 | 0.1076 | 0.1164 |
| 68 | /USB/CC2 | 2 | 2 | 0.991127 | 0.991127 | 0.0786 | 0.0891 |
| 69 | /SFPs/PORTD_3V3 | 2 | 2 | 0.499666 | 0.499666 | 0.0303 | 0.0390 |
| 70 | /SFPs/PORTE_3V3 | 3 | 2 | 1.193640 | 1.193640 | 0.0427 | 0.0444 |
| 71 | /SFPs/PORTF_3V3 | 2 | 2 | 0.248549 | 0.248549 | 0.0347 | 0.0414 |
| 72 | /SFPs/D_NDET | 3 | 3 | 0.414214 | 0.414214 | 0.0512 | 0.0640 |
| 73 | Net-(U11-SET) | 2 | 2 | 0.033137 | 0.033137 | 0.0153 | 0.0185 |
| 74 | /SFPs/E_NDET | 2 | 2 | 0.231964 | 0.397649 | 0.0452 | 0.0618 |
| 75 | Net-(U12-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0041 | 0.0058 |
| 76 | /SFPs/F_NDET | 2 | 2 | 0.836438 | 0.836438 | 0.1153 | 0.1495 |
| 77 | Net-(U13-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0049 | 0.0061 |
| 78 | /SFPs/D_LSEN | 2 | 2 | 0.165686 | 0.165686 | 0.0245 | 0.0284 |
| 79 | /SFPs/E_LSEN | 2 | 2 | -0.000000 | -0.000000 | 0.0218 | 0.0269 |
| 80 | /SFPs/F_LSEN | 2 | 2 | 1.792772 | 1.792772 | 0.0327 | 0.0363 |
| 81 | /bot-top-link/TOP_VBAT_SW | 2 | 2 | 0.687899 | 1.267786 | 0.0840 | 0.1041 |
| 82 | Net-(D2-DIN) | 1 | 1 | 0.000000 | 0.000000 | 0.0046 | 0.0060 |
| 83 | Net-(U14-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0047 | 0.0061 |
| 84 | Net-(R24-Pad1) | 1 | 1 | 0.000000 | 0.000000 | 0.0039 | 0.0057 |
| 85 | Net-(D2-DOUT) | 1 | 1 | 0.000000 | 0.000000 | 0.0037 | 0.0050 |
| 86 | /bot-top-link/LED_DATA_TOP | 1 | 1 | 0.000000 | 0.000000 | 0.0048 | 0.0067 |
| 87 | /NA_HS1 | 2 | 2 | 0.263624 | 0.263624 | 0.0562 | 0.0683 |
| 88 | /NA_HS2 | 2 | 2 | 0.530856 | 0.530856 | 0.0796 | 0.0951 |
| 89 | /NA_HS3 | 2 | 2 | 0.000005 | 0.000005 | 0.0607 | 0.0666 |
| 90 | /NA_HS4 | 2 | 2 | 0.298106 | 0.298106 | 0.0939 | 0.1171 |
| 91 | /NB_HS1 | 3 | 2 | 0.614681 | 0.780366 | 0.6119 | 0.5143 |
| 92 | /NB_HS2 | 2 | 2 | 0.190786 | 0.190786 | 0.4440 | 0.5136 |
| 93 | /NB_HS3 | 3 | 3 | 0.345149 | 0.345149 | 0.6452 | 0.6544 |
| 94 | /NB_HS4 | 2 | 2 | 0.000015 | 0.000015 | 0.2953 | 0.3078 |
| 95 | /NC_HS1 | 2 | 2 | 0.000026 | 0.000026 | 0.6681 | 0.6933 |
| 96 | /NC_HS2 | 2 | 2 | 0.000061 | 0.000061 | 0.8380 | 0.8454 |
| 97 | /NC_HS3 | 2 | 2 | 0.000100 | 0.000100 | 1.1888 | 1.2069 |
| 98 | /NC_HS4 | 2 | 2 | 0.189752 | 0.189752 | 1.0489 | 1.2787 |
| 99 | /NF_HS1 | 3 | 3 | 0.273056 | 0.273056 | 0.1954 | 0.2406 |
| 100 | /NF_HS2 | 2 | 2 | 0.594105 | 0.594105 | 0.1255 | 0.1385 |
| 101 | /NF_HS3 | 2 | 2 | 0.582860 | 0.582860 | 0.0850 | 0.0975 |
| 102 | /NF_HS4 | 2 | 2 | 0.757389 | 0.757389 | 0.1061 | 0.1220 |
| 103 | /I2C/SDA_A | 2 | 2 | 0.527311 | 0.527311 | 0.2785 | 0.3105 |
| 104 | /I2C/SCL_A | 2 | 2 | 0.576643 | 0.576643 | 0.2212 | 0.2399 |
| 105 | /I2C/SDA_B | 3 | 2 | 0.501476 | 0.501476 | 0.5963 | 0.5864 |
| 106 | /I2C/SCL_B | 3 | 3 | 0.891402 | 0.891402 | 0.5866 | 0.6550 |
| 107 | /I2C/SDA_C | 2 | 2 | 0.165685 | 0.165685 | 0.0246 | 0.0310 |
| 108 | /I2C/SCL_C | 2 | 2 | 0.165685 | 0.165685 | 0.0286 | 0.0332 |
| 109 | /I2C/SDA_D | 2 | 2 | 0.000019 | 0.000019 | 0.0545 | 0.0597 |
| 110 | /I2C/SCL_D | 2 | 2 | 0.000008 | 0.000008 | 0.1195 | 0.1254 |
| 111 | /I2C/SDA_E | 2 | 2 | 0.000073 | 0.000073 | 0.2763 | 0.2906 |
| 112 | /I2C/SCL_E | 2 | 2 | 1.168405 | 1.168405 | 0.2791 | 0.3495 |
| 113 | /I2C/SDA_F | 2 | 2 | 0.678318 | 0.678318 | 1.9864 | 2.0277 |
| 114 | /I2C/SCL_F | 3 | 3 | 0.055053 | 0.055053 | 2.1421 | 2.1867 |
| 115 | /GPIO/DLS1 | 2 | 2 | 0.351472 | 0.351472 | 0.0281 | 0.0319 |
| 116 | /GPIO/DLS2 | 2 | 2 | 0.248549 | 0.248549 | 0.0450 | 0.0565 |
| 117 | /GPIO/DLS3 | 2 | 2 | 0.000000 | 0.000000 | 0.0288 | 0.0329 |
| 118 | /GPIO/DLS4 | 2 | 2 | 0.000009 | 0.000009 | 0.0360 | 0.0405 |
| 119 | /GPIO/DLS5 | 2 | 2 | 0.000019 | 0.000019 | 0.0345 | 0.0377 |
| 120 | /GPIO/ELS1 | 2 | 2 | 0.000006 | 0.000006 | 0.1982 | 0.2063 |
| 121 | /GPIO/ELS2 | 2 | 2 | 0.165706 | 0.165706 | 0.2062 | 0.2592 |
| 122 | /GPIO/ELS3 | 2 | 2 | 0.000014 | 0.000014 | 0.1311 | 0.1380 |
| 123 | /GPIO/ELS4 | 2 | 2 | 0.248549 | 0.248549 | 0.0940 | 0.1275 |
| 124 | /GPIO/ELS5 | 1 | 1 | 0.000000 | 0.000000 | 0.0186 | 0.0221 |
| 125 | /GPIO/FLS5 | 3 | 3 | 0.248570 | 0.248570 | 0.2093 | 0.2186 |
| 126 | /GPIO/FLS4 | 2 | 2 | 0.199044 | 0.199044 | 0.2444 | 0.2642 |
| 127 | /GPIO/FLS3 | 2 | 2 | 0.329021 | 0.329021 | 0.2362 | 0.2573 |
| 128 | /GPIO/FLS2 | 2 | 2 | 0.000065 | 0.000065 | 0.2793 | 0.2879 |
| 129 | /GPIO/FLS1 | 2 | 2 | 1.406322 | 1.406322 | 0.3413 | 0.4276 |
| 130 | /NE_HS1 | 2 | 2 | 0.173993 | 0.173993 | 0.3175 | 0.4382 |
| 131 | /NE_HS2 | 3 | 2 | 0.298248 | 0.298248 | 0.5225 | 0.5233 |
| 132 | /NE_HS3 | 2 | 2 | 0.078872 | 0.078872 | 0.2838 | 0.2889 |
| 133 | /NE_HS4 | 2 | 2 | 0.248576 | 0.414261 | 0.2104 | 0.2264 |
| 134 | /ND_HS1 | 2 | 2 | 0.786704 | 0.786704 | 0.5744 | 0.8467 |
| 135 | /ND_HS2 | 2 | 2 | 0.248580 | 0.248580 | 0.4261 | 0.4461 |
| 136 | /ND_HS3 | 2 | 2 | 0.000087 | 0.000087 | 0.5081 | 0.5248 |
| 137 | /ND_HS4 | 3 | 2 | 0.331465 | 0.331465 | 0.5358 | 0.5294 |
| 138 | /SDA_SYS | 3 | 3 | 1.935205 | 1.935205 | 1.0939 | 1.3517 |
| 139 | /SCL_SYS | 2 | 2 | 1.188604 | 1.188604 | 0.8856 | 0.9484 |
| 140 | /~{INT_SYS} | 3 | 3 | 0.800668 | 0.800668 | 1.0839 | 1.2262 |
| 141 | /LED_DATA | 5 | 3 | 1.307107 | 1.307107 | 0.1192 | 0.1234 |
| 142 | Net-(U3-REGN) | 1 | 1 | 0.000000 | 0.000000 | 0.0042 | 0.0053 |
| 143 | Net-(C26-Pad1) | 2 | 2 | 0.000000 | 0.000000 | 0.0129 | 0.0183 |
| 144 | Net-(U3-BTST) | 1 | 1 | 0.000000 | 0.000000 | 0.0037 | 0.0056 |
| 145 | /USB/BAT+ | 1 | 1 | 0.000000 | 0.000000 | 0.0143 | 0.0160 |
| 146 | /USB/STAT | 3 | 3 | 4.363072 | 4.363091 | 0.3888 | 0.4869 |
| 147 | Net-(D1-A) | 1 | 1 | 0.000000 | 0.000000 | 0.0049 | 0.0067 |
| 148 | Net-(U3-ILIM) | 1 | 1 | 0.000000 | 0.000000 | 0.0058 | 0.0089 |
| 149 | Net-(U3-TS) | 2 | 2 | 0.000011 | 0.000011 | 0.0563 | 0.0630 |
| 150 | 3V3_SYS | 3 | 3 | 13.252911 | 13.252911 | 4.6121 | 5.5604 |
| 151 | Net-(U43-FB) | 1 | 1 | 0.000000 | 0.000000 | 0.0129 | 0.0143 |
| 152 | Net-(U43-SW) | 1 | 1 | 0.000000 | 0.000000 | 0.0038 | 0.0051 |
| 154 | /USB/PMID | 3 | 2 | 1.968221 | 1.968221 | 0.4263 | 0.5010 |
| 155 | /VSYS | 2 | 2 | 0.779096 | 0.779096 | 0.0784 | 0.0907 |
| 156 | /USB/HOST_D+ | 2 | 2 | 0.000038 | 0.000038 | 0.1467 | 0.1566 |
| 157 | /USB/HOST_D- | 2 | 2 | 0.000036 | 0.000036 | 0.1216 | 0.1343 |
| 158 | /SDA_HOST | 2 | 2 | 0.000084 | 0.000084 | 0.2187 | 0.2292 |
| 159 | /SCL_HOST | 2 | 2 | 0.000013 | 0.000013 | 0.3164 | 0.3249 |
| 160 | /USB/PMIC_OTG | 2 | 2 | 0.165703 | 0.165703 | 0.0859 | 0.0908 |
| 161 | /TOP_HS1 | 2 | 2 | 0.000042 | 0.000042 | 0.0520 | 0.0589 |
| 162 | /TOP_HS2 | 2 | 2 | 0.000011 | 0.000011 | 0.0396 | 0.0472 |
| 163 | /TOP_HS3 | 2 | 2 | 0.000021 | 0.000021 | 0.0841 | 0.0903 |
| 164 | /TOP_HS4 | 2 | 2 | 0.000011 | 0.000011 | 0.0462 | 0.0537 |
| 165 | /SDA_TOP | 2 | 2 | 0.331458 | 0.331458 | 0.6610 | 0.9203 |
| 166 | /SCL_TOP | 2 | 2 | 0.683550 | 0.683550 | 0.6440 | 0.7844 |
| 167 | /I2C_RESET | 3 | 3 | 0.497181 | 0.497166 | 1.0481 | 1.2959 |
| 168 | /GPIO/TLS2 | 2 | 2 | 0.000044 | 0.000044 | 0.1314 | 0.1362 |
| 169 | /GPIO/TLS1 | 3 | 3 | 0.279028 | 0.279028 | 0.1815 | 0.1750 |
| 170 | /ESP_TXD | 3 | 3 | 1.874619 | 1.874619 | 0.8032 | 0.6665 |
| 171 | /ESP_RXD | 2 | 2 | 0.358603 | 0.358603 | 0.5832 | 0.4284 |
| 172 | /VBUS | 2 | 2 | 0.504128 | 0.504128 | 0.4071 | 0.3671 |
| 173 | /DEV_USB+ | 2 | 2 | 0.372862 | 0.372862 | 0.2741 | 0.2250 |
| 174 | /DEV_USB- | 2 | 2 | 0.497157 | 0.497157 | 0.2566 | 0.2304 |
| 175 | /USBSEL | 3 | 3 | 2.679974 | 2.679974 | 0.3797 | 0.3632 |
| 176 | /INT_ACCEL | 5 | 3 | 4.835730 | 4.835730 | 0.5316 | 0.3980 |
| 177 | /USB/TX | 3 | 3 | 0.704506 | 0.704506 | 0.1947 | 0.1953 |
| 178 | /USB/RX | 2 | 2 | 0.000020 | 0.000020 | 0.0649 | 0.0450 |
| 179 | /USB/PMID_SW | 3 | 2 | 1.518847 | 1.518844 | 0.2929 | 0.2067 |
| 180 | Net-(U51-SET) | 1 | 1 | 0.000000 | 0.000000 | 0.0066 | 0.0068 |
| 181 | /VBUS_SW | 2 | 2 | 0.000000 | 0.000000 | 0.0587 | 0.0545 |
