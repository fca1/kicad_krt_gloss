# Gloss : réalisation en deux étapes

6 septembre 2026 — `improve_gloss`, travail non commité.
Suite de `GLOSS_REALTIME_REVIEW.md`. Les entrées et leurs hashes sont inchangés.

## Étape 1 : données KRT, puis une carte

Réutilisation des tableaux de cuivre KRT et de leurs bornes géométriques pendant
une recherche explicitement sans mutation. La portée se termine avant toute
application de candidat, y compris sur timeout, exception ou rejet. Hors de
cette portée, la vérification de signature KRT reste inchangée.

A/B séquentiel sur **ember_he**, en désactivant seulement cette réutilisation
dans le même code pour la référence :

| État | Temps mural | Gain | Résultat |
| --- | ---: | ---: | --- |
| Sans réutilisation des tableaux | 24,80 s | 43,3194 mm | convergence, certification réussie |
| Avec réutilisation des tableaux | 23,57 s | 43,3194 mm | convergence, certification réussie |

949 préparations, 27 893 réutilisations. Gain temporel d'environ 5 %.
Cette validation a précédé les modifications de l'étape 2.

## Étape 2 : les quatre autres propositions

### Recherches inchangées

Les recherches infructueuses de raccourcis et d'approches de pads sont
mémorisées, dans un cache borné à 2048 entrées. Les événements de modification
de cuivre invalident les certificats touchés. Une modification du même net
invalide toujours ; une modification étrangère invalide si elle touche la
région de recherche ou une zone du net concerné. Les déplacements possibles
des glissements sont inclus dans les bornes de dépendance.

Seuls les échecs d'une recherche achevée sont mémorisés : jamais les résultats
partiels d'une recherche interrompue par son budget. Le cache ne réapplique pas
de géométrie, et ne supprime pas la certification finale. Les recherches de
jonctions/vias bénéficient des données/certificats KRT réutilisés, mais ne sont
pas encore entièrement mémoïsées entre passes.

### Modèles de zones

Dans **le sous-module KRT**, `ZoneFillModel.largest_component()` mémorise le
résultat sur son bitmap immuable. Une API `invalidate_copper_models()` retire
les modèles dont les empreintes de cuivre étranger peuvent avoir changé.
Elle traite ancien et nouveau cuivre, les vias sur toutes les couches et les
clearances applicables. Le modèle complet concerné est reconstruit à la demande,
pas uniquement quelques cellules : ses composants peuvent changer à distance.

Une modification du cuivre du même net n'invalide pas son propre modèle : le
constructeur KRT ne le soustrait pas du remplissage. Les caches secondaires KRT
sont invalidés en même temps. Les modifications de pads, règles ou contours
restent hors du contrat de cette API cuivre et nécessitent une remise à zéro.

### Glissements

Les certificats géométriques KRT identiques sont réutilisés dans la même portée
de cuivre immuable. Aucun pas intermédiaire du glissement n'est supprimé pour
gagner du temps. Le premier obstacle confirmé interrompt toujours la famille.
Le filtrage grille existant est conservé ; une réponse géométrique ne survit pas
à la fin de sa portée de géométrie stable.

### Interaction

`GlossSession` exécute le calcul sur une copie des listes de pistes/vias et des
caches mutables du PCB Python. L'interface dispose de Pause, Resume et Cancel.
La pause conserve la pile de recherche et les caches ; sa durée n'est pas
décomptée du budget actif. L'annulation abandonne la transaction privée.
L'application native ne se fait que dans le thread d'interface, après obtention
d'un résultat certifié. Les messages du worker sont transmis par `wx.CallAfter`.

Ce mécanisme est coopératif : un appel KRT en cours finit avant le prochain point
d'interruption. Il améliore la réactivité de l'interface, pas la garantie de
durée absolue du calcul. La reprise concerne une session en pause, pas une
sérialisation persistante après fermeture de KiCad ou expiration du budget.

