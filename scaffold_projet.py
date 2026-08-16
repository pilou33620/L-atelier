"""
Préparation d'un dossier projet pour Antigravity ou Claude Code — « L'Atelier ».

Ce module est le chaînon manquant entre l'outil Python et le kit d'agents :
quand tu crées un projet dans le lanceur, il installe dans le dossier tout ce
que les agents attendent d'y trouver, et rien de plus.

Il supporte deux types d'outils IA :
- « antigravity » : installe AGENTS.md et le dossier .agents/
- « claude_code » : installe CLAUDE.md, AGENTS.md et le dossier .claude/

Ce qu'il fait, dans l'ordre :

1. copie les fichiers de configuration (AGENTS.md / CLAUDE.md) et le dossier d'agents
   (.agents/ ou .claude/) depuis le kit de référence correspondant ;
2. élague les familles d'agents inutiles au mode choisi, ainsi que leurs
   workflows/commandes, skills et scripts ;
3. crée les dossiers attendus (.agent_reports/, data_sheets/, kicad_libs/,
   pieces/, tests/ selon le mode) ;
4. complète le .gitignore (.agents/cache/, .claude/cache/, .agent_reports/, etc.) ;
5. adapte les hooks au bon interpréteur Python ;
6. écrit le cache d'environnement (env.json) + le wrapper scripts/run_projet.py
   pour que les agents puissent exécuter SKiDL ou CadQuery avec les mêmes
   variables d'environnement KiCad que l'outil ;
7. en mode hardware, construit l'index KiCad (kicad_search.py --index) pour
   que les agents n'aient jamais à sortir du workspace.

Usage depuis ui.py :

    from scaffold_projet import preparer_projet

    rapport = preparer_projet(project_path, app_mode,
                              target_tool="antigravity", # ou "claude_code"
                              kit_source=CHEMIN_DU_KIT,
                              env_kicad={"KICAD8_SYMBOL_DIR": ...})
    for ligne in rapport.lignes:
        self.add_system_message(ligne)

Utilisable aussi en ligne de commande :

    python scaffold_projet.py <dossier_projet> <coder|hardware|meca> [antigravity|claude_code] [kit]
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------
# Table de correspondance mode de l'outil -> famille d'agents du kit
# --------------------------------------------------------------------------

FAMILLES = {"coder": "code", "hardware": "hw", "meca": "meca"}

OUTILS_CIBLES = {
    "antigravity": {
        "nom": "Antigravity (Gemini)",
        "dossier_agents": ".agents",
        "fichier_principal": "AGENTS.md",
        "sous_dossier_kit": "antigravity",
    },
    "claude_code": {
        "nom": "Claude Code (Claude)",
        "dossier_agents": ".claude",
        "fichier_principal": "CLAUDE.md",
        "sous_dossier_kit": "claude_code",
    },
}

# --------------------------------------------------------------------------
# Modèles IA & Presets supportés (Gemini / Antigravity & Claude / Claude Code)
# --------------------------------------------------------------------------

MODELES_DISPONIBLES_PAR_OUTIL = {
    "antigravity": [
        ("inherit", "Hérité (Défaut du système Gemini)"),
        ("flash_lite", "Gemini Flash-Lite (Ultra-léger & ultra-rapide)"),
        ("flash", "Gemini Flash (Rapide, économique, aiguillage/revue)"),
        ("pro", "Gemini Pro (Raisonnement avancé, architecture/code)"),
    ],
    "claude_code": [
        ("inherit", "Hérité (Défaut de la session Claude)"),
        ("haiku", "Claude 3.5 Haiku (Rapide, économique, aiguillage/revue)"),
        ("sonnet", "Claude 3.5 Sonnet (Recommandé : architecture, code & précision)"),
        ("opus", "Claude 3 Opus (Raisonnement maximal & réflexion approfondie)"),
    ],
}

MODELES_DISPONIBLES = MODELES_DISPONIBLES_PAR_OUTIL["antigravity"]

DESCRIPTIONS_AGENTS = {
    # Famille Code
    "code-orchestrateur": "Aiguilleur / Manager - Analyse et délègue",
    "code-architect": "Architecte Logiciel - Conçoit l'architecture et les specs",
    "code-coder": "Développeur - Implémente et modifie le code",
    "code-reviewer": "Revue de Code - Audite et valide les modifications",
    "code-debugger": "Débogueur - Diagnostique et corrige les anomalies",
    "code-security": "Sécurité & Robustesse - Audite les failles et entrées sensibles",
    "code-analyst": "Analyste de Code - Explore et explique la base de code",
    "code-documentalist": "Documentaliste - Rédige docstrings, README et manuels",
    "code-tech-lead": "Tech Lead - Oriente les choix de librairies et refontes",
    "code-test-writer": "Rédacteur de Tests - Écrit la suite de tests pytest",
    "code-consistency-checker": "Vérificateur de Cohérence - Harmonise signatures et usages",
    # Famille Hardware
    "hw-orchestrateur": "Aiguilleur Hardware - Coordonne la conception électronique",
    "hw-architect": "Architecte Hardware - Conçoit les schémas et l'architecture",
    "hw-coder-skidl": "Codeur SKiDL - Rédige le code Python netlist KiCad",
    "hw-erc-drc": "Vérificateur DRC/ERC - Contrôle les règles de conception",
    "hw-component": "Expert Composants - Analyse datasheets et sélectionne les pièces",
    "hw-calculator": "Calculateur - Dimensionne alimentations, filtres et puissances",
    "hw-footprint": "Gestionnaire Empreintes - Recherche et assigne les empreintes KiCad",
    "hw-documentalist": "Documentaliste Hardware - Rédige manuel de carte et BOM",
    # Famille Mécanique
    "meca-orchestrateur": "Aiguilleur Mécanique - Coordonne la modélisation 3D",
    "meca-lead": "Lead Mécanique - Définit cinématique et contraintes",
    "meca-designer": "Modélisateur CadQuery - Rédige le code 3D (STEP/STL)",
    "meca-reviewer": "Revue Mécanique - Contrôle tolérances, épaisseurs et faisabilité",
    "meca-materials": "Expert Matériaux - Sélectionne matières et procédés d'usinage",
    # Transversal
    "spec-translator": "Passerelle Spécifications - Ingestion FR -> specs techniques EN",
    "minimal": "Agent Minimaliste - Diagnostic léger",
}

# Profil recommandé Antigravity (Gemini)
PRESET_EQUILIBRE_GEMINI = {
    # Code
    "code-orchestrateur": "flash",
    "code-architect": "pro",
    "code-coder": "pro",
    "code-reviewer": "flash",
    "code-debugger": "pro",
    "code-security": "pro",
    "code-analyst": "flash",
    "code-documentalist": "flash",
    "code-tech-lead": "pro",
    "code-test-writer": "flash",
    "code-consistency-checker": "flash",
    # Hardware
    "hw-orchestrateur": "flash",
    "hw-architect": "pro",
    "hw-coder-skidl": "pro",
    "hw-erc-drc": "flash",
    "hw-component": "flash",
    "hw-calculator": "pro",
    "hw-footprint": "flash",
    "hw-documentalist": "flash",
    # Mécanique
    "meca-orchestrateur": "flash",
    "meca-lead": "pro",
    "meca-designer": "pro",
    "meca-reviewer": "flash",
    "meca-materials": "flash",
    # Transversal
    "spec-translator": "flash",
    "minimal": "inherit",
}

# Profil recommandé Claude Code (Claude)
PRESET_EQUILIBRE_CLAUDE = {
    # Code
    "code-orchestrateur": "haiku",
    "code-architect": "sonnet",
    "code-coder": "sonnet",
    "code-reviewer": "haiku",
    "code-debugger": "sonnet",
    "code-security": "sonnet",
    "code-analyst": "haiku",
    "code-documentalist": "haiku",
    "code-tech-lead": "sonnet",
    "code-test-writer": "haiku",
    "code-consistency-checker": "haiku",
    # Hardware
    "hw-orchestrateur": "haiku",
    "hw-architect": "sonnet",
    "hw-coder-skidl": "sonnet",
    "hw-erc-drc": "haiku",
    "hw-component": "haiku",
    "hw-calculator": "sonnet",
    "hw-footprint": "haiku",
    "hw-documentalist": "haiku",
    # Mécanique
    "meca-orchestrateur": "haiku",
    "meca-lead": "sonnet",
    "meca-designer": "sonnet",
    "meca-reviewer": "haiku",
    "meca-materials": "haiku",
    # Transversal
    "spec-translator": "haiku",
    "minimal": "inherit",
}

PRESET_EQUILIBRE = PRESET_EQUILIBRE_GEMINI

PRESETS_MODELES_PAR_OUTIL = {
    "antigravity": {
        "equilibre": {
            "id": "equilibre",
            "nom": "⚖️ Équilibré (Recommandé : Orchestrateur Flash + Architecte/Codeur Pro + Reviewer Flash)",
            "mapping": PRESET_EQUILIBRE_GEMINI,
        },
        "rapide": {
            "id": "rapide",
            "nom": "⚡ Rapide (Tout en Gemini Flash)",
            "mapping": {k: "flash" for k in PRESET_EQUILIBRE_GEMINI},
        },
        "precision": {
            "id": "precision",
            "nom": "🧠 Haute Précision (Tout en Gemini Pro)",
            "mapping": {k: "pro" for k in PRESET_EQUILIBRE_GEMINI},
        },
        "defaut": {
            "id": "defaut",
            "nom": "🔄 Par Défaut (Tout en Hérité / inherit)",
            "mapping": {k: "inherit" for k in PRESET_EQUILIBRE_GEMINI},
        },
    },
    "claude_code": {
        "equilibre": {
            "id": "equilibre",
            "nom": "⚖️ Équilibré (Recommandé : Orchestrateur Haiku + Architecte/Codeur Sonnet + Reviewer Haiku)",
            "mapping": PRESET_EQUILIBRE_CLAUDE,
        },
        "rapide": {
            "id": "rapide",
            "nom": "⚡ Rapide (Tout en Claude 3.5 Haiku)",
            "mapping": {k: "haiku" for k in PRESET_EQUILIBRE_CLAUDE},
        },
        "precision": {
            "id": "precision",
            "nom": "🧠 Haute Précision (Tout en Claude 3.5 Sonnet)",
            "mapping": {k: "sonnet" for k in PRESET_EQUILIBRE_CLAUDE},
        },
        "defaut": {
            "id": "defaut",
            "nom": "🔄 Par Défaut (Tout en Hérité / inherit)",
            "mapping": {k: "inherit" for k in PRESET_EQUILIBRE_CLAUDE},
        },
    },
}

PRESETS_MODELES = PRESETS_MODELES_PAR_OUTIL["antigravity"]

def obtenir_modeles_disponibles(target_tool: str = "antigravity") -> list[tuple[str, str]]:
    """Retourne la liste des modèles LLM disponibles pour l'outil IA spécifié."""
    outil = normaliser_outil(target_tool)
    return MODELES_DISPONIBLES_PAR_OUTIL.get(outil, MODELES_DISPONIBLES_PAR_OUTIL["antigravity"])

