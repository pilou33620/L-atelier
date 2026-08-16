---
description: Conception d'une piece ou d'un assemblage 3D CadQuery (lead -> materiaux -> designer -> reviewer)
---

**Demande / Objectif :** $ARGUMENTS

# /meca-piece

Mode conception mécanique 3D, piloté par `meca-orchestrateur`.

## 0. Ouverture de mission & Spécification Ingress

- Si `.agent_reports/spec_ingress.md` est présent ou qu'une spécification a été produite par `spec-translator`, s'appuyer sur ses exigences géométriques, cotes et contraintes de fabrication.
- **Vérifier qu'on a les cotes.** Consulter la section `## 5. Assumptions & Open Questions` : dimensions, jeux fonctionnels, méthode de fabrication, contraintes d'assemblage. Si ça manque, `AskQuestion` MAINTENANT : une cote inventée donne une pièce qui ne s'assemble pas.
- Identifiant de mission (`AAAA-MM-JJ-slug`), annoncé.
- `LS` sur `.agent_reports/` : écarter les rapports périmés.

## 1. Cahier des charges

Invoquer `meca-lead`. Attendre `.agent_reports/meca-lead.md` avec la
décomposition géométrique en 4 étapes (base, ajouts, soustractions, finitions) et
le tableau des paramètres.

Si le lead termine par `BLOQUE`, relayer ses questions avant d'aller plus loin.

## 2. Matériaux

Invoquer `meca-materials`. Son rapport conditionne les épaisseurs de paroi
minimales et les tolérances du concepteur : ne pas sauter cette étape pour une
pièce destinée à être fabriquée.

Pour une pièce purement décorative ou un prototype de forme, on peut la sauter et
le dire explicitement.

## 3. Conception

Invoquer `meca-designer` en lui demandant de lire les deux rapports.

## 4. Vérification

Invoquer `meca-reviewer`. Il exécute réellement le modèle avec
`.claude/scripts/cq_check.py` et compare les dimensions obtenues au cahier des
charges.

- `APPROUVE` -> étape suivante.
- `CORRECTIONS_REQUISES` -> re-invoquer `meca-designer` sur
  `.agent_reports/meca-reviewer.md`, en exigeant une correction CHIRURGICALE et
  non une réécriture. **Maximum 2 tours.**

## 5. Validation visuelle

`ask_question` : demander à l'utilisateur d'ouvrir le script dans cq-editor et de
confirmer le rendu. Aucune vérification automatique ne remplace un œil sur la
forme.

Demander à cette occasion s'il veut un export STEP : le concepteur ne l'ajoute
que sur demande explicite.

## 6. Clôture

Résumer : fichiers produits, dimensions MESURÉES (pas espérées), matériau
recommandé, procédé de fabrication et ses paramètres, ce qui reste à valider.
