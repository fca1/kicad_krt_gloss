# Déploiement local pour essai manuel — 12 octobre 2026

Demande utilisateur : « commit, deploie pour que je teste à la main ».

Le code déployé correspond à `d1897cb04ba2cc3f470296b979f40b85e43c0282`,
version 0.1.4, avec le moteur validé jusqu'à `4bd0eb8`. KRT reste à
`9577628635e3de81d2c1fd8ac882254c0fa7d032`, version 0.23.0. Les prototypes
externes de l'audit ne font pas partie de cette installation.

Installation :
`C:/Users/frant/Documents/KiCad/10.0/3rdparty/plugins/com_github_fca1_kicadkrtgloss`.

Sauvegarde de l'installation précédente, hors des chemins de découverte KiCad :
`C:/Users/frant/Documents/KiCad/plugin-backups/kicadkrtgloss-before-d1897cb-20261012-140731`.

Le paquet est préparé par `package_pcm.py --stage-only`, sans ZIP, dans
`.build/manual-deploy-d1897cb-20261012/unpacked`. Les binaires officiels KRT
0.23.0 sont téléchargés par le packager. L'éditeur PCB est absent avant le
remplacement ; seul le gestionnaire KiCad est ouvert. Le dossier précédent
est déplacé en sauvegarde, puis le paquet complet est copié à son emplacement.
Le registre des paquets PCM reste inchangé et peut donc encore afficher son
historique 0.1.3 ; le module installé déclare 0.1.4.

Vérifications :

- Test natif `check_branch_memory_native.py --scope multiple` sur carte détachée :
  branches, Add/Replace/Clear, highlight, interface Gloss seule et périmètre
  préservés ; G5 valide, carte source inchangée. Avertissements wx préexistants.
- 274 fichiers installés identiques au staging, hors caches Python ; tous les
  modules de production `dgloss/*.py` identiques au dépôt.
- Chargement réussi avec `D:/kicad/bin/python.exe` depuis le dossier installé :
  plugin, version 0.1.4, moteur et extension Rust officiels.
- SHA-256 Windows :
  `542047fded20cde0cccefa22c2d4782e60d6b8f5a18de68ea4312205ea35771f`,
  export `lane_search` présent.

Les traces locales sont dans
`.build/manual-deploy-d1897cb-20261012/deployment-paths.json` et
`deployment-verified.json`. Aucun PCB utilisateur n'est ouvert ni sauvegardé
par le déploiement. L'essai interactif dans l'éditeur reste à faire par l'utilisateur.
