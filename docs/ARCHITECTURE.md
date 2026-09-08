# Architecture du moteur Gloss

Le plugin KiCad charge une carte détachée, configure le moteur et applique
uniquement son résultat certifié. KRT conserve la responsabilité des distances,
obstacles, clearances et graphes électriques. La façade `dgloss/krt_api.py`
résout les symboles une fois ; elle n'ajoute pas de dispatch par candidat.

## Responsabilités

| Module | Responsabilité |
| --- | --- |
| `pipeline` | Actions publiques, transaction Gloss/Centering, assemblage des résultats |
| `optimization` | Une passe ordonnée et ses services explicites `PassOperations` |
| `passes` | Arrêt G4 par gain marginal et nombre de passes |
| `transaction` | Résultat, propriété des entrées et restauration complète |
| `certification` | Vérifications de passe et certification finale KRT |
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
par net modifié dans chaque étape. La fusion réalisée par KRT notifie le même
chemin d'invalidation après son propre remplacement.

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
