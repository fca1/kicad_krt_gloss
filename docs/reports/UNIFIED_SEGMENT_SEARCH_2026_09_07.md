# Recherche commune de segments — essai et choix d'intégration

Essai demandé le 7 septembre 2026, avant un nouveau cycle de prototype.
Production inchangée. Branche de travail : main. Aucun push ou ZIP.

## Ce qui a été testé

Le harnais `tools/unified_segment_search.py` impose la même recherche locale
sur fenêtres de deux/trois segments, avec le glissement adaptatif existant,
pour la réduction de longueur dans les deux modes. Le booléen corridor ne
change plus cette sélection de moteur : il active seulement le certificat
de déplacement. Clearance finale et connectivité restent obligatoires.

La recherche plus large sur la chaîne n'est pas exécutée pour la réduction
de longueur dans cette variante. La réduction du nombre de segments à longueur
égale conserve son chemin existant dans les deux modes. La passe locale tardive
du mode sans corridor est neutralisée, puisque G3 utilise déjà ce moteur.
Les autres étapes du pipeline et leurs options ne sont pas modifiées.

Les paramètres des certificats, leurs subdivisions et leurs budgets restent
ceux du prototype précédent. Ni filtre Rust ni nouveau cache ne sont ajoutés.
Le nouveau paramètre des modules expérimentaux vaut True par défaut : les
anciens essais de prototype conservent leur comportement.

Cette comparaison évalue un choix de recherche complet ; elle n'isole pas
le simple coût du test booléen. Les séquences de candidats, les seuils du
moteur local et les optimisations suivantes peuvent différer de la référence.

## Validation

67 tests ciblés réussis : les deux modes passent par le moteur local commun,
la désactivation du corridor ne désactive ni clearance ni connectivité,
un raccourci non admissible par déformation peut être accepté sans corridor,
et la passe locale redondante reste vide. Les tests antérieurs de géométrie,
budgets, marges Rust et transaction Centering sont également exécutés.

Un seul essai par carte/variante/mode, sans préchauffage ni répétition.
Budget 20 s, Gloss complet sans Centering ; parsing exclu, contexte et G5 inclus.
L'ordre des variantes est décalé entre les deux cartes. Les sources ne sont
pas écrites et leurs SHA256 restent identiques.

| Carte | Corridor | Temps actuel | Temps unifié | Gain actuel | Gain unifié |
|---|---|---:|---:|---:|---:|
| dispenser | Non | 7,809 s | 3,094 s | 20,4292 mm | 18,1539 mm |
| dispenser | Oui | 2,430 s | 3,802 s | 11,9936 mm | 17,3958 mm |
| bitaxe_ultra | Non | 15,842 s | 9,560 s | 116,7689 mm | 117,8208 mm |
| bitaxe_ultra | Oui | 9,192 s | 13,261 s | 55,1363 mm | 77,1097 mm |

Les huit essais convergent, passent G5 et rapportent zéro régression de
connectivité. Ces mesures uniques ne sont pas une estimation statistique.

Sans corridor, le moteur commun réduit fortement le temps dans les deux cas.
La perte de 2,2753 mm de gain sur dispenser montre cependant que la recherche
plus large reste utile sur certaines géométries. Avec corridor, les gains
augmentent mais le coût des certificats demeure.

Les deux modes unifiés partagent la recherche ; ils ne garantissent pas un
résultat global identique, car accepter un autre candidat modifie les fenêtres
suivantes. Sans corridor, la recherche adaptative garde une politique locale
et n'énumère pas toutes les régions libres derrière un obstacle.

Résultats locaux : `.build/unified_segment_known_boards.json`.

```text
python tools/benchmark_unified_segment_search.py C:/Users/frant/Documents/KiCad/10.0/projects/dispenser/dispenser.kicad_pcb C:/Users/frant/Documents/kicad_track_gloss_stress/sources/set1/bitaxe_ultra.kicad_pcb --output .build/unified_segment_known_boards.json
```

## Possibilités d'intégration encore ouvertes

Les microsegments, caches KRT existants, façade KRT, transaction Gloss puis
Centering, contrôle conjoint vias/T et recherche pad déjà intégrés ne sont
pas remis dans cette liste.

| Possibilité | État des preuves | Proposition avant décision |
|---|---|---|
| Sens utile seul dans le parcours existant | 676 fenêtres d'ember : 4 974 → 691 contrôles, mêmes candidats | Intégration isolée envisageable ; bénéfice total de temps non mesuré |
| Recherche locale commune aux deux modes | Huit essais présents valides ; sans corridor plus rapide, perte de gain sur dispenser | Choix prometteur ; décider si cette perte est acceptable ou garder un complément large ciblé |
| Glissements partiels adaptatifs | Gains supplémentaires sur cartes connues ; coût du corridor encore élevé | Conserver en prototype jusqu'à amélioration du certificat |
| Budget de certificat par candidat, verdict indéterminé distinct | Profil bitaxe : 41 recherches épuisent 512 contrôles sur le premier candidat, sans résultat | Priorité du prochain cycle ; pas encore implémenté/testé |
| Certificat des voisins sorti de la subdivision du segment central | 12 740 appels / 1,70 s dans le profil bitaxe ; couverture par le voisin le plus long | À prototyper et mesurer, sans additionner ce coût aux recherches plafonnées |
| Cache de fenêtres infructueuses | 280 recherches sur une géométrie source déjà rencontrée | À prototyper avec invalidation cuivre/topologie ; les 280 ne sont pas toutes réutilisables |
| Enveloppe décalée et marges Rust | Rapide mais peu de réponses libres ; 32 désaccords avec l'exact sur picofx sans garde | Ne pas intégrer comme certificat autonome ; rôle de guidage éventuel à tester |

Une recherche large complémentaire reste une option de conception, pas un
correctif mesuré dans cet essai. Elle devrait être choisie indépendamment du
booléen corridor et appliquer le même contrat de validation.

Les limites connues de certification des contacts intermédiaires de zones
et du cuivre du même net restent présentes. Aucun DRC natif KiCad ni
remplissage des zones n'a été exécuté pour cet essai. Aucun nouveau cycle de
prototype n'est lancé après cette comparaison.
