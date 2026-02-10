#!/usr/bin/env bash
# deploy_check.sh — Gate na git pull: venv + pip + pytest + make_report.
# Als tests of report falen, mag er niets automatisch getweakt worden.
# Usage: ./scripts/deploy_check.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# Ensure pyenv for non-interactive shells (Linux/VPS)
export PATH="${HOME:-/usr/local}/.pyenv/bin:$PATH"
if command -v pyenv >/dev/null 2>&1; then
  eval "$(pyenv init -)"
  eval "$(pyenv virtualenv-init -)"
  pyenv local "$(cat .python-version 2>/dev/null || true)" 2>/dev/null || true
fi

# Use venv (Windows: .venv, Linux: often .venv310 or .venv)
if [ -d .venv310 ]; then
  source .venv310/bin/activate
elif [ -d .venv ]; then
  if [ -f .venv/Scripts/activate ]; then
    source .venv/Scripts/activate
  else
    source .venv/bin/activate
  fi
fi

python --version
pip install -U pip setuptools wheel
pip install ".[dev,yfinance]"

# 1) Tests — gate: fail = exit 1
pytest

# 2) Report — tests + backtest, write reports/latest/
if [ -f scripts/make_report.py ]; then
  python scripts/make_report.py
fi

echo "[deploy_check] PASS: tests + report OK. Safe to let OpenClaw run backtests."