def obtenir_presets_modele(target_tool: str = "antigravity") -> dict:
    """Retourne les presets disponibles pour l'outil IA spécifié."""
    outil = normaliser_outil(target_tool)
    return PRESETS_MODELES_PAR_OUTIL.get(outil, PRESETS_MODELES_PAR_OUTIL["antigravity"])

def liste_agents_famille(famille: str) -> list[str]:
    """Retourne la liste ordonnée des agents appartenant à une famille (code, hw, meca)."""
    prefix = famille + "-"
    agents = [ag for ag in DESCRIPTIONS_AGENTS if ag.startswith(prefix)]
    if "spec-translator" not in agents:
        agents.append("spec-translator")
    return sorted(agents)

def obtenir_mapping_effectif(preset: str = "equilibre", surcharges: dict[str, str] | None = None,
                             target_tool: str = "antigravity") -> dict[str, str]:
    """Calcule le mapping effectif des modèles en combinant le preset et les surcharges éventuelles pour l'outil cible."""
    outil = normaliser_outil(target_tool)
    presets = PRESETS_MODELES_PAR_OUTIL.get(outil, PRESETS_MODELES_PAR_OUTIL["antigravity"])
    base = dict(presets.get(preset, presets.get("equilibre", {}))["mapping"])
    if surcharges:
        base.update(surcharges)
    return base


SKILLS_PAR_FAMILLE = {
    "code": ["protocole-multi-agents", "verification-python", "graphify-graph"],
    "hw": ["protocole-multi-agents", "verification-python", "skidl-kicad",
           "datasheets-json"],
    "meca": ["protocole-multi-agents", "verification-python",
             "cadquery-parametrique"],
}

SCRIPTS_PAR_FAMILLE = {
    "code": ["run_projet.py", "graph_query.py", "spec_ingress.py"],
    "hw": ["run_projet.py", "kicad_search.py", "kicad_fetch_part.py",
           "pcbparts.py", "spec_ingress.py"],
    "meca": ["run_projet.py", "cq_check.py", "spec_ingress.py"],
}

DOSSIERS_PAR_FAMILLE = {
    "code": [".agent_reports", "tests"],
    "hw": [".agent_reports", "data_sheets", "kicad_libs", "footprints.pretty",
           "circuits"],
    "meca": [".agent_reports", "pieces"],
}

