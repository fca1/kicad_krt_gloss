# Corridor : suppression des enveloppes artificielles et revue

## Périmètre et décision

Correction à partir de `cc758f9`, après autorisation explicite. KRT reste au
sous-module `0aff32c04fa51b4d53ecabc843b09b356aaef94b`, sans modification.
Aucun ZIP, changement du dialogue, timer ou correctif particulier au net `/A`.

L'ancien certificat augmentait la largeur des pistes selon le déplacement et
la grille. Cette enveloppe conservatrice pouvait rejeter une réduction sans
qu'aucun obstacle soit franchi. Son coût borné et la réutilisation des contrôles
de segments expliquaient le prototype ; aucune mesure retrouvée ne prouvait
qu'un certificat géométrique continu avait été écarté pour des raisons de temps réel.

## Certificat désormais utilisé

Les sommets correspondants des chaînes sont obtenus par abscisse curviligne
normalisée. Ils sont déplacés successivement, avec leurs voisins fixes.
Chaque segment incident balaie alors un triangle rempli, éventuellement
dégénéré. Les sommets communs aux branches d'un via ou d'une jonction T sont
déplacés ensemble. Le cuivre garde sa largeur réelle.

KRT contrôle les capsules des trois arêtes. Des représentants des composantes
d'obstacles détectent aussi les obstacles entièrement enfermés dans le triangle.
Les tableaux KRT fournissent pistes, vias, pads et trous ; les composantes des
pads personnalisés, keepouts et découpes de carte sont également examinées.
Le corps d'un via mobile balaie les capsules de son diamètre et de son percement
réels, avec les règles de cuivre et de trou-à-trou de KRT, y compris entre vias
du même net. Aucun rayon n'est augmenté selon le mouvement.

Il s'agit du certificat d'UNE déformation construite, pas d'une recherche de
toutes les homotopies. Un refus ne démontre pas qu'aucun contournement admissible
n'existe. Les états intermédiaires peuvent être non octolinéaires ; le cuivre
produit doit être octolinéaire. Un certificat expiré n'autorise pas le mouvement.
Les gardes électriques restent distincts.

## Artefacts identifiés et traitement

| Emplacement | Ancien comportement | Correction |
| --- | --- | --- |
| `corridor` | Gonflement lié à la grille, plafond de 2 000 échantillons | Balayages triangulaires à largeur réelle |
| `reduction_motion` | Diamètre, percement et pistes gonflés ; 128 intervalles, profondeur 10 | Balayages conjoints et volume physique du via |
| `krt_clearance`, `krt_sweep` | Keepouts et distances aux pads échantillonnés ; voisinage arbitraire de 5 mm | Composition analytique des formes et primitives KRT ; voisinage issu des dimensions et règles réelles |
| Clearance | Tolérance géométrique de 0,0001 mm | Résidu numérique `FP_EPS_MM` de KRT, 1e-9 mm, indépendant de la grille |
| Recherche G3/pads/vias | Certains refus de grille éliminaient un candidat | La grille seule ne suffit plus à rejeter ces candidats |
| Coudes et glissements | Arrondis intermédiaires de 4 ou 6 décimales | Construction aux ancres réelles, sans arrondi des coordonnées produites |
| Validation octolinéaire | Tolérance pouvant dépendre du pas de grille | Contrôle commun indépendant de la grille |
| Chaînes | Largeurs regroupées après arrondi ; arrêts à 100 segments | Largeurs exactes ; marche jusqu'à l'ancre réelle ou la fin des arêtes non visitées |
| Graphes de chaînes | Clés proches pouvant créer une fausse jonction | Vérification des extrémités réelles ; pas de fermeture implicite d'un espace |
| Recherche de glissement | Plafond implicite de 2 000 positions | Plus de plafond de production ; budget temporel conservé |
| Fusion KRT | Mutation immédiate et exemption déclarative | Proposition sur copie, preuve de même support cuivre/largeur/net/couche et contrôle électrique avant application |

