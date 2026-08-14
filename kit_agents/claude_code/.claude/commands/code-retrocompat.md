---
description: Verification que les ajouts recents sont repercutes partout
---

**Demande / Objectif :** $ARGUMENTS

# /code-retrocompat

Mode vérification de cohérence, à lancer après l'ajout d'un champ, d'un paramètre
ou d'une clé de configuration.

## 0. Ouverture de mission

Identifiant de mission, et `list_dir` sur `.agent_reports/`.

## 1. Déléguer l'inventaire

Invoquer `code-consistency-checker` avec l'identifiant de mission. S'il connaît déjà
la liste des nouvelles définitions (parce qu'un `code-architect` ou un `code-coder` vient
de travailler dessus), la lui transmettre dans le prompt. Sinon, il l'établit
lui-même à partir de `git diff` : il a l'accès git en lecture pour ça.

Ne pas essayer de lancer `git diff` depuis l'orchestrateur, il n'exécute aucune
commande.

## 2. Lire le résultat

Lire `.agent_reports/code-consistency-checker.md`. S'il a terminé par
`RIEN_A_SIGNALER`, la mission s'arrête là et c'est un bon résultat : le dire sans
chercher à produire du travail.

## 3. Corriger

S'il y a des incohérences, invoquer `code-coder` en lui demandant de lire
`.agent_reports/code-consistency-checker.md`, puis `code-reviewer`. Maximum 2 tours de
correction.

## 4. Re-vérifier

Après correction, relancer `code-consistency-checker` une fois pour confirmer que les
sites signalés sont traités. Une correction partielle sur ce type de bug est
indétectable autrement.
