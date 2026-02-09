#!/usr/bin/env bash
# oclw_bot: run unit, integration, regression, performance tests.
# Usage: ./scripts/run_tests.sh [pytest-args]
# Example: ./scripts/run_tests.sh -q
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH=.
python -m pytest tests/ -v --tb=short "$@"
