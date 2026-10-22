# Fixture IPC avec zones

Copier ce dossier dans un répertoire de test avant de l'ouvrir dans KiCad.
Ne pas enregistrer d'essai dans cette fixture de référence.

`zones.kicad_pcb` contient un contour de 40 × 30 mm, trois pistes `/A`, quatre
pads et deux zones GND non remplies. `zones.kicad_pro` fournit les minima et
la classe Default ; `fp-lib-table` et `Acceptance.pretty` sont nécessaires
pour vérifier la bibliothèque locale. Conserver ces fichiers ensemble.

Génération de fichier : KiCad 10.0.7. Recette réelle : KiCad
10.99.0-5583-g6a6fb7561d, IPC et DRC sans SWIG. Avant Gloss, remplir les zones
pour le DRC de référence. Pour prouver le remplissage du plugin, annuler ce
remplissage et vérifier zéro polygone avant Gloss ; `/A` se réduit de trois
pistes (34,1421 mm) à une (30 mm). Les deux zones doivent ensuite être remplies.
Exporter l'état réel et faire son DRC sans remplissage supplémentaire.

La zone F.Cu reste hors du trajet modifié ; la seconde zone est sur B.Cu. Ce témoin prouve
la demande et l'exécution du remplissage, pas tous les cas de dégagement
autour de pistes déplacées dans un plan. Le projet n'a pas de schéma.

Voir `docs/reports/IPC_TOOLBAR_ZONES_DRC_2026_10_21.md` pour les résultats,
les filtres DRC par défaut et la limite des deux Undo avec zones remplies.
