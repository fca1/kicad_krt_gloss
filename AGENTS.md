# Instructions du projet

Le projet Smooth Gloss KRT est un projet de référence.

Pour reprendre le projet, lire d'abord [le guide de reprise](docs/REPRISE_PROJET.md),
puis les références pertinentes qu'il indique. Mettre ce guide à jour après
une intégration qui change les règles, l'architecture ou les limites connues.

Analyser avant toute action.

Modifier le code uniquement après « go ».

Créer un ZIP uniquement sur demande explicite.

Après une modification validée, faire un commit dédié sans inclure les autres
modifications existantes du dépôt.

Les tests doivent être rapides et ciblés, sauf demande contraire.

KRT reste l’autorité pour les obstacles, les clearances et les validations.

KRT ne doit pas être modifié.

Gloss et Centering sont deux actions distinctes.

Lorsqu’un Centering est demandé :

1. exécuter le Gloss avec `stay_in_corridor=True` ;
2. exécuter ensuite le Centering ;
3. ne plus transformer la géométrie après le Centering.

Le Gloss doit raisonner sur les relations géométriques entre segments, sans
privilégier horizontal, vertical ou diagonal.

La réduction locale part d’un pad et progresse dans un seul sens.

Toute réduction doit respecter clearance, connectivité et, si activé, le
corridor admissible.

Les options internes ou expérimentales ne doivent pas être exposées sans
validation explicite.
