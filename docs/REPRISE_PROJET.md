# Reprendre Smooth Gloss KRT — branche gloss_only

## État du 12 octobre 2026

La comparaison `cube_pcb1_complete1.brd` / Fusion a conduit à trois corrections
ciblées : transitions de largeur libres sur trois segments (`width_transitions`),
reconnaissance d'un départ simple dont plusieurs extrémités touchent le même pad
et recherche de préfixes depuis ce pad, puis affinement du dernier intervalle
de glissement. Les glissements affinés vérifient aussi les coordonnées arrondies
au nanomètre afin de conserver la clearance après écriture KiCad.
Voir [diagnostic et validation](reports/GLOSS_FUSION_2026_10_12.md).

Sur `complete1` réimporté, à vias fixes et sans G4 : 8,4176 mm gagnés contre
2,6267 mm avant correction ; 655 segments contre 662. G5 valide, puis relecture
du fichier produit : 93 nouveaux segments contrôlés, aucune régression de
clearance ni de partition électrique. Le mode corridor gagne 4,0446 mm contre
0,8870 mm. 272 tests ciblés passent. Ces essais ne remplacent pas un DRC complet
et n'impliquent ni installation du plugin ni nouvelle campagne PACK0.

Les recherches sont maintenant filtrées par des bornes de gain conservatrices
(affinement de glissement et connecteurs de pad). Le graphe d'une chaîne prépare
ses directions une seule fois, réutilisées lors des rejets KRT successifs.
Sur `complete1`, géométrie strictement identique dans les trois modes testés ;
médianes mesurées : 5,46 → 3,88 s à vias fixes, 5,78 → 3,38 s à vias mobiles,
corridor pratiquement inchangé à 2,3 s. 321 tests ciblés passent.
Voir [mesures, preuves et limites](reports/GLOSS_PERFORMANCE_2026_10_12.md).

La grille KRT est désormais construite seulement à sa première utilisation,
depuis le cuivre courant ; les étapes purement exactes ne la préparent plus.
Le cache des distances aux pads conserve 32 768 entrées pour les passes G4.
Face à `44c6c16`, complete1 avec une passe G4 gagne 23,2 % sans corridor et
38,5 % avec corridor (trois essais). PACK0 conserve exactement ses résultats
dans les deux modes, G5 valide partout ; son temps cumulé baisse de 4,3 % et
16,9 % respectivement. Le seuil de 20 % n'est donc pas atteint sur tout le
corpus. 336 tests ciblés passent. Voir le
[bilan détaillé](reports/GLOSS_LAZY_OBSTACLES_2026_10_12.md).

Les petites zones reçoivent maintenant une présélection conservatrice du cuivre
avant leur construction par KRT. Les recherches de chaînes, de connecteurs de
pads et de réductions locales indexent leurs voisins du même net, avec maintien
de l'ordre et des prédicats existants. Face à `8121a1d`, azukar_fpga gagne
45,8 % sans corridor et 51,3 % avec corridor dans la série finale. Le cumul PACK0
baisse de 19,3 % et 25,8 % ; chart_plotter_hat avec corridor montre toutefois
une petite hausse de 1,5 % en médiane de trois essais. Ne pas promettre 20 %
sur chaque carte ni une absence universelle de régression temporelle.
Les 13 configurations conservent exactement leur géométrie et les statistiques
hors chronométrage, G5 valide ; 361 tests ciblés passent. Les sorties complete1
relues conservent clearance et connectivité. Voir les
[mesures et contrats des présélections](reports/GLOSS_SPATIAL_FILTERS_2026_10_12.md).

