---
name: verification-python
description: >
  Source unique des commandes de vérification de ce projet (syntaxe, lint,
  format, tests, diff) et procédure d'auto-vérification après modification de
  code. À charger avant de lancer un lint, une compilation ou une suite de
  tests, avant de valider une implémentation, et avant de rendre un verdict de
  revue. Ne jamais deviner les commandes de vérification : elles sont ici.
---

# Vérification du code

## 1. D'où viennent les commandes

Les commandes exactes de ce projet sont déclarées dans `CLAUDE.md / AGENTS.md`, section
« Commandes de vérification ». **C'est la seule source autorisée.**

Procédure :

1. Lis la section « Commandes de vérification » de `CLAUDE.md / AGENTS.md`.
2. Lance les commandes qui y figurent, telles quelles.
3. Si la section est vide ou incomplète, ne devine PAS une chaîne d'outils.
   Détecte le gestionnaire réellement présent à la racine (`pyproject.toml`,
   `package.json`, `Cargo.toml`, `go.mod`, `composer.json`, `Makefile`,
   `justfile`...), propose les commandes correspondantes, et signale dans ta
   réponse finale que `CLAUDE.md / AGENTS.md` devrait être complété.

Ne recopie jamais de commandes en dur depuis un autre agent, un autre projet ou
ta mémoire : c'est comme ça qu'on finit par lancer `ruff` sur un projet Node.

## 2. Ordre d'exécution

Du moins coûteux au plus coûteux, en s'arrêtant au premier échec bloquant :

1. Syntaxe / compilation
2. Lint
3. Tests

Si `CLAUDE.md / AGENTS.md` déclare une commande de formatage, ne la lance jamais
automatiquement sur l'ensemble du dépôt : un reformatage global noie le diff et
rend la revue impossible. Formate uniquement les fichiers que tu as touchés,
ou signale l'écart sans le corriger.

## 3. Périmètre du diff

Pour savoir ce qui a réellement changé : `git diff` (non indexé),
`git diff --staged` (indexé), `git diff --stat` pour une vue d'ensemble.

Ces commandes sont en lecture seule et sûres. En revanche, `git add`,
`git commit`, `git checkout --`, `git reset`, `git stash` modifient l'état du
dépôt : aucun agent ne les lance de sa propre initiative.

## 4. Auto-vérification obligatoire après modification

Avant de rendre la main, relis EN ENTIER chaque fonction modifiée et vérifie la
logique bout en bout :

- les variables créées sont-elles réellement persistées et utilisées, ou
  calculées puis jetées ?
- les nouveaux champs sont-ils propagés à TOUS les sites de construction, de
  sauvegarde, de validation, de sérialisation et d'affichage de l'objet ?
- tous les appelants d'une signature modifiée ont-ils été mis à jour ?
  (`grep_search` sur le nom de la fonction, pas de mémoire)
- les chemins de code alternatifs sont-ils traités : saisie manuelle, import de
  fichier, migration, valeurs par défaut, fixtures de test, constructeurs de
  secours ?

Ne termine jamais sur une simple impression d'avoir fini.

## 5. Modifications visuelles

Aucune commande ne remplace un œil humain sur un rendu. Pour toute modification
d'interface : décris précisément ce qu'il faut regarder (écran, action,
résultat attendu) et termine par `VALIDATION_VISUELLE_REQUISE`. Ne prétends pas
avoir validé un rendu que tu n'as pas vu.
