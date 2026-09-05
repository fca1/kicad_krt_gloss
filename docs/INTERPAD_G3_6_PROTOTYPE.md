# Centering M01 — premier test complet

## Périmètre

Le prototype applique les règles M01 à une seule porte d'un seul net. Il ne
modifie pas le fichier KiCad : il détecte la porte, construit la chaîne centrée
en mémoire, puis la soumet aux contrôles KRT de clearance et de connectivité.

Aucune primitive Rust KRG n'est ajoutée. Le prototype réutilise les géométries,
l'index spatial, les règles de carte et les contrôles existants de KRT.

## Carte et cas retenu

- Carte : `magic_keys.kicad_pcb`, jeu `set21`.
- Net : `Net-(A2-SD_DATA_0)` (identifiant 27).
- Couche : `B.Cu`.
- Porte : pads `SDCardReaderBreakoutBoard1.1` et
  `SDCardReaderBreakoutBoard1.12`.
- Segment concerné : `(163.068, 120.650) -> (160.274, 120.650)`.

La recherche limitée à ce net examine 23 paires de pads et trouve une seule
porte valide, traversée par cette seule piste.

## Calcul de la porte

| Mesure | Valeur |
| --- | ---: |
| Intersection actuelle | `(161.784632, 120.650000)` |
| Axe admissible pondéré | `(161.836143, 120.976237)` |
| Décalage dans la porte | `0.330279 mm` |
| Distance cuivre à cuivre | `2.025257 mm` |
| Clearance de chaque côté | `0.2 mm` |
| Largeur actuelle | `0.2 mm` |
| Largeur admissible théorique | `1.625257 mm` |

## Transformation octolinéaire

Le segment horizontal est déplacé sur l'axe de la porte. Ses deux extrémités
glissent sur les segments voisins : le premier reste vertical et le troisième
reste diagonal à 45 degrés.

Chaîne initiale :

```text
(163.068,118.110) -> (163.068,120.650)
(163.068,120.650) -> (160.274,120.650)
(160.274,120.650) -> (151.638,112.014)
```

Chaîne centrée :

```text
(163.068,118.110) -> (163.068,120.976237)
(163.068,120.976237) -> (160.600237,120.976237)
(160.600237,120.976237) -> (151.638,112.014)
```

Le nombre de segments reste égal à trois. La longueur passe de `17.547148 mm`
à `18.008517 mm`, soit une augmentation de `0.461369 mm`. Ce résultat applique
explicitement M01 : le centering peut augmenter la longueur du net et n'est pas
subordonné à la réduction de longueur.

## Validation

| Contrôle | Résultat |
| --- | --- |
| Octolinéarité des trois segments | valide |
| Clearance exacte KRT | valide |
| Connectivité KRT | valide |
| Composantes avant/après | `1 / 1` |
| Pads déconnectés avant/après | `0 / 0` |

La détection seule, répétée 30 fois sur ce net, prend `2.063 ms` en médiane
(`1.979` à `2.460 ms`). La détection et la construction du candidat prennent
environ `3.94 ms` sur le passage complet ; les validations KRT prennent environ
`1.86 ms`.

## Cas écarté pendant le test

La porte initialement envisagée sur `Net-(A1-D4)`, entre `J3.6` et `J3.7`,
n'était pas valide : une piste du net `Net-(A1-A4)` aboutit à l'intérieur de la
porte. Le premier détecteur ne comptait que les intersections internes aux
segments et ignorait cette extrémité. Le détecteur compte maintenant aussi une
piste dont une extrémité se trouve dans la porte, et un test protège ce cas.
