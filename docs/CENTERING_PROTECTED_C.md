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
Au 6 septembre, cette modification n'ajoutait pas de rollback du Gloss lorsque
le Centering ne produisait rien. Cette limite est levée par l'intégration
atomique du 7 septembre décrite ci-dessous.

## Intégration atomique du 7 septembre 2026

Suite à la consigne explicite « Le gloss + centering est atomique »,
`run_centering` restaure l'état précédant le Gloss si aucune branche n'est
centrée, si le budget est épuisé au retour du Centering, ou si une exception
survient, notamment lors de la certification. Aucun nettoyage seul ni résultat
partiel arrêté sur budget n'est publié. Le budget reste commun aux deux phases.
Une fois le centrage terminé, la certification finale reste obligatoire, même
si elle fait dépasser le budget de recherche. Il n'y a pas d'exigence de centrer
toutes les branches possibles : le résultat doit avoir un centrage effectif,
sans arrêt sur budget ni échec de certification.

Tests du 7 septembre : 19 tests ciblés réussis, dont quatre tests de transaction
(absence de centrage, expiration du budget, erreur Centering, erreur G5).
Les tests d'erreurs et d'expiration injectent ces événements ; ils ne mesurent
pas leur fréquence réelle. La carte connue `test_centering2.kicad_pcb`, net `/C`,
a été rejouée en lecture seule : 104,4542 → 98,6859 → 118,5233 mm, quatre portes,
15 segments, G5 valide, 255,075 ms pour l'ensemble (mesure unique).

Un test historique distinct,
`test_a_later_gloss_completely_removes_a_longer_centering_path`, échoue car il
attend un centrage que le moteur protégé ne produit plus sur sa géométrie.
L'échec a aussi été reproduit avec le pipeline HEAD précédant cette intégration.
Son attente n'a pas été modifiée pour masquer cet échec préexistant.

L'atomicité ci-dessus porte sur la transaction de calcul avant application.
L'adaptateur KiCad n'a pas été changé : une erreur après suppression native
partielle n'offre toujours pas de restauration complète garantie par le code.
Les mesures de temps historiques des autres points sont conservées dans
`docs/reports/MICRO_REPAIR_DISPENSER_2026_09_07.md`,
`docs/reports/REDUCTION_CONTACTS_PICOFX_2026_09_07.md` et
`dgloss/GLOSS_REALTIME_STAGE2.md`. Le coût propre du rollback n'a pas été isolé.
