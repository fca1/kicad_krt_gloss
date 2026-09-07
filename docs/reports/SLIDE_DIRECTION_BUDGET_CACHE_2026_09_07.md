# Sens utile intégré ; essais indépendants du budget et du cache

Travail demandé le 7 septembre 2026. Aucun cumul des deux expériences.

## Intégration du sens utile

Commit `a5994c6` sur main. `slide_length_rate` calcule analytiquement la
variation de longueur par millimètre normal. Le parcours existant
`_reachable_segment_slides` ne consulte les clearances que dans le sens
décroissant ; une pente nulle ou une géométrie non prise en charge ne déclenche
aucun parcours. Les positions, seuils de gain et contrôles du sens utile
restent ceux de l'algorithme existant.

37 tests ciblés passent, avec couverture des huit rotations et des réflexions.
L'analyse antérieure sur 676 fenêtres d'ember avait observé les mêmes candidats
avec 691 contrôles au lieu de 4 974. Cette intégration n'active ni le moteur
local unifié ni les nouvelles recherches adaptatives en production.

## Essai A : budget par candidat

Dans le prototype uniquement, `max_candidate_probes=32` borne le nombre de
contrôles élémentaires KRT d'un candidat. Le plafond global de 512 et les
32 candidats maximum restent présents. Les 32 contrôles sont une allocation
de travail, pas 32 ms et pas un nouveau paramètre utilisateur.

Si cette allocation est épuisée, le résultat est indéterminé : le compteur
`candidate_capped` augmente, aucun déplacement n'est accepté, et un intervalle
plus petit est essayé. La borne déjà certifiée et le meilleur résultat restent
conservés. Aucun cache de fenêtres n'est activé dans cet essai.

| Carte | Prototype référence | Budget par candidat | Gain référence | Gain avec budget |
|---|---:|---:|---:|---:|
| bitaxe_ultra | 13,393 s | 9,768 s | 77,1097 mm | 72,3734 mm |
| picofx_pump | 4,432 s | 4,599 s | 96,6173 mm | 96,6173 mm |

Sur bitaxe, les sondes passent de 26 749 à 11 963, avec 226 allocations de
candidats épuisées. Le temps diminue d'environ 27 %, au prix de 4,7363 mm de
gain en moins (environ 6 %). Sur picofx, les sondes augmentent de 6 832 à
7 181, avec 49 allocations épuisées : les intervalles plus petits demandent
du travail supplémentaire sans améliorer le résultat.

Ce budget évite bien les recherches qui consommaient leur allocation entière
sur un candidat, mais 32 n'est pas démontré comme valeur optimale universelle.
Une allocation adaptée au coût et à la taille de l'intervalle serait une piste
ultérieure. Elle n'a pas été implémentée pendant cet essai.

## Essai B : cache de fenêtres infructueuses

`tools/slide_failure_cache.py` réutilise le `SearchCache` existant, ses zones
de dépendance et ses invalidations de cuivre. Une table bornée d'identités
canoniques permet de reconnaître les mêmes segments reconstruits à coordonnées
identiques. Les coordonnées ne sont pas arrondies davantage pour la clé.

La clé inclut toute la géométrie extérieure du même net, les vias, les ancrages
et la politique de recherche. C'est nécessaire parce que les changements
intermédiaires du moteur local ne sont pas encore publiés dans le contexte.
Une recherche interrompue par le temps ou un plafond de travail n'est pas
mémorisée ; les cas neutres, très peu coûteux, ne sont pas enregistrés.

Le budget par candidat reste désactivé dans cet essai. Le moteur, ses sondes
et ses seuils sont ceux du prototype de référence.

| Carte | Temps référence | Temps avec cache | Réutilisations | Sondes évitées | Surcoût mesuré du cache |
|---|---:|---:|---:|---:|---:|
| bitaxe_ultra | 13,393 s | 13,165 s | 4 | 24 | 20,1 ms |
| picofx_pump | 4,432 s | 4,452 s | 0 | 0 | 11,1 ms |

Les gains restent exactement ceux de la référence. Il ne faut pas attribuer
les 228 ms d'écart global sur bitaxe au cache : seules 24 sondes sont évitées
et le cache ajoute lui-même du travail. Les mesures uniques fluctuent.

Sur bitaxe, 387 fenêtres sont enregistrées et 60 entrées rencontrées sont
invalidées ; sur picofx, ces nombres sont 337 et 77. Des géométries sources
répétées ne constituent donc pas autant de résultats réutilisables : les
dépendances du même net, du cuivre voisin et les interruptions comptent.
Ce cache conservateur n'apporte pas de bénéfice convaincant sur les cartes
mesurées et n'est pas proposé à l'intégration en l'état.

## Protocole et état final

Un passage par carte et variante, sans préchauffage ni répétition. Gloss avec
corridor, budget de 20 s, sans Centering. Parsing exclu ; contexte et G5 inclus.
L'ordre des variantes tourne entre les cartes. Les variantes budget et cache
partagent une référence, mais ne sont jamais combinées.

Les six essais convergent, passent G5 et rapportent zéro régression de
connectivité. Les cartes sources ne sont pas écrites et leurs SHA256 sont
vérifiés. Les limites existantes sur les contacts intermédiaires restent
présentes ; aucun DRC natif KiCad ou remplissage des zones n'est exécuté.

97 tests ciblés passent après les modifications : géométrie, sens, corridors,
microsegments, politique, transaction Centering et expériences. Les nouveaux
tests couvrent notamment le repli vers un candidat plus petit, l'obstacle mince,
la reconstruction d'une fenêtre identique, les changements extérieurs locaux,
les invalidations étrangères/du même net et l'exclusion des recherches plafonnées.

Résultats locaux : `.build/slide_budget_cache_separate.json`.

```text
python tools/benchmark_slide_budget_cache.py C:/Users/frant/Documents/kicad_track_gloss_stress/sources/set1/bitaxe_ultra.kicad_pcb C:/Users/frant/Documents/kicad_track_gloss_stress/sources/set21/picofx_pump.kicad_pcb --output .build/slide_budget_cache_separate.json
```

Seul le sens utile est activé en production. Les expériences budget et cache
restent dans tools. Aucun ZIP créé, aucun push effectué.
