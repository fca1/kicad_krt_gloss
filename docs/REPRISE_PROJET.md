# Reprendre Smooth Gloss KRT — branche gloss_only

## État du 12 octobre 2026

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
