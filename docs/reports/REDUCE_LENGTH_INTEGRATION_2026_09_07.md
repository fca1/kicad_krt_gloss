# Intégration de la réduction de longueur — 7 septembre 2026

Intégration autorisée après les essais du prototype sur dispenser,
picofx_pump, ember_he et bitaxe_ultra.

## Comportement intégré

- Les imports du moteur, du plugin et de la CLI passent par `dgloss/krt_api.py`.
  Voir `docs/KRT_API.md` pour le contrat et ses limites.
- Le certificat conjoint vias / segments incidents et jonctions T est dans
  `dgloss/reduction_motion.py`. Le pipeline l'active lorsque
  `stay_in_corridor=True`, et réutilise ses compteurs entre les passes.
  Il est donc actif dans le Gloss précédant le Centering atomique.
- La recherche G3.2 valide immédiatement les candidats compétitifs et conserve
  le meilleur déjà certifié si le budget expire. Elle exploite l'ordre croissant
  des longueurs dans chaque famille pour arrêter les candidats non compétitifs.
- Le certificat utilise l'horloge coopérative du moteur pour respecter
  pause et annulation. Les primitives et caches restent ceux de KRT.
- Les statistiques `corridor_motion` exposent les contrôles, refus et temps.
- Le moteur ne dépend plus du module de prototype dans `tools` ni de ses
  monkey-patches. Ce module reste uniquement un harnais A/B, avec l'ancienne
  recherche pad pour reproduire la variante de référence.

Le contrôle de déplacement reste conditionné à l'option corridor existante.
Le Gloss sans corridor garde cette liberté de déplacement. Aucune nouvelle
option expérimentale n'est exposée. Microsegments, caches KRT et transaction
Gloss puis Centering précédemment intégrés sont conservés.

## Validation

94 tests ciblés réussis : 79 tests de frontière KRT, microsegments, corridor,
déplacements, politique, transaction et plugin ; puis 15 tests existants
concernant pads, vias et caches. Ce n'est pas une exécution de toute la suite.

Vérification du chemin CLI de production sur bitaxe_ultra, un seul essai,
sans préchauffage ni harnais A/B :

```text
python gloss.py C:/Users/frant/Documents/kicad_track_gloss_stress/sources/set1/bitaxe_ultra.kicad_pcb --preview --stay-in-corridor --budget-seconds 20 --json-out .build/integrated_bitaxe_ultra.json
```

| Mesure | Résultat |
|---|---:|
| Longueur initiale | 2 126,8901 mm |
| Longueur finale | 2 071,7538 mm |
| Gain | 55,1363 mm |
| Temps moteur, G5 inclus | 9,038 s |
| Temps indiqué par la CLI | 9,044 s |
| Coût direct du certificat | 215,3 ms |
| Contrôles via / jonction | 27 / 9 |
| Refus | 3 |
| Arrêts à la limite d'intervalles | 0 |
| Validation | G5 valide, 0 régression de connectivité |
| Arrêt | Convergence, 2 passes G4, budget non atteint |

Gain et compteurs identiques à ceux du prototype complet testé sur cette carte.
Une mesure unique ne constitue pas une comparaison statistique des temps.
Carte source inchangée, SHA256 :
`267a1aa4475efa098e13af90b2f5280f69b5e9ed2fc7f71da87dccb56a8adec9`.

## Limites conservées

Le certificat démontre une déformation prescrite, avec subdivision bornée ;
il ne cherche pas tous les détours possibles. Un refus n'établit donc pas
l'absence de corridor. Les contacts intermédiaires aux zones et les nouveaux
contacts de cuivre du même net ne font pas l'objet d'une certification
topologique exhaustive. Les contrôles supplémentaires du même net précédemment
écartés ne sont pas réintroduits. Aucun DRC natif KiCad ni remplissage des zones
n'a été exécuté lors de cette vérification CLI.

KRT n'a pas été modifié. Aucun ZIP n'a été créé. Les modifications locales
préexistantes de version, packaging et affichage ne font pas partie de cette
intégration.
