import os
import sys
import re
import html
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTextEdit, QComboBox, QPushButton, QFileDialog, QMessageBox,
                             QFrame, QSplitter, QTreeView, QPlainTextEdit, QCheckBox,
                             QScrollArea, QTabWidget, QLineEdit, QApplication,
                             QDialog, QRadioButton, QDialogButtonBox, QInputDialog, QButtonGroup, QMenu, QListWidget, QProgressBar,
                             QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import Qt, QTimer, QSettings, QFileSystemWatcher, pyqtSignal, QRectF
from PyQt6.QtGui import QFileSystemModel, QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QAction
import subprocess
import threading
import json
import urllib.request
import shutil
from datetime import datetime

try:
    import docker
    import requests
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

# Préparation du dossier projet pour les agents Antigravity : copie du kit,
# élagage au mode choisi, index KiCad, environnement rejouable. Import tolérant,
# l'outil doit rester utilisable si le module n'est pas déployé.
try:
    from scaffold_projet import (preparer_projet, mettre_a_jour_env,
                                 kit_par_defaut, emplacements_kit, est_un_kit,
                                 OUTILS_CIBLES)
    SCAFFOLD_AVAILABLE = True
except ImportError:
    SCAFFOLD_AVAILABLE = False
    OUTILS_CIBLES = {
        "antigravity": {"nom": "Antigravity (Gemini)", "dossier_agents": ".agents"},
        "claude_code": {"nom": "Claude Code (Claude)", "dossier_agents": ".claude"},
    }

    def kit_par_defaut(target_tool="antigravity"):
        return None

    def emplacements_kit(target_tool="antigravity"):
        return []

    def est_un_kit(_, target_tool="antigravity"):
        return False

# Client pcbparts.dev : recherche, tarifs, modèles KiCad. Les appels réseau se
# font ICI et déposent des fichiers dans le projet ; les agents ne sortent
# jamais sur le réseau, ils lisent ce qui a été déposé.
try:
    import pcbparts
    PCBPARTS_AVAILABLE = True
except ImportError:
    PCBPARTS_AVAILABLE = False

def resolve_external_binary(name):
    """Résout le chemin ABSOLU d'un binaire externe via le PATH de
    l'APPLICATION (jamais via le répertoire du projet)."""
    return shutil.which(name)

def hardened_subprocess_env(base_env=None):
    """Environnement durci pour les sous-processus lancés avec
    cwd = racine du projet."""
    env = dict(base_env if base_env is not None else os.environ)
    env["NoDefaultCurrentDirectoryInExePath"] = "1"
    return env

class FileSandbox:
    _file_lock = threading.Lock()
    MAX_FILE_CHARS = 30000

    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(f"{root} n'est pas un dossier")
        self.backup_dir = self.root / ".agent_backups"

    def _safe_path(self, user_path, write_mode=False):
        """Resolves path nativement sans restrictions."""
        return (self.root / user_path).resolve(strict=False)

    def _backup_file(self, target):
        """Sauvegarde une copie du fichier avant écriture et nettoie les anciens backups."""
        if target.exists() and target.is_file():
            if not self.backup_dir.exists():
                try:
                    self.backup_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_name = f"{target.name}_{timestamp}.bak"
            try:
                shutil.copy2(target, self.backup_dir / backup_name)
                
                # Purge (on garde les 20 plus récents pour ce fichier spécifique)
                backups = sorted(self.backup_dir.glob(f"{target.name}_*.bak"), key=os.path.getmtime)
                if len(backups) > 20:
                    for old_bak in backups[:-20]:
                        old_bak.unlink(missing_ok=True)
            except Exception as e:
                raise RuntimeError(f"Échec de la sauvegarde de {target.name} : {e}")

    def write_file(self, path, content):
        with self._file_lock:
            target = self._safe_path(path, write_mode=True)
                
            self._backup_file(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            if hasattr(os, 'O_NOFOLLOW'):
                flags |= os.O_NOFOLLOW
                
            fd = os.open(target, flags, 0o666)
            try:
                f = open(fd, 'w', encoding="utf-8")
            except Exception:
                os.close(fd)
                raise
            with f:
                f.write(content)

    def delete_file(self, path):
        with self._file_lock:
            target = self._safe_path(path, write_mode=True)
            if not target.exists():
                raise FileNotFoundError(f"Fichier introuvable : {path}")
            self._backup_file(target)
            target.unlink()

    def graphify_build(self, target_dir=".", code_only=True):
        """Construit ou met à jour le graphe structurel Graphify (graph.json)."""
        graphify_bin = resolve_external_binary("graphify")
        if not graphify_bin:
            return ("Impossible de lancer graphify : binaire introuvable sur "
                    "le PATH de l'application. Assurez-vous qu'il est installé.")
        try:
            cmd = [graphify_bin, target_dir, "--out", "."]
            if code_only:
                cmd.append("--code-only")
            env = hardened_subprocess_env()

            proc = subprocess.run(
                cmd,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=600,
                env=env
            )
            if proc.returncode == 0:
                # Le build structurel ne produit pas GRAPH_REPORT.md, que tous
                # les agents du mode code doivent lire en premier.
                resume = self.ecrire_rapport_graphe()
                return (f"Graphe Graphify généré avec succès pour '{target_dir}' dans "
                        f"'graphify-out/'.\n{resume}")
            else:
                return f"Erreur lors de la génération du graphe:\n{proc.stderr or ''}"
        except Exception as e:
            return f"Impossible de lancer graphify : {e}. Assurez-vous qu'il est installé."

    def ecrire_rapport_graphe(self):
        """Produit graphify-out/GRAPH_REPORT.md à partir de graph.json.

        Tous les agents du mode code ont pour consigne de lire ce fichier EN
        PREMIER, et c'est le seul accès au graphe de `code-orchestrateur`, qui
        n'a pas le droit d'exécuter de commande. Le build `--code-only` ne le
        produit pas : sans ce repli, le premier réflexe prescrit à tout le mode
        code échoue.

        Ce rapport est volontairement factuel (comptages, god nodes, fichiers
        les plus reliés) : il ne prétend pas remplacer l'analyse sémantique de
        Graphify, et le dit en clair dans son en-tête.
        """
        sortie = self.root / "graphify-out"
        graphe = sortie / "graph.json"
        if not graphe.is_file():
            return "Aucun graph.json : rien à résumer."

        try:
            brut = json.loads(graphe.read_text(encoding="utf-8"))
        except (ValueError, OSError) as err:
            return f"graph.json illisible : {err}"

        racine = brut
        if isinstance(brut, dict):
            for enveloppe in ("graph", "data", "result"):
                interne = brut.get(enveloppe)
                if isinstance(interne, dict) and any(
                        k in interne for k in ("nodes", "vertices", "entities")):
                    racine = interne
                    break

        def premiere(dico, cles, defaut=""):
            for c in cles:
                v = dico.get(c) if isinstance(dico, dict) else None
                if v not in (None, ""):
                    return v if isinstance(v, str) else str(v)
            return defaut

        noeuds_bruts = None
        for cle in ("nodes", "vertices", "entities", "symbols"):
            if isinstance(racine, dict) and racine.get(cle):
                noeuds_bruts = racine[cle]
                break
        if noeuds_bruts is None:
            return "Schéma de graph.json non reconnu : pas de liste de noeuds."
        if isinstance(noeuds_bruts, dict):
            noeuds_bruts = [dict(v, id=k) if isinstance(v, dict) else {"id": k}
                            for k, v in noeuds_bruts.items()]

        aretes_brutes = []
        for cle in ("edges", "links", "relationships", "relations"):
            if isinstance(racine, dict) and racine.get(cle):
                aretes_brutes = racine[cle]
                break

        noeuds = {}
        for nd in noeuds_bruts:
            if not isinstance(nd, dict):
                continue
            ident = premiere(nd, ("id", "name", "label", "key", "qualified_name"))
            if not ident:
                continue
            noeuds[ident] = {
                "type": premiere(nd, ("type", "kind", "category", "node_type"), "?"),
                "fichier": premiere(nd, ("file", "path", "filepath", "file_path",
                                         "source_file")),
            }

        degres = {}
        relations = {}
        confiances = {}
        for ar in aretes_brutes:
            if not isinstance(ar, dict):
                continue
            src = premiere(ar, ("source", "from", "src", "start", "subject"))
            dst = premiere(ar, ("target", "to", "dst", "end", "object"))
            if not src or not dst:
                continue
            degres[src] = degres.get(src, 0) + 1
            degres[dst] = degres.get(dst, 0) + 1
            rel = premiere(ar, ("type", "label", "relation", "kind"), "?")
            relations[rel] = relations.get(rel, 0) + 1
            conf = premiere(ar, ("confidence", "tag", "provenance", "origin"), "?")
            confiances[conf] = confiances.get(conf, 0) + 1

        types = {}
        fichiers = {}
        for ident, nd in noeuds.items():
            types[nd["type"]] = types.get(nd["type"], 0) + 1
            if nd["fichier"]:
                fichiers[nd["fichier"]] = fichiers.get(nd["fichier"], 0) + \
                    degres.get(ident, 0)

        def tableau(titre, dico, limite=15):
            lignes = [f"### {titre}", "", "| Élément | Nombre |", "|---|---|"]
            for cle, val in sorted(dico.items(), key=lambda x: -x[1])[:limite]:
                lignes.append(f"| `{cle}` | {val} |")
            lignes.append("")
            return lignes

        horodatage = datetime.fromtimestamp(graphe.stat().st_mtime)
        lignes = [
            "# GRAPH_REPORT.md",
            "",
            f"<!-- généré par L'Atelier depuis graph.json le "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')} -->",
            "",
            "> **Rapport factuel, pas une analyse sémantique.** Il est calculé "
            "directement depuis `graph.json` : comptages, éléments les plus "
            "connectés, fichiers les plus reliés. Il ne contient ni "
            "interprétation ni détection de composants logiques.",
            "",
            f"- Graphe daté du : **{horodatage.strftime('%Y-%m-%d %H:%M')}**",
            f"- Noeuds : **{len(noeuds)}**",
            f"- Relations : **{sum(relations.values())}**",
            "",
            "Si ce graphe est plus ancien que les dernières modifications du "
            "code, il reste fiable pour la cartographie générale, pas pour les "
            "signatures ni la liste exacte des appelants.",
            "",
        ]
        lignes += tableau("Types de noeuds", types)
        lignes += tableau("Types de relations", relations)
        lignes += tableau("Confiance des relations", confiances, limite=8)

        lignes += ["### God nodes (les plus connectés)", "",
                   "| Liens | Élément | Type | Fichier |", "|---|---|---|---|"]
        for ident, deg in sorted(degres.items(), key=lambda x: -x[1])[:20]:
            info = noeuds.get(ident, {"type": "?", "fichier": ""})
            lignes.append(f"| {deg} | `{ident}` | {info['type']} | "
                          f"{info['fichier']} |")
        lignes += ["",
                   "Ces éléments sont les abstractions centrales : toute "
                   "modification de leur signature se propage largement. "
                   "Vérifier les appelants avec "
                   "`graph_query.py callers \"<nom>\"` avant d'y toucher.",
                   ""]

        lignes += ["### Fichiers les plus reliés", "",
                   "| Liens cumulés | Fichier |", "|---|---|"]
        for fic, poids in sorted(fichiers.items(), key=lambda x: -x[1])[:20]:
            lignes.append(f"| {poids} | `{fic}` |")
        lignes.append("")

        try:
            sortie.mkdir(parents=True, exist_ok=True)
            (sortie / "GRAPH_REPORT.md").write_text("\n".join(lignes),
                                                    encoding="utf-8")
        except OSError as err:
            return f"Impossible d'écrire GRAPH_REPORT.md : {err}"
        return (f"GRAPH_REPORT.md écrit : {len(noeuds)} noeuds, "
                f"{sum(relations.values())} relations.")

    def run_python_script(self, script_path, timeout=60):
        """Exécute un script Python dans l'environnement du projet."""
        target = self._safe_path(script_path, write_mode=False)
        if not target.exists():
            return f"ÉCHEC : Le fichier {script_path} n'existe pas."
            
        fallback = True
        if DOCKER_AVAILABLE:
            try:
                client = docker.from_env()
                client.ping()
                
                # Chemin relatif pour le script monté dans le volume
                rel_script = target.relative_to(self.root).as_posix()
                
                # Installation des requirements si présents, puis exécution
                command = f'bash -c "if [ -f requirements.txt ]; then pip install -q -r requirements.txt; fi && python {rel_script}"'
                
                container = client.containers.run(
                    "python:3.10-slim",
                    command=command,
                    volumes={str(self.root): {'bind': '/project', 'mode': 'rw'}},
                    working_dir="/project",
                    network_disabled=False, # Requis pour pip install
                    detach=True
                )
                
                try:
                    result = container.wait(timeout=timeout)
                    output = container.logs().decode('utf-8', errors='replace').strip()
                    container.remove(force=True)
                    returncode = result.get('StatusCode', 1)
                    
                    if not output:
                        output = "(aucune sortie)"
                        
                    if len(output) > 8000:
                        half = 4000
                        output = (output[:half] + "\n... [sortie tronquée au milieu] ...\n" + output[-half:])
                        
                    status = "SUCCÈS" if returncode == 0 else f"ÉCHEC (code retour {returncode})"
                    return f"Exécution (Docker) de {target.name} : {status}\n--- SORTIE ---\n{output}"
                    
                except requests.exceptions.ReadTimeout:
                    container.stop(timeout=1)
                    container.remove(force=True)
                    return f"ÉCHEC : l'exécution (Docker) a dépassé le délai de {timeout}s."
            except Exception as e:
                logger.warning(f"[SANDBOX] Erreur Docker, repli sur sous-processus local: {e}")
                fallback = True
                
        if fallback:
            bootstrap_code = f"""
import sys, runpy

try:
    runpy.run_path(r'{target.as_posix()}', run_name='__main__')
except SystemExit:
    pass
except Exception as e:
    import traceback
    traceback.print_exc()
"""
            argv = [sys.executable, "-c", bootstrap_code]
            try:
                proc = subprocess.run(
                    argv, cwd=self.root, capture_output=True, text=True,
                    timeout=timeout, env=hardened_subprocess_env(),
                )
            except subprocess.TimeoutExpired:
                return f"ÉCHEC : l'exécution a dépassé le délai de {timeout}s."
            except Exception as e:
                return f"ÉCHEC : impossible de lancer le script ({e})."
    
            output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
            if not output:
                output = "(aucune sortie)"
                
            if len(output) > 8000:
                half = 4000
                output = (output[:half]
                          + "\n... [sortie tronquée au milieu] ...\n"
                          + output[-half:])
                
            status = "SUCCÈS" if proc.returncode == 0 else f"ÉCHEC (code retour {proc.returncode})"
            return f"Exécution de {target.name} : {status}\n--- SORTIE ---\n{output}"

    def search_mcp_pcbparts(self, query, limit=5):
        """Recherche un composant sur pcbparts.dev (MCP)."""
        import urllib.request
        import json
        
        url = "https://pcbparts.dev/mcp"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "jlc_search",
                "arguments": {"query": query, "limit": limit}
            }
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                for line in response:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data_json = json.loads(line[6:])
                        if 'error' in data_json:
                            return (False, f"Erreur du MCP : {data_json['error']}")
                        
                        if 'result' in data_json and 'structuredContent' in data_json['result']:
                            structured = data_json['result']['structuredContent']
                            if 'error' in structured:
                                return (False, f"Erreur lors de la recherche du composant : {structured['error']}")
                                
                            results = structured.get('results', [])
                            if not results:
                                return (False, "Aucun composant trouvé.")
                            
                            return (True, results)
                        
            return (False, "ÉCHEC : Réponse inattendue du serveur MCP.")
        except Exception as e:
            return (False, f"ÉCHEC de la connexion au serveur MCP : {e}")

