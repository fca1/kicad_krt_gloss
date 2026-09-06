# Intégration KRT : règles et évaluation des cartes de vias

6 septembre 2026 — branche `improve_gloss`.

## Modifications retenues

- `dgloss/rules.py` rassemble l'installation des canaux de règles KRT pour
  l'interface et la ligne de commande. Les valeurs CLI explicites restent
  traitées par leur chemin existant.
- L'interface utilise `DesignRules.from_pcbnew` pour les dimensions de la
  classe Default et les minimums de carte. Sa table de règles en mémoire
  remplace la table provenant du fichier après installation des canaux KRT.
  Le minimum de distance entre perçages de la carte est désormais transmis.
- La lecture des dégagements des classes effectives en mémoire est conservée :
  KRT lit encore les affectations des classes depuis les fichiers. Supprimer
  cette lecture ferait perdre certaines affectations non enregistrées.
- Le contrôle via/pad délègue la surcharge locale à
  `GridRouteConfig.pad_override_clearance`. Une surcharge remplace le
  dégagement de classe, avec le plancher de carte, conformément au contrat KRT.

Il s'agit d'une centralisation du chargement et d'une réutilisation ciblée des
règles KRT. Les contrôles de pistes et cartes d'obstacles consomment encore les
canaux historiques KRT (net, couche, piste) ; ils n'ont pas tous été migrés vers
`DesignRules.resolve`. La présence de `config.rules` ne signifie donc pas que
toutes les expressions de règles KiCad sont prises en charge par le gloss.

## Binaire Rust

Le binaire local chargé après le pull ne possédait pas l'API multi-tailles
complète (`add_blocked_vias_rung_batch` notamment). Il a été recompilé depuis
les sources KRT `0aff32c0`, avec `python KRT/build_router.py --from-source`.
Le binaire annonce 0.22.0. Aucun fichier source du sous-module n'a été modifié.
Cette compilation locale ne remplace pas les binaires d'autres installations.

## Évaluation du filtre des vias

Un outil temporaire a exécuté le benchmark sans enregistrer la carte et comparé
les réponses de la grille avec le contrôle exact, sans changer ses décisions.
Les nets dont tous les vias ont la même taille fournissaient un niveau de carte
supplémentaire. Les dimensions sans correspondance étaient comptées séparément.
L'essai ne constitue pas un certificat de sûreté du filtre.

Sur `sources/set21/ember_he.kicad_pcb`, budget 60 s, grille 0,1 mm :

- 2 géométries disponibles, 43 appels de contrôle de via ;
- les 43 candidats sont hors grille ;
- 9 réponses grille libres correspondent à des positions exactes valides ;
- 24 réponses bloquées correspondent à des positions invalides ;
- 10 réponses bloquées correspondent à des positions pourtant valides ;
- contrôles exacts : 0,036 s ; consultations de grille, incluant l'accès à la
  carte excluant le net : 0,094 s.

Le rejet direct sur cellule bloquée perdrait des candidats valides. La grille
ne remplace pas non plus les contrôles de perçages du même net. Aucun filtre
supplémentaire n'est activé en production : cette piste n'apporte pas de gain
sur la carte mesurée. Cette piste est abandonnée à la demande de l'utilisateur ;
l'outil temporaire a été supprimé. Les déplacements de vias conservent leurs
contrôles exacts.

## Vérification

Le benchmark avant modifications et recompilation donne 20,12 s au total ;
le benchmark final sans instrumentation donne 20,76 s. Mesures uniques :
elles ne démontrent ni accélération, ni équivalence temporelle stricte, et
ne permettent pas d'isoler l'effet de la recompilation Rust.

Les deux exécutions convergent, conservent exactement le gain de
43,319423 mm et passent la certification interne sans modification du fichier
d'entrée. Aucun DRC natif exhaustif n'a été lancé dans cette passe.

Les tests couvrent notamment les unités natives, le minimum entre perçages,
la conservation de la table en mémoire après les chargeurs de fichiers et les
surcharges locales de pads plus faibles que leur classe avec plancher de carte.
