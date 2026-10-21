# Gloss : quatre optimisations sans changement de KRT — 21 octobre 2026

## Diagnostic et intégration

Référence avant modification : `f587864`, copiée intégralement pour les modules
Gloss et IPC avant les éditions. La revue a confirmé quatre coûts évitables :

1. L'ouverture du dialogue avec mémoire EB importait la même carte trois fois
   (sélection, préparation, capture EB). `initial_import()` partage désormais
   un seul import pendant le `Run()` initial. Il est purgé en `finally`, avant
   la boucle événementielle. Chaque action ultérieure refait son import ;
   la double capture anti-import déchiré et les contrôles avant publication
   restent présents, y compris pour l'exécution directe sur un net.
2. La conversion des poses IPC recopiait le texte complet à chaque empreinte.
   Elle assemble maintenant les fragments dans l'ordre du fichier, puis fait
   un seul `join`. Les validations des poses et des échelles sont conservées.
3. Les pads polygonaux éloignés recevaient quand même la distance exacte.
   Leurs rectangles englobent tous les composants ; le filtre inclut la
   demi-largeur du candidat et les clearances effectives, locales et de net.
4. Chaque candidat parcourait les capsules de perçages et revalidait leur
   préparation. Les capsules produites par KRT sont désormais préparées une
   fois par adaptateur/action, puis filtrées avec leur rayon physique et
   leur clearance locale. Les oblongs et décentrages restent ceux de KRT.

Les nouveaux filtres arrondissent vers l'extérieur avec marge numérique.
Les données invalides ou trop grandes conservent le chemin de calcul complet.
L'ordre des candidats, les prédicats KRT, les passes, la connectivité, le
corridor et G5 restent inchangés. Aucun cache de cuivre mobile ni optimisation
supplémentaire de topologie n'a été ajouté.

KRT reste au commit `295f9ee197517e8323726853361eb137cc08ba9e`, version 0.23.1.
Aucune source KRT n'est modifiée. Le fichier de verrouillage non suivi
`~test_board.kicad_pcb.lck` était déjà présent avant l'intervention.

## Protocole de comparaison

`tools/measure_gloss_performance.py` lance une carte dans un processus neuf.
La référence figée et les sources courantes emploient le même Python 3.13,
les mêmes sources KRT et le même binaire officiel Windows :
`0c60ea2062a3023795db92bceae54e7f9dec0bf3b34bb86bda5908d651e18aad`.

Les cinq cartes [PACK0](../PACK0.json) sont testées avec et sans corridor,
vias mobiles et une passe G4. Le budget de 600 s sert à éviter des résultats
différents dus à une interruption temporelle ; tout budget expiré ou G5 invalide
fait échouer l'outil. Le parsing est chronométré séparément du moteur ;
l'ouverture IPC complète n'a pas pu être mesurée sur la nightly installée.
Les processus sont exécutés séquentiellement ; l'ordre avant/après
est alterné. La paire préliminaire Azukar est exclue : elle utilisait une
révision intermédiaire du code. Les trois paires retenues utilisent toutes
les mêmes sources finales.

Chaque paire compare les coordonnées exactes, nets, couches, largeurs,
diamètres, perçages et verrous des pistes/vias, ainsi que toutes les statistiques
hors chronométrage. Cette signature ne contient pas les UUID ni toutes les
métadonnées des vias ; elle prouve l'identité géométrique, pas celle de toute
leur représentation sérialisée.
Les SHA-256 des PCB, projets et règles présents sont vérifiés avant/après ;
aucun fichier d'entrée n'est enregistré par le moteur. Les empreintes des
sources, du binaire et des sorties permettent de rattacher les mesures à leur
code et à leurs entrées.

Les distances intermédiaires d'un obstacle écarté peuvent devenir infinies :
le contrat des présélections est l'identité de la décision de clearance au
seuil, vérifiée contre le chemin exact. Il ne s'agit pas de conserver la
distance à un obstacle sans influence sur cette décision.

## Résultats du moteur

**36 exécutions, 10 configurations : géométrie exacte et statistiques hors temps
identiques, G5 valide partout, aucun budget expiré.** Les entrées sont inchangées.

| Carte | Sans corridor : avant → après | Réduction | Avec corridor : avant → après | Réduction |
|---|---:|---:|---:|---:|
| micro_dmm | 0,603 → 0,560 s | 7,2 % | 0,203 → 0,190 s | 6,2 % |
| chart_plotter_hat | 5,173 → 4,530 s | 12,4 % | 3,563 → 3,114 s | 12,6 % |
| environment_sensor | 3,692 → 3,430 s | 7,1 % | 2,087 → 2,027 s | 2,9 % |
| azukar_fpga | 14,780 → 12,661 s | 14,3 % | 9,173 → 8,460 s | 7,8 % |
| tildagon_base | 43,651 → 42,607 s | 2,4 % | 26,586 → 26,298 s | 1,1 % |
| PACK0 cumulé | 67,898 → 63,787 s | 6,1 % | 41,611 → 40,089 s | 3,7 % |

