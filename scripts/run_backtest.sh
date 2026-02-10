#!/usr/bin/env bash
# oclw_bot: run backtest; report -> logs/oclw_bot_<ts>.log, data -> logs/json/run_<ts>.json
# Usage:
#   ./scripts/run_backtest.sh [config.yaml]
#   ./scripts/run_backtest.sh --config configs/xauusd.yaml --out artifacts/run_<ts>  # also for Telegram
set -e
cd "$(dirname "$0")/.."

CONFIG="configs/xauusd.yaml"
OUT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --config|-c) CONFIG="$2"; shift 2 ;;
    --out|-o)    OUT="$2";    shift 2 ;;
    *)           CONFIG="$1"; shift ;;
  esac
done

if [ -n "$OUT" ]; then
  python scripts/run_backtest_to_artifacts.py --config "$CONFIG" --out "$OUT"
else
  python scripts/run_backtest_to_artifacts.py --config "$CONFIG"
fi
