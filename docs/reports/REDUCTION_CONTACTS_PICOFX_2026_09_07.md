# Réduction des segments et contrôle des contacts — picofx_pump

Mesure du 7 septembre 2026 sur une carte déjà utilisée dans les rapports
G3–G5 et les revues de temps réel du projet.

## Entrée et protocole

- Carte : `C:/Users/frant/Documents/kicad_track_gloss_stress/sources/set21/picofx_pump.kicad_pcb`.
- SHA256 : `d4859e08476fe28504782f41ace60e3e16802430394b8e1dceb76de55e538328`,
  identique à celui du rapport `dgloss/GLOSS_REALTIME_REVIEW.md`.
- Entrée parsée : 347 segments, 30 vias, 222 pads, 39 nets routés,
  longueur des segments 2 243,914258 mm (hors longueur des vias).
- Grille 0,1 mm ; budget de 20 s ; réglages Gloss par défaut, multipasses,
  mouvements de vias et jonctions et optimisation des approches de pads actifs.
  `stay_in_corridor=False`, Centering désactivé.
- Un échauffement exclu, puis trois répétitions par variante, exécutées
  séquentiellement dans un ordre alterné. Chaque essai recharge le même fichier.
- Temps mural du Gloss complet, préparation du contexte et G5 compris,
  lecture/parsing exclus (environ 0,12 s). Aucun profileur. Les chronomètres
  légers du contrôle de contacts sont actifs dans les trois variantes.
- Le fichier PCB n'est jamais enregistré ; son hash est vérifié après les essais.
  KRT n'a pas été modifié.

La variante « sans réparation » désactive seulement `micro_free_candidates`
dans le code de travail actuel. Ce n'est pas une reconstruction complète d'une
ancienne révision : notamment, la conservation des identités des segments
inchangés reste active.

La variante contacts ajoute le prototype au contrôle existant de
`dgloss.algorithm._touches_other_same_net` pendant cet essai seulement. Elle
conserve ses refus et ajoute ceux de `ContactProbe`. Elle couvre les appels G3,
G3.5 et locaux passant par cette fonction ; elle ne remplace pas toutes les
validations de tous les autres modules. Aucun changement de production.

## Résultats

| Variante | Temps médian | Min–max | Gain conservé | Segments finaux | Validation |
|---|---:|---:|---:|---:|---|
| Sans réparation des microsegments | 5,535 s | 5,492–5,574 s | 0 mm | 347 | Annulation |
| Réparation active | 12,268 s | 12,162–12,411 s | 129,492204 mm | 242 | G5 valide |
| Réparation + contacts expérimentaux | 12,877 s | 12,846–12,938 s | 121,468265 mm | 243 | G5 valide |

Les gains et nombres de segments sont identiques sur les trois répétitions
de chaque variante. Les deux variantes valides convergent après cinq passes
G4, avant l'expiration du budget. Les 30 vias sont conservés en nombre.

Sans réparation, le message final est
`G3.5 produced a micro-segment` : le pipeline restaure l'entrée.
Son temps plus court est donc celui d'un échec, pas celui d'un nettoyage réussi.
Les 129,492204 mm sont le gain total du Gloss rendu possible par la réparation,
et non le gain directement attribuable aux seuls microsegments.

Le prototype ajoute **0,609 s, soit 4,97 %**, au temps mural médian et réduit
le gain de **8,023939 mm**. Les longueurs finales sont respectivement
2 114,422054 mm et 2 122,445993 mm.

## Coût du prototype

Sur chacune des trois exécutions avec contacts :

- 14 407 appels au contrôle instrumenté ;
- 807 constructions d'index spatial KRT ;
- 4 255 évaluations exactes de distances entre segments par KRT ;
- 211 propositions refusées en supplément (pas 211 défauts distincts).

Temps médians cumulés : contrôle initial 89 ms ; construction/vérification de
réutilisation de l'index 34 ms ; requêtes du prototype 957 ms. L'index utilise
les cellules KRT élargies pour couvrir les largeurs du cuivre et les limites de
cellules ; les distances exactes ne sont calculées que pour les voisins retenus.
Il n'y a pas de comparaison exacte systématique de toutes les paires de pistes.

Le coût direct supplémentaire est proche de 0,99 s. Le surcoût du Gloss entier
est plus faible car les refus changent la recherche et les géométries ultérieures ;
le nombre de requêtes passe notamment de 14 866 à 14 407. Ces deux mesures ne
doivent pas être confondues.

## Conclusion et limite

La correction des microsegments débloque cette carte réelle. Le contrôle
supplémentaire conserve un temps voisin de 13 s, sous le budget de 20 s, sur
cette machine et cette carte. Il ne rend pas le traitement instantané.

Le prototype reste expérimental : les 211 refus n'ont pas tous été classés en
contacts nouveaux ou contacts préexistants acceptables. Il ne dispose pas d'un
certificat complet de conservation des contacts initiaux. La baisse du gain ne
prouve donc pas que les 8,02 mm correspondaient exclusivement à des raccourcis
incorrects. G5 vérifie le résultat conservé, pas l'optimalité ni la pertinence de
chaque refus. Aucun DRC natif KiCad avec remplissage des zones n'a été exécuté.

## Reproduction

```powershell
python tools/benchmark_reduction_contacts.py C:/Users/frant/Documents/kicad_track_gloss_stress/sources/set21/picofx_pump.kicad_pcb --output .build/reduction_contacts_picofx.json --budget 20 --repeats 3
```

Le script nécessite le répertoire de travail actuel, notamment
`dgloss/local_gloss.py`, déjà non suivi avant ces essais. Les résultats détaillés,
réglages, journaux et échantillons de refus sont dans
`.build/reduction_contacts_picofx.json`. L'essai préliminaire sur ice4pi a été
interrompu à la demande de l'utilisateur et n'entre pas dans ces résultats.
