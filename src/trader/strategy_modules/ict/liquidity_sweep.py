"""Liquidity Sweep – ICT stop hunt then reversal."""
import pandas as pd
import numpy as np
from typing import Dict

from src.trader.strategy_modules.base import BaseModule


class LiquiditySweepModule(BaseModule):
    @property
    def name(self) -> str:
        return "Liquidity Sweep"

    @property
    def category(self) -> str:
        return "ict"

    @property
    def description(self) -> str:
        return "ICT stop hunts – fake breakouts before reversal"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "lookback_candles", "label": "Lookback", "type": "number", "default": 20, "min": 10, "max": 50},
                {"name": "sweep_threshold_pct", "label": "Sweep Threshold %", "type": "number", "default": 0.2, "min": 0.1, "max": 1.0},
                {"name": "reversal_candles", "label": "Reversal Window", "type": "number", "default": 3, "min": 1, "max": 5},
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        lookback = config.get("lookback_candles", 20)
        thresh = config.get("sweep_threshold_pct", 0.2) / 100.0
        rev_n = config.get("reversal_candles", 3)
        df["swing_high"] = df["high"].rolling(lookback, center=False).max().shift(1)
        df["swing_low"] = df["low"].rolling(lookback, center=False).min().shift(1)
        df["bullish_sweep"] = False
        df["bearish_sweep"] = False
        # Swept levels: the exact structure point that was swept (for SL anchoring)
        df["swept_low"] = np.nan
        df["swept_high"] = np.nan
        for i in range(lookback + rev_n, len(df)):
            sh, sl = df.iloc[i - 1]["swing_high"], df.iloc[i - 1]["swing_low"]
            if pd.isna(sh) or pd.isna(sl):
                continue
            h, l_ = df.iloc[i]["high"], df.iloc[i]["low"]
            if l_ <= sl * (1 - thresh):
                for j in range(i, min(i + rev_n + 1, len(df))):
                    if df.iloc[j]["high"] >= sl * (1 + thresh):
                        df.iloc[i, df.columns.get_loc("bullish_sweep")] = True
                        df.iloc[i, df.columns.get_loc("swept_low")] = sl
                        break
            if h >= sh * (1 + thresh):
                for j in range(i, min(i + rev_n + 1, len(df))):
                    if df.iloc[j]["low"] <= sh * (1 - thresh):
                        df.iloc[i, df.columns.get_loc("bearish_sweep")] = True
                        df.iloc[i, df.columns.get_loc("swept_high")] = sh
                        break
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("bullish_sweep", False))
        if direction == "SHORT":
            return bool(row.get("bearish_sweep", False))
        return False
