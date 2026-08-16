---
description: Cycle complet d'ajout de fonctionnalite (architecte -> codeur -> revieweur)
---

**Demande / Objectif :** $ARGUMENTS

# /code-feature

Mode conception de fonctionnalité, piloté par l'`code-orchestrateur`.

## 0. Ouverture de mission & Spécification Ingress

- Si `.agent_reports/spec_ingress.md` est présent ou qu'une spécification a été produite par `spec-translator`, s'appuyer sur ses exigences, contraintes strictes et fichiers cartographiés.
- Vérifier la section `## 5. Assumptions & Open Questions` : si un point bloquant subsiste, poser la question avec `AskQuestion` MAINTENANT. Seul l'agent principal peut questionner sans risque de timeout.
- Fabriquer l'identifiant de mission (`AAAA-MM-JJ-slug`) et l'annoncer.
- `LS` sur `.agent_reports/` : tout rapport portant un autre identifiant
  est périmé. Le signaler et ne pas s'en servir.

## 1. Localiser

`grep_search` et `find_by_name` pour trouver les fichiers, lignes et symboles
concernés. Ces résultats iront dans le prompt de délégation : un sous-agent
démarre à zéro et refera la recherche sinon.

## 2. Concevoir

Invoquer `code-architect` avec l'identifiant de mission et les chemins trouvés.
Attendre la publication de `.agent_reports/code-architect.md`.

Si l'architecte termine par `BLOQUE`, relayer sa question à l'utilisateur avant
d'aller plus loin. Ne pas coder sur un plan incomplet.

## 3. Implémenter

- **Si $\le 2$ fichiers** : Invoquer `code-coder` avec l'identifiant de mission, en lui demandant de lire `.agent_reports/code-architect.md`.
- **Si $> 2$ fichiers (dès 3 fichiers)** : Appliquer obligatoirement les passes séquentielles (Option B) :
  1. Invoquer `code-coder` pour la Passe 1 (Fichier 1).
  2. Vérifier la présence du fichier sur disque (`Glob` / `Grep` / `LS`).
  3. Invoquer `code-coder` pour la Passe 2 (Fichier 2) en s'appuyant sur le Fichier 1.
  4. Répéter pour chaque passe jusqu'au dernier fichier.


## 4. Relire

Invoquer `code-reviewer`, focalisé sur le diff.

- `APPROUVE` -> étape suivante.
- `CORRECTIONS_REQUISES` -> re-invoquer `code-coder` sur `.agent_reports/code-reviewer.md`,
  puis relancer `code-reviewer`. **Maximum 2 tours.** Au troisième échec, arrêter et
  remonter à l'utilisateur ce qui coince.

## 5. Couvrir

Invoquer `code-test-writer` sur la fonctionnalité ajoutée, si le projet a une suite de
tests. S'il termine par `BLOQUE`, il a trouvé un vrai défaut : repasser par
`code-coder`.

## 6. Vérifier la cohérence

Si un champ, un paramètre ou une clé de configuration a été ajouté, invoquer
`code-consistency-checker`. C'est le cas le plus fréquent de régression silencieuse.

## 7. Valider le visuel

Si un agent a terminé par `VALIDATION_VISUELLE_REQUISE`, relayer la question de
rendu à l'utilisateur avec `ask_question`, puis renvoyer sa réponse au `code-coder` si
un ajustement est nécessaire.

## 8. Clôturer

Résumer : fichiers modifiés, vérifications passées (commandes exactes et issues),
rapports à consulter, ce qui reste à tester manuellement.
