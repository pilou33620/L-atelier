---
description: Audit d'une base de code decouverte (analyste + tech lead, securite si pertinent)
---

# /code-audit

Mode audit de code existant, piloté par l'`code-orchestrateur`.

## 0. Ouverture de mission

Identifiant de mission, et `list_dir` sur `.agent_reports/` pour repérer les
rapports périmés.

## 1. Choisir les agents pertinents

`code-analyst` et `code-tech-lead` sont systématiques. Ils sont indépendants et en lecture
seule : les invoquer EN PARALLÈLE dans le même tour.

- `code-analyst` -> architecture réelle, qualité, dette technique
- `code-tech-lead` -> obsolescence des dépendances et choix technologiques

N'ajouter `code-security` que si le projet a une surface d'exposition réelle : réseau,
base de données, authentification, ou traitement d'entrées non fiables. Sur un
outil local sans exposition (script de calcul, simulation, utilitaire hors
ligne), le sauter et le dire explicitement dans la synthèse. Un audit de sécurité
sur un projet sans surface d'attaque produit du bruit.

## 2. Superviser la phase parallèle

Avant de synthétiser, `manage_subagents` avec l'action `list` pour vérifier que
les agents lancés ont bien terminé. Synthétiser en croyant qu'un agent a fini
alors qu'il tourne encore produit une synthèse incomplète présentée comme
complète.

## 3. Tolérance aux échecs

Si un agent échoue, expire ou refuse, les autres continuent. Produire la synthèse
avec les rapports disponibles, en signalant lequel manque et pourquoi. Ne jamais
arrêter le workflow entier pour un agent, et ne jamais confier sa tâche à un
agent dont ce n'est pas le rôle.

## 4. Synthèse

Lire les rapports présents (`.agent_reports/code-analyst.md`, `tech-lead.md`, et
`security.md` s'il existe) avec `view_file`, croiser leurs conclusions, et
hiérarchiser les chantiers par rapport coût / bénéfice.

Ne pas recopier les rapports : y renvoyer. Signaler explicitement les points où
deux rapports se contredisent, plutôt que de trancher à leur place.

Un audit ne débouche sur aucune modification de code. Si l'utilisateur veut
corriger ce qui a été trouvé, c'est une nouvelle mission (`/code-feature` ou
`/code-bugfix`), avec un nouvel identifiant.
