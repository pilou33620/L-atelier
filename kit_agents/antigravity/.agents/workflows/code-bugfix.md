---
description: Cycle de correction de bug (debogueur -> codeur -> revieweur)
---

# /code-bugfix

Mode correction de bug, piloté par l'`code-orchestrateur`.

## 0. Ouverture de mission

Identifiant de mission, puis `list_dir` sur `.agent_reports/` pour écarter les
rapports périmés d'une mission précédente.

## 1. Cadrer le symptôme

Reformuler le symptôme exact et les conditions de reproduction. Si elles
manquent, les demander avec `ask_question` : un diagnostic sur un symptôme flou
produit une cause inventée.

## 2. Diagnostiquer

Invoquer `code-debugger` avec l'identifiant de mission et le symptôme. Attendre
`.agent_reports/code-debugger.md`.

## 3. Arbitrer

Lire le diagnostic. Si la cause racine reste incertaine (le rapport liste
plusieurs hypothèses), NE PAS coder : revenir à l'utilisateur avec les hypothèses
et le test qui trancherait.

## 4. Corriger

Invoquer `code-coder` en lui demandant de lire `.agent_reports/code-debugger.md` et
d'appliquer le correctif MINIMAL. Pas de refactoring opportuniste dans un bugfix.

## 5. Verrouiller la non-régression

Invoquer `code-test-writer` pour un test qui échouerait sans le correctif. Sans ça, le
bug reviendra.

## 6. Relire

Invoquer `code-reviewer`, focalisé sur le diff. Maximum 2 tours de correction.

## 7. Effets de bord

Vérifier explicitement les effets de bord listés par le `code-debugger` dans son
rapport. C'est l'étape qu'on oublie et celle qui casse la production.
