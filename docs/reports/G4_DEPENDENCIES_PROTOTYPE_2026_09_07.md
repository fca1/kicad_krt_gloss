# Prototype G4 : reprises ciblées et seuil de gain marginal

Demande : s'inspirer de la gestion des dépendances de l'autorouteur KRT, tester
sur tildagon_base de PACK0 (dépassement du budget 60 s), et ajouter un critère
d'arrêt à partir de la troisième passe.

## Comportement expérimental

`tools/dependency_g4.py` s'active explicitement par un contrôleur de contexte.
Le code de production, KRT et les paramètres de l'interface ne sont pas modifiés.
Les recherches et validations géométriques restent celles de production.

Pendant la première chaîne et les passes G4, les contrôles de segments et vias
refusés par `KrtClearanceAdapter` enregistrent une zone de dépendance, élargie
par les clearances de configuration. Le `SpatialIndex` KRT (via la facade
existante) stocke ces abonnements avec une maille d'indexation de 2 mm. Cette
maille n'est ni le pas de routage de 0,1 mm, ni un certificat de clearance.
L'index est Python, pas la grille native Rust. Les refus ne sont pas attribués
à un bloqueur exact : ce sont des dépendances spatiales approximatives.

Une modification réveille son propre net et les abonnements recoupant les
anciennes ou nouvelles positions du cuivre. Les propriétaires de zones sont
réveillés largement pour leurs dépendances topologiques. Les grandes régions
dépassant 4 096 cases basculent vers un réveil conservateur ; ce seuil ne tronque
pas silencieusement l'index. Les abonnements sont dédoublonnés et conservés pour
tout le run : des dépendances périmées peuvent occasionner des reprises inutiles.

La première vague G4 est initialisée depuis les changements de la chaîne initiale.
Les vagues suivantes concernent les nets affectés par la précédente. Au sein
d'une vague, l'ordre numérique alterné est conservé pour isoler le changement
de périmètre. Ce prototype ne parallélise pas les transformations.

Certaines décisions de rejet ne passent pas par ces contrôles, et les zones
enregistrées ne prouvent pas toutes les dépendances. Une vague ciblée silencieuse
est donc suivie d'un audit de tous les nets avant de déclarer `converged`.
Un arrêt sur budget ou gain marginal n'est jamais présenté comme convergence.

## Seuil de gain marginal

Interprétation annoncée avant l'essai : la chaîne initiale est la passe totale 1 ;
la première G4 est la passe totale 2. À partir de la passe totale 3, arrêter si :

`gain_de_la_passe <= gain_de_la_passe_précédente * 0,01`

Exemple : passe 2 = 10 mm gagnés ; passe 3 = 0,1 mm gagnés : arrêt.
Ce n'est pas 1 % de la longueur restante de la carte. Le calcul utilise les gains
non arrondis ; si le précédent gain est nul ou numériquement négligeable, le ratio
n'est pas défini et ce critère ne s'applique pas. L'arrêt est évalué après une
passe complète ; l'expiration du budget reste prioritaire. Le résultat accepté
de la dernière passe est conservé et passe les validations finales habituelles.

Le seuil 1 % reste interne au prototype, réglable via `Controller(percent=...)`.
L'arrêt est publié sous `marginal_gain` pour le distinguer de `converged`.

## Mesure à 60 s sur tildagon_base

Un seul passage du prototype, sans préchauffage ou répétition ; comparaison à
la mesure initiale PACK0, sans relancer le contrôle. Même SHA256, options de
production par défaut, corridor=False, grille 0,1 mm, budget 60 s, sans Centering.
La gestion des dépendances est incluse dans le temps et consomme le budget.

| Mesure | Production PACK0 | Prototype |
|---|---:|---:|
| Temps Gloss | 62,587 s | 62,496 s |
| Gain de longueur conservé | 107,3993 mm | 99,7063 mm |
| Nets du périmètre | 164 | 164 |
| Nets sélectionnés pour la première G4 | 164 | 146 |
| Gain de la première G4 | 21,0992 mm | 13,4061 mm |
| Temps G4 | 20,729 s | 15,396 s |
| Passes G4 complètes | 0 | 0 |
| Temps G5 | 1,205 s | 1,293 s |
| Validation G5 | Valide | Valide |
| Régressions de connectivité rapportées | 0 | 0 |
| Arrêt | Budget | Budget |

18 nets ne sont pas sélectionnés dans cette vague (-11 %). Cela ne suffit pas à
terminer la passe. Les 91 ms d'écart de temps total ne sont pas une accélération
significative établie : les deux exécutions sont contraintes par le budget.
Le prototype conserve 7,6930 mm de réduction en moins (environ 7,2 % du gain
de référence). Il ne démontre donc pas une amélioration du rendement sous budget.

Le temps G4 plus court ne prouve pas une accélération de G4 : la première chaîne
consomme davantage de temps dans cet essai, laissant moins de budget à G4.
Par exemple G3 passe de 21,861 à 24,055 s et G3 local de 6,537 à 7,686 s.
L'instrumentation peut contribuer à ces coûts ; une seule mesure ne permet pas
de séparer sa contribution de la variabilité d'exécution. Les gains avant G4
restent identiques à l'arrondi (86,3002 mm).

