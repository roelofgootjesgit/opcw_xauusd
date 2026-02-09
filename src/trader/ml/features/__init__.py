"""
Feature engineering for ML-based strategy optimization.

- pipeline: FeatureExtractionPipeline
- market_structure: Swing structure, break of structure, higher highs/lows
- liquidity: Sweep indicators, liquidity zones
- technical: ATR, EMA, momentum
- statistical: Volatility, returns distribution, rolling stats
"""
from src.trader.ml.features.pipeline import FeatureExtractionPipeline

__all__ = ["FeatureExtractionPipeline"]
