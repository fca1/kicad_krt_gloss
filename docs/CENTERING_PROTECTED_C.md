# Centering : passages locaux et distances protégées

Test du 6 septembre 2026 : `test_centering2.kicad_pcb`, net `/C`,
proximité 5 mm, construction multiporte et nouveaux segments activés.

Le Gloss préalable utilise `stay_in_corridor=True`. Le constructeur Centering
choisit des passages centrés de longueur finie, puis leurs raccordements
octolinéaires. Il ne prolonge plus obligatoirement deux droites jusqu'à leur
intersection. Aucune transformation ne suit le Centering.

Pour un obstacle commun à plusieurs portes, la distance protégée est le minimum
des distances acquises. Les clearances KRT restent obligatoires. La protection
porte sur tous les segments reconstruits et utilise la distance cuivre-cuivre
calculée avec les primitives KRT. Une tolérance numérique de 0,0002 mm couvre
les approximations des primitives de distance aux pads arrondis.
Les pads du net traité ne deviennent pas des obstacles à leur propre connexion.

## Mesures

| État | Longueur du net |
| --- | ---: |
| PCB initial | 104,4542 mm |
| Gloss préalable | 98,6860 mm |
| Ancien Centering à intersections de droites | 159,9494 mm |
| Centering avec passages finis protégés | 118,5233 mm |

Quatre portes conservées ; aucune exclusion nécessaire pour ce test.
Le net final comporte 15 segments, dont 14 reconstruits par le Centering.
La certification finale KRT est valide. Durée mesurée : environ 0,26 s.

Angles piste-porte finaux : TP7–TP18 82,185° ; TP11–TP12 72,429° ;
TP6–TP12 81,703° ; TP15–TP6 81,069°.

## Vérification reproductible

`python tools/check_centering_protected.py CHEMIN_DU_PCB`

Ce test travaille en mémoire, vérifie les quatre portes, la longueur, le nombre
de segments, la certification et les distances protégées sur le net final.
Les tests unitaires sont dans `tests/test_protected_centering.py`.

## Limites

Les meilleures orientations locales sont choisies une seule fois : aucune
énumération de leurs combinaisons. Une programmation dynamique conserve le
meilleur préfixe pour chaque sortie de porte, parmi six demi-longueurs de
passage (grille, 0,5, 1, 2, 4, 8 mm). Le nombre de transitions candidates est
O(nombre de portes × 6²), avec en plus le coût des contrôles géométriques KRT.
Ce n'est pas un optimum global : les longueurs sont échantillonnées et les
orientations ne sont pas réessayées. La piste reste plus longue de 14,0691 mm
que le PCB initial.

Le choix automatique d'exclure une porte contraignante n'est pas ajouté ici.
Le repli local existant reste soumis aux protections et validations.
Cette modification n'ajoute pas non plus de rollback du Gloss lorsque le
Centering ne produit rien : ce sujet antérieur reste distinct.