## Campagne complète à convergence

Budget de recherche 60 s, grille 0,1 mm, mêmes exclusions et options que la
comparaison précédente, sans profileur. Temps muraux parse + préparation + gloss.
Mesures individuelles, pas médianes ; les variations sous la seconde ne doivent
pas être surinterprétées.

| Carte | Avant cette demande | Après les deux étapes | Gain final |
| --- | ---: | ---: | ---: |
| dispenser | 7,92 s | 7,55 s | 20,3142 mm |
| picofx_pump | 14,91 s | 13,09 s | 130,2172 mm |
| ember_he | 24,80 s | 20,36 s | 43,3194 mm |
| bitaxe_ultra | 20,36 s, arrêt sur budget | 17,86 s, convergence | 115,2939 mm |

Les quatre résultats convergent, passent la certification finale et conservent
les gains de la passe précédente. Pour bitaxe_ultra, la comparaison antérieure
est un arrêt de budget, donc pas une comparaison de temps jusqu'à convergence.

Une seconde campagne avec le budget habituel de **20 s** donne 7,53 s,
13,06 s, 19,93 s et 17,53 s respectivement : les quatre cartes convergent aussi,
avec les mêmes gains et les certifications réussies. Ember_he reste très proche
de la limite ; cette mesure ne garantit pas sa convergence sous 20 s sur une
autre exécution ou une autre machine.

| Carte | Échecs réutilisés | Invalidations de recherches | Modèles de zones invalidés* |
| --- | ---: | ---: | ---: |
| dispenser | 541 | 383 | 8 |
| picofx_pump | 174 | 377 | 0 |
| ember_he | 775 | 1246 | 10 |
| bitaxe_ultra | 1069 | 1811 | 28 |

*Compteur agrégé de nets de zones affectés par notification, pas un nombre de
zones physiques distinctes.

La passe finale sans gain d'ember_he passe d'environ **4,10 s à 1,61 s**.
La recherche de pistes reste néanmoins le premier coût : environ 9,85 s cumulées
sur ember_he, 10,91 s sur picofx_pump. Les modèles de zones désormais invalidés
ont un coût réel ; ne pas les figer pour améliorer artificiellement ce chiffre.

## Vérifications

- `python -m pytest -q tests dgloss/tests` : **156 tests réussis**.
- Contrôles KRT exécutés directement : `test_fill_model_pad_override.py`,
  `test_fill_model_netclass_483.py`, `test_plane_fill_keepout.py` : réussis.
  Certains de ces fichiers ont un `main()` et ne sont pas tous exécutés par pytest.
- Sur ember_he réelle, session en arrière-plan : pause prise en compte en
  0,196 s, pause de 0,210 s exclue du budget, reprise jusqu'à convergence avec
  43,3194 mm gagnés ; annulation d'une seconde session en 0,009 s. L'entrée
  reste inchangée. Ces latences sont des observations, pas des garanties.
- KiCad natif sur bitaxe_ultra complète : chargement, remplissage des zones,
  application en mémoire des 466 pistes retirées / 320 ajoutées et 17 vias
  déplacés, nouveau remplissage. Les **140 pads GND restent dans un seul groupe**,
  incluant C22–C25. Aucun fichier carte enregistré.
- Compilation Python et `git diff --check` réussis.

La fenêtre wx a été intégrée et compilée, mais n'a pas été manipulée visuellement
dans KiCad pendant cette passe. Un essai utilisateur Pause/Resume/Cancel dans
l'éditeur reste nécessaire. Le contrôle natif cité vise la connectivité GND,
pas un DRC natif exhaustif des quatre cartes.

Les modifications comprennent `KRT/py_router/plane_fill_model.py` dans le
sous-module : lors du futur commit, il faudra conserver cette évolution KRT
avec le dépôt principal. Aucun commit ni publication n'a été effectué.
