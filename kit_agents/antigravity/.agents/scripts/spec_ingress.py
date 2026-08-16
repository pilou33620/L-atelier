#!/usr/bin/env python3
"""
spec_ingress.py — Gestionnaire de contexte et d'historique pour l'agent Specifier & Translator.

Fonctions principales :
1. Maintient une fenêtre glissante FIFO des 2-3 derniers tours d'échanges
   (FR/EN) dans .agents/cache/conversation_window.json ou .claude/cache/conversation_window.json.
2. Génère un snapshot léger des fichiers du projet pour permettre la résolution
   exacte des chemins par l'agent sans hallucination.
3. Enregistre la spécification technique produite dans .agent_reports/spec_ingress.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def detecter_dossier_config(racine: Path | None = None) -> tuple[Path, str]:
    """Détecte si l'environnement actif est .agents (Antigravity) ou .claude (Claude Code)."""
    base = racine or RACINE
    if (base / ".claude").is_dir():
        return base / ".claude", "claude_code"
    return base / ".agents", "antigravity"


def chemin_cache_historique(racine: Path | None = None) -> Path:
    """Retourne le chemin du fichier JSON de cache de l'historique."""
    dossier, _ = detecter_dossier_config(racine)
    cache_dir = dossier / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "conversation_window.json"


