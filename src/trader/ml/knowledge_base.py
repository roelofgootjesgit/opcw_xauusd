"""
Meta-learning: configuration genealogy, regime tagging, knowledge base of successful configs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.trader.ml.config_space import sample_config


class StrategyKnowledgeBase:
    """
    Tracks configuration genealogy, optional regime labels, and stores
    successful strategy configurations for transfer learning.
    """

    def __init__(
        self,
        storage_path: Path | str | None = None,
        max_successful: int = 100,
    ):
        self.storage_path = Path(storage_path) if storage_path else None
        self.max_successful = max_successful
        self.genealogy: List[Dict[str, Any]] = []
        self.successful_configs: List[Dict[str, Any]] = []
        self.regime_cache: Dict[str, List[Dict[str, Any]]] = {}

    def record_evaluation(
        self,
        config: Dict[str, Any],
        reward: float,
        metrics: Dict[str, Any],
        parent_id: Optional[str] = None,
        regime: Optional[str] = None,
    ) -> str:
        """
        Record a configuration evaluation with optional parent (genealogy) and regime.
        Returns an id for this record.
        """
        import uuid

        record_id = str(uuid.uuid4())[:8]
        entry = {
            "id": record_id,
            "config": config,
            "reward": reward,
            "metrics": metrics,
            "parent_id": parent_id,
            "regime": regime,
        }
        self.genealogy.append(entry)

        if reward > 0 and (not self.successful_configs or reward >= min(c["reward"] for c in self.successful_configs)):
            self.successful_configs.append({"id": record_id, "config": config, "reward": reward, "metrics": metrics})
            self.successful_configs.sort(key=lambda x: x["reward"], reverse=True)
            self.successful_configs = self.successful_configs[: self.max_successful]

        if regime:
            self.regime_cache.setdefault(regime, []).append(entry)

        return record_id

    def get_best_for_regime(self, regime: str) -> Dict[str, Any] | None:
        """Return best config for a given regime if available."""
        entries = self.regime_cache.get(regime, [])
        if not entries:
            return None
        best = max(entries, key=lambda x: x["reward"])
        return best.get("config")

    def get_top_configs(self, n: int = 5) -> List[Dict[str, Any]]:
        """Return top n successful configs (config dicts)."""
        return [c["config"] for c in self.successful_configs[:n]]

    def save(self, path: Path | str | None = None) -> None:
        """Persist genealogy and successful configs to JSON."""
        path = path or self.storage_path
        if not path:
            return
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "genealogy_len": len(self.genealogy),
            "successful_configs": self.successful_configs,
            "regimes": list(self.regime_cache.keys()),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def load(self, path: Path | str | None = None) -> None:
        """Load from JSON (successful_configs and regime keys; genealogy not fully restored)."""
        path = path or self.storage_path
        if not path or not Path(path).exists():
            return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.successful_configs = data.get("successful_configs", [])
