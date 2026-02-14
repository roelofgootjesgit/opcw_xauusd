"""
Economic Calendar / News Filter for XAUUSD.

Provides no-trade zones around high-impact events (NFP, FOMC, CPI, etc.)
to prevent entries during extreme volatility.

Data sources:
  - ForexFactory calendar (CSV scraping)
  - Oanda Labs calendar API (when broker is configured)
  - Local cache fallback

For backtesting, uses cached historical calendar data.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
NEWS_CACHE_DIR = ROOT / "data" / "news_cache"

# Default no-trade zone configs per impact level
DEFAULT_NEWS_CONFIG = {
    "enabled": False,
    "high_impact": {
        "pre_minutes": 30,
        "post_minutes": 60,
        "action": "NO_TRADE",
    },
    "medium_impact": {
        "pre_minutes": 15,
        "post_minutes": 30,
        "action": "REDUCE_SIZE",
    },
    "low_impact": {
        "action": "NONE",
    },
    # Specific event overrides
    "event_overrides": {
        "FOMC": {"pre_minutes": 60, "post_minutes": 120, "action": "NO_TRADE"},
        "NFP": {"pre_minutes": 30, "post_minutes": 90, "action": "NO_TRADE"},
        "Non-Farm Payrolls": {"pre_minutes": 30, "post_minutes": 90, "action": "NO_TRADE"},
        "CPI": {"pre_minutes": 30, "post_minutes": 60, "action": "NO_TRADE"},
        "PPI": {"pre_minutes": 15, "post_minutes": 30, "action": "NO_TRADE"},
        "GDP": {"pre_minutes": 15, "post_minutes": 30, "action": "NO_TRADE"},
        "Fed Chair": {"pre_minutes": 30, "post_minutes": 60, "action": "NO_TRADE"},
        "Interest Rate": {"pre_minutes": 60, "post_minutes": 120, "action": "NO_TRADE"},
        "Jobless Claims": {"pre_minutes": 10, "post_minutes": 15, "action": "REDUCE_SIZE"},
        "PMI": {"pre_minutes": 10, "post_minutes": 15, "action": "REDUCE_SIZE"},
        "ISM": {"pre_minutes": 10, "post_minutes": 15, "action": "REDUCE_SIZE"},
    },
}

# Gold-relevant currencies and keywords
GOLD_RELEVANT_CURRENCIES = {"USD", "EUR", "GBP", "CHF", "JPY"}
GOLD_RELEVANT_KEYWORDS = [
    "fomc", "fed", "nfp", "non-farm", "payrolls", "cpi", "ppi", "gdp",
    "interest rate", "inflation", "unemployment", "jobless", "retail sales",
    "pmi", "ism", "gold", "treasury", "bond", "yield",
]


def _match_event_override(event_name: str, overrides: Dict) -> Optional[Dict]:
    """Check if event name matches any override (case-insensitive partial match)."""
    event_lower = event_name.lower()
    for key, config in overrides.items():
        if key.lower() in event_lower:
            return config
    return None


def _get_event_zone(
    event_time: datetime,
    impact: str,
    event_name: str,
    news_cfg: Dict,
) -> Tuple[datetime, datetime, str]:
    """
    Get no-trade zone (start, end, action) for a specific event.
    Returns (zone_start, zone_end, action).
    """
    overrides = news_cfg.get("event_overrides", DEFAULT_NEWS_CONFIG["event_overrides"])
    override = _match_event_override(event_name, overrides)

    if override:
        pre = override.get("pre_minutes", 30)
        post = override.get("post_minutes", 60)
        action = override.get("action", "NO_TRADE")
    elif impact.lower() == "high":
        cfg = news_cfg.get("high_impact", DEFAULT_NEWS_CONFIG["high_impact"])
        pre = cfg.get("pre_minutes", 30)
        post = cfg.get("post_minutes", 60)
        action = cfg.get("action", "NO_TRADE")
    elif impact.lower() == "medium":
        cfg = news_cfg.get("medium_impact", DEFAULT_NEWS_CONFIG["medium_impact"])
        pre = cfg.get("pre_minutes", 15)
        post = cfg.get("post_minutes", 30)
        action = cfg.get("action", "REDUCE_SIZE")
    else:
        return (event_time, event_time, "NONE")

    zone_start = event_time - timedelta(minutes=pre)
    zone_end = event_time + timedelta(minutes=post)
    return (zone_start, zone_end, action)


def is_in_no_trade_zone(
    timestamp: datetime,
    events_df: pd.DataFrame,
    news_cfg: Optional[Dict] = None,
) -> bool:
    """
    Check if a timestamp falls within any no-trade zone.
    Returns True if trading should be blocked.
    """
    cfg = news_cfg or DEFAULT_NEWS_CONFIG
    if not cfg.get("enabled", False):
        return False
    if events_df is None or events_df.empty:
        return False

    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")

    for _, event in events_df.iterrows():
        event_time = pd.Timestamp(event.get("datetime", event.get("time", None)))
        if event_time is None:
            continue
        if event_time.tzinfo is None:
            event_time = event_time.tz_localize("UTC")

        impact = str(event.get("impact", "low"))
        name = str(event.get("event", event.get("name", "")))

        zone_start, zone_end, action = _get_event_zone(event_time, impact, name, cfg)
        if zone_start.tzinfo is None:
            zone_start = zone_start.tz_localize("UTC")
        if zone_end.tzinfo is None:
            zone_end = zone_end.tz_localize("UTC")

        if action == "NO_TRADE" and zone_start <= ts <= zone_end:
            return True

    return False


def get_position_size_multiplier(
    timestamp: datetime,
    events_df: pd.DataFrame,
    news_cfg: Optional[Dict] = None,
) -> float:
    """
    Get position size multiplier based on news proximity.
    Returns 1.0 for normal, 0.5 for REDUCE_SIZE, 0.0 for NO_TRADE.
    """
    cfg = news_cfg or DEFAULT_NEWS_CONFIG
    if not cfg.get("enabled", False):
        return 1.0
    if events_df is None or events_df.empty:
        return 1.0

    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")

    min_multiplier = 1.0

    for _, event in events_df.iterrows():
        event_time = pd.Timestamp(event.get("datetime", event.get("time", None)))
        if event_time is None:
            continue
        if event_time.tzinfo is None:
            event_time = event_time.tz_localize("UTC")

        impact = str(event.get("impact", "low"))
        name = str(event.get("event", event.get("name", "")))

        zone_start, zone_end, action = _get_event_zone(event_time, impact, name, cfg)
        if zone_start.tzinfo is None:
            zone_start = zone_start.tz_localize("UTC")
        if zone_end.tzinfo is None:
            zone_end = zone_end.tz_localize("UTC")

        if zone_start <= ts <= zone_end:
            if action == "NO_TRADE":
                return 0.0
            elif action == "REDUCE_SIZE":
                min_multiplier = min(min_multiplier, 0.5)

    return min_multiplier


def nearest_event_minutes(
    timestamp: datetime,
    events_df: pd.DataFrame,
) -> Optional[float]:
    """Get minutes to nearest high/medium impact event. None if no events."""
    if events_df is None or events_df.empty:
        return None

    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")

    min_dist = None
    for _, event in events_df.iterrows():
        impact = str(event.get("impact", "low")).lower()
        if impact not in ("high", "medium"):
            continue
        event_time = pd.Timestamp(event.get("datetime", event.get("time", None)))
        if event_time is None:
            continue
        if event_time.tzinfo is None:
            event_time = event_time.tz_localize("UTC")
        dist = abs((ts - event_time).total_seconds()) / 60.0
        if min_dist is None or dist < min_dist:
            min_dist = dist

    return min_dist


def load_news_calendar(
    period_days: int = 90,
    cache_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Load economic calendar data from cache.
    Returns DataFrame with columns: datetime, event, impact, currency, actual, forecast, previous.

    For production, this should be populated by fetch_calendar_from_oanda() or
    fetch_calendar_from_forexfactory().
    """
    cache = cache_dir or NEWS_CACHE_DIR
    if not cache.exists():
        cache.mkdir(parents=True, exist_ok=True)
        logger.info("News cache directory created: %s", cache)
        return pd.DataFrame()

    # Try to load cached calendar files
    json_files = sorted(cache.glob("*.json"), reverse=True)
    if not json_files:
        logger.info("No cached news data found in %s", cache)
        return pd.DataFrame()

    all_events = []
    cutoff = datetime.now() - timedelta(days=period_days)

    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                all_events.extend(data)
            elif isinstance(data, dict) and "events" in data:
                all_events.extend(data["events"])
        except Exception as e:
            logger.warning("Failed to load news file %s: %s", f, e)

    if not all_events:
        return pd.DataFrame()

    df = pd.DataFrame(all_events)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
        df = df.dropna(subset=["datetime"])
        df = df[df["datetime"] >= pd.Timestamp(cutoff, tz="UTC")]

    return df


