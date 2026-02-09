#!/usr/bin/env bash
# oclw_bot: run backtest with config.
# Usage: ./scripts/run_backtest.sh [config.yaml]
# Example: ./scripts/run_backtest.sh configs/xauusd.yaml
set -e
cd "$(dirname "$0")/.."
CONFIG="${1:-configs/xauusd.yaml}"
oclw_bot backtest --config "$CONFIG"
