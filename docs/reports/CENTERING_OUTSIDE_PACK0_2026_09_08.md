# Centering hors PACK0 — bilan sur 4d14d3b

Proxi 2,54 mm, grille 0,1 mm, budget 20 s, tous les nets admissibles,
Gloss préparatoire avec corridor, sans G4. Aucun PCB source sauvegardé ;
empreintes vérifiées avant/après. Temps moteur hors chargement et application.

| Carte | Lecture | Temps moteur | Résultat |
| --- | --- | --- | --- |
| usb_dali | Native KiCad 10.0.6 | 5,36 s | 5 portes centrées, G5 valide, application native refusée |
| bitaxe_ultra | Parseur texte KRT | 12,77 s | 5 portes centrées, G5 valide, six alertes de clearance complémentaires à qualifier |
| usbc_power_adapter | Native | 20,04 s | Budget expiré, restauration |
| pmod_i3c_sensor | Native | 20,04 s | 8 portes traitées avant expiration, puis restauration |
| bornhack_circle_badge | Parseur texte KRT | 0,36 s | Aucune porte admissible, entrée conservée |

Le Centering seul prend 4,12 s sur usb_dali, 5,76 s sur bitaxe_ultra
et 18,35 s sur pmod_i3c_sensor. Les mesures sont ponctuelles, non des moyennes.
Les reprises diagnostiques suivantes ne sont pas agrégées à ces temps.

## Réserves confirmées

- `usbc_power_adapter`, net 33 `/USB PD/CC2` : essai ciblé terminé en
  1,28 s, G5 valide, application native réussie, mais coude à 90° en
  (87,873 ; 65,393541), B.Cu. Les propositions acceptées proviennent du
  glissement local existant, pas de la nouvelle propagation. La présence du
  coude est confirmée dans le cuivre natif ; le seul audit des directions
  individuelles ne suffit pas.
- `usb_dali`, net 60 `/USB+` : huit arcs natifs présents, net pourtant traité.
  Des fragments importés de ces arcs sont demandés en suppression comme pistes
  droites ; l'application refuse avec `Copper changed before Track Gloss apply`.
  Une pointe supplémentaire est signalée dans le résultat du Gloss préparatoire.
  L'exclusion des nets avec arcs doit être revue, sans modifier KRT.
- `bitaxe_ultra` : aucun nouveau coude détecté, mais six segments nouvellement
  représentés sont refusés par le contrôle complémentaire de clearance sur les
  nets 24, 32 et 39. Distinguer support hérité/fusion et vraie nouvelle violation
  avant de conclure ; aucune application native n'a été validée pour cette carte.

Les copies non routées fournies dans KRT ne constituaient pas des essais utiles.
La copie ancienne de splitflap_driver n'a pas fourni de pistes au parseur texte
et son essai natif n'a pas abouti ; elle est exclue du tableau de validation.
Aucun résultat positif d'installation générale ou d'absence d'artefacts n'est
revendiqué. Aucun code de production modifié pendant cette campagne.

## Sources du corpus local

Racine : `C:/Users/frant/Documents/kicad_track_gloss_stress/sources`.

| Chemin | SHA-256 |
| --- | --- |
| set23/usb_dali.kicad_pcb | 996f461ae09fada844b4b30f5f6b70e0adc2cfeaa78ddc21b7e6545e517f4bb0 |
| set1/bitaxe_ultra.kicad_pcb | 267a1aa4475efa098e13af90b2f5280f69b5e9ed2fc7f71da87dccb56a8adec9 |
| set27/usbc_power_adapter.kicad_pcb | f2ca55189e62f4f2638b7bde1058085ea6ab8bce9f7d846ca6946c1174d9c0e3 |
| set26/pmod_i3c_sensor.kicad_pcb | 46b3d94b4574a698f273c4324e7b5a5bcb1779663b037b6bdecfe43bc2017b74 |
| set24/bornhack_circle_badge.kicad_pcb | 886a8cadb81b758929fddcc6513e4dff6d96dc7c044958e27a2602a4131297ad |
