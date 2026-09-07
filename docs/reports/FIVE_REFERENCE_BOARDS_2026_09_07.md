# Cinq nouvelles cartes de référence : production intégrée

Version testée : main `ed30b605a2f87880b432f49a78dbcb6d348bd87e`.
KRT : `0aff32c04fa51b4d53ecabc843b09b356aaef94b`, inchangé.
Python 3.13.2, Windows. Campagne du 7 septembre 2026.

## Sélection et protocole

Les cinq cartes ne figurent pas dans les rapports ni les résultats locaux des
campagnes précédentes de ce dépôt. Elles proviennent du corpus local existant ;
cela ne signifie pas qu'elles n'ont jamais été utilisées dans un autre projet.
Les niveaux sont des classes de charge pratiques, fondées sur le cuivre routé,
les vias et les pads, pas une mesure universelle de difficulté.

| Référence | Classe | Source dans le corpus | Segments | Vias | Pads | Couches cuivre | Nets routés éligibles |
|---|---|---|---:|---:|---:|---:|---:|
| micro_dmm | Légère | set23/micro_dmm.kicad_pcb | 167 | 19 | 101 | 4 | 29 |
| chart_plotter_hat | Moyenne | set18/chart_plotter_hat.kicad_pcb | 659 | 99 | 292 | 4 | 63 |
| environment_sensor | Moyenne | set26/environment_sensor.kicad_pcb | 863 | 144 | 325 | 4 | 52 |
| azukar_fpga | Complexe | set23/azukar_fpga.kicad_pcb | 1 813 | 200 | 630 | 2 | 142 |
| tildagon_base | Complexe | set15/tildagon_base.kicad_pcb | 4 651 | 693 | 1 203 | 4 | 164 |

Racine du corpus : `C:/Users/frant/Documents/kicad_track_gloss_stress/sources`.
Les chemins absolus et SHA256 sont conservés dans le JSON associé.
Aucun net routé exclu par la résolution du périmètre sur ces cinq cartes.

Un seul passage de production par carte, séquentiel, sans préchauffage ni
répétition, sans profilage. Le harnais existant `tools/benchmark_gloss.py`
est utilisé avec `--budget 60`. Aucun patch expérimental n'est activé.
Options Gloss par défaut : `stay_in_corridor=False`, multipasses et déplacements
activés, G3.6/Centering désactivé, grille 0,1 mm. Ce mode exerce notamment le
calcul intégré du sens utile dans la recherche générale de glissement.
Le mode corridor=True et la transaction Centering ne sont pas testés sur ces
cartes dans cette campagne ; leur couverture ici est limitée aux tests ciblés.

Le temps Gloss inclut construction du contexte, optimisations, contrôles et
validation finale lorsqu'elle est atteinte. Le chargement/configuration est
mesuré à part. Le débit est `stats.nets_processed / temps_Gloss` : c'est le
nombre de nets du périmètre par seconde, pas le nombre de nets améliorés ni
le nombre d'itérations. Sur une exécution arrêtée au budget, ce débit ne signifie
pas que tous les nets ont été optimisés jusqu'à convergence. Sur un échec, le
compteur de nets traités n'est pas retourné : le débit reste indisponible.

## Mesures

| Carte | Chargement s | Gloss s | Nets/s | Gain conservé mm | Nets modifiés | État |
|---|---:|---:|---:|---:|---:|---|
| micro_dmm | 0,053 | 0,651 | 44,53 | 7,6664 | 12 | G5 valide, convergence |
| chart_plotter_hat | 0,091 | 5,412 | 11,64 | 65,7578 | 53 | G5 valide, convergence |
| environment_sensor | 0,568 | 4,349 | 11,96 | 27,0909 | 43 | G5 valide, convergence |
| azukar_fpga | 0,311 | 22,203 | — | 0,0000 | 0 | Échec de connectivité détecté, annulation |
| tildagon_base | 0,577 | 62,587 | 2,62 | 107,3993 | 140 | G5 valide, arrêt sur budget |

