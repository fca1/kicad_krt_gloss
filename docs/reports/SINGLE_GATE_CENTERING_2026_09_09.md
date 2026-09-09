# Centering d'une porte isolée

## Cause et correctif

Le regroupement `_branch_door_groups` excluait les groupes d'une seule porte.
Ce filtre hérité du traitement multiporte (08992686) est devenu bloquant lorsque
la construction protégée est devenue l'entrée unique (d537c958). Une porte était
détectée, mais aucun candidat n'était généré et aucune géométrie n'était validée.
Le regroupement accepte maintenant les groupes isolés, avec le même constructeur
par supports et les mêmes validations KRT. Pas de changement KRT ni d'heuristique.
Le log distingue désormais zéro candidat généré d'un refus de géométrie.

## Reproduction native

Carte : `C:/Users/frant/Documents/kicad_track_gloss_stress/sources/set1monster/antmicro__artix_dc_scm.kicad_pcb`.
SHA256 avant/après : `59fe3412ce67a930d8b14f94e774096c012b944a7d8a0351e624774ec6f54668`.
Net entier ULPI1_DATA4, Proxi 1 mm, budget 20 s, Gloss préparatoire corridor actif.
U14.AB21 et U14.AB20 : entraxe 1 mm, pads circulaires de diamètre 0.5 mm.
Piste 0.15 mm, clearances 0.1 mm, centre Y=110.676 mm.
Avant correctif : 1 porte, 0 candidat, restauration `no_centering`.
Après : 1 porte centrée, +0.0613 mm, G5 vrai. Application sur carte détachée :
3 pistes remplacées par 3 ; réimport natif : décalage à l'axe exactement nul.
Exécution moteur observée 1718.6 ms (mesure unique, hors import et application).
Le fichier source n'est jamais sauvegardé.

## Tests

98 tests ciblés réussis, dont `test_single_gate_centering.py` qui passe par
`run_centering` avec de vraies géométries et validations KRT, sans mock moteur,
sous rotations 0°, 45°, 90°, 180°. Vérifie détection unique, regroupement,
construction, G5 et position finale sur l'axe. Les tests existants de transactions,
portes multiples, supports collinéaires, sélection EB et frontières plugin passent.
Cette validation ciblée n'est pas une campagne PACK0 ni un DRC KiCad complet.
