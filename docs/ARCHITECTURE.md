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
| `pipeline` | Actions publiques, transaction Gloss/Centering, assemblage des résultats |
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
| `topology` | Politique électrique et réutilisation des certificats de référence |
| `algorithm`, `local_gloss`, `via_mobile`, `pad_terminals`, `sliding_nodes` | Recherche et sélection des transformations |
| `interpad_detection` | Détection des portes pad–pad |
| `interpad_geometry`, `interpad_types` | Géométrie d'une porte et descriptions immuables |
| `interpad_paths` | Construction des chemins candidats de Centering |
| `interpad` | Ordonnancement, validation et application du Centering |
| `kicad_bridge` | Façade KRG vers la carte KiCad native ; délégation de l'import et des règles à KRT |

Les anciens points d'import des helpers restent disponibles dans `algorithm`,
`interpad` et `pipeline` pour les outils de diagnostic. Les stratégies utilisent
directement les modules partagés lorsque cela évite une dépendance réciproque.

## Durée de vie des données

Chaque contexte ouvre une nouvelle durée de vie pour les vues et les certificats.
Pendant une action, pads et règles sont fixes ; les pistes et vias sont remplacés
par de nouveaux objets, sans modification en place. Les vues par net suivent les
listes de cuivre et le cache de chaînes conserve les objets qui justifient ses clés.

Les contacts avec les pads utilisent l'index spatial KRT puis la distance exacte
KRT. Leur mémoïsation est bornée à 16 384 requêtes. Les chaînes sont réutilisées
uniquement si leurs segments, vias et périmètre modifiable sont identiques.

`GlossContext.apply_replacement` applique le cuivre déjà validé et notifie les
caches et le périmètre modifiable. Les cartes d'obstacles sont rafraîchies une fois
par net modifié dans chaque étape. KRT propose les fusions sur une copie ; seuls
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
la transaction Gloss puis Centering sont conservés. Cette réorganisation
n'étend pas le Centering aux portes comportant des vias.
