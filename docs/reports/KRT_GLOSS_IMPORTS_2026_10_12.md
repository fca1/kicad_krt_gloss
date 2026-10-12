# Coexistence Gloss / KRT — 12 octobre 2026

## Cause et autorisation

Signalement Autodesk : KRT échoue après utilisation puis fermeture de Gloss,
avec « WARNING: Could not read version from Cargo.toml ». L’utilisateur a
répondu « go » à la proposition de corriger les imports et la métadonnée.

Gloss ajoutait sa copie KRT aux chemins globaux. Ses modules aux noms plats
pouvaient alors être repris par le plugin standard, même dialogue fermé.
Le packager omettait rust_router/Cargo.toml. Le contrôle réel échouait avec
installed=0.23.0, Cargo.toml=unknown ; la GUI standard ne montrait que la sortie
WARNING capturée. Les 165 sources py_router embarquées correspondent au sous-module,
mais 14 diffèrent de l’installation standard malgré le même VERSION 0.23.0.
Partager arbitrairement le moteur standard n’est donc pas une correction sûre.
La mémoire de la session utilisateur initialement en défaut n’a pas été lue.

## Correction

Les sources KRT restent intactes. isolated_krt.py les charge sous
_gloss_embedded_krt et redirige leurs imports internes, y compris différés,
par un dictionnaire builtins propre à chaque module. Une vue de sys réserve
les changements de sys.path à ce moteur ; les autres attributs restent ceux
du processus (notamment stdout et les dépendances partagées). Les chemins KRT
ne sont plus ajoutés au sys.path global. La façade dgloss/krt_api sélectionne
ce namespace après configuration ; le vérificateur de dépendances est aussi
chargé dans cet espace. Les modules standard ne sont ni supprimés ni remplacés.
Une seconde installation Gloss différente exige un redémarrage.

Le packaging inclut maintenant le Cargo.toml original du sous-module et le
chargeur. Aucun ZIP créé ; aucun binaire ni source KRT modifié. La version du
package demeure 0.1.4 ; correction locale, pas de publication.

## Vérification

- 46 tests ciblés réussis : isolation, imports différés, packages relatifs,
  ordre d’ouverture, non-repli vers une autre copie, réouverture, frontières
  du plugin et staging sans ZIP.
- Python natif D:/kicad/bin/python.exe : vrais moteurs 0.23.0 chargés dans
  les deux ordres, contrôle Cargo réussi, origine standard de route,
  startup_checks, kicad_parser et grid_router préservée.
- Dans chaque ordre, essai natif Gloss sur carte détachée test_centering2 :
  deux branches /A, 15 segments éditables, remplacement 13 → 2, gain
  37,4697 mm, G5 valide ; cuivre hors portée et SHA-256 du fichier préservés.
- La première tentative sur complete1_import ne possédait pas le net /A
  requis par cette recette ; arrêt avant exécution de Gloss, puis reprise
  sur la fixture adéquate.
- Avertissements wx de parentage/fermeture déjà connus ; pas de qualification
  interactive de l’éditeur ni de routage complet KRT ou DRC complet.

La recette reproductible tools/check_runtime_coexistence.py accepte le dossier
Gloss, le dossier KRT standard, --order gloss-first/krt-first et --board pour
exercer la recette native existante. Le staging utilise les binaires officiels
déjà installés, sans télécharger ni remplacer les extensions chargées.

## Activation

Déploiement local prévu après commit dédié, limité à runtime.py,
isolated_krt.py, dgloss/krt_api.py et KRT/rust_router/Cargo.toml. Sauvegarder
les fichiers remplacés et vérifier leur identité au commit. Redémarrage complet
de KiCad nécessaire : les anciens modules déjà chargés ne sont pas réparés à chaud.