Médianes de trois essais par version pour Azukar sans corridor, Chart Plotter
dans les deux modes et micro_dmm avec corridor. Les autres cases sont une
paire par version ; les petits gains, notamment sur Tildagon, demandent donc
de rester prudent. Le cumul additionne les valeurs de ce tableau. La première
paire micro_dmm avec corridor était plus lente après modification de 8 ms ;
ce ralentissement n'est pas reproduit dans les deux répétitions suivantes.

Les [données et empreintes](data/gloss_ipc_performance_2026_10_21.json) conservent
tous les temps retenus et les signatures comparées. Exemple de reproduction,
avec la référence `f587864` dans un checkout séparé et le runtime officiel :

```powershell
python tools/measure_gloss_performance.py <carte.kicad_pcb> --source-root <checkout> --runtime-root <plugins-officiels> --output <mesure.json>
```

Ajouter `--corridor` pour l'autre mode. Employer un répertoire temporaire
accessible au Python de test pour son cache du binaire KRT.

## IPC et normalisation

Le test du cycle d'ouverture confirme trois demandes d'import pour un seul
parsing et deux captures d'état. Dans le chemin nominal kicad-python 0.8,
cela ramène les requêtes d'import de 42 à 14, auxquelles s'ajoutent les trois
lectures de sélection inchangées. Les tests vérifient les imports frais au
cycle suivant, la purge après exception, l'import déchiré et le refus de
publier si carte, projet ou DRU ont changé.

La normalisation est aussi comparée avec le véritable itérateur KRT, sans
simulation du parseur :

| Cas | Médiane avant | Médiane après | Identité |
|---|---:|---:|---|
| Synthétique, 100 empreintes, 226 530 octets | 2,254 ms | 1,358 ms | Texte et 100 pads |
| Synthétique, 500 empreintes, 1 132 930 octets | 183,435 ms | 6,936 ms | Texte et 500 pads |
| Instantané réel KiCad 10.99, 31 pads | 1,776 ms | 1,632 ms | Texte et 31 pads |

Trois conversions par version ; le parsing de vérification est hors chrono.
Les synthétiques contiennent une pose transformée et un pad par empreinte,
avec 2 048 espaces par bloc. Leurs temps individuels n'ont pas été conservés ;
les trois essais individuels de l'instantané réel figurent dans les données.
Les pads réels correspondent également aux pads du fichier source.

**Limite constatée sur la nightly actuellement installée :** KiCad est maintenant
`10.99.0-5583-g6a6fb7561d`, alors que la recette du 19 octobre portait sur
`10.99.0-2520-g89476220a8`. L'import complet échoue avant et après ces changements
avec `the requested project  is not open`, pendant `Project.get_net_classes()`.
Le document IPC identifie bien le projet `board` ; le SDK kicad-python 0.8 envoie
une requête `GetNetClasses` vide, sans identifiant de projet. Le refus observé
est donc préexistant à ces quatre optimisations. Aucune adaptation de protocole
supplémentaire n'est incluse dans ce commit.

La sérialisation de la carte et la normalisation sont validées sur cette nightly,
mais le temps total d'ouverture du dialogue et l'application/Undo du Gloss
ne sont pas revalidés dessus. Aucun contournement des règles n'est utilisé.
L'instance jetable a été fermée ; sa carte n'a pas été enregistrée.

## Tests et revue

**404 tests ciblés réussis**, un `xfail` connu du prédicat de croisement KRT,
et un test de présentation PCM préexistant désélectionné : il attend
« Very based » alors que les métadonnées contiennent déjà « Based ».
Les tests de frontières du plugin et d'isolation sont exécutés séparément :
un ancien test enlève `dgloss` de `sys.modules` et perturbe sinon les tests
géométriques chargés dans le même processus.

Le bootstrap de tests sélectionne les sources courantes après l'initialisation
du runtime officiel ; les anciens imports de fixtures `kicad_parser`,
`routing_config` et `check_drc` sont liés aux modules privés KRT du même processus.
Les tests couvrent IPC, frontières, mémoire EB, architecture, régressions Fusion,
vias progressifs, corridor, clearance et filtres spatiaux.
Les 61 nouveaux cas géométriques incluent seuils nanométriques, rotations,
réflexions, composants multiples, trous oblongs et décentrés, règles locales,
géométries invalides et comparaisons aléatoires aux décisions exactes.
Une revue indépendante des changements et du protocole n'a relevé aucun défaut
de production supplémentaire.

## Livraison

Les quatre optimisations et leurs preuves sont intégrées au dépôt. L'installation
locale KiCad 10.99 du 19 octobre reste inchangée : l'incompatibilité de lecture
des classes sur la nouvelle nightly empêche une recette complète avant
redéploiement. Aucun ZIP n'est créé.

## Limites

Les résultats prouvent l'identité sur les configurations testées, pas sur
toutes les cartes possibles. Les durées dépendent du matériel, du système et
du contenu de la carte. Le budget utilisateur par défaut peut arrêter plus
tôt une recherche ; ces mesures éliminent volontairement cette variable.
G5 ne remplace pas un DRC KiCad complet. Les gains d'ouverture IPC et de calcul
Gloss concernent des phases distinctes et ne doivent pas être additionnés.