`krt_sweep` compose les primitives exactes de KRT avec ses tableaux de formes :
rectangles intérieurs et rayons physiques des pads, capsules et anneaux.
Cela n'introduit ni un second jeu de règles ni une modification de KRT.
Le Centering réutilise cette distance aux pads ; son ordonnancement reste inchangé.

Les fusions rejetées sont journalisées avec le nom du net et la raison. La
proposition refusée laisse le cuivre et les résultats vivants intacts ; les
autres nets peuvent conserver leurs réductions valides. L'étiquette
`geometry_preserving` est justifiée par une preuve de support, pas par le nom
de l'opération. C'est notamment ce garde qui évite l'annulation sur `azukar_fpga`.

Les marges d'invalidation des caches sont conservées : elles imposent davantage
de recalculs, sans grossir le cuivre. Les critères de gain, la résolution de
recherche, les familles de candidats et les limites G4 restent des politiques
d'optimisation explicites, pas des certificats de clearance. Cette revue ciblée
ne prétend pas démontrer l'absence de tout défaut dans l'ensemble du plugin/KRT,
ni garantir l'optimum global ou un gain inchangé sur chaque net.

## Reproduction native de `/A`

Carte `test_centering1/test_centering2.kicad_pcb`, SHA-256
`02444ca7e2856235f09683a66ef85a7206e1280926a436f780a5c1019d133cec`.
Python KiCad 10.0.5, net 7 `/A`, grille 0,1 mm, corridor actif, une passe G4
supplémentaire au maximum. Carte détachée, aucune sauvegarde.

```powershell
D:\kicad\bin\python.exe tools/reproduce_corridor_fold.py C:/Users/frant/Downloads/kicad_centering/test_centering1/test_centering2.kicad_pcb
```

- Longueur : 63,41214893 → 60,59214893 mm ; gain 2,8200 mm.
- Pistes : 8 → 7 ; paires en recouvrement collinéaire positif : 1 → 0.
- Le segment `(146.255,90.445) → (144.845,90.445)` et son voisin sont
  remplacés par `(146.255,90.445) → (158.265,90.445)`.
- Réduction par G3, pas par une fusion spécifique.
- Sortie octolinéaire, G5 valide, zéro régression de connectivité signalée.
- SHA source inchangé. Pas de validation visuelle interactive, de remplissage
  des zones ni de DRC KiCad complet.

## Tests unitaires et protocole PACK0

La suite complète donne **369 réussites et un échec préexistant** :
`test_a_later_gloss_completely_removes_a_longer_centering_path` ne centre aucune
porte. Il reste actif et échoue, sans `xfail` ni assertion affaiblie. Les anciens
contrôles d'inventaire Markdown et d'import optionnel testent maintenant le
contrat actuel. Les fixtures d'optimisation censées être valides sont réellement
octolinéaires ; les tests de glissement comparent les points analytiques et non
un ancien arrondi décimal.

Les tests dédiés couvrent rotations/réflexions, trois grilles, obstacles enfermés,
obstacles fins entre anciens échantillons, pads tournés, règles dépassant l'ancien
voisinage de 5 mm, percement du même net, expiration, largeur exacte, chaînes de
120 segments, fausses jonctions et rejet transactionnel d'une fusion.

PACK0 est exécuté après les tests unitaires, avec et sans corridor. Protocole :
grille 0,1 mm, budget initial 60 s, G4 actif (maximum deux passes supplémentaires),
tous les nets routés admissibles, aucune écriture des PCB. Parsing séparé ; le
temps moteur inclut contexte, G4 et G5, pas l'application native. G4 n'est pas
borné par les 60 s. Les mesures sont des passages uniques par configuration,
sans préchauffage ; les relances de diagnostic ne constituent pas une statistique
de performance. Empreintes vérifiées avant et après chaque exécution.

