# Recette IPC : barre d'outils, zones et DRC — 21 octobre 2026

La recette complémentaire passe sur **KiCad 10.99.0-5583-g6a6fb7561d**,
avec le plugin installé au commit `8572919`. Aucun code de production,
aucun réglage du moteur et aucun fichier KRT n'ont été modifiés.

## Périmètre et références

Le RAG `kicad` a été consulté en premier : sections complètes pertinentes de
[la CLI nightly](https://docs.kicad.org/master/en/cli/cli.html#pcb) et de
[Board SDK 0.8](https://docs.kicad.org/kicad-python-0.8.0/board.html), indexées
le 16 octobre. L'aide du CLI réellement installé et le SDK local ont complété
ces instantanés. Le format des constats a été vérifié dans le
[rapport DRC de la nightly exacte](https://gitlab.com/kicad/code/kicad/-/blob/6a6fb7561d7d35f3a2324326f22d19c01c9f7462/pcbnew/drc/drc_report.cpp#L143)
et le [schéma JSON officiel](https://schemas.kicad.org/drc.v1.json).

La carte de contrôle synthétique est conservée dans
`tests/fixtures/ipc_zones/` : contour fermé de 40 × 30 mm, un connecteur avec
quatre pads, net `/A` en trois pistes de 34,1421 mm, deux pads traversants GND,
deux zones GND F.Cu/B.Cu. Une bibliothèque locale évite les dépendances externes.
Le fichier a été généré avec KiCad 10.0.7 ; **l'application, les remplissages
et tous les DRC de cette recette sont exécutés avec KiCad 10.99-5583**.

L'éditeur ne travaille que sur la copie `.build/ipc-final-acceptance/fixture/`.
Configuration et socket sont isolés ; le chemin complet du document est
vérifié au début des séquences IPC, qui conservent ensuite cet objet document.
Le PCB source reste inchangé, SHA256
`fd0e485ac692938572b2343c3fb7a5787dd0ebbdf55f239eb8cb1d933a007384`.

## Lancement réel par la barre d'outils

Le bouton a été cliqué dans la barre de PCB Editor avec la compétence
[computer-use](C:/Users/frant/.codex/plugins/cache/openai-bundled/computer-use/26.1013.40934/skills/computer-use/SKILL.md).
Les premiers clics de contrôle utilisaient le bouton secondaire : le réglage
Windows `SwapMouseButtons=1` a été constaté en lecture seule. Employer le
bouton principal configuré a ouvert le dialogue ; aucun réglage système changé.

La filiation des processus confirme le lancement par `pcbnew.exe` du Python
de `AppData/Local/KiCad/10.99/python-environments/com.github.fca1.kicadkrtgloss`,
avec le point d'entrée installé
`Documents/KiCad/10.99/plugins/com.github.fca1.kicadkrtgloss/ipc_entry.py`.
L'entrée n'a pas été appelée directement par le script de recette.

Dans le dialogue ouvert, `/A` a été coché, puis le bouton Gloss activé.
Le dialogue de progression et le journal ont été observés. Résultat :
**3 pistes → 1, 34,1421 → 30,0000 mm, gain 4,1421 mm, G5 valide**.

## Preuve du remplissage effectué par le plugin

1. Les deux zones initialement vides sont remplies par IPC pour constituer
   la référence. Leurs polygones non vides deviennent stables ; le DRC de
   cet instantané ne signale aucun défaut ni connexion manquante.
2. Un Undo annule ce seul remplissage initial. Avant le clic Gloss, les deux
   zones ont `filled=false` et zéro polygone ; tous les UUID et propriétés
   des pistes restent identiques à la référence.
3. Gloss est lancé depuis le dialogue natif. Après son application, sans
   autre demande de remplissage, les deux zones ont `filled=true` et un
   polygone chacune, observés stables sur trois lectures successives.
4. L'état réel est exporté par `get_as_string`, sans sauvegarder le document.
   Les projets copiés avec chaque export sont identiques et la bibliothèque
   locale reste disponible. Le premier DRC après Gloss ne remplit rien.

Ce témoin zéro → deux polygones prouve le remplissage par le parcours du
plugin ; le simple accusé IPC ne constituait pas cette preuve. La zone F.Cu
est hors du trajet raccourci et la seconde zone est sur B.Cu : leurs géométries finales retrouvent
les empreintes de la référence. Ce cas ne démontre pas tous les cas possibles
de dégagement autour de pistes déplacées au sein d'un plan.

## DRC avant/après

Même exécutable, mêmes règles et options :

```text
kicad-cli pcb drc --format json --units mm --severity-all --all-track-errors --exit-code-violations -o RAPPORT CARTE
```

| État contrôlé | Remplissage supplémentaire par le CLI | Violations | Connexions manquantes | Code retour |
|---|---|---:|---:|---:|
| Référence avant Gloss | Non | 0 | 0 | 0 |
| État réellement appliqué par Gloss | Non | 0 | 0 | 0 |
| Vérification indépendante après Gloss | Oui, `--refill-zones` | 0 | 0 | 0 |

Aucun `--save-board` utilisé. Le second contrôle après Gloss vérifie que le
remplissage indépendant ne révèle pas de défaut ; il ne remplace pas le
contrôle sans remplissage qui précède.

Les cinq contrôles ignorés par défaut par KiCad sont identiques dans les
trois rapports : `missing_courtyard`, `track_not_centered_on_via`,
`tuning_profile_track_geometries`, `footprint_filters_mismatch` et
`footprint_type_mismatch`. Aucune exclusion ou désactivation spécifique n'a
été ajoutée pour obtenir ce résultat. La fixture n'a pas de schéma ; aucune
vérification de parité schéma/PCB n'est revendiquée.

`tools/check_ipc_drc.py` compare les trois rubriques de constats, les positions,
descriptions, types, sévérités, exclusions et multiplicités. Il ignore les UUID
de tous les objets cités dans les constats, afin de tolérer le remplacement
des pistes, et refuse un changement de version déclarée, unités ou
filtres. **18 tests ciblés passent** ; revue indépendante sans défaut identifié.
Les données et rapports bruts sont conservés dans
[le relevé JSON](data/ipc_toolbar_zones_drc_2026_10_21.json).

## Limite confirmée : Undo avec remplissage

Le remplissage automatique de cette nightly crée une transaction native
supplémentaire. **Deux Undo** sont nécessaires dans ce cas : le premier
retire les polygones de zones mais laisse la piste raccourcie ; le second
restaure exactement les trois pistes d'origine, avec leurs UUID/propriétés.
La garantie d'un seul Undo du rapport précédent ne s'appliquait qu'aux
recettes sans remplissage de zones. La documentation est corrigée en ce sens.
Le moteur et l'installation exécutable restent inchangés.

## Défaut constaté lors de la fermeture

Close fait disparaître le dialogue, mais les PID Python 46824 et 47664 restent
actifs, y compris après l'arrêt de l'éditeur de test. Leur filiation et leur
ligne de commande ont été revérifiées avant leur arrêt ciblé ; aucune autre
instance n'est concernée.

Le code explique ce comportement : `settings_dialog.py` appelle `self.Close()`,
le handler `action_plugin.py:on_dialog_close` laisse le traitement wx continuer
avec `event.Skip()` sans `Destroy()`, et le dialogue est affiché avec `Show()`.
Le [traitement wx par défaut d'un dialogue non modal](https://docs.wxpython.org/window_deletion_overview.html#default-window-close-behaviour)
le masque sans le détruire. `ipc_entry.py` reste donc dans `app.MainLoop()` ;
la fermeture du dialogue ne libère pas automatiquement le processus externe.
La pile exacte des deux PID n'a pas été inspectée. Ce défaut préexistant de
cycle de vie est consigné ; aucune correction de production n'est intégrée
dans cette recette.

La recette valide donc le bouton natif, le remplissage et le DRC sur cette
petite carte de contrôle. Elle ne constitue pas une garantie universelle sur
toutes les cartes ni sur d'autres builds. Les limites DRU/KRT documentées
restent applicables. Les processus de test ont été arrêtés sans sauvegarde du PCB.