Ce sont des observations uniques, sans estimation de dispersion. Ces cartes
constituent désormais un point de référence ; aucun ancien commit n'a été
exécuté sur elles. Il n'est donc pas possible d'attribuer une accélération ou
l'échec observé à une intégration précise à partir de cette campagne seule.

## Problèmes révélés

### azukar_fpga : candidat régressif rejeté

Message exact : `G3.5 connectivity regression on net 11`.
Le net 11 est `+3V3`. Le contrôle `_validate_final` de `dgloss/pipeline.py`
détecte une connectivité dégradée et l'exception déclenche la restauration.
Le journal dit `Track Gloss skipped; input preserved`, avec `gloss_errors=1`,
aucun net modifié et longueur finale égale à la longueur initiale.
Le fichier source est inchangé, vérifié par SHA256.

Le préfixe « G3.5 » est le nom du contrôle de sécurité, conservé également dans
les appels internes G4. Il n'identifie pas à lui seul la transformation fautive.
La cause géométrique exacte, l'étape qui l'a introduite et son ancienneté ne sont
pas établies sans une investigation instrumentée distincte. Cette campagne ne
relance pas la carte et n'introduit aucun correctif.

Le parseur signale aussi deux références d'empreintes kibuzzard dupliquées,
en conservant tous les blocs. Aucun lien causal avec la régression n'est démontré.
Cette carte reste dans la référence comme cas d'échec, sans la remplacer par
une carte qui passe.

### tildagon_base : budget souple dépassé

Arrêt G4 : `budget`, avec `budget_expired=True`, zéro passe G4 complète,
mais des améliorations intermédiaires conservées et certifiées. Le temps Gloss
est de 62,587 s pour un budget demandé de 60 s : dépassement de 2,587 s (4,31 %).
La validation G5 coûte 1,205 s ; elle explique une partie, pas la totalité, du
dépassement. Le budget n'est donc pas une borne stricte de latence de retour.

Principaux temps publiés par les étapes : G3 21,861 s, G4 20,729 s,
G3 local 6,537 s, réduction à longueur égale 3,530 s, G5 1,205 s.
G4 agrège ses appels internes : ne pas ajouter leurs détails une seconde fois.
Le validateur final n'est pas le coût dominant sur cette carte.

Pour les cartes moyennes, G3/G4 dominent également : 1,143/2,383 s sur
chart_plotter_hat, 0,934/1,497 s sur environment_sensor.

## Non-régression et limites

- Quatre résultats acceptés et certifiés par G5, chacun avec zéro régression
  de connectivité rapportée ; un résultat régressif détecté et annulé.
- Trois convergences, une exécution bornée par le budget, un échec.
- Aucune longueur finale augmentée ; les cinq fichiers sources sont inchangés.
- 59 tests ciblés passent en 0,74 s : sens et glissement, microsegments,
  prototype de mouvement/corridor, facade KRT, réutilisation, politique Gloss,
  corridor et transaction Centering.
- Aucun DRC natif KiCad, remplissage des zones ou validation exhaustive du
  cuivre préexistant. G5 certifie les modifications selon le modèle du projet.
- Le résultat n'est pas un « tout passe » : azukar doit être investiguée, et
  tildagon expose une limite réelle de temps de réponse sur la charge complexe.

## Référence reproductible

Données, journaux, configuration, compteurs et empreintes :
`data/five_reference_boards_2026_09_07.json`.

```text
python tools/benchmark_gloss.py <micro_dmm> <chart_plotter_hat> <environment_sensor> <azukar_fpga> <tildagon_base> --budget 60
```

Le code de sortie de la campagne est 1 à cause d'azukar, conformément au harnais.
Les comparaisons futures devront conserver ces empreintes, ces options, la
définition de nets/s et les statuts convergence/budget/échec. Aucun code de
production ou KRT modifié pendant cette campagne, aucun ZIP créé.
