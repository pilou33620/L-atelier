"""
Préparation d'un dossier projet pour Antigravity — « L'Atelier ».

Ce module est le chaînon manquant entre l'outil Python et le kit d'agents :
quand tu crées un projet dans le lanceur, il installe dans le dossier tout ce
que les agents attendent d'y trouver, et rien de plus.

Ce qu'il fait, dans l'ordre :

1. copie `AGENTS.md` et `.agents/` depuis le kit de référence (sans jamais
   écraser un `AGENTS.md` existant) ;
2. élague les deux familles d'agents inutiles au mode choisi, ainsi que leurs
   workflows, skills et scripts ;
3. crée les dossiers attendus (`.agent_reports/`, `data_sheets/`,
   `kicad_libs/`, `pieces/`, `tests/` selon le mode) ;
4. complète le `.gitignore` ;
5. adapte `.agents/hooks.json` à l'interpréteur réellement présent (`python`
   sous Windows, `python3` ailleurs) — sinon le garde-fou ne se déclenche
   jamais ;
6. écrit `.agents/cache/env.json` + `.agents/scripts/run_projet.py`, pour que
   les agents puissent exécuter un script SKiDL ou CadQuery avec les mêmes
   variables d'environnement KiCad que l'outil ;
7. en mode hardware, construit l'index KiCad (`kicad_search.py --index`) pour
   que les agents n'aient jamais à sortir du workspace.

Usage depuis ui.py :

    from scaffold_projet import preparer_projet

    rapport = preparer_projet(project_path, app_mode,
                              kit_source=CHEMIN_DU_KIT,
                              env_kicad={"KICAD8_SYMBOL_DIR": ...})
    for ligne in rapport.lignes:
        self.add_system_message(ligne)

Utilisable aussi en ligne de commande :

    python scaffold_projet.py <dossier_projet> <coder|hardware|meca> [kit]
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Table de correspondance mode de l'outil -> famille d'agents du kit
# --------------------------------------------------------------------------

FAMILLES = {"coder": "code", "hardware": "hw", "meca": "meca"}

SKILLS_PAR_FAMILLE = {
    "code": ["protocole-multi-agents", "verification-python", "graphify-graph"],
    "hw": ["protocole-multi-agents", "verification-python", "skidl-kicad",
           "datasheets-json"],
    "meca": ["protocole-multi-agents", "verification-python",
             "cadquery-parametrique"],
}

SCRIPTS_PAR_FAMILLE = {
    "code": ["run_projet.py", "graph_query.py"],
    "hw": ["run_projet.py", "kicad_search.py", "kicad_fetch_part.py",
           "pcbparts.py"],
    "meca": ["run_projet.py", "cq_check.py"],
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
    "graphify-out/",
    ".skidl_search_tmp.py",
]

IGNORE_PAR_FAMILLE = {
    "code": [],
    # Sous-produits SKiDL, regenerables a chaque execution du script.
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
   sur une librairie de symboles introuvable. On relit .agents/cache/env.json et
   on les reinjecte.

2. SKiDL nomme ses fichiers de sortie (.erc, .log, _sklib.py) d'apres le script
   de PLUS HAUT NIVEAU de la pile d'appels. Executer le script cible depuis ce
   wrapper avec runpy ou exec laissait donc des fichiers appeles
   « run_projet.erc », « run_projet.log » a la racine du projet. On lance donc un
   VRAI sous-processus : le script cible redevient le script de plus haut niveau,
   et ses sorties portent son nom.

Les sous-produits SKiDL sont ensuite ranges a cote du script, dans circuits/.

    python .agents/scripts/run_projet.py circuits/carte-capteur.py
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CONFIG = RACINE / ".agents" / "cache" / "env.json"

# Sous-produits que SKiDL depose dans le repertoire courant, nommes d'apres le
# script. Le netlist n'y figure pas : le script doit le placer lui-meme avec
# generate_netlist(file_=...).
SUFFIXES = (".erc", ".log", "_sklib.py")


def environnement():
    env = dict(os.environ)
    if not CONFIG.is_file():
        print(
            "Aucun .agents/cache/env.json : execution avec l'environnement brut. "
            "Si SKiDL ne trouve pas ses librairies, relancer la preparation du "
            "projet depuis L'Atelier.",
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


def est_un_kit(dossier):
    """Un kit, c'est un dossier qui contient AGENTS.md ET .agents/."""
    try:
        dossier = Path(dossier)
        return (dossier / "AGENTS.md").is_file() and (dossier / ".agents").is_dir()
    except OSError:
        return False