IGNORE_COMMUN = [
    "# --- L'Atelier / agents (données locales régénérables) ---",
    ".agent_reports/",
    ".agent_backups/",
    ".agents/cache/",
    ".claude/cache/",
    "graphify-out/",
    ".skidl_search_tmp.py",
]

IGNORE_PAR_FAMILLE = {
    "code": [],
    # Sous-produits SKiDL, régénérables à chaque exécution du script.
    "hw": ["*.net", "*.erc", "*.log", "*_sklib.py", "*-backups/"],
    "meca": ["temp_viewer.py", "*.step.bak"],
}

# Wrapper d'exécution : les agents lancent les scripts du projet à travers lui,
# ce qui garantit qu'ils voient les mêmes chemins KiCad que l'outil.
RUN_PROJET = '''#!/usr/bin/env python3
"""
Execute un script du projet avec l'environnement enregistre par L'Atelier.

Deux problemes a resoudre, et c'est pourquoi ce wrapper existe :

1. Les variables d'environnement KiCad sont definies dans le processus de
   l'outil graphique. Un agent lance ailleurs ne les voit pas, et SKiDL echoue
   sur une librairie de symboles introuvable. On relit .claude/cache/env.json ou
   .agents/cache/env.json et on les reinjecte.

2. SKiDL nomme ses fichiers de sortie (.erc, .log, _sklib.py) d'apres le script
   de PLUS HAUT NIVEAU de la pile d'appels. Executer le script cible depuis ce
   wrapper avec runpy ou exec laissait donc des fichiers appeles
   « run_projet.erc », « run_projet.log » a la racine du projet. On lance donc un
   VRAI sous-processus : le script cible redevient le script de plus haut niveau,
   et ses sorties portent son nom.

Les sous-produits SKiDL sont ensuite ranges a cote du script, dans circuits/.

    python .agents/scripts/run_projet.py circuits/carte-capteur.py
    # ou
    python .claude/scripts/run_projet.py circuits/carte-capteur.py
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CONFIG_CLAUDE = RACINE / ".claude" / "cache" / "env.json"
CONFIG_AGY = RACINE / ".agents" / "cache" / "env.json"
CONFIG = CONFIG_CLAUDE if CONFIG_CLAUDE.is_file() else CONFIG_AGY

# Sous-produits que SKiDL depose dans le repertoire courant, nommes d'apres le
# script. Le netlist n'y figure pas : le script doit le placer lui-meme avec
# generate_netlist(file_=...).
SUFFIXES = (".erc", ".log", "_sklib.py")


def environnement():
    env = dict(os.environ)
    if not CONFIG.is_file():
        print(
            "Aucun fichier d'environnement (.claude/cache/env.json ou .agents/cache/env.json) : "
            "execution avec l'environnement brut. Si SKiDL ne trouve pas ses librairies, "
            "relancer la preparation du projet depuis L'Atelier.",
            file=sys.stderr,
        )
        return env
    try:
        for cle, valeur in json.loads(CONFIG.read_text("utf-8")).items():
            env.setdefault(cle, str(valeur))
    except (ValueError, OSError) as err:
        print("env.json illisible : {}".format(err), file=sys.stderr)
    return env


def ranger(script):
    """Deplace les sous-produits SKiDL a cote du script."""
    base = script.stem
    deplaces = []
    for suffixe in SUFFIXES:
        source = RACINE / (base + suffixe)
        if not source.is_file():
            continue
        cible = script.parent / source.name
        if source.resolve() == cible.resolve():
            continue
        try:
            shutil.move(str(source), str(cible))
            deplaces.append(cible.relative_to(RACINE).as_posix())
        except (OSError, shutil.Error):
            pass
    if deplaces:
        print("Sous-produits ranges : {}".format(", ".join(deplaces)),
              file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print("usage : run_projet.py <script.py> [args...]", file=sys.stderr)
        return 2

    script = Path(sys.argv[1])
    if not script.is_absolute():
        script = RACINE / script
    if not script.is_file():
        print("Script introuvable : {}".format(sys.argv[1]), file=sys.stderr)
        return 2

    # Repertoire courant = racine du projet, pour que les chemins relatifs du
    # script (kicad_libs/, footprints.pretty/) restent valides.
    processus = subprocess.run(
        [sys.executable, str(script)] + sys.argv[2:],
        cwd=str(RACINE), env=environnement(),
    )
    ranger(script)
    return processus.returncode


if __name__ == "__main__":
    sys.exit(main())
'''


@dataclass
class Rapport:
    """Ce qui a été fait, pour affichage dans l'interface."""

    lignes: list = field(default_factory=list)
    erreurs: list = field(default_factory=list)

    def ok(self, texte):
        self.lignes.append("✅ " + texte)

    def info(self, texte):
        self.lignes.append("• " + texte)

    def attente(self, texte):
        """Reste à faire, mais ce n'est pas un échec de la préparation."""
        self.lignes.append("⏭️ " + texte)

    def alerte(self, texte):
        self.lignes.append("⚠️ " + texte)
        self.erreurs.append(texte)

    @property
    def succes(self):
        return not self.erreurs


# --------------------------------------------------------------------------
# Localisation du kit de référence
# --------------------------------------------------------------------------


def normaliser_outil(target_tool: str) -> str:
    """Normalise le nom de l'outil cible."""
    target = str(target_tool).strip().lower()
    if target in ("claude", "claude_code", "claudecode", "claude-code", "2"):
        return "claude_code"
    return "antigravity"


def est_un_kit(dossier, target_tool: str = "antigravity"):
    """Vérifie si un dossier contient un kit d'agents valide pour l'outil demandé."""
    try:
        dossier = Path(dossier)
        outil = normaliser_outil(target_tool)
        if outil == "claude_code":
            has_claude_dir = (dossier / ".claude").is_dir()
            has_agents_dir = (dossier / ".agents").is_dir()
            has_claude_md = (dossier / "CLAUDE.md").is_file()
            has_agents_md = (dossier / "AGENTS.md").is_file()
            return (has_claude_dir or has_agents_dir) and (has_claude_md or has_agents_md)
        else:
            return (dossier / "AGENTS.md").is_file() and (dossier / ".agents").is_dir()
    except OSError:
        return False