Compteurs de dépendances :

- 49 743 consultations refusées observées ;
- 10 841 abonnements enregistrés, 39 004 réutilisations/doublons évités ;
- aucun basculement « grande région » ;
- 146 nets notifiés pour la vague initiale ;
- 301 ms mesurées dans l'enregistrement et la recherche des abonnements.

Ces 301 ms ne mesurent pas tout le surcoût des wrappers : l'interception des
consultations réussies, notamment, n'entre pas dans ce compteur.

La passe totale 3 n'est pas atteinte. Le critère de 1 % ne se déclenche donc pas
sur cette carte et n'explique aucune différence de résultat. Il ne peut pas
résoudre un dépassement survenant dès la deuxième passe totale.

## Vérifications et suite à envisager

36 tests ciblés passent : dépendances proches/éloignées/couches, repli conservateur,
zones, audit complet après vague silencieuse, calcul du seuil, arrêt effectif à
la troisième passe avec conservation du résultat, G4 existant, politique,
corridor et transaction Centering. G5 valide les changements du PCB testé ;
le SHA256 du fichier source est inchangé. Aucun DRC natif KiCad n'est exécuté.

Le prototype reste expérimental. L'essai à 60 s ne permet pas de valider l'efficacité
des vagues ultérieures, faute d'atteindre la troisième passe. Pour améliorer la
première vague, il faudrait mieux sélectionner ou ordonner les recherches
coûteuses, et réduire le coût avant G4. L'attribution aux bloqueurs exacts reste
à étudier ; la simple empreinte des contrôles refusés est encore assez large
pour réveiller 89 % des nets. Aucun correctif supplémentaire n'est intégré ici.

Reproduction : `python tools/benchmark_dependency_g4.py`.
Données : `data/dependency_g4_tildagon_2026_09_07.json`.
Référence : [PACK0](../PACK0.md).

## Extension demandée : budget 120 s

À la demande de l'utilisateur, un passage supplémentaire du même prototype,
avec le seul budget porté à 120 s. Ce n'est pas une répétition du même réglage.
Pas de nouvelle exécution de production à 120 s : la comparaison directe de
l'efficacité de l'ordonnanceur à budget égal reste donc indisponible.

| Mesure | Prototype 60 s | Prototype 120 s |
|---|---:|---:|
| Temps Gloss | 62,496 s | 121,326 s |
| Réduction conservée | 99,7063 mm | 130,5828 mm |
| G4 complètes | 0 | 4 |
| Temps G4 | 15,396 s | 82,519 s |
| Temps G5 | 1,293 s | 1,057 s |
| G5 / régressions de connectivité | Valide / 0 | Valide / 0 |
| Arrêt | Budget | Budget |

La réduction augmente de 30,8765 mm. La latence dépasse le nouveau budget de
1,326 s. Le SHA256 de la source est inchangé. La passe initiale produit encore
86,3002 mm de réduction, puis G4 ajoute 44,2826 mm.

| Passe totale | Type | Nets sélectionnés | Temps | Gain mm | Gain / gain précédent | Complète |
|---|---|---:|---:|---:|---:|---|
| 2 | Affectés | 146 | 24,577 s | 21,3687 | 24,76 % | Oui |
| 3 | Affectés | 135 | 23,192 s | 13,0154 | 60,91 % | Oui |
| 4 | Affectés | 102 | 18,844 s | 5,7528 | 44,20 % | Oui |
| 5 | Affectés | 75 | 15,347 s | 4,1458 | 72,07 % | Oui |
| 6 | Affectés | 66 | 0,454 s | 0,0000 | Non interprétable | Non |

Le seuil de 1 % n'est atteint par aucune des passes complètes où il s'applique.
Le gain nul de la passe 6 ne permet pas de conclure : le budget interrompt cette
passe. Le contrôle du budget est prioritaire, donc aucune fausse convergence
ou fausse conclusion de faible rendement n'est enregistrée. Aucun audit complet
de tous les nets n'est atteint dans cet essai.

Le nombre de nets sélectionnés décroît effectivement de 146 à 75 sur les quatre
vagues complètes. Leur temps ne diminue pas proportionnellement (24,6 à 15,3 s) :
réduire le nombre de nets ne suffit pas à prédire le coût des nets restants.
Les compteurs enregistrent 126 597 refus, 11 534 abonnements, 115 552 doublons,
aucun repli grande région, et 506 ms dans la gestion des abonnements (toujours
hors coût complet d'interception des appels).

Cette extension vérifie que les vagues ciblées progressent avec des résultats
certifiés jusqu'à la passe 5. Elle ne démontre ni la convergence de la carte
ni une accélération par rapport à la production à 120 s. Le critère marginal
est opérationnel mais n'apporte pas d'arrêt anticipé sur les passes observées.

Reproduction :
`python tools/benchmark_dependency_g4.py --budget 120 --output .build/dependency_g4_tildagon_120.json`.
Données : `data/dependency_g4_tildagon_120_2026_09_07.json`.
