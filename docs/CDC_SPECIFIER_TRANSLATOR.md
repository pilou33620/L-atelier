# Cahier des Charges (CDC) : Agent « Specifier & Translator » (PreWorkflow Ingress)

Ce document définit les spécifications fonctionnelles et techniques de l'agent passerelle d'entrée **« Specifier & Translator »** (`spec-translator`), chargé de transformer toute demande, consigne ou bug report rédigé en français naturel en spécifications techniques optimisées en anglais structuré, immédiatement exploitables par les orchestrateurs et agents spécialistes de **L'Atelier** (Code, Hardware, Mécanique).

---

## 1. Contexte et Objectifs

* **Rôle** : Passerelle d'entrée transversale (« Step 0 ») du pipeline multi-agents.
* **Mission principale** : Ingérer une demande en français (expression de besoin libre, CDC complet, modification de code/circuit/pièce, log d'erreur avec commentaires) et générer un document Markdown en anglais technique normé, prêt pour l'orchestrateur du domaine ciblé.
* **Bénéfices clés** :
  1. **Performance maximale des modèles en aval** : Les LLMs spécialisés en code, électronique (SKiDL/KiCad) et CAO (CadQuery) sont entraînés massivement sur des corpus anglophones.
  2. **Suppression des hallucinations et contresens linguistiques** : Précision chirurgicale sur les termes d'ingénierie.
  3. **Standardisation du format** : Schéma invariant pour toute la flotte d'agents.
  4. **Zéro friction utilisateur** : L'utilisateur s'exprime naturellement en français, de manière itérative ou synthétique.

---

## 2. Spécifications Fonctionnelles

### Données d'Entrée (Input)
1. **Demande courante** : Texte brut en français (besoin, modification, log d'erreur).
2. **Mémoire conversationnelle glissante** : Les 2 à 3 derniers tours de dialogue (`[Demande FR, Spec EN générée]`) stockés dans `.agents/cache/conversation_window.json` (ou `.claude/cache/conversation_window.json`), permettant de résoudre les anaphores et requêtes itératives (*« fais pareil pour le module suivant »*, *« ajoute une résistance de 10k dessus »*).
3. **Contexte du projet (Snapshot)** : Liste des fichiers et modules réels présents sur le disque.

### Règles de Traitement & Transformation
1. **Traduction technique idiomatique** : Convertir les concepts métier et fonctionnels en vocabulaire standard de l'ingénierie logicielle, électronique et mécanique (ex : *« plan de masse »* $\rightarrow$ *« ground plane »*, *« dépouille »* $\rightarrow$ *« draft angle »*, *« mise en cache »* $\rightarrow$ *« request caching / memoization »*).
2. **Préservation stricte des éléments nommés** : Ne JAMAIS modifier ni traduire les noms de variables, fonctions, endpoints, classes, chemins de fichiers existants, numéros de broches, ou références de composants.
3. **Extraction des contraintes non négociables** : Isoler systématiquement les règles strictes (*« ne pas modifier telle fonction »*, *« préserver la rétrocompatibilité »*, *« tolérance stricte »*) dans la section dédiée.
4. **Détection du domaine et du workflow** : Identifier automatiquement le domaine (`Code`, `Hardware`, `Meca`) et le workflow recommandé (`/code-feature`, `/hw-carte`, `/meca-piece`, etc.).
5. **Isolation des hypothèses et manques** : Renseigner systématiquement la section `## 5. Assumptions & Open Questions` dès qu'une information physique ou technique est manquante ou sous-entendue, évitant que les agents en aval n'inventent une valeur.
6. **Zéro bavardage** : Sortie 100 % Markdown structuré, sans formule de politesse ni commentaire conversationnel.

---

## 3. Schéma de Sortie Attendu (Template Markdown)

L'agent formate sa réponse selon la structure exacte suivante :

```markdown
# TASK: [Action-oriented technical title in English]

**Domain**: [Code | Hardware | Meca]
**Recommended Workflow**: [/code-feature | /code-bugfix | /code-audit | /code-retrocompat | /hw-carte | /hw-datasheet | /meca-piece]

## 1. Objective
[Concise 1-2 sentence high-level goal in clear technical English]

## 2. Technical Requirements
- [Detailed functional requirement 1]
- [Detailed functional requirement 2]
- [Target file/module identified on disk: e.g., `circuits/alimentation.py`]

## 3. Strict Constraints & Guidelines
- [Rule 1 / Code style / Zero simplification rule / Invariance rule]
- [Preserved components, functions, variable names, pinouts, tolerances]

## 4. Context & Provided Data
- **Mapped Project Files**: [`path/to/file.ext`]
- **Input Snippets / Logs / Notes**: [Raw technical data translated/adapted]

## 5. Assumptions & Open Questions
- [Assumption 1: e.g. Assumed baud rate is 115200 bps]
- [Open question / Missing data: e.g. Exact GPIO pin for trigger signal not provided by user]
```

---

## 4. Configuration & Prompt Système (System Prompt)

```plaintext
You are a Senior Technical Specifier and Ingress Gateway acting as a bridge between a French-speaking user and downstream English-speaking AI coding/engineering agents (Code, Hardware, and Mechanics).

YOUR MISSION:
Take the provided French requirements, bug reports, feature requests, or specifications, along with the recent conversation history and project file tree, and convert them into a clear, rigorous, unambiguous, self-contained, and highly structured English technical specification.

OPERATING RULES:
1. TECHNICAL IDIOMATIC TRANSLATION: Do not translate word-for-word. Reframe concepts using standard software engineering, electronics (SKiDL/KiCad), or mechanical CAD (CadQuery) terminology.
2. RESOLVE CONTEXT & ANAPHORAS: Use the provided 2-3 recent conversation turns to fully resolve relative references ("do the same for X", "add a resistor on it", "change its dimensions"). The generated specification must be completely self-contained.
3. MAP REAL FILES: Match user references against the provided real project file tree. Never hallucinate non-existent paths when a corresponding project file exists.
4. PRESERVE IDENTIFIERS: Never translate or alter file names, variable names, function signatures, API endpoints, component designators (R1, C2, U3), pin names, or dimensions.
5. STRICT CONSTRAINTS: Isolate absolute rules (e.g. backward compatibility, zero simplification, preserve existing interfaces) in Section 3.
6. ISOLATE ASSUMPTIONS & QUESTIONS: Whenever a physical value, pin number, tolerance, or behavioral detail is missing, document it explicitly in Section 5 ("Assumptions & Open Questions"). Never let downstream agents guess physical values.
7. ZERO CONVERSATION: Output ONLY the formatted markdown specification. Do not include greetings, explanations, or closing remarks.
```

---

## 5. Matrice Terminologique Tri-Domaine

| Domaine | Terme FR typique | Traduction technique normalisée (EN) |
| :--- | :--- | :--- |
| **Code** | *« mise en cache »* | `request caching / memoization layer` |
| **Code** | *« intercepter l'erreur »* | `graceful error handling / exception catching` |
| **Code** | *« rétrocompatibilité »* | `backward compatibility / zero breaking change` |
| **Hardware** | *« plan de masse »* | `ground plane / copper pour` |
| **Hardware** | *« résistance de tirage »* | `pull-up / pull-down resistor` |
| **Hardware** | *« piste de puissance »* | `high-current power trace / power bus` |
| **Hardware** | *« condensateur de découplage »* | `decoupling / bypass capacitor` |
| **Hardware** | *« patte / broche »* | `pin assignment / pinout` |
| **Mécanique** | *« chanfrein »* | `chamfer` |
| **Mécanique** | *« congé / arrondi »* | `fillet` |
| **Mécanique** | *« dépouille »* | `draft angle` |
| **Mécanique** | *« jeu de fonctionnement »* | `clearance / mechanical fit tolerance` |
| **Mécanique** | *« trou taraudé »* | `tapped / threaded hole` |

---

## 6. Intégration PreWorkflow & Cycle de Vie

1. **Interception** : L'utilisateur soumet son texte en français dans l'UI ou le CLI.
2. **Hook PreWorkflow** : Le script utilitaire `spec_ingress.py` lit le prompt, charge la fenêtre d'historique (`conversation_window.json`), scanne l'arborescence du projet, et génère la spécification anglaise dans `.agent_reports/spec_ingress.md`.
3. **Étape 0 de l'Orchestrateur** : L'orchestrateur ciblé (`code-orchestrateur`, `hw-orchestrateur`, `meca-orchestrateur`) lit `.agent_reports/spec_ingress.md` au démarrage de sa mission et transmet directement la spécification à l'Architecte du domaine.