### Résultats définitifs

Les dix exécutions corrigées donnent G5 vrai, zéro régression de connectivité
signalée et zéro nouveau segment non octolinéaire. Les dix sources sont intactes.
Le contrôle indépendant des directions du benchmark utilise 1e-7 mm ; le moteur
emploie le seuil plus strict de KRT, 1e-9 mm.

| Carte | Gain avant sans corridor (mm) | Gain après sans corridor (mm) | Temps après (s) | Nets/s |
| --- | ---: | ---: | ---: | ---: |
| micro_dmm | 7,6664 | 8,4240 | 0,484 | 59,94 |
| chart_plotter_hat | 64,5262 | 66,9654 | 4,267 | 14,76 |
| environment_sensor | 27,0909 | 24,3122 | 3,887 | 13,38 |
| azukar_fpga | 0 (annulé) | 127,6291 | 30,038 | 4,73 |
| tildagon_base | 113,7842 | 102,3960 | 66,810 | 2,45 |

| Carte | Gain avant avec corridor (mm) | Gain après avec corridor (mm) | Temps après (s) | Nets/s |
| --- | ---: | ---: | ---: | ---: |
| micro_dmm | 2,5919 | 2,5919 | 0,385 | 75,24 |
| chart_plotter_hat | 0 (annulé) | 36,0666 | 3,907 | 16,13 |
| environment_sensor | 9,1625 | 12,8956 | 2,444 | 21,28 |
| azukar_fpga | 0 (annulé) | 59,4685 | 22,808 | 6,23 |
| tildagon_base | 23,1025 | 38,8482 | 37,813 | 4,34 |

Les anciens temps sont également conservés dans les données, notamment 86,093 s
sans corridor et 25,865 s avec corridor pour tildagon. Le nouveau certificat
continu ne constitue donc pas une accélération universelle.

Données et journaux : [avant sans corridor](data/corridor_before_off_2026_09_08.json),
[après sans corridor](data/corridor_after_off_2026_09_08.json),
[avant avec corridor](data/corridor_before_on_2026_09_08.json),
[après avec corridor](data/corridor_after_on_2026_09_08.json),
[audit des deux cartes avec baisse de gain](data/corridor_loss_audit_2026_09_08.json).

Reproduction : `tools/benchmark_architecture.py --budget 60 --output ...`,
avec `--corridor` pour l'autre configuration, `--details` pour conserver les
instantanés par net et `--engine-root` pour la référence archivée. Le script
retourne un statut non nul si G5 échoue, si la source change ou si une nouvelle
direction est invalide. `tools/compare_corridor_runs.py avant.json apres.json
--output audit.json` contrôle les instantanés détaillés sans sauvegarder de PCB.

### Interprétation des différences de gain

Les géométries ne sont pas identiques à `cc758f9`. Sans corridor, deux cartes
économisent moins de longueur : `environment_sensor` et `tildagon_base`.
L'audit des sorties de référence y a trouvé respectivement 35 et 409 nouveaux
segments non octolinéaires malgré G5 valide.

Le contrôle indépendant des instantanés distingue le cuivre déjà présent des
portions nouvelles : les anomalies de clearance conservées après correction
sont héritées des portions d'entrée reprises à l'identique par les fusions,
pas de cuivre nouvellement créé. Les anciennes sorties présentent aussi des
portions nouvelles refusées par les contrôles exacts. Ne pas attribuer cependant
chaque perte de gain à ces défauts : les choix successifs d'un optimiseur local
changent aussi ses possibilités. Aucune non-régression du gain par net n'est revendiquée.

Ces contrôles ne réparent pas tous les défauts initiaux d'une carte. Une fusion
prouvée conserver le cuivre peut conserver un défaut initial de clearance.
KRT ne modélise pas toutes les conditions `.kicad_dru` ; ses avertissements restent
pertinents. G5 n'est ni un DRC KiCad complet ni une validation graphique.
