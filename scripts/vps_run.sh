#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# ensure pyenv for non-interactive shells
export PATH="$HOME/.pyenv/bin:$PATH"
if command -v pyenv >/dev/null 2>&1; then
  eval "$(pyenv init -)"
  eval "$(pyenv virtualenv-init -)"
  pyenv local "$(cat .python-version)"
fi

# use the 3.10 venv
source .venv310/bin/activate

python --version
pip install -U pip setuptools wheel
pip install ".[dev,yfinance]"

pytest

# run report if present
if [ -f scripts/make_report.py ]; then
  python scripts/make_report.py
fi
