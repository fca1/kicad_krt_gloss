# PACK0 — cartes de référence

PACK0 désigne durablement les cinq cartes retenues le 7 septembre 2026 pour
les mesures de temps et les contrôles de non-régression de Smooth Gloss KRT.
Toute demande de test sur « PACK0 » se rapporte à cette liste, dans cet ordre.

| Carte | Classe | Chemin relatif dans le corpus |
|---|---|---|
| micro_dmm | Légère | set23/micro_dmm.kicad_pcb |
| chart_plotter_hat | Moyenne | set18/chart_plotter_hat.kicad_pcb |
| environment_sensor | Moyenne | set26/environment_sensor.kicad_pcb |
| azukar_fpga | Complexe | set23/azukar_fpga.kicad_pcb |
| tildagon_base | Complexe | set15/tildagon_base.kicad_pcb |

Racine locale du corpus :
`C:/Users/frant/Documents/kicad_track_gloss_stress/sources`.
Le [manifeste PACK0](PACK0.json) conserve les chemins relatifs et les SHA256
des cartes originales. Vérifier les empreintes avant une comparaison ; une
carte modifiée ne doit pas remplacer silencieusement la référence.

Protocole initial : un passage par carte, sans répétition ni préchauffage,
Gloss de production, grille 0,1 mm, `stay_in_corridor=False`, budget 60 s,
sans Centering et sans écriture des PCB. Mesurer le chargement séparément ;
`nets/s = nets_processed / temps_Gloss`, contexte et validation finale inclus.
Signaler toute variation de configuration pour les campagnes ultérieures.

Conserver les cinq cartes même en cas d'échec : azukar_fpga expose une
régression de connectivité détectée et annulée sur le net 11 (+3V3) ;
tildagon_base atteint le budget sans convergence lors de la campagne initiale.
Ce sont des cas de référence, pas des critères autorisant à ignorer ces défauts.

- [Rapport initial](reports/FIVE_REFERENCE_BOARDS_2026_09_07.md)
- [Mesures et journaux initiaux](reports/data/five_reference_boards_2026_09_07.json)
