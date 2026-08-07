---
description: Conception complete d'une carte electronique (architecte -> composants -> validation -> empreintes/calculs -> SKiDL -> ERC)
---

# /hw-carte

Mode conception de carte électronique, piloté par `hw-orchestrateur`.

## 0. Ouverture de mission

- Identifiant de mission (`AAAA-MM-JJ-slug`), annoncé.
- `list_dir` sur `data_sheets/` : quels composants sont documentés ? Un composant
  attendu sans datasheet est un risque à signaler dès maintenant.
- `list_dir` sur `.agent_reports/` : écarter explicitement les rapports périmés.
- Si la tension d'alimentation, les interfaces, les contraintes de taille ou le
  budget sont flous, `ask_question` MAINTENANT.

## 1. Architecture

Invoquer `hw-architect`. Attendre `.agent_reports/hw-architect.md` avec son
diagramme Mermaid et son bilan de puissance.

## 2. Composants

Invoquer `hw-component` sur les composants à documenter. Plusieurs composants
indépendants peuvent être traités en parallèle (mode essaim), un sous-agent par
composant. Donner à chacun la référence du composant : chacun écrit dans
`.agent_reports/hw-component-<reference>.md`, sinon les instances parallèles
s'écrasent mutuellement.

## 3. POINT DE CONTRÔLE OBLIGATOIRE

`ask_question` : lister à l'utilisateur les composants principaux retenus avec
leurs références exactes, et demander confirmation.

**Ne jamais franchir cette étape sans accord explicite.** Une erreur de composant
détectée ici coûte une question ; détectée après fabrication, elle coûte un tour
de prototypage.

## 4. Empreintes et dimensionnement

Invoquer `hw-footprint` et `hw-calculator` EN PARALLÈLE : ils sont indépendants.
Avant de continuer, `manage_subagents` (action `list`) pour vérifier qu'ils ont
tous les deux terminé.

## 5. Codage

Invoquer `hw-coder-skidl` en lui demandant de lire les quatre rapports
(architecte, composants, calculateur, empreintes).

## 6. Revue électrique

Invoquer `hw-erc-drc`.

- `APPROUVE` -> étape suivante.
- `CORRECTIONS_REQUISES` -> re-invoquer `hw-coder-skidl` sur
  `.agent_reports/hw-erc-drc.md`, puis relancer `hw-erc-drc`. **Maximum 2 tours.**
  Au troisième échec, remonter à l'utilisateur : le problème est probablement dans
  l'architecture, pas dans le code.

## 7. Documentation

Invoquer `hw-documentalist` pour le README de la carte : nomenclature, diagramme,
tableau de brochage.

## 8. Clôture

Le script vit dans `circuits/<nom-de-la-carte>.py`, et son netlist comme son
rapport ERC portent le même nom de base à côté de lui.

Résumer : composants retenus avec références, fichiers produits (script, netlist,
empreintes créées), résultat ERC, et ce qui reste à faire à la main (routage du
circuit imprimé, vérification des empreintes créées, contrôle visuel dans KiCad).