import logging
import traceback
from PyQt6.QtCore import QThread, pyqtSignal

class FunctionWorker(QThread):
    finished_task = pyqtSignal(bool, object)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False
        
    def cancel(self):
        self._is_cancelled = True
        
    def run(self):
        try:
            res = self.func(*self.args, **self.kwargs)
            if not self._is_cancelled:
                self.finished_task.emit(True, res)
        except Exception as e:
            if not self._is_cancelled:
                self.finished_task.emit(False, str(e))


logger = logging.getLogger(__name__)

DARK_QSS = """
QWidget { background:#1e1e1e; color:#d4d4d4; font-family:'Segoe UI',Arial; font-size:13px; }
QMainWindow, QDialog { background:#1e1e1e; }
QFrame#Toolbar { background:#2d2d30; border-bottom:1px solid #3c3c3c; }
QFrame#EditorHead, QFrame#InputRow { background:#252526; border-bottom:1px solid #3c3c3c; }
QFrame#Sep { background:#3c3c3c; max-width:1px; margin:2px 4px; }
QLabel#PanelHeader { background:#2d2d30; color:#bbbbbb; font-weight:bold; padding:6px; letter-spacing:1px; }
QLabel#Muted { color:#858585; font-size:11px; padding:2px 4px; }
QPushButton { background:#3a3d41; color:#e0e0e0; border:1px solid #4a4a4a; border-radius:5px; padding:5px 10px; }
QPushButton:hover { background:#45494e; }
QPushButton:disabled { background:#2a2a2a; color:#666666; }
QPushButton#Accent { background:#0e639c; border:1px solid #0e639c; color:white; font-weight:bold; }
QPushButton#Accent:hover { background:#1177bb; }
QComboBox { background:#3c3c3c; border:1px solid #4a4a4a; border-radius:4px; padding:3px 6px; min-width:120px; }
QComboBox QAbstractItemView { background:#252526; selection-background-color:#0e639c; }
QLineEdit, QTextEdit, QPlainTextEdit { background:#1e1e1e; color:#d4d4d4; border:1px solid #3c3c3c; border-radius:4px; }
QTreeView { background:#252526; border:none; outline:0; }
QTreeView::item { padding:3px; }
QTreeView::item:hover { background:#2a2d2e; }
QTreeView::item:selected { background:#094771; }
QPlainTextEdit#Editor { background:#1e1e1e; border:none; padding:6px; }
QTextEdit#Chat { background:#1e1e1e; border:none; padding:8px; }
QTextEdit#ChatInput { background:#2d2d30; border:1px solid #3c3c3c; border-radius:6px; padding:4px; }
QScrollBar:vertical { background:#1e1e1e; width:12px; }
QScrollBar::handle:vertical { background:#424242; border-radius:5px; min-height:24px; }
QScrollBar::handle:vertical:hover { background:#4f4f4f; }
QScrollBar::add-line, QScrollBar::sub-line { height:0; }
QHeaderView::section { background:#252526; color:#bbbbbb; border:none; }
QRadioButton, QCheckBox { padding:4px; }
QRadioButton::indicator { width: 14px; height: 14px; border: 1px solid #858585; border-radius: 8px; background: #252526; }
QRadioButton::indicator:hover { border-color: #0e639c; }
QRadioButton::indicator:checked { border: 1px solid #0e639c; background: #0e639c; image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='14' height='14'><circle cx='12' cy='12' r='6' fill='white'/></svg>"); }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #858585; border-radius: 3px; background: #252526; }
QCheckBox::indicator:hover { border-color: #0e639c; }
QCheckBox::indicator:checked { border: 1px solid #0e639c; background: #0e639c; image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='14' height='14'><path fill='white' d='M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>"); }
QTabWidget::pane { border: 1px solid #3c3c3c; background: #1e1e1e; }
QTabBar::tab { background: #2d2d30; color: #d4d4d4; padding: 6px 12px; border: 1px solid #3c3c3c; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
QTabBar::tab:selected { background: #1e1e1e; border-top: 2px solid #0e639c; color: #ffffff; }
QTabBar::tab:hover:!selected { background: #3a3d41; }
"""

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        kw_fmt = QTextCharFormat(); kw_fmt.setForeground(QColor("#569cd6"))
        keywords = ["def", "class", "return", "if", "elif", "else", "for", "while",
                    "import", "from", "as", "try", "except", "finally", "with",
                    "lambda", "None", "True", "False", "and", "or", "not", "in",
                    "is", "pass", "break", "continue", "raise", "yield", "global",
                    "nonlocal", "assert", "del", "async", "await", "self"]
        for kw in keywords:
            self.rules.append((re.compile(r"\b" + kw + r"\b"), kw_fmt))

        num_fmt = QTextCharFormat(); num_fmt.setForeground(QColor("#b5cea8"))
        self.rules.append((re.compile(r"\b[0-9]+\.?[0-9]*\b"), num_fmt))

        def_fmt = QTextCharFormat(); def_fmt.setForeground(QColor("#dcdcaa"))
        self.rules.append((re.compile(r"(?<=def )\w+"), def_fmt))
        self.rules.append((re.compile(r"(?<=class )\w+"), def_fmt))

        # Chaînes et commentaires en dernier pour qu'ils l'emportent
        str_fmt = QTextCharFormat(); str_fmt.setForeground(QColor("#ce9178"))
        self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
        self.rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))

        com_fmt = QTextCharFormat(); com_fmt.setForeground(QColor("#6a9955"))
        self.rules.append((re.compile(r"#[^\n]*"), com_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

class ProjectLauncherDialog(QDialog):
    """Fenêtre de dialogue pour choisir ou créer un projet et sélectionner l'outil IA."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Choix du Projet et Outil IA")
        self.setModal(True)
        self.resize(420, 420)
        
        reglages = QSettings("Antigravity", "LAtelierIA")
        outil_memorise = reglages.value("target_tool", "antigravity", type=str)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- 1. Groupe Domaine et Action ---
        grp_mode = QGroupBox("1. Domaine & Action du projet")
        mode_layout = QVBoxLayout(grp_mode)
        mode_layout.setSpacing(6)

        self.mode_group = QButtonGroup(self)
        self.radio_new_coder = QRadioButton("Concevoir un nouveau projet code")
        self.radio_edit_coder = QRadioButton("Modifier un projet code existant")
        self.radio_new_hardware = QRadioButton("Concevoir une carte électronique (KiCad/SKiDL)")
        self.radio_edit_hardware = QRadioButton("Reprendre une carte électronique existante")
        self.radio_new_meca = QRadioButton("Concevoir une pièce 3D (CadQuery)")
        self.radio_edit_meca = QRadioButton("Reprendre une pièce 3D existante")

        self.mode_group.addButton(self.radio_new_coder, 1)
        self.mode_group.addButton(self.radio_edit_coder, 2)
        self.mode_group.addButton(self.radio_new_hardware, 3)
        self.mode_group.addButton(self.radio_new_meca, 4)
        self.mode_group.addButton(self.radio_edit_hardware, 5)
        self.mode_group.addButton(self.radio_edit_meca, 6)

        self.CHOIX_NEUF = {1: "coder", 3: "hardware", 4: "meca"}
        self.CHOIX_EXISTANT = {2: "coder", 5: "hardware", 6: "meca"}

        self.radio_new_coder.setChecked(True)
        for radio in (self.radio_new_coder, self.radio_edit_coder,
                      self.radio_new_hardware, self.radio_edit_hardware,
                      self.radio_new_meca, self.radio_edit_meca):
            mode_layout.addWidget(radio)
        layout.addWidget(grp_mode)

        # --- 2. Groupe Outil IA Cible ---
        grp_tool = QGroupBox("2. Outil IA cible")
        tool_layout = QVBoxLayout(grp_tool)
        tool_layout.setSpacing(6)

        self.tool_group = QButtonGroup(self)
        self.radio_antigravity = QRadioButton("Antigravity (Gemini) — Dossier .agents/ & AGENTS.md")
        self.radio_antigravity.setToolTip("Configure le projet pour Antigravity avec l'arborescence .agents/ et les 25 agents Gemini.")
        self.radio_claude_code = QRadioButton("Claude Code (Claude) — Dossier .claude/ & CLAUDE.md")
        self.radio_claude_code.setToolTip("Configure le projet pour Claude Code avec l'arborescence .claude/, CLAUDE.md et les commandes slash.")

        self.tool_group.addButton(self.radio_antigravity, 1)
        self.tool_group.addButton(self.radio_claude_code, 2)

        if outil_memorise == "claude_code":
            self.radio_claude_code.setChecked(True)
        else:
            self.radio_antigravity.setChecked(True)

        tool_layout.addWidget(self.radio_antigravity)
        tool_layout.addWidget(self.radio_claude_code)
        layout.addWidget(grp_tool)

        # --- 3. Option Scaffolding ---
        self.chk_preparer = QCheckBox(
            "Installer / mettre à jour le kit d'agents dans le projet")
        self.chk_preparer.setChecked(True)
        self.chk_preparer.setToolTip(
            "Installe les agents, adapte les workflows et scripts, crée les dossiers "
            "attendus et prépare l'environnement rejouable pour l'IA.")
        self.chk_preparer.setEnabled(SCAFFOLD_AVAILABLE)
        if not SCAFFOLD_AVAILABLE:
            self.chk_preparer.setText(
                "Kit d'agents : module scaffold_projet.py introuvable")
        layout.addWidget(self.chk_preparer)

        layout.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Démarrer")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self.selected_app_mode = "coder"
        self.selected_target_tool = "antigravity"
        self.selected_path = ""

    def accept(self):
        choice = self.mode_group.checkedId()
        self.selected_target_tool = "claude_code" if self.radio_claude_code.isChecked() else "antigravity"

        reglages = QSettings("Antigravity", "LAtelierIA")
        reglages.setValue("target_tool", self.selected_target_tool)

        if choice in self.CHOIX_NEUF:
            parent_dir = QFileDialog.getExistingDirectory(self, "Sélectionnez le dossier parent")
            if not parent_dir:
                return
            project_name, ok = QInputDialog.getText(self, "Nom du projet", "Entrez le nom du projet:")
            if not ok or not project_name.strip():
                return
            project_path = os.path.join(parent_dir, project_name.strip())
            try:
                os.makedirs(project_path, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le dossier: {e}")
                return
            self.selected_path = project_path
            self.selected_app_mode = self.CHOIX_NEUF[choice]

        elif choice in self.CHOIX_EXISTANT:
            project_path = QFileDialog.getExistingDirectory(self, "Sélectionnez le projet")
            if not project_path:
                return
            self.selected_path = project_path
            self.selected_app_mode = self.CHOIX_EXISTANT[choice]

        else:
            return

        if self.chk_preparer.isChecked() and SCAFFOLD_AVAILABLE:
            if not self._preparer_pour_agents():
                return

        super().accept()

    def _preparer_pour_agents(self):
        reglages = QSettings("Antigravity", "LAtelierIA")
        tool = self.selected_target_tool
        nom_outil = "Claude Code" if tool == "claude_code" else "Antigravity"

        kit_key = f"kit_agents_path_{tool}"
        memorise = reglages.value(kit_key, "", type=str) or reglages.value("kit_agents_path", "", type=str)
        kit = memorise if (memorise and est_un_kit(memorise, target_tool=tool)) else kit_par_defaut(target_tool=tool)

        if kit is None:
            consultes = "\n".join("  • " + str(c) for c in emplacements_kit(target_tool=tool))
            reponse = QMessageBox.question(
                self, f"Kit d'agents introuvable ({nom_outil})",
                f"Aucun dossier valide pour {nom_outil} n'a été trouvé.\n\n"
                f"Emplacements consultés :\n{consultes}\n\n"
                "Voulez-vous le désigner maintenant ? Le chemin sera mémorisé.\n"
                "Répondre « Non » ouvre le projet sans agents.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes)
            if reponse != QMessageBox.StandardButton.Yes:
                return True
            dossier = QFileDialog.getExistingDirectory(
                self, f"Dossier du kit d'agents pour {nom_outil}")
            if not dossier:
                return True
            if not est_un_kit(dossier, target_tool=tool):
                QMessageBox.warning(
                    self, "Ce n'est pas un kit valide",
                    f"{dossier}\n\nne contient pas de configuration valide pour {nom_outil}. "
                    "Le projet est ouvert sans agents.")
                return True
            kit = dossier

        reglages.setValue(kit_key, str(kit))

        rapport = preparer_projet(self.selected_path, self.selected_app_mode,
                                  target_tool=tool,
                                  kit_source=kit)
        texte = "\n".join(rapport.lignes) or "Rien à faire."
        if rapport.succes:
            QMessageBox.information(self, f"Projet préparé pour {nom_outil}", texte)
            return True

        reponse = QMessageBox.warning(
            self, "Préparation incomplète",
            texte + "\n\nOuvrir le projet quand même ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        return reponse == QMessageBox.StandardButton.Yes

    def get_selection(self):
        return self.selected_app_mode, self.selected_path, self.selected_target_tool




class MainWindow(QMainWindow):
    def __init__(self, app_mode="coder", target_tool="antigravity"):
        super().__init__()
        self.app_mode = app_mode
        self.target_tool = target_tool
        self.setWindowTitle("L'Atelier — V4.5.0")
        self.resize(1400, 860)

        self.settings = QSettings("Antigravity", "LAtelierIA")
        self.save_directory = self.settings.value("last_dir", "")
        self.project_root = self.save_directory
        self.wants_to_go_back = False
        
        self.current_file = None
        self.sandbox = None
        # Chemins KiCad saisis par l'utilisateur : conservés pour être écrits
        # dans .agents/cache/env.json, sinon les agents ne les verront jamais.
        self.env_kicad = {}
        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.fileChanged.connect(self.on_file_changed_externally)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(self._build_file_panel(), "Fichiers")
        # L'éditeur est présent dans TOUS les modes : le bouton d'exécution
        # SKiDL demande de relire le script avant d'autoriser, ce qui est
        # impossible sans éditeur. Un script SKiDL est du Python, la coloration
        # syntaxique s'applique déjà.
        self.editor_panel = self._build_editor_panel()
        self.left_tabs.addTab(self.editor_panel, "Editeur")
        self.left_tabs.addTab(self._build_journal_panel(), "Journal")
        
        splitter.addWidget(self.left_tabs)
        
        self.right_panel_container = QWidget()
        self.right_panel_layout = QVBoxLayout(self.right_panel_container)
        self.right_panel_layout.setContentsMargins(0, 0, 0, 0)
        
        if self.app_mode == "coder":
            self.right_panel = CoderPanel(self)
        elif self.app_mode == "hardware":
            self.right_panel = HardwarePanel(self)
        elif self.app_mode == "meca":
            self.right_panel = MecaPanel(self)
        else:
            self.right_panel = QWidget()
            
        self.right_panel_layout.addWidget(self.right_panel)
        splitter.addWidget(self.right_panel_container)
        
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([970, 420])
            
        root_layout.addWidget(splitter, 1)

    def run_graphify(self):
        if not self.sandbox:
            QMessageBox.warning(self, "Erreur", "Ouvre d'abord un dossier projet.")
            return

        import shutil
        if not hasattr(self, "_graphify_tool_path"):
            self._graphify_tool_path = None
        
        # Si l'outil n'est pas dans le PATH global (ce qui n'est pas votre cas), on demande son emplacement
        if not shutil.which("graphify") and not self._graphify_tool_path:
            dir_path = QFileDialog.getExistingDirectory(
                self, 
                "Où se trouve l'outil Graphify (dossier contenant graphify.exe) ?"
            )
            if dir_path:
                self._graphify_tool_path = dir_path
                import os
                # On ajoute ce dossier temporairement au PATH de l'application
                os.environ["PATH"] = dir_path + os.pathsep + os.environ.get("PATH", "")
            else:
                QMessageBox.warning(self, "Erreur", "Le dossier contenant l'outil Graphify est requis.")
                return


        selected_path = "."
        indexes = self.tree_view.selectionModel().selectedIndexes()
        if indexes:
            idx = [i for i in indexes if i.column() == 0]
            if idx:
                path = self.fs_model.filePath(idx[0])
                selected_path = path
                
                try:
                    rel_path = os.path.relpath(selected_path, self.sandbox.root)
                    if not rel_path.startswith(".."):
                        selected_path = rel_path
                    else:
                        selected_path = "."
                except ValueError:
                    selected_path = "."

        if selected_path not in (".", ""):
            reply = QMessageBox.question(
                self, "Graphify", 
                f"Voulez-vous analyser uniquement le dossier sélectionné ('{selected_path}') ?\n\n"
                "Oui : Analyser uniquement ce dossier\n"
                "Non : Analyser tout le projet",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No:
                selected_path = "."

        # v4.2.0 : plus AUCUNE clé API transmise au binaire tiers 'graphify'.
        # Le build est purement structurel (--code-only) ; l'enrichissement
        # sémantique (GRAPH_REPORT.md) est fait par « 🧠 Analyse Graphify ».
        # ROBUSTESSE (V4.4.0) : le build (subprocess, timeout 300 s) tournait
        # sur le thread PRINCIPAL -> interface figée jusqu'à 5 minutes. Il est
        # désormais exécuté dans un FunctionWorker.
        self.graphify_btn.setEnabled(False)
        self.graphify_btn.setText("⏳ Construction...")
        
        from PyQt6.QtCore import QSettings
        settings = QSettings("Antigravity", "LAtelierIA")
        code_only = settings.value("graphify_code_only", True, type=bool)
        settings.setValue("graphify_code_only", code_only)

        self._graphify_build_worker = FunctionWorker(self.sandbox.graphify_build, target_dir=selected_path, code_only=code_only)
        self._graphify_build_worker.finished_task.connect(self._on_graphify_build_finished)
        self._graphify_build_worker.start()

    def _on_graphify_build_finished(self, success, result):
        self.graphify_btn.setEnabled(True)
        self.graphify_btn.setText("🚀 Graphify")
        if not success:
            result = f"Erreur inattendue : {result}"

        if "succès" in str(result).lower():
            QMessageBox.information(self, "Graphify",
                                    "Le graphe structurel a été construit avec succès !")
        else:
            QMessageBox.critical(self, "Erreur Graphify", str(result))



    def run_github_helper(self):
        if not self.sandbox:
            QMessageBox.warning(self, "Erreur", "Ouvre d'abord un dossier projet.")
            return

        git_path = os.path.join(self.project_root, ".git")
        is_update = os.path.exists(git_path) and os.path.isdir(git_path)
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Mode GitHub - L'Atelier")
        dialog.resize(600, 450)
        
        layout = QVBoxLayout(dialog)
        
        if is_update:
            header = QLabel("🚀 <b>Dépôt Git détecté ! Voici les commandes de mise à jour :</b>")
            msg = """<p>1. Vérifier l'état de vos fichiers :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git status</code></p>

<p>2. Préparer les modifications (Staging) :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git add .</code></p>

<p>3. Enregistrer les modifications localement (Commit) :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git commit -m "Description de la modification apportée"</code></p>

<p>4. Envoyer les modifications sur GitHub (Push) :<br>
<code style="background-color: #2d2d30; padding: 4px; font-family: Consolas, monospace; color: #569cd6; font-size: 14px;">git push</code></p>

<hr>
<p><i>En résumé, le "trio" magique au quotidien :</i></p>

<pre style="background-color: #2d2d30; padding: 10px; font-family: Consolas, monospace; color: #ce9178; font-size: 14px; border-left: 3px solid #0e639c;">git add .
git commit -m "Mise à jour"
git push</pre>"""
        else:
            header = QLabel("🛑 <b>Aucun dépôt Git détecté. Voici le manuel de création :</b>")
            msg = """<p><b>1. Création du dépôt distant (GitHub)</b></p>
<ul>
  <li>Connectez-vous à votre compte GitHub.</li>
  <li>Cliquez sur "New" en haut à gauche.</li>
  <li>Donnez un nom à votre dépôt.</li>
  <li>Laissez les cases "Initialize this repository with..." décochées.</li>
  <li>Cliquez sur "Create repository" et copiez l'URL du dépôt.</li>
</ul>

<p><b>2. Initialisation locale et envoi</b><br>
Ouvrez votre terminal directement dans le dossier du projet et exécutez :</p>

<pre style="background-color: #2d2d30; padding: 10px; font-family: Consolas, monospace; color: #ce9178; font-size: 14px; border-left: 3px solid #0e639c;"># 1. Initialiser le dossier comme un dépôt Git
git init

# 2. Ajouter tous les fichiers du dossier
git add .

# 3. Créer le premier point de sauvegarde (commit)
git commit -m "Premier commit : initialisation du projet"

# 4. Renommer la branche principale en 'main'
git branch -M main

# 5. Connecter le dossier local au dépôt distant (remplacez l'URL)
git remote add origin https://github.com/votre-nom/nom-du-repo.git

# 6. Envoyer vos fichiers vers GitHub
git push -u origin main</pre>"""
        
        layout.addWidget(header)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(msg)
        layout.addWidget(text_edit)
        
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("📋 Copier tout le texte")
        copy_btn.setObjectName("Accent")
        
        def copy_to_clipboard():
            QApplication.clipboard().setText(text_edit.toPlainText())
            copy_btn.setText("✅ Copié !")
            QTimer.singleShot(2000, lambda: copy_btn.setText("📋 Copier tout le texte"))
            
        copy_btn.clicked.connect(copy_to_clipboard)
        
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(dialog.accept)
        
        btn_layout.addWidget(copy_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()



    def closeEvent(self, event):
        """Gestion propre de la fermeture pour annuler les threads en cours."""
        workers = [
                   getattr(self, '_graphify_build_worker', None),
                   getattr(self, '_task_worker', None)]
        for w in workers:
            if w and w.isRunning():
                if hasattr(w, "cancel"):
                    w.cancel()
                if not w.wait(5000):
                    logger.warning("[FERMETURE] Un worker ne répond pas après 5 s : "
                                   "arrêt forcé (terminate).")
                    w.terminate()
                    w.wait(1000)
                    
        event.accept()

    # ============================ TOOLBAR ============================
    def _build_toolbar(self):
        bar = QFrame(); bar.setObjectName("Toolbar")
        bar.setFixedHeight(46)
        h = QHBoxLayout(bar); h.setContentsMargins(8, 6, 8, 6); h.setSpacing(6)

        self.open_btn = QPushButton("📂 Ouvrir un dossier")
        self.open_btn.setObjectName("Accent")
        # clicked émet un booléen : sans le lambda, open_folder reçoit
        # path=False et ne fonctionne que par accident.
        self.open_btn.clicked.connect(lambda: self.open_folder())
        h.addWidget(self.open_btn)

        h.addWidget(self._vsep())

        self.git_btn = QPushButton("🐙 Aide GitHub")
        self.git_btn.setToolTip("Commandes git à copier selon l'état du dépôt")
        self.git_btn.clicked.connect(self.run_github_helper)
        h.addWidget(self.git_btn)

        self.env_btn = QPushButton("🔧 Réenregistrer l'env. agents")
        self.env_btn.setToolTip(
            "Réécrit .agents/cache/env.json et reconstruit l'index KiCad, pour "
            "que les agents Antigravity voient les mêmes chemins que l'outil.")
        self.env_btn.clicked.connect(self.resynchroniser_env_agents)
        self.env_btn.setEnabled(SCAFFOLD_AVAILABLE)
        h.addWidget(self.env_btn)

        h.addStretch()
        return bar

    def _vsep(self):
        line = QFrame(); line.setFrameShape(QFrame.Shape.VLine); line.setObjectName("Sep")
        line.setFixedHeight(26)
        return line



    # ========================== PANNEAU FICHIERS ==========================
    def _build_file_panel(self):
        panel = QWidget()
        v = QVBoxLayout(panel); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        header = QLabel("  EXPLORER"); header.setObjectName("PanelHeader")
        v.addWidget(header)

        self.pick_folder_btn = QPushButton("📂 Sélectionner un dossier…")
        self.pick_folder_btn.setObjectName("Accent")
        self.pick_folder_btn.clicked.connect(lambda: self.open_folder())
        v.addWidget(self.pick_folder_btn)

        self.path_label = QLabel("  Aucun dossier sélectionné")
        self.path_label.setObjectName("Muted"); self.path_label.setWordWrap(True)
        v.addWidget(self.path_label)

        self.fs_model = QFileSystemModel()

        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(4, 4, 4, 4)
        btn_layout.setSpacing(4)
        
        self.graphify_btn = QPushButton("🚀 Graphify")
        self.graphify_btn.setToolTip("Générer le graphe de connaissances du projet")
        self.graphify_btn.clicked.connect(self.run_graphify)
        if self.app_mode != "coder":
            self.graphify_btn.hide()
        btn_layout.addWidget(self.graphify_btn)
        icons_layout = QHBoxLayout()
        icons_layout.setSpacing(4)
        
        self.view_graph_btn = QPushButton("👁️")
        self.view_graph_btn.setToolTip("Voir le fichier JSON brut (graph.json)")
        self.view_graph_btn.clicked.connect(self.show_graph_file)
        if self.app_mode != "coder":
            self.view_graph_btn.hide()
        icons_layout.addWidget(self.view_graph_btn)
        
        self.view_html_btn = QPushButton("🕸️")
        self.view_html_btn.setToolTip("Voir le graphe visuel interactif dans le navigateur")
        self.view_html_btn.clicked.connect(self.show_html_graph)
        if self.app_mode != "coder":
            self.view_html_btn.hide()
        icons_layout.addWidget(self.view_html_btn)
        
        self.callflow_html_btn = QPushButton("🗺️")
        self.callflow_html_btn.setToolTip("Générer et voir la carte interactive de l'architecture (Callflow HTML)")
        self.callflow_html_btn.clicked.connect(self.show_callflow_html)
        if self.app_mode != "coder":
            self.callflow_html_btn.hide()
        icons_layout.addWidget(self.callflow_html_btn)
        
        btn_layout.addLayout(icons_layout)
        v.addLayout(btn_layout)

        self.tree_view = QTreeView()
        self.tree_view.setModel(self.fs_model)
        for col in (1, 2, 3):
            self.tree_view.setColumnHidden(col, True)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.clicked.connect(self.open_file_from_index)
        self.tree_view.hide()
        v.addWidget(self.tree_view)
        return panel

    # ========================== PANNEAU JOURNAL ==========================
    # Les résultats d'exécution (netlist, ERC, recherches) partaient dans
    # statusBar().showMessage() : les balises HTML s'affichaient en clair et le
    # message disparaissait au bout de 5 secondes. Ils sont désormais empilés
    # ici, et restent consultables.
    def _build_journal_panel(self):
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QFrame()
        head.setObjectName("EditorHead")
        hh = QHBoxLayout(head)
        hh.setContentsMargins(10, 4, 10, 4)
        hh.addWidget(QLabel("Journal des opérations"))
        hh.addStretch()
        clear_btn = QPushButton("Vider")
        clear_btn.clicked.connect(lambda: self.journal.clear())
        hh.addWidget(clear_btn)
        v.addWidget(head)

        self.journal = QTextEdit()
        self.journal.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self.journal.setFont(mono)
        v.addWidget(self.journal)
        return panel

    # ========================== PANNEAU ÉDITEUR ==========================
    def _build_editor_panel(self):
        panel = QWidget()
        v = QVBoxLayout(panel); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        head = QFrame(); head.setObjectName("EditorHead")
        hh = QHBoxLayout(head); hh.setContentsMargins(10, 4, 10, 4)
        self.editor_label = QLabel("Aucun fichier ouvert")
        hh.addWidget(self.editor_label); hh.addStretch()
        self.save_btn = QPushButton("💾 Enregistrer")
        self.save_btn.clicked.connect(self.save_current_file)
        self.save_btn.setEnabled(False)
        hh.addWidget(self.save_btn)
        v.addWidget(head)

        self.editor = QPlainTextEdit(); self.editor.setObjectName("Editor")
        mono = QFont("Consolas"); mono.setStyleHint(QFont.StyleHint.Monospace); mono.setPointSize(11)
        self.editor.setFont(mono)
        self.editor.setPlaceholderText("Sélectionne un fichier dans l'explorateur pour l'afficher ici.")
        self.highlighter = PythonHighlighter(self.editor.document())
        v.addWidget(self.editor)
        return panel




    # ============================ FICHIERS ============================
    def open_folder(self, path=None):
        if path:
            directory = path
        else:
            directory = QFileDialog.getExistingDirectory(self, "Ouvrir le dossier projet")
            if not directory:
                return
        try:
            self.sandbox = FileSandbox(directory)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Dossier invalide : {e}")
            return
        self.project_root = directory
        self.save_directory = directory
        self.settings.setValue("last_dir", directory)
        self.fs_model.setRootPath(directory)
        self.tree_view.setRootIndex(self.fs_model.index(directory))
        self.tree_view.show()
        self.pick_folder_btn.setText("📂 Changer de dossier…")
        self.path_label.setText("  " + directory)

        # NOTE : c'est le SEUL point d'entrée de l'import de datasheets.
        # main.py appelait aussi import_datasheets() juste après open_folder(),
        # ce qui ouvrait deux fois de suite le sélecteur de fichiers.
        if self.app_mode == "hardware":
            reply = QMessageBox.question(self, "Import de Datasheets", 
                                         "Avez-vous des datasheets à importer pour ce projet ?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.import_datasheets(directory)

    def resynchroniser_env_agents(self):
        """Réécrit .agents/cache/env.json et reconstruit l'index KiCad.

        Les variables KiCad sont posées avec os.environ dans CE processus.
        Antigravity est lancé séparément : ses agents n'en héritent pas, et
        l'exécution d'un script SKiDL échoue alors sur une librairie de symboles
        introuvable. On les dépose donc dans le projet, où le wrapper
        .agents/scripts/run_projet.py les relira.
        """
        if not SCAFFOLD_AVAILABLE:
            QMessageBox.warning(self, "Indisponible",
                                "Le module scaffold_projet.py est introuvable.")
            return
        if not self.project_root:
            QMessageBox.warning(self, "Erreur", "Ouvre d'abord un dossier projet.")
            return

        rapport = mettre_a_jour_env(self.project_root, self.env_kicad or {}, target_tool=self.target_tool)
        self.afficher_rapport_preparation(rapport)
        if rapport.succes:
            QMessageBox.information(self, "Environnement agents",
                                    "\n".join(rapport.lignes))
        else:
            QMessageBox.warning(self, "Environnement agents",
                                "\n".join(rapport.lignes))

    # Le chemin du convertisseur était figé sur "<dossier de ui.py>/hardware/",
    # alors qu'il vit le plus souvent à la racine, à côté de ui.py. On cherche
    # aux emplacements plausibles, puis on demande une fois pour toutes.
    NOM_CONVERTISSEUR = "convertisseur PDF-Json.py"

    def _trouver_convertisseur(self):
        base = Path(__file__).resolve().parent
        memorise = self.settings.value("convertisseur_path", "", type=str)

        candidats = []
        if memorise:
            candidats.append(Path(memorise))
        candidats += [base / self.NOM_CONVERTISSEUR,
                      base / "hardware" / self.NOM_CONVERTISSEUR,
                      base / "tools" / self.NOM_CONVERTISSEUR,
                      base / "scripts" / self.NOM_CONVERTISSEUR]
        if self.project_root:
            candidats.append(Path(self.project_root) / self.NOM_CONVERTISSEUR)

        for chemin in candidats:
            if chemin.is_file():
                self.settings.setValue("convertisseur_path", str(chemin))
                return str(chemin)

        # Repli tolérant : nom approchant (accents, tiret, casse, version).
        for dossier in [base, base / "hardware", base / "tools"]:
            if not dossier.is_dir():
                continue
            for trouve in sorted(dossier.glob("*.py")):
                nom = trouve.name.lower()
                if "convert" in nom and "json" in nom and "pdf" in nom:
                    self.settings.setValue("convertisseur_path", str(trouve))
                    self.add_system_message(
                        f"ℹ️ Convertisseur trouvé sous un nom approchant : "
                        f"<b>{html.escape(trouve.name)}</b>")
                    return str(trouve)

        cherches = "\n".join("  • " + str(c) for c in candidats)
        reponse = QMessageBox.question(
            self, "Convertisseur introuvable",
            f"Le script « {self.NOM_CONVERTISSEUR} » n'a pas été trouvé.\n\n"
            f"Emplacements consultés :\n{cherches}\n\n"
            "Voulez-vous le désigner maintenant ? Le chemin sera mémorisé.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if reponse != QMessageBox.StandardButton.Yes:
            return ""

        choisi, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner le convertisseur PDF -> JSON",
            str(base), "Script Python (*.py)")
        if not choisi:
            return ""
        self.settings.setValue("convertisseur_path", choisi)
        self.add_system_message(
            f"✅ Convertisseur mémorisé : <b>{html.escape(choisi)}</b>")
        return choisi

    def import_datasheets(self, directory):
        files, _ = QFileDialog.getOpenFileNames(self, "Sélectionner les datasheets (PDF)", "", "Fichiers PDF (*.pdf)")
        if not files:
            return
            
        try:
            import importlib.util
            import sys
            
            script_path = self._trouver_convertisseur()
            if not script_path:
                return
                
            spec = importlib.util.spec_from_file_location("convertisseur_pdf_json", script_path)
            convertisseur = importlib.util.module_from_spec(spec)
            sys.modules["convertisseur_pdf_json"] = convertisseur
            spec.loader.exec_module(convertisseur)
            
            self.add_system_message("⏳ Importation et conversion des datasheets en cours...")
            QApplication.processEvents()
            
            convertisseur.process_multiple_pdfs(files, directory)
            
            self.add_system_message("✅ Datasheets importées et converties avec succès.")
            QMessageBox.information(self, "Succès", "L'importation et la conversion des datasheets sont terminées !")
        except Exception as e:
            self.add_system_message(f"❌ Erreur lors de la conversion des datasheets : {e}")
            QMessageBox.critical(self, "Erreur", f"Une erreur est survenue lors de la conversion :\n{e}")



    def open_file_from_index(self, index):
        path = self.fs_model.filePath(index)
        self.open_file_path(path)

    def open_file_path(self, path):
        if not os.path.isfile(path):
            return
            
        # Check size before reading
        if os.path.getsize(path) > 2 * 1024 * 1024:
            self.editor.setPlainText(f"[Fichier trop volumineux (>2Mo). Lecture refusée.]")
            self.current_file = None
            self.save_btn.setEnabled(False)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            self.editor.setPlainText(f"[Fichier binaire non supporté ou encodage invalide]")
            self.current_file = None
            self.save_btn.setEnabled(False)
            return
        except Exception as e:
            self.editor.setPlainText(f"[Impossible d'afficher ce fichier : {e}]")
            self.current_file = None
            self.save_btn.setEnabled(False)
            return
            
        if self.current_file:
            self.file_watcher.removePath(self.current_file)
            
        self.current_file = path
        self.editor.setPlainText(content)
        self.editor_label.setText(os.path.basename(path))
        self.save_btn.setEnabled(True)
        self.file_watcher.addPath(path)
        if hasattr(self, 'left_tabs') and self.left_tabs.count() > 1:
            self.left_tabs.setCurrentIndex(1)



    def show_graph_file(self):
        if not self.sandbox:
            return
        graph_path = os.path.join(self.sandbox.root, "graphify-out", "graph.json")
        if os.path.exists(graph_path):
            self.open_file_path(graph_path)
        else:
            QMessageBox.warning(self, "Erreur", "Le fichier graph.json est introuvable. Avez-vous lancé Graphify ?")

    def show_html_graph(self):
        if not self.sandbox: return
        import subprocess
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        from PyQt6.QtWidgets import QMessageBox
        
        graph_json = os.path.join(self.sandbox.root, "graphify-out", "graph.json")
        if not os.path.exists(graph_json):
            QMessageBox.warning(self, "Erreur", "Générez d'abord le graphe (Bouton 'Graphify').")
            return
            
        html_path1 = os.path.join(self.sandbox.root, "graphify-out", "graph.html")
        html_path2 = os.path.join(self.sandbox.root, "graphify-out", "GRAPH_TREE.html")
        
        reply = QMessageBox.question(self, "Choix de la vue",
            "Voulez-vous forcer la vue 'Méli-mélo' (Force-Directed Graph) ?\n"
            "⚠️ Sur un gros projet, cela peut faire ramer votre navigateur Web.\n\n"
            "Cliquez sur 'Non' pour ouvrir la vue 'Arbre' optimisée et bien rangée.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
            
        target_html = None
        self.view_html_btn.setText("⏳")
        QApplication.processEvents()
        
        # SÉCURITÉ (V4.3.0) : chemin ABSOLU du binaire résolu via le PATH de
        # l'application + env durci (jamais de nom nu avec cwd=projet, sinon
        # un 'graphify.exe' hostile déposé à la racine du dépôt serait lancé
        # sous Windows).
        graphify_bin = resolve_external_binary("graphify")
        if not graphify_bin:
            self.view_html_btn.setText("🕸️")
            QMessageBox.critical(self, "Erreur",
                                 "Binaire 'graphify' introuvable sur le PATH. "
                                 "Assurez-vous qu'il est installé.")
            return

        try:
            # ROBUSTESSE (V4.4.0) : ces subprocess n'avaient AUCUN timeout —
            # un binaire bloqué figeait l'interface indéfiniment.
            if reply == QMessageBox.StandardButton.Yes:
                env = hardened_subprocess_env()
                env["GRAPHIFY_VIZ_NODE_LIMIT"] = "30000"
                subprocess.run([graphify_bin, "cluster-only", "."], cwd=self.sandbox.root,
                               capture_output=True, env=env, timeout=180)
                if os.path.exists(html_path1):
                    target_html = html_path1
            else:
                subprocess.run([graphify_bin, "tree"], cwd=self.sandbox.root, capture_output=True,
                               env=hardened_subprocess_env(), timeout=180)
                if os.path.exists(html_path2):
                    target_html = html_path2
        except subprocess.TimeoutExpired:
            QMessageBox.critical(self, "Erreur",
                                 "La génération du HTML a dépassé 180 s et a été interrompue.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de générer le HTML: {e}")
        finally:
            self.view_html_btn.setText("🕸️")
            
        if target_html:
            QDesktopServices.openUrl(QUrl.fromLocalFile(target_html))
        else:
            QMessageBox.warning(self, "Erreur", "Le fichier HTML interactif n'a pas pu être trouvé ou généré.")

    def show_callflow_html(self):
        if not self.sandbox: return
        import subprocess
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        from PyQt6.QtWidgets import QMessageBox
        
        graph_json = os.path.join(self.sandbox.root, "graphify-out", "graph.json")
        if not os.path.exists(graph_json):
            QMessageBox.warning(self, "Erreur", "Générez d'abord le graphe (Bouton 'Graphify').")
            return
            
        self.callflow_html_btn.setText("⏳")
        QApplication.processEvents()
        
        graphify_bin = resolve_external_binary("graphify")
        if not graphify_bin:
            self.callflow_html_btn.setText("🗺️")
            QMessageBox.critical(self, "Erreur", "Binaire 'graphify' introuvable sur le PATH.")
            return

        try:
            subprocess.run([graphify_bin, "export", "callflow-html", "."], cwd=self.sandbox.root, capture_output=True, env=hardened_subprocess_env(), timeout=180)
            
            project_name = Path(self.sandbox.root).name
            html_path = os.path.join(self.sandbox.root, "graphify-out", f"{project_name}-callflow.html")
            
            if os.path.exists(html_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(html_path))
            else:
                QMessageBox.warning(self, "Erreur", "Le fichier HTML Callflow n'a pas pu être trouvé ou généré.")
        except subprocess.TimeoutExpired:
            QMessageBox.critical(self, "Erreur", "La génération du Callflow HTML a dépassé 180 s et a été interrompue.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de générer le Callflow HTML: {e}")
        finally:
            self.callflow_html_btn.setText("🗺️")

    def save_current_file(self):
        if not self.current_file:
            return
        try:
            if self.sandbox:
                self.sandbox._backup_file(Path(self.current_file))
            with open(self.current_file, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
            self.editor.document().setModified(False)
            self.add_system_message(f"💾 Enregistré : {os.path.basename(self.current_file)}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Échec de l'enregistrement : {e}")

    def on_file_changed_externally(self, path):
        if path == self.current_file:
            self.reload_current_file()

    def reload_current_file(self):
        if self.current_file and os.path.isfile(self.current_file):
            if self.editor.document().isModified():
                reply = QMessageBox.question(
                    self, 'Modifications en cours',
                    "L'agent vient de modifier ce fichier mais vous avez des modifications non enregistrées dans l'éditeur.\nVoulez-vous recharger le fichier (et perdre vos modifications) ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.No:
                    return

            try:
                with open(self.current_file, "r", encoding="utf-8") as f:
                    self.editor.setPlainText(f.read())
                    self.editor.document().setModified(False)
            except Exception:
                pass

    def add_system_message(self, text):
        logger.info(re.sub(r"<[^>]+>", "", str(text)))

        horodatage = datetime.now().strftime("%H:%M:%S")
        if getattr(self, "journal", None) is not None:
            self.journal.append(f"<span style='color:#6a9955'>[{horodatage}]</span> "
                                f"{text}")
            barre = self.journal.verticalScrollBar()
            barre.setValue(barre.maximum())

        # La barre de statut n'interprète pas le HTML : on lui donne du texte nu.
        nu = re.sub(r"<[^>]+>", "", str(text)).strip()
        if self.statusBar() is not None:
            self.statusBar().showMessage(nu[:200], 5000)

    def afficher_rapport_preparation(self, rapport):
        """Affiche dans le journal le résultat d'une préparation de projet."""
        for ligne in rapport.lignes:
            self.add_system_message(html.escape(ligne))


class CoderPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # CoderPanel is empty now that AI features are removed.
        # It's kept just to not break layout in main window.
        pass

class HardwarePanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        
        self.skidl_tab = QWidget()
        skidl_layout = QVBoxLayout(self.skidl_tab)
        skidl_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- Toolbar SKIDL ---
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        
        toolbar_layout.addWidget(QLabel("🛠️ Outils SKIDL :"))
        
        self.btn_netlist = QPushButton("🖨️ Générer la Netlist")
        self.btn_netlist.clicked.connect(self.generate_netlist)
        
        self.btn_erc = QPushButton("🔍 Vérifier l'ERC")
        self.btn_erc.clicked.connect(self.verify_erc)
        
        self.btn_components = QPushButton("🔌 Voir les composants")
        self.btn_components.clicked.connect(self.view_components)
        
        self.btn_pcbparts = QPushButton("🔍 Recherche PCBParts")
        self.btn_pcbparts.clicked.connect(self.search_pcbparts)

        # kicad_libs/ est créé vide à la préparation du projet, et le kit exige
        # que le symbole de tout circuit intégré y soit AVANT d'être instancié.
        # Ce bouton est le seul moyen de le remplir sans quitter l'outil.
        self.btn_pcb_import = QPushButton("🌐 PCBParts : modèle + tarifs")
        self.btn_pcb_import.setToolTip(
            "Télécharge le symbole et l'empreinte KiCad depuis pcbparts.dev, "
            "et écrit un rapport prix / stock / LCSC lisible par les agents.")
        self.btn_pcb_import.clicked.connect(self.importer_depuis_pcbparts)
        self.btn_pcb_import.setEnabled(PCBPARTS_AVAILABLE)

        self.btn_symbole = QPushButton("📥 Importer un symbole")
        self.btn_symbole.setToolTip(
            "Recopie un symbole des librairies KiCad installées vers "
            "kicad_libs/ du projet, avec ses sous-unités et son symbole parent.")
        self.btn_symbole.clicked.connect(self.importer_symbole)

        toolbar_layout.addWidget(self.btn_netlist)
        toolbar_layout.addWidget(self.btn_erc)
        toolbar_layout.addWidget(self.btn_components)
        toolbar_layout.addWidget(self.btn_symbole)
        toolbar_layout.addWidget(self.btn_pcbparts)
        toolbar_layout.addWidget(self.btn_pcb_import)
        
        skidl_layout.addLayout(toolbar_layout)
        
        self.tabs.addTab(self.skidl_tab, "Agent Concepteur (SKIDL)")
        
        self.layout.addWidget(self.tabs)
        
        # Demander les chemins KiCad au démarrage si manquant
        self._check_kicad_env()

    def _check_kicad_env(self):
        import os
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        
        # SKiDL 2.3 cherche KICAD_SYMBOL_DIR et KICAD6 à KICAD10 : on écrit
        # toute la plage, sinon il avertit et ignore les librairies.
        env_vars = ["KICAD_SYMBOL_DIR", "KICAD10_SYMBOL_DIR", "KICAD9_SYMBOL_DIR",
                    "KICAD8_SYMBOL_DIR", "KICAD7_SYMBOL_DIR", "KICAD6_SYMBOL_DIR"]
        # Les empreintes étaient écrites dans KICAD9_FOOTPRINT_DIR seulement,
        # alors que kicad_search.py lit d'abord KICAD8_/KICAD_ : l'index se
        # construisait sans aucune empreinte. On écrit les deux familles.
        fp_vars = ["KICAD_FOOTPRINT_DIR", "KICAD10_FOOTPRINT_DIR",
                   "KICAD9_FOOTPRINT_DIR", "KICAD8_FOOTPRINT_DIR",
                   "KICAD7_FOOTPRINT_DIR"]
        if any(var in os.environ for var in env_vars):
            self._memoriser_env(env_vars + fp_vars)
            return
            
        reply = QMessageBox.question(
            self, "Configuration KiCad",
            "Les variables d'environnement KiCad ne sont pas définies sur ce système.\n"
            "Souhaitez-vous configurer le chemin d'accès aux librairies KiCad pour cette session ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            default_sym_path = r"C:\Program Files\KiCad\9.0\share\kicad\symbols"
            sym_path, ok1 = QInputDialog.getText(
                self, "Chemin des symboles KiCad",
                "Chemin vers le dossier 'symbols' (ex: C:\\Program Files\\KiCad\\9.0\\share\\kicad\\symbols) :",
                text=default_sym_path
            )
            if ok1 and sym_path:
                for var in env_vars:
                    os.environ[var] = sym_path
                
                # S'assurer que le main_window a la méthode avant d'appeler
                if hasattr(self.main_window, 'add_system_message'):
                    self.main_window.add_system_message(f"✅ <b>Symboles KiCad définis temporairement</b> vers : {sym_path}")

            default_fp_path = r"C:\Program Files\KiCad\9.0\share\kicad\footprints"
            fp_path, ok2 = QInputDialog.getText(
                self, "Chemin des empreintes KiCad",
                "Chemin vers le dossier 'footprints' (ex: C:\\Program Files\\KiCad\\9.0\\share\\kicad\\footprints) :",
                text=default_fp_path
            )
            if ok2 and fp_path:
                for var in fp_vars:
                    os.environ[var] = fp_path
                if hasattr(self.main_window, 'add_system_message'):
                    self.main_window.add_system_message(f"✅ <b>Empreintes KiCad définies temporairement</b> vers : {fp_path}")

            self._memoriser_env(env_vars + fp_vars)

            # Ces chemins n'existaient pas quand le projet a été préparé :
            # on les redépose maintenant pour que les agents les voient.
            if SCAFFOLD_AVAILABLE and getattr(self.main_window, "project_root", ""):
                rapport = mettre_a_jour_env(self.main_window.project_root,
                                            self.main_window.env_kicad)
                if hasattr(self.main_window, "afficher_rapport_preparation"):
                    self.main_window.afficher_rapport_preparation(rapport)

    def _memoriser_env(self, variables):
        valeurs = {v: os.environ[v] for v in variables if os.environ.get(v)}
        if valeurs and hasattr(self.main_window, "env_kicad"):
            self.main_window.env_kicad.update(valeurs)

    # ------------------------------------------------------------------ #
    #  Exécution en arrière-plan (V4.4.0)                                 #
    # ------------------------------------------------------------------ #
    # ROBUSTESSE : run_python_script (jusqu'à 60 s) et la recherche
    # PCBParts (30 s) tournaient sur le thread PRINCIPAL -> interface
    # figée pendant toute la durée de l'appel. Ces opérations passent
    # désormais par un FunctionWorker (core.workers). Le worker est stocké
    # sur main_window._task_worker pour être annulé/attendu par closeEvent.
    def _run_in_background(self, fn, on_done, *args, **kwargs):
        existing = getattr(self.main_window, '_task_worker', None)
        if existing and existing.isRunning():
            QMessageBox.information(self, "Occupé",
                                    "Une opération est déjà en cours, patientez.")
            return False
        worker = FunctionWorker(fn, *args, **kwargs)
        worker.finished_task.connect(on_done)
        self.main_window._task_worker = worker
        worker.start()
        return True

    def _set_toolbar_enabled(self, enabled):
        for btn in (self.btn_netlist, self.btn_erc, self.btn_components,
                    self.btn_pcbparts, self.btn_pcb_import, self.btn_symbole):
            btn.setEnabled(enabled)

    def _script_du_circuit(self):
        """Détermine le script à exécuter : celui ouvert, sinon circuits/.

        Le kit impose désormais `circuits/<nom-de-la-carte>.py`. Exiger un
        fichier ouvert dans l'éditeur était une contrainte inutile quand le
        projet n'en contient qu'un.
        """
        ouvert = self.main_window.current_file
        if ouvert:
            return ouvert

        racine = getattr(self.main_window, "project_root", "")
        dossier = os.path.join(racine, "circuits") if racine else ""
        scripts = []
        if dossier and os.path.isdir(dossier):
            scripts = sorted(
                os.path.join(dossier, f) for f in os.listdir(dossier)
                if f.endswith(".py") and not f.startswith("_"))

        if not scripts:
            QMessageBox.warning(
                self, "Aucun script",
                "Aucun script trouvé.\n\nOuvre-le dans l'éditeur, ou place-le "
                "dans circuits/<nom-de-la-carte>.py comme le prévoit le kit.")
            return ""

        if len(scripts) == 1:
            return scripts[0]

        noms = [os.path.basename(s) for s in scripts]
        choix, ok = QInputDialog.getItem(
            self, "Script à exécuter",
            "Plusieurs scripts dans circuits/ :", noms, 0, False)
        if not ok or not choix:
            return ""
        return scripts[noms.index(choix)]

    def _run_current_skidl_script(self, action_name):
        current_file = self._script_du_circuit()
        if not current_file:
            return
            
        if not self.main_window.sandbox:
            QMessageBox.warning(self, "Erreur", "Aucun projet ouvert.")
            return

        # SÉCURITÉ (V4.4.0) : ce bouton EXÉCUTE un script du projet — script
        # que l'agent Codeur a potentiellement écrit. C'est la même classe de
        # risque qui a motivé le retrait de pytest de la liste blanche. On
        # avertit explicitement l'utilisateur, comme pour graphify.
        import os
        reply = QMessageBox.question(
            self, f"{action_name} — Confirmation",
            f"Cette action va EXÉCUTER le script Python suivant sur votre machine,\n"
            f"avec vos droits utilisateur :\n\n{os.path.basename(current_file)}\n\n"
            f"⚠️ Si ce script a été écrit ou modifié par un agent, relisez-le avant\n"
            f"d'autoriser (il sera exécuté tel quel).\n\nContinuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.main_window.add_system_message(
            f"⏳ <b>{action_name}</b> en cours d'exécution sur "
            f"{html.escape(os.path.basename(current_file))}...")
        self._set_toolbar_enabled(False)

        def on_done(success, result):
            self._set_toolbar_enabled(True)
            if not success:
                self.main_window.add_system_message(f"❌ <b>Erreur {action_name} :</b> {result}")
                QMessageBox.warning(self, "Erreur", str(result))
                return
            formatted_result = str(result).replace('\n', '<br>')
            self.main_window.add_system_message(f"<b>Résultat {action_name} :</b><br><pre>{formatted_result}</pre>")
            if "SUCCÈS" in str(result).split("\n", 1)[0]:
                QMessageBox.information(self, "Succès", f"{action_name} terminée avec succès.")
            else:
                QMessageBox.warning(self, "Erreur", f"{action_name} a rencontré un problème. Vérifiez les messages système.")

        self._run_in_background(self.main_window.sandbox.run_python_script,
                                on_done, current_file)

    def generate_netlist(self):
        self._run_current_skidl_script("Génération de Netlist")
        
    def verify_erc(self):
        self._run_current_skidl_script("Vérification ERC")
        
    def view_components(self):
        from PyQt6.QtWidgets import QInputDialog
        
        if not self.main_window.sandbox:
            QMessageBox.warning(self, "Erreur", "Aucun projet ouvert.")
            return
            
        term, ok = QInputDialog.getText(self, "Recherche de Composants", "Entrez un mot-clé (ex: resistor, R, capacitor) :")
        if ok and term:
            self.main_window.add_system_message(f"⏳ <b>Recherche SKIDL :</b> '{term}'...")
            self._set_toolbar_enabled(False)
            
            temp_script = ".skidl_search_tmp.py"
            # BUGFIX CRITIQUE (V4.4.0) : l'ancienne f-string utilisait '\\n'
            # (antislash + n LITTÉRAL) -> le script généré tenait sur une
            # seule ligne et levait SyntaxError à CHAQUE exécution. On écrit
            # de vrais sauts de ligne, et le terme passe par repr() ({term!r})
            # pour neutraliser apostrophes et caractères spéciaux (l'ancien
            # code cassait sur un terme contenant « ' » — injection de code).
            code = f"from skidl import search\nsearch({term!r})\n"

            def run_search():
                sandbox = self.main_window.sandbox
                sandbox.write_file(temp_script, code)
                try:
                    return sandbox.run_python_script(temp_script)
                finally:
                    try:
                        sandbox.delete_file(temp_script)
                    except Exception:
                        pass

            def on_done(success, result):
                self._set_toolbar_enabled(True)
                if not success:
                    QMessageBox.warning(self, "Erreur", f"Erreur lors de la recherche : {result}")
                    return
                formatted_result = str(result).replace('\n', '<br>')
                self.main_window.add_system_message(f"<b>Résultat Recherche :</b><br><pre>{formatted_result}</pre>")

            self._run_in_background(run_search, on_done)

    def importer_symbole(self):
        """Cherche puis recopie un symbole KiCad dans kicad_libs/ du projet."""
        racine = getattr(self.main_window, "project_root", "")
        if not racine:
            QMessageBox.warning(self, "Erreur", "Ouvre d'abord un dossier projet.")
            return

        script = os.path.join(racine, ".agents", "scripts", "kicad_fetch_part.py")
        if not os.path.isfile(script):
            script = os.path.join(racine, ".claude", "scripts", "kicad_fetch_part.py")
        if not os.path.isfile(script):
            QMessageBox.warning(
                self, "Script absent",
                "kicad_fetch_part.py n'est pas dans ce projet.\n\n"
                "Relance la préparation du projet, ou vérifie que le kit "
                "d'agents est à jour.")
            return

        terme, ok = QInputDialog.getText(
            self, "Importer un symbole",
            "Référence ou boîtier à chercher (ex. ESP32-C3-MINI, BME280) :")
        if not ok or not terme.strip():
            return

        code, sortie = self._lancer_fetch(script, racine, "chercher", terme.strip())
        lignes = [l for l in sortie.splitlines() if "\t" in l]
        if code != 0 or not lignes:
            self.main_window.add_system_message(
                f"❌ Aucun symbole ne correspond à <b>{html.escape(terme)}</b>")
            QMessageBox.information(
                self, "Rien trouvé",
                f"Aucun symbole ne correspond à « {terme} » dans les librairies "
                "KiCad détectées.\n\n"
                "Vérifie les chemins KiCad, ou crée le symbole dans KiCad puis "
                "place le .kicad_sym dans kicad_libs/.")
            return

        references = [l.split("\t")[0] for l in lignes]
        choix, ok = QInputDialog.getItem(
            self, "Symbole à importer",
            f"{len(references)} résultat(s). Lequel recopier dans kicad_libs/ ?",
            references, 0, False)
        if not ok or not choix:
            return

        code, sortie = self._lancer_fetch(script, racine, "copier", choix)
        if code == 0:
            self.main_window.add_system_message(
                "✅ Symbole importé :<pre>" + html.escape(sortie.strip()) + "</pre>")
            QMessageBox.information(self, "Symbole importé", sortie.strip())
        else:
            self.main_window.add_system_message(
                "❌ Import du symbole échoué :<pre>"
                + html.escape(sortie.strip()) + "</pre>")
            QMessageBox.warning(self, "Import échoué", sortie.strip() or
                                f"Code de sortie {code}.")

    def importer_depuis_pcbparts(self):
        """Télécharge modèles KiCad + tarifs, puis reconstruit l'index."""
        if not PCBPARTS_AVAILABLE:
            QMessageBox.warning(self, "Indisponible",
                                "Le module pcbparts.py est introuvable.")
            return
        racine = getattr(self.main_window, "project_root", "")
        if not racine:
            QMessageBox.warning(self, "Erreur", "Ouvre d'abord un dossier projet.")
            return

        reference, ok = QInputDialog.getText(
            self, "PCBParts",
            "Référence fabricant ou code LCSC (ex. LM358DR, C7950) :")
        if not ok or not reference.strip():
            return
        reference = reference.strip()

        self.main_window.add_system_message(
            f"⏳ <b>PCBParts :</b> récupération de "
            f"{html.escape(reference)}…")
        QApplication.processEvents()

        def termine(succes, resultat):
            if not succes:
                self.main_window.add_system_message(
                    f"❌ <b>PCBParts :</b> {html.escape(str(resultat))}")
                QMessageBox.warning(self, "PCBParts", str(resultat))
                return
            ok_import, lignes = resultat
            for ligne in lignes:
                self.main_window.add_system_message(
                    ("✅ " if ok_import else "⚠️ ") + html.escape(ligne))
            texte = "\n".join(lignes) or "Aucun résultat."
            if ok_import:
                # Les nouveaux fichiers ne sont pas dans l'index : sans ça,
                # hw-footprint ne verrait pas l'empreinte qu'on vient d'importer.
                if SCAFFOLD_AVAILABLE:
                    rapport = mettre_a_jour_env(racine,
                                                self.main_window.env_kicad)
                    self.main_window.afficher_rapport_preparation(rapport)
                QMessageBox.information(
                    self, "PCBParts",
                    texte + "\n\nLe modèle vient d'une source tierce "
                    "(SamacSys) : compare son plan de pose avec la datasheet "
                    "avant de router.")
            else:
                QMessageBox.warning(self, "PCBParts", texte)

        self._run_in_background(pcbparts.installer, termine, racine, reference)

    def diagnostiquer_pcbparts(self):
        """Liste les outils réellement exposés par le serveur MCP."""
        ok, resultat = pcbparts.lister_outils()
        if not ok:
            QMessageBox.warning(self, "PCBParts", str(resultat))
            return
        lignes = ["{} — {}".format(nom, (desc or "")[:80])
                  for nom, desc in resultat]
        QMessageBox.information(self, "Outils pcbparts.dev",
                                "\n".join(lignes))

    def _lancer_fetch(self, script, racine, action, argument):
        """Exécute kicad_fetch_part.py avec l'environnement KiCad de l'outil."""
        env = dict(os.environ)
        env.update({k: v for k, v in (self.main_window.env_kicad or {}).items() if v})
        try:
            proc = subprocess.run(
                [sys.executable, script, action, argument],
                cwd=racine, capture_output=True, text=True, timeout=180, env=env)
        except (OSError, subprocess.TimeoutExpired) as err:
            return 1, str(err)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

    def search_pcbparts(self):
        from PyQt6.QtWidgets import QInputDialog
        
        if not self.main_window.sandbox:
            QMessageBox.warning(self, "Erreur", "Aucun projet ouvert.")
            return
            
        term, ok = QInputDialog.getText(self, "Recherche PCBParts", "Entrez la référence d'un composant (ex: LM358, ESP32) :")
        if ok and term:
            self.main_window.add_system_message(f"⏳ <b>Recherche PCBParts :</b> '{term}'...")
            self._set_toolbar_enabled(False)

            def on_done(success, result):
                self._set_toolbar_enabled(True)
                if not success:
                    self.main_window.add_system_message(f"❌ <b>Erreur PCBParts :</b> {result}")
                    QMessageBox.warning(self, "Erreur", str(result))
                    return
                ok_flag, result_data = result
                if ok_flag:
                    self.main_window.add_system_message("✅ <b>Recherche PCBParts terminée.</b> Affichage des résultats.")
                    dialog = PcbPartsResultDialog(self, term, result_data)
                    dialog.exec()
                else:
                    self.main_window.add_system_message(f"❌ <b>Erreur PCBParts :</b> {result_data}")
                    QMessageBox.warning(self, "Erreur", str(result_data))

            self._run_in_background(self.main_window.sandbox.search_mcp_pcbparts,
                                    on_done, term)

class PcbPartsResultDialog(QDialog):
    def __init__(self, parent, term, results):
        super().__init__(parent)
        self.setWindowTitle(f"Résultats PCBParts pour '{term}'")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        container = QWidget()
        container_layout = QVBoxLayout(container)

        # SÉCURITÉ (V4.4.0) : les chaînes viennent d'un serveur DISTANT
        # (pcbparts.dev). QLabel interprète le rich text par défaut — une
        # réponse contenant du HTML pouvait truquer l'affichage. Tous les
        # labels de données sont désormais en texte brut.
        def _plain(text):
            lbl = QLabel(str(text))
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            return lbl
        
        for r in results:
            group = QGroupBox(f"{r.get('model', 'N/A')} ({r.get('manufacturer', 'N/A')})")
            g_layout = QFormLayout(group)
            
            g_layout.addRow("Fournisseur :", _plain("JLCPCB"))
            g_layout.addRow("LCSC :", _plain(r.get('lcsc', 'N/A')))
            g_layout.addRow("Package :", _plain(r.get('package', 'N/A')))
            g_layout.addRow("Prix :", _plain(f"${r.get('price', 'N/A')}"))
            g_layout.addRow("Stock :", _plain(r.get('stock', 'N/A')))
            
            desc_label = _plain(r.get('description', 'N/A'))
            desc_label.setWordWrap(True)
            g_layout.addRow("Description :", desc_label)
            
            specs = r.get('specs', {})
            if specs:
                table = QTableWidget(len(specs), 2)
                table.setHorizontalHeaderLabels(["Spécification", "Valeur"])
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                table.verticalHeader().setVisible(False)
                
                row = 0
                for k, v in specs.items():
                    table.setItem(row, 0, QTableWidgetItem(str(k)))
                    table.setItem(row, 1, QTableWidgetItem(str(v)))
                    row += 1
                
                # Hauteur dynamique pour ne pas trop prendre de place
                table.setFixedHeight(min(250, 35 + 30 * len(specs)))
                g_layout.addRow("Spécifications :", table)
                
            container_layout.addWidget(group)
            
        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

class MecaPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        
        self.meca_tab = QWidget()
        meca_layout = QVBoxLayout(self.meca_tab)
        meca_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- Toolbar Meca ---
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        
        toolbar_layout.addWidget(QLabel("🛠️ Outils CAO 3D :"))
        
        self.btn_view = QPushButton("👁️ Voir dans CQ-Editor")
        self.btn_view.clicked.connect(self.open_in_cq_editor)
        
        toolbar_layout.addWidget(self.btn_view)
        
        meca_layout.addLayout(toolbar_layout)
        
        self.tabs.addTab(self.meca_tab, "Outils Meca 3D")
        
        self.layout.addWidget(self.tabs)

    def open_in_cq_editor(self):
        from PyQt6.QtWidgets import QFileDialog
        import os
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un fichier à ouvrir dans CQ-Editor",
            "",
            "Fichiers CadQuery / STEP (*.py *.step);;Tous les fichiers (*.*)"
        )
        
        if not file_path:
            return
            
        try:
            self.main_window.add_system_message(f"Tentative d'ouverture de '{os.path.basename(file_path)}' dans CQ-Editor...")
            
            if file_path.lower().endswith('.step') or file_path.lower().endswith('.stp'):
                # Script autogénéré pour visualiser le STEP dans CQ-Editor
                # Écrit dans le PROJET, pas dans le dossier de l'application :
                # le fichier atterrissait à côté de ui.py et n'était jamais nettoyé.
                racine = getattr(self.main_window, "project_root", "") or os.getcwd()
                script_name = os.path.join(racine, "temp_viewer.py")
                script_content = f"""import cadquery as cq

# Script autogénéré pour visualiser le STEP dans CQ-Editor
shape = cq.importers.importStep(r'{file_path}')
if 'show_object' in locals():
    show_object(shape)
"""
                with open(script_name, "w", encoding="utf-8") as file:
                    file.write(script_content)
                cq_bin = resolve_external_binary("cq-editor")
                if not cq_bin:
                    raise FileNotFoundError("L'exécutable cq-editor est introuvable dans le PATH.")
                
                subprocess.Popen([cq_bin, script_name], env=hardened_subprocess_env())
            else:
                cq_bin = resolve_external_binary("cq-editor")
                if not cq_bin:
                    raise FileNotFoundError("L'exécutable cq-editor est introuvable dans le PATH.")
                    
                subprocess.Popen([cq_bin, file_path], env=hardened_subprocess_env())
                
        except FileNotFoundError:
            QMessageBox.critical(
                self, "Erreur",
                "La commande 'cq-editor' est introuvable. "
                "Assurez-vous que l'application est installée et accessible dans votre PATH."
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir CQ-Editor : {e}")