def emplacements_kit(target_tool: str = "antigravity"):
    """Emplacements consultés, dans l'ordre, pour trouver le kit d'agents."""
    base = Path(__file__).resolve().parent
    outil = normaliser_outil(target_tool)
    sous_nom = OUTILS_CIBLES[outil]["sous_dossier_kit"]

    candidats = [
        base / "kit_agents" / sous_nom,
        base / sous_nom,
        base / "kit_agents",
        base,
        base.parent / "kit_agents" / sous_nom,
        base.parent / "kit_agents",
        Path.home() / ".latelier" / "kit" / sous_nom,
        Path.home() / ".latelier" / "kit",
    ]
    if outil == "antigravity":
        candidats.extend([
            base / "agents-3-modes",
            base / "agents-3-modes-corrige",
        ])

    # Puis n'importe quel sous-dossier de premier niveau qui ressemble à un kit
    try:
        for sous in sorted(base.iterdir()):
            if sous.is_dir() and sous.name not in ("__pycache__", ".git") \
                    and sous not in candidats:
                candidats.append(sous)
    except OSError:
        pass
    return candidats


def modules_outil():
    """Modules que L'Atelier doit avoir à côté de lui pour tout activer."""
    base = Path(__file__).resolve().parent
    return {
        "pcbparts.py": (base / "pcbparts.py").is_file(),
    }


def kit_par_defaut(target_tool: str = "antigravity"):
    """Premier emplacement contenant un kit pour l'outil demandé, ou None."""
    outil = normaliser_outil(target_tool)
    for c in emplacements_kit(outil):
        if est_un_kit(c, target_tool=outil):
            return c
    return None


# --------------------------------------------------------------------------
# Étapes de Scaffolding
# --------------------------------------------------------------------------


def _empreinte(chemin: Path):
    """Empreinte du contenu d'un fichier, pour reconnaître la version du kit."""
    try:
        return hashlib.sha256(chemin.read_bytes()).hexdigest()
    except OSError:
        return ""


def _enregistrer_empreinte(racine: Path, kit: Path, target_tool: str = "antigravity"):
    outil = normaliser_outil(target_tool)
    dossier_agents = OUTILS_CIBLES[outil]["dossier_agents"]
    cache = racine / dossier_agents / "cache"
    fichier_md = kit / OUTILS_CIBLES[outil]["fichier_principal"]
    if not fichier_md.is_file():
        fichier_md = kit / "AGENTS.md"

    try:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "kit.json").write_text(
            json.dumps({
                "md_hash": _empreinte(fichier_md),
                "source": str(kit),
                "target_tool": outil,
            }, indent=2),
            encoding="utf-8")
    except OSError:
        pass


def _empreinte_enregistree(racine: Path, target_tool: str = "antigravity"):
    outil = normaliser_outil(target_tool)
    dossier_agents = OUTILS_CIBLES[outil]["dossier_agents"]
    fichier = racine / dossier_agents / "cache" / "kit.json"
    try:
        data = json.loads(fichier.read_text(encoding="utf-8"))
        return data.get("md_hash", "") or data.get("agents_md", "")
    except (OSError, ValueError):
        return ""


def _filtre_copie(source_dir: Path, famille: str):
    """Construit le filtre `ignore` de copytree pour élaguer les autres familles."""
    autres = [f for f in FAMILLES.values() if f != famille]
    skills = set(SKILLS_PAR_FAMILLE[famille])
    scripts = set(SCRIPTS_PAR_FAMILLE[famille])
    source_root = source_dir.resolve()

    def ignorer(dossier, noms):
        try:
            relatif = Path(dossier).resolve().relative_to(source_root).as_posix()
        except ValueError:
            relatif = ""
        exclus = {n for n in noms if n == "__pycache__" or n.endswith(".pyc")}

        if relatif == "agents":
            exclus |= {n for n in noms
                       if any(n.startswith(a + "-") for a in autres)}
        elif relatif in ("workflows", "commands"):
            exclus |= {n for n in noms
                       if any(n.startswith(a + "-") for a in autres)}
        elif relatif == "skills":
            exclus |= {n for n in noms
                       if (Path(dossier) / n).is_dir() and n not in skills}
        elif relatif == "scripts":
            exclus |= {n for n in noms
                       if n.endswith(".py") and n not in scripts}
        return exclus

    return ignorer


def _copier_kit(kit: Path, racine: Path, famille: str, target_tool: str,
                rapport: Rapport, elaguer: bool = True):
    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]
    cible_agents = racine / dossier_nom

    # Source du sous-dossier d'agents (.claude ou .agents)
    source_sub = kit / dossier_nom
    if not source_sub.is_dir():
        # Repli si kit contient .agents mais qu'on installe .claude ou inversement
        source_sub = kit / ".agents" if (kit / ".agents").is_dir() else (kit / ".claude")

    if not source_sub.is_dir():
        rapport.alerte(f"Dossier des agents introuvable dans le kit : {kit}")
        return

    if cible_agents.exists():
        rapport.info(f"{dossier_nom}/ déjà présent : conservé tel quel, rien n'est supprimé.")
        _signaler_familles_en_trop(cible_agents, famille, rapport)
    else:
        filtre = _filtre_copie(source_sub, famille) if elaguer else None
        shutil.copytree(source_sub, cible_agents, ignore=filtre)
        nb = len(list((cible_agents / "agents").glob("*/"))) \
            if (cible_agents / "agents").is_dir() else 0
        rapport.ok(
            f"{dossier_nom}/ installé ({OUTILS_CIBLES[outil]['nom']}) — {nb} agents de la "
            f"famille « {famille} » (les autres familles ne sont pas copiées)."
        )

    # Copie des fichiers markdown de configuration (CLAUDE.md et/ou AGENTS.md)
    fichiers_a_copier = []
    if outil == "claude_code":
        fichiers_a_copier = ["CLAUDE.md", "AGENTS.md"]
    else:
        fichiers_a_copier = ["AGENTS.md"]

    for nom_fichier in fichiers_a_copier:
        src_md = kit / nom_fichier
        if not src_md.is_file():
            # Repli
            src_md = kit / "AGENTS.md" if (kit / "AGENTS.md").is_file() else kit / "CLAUDE.md"
        if not src_md.is_file():
            continue

        cible_md = racine / nom_fichier
        if cible_md.exists():
            if _empreinte(src_md) == _empreinte_enregistree(racine, outil):
                rapport.info(f"{nom_fichier} déjà issu de cette version du kit.")
            else:
                secours = racine / f"{nom_fichier}.nouveau"
                shutil.copy2(src_md, secours)
                rapport.alerte(
                    f"{nom_fichier} existe déjà et diffère du kit : la version du kit a "
                    f"été écrite à côté, dans {nom_fichier}.nouveau."
                )
        else:
            shutil.copy2(src_md, cible_md)
            rapport.ok(f"{nom_fichier} installé.")

    _enregistrer_empreinte(racine, kit, target_tool=outil)


