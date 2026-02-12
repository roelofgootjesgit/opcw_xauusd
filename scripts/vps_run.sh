#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

DAYS="${1:-30}"  # default 30 dagen, override met: ./scripts/vps_run.sh 90
CONFIG="configs/xauusd.yaml"

# ensure pyenv for non-interactive shells
export PATH="$HOME/.pyenv/bin:$PATH"
if command -v pyenv >/dev/null 2>&1; then
  eval "$(pyenv init -)"
  eval "$(pyenv virtualenv-init -)" || true
  pyenv local "$(cat .python-version)"
fi

# Rebuild venv if missing or broken
if [ ! -f ".venv310/bin/activate" ]; then
  echo "[vps_run] .venv310 missing/broken -> rebuilding"
  rm -rf .venv310
  python -m venv .venv310
fi

source .venv310/bin/activate
python --version

pip install -U pip setuptools wheel
pip install ".[dev,yfinance]"

# Volledige test: fetch + backtest + tests + rapport
python scripts/run_full_test.py --days "$DAYS" --config "$CONFIG" --report
