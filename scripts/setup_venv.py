#!/usr/bin/env python3
"""
Setup venv en installeer oclw_bot met alle dependencies (inclusief yfinance).

Gebruik lokaal of op VPS (Linux/Windows):
  python scripts/setup_venv.py

Doet:
  - Maakt .venv aan als die nog niet bestaat
  - Installeert het project in de venv: pip install -e ".[yfinance]"
  - Kopieert .env.example naar .env als .env nog niet bestaat
"""
import os
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    root = project_root()
    venv_dir = root / ".venv"
    is_windows = os.name == "nt"
    scripts_dir = venv_dir / ("Scripts" if is_windows else "bin")
    # Windows: pip.exe; Linux: pip
    pip_name = "pip.exe" if is_windows else "pip"
    pip_exe = scripts_dir / pip_name
    if not pip_exe.exists():
        pip_exe = scripts_dir / "pip"  # fallback zonder .exe
    pip_cmd = str(pip_exe)

    print("[setup_venv] Project root:", root)

    # 1) Venv aanmaken
    if not venv_dir.exists():
        print("[setup_venv] Aanmaken .venv ...")
        r = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            cwd=root,
        )
        if r.returncode != 0:
            print("[setup_venv] Fout bij aanmaken venv.")
            return 1
        print("[setup_venv] .venv aangemaakt.")
    else:
        print("[setup_venv] .venv bestaat al.")

    if pip_exe.exists():
        install_cmd = [pip_cmd, "install", "-e", ".[yfinance]"]
    else:
        # Fallback: venv zonder pip.exe (bijv. --without-pip); gebruik python -m pip
        venv_python = scripts_dir / ("python.exe" if is_windows else "python")
        if not venv_python.exists():
            print("[setup_venv] Fout: pip noch python gevonden in venv:", scripts_dir)
            return 1
        install_cmd = [str(venv_python), "-m", "pip", "install", "-e", ".[yfinance]"]

    # 2) Project installeren (met yfinance)
    print("[setup_venv] Installeren: pip install -e \".[yfinance]\" ...")
    r = subprocess.run(
        install_cmd,
        cwd=root,
    )
    if r.returncode != 0:
        print("[setup_venv] Fout bij pip install.")
        return 1
    print("[setup_venv] Installatie klaar.")

    # 3) .env (optioneel)
    env_example = root / ".env.example"
    env_file = root / ".env"
    if env_example.exists() and not env_file.exists():
        import shutil
        shutil.copy(env_example, env_file)
        print("[setup_venv] .env aangemaakt uit .env.example (pas aan indien nodig).")
    elif not env_file.exists():
        print("[setup_venv] Geen .env.example gevonden; .env niet aangemaakt.")

    # 4) Volgende stappen
    activate_ps = ".\.venv\\Scripts\\Activate.ps1"
    activate_sh = "source .venv/bin/activate"
    activate = activate_ps if is_windows else activate_sh
    print()
    print("--- Volgende stappen ---")
    print("  Activeren venv:")
    print("    Windows (PowerShell):", activate_ps)
    print("    Linux/VPS:          ", activate_sh)
    print("  Daarna o.a.:")
    print("    python scripts/run_full_test.py")
    print("    oclw_bot fetch --days 30")
    print("    oclw_bot backtest --config configs/xauusd.yaml")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
