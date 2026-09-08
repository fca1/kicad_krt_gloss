# Refonte des responsabilités et non-régressions

Référence avant modification : `9d335f0`, branche `main`. KRT reste inchangé.
La carte source n'est jamais sauvegardée par les essais. Les SHA-256 de PACK0
sont vérifiés avant et après chaque exécution.

## Changements

- Restauration complète des données dérivées : modèles de zones et références
  secondaires KRT, vues du cuivre et certificats électriques.
- Application commune des remplacements validés dans `GlossContext` ; les
  stratégies ne recopient plus chacune le protocole d'invalidation.
- Vues des segments/vias par net ; index spatial KRT et mémoïsation bornée des
  contacts pad ; cache des chaînes associé à leur géométrie et périmètre.
- Partage du certificat électrique de référence entre recherches, invalidé
  après toute mutation. Les candidats et G5 restent vérifiés par KRT.
- Extraction des primitives géométriques et parcours de chaînes hors des
  stratégies via/pad/jonction, sans dépendances réciproques entre celles-ci.
- Séparation de la transaction, de la certification, de l'exécution d'une passe
  et des résultats visuels. `pipeline.py` passe de 869 à 507 lignes.
- Séparation du Centering en détection, géométrie, construction de chemins et
  orchestration. `interpad.py` passe de 1 213 à 332 lignes. Les règles et les
  possibilités de Centering restent inchangées.

La carte des responsabilités est décrite dans [ARCHITECTURE.md](../ARCHITECTURE.md).
Les imports historiques utiles aux outils sont conservés sous forme d'alias.

## Comparaison PACK0

Une mesure finale par version et par carte, sans répétitions statistiques ni
préchauffage. Première passe avec budget de 120 s pour éviter de comparer des
résultats tronqués par le temps ; G4 actif, maximum deux passes supplémentaires,
seuil de 10 %. Corridor désactivé. Aucun budget initial n'est épuisé.
Les temps incluent contexte, moteur et certification ; ils excluent parsing et
application native. La comparaison vérifie la signature géométrique exacte,
la réduction, le nombre de segments/vias et le nombre de passes G4.

| Carte | Avant, s | Après, s | Temps en moins | Nets/s après | Résultat |
| --- | ---: | ---: | ---: | ---: | --- |
| micro_dmm | 0.605 | 0.564 | 6.7 % | 51.40 | Géométrie identique, G5 valide |
| chart_plotter_hat | 4.285 | 4.058 | 5.3 % | 15.52 | Géométrie identique, G5 valide |
| environment_sensor | 4.619 | 4.203 | 9.0 % | 12.37 | Géométrie identique, G5 valide |
| azukar_fpga | 24.357 | 23.299 | — | — | Échec et restauration avant comme après |
| tildagon_base | 94.398 | 89.411 | 5.3 % | 1.83 | Géométrie identique, G5 valide |

Les écarts temporels sont indicatifs. `azukar_fpga` ne constitue pas une
validation fonctionnelle réussie : les deux versions abandonnent la transaction
et restituent la même géométrie initiale. Ce défaut préexistant n'est pas corrigé
par la refonte. Le détail est conservé dans
[les mesures JSON](data/architecture_regression_2026_09_08.json).

Commande : `python tools/benchmark_architecture.py --output <mesures.json>`.
L'option `--engine-root` permet d'utiliser une copie figée du moteur de référence.

## Tests et KiCad natif

Suite complète : **299 réussis, 4 échecs préexistants reproduits avec le moteur
de référence**. Aucun nouvel échec après refonte. Les quatre échecs concernent :

- la présence de `AGENTS.md` à la racine, que l'ancien test documentaire refuse ;
- le document explicatif français sans équivalent anglais dans l'ancien inventaire ;
- le test textuel d'absence de dépendance plugin, qui refuse la déclaration
  de l'accès optionnel à `NetSelectionPanel` dans la façade KRT ;
- `test_a_later_gloss_completely_removes_a_longer_centering_path`, dont le
  Centering ne produit déjà aucune porte centrée dans la version de référence.

Sept nouveaux cas couvrent les contacts indexés face aux distances KRT exactes
(trois rotations et plusieurs couches/largeurs), la restauration des modèles
de zones, le partage du certificat initial, son invalidation après une mutation
propre ou étrangère, la certification finale non cachée et les nouvelles ancres
via/périmètres modifiables dans le cache de chaînes.

Essai natif KiCad sur `test_centering2`, quatre nets, corridor et G4 actifs :
**0.820 s de moteur**, **0.0047 s d'application**, **112.2373 mm économisés**,
G5 valide, aucune assertion. L'application se fait uniquement sur la carte
détachée chargée en mémoire. Les modules du moteur refondu sont copiés dans un
répertoire de test contenant le runtime natif ; aucun ZIP n'est créé.

[Mesures natives](data/architecture_native_2026_09_08.json).
