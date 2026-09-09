# Prototype supports collinéaires — 9 septembre 2026

Référence : tag annoté local `before_colli`, commit
`f56597f9ef17ecc4342ef796580a50eabc9bb885`. Aucun push ni ZIP demandé.
Le correctif reste dans `tools/prototype_collinear_supports.py`, non intégré
au moteur de production. L'activation de test remplace temporairement seulement
`dgloss.support_prototype.solve_supports` dans le processus de diagnostic.

## Origine et correction

Le constructeur du ZIP validé sur `/A` refusait toute intersection de supports
parallèles, même confondus. C'était une limite explicitement conservée lors de
l'intégration `05091c6`, pas une nouvelle régression du Gloss. Les tests de
chaînes droites du Centering n'avaient pas été inclus dans le premier groupe
de tests du prototype/packaging ; leur échec a été constaté à l'intégration.
Le succès de `/A` ne couvrait pas ce cas et ne justifiait pas une qualification
générale.

Le prototype groupe les supports consécutifs de même direction orientée.
Les contraintes de toutes leurs portes doivent désigner la même droite.
Les joints internes sont projetés sur ce support commun, en conservant leur
coordonnée longitudinale ; les joints avec les supports voisins restent des
intersections. Pas de fusion du cuivre, ratio de partage ni raccord artificiel.
Les ancres restent fixes et les segments retournés sont refusés. Une solution
qui nécessiterait de déplacer longitudinalement un joint interne reste hors
du domaine de ce prototype.

## Tests ciblés et `/A`

37 tests réussis avec activation temporaire du prototype, dont les trois tests
de droite à 0°, 45° et 90° précédemment en échec. Les nouvelles vérifications
couvrent huit orientations, contraintes incompatibles, ancre fixe, retournement,
parcours inversé et propagation d'une seule contrainte au support commun.
Le mock de clearance du test historique a reçu la méthode `segment_clears`
utilisée par le constructeur ; aucune assertion métier n'a été affaiblie.

`test_centering2`, `/A`, Proxi 2,54 mm : empreinte source
`08b5d8efe0990e9753f111b680fd1d95cf6ddb78e82888aa09182422c8f797fb`.
Comparaison native en mémoire : géométrie exacte identique avant/après correctif,
3 portes centrées, G5 valide, longueur 85,3560 mm. Mesure prototype isolée :
98,503 ms moteur, dont 16,178 ms Centering. Pas d'application à l'éditeur ni
de sauvegarde de la carte source pendant cette passe.

## PACK0

Les cinq empreintes du manifeste ont été vérifiées. Tous les nets non nuls
sont proposés au moteur, qui conserve ses exclusions. Grille 0,1 mm,
corridor actif, G4 désactivé, budget de recherche 20 s, Proxi 2,54 mm pour
Centering. Une exécution par carte/action/version, processus frais, sans
préchauffage. Les temps ci-dessous couvrent le moteur avec contexte et G5,
hors chargement, construction initiale de configuration et application native.
Centering inclut son Gloss préparatoire.

Les trois premières cartes utilisent l'import natif KiCad 10.0.6.
Le premier essai natif `azukar_fpga` n'a produit aucun résultat en 100 s et
a été terminé par le délai du processus de test. La cause de ce blocage n'est
pas diagnostiquée ici. Les deux dernières cartes ont été comparées avec le
parseur CLI KRT dans les deux versions : ne pas comparer leurs temps absolus
à ceux d'un autre importeur.

| Carte | Gloss référence → prototype (s) | Centering référence → prototype (s) | Résultat |
| --- | ---: | ---: | --- |
| micro_dmm | 0,349 → 0,344 | 0,545 → 0,550 | Gloss identique, G5 vrai ; Centering sans solution, entrée restaurée |
| chart_plotter_hat | 3,736 → 3,628 | 6,912 → 6,845 | Deux actions identiques ; 13 portes centrées, G5 vrai |
| environment_sensor | 2,361 → 2,287 | 20,016 → 20,022 | Gloss identique, G5 vrai ; Centering annulé au budget dans les deux versions |
| azukar_fpga (CLI) | 21,041 → 21,223 | 21,369 → 21,455 | Gloss G5 vrai mais résultats partiels différents ; Centering annulé au budget |
| tildagon_base (CLI) | 21,660 → 21,732 | 21,641 → 21,577 | Gloss identique, G5 vrai ; Centering annulé au budget |

Les cinq résultats Centering avant/après ont exactement la même empreinte
géométrique, mais quatre ne sont pas des centrages réussis : absence de solution
sur micro_dmm et expiration sur les trois autres cartes concernées.
Le correctif collinéaire est donc couvert positivement par les tests ciblés,
pas par un nouveau gain sur PACK0.

Sur azukar_fpga, le Gloss n'appelle pas le solveur modifié. Le budget temporel
interrompt néanmoins ses recherches à des positions différentes : gains
59,8956 mm puis 57,7936 mm. Cette comparaison ne prouve pas une non-régression
géométrique à convergence. Les durées proches ne constituent pas non plus une
preuve d'accélération. Les résultats partiels certifiés et les annulations ne
doivent pas être présentés comme une validation complète de PACK0.

Mesures détaillées locales : `.build/collinear-pack0/results.json`.
Reproduction : `D:/kicad/bin/python.exe tools/check_collinear_pack0.py` ;
reprise des deux dernières cartes après blocage natif :
`python tools/check_collinear_pack0.py --text-parser --resume-large`.
Les sources PCB ne sont jamais sauvegardées et leurs empreintes sont revérifiées.

Conclusion : prototype valide sur les cas collinéaires ciblés, `/A` conservé ;
qualification PACK0 partielle, limitée par les budgets et le blocage natif.
Les limites générales du certificat d'auto-contact pendant le mouvement restent
inchangées. Aucune intégration automatique de ce correctif.