def emplacements_kit():
    """Emplacements consultés, dans l'ordre, pour trouver le kit d'agents.

    La racine de l'outil vient en premier : y déposer AGENTS.md et .agents/
    directement est le réflexe naturel quand on décompresse l'archive, et ça
    doit marcher.
    """
    base = Path(__file__).resolve().parent
    candidats = [
        base,
        base / "kit_agents",
        base / "agents-3-modes",
        base / "agents-3-modes-corrige",
        base.parent / "kit_agents",
        Path.home() / ".latelier" / "kit",
    ]
    # Puis n'importe quel sous-dossier de premier niveau qui ressemble à un kit
    # (cas d'une archive décompressée dans un dossier au nom quelconque).
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


def kit_par_defaut():
    """Premier emplacement contenant un kit, ou None."""
    for c in emplacements_kit():
        if est_un_kit(c):
            return c
    return None


# --------------------------------------------------------------------------
# Étapes
# --------------------------------------------------------------------------


def _empreinte(chemin: Path):
    """Empreinte du contenu d'un fichier, pour reconnaître la version du kit."""
    try:
        return hashlib.sha256(chemin.read_bytes()).hexdigest()
    except OSError:
        return ""


def _enregistrer_empreinte(racine: Path, kit: Path):
    cache = racine / ".agents" / "cache"
    try:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "kit.json").write_text(
            json.dumps({"agents_md": _empreinte(kit / "AGENTS.md"),
                        "source": str(kit)}, indent=2),
            encoding="utf-8")
    except OSError:
        pass


def _empreinte_enregistree(racine: Path):
    fichier = racine / ".agents" / "cache" / "kit.json"
    try:
        return json.loads(fichier.read_text(encoding="utf-8")).get("agents_md", "")
    except (OSError, ValueError):
        return ""


def _filtre_copie(kit: Path, famille: str):
    """Construit le filtre `ignore` de copytree.

    On ne copie QUE la famille demandée, au lieu de tout copier puis d'effacer
    le reste : sous Windows, supprimer des fichiers fraîchement copiés déclenche
    une demande de droits administrateur. Aucune suppression n'a lieu.
    """
    autres = [f for f in FAMILLES.values() if f != famille]
    skills = set(SKILLS_PAR_FAMILLE[famille])
    scripts = set(SCRIPTS_PAR_FAMILLE[famille])
    source_agents = (kit / ".agents").resolve()

    def ignorer(dossier, noms):
        try:
            relatif = Path(dossier).resolve().relative_to(source_agents).as_posix()
        except ValueError:
            relatif = ""
        exclus = {n for n in noms if n == "__pycache__" or n.endswith(".pyc")}

        if relatif == "agents":
            exclus |= {n for n in noms
                       if any(n.startswith(a + "-") for a in autres)}
        elif relatif == "workflows":
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


def _copier_kit(kit: Path, racine: Path, famille: str, rapport: Rapport,
                elaguer: bool = True):
    cible_agents = racine / ".agents"
    if cible_agents.exists():
        rapport.info(".agents/ déjà présent : conservé tel quel, rien n'est "
                     "supprimé.")
        _signaler_familles_en_trop(cible_agents, famille, rapport)
    else:
        filtre = _filtre_copie(kit, famille) if elaguer else None
        shutil.copytree(kit / ".agents", cible_agents, ignore=filtre)
        nb = len(list((cible_agents / "agents").glob("*/"))) \
            if (cible_agents / "agents").is_dir() else 0
        rapport.ok(".agents/ installé — {} agents de la famille « {} » "
                   "(les autres familles ne sont pas copiées).".format(nb, famille))

    cible_md = racine / "AGENTS.md"
    if cible_md.exists():
        # Le fichier du projet porte l'en-tête de mode ajouté à la préparation :
        # on compare hors en-tête pour ne pas signaler une différence qu'on a
        # créée soi-même, et pour ne pas semer un AGENTS.md.nouveau à chaque
        # relance.
        if _empreinte(kit / "AGENTS.md") == _empreinte_enregistree(racine):
            rapport.info("AGENTS.md déjà issu de cette version du kit.")
        else:
            secours = racine / "AGENTS.md.nouveau"
            shutil.copy2(kit / "AGENTS.md", secours)
            rapport.alerte(
                "AGENTS.md existe déjà et diffère du kit : la version du kit a "
                "été écrite à côté, dans AGENTS.md.nouveau. Rien n'a été "
                "écrasé — fusionne à la main si besoin."
            )
    else:
        shutil.copy2(kit / "AGENTS.md", cible_md)
        _enregistrer_empreinte(racine, kit)
        rapport.ok("AGENTS.md installé.")


def _signaler_familles_en_trop(dossier_agents: Path, famille: str,
                               rapport: Rapport):
    """Signale les agents des autres familles SANS rien supprimer.

    Sur un projet qui a déjà son .agents/, on ne touche à rien : c'est peut-être
    volontaire, et supprimer le travail de quelqu'un n'est pas le rôle d'un
    outil de préparation.
    """
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


