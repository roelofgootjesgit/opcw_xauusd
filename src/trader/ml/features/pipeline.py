"""
Feature extraction pipeline: runs all feature modules in order.
"""
from typing import Any, Dict

import pandas as pd

from src.trader.ml.features.market_structure import add_market_structure_features
from src.trader.ml.features.liquidity import add_liquidity_features
from src.trader.ml.features.technical import add_technical_features
from src.trader.ml.features.statistical import add_statistical_features


class FeatureExtractionPipeline:
    """
    Robust feature extraction pipeline:
    market structure -> liquidity -> technical -> statistical.
    """

    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}
        self._feature_columns: list[str] | None = None

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all features; store feature column names for later."""
        out = df.copy()
        out = add_market_structure_features(out, self.config.get("market_structure", {}))
        out = add_liquidity_features(out, self.config.get("liquidity", {}))
        out = add_technical_features(out, self.config.get("technical", {}))
        out = add_statistical_features(out, self.config.get("statistical", {}))
        self._feature_columns = [c for c in out.columns if c.startswith("feat_")]
        return out

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply same feature steps (e.g. on new data)."""
        return self.fit_transform(df)

    @property
    def feature_columns(self) -> list[str]:
        """Names of columns added by the pipeline."""
        if self._feature_columns is None:
            return []
        return self._feature_columns
