# Architecture du moteur Gloss

Le plugin KiCad charge une carte détachée, configure le moteur et applique
uniquement son résultat certifié. KRT conserve la responsabilité des distances,
obstacles, clearances et graphes électriques. La façade `dgloss/krt_api.py`
résout les symboles une fois ; elle n'ajoute pas de dispatch par candidat.
`kicad_krt_gloss/kicad_bridge.py` est la frontière inverse : elle rassemble les
accès KRG aux bindings natifs de KiCad (carte active, sélection, application,
rafraîchissement), sans réimplémenter l'import, les règles ou les validations
KRT.

## Responsabilités

| Module | Responsabilité |
| --- | --- |
| `pipeline` | Entrées publiques, transaction Gloss, assemblage des résultats |
| `optimization` | Une passe ordonnée et ses services explicites `PassOperations` |
| `passes` | Arrêt G4 par gain marginal et nombre de passes |
| `transaction` | Résultat, propriété des entrées et restauration complète |
| `certification` | Vérifications de passe et certification finale KRT |
| `corridor`, `reduction_motion` | Construction de déformations continues, sans gonflement artificiel |
| `krt_clearance`, `krt_sweep` | Composition des formes, distances et règles KRT pour les capsules et surfaces balayées |
| `krt_merge` | Proposition KRT sur copie, preuve du support cuivre et garde électrique avant publication |
| `outcome_geometry` | Signatures géométriques et différences visuelles finales |
| `context` | Cuivre modifiable, application des remplacements, invalidations et obstacles |
| `board_views` | Vues par net et requêtes de contact pad indexées par KRT |
| `chain_topology` | Construction et parcours des chaînes, indépendants des stratégies |
| `route_geometry` | Primitives partagées par pistes, pads, vias et jonctions |
| `corner_reduction` | Réductions locales par supports octolinéaires, contact KRT et certificat de surfaces emboîtées |
| `width_transitions` | Absorption locale d'un segment près d'une transition libre, avec largeurs distinctes et mouvement conjoint certifié |
| `topology` | Politique électrique et réutilisation des certificats de référence |
| `algorithm`, `local_gloss`, `via_mobile`, `pad_terminals`, `sliding_nodes` | Recherche et sélection des transformations |
| `kicad_bridge` | Façade KRG vers la carte KiCad native ; délégation de l'import et des règles à KRT |

Les anciens points d'import des helpers restent disponibles dans `algorithm`,
et `pipeline` pour les outils de diagnostic. Les stratégies utilisent
directement les modules partagés lorsque cela évite une dépendance réciproque.

## Frontière native KiCad

L'orchestration, y compris la mémoire EB intégrée, utilise les méthodes publiques
de `KiCadBoardBridge`. Les imports `pcbnew` nécessaires à l'enregistrement du
plugin ne donnent pas accès aux opérations de carte dans l'orchestration.
Les adaptateurs `selection.py`, `board_adapter.py`, `gloss_visualization.py` et
`native_branch_selection.py` implémentent les accès natifs derrière cette façade.
L'adaptateur EB conserve l'index UUID, la capture et le highlight ; il ne change
ni la sélection native, ni les algorithmes KRT. Le test `test_kicad_boundary.py`
contrôle les imports et les accès natifs identifiés sur les modules de production.

## Durée de vie des données

Les préparations de clearance sont dans `clearance_preparation.py`, derrière
`KrtClearanceAdapter`. Pads/règles fixes : arêtes et règles préparées par couche.
Cuivre mobile : rectangles englobants reconstruits à chaque nouvelle liste de
segments. Les prédicats KRT des vias restent dans les méthodes `_exact`, après
présélection conservatrice cuivre/perçages ; les pads sont tous conservés.
Les premières distances bloquantes interrompent les contrôles inutiles.
Les références électriques restent en cache uniquement pour les nets inchangés
sans zone ; chaque modification invalide tous les nets possédant une zone.
Les contrôles finaux G5 restent présents, sans réutilisation des grades finaux.

`zone_models` présélectionne les pistes et vias pouvant atteindre la grille
d'une petite zone, avec leurs rayons, les clearances de classes et une marge
de deux cellules arrondie vers l'extérieur. KRT construit ensuite le modèle
complet ; pads, règles, contours et keepouts restent ceux de la carte entière.
Les zones dont la grille couvre au moins un quart du rectangle de la carte
gardent le chemin original pour éviter une présélection peu rentable. Ce seuil
ne change que le coût. En cas d'échec de la présélection, KRT reçoit la carte
entière. Le modèle est publié dans les deux caches KRT existants et suit les
invalidations habituelles.

`same_net_index` fournit un instantané ordonné des segments extérieurs à une
recherche de chaîne, de connecteur de pad ou de réduction locale. Une grille
paresseuse présélectionne leurs axes ; les prédicats de contact et de recouvrement
restent inchangés. La requête inclut une marge supérieure à la tolérance de
colinéarité. Les petits ensembles gardent le parcours intégral ; les grandes
requêtes ou les ensembles avec beaucoup de longs segments utilisent un filtre
vectorisé des rectangles englobants. Les grands segments restent sinon dans
une liste de débordement toujours consultée. Les contacts aux extrémités sont
indexés avec les clés de position KRT exactes. L'ordre initial est conservé.
L'index ne survit pas à la recherche et
n'est jamais partagé entre révisions du cuivre.

Chaque contexte ouvre une nouvelle durée de vie pour les vues et les certificats.
Pendant une action, pads et règles sont fixes ; les pistes et vias sont remplacés
par de nouveaux objets, sans modification en place. Les vues par net suivent les
listes de cuivre et le cache de chaînes conserve les objets qui justifient ses clés.

Les contacts avec les pads utilisent l'index spatial KRT puis la distance exacte
KRT. Leur mémoïsation est bornée à 16 384 requêtes. Les chaînes sont réutilisées
uniquement si leurs segments, vias et périmètre modifiable sont identiques.

`GlossContext.apply_replacement` applique le cuivre déjà validé et notifie les
caches et le périmètre modifiable. La carte d'obstacles sur grille est construite
à la première sonde de chanfrein qui la consulte, depuis le cuivre courant.
Avant cette construction, les notifications de rafraîchissement ne construisent
rien. Ensuite, les cartes sont rafraîchies une fois par net modifié dans chaque
étape. Les étapes purement géométriques ne demandent pas de carte sur grille.
Le cache des distances exactes aux pads, fixes pendant l'action, conserve au
maximum 32 768 entrées pour limiter les évictions entre passes G4.
KRT propose les fusions sur une copie ; seuls
les remplacements prouvés préserver le support cuivre et la connectivité sont
publiés par ce même chemin. L'étiquette `geometry_preserving` exige cette preuve.

Le certificat électrique de référence peut être partagé entre recherches sur
le même état. Toute mutation invalide ce cache, y compris celle d'un autre net
qui pourrait affecter un plan de cuivre. Les certificats des candidats et les
grades finaux G5 sont recalculés. Cette réutilisation n'enlève aucune validation.

Une restauration remet les objets initiaux et leur propriété dans les résultats,
invalide les vues et les références électriques, puis supprime les modèles de
zones du PCB et leurs entrées secondaires KRT lorsqu'elles lui appartiennent.
Les modèles d'un autre instantané ne sont pas supprimés.

Les règles de mouvement, l'ordre des candidats, l'autogloss, les limites G4 et
la transaction Gloss sont conservés.