def _nettoyer_table_commandes(racine: Path, rapport: Rapport):
    """Retire du tableau d'AGENTS.md les commandes dont le script a été élagué.

    AGENTS.md se présente comme la seule source autorisée pour les commandes de
    vérification : y laisser une ligne qui pointe vers un fichier absent envoie
    l'agent droit sur une erreur d'exécution.
    """
    md = racine / "AGENTS.md"
    dossier = racine / ".agents" / "scripts"
    if not md.is_file() or not dossier.is_dir():
        return
    presents = {p.name for p in dossier.glob("*.py")}
    lignes, retirees = [], 0
    for ligne in md.read_text(encoding="utf-8").splitlines(keepends=True):
        if ligne.lstrip().startswith("|") and ".agents/scripts/" in ligne:
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
        rapport.ok("{} commande(s) obsolète(s) retirée(s) d'AGENTS.md.".format(retirees))


def _marquer_mode(racine: Path, famille: str, rapport: Rapport):
    """Écrit en tête d'AGENTS.md le mode réellement installé.

    Sans ça, AGENTS.md continue d'annoncer trois familles d'agents dont deux
    n'existent plus dans le dossier : l'orchestrateur cherche des sous-agents
    absents et termine sur BLOQUE.
    """
    md = racine / "AGENTS.md"
    if not md.is_file():
        return
    texte = md.read_text(encoding="utf-8")
    if "<!-- mode-atelier:" in texte:
        return
    principal = {"code": "code-orchestrateur", "hw": "hw-orchestrateur",
                 "meca": "meca-orchestrateur"}[famille]
    entete = (
        "<!-- mode-atelier: {famille} -->\n\n"
        "> **Mode installé dans ce projet : `{famille}`.** Les deux autres\n"
        "> familles d'agents ont été retirées par L'Atelier lors de la création du\n"
        "> projet. L'agent principal à ouvrir est **`{principal}`** ; les tableaux\n"
        "> ci-dessous qui décrivent les autres modes ne s'appliquent pas ici.\n\n"
    ).format(famille=famille, principal=principal)
    md.write_text(entete + texte, encoding="utf-8")
    rapport.ok("Mode « {} » marqué en tête d'AGENTS.md.".format(famille))


def _creer_dossiers(racine: Path, famille: str, rapport: Rapport):
    for nom in DOSSIERS_PAR_FAMILLE[famille]:
        (racine / nom).mkdir(parents=True, exist_ok=True)
    (racine / ".agents" / "cache").mkdir(parents=True, exist_ok=True)
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


def _adapter_hooks(racine: Path, rapport: Rapport):
    """`python3` n'existe pas sous Windows : le hook échouerait en silence."""
    chemin = racine / ".agents" / "hooks.json"
    if not chemin.is_file():
        rapport.alerte(".agents/hooks.json absent : le garde-fou n'est pas installé.")
        return

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

    brut = chemin.read_text(encoding="utf-8")
    remplace = brut.replace("python3 .agents/hooks/garde_fou.py",
                            interpreteur + " .agents/hooks/garde_fou.py")
    remplace = remplace.replace("python .agents/hooks/garde_fou.py",
                                interpreteur + " .agents/hooks/garde_fou.py")
    if remplace != brut:
        chemin.write_text(remplace, encoding="utf-8")
        rapport.ok("Garde-fou câblé sur « {} ».".format(interpreteur))
    else:
        rapport.info("Garde-fou déjà câblé sur « {} ».".format(interpreteur))


