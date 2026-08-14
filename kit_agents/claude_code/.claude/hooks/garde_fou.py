#!/usr/bin/env python3
"""
Garde-fou PreToolUse pour l'equipe d'agents.

Ce script est la SEULE barriere reellement contraignante du dispositif : les
regles ecrites dans les prompts sont des consignes, pas des verrous. Un hook,
lui, peut refuser un appel d'outil avant son execution.

Contrat (voir la doc Antigravity, section Hooks) :
  - entree : JSON sur stdin, avec toolCall.name et toolCall.args
  - sortie : JSON sur stdout, champ "decision" parmi
      allow | deny | ask | force_ask | deny_unless_prior_grant

Limite importante et assumee : la charge utile du hook ne contient PAS le nom
de l'agent appelant (seulement conversationId et modelName). Il est donc
impossible d'ecrire ici une regle du type "si l'agent est security, refuse
toute ecriture hors .agent_reports/". Le perimetre lecture-seule des agents
d'audit reste garanti par leur prompt et par leur liste d'outils ; ce hook
protege ce qui peut l'etre sans connaitre l'appelant : commandes destructives,
fichiers de secrets, definitions des agents.

Cas neutre : on n'ecrit RIEN sur stdout, pour laisser Antigravity appliquer sa
politique de permissions habituelle. Repondre {"decision": "allow"} partout
aurait pour effet d'auto-approuver toutes les ecritures, donc d'affaiblir la
securite au lieu de la renforcer.
"""

import json
import os
import re
import sys

# --- Commandes refusees sans discussion -------------------------------------
# Le message de refus explique a l'agent quoi faire : demander a l'utilisateur.
COMMANDES_INTERDITES = [
    (r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+", "suppression recursive de fichiers"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+clean\s+-[a-zA-Z]*f", "git clean -f"),
    (r"\bgit\s+checkout\s+--\s", "git checkout -- (perte des modifications)"),
    (r"\bgit\s+push\b.*(--force|(\s|^)-f(\s|$))", "git push --force"),
    (r"\bgit\s+filter-branch\b", "reecriture de l'historique git"),
    (r"\bgit\s+rebase\b", "reecriture de l'historique git"),
    (r"\bgit\s+stash\s+(drop|clear)\b", "suppression de stash"),
    (r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b", "destruction de donnees SQL"),
    (r"\bmkfs\b|\bdd\s+if=", "operation disque destructive"),
    (r"\bchmod\s+-R\s+777\b", "permissions 777 recursives"),
    (r"curl[^|]*\|\s*(ba)?sh", "execution d'un script telecharge"),
    (r"\bhistory\s+-c\b", "effacement de l'historique shell"),
]

# --- Commandes qui exigent une confirmation explicite ----------------------
COMMANDES_A_CONFIRMER = [
    (r"\bgit\s+(commit|push|tag)\b", "operation git ecrivant dans l'historique"),
    (r"\bsudo\b", "elevation de privileges"),
    (r"\b(npm|yarn|pnpm)\s+publish\b|\btwine\s+upload\b", "publication de paquet"),
    (r"\b(pip|npm|yarn|pnpm|cargo|go)\s+(install|add|get)\b", "installation de dependance"),
    (r"\balembic\s+upgrade\b|\bmigrate\b", "migration de base de donnees"),
]

# --- Fichiers dont l'ecriture est refusee ----------------------------------
FICHIERS_INTERDITS = [
    (r"(^|/)\.env($|\.|/)", "fichier d'environnement"),
    (r"(^|/)\.git/", "interne de git"),
    (r"\.(pem|key|p12|pfx|jks|keystore)$", "materiel cryptographique"),
    (r"(^|/)(id_rsa|id_ed25519|id_ecdsa)(\.pub)?$", "cle SSH"),
    (r"(^|/)(credentials|secrets?|service[-_]account)[^/]*\.(json|ya?ml|toml|ini|cfg)$",
     "fichier de secrets"),
    (r"(^|/)\.(npmrc|pypirc|netrc|aws/credentials)$", "identifiants d'outil"),
    # Donnees de reference fournies par l'utilisateur : lecture seule pour tous
    # les agents, sans exception. C'est la source de verite du mode hardware.
    (r"(^|/)data_sheets/", "datasheet de reference (lecture seule)"),
    # Sortie generee par Graphify : la modifier a la main n'a aucun effet sur le
    # code et fausse le graphe pour tous les agents suivants.
    (r"(^|/)graphify-out/", "graphe genere (lecture seule)"),
]

# --- Fichiers dont l'ecriture demande confirmation ------------------------
FICHIERS_A_CONFIRMER = [
    (r"(^|/)\.claude/", "definition de l'equipe d'agents"),
    (r"(^|/)\.agents/", "definition de l'equipe d'agents"),
    (r"(^|/)CLAUDE\.md$", "consignes du projet Claude Code"),
    (r"(^|/)AGENTS\.md$", "contrat du projet"),
    (r"(^|/)\.github/workflows/", "chaine d'integration continue"),
    (r"(^|/)(Dockerfile|docker-compose\.ya?ml)$", "infrastructure de conteneur"),
]

OUTILS_ECRITURE = {
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
}


def repondre(decision, raison):
    json.dump({"decision": decision, "reason": raison}, sys.stdout)
    sys.stdout.write("\n")
    sys.exit(0)


def laisser_passer():
    """Cas neutre : aucune sortie, la politique par defaut d'Antigravity s'applique."""
    sys.exit(0)


def tester(valeur, regles, insensible=True):
    drapeaux = re.IGNORECASE if insensible else 0
    for motif, libelle in regles:
        if re.search(motif, valeur, drapeaux):
            return libelle
    return None


def main():
    try:
        charge = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        laisser_passer()

    appel = charge.get("toolCall") or {}
    nom = appel.get("name") or ""
    args = appel.get("args") or {}

    if nom == "run_command":
        commande = str(args.get("CommandLine") or "")
        if not commande:
            laisser_passer()

        libelle = tester(commande, COMMANDES_INTERDITES)
        if libelle:
            repondre(
                "deny",
                "Commande refusee par le garde-fou du projet ({}). "
                "Cette operation est irreversible : ne la contourne pas, "
                "arrete-toi et demande a l'utilisateur de la lancer lui-meme "
                "s'il la veut.".format(libelle),
            )

        libelle = tester(commande, COMMANDES_A_CONFIRMER)
        if libelle:
            repondre(
                "force_ask",
                "Confirmation requise ({}).".format(libelle),
            )

        laisser_passer()

    if nom in OUTILS_ECRITURE:
        cible = str(args.get("TargetFile") or "")
        if not cible:
            laisser_passer()

        chemin = cible.replace("\\", "/")

        libelle = tester(chemin, FICHIERS_INTERDITS)
        if libelle:
            repondre(
                "deny",
                "Ecriture refusee par le garde-fou du projet : {} ({}). "
                "Les secrets ne s'ecrivent pas dans le depot, et les donnees de "
                "reference fournies par l'utilisateur ne se modifient "
                "pas.".format(cible, libelle),
            )

        libelle = tester(chemin, FICHIERS_A_CONFIRMER)
        if libelle:
            repondre(
                "force_ask",
                "Confirmation requise avant de modifier {} ({}).".format(cible, libelle),
            )

    laisser_passer()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        os._exit(0)
