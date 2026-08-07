---
name: protocole-multi-agents
description: >
  Protocole obligatoire de l'équipe d'agents de ce projet : format des rapports
  dans .agent_reports/, en-tête de mission, passage de contexte aux sous-agents,
  vocabulaire des verdicts, vérification avant affirmation, escalade vers
  l'utilisateur. À charger dès qu'une tâche implique de déléguer à un
  sous-agent, de lire ou d'écrire un rapport d'agent, de rendre un verdict de
  revue, ou de coordonner plusieurs rôles (architect, coder, reviewer,
  debugger, security, analyst, tech-lead, consistency-checker, documentalist,
  test-writer).
---

# Protocole multi-agents

Ces règles s'appliquent à TOUS les agents du projet, y compris quand un agent
est lancé directement comme agent principal.

## 1. Identifiant de mission

Toute mission possède un identifiant court, en minuscules, de la forme
`AAAA-MM-JJ-slug` (exemple : `2026-08-05-ajout-champ-tva`).

- L'orchestrateur le crée au début de la mission et le transmet dans CHAQUE
  prompt de délégation.
- Un agent lancé directement sans identifiant fourni en fabrique un et
  l'annonce dans sa réponse.

Cet identifiant est ce qui distingue un rapport utile d'un rapport périmé.

## 2. Convention des rapports

Tout agent qui produit une analyse écrit son rapport dans
`.agent_reports/<nom-agent>.md`. Le chemin est déterministe : il n'y a jamais à
deviner ni à inventer un nom de fichier.

`.agent_reports/` n'est PAS un espace de travail partagé en écriture. Chaque
agent écrit uniquement son propre fichier et lit ceux des autres. Personne ne
supprime ni ne modifie le rapport d'un autre.

### En-tête obligatoire

La première ligne de tout rapport est exactement :

```
<!-- mission: <identifiant-de-mission> | agent: <nom-agent> | date: AAAA-MM-JJ -->
```

### Règle de fraîcheur (importante)

Avant d'exploiter un rapport, lis son en-tête.

- Identifiant de mission identique -> le rapport est valide, utilise-le.
- Identifiant différent, absent, ou date qui ne colle pas -> **traite le
  rapport comme inexistant**. Ne l'applique pas. Signale-le : « le rapport
  `.agent_reports/code-architect.md` concerne une autre mission, je n'en tiens pas
  compte ».

Les chemins étant réutilisés d'une mission à l'autre, un rapport de la semaine
dernière traîne toujours sur le disque. Appliquer un plan périmé est le pire
échec possible de ce dispositif.

## 3. Passage de contexte

Un sous-agent invoqué via `invoke_subagent` démarre avec un contexte VIERGE :
il n'a pas vu la conversation parente.

À inclure dans le prompt de délégation :

- l'identifiant de mission ;
- l'objectif en une ou deux phrases ;
- les chemins, numéros de ligne et symboles déjà trouvés, pour qu'il ne refasse
  pas la recherche ;
- le ou les rapports à lire, par leur chemin.

À ne JAMAIS inclure : le contenu d'un plan, d'un rapport ou d'une trace
d'erreur. Les rapports sont sur disque. On pointe vers le fichier :
« Lis `.agent_reports/code-architect.md` et agis en conséquence ».

## 4. Vocabulaire des verdicts

Certains mots sont des tokens de protocole, pas du langage naturel. Quand un
agent doit rendre un verdict, il termine sa réponse par une ligne contenant
UNIQUEMENT l'un de ces tokens :

| Token | Émis par | Signification |
|---|---|---|
| `APPROUVE` | reviewer | Le diff est conforme, rien à corriger. |
| `CORRECTIONS_REQUISES` | reviewer | Rapport écrit, corrections à appliquer. |
| `BLOQUE` | tout agent | Impossible d'aboutir, la raison est dans la réponse. |
| `VALIDATION_VISUELLE_REQUISE` | coder, test-writer | Un humain doit regarder le rendu. |
| `RIEN_A_SIGNALER` | agents d'audit | Audit fait, aucune anomalie réelle. |

Ne paraphrase pas ces tokens et n'en invente pas d'autres. L'orchestrateur route
en fonction d'eux.

## 5. Vérification avant affirmation

Ne conclus jamais qu'un fichier a été créé, modifié ou publié sans l'avoir
vérifié avec `list_dir`, `find_by_name`, `view_file` ou `git diff`.

Les agents en lecture seule ne produisent aucun fichier source. C'est attendu :
leur absence de modification n'est pas un échec et n'est pas une hallucination.

## 6. Escalade vers l'utilisateur

Un sous-agent est soumis à un délai d'interaction court (de l'ordre de la
minute) : **une question posée depuis un sous-agent risque d'expirer avant que
l'utilisateur réponde.**

Règle : seul l'agent principal pose des questions bloquantes à l'utilisateur.
Un sous-agent qui a besoin d'un arbitrage humain ne s'arrête pas dessus, il
rend la main en terminant par `BLOQUE` ou `VALIDATION_VISUELLE_REQUISE` et en
formulant la question précise à poser. L'orchestrateur la relaie.

Cas nécessitant un arbitrage humain :

- la demande est ambiguë sur un choix technique majeur ;
- une vérification visuelle est nécessaire (rendu, interface) ;
- la tâche semble irréaliste ou risquée en l'état.

## 7. Un seul routeur

Seul l'`code-orchestrateur` délègue. Les spécialistes ne s'appellent pas entre eux,
même quand ça paraîtrait pratique.

Raison : deux agents qui délèguent en parallèle sur les mêmes fichiers
produisent deux boucles de correction concurrentes, sans plafond et sans
personne qui ait la vue d'ensemble. Un spécialiste qui a besoin d'un autre rôle
termine par `BLOQUE` en nommant le rôle attendu.