def lire_historique(max_tours: int = 3, racine: Path | None = None) -> list[dict]:
    """Lit la liste des derniers échanges stockés dans le cache."""
    fichier = chemin_cache_historique(racine)
    if not fichier.is_file():
        return []
    try:
        data = json.loads(fichier.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data[-max_tours:]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def enregistrer_tour(prompt_fr: str, spec_en: str, max_tours: int = 3, racine: Path | None = None) -> list[dict]:
    """Ajoute un échange [prompt_fr, spec_en] dans la fenêtre glissante."""
    historique = lire_historique(max_tours=10, racine=racine)
    historique.append({
        "prompt_fr": prompt_fr.strip(),
        "spec_en": spec_en.strip()
    })
    # Conserver uniquement les max_tours derniers
    historique = historique[-max_tours:]
    
    fichier = chemin_cache_historique(racine)
    try:
        fichier.write_text(json.dumps(historique, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as err:
        print(f"[spec_ingress] Avertissement: impossible d'écrire l'historique : {err}", file=sys.stderr)
    return historique


def effacer_historique(racine: Path | None = None) -> None:
    """Réinitialise la mémoire conversationnelle."""
    fichier = chemin_cache_historique(racine)
    if fichier.is_file():
        try:
            fichier.unlink()
        except OSError:
            pass


def snapshot_fichiers_projet(racine: Path | None = None, max_fichiers: int = 150) -> list[str]:
    """Génère une liste allégée des fichiers du projet pour sensibiliser le specifier."""
    base = racine or RACINE
    ignores = {
        ".git", "__pycache__", ".pytest_cache", ".agent_reports",
        ".agent_backups", "cache", "graphify-out", ".venv", "venv",
        "node_modules", "dist", "build"
    }
    
    fichiers = []
    try:
        for racine_cur, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ignores and not d.startswith(".")]
            for f in sorted(files):
                if f.startswith(".") or f.endswith((".pyc", ".png", ".jpg", ".step", ".bak")):
                    continue
                p = (Path(racine_cur) / f).relative_to(base).as_posix()
                fichiers.append(p)
                if len(fichiers) >= max_fichiers:
                    break
            if len(fichiers) >= max_fichiers:
                break
    except OSError:
        pass
    return sorted(fichiers)


def sauvegarder_spec_ingress(spec_markdown: str, racine: Path | None = None) -> Path:
    """Enregistre le markdown de spécification dans .agent_reports/spec_ingress.md."""
    base = racine or RACINE
    reports_dir = base / ".agent_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    cible = reports_dir / "spec_ingress.md"
    cible.write_text(spec_markdown.strip() + "\n", encoding="utf-8")
    return cible


def formater_prompt_specifier(prompt_fr: str, racine: Path | None = None) -> str:
    """Assemble le prompt d'entrée complet (historique + snapshot + prompt FR)."""
    base = racine or RACINE
    historique = lire_historique(max_tours=3, racine=base)
    fichiers = snapshot_fichiers_projet(racine=base)
    
    morceaux = []
    if historique:
        morceaux.append("## RECENT CONVERSATION HISTORY (Last turns)")
        for i, tour in enumerate(historique, 1):
            morceaux.append(f"### Turn {i}")
            morceaux.append(f"**User (FR)**: {tour.get('prompt_fr', '')}")
            morceaux.append(f"**Previous Spec (EN)**:\n{tour.get('spec_en', '')}\n")
    
    if fichiers:
        morceaux.append("## PROJECT FILES SNAPSHOT (Real files on disk)")
        morceaux.append("```text")
        morceaux.extend(fichiers[:100])
        morceaux.append("```\n")
    
    morceaux.append("## CURRENT USER REQUEST (FR)")
    morceaux.append(prompt_fr.strip())
    
    return "\n".join(morceaux)


def auto_test():
    """Vérification unitaire du module spec_ingress."""
    print("Test de spec_ingress.py...")
    temp_racine = Path(os.environ.get("TEMP", "/tmp")) / "latelier_test_spec_ingress"
    temp_racine.mkdir(parents=True, exist_ok=True)
    
    try:
        # 1. Test historique vide
        effacer_historique(temp_racine)
        assert lire_historique(racine=temp_racine) == []
        
        # 2. Test enregistrement tour FIFO
        enregistrer_tour("Demande 1", "Spec 1", max_tours=2, racine=temp_racine)
        enregistrer_tour("Demande 2", "Spec 2", max_tours=2, racine=temp_racine)
        enregistrer_tour("Demande 3", "Spec 3", max_tours=2, racine=temp_racine)
        
        h = lire_historique(max_tours=2, racine=temp_racine)
        assert len(h) == 2, f"Attendu 2 tours, obtenu {len(h)}"
        assert h[0]["prompt_fr"] == "Demande 2"
        assert h[1]["prompt_fr"] == "Demande 3"
        
        # 3. Test sauvegarde spec_ingress
        spec_test = "# TASK: Test Ingress\n## 1. Objective\nValidate pipeline."
        cible = sauvegarder_spec_ingress(spec_test, racine=temp_racine)
        assert cible.is_file()
        assert "# TASK: Test Ingress" in cible.read_text(encoding="utf-8")
        
        # 4. Test formatage prompt
        prompt_formate = formater_prompt_specifier("Nouvelle demande FR", racine=temp_racine)
        assert "Demande 3" in prompt_formate
        assert "Nouvelle demande FR" in prompt_formate
        
        print("[OK] Tous les tests unitaires de spec_ingress.py ont reussi.")
        return 0
    finally:
        # Nettoyage
        import shutil
        if temp_racine.exists():
            shutil.rmtree(temp_racine, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Gestionnaire d'entrée Specifier & Translator")
    parser.add_argument("--test", action="store_true", help="Lance l'auto-test du script")
    parser.add_argument("--history", action="store_true", help="Affiche l'historique des derniers tours")
    parser.add_argument("--snapshot", action="store_true", help="Affiche la liste des fichiers du projet")
    parser.add_argument("--clear-history", action="store_true", help="Efface la mémoire conversationnelle")
    parser.add_argument("--record", action="store_true", help="Enregistre un tour (nécessite --fr et --en)")
    parser.add_argument("--fr", type=str, default="", help="Texte de la demande en français")
    parser.add_argument("--en", type=str, default="", help="Spécification anglaise produite")
    parser.add_argument("--save-spec", type=str, default="", help="Enregistre le markdown dans .agent_reports/spec_ingress.md")
    
    args = parser.parse_args()
    
    if args.test:
        return auto_test()
        
    if args.clear_history:
        effacer_historique()
        print("Mémoire conversationnelle réinitialisée.")
        return 0
        
    if args.history:
        h = lire_historique()
        print(json.dumps(h, indent=2, ensure_ascii=False))
        return 0
        
    if args.snapshot:
        fichiers = snapshot_fichiers_projet()
        print("\n".join(fichiers))
        return 0
        
    if args.record and args.fr and args.en:
        enregistrer_tour(args.fr, args.en)
        print("Tour enregistré.")
        return 0
        
    if args.save_spec:
        cible = sauvegarder_spec_ingress(args.save_spec)
        print(f"Spécification enregistrée dans {cible}")
        return 0
        
    if args.fr:
        print(formater_prompt_specifier(args.fr))
        return 0
        
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