def _signaler_familles_en_trop(dossier_agents: Path, famille: str,
                                rapport: Rapport):
    """Signale les agents des autres familles SANS rien supprimer."""
    autres = [f for f in FAMILLES.values() if f != famille]
    cible = dossier_agents / "agents"
    if not cible.is_dir():
        return
    en_trop = sorted(d.name for d in cible.iterdir()
                     if d.is_dir() and any(d.name.startswith(a + "-")
                                           for a in autres))
    if en_trop:
        rapport.info(
            "{} agents d'autres familles sont présents ({}…). Ils sont "
            "conservés ; supprime-les à la main si tu veux alléger /agents."
            .format(len(en_trop), ", ".join(en_trop[:3]))
        )


def _nettoyer_table_commandes(racine: Path, target_tool: str, rapport: Rapport):
    """Retire du tableau des commandes celles dont le script a été élagué."""
    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]
    fichiers = [racine / "AGENTS.md"]
    if outil == "claude_code":
        fichiers.append(racine / "CLAUDE.md")

    dossier_scripts = racine / dossier_nom / "scripts"
    if not dossier_scripts.is_dir():
        return
    presents = {p.name for p in dossier_scripts.glob("*.py")}

    for md in fichiers:
        if not md.is_file():
            continue
        lignes, retirees = [], 0
        for ligne in md.read_text(encoding="utf-8").splitlines(keepends=True):
            if ligne.lstrip().startswith("|") and ("scripts/" in ligne):
                cites = {m for m in presents if m in ligne}
                if not cites and any(
                    nom in ligne
                    for fam in SCRIPTS_PAR_FAMILLE.values()
                    for nom in fam
                ):
                    retirees += 1
                    continue
            lignes.append(ligne)
        if retirees:
            md.write_text("".join(lignes), encoding="utf-8")
            rapport.ok(f"{retirees} commande(s) obsolète(s) retirée(s) de {md.name}.")


def _marquer_mode(racine: Path, famille: str, target_tool: str, rapport: Rapport):
    """Écrit en tête d'AGENTS.md et/ou CLAUDE.md le mode réellement installé."""
    outil = normaliser_outil(target_tool)
    fichiers = [racine / "AGENTS.md"]
    if outil == "claude_code":
        fichiers.append(racine / "CLAUDE.md")

    principal = {"code": "code-orchestrateur", "hw": "hw-orchestrateur",
                 "meca": "meca-orchestrateur"}[famille]

    for md in fichiers:
        if not md.is_file():
            continue
        texte = md.read_text(encoding="utf-8")
        if "<!-- mode-atelier:" in texte:
            continue
        entete = (
            "<!-- mode-atelier: {famille} -->\n\n"
            "> **Mode installé dans ce projet : `{famille}` ({outil_nom})**.\n"
            "> Les deux autres familles d'agents ont été retirées par L'Atelier.\n"
            "> L'agent principal à ouvrir est **`{principal}`** ; les tableaux\n"
            "> décrivant les autres modes ne s'appliquent pas ici.\n\n"
        ).format(famille=famille, outil_nom=OUTILS_CIBLES[outil]["nom"], principal=principal)
        md.write_text(entete + texte, encoding="utf-8")
        rapport.ok(f"Mode « {famille} » marqué en tête de {md.name}.")


def _creer_dossiers(racine: Path, famille: str, target_tool: str, rapport: Rapport):
    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]

    for nom in DOSSIERS_PAR_FAMILLE[famille]:
        (racine / nom).mkdir(parents=True, exist_ok=True)
    (racine / dossier_nom / "cache").mkdir(parents=True, exist_ok=True)
    rapport.ok("Dossiers créés : " + ", ".join(DOSSIERS_PAR_FAMILLE[famille]) + ".")

    if famille == "hw":
        garde = racine / "data_sheets" / "LISEZ-MOI.md"
        if not garde.exists():
            garde.write_text(
                "# data_sheets/\n\n"
                "Datasheets pré-extraites, une par composant :\n\n"
                "```\n<composant>.json          [{\"page\": 1, \"texte_markdown\": \"...\","
                " \"images\": [\"data_sheets/<composant>_images/page1_img1.png\"]}]\n"
                "<composant>_images/       captures extraites du PDF\n```\n\n"
                "Dossier en **lecture seule** pour tous les agents (le garde-fou "
                "refuse l'écriture). Seul `hw-component` a le droit de l'ouvrir.\n"
                "Les fichiers sont produits par L'Atelier, bouton d'import de "
                "datasheets.\n",
                encoding="utf-8",
            )


def _gitignore(racine: Path, famille: str, rapport: Rapport):
    chemin = racine / ".gitignore"
    existant = chemin.read_text(encoding="utf-8").splitlines() if chemin.is_file() else []
    presents = {l.strip() for l in existant}
    ajouts = [l for l in IGNORE_COMMUN + IGNORE_PAR_FAMILLE[famille]
              if l.strip() not in presents]
    if not ajouts:
        return
    with chemin.open("a", encoding="utf-8") as fh:
        if existant and existant[-1].strip():
            fh.write("\n")
        fh.write("\n".join(ajouts) + "\n")
    rapport.ok("{} entrées ajoutées au .gitignore.".format(len(ajouts)))


def _adapter_hooks(racine: Path, target_tool: str, rapport: Rapport):
    """Adapte les hooks de sécurité à l'interpréteur Python présent."""
    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]
    chemin_hooks_json = racine / dossier_nom / "hooks.json"
    
    interpreteur = "python" if os.name == "nt" else "python3"
    if shutil.which(interpreteur) is None:
        autre = "python3" if interpreteur == "python" else "python"
        if shutil.which(autre):
            interpreteur = autre
        else:
            rapport.alerte(
                "Aucun interpréteur « python » sur le PATH : le garde-fou ne "
                "pourra pas se lancer."
            )
            return

    if chemin_hooks_json.is_file():
        brut = chemin_hooks_json.read_text(encoding="utf-8")
        remplace = brut.replace("python3 ", interpreteur + " ").replace("python ", interpreteur + " ")
        if remplace != brut:
            chemin_hooks_json.write_text(remplace, encoding="utf-8")
            rapport.ok(f"Garde-fou câblé sur « {interpreteur} ».")
        else:
            rapport.info(f"Garde-fou déjà configuré sur « {interpreteur} ».")


