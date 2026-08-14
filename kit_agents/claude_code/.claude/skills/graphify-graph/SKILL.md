---
name: graphify-graph
description: >
  Exploitation du graphe de connaissance Graphify du projet (dossier
  graphify-out/ : GRAPH_REPORT.md, graph.json, graph.html) pour localiser du code,
  tracer une chaîne d'appels, trouver tous les appelants d'une fonction, mesurer
  l'impact d'une modification ou cartographier une base inconnue. À charger avant
  de chercher où se trouve quelque chose dans le code, avant de planifier une
  modification touchant plusieurs fichiers, et avant tout audit de cohérence.
  Contient aussi les règles de fraîcheur et de vérification du graphe.
---

# Le graphe Graphify : s'en servir sans se faire piéger

## 1. Ce qui est sur le disque

```
graphify-out/
  GRAPH_REPORT.md    synthèse lisible : concepts clés, god nodes, clusters
  graph.json         le graphe complet, interrogeable
  graph.html         visualisation interactive (pour l'humain, pas pour toi)
```

`graphify-out/` est en LECTURE SEULE, sans exception. C'est une sortie générée :
la modifier à la main n'a aucun effet sur le code et fausse le graphe pour tous les
agents suivants. Le garde-fou refuse l'écriture dans ce dossier.

N'ouvre jamais `graph.html` : c'est du HTML de visualisation, illisible et
volumineux pour un agent.

## 2. Ordre d'exploitation

1. **`GRAPH_REPORT.md` d'abord.** C'est une synthèse conçue pour être lue : les
   composants logiques détectés, les god nodes (éléments les plus connectés, donc
   les abstractions centrales), les clusters. Quelques centaines de lignes qui
   remplacent des heures de lecture de fichiers.
2. **`graph.json` ensuite, par requête ciblée.** Ne le lis JAMAIS avec
   `view_file` : sur un projet réel c'est plusieurs mégaoctets, tu épuiserais ton
   contexte d'un coup. Passe par le script :

```
run_command: python .claude/scripts/graph_query.py stats
run_command: python .claude/scripts/graph_query.py find "authenticate"
run_command: python .claude/scripts/graph_query.py callers "valider_commande"
run_command: python .claude/scripts/graph_query.py callees "traiter_paiement"
run_command: python .claude/scripts/graph_query.py neighbors "Facture"
run_command: python .claude/scripts/graph_query.py path "api_commande" "base_donnees"
```

3. **Le fichier source en dernier**, sur les zones que le graphe a désignées.

Ce trio est l'inverse du réflexe habituel : on ne part plus du fichier pour
comprendre la structure, on part de la structure pour choisir quel fichier ouvrir.

## 3. EXTRACTED contre INFERRED : la distinction qui compte

Chaque relation du graphe porte une étiquette de confiance :

- **`EXTRACTED`** — lu directement dans le code source : import explicite, appel
  de fonction, définition de classe. Fiable.
- **`INFERRED`** — déduit par l'analyse : dépendance indirecte, inférence de
  type, résolution entre fichiers. C'est une hypothèse, pas un fait.

Règle : **on n'agit jamais sur une relation `INFERRED` sans l'avoir vérifiée** au
`grep_search` ou au `view_file`. Une relation inférée à tort qui devient une
modification de code produit exactement le genre de bug que ce dispositif existe
pour éviter.

Dans ton rapport, indique toujours l'origine : « d'après le graphe (EXTRACTED) »,
« d'après le graphe (INFERRED), vérifié dans `module.py:88` ».

## 4. Fraîcheur : le piège principal

Le graphe est un **cache**, construit à un instant donné. S'il a été généré avant
les modifications de la mission en cours, sa vision du code est périmée — et un
graphe périmé est plus dangereux qu'une absence de graphe, parce qu'il a l'air
autoritaire.

Avant de t'y fier :

1. `list_dir` sur `graphify-out/` pour voir si le dossier existe.
2. Compare sa date à celle des fichiers que tu vas toucher
   (`run_command: git log -1 --format=%cd` sur les fichiers concernés, ou la date
   de modification via `list_dir`).
3. Si le graphe est plus ancien que les dernières modifications du code : il reste
   utile pour la **cartographie générale** (quels modules existent, comment ils
   s'organisent), mais **pas** pour l'exactitude locale (signatures, appelants
   précis). Dis-le explicitement dans ton rapport.
4. S'il est absent : ce n'est pas bloquant. Tu retombes sur `grep_search` et
   `find_by_name`, comme avant. Signale simplement dans ta réponse qu'un
   `/graphify .` rendrait les prochaines missions plus rapides.

Aucun agent ne régénère le graphe de sa propre initiative : c'est une opération
longue et coûteuse, elle appartient à l'utilisateur.

## 5. Ce que le graphe remplace, et ce qu'il ne remplace pas

**Il remplace efficacement :**

- « où est défini X ? » -> `find`
- « qui appelle X ? » -> `callers`, bien plus fiable qu'un `grep_search` sur un
  nom, qui rate les alias et attrape les homonymes
- « qu'est-ce que je casse si je change cette signature ? » -> `callers`
- « comment ce module est-il relié à la base de données ? » -> `path`
- « quelles sont les abstractions centrales ? » -> god nodes du rapport

**Il ne remplace pas :**

- la lecture du corps d'une fonction avant de la modifier ;
- la vérification qu'un changement est complet (le graphe dit qui appelle quoi,
  pas si chaque appelant a été correctement mis à jour) ;
- l'exécution des tests ;
- le `git diff`, qui seul dit ce qui a réellement changé maintenant.

Le graphe localise. Le fichier confirme. Les tests valident. Ne saute aucune des
trois étapes.

## 6. Intégration MCP (variante)

Si le serveur MCP Graphify est configuré dans l'espace de travail, les requêtes de
graphe deviennent des outils natifs, interrogeables en direct plutôt que via un
fichier figé. C'est préférable quand c'est disponible : plus de question de
fraîcheur.

Dans ce cas, l'agent déclare le serveur dans son frontmatter (`mcpServers`) et les
outils apparaissent normalement. Les règles des sections 3 et 5 restent valables
telles quelles : `INFERRED` reste une hypothèse, et le graphe reste un localisateur,
pas une source de vérité sur le contenu du code.
