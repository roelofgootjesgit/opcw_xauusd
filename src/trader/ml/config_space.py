"""
Probabilistic configuration space for strategy parameters.
Supports uniform and normal distributions; sampling for Bayesian / genetic search.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Literal

import numpy as np


DistributionKind = Literal["uniform", "normal", "loguniform"]


def get_default_config_space() -> Dict[str, Any]:
    """
    Default probabilistic configuration space for SQE + backtest params.
    Matches strategy and backtest engine knobs.
    """
    return {
        "backtest": {
            "tp_r": {"distribution": "uniform", "min": 1.5, "max": 3.0},
            "sl_r": {"distribution": "uniform", "min": 0.5, "max": 2.0},
        },
        "strategy": {
            "liquidity_sweep": {
                "lookback_candles": {"distribution": "uniform", "min": 10, "max": 50},
                "sweep_threshold_pct": {"distribution": "uniform", "min": 0.1, "max": 1.0},
                "reversal_candles": {"distribution": "uniform", "min": 1, "max": 5},
            },
            "displacement": {
                "min_body_pct": {"distribution": "uniform", "min": 50, "max": 90},
                "min_candles": {"distribution": "uniform", "min": 2, "max": 5},
                "min_move_pct": {"distribution": "uniform", "min": 0.5, "max": 3.0},
            },
            "fair_value_gaps": {
                "min_gap_pct": {"distribution": "uniform", "min": 0.2, "max": 1.0},
                "validity_candles": {"distribution": "uniform", "min": 20, "max": 80},
            },
            "market_structure_shift": {
                "swing_lookback": {"distribution": "uniform", "min": 3, "max": 10},
                "break_threshold_pct": {"distribution": "normal", "mu": 0.2, "sigma": 0.05, "min": 0.05, "max": 0.5},
            },
            "use_mss": {"distribution": "choice", "choices": [True, False]},
        },
        "entry_conditions": {
            "liquidity_sweep_threshold": {"distribution": "normal", "mu": 0.2, "sigma": 0.05},
            "market_structure_sensitivity": {"distribution": "normal", "mu": 0.5, "sigma": 0.1},
        },
    }


def _sample_one(spec: Dict[str, Any], rng: np.random.Generator) -> Any:
    dist = spec.get("distribution", "uniform")
    if dist == "uniform":
        lo, hi = spec["min"], spec["max"]
        return float(rng.uniform(lo, hi))
    if dist == "loguniform":
        lo, hi = spec["min"], spec["max"]
        return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
    if dist == "normal":
        mu, sigma = spec["mu"], spec["sigma"]
        x = float(rng.normal(mu, sigma))
        if "min" in spec:
            x = max(x, spec["min"])
        if "max" in spec:
            x = min(x, spec["max"])
        return x
    if dist == "choice":
        return rng.choice(spec["choices"]).item()
    return spec.get("default", 0.0)


def _sample_nested(
    space: Dict[str, Any],
    rng: np.random.Generator,
    base_cfg: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Recursively sample; leaves are distribution specs."""
    out = {} if base_cfg is None else copy.deepcopy(base_cfg)
    for k, v in space.items():
        if isinstance(v, dict):
            if "distribution" in v:
                out[k] = _sample_one(v, rng)
            else:
                out[k] = _sample_nested(
                    v,
                    rng,
                    base_cfg.get(k) if isinstance(base_cfg, dict) else None,
                )
        else:
            out[k] = v
    return out


def sample_config(
    config_space: Dict[str, Any],
    base_config: Dict[str, Any] | None = None,
    rng: np.random.Generator | None = None,
) -> Dict[str, Any]:
    """
    Sample a full configuration from the probabilistic config space.
    Returns a flat-ish config that can be merged into run_backtest(cfg):
    { "backtest": { "tp_r", "sl_r" }, "strategy": { ... } }
    """
    rng = rng or np.random.default_rng()
    sampled = _sample_nested(config_space, rng, base_config)

    # Ensure numeric strategy params are valid (integers where expected)
    strategy = sampled.get("strategy", {})
    for module_name, params in strategy.items():
        if module_name == "use_mss":
            continue
        if not isinstance(params, dict):
            continue
        for key, val in params.items():
            if key in ("lookback_candles", "reversal_candles", "min_candles", "validity_candles", "swing_lookback"):
                if isinstance(val, (int, float)):
                    strategy[module_name][key] = int(np.clip(round(val), 1, 500))

    return sampled


def config_to_backtest_cfg(sampled: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge sampled config into a full backtest config (symbol, data, backtest, strategy).
    """
    merged = copy.deepcopy(base)
    if "backtest" in sampled:
        merged.setdefault("backtest", {}).update(sampled["backtest"])
    if "strategy" in sampled:
        merged.setdefault("strategy", {}).update(sampled["strategy"])
    return merged