def _ecrire_env(racine: Path, env_kicad: dict, famille: str, target_tool: str,
                rapport: Rapport, bloquant: bool = True):
    """Rend l'environnement de l'outil rejouable par les agents."""
    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]

    # Écrire dans le dossier cible (et dans .agents si présent)
    dossiers_cache = [racine / dossier_nom / "cache"]
    if (racine / ".agents" / "cache").is_dir() and dossier_nom != ".agents":
        dossiers_cache.append(racine / ".agents" / "cache")

    valeurs = {}
    interessantes = ("KICAD", "SKIDL")
    for cle, val in os.environ.items():
        if any(cle.startswith(p) for p in interessantes):
            valeurs[cle] = val
    valeurs.update({k: v for k, v in (env_kicad or {}).items() if v})

    for cache in dossiers_cache:
        cache.mkdir(parents=True, exist_ok=True)
        if valeurs:
            (cache / "env.json").write_text(
                json.dumps(valeurs, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    if valeurs:
        rapport.ok(f"{len(valeurs)} variables d'environnement enregistrées dans {dossier_nom}/cache/env.json.")
    elif famille == "hw":
        message = ("Chemins KiCad pas encore connus : ils sont demandés à "
                   "l'ouverture de la fenêtre, et l'environnement sera écrit à "
                   "ce moment-là.")
        rapport.alerte(message) if bloquant else rapport.attente(message)

    # Installer run_projet.py
    scripts_dir = racine / dossier_nom / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    wrapper = scripts_dir / "run_projet.py"
    if not wrapper.is_file():
        wrapper.write_text(RUN_PROJET, encoding="utf-8")
        rapport.ok(f"{dossier_nom}/scripts/run_projet.py installé.")

    _declarer_commande(racine, target_tool, rapport)


def _declarer_commande(racine: Path, target_tool: str, rapport: Rapport):
    """Ajoute le wrapper au tableau des commandes de vérification."""
    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]
    fichiers = [racine / "AGENTS.md"]
    if outil == "claude_code":
        fichiers.append(racine / "CLAUDE.md")

    for md in fichiers:
        if not md.is_file():
            continue
        texte = md.read_text(encoding="utf-8")
        if "run_projet.py" in texte:
            continue
        ancre = "| Diff en cours |"
        ligne = (f"| Exécution d'un script du projet | "
                 f"`python {dossier_nom}/scripts/run_projet.py circuits/<nom>.py` |\n")
        if ancre in texte:
            avant, apres = texte.split(ancre, 1)
            fin_ligne = apres.index("\n") + 1
            texte = avant + ancre + apres[:fin_ligne] + ligne + apres[fin_ligne:]
            md.write_text(texte, encoding="utf-8")
            rapport.ok(f"Commande d'exécution déclarée dans {md.name}.")


def _index_kicad(racine: Path, env_kicad: dict, target_tool: str, rapport: Rapport,
                 bloquant: bool = True):
    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]
    script = racine / dossier_nom / "scripts" / "kicad_search.py"
    if not script.is_file():
        # Repli
        script = racine / ".agents" / "scripts" / "kicad_search.py"
    if not script.is_file():
        rapport.alerte("kicad_search.py absent : pas d'index KiCad.")
        return

    env = dict(os.environ)
    env.update({k: v for k, v in (env_kicad or {}).items() if v})
    env["NoDefaultCurrentDirectoryInExePath"] = "1"

    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--index"],
            cwd=str(racine), capture_output=True, text=True, timeout=300, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        rapport.alerte("Index KiCad non construit : {}".format(err))
        return

    if proc.returncode == 0:
        rapport.ok((proc.stdout or "").strip() or "Index KiCad construit.")
        return

    detail = (proc.stderr or "").strip()[:400]
    if proc.returncode == 3 and not bloquant:
        rapport.attente("Index KiCad à construire une fois les chemins KiCad "
                        "renseignés.")
    else:
        rapport.alerte(
            "Index KiCad non construit (code {}). Sans lui les agents "
            "s'arrêteront sur BLOQUE au lieu d'inventer des empreintes.\n{}"
            .format(proc.returncode, detail))


# --------------------------------------------------------------------------
# Gestion des Modèles LLM, Activation & Synchronisation des Agents
# --------------------------------------------------------------------------