def _ecrire_env(racine: Path, env_kicad: dict, famille: str, rapport: Rapport,
                bloquant: bool = True):
    """Rend l'environnement de l'outil rejouable par les agents."""
    cache = racine / ".agents" / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    valeurs = {}
    interessantes = ("KICAD", "SKIDL")
    for cle, val in os.environ.items():
        if any(cle.startswith(p) for p in interessantes):
            valeurs[cle] = val
    valeurs.update({k: v for k, v in (env_kicad or {}).items() if v})

    if valeurs:
        (cache / "env.json").write_text(
            json.dumps(valeurs, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        rapport.ok("{} variables d'environnement enregistrées dans "
                   ".agents/cache/env.json.".format(len(valeurs)))
    elif famille == "hw":
        message = ("Chemins KiCad pas encore connus : ils sont demandés à "
                   "l'ouverture de la fenêtre, et l'environnement sera écrit à "
                   "ce moment-là.")
        rapport.alerte(message) if bloquant else rapport.attente(message)

    wrapper = racine / ".agents" / "scripts" / "run_projet.py"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    if not wrapper.is_file():
        wrapper.write_text(RUN_PROJET, encoding="utf-8")
        rapport.ok(".agents/scripts/run_projet.py installé.")

    _declarer_commande(racine, rapport)


def _declarer_commande(racine: Path, rapport: Rapport):
    """Ajoute le wrapper au tableau des commandes de vérification d'AGENTS.md.

    AGENTS.md se déclare « seule source autorisée » pour les commandes : un
    outil que les agents doivent utiliser mais qui n'y figure pas ne sera pas
    utilisé.
    """
    md = racine / "AGENTS.md"
    if not md.is_file():
        return
    texte = md.read_text(encoding="utf-8")
    if "run_projet.py" in texte:
        return
    ancre = "| Diff en cours |"
    ligne = ("| Exécution d'un script du projet | "
             "`python .agents/scripts/run_projet.py <script.py>` |\n")
    if ancre in texte:
        avant, apres = texte.split(ancre, 1)
        fin_ligne = apres.index("\n") + 1
        texte = avant + ancre + apres[:fin_ligne] + ligne + apres[fin_ligne:]
        md.write_text(texte, encoding="utf-8")
        rapport.ok("Commande d'exécution déclarée dans AGENTS.md.")


def _index_kicad(racine: Path, env_kicad: dict, rapport: Rapport,
                 bloquant: bool = True):
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
        # Index vide faute de chemins : normal à la création du projet.
        rapport.attente("Index KiCad à construire une fois les chemins KiCad "
                        "renseignés.")
    else:
        rapport.alerte(
            "Index KiCad non construit (code {}). Sans lui les agents "
            "s'arrêteront sur BLOQUE au lieu d'inventer des empreintes.\n{}"
            .format(proc.returncode, detail))


# --------------------------------------------------------------------------
# Point d'entrée
# --------------------------------------------------------------------------


def preparer_projet(project_root, app_mode, kit_source=None, env_kicad=None,
                    elaguer=True):
    """Installe et adapte le kit d'agents dans `project_root`.

    Retourne un `Rapport` : `rapport.lignes` est prêt à être affiché,
    `rapport.succes` dit si tout est passé.
    """
    rapport = Rapport()

    famille = FAMILLES.get(app_mode)
    if famille is None:
        rapport.alerte("Mode inconnu : {!r}.".format(app_mode))
        return rapport

    racine = Path(project_root).resolve()
    if not racine.is_dir():
        rapport.alerte("Dossier projet introuvable : {}".format(racine))
        return rapport

    kit = Path(kit_source).resolve() if kit_source else kit_par_defaut()
    if kit is None or not (kit / "AGENTS.md").is_file():
        rapport.alerte(
            "Kit d'agents introuvable. Place le dossier contenant AGENTS.md et "
            ".agents/ à côté de l'outil (dossier « kit_agents ») ou dans "
            "~/.latelier/kit."
        )
        return rapport

    try:
        _copier_kit(kit, racine, famille, rapport, elaguer=elaguer)
        _nettoyer_table_commandes(racine, rapport)
        _marquer_mode(racine, famille, rapport)
        _creer_dossiers(racine, famille, rapport)
        _gitignore(racine, famille, rapport)
        _adapter_hooks(racine, rapport)
        _ecrire_env(racine, env_kicad or {}, famille, rapport, bloquant=False)
        if famille == "hw":
            _index_kicad(racine, env_kicad or {}, rapport, bloquant=False)
    except (OSError, shutil.Error) as err:
        rapport.alerte("Préparation interrompue : {}".format(err))

    return rapport


def mettre_a_jour_env(project_root, env_kicad=None, famille=None):
    """Réenregistre l'environnement KiCad et reconstruit l'index.

    À appeler quand l'utilisateur vient de renseigner les chemins KiCad dans
    l'outil : au moment de la création du projet, ces chemins n'étaient pas
    encore connus, donc `env.json` était vide et l'index absent.
    """
    rapport = Rapport()
    racine = Path(project_root).resolve()
    if not (racine / ".agents").is_dir():
        rapport.alerte(
            "Pas de .agents/ dans {} : rien à mettre à jour.".format(racine.name)
        )
        return rapport

    if famille is None:
        marqueur = racine / "AGENTS.md"
        famille = "hw"
        if marqueur.is_file():
            tete = marqueur.read_text(encoding="utf-8", errors="ignore")[:200]
            for f in FAMILLES.values():
                if "mode-atelier: " + f in tete:
                    famille = f
                    break

    _ecrire_env(racine, env_kicad or {}, famille, rapport)
    if famille == "hw":
        _index_kicad(racine, env_kicad or {}, rapport)
    return rapport


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    kit = argv[3] if len(argv) > 3 else None
    rapport = preparer_projet(argv[1], argv[2], kit_source=kit)
    for ligne in rapport.lignes:
        print(ligne)
    return 0 if rapport.succes else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