def save_news_events(events: List[Dict], filename: Optional[str] = None) -> Path:
    """Save news events to cache."""
    NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fname = filename or f"calendar_{datetime.now().strftime('%Y-%m-%d')}.json"
    path = NEWS_CACHE_DIR / fname
    path.write_text(json.dumps(events, indent=2, default=str), encoding="utf-8")
    logger.info("Saved %d news events to %s", len(events), path)
    return path


def fetch_calendar_from_oanda(
    account_id: str,
    token: str,
    environment: str = "practice",
    period_days: int = 30,
) -> pd.DataFrame:
    """
    Fetch economic calendar from Oanda Labs API.
    Requires oandapyV20 package and valid credentials.
    """
    try:
        import oandapyV20
        from oandapyV20.endpoints.forexlabs import Calendar

        client = oandapyV20.API(
            access_token=token,
            environment=environment,
        )
        params = {
            "instrument": "XAU_USD",
            "period": period_days * 86400,  # seconds
        }
        r = Calendar(params=params)
        response = client.request(r)

        events = []
        for item in response:
            events.append({
                "datetime": item.get("timestamp"),
                "event": item.get("title", ""),
                "impact": _map_oanda_impact(item.get("impact", 0)),
                "currency": item.get("currency", "USD"),
                "actual": item.get("actual"),
                "forecast": item.get("forecast"),
                "previous": item.get("previous"),
            })

        save_news_events(events)
        return pd.DataFrame(events)

    except ImportError:
        logger.warning("oandapyV20 not installed. Run: pip install oandapyV20")
        return pd.DataFrame()
    except Exception as e:
        logger.error("Failed to fetch Oanda calendar: %s", e)
        return pd.DataFrame()


def _map_oanda_impact(impact_val) -> str:
    """Map Oanda numeric impact to string."""
    if isinstance(impact_val, (int, float)):
        if impact_val >= 3:
            return "high"
        elif impact_val >= 2:
            return "medium"
        return "low"
    return str(impact_val).lower()