def appliquer_modeles_agents(racine: Path, famille: str = "code", target_tool: str = "antigravity",
                             modeles: dict[str, str] | None = None, preset: str = "equilibre",
                             agents_actifs: set[str] | list[str] | None = None,
                             rapport: Rapport | None = None) -> Rapport:
    """Applique les modèles LLM configurés aux agents du projet :
    1. Met à jour le champ 'model:' dans le frontmatter YAML de chaque agent.md.
    2. Adapte le prompt de délégation de l'orchestrateur pour forcer Model="..." dans invoke_subagent.
    3. Documente la matrice des modèles dans AGENTS.md / CLAUDE.md.
    4. Enregistre la configuration dans .agents/cache/models.json.
    """
    if rapport is None:
        rapport = Rapport()

    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]
    racine_agents = racine / dossier_nom
    if not racine_agents.is_dir():
        # Repli si .agents ou .claude existe
        racine_agents = racine / ".agents" if (racine / ".agents").is_dir() else (racine / ".claude")

    dossier_agents = racine_agents / "agents"
    if not dossier_agents.is_dir():
        rapport.alerte(f"Dossier agents introuvable dans {racine_agents.name} : modèles non appliqués.")
        return rapport

    mapping_complet = obtenir_mapping_effectif(preset, modeles, target_tool=outil)
    modifies = 0

    presents = {d.name for d in dossier_agents.iterdir() if d.is_dir()}
    if agents_actifs is not None:
        presents &= set(agents_actifs)

    # 1. Mise à jour du frontmatter YAML dans chaque agent.md
    for agent_dir in sorted(dossier_agents.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_name = agent_dir.name
        agent_md = agent_dir / "agent.md"
        if not agent_md.is_file():
            continue

        target_model = mapping_complet.get(agent_name, "inherit")
        contenu = agent_md.read_text(encoding="utf-8")

        if contenu.startswith("---"):
            parties = contenu.split("---", 2)
            if len(parties) >= 3:
                frontmatter = parties[1]
                body = parties[2]
                if re.search(r"^model:\s*.*$", frontmatter, flags=re.MULTILINE):
                    frontmatter = re.sub(r"^model:\s*.*$", f"model: {target_model}", frontmatter, flags=re.MULTILINE)
                else:
                    frontmatter = frontmatter.rstrip() + f"\nmodel: {target_model}\n"
                agent_md.write_text(f"---{frontmatter}---{body}", encoding="utf-8")
                modifies += 1

    # 2. Adaptation du prompt de délégation dans l'agent orchestrateur
    orch_map = {"code": "code-orchestrateur", "hw": "hw-orchestrateur", "meca": "meca-orchestrateur"}
    orchestrateur_nom = orch_map.get(famille, f"{famille}-orchestrateur")
    orch_file = dossier_agents / orchestrateur_nom / "agent.md"
    if orch_file.is_file():
        texte_orch = orch_file.read_text(encoding="utf-8")
        noms_actifs_str = ", ".join(f"`{a}`" for a in sorted(presents) if a != orchestrateur_nom)
        texte_orch = re.sub(
            r"Les noms\s+valides sont STRICTEMENT\s*:[^\n]+",
            f"Les noms valides sont STRICTEMENT : {noms_actifs_str}.",
            texte_orch
        )

        if outil == "claude_code":
            bloc_delegation = "### Modèles assignés aux sous-agents\n\n"
            bloc_delegation += "Les sous-agents du projet sont configurés avec les modèles Claude suivants :\n"
            for ag in sorted(presents):
                if ag == orchestrateur_nom:
                    continue
                m = mapping_complet.get(ag, "inherit")
                bloc_delegation += f"- `{ag}` : `model: {m}`\n"
            bloc_delegation += "\n"
        else:
            bloc_delegation = "### Modèles d'invocation assignés (invoke_subagent)\n\n"
            bloc_delegation += "Lors de la délégation avec `invoke_subagent`, spécifie OBLIGATOIREMENT le paramètre `Model` suivant selon le sous-agent actif :\n"
            for ag in sorted(presents):
                if ag == orchestrateur_nom:
                    continue
                m = mapping_complet.get(ag, "inherit")
                bloc_delegation += f"- `{ag}` : `Model=\"{m}\"`\n"
            bloc_delegation += "\n"

        if "### Modèles" in texte_orch:
            texte_orch = re.sub(r"### Modèles.*?(\n# |\Z)", bloc_delegation + r"\1", texte_orch, flags=re.DOTALL)
        elif "# Délégation" in texte_orch:
            texte_orch = texte_orch.replace("# Délégation", f"# Délégation\n\n{bloc_delegation}")

        orch_file.write_text(texte_orch, encoding="utf-8")
        rapport.ok(f"Prompt de `{orchestrateur_nom}` adapté aux {len(presents)} agent(s) actif(s).")

    # 3. Injection du tableau récapitulatif dans AGENTS.md / CLAUDE.md
    fichiers_doc = []
    if outil == "claude_code":
        fichiers_doc.append(racine / "CLAUDE.md")
    else:
        fichiers_doc.append(racine / "AGENTS.md")

    tableau_md = "## Matrice des Modèles IA Déployés\n\n"
    tableau_md += "| Agent | Rôle | Modèle LLM | Statut |\n"
    tableau_md += "|---|---|---|---|\n"
    for ag_name in sorted(presents):
        m = mapping_complet.get(ag_name, "inherit")
        desc = DESCRIPTIONS_AGENTS.get(ag_name, ag_name)
        tableau_md += f"| `{ag_name}` | {desc} | **`{m}`** | Actif |\n"
    tableau_md += "\n"

    for fdoc in fichiers_doc:
        if not fdoc.is_file():
            continue
        tdoc = fdoc.read_text(encoding="utf-8")
        if "## Matrice des Modèles IA Déployés" in tdoc:
            tdoc = re.sub(r"## Matrice des Modèles IA Déployés.*?(\n## |\Z)", tableau_md + r"\1", tdoc, flags=re.DOTALL)
        else:
            tdoc = tdoc.rstrip() + "\n\n" + tableau_md
        fdoc.write_text(tdoc, encoding="utf-8")
        rapport.ok(f"Matrice des agents actifs documentée dans {fdoc.name}.")

    # 4. Enregistrement dans .agents/cache/models.json ou .claude/cache/models.json
    cache_dir = racine_agents / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    fichier_json = cache_dir / "models.json"
    data = {
        "preset": preset,
        "active_agents": sorted(list(presents)),
        "models": mapping_complet,
        "updated_at": datetime.now().isoformat(),
        "tool": outil,
    }
    fichier_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    rapport.ok(f"{modifies} agent(s) configurés avec succès (cache: {fichier_json.name}).")

    return rapport


def synchroniser_agents_projet(racine: Path, famille: str = "code", target_tool: str = "antigravity",
                               agents_actifs: list[str] | set[str] | None = None,
                               modeles: dict[str, str] | None = None,
                               preset: str = "equilibre",
                               kit_source: Path | str | None = None,
                               rapport: Rapport | None = None) -> Rapport:
    """Synchronise l'arborescence des agents du projet :
    - Copie les agents activés depuis le kit de référence s'ils sont absents.
    - Supprime du projet les agents désactivés.
    - Applique les modèles LLM configurés et met à jour le prompt de l'orchestrateur et AGENTS.md / CLAUDE.md.
    """
    if rapport is None:
        rapport = Rapport()

    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]
    racine_agents = racine / dossier_nom
    if not racine_agents.is_dir():
        racine_agents = racine / ".agents" if (racine / ".agents").is_dir() else (racine / ".claude")

    dossier_agents = racine_agents / "agents"
    dossier_agents.mkdir(parents=True, exist_ok=True)

    # Récupération du kit source
    kit = Path(kit_source).resolve() if kit_source else kit_par_defaut(target_tool=outil)
    source_agents_dir = None
    if kit and est_un_kit(kit, target_tool=outil):
        source_sub = kit / dossier_nom / "agents"
        if not source_sub.is_dir():
            source_sub = kit / ".agents" / "agents" if (kit / ".agents" / "agents").is_dir() else (kit / ".claude" / "agents")
        if source_sub.is_dir():
            source_agents_dir = source_sub

    # Si aucun agents_actifs n'est passé, on prend la liste complète de la famille
    if agents_actifs is None:
        agents_actifs_set = set(liste_agents_famille(famille))
    else:
        agents_actifs_set = set(agents_actifs)

    # L'orchestrateur du mode est TOUJOURS obligatoire
    orch_map = {"code": "code-orchestrateur", "hw": "hw-orchestrateur", "meca": "meca-orchestrateur"}
    orchestrateur_nom = orch_map.get(famille, f"{famille}-orchestrateur")
    agents_actifs_set.add(orchestrateur_nom)

    # 1. Ajout / Restauration des agents activés depuis le kit source
    ajoutes = 0
    if source_agents_dir:
        for ag in sorted(agents_actifs_set):
            cible_agent = dossier_agents / ag
            if not cible_agent.is_dir():
                src_agent = source_agents_dir / ag
                if src_agent.is_dir():
                    shutil.copytree(src_agent, cible_agent)
                    ajoutes += 1
                    rapport.ok(f"Agent `{ag}` activé et installé depuis le kit.")

    # 2. Suppression des agents désactivés (sauf orchestrateur)
    retires = 0
    for ag_dir in list(dossier_agents.iterdir()):
        if not ag_dir.is_dir():
            continue
        if ag_dir.name not in agents_actifs_set and ag_dir.name != orchestrateur_nom:
            try:
                shutil.rmtree(ag_dir)
                retires += 1
                rapport.ok(f"Agent `{ag_dir.name}` désactivé et retiré du projet.")
            except Exception as e:
                rapport.alerte(f"Impossible de retirer l'agent {ag_dir.name} : {e}")

    # 3. Application des modèles, prompt de l'orchestrateur et AGENTS.md / CLAUDE.md
    appliquer_modeles_agents(racine, famille=famille, target_tool=outil, modeles=modeles,
                             preset=preset, agents_actifs=agents_actifs_set, rapport=rapport)

    rapport.ok(f"Synchronisation terminée : {len(agents_actifs_set)} agents actifs ({ajoutes} installés, {retires} retirés).")
    return rapport