Une [nouvelle passe d'audit](reports/GLOSS_FOLLOWUP_AUDIT_2026_10_12.md) de
`4bd0eb8` reconfirme les 361 tests et les résultats des grandes cartes. Cinq
nouvelles paires sur chart_plotter_hat avec corridor ne reproduisent pas une
hausse temporelle stable : médianes 3,707 → 3,691 s. Un prototype externe de
présélection des pads polygonaux gagne 5,9 % en médiane sur azukar_fpga, avec
30 889 décisions de clearance comparées et identiques. Le prototype de
réutilisation des tableaux de cuivre ne montre pas de gain. Ces prototypes
ne sont pas intégrés ; les pads polygonaux puis les perçages fixes restent les
priorités proposées. Aucune nouvelle baisse globale de plus de 20 % n'est prouvée.

Cette branche conserve uniquement l’action Gloss. Les points d’entrée publics
sont `run_final_gloss` et `run_post_smooth_gloss`. Le moteur de placement dans
les passages, ses prototypes, réglages, commandes et visualisations ont été
retirés, ainsi que les tests et documents dédiés. Les anciennes implémentations
restent accessibles dans l’historique Git et sur la branche d’origine.

Le dialogue propose General, Gloss, Log et About, avec Gloss et Close en bas.
General conserve la liste des nets, Add/Replace/Clear, les filtres, le highlight
et la mémoire des branches élémentaires. Ces contrôles utilisent désormais
les noms `scope_*`. Le statut de sélection est affiché dans General.
Les captures de l’ancien dialogue ne décrivent plus cette branche.

KRT reste au commit `95776286`, version 0.23.0 ; aucune source KRT modifiée.
La version du package reste 0.1.4. Ne pas confondre le binaire local non suivi
`KRT/rust_router/grid_router.pyd` avec les binaires officiels téléchargés lors
de la préparation PCM. Voir [le bilan KRT](reports/KRT_UPDATE_2026_10_12.md).

La version 0.1.4 issue de `d1897cb` est maintenant déployée localement pour
les essais manuels dans
`C:/Users/frant/Documents/KiCad/10.0/3rdparty/plugins/com_github_fca1_kicadkrtgloss`.
Les 274 fichiers du paquet sont vérifiés et le chargement natif utilise le
binaire officiel Windows KRT 0.23.0. Le test natif de plusieurs branches passe,
G5 valide et carte source intacte. L'ancienne installation est sauvegardée dans
`C:/Users/frant/Documents/KiCad/plugin-backups/kicadkrtgloss-before-d1897cb-20261012-140731`.
Le registre PCM conserve son historique 0.1.3 : ce remplacement est manuel.
Les prototypes de la dernière passe restent exclus du moteur installé.
Voir [la trace de déploiement](reports/GLOSS_DEPLOYMENT_2026_10_12.md).

## Ordre de lecture

1. [AGENTS.md](../AGENTS.md) : autorisations et règles de collaboration.
2. [Spécification Gloss](../dgloss/doc_fr/gloss_rules.md), puis son
   [explication](../dgloss/doc_fr/gloss_explain.md).
3. [Architecture](ARCHITECTURE.md), [API KRT](KRT_API.md) et [PACK0](PACK0.md)
   selon la modification envisagée.

Les rapports datés conservés décrivent des expériences historiques, parfois
sur les deux anciennes actions. Ils ne définissent pas l’API de cette branche.
Leur présence ne prouve ni une intégration ni une validation actuelle.

## Contrats à préserver

KRT est l’autorité pour les obstacles, distances, clearances et validations
électriques. `dgloss/krt_api.py` isole ses imports ; `kicad_bridge.py` isole les
accès natifs KiCad. Les stratégies géométriques restent invariantes par rotation
et réflexion, sans privilège horizontal, vertical ou diagonal.

Le Gloss réduit et simplifie le cuivre existant. Les protections, exclusions,
largeurs, couches, connectivité et périmètre modifiable restent applicables.
La réduction locale progresse depuis un pad dans un seul sens. Elle peut créer
un coude si cela réduit la longueur ; l’autogloss réexamine les chaînes complètes.

`Stay in corridor` est désactivé par défaut. S’il est activé, tout mouvement
exige une déformation continue admissible, pas seulement une arrivée libre.
Les balayages utilisent la largeur physique des pistes et les capsules des vias.
Un refus de certificat ne prouve pas l’impossibilité de tous les contournements.

Un via mobile et ses segments incidents sont traités ensemble. L’arrêt sur un
pad exige l’absorption effective jusqu’au pad terminal sur la couche concernée,
avec la demi-largeur du segment. Aucun verrou permanent n’est écrit sur la carte.

Une transition de largeur sans pad, via ni ramification peut absorber le segment
voisin s'il partage l'une des deux largeurs. Les deux supports extérieurs et
leurs largeurs sont conservés ; la proposition exige une réduction utile,
une certification de mouvement continu aux deux largeurs et la garde électrique.
Cette famille conservatrice reste certifiée même avec le corridor désactivé.

G4 reste distinct du budget initial de 20 secondes : le dialogue autorise de
1 à 10 passes supplémentaires (1 par défaut). Arrêt si le gain incrémental est
inférieur ou égal à 10 % du gain incrémental précédent ; un gain précédent nul
ne déclenche pas ce ratio. Aucune transformation arrête les passes.
Le seuil reste interne. Le budget initial n’est pas un plafond total.

Le CLI traite exclusivement des nets entiers : ne pas exposer de réglage EB,
branches ou graines, ni le nombre de passes G4. `--stay-in-corridor` reste public.
Le README public reste en anglais, court et consacré au plugin.

## Sélection et application native

Add/Replace mémorise les branches par net ; seuls les nets cochés sont traités.
Sans mémoire, le net est entier. Une couverture exacte et vérifiée de tout le
net devient une portée entière. Des références périmées imposent une nouvelle
importation, sans élargissement silencieux. Chaque action repart de la carte
courante. Le clic prévisualise la portée ; la coche définit la portée d’action.

Le highlight utilise les UUID et `SetBrightened`/`ClearBrightened` derrière
`native_branch_selection.py`. Aucun timer ni clic simulé dans le dialogue.
General garde ses deux colonnes, la liste remplit son conteneur et EB reste
compacte (50 DIP). La fenêtre est détachée et fermée avec l’éditeur.

Les remplacements passent par `GlossContext.apply_replacement`. Les caches
suivent le cuivre précis ; les références électriques sont réutilisables seulement
pour les nets inchangés sans zone. Toute mutation invalide les références des
nets avec zones. Restaurer le cuivre exige aussi d’invalider les données dérivées.
G5 reste recalculé et obligatoire. Les fusions KRT exigent la preuve du support
cuivre et de la connectivité avant application.

## Limites connues

- Le test adversarial de balayage d’un via à un croisement perpendiculaire reste
  xfail : le prédicat KRT peut manquer ce cas précis. Ne pas annoncer une absence
  générale d’artefacts.
- G5 n’est pas un DRC KiCad complet. Aucun nouvel essai Linux/macOS ni campagne
  complète PACK0 n’est impliqué par ce nettoyage.
- KiCad 10 peut marquer la carte modifiée après une simple ouverture d’ActionPlugin,
  même sans changement effectif ; ne pas masquer cet état par Undo ou sauvegarde.
- Une extension Rust Windows chargée est verrouillée : réutiliser le binaire si
  son SHA-256 correspond, sans copie basée sur le seul horodatage.
- Les fichiers de cartes locaux évoluent : enregistrer leur empreinte pour les
  essais et ne jamais sauvegarder les PCB sources pendant une validation.

## Validation et livraison

Après un « go », limiter les modifications au périmètre autorisé, lancer des tests
rapides et ciblés, actualiser ce guide puis faire un commit dédié. Préserver les
modifications et fichiers non suivis préexistants. Aucun ZIP sans demande explicite.

Bootstrap de tests :

```powershell
python -c "from kicad_krt_gloss.runtime import configure_krt_runtime; configure_krt_runtime(); import dgloss, pytest; raise SystemExit(pytest.main(['tests/test_architecture.py']))"
```

Le Python natif constaté est `D:/kicad/bin/python.exe`. Le contrôle
`tools/check_branch_memory_native.py CARTE --scope multiple` exerce le dialogue,
les imports, le highlight, la portée EB et le Gloss sur une carte détachée.
`python package_pcm.py --stage-only --output-dir CHEMIN_NEUF` prépare les fichiers
installables sans ZIP et télécharge les binaires officiels de la version KRT.
Le test de staging utilise des binaires factices et ne prouve pas leur exécution.

Validation du nettoyage : 164 tests ciblés réussis (moteur, architecture,
frontière native, sélection/EB, corridor, overlay, documentation et staging).
Deux essais natifs détachés réussis sur `/A` : plusieurs EB et portée entière,
G5 valide, cuivre hors portée et fichier source préservés. Les quatre onglets
restants et les polices des champs de calcul sont contrôlés. Des avertissements
wxWidgets de parentage et de fermeture restent émis ; pas de qualification
visuelle dans l’éditeur ni de nouvelle campagne de performance. Aucun ZIP créé.
