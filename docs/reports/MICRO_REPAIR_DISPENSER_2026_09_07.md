# Réparation des microsegments — dispenser — 7 septembre 2026

Le contrôle supplémentaire des contacts est mis de côté. Seul le correctif
des microsegments est activé/désactivé pour cette comparaison.

## Carte et protocole

Carte connue des rapports G3–G5 du projet :
`C:/Users/frant/Documents/KiCad/10.0/projects/dispenser/dispenser.kicad_pcb`.

SHA256 avant/après :
`2b5ae5932e9823558456684c43a00cb78bf99458f843e54fa5760040aba729a0`.
Il correspond à l'entrée documentée dans `dgloss/GLOSS_REALTIME_REVIEW.md`.

Entrée : 440 segments, 76 vias, 292 pads, 31 nets routés. Le Gloss en traite
30 ; le net 9 est exclu par la protection existante. Longueur initiale des
segments : 1 042,794108 mm, hors longueur verticale des vias.

- Trois répétitions par variante, ordre alterné, après un échauffement exclu.
- Même fichier rechargé avant chaque essai ; aucune sauvegarde du PCB.
- Grille 0,1 mm, budget 20 s, réglages Gloss par défaut et multipasses actives.
- `stay_in_corridor=False`, Centering désactivé.
- Temps mural du Gloss complet, préparation du contexte et G5 compris ;
  lecture/parsing exclus (environ 0,060 s). Aucun profileur.
- Aucune construction ni requête du prototype de contacts dans ces essais.
  Les contrôles habituels KRT et du Gloss restent actifs.

La variante sans réparation désactive uniquement `micro_free_candidates` dans
le répertoire de travail actuel. Elle n'est pas une ancienne révision complète :
la préservation des identités des segments inchangés reste active.

## Résultats

| Variante | Temps médian | Min–max | Gain conservé | Segments finaux | Résultat |
|---|---:|---:|---:|---:|---|
| Sans réparation | 4,155 s | 4,121–4,156 s | 0 mm | 440 | Annulation |
| Réparation seule | 7,781 s | 7,726–7,800 s | 20,429209 mm | 361 | G5 valide |

Les trois exécutions corrigées donnent les mêmes gains et nombres de segments,
convergent après quatre passes G4 et rapportent zéro régression de connectivité.
La longueur finale est 1 022,364899 mm : réduction de 79 segments et d'environ
1,96 % de la longueur initiale. Le nombre de vias reste 76 ; les mouvements de
vias permis par les réglages par défaut restent actifs.

Les trois exécutions sans réparation échouent avec
`G3.5 produced a micro-segment`, puis restaurent l'entrée. Leur durée plus courte
ne mesure donc pas un nettoyage réussi et ne permet pas de calculer le surcoût
propre du correctif. Les 20,429209 mm représentent le gain global du Gloss rendu
possible par la correction, pas celui des seuls microsegments.

## Conclusion

Le résultat sur cette seconde carte connue confirme celui de picofx_pump :
la réparation évite l'annulation du nettoyage, sans contrôle supplémentaire des
contacts. Le Gloss complet termine ici en environ 7,8 s sous le budget de 20 s.
Ce temps vaut pour cette carte et cette machine ; ce n'est pas une garantie
universelle de latence. La validation est celle de KRT/G5, sans DRC natif KiCad
avec remplissage des zones. KRT et la carte source sont inchangés.

## Reproduction

```powershell
python tools/benchmark_reduction_contacts.py C:/Users/frant/Documents/KiCad/10.0/projects/dispenser/dispenser.kicad_pcb --output .build/micro_repair_dispenser.json --budget 20 --repeats 3 --modes without_repair repair
```

Résultats détaillés et journaux : `.build/micro_repair_dispenser.json`.
Le script utilise le répertoire de travail actuel, notamment le fichier
`dgloss/local_gloss.py`, déjà non suivi avant les travaux de cette conversation.