def charger_modeles_projet(racine: Path, target_tool: str = "antigravity") -> dict:
    """Charge la configuration des modèles et agents actifs enregistrée dans le projet."""
    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]
    preset_defaut = PRESETS_MODELES_PAR_OUTIL.get(outil, PRESETS_MODELES_PAR_OUTIL["antigravity"])["equilibre"]

    for d in [racine / dossier_nom / "cache" / "models.json",
              racine / ".agents" / "cache" / "models.json",
              racine / ".claude" / "cache" / "models.json"]:
        if d.is_file():
            try:
                data = json.loads(d.read_text(encoding="utf-8"))
                return data
            except Exception:
                pass
    return {"preset": "equilibre", "models": preset_defaut["mapping"], "active_agents": None}


# --------------------------------------------------------------------------
# Point d'entrée Principal
# --------------------------------------------------------------------------


def preparer_projet(project_root, app_mode, target_tool: str = "antigravity",
                    kit_source=None, env_kicad=None, elaguer=True,
                    modeles: dict[str, str] | None = None,
                    preset_modeles: str = "equilibre",
                    agents_actifs: list[str] | set[str] | None = None):
    """Installe et adapte le kit d'agents dans `project_root` pour l'outil choisi.

    target_tool : "antigravity" (par défaut) ou "claude_code".
    Retourne un `Rapport` : `rapport.lignes` est prêt à être affiché,
    `rapport.succes` dit si tout est passé.
    """
    rapport = Rapport()
    outil = normaliser_outil(target_tool)

    famille = FAMILLES.get(app_mode)
    if famille is None:
        rapport.alerte("Mode inconnu : {!r}.".format(app_mode))
        return rapport

    racine = Path(project_root).resolve()
    if not racine.is_dir():
        rapport.alerte("Dossier projet introuvable : {}".format(racine))
        return rapport

    kit = Path(kit_source).resolve() if kit_source else kit_par_defaut(target_tool=outil)
    if kit is None or not est_un_kit(kit, target_tool=outil):
        nom_outil = OUTILS_CIBLES[outil]["nom"]
        rapport.alerte(
            f"Kit d'agents introuvable pour {nom_outil}. Place le dossier contenant "
            f"le kit dans « kit_agents/{OUTILS_CIBLES[outil]['sous_dossier_kit']} » ou "
            f"dans ~/.latelier/kit."
        )
        return rapport

    try:
        _copier_kit(kit, racine, famille, outil, rapport, elaguer=elaguer)
        _nettoyer_table_commandes(racine, outil, rapport)
        _marquer_mode(racine, famille, outil, rapport)
        _creer_dossiers(racine, famille, outil, rapport)
        synchroniser_agents_projet(racine, famille=famille, target_tool=outil,
                                   agents_actifs=agents_actifs, modeles=modeles,
                                   preset=preset_modeles, kit_source=kit,
                                   rapport=rapport)
        _gitignore(racine, famille, rapport)
        _adapter_hooks(racine, outil, rapport)
        _ecrire_env(racine, env_kicad or {}, famille, outil, rapport, bloquant=False)
        if famille == "hw":
            _index_kicad(racine, env_kicad or {}, outil, rapport, bloquant=False)
    except (OSError, shutil.Error) as err:
        rapport.alerte("Préparation interrompue : {}".format(err))

    return rapport


def mettre_a_jour_env(project_root, env_kicad=None, famille=None, target_tool=None):
    """Réenregistre l'environnement KiCad et reconstruit l'index."""
    rapport = Rapport()
    racine = Path(project_root).resolve()

    if target_tool is None:
        if (racine / ".claude").is_dir():
            target_tool = "claude_code"
        else:
            target_tool = "antigravity"
    outil = normaliser_outil(target_tool)
    dossier_nom = OUTILS_CIBLES[outil]["dossier_agents"]

    if not (racine / dossier_nom).is_dir() and not (racine / ".agents").is_dir():
        rapport.alerte(
            f"Pas de dossier d'agents dans {racine.name} : rien à mettre à jour."
        )
        return rapport

    if famille is None:
        famille = "hw"
        for md_name in ["CLAUDE.md", "AGENTS.md"]:
            marqueur = racine / md_name
            if marqueur.is_file():
                tete = marqueur.read_text(encoding="utf-8", errors="ignore")[:300]
                for f in FAMILLES.values():
                    if "mode-atelier: " + f in tete:
                        famille = f
                        break

    _ecrire_env(racine, env_kicad or {}, famille, outil, rapport)
    if famille == "hw":
        _index_kicad(racine, env_kicad or {}, outil, rapport)
    return rapport


def main(argv):
    if len(argv) < 3:
        print("\n=== L'Atelier — Préparation d'un dossier projet ===")
        dossier = input("Chemin du dossier projet : ").strip().strip('"')
        if not dossier:
            print("Chemin requis.")
            return 2
        
        print("\nChoisissez le mode :")
        print("  1. Coder (logiciel Python)")
        print("  2. Hardware (carte électronique KiCad/SKiDL)")
        print("  3. Méca (pièce 3D CadQuery)")
        choix_mode = input("Votre choix [1/2/3] (défaut: 1) : ").strip()
        mode_map = {"1": "coder", "2": "hardware", "3": "meca", "": "coder"}
        app_mode = mode_map.get(choix_mode, "coder")

        print("\nChoisissez l'outil IA cible :")
        print("  1. Antigravity (Gemini) [.agents/]")
        print("  2. Claude Code (Claude) [.claude/]")
        choix_outil = input("Votre choix [1/2] (défaut: 1) : ").strip()
        target_tool = "claude_code" if choix_outil == "2" else "antigravity"

        rapport = preparer_projet(dossier, app_mode, target_tool=target_tool)
        print("\n--- Résultat de la préparation ---")
        for ligne in rapport.lignes:
            print(ligne)
        return 0 if rapport.succes else 1

    dossier_projet = argv[1]
    app_mode = argv[2]
    
    target_tool = "antigravity"
    kit = None

    if len(argv) > 3:
        arg3 = argv[3].lower()
        if arg3 in ("antigravity", "claude_code", "claude", "gemini"):
            target_tool = "claude_code" if "claude" in arg3 else "antigravity"
            if len(argv) > 4:
                kit = argv[4]
        else:
            kit = argv[3]

    rapport = preparer_projet(dossier_projet, app_mode, target_tool=target_tool, kit_source=kit)
    for ligne in rapport.lignes:
        print(ligne)
    return 0 if rapport.succes else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
