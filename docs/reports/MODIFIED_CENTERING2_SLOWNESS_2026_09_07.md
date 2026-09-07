# test_centering2 modifié : diagnostic de lenteur — 7 septembre 2026

## Source et périmètre

Fichier sauvegardé : `C:/Users/frant/Downloads/kicad_centering/test_centering1/test_centering2.kicad_pcb`.
SHA256 actuel : 8556b99dd650bc1e5db02582fed0de45d391357d2b2dee6080d81137770370c4.
Ancien SHA256 : 0477f2aa2d7e5a3e4954f155f9fb3ec301162ae53493b0a10f34892b51f5ce6b.
La version modifiée a bien été chargée, sans écriture du fichier source.

La configuration exacte de l'action lente dans l'interface a été demandée ;
aucune réponse n'était disponible à la rédaction. Les essais ci-dessous couvrent
/B seul, les quatre nets routés, le corridor, G4 et un Centering à proximité 1 mm.
Ils ne capturent pas l'état non sauvegardé d'une fenêtre KiCad, sa sélection de
segments ni ses réglages courants.

## Le calcul seul ne reproduit pas une très longue attente

| Essai sur le fichier modifié | Temps observé |
|---|---:|
| B, production, sans corridor, G4 off, confirmation comprise | 0,152 s |
| B, prototype, sans corridor, G4 off, confirmation comprise | 0,148 s |
| B, production, corridor, G4 off, confirmation comprise | 0,392 s |
| B, prototype, corridor, G4 off, confirmation comprise | 0,375 s |
| Toute la carte, prototype, sans corridor, G4 off | 0,539 s |
| Toute la carte, prototype, corridor, G4 on | 0,781 s |
| Toute la carte, Gloss + Centering, proximité 1 mm | 0,691 s |

Le dernier essai annule la transaction pour `no_centering` et conserve l'entrée :
il ne doit pas être présenté comme un Centering effectué/certifié. Les autres
résultats passent G5. Sur B, toutes les variantes économisent 106,4690 mm et
atteignent une signature stable après un appel productif et une confirmation.
Le chargement textuel de la carte coûte environ 0,010 s.

Toute carte, corridor + G4 : G3 0,276 s, approches de pads G3.2 0,272 s,
vias G3.1 0,008 s, raffinements G3.4 0,042 s, confirmation G4 0,110 s.
Les vias ne dominent donc pas ces durées algorithmiques.

## Blocage reproduit avec le ZIP dans le runtime natif de KiCad

Test sous **KiCad 10.0.5**, avec `D:/kicad/bin/python.exe`, à partir du ZIP livré
`KiCadKrtGloss-0.1.3-prototype-via-fc23d42.zip`, extrait dans un dossier de diagnostic.
La carte est chargée par `pcbnew.LoadBoard` en mémoire indépendante, puis exportée
par l'adaptateur KRT. L'application de la géométrie vise uniquement cette copie
native en mémoire, jamais la carte ouverte par l'utilisateur ni le fichier.

`apply_gloss` indexe les vias natifs à l'aide de `_native_via_key`. Cette fonction
appelle `via.GetWidth()` **sans préciser de couche**, à la ligne115 de
`kicad_krt_gloss/board_adapter.py`. Le runtime émet :

    PCB_VIA::GetWidth called without a layer argument

L'appel déclenche une assertion native et le processus ne rend pas la main.
Le processus de diagnostic a été interrompu. Il ne s'agit pas d'un temps de
recherche mesuré ni d'un simple coût supplémentaire de calcul. L'interface
peut présenter/attendre une assertion ; l'état exact de la fenêtre utilisateur
n'a pas été observé, donc l'identité avec son symptôme reste à confirmer.

Une première tentative native a aussi révélé une erreur d'import relatif propre
au script de test ; elle a été corrigée dans ce script avant le diagnostic natif
ci-dessus et ne concerne pas le plugin installé.

## Contre-expérience isolée

Le script de diagnostic remplace uniquement cet appel par
`via.GetWidth(pcbnew.F_Cu)` **dans son processus**, sans toucher au plugin ou au ZIP.
Cette substitution supprime l'assertion sur la carte testée. Elle sert à isoler
la cause, pas à définir le correctif général des padstacks de vias.

Sous profileur, le même chemin complet donne :

| Phase native | Temps |
|---|---:|
| Charger la carte | 0,0086 s |
| Exporter vers les données KRT | 0,0092 s |
| Construire la configuration native | 0,0090 s |
| Gloss, corridor + G4 | 1,2746 s |
| Appliquer le cuivre, visualisation et reconstruction natives | 0,0107 s |

G5 est valide. Ces temps incluent le coût du profileur : ne pas les comparer
comme un benchmark direct aux mesures non instrumentées ci-dessus.
Le profileur localise notamment 0,665 s cumulée dans les contrôles de segments
et 0,625 s dans les certificats de corridor ; ces temps se recouvrent et ne
s'additionnent pas. Les calculs d'approche de pads occupent également une part
notable. Rien ici n'explique une attente très prolongée pendant le calcul.

## Conclusion

Un **blocage reproductible dans l'adaptateur KiCad après le calcul** a été trouvé.
Il est un candidat concret pour expliquer la lenteur ressentie, surtout si elle
survient après les lignes de validation/finalisation dans le journal. Le problème
existe dans l'adaptateur partagé avec la production, pas seulement dans le moteur
du prototype via ; la présence d'un via suffit à atteindre cet appel.

Le correctif à préparer concerne la lecture du diamètre natif du via avec l'API
KiCad appropriée, cohérente avec l'import KRT et les couches de son padstack.
Il ne faut ni masquer les assertions ni changer les algorithmes géométriques
pour contourner ce problème. L'appel F.Cu n'est démontré ici que comme diagnostic.

Aucun correctif de production et aucun nouveau ZIP pendant cette analyse.
Les mesures ne permettent pas d'exclure un autre coût lié à une configuration ou
à un état non sauvegardé différent de ceux testés. Les scripts et les profils
sont conservés pour reproduire le diagnostic.


## Correctif appliqué et re-test demandé

`_native_via_key` utilise maintenant `GetFrontWidth()` en priorité, comme
l'importeur KRT, puis `GetWidth()` en repli pour les anciennes liaisons natives.
KRT est inchangé. Aucun appel F.Cu forcé ou masquage d'assertion n'est utilisé.
Le test unitaire couvre un via moderne dont `GetWidth()` interdit l'appel, ainsi
que le cas ancien ne proposant pas `GetFrontWidth()`. 46 tests ciblés passent.

Le package expérimental a été extrait dans un autre dossier de diagnostic et
son adaptateur remplacé par le fichier corrigé, sans modifier le ZIP livré.
Test natif complet sous KiCad 10.0.5, sur la même carte modifiée, quatre nets,
corridor et G4 activés, sans profileur et sans substitution de fonction :

| Phase | Temps |
|---|---:|
| Chargement natif | 0,0209 s |
| Export KRT | 0,0056 s |
| Configuration | 0,0412 s |
| Gloss et validation | 0,9201 s |
| Application native, visualisation et reconstruction | 0,0233 s |

Total des phases : environ 1,01 s, hors démarrage Python/imports. G5 valide,
112,2373 mm économisés, aucune assertion et aucun blocage. Le fichier source
est resté inchangé ; les mutations natives visent seulement la copie chargée
en mémoire. Le résultat ne doit pas être interprété comme une mesure de toute
la latence de l'interface utilisateur.

Le correctif est dans le dépôt. Le ZIP antérieur reste inchangé et doit être
régénéré pour distribuer cette correction à l'installation KiCad.
