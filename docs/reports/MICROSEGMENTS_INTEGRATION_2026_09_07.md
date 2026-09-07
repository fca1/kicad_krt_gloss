# Intégration microsegments — 7 septembre 2026

Suite au go explicite « integre microsegments », le commit enregistre
`local_gloss.py`, son raccordement dans `shorten_routes` et la passe locale
de fin d'optimisation dans le pipeline. Ces dépendances étaient présentes
dans le répertoire de travail lors des mesures sur cartes, mais non commitées.
La réparation géométrique est déjà enregistrée dans `07f36c4`.

Le correctif reconstruit un raccord sans microsegment lorsque c'est possible,
avec extrémités fixes et validations KRT. La géométrie précédente reste en place
si aucune proposition valide et améliorante n'est trouvée. Les segments
inchangés ne sont pas déclarés comme retirés ou ajoutés.

Le contrôle supplémentaire des contacts n'est pas intégré. Les modifications
préexistantes du déroulement de Centering, de l'interface, des versions et du
packaging restent hors de ce commit. KRT n'est pas modifié.

## Historique des vérifications

| Point | Quand et suite à quoi | Preuve et portée |
|---|---|---|
| Réparation géométrique | 7 septembre, après l'accord sur le point (1) de la revue | Quatre tests ciblés : raccord presque diagonal, absorption d'un microsegment existant, obstacle bloquant, rotations. |
| Cartes réelles | 7 septembre, après le go d'extension puis la demande d'écarter les contacts | picofx_pump : 129,49 mm en 12,27 s ; dispenser : 20,43 mm en 7,78 s. Trois répétitions par variante, validation G5. Voir les rapports dédiés. |
| Raccordement dans le pipeline | 7 septembre, après le go d'intégration | Deux nouveaux cas avec/sans corridor, recherche DAG neutralisée pour isoler le chemin local ; réduction effective et G5 valide. |
| Delta des segments inchangés | 7 septembre, après le go d'intégration | Nouveau cas où seule une portion de la chaîne change ; les objets conservés sont absents des listes de retrait et d'ajout. |
| Clearance, connectivité, corridor | Revue initiale du 7 septembre, puis intégration | Tests existants de politique et corridor relancés avec les tests microsegments. 27 tests passent, également avec le pipeline de l'index Git, excluant les changements Centering en attente. |
| Départ pad/via/T | Clarification de l'utilisateur après le point (2) de la revue, le 7 septembre | Comportement accepté et code examiné ; pas de nouvelle campagne dédiée comparant exhaustivement les trois types d'ancres. Ce n'est pas un nouveau correctif. |
| Contacts supplémentaires | 7 septembre, après la demande de prototype puis d'extension | Sept petits exemples, puis picofx_pump : environ +5 % de temps ; refus supplémentaires non tous classés. Mis de côté à la demande de l'utilisateur. |
| Gloss avant Centering | Rapport préexistant daté du 6 septembre | `docs/CENTERING_PROTECTED_C.md` documente test_centering2, net /C. Ce résultat est historique, pas un nouvel essai effectué pour les microsegments ; Centering était désactivé dans les mesures picofx_pump/dispenser. |

## Tests rapides d'intégration

```powershell
python -m pytest -q -p no:cacheprovider tests/test_local_micro_cleanup.py tests/test_corridor.py tests/test_gloss_policy.py
```

27 tests réussis. Les mesures sur cartes n'ont pas été répétées pour ce commit :
le chemin de production Gloss est celui déjà mesuré ; les changements de ce
dernier passage portent sur son enregistrement Git et les tests d'intégration.
La validation KRT ne constitue pas un DRC natif KiCad avec remplissage des zones.
