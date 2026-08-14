---
name: cadquery-parametrique
description: >
  Règles de conception 3D paramétrique avec CadQuery : paramétrisation stricte
  sans magic number, une pièce = une fonction, sélecteurs topologiques robustes,
  gestion du centrage et de l'origine, assemblages cq.Assembly, finitions en fin
  de script. À charger avant d'écrire, modifier ou relire un script CadQuery, ou
  de concevoir une pièce mécanique ou un assemblage par le code.
---

# CadQuery paramétrique : règles de conception

Cible : CadQuery 2.x (`import cadquery as cq`).

## 1. Paramétrisation stricte

Toutes les cotes, tolérances, jeux et quantités sont regroupés en tête de
fichier (ou dans un `config.py` dédié pour un projet multi-fichiers).

- **Zéro magic number** dans la géométrie. Aucune valeur numérique brute au
  milieu d'un appel.
- Les cotes dépendantes sont des formules, pas des valeurs recopiées. Si
  `epaisseur_paroi` change, tout doit suivre sans intervention.
- Nommage `snake_case` explicite, unité implicite en millimètres :
  `diametre_axe`, `epaisseur_paroi`, `jeu_fonctionnel`, `hauteur_totale`.

Le test qui compte : modifier une seule variable en tête de fichier ne doit
jamais casser l'assemblage.

## 2. Une pièce = une fonction

Chaque pièce est isolée dans sa propre fonction qui retourne l'objet CadQuery.
L'assemblage (`.union()`, `.cut()`, `cq.Assembly`) se fait exclusivement dans la
partie principale, à la fin du script.

Dès que deux pièces s'emboîtent ou s'articulent, le jeu est une variable
paramétrique, jamais une valeur en dur.

## 3. Décomposition géométrique, dans l'ordre

1. La base : la forme primitive.
2. Les ajouts : extrusions, bossages.
3. Les soustractions : trous, poches, lumières.
4. Les détails et finitions : congés (`fillet()`), chanfreins (`chamfer()`).

Les finitions **toujours en dernier**. Un congé placé avant une soustraction
disparaît ou fait échouer l'opération suivante.

## 4. Sélecteurs topologiques robustes

**Aucun index numérique.** `faces()[3]` est interdit : l'ordre des faces change
dès que la géométrie change, et le script casse silencieusement.

Utilise les sélecteurs intégrés : `faces(">Z")` (face supérieure), `faces("<X")`
(gauche), `edges("|Z")` (arêtes verticales), `faces("%CYLINDER")`,
`faces("%PLANE")`.

## 5. Centrage et origine

Les primitives 3D (`box`, `cylinder`...) sont centrées par défaut, donc réparties
de `-hauteur/2` à `+hauteur/2`.

Utilise systématiquement `centered=(True, True, False)` pour que la base
commence à `Z=0`, et mets à jour les formules de translation en conséquence.
C'est la source n°1 de chevauchements et de décalages inexpliqués : une pièce qui
« s'enfonce de la moitié de sa hauteur » vient toujours de là.

Et si tu vois un `-0.1` sans justification dans une translation, c'est le
symptôme d'un centrage mal compris qu'on a compensé à la main : corrige la cause,
pas le symptôme.

## 6. Pas de chaînes infinies

Casse les chaînes de méthodes en variables logiques intermédiaires. Trois
opérations par ligne au maximum.

```python
base = cq.Workplane("XY").box(lg, la, h, centered=(True, True, False))
avec_poche = base.faces(">Z").workplane().rect(lg_poche, la_poche).cutBlind(-prof)
resultat = avec_poche.edges("|Z").fillet(rayon_conge)
```

Une chaîne de quinze appels est indébogable : quand elle échoue, on ne sait pas
laquelle des quinze opérations a produit l'erreur.

## 7. Assemblages

Dès deux pièces, `cq.Assembly()` est obligatoire. Chaque composant ajouté porte :

1. un nom unique (`name="..."`) ;
2. une couleur distincte (`color=cq.Color(...)`) pour l'identification visuelle ;
3. une position explicite (`loc=cq.Location(...)`) ou un alignement par
   contraintes (`constrain()` puis `solve()`).

Pour les projets complexes : sous-assemblages imbriqués (regrouper axe + pignon
+ roulement dans un sous-ensemble, puis l'ajouter à l'assemblage principal), et
répartition des pièces dans des modules distincts (`pieces/boitier.py`,
`pieces/support.py`) qui importent tous le même `config.py`.

## 8. Fin de script

Termine par `show_object(...)` UNIQUEMENT. Pas d'export STEP, sauf demande
explicite de l'utilisateur.

## 9. Vérification

Le script de contrôle du projet exécute le modèle hors cq-editor et rapporte les
erreurs réelles, la boîte englobante et le volume :

```
run_command: python .claude/scripts/cq_check.py chemin/vers/piece.py
```

Une boîte englobante très éloignée des cotes attendues, ou un volume nul,
révèlent une erreur géométrique qu'aucune relecture ne voit. C'est plus fiable
qu'une exécution mentale du code.

## 10. Limites à annoncer honnêtement

CadQuery modélise par la géométrie et les opérations booléennes. Les formes
organiques, les doubles courbures, les surfaces sculptées de style « design
produit » s'y expriment très mal.

Si la demande relève de ça, dis-le avant de commencer et propose une approche
géométrique simplifiée, plutôt que de produire trois cents lignes de
contournement fragile.
